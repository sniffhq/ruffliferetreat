from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user
from app import db
from app.models import Pet, Appointment, ServiceType, VaccinationRecord
from werkzeug.utils import secure_filename
from datetime import datetime
import os
import logging

logger = logging.getLogger(__name__)

bp = Blueprint('customer', __name__, url_prefix='/customer')

def allowed_file(filename):
    ALLOWED_EXTENSIONS = {'pdf', 'png', 'jpg', 'jpeg', 'gif'}
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@bp.route('/onboarding', methods=['GET', 'POST'])
@login_required
def onboarding():
    if current_user.onboarding_complete:
        return redirect(url_for('customer.dashboard'))
    
    if request.method == 'POST':
        try:
            # Update user profile
            current_user.address = request.form.get('address')
            current_user.city = request.form.get('city')
            current_user.state = request.form.get('state')
            current_user.zip_code = request.form.get('zip_code')
            current_user.emergency_contact_name = request.form.get('emergency_contact_name')
            current_user.emergency_contact_phone = request.form.get('emergency_contact_phone')
            current_user.how_heard = request.form.get('how_heard')
            current_user.preferences = request.form.get('preferences')
            
            # Create pet
            pet = Pet(
                user_id=current_user.id,
                name=request.form.get('pet_name'),
                breed=request.form.get('pet_breed'),
                age=request.form.get('pet_age'),
                weight=request.form.get('pet_weight'),
                gender=request.form.get('pet_gender'),
                spayed_neutered=request.form.get('spayed_neutered') == 'yes',
                microchipped=request.form.get('microchipped') == 'yes',
                microchip_number=request.form.get('microchip_number'),
                vet_name=request.form.get('vet_name'),
                vet_phone=request.form.get('vet_phone'),
                medical_notes=request.form.get('pet_medical_notes')
            )
            
            # Handle pet photo upload
            if 'pet_photo' in request.files:
                file = request.files['pet_photo']
                if file and file.filename and allowed_file(file.filename):
                    filename = secure_filename(f"pet_{current_user.id}_{pet.name}_{file.filename}")
                    filepath = os.path.join('app/static/uploads', filename)
                    file.save(filepath)
                    pet.photo_path = filename
            
            db.session.add(pet)
            db.session.flush()  # Flush to get pet.id without committing

            current_user.onboarding_complete = True
            if request.form.get('waiver_accepted') == '1':
                from datetime import datetime as _dt
                current_user.waiver_accepted    = True
                current_user.waiver_accepted_at = _dt.now()
            db.session.commit()

            flash(f'Welcome to Ruff Life Retreat! {pet.name} has been added to your account. Please bring vaccination records (Bordetella, Rabies, DHPP) to your first visit.', 'success')
            return redirect(url_for('customer.dashboard'))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Error during onboarding: {str(e)}', 'danger')
            return render_template('customer/onboarding.html')
    
    return render_template('customer/onboarding.html')

