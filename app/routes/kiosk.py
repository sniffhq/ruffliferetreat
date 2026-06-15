from flask import Blueprint, render_template, request, flash, redirect, url_for
from app import db
from app.models import Pet, User, DaycareEnrollment, DaycareAttendance
from datetime import datetime

bp = Blueprint('kiosk', __name__, url_prefix='/kiosk')

@bp.route('/', methods=['GET', 'POST'])
def index():
    """Single page for check-in and check-out"""
    if request.method == 'POST':
        phone    = request.form.get('phone', '').strip()
        pet_name = request.form.get('pet_name', '').strip()
        action   = request.form.get('action')

        if not phone or not pet_name:
            flash('Please enter both phone number and pet name.', 'warning')
            return redirect(url_for('kiosk.index'))

        # Normalize phone — strip non-digits for flexible matching
        import re
        phone_digits = re.sub(r'\D', '', phone)

        # Find the pet by owner phone and pet name
        all_users = User.query.filter(User.phone.isnot(None)).all()
        owner = None
        for u in all_users:
            if re.sub(r'\D', '', u.phone or '') == phone_digits:
                owner = u
                break

        if not owner:
            flash(f'No account found for phone number "{phone}". Please contact staff.', 'danger')
            return redirect(url_for('kiosk.index'))

        pet = Pet.query.filter(
            Pet.user_id == owner.id,
            db.func.lower(Pet.name) == pet_name.lower(),
            Pet.is_active == True
        ).first()

        if not pet:
            flash(f'No pet named "{pet_name}" found for that phone number.', 'danger')
            return redirect(url_for('kiosk.index'))

        # Check enrollment
        enrollment = DaycareEnrollment.query.filter_by(
            pet_id=pet.id,
            active=True
        ).first()

        if not enrollment:
            flash(f'{pet.name} is not enrolled in daycare. Please contact staff.', 'warning')
            return redirect(url_for('kiosk.index'))

        # Process action
        if action == 'checkin':
            return process_checkin(enrollment, pet)
        elif action == 'checkout':
            return process_checkout(enrollment, pet)
        else:
            flash('Invalid action.', 'danger')
            return redirect(url_for('kiosk.index'))

    return render_template('kiosk/index.html')


@bp.route('/lookup-pets')
def lookup_pets():
    """AJAX: return daycare-enrolled pets for a given phone number."""
    import re
    from flask import jsonify

    phone = request.args.get('phone', '').strip()
    phone_digits = re.sub(r'\D', '', phone)

    if len(phone_digits) < 10:
        return jsonify({'error': 'Enter a full phone number', 'pets': []})

    all_users = User.query.filter(User.phone.isnot(None)).all()
    owner = None
    for u in all_users:
        if re.sub(r'\D', '', u.phone or '') == phone_digits:
            owner = u
            break

    if not owner:
        return jsonify({'error': 'No account found for that number', 'pets': []})

    enrollments = (DaycareEnrollment.query
        .filter_by(active=True)
        .join(Pet, DaycareEnrollment.pet_id == Pet.id)
        .filter(Pet.user_id == owner.id, Pet.is_active == True)
        .all())

    pets = [{'name': e.pet.name} for e in enrollments]

    if not pets:
        return jsonify({'error': f'No enrolled pets found for {owner.first_name}', 'pets': []})

    return jsonify({'owner': owner.first_name, 'pets': pets})


@bp.route('/dashboard')
def dashboard():
    """Redirect old kiosk.dashboard references to admin daycare dashboard"""
    return redirect(url_for('admin.daycare_dashboard'))


def process_checkin(enrollment, pet):
    """Handle check-in"""
    today = datetime.now().date()
    
    existing = DaycareAttendance.query.filter(
        DaycareAttendance.enrollment_id == enrollment.id,
        db.func.date(DaycareAttendance.check_in_time) == today,
        DaycareAttendance.check_out_time == None
    ).first()
    
    if existing:
        flash(f'{pet.name} is already checked in!', 'warning')
        return redirect(url_for('kiosk.index'))
    
    check_in_time = datetime.now()
    attendance = DaycareAttendance(
        enrollment_id=enrollment.id,
        check_in_time=check_in_time
    )
    db.session.add(attendance)

    # flush() assigns the ID before commit — needed for play group assignment
    db.session.flush()
    attendance_id = attendance.id
    db.session.commit()

    # Auto-assign play group in a separate operation after the commit
    try:
        from app.models import PlayGroup
        weight = float(pet.weight) if pet.weight else 0
        if weight < 25:
            size = 'small'
        elif weight <= 50:
            size = 'medium'
        else:
            size = 'large'
        temp = pet.temperament or 'calm'
        group = (PlayGroup.query.filter_by(size_category=size, temperament=temp, active=True).first()
                 or PlayGroup.query.filter_by(size_category=size, temperament='mixed', active=True).first()
                 or PlayGroup.query.filter_by(size_category=size, active=True).first())
        if group:
            DaycareAttendance.query.filter_by(id=attendance_id).update({'play_group_id': group.id})
            db.session.commit()
    except Exception as e:
        db.session.rollback()
        import logging; logging.getLogger(__name__).error(f'Play group auto-assign failed: {e}')

    flash(f'✓ {pet.name} checked in successfully at {check_in_time.strftime("%I:%M %p")}!', 'success')
    return redirect(url_for('kiosk.index'))


def process_checkout(enrollment, pet):
    """Handle check-out"""
    attendance = DaycareAttendance.query.filter(
        DaycareAttendance.enrollment_id == enrollment.id,
        DaycareAttendance.check_out_time == None
    ).order_by(DaycareAttendance.check_in_time.desc()).first()
    
    if not attendance:
        flash(f'{pet.name} is not currently checked in.', 'warning')
        return redirect(url_for('kiosk.index'))
    
    check_out_time = datetime.now()
    attendance.check_out_time = check_out_time
    db.session.commit()

    # Check daycare milestone survey
    try:
        from app.survey_service import check_daycare_milestone
        if pet.owner:
            check_daycare_milestone(pet.owner.id)
    except Exception as e:
        import logging; logging.getLogger(__name__).error(f'Survey milestone check failed: {e}')

    duration = (attendance.check_out_time - attendance.check_in_time).total_seconds() / 3600
    flash(f'✓ {pet.name} checked out successfully! Duration: {duration:.1f} hours', 'success')
    return redirect(url_for('kiosk.index'))