@bp.route('/dashboard')
@login_required
def dashboard():
    if not current_user.onboarding_complete:
        return redirect(url_for('customer.onboarding'))

    from app.models import Appointment, DaycareEnrollment, DaycareAttendance, ReportCard, ServiceBlock, Boarding, CustomerPhoto
    from datetime import date, timedelta
    import json

    today = date.today()

    pets = Pet.query.filter_by(user_id=current_user.id, is_active=True).all()

    # Upcoming appointments — show all pending and confirmed
    # For boarding: hide only if the boarding stay is already completed
    completed_boarding_pet_dates = {
        (b.pet_id, b.check_in_date) for b in Boarding.query
        .join(Pet, Boarding.pet_id == Pet.id)
        .filter(Pet.user_id == current_user.id, Boarding.status == 'completed')
        .all()
    }
    all_upcoming = (Appointment.query
        .filter_by(user_id=current_user.id)
        .filter(Appointment.appointment_date >= today)
        .filter(Appointment.status.in_(['pending', 'confirmed']))
        .order_by(Appointment.appointment_date.asc())
        .all())
    upcoming_appointments = [
        a for a in all_upcoming
        if not (a.service_type and 'boarding' in a.service_type.name.lower()
                and (a.pet_id, a.appointment_date) in completed_boarding_pet_dates)
    ]

    past_appointments = (Appointment.query
        .filter_by(user_id=current_user.id)
        .filter(db.or_(
            Appointment.appointment_date < today,
            Appointment.status.in_(['completed', 'cancelled'])
        ))
        .order_by(Appointment.appointment_date.desc())
        .limit(10).all())

    upcoming_boarding = (Boarding.query
        .join(Pet, Boarding.pet_id == Pet.id)
        .filter(Pet.user_id == current_user.id, Boarding.status == 'active',
                Boarding.check_out_date >= today)
        .order_by(Boarding.check_in_date.asc()).all())

    past_boarding = (Boarding.query
        .join(Pet, Boarding.pet_id == Pet.id)
        .filter(Pet.user_id == current_user.id, Boarding.status == 'completed')
        .order_by(Boarding.check_out_date.desc()).limit(10).all())

    enrollments = (DaycareEnrollment.query
        .join(Pet, DaycareEnrollment.pet_id == Pet.id)
        .filter(Pet.user_id == current_user.id, DaycareEnrollment.active == True)
        .all())

    pet_ids = [p.id for p in pets]
    report_cards = (ReportCard.query
        .filter(ReportCard.pet_id.in_(pet_ids))
        .filter(ReportCard.sent_at.isnot(None))
        .order_by(ReportCard.card_date.desc())
        .limit(20).all())

    blocks = (ServiceBlock.query
        .filter(ServiceBlock.end_date >= today,
                ServiceBlock.start_date <= today + timedelta(days=90))
        .order_by(ServiceBlock.start_date.asc()).all())

    import calendar as cal_mod
    cal_mod.setfirstweekday(6)  # 6 = Sunday, matches Su/Mo/Tu/We/Th/Fr/Sa headers
    months = []
    for offset in range(3):
        m = (today.month - 1 + offset) % 12 + 1
        y = today.year + ((today.month - 1 + offset) // 12)
        months.append({'year': y, 'month': m,
                       'name': cal_mod.month_name[m],
                       'weeks': cal_mod.monthcalendar(y, m)})

    blocked_dates = set()
    for b in blocks:
        d = b.start_date
        while d <= b.end_date:
            blocked_dates.add(d.isoformat())
            d += timedelta(days=1)

    customer_photos = (CustomerPhoto.query
        .filter_by(user_id=current_user.id)
        .order_by(CustomerPhoto.uploaded_at.desc())
        .all())

    from datetime import timedelta as _td
    return render_template('customer/dashboard.html',
                           timedelta=_td,
                           pets=pets,
                           upcoming_appointments=upcoming_appointments,
                           past_appointments=past_appointments,
                           upcoming_boarding=upcoming_boarding,
                           past_boarding=past_boarding,
                           enrollments=enrollments,
                           report_cards=report_cards,
                           blocks=blocks,
                           months=months,
                           blocked_dates=json.dumps(list(blocked_dates)),
                           customer_photos=customer_photos,
                           today=today)


@bp.route('/my-photos')
@login_required
def my_photos():
    """Customer-facing read-only photo gallery."""
    from app.models import CustomerPhoto
    photos = (CustomerPhoto.query
              .filter_by(user_id=current_user.id)
              .order_by(CustomerPhoto.uploaded_at.desc())
              .all())
    return render_template('customer/my_photos.html', photos=photos)


@bp.route('/profile/update', methods=['POST'])
@login_required
def update_profile():
    """Customer updates their own basic info."""
    current_user.first_name = request.form.get('first_name', '').strip() or current_user.first_name
    current_user.last_name  = request.form.get('last_name', '').strip() or current_user.last_name
    current_user.phone      = request.form.get('phone', '').strip() or None
    current_user.address    = request.form.get('address', '').strip() or None
    current_user.city       = request.form.get('city', '').strip() or None
    current_user.state      = request.form.get('state', '').strip() or None
    current_user.zip_code   = request.form.get('zip_code', '').strip() or None
    current_user.sms_opt_in = request.form.get('sms_opt_in') == '1'
    db.session.commit()
    flash('Profile updated successfully.', 'success')
    return redirect(url_for('customer.dashboard') + '#profile')

@bp.route('/pets')
@login_required
def pets():
    if not current_user.onboarding_complete:
        return redirect(url_for('customer.onboarding'))
    pets = Pet.query.filter_by(user_id=current_user.id).all()
    return render_template('customer/pets.html', pets=pets)

@bp.route('/pets/add', methods=['GET', 'POST'])
@login_required
def add_pet():
    if not current_user.onboarding_complete:
        return redirect(url_for('customer.onboarding'))
        
    if request.method == 'POST':
        try:
            pet = Pet(
                user_id=current_user.id,
                name=request.form.get('name'),
                breed=request.form.get('breed'),
                age=request.form.get('age'),
                weight=request.form.get('weight'),
                gender=request.form.get('gender'),
                spayed_neutered=request.form.get('spayed_neutered') == 'yes',
                microchipped=request.form.get('microchipped') == 'yes',
                microchip_number=request.form.get('microchip_number'),
                vet_name=request.form.get('vet_name'),
                vet_phone=request.form.get('vet_phone'),
                medical_notes=request.form.get('medical_notes')
            )
            
            if 'photo' in request.files:
                file = request.files['photo']
                if file and file.filename and allowed_file(file.filename):
                    filename = secure_filename(f"pet_{current_user.id}_{pet.name}_{file.filename}")
                    filepath = os.path.join('app/static/uploads', filename)
                    file.save(filepath)
                    pet.photo_path = filename
            
            if 'vaccination_record' in request.files:
                file = request.files['vaccination_record']
                if file and file.filename and allowed_file(file.filename):
                    filename = secure_filename(f"vaccine_{current_user.id}_{pet.name}_{file.filename}")
                    filepath = os.path.join('app/static/uploads', filename)
                    file.save(filepath)
                    pet.vaccination_record_path = filename
            
            db.session.add(pet)
            db.session.flush()  # Flush to get pet.id without committing
            
            # ========== NEW: Handle vaccination records ==========
            vaccine_names = request.form.getlist('vaccine_name[]')
            vaccine_dates = request.form.getlist('vaccination_date[]')
            vaccine_expirations = request.form.getlist('expiration_date[]')
            vaccine_vets = request.form.getlist('veterinarian[]')
            vaccine_clinics = request.form.getlist('clinic_name[]')
            vaccine_lots = request.form.getlist('lot_number[]')
            vaccine_notes = request.form.getlist('vaccine_notes[]')
            
            # Create VaccinationRecord entries
            for i in range(len(vaccine_names)):
                if vaccine_names[i] and vaccine_dates[i] and vaccine_expirations[i]:
                    # Handle "Other" vaccine name
                    vaccine_name = vaccine_names[i]
                    if vaccine_name == 'Other' and i < len(request.form.getlist('other_vaccine_name[]')):
                        other_names = request.form.getlist('other_vaccine_name[]')
                        if i < len(other_names) and other_names[i]:
                            vaccine_name = other_names[i]
                    
                    vaccination = VaccinationRecord(
                        pet_id=pet.id,
                        vaccine_name=vaccine_name,
                        vaccination_date=datetime.strptime(vaccine_dates[i], '%Y-%m-%d').date(),
                        expiration_date=datetime.strptime(vaccine_expirations[i], '%Y-%m-%d').date(),
                        veterinarian=vaccine_vets[i] if i < len(vaccine_vets) else None,
                        clinic_name=vaccine_clinics[i] if i < len(vaccine_clinics) else None,
                        lot_number=vaccine_lots[i] if i < len(vaccine_lots) else None,
                        notes=vaccine_notes[i] if i < len(vaccine_notes) else None
                    )
                    db.session.add(vaccination)
            # ========== END NEW CODE ==========
            
            db.session.commit()
            flash(f'{pet.name} has been added successfully with vaccination records!', 'success')
            return redirect(url_for('customer.pets'))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Error adding pet: {str(e)}', 'danger')
            
    return render_template('customer/add_pet.html')

@bp.route('/pets/<int:pet_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_pet(pet_id):
    if not current_user.onboarding_complete:
        return redirect(url_for('customer.onboarding'))
    
    pet = Pet.query.get_or_404(pet_id)
    
    # Make sure the pet belongs to the current user
    if pet.user_id != current_user.id:
        flash('You can only edit your own pets.', 'danger')
        return redirect(url_for('customer.pets'))
    
    if request.method == 'POST':
        try:
            # Update basic info
            pet.name = request.form.get('name')
            pet.breed = request.form.get('breed')
            pet.age = request.form.get('age')
            pet.weight = request.form.get('weight')
            pet.gender = request.form.get('gender')
            pet.spayed_neutered = request.form.get('spayed_neutered') == 'yes'
            pet.microchipped = request.form.get('microchipped') == 'yes'
            pet.microchip_number = request.form.get('microchip_number')
            pet.vet_name = request.form.get('vet_name')
            pet.vet_phone = request.form.get('vet_phone')
            pet.medical_notes = request.form.get('medical_notes')
            
            # Handle photo upload
            if 'photo' in request.files:
                file = request.files['photo']
                if file and file.filename and allowed_file(file.filename):
                    # Delete old photo if exists
                    if pet.photo_path:
                        old_photo = os.path.join('app/static/uploads', pet.photo_path)
                        if os.path.exists(old_photo):
                            try:
                                os.remove(old_photo)
                            except:
                                pass
                    
                    # Save new photo
                    filename = secure_filename(f"pet_{current_user.id}_{pet.name}_{file.filename}")
                    filepath = os.path.join('app/static/uploads', filename)
                    file.save(filepath)
                    pet.photo_path = filename
            
            # Handle vaccine record upload
            if 'vaccination_record' in request.files:
                file = request.files['vaccination_record']
                if file and file.filename and allowed_file(file.filename):
                    # Delete old record if exists
                    if pet.vaccination_record_path:
                        old_record = os.path.join('app/static/uploads', pet.vaccination_record_path)
                        if os.path.exists(old_record):
                            try:
                                os.remove(old_record)
                            except:
                                pass
                    
                    # Save new record
                    filename = secure_filename(f"vaccine_{current_user.id}_{pet.name}_{file.filename}")
                    filepath = os.path.join('app/static/uploads', filename)
                    file.save(filepath)
                    pet.vaccination_record_path = filename
            
            # ========== NEW: Handle vaccination records (for edit) ==========
            vaccine_names = request.form.getlist('vaccine_name[]')
            vaccine_dates = request.form.getlist('vaccination_date[]')
            vaccine_expirations = request.form.getlist('expiration_date[]')
            vaccine_vets = request.form.getlist('veterinarian[]')
            vaccine_clinics = request.form.getlist('clinic_name[]')
            vaccine_lots = request.form.getlist('lot_number[]')
            vaccine_notes = request.form.getlist('vaccine_notes[]')
            
            # Only add new vaccination records if data is provided
            for i in range(len(vaccine_names)):
                if vaccine_names[i] and vaccine_dates[i] and vaccine_expirations[i]:
                    # Handle "Other" vaccine name
                    vaccine_name = vaccine_names[i]
                    if vaccine_name == 'Other' and i < len(request.form.getlist('other_vaccine_name[]')):
                        other_names = request.form.getlist('other_vaccine_name[]')
                        if i < len(other_names) and other_names[i]:
                            vaccine_name = other_names[i]
                    
                    vaccination = VaccinationRecord(
                        pet_id=pet.id,
                        vaccine_name=vaccine_name,
                        vaccination_date=datetime.strptime(vaccine_dates[i], '%Y-%m-%d').date(),
                        expiration_date=datetime.strptime(vaccine_expirations[i], '%Y-%m-%d').date(),
                        veterinarian=vaccine_vets[i] if i < len(vaccine_vets) else None,
                        clinic_name=vaccine_clinics[i] if i < len(vaccine_clinics) else None,
                        lot_number=vaccine_lots[i] if i < len(vaccine_lots) else None,
                        notes=vaccine_notes[i] if i < len(vaccine_notes) else None
                    )
                    db.session.add(vaccination)
            # ========== END NEW CODE ==========
            
            db.session.commit()
            flash(f'{pet.name} has been updated successfully!', 'success')
            return redirect(url_for('customer.pets'))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Error updating pet: {str(e)}', 'danger')
    
    from datetime import date
    return render_template('customer/edit_pet.html', pet=pet, today=date.today())

@bp.route('/book', methods=['GET', 'POST'])
@login_required
def book_appointment():
    if not current_user.onboarding_complete:
        return redirect(url_for('customer.onboarding'))
        
    pets = Pet.query.filter_by(user_id=current_user.id).all()
    services = ServiceType.query.filter(
        ServiceType.name.ilike('%boarding%')
    ).all()

    # Build set of blocked dates — boarding service blocks only
    from app.models import ServiceBlock, ServiceType as _ST
    from datetime import timedelta
    import json as _json
    today = datetime.now().date()

    _boarding_svc = _ST.query.filter(_ST.name.ilike('%boarding%')).first()
    future_blocks = (ServiceBlock.query
        .filter(ServiceBlock.end_date >= today)
        .filter(ServiceBlock.service_type_id == _boarding_svc.id if _boarding_svc else False)
        .order_by(ServiceBlock.start_date.asc()).all()) if _boarding_svc else []

    # Build a flat set of all individually blocked date strings for the JS date picker
    blocked_dates = set()
    for b in future_blocks:
        d = b.start_date
        while d <= b.end_date:
            blocked_dates.add(d.isoformat())
            d += timedelta(days=1)

    blocked_dates_json = _json.dumps(sorted(blocked_dates))

    if request.method == 'POST':
        try:
            date_str          = request.form.get('appointment_date')
            time_str          = request.form.get('appointment_time', '08:00')
            checkout_date_str = request.form.get('checkout_date', '').strip()
            service_type_id   = request.form.get('service_type_id')
            pet_ids           = request.form.getlist('pet_ids')

            if not pet_ids:
                flash('Please select at least one pet.', 'danger')
                return redirect(url_for('customer.book_appointment'))

            appointment_date = datetime.strptime(date_str, '%Y-%m-%d').date()

            # Server-side block validation — can't be bypassed by disabling JS
            if date_str in blocked_dates:
                flash('The selected check-in date is unavailable due to a scheduled closure. Please choose a different date.', 'danger')
                return redirect(url_for('customer.book_appointment'))

            if checkout_date_str and checkout_date_str in blocked_dates:
                flash('The selected check-out date is unavailable due to a scheduled closure. Please choose a different date.', 'danger')
                return redirect(url_for('customer.book_appointment'))

            # Also check if the stay spans a blocked date
            if checkout_date_str:
                checkout_date = datetime.strptime(checkout_date_str, '%Y-%m-%d').date()
                d = appointment_date
                while d <= checkout_date:
                    if d.isoformat() in blocked_dates:
                        flash(f'Your requested stay includes {d.strftime("%B %d")}, which falls within a scheduled closure. Please adjust your dates.', 'danger')
                        return redirect(url_for('customer.book_appointment'))
                    d += timedelta(days=1)

            appointment_time = datetime.strptime(time_str, '%H:%M').time()
            start_datetime   = datetime.combine(appointment_date, appointment_time)

            # Vaccination check — only pets selected for THIS reservation
            from app.models import VaccinationRecord
            from datetime import date as date_type
            today_check = date_type.today()

            # Ownership-scoped lookup: only this customer's pets can match
            selected_ids  = [int(pid) for pid in pet_ids]
            selected_pets = Pet.query.filter(
                Pet.id.in_(selected_ids),
                Pet.user_id == current_user.id
            ).all()

            if len(selected_pets) != len(set(selected_ids)):
                flash('One or more selected pets could not be found on your account.', 'danger')
                return redirect(url_for('customer.book_appointment'))

            pets_non_compliant = []
            for p in selected_pets:
                records = VaccinationRecord.query.filter_by(pet_id=p.id).all()
                if not records:
                    pets_non_compliant.append(f'{p.name} (no records on file)')
                else:
                    valid = [r for r in records if r.expiration_date and r.expiration_date >= today_check]
                    if not valid:
                        pets_non_compliant.append(f'{p.name} (all records expired)')

            if pets_non_compliant:
                issues = ', '.join(pets_non_compliant)
                flash(
                    f'Booking could not be submitted — {issues}. '
                    f'Please contact us to upload current vaccination records before booking.',
                    'danger'
                )
                return redirect(url_for('customer.book_appointment'))

            # For boarding — store check-out date+time in end_time
            end_datetime = None
            if checkout_date_str:
                try:
                    checkout_date = datetime.strptime(checkout_date_str, '%Y-%m-%d').date()
                    pickup_time_str = request.form.get('pickup_time', '17:00')
                    try:
                        pickup_time = datetime.strptime(pickup_time_str, '%H:%M').time()
                    except ValueError:
                        pickup_time = datetime.strptime('17:00', '%H:%M').time()
                    end_datetime = datetime.combine(checkout_date, pickup_time)
                except ValueError:
                    pass

            # Create one appointment per selected pet
            addon_map = {'spa_bath_nails': 'Spa Bath + Nail Trim ($30)', 'spa_bath': 'Spa Bath ($20)', 'nail_trim': 'Nail Trim ($15)'}
            selected_addons = [addon_map[a] for a in request.form.getlist('addons') if a in addon_map]
            addon_note  = ('\nAdd-ons: ' + ', '.join(selected_addons)) if selected_addons else ''
            base_notes  = request.form.get('notes', '').strip()
            full_notes  = (base_notes + addon_note).strip() or None

            for pet_id in pet_ids:
                appointment = Appointment(
                    user_id          = current_user.id,
                    pet_id           = pet_id,
                    service_type_id  = service_type_id,
                    appointment_date = appointment_date,
                    start_time       = start_datetime,
                    end_time         = end_datetime,
                    notes            = full_notes
                )
                db.session.add(appointment)

            db.session.commit()

            pet_names = [Pet.query.get(pid).name for pid in pet_ids if Pet.query.get(pid)]
            if len(pet_names) > 1:
                msg = f'Boarding request submitted for {", ".join(pet_names)}! We will confirm shortly.'
            else:
                msg = 'Boarding request submitted! We will confirm shortly.'
            flash(msg, 'success')
            return redirect(url_for('customer.dashboard'))
        except ValueError as e:
            flash(f'Invalid date or time format: {str(e)}', 'danger')
        except Exception as e:
            flash(f'Error booking appointment: {str(e)}', 'danger')
            db.session.rollback()
    
    return render_template('customer/book_appointment.html',
                           pets=pets,
                           services=services,
                           blocked_dates_json=blocked_dates_json,
                           future_blocks=future_blocks,
                           today=today)

@bp.route('/available-times')
@login_required
def available_times():
    """
    Returns available 15-minute time slots for a given date and slot type.
    Slots already taken by active boarding reservations are excluded.
    """
    from app.models import Boarding
    from datetime import date as date_type
    import json

    date_str  = request.args.get('date', '')
    slot_type = request.args.get('type', 'checkin')  # 'checkin' or 'checkout'

    try:
        target_date = datetime.strptime(date_str, '%Y-%m-%d').date()
    except ValueError:
        return json.dumps([]), 200, {'Content-Type': 'application/json'}

    # Generate slots based on day-of-week schedule:
    #   Mon-Fri  : 07:00 - 18:00
    #   Saturday : 07:00 - 11:00  and  17:00 - 18:00
    #   Sunday   : 15:00 - 18:00
    weekday = target_date.weekday()  # 0=Mon, 5=Sat, 6=Sun

    if weekday == 6:        # Sunday
        windows = [(15, 18)]
    elif weekday == 5:      # Saturday
        windows = [(7, 11), (17, 18)]
    else:                   # Mon-Fri
        windows = [(7, 18)]

    slots = []
    for (start_h, end_h) in windows:
        for hour in range(start_h, end_h + 1):
            for minute in (0, 15, 30, 45):
                if hour == end_h and minute > 0:
                    break
                time_str = f'{hour:02d}:{minute:02d}'
                display  = datetime.strptime(time_str, '%H:%M').strftime('%I:%M %p').lstrip('0')
                slots.append({'time': time_str, 'display': display})

    # Find already-taken slots on this date
    taken = set()
    if slot_type == 'checkin':
        bookings = Boarding.query.filter_by(
            check_in_date=target_date, status='active'
        ).all()
        for b in bookings:
            if b.check_in_time:
                # Normalise to HH:MM
                t = str(b.check_in_time)[:5]
                taken.add(t)
    else:
        bookings = Boarding.query.filter_by(
            check_out_date=target_date, status='active'
        ).all()
        for b in bookings:
            if b.check_out_time:
                t = str(b.check_out_time)[:5]
                taken.add(t)

    # Return only available slots, marking taken ones so UI can show them
    result = [
        {'time': s['time'], 'display': s['display'], 'available': s['time'] not in taken}
        for s in slots
    ]

    return json.dumps(result), 200, {'Content-Type': 'application/json'}


@bp.route('/pets/<int:pet_id>/vaccinations/ocr', methods=['POST'])
@login_required
def ocr_vaccination_record(pet_id):
    """
    Accept an uploaded vaccination record file, run OCR on it,
    and return extracted vaccine data as JSON for the form to pre-fill.
    """
    import json
    from app.vacc_ocr import extract_vaccination_data
    from werkzeug.utils import secure_filename
    import os, tempfile

    pet = Pet.query.get_or_404(pet_id)
    if pet.user_id != current_user.id and not current_user.is_admin:
        return json.dumps({'error': 'Unauthorized'}), 403

    file = request.files.get('file')
    if not file or not file.filename:
        return json.dumps({'error': 'No file provided'}), 400

    allowed = {'.pdf', '.jpg', '.jpeg', '.png', '.bmp', '.tiff'}
    ext = os.path.splitext(secure_filename(file.filename))[1].lower()
    if ext not in allowed:
        return json.dumps({'error': 'Unsupported file type'}), 400

    # Save to temp file for OCR processing
    with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
        file.save(tmp.name)
        tmp_path = tmp.name

    try:
        records = extract_vaccination_data(tmp_path)
        # Serialise dates to strings for JSON
        serialised = []
        for r in records:
            serialised.append({
                'vaccine_name':     r['vaccine_name'],
                'vaccination_date': r['vaccination_date'].strftime('%Y-%m-%d') if r['vaccination_date'] else '',
                'expiration_date':  r['expiration_date'].strftime('%Y-%m-%d')  if r['expiration_date']  else '',
                'confidence':       r['confidence'],
            })
        return json.dumps({'records': serialised}), 200, {'Content-Type': 'application/json'}
    except Exception as e:
        import traceback
        logger.error(f'OCR endpoint error: {e}\n{traceback.format_exc()}')
        return json.dumps({'error': str(e)}), 500
    finally:
        try:
            os.unlink(tmp_path)
        except Exception:
            pass


@bp.route('/chat', methods=['POST'])
@login_required
def customer_chat():
    """AI chat endpoint for customers — grounded in FAQ content."""
    import json
    from app.chat_service import chat_customer

    data    = request.get_json() or {}
    message = data.get('message', '').strip()
    history = data.get('history', [])

    if not message:
        return json.dumps({'error': 'No message provided'}), 400, {'Content-Type': 'application/json'}

    try:
        reply = chat_customer(message, history, user_id=current_user.id)
        return json.dumps({'reply': reply}), 200, {'Content-Type': 'application/json'}
    except Exception as e:
        import traceback
        logger.error(f'Customer chat error: {e}\n{traceback.format_exc()}')
        return json.dumps({'error': str(e)}), 500, {'Content-Type': 'application/json'}


@bp.route('/faq')
def faq():
    """Customer-facing FAQ page. No login required."""
    return render_template('customer/faq.html')

@bp.route('/appointment/<int:appt_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_appointment(appt_id):
    """Allow customer to edit a pending or confirmed boarding appointment.
    Drops back to pending for staff re-approval.
    Blocked within 24 hours of appointment date.
    """
    from app.models import Appointment, Pet, ServiceType, ServiceBlock, VaccinationRecord
    from datetime import timedelta, date as date_type
    import json as _json, re as _re

    appt = Appointment.query.filter_by(id=appt_id).first_or_404()

    # Ownership check
    if appt.user_id != current_user.id:
        flash('Access denied.', 'danger')
        return redirect(url_for('customer.dashboard'))

    # Only pending or confirmed
    if appt.status not in ('pending', 'confirmed'):
        flash('This appointment can no longer be edited.', 'warning')
        return redirect(url_for('customer.dashboard'))

    # 24-hour cutoff
    from datetime import datetime as _dt
    today = _dt.now().date()
    if _dt.now() >= _dt.combine(appt.appointment_date, _dt.min.time().replace(hour=0)) - timedelta(hours=24):
        flash('Appointments cannot be edited within 24 hours of the scheduled date.', 'warning')
        return redirect(url_for('customer.dashboard'))

    pets     = Pet.query.filter_by(user_id=current_user.id, is_active=True).all()
    services = ServiceType.query.filter(ServiceType.name.ilike('%boarding%')).all()

    # Blocked dates
    _boarding_svc = ServiceType.query.filter(ServiceType.name.ilike('%boarding%')).first()
    future_blocks = (ServiceBlock.query
        .filter(ServiceBlock.end_date >= today)
        .filter(ServiceBlock.service_type_id == _boarding_svc.id if _boarding_svc else False)
        .order_by(ServiceBlock.start_date.asc()).all()) if _boarding_svc else []

    blocked_dates = set()
    for b in future_blocks:
        d = b.start_date
        while d <= b.end_date:
            blocked_dates.add(d.isoformat())
            d += timedelta(days=1)
    blocked_dates_json = _json.dumps(sorted(blocked_dates))

    # Parse existing add-ons
    existing_addons = []
    if appt.notes and 'Add-ons:' in appt.notes:
        m = _re.search(r'Add-ons:\s*(.+)', appt.notes)
        if m:
            raw = m.group(1)
            if 'Spa Bath + Nail Trim' in raw:
                existing_addons.append('spa_bath_nails')
            elif 'Spa Bath' in raw:
                existing_addons.append('spa_bath')
            if 'Nail Trim' in raw and 'spa_bath_nails' not in existing_addons:
                existing_addons.append('nail_trim')

    base_notes = appt.notes or ''
    if 'Add-ons:' in base_notes:
        base_notes = base_notes[:base_notes.index('Add-ons:')].strip()

    if request.method == 'POST':
        try:
            date_str          = request.form.get('appointment_date')
            time_str          = request.form.get('appointment_time', '08:00')
            checkout_date_str = request.form.get('checkout_date', '').strip()
            pet_ids           = request.form.getlist('pet_ids')

            if not pet_ids:
                flash('Please select at least one pet.', 'danger')
                return redirect(url_for('customer.edit_appointment', appt_id=appt_id))

            appointment_date = datetime.strptime(date_str, '%Y-%m-%d').date()

            # Cutoff on new date
            if _dt.now() >= _dt.combine(appointment_date, _dt.min.time().replace(hour=0)) - timedelta(hours=24):
                flash('Cannot set a date within 24 hours of today.', 'warning')
                return redirect(url_for('customer.edit_appointment', appt_id=appt_id))

            # Block validation
            if date_str in blocked_dates:
                flash('The selected check-in date is unavailable due to a scheduled closure.', 'danger')
                return redirect(url_for('customer.edit_appointment', appt_id=appt_id))
            if checkout_date_str and checkout_date_str in blocked_dates:
                flash('The selected check-out date is unavailable due to a scheduled closure.', 'danger')
                return redirect(url_for('customer.edit_appointment', appt_id=appt_id))
            if checkout_date_str:
                checkout_date = datetime.strptime(checkout_date_str, '%Y-%m-%d').date()
                d = appointment_date
                while d <= checkout_date:
                    if d.isoformat() in blocked_dates:
                        flash(f'Your stay includes {d.strftime("%B %d")}, which falls within a scheduled closure.', 'danger')
                        return redirect(url_for('customer.edit_appointment', appt_id=appt_id))
                    d += timedelta(days=1)

            # Vaccination check
            today_check = date_type.today()
            pets_nc = []
            for pid in pet_ids:
                p = Pet.query.get(int(pid))
                if p:
                    records = VaccinationRecord.query.filter_by(pet_id=p.id).all()
                    if not records:
                        pets_nc.append(f'{p.name} (no records on file)')
                    else:
                        valid = [r for r in records if r.expiration_date and r.expiration_date >= today_check]
                        if not valid:
                            pets_nc.append(f'{p.name} (all records expired)')
            if pets_nc:
                flash(f'Booking could not be updated — {", ".join(pets_nc)}.', 'danger')
                return redirect(url_for('customer.edit_appointment', appt_id=appt_id))

            appointment_time = datetime.strptime(time_str, '%H:%M').time()
            start_datetime   = datetime.combine(appointment_date, appointment_time)

            end_datetime = None
            if checkout_date_str:
                checkout_date   = datetime.strptime(checkout_date_str, '%Y-%m-%d').date()
                pickup_time_str = request.form.get('pickup_time', '17:00')
                try:
                    pickup_time = datetime.strptime(pickup_time_str, '%H:%M').time()
                except ValueError:
                    pickup_time = datetime.strptime('17:00', '%H:%M').time()
                end_datetime = datetime.combine(checkout_date, pickup_time)

            addon_map = {
                'spa_bath_nails': 'Spa Bath + Nail Trim ($30)',
                'spa_bath':       'Spa Bath ($20)',
                'nail_trim':      'Nail Trim ($15)'
            }
            selected_addons = [addon_map[a] for a in request.form.getlist('addons') if a in addon_map]
            addon_note  = ('\nAdd-ons: ' + ', '.join(selected_addons)) if selected_addons else ''
            new_notes   = (request.form.get('notes', '').strip() + addon_note).strip() or None

            old_status = appt.status

            appt.pet_id           = int(pet_ids[0])
            appt.appointment_date = appointment_date
            appt.start_time       = start_datetime
            appt.end_time         = end_datetime
            appt.notes            = new_notes
            appt.status           = 'pending'

            # Handle additional pets
            if len(pet_ids) > 1:
                siblings = Appointment.query.filter(
                    Appointment.user_id          == current_user.id,
                    Appointment.appointment_date == appt.appointment_date,
                    Appointment.id               != appt.id,
                    Appointment.status.in_(['pending', 'confirmed'])
                ).all()
                for s in siblings:
                    db.session.delete(s)
                for pid in pet_ids[1:]:
                    new_appt = Appointment(
                        user_id          = current_user.id,
                        pet_id           = int(pid),
                        service_type_id  = appt.service_type_id,
                        appointment_date = appointment_date,
                        start_time       = start_datetime,
                        end_time         = end_datetime,
                        notes            = new_notes,
                        status           = 'pending'
                    )
                    db.session.add(new_appt)

            db.session.commit()

            # Audit log
            try:
                from app.audit_service import audit
                audit('appointment.edited', 'appointment', appt_id,
                      f'Appointment #{appt_id}',
                      f'Appointment #{appt_id} edited by customer {current_user.first_name} {current_user.last_name}')
            except Exception:
                pass

            # Staff SMS
            try:
                from app.sms_service import _normalize_phone
                from app.models import SmsMessage
                from twilio.rest import Client
                from flask import current_app
                staff_phone = current_app.config.get('SUPPORT_PHONE') or current_app.config.get('BUSINESS_PHONE')
                if staff_phone:
                    pet_names = [Pet.query.get(int(pid)).name for pid in pet_ids if Pet.query.get(int(pid))]
                    to_e164   = _normalize_phone(staff_phone)
                    from_num  = current_app.config.get('TWILIO_PHONE_NUMBER')
                    body = (
                        f"Booking updated by {current_user.first_name} {current_user.last_name}: "
                        f"{', '.join(pet_names)} — {appointment_date.strftime('%b %d')}"
                        f"{' to ' + end_datetime.strftime('%b %d') if end_datetime else ''}. "
                        f"Reset to pending — please re-approve."
                    )
                    Client(current_app.config.get('TWILIO_ACCOUNT_SID'),
                           current_app.config.get('TWILIO_AUTH_TOKEN')
                    ).messages.create(body=body, from_=from_num, to=to_e164)
            except Exception as e:
                current_app.logger.error(f'Edit appt staff SMS failed: {e}')

            if old_status == 'confirmed':
                flash('Your booking has been updated and sent back to staff for re-approval.', 'success')
            else:
                flash('Your booking request has been updated.', 'success')
            return redirect(url_for('customer.dashboard'))

        except ValueError as e:
            flash(f'Invalid date or time format: {str(e)}', 'danger')
        except Exception as e:
            flash(f'Error updating appointment: {str(e)}', 'danger')
            db.session.rollback()

    return render_template('customer/edit_appointment.html',
                           appt=appt,
                           pets=pets,
                           services=services,
                           blocked_dates_json=blocked_dates_json,
                           future_blocks=future_blocks,
                           existing_addons=existing_addons,
                           base_notes=base_notes,
                           today=today)


# ── NEW: Customer self-service cancellation ───────────────────────────────────
@bp.route('/appointment/<int:appt_id>/cancel', methods=['POST'])
@login_required
def cancel_appointment(appt_id):
    """Allow customer to cancel a pending or confirmed boarding appointment.
    Respects the same 24-hour cutoff as edit. Notifies staff via SMS.
    """
    from datetime import timedelta
    from datetime import datetime as _dt
    from flask import current_app

    appt = Appointment.query.filter_by(id=appt_id).first_or_404()

    # Ownership check
    if appt.user_id != current_user.id:
        flash('Access denied.', 'danger')
        return redirect(url_for('customer.dashboard'))

    # Only pending or confirmed can be cancelled
    if appt.status not in ('pending', 'confirmed'):
        flash('This appointment cannot be cancelled.', 'warning')
        return redirect(url_for('customer.dashboard'))

    # 24-hour cutoff
    if _dt.now() >= _dt.combine(appt.appointment_date, _dt.min.time().replace(hour=0)) - timedelta(hours=24):
        flash('Appointments cannot be cancelled within 24 hours of the scheduled date. Please call us directly.', 'warning')
        return redirect(url_for('customer.dashboard'))

    old_status   = appt.status
    pet          = Pet.query.get(appt.pet_id)
    pet_name     = pet.name if pet else f'Pet #{appt.pet_id}'
    checkin_str  = appt.appointment_date.strftime('%b %d')
    checkout_str = appt.end_time.strftime('%b %d') if appt.end_time else None

    appt.status = 'cancelled'
    db.session.commit()

    # Audit log
    try:
        from app.audit_service import audit
        audit('appointment.cancelled', 'appointment', appt_id,
              f'Appointment #{appt_id}',
              f'Appointment #{appt_id} cancelled by customer {current_user.first_name} {current_user.last_name}')
    except Exception:
        pass

    # Staff SMS notification
    try:
        from app.sms_service import _normalize_phone
        from twilio.rest import Client
        staff_phone = current_app.config.get('SUPPORT_PHONE') or current_app.config.get('BUSINESS_PHONE')
        if staff_phone:
            to_e164  = _normalize_phone(staff_phone)
            from_num = current_app.config.get('TWILIO_PHONE_NUMBER')
            body = (
                f"Booking CANCELLED by {current_user.first_name} {current_user.last_name}: "
                f"{pet_name} — {checkin_str}"
                f"{' to ' + checkout_str if checkout_str else ''}."
                f" Was {old_status}."
            )
            Client(current_app.config.get('TWILIO_ACCOUNT_SID'),
                   current_app.config.get('TWILIO_AUTH_TOKEN')
            ).messages.create(body=body, from_=from_num, to=to_e164)
    except Exception as e:
        current_app.logger.error(f'Cancel appt staff SMS failed: {e}')

    flash('Your reservation has been cancelled. Contact us if you have any questions.', 'success')
    return redirect(url_for('customer.dashboard'))
# ── END NEW ───────────────────────────────────────────────────────────────────