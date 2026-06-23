from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify, current_app, make_response
from flask_login import login_required, current_user
from functools import wraps
from app import db
from app.models import User, Pet, Appointment, ServiceType, ServiceBlock, DaycareEnrollment, DaycareAttendance, DaycareWaitlist, Boarding, OpsNote
from datetime import datetime, timedelta
from sqlalchemy import and_
import os

bp = Blueprint('admin', __name__, url_prefix='/admin')

def _fmt_t(t):
    """Convert 'HH:MM' string or time/datetime object to '2:30 PM' format."""
    if not t:
        return ''
    try:
        if isinstance(t, str):
            return datetime.strptime(str(t)[:5], '%H:%M').strftime('%I:%M %p').lstrip('0')
        return t.strftime('%I:%M %p').lstrip('0')
    except Exception:
        return str(t)

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_admin:
            flash('Access denied.', 'danger')
            return redirect(url_for('public.index'))
        return f(*args, **kwargs)
    return decorated_function

@bp.route('/daily-log', methods=['GET'])
@login_required
@admin_required
def daily_log():
    """View daily log entries."""
    from app.models import DailyLog, DailyLogPetFlag, Boarding, DaycareAttendance
    from datetime import date, timedelta

    today    = date.today()
    # Last 14 days of entries
    entries  = (DailyLog.query
                .filter(DailyLog.log_date >= today - timedelta(days=14))
                .order_by(DailyLog.log_date.desc())
                .all())

    # Today's active pets (for flagging)
    todays_boarders = Boarding.query.filter(
        Boarding.check_in_date  <= today,
        Boarding.check_out_date >= today,
        Boarding.status == 'active'
    ).all()

    todays_daycare = (DaycareAttendance.query
        .filter(DaycareAttendance.check_out_time == None)
        .all())

    todays_pets = []
    seen = set()
    for b in todays_boarders:
        if b.pet_id not in seen:
            todays_pets.append({'pet': b.pet, 'service': 'Boarding'})
            seen.add(b.pet_id)
    for a in todays_daycare:
        if a.enrollment and a.enrollment.pet_id not in seen:
            todays_pets.append({'pet': a.enrollment.pet, 'service': 'Daycare'})
            seen.add(a.enrollment.pet_id)

    # Today's existing entry if any
    today_entry = DailyLog.query.filter_by(
        log_date=today, author_id=current_user.id
    ).first()

    return render_template('admin/daily_log.html',
        today=today,
        entries=entries,
        todays_pets=todays_pets,
        today_entry=today_entry)


@bp.route('/daily-log/save', methods=['POST'])
@login_required
@admin_required
def save_daily_log():
    """Save or update today's daily log entry."""
    from app.models import DailyLog, DailyLogPetFlag
    from datetime import date

    today = date.today()

    # Get or create today's entry for this staff member
    entry = DailyLog.query.filter_by(log_date=today, author_id=current_user.id).first()
    if not entry:
        entry = DailyLog(log_date=today, author_id=current_user.id)
        db.session.add(entry)

    entry.notes     = request.form.get('notes', '').strip()
    entry.incidents = request.form.get('incidents', '').strip()
    entry.staffing  = request.form.get('staffing', '').strip()

    db.session.flush()

    # Replace pet flags
    DailyLogPetFlag.query.filter_by(log_id=entry.id).delete()

    pet_ids    = request.form.getlist('flagged_pet_ids')
    flag_types = request.form.getlist('flag_types')
    flag_notes = request.form.getlist('flag_notes')

    for i, pid in enumerate(pet_ids):
        if not pid:
            continue
        flag = DailyLogPetFlag(
            log_id    = entry.id,
            pet_id    = int(pid),
            flag_type = flag_types[i] if i < len(flag_types) else 'needs_followup',
            note      = flag_notes[i] if i < len(flag_notes) else ''
        )
        db.session.add(flag)

    db.session.commit()
    flash("Today's log saved.", 'success')
    return redirect(url_for('admin.daily_log'))


@bp.route('/chat', methods=['POST'])
@login_required
@admin_required
def staff_chat():
    """AI chat endpoint for staff — grounded in KB articles."""
    import json
    from app.chat_service import chat_staff

    data    = request.get_json() or {}
    message = data.get('message', '').strip()
    history = data.get('history', [])

    if not message:
        return json.dumps({'error': 'No message provided'}), 400, {'Content-Type': 'application/json'}

    try:
        reply = chat_staff(message, history)
        return json.dumps({'reply': reply}), 200, {'Content-Type': 'application/json'}
    except Exception as e:
        import logging
        logging.getLogger(__name__).error(f'Staff chat error: {e}')
        return json.dumps({'error': str(e)}), 500, {'Content-Type': 'application/json'}


@bp.route('/dashboard')
@login_required
@admin_required
def dashboard():
    total_customers = User.query.filter_by(role='customer', is_active=True).count()



    total_pets = Pet.query.filter_by(is_active=True).count()
    total_appointments = Appointment.query.count()
    pending_count = Appointment.query.filter_by(status='pending').count()
    
    today = datetime.now().date()
    start_of_week = today - timedelta(days=today.weekday())
    end_of_week = start_of_week + timedelta(days=6)
    
    week_offset = request.args.get('week', 0, type=int)
    start_of_week = start_of_week + timedelta(weeks=week_offset)
    end_of_week = start_of_week + timedelta(days=6)
    
    week_appointments = Appointment.query.filter(
        and_(
            Appointment.appointment_date >= start_of_week,
            Appointment.appointment_date <= end_of_week
        )
    ).order_by(Appointment.appointment_date, Appointment.start_time).all()
    
    appointments_by_day = {}
    for i in range(7):
        day = start_of_week + timedelta(days=i)
        appointments_by_day[day] = [
            appt for appt in week_appointments 
            if appt.appointment_date == day
        ]

    # Build daycare pets per day based on enrollment schedule flags
    day_attr_map = {0: 'monday', 1: 'tuesday', 2: 'wednesday', 3: 'thursday'}
    active_enrollments = DaycareEnrollment.query.filter_by(active=True).all()
    daycare_by_day = {}
    for i in range(7):
        day = start_of_week + timedelta(days=i)
        day_attr = day_attr_map.get(day.weekday())
        if day_attr:
            daycare_by_day[day] = [e for e in active_enrollments if getattr(e, day_attr)]
        else:
            daycare_by_day[day] = []

    recent_appointments = Appointment.query.order_by(
        Appointment.appointment_date.desc()
    ).limit(10).all()

    # Active staff notices not dismissed by current user
    from app.models import StaffNotice
    from datetime import datetime as dt
    all_notices = StaffNotice.query.filter(
        StaffNotice.expires_at > dt.now()
    ).order_by(StaffNotice.priority.desc(), StaffNotice.created_at.desc()).all()
    notices = [n for n in all_notices if not n.is_dismissed_by(current_user.id)]

    return render_template('admin/dashboard.html',
                         total_customers=total_customers,
                         total_pets=total_pets,
                         total_appointments=total_appointments,
                         pending_count=pending_count,
                         appointments_by_day=appointments_by_day,
                         daycare_by_day=daycare_by_day,
                         week_offset=week_offset,
                         start_of_week=start_of_week,
                         end_of_week=end_of_week,
                         today=today,
                         recent_appointments=recent_appointments,
                         notices=notices)

@bp.route('/users')
@login_required
@admin_required
def users():
    users = User.query.filter(User.role.in_(['staff', 'admin'])).order_by(User.last_name, User.first_name).all()
    return render_template('admin/users.html', users=users)

@bp.route('/users/<int:user_id>/archive', methods=['POST'])
@login_required
@admin_required
def archive_user(user_id):
    user = User.query.get_or_404(user_id)
    user.is_active = False
    user.archived_at = datetime.now()
    db.session.commit()
    try:
        from app.audit_service import audit
        audit('user.archived', 'user', user_id,
              f'{user.first_name} {user.last_name}',
              f'User {user.first_name} {user.last_name} archived by {current_user.first_name} {current_user.last_name}')
    except Exception: pass
    flash(f'User {user.first_name} {user.last_name} has been archived.', 'success')
    return redirect(url_for('admin.users'))

@bp.route('/pets')
@login_required
@admin_required
def pets():
    pets = Pet.query.filter_by(is_active=True).order_by(Pet.name).all()
    return render_template('admin/pets.html', pets=pets)

@bp.route('/pets/<int:pet_id>/archive', methods=['POST'])
@login_required
@admin_required
def archive_pet(pet_id):
    pet = Pet.query.get_or_404(pet_id)
    pet.is_active = False
    pet.archived_at = datetime.now()
    db.session.commit()
    flash(f'Pet {pet.name} has been archived.', 'success')
    return redirect(url_for('admin.pets'))

@bp.route('/appointments')
@login_required
@admin_required
def appointments():
    appointments = Appointment.query.filter_by(archived=False).order_by(Appointment.appointment_date.desc()).all()
    return render_template('admin/appointments.html', appointments=appointments)

@bp.route('/appointments/<int:appt_id>/complete', methods=['POST'])
@login_required
@admin_required
def complete_appointment(appt_id):
    appt = Appointment.query.get_or_404(appt_id)
    appt.status = 'completed'
    db.session.commit()
    try:
        from app.audit_service import audit
        audit('appointment.completed', 'appointment', appt_id, f'Appointment #{appt.id}',
              f'Appointment #{appt.id} marked completed by {current_user.first_name} {current_user.last_name}')
    except Exception: pass
    flash(f'Appointment {appt.id} marked as completed.', 'success')
    return redirect(url_for('admin.appointments'))


@bp.route('/appointments/<int:appt_id>/approve', methods=['POST'])
@login_required
@admin_required
def approve_appointment(appt_id):
    appt = Appointment.query.get_or_404(appt_id)
    appt.status = 'confirmed'
    appt.needs_reapproval = False
    db.session.commit()

    # If this is a boarding appointment, auto-create the Boarding record
    # so it appears on the boarding dashboard regardless of which page approved it
    try:
        if appt.service_type and 'boarding' in appt.service_type.name.lower():
            existing = Boarding.query.filter_by(
                pet_id=appt.pet_id, status='active'
            ).filter(
                Boarding.check_in_date == appt.appointment_date
            ).first()

            if not existing:
                check_out_date = appt.end_time.date() if appt.end_time else appt.appointment_date
                check_in_time  = appt.start_time.strftime('%H:%M') if appt.start_time else '08:00'
                check_out_time = appt.end_time.strftime('%H:%M') if appt.end_time else '17:00'

                booking = Boarding(
                    pet_id         = appt.pet_id,
                    user_id        = appt.user_id,
                    check_in_date  = appt.appointment_date,
                    check_in_time  = check_in_time,
                    check_out_date = check_out_date,
                    check_out_time = check_out_time,
                    status         = 'active',
                    booking_number = _next_board_number()
                )
                db.session.add(booking)
                db.session.commit()

                # Send confirmation SMS
                try:
                    from app.sms_service import _normalize_phone
                    from app.models import SmsMessage
                    from twilio.rest import Client
                    owner = appt.user
                    if owner and owner.phone:
                        def _fmt_t(t):
                            try:
                                from datetime import datetime as _dt
                                return _dt.strptime(str(t)[:5], '%H:%M').strftime('%I:%M %p').lstrip('0')
                            except Exception:
                                return str(t)
                        to_e164     = _normalize_phone(owner.phone)
                        from_number = current_app.config.get('TWILIO_PHONE_NUMBER')
                        body = (
                            f"\u2705 Great news, {owner.first_name}! Your boarding request for "
                            f"{appt.pet.name} has been approved. "
                            f"Ref: {booking.booking_number}. "
                            f"Check-in: {appt.appointment_date.strftime('%a, %b %d')} at {_fmt_t(check_in_time)}. "
                            f"Check-out: {check_out_date.strftime('%a, %b %d')} at {_fmt_t(check_out_time)}. "
                            f"Questions? Reply to this message. \u2014 Ruff Life Retreat"
                        )
                        client  = Client(current_app.config.get('TWILIO_ACCOUNT_SID'),
                                         current_app.config.get('TWILIO_AUTH_TOKEN'))
                        message = client.messages.create(body=body, from_=from_number, to=to_e164)
                        log = SmsMessage(user_id=owner.id, direction='outbound',
                                         from_number=from_number, to_number=to_e164,
                                         body=body, twilio_sid=message.sid, is_read=True)
                        db.session.add(log)
                        db.session.commit()
                except Exception as sms_err:
                    current_app.logger.error(f'SMS failed on appointment approval {appt_id}: {sms_err}')

                flash(f'Appointment #{appt.id} approved and boarding reservation created.', 'success')
                return redirect(url_for('admin.appointments'))
    except Exception as e:
        current_app.logger.error(f'Failed to auto-create boarding record for appt {appt_id}: {e}')

    try:
        from app.audit_service import audit
        audit('appointment.approved', 'appointment', appt_id, f'Appointment #{appt.id}',
              f'Appointment #{appt.id} approved by {current_user.first_name} {current_user.last_name}')
    except Exception: pass
    flash(f'Appointment #{appt.id} approved.', 'success')
    return redirect(url_for('admin.appointments'))

@bp.route('/appointments/<int:appt_id>/cancel', methods=['POST'])
@login_required
@admin_required
def cancel_appointment(appt_id):
    appt = Appointment.query.get_or_404(appt_id)
    appt.status = 'cancelled'
    db.session.commit()
    try:
        from app.audit_service import audit
        audit('appointment.cancelled', 'appointment', appt_id, f'Appointment #{appt.id}',
              f'Appointment #{appt.id} cancelled by {current_user.first_name} {current_user.last_name}')
    except Exception: pass
    flash(f'Appointment {appt.id} cancelled.', 'warning')
    return redirect(url_for('admin.appointments'))

@bp.route('/service-types')
@login_required
@admin_required
def service_types():
    types = ServiceType.query.all()
    return render_template('admin/service_types.html', service_types=types)

@bp.route('/service-types/create', methods=['POST'])
@login_required
@admin_required
def create_service_type():
    name = request.form.get('name')
    price = request.form.get('price', type=float)
    duration = request.form.get('duration', type=int)

    if not name or price is None:
        flash('Name and price are required.', 'danger')
        return redirect(url_for('admin.service_types'))

    service_type = ServiceType(name=name, base_price=price,
                               duration_minutes=duration or 60)
    db.session.add(service_type)
    db.session.commit()
    flash(f'Service "{name}" created.', 'success')
    return redirect(url_for('admin.service_types'))


@bp.route('/service-types/<int:service_id>/update', methods=['POST'])
@login_required
@admin_required
def update_service_type(service_id):
    svc = ServiceType.query.get_or_404(service_id)
    svc.name             = request.form.get('name', '').strip() or svc.name
    price                = request.form.get('base_price', '').strip()
    svc.base_price       = float(price) if price else svc.base_price
    duration             = request.form.get('duration_minutes', '').strip()
    svc.duration_minutes = int(duration) if duration else svc.duration_minutes
    svc.description      = request.form.get('description', '').strip() or None
    db.session.commit()
    flash(f'"{svc.name}" updated.', 'success')
    return redirect(url_for('admin.service_types'))


@bp.route('/service-types/<int:service_id>/delete', methods=['POST'])
@login_required
@admin_required
def delete_service_type(service_id):
    svc = ServiceType.query.get_or_404(service_id)
    # Check if any appointments use this service type
    appt_count = Appointment.query.filter_by(service_type_id=service_id).count()
    if appt_count > 0:
        flash(f'Cannot delete "{svc.name}" — {appt_count} appointment(s) reference it.', 'danger')
        return redirect(url_for('admin.service_types'))
    name = svc.name
    db.session.delete(svc)
    db.session.commit()
    flash(f'"{name}" deleted.', 'success')
    return redirect(url_for('admin.service_types'))

@bp.route('/blocks')
@login_required
@admin_required
def blocks():
    blocks = ServiceBlock.query.all()
    service_types = ServiceType.query.all()
    return render_template('admin/blocks.html', blocks=blocks, service_blocks=blocks, service_types=service_types)

@bp.route('/blocks/create', methods=['POST'])
@login_required
@admin_required
def create_block():
    service_type_id = request.form.get('service_type_id', type=int)
    start_date = request.form.get('start_date')
    end_date = request.form.get('end_date')
    reason = request.form.get('reason')
    
    if not service_type_id or not start_date or not end_date:
        flash('All fields are required.', 'danger')
        return redirect(url_for('admin.blocks'))
    
    try:
        start = datetime.strptime(start_date, '%Y-%m-%d').date()
        end = datetime.strptime(end_date, '%Y-%m-%d').date()
    except ValueError:
        flash('Invalid date format.', 'danger')
        return redirect(url_for('admin.blocks'))
    
    if end < start:
        flash('End date must be after start date.', 'danger')
        return redirect(url_for('admin.blocks'))
    
    service_type = ServiceType.query.get_or_404(service_type_id)
    block = ServiceBlock(service_type_id=service_type_id, start_date=start, end_date=end, reason=reason)
    db.session.add(block)
    db.session.commit()
    flash(f'Service block created for {service_type.name}.', 'success')
    return redirect(url_for('admin.blocks'))

@bp.route('/blocks/<int:block_id>/delete', methods=['POST'])
@login_required
@admin_required
def delete_block(block_id):
    block = ServiceBlock.query.get_or_404(block_id)
    service_name = block.service_type.name
    db.session.delete(block)
    db.session.commit()
    flash(f'Service block for {service_name} deleted.', 'success')
    return redirect(url_for('admin.blocks'))

@bp.route('/daycare/dashboard')
@login_required
@admin_required
def daycare_dashboard():
    """Daycare management dashboard"""
    # Get all daycare enrollments
    enrollments = (DaycareEnrollment.query
        .filter_by(active=True)
        .join(Pet, DaycareEnrollment.pet_id == Pet.id)
        .order_by(Pet.name)
        .all())
    
    # Calculate today's attendance
    today = datetime.now().date()
    all_today = DaycareAttendance.query.filter(
        DaycareAttendance.check_in_time >= datetime.combine(today, datetime.min.time()),
        DaycareAttendance.check_in_time <= datetime.combine(today, datetime.max.time())
    ).all()

    # Split into currently checked in vs completed visits
    all_today = [a for a in all_today if a is not None]
    checked_in       = [a for a in all_today if a.check_out_time is None]
    todays_attendance = [a for a in all_today if a.check_out_time is not None]

    # Map enrollment_id -> attendance_id for pets currently checked in
    # Used by the admin Check Out button in the enrollments table
    checked_in_by_enrollment = {
        a.enrollment_id: a.id
        for a in checked_in
        if a.id is not None
    }
    
    # Get pending waitlist
    pending_waitlist = DaycareWaitlist.query.filter_by(contacted=False).order_by(
        DaycareWaitlist.submitted_date.asc()
    ).all()
    
    # Get contacted waitlist
    contacted_waitlist = DaycareWaitlist.query.filter_by(contacted=True).order_by(
        DaycareWaitlist.submitted_date.desc()
    ).all()
    
    # Get all waitlist for total count
    all_waitlist = DaycareWaitlist.query.all()
    
    # Upcoming service blocks for daycare (next 60 days)
    from app.models import ServiceBlock, ServiceType
    from datetime import timedelta
    daycare_service = ServiceType.query.filter(
        ServiceType.name.ilike('%daycare%')
    ).first()
    upcoming_blocks = []
    if daycare_service:
        upcoming_blocks = (ServiceBlock.query
            .filter_by(service_type_id=daycare_service.id)
            .filter(ServiceBlock.end_date >= today)
            .order_by(ServiceBlock.start_date.asc())
            .limit(10).all())

    # Daycare 2-week calendar (boarding-style)
    import json as _json
    dc_offset = request.args.get('dc_offset', 0, type=int)
    dc_offset = max(0, dc_offset)
    monday_start = today - timedelta(days=today.weekday())
    cal_start = monday_start + timedelta(weeks=dc_offset * 2)
    cal_end   = cal_start + timedelta(days=13)

    # Closure dates within this window
    closure_dates_set = set()
    if daycare_service:
        blocks_in_range = (ServiceBlock.query
            .filter_by(service_type_id=daycare_service.id)
            .filter(ServiceBlock.end_date >= cal_start)
            .filter(ServiceBlock.start_date <= cal_end)
            .all())
        for blk in blocks_in_range:
            bd = blk.start_date
            while bd <= blk.end_date:
                if cal_start <= bd <= cal_end:
                    closure_dates_set.add(bd)
                bd += timedelta(days=1)

    _day_fields = {0: 'monday', 1: 'tuesday', 2: 'wednesday', 3: 'thursday'}
    daycare_cal_dates       = {}  # date_str -> [pet names]  (Jinja highlighting)
    daycare_cal_detail_data = {}  # date_str -> {pets, is_closed, count}  (JS modal)

    for _offset in range(14):
        d   = cal_start + timedelta(days=_offset)
        dow = d.weekday()
        if dow >= 4:   # skip Friday, Saturday, Sunday — daycare is Mon-Thu only
            continue
        field    = _day_fields[dow]
        day_pets = [e for e in enrollments if getattr(e, field)]
        ds       = d.isoformat()
        is_closed = d in closure_dates_set
        if day_pets and not is_closed:
            daycare_cal_dates[ds] = [e.pet.name for e in day_pets]
        daycare_cal_detail_data[ds] = {
            'pets': [
                {
                    'name':          e.pet.name,
                    'breed':         e.pet.breed or 'Dog',
                    'owner':         f'{e.pet.owner.first_name} {e.pet.owner.last_name}',
                    'special_rate':  float(e.special_rate) if e.special_rate else None,
                    'enrollment_id': e.id,
                    'is_checked_in': e.id in checked_in_by_enrollment,
                }
                for e in day_pets
            ],
            'is_closed': is_closed,
            'count':     len(day_pets),
        }

    dc_weeks = [
        [cal_start + timedelta(days=i)     for i in range(7)],
        [cal_start + timedelta(days=7 + i) for i in range(7)],
    ]

    return render_template('admin/daycare_dashboard.html',
                         enrollments=enrollments,
                         checked_in=checked_in,
                         checked_in_by_enrollment=checked_in_by_enrollment,
                         todays_attendance=todays_attendance,
                         today_attendance=checked_in + todays_attendance,
                         pending_waitlist=pending_waitlist,
                         contacted_waitlist=contacted_waitlist,
                         all_waitlist=all_waitlist,
                         upcoming_blocks=upcoming_blocks,
                         dc_offset=dc_offset,
                         dc_weeks=dc_weeks,
                         daycare_cal_dates=daycare_cal_dates,
                         daycare_cal_detail=_json.dumps(daycare_cal_detail_data),
                         now=datetime.now(),
                         today=today)

@bp.route('/daycare/enroll', methods=['GET', 'POST'])
@login_required
@admin_required
def daycare_enroll():
    """Enroll a pet in daycare"""
    if request.method == 'POST':
        pet_id    = request.form.get('pet_id', type=int)
        monday    = bool(request.form.get('monday'))
        tuesday   = bool(request.form.get('tuesday'))
        wednesday = bool(request.form.get('wednesday'))
        thursday  = bool(request.form.get('thursday'))
        friday    = bool(request.form.get('friday'))
        notes     = request.form.get('notes', '')

        if not pet_id or not (monday or tuesday or wednesday or thursday or friday):
            flash('Please select pet and at least one day.', 'danger')
            return redirect(url_for('admin.daycare_enroll'))

        pet = Pet.query.get_or_404(pet_id)
        enrollment = DaycareEnrollment(
            pet_id=pet_id,
            enrollment_date=datetime.now().date(),
            monday=monday,
            tuesday=tuesday,
            wednesday=wednesday,
            thursday=thursday,
            friday=friday,
            notes=notes,
            active=True
        )
        db.session.add(enrollment)
        db.session.commit()
        try:
            from app.audit_service import audit
            audit('daycare.enrolled', 'daycare_enrollment', enrollment.id, pet.name,
                  f'{pet.name} enrolled in daycare by {current_user.first_name} {current_user.last_name}')
        except Exception: pass
        flash(f'{pet.name} enrolled in daycare.', 'success')
        return redirect(url_for('admin.daycare_dashboard'))

    pets = Pet.query.filter_by(is_active=True).order_by(Pet.name).all()
    return render_template('admin/daycare_enroll.html', pets=pets)
@bp.route('/daycare/enrollment/<int:enrollment_id>/checkin', methods=['POST'])
@login_required
@admin_required
def daycare_checkin(enrollment_id):
    """Admin manual check-in for a daycare pet."""
    enrollment  = DaycareEnrollment.query.get_or_404(enrollment_id)
    pet         = enrollment.pet
    owner       = pet.owner
    check_in_time = datetime.now()

    # Capture owner data before any commit
    owner_phone = owner.phone if owner else None
    owner_id    = owner.id if owner else None
    pet_name    = pet.name
    time_str    = check_in_time.strftime('%I:%M %p')

    # Check not already checked in today
    from datetime import date
    existing = DaycareAttendance.query.filter(
        DaycareAttendance.enrollment_id == enrollment_id,
        db.func.date(DaycareAttendance.check_in_time) == date.today(),
        DaycareAttendance.check_out_time.is_(None)
    ).first()
    if existing:
        flash(f'{pet_name} is already checked in.', 'warning')
        return redirect(url_for('admin.daycare_dashboard'))

    attendance = DaycareAttendance(
        enrollment_id = enrollment_id,
        check_in_time = check_in_time
    )
    db.session.add(attendance)
    db.session.flush()
    attendance_id = attendance.id
    db.session.commit()

    # Auto-assign play group
    try:
        from app.models import PlayGroup
        weight = float(pet.weight) if pet.weight else 0
        size   = 'small' if weight < 25 else ('medium' if weight <= 50 else 'large')
        temp   = pet.temperament or 'calm'
        group  = (PlayGroup.query.filter_by(size_category=size, temperament=temp, active=True).first()
                  or PlayGroup.query.filter_by(size_category=size, temperament='mixed', active=True).first()
                  or PlayGroup.query.filter_by(size_category=size, active=True).first())
        if group:
            DaycareAttendance.query.filter_by(id=attendance_id).update({'play_group_id': group.id})
            db.session.commit()
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f'Play group assign failed on admin check-in: {e}')



    try:
        from app.audit_service import audit
        audit('daycare.checkin', 'daycare_attendance', attendance_id, pet_name,
              f'{pet_name} checked in to daycare at {time_str} by {current_user.first_name} {current_user.last_name}')
    except Exception: pass
    flash(f'{pet_name} checked in at {time_str}.', 'success')
    return redirect(url_for('admin.daycare_dashboard'))

@bp.route('/daycare/attendance/<int:attendance_id>/checkout', methods=['POST'])
@login_required
@admin_required
def daycare_checkout(attendance_id):
    """Check out a pet"""
    attendance = DaycareAttendance.query.get_or_404(attendance_id)

    # Capture all needed data before commit
    pet         = attendance.enrollment.pet
    owner       = pet.owner
    owner_phone = owner.phone if owner else None
    owner_id    = owner.id if owner else None
    pet_name    = pet.name
    check_out_time = datetime.now()
    time_str    = check_out_time.strftime('%I:%M %p')

    attendance.check_out_time = check_out_time
    db.session.commit()

    try:
        from app.audit_service import audit
        audit('daycare.checkout', 'daycare_attendance', attendance_id, pet_name,
              f'{pet_name} checked out of daycare at {time_str} by {current_user.first_name} {current_user.last_name}')
    except Exception: pass
    flash(f'{pet_name} checked out at {time_str}.', 'success')

    # Check punch card — issue loyalty credit if threshold reached
    try:
        from app.loyalty_service import check_daycare_punch
        if owner:
            credit = check_daycare_punch(owner, db)
            if credit:
                flash(f'🎉 {owner.first_name} has earned a free daycare day! A loyalty credit of ${float(credit.amount):.2f} has been added to their account.', 'success')
    except ImportError:
        pass  # loyalty_service not deployed
    except Exception as e:
        current_app.logger.error(f'Daycare punch card check failed: {e}')

    return redirect(url_for('admin.daycare_dashboard'))

@bp.route('/daycare/enrollment/<int:enrollment_id>/deactivate', methods=['POST'])
@login_required
@admin_required
def deactivate_daycare_enrollment(enrollment_id):
    """Deactivate daycare enrollment"""
    enrollment = DaycareEnrollment.query.get_or_404(enrollment_id)
    enrollment.active = False
    db.session.commit()
    try:
        from app.audit_service import audit
        audit('daycare.unenrolled', 'daycare_enrollment', enrollment_id, enrollment.pet.name,
              f'{enrollment.pet.name} removed from daycare by {current_user.first_name} {current_user.last_name}')
    except Exception: pass
    flash(f'{enrollment.pet.name} removed from daycare.', 'success')
    return redirect(url_for('admin.daycare_dashboard'))

@bp.route('/daycare/enrollment/<int:enrollment_id>/toggle-day/<string:day>', methods=['POST'])
@login_required
@admin_required
def toggle_daycare_day(enrollment_id, day):
    """Toggle a single daycare day on or off for an enrollment."""
    enrollment = DaycareEnrollment.query.get_or_404(enrollment_id)

    valid_days = ('monday', 'tuesday', 'wednesday', 'thursday')
    if day not in valid_days:
        flash('Invalid day.', 'danger')
        return redirect(url_for('admin.daycare_dashboard'))

    current_val = getattr(enrollment, day)
    setattr(enrollment, day, not current_val)
    db.session.commit()

    state = 'added' if not current_val else 'removed'
    flash(f'{enrollment.pet.name} — {day.title()} {state}.', 'success')
    return redirect(url_for('admin.daycare_dashboard'))


@bp.route('/daycare/enrollment/<int:enrollment_id>/toggle-special-rate', methods=['POST'])
@login_required
@admin_required
def toggle_special_rate(enrollment_id):
    """Toggle the $20/day special rate for a daycare enrollment."""
    from app.models import DaycareEnrollment
    enrollment = DaycareEnrollment.query.get_or_404(enrollment_id)

    if enrollment.special_rate:
        enrollment.special_rate = None
        flash(f'{enrollment.pet.name} — special rate removed, standard pricing restored.', 'info')
    else:
        enrollment.special_rate = 20.0
        flash(f'{enrollment.pet.name} — special rate applied ($20/day flat).', 'success')

    db.session.commit()
    return redirect(url_for('admin.daycare_dashboard'))


@bp.route('/daycare/schedule')
@login_required
@admin_required
def daycare_schedule():
    """Drag-and-drop daycare schedule board."""
    import json as _json

    pending = DaycareWaitlist.query.order_by(DaycareWaitlist.submitted_date.asc()).all()

    # Active enrollments, grouped by day
    enrollments = (
        DaycareEnrollment.query
        .filter_by(active=True)
        .join(Pet)
        .order_by(Pet.name)
        .all()
    )

    # For each pending entry, resolve the pet_id if a registered user exists
    # so the JS can pass pet_id on drop rather than a string name
    pending_data = []
    for entry in pending:
        pet_id = None
        if entry.user_id:
            matched = Pet.query.filter_by(
                user_id=entry.user_id, name=entry.pet_name, is_active=True
            ).first()
            if matched:
                pet_id = matched.id
        pending_data.append({
            'id':         entry.id,
            'name':       f'{entry.first_name} {entry.last_name}',
            'first_name': entry.first_name,
            'pet_name':   entry.pet_name or '',
            'breed':      entry.breed or '',
            'phone':      entry.phone or '',
            'user_id':    entry.user_id,
            'pet_id':     pet_id,
            'days': {
                'monday':    entry.monday,
                'tuesday':   entry.tuesday,
                'wednesday': entry.wednesday,
                'thursday':  entry.thursday,
            },
        })

    # Enrolled pets per day for the board columns
    days = ['monday', 'tuesday', 'wednesday', 'thursday']
    board = {day: [] for day in days}
    for enr in enrollments:
        for day in days:
            if getattr(enr, day):
                board[day].append({
                    'enrollment_id': enr.id,
                    'pet_id':        enr.pet.id,
                    'pet_name':      enr.pet.name,
                    'breed':         enr.pet.breed or '',
                    'owner':         f'{enr.pet.owner.first_name} {enr.pet.owner.last_name}',
                })

    return render_template(
        'admin/daycare_schedule.html',
        pending_json  = _json.dumps(pending_data),
        board_json    = _json.dumps(board),
    )


@bp.route('/daycare/schedule/enroll', methods=['POST'])
@login_required
@admin_required
def schedule_enroll():
    """AJAX: add a pet to a day on the schedule board."""
    data      = request.get_json(force=True)
    pet_id    = data.get('pet_id')
    day       = data.get('day')
    days_list = ['monday', 'tuesday', 'wednesday', 'thursday']

    if not pet_id or day not in days_list:
        return jsonify({'ok': False, 'error': 'Invalid pet or day'}), 400

    pet = Pet.query.get(pet_id)
    if not pet:
        return jsonify({'ok': False, 'error': 'Pet not found'}), 404

    enr = DaycareEnrollment.query.filter_by(pet_id=pet_id, active=True).first()
    if enr:
        setattr(enr, day, True)
    else:
        enr = DaycareEnrollment(
            pet_id=pet_id,
            enrollment_date=datetime.now().date(),
            active=True,
            **{d: (d == day) for d in days_list},
        )
        db.session.add(enr)
    db.session.commit()
    return jsonify({'ok': True, 'enrollment_id': enr.id})


@bp.route('/daycare/schedule/unenroll', methods=['POST'])
@login_required
@admin_required
def schedule_unenroll():
    """AJAX: remove a pet from a specific day (deactivate if no days remain)."""
    data      = request.get_json(force=True)
    pet_id    = data.get('pet_id')
    day       = data.get('day')
    days_list = ['monday', 'tuesday', 'wednesday', 'thursday']

    if not pet_id or day not in days_list:
        return jsonify({'ok': False, 'error': 'Invalid pet or day'}), 400

    enr = DaycareEnrollment.query.filter_by(pet_id=pet_id, active=True).first()
    if enr:
        setattr(enr, day, False)
        if not any(getattr(enr, d) for d in days_list):
            enr.active = False
        db.session.commit()
    return jsonify({'ok': True})


@bp.route('/daycare/waitlist/<int:entry_id>/approve-schedule', methods=['POST'])
@login_required
@admin_required
def approve_waitlist_schedule(entry_id):
    """AJAX: approve a waitlist request and enroll the pet for chosen days."""
    data      = request.get_json(force=True)
    pet_id    = data.get('pet_id')
    day_flags = data.get('days', {})   # {monday: true, tuesday: false, …}
    days_list = ['monday', 'tuesday', 'wednesday', 'thursday']

    if not pet_id:
        return jsonify({'ok': False, 'error': 'No pet selected'}), 400
    if not any(day_flags.get(d) for d in days_list):
        return jsonify({'ok': False, 'error': 'Select at least one day'}), 400

    entry = DaycareWaitlist.query.get(entry_id)
    if not entry:
        return jsonify({'ok': False, 'error': 'Waitlist entry not found'}), 404

    pet = Pet.query.get(pet_id)
    if not pet:
        return jsonify({'ok': False, 'error': 'Pet not found'}), 404

    enr = DaycareEnrollment.query.filter_by(pet_id=pet_id, active=True).first()
    if enr:
        for d in days_list:
            if day_flags.get(d):
                setattr(enr, d, True)
    else:
        enr = DaycareEnrollment(
            pet_id=pet_id,
            enrollment_date=datetime.now().date(),
            active=True,
            **{d: bool(day_flags.get(d)) for d in days_list},
        )
        db.session.add(enr)

    db.session.delete(entry)
    db.session.commit()

    try:
        from app.audit_service import audit
        audit('daycare.enrolled', 'daycare_enrollment', enr.id, pet.name,
              f'{pet.name} enrolled via schedule board by {current_user.first_name} {current_user.last_name}')
    except Exception:
        pass

    return jsonify({
        'ok': True,
        'enrollment_id': enr.id,
        'pet_id':    pet.id,
        'pet_name':  pet.name,
        'breed':     pet.breed or '',
        'owner':     f'{pet.owner.first_name} {pet.owner.last_name}',
    })


@bp.route('/daycare/waitlist/<int:entry_id>/contact-schedule', methods=['POST'])
@login_required
@admin_required
def contact_waitlist_schedule(entry_id):
    """AJAX: send SMS to a waitlist entry from the schedule board."""
    data         = request.get_json(force=True)
    message_type = data.get('message_type', 'standby')

    entry      = DaycareWaitlist.query.get_or_404(entry_id)
    phone      = entry.phone
    first_name = entry.first_name
    pet_name   = entry.pet_name or 'your pup'
    business   = current_app.config.get('BUSINESS_NAME', 'Ruff Life Retreat')
    linked_user_id = entry.user_id

    if entry.user_id:
        linked = User.query.get(entry.user_id)
        if linked and linked.phone:
            phone = linked.phone

    if message_type == 'standby':
        body = (
            f"Hi {first_name}! Thank you for your interest in {business} Doggy Daycare. "
            f"We don't have an opening available at this time, but we've placed {pet_name} "
            f"on our standby list and will reach out as soon as a spot opens up! — {business}"
        )
    else:
        body = (
            f"Hi {first_name}! Great news — a spot has opened up in our Doggy Daycare program! "
            f"We'd love to get {pet_name} enrolled. Please reply to this message or give us a call "
            f"to get started. — {business}"
        )

    try:
        from app.sms_service import _normalize_phone
        from app.models import SmsMessage
        from twilio.rest import Client

        to_e164     = _normalize_phone(phone)
        from_number = current_app.config.get('TWILIO_PHONE_NUMBER')
        client      = Client(current_app.config.get('TWILIO_ACCOUNT_SID'),
                             current_app.config.get('TWILIO_AUTH_TOKEN'))
        message     = client.messages.create(body=body, from_=from_number, to=to_e164)

        log = SmsMessage(
            user_id=linked_user_id, direction='outbound',
            from_number=from_number, to_number=to_e164,
            body=body, twilio_sid=message.sid, is_read=True,
        )
        db.session.add(log)
        entry.contacted = True
        db.session.commit()
        return jsonify({'ok': True})
    except Exception as e:
        current_app.logger.error(f'Schedule board SMS failed for entry {entry_id}: {e}')
        return jsonify({'ok': False, 'error': str(e)}), 500


@bp.route('/daycare/waitlist/<int:entry_id>/dismiss', methods=['POST'])
@login_required
@admin_required
def dismiss_waitlist_entry(entry_id):
    """AJAX: remove a waitlist entry without enrolling (decline/dismiss)."""
    entry = DaycareWaitlist.query.get_or_404(entry_id)
    db.session.delete(entry)
    db.session.commit()
    return jsonify({'ok': True})


@bp.route('/daycare/waitlist')
@login_required
@admin_required
def daycare_waitlist_admin():
    """View full daycare waitlist"""
    pending = DaycareWaitlist.query.filter_by(contacted=False).order_by(
        DaycareWaitlist.submitted_date.asc()
    ).all()

    # Build pet lists per entry for the Approve modal — serialised to JSON here
    # so the template never has to deal with escaping
    import json as _json
    entry_pets_map = {}
    for entry in pending:
        if entry.user_id:
            pets_qs = Pet.query.filter_by(user_id=entry.user_id, is_active=True).order_by(Pet.name).all()
        else:
            pets_qs = Pet.query.filter_by(is_active=True).order_by(Pet.name).all()
        entry_pets_map[entry.id] = [{'id': p.id, 'name': p.name} for p in pets_qs]

    # JSON string keyed by string (JSON keys must be strings)
    entry_pets_json = _json.dumps({str(k): v for k, v in entry_pets_map.items()})

    # Days of interest per entry for the Approve modal pre-selection
    entry_days_map = {}
    for entry in pending:
        entry_days_map[str(entry.id)] = {
            'monday':    entry.monday,
            'tuesday':   entry.tuesday,
            'wednesday': entry.wednesday,
            'thursday':  entry.thursday,
        }
    entry_days_json = _json.dumps(entry_days_map)

    return render_template('admin/daycare_waitlist.html',
                           pending=pending,
                           entry_pets_json=entry_pets_json,
                           entry_days_json=entry_days_json)


@bp.route('/daycare/waitlist/mark-contacted/<int:entry_id>', methods=['POST'])
@login_required
@admin_required
def mark_waitlist_contacted(entry_id):
    """Toggle contacted status for waitlist entry (legacy — kept for compatibility)"""
    entry = DaycareWaitlist.query.get_or_404(entry_id)
    entry.contacted = not entry.contacted
    db.session.commit()
    status = 'contacted' if entry.contacted else 'not contacted'
    flash(f'{entry.first_name} {entry.last_name} marked as {status}.', 'success')
    return redirect(url_for('admin.daycare_waitlist_admin'))


@bp.route('/daycare/waitlist/<int:entry_id>/approve', methods=['POST'])
@login_required
@admin_required
def approve_waitlist_entry(entry_id):
    """Enroll a pet from the waitlist and remove the waitlist entry."""
    entry     = DaycareWaitlist.query.get_or_404(entry_id)
    pet_id    = request.form.get('pet_id', type=int)
    monday    = bool(request.form.get('monday'))
    tuesday   = bool(request.form.get('tuesday'))
    wednesday = bool(request.form.get('wednesday'))
    thursday  = bool(request.form.get('thursday'))
    friday    = bool(request.form.get('friday'))
    notes     = request.form.get('notes', '')

    if not pet_id or not any([monday, tuesday, wednesday, thursday, friday]):
        flash('Please select a pet and at least one day.', 'danger')
        return redirect(url_for('admin.daycare_waitlist_admin'))

    pet = Pet.query.get_or_404(pet_id)
    enrollment = DaycareEnrollment(
        pet_id          = pet_id,
        enrollment_date = datetime.now().date(),
        monday=monday, tuesday=tuesday, wednesday=wednesday,
        thursday=thursday, friday=friday,
        notes=notes, active=True,
    )
    db.session.add(enrollment)
    db.session.delete(entry)
    db.session.commit()

    try:
        from app.audit_service import audit
        audit('daycare.enrolled', 'daycare_enrollment', enrollment.id, pet.name,
              f'{pet.name} enrolled from waitlist by {current_user.first_name} {current_user.last_name}')
    except Exception:
        pass

    flash(f'{pet.name} enrolled in daycare and removed from the waitlist.', 'success')
    return redirect(url_for('admin.daycare_dashboard'))


@bp.route('/daycare/waitlist/<int:entry_id>/contact', methods=['POST'])
@login_required
@admin_required
def contact_waitlist_entry(entry_id):
    """Send a pre-written SMS to a waitlist customer and mark them as contacted."""
    entry        = DaycareWaitlist.query.get_or_404(entry_id)
    message_type = request.form.get('message_type', 'standby')  # 'standby' or 'opening'

    # Prefer linked user's phone number
    phone = entry.phone
    linked_user_id = entry.user_id
    if entry.user_id:
        linked = User.query.get(entry.user_id)
        if linked and linked.phone:
            phone = linked.phone

    first_name = entry.first_name
    pet_name   = entry.pet_name or 'your pup'
    business   = current_app.config.get('BUSINESS_NAME', 'Ruff Life Retreat')

    if message_type == 'standby':
        body = (
            f"Hi {first_name}! Thank you for your interest in {business} Doggy Daycare. "
            f"We don't have an opening available at this time, but we've placed {pet_name} "
            f"on our standby list and will reach out as soon as a spot opens up! — {business}"
        )
    else:
        body = (
            f"Hi {first_name}! Great news — a spot has opened up in our Doggy Daycare program! "
            f"We'd love to get {pet_name} enrolled. Please reply to this message or give us a call "
            f"to get started. — {business}"
        )

    try:
        from app.sms_service import _normalize_phone
        from app.models import SmsMessage
        from twilio.rest import Client

        to_e164     = _normalize_phone(phone)
        from_number = current_app.config.get('TWILIO_PHONE_NUMBER')
        client      = Client(current_app.config.get('TWILIO_ACCOUNT_SID'),
                             current_app.config.get('TWILIO_AUTH_TOKEN'))
        message     = client.messages.create(body=body, from_=from_number, to=to_e164)

        log = SmsMessage(
            user_id     = linked_user_id,
            direction   = 'outbound',
            from_number = from_number,
            to_number   = to_e164,
            body        = body,
            twilio_sid  = message.sid,
            is_read     = True,
        )
        db.session.add(log)
        entry.contacted = True
        db.session.commit()
        flash(f'Message sent to {first_name} {entry.last_name}.', 'success')
    except Exception as e:
        current_app.logger.error(f'Waitlist SMS failed for entry {entry_id}: {e}')
        flash(f'SMS failed: {e}', 'danger')

    return redirect(url_for('admin.daycare_waitlist_admin'))

def get_available_time_slots(target_date, booking_type='check_in'):
    """
    Get available 30-minute time slots for a given date.
    Enforces day-of-week drop/pickup schedule:
        Mon-Fri  : 07:00 - 18:00
        Saturday : 07:00 - 11:00  and  17:00 - 18:00
        Sunday   : 15:00 - 18:00

    Args:
        target_date: Date object to check availability
        booking_type: 'check_in' or 'check_out'

    Returns:
        List of tuples: [(time_string, display_string), ...]
    """
    weekday = target_date.weekday()  # 0=Mon, 5=Sat, 6=Sun

    if weekday == 6:        # Sunday
        windows = [(15, 18)]
    elif weekday == 5:      # Saturday
        windows = [(7, 11), (17, 18)]
    else:                   # Mon-Fri
        windows = [(7, 18)]

    all_slots = []
    for (start_h, end_h) in windows:
        hour   = start_h
        minute = 0
        while (hour < end_h) or (hour == end_h and minute == 0):
            time_str = "%02d:%02d" % (hour, minute)
            if hour < 12:
                display = "%d:%02d AM" % (hour, minute)
            elif hour == 12:
                display = "12:%02d PM" % minute
            else:
                display = "%d:%02d PM" % (hour - 12, minute)
            all_slots.append((time_str, display))
            minute += 30
            if minute >= 60:
                minute = 0
                hour  += 1

    # Filter out already-taken slots
    active_bookings = Boarding.query.filter_by(status='active').all()
    available_slots = []

    for time_str, display in all_slots:
        is_available = True
        if booking_type == 'check_in':
            for booking in active_bookings:
                if booking.check_in_date == target_date and booking.check_in_time == time_str:
                    is_available = False
                    break
        elif booking_type == 'check_out':
            for booking in active_bookings:
                if booking.check_out_date == target_date and booking.check_out_time == time_str:
                    is_available = False
                    break
        if is_available:
            available_slots.append((time_str, display))

    return available_slots


@bp.route('/boarding/available-times', methods=['GET'])
@login_required
@admin_required
def get_available_times():
    """AJAX endpoint to get available time slots for a given date"""
    date_str = request.args.get('date')
    booking_type = request.args.get('type', 'check_in')
    
    try:
        target_date = datetime.strptime(date_str, '%Y-%m-%d').date()
    except (ValueError, TypeError):
        return jsonify({'error': 'Invalid date format'}), 400
    
    available_slots = get_available_time_slots(target_date, booking_type)
    
    # Return as JSON with time and display name
    slots_data = [{'time': time_str, 'display': display} for time_str, display in available_slots]
    
    return jsonify(slots_data)


@bp.route('/invoices/audit')
@login_required
@admin_required
def invoice_audit():
    """Invoice register — Open, Paid, Adjustments, SMS History."""
    from app.models import SmsMessage, Payment, Boarding, DaycareAttendance, DaycareEnrollment, InvoiceAdjustment
    from datetime import date, timedelta

    today = date.today()

    # ── TAB 1: Open Invoices ──────────────────────────────────────────────
    # Find every customer with unpaid boarding or daycare
    open_invoices = []
    customers_with_pets = User.query.filter_by(role='customer', is_active=True).all()

    for c in customers_with_pets:
        boarding_balance = 0.0
        daycare_balance  = 0.0
        boarding_count   = 0
        daycare_count    = 0
        oldest_unpaid    = None

        from app.rate_resolver import get_rates
        rates = get_rates(c)

        for pet in c.pets:
            # Unpaid completed boardings
            boardings = Boarding.query.filter_by(
                pet_id=pet.id, status='completed'
            ).filter(Boarding.payment_id == None).all()

            for b in boardings:
                days     = _boarding_days(b)
                siblings = Boarding.query.filter_by(
                    user_id=c.id,
                    check_in_date=b.check_in_date,
                    check_out_date=b.check_out_date,
                    status='completed'
                ).order_by(Boarding.pet_id.asc()).all()
                is_first = (not siblings) or siblings[0].pet_id == pet.id
                from app.rate_resolver import get_pet_boarding_rate as _gpbr3
                rate     = _gpbr3(pet, c, is_additional=not is_first)
                _, addon_total = _parse_addons_from_notes(b.special_notes or '')
                if addon_total == 0:
                    try:
                        from app.models import Appointment as _Ar, ServiceType as _STr
                        _svcr = _STr.query.filter(_STr.name.ilike('%boarding%')).first()
                        if _svcr:
                            _ar = _Ar.query.filter_by(
                                pet_id=pet.id, user_id=c.id,
                                service_type_id=_svcr.id
                            ).order_by(_Ar.id.desc()).first()
                            if _ar and _ar.notes:
                                _, addon_total = _parse_addons_from_notes(_ar.notes)
                    except Exception:
                        pass
                boarding_balance += rate * days + addon_total
                boarding_count   += 1
                if oldest_unpaid is None or b.check_out_date < oldest_unpaid:
                    oldest_unpaid = b.check_out_date

            # Unpaid daycare
            for enr in DaycareEnrollment.query.filter_by(pet_id=pet.id).all():
                atts = DaycareAttendance.query.filter_by(
                    enrollment_id=enr.id
                ).filter(
                    DaycareAttendance.check_out_time != None,
                    DaycareAttendance.payment_id == None
                ).all()
                for att in atts:
                    week_start = att.check_in_time.date() - timedelta(days=att.check_in_time.weekday())
                    week_end   = week_start + timedelta(days=6)
                    wc = DaycareAttendance.query.filter(
                        DaycareAttendance.enrollment_id == enr.id,
                        DaycareAttendance.check_in_time >= week_start,
                        DaycareAttendance.check_in_time <= week_end
                    ).count()
                    rate = enr.special_rate if enr.special_rate else (rates['daycare'] if wc > 1 else float(current_app.config.get('DAYCARE_RATE_SINGLE', 25.0)))
                    daycare_balance += rate
                    daycare_count   += 1

        if boarding_balance > 0 or daycare_balance > 0:
            days_outstanding = (today - oldest_unpaid).days if oldest_unpaid else 0
            open_invoices.append({
                'customer':          c,
                'boarding_balance':  boarding_balance,
                'daycare_balance':   daycare_balance,
                'total_balance':     boarding_balance + daycare_balance,
                'boarding_count':    boarding_count,
                'daycare_count':     daycare_count,
                'days_outstanding':  days_outstanding,
            })

    open_invoices.sort(key=lambda x: x['total_balance'], reverse=True)
    total_open = sum(i['total_balance'] for i in open_invoices)

    # ── TAB 2: Paid Invoices ──────────────────────────────────────────────
    paid_invoices = (Payment.query
        .filter_by(status='paid')
        .order_by(Payment.payment_date.desc())
        .all())
    total_collected = sum(p.amount for p in paid_invoices)

    # ── TAB 3: Adjustments ───────────────────────────────────────────────
    adjustments = (InvoiceAdjustment.query
        .order_by(InvoiceAdjustment.created_at.desc())
        .all())

    # ── TAB 4: SMS History ────────────────────────────────────────────────
    invoice_msgs = (SmsMessage.query
        .filter(SmsMessage.direction == 'outbound',
                SmsMessage.body.like('%rufflife.app/invoice/%'))
        .order_by(SmsMessage.created_at.desc()).all())

    estimate_msgs = (SmsMessage.query
        .filter(SmsMessage.direction == 'outbound',
                db.or_(SmsMessage.body.like('%rufflife.app/estimate/%'),
                       SmsMessage.body.like('%[checkout-estimate]%')))
        .order_by(SmsMessage.created_at.desc()).all())

    sms_rows = []
    for msg in invoice_msgs:
        sms_rows.append({
            'type': 'Invoice', 'type_color': '#0d6efd',
            'customer': msg.user, 'sent_at': msg.created_at,
            'to_number': msg.to_number, 'body': msg.body, 'auto': False,
        })
    for msg in estimate_msgs:
        is_auto = '[checkout-estimate]' in (msg.body or '')
        sms_rows.append({
            'type': 'Estimate (Auto)' if is_auto else 'Estimate',
            'type_color': '#fd7e14' if is_auto else '#FFC107',
            'customer': msg.user, 'sent_at': msg.created_at,
            'to_number': msg.to_number, 'body': msg.body, 'auto': is_auto,
        })
    sms_rows.sort(key=lambda r: r['sent_at'], reverse=True)

    total_sent       = len(sms_rows)
    invoices_sent    = sum(1 for r in sms_rows if r['type'] == 'Invoice')
    estimates_sent   = sum(1 for r in sms_rows if 'Estimate' in r['type'])
    auto_sent        = sum(1 for r in sms_rows if r['auto'])
    unique_customers = len({r['customer'].id for r in sms_rows if r['customer']})

    return render_template('admin/invoice_audit.html',
        today=today,
        # Tab 1
        open_invoices=open_invoices,
        total_open=total_open,
        # Tab 2
        paid_invoices=paid_invoices,
        total_collected=total_collected,
        # Tab 3
        adjustments=adjustments,
        # Tab 4
        sms_rows=sms_rows,
        total_sent=total_sent,
        invoices_sent=invoices_sent,
        estimates_sent=estimates_sent,
        auto_sent=auto_sent,
        unique_customers=unique_customers,
    )


@bp.route('/boarding/send-checkout-estimates', methods=['POST'])
@login_required
@admin_required
def run_checkout_estimates():
    """Manually trigger checkout day estimate SMS for all pets checking out today."""
    from app.checkout_estimate import run_checkout_estimates as do_run
    try:
        summary = do_run(current_app._get_current_object())
        if summary['sent'] > 0:
            flash(f"Checkout estimates sent — {summary['sent']} SMS sent to today's pickups.", 'success')
        else:
            flash('No checkouts today, or all estimates already sent.', 'info')
    except Exception as e:
        flash(f'Failed: {e}', 'danger')
    return redirect(url_for('admin.boarding_dashboard'))


@bp.route('/boarding/dashboard')
@login_required
@admin_required
def boarding_dashboard():
    """Boarding management dashboard with pending requests, active guests, and calendar."""
    from app.models import Appointment
    import calendar as cal_mod

    today = datetime.now().date()

    # ── Pending boarding appointment requests from customers ──────────────────
    boarding_service = ServiceType.query.filter(
        ServiceType.name.ilike('%boarding%')
    ).first()

    pending_requests = []
    if boarding_service:
        pending_requests = (Appointment.query
            .filter_by(service_type_id=boarding_service.id, status='pending')
            .order_by(Appointment.appointment_date.asc())
            .all())

    # ── Active boarding reservations — split by check-in status ─────────────
    all_active = Boarding.query.filter_by(status='active').order_by(
        Boarding.check_in_date.asc()
    ).all()

    checked_in_bookings = [b for b in all_active if b.checked_in]
    upcoming_bookings   = [b for b in all_active if not b.checked_in]

    # ── Completed bookings (last 30 days) ─────────────────────────────────────
    thirty_days_ago = today - timedelta(days=30)
    completed_bookings = Boarding.query.filter(
        Boarding.status == 'completed',
        Boarding.completed_at >= thirty_days_ago
    ).order_by(Boarding.completed_at.desc()).all()

    # ── Calendar — all active boarding regardless of date ────────────────
    future_bookings = Boarding.query.filter(
        Boarding.status == 'active',
        Boarding.check_out_date >= today
    ).all()

    # Build rich calendar data — each date maps to pet names (for highlighting)
    # and detailed booking info (for modal popup)
    boarding_dates  = {}  # date -> [pet names]  (for Jinja calendar)
    calendar_detail = {}  # date -> [{name, owner, checkin, checkout, addons, status}]

    # Pre-fetch boarding service type and related appointments once (not per booking)
    import re
    _boarding_svc = ServiceType.query.filter(ServiceType.name.ilike('%boarding%')).first()
    _appt_notes = {}  # (pet_id, user_id) -> notes string
    if _boarding_svc:
        from app.models import Appointment as _Appt
        for _a in _Appt.query.filter_by(service_type_id=_boarding_svc.id).all():
            key = (_a.pet_id, _a.user_id)
            if _a.notes and 'Add-ons:' in _a.notes:
                _appt_notes[key] = _a.notes

    for b in future_bookings:
        # Parse add-ons from pre-fetched appointment notes
        addons = []
        try:
            notes = _appt_notes.get((b.pet_id, b.user_id), '')
            if notes:
                m = re.search(r'Add-ons:\s*(.+)', notes)
                if m:
                    addons = [a.strip() for a in m.group(1).split(',')]
        except Exception:
            pass

        owner = b.pet.owner
        booking_info = {
            'id':        b.id,
            'name':      b.pet.name,
            'breed':     b.pet.breed or 'Dog',
            'owner':     f'{owner.first_name} {owner.last_name}' if owner else '—',
            'phone':     owner.phone or '—' if owner else '—',
            'checkin':   b.check_in_date.isoformat(),
            'checkout':  b.check_out_date.isoformat(),
            'cin_time':  _fmt_t(b.check_in_time or '08:00'),
            'cout_time': _fmt_t(b.check_out_time or '17:00'),
            'kennel':    (f'{(b.kennel_type or "Kennel").title()} #{b.kennel_number}') if b.kennel_number else None,
            'addons':    addons,
            'checked_in': bool(b.checked_in),
        }

        d = b.check_in_date
        while d <= b.check_out_date:
            ds = d.isoformat()
            boarding_dates.setdefault(ds, [])
            boarding_dates[ds].append(b.pet.name)
            calendar_detail.setdefault(ds, [])
            # Tag each entry with what's happening on this specific day
            entry = dict(booking_info)
            entry['is_checkin']  = (d == b.check_in_date)
            entry['is_checkout'] = (d == b.check_out_date)
            calendar_detail[ds].append(entry)
            d += timedelta(days=1)

    # Build 2-month calendar — weeks start Sunday to match Su/Mo/Tu/We/Th/Fr/Sa headers
    # cal_offset allows staff to page forward/back through months
    cal_mod.setfirstweekday(6)  # 6 = Sunday
    cal_offset = request.args.get('cal_offset', 0, type=int)
    # Clamp: don't allow going before current month
    cal_offset = max(0, cal_offset)
    months = []
    for offset in range(2):
        total_offset = cal_offset + offset
        m = (today.month - 1 + total_offset) % 12 + 1
        y = today.year + ((today.month - 1 + total_offset) // 12)
        weeks = cal_mod.monthcalendar(y, m)
        months.append({'year': y, 'month': m,
                       'name': cal_mod.month_name[m], 'weeks': weeks})

    import json
    from app.settings_service import get_kennel_capacity
    kennel_capacity = get_kennel_capacity()
    all_pets = Pet.query.filter_by(is_active=True).order_by(Pet.name).all()
    today_check_in_slots = get_available_time_slots(today, 'check_in')

    return render_template('admin/boarding_dashboard.html',
                         pending_requests=pending_requests,
                         all_bookings=all_active,
                         checked_in_bookings=checked_in_bookings,
                         upcoming_bookings=upcoming_bookings,
                         completed_bookings=completed_bookings,
                         all_pets=all_pets,
                         today=today,
                         today_check_in_slots=today_check_in_slots,
                         months=months,
                         cal_offset=cal_offset,
                         kennel_capacity=kennel_capacity,
                         boarding_dates=json.dumps(boarding_dates),
                         boarding_dates_parsed=boarding_dates,
                         calendar_detail=json.dumps(calendar_detail))


# ============================================================
# OPERATIONS DASHBOARD
# ============================================================

@bp.route('/ops/dashboard')
@login_required
@admin_required
def ops_dashboard():
    """Combined Operations Dashboard: all currently checked-in pets + today's schedule."""
    import json as _json

    today = datetime.now().date()

    # ── Daycare: currently checked in ─────────────────────────────────────────
    _today_att = DaycareAttendance.query.filter(
        DaycareAttendance.check_in_time >= datetime.combine(today, datetime.min.time()),
        DaycareAttendance.check_in_time <= datetime.combine(today, datetime.max.time()),
        DaycareAttendance.check_out_time == None,
    ).all()

    daycare_checked_in = []
    for a in _today_att:
        enr = DaycareEnrollment.query.get(a.enrollment_id)
        if enr and enr.pet:
            daycare_checked_in.append({
                'attendance': a,
                'pet':        enr.pet,
                'owner':      enr.pet.owner,
                'enrollment': enr,
            })

    # ── Boarding: currently checked in ────────────────────────────────────────
    boarding_checked_in = Boarding.query.filter_by(
        status='active', checked_in=True
    ).order_by(Boarding.check_in_date.asc()).all()

    # ── Today's daycare expected (not yet checked in) ─────────────────────────
    _dc_fields = {0: 'monday', 1: 'tuesday', 2: 'wednesday', 3: 'thursday'}
    dow = today.weekday()
    daycare_expected_today = []
    _checked_in_ids = {a.enrollment_id for a in _today_att}
    if dow in _dc_fields:
        field = _dc_fields[dow]
        enrollments = (DaycareEnrollment.query.filter_by(active=True, is_walkin=False)
                       .join(Pet, DaycareEnrollment.pet_id == Pet.id)
                       .order_by(Pet.name).all())
        for e in enrollments:
            if getattr(e, field) and e.id not in _checked_in_ids:
                daycare_expected_today.append(e)
        walkins = (DaycareEnrollment.query.filter_by(active=False, is_walkin=True)
                   .join(Pet, DaycareEnrollment.pet_id == Pet.id)
                   .order_by(Pet.name).all())
        for e in walkins:
            if getattr(e, field) and e.id not in _checked_in_ids:
                daycare_expected_today.append(e)

    # ── Today's boarding arrivals / departures ────────────────────────────────
    boarding_arrivals_today = Boarding.query.filter(
        Boarding.status == 'active',
        Boarding.check_in_date == today,
        Boarding.checked_in == False,
    ).all()
    boarding_departures_today = Boarding.query.filter(
        Boarding.status == 'active',
        Boarding.check_out_date == today,
    ).all()

    # ── Daycare capacity today ────────────────────────────────────────────────
    if dow in _dc_fields:
        field = _dc_fields[dow]
        daycare_capacity_today = DaycareEnrollment.query.filter_by(active=True).filter(
            getattr(DaycareEnrollment, field) == True
        ).count()
    else:
        daycare_capacity_today = 0
    DC_MAX = 15

    # ── Ops notes for today ───────────────────────────────────────────────────
    today_notes = OpsNote.query.filter_by(note_date=today).all()
    pet_notes, day_notes = {}, []
    for n in today_notes:
        if n.pet_id:
            pet_notes.setdefault(n.pet_id, []).append(n)
        else:
            day_notes.append(n)

    # ── All pets (walk-in modal) ──────────────────────────────────────────────
    all_pets = (Pet.query.join(User, Pet.user_id == User.id)
                .filter(User.is_active == True)
                .order_by(Pet.name).all())

    # ── Pending daycare requests ──────────────────────────────────────────────
    pending_requests = (DaycareWaitlist.query
                        .filter_by(contacted=False)
                        .order_by(DaycareWaitlist.submitted_date.asc()).all())
    _req_pets_map, _req_days_map = {}, {}
    for req in pending_requests:
        pets_qs = (Pet.query.filter_by(user_id=req.user_id, is_active=True).order_by(Pet.name).all()
                   if req.user_id else
                   Pet.query.filter_by(is_active=True).order_by(Pet.name).all())
        _req_pets_map[req.id] = [{'id': p.id, 'name': p.name} for p in pets_qs]
        _req_days_map[str(req.id)] = {
            'monday': req.monday, 'tuesday': req.tuesday,
            'wednesday': req.wednesday, 'thursday': req.thursday,
        }
    req_pets_json = _json.dumps({str(k): v for k, v in _req_pets_map.items()})
    req_days_json = _json.dumps(_req_days_map)

    return render_template('admin/ops_dashboard.html',
                           daycare_checked_in=daycare_checked_in,
                           boarding_checked_in=boarding_checked_in,
                           daycare_expected_today=daycare_expected_today,
                           boarding_arrivals_today=boarding_arrivals_today,
                           boarding_departures_today=boarding_departures_today,
                           daycare_capacity_today=daycare_capacity_today,
                           dc_max=DC_MAX,
                           pet_notes=pet_notes,
                           day_notes=day_notes,
                           today=today,
                           all_pets=all_pets,
                           pending_requests=pending_requests,
                           req_pets_json=req_pets_json,
                           req_days_json=req_days_json)


# ── Daycare walk-in ───────────────────────────────────────────────────────────

@bp.route('/daycare/walkin', methods=['POST'])
@login_required
@admin_required
def daycare_walkin():
    data     = request.get_json(silent=True) or {}
    pet_id   = data.get('pet_id')
    action   = data.get('action', 'expected')
    date_str = data.get('date') or datetime.now().date().isoformat()
    if not pet_id:
        return jsonify({'ok': False, 'error': 'Pet is required.'})
    try:
        target_date = datetime.strptime(date_str, '%Y-%m-%d').date()
    except ValueError:
        return jsonify({'ok': False, 'error': 'Invalid date.'})
    _dc_fields = {0: 'monday', 1: 'tuesday', 2: 'wednesday', 3: 'thursday', 4: 'friday'}
    dow = target_date.weekday()
    if dow not in _dc_fields:
        return jsonify({'ok': False, 'error': 'Daycare is only available Mon–Fri.'})
    field = _dc_fields[dow]
    pet   = Pet.query.get(int(pet_id))
    if not pet:
        return jsonify({'ok': False, 'error': 'Pet not found.'})
    enr = DaycareEnrollment.query.filter_by(pet_id=pet.id, is_walkin=True).first()
    if enr:
        enr.monday    = (field == 'monday')
        enr.tuesday   = (field == 'tuesday')
        enr.wednesday = (field == 'wednesday')
        enr.thursday  = (field == 'thursday')
        enr.friday    = (field == 'friday')
        enr.active    = False
    else:
        enr = DaycareEnrollment(
            pet_id=pet.id, enrollment_date=target_date, active=False, is_walkin=True,
            monday=(field=='monday'), tuesday=(field=='tuesday'),
            wednesday=(field=='wednesday'), thursday=(field=='thursday'), friday=(field=='friday'),
        )
        db.session.add(enr)
    db.session.flush()
    if action == 'checkin':
        today = datetime.now().date()
        existing = DaycareAttendance.query.filter(
            DaycareAttendance.enrollment_id == enr.id,
            db.func.date(DaycareAttendance.check_in_time) == today,
            DaycareAttendance.check_out_time.is_(None)
        ).first()
        if existing:
            db.session.rollback()
            return jsonify({'ok': False, 'error': f'{pet.name} is already checked in today.'})
        db.session.add(DaycareAttendance(enrollment_id=enr.id, check_in_time=datetime.now()))
    db.session.commit()
    return jsonify({'ok': True, 'action': action, 'pet_name': pet.name})


# ── OpsNote AJAX ─────────────────────────────────────────────────────────────

@bp.route('/ops/note', methods=['POST'])
@login_required
@admin_required
def ops_note_create():
    data      = request.get_json(silent=True) or {}
    note_text = (data.get('note') or '').strip()
    if not note_text:
        return jsonify({'ok': False, 'error': 'Note cannot be empty'}), 400
    from datetime import date as _date
    try:
        note_date = _date.fromisoformat(data.get('note_date') or datetime.now().date().isoformat())
    except ValueError:
        return jsonify({'ok': False, 'error': 'Invalid date'}), 400
    pet_id = data.get('pet_id')
    n = OpsNote(note_date=note_date, pet_id=int(pet_id) if pet_id else None,
                note=note_text, flag_type=data.get('flag_type', 'info'),
                created_by=current_user.id)
    db.session.add(n)
    db.session.commit()
    return jsonify({'ok': True, 'id': n.id, 'note': n.note, 'flag_type': n.flag_type})


@bp.route('/ops/note/<int:note_id>', methods=['DELETE'])
@login_required
@admin_required
def ops_note_delete(note_id):
    n = OpsNote.query.get_or_404(note_id)
    db.session.delete(n)
    db.session.commit()
    return jsonify({'ok': True})


def _check_boarding_conflict(pet_id, check_in_date, check_out_date, exclude_booking_id=None):
    """
    Returns a conflicting Boarding record if the pet already has an active
    reservation that overlaps with the given date range, otherwise None.
    Two stays overlap if one starts before the other ends:
        existing.check_in_date < new.check_out_date
        AND existing.check_out_date > new.check_in_date
    """
    query = Boarding.query.filter(
        Boarding.pet_id == pet_id,
        Boarding.status == 'active',
        Boarding.check_in_date < check_out_date,
        Boarding.check_out_date > check_in_date
    )
    if exclude_booking_id:
        query = query.filter(Boarding.id != exclude_booking_id)
    return query.first()


def _check_customer_vaccinations(user_id):
    """
    Returns a list of (pet_name, reason) tuples for pets that are
    non-compliant — either missing records entirely or all records expired.
    Used to block boarding reservations.
    """
    from app.models import VaccinationRecord
    from datetime import date
    today = date.today()
    owner = User.query.get(user_id)
    if not owner:
        return []
    non_compliant = []
    for pet in owner.pets:
        if not pet.is_active:
            continue
        records = VaccinationRecord.query.filter_by(pet_id=pet.id).all()
        if not records:
            non_compliant.append((pet.name, 'no vaccination records on file'))
        else:
            # Check if ALL records are expired
            valid = [r for r in records if r.expiration_date and r.expiration_date >= today]
            if not valid:
                non_compliant.append((pet.name, 'all vaccination records are expired'))
    return non_compliant


@bp.route('/boarding/create', methods=['POST'])
@login_required
@admin_required
def create_boarding():
    """Create a new boarding reservation"""
    pet_id = request.form.get('pet_id', type=int)
    check_in_date_str = request.form.get('check_in_date')
    check_in_time = request.form.get('check_in_time')
    check_out_date_str = request.form.get('check_out_date')
    check_out_time = request.form.get('check_out_time')
    medications = request.form.get('medications', '')
    feeding_schedule = request.form.get('feeding_schedule', '')
    special_notes = request.form.get('special_notes', '')

    # Build add-on note string
    addon_map = {
        'addon_spa_bath_nails': 'Spa Bath + Nail Trim ($30)',
        'addon_spa_bath':       'Spa Bath ($20)',
        'addon_nail_trim':      'Nail Trim ($15)',
    }
    selected_addons = [label for key, label in addon_map.items() if request.form.get(key)]
    addon_note = ('\nAdd-ons: ' + ', '.join(selected_addons)) if selected_addons else ''

    if not pet_id or not check_in_date_str or not check_in_time or not check_out_date_str or not check_out_time:
        flash('Pet, check-in date/time, and check-out date/time are required.', 'danger')
        return redirect(url_for('admin.boarding_dashboard'))

    try:
        check_in_date  = datetime.strptime(check_in_date_str, '%Y-%m-%d').date()
        check_out_date = datetime.strptime(check_out_date_str, '%Y-%m-%d').date()
    except ValueError:
        flash('Invalid date format.', 'danger')
        return redirect(url_for('admin.boarding_dashboard'))

    try:
        datetime.strptime(check_in_time, '%H:%M')
        datetime.strptime(check_out_time, '%H:%M')
    except ValueError:
        flash('Invalid time format.', 'danger')
        return redirect(url_for('admin.boarding_dashboard'))

    if check_out_date < check_in_date or (check_out_date == check_in_date and check_out_time <= check_in_time):
        flash('Check-out must be after check-in.', 'danger')
        return redirect(url_for('admin.boarding_dashboard'))

    pet = Pet.query.get_or_404(pet_id)
    user_id = pet.user_id

    # Vaccination check — all active pets on the account must be compliant
    missing_vaccs = _check_customer_vaccinations(user_id)
    if missing_vaccs:
        issues = '; '.join(f'{name} ({reason})' for name, reason in missing_vaccs)
        flash(
            f'Cannot create reservation — the following pet(s) have vaccination issues: '
            f'{issues}. Please upload current vaccination records before booking.',
            'danger'
        )
        return redirect(url_for('admin.boarding_dashboard'))

    # Conflict check
    conflict = _check_boarding_conflict(pet_id, check_in_date, check_out_date)
    if conflict:
        flash(
            f'{pet.name} already has an active boarding reservation from '
            f'{conflict.check_in_date.strftime("%b %d")} to '
            f'{conflict.check_out_date.strftime("%b %d, %Y")}. '
            f'Please adjust the dates or complete the existing reservation first.',
            'danger'
        )
        return redirect(url_for('admin.boarding_dashboard'))

    # Create boarding reservation
    booking = Boarding(
        pet_id=pet_id,
        user_id=user_id,
        check_in_date=check_in_date,
        check_in_time=check_in_time,
        check_out_date=check_out_date,
        check_out_time=check_out_time,
        medications=medications,
        feeding_schedule=feeding_schedule,
        special_notes=(special_notes + addon_note).strip() or '',
        kennel_number=request.form.get('kennel_number', '').strip() or None,
        kennel_type=request.form.get('kennel_type', 'kennel'),
        status='active',
        booking_number=_next_board_number()
    )

    db.session.add(booking)

    # Also create an Appointment record to store add-ons so they appear
    # on estimates, invoices, and the boarding dashboard add-on badges
    if selected_addons:
        try:
            boarding_svc = ServiceType.query.filter(ServiceType.name.ilike('%boarding%')).first()
            if boarding_svc:
                from app.models import Appointment
                appt = Appointment(
                    user_id          = user_id,
                    pet_id           = pet_id,
                    service_type_id  = boarding_svc.id,
                    appointment_date = check_in_date,
                    start_time       = datetime.combine(check_in_date, datetime.strptime(check_in_time, '%H:%M').time()),
                    end_time         = datetime.combine(check_out_date, datetime.strptime(check_out_time, '%H:%M').time()),
                    status           = 'confirmed',
                    notes            = 'Add-ons: ' + ', '.join(selected_addons)
                )
                db.session.add(appt)
        except Exception as e:
            current_app.logger.warning(f'Could not create add-on appointment record: {e}')

    db.session.commit()

    addon_msg = f' with {", ".join(selected_addons)}' if selected_addons else ''
    try:
        from app.audit_service import audit
        audit('boarding.created', 'boarding', booking.id,
              f'{pet.name} ({check_in_date} to {check_out_date})',
              f'Boarding reservation created for {pet.name} by {current_user.first_name} {current_user.last_name}')
    except Exception: pass
    flash(f'Boarding reservation created for {pet.name} ({check_in_date} to {check_out_date}){addon_msg}.', 'success')
    return redirect(url_for('admin.boarding_dashboard'))

@bp.route('/boarding/<int:booking_id>/checkin', methods=['POST'])
@login_required
@admin_required
def checkin_boarding(booking_id):
    """Mark a boarding pet as physically checked in."""
    booking = Boarding.query.get_or_404(booking_id)
    booking.checked_in    = True
    booking.checked_in_at = datetime.now()
    db.session.commit()

    try:
        from app.audit_service import audit
        audit('boarding.checkin', 'boarding', booking.id, booking.pet.name,
              f'{booking.pet.name} checked in to boarding by {current_user.first_name} {current_user.last_name}')
    except Exception: pass
    flash(f'{booking.pet.name} checked in successfully.', 'success')
    return redirect(url_for('admin.boarding_dashboard'))


@bp.route('/boarding/<int:booking_id>/revert', methods=['POST'])
@login_required
@admin_required
def revert_boarding(booking_id):
    """Revert a completed boarding reservation back to active."""
    booking = Boarding.query.get_or_404(booking_id)

    if booking.status != 'completed':
        flash('Only completed bookings can be reverted.', 'warning')
        return redirect(url_for('admin.boarding_detail', booking_id=booking_id))

    booking.status       = 'active'
    booking.completed_at = None
    booking.checked_in   = True
    db.session.commit()

    try:
        from app.audit_service import audit
        audit('boarding.reverted', 'boarding', booking_id, booking.pet.name,
              f'Boarding reverted to active for {booking.pet.name} by {current_user.first_name} {current_user.last_name}')
    except Exception: pass
    flash(f'{booking.pet.name}\'s booking has been reverted to active.', 'success')
    return redirect(url_for('admin.boarding_detail', booking_id=booking_id))


@bp.route('/boarding/<int:booking_id>/complete', methods=['POST'])
@login_required
@admin_required
def complete_boarding(booking_id):
    """Mark a boarding reservation as completed and send satisfaction survey."""
    from app.models import Appointment
    booking = Boarding.query.get_or_404(booking_id)
    booking.status = 'completed'
    booking.completed_at = datetime.now()
    db.session.commit()

    # Mark any linked confirmed appointment as completed too
    try:
        boarding_service = ServiceType.query.filter(
            ServiceType.name.ilike('%boarding%')
        ).first()
        if boarding_service:
            linked_appt = Appointment.query.filter_by(
                pet_id         = booking.pet_id,
                user_id        = booking.user_id,
                service_type_id = boarding_service.id,
                status         = 'confirmed'
            ).order_by(Appointment.appointment_date.desc()).first()
            if linked_appt:
                linked_appt.status = 'completed'
                db.session.commit()
    except Exception as e:
        current_app.logger.error(f'Failed to update linked appointment on boarding complete: {e}')

    # Auto-send satisfaction survey
    try:
        from app.survey_service import create_and_send_survey
        owner = booking.pet.owner
        if owner:
            create_and_send_survey(owner, 'Boarding', trigger='boarding_complete')
    except Exception as e:
        current_app.logger.error(f'Survey send failed after boarding complete: {e}')

    # Punch card — only active if loyalty_service is deployed
    try:
        from app.loyalty_service import check_boarding_punch
        owner = booking.pet.owner
        if owner:
            credit = check_boarding_punch(owner, db)
            if credit:
                flash(f'🎉 {owner.first_name} has earned a free night! A loyalty credit of ${float(credit.amount):.2f} has been added to their account.', 'success')
    except ImportError:
        pass
    except Exception as e:
        current_app.logger.error(f'Punch card check failed after boarding complete: {e}')

    try:
        from app.audit_service import audit
        audit('boarding.completed', 'boarding', booking.id, booking.pet.name,
              f'Boarding completed for {booking.pet.name} by {current_user.first_name} {current_user.last_name}')
    except Exception: pass
    flash(f'{booking.pet.name}\'s boarding has been marked as completed.', 'success')
    return redirect(url_for('admin.boarding_dashboard'))

@bp.route('/boarding/<int:booking_id>/cancel', methods=['POST'])
@login_required
@admin_required
def cancel_boarding(booking_id):
    """Cancel a boarding reservation and sync the linked Appointment so the customer portal updates."""
    from app.models import Appointment

    booking = Boarding.query.get_or_404(booking_id)
    booking.status = 'cancelled'

    # Also cancel the linked Appointment so the customer portal updates
    try:
        boarding_svc = ServiceType.query.filter(
            ServiceType.name.ilike('%boarding%')
        ).first()
        if boarding_svc:
            linked_appt = Appointment.query.filter_by(
                pet_id          = booking.pet_id,
                user_id         = booking.user_id,
                service_type_id = boarding_svc.id,
            ).filter(
                Appointment.status.in_(['pending', 'confirmed'])
            ).filter(
                Appointment.appointment_date == booking.check_in_date
            ).first()
            if linked_appt:
                linked_appt.status = 'cancelled'
    except Exception as e:
        current_app.logger.error(f'Failed to cancel linked appointment for boarding {booking_id}: {e}')

    db.session.commit()

    # Notify customer via SMS
    try:
        from app.sms_service import _normalize_phone
        from app.models import SmsMessage
        from twilio.rest import Client
        owner = booking.pet.owner
        if owner and owner.phone:
            to_e164     = _normalize_phone(owner.phone)
            from_number = current_app.config.get('TWILIO_PHONE_NUMBER')
            body = (
                f"Hi {owner.first_name}, your boarding reservation for "
                f"{booking.pet.name} "
                f"({booking.check_in_date.strftime('%b %d')} to "
                f"{booking.check_out_date.strftime('%b %d')}) "
                f"has been cancelled. Please contact us if you have questions. "
                f"\u2014 Ruff Life Retreat"
            )
            client  = Client(current_app.config.get('TWILIO_ACCOUNT_SID'),
                             current_app.config.get('TWILIO_AUTH_TOKEN'))
            message = client.messages.create(body=body, from_=from_number, to=to_e164)
            log = SmsMessage(
                user_id     = owner.id,
                direction   = 'outbound',
                from_number = from_number,
                to_number   = to_e164,
                body        = body,
                twilio_sid  = message.sid,
                is_read     = True
            )
            db.session.add(log)
            db.session.commit()
    except Exception as e:
        current_app.logger.error(f'Cancel boarding SMS failed for booking {booking_id}: {e}')

    try:
        from app.audit_service import audit
        audit('boarding.cancelled', 'boarding', booking.id, booking.pet.name,
              f'Boarding cancelled for {booking.pet.name} by {current_user.first_name} {current_user.last_name}')
    except Exception: pass
    flash(f'{booking.pet.name}\'s boarding has been cancelled.', 'warning')
    return redirect(url_for('admin.boarding_dashboard'))

@bp.route('/boarding/<int:booking_id>/delete', methods=['POST'])
@login_required
@admin_required
def delete_boarding(booking_id):
    """Delete a boarding reservation"""
    booking = Boarding.query.get_or_404(booking_id)
    pet_name = booking.pet.name
    
    db.session.delete(booking)
    db.session.commit()
    
    flash(f'Boarding reservation for {pet_name} has been deleted.', 'info')
    return redirect(url_for('admin.boarding_dashboard'))

@bp.route('/boarding/<int:booking_id>', methods=['GET', 'POST'])
@login_required
@admin_required
def boarding_detail(booking_id):
    """View and edit booking details"""
    import re
    booking = Boarding.query.get_or_404(booking_id)
    
    if request.method == 'POST':
        booking.medications     = request.form.get('medications', '')
        booking.feeding_schedule = request.form.get('feeding_schedule', '')
        booking.special_notes   = request.form.get('special_notes', '')
        db.session.commit()
        flash('Booking details updated.', 'success')
        return redirect(url_for('admin.boarding_dashboard'))

    # Parse add-ons from linked appointment notes
    addons = []
    try:
        boarding_svc = ServiceType.query.filter(ServiceType.name.ilike('%boarding%')).first()
        if boarding_svc:
            from app.models import Appointment
            appt = (Appointment.query
                .filter_by(pet_id=booking.pet_id,
                           user_id=booking.user_id,
                           service_type_id=boarding_svc.id)
                .order_by(Appointment.id.desc()).first())
            if appt and appt.notes and 'Add-ons:' in appt.notes:
                m = re.search(r'Add-ons:\s*(.+)', appt.notes)
                if m:
                    addons = [a.strip() for a in m.group(1).split(',')]
    except Exception:
        pass

    from datetime import date
    from app.rate_resolver import get_rates, get_pet_boarding_rate

    customer = User.query.get(booking.user_id)
    rates    = get_rates(customer)
    today_d  = date.today()

    # Build invoice preview for active and upcoming boardings
    invoice_preview = None
    if booking.status in ('active', 'upcoming', 'confirmed', 'pending', 'completed'):
        try:
            from app.models import InvoiceAdjustment

            # Nights: base nights + 1 if pickup after 10 AM
            cout = str(booking.check_out_time or '17:00')[:5]
            days = (booking.check_out_date - booking.check_in_date).days
            if cout > '10:00':
                days += 1

            # Is this the first pet for this stay?
            # Use lowest pet_id among siblings as the primary — same logic as invoice_audit
            all_siblings = Boarding.query.filter(
                Boarding.user_id        == booking.user_id,
                Boarding.check_in_date  == booking.check_in_date,
                Boarding.check_out_date == booking.check_out_date,
                Boarding.status.in_(['active', 'completed'])
            ).order_by(Boarding.pet_id.asc()).all()
            is_first = (not all_siblings) or all_siblings[0].pet_id == booking.pet_id
            # Use full priority chain: pet-level → customer-level → facility default
            nightly  = get_pet_boarding_rate(booking.pet, customer, is_additional=not is_first)
            subtotal = nightly * days

            # Addon lines from appointment notes
            addon_lines = []
            for addon in addons:
                name  = addon.strip()
                price = 0.0
                nl    = name.lower()
                if 'spa bath' in nl and 'nail' in nl:
                    price = rates['addon_spa_bath_nails']
                elif 'spa bath' in nl or 'bath' in nl:
                    price = rates['addon_spa_bath']
                elif 'nail' in nl:
                    price = rates['addon_nail_trim']
                if price > 0:
                    addon_lines.append({'name': name, 'amount': price})

            addon_total = sum(a['amount'] for a in addon_lines)

            # Existing adjustments for this boarding only
            adjustments = InvoiceAdjustment.query.filter(
                InvoiceAdjustment.customer_id == booking.user_id,
                InvoiceAdjustment.adj_type    == 'custom',
                db.or_(
                    InvoiceAdjustment.service_type == 'boarding',
                    InvoiceAdjustment.service_type == None
                )
            ).all()

            invoice_preview = {
                'nights':      days,
                'nightly':     nightly,
                'is_first':    is_first,
                'subtotal':    subtotal,
                'addon_lines': addon_lines,
                'addon_total': addon_total,
                'adjustments': adjustments,
                'grand_total': subtotal + addon_total + sum(a.amount for a in adjustments),
                'has_custom':  rates['has_custom'],
                'rate_note':   rates['note'],
            }
        except Exception as e:
            current_app.logger.error(f'Invoice preview error: {e}')

    return render_template('admin/boarding_detail.html',
        booking=booking, addons=addons, today=today_d,
        invoice_preview=invoice_preview, rates=rates, customer=customer)


@bp.route('/boarding/<int:booking_id>/update-details', methods=['POST'])
@login_required
@admin_required
def update_booking_details(booking_id):
    """Update booking dates, times, and kennel assignment."""
    booking = Boarding.query.get_or_404(booking_id)

    try:
        check_in_str  = request.form.get('check_in_date', '').strip()
        check_out_str = request.form.get('check_out_date', '').strip()

        if check_in_str:
            booking.check_in_date  = datetime.strptime(check_in_str, '%Y-%m-%d').date()
        if check_out_str:
            booking.check_out_date = datetime.strptime(check_out_str, '%Y-%m-%d').date()

        # Conflict check — exclude this booking itself
        conflict = _check_boarding_conflict(
            booking.pet_id, booking.check_in_date, booking.check_out_date,
            exclude_booking_id=booking.id
        )
        if conflict:
            db.session.rollback()
            flash(
                f'{booking.pet.name} already has an active reservation from '
                f'{conflict.check_in_date.strftime("%b %d")} to '
                f'{conflict.check_out_date.strftime("%b %d, %Y")} that overlaps with these dates.',
                'danger'
            )
            return redirect(url_for('admin.boarding_detail', booking_id=booking_id))

        booking.check_in_time  = request.form.get('check_in_time', booking.check_in_time)
        booking.check_out_time = request.form.get('check_out_time', booking.check_out_time)
        booking.kennel_type    = request.form.get('kennel_type', booking.kennel_type)
        booking.kennel_number  = request.form.get('kennel_number', '').strip() or None

        db.session.commit()
        try:
            from app.audit_service import audit
            audit('boarding.updated', 'boarding', booking_id, booking.pet.name,
                  f'Boarding dates/details updated for {booking.pet.name} by {current_user.first_name} {current_user.last_name}')
        except Exception: pass
        flash('Booking details updated successfully.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Failed to update booking: {e}', 'danger')

    return redirect(url_for('admin.boarding_detail', booking_id=booking_id))

@bp.route('/daycare/waitlist/delete/<int:entry_id>', methods=['POST'])
@login_required
@admin_required
def delete_waitlist_entry(entry_id):
    """Delete a waitlist entry"""
    entry = DaycareWaitlist.query.get_or_404(entry_id)
    name = f'{entry.first_name} {entry.last_name}'
    db.session.delete(entry)
    db.session.commit()
    
    flash(f'Removed {name} from waitlist.', 'success')
    return redirect(url_for('admin.daycare_waitlist_admin'))


# ============================================================
# USER MANAGEMENT
# ============================================================





# ============================================================
# USER MANAGEMENT - Add / Edit / Reset / Toggle / Delete
# ============================================================

@bp.route('/users/add', methods=['GET', 'POST'])
@login_required
@admin_required
def add_user():
    """Add a new user"""
    if request.method == 'POST':
        first_name = request.form.get('first_name', '').strip()
        last_name  = request.form.get('last_name', '').strip()
        email      = request.form.get('email', '').strip().lower()
        password   = request.form.get('password', '').strip()
        role       = request.form.get('role', 'staff')

        if not first_name or not last_name or not email or not password:
            flash('All fields are required.', 'danger')
            return redirect(url_for('admin.users'))

        if User.query.filter_by(email=email).first():
            flash('A user with that email already exists.', 'warning')
            return redirect(url_for('admin.users'))

        user = User(
            first_name=first_name,
            last_name=last_name,
            email=email,
            is_admin=(role == 'admin'),
            role=role,
            is_active=True
        )
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        try:
            from app.audit_service import audit
            audit('user.created', 'user', user.id, f'{first_name} {last_name}',
                  f'Staff user {first_name} {last_name} created by {current_user.first_name} {current_user.last_name}')
        except Exception: pass
        flash(f'{first_name} {last_name} created successfully.', 'success')
        return redirect(url_for('admin.users'))

    return redirect(url_for('admin.users'))


@bp.route('/users/<int:user_id>/edit', methods=['POST'])
@login_required
@admin_required
def edit_user(user_id):
    """Edit a user's name, email, and role"""
    user = User.query.get_or_404(user_id)

    first_name = request.form.get('first_name', '').strip()
    last_name  = request.form.get('last_name', '').strip()
    email      = request.form.get('email', '').strip().lower()
    role       = request.form.get('role', 'staff')

    if not first_name or not last_name or not email:
        flash('All fields are required.', 'danger')
        return redirect(url_for('admin.users'))

    existing = User.query.filter_by(email=email).first()
    if existing and existing.id != user.id:
        flash('That email is already in use by another user.', 'warning')
        return redirect(url_for('admin.users'))

    user.first_name = first_name
    user.last_name  = last_name
    user.email      = email
    user.is_admin   = (role == 'admin')
    user.role     = role
    db.session.commit()
    try:
        from app.audit_service import audit
        audit('user.updated', 'user', user_id, f'{first_name} {last_name}',
              f'Staff user {first_name} {last_name} updated by {current_user.first_name} {current_user.last_name}')
    except Exception: pass
    flash(f'{first_name} {last_name} updated successfully.', 'success')
    return redirect(url_for('admin.users'))


@bp.route('/users/<int:user_id>/reset-password', methods=['POST'])
@login_required
@admin_required
def reset_user_password(user_id):
    """Reset a user password"""
    user     = User.query.get_or_404(user_id)
    password = request.form.get('new_password', '').strip()

    if not password or len(password) < 6:
        flash('Password must be at least 6 characters.', 'danger')
        return redirect(url_for('admin.users'))

    user.set_password(password)
    db.session.commit()
    flash(f'Password for {user.first_name} {user.last_name} has been reset.', 'success')
    return redirect(url_for('admin.users'))


@bp.route('/users/<int:user_id>/toggle-active', methods=['POST'])
@login_required
@admin_required
def toggle_user_active(user_id):
    """Activate or deactivate a user"""
    user = User.query.get_or_404(user_id)

    if user.id == current_user.id:
        flash('You cannot deactivate your own account.', 'warning')
        return redirect(url_for('admin.users'))

    user.is_active = not user.is_active
    db.session.commit()
    status = 'activated' if user.is_active else 'deactivated'
    flash(f'{user.first_name} {user.last_name} has been {status}.', 'success')
    return redirect(url_for('admin.users'))


@bp.route('/users/<int:user_id>/delete', methods=['POST'])
@login_required
@admin_required
def delete_user(user_id):
    """Permanently delete a user"""
    user = User.query.get_or_404(user_id)

    if user.id == current_user.id:
        flash('You cannot delete your own account.', 'warning')
        return redirect(url_for('admin.users'))

    name = f'{user.first_name} {user.last_name}'
    db.session.delete(user)
    db.session.commit()
    flash(f'{name} has been permanently deleted.', 'danger')
    return redirect(url_for('admin.users'))






@bp.route('/customers/<int:customer_id>')
@login_required
@admin_required
def customer_detail(customer_id):
    from datetime import date
    from app.models import SmsMessage, InvoiceToken, Boarding, ReportCard

    customer = User.query.get_or_404(customer_id)
    today    = date.today()

    # Report cards for all of this customer's pets
    pet_ids      = [p.id for p in customer.pets]
    report_cards = (ReportCard.query
        .filter(ReportCard.pet_id.in_(pet_ids))
        .order_by(ReportCard.card_date.desc())
        .all()) if pet_ids else []

    # Invoice & estimate SMS history for this customer
    invoice_history = (SmsMessage.query
        .filter(
            SmsMessage.user_id   == customer_id,
            SmsMessage.direction == 'outbound',
            db.or_(
                SmsMessage.body.like('%rufflife.app/invoice/%'),
                SmsMessage.body.like('%rufflife.app/estimate/%'),
                SmsMessage.body.like('%[checkout-estimate]%')
            )
        )
        .order_by(SmsMessage.created_at.desc())
        .all())

    # Get token for view links
    token_rec = InvoiceToken.query.filter_by(customer_id=customer_id).first()
    inv_token = token_rec.token if token_rec else None

    # Boarding reservations — all, sorted by check-in desc
    all_boardings = (Boarding.query
        .join(Pet, Boarding.pet_id == Pet.id)
        .filter(Pet.user_id == customer_id)
        .order_by(Boarding.check_in_date.desc())
        .all())

    current_boardings  = [b for b in all_boardings if b.check_in_date <= today <= b.check_out_date and b.status == 'active']
    upcoming_boardings = [b for b in all_boardings if b.check_in_date > today and b.status in ('active', 'pending')]
    past_boardings     = [b for b in all_boardings if b.check_out_date < today or b.status == 'completed']

    from app.rate_resolver import get_rates
    default_rates = get_rates(None)  # facility defaults with no customer override

    return render_template('admin/customer_detail.html',
        customer=customer,
        today=today,
        invoice_history=invoice_history,
        inv_token=inv_token,
        current_boardings=current_boardings,
        upcoming_boardings=upcoming_boardings,
        past_boardings=past_boardings,
        report_cards=report_cards,
        default_rates=default_rates)


@bp.route('/pets/<int:pet_id>/tags', methods=['POST'])
@login_required
@admin_required
def save_pet_tags(pet_id):
    """Save comma-separated tags for a pet — AJAX."""
    import json
    from app.models import Pet as PetModel
    pet  = PetModel.query.get_or_404(pet_id)
    data = request.get_json() or {}
    tags = [t.strip() for t in data.get('tags', []) if t.strip()]
    pet.pet_tags = ','.join(tags) if tags else None
    db.session.commit()
    return json.dumps({'success': True, 'tags': tags}), 200, {'Content-Type': 'application/json'}


@bp.route('/pets/<int:pet_id>/rates', methods=['POST'])
@login_required
@admin_required
def update_pet_rates(pet_id):
    """Save or clear custom pricing rates for a specific pet."""
    from app.models import Pet as PetModel
    pet = PetModel.query.get_or_404(pet_id)
    customer_id = pet.user_id

    if request.form.get('clear_rates'):
        pet.custom_boarding_rate = None
        pet.custom_daycare_rate  = None
        pet.custom_rate_note     = None
        db.session.commit()
        flash(f'Custom rates cleared for {pet.name}.', 'info')
        return redirect(url_for('admin.pet_detail', pet_id=pet_id))

    def parse_rate(field):
        val = request.form.get(field, '').strip()
        if not val:
            return None
        try:
            v = float(val)
            return v if v >= 0 else None
        except (ValueError, TypeError):
            return None

    pet.custom_boarding_rate = parse_rate('custom_boarding_rate')
    pet.custom_daycare_rate  = parse_rate('custom_daycare_rate')
    pet.custom_rate_note     = request.form.get('custom_rate_note', '').strip() or None
    db.session.commit()
    flash(f'Custom rates saved for {pet.name}.', 'success')
    return redirect(url_for('admin.pet_detail', pet_id=pet_id))


@bp.route('/customers/<int:customer_id>/rates', methods=['POST'])
@login_required
@admin_required
def update_customer_rates(customer_id):
    """Save or clear custom pricing rates for a customer."""
    customer = User.query.get_or_404(customer_id)

    # Clear all custom rates
    if request.form.get('clear_rates'):
        customer.custom_boarding_rate            = None
        customer.custom_boarding_rate_additional = None
        customer.custom_daycare_rate             = None
        customer.custom_addon_spa_bath_nails     = None
        customer.custom_addon_spa_bath           = None
        customer.custom_addon_nail_trim          = None
        customer.custom_rate_note                = None
        db.session.commit()
        flash('Custom rates cleared — facility defaults will be used.', 'info')
        return redirect(url_for('admin.customer_detail', customer_id=customer_id))

    def parse_rate(field):
        val = request.form.get(field, '').strip()
        if not val:
            return None
        try:
            v = float(val)
            return v if v >= 0 else None
        except (ValueError, TypeError):
            return None

    customer.custom_boarding_rate            = parse_rate('custom_boarding_rate')
    customer.custom_boarding_rate_additional = parse_rate('custom_boarding_rate_additional')
    customer.custom_daycare_rate             = parse_rate('custom_daycare_rate')
    customer.custom_addon_spa_bath_nails     = parse_rate('custom_addon_spa_bath_nails')
    customer.custom_addon_spa_bath           = parse_rate('custom_addon_spa_bath')
    customer.custom_addon_nail_trim          = parse_rate('custom_addon_nail_trim')
    customer.custom_rate_note                = request.form.get('custom_rate_note', '').strip() or None

    db.session.commit()
    flash(f'Custom rates saved for {customer.first_name} {customer.last_name}.', 'success')
    return redirect(url_for('admin.customer_detail', customer_id=customer_id))


@bp.route('/pets/<int:pet_id>/delete', methods=['POST'])
@login_required
@admin_required
def delete_pet(pet_id):
    from app.models import (Pet, DaycareEnrollment, DaycareAttendance,
                            Boarding, Appointment, ReportCard, VaccinationRecord)
    pet = Pet.query.get_or_404(pet_id)
    name = pet.name
    customer_id = pet.user_id

    try:
        # Delete in dependency order — children before parents
        # Attendance records first (depend on enrollment)
        enrollment_ids = [e.id for e in DaycareEnrollment.query.filter_by(pet_id=pet_id).all()]
        if enrollment_ids:
            DaycareAttendance.query.filter(
                DaycareAttendance.enrollment_id.in_(enrollment_ids)
            ).delete(synchronize_session='fetch')

        DaycareEnrollment.query.filter_by(pet_id=pet_id).delete()
        Boarding.query.filter_by(pet_id=pet_id).delete()
        Appointment.query.filter_by(pet_id=pet_id).delete()
        ReportCard.query.filter_by(pet_id=pet_id).delete()
        VaccinationRecord.query.filter_by(pet_id=pet_id).delete()

        db.session.delete(pet)
        db.session.commit()
        try:
            from app.audit_service import audit
            audit('pet.deleted', 'pet', pet_id, name,
                  f'Pet {name} permanently deleted by {current_user.first_name} {current_user.last_name}')
        except Exception: pass
        flash(f'{name} and all associated records have been deleted.', 'success')
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f'Failed to delete pet {pet_id}: {e}')
        flash(f'Failed to delete {name}: {e}', 'danger')

    return redirect(url_for('admin.customer_detail', customer_id=customer_id))


@bp.route('/customers')
@login_required
@admin_required
def customers():
    show_archived = request.args.get('show_archived')
    search = request.args.get('q', '').strip()
    sms_filter = request.args.get('sms_filter', '')

    if show_archived:
        query = User.query.filter_by(role='customer', is_active=False)
    else:
        query = User.query.filter_by(role='customer', is_active=True)

    if sms_filter == 'no':
        query = query.filter(
            db.or_(User.sms_opt_in == False, User.sms_opt_in == None)
        )

    if search:
        sl = search.lower()
        all_customers = [c for c in query.order_by(
                             db.func.lower(User.first_name),
                             db.func.lower(User.last_name)
                         ).all()
                         if sl in c.first_name.lower()
                         or sl in c.last_name.lower()
                         or sl in (c.email or '').lower()
                         or sl in (c.phone or '').lower()]
    else:
        all_customers = query.order_by(
            db.func.lower(User.first_name),
            db.func.lower(User.last_name)
        ).all()

    resp = make_response(render_template('admin/customers.html',
        customers=all_customers,
        show_archived=show_archived,
        search=search,
        sms_filter=sms_filter))
    resp.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    resp.headers['Pragma'] = 'no-cache'
    resp.headers['Expires'] = '0'
    return resp


@bp.route('/customers/create', methods=['POST'])
@login_required
@admin_required
def create_customer():
    """Manually create a customer account from the admin dashboard."""
    first_name             = request.form.get('first_name', '').strip()
    last_name              = request.form.get('last_name', '').strip()
    email                  = request.form.get('email', '').strip().lower()
    phone                  = request.form.get('phone', '').strip() or None
    address                = request.form.get('address', '').strip() or None
    city                   = request.form.get('city', '').strip() or None
    state                  = request.form.get('state', '').strip() or None
    zip_code               = request.form.get('zip_code', '').strip() or None
    emergency_contact_name = request.form.get('emergency_contact_name', '').strip() or None
    emergency_contact_phone= request.form.get('emergency_contact_phone', '').strip() or None
    how_heard              = request.form.get('how_heard', '').strip() or None
    sms_opt_in             = request.form.get('sms_opt_in') == '1'
    password               = request.form.get('password', '').strip()

    if not all([first_name, last_name, email, password]):
        flash('First name, last name, email, and password are required.', 'danger')
        return redirect(url_for('admin.customers'))

    if User.query.filter_by(email=email).first():
        flash(f'An account with email {email} already exists.', 'warning')
        return redirect(url_for('admin.customers'))

    if len(password) < 6:
        flash('Password must be at least 6 characters.', 'danger')
        return redirect(url_for('admin.customers'))

    user = User(
        first_name              = first_name,
        last_name               = last_name,
        email                   = email,
        phone                   = phone,
        address                 = address,
        city                    = city,
        state                   = state,
        zip_code                = zip_code,
        emergency_contact_name  = emergency_contact_name,
        emergency_contact_phone = emergency_contact_phone,
        how_heard               = how_heard,
        sms_opt_in              = sms_opt_in,
        role                    = 'customer',
        is_active               = True,
        onboarding_complete     = True
    )
    user.set_password(password)
    db.session.add(user)
    db.session.commit()

    try:
        from app.audit_service import audit
        audit('customer.created', 'customer', user.id, f'{first_name} {last_name}',
              f'Customer {first_name} {last_name} created by {current_user.first_name} {current_user.last_name}')
    except Exception: pass
    flash(f'Customer {first_name} {last_name} created successfully.', 'success')
    return redirect(url_for('admin.customer_detail', customer_id=user.id))


@bp.route('/customers/<int:customer_id>/delete', methods=['POST'])
@login_required
@admin_required
def delete_customer(customer_id):
    """
    Permanently delete a customer and all their associated data.
    This is irreversible — use archive for soft-delete instead.
    """
    user = User.query.get_or_404(customer_id)

    if user.is_admin:
        flash('Admin accounts cannot be deleted.', 'danger')
        return redirect(url_for('admin.customers'))

    name = f'{user.first_name} {user.last_name}'

    # Delete in dependency order
    try:
        from app.models import (SurveyResponse, SmsMessage, ReportCard,
                                PasswordResetToken, DaycareAttendance,
                                DaycareEnrollment, DaycareWaitlist, Boarding,
                                Appointment, Pet)
        for pet in user.pets:
            ReportCard.query.filter_by(pet_id=pet.id).delete()
            DaycareAttendance.query.filter(
                DaycareAttendance.enrollment_id.in_(
                    db.session.query(DaycareEnrollment.id).filter_by(pet_id=pet.id)
                )
            ).delete(synchronize_session='fetch')
            DaycareEnrollment.query.filter_by(pet_id=pet.id).delete()
            Boarding.query.filter_by(pet_id=pet.id).delete()
            Appointment.query.filter_by(pet_id=pet.id).delete()
            db.session.delete(pet)

        SurveyResponse.query.filter_by(user_id=customer_id).delete()
        SmsMessage.query.filter_by(user_id=customer_id).delete()
        PasswordResetToken.query.filter_by(user_id=customer_id).delete()
        Appointment.query.filter_by(user_id=customer_id).delete()
        DaycareWaitlist.query.filter_by(email=user.email).delete()

        db.session.delete(user)
        db.session.commit()
        try:
            from app.audit_service import audit
            audit('customer.deleted', 'customer', customer_id, name,
                  f'Customer {name} permanently deleted by {current_user.first_name} {current_user.last_name}')
        except Exception: pass
        flash(f'Customer {name} and all associated data permanently deleted.', 'success')
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f'Failed to delete customer {customer_id}: {e}')
        flash(f'Failed to delete customer: {e}', 'danger')

    return redirect(url_for('admin.customers'))

@bp.route('/customers/<int:customer_id>/edit', methods=['POST'])
@login_required
@admin_required
def edit_customer(customer_id):
    """Edit a customer's contact and personal information."""
    customer = User.query.get_or_404(customer_id)

    customer.first_name              = request.form.get('first_name', '').strip()
    customer.last_name               = request.form.get('last_name', '').strip()
    customer.email                   = request.form.get('email', '').strip()
    customer.phone                   = request.form.get('phone', '').strip() or None
    customer.address                 = request.form.get('address', '').strip() or None
    customer.city                    = request.form.get('city', '').strip() or None
    customer.state                   = request.form.get('state', '').strip() or None
    customer.zip_code                = request.form.get('zip_code', '').strip() or None
    customer.emergency_contact_name  = request.form.get('emergency_contact_name', '').strip() or None
    customer.emergency_contact_phone = request.form.get('emergency_contact_phone', '').strip() or None
    customer.sms_opt_in              = request.form.get('sms_opt_in') == '1'
    customer.is_active               = request.form.get('is_active') == '1'

    db.session.commit()
    try:
        from app.audit_service import audit
        audit('customer.edited', 'customer', customer_id,
              f'{customer.first_name} {customer.last_name}',
              f'Customer profile edited by {current_user.first_name} {current_user.last_name}')
    except Exception: pass
    flash(f'{customer.first_name} {customer.last_name} updated successfully.', 'success')
    return redirect(url_for('admin.customer_detail', customer_id=customer_id))


@bp.route('/customers/<int:customer_id>/photos/upload', methods=['POST'])
@login_required
@admin_required
def upload_customer_photo(customer_id):
    """Upload a photo to a customer's gallery."""
    from app.models import CustomerPhoto
    from werkzeug.utils import secure_filename

    customer = User.query.get_or_404(customer_id)
    photo    = request.files.get('photo')
    caption  = request.form.get('caption', '').strip() or None

    if not photo or not photo.filename:
        flash('No photo selected.', 'warning')
        return redirect(url_for('admin.customer_detail', customer_id=customer_id))

    upload_dir = os.path.join(current_app.root_path, 'static', 'uploads', 'customers', str(customer_id))
    os.makedirs(upload_dir, exist_ok=True)

    from datetime import datetime as dt
    timestamp = dt.now().strftime('%Y%m%d%H%M%S')
    filename  = secure_filename(f'{timestamp}_{photo.filename}')
    photo.save(os.path.join(upload_dir, filename))

    rec = CustomerPhoto(
        user_id     = customer_id,
        filename    = filename,
        caption     = caption,
        uploaded_by = current_user.id
    )
    db.session.add(rec)
    db.session.commit()
    flash('Photo uploaded successfully.', 'success')
    return redirect(url_for('admin.customer_detail', customer_id=customer_id))


# ============================================================
# PAYMENT TRACKING
# ============================================================
# ============================================================
# PAYMENT TRACKING
# ============================================================

@bp.route('/payments/outstanding')
@login_required
@admin_required
def outstanding_balances():
    """Report of all customers with outstanding balances."""
    from app.models import Payment
    from datetime import date, timedelta

    today = date.today()

    # Get all outstanding payments grouped by customer
    outstanding = (Payment.query
        .filter_by(status='outstanding')
        .order_by(Payment.payment_date.asc())
        .all())

    # Group by customer
    customer_map = {}
    for p in outstanding:
        cid = p.customer_id
        if cid not in customer_map:
            customer_map[cid] = {
                'customer': p.customer,
                'payments': [],
                'total': 0,
                'oldest_date': p.payment_date,
            }
        customer_map[cid]['payments'].append(p)
        customer_map[cid]['total'] += p.amount
        if p.payment_date < customer_map[cid]['oldest_date']:
            customer_map[cid]['oldest_date'] = p.payment_date

    # Sort by oldest outstanding date descending (most overdue first)
    rows = sorted(customer_map.values(),
                  key=lambda x: x['oldest_date'])

    # Summary stats
    total_outstanding = sum(r['total'] for r in rows)
    over_30 = [r for r in rows if (today - r['oldest_date']).days > 30]
    over_60 = [r for r in rows if (today - r['oldest_date']).days > 60]

    return render_template('admin/outstanding_balances.html',
                           rows=rows,
                           total_outstanding=total_outstanding,
                           over_30=over_30,
                           over_60=over_60,
                           today=today)


@bp.route('/payments')
@login_required
@admin_required
def payments():
    """All payments across all customers"""
    from app.models import Payment
    all_payments = Payment.query.order_by(Payment.payment_date.desc()).all()
    customers = User.query.filter_by(role='customer').order_by(User.last_name).all()
    total_paid = sum(p.amount for p in all_payments if p.status == 'paid')
    total_outstanding = sum(p.amount for p in all_payments if p.status == 'outstanding')
    return render_template('admin/payments.html',
        payments=all_payments,
        customers=customers,
        total_paid=total_paid,
        total_outstanding=total_outstanding)


@bp.route('/payments/add', methods=['POST'])
@login_required
@admin_required
def add_payment():
    """Add a new payment"""
    from app.models import Payment
    from datetime import date
    customer_id    = request.form.get('customer_id')
    amount         = request.form.get('amount')
    payment_date   = request.form.get('payment_date')
    service_type   = request.form.get('service_type', '').strip()
    payment_method = request.form.get('payment_method', '').strip()
    notes          = request.form.get('notes', '').strip()
    status         = request.form.get('status', 'paid')

    if not customer_id or not amount or not payment_date:
        flash('Customer, amount, and date are required.', 'danger')
        return redirect(request.referrer or url_for('admin.payments'))

    payment = Payment(
        customer_id=int(customer_id),
        amount=float(amount),
        payment_date=date.fromisoformat(payment_date),
        service_type=service_type,
        payment_method=payment_method,
        notes=notes,
        status=status
    )
    db.session.add(payment)
    db.session.commit()
    try:
        from app.audit_service import audit
        audit('payment.created', 'payment', payment.id,
              f'Customer #{customer_id}',
              f'Payment of ${amount} recorded by {current_user.first_name} {current_user.last_name}',
              {'method': payment_method, 'status': status})
    except Exception: pass
    flash('Payment recorded successfully.', 'success')
    return redirect(request.referrer or url_for('admin.payments'))


@bp.route('/payments/<int:payment_id>/edit', methods=['POST'])
@login_required
@admin_required
def edit_payment(payment_id):
    """Edit a payment"""
    from app.models import Payment
    from datetime import date
    payment = Payment.query.get_or_404(payment_id)
    payment.amount         = float(request.form.get('amount', payment.amount))
    payment.payment_date   = date.fromisoformat(request.form.get('payment_date'))
    payment.service_type   = request.form.get('service_type', '').strip()
    payment.payment_method = request.form.get('payment_method', '').strip()
    payment.notes          = request.form.get('notes', '').strip()
    payment.status         = request.form.get('status', 'paid')
    db.session.commit()
    flash('Payment updated.', 'success')
    return redirect(request.referrer or url_for('admin.payments'))


@bp.route('/payments/<int:payment_id>/delete', methods=['POST'])
@login_required
@admin_required
def delete_payment(payment_id):
    """Delete a payment"""
    from app.models import Payment
    payment = Payment.query.get_or_404(payment_id)
    db.session.delete(payment)
    db.session.commit()
    try:
        from app.audit_service import audit
        audit('payment.deleted', 'payment', payment_id, f'Payment #{payment_id}',
              f'Payment #{payment_id} deleted by {current_user.first_name} {current_user.last_name}')
    except Exception: pass
    flash('Payment deleted.', 'danger')
    return redirect(request.referrer or url_for('admin.payments'))


def _next_board_number():
    """
    Generate the next sequential BOARD-N number.
    Scans existing booking_number values to find the highest N, then returns N+1.
    Safe against gaps or manually edited numbers.
    """
    rows = db.session.execute(
        db.text("SELECT booking_number FROM boarding WHERE booking_number IS NOT NULL")
    ).fetchall()
    max_n = 0
    for row in rows:
        try:
            n = int(str(row[0]).split('-')[1])
            if n > max_n:
                max_n = n
        except (IndexError, ValueError, AttributeError):
            pass
    return f'BOARD-{max_n + 1}'


def _boarding_days(b):
    """
    Calculate billable nights for a boarding record.
    Base = checkout_date - checkin_date (nights slept).
    If pickup is after 10:00 AM, the checkout day counts as an extra night.
    e.g. Jun 20–22, pickup at 5 PM = 3 nights; pickup at 9 AM = 2 nights.
    """
    base = (b.check_out_date - b.check_in_date).days
    cout = str(b.check_out_time or '17:00')[:5]
    return base if cout <= '10:00' else base + 1


@bp.route('/customers/<int:customer_id>/invoice')
@login_required
@admin_required
def customer_invoice(customer_id):
    """Printable invoice — boarding or daycare, controlled by ?type= param."""
    from app.models import Payment, Boarding, DaycareAttendance, DaycareEnrollment, InvoiceAdjustment
    from datetime import date, timedelta
    import re

    customer     = User.query.get_or_404(customer_id)
    today        = date.today()
    invoice_type = request.args.get('type', 'boarding')  # 'boarding' or 'daycare'
    payment_id   = request.args.get('payment_id', type=int)  # view a specific paid invoice

    # If viewing a specific payment, load it for display
    viewing_payment = None
    if payment_id:
        viewing_payment = Payment.query.filter_by(id=payment_id, customer_id=customer_id).first()

    # Resolve customer-specific or facility-default rates
    from app.rate_resolver import get_rates, get_pet_boarding_rate, get_pet_daycare_rate
    rates = get_rates(customer)

    DAYCARE_SINGLE = float(current_app.config.get('DAYCARE_RATE_SINGLE', 25.0))

    def daycare_rate_for_attendance(attendance, pet=None):
        enrollment = attendance.enrollment
        from app.rate_resolver import get_pet_daycare_rate as _gdr
        return _gdr(pet, customer, enrollment)

    open_mode    = request.args.get('open') == '1'
    pet_sections = []

    for pet in sorted(customer.pets, key=lambda p: p.name):
        lines = []

        if invoice_type == 'boarding':
            if viewing_payment:
                # Show boardings paid under this specific payment
                boardings = Boarding.query.filter_by(
                    pet_id=pet.id, payment_id=payment_id
                ).order_by(Boarding.check_in_date.asc()).all()
            elif open_mode:
                # Show active (currently checked-in) boardings — estimated invoice
                boardings = Boarding.query.filter_by(
                    pet_id=pet.id, status='active'
                ).order_by(Boarding.check_in_date.asc()).all()
            else:
                # Boarding records — completed and unpaid
                boardings = Boarding.query.filter_by(
                    pet_id=pet.id, status='completed'
                ).filter(Boarding.payment_id == None).order_by(
                    Boarding.check_in_date.asc()
                ).all()

            for b in boardings:
                days     = _boarding_days(b)
                sibling_status = 'active' if open_mode else 'completed'
                siblings = Boarding.query.filter_by(
                    user_id=b.user_id,
                    check_in_date=b.check_in_date,
                    check_out_date=b.check_out_date,
                    status=sibling_status
                ).order_by(Boarding.pet_id.asc()).all()
                is_first   = (not siblings) or siblings[0].pet_id == pet.id
                rate       = get_pet_boarding_rate(pet, customer, is_additional=not is_first)
                amount     = rate * days

                addons = []
                try:
                    addons, _at = _parse_addons_from_notes(b.special_notes or '')
                    if not addons:
                        # Older bookings stored add-ons only in the appointment notes
                        from app.models import Appointment as _Appt, ServiceType as _ST
                        _svc = _ST.query.filter(_ST.name.ilike('%boarding%')).first()
                        if _svc:
                            _a = _Appt.query.filter_by(
                                pet_id=pet.id, user_id=customer.id,
                                service_type_id=_svc.id
                            ).order_by(_Appt.id.desc()).first()
                            if _a and _a.notes:
                                addons, _ = _parse_addons_from_notes(_a.notes)
                except Exception:
                    pass

                lines.append({
                    'type':        'boarding',
                    'boarding_id': b.id,
                    'line_key':    f'boarding_{b.id}',
                    'description': f'Boarding — {b.check_in_date.strftime("%b %d")} to {b.check_out_date.strftime("%b %d, %Y")}',
                    'detail':      f'{days} night{"s" if days != 1 else ""} @ ${rate:.0f}/night{"  (additional pet)" if not is_first else ""}',
                    'amount':      amount,
                    'addons':      addons,
                    'addon_total': sum(_parse_addon_price(a) for a in addons),
                })

        elif invoice_type == 'daycare':
            enrollments = DaycareEnrollment.query.filter_by(pet_id=pet.id).all()
            for enr in enrollments:
                if viewing_payment:
                    # Show daycare sessions paid under this specific payment
                    attendances = DaycareAttendance.query.filter_by(
                        enrollment_id=enr.id, payment_id=payment_id
                    ).order_by(DaycareAttendance.check_in_time.asc()).all()
                else:
                    # Daycare attendance — checked out and unpaid
                    attendances = DaycareAttendance.query.filter_by(
                        enrollment_id=enr.id
                    ).filter(
                        DaycareAttendance.check_out_time != None,
                        DaycareAttendance.payment_id == None
                    ).order_by(DaycareAttendance.check_in_time.asc()).all()

                for att in attendances:
                    rate = daycare_rate_for_attendance(att)
                    lines.append({
                        'type':          'daycare',
                        'attendance_id': att.id,
                        'line_key':      f'daycare_{att.id}',
                        'description':   f'Daycare — {att.check_in_time.strftime("%b %d, %Y")}',
                        'detail':        f'${"%.0f" % rate}/day',
                        'amount':        rate,
                        'addons':        [],
                        'addon_total':   0,
                    })

        if lines:
            subtotal = sum(l['amount'] + l['addon_total'] for l in lines)
            pet_sections.append({'pet': pet, 'lines': lines, 'subtotal': subtotal})

    # ── Invoice adjustments scoped to this invoice type ───────────────────
    all_adjs    = InvoiceAdjustment.query.filter_by(customer_id=customer_id).all()
    type_prefix = invoice_type  # 'boarding' or 'daycare'

    # Filter by service_type column if set, fall back to line_key prefix for legacy records
    def adj_matches_type(a):
        if a.service_type:
            return a.service_type == invoice_type
        if a.line_key:
            return a.line_key.startswith(type_prefix)
        return invoice_type == 'boarding'  # legacy untyped adjustments default to boarding

    adj_by_key   = {a.line_key: a for a in all_adjs
                    if a.adj_type == 'override' and a.line_key and adj_matches_type(a)}
    custom_lines = [a for a in all_adjs
                    if a.adj_type == 'custom' and adj_matches_type(a)]

    # Apply overrides
    for section in pet_sections:
        for line in section['lines']:
            key = line.get('line_key')
            if key and key in adj_by_key:
                line['override']       = adj_by_key[key]
                line['display_amount'] = adj_by_key[key].amount
            else:
                line['override']       = None
                line['display_amount'] = line['amount'] + line['addon_total']
        section['subtotal'] = sum(l['display_amount'] for l in section['lines'])

    # ── Payment history ───────────────────────────────────────────────────
    if open_mode:
        # Open boarding estimate — don't load past payment history; it's not relevant
        # and would incorrectly offset the projected balance.
        payments   = []
        total_paid = 0.0
    else:
        payments   = Payment.query.filter_by(
            customer_id=customer_id,
            service_type=invoice_type.capitalize()
        ).order_by(Payment.payment_date.desc()).all()
        total_paid = sum(p.amount for p in payments if p.status == 'paid')
    adj_total         = sum(a.amount for a in custom_lines)
    total_outstanding = sum(s['subtotal'] for s in pet_sections) + adj_total
    grand_total       = total_outstanding

    return render_template('admin/invoice.html',
        customer=customer,
        invoice_type=invoice_type,
        pet_sections=pet_sections,
        custom_lines=custom_lines,
        payments=payments,
        total_paid=total_paid,
        total_outstanding=total_outstanding,
        true_balance=max(0.0, total_outstanding - total_paid),
        grand_total=grand_total,
        today=today,
        rates=rates,
        viewing_payment=viewing_payment,
        open_mode=open_mode)



def _parse_addons_from_notes(notes):
    """
    Parse add-ons from appointment notes.
    Handles structured format (Add-ons: Spa Bath ($20))
    and freetext fallback (bath, nails, wash, etc.)
    """
    import re as _re
    if not notes:
        return [], 0.0
    addons = []
    total  = 0.0
    # Structured
    if 'Add-ons:' in notes:
        m = _re.search(r'Add-ons:\s*(.+)', notes)
        if m:
            for item in m.group(1).split(','):
                item = item.strip()
                if not item:
                    continue
                addons.append(item)
                pm = _re.search(r'\$(\d+)', item)
                if pm:
                    total += float(pm.group(1))
        return addons, total
    # Freetext fallback
    n = notes.lower()
    has_bath  = any(w in n for w in ['bath', 'bathe', 'wash', 'shampoo', 'spa'])
    has_nails = any(w in n for w in ['nail', 'nails', 'trim', 'clip'])
    if has_bath and has_nails:
        addons.append('Spa Bath + Nail Trim ($30)'); total = 30.0
    elif has_bath:
        addons.append('Spa Bath ($20)');  total = 20.0
    elif has_nails:
        addons.append('Nail Trim ($15)'); total = 15.0
    return addons, total

def _parse_addon_price(addon_str):
    """Extract dollar amount from addon string like 'Spa Bath ($20)'."""
    import re
    m = re.search(r'\$(\d+)', addon_str)
    return float(m.group(1)) if m else 0.0



@bp.route('/customers/<int:customer_id>/estimate/send-sms', methods=['POST'])
@login_required
@admin_required
def send_estimate_sms(customer_id):
    """Generate a tokenized estimate link and send it to the customer via SMS."""
    from app.models import InvoiceToken, SmsMessage, Boarding, DaycareAttendance, DaycareEnrollment
    from app.sms_service import _normalize_phone
    import secrets, re
    from datetime import date, timedelta

    customer = User.query.get_or_404(customer_id)

    if not customer.phone:
        flash('No phone number on file — SMS not sent.', 'danger')
        return redirect(url_for('admin.customer_invoice', customer_id=customer_id))

    # Reuse or create token (same token as invoice — different URL path)
    token_rec = InvoiceToken.query.filter_by(customer_id=customer_id).first()
    if not token_rec:
        token_rec = InvoiceToken(
            customer_id = customer_id,
            token       = secrets.token_urlsafe(32)
        )
        db.session.add(token_rec)

    token_rec.last_sent = datetime.now()
    db.session.commit()

    # Calculate estimate total from active boardings + open daycare sessions
    from app.rate_resolver import get_rates as _get_rates
    _rates         = _get_rates(customer)
    DAYCARE_MULTI  = _rates['daycare']
    DAYCARE_SINGLE = float(current_app.config.get('DAYCARE_RATE_SINGLE', 25.0))

    def _boarding_days(b):
        base = (b.check_out_date - b.check_in_date).days
        cout = str(b.check_out_time or '17:00')[:5]
        return base if cout <= '10:00' else base + 1

    total = 0.0
    pet_lines = []

    for pet in customer.pets:
        pet_total = 0.0

        # Active boardings (not yet completed)
        boardings = Boarding.query.filter(
            Boarding.pet_id == pet.id,
            Boarding.status == 'active'
        ).all()

        for b in boardings:
            days = _boarding_days(b)
            siblings = Boarding.query.filter_by(
                user_id=b.user_id,
                check_in_date=b.check_in_date,
                check_out_date=b.check_out_date,
            ).filter(Boarding.status == 'active').order_by(Boarding.pet_id.asc()).all()
            is_first = (not siblings) or siblings[0].pet_id == pet.id
            from app.rate_resolver import get_pet_boarding_rate as _gpbr
            rate   = _gpbr(pet, customer, is_additional=not is_first)
            amount = rate * days
            addon_names = []
            try:
                _addons, addon_cost = _parse_addons_from_notes(b.special_notes or '')
                amount += addon_cost
                addon_names = [a.split('(')[0].strip() for a in _addons]
            except Exception:
                pass

            pet_total += amount

            # Include add-on names in the line for the SMS
            if addon_names:
                pet_lines.append(f'{pet.name}: ${pet_total:.2f} (incl. {", ".join(addon_names)})')
            else:
                pet_lines.append(f'{pet.name}: ${pet_total:.2f}')

        total += pet_total

    if total <= 0:
        flash('No active services found to estimate.', 'warning')
        return redirect(url_for('admin.customer_invoice', customer_id=customer_id))

    try:
        from twilio.rest import Client
        to_e164     = _normalize_phone(customer.phone)
        from_number = current_app.config.get('TWILIO_PHONE_NUMBER')
        business    = current_app.config.get('BUSINESS_NAME', 'Ruff Life Retreat')
        link        = f'https://rufflife.app/estimate/{token_rec.token}'

        pet_summary = ', '.join(pet_lines)
        body = (
            f"Hi {customer.first_name}! Here's your estimated balance with {business}: "
            f"${total:.2f} ({pet_summary}). "
            f"View the full breakdown: {link} "
            f"Final amount confirmed at checkout."
        )

        client  = Client(current_app.config.get('TWILIO_ACCOUNT_SID'),
                         current_app.config.get('TWILIO_AUTH_TOKEN'))
        message = client.messages.create(body=body, from_=from_number, to=to_e164)

        log = SmsMessage(
            user_id     = customer.id,
            direction   = 'outbound',
            from_number = from_number,
            to_number   = to_e164,
            body        = body,
            twilio_sid  = message.sid,
            is_read     = True
        )
        db.session.add(log)
        db.session.commit()
        flash(f'Estimate sent to {customer.first_name} — ${total:.2f}.', 'success')

    except Exception as e:
        current_app.logger.error(f'Estimate SMS failed for customer {customer_id}: {e}')
        flash(f'Failed to send SMS: {e}', 'danger')

    return redirect(url_for('admin.customer_invoice', customer_id=customer_id))


@bp.route('/customers/<int:customer_id>/invoice/adjustment/override', methods=['POST'])
@login_required
@admin_required
def invoice_override_line(customer_id):
    """Override the amount on a specific auto-calculated invoice line."""
    from app.models import InvoiceAdjustment
    line_key    = request.form.get('line_key', '').strip()
    description = request.form.get('description', '').strip()
    try:
        amount = float(request.form.get('amount', 0))
    except ValueError:
        flash('Invalid amount.', 'danger')
        return redirect(url_for('admin.customer_invoice', customer_id=customer_id))

    if not line_key:
        flash('Missing line reference.', 'danger')
        return redirect(url_for('admin.customer_invoice', customer_id=customer_id))

    # Update existing override or create new one
    adj = InvoiceAdjustment.query.filter_by(
        customer_id=customer_id, adj_type='override', line_key=line_key
    ).first()

    if adj:
        adj.amount      = amount
        adj.description = description
    else:
        adj = InvoiceAdjustment(
            customer_id = customer_id,
            adj_type    = 'override',
            line_key    = line_key,
            description = description,
            amount      = amount,
            created_by  = current_user.id
        )
        db.session.add(adj)

    db.session.commit()
    flash(f'Line amount updated to ${amount:.2f}.', 'success')
    return redirect(url_for('admin.customer_invoice', customer_id=customer_id))


@bp.route('/customers/<int:customer_id>/invoice/adjustment/override/<int:adj_id>/delete', methods=['POST'])
@login_required
@admin_required
def invoice_override_delete(customer_id, adj_id):
    """Remove a line override, restoring the calculated amount."""
    from app.models import InvoiceAdjustment
    adj = InvoiceAdjustment.query.get_or_404(adj_id)
    db.session.delete(adj)
    db.session.commit()
    flash('Override removed — calculated amount restored.', 'info')
    return redirect(url_for('admin.customer_invoice', customer_id=customer_id))


@bp.route('/customers/<int:customer_id>/invoice/adjustment/custom', methods=['POST'])
@login_required
@admin_required
def invoice_add_custom_line(customer_id):
    """Add a custom line item (charge or discount) to an invoice."""
    from app.models import InvoiceAdjustment

    # Accept either 'label' or 'description' field name
    description = (request.form.get('label') or request.form.get('description') or '').strip()
    adj_type    = request.form.get('adjustment_type', 'custom')
    service_type = request.form.get('invoice_type', 'boarding')  # 'boarding' or 'daycare'

    try:
        amount = float(request.form.get('amount', 0))
    except ValueError:
        flash('Invalid amount.', 'danger')
        return redirect(request.referrer or url_for('admin.customer_invoice', customer_id=customer_id))

    if not description:
        flash('Description is required.', 'danger')
        return redirect(request.referrer or url_for('admin.customer_invoice', customer_id=customer_id))

    # Make discounts negative automatically if type is 'discount' and amount is positive
    if adj_type == 'discount' and amount > 0:
        amount = -amount

    adj = InvoiceAdjustment(
        customer_id  = customer_id,
        adj_type     = 'custom',
        description  = description,
        amount       = amount,
        service_type = service_type,
        created_by   = current_user.id
    )
    db.session.add(adj)
    db.session.commit()
    label = 'Discount' if amount < 0 else 'Charge'
    flash(f'{label} of ${abs(amount):.2f} added to invoice.', 'success')
    return redirect(request.referrer or url_for('admin.customer_invoice', customer_id=customer_id))


@bp.route('/customers/<int:customer_id>/invoice/adjustment/custom/<int:adj_id>/delete', methods=['POST'])
@login_required
@admin_required
def invoice_delete_custom_line(customer_id, adj_id):
    """Remove a custom line item from an invoice."""
    from app.models import InvoiceAdjustment
    adj = InvoiceAdjustment.query.get_or_404(adj_id)
    db.session.delete(adj)
    db.session.commit()
    flash('Line item removed.', 'info')
    return redirect(url_for('admin.customer_invoice', customer_id=customer_id))


@bp.route('/customers/<int:customer_id>/invoice/send-sms', methods=['POST'])
@login_required
@admin_required
def send_invoice_sms(customer_id):
    """Generate a tokenized invoice link, send it via SMS, and create an outstanding Payment record."""
    from app.models import InvoiceToken, SmsMessage, Payment, Boarding, DaycareAttendance, DaycareEnrollment, InvoiceAdjustment
    from app.sms_service import _normalize_phone
    from app.rate_resolver import get_rates
    from datetime import date, timedelta
    import secrets

    customer     = User.query.get_or_404(customer_id)
    invoice_type = request.form.get('invoice_type', 'boarding')

    if not customer.phone:
        flash('No phone number on file — SMS not sent.', 'danger')
        return redirect(url_for('admin.customer_invoice', customer_id=customer_id, type=invoice_type))

    # ── Calculate invoice total ───────────────────────────────────────────
    rates = get_rates(customer)
    today = date.today()
    total = 0.0

    for pet in customer.pets:
        if invoice_type == 'boarding':
            boardings = Boarding.query.filter_by(
                pet_id=pet.id, status='completed'
            ).filter(Boarding.payment_id == None).all()
            for b in boardings:
                days     = _boarding_days(b)
                siblings = Boarding.query.filter_by(
                    user_id=customer.id,
                    check_in_date=b.check_in_date,
                    check_out_date=b.check_out_date,
                    status='completed'
                ).order_by(Boarding.pet_id.asc()).all()
                is_first = (not siblings) or siblings[0].pet_id == pet.id
                from app.rate_resolver import get_pet_boarding_rate as _gpbr4
                rate     = _gpbr4(pet, customer, is_additional=not is_first)
                _, addon_cost = _parse_addons_from_notes(b.special_notes or '')
                total += rate * days + addon_cost
        else:
            for enr in DaycareEnrollment.query.filter_by(pet_id=pet.id).all():
                atts = DaycareAttendance.query.filter_by(
                    enrollment_id=enr.id
                ).filter(
                    DaycareAttendance.check_out_time != None,
                    DaycareAttendance.payment_id == None
                ).all()
                for att in atts:
                    week_start = att.check_in_time.date() - timedelta(days=att.check_in_time.weekday())
                    week_end   = week_start + timedelta(days=6)
                    wc = DaycareAttendance.query.filter(
                        DaycareAttendance.enrollment_id == enr.id,
                        DaycareAttendance.check_in_time >= week_start,
                        DaycareAttendance.check_in_time <= week_end
                    ).count()
                    rate = enr.special_rate if enr.special_rate else (
                        rates['daycare'] if wc > 1
                        else float(current_app.config.get('DAYCARE_RATE_SINGLE', 25.0))
                    )
                    total += rate

    # Apply custom line adjustments
    adjs = InvoiceAdjustment.query.filter_by(
        customer_id=customer_id, adj_type='custom'
    ).filter(
        db.or_(InvoiceAdjustment.service_type == invoice_type,
               InvoiceAdjustment.service_type == None)
    ).all()
    total += sum(a.amount for a in adjs)
    total  = max(0.0, total)

    # ── Reuse or create token ─────────────────────────────────────────────
    token_rec = InvoiceToken.query.filter_by(customer_id=customer_id).first()
    if not token_rec:
        token_rec = InvoiceToken(
            customer_id = customer_id,
            token       = secrets.token_urlsafe(32)
        )
        db.session.add(token_rec)

    token_rec.last_sent = datetime.now()
    db.session.flush()

    # ── Auto-create outstanding Payment record ────────────────────────────
    if total > 0:
        # Check if an outstanding payment already exists for this type to avoid duplicates
        existing = Payment.query.filter_by(
            customer_id  = customer_id,
            service_type = invoice_type.capitalize(),
            status       = 'outstanding'
        ).first()

        if existing:
            # Update existing outstanding payment amount
            existing.amount       = total
            existing.payment_date = today
            existing.notes        = f'{invoice_type.capitalize()} invoice sent via SMS — updated'
        else:
            payment = Payment(
                customer_id    = customer_id,
                amount         = total,
                payment_date   = today,
                service_type   = invoice_type.capitalize(),
                payment_method = 'Invoice',
                status         = 'outstanding',
                notes          = f'{invoice_type.capitalize()} invoice sent via SMS'
            )
            db.session.add(payment)

    db.session.commit()

    # ── Send SMS ──────────────────────────────────────────────────────────
    try:
        from twilio.rest import Client
        to_e164     = _normalize_phone(customer.phone)
        from_number = current_app.config.get('TWILIO_PHONE_NUMBER')
        business    = current_app.config.get('BUSINESS_NAME', 'Ruff Life Retreat')
        domain      = current_app.config.get('BUSINESS_DOMAIN', 'rufflife.app')
        link        = f'https://{domain}/invoice/{token_rec.token}'

        body = (
            f"Hi {customer.first_name}! Your {invoice_type} invoice from {business} "
            f"is ready — ${total:.2f} due. View it here: {link}"
        )

        client  = Client(current_app.config.get('TWILIO_ACCOUNT_SID'),
                         current_app.config.get('TWILIO_AUTH_TOKEN'))
        message = client.messages.create(body=body, from_=from_number, to=to_e164)

        log = SmsMessage(
            user_id     = customer.id,
            direction   = 'outbound',
            from_number = from_number,
            to_number   = to_e164,
            body        = body,
            twilio_sid  = message.sid,
            is_read     = True
        )
        db.session.add(log)
        db.session.commit()
        try:
            from app.audit_service import audit
            audit('invoice.sent', 'customer', customer_id,
                  f'{customer.first_name} {customer.last_name}',
                  f'{invoice_type.capitalize()} invoice ${total:.2f} sent via SMS by {current_user.first_name} {current_user.last_name}')
        except Exception: pass
        flash(f'Invoice sent to {customer.first_name} via SMS — ${total:.2f} recorded as outstanding.', 'success')

    except Exception as e:
        current_app.logger.error(f'Invoice SMS failed for customer {customer_id}: {e}')
        flash(f'Failed to send SMS: {e}', 'danger')

    return redirect(url_for('admin.customer_invoice', customer_id=customer_id, type=invoice_type))


@bp.route('/customers/<int:customer_id>/invoice/pay', methods=['POST'])
@login_required
@admin_required
def mark_invoice_paid(customer_id):
    """Mark unpaid service records as paid, scoped to boarding or daycare."""
    from app.models import Payment, Boarding, DaycareAttendance, DaycareEnrollment
    from datetime import date, timedelta
    import re

    customer     = User.query.get_or_404(customer_id)
    today        = date.today()
    method       = request.form.get('payment_method', 'card')
    invoice_type = request.form.get('invoice_type', 'boarding')

    DAYCARE_MULTI  = 20.00
    DAYCARE_SINGLE = 25.00

    total          = 0.0
    boarding_ids   = []
    attendance_ids = []

    for pet in customer.pets:
        if invoice_type == 'boarding':
            boardings = Boarding.query.filter_by(
                pet_id=pet.id, status='completed'
            ).filter(Boarding.payment_id == None).all()

            for b in boardings:
                days     = _boarding_days(b)
                siblings = Boarding.query.filter_by(
                    user_id=b.user_id,
                    check_in_date=b.check_in_date,
                    check_out_date=b.check_out_date,
                    status='completed'
                ).order_by(Boarding.pet_id.asc()).all()
                is_first = (not siblings) or siblings[0].pet_id == pet.id
                rate     = 40.00 if is_first else 25.00
                amount   = rate * days

                try:
                    from app.models import Appointment as _Appt, ServiceType as _ST
                    _svc = _ST.query.filter(_ST.name.ilike('%boarding%')).first()
                    if _svc:
                        _a = _Appt.query.filter_by(
                            pet_id=pet.id, user_id=customer.id,
                            service_type_id=_svc.id
                        ).order_by(_Appt.id.desc()).first()
                        if _a and _a.notes:
                            _, addon_cost = _parse_addons_from_notes(_a.notes)
                            amount += addon_cost
                except Exception:
                    pass

                total += amount
                boarding_ids.append(b.id)

        elif invoice_type == 'daycare':
            for enr in DaycareEnrollment.query.filter_by(pet_id=pet.id).all():
                attendances = DaycareAttendance.query.filter_by(
                    enrollment_id=enr.id
                ).filter(
                    DaycareAttendance.check_out_time != None,
                    DaycareAttendance.payment_id == None
                ).all()
                for att in attendances:
                    week_start = att.check_in_time.date() - timedelta(days=att.check_in_time.weekday())
                    week_end   = week_start + timedelta(days=6)
                    week_count = DaycareAttendance.query.filter(
                        DaycareAttendance.enrollment_id == enr.id,
                        DaycareAttendance.check_in_time >= week_start,
                        DaycareAttendance.check_in_time <= week_end
                    ).count()
                    rate = enr.special_rate if enr.special_rate else (DAYCARE_MULTI if week_count > 1 else DAYCARE_SINGLE)
                    total += rate
                    attendance_ids.append(att.id)

    if total <= 0:
        flash('No unpaid services found.', 'info')
        return redirect(url_for('admin.customer_invoice', customer_id=customer_id, type=invoice_type))

    payment = Payment(
        customer_id    = customer_id,
        amount         = round(total, 2),
        payment_date   = today,
        payment_method = method,
        service_type   = invoice_type.capitalize(),
        notes          = f'{invoice_type.capitalize()} invoice paid — {len(boarding_ids) or len(attendance_ids)} record(s)',
        status         = 'paid'
    )
    db.session.add(payment)
    db.session.flush()

    for bid in boarding_ids:
        b = Boarding.query.get(bid)
        if b:
            b.payment_id = payment.id

    for aid in attendance_ids:
        a = DaycareAttendance.query.get(aid)
        if a:
            a.payment_id = payment.id

    db.session.commit()
    try:
        from app.audit_service import audit
        audit('invoice.paid', 'payment', payment.id,
              f'Customer #{customer_id}',
              f'{invoice_type.capitalize()} invoice ${total:.2f} paid — recorded by {current_user.first_name} {current_user.last_name}')
    except Exception: pass
    flash(f'{invoice_type.capitalize()} invoice marked as paid — ${total:.2f} recorded.', 'success')
    return redirect(url_for('admin.customer_detail', customer_id=customer_id))


@bp.route('/reports')
@login_required
@admin_required
def reports_dashboard():
    """Analytics and reporting dashboard."""
    from app.models import Payment, Boarding, DaycareAttendance, DaycareEnrollment, VaccinationRecord
    from datetime import date, timedelta
    from collections import defaultdict
    import json, re

    today     = date.today()
    year      = today.year

    # ── 1. Monthly Revenue (last 12 months) ───────────────────────────────
    revenue_months  = []
    revenue_boarding = []
    revenue_daycare  = []
    revenue_addons   = []

    DAYCARE_MULTI  = 20.0
    DAYCARE_SINGLE = 25.0

    def _boarding_days_r(b):
        base = (b.check_out_date - b.check_in_date).days
        cout = str(b.check_out_time or '17:00')[:5]
        return base if cout <= '10:00' else base + 1

    for i in range(11, -1, -1):
        mo = (today.month - 1 - i) % 12 + 1
        yr = today.year - ((i - today.month + 1) // 12 + (1 if (i - today.month + 1) % 12 != 0 else 0))
        if mo > today.month:
            yr = today.year - 1
        # Recalculate properly
        from datetime import date as d_
        ref = d_(today.year, today.month, 1)
        for _ in range(i):
            ref = (ref.replace(day=1) - timedelta(days=1)).replace(day=1)
        mo, yr = ref.month, ref.year

        revenue_months.append(ref.strftime('%b %Y'))

        # Boarding revenue from payments in that month
        mo_payments = Payment.query.filter(
            Payment.status == 'paid',
            db.extract('month', Payment.payment_date) == mo,
            db.extract('year',  Payment.payment_date) == yr
        ).all()

        b_rev  = sum(p.amount for p in mo_payments
                     if p.service_type and 'board' in p.service_type.lower())
        dc_rev = sum(p.amount for p in mo_payments
                     if p.service_type and 'daycare' in p.service_type.lower())
        # Everything else counts as add-ons/misc
        other  = sum(p.amount for p in mo_payments
                     if p.service_type and 'board' not in p.service_type.lower()
                     and 'daycare' not in p.service_type.lower())

        revenue_boarding.append(round(b_rev + other * 0.5, 2))
        revenue_daycare.append(round(dc_rev, 2))
        revenue_addons.append(round(other * 0.5, 2))

    # ── 2. Outstanding Balances (top 10 customers) ────────────────────────
    outstanding_raw = (db.session.query(
        Payment.customer_id,
        db.func.sum(Payment.amount).label('total')
    ).filter_by(status='outstanding')
     .group_by(Payment.customer_id)
     .order_by(db.func.sum(Payment.amount).desc())
     .limit(10).all())

    outstanding_labels  = []
    outstanding_amounts = []
    for row in outstanding_raw:
        c = User.query.get(row.customer_id)
        if c:
            outstanding_labels.append(f'{c.first_name} {c.last_name}')
            outstanding_amounts.append(float(row.total))

    # ── 3. Add-on Attach Rate ─────────────────────────────────────────────
    from app.models import Appointment, ServiceType as _ST
    _bsvc = _ST.query.filter(_ST.name.ilike('%boarding%')).first()
    total_boarding_appts = 0
    addons_count         = 0
    if _bsvc:
        appts = Appointment.query.filter_by(service_type_id=_bsvc.id).all()
        total_boarding_appts = len(appts)
        addons_count = sum(1 for a in appts if a.notes and 'Add-ons:' in a.notes)
    attach_rate   = round((addons_count / total_boarding_appts * 100) if total_boarding_appts else 0, 1)

    # Breakdown by addon type
    spa_bath_count  = 0
    nails_count     = 0
    both_count      = 0
    if _bsvc:
        for a in Appointment.query.filter_by(service_type_id=_bsvc.id).all():
            if not a.notes or 'Add-ons:' not in a.notes:
                continue
            n = a.notes.lower()
            has_bath  = 'spa bath' in n
            has_nails = 'nail' in n
            if has_bath and has_nails:
                both_count += 1
            elif has_bath:
                spa_bath_count += 1
            elif has_nails:
                nails_count += 1

    # ── 4. Revenue per customer (top 10) ──────────────────────────────────
    top_customers_raw = (db.session.query(
        Payment.customer_id,
        db.func.sum(Payment.amount).label('total')
    ).filter_by(status='paid')
     .group_by(Payment.customer_id)
     .order_by(db.func.sum(Payment.amount).desc())
     .limit(10).all())

    top_customer_labels  = []
    top_customer_amounts = []
    for row in top_customers_raw:
        c = User.query.get(row.customer_id)
        if c:
            top_customer_labels.append(f'{c.first_name} {c.last_name}')
            top_customer_amounts.append(float(row.total))

    # ── 5. Occupancy rate (last 60 days) ──────────────────────────────────
    from app.settings_service import get_kennel_capacity
    TOTAL_KENNELS = get_kennel_capacity()
    occ_labels      = []
    occ_values      = []
    for i in range(59, -1, -1):
        d = today - timedelta(days=i)
        count = Boarding.query.filter(
            Boarding.check_in_date  <= d,
            Boarding.check_out_date >= d,
            Boarding.status.in_(['active', 'completed'])
        ).count()
        occ_labels.append(d.strftime('%b %d'))
        occ_values.append(min(round(count / TOTAL_KENNELS * 100, 1), 100))

    # ── 6. Average length of stay ─────────────────────────────────────────
    stay_buckets = {'1 day': 0, '2–3 days': 0, '4–6 days': 0, '7–13 days': 0, '14+ days': 0}
    for b in Boarding.query.filter(Boarding.status == 'completed').all():
        days = _boarding_days_r(b)
        if   days <= 1:  stay_buckets['1 day']     += 1
        elif days <= 3:  stay_buckets['2–3 days']   += 1
        elif days <= 6:  stay_buckets['4–6 days']   += 1
        elif days <= 13: stay_buckets['7–13 days']  += 1
        else:            stay_buckets['14+ days']   += 1

    # ── 7. Daycare heatmap — avg attendance by day of week ────────────────
    day_counts = defaultdict(int)
    day_weeks  = defaultdict(set)
    for att in DaycareAttendance.query.filter(
        DaycareAttendance.check_out_time != None
    ).all():
        wd = att.check_in_time.strftime('%A')
        wk = att.check_in_time.strftime('%Y-W%U')
        day_counts[wd] += 1
        day_weeks[wd].add(wk)

    days_order  = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday']
    heatmap_labels = days_order
    heatmap_values = []
    for d in days_order:
        weeks = len(day_weeks[d]) or 1
        heatmap_values.append(round(day_counts[d] / weeks, 1))

    # ── 8. New customer growth (last 12 months) ───────────────────────────
    growth_months = revenue_months[:]  # reuse same month labels
    growth_values = []
    for label in growth_months:
        from datetime import datetime as _dt
        ref = _dt.strptime(label, '%b %Y')
        count = User.query.filter(
            User.role == 'customer',
            db.extract('month', User.created_at) == ref.month,
            db.extract('year',  User.created_at) == ref.year
        ).count()
        growth_values.append(count)

    # ── 9. Retention vs churn ─────────────────────────────────────────────
    cutoff_active = today - timedelta(days=90)
    cutoff_churn  = today - timedelta(days=90)
    all_customers = User.query.filter_by(role='customer', is_active=True).all()

    active_count = 0
    at_risk_count = 0
    churned_count = 0

    for c in all_customers:
        last_b = Boarding.query.filter_by(user_id=c.id).order_by(Boarding.check_in_date.desc()).first()
        last_d = None
        for enr in c.pets:
            pass  # will query below
        # Last activity
        last_boarding  = Boarding.query.join(Pet).filter(Pet.user_id == c.id).order_by(Boarding.check_in_date.desc()).first()
        enr_ids        = [e.id for p in c.pets for e in p.enrollments]
        last_daycare   = None
        if enr_ids:
            last_daycare = DaycareAttendance.query.filter(
                DaycareAttendance.enrollment_id.in_(enr_ids)
            ).order_by(DaycareAttendance.check_in_time.desc()).first()

        last_activity = None
        if last_boarding:
            last_activity = last_boarding.check_in_date
        if last_daycare:
            ld = last_daycare.check_in_time.date()
            last_activity = max(last_activity, ld) if last_activity else ld

        if last_activity is None:
            churned_count += 1
        elif last_activity >= cutoff_active:
            active_count += 1
        elif last_activity >= today - timedelta(days=180):
            at_risk_count += 1
        else:
            churned_count += 1

    # ── 10. Summary KPIs ─────────────────────────────────────────────────
    total_revenue    = sum(p.amount for p in Payment.query.filter_by(status='paid').all())
    total_outstanding= sum(p.amount for p in Payment.query.filter_by(status='outstanding').all())
    total_boardings  = Boarding.query.filter_by(status='completed').count()
    total_customers  = User.query.filter_by(role='customer', is_active=True).count()
    total_pets       = Pet.query.filter_by(is_active=True).count()
    avg_stay         = 0
    stays = [_boarding_days_r(b) for b in Boarding.query.filter_by(status='completed').all()]
    if stays:
        avg_stay = round(sum(stays) / len(stays), 1)

    return render_template('admin/reports.html',
        today=today,
        # Revenue
        revenue_months=json.dumps(revenue_months),
        revenue_boarding=json.dumps(revenue_boarding),
        revenue_daycare=json.dumps(revenue_daycare),
        revenue_addons=json.dumps(revenue_addons),
        # Outstanding
        outstanding_labels=json.dumps(outstanding_labels),
        outstanding_amounts=json.dumps(outstanding_amounts),
        # Add-on attach rate
        attach_rate=attach_rate,
        total_boarding_appts=total_boarding_appts,
        addons_count=addons_count,
        spa_bath_count=spa_bath_count,
        nails_count=nails_count,
        both_count=both_count,
        # Top customers
        top_customer_labels=json.dumps(top_customer_labels),
        top_customer_amounts=json.dumps(top_customer_amounts),
        # Occupancy
        occ_labels=json.dumps(occ_labels),
        occ_values=json.dumps(occ_values),
        # Stay length
        stay_buckets=json.dumps(list(stay_buckets.keys())),
        stay_values=json.dumps(list(stay_buckets.values())),
        # Daycare heatmap
        heatmap_labels=json.dumps(heatmap_labels),
        heatmap_values=json.dumps(heatmap_values),
        # Growth
        growth_months=json.dumps(growth_months),
        growth_values=json.dumps(growth_values),
        # Retention
        active_count=active_count,
        at_risk_count=at_risk_count,
        churned_count=churned_count,
        # KPIs
        total_revenue=total_revenue,
        total_outstanding=total_outstanding,
        total_boardings=total_boardings,
        total_customers=total_customers,
        total_pets=total_pets,
        avg_stay=avg_stay,
        TOTAL_KENNELS=TOTAL_KENNELS,
        kennel_capacity=TOTAL_KENNELS,
    )


@bp.route('/appointments/<int:appt_id>/archive', methods=['POST'])
@login_required
@admin_required
def archive_appointment(appt_id):
    appt = Appointment.query.get_or_404(appt_id)
    appt.archived = True
    db.session.commit()
    flash(f'Appointment #{appt_id} archived.', 'success')
    return redirect(url_for('admin.appointments'))


@bp.route('/appointments/archived')
@login_required
@admin_required
def archived_appointments():
    appointments = Appointment.query.filter_by(archived=True).order_by(Appointment.appointment_date.desc()).all()
    return render_template('admin/appointments.html', appointments=appointments, show_archived=True)



@bp.route('/customers/<int:customer_id>/daycare/update', methods=['POST'])
@login_required
@admin_required
def update_daycare_schedule(customer_id):
    """Update daycare days for a customer's enrolled pets"""
    from app.models import DaycareEnrollment
    enrollments = DaycareEnrollment.query.join(DaycareEnrollment.pet).filter_by(user_id=customer_id).all()
    for enrollment in enrollments:
        prefix = f'enrollment_{enrollment.id}_'
        enrollment.monday    = bool(request.form.get(f'{prefix}monday'))
        enrollment.tuesday   = bool(request.form.get(f'{prefix}tuesday'))
        enrollment.wednesday = bool(request.form.get(f'{prefix}wednesday'))
        enrollment.thursday  = bool(request.form.get(f'{prefix}thursday'))
        enrollment.friday    = bool(request.form.get(f'{prefix}friday'))
    db.session.commit()
    flash('Daycare schedule updated.', 'success')
    return redirect(url_for('admin.customer_detail', customer_id=customer_id))

# ============================================================
# SMS INBOX
# ============================================================

@bp.route('/inbox')
@login_required
@admin_required
def sms_inbox():
    """
    Show all SMS conversations grouped by customer account.
    Unknown senders (no matching User) are grouped separately.
    """
    from app.models import SmsMessage
    from sqlalchemy import func
    import json

    # Get the most recent message per user_id (known customers)
    known_threads = (
        db.session.query(
            SmsMessage.user_id,
            func.max(SmsMessage.created_at).label('last_at'),
            func.sum(
                db.case((
                    (SmsMessage.is_read == False) & (SmsMessage.direction == 'inbound'),
                    1
                ), else_=0)
            ).label('unread_count')
        )
        .filter(SmsMessage.user_id.isnot(None))
        .group_by(SmsMessage.user_id)
        .order_by(func.max(SmsMessage.created_at).desc())
        .all()
    )

    threads = []
    for row in known_threads:
        user = User.query.get(row.user_id)
        last_msg = (SmsMessage.query
                    .filter_by(user_id=row.user_id)
                    .order_by(SmsMessage.created_at.desc())
                    .first())
        threads.append({
            'user':         user,
            'last_message': last_msg,
            'unread_count': row.unread_count,
            'last_at':      row.last_at,
        })

    # Unknown senders (no user account matched)
    unknown_msgs = (SmsMessage.query
                    .filter_by(user_id=None, direction='inbound')
                    .order_by(SmsMessage.created_at.desc())
                    .all())

    # All active customers — for the ad-hoc message picker
    all_customers = (User.query
                     .filter_by(is_active=True, is_admin=False)
                     .order_by(User.last_name.asc(), User.first_name.asc())
                     .all())
    customers_json = json.dumps([
        {
            'id':         c.id,
            'name':       f'{c.first_name} {c.last_name}',
            'phone':      c.phone or '',
            'sms_opt_in': c.sms_opt_in,
        }
        for c in all_customers
    ])

    return render_template('admin/inbox.html',
                           threads=threads,
                           unknown_msgs=unknown_msgs,
                           customers_json=customers_json)


@bp.route('/sms/media-proxy')
@login_required
@admin_required
def sms_media_proxy():
    """Proxy Twilio MMS media URLs so the browser doesn't need Twilio credentials."""
    import requests as _req
    from flask import Response
    url = request.args.get('url', '').strip()
    if not url or 'twilio.com' not in url:
        return ('Forbidden', 403)
    try:
        r = _req.get(
            url,
            auth=(current_app.config.get('TWILIO_ACCOUNT_SID'),
                  current_app.config.get('TWILIO_AUTH_TOKEN')),
            timeout=10
        )
        return Response(r.content, content_type=r.headers.get('Content-Type', 'image/jpeg'))
    except Exception as e:
        current_app.logger.error(f'MMS proxy error: {e}')
        return ('Error fetching media', 502)


@bp.route('/sms-report')
@login_required
@admin_required
def sms_report():
    """SMS send counts broken down by category."""
    from app.models import SmsMessage
    from datetime import date, timedelta

    period = request.args.get('period', '30')  # 7, 30, 90, or 'all'

    query = SmsMessage.query
    if period != 'all':
        try:
            days = int(period)
            since = date.today() - timedelta(days=days)
            query = query.filter(SmsMessage.created_at >= since)
        except ValueError:
            pass

    all_msgs = query.order_by(SmsMessage.created_at.desc()).all()

    # ── Categorise each outbound message ────────────────────────────────────
    CATEGORIES = [
        # Marker-based (exact, highest priority)
        ('Vaccine Nudge',         lambda b: '[no-vaccine-nudge]' in b),
        ('No Pet Nudge',          lambda b: '[no-pet-nudge]' in b),
        ('Checkout Estimate',     lambda b: '[checkout-estimate]' in b),
        # Boarding
        ('Boarding Approved',     lambda b: 'boarding' in b and ('approved' in b or 'confirmed' in b) and 'cancelled' not in b),
        ('Boarding Cancelled',    lambda b: 'boarding' in b and 'cancelled' in b),
        ('Boarding Completed',    lambda b: 'stay is complete' in b or ('boarding' in b and 'complete' in b)),
        # Appointments (grooming etc.)
        ('Appt Confirmed',        lambda b: 'appointment' in b and 'confirmed' in b),
        ('Appt Cancelled',        lambda b: 'appointment' in b and 'cancelled' in b),
        ('Appt Reminder',         lambda b: 'appointment' in b and 'tomorrow' in b),
        # Daycare
        ('Daycare Check-In',      lambda b: 'daycare' in b and 'checked in' in b),
        ('Daycare Checkout',      lambda b: 'daycare' in b and ('checked out' in b or 'checkout' in b)),
        # Misc automated
        ('Password Reset',        lambda b: 'reset' in b and 'password' in b),
        ('Waitlist',              lambda b: 'waitlist' in b or 'waiting list' in b),
        ('Report Card',           lambda b: 'report card' in b),
        ('Incident Report',       lambda b: 'incident' in b and 'ruff life' in b),
        ('Welcome',               lambda b: 'welcome to ruff life' in b),
        ('SMS Opt-In',            lambda b: 'subscribed to sms' in b or 'msg & data rates' in b),
    ]

    def categorise(msg):
        body = (msg.body or '').lower()
        if msg.direction == 'inbound':
            return 'Inbound'
        for name, fn in CATEGORIES:
            if fn(body):
                return name
        return 'Other'

    counts   = {name: 0 for name, _ in CATEGORIES}
    counts['Inbound'] = 0
    counts['Other']   = 0
    total_out = 0
    total_in  = 0
    detail_msgs = []

    active_category = request.args.get('category', '')

    for msg in all_msgs:
        cat = categorise(msg)
        counts[cat] = counts.get(cat, 0) + 1
        if msg.direction == 'inbound':
            total_in += 1
        else:
            total_out += 1
        if active_category and cat == active_category:
            detail_msgs.append(msg)

    rows = [(name, counts[name]) for name, _ in CATEGORIES]
    rows += [('Inbound', counts['Inbound']), ('Other', counts['Other'])]

    # If no category filter, show all messages
    if not active_category:
        detail_msgs = all_msgs

    # ── Twilio cost lookup ───────────────────────────────────────────────────
    twilio_costs = None
    try:
        from twilio.rest import Client as TwilioClient
        tc = TwilioClient(
            current_app.config.get('TWILIO_ACCOUNT_SID'),
            current_app.config.get('TWILIO_AUTH_TOKEN')
        )
        kwargs = {}
        if period != 'all':
            kwargs['start_date'] = since
            kwargs['end_date']   = date.today()

        out_records = tc.usage.records.list(category='sms-outbound-longcode', **kwargs)
        in_records  = tc.usage.records.list(category='sms-inbound-longcode',  **kwargs)

        out_cost = sum(abs(float(r.price or 0)) for r in out_records)
        in_cost  = sum(abs(float(r.price or 0)) for r in in_records)
        twilio_costs = {
            'outbound': out_cost,
            'inbound':  in_cost,
            'total':    out_cost + in_cost,
            'currency': (out_records[0].price_unit if out_records else 'USD'),
        }
    except Exception as e:
        current_app.logger.warning(f'Twilio usage fetch failed: {e}')

    return render_template('admin/sms_report.html',
        rows=rows, total_out=total_out, total_in=total_in,
        period=period, active_category=active_category,
        detail_msgs=detail_msgs, twilio_costs=twilio_costs)


@bp.route('/inbox/adhoc', methods=['POST'])
@login_required
@admin_required
def sms_adhoc():
    """Send a one-off SMS to any customer, opened from the inbox."""
    from app.models import SmsMessage
    from app.sms_service import _normalize_phone
    from twilio.rest import Client

    user_id = request.form.get('user_id', '').strip()
    body    = request.form.get('body', '').strip()

    if not user_id or not body:
        flash('Customer and message are both required.', 'warning')
        return redirect(url_for('admin.sms_inbox'))

    customer = User.query.get_or_404(int(user_id))

    if not customer.phone:
        flash(f'{customer.first_name} does not have a phone number on file.', 'danger')
        return redirect(url_for('admin.sms_inbox'))

    try:
        account_sid = current_app.config.get('TWILIO_ACCOUNT_SID')
        auth_token  = current_app.config.get('TWILIO_AUTH_TOKEN')
        from_number = current_app.config.get('TWILIO_PHONE_NUMBER')
        to_e164     = _normalize_phone(customer.phone)

        client  = Client(account_sid, auth_token)
        message = client.messages.create(body=body, from_=from_number, to=to_e164)

        msg = SmsMessage(
            user_id     = customer.id,
            direction   = 'outbound',
            from_number = from_number,
            to_number   = to_e164,
            body        = body,
            twilio_sid  = message.sid,
            is_read     = True
        )
        db.session.add(msg)
        db.session.commit()
        flash(f'Message sent to {customer.first_name} {customer.last_name}.', 'success')
        return redirect(url_for('admin.sms_conversation', user_id=customer.id))

    except Exception as e:
        current_app.logger.error(f'Ad-hoc SMS failed for user {user_id}: {e}')
        flash(f'Failed to send message: {e}', 'danger')
        return redirect(url_for('admin.sms_inbox'))


@bp.route('/inbox/<int:user_id>')
@login_required
@admin_required
def sms_conversation(user_id):
    """View full SMS conversation with a specific customer."""
    from app.models import SmsMessage
    from datetime import date

    customer = User.query.get_or_404(user_id)
    messages = (SmsMessage.query
                .filter_by(user_id=user_id)
                .order_by(SmsMessage.created_at.asc())
                .all())

    # Mark all inbound messages as read
    (SmsMessage.query
     .filter_by(user_id=user_id, direction='inbound', is_read=False)
     .update({'is_read': True}))
    db.session.commit()

    return render_template('admin/inbox_conversation.html',
                           customer=customer,
                           messages=messages,
                           today=date.today())


@bp.route('/inbox/<int:user_id>/reply', methods=['POST'])
@login_required
@admin_required
def sms_reply(user_id):
    """Send an SMS reply to a customer from the admin inbox."""
    from app.models import SmsMessage
    from app.sms_service import _normalize_phone
    from twilio.rest import Client

    customer = User.query.get_or_404(user_id)
    body = request.form.get('body', '').strip()

    if not body:
        flash('Message cannot be empty.', 'warning')
        return redirect(url_for('admin.sms_conversation', user_id=user_id))

    if not customer.phone:
        flash(f'{customer.first_name} does not have a phone number on file.', 'danger')
        return redirect(url_for('admin.sms_conversation', user_id=user_id))

    try:
        account_sid = current_app.config.get('TWILIO_ACCOUNT_SID')
        auth_token  = current_app.config.get('TWILIO_AUTH_TOKEN')
        from_number = current_app.config.get('TWILIO_PHONE_NUMBER')
        to_e164     = _normalize_phone(customer.phone)

        client  = Client(account_sid, auth_token)
        message = client.messages.create(body=body, from_=from_number, to=to_e164)

        msg = SmsMessage(
            user_id     = customer.id,
            direction   = 'outbound',
            from_number = from_number,
            to_number   = to_e164,
            body        = body,
            twilio_sid  = message.sid,
            is_read     = True
        )
        db.session.add(msg)
        db.session.commit()
        flash('Message sent!', 'success')
    except Exception as e:
        current_app.logger.error(f'Admin SMS reply failed for user {user_id}: {e}')
        flash(f'Failed to send message: {e}', 'danger')

    return redirect(url_for('admin.sms_conversation', user_id=user_id))


@bp.route('/inbox/<int:user_id>/delete', methods=['POST'])
@login_required
@admin_required
def sms_delete_thread(user_id):
    """Delete all SMS messages in a conversation with a customer."""
    from app.models import SmsMessage
    SmsMessage.query.filter_by(user_id=user_id).delete()
    db.session.commit()
    flash('Conversation deleted.', 'success')
    return redirect(url_for('admin.sms_inbox'))


@bp.route('/inbox/unknown/<int:msg_id>/delete', methods=['POST'])
@login_required
@admin_required
def sms_delete_unknown(msg_id):
    """Delete a single unknown sender SMS message."""
    from app.models import SmsMessage
    msg = SmsMessage.query.get_or_404(msg_id)
    db.session.delete(msg)
    db.session.commit()
    flash('Message deleted.', 'success')
    return redirect(url_for('admin.sms_inbox'))
# ============================================================
# PET DETAIL + VACCINATION MANAGEMENT
# ============================================================

@bp.route('/pets/<int:pet_id>/detail')
@login_required
@admin_required
def pet_detail(pet_id):
    """Pet detail page with vaccination records."""
    from app.models import Pet
    from app.rate_resolver import get_pet_boarding_rate, get_pet_daycare_rate, rate_source
    pet      = Pet.query.get_or_404(pet_id)
    customer = pet.owner

    effective_boarding_rate = get_pet_boarding_rate(pet, customer, is_additional=False)
    effective_daycare_rate  = get_pet_daycare_rate(pet, customer)
    rate_source_boarding    = rate_source(pet, customer, 'boarding')
    rate_source_daycare     = rate_source(pet, customer, 'daycare')

    return render_template('admin/pet_detail.html',
        pet=pet, now=datetime.now(),
        effective_boarding_rate=effective_boarding_rate,
        effective_daycare_rate=effective_daycare_rate,
        rate_source_boarding=rate_source_boarding,
        rate_source_daycare=rate_source_daycare)


@bp.route('/customers/<int:customer_id>/add-pet', methods=['GET', 'POST'])
@login_required
@admin_required
def admin_add_pet(customer_id):
    """Add a pet to a customer's account from the admin side."""
    from app.models import Pet
    customer = User.query.get_or_404(customer_id)

    if request.method == 'POST':
        name        = request.form.get('name', '').strip()
        breed       = request.form.get('breed', '').strip() or None
        weight      = request.form.get('weight', type=float) or None
        temperament = request.form.get('temperament', 'calm')

        if not name:
            flash('Pet name is required.', 'danger')
            return redirect(url_for('admin.admin_add_pet', customer_id=customer_id))

        pet = Pet(
            user_id              = customer_id,
            name                 = name,
            breed                = breed,
            weight               = weight,
            age                  = request.form.get('age', type=int) or None,
            gender               = request.form.get('gender', '').strip() or None,
            temperament          = temperament,
            spayed_neutered      = request.form.get('spayed_neutered') == '1',
            vet_name             = request.form.get('vet_name', '').strip() or None,
            vet_phone            = request.form.get('vet_phone', '').strip() or None,
            medical_notes        = request.form.get('medical_notes', '').strip() or None,
            special_instructions = request.form.get('special_instructions', '').strip() or None,
            is_active            = True
        )
        db.session.add(pet)
        db.session.flush()  # get pet.id before commit

        # Handle pet photo upload
        upload_dir = os.path.join(current_app.root_path, 'static', 'uploads')
        os.makedirs(upload_dir, exist_ok=True)

        pet_photo = request.files.get('pet_photo')
        if pet_photo and pet_photo.filename:
            from werkzeug.utils import secure_filename
            filename = secure_filename(f'pet_{customer_id}_{pet.name}_{pet_photo.filename}')
            pet_photo.save(os.path.join(upload_dir, filename))
            pet.photo_path = filename

        vaccine_record = request.files.get('vaccine_record')
        if vaccine_record and vaccine_record.filename:
            from werkzeug.utils import secure_filename
            filename = secure_filename(f'vaccine_{customer_id}_{pet.name}_{vaccine_record.filename}')
            vaccine_record.save(os.path.join(upload_dir, filename))
            pet.vaccination_record_path = filename

        db.session.commit()

        # Mark onboarding complete if the customer now has at least one active pet
        if not customer.onboarding_complete:
            customer.onboarding_complete = True
            db.session.commit()

        try:
            from app.audit_service import audit
            audit('pet.created', 'pet', pet.id, name,
                  f'Pet {name} added to customer #{customer_id} by {current_user.first_name} {current_user.last_name}')
        except Exception: pass
        flash(f'{name} added successfully! Add vaccination records below.', 'success')
        return redirect(url_for('admin.pet_detail', pet_id=pet.id))

    return render_template('admin/admin_add_pet.html', customer=customer)


@bp.route('/pets/<int:pet_id>/edit', methods=['POST'])
@login_required
@admin_required
def edit_pet(pet_id):
    """Edit a pet's basic info."""
    from app.models import Pet
    pet = Pet.query.get_or_404(pet_id)

    pet.name                 = request.form.get('name', '').strip() or pet.name
    pet.breed                = request.form.get('breed', '').strip() or None
    pet.gender               = request.form.get('gender', '').strip() or None
    pet.temperament          = request.form.get('temperament', '').strip() or None
    pet.vet_name             = request.form.get('vet_name', '').strip() or None
    pet.vet_phone            = request.form.get('vet_phone', '').strip() or None
    pet.special_instructions = request.form.get('special_instructions', '').strip() or None
    pet.medical_notes        = request.form.get('medical_notes', '').strip() or None
    pet.additional_notes     = request.form.get('additional_notes', '').strip() or None
    pet.spayed_neutered      = request.form.get('spayed_neutered') == '1'

    weight = request.form.get('weight', '').strip()
    pet.weight = float(weight) if weight else None

    age = request.form.get('age', '').strip()
    pet.age = int(age) if age else None

    # Handle optional photo upload
    photo = request.files.get('pet_photo')
    if photo and photo.filename:
        from werkzeug.utils import secure_filename
        upload_dir = os.path.join(current_app.root_path, 'static', 'uploads')
        os.makedirs(upload_dir, exist_ok=True)
        filename = secure_filename(f'pet_{pet.user_id}_{pet.id}_{photo.filename}')
        photo.save(os.path.join(upload_dir, filename))
        pet.photo_path = filename

    db.session.commit()
    try:
        from app.audit_service import audit
        audit('pet.updated', 'pet', pet_id, pet.name,
              f'Pet {pet.name} updated by {current_user.first_name} {current_user.last_name}')
    except Exception: pass
    flash(f'{pet.name} updated successfully.', 'success')
    return redirect(url_for('admin.pet_detail', pet_id=pet_id))


@bp.route('/pets/<int:pet_id>/upload-photo', methods=['POST'])
@login_required
@admin_required
def upload_pet_photo(pet_id):
    """Standalone pet photo upload from the admin pet detail page."""
    from app.models import Pet
    from werkzeug.utils import secure_filename
    pet = Pet.query.get_or_404(pet_id)

    photo = request.files.get('pet_photo')
    if not photo or not photo.filename:
        flash('No photo selected.', 'warning')
        return redirect(url_for('admin.pet_detail', pet_id=pet_id))

    upload_dir = os.path.join(current_app.root_path, 'static', 'uploads')
    os.makedirs(upload_dir, exist_ok=True)
    filename = secure_filename(f'pet_{pet.user_id}_{pet.id}_{photo.filename}')
    photo.save(os.path.join(upload_dir, filename))
    pet.photo_path = filename
    db.session.commit()

    flash(f'Photo updated for {pet.name}.', 'success')
    return redirect(url_for('admin.pet_detail', pet_id=pet_id))


@bp.route('/pets/<int:pet_id>/vaccinations/add', methods=['POST'])
@login_required
@admin_required
def add_vaccination(pet_id):
    """Add a new vaccination record to a pet."""
    from app.models import Pet, VaccinationRecord
    from datetime import datetime
    Pet.query.get_or_404(pet_id)

    vax_date = request.form.get('vaccination_date', '').strip()
    exp_date = request.form.get('expiration_date', '').strip()

    if not vax_date or not exp_date:
        flash('Vaccination date and expiration date are required.', 'danger')
        return redirect(url_for('admin.pet_detail', pet_id=pet_id))

    rec = VaccinationRecord(
        pet_id           = pet_id,
        vaccine_name     = request.form.get('vaccine_name', '').strip(),
        vaccination_date = datetime.strptime(vax_date, '%Y-%m-%d').date() if vax_date else None,
        expiration_date  = datetime.strptime(exp_date, '%Y-%m-%d').date() if exp_date else None,
        veterinarian     = request.form.get('administered_by', '').strip() or None,
    )
    db.session.add(rec)
    db.session.flush()  # get rec.id before saving file

    # Handle document upload on creation
    doc = request.files.get('vax_document')
    if doc and doc.filename:
        from werkzeug.utils import secure_filename
        upload_dir = os.path.join(current_app.root_path, 'static', 'uploads', 'vaccines')
        os.makedirs(upload_dir, exist_ok=True)
        filename = secure_filename(f'vax_{pet_id}_{rec.id}_{doc.filename}')
        doc.save(os.path.join(upload_dir, filename))
        rec.document_path = f'uploads/vaccines/{filename}'

    db.session.commit()

    # Auto-complete onboarding if the owner hasn't been marked complete yet
    # — staff added the pet and vaccinations outside the customer onboarding flow
    pet = Pet.query.get(pet_id)
    if pet and pet.owner and not pet.owner.onboarding_complete:
        has_pets = any(p.is_active for p in pet.owner.pets)
        if has_pets:
            pet.owner.onboarding_complete = True
            db.session.commit()

    try:
        from app.audit_service import audit
        audit('vaccination.created', 'vaccination', rec.id, rec.vaccine_name,
              f'{rec.vaccine_name} added for pet #{pet_id} by {current_user.first_name} {current_user.last_name}',
              {'expiration': str(rec.expiration_date)})
    except Exception: pass
    flash(f'{rec.vaccine_name} record added successfully.', 'success')
    return redirect(url_for('admin.pet_detail', pet_id=pet_id))


@bp.route('/vaccinations/<int:rec_id>/edit', methods=['POST'])
@login_required
@admin_required
def edit_vaccination(rec_id):
    """Edit an existing vaccination record."""
    from app.models import VaccinationRecord
    from datetime import datetime
    rec = VaccinationRecord.query.get_or_404(rec_id)

    vax_date = request.form.get('vaccination_date', '').strip()
    exp_date = request.form.get('expiration_date', '').strip()

    rec.vaccine_name     = request.form.get('vaccine_name', '').strip() or rec.vaccine_name
    rec.vaccination_date = datetime.strptime(vax_date, '%Y-%m-%d').date() if vax_date else rec.vaccination_date
    rec.expiration_date  = datetime.strptime(exp_date, '%Y-%m-%d').date() if exp_date else rec.expiration_date
    rec.veterinarian     = request.form.get('administered_by', '').strip() or None

    # Handle document upload
    doc = request.files.get('vax_document')
    if doc and doc.filename:
        from werkzeug.utils import secure_filename
        upload_dir = os.path.join(current_app.root_path, 'static', 'uploads', 'vaccines')
        os.makedirs(upload_dir, exist_ok=True)
        filename = secure_filename(f'vax_{rec.pet_id}_{rec.id}_{doc.filename}')
        doc.save(os.path.join(upload_dir, filename))
        rec.document_path = f'uploads/vaccines/{filename}'

    db.session.commit()
    try:
        from app.audit_service import audit
        audit('vaccination.updated', 'vaccination', rec_id, rec.vaccine_name,
              f'{rec.vaccine_name} updated for pet #{rec.pet_id} by {current_user.first_name} {current_user.last_name}')
    except Exception: pass
    flash(f'{rec.vaccine_name} record updated successfully.', 'success')
    return redirect(url_for('admin.pet_detail', pet_id=rec.pet_id))


@bp.route('/vaccinations/<int:rec_id>/delete', methods=['POST'])
@login_required
@admin_required
def delete_vaccination(rec_id):
    """Delete a vaccination record."""
    from app.models import VaccinationRecord
    rec = VaccinationRecord.query.get_or_404(rec_id)
    pet_id = rec.pet_id
    db.session.delete(rec)
    db.session.commit()
    try:
        from app.audit_service import audit
        audit('vaccination.deleted', 'vaccination', rec_id, 'Vaccination Record',
              f'Vaccination record #{rec_id} deleted for pet #{pet_id} by {current_user.first_name} {current_user.last_name}')
    except Exception: pass
    flash('Vaccination record deleted.', 'success')
    return redirect(url_for('admin.pet_detail', pet_id=pet_id))


@bp.route('/pet/<int:pet_id>/acknowledge-vacc-alert', methods=['POST'])
@login_required
def acknowledge_vacc_alert(pet_id):
    """Staff acknowledges a vaccination expiry alert for a pet."""
    from app.models import Pet
    from datetime import datetime
    pet = Pet.query.get_or_404(pet_id)
    reset = request.args.get('reset') == '1'
    if reset:
        pet.vacc_alert_acknowledged = False
        pet.vacc_alert_ack_at = None
        pet.vacc_alert_ack_by = None
        flash(f'Vaccination alert for {pet.name} has been reset.', 'info')
    else:
        pet.vacc_alert_acknowledged = True
        pet.vacc_alert_ack_at = datetime.now()
        pet.vacc_alert_ack_by = f'{current_user.first_name} {current_user.last_name}'
        flash(f'Vaccination alert for {pet.name} acknowledged.', 'success')
    db.session.commit()
    return redirect(url_for('admin.pet_detail', pet_id=pet_id))


# ============================================================
# GALLERY
# ============================================================

@bp.route('/gallery/upload', methods=['POST'])
@login_required
@admin_required
def gallery_upload():
    """Upload a photo to the public gallery."""
    import os
    from werkzeug.utils import secure_filename
    from app.models import GalleryPhoto

    photo = request.files.get('photo')
    caption  = request.form.get('caption', '').strip()
    category = request.form.get('category', 'General').strip()

    if not photo or not photo.filename:
        flash('No photo selected.', 'danger')
        return redirect(url_for('public.gallery'))

    gallery_dir = os.path.join(current_app.root_path, 'static', 'uploads', 'gallery')
    os.makedirs(gallery_dir, exist_ok=True)

    filename = secure_filename(photo.filename)
    # Prefix with timestamp to avoid collisions
    from datetime import datetime
    timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
    filename = f'{timestamp}_{filename}'
    photo.save(os.path.join(gallery_dir, filename))

    rec = GalleryPhoto(filename=filename, caption=caption, category=category)
    db.session.add(rec)
    db.session.commit()
    flash('Photo uploaded successfully!', 'success')
    return redirect(url_for('public.gallery'))


@bp.route('/gallery/<int:photo_id>/delete', methods=['POST'])
@login_required
@admin_required
def gallery_delete(photo_id):
    """Delete a gallery photo."""
    import os
    from app.models import GalleryPhoto

    photo = GalleryPhoto.query.get_or_404(photo_id)
    filepath = os.path.join(current_app.root_path, 'static', 'uploads', 'gallery', photo.filename)
    if os.path.exists(filepath):
        os.remove(filepath)
    db.session.delete(photo)
    db.session.commit()
    flash('Photo deleted.', 'success')
    return redirect(url_for('public.gallery'))


# ── HOMEPAGE PHOTO MANAGEMENT ────────────────────────────────────────────────

@bp.route('/site/homepage-photo', methods=['GET'])
@login_required
@admin_required
def homepage_photo_settings():
    """Show the homepage hero photo management page."""
    from app.settings_service import get_setting
    current_filename = get_setting('homepage_hero_photo')
    if current_filename:
        current_url = url_for('static', filename=f'uploads/homepage/{current_filename}')
    else:
        current_url = url_for('static', filename='img/homepage.jpg')
    return render_template('admin/homepage_photo.html',
                           current_url=current_url,
                           current_filename=current_filename)


@bp.route('/site/homepage-photo/upload', methods=['POST'])
@login_required
@admin_required
def homepage_photo_upload():
    """Replace the homepage hero photo — no server restart needed."""
    import os
    from werkzeug.utils import secure_filename
    from app.settings_service import set_setting, get_setting
    from datetime import datetime as _dt

    photo = request.files.get('photo')
    if not photo or not photo.filename:
        flash('No photo selected.', 'danger')
        return redirect(url_for('admin.homepage_photo_settings'))

    allowed = {'jpg', 'jpeg', 'png', 'gif', 'webp'}
    ext = photo.filename.rsplit('.', 1)[-1].lower()
    if ext not in allowed:
        flash('Invalid file type. Please upload a JPG, PNG, GIF, or WebP image.', 'danger')
        return redirect(url_for('admin.homepage_photo_settings'))

    upload_dir = os.path.join(current_app.root_path, 'static', 'uploads', 'homepage')
    os.makedirs(upload_dir, exist_ok=True)

    # Remove old uploaded file if one exists (keep static/img/homepage.jpg untouched)
    old_filename = get_setting('homepage_hero_photo')
    if old_filename:
        old_path = os.path.join(upload_dir, old_filename)
        if os.path.exists(old_path):
            try:
                os.remove(old_path)
            except OSError:
                pass

    filename = f'hero_{_dt.now().strftime("%Y%m%d%H%M%S")}.{ext}'
    photo.save(os.path.join(upload_dir, filename))
    set_setting('homepage_hero_photo', filename, user_id=current_user.id)

    flash('Homepage photo updated! Changes are live immediately.', 'success')
    return redirect(url_for('admin.homepage_photo_settings'))


@bp.route('/site/homepage-photo/reset', methods=['POST'])
@login_required
@admin_required
def homepage_photo_reset():
    """Revert to the default homepage photo."""
    import os
    from app.settings_service import set_setting, get_setting

    upload_dir = os.path.join(current_app.root_path, 'static', 'uploads', 'homepage')
    old_filename = get_setting('homepage_hero_photo')
    if old_filename:
        old_path = os.path.join(upload_dir, old_filename)
        if os.path.exists(old_path):
            try:
                os.remove(old_path)
            except OSError:
                pass
    set_setting('homepage_hero_photo', '', user_id=current_user.id)
    flash('Homepage photo reset to default.', 'info')
    return redirect(url_for('admin.homepage_photo_settings'))


@bp.route('/inbox/unread-count')
@login_required
@admin_required
def inbox_unread_count():
    """Lightweight endpoint for real-time badge polling."""
    from app.models import SmsMessage
    count = SmsMessage.query.filter_by(direction='inbound', is_read=False).count()
    return jsonify({'unread': count})


# ============================================================
# REPORT CARDS
# ============================================================

@bp.route('/report-cards')
@login_required
@admin_required
def report_cards():
    """
    Daily roster — today's daycare attendees and current boarding guests.
    Staff selects a pet and fills out their report card from here.
    """
    from app.models import DaycareAttendance, Boarding, ReportCard
    from datetime import date

    today = date.today()

    # Today's daycare check-ins — filter out any orphaned records
    daycare_today = [a for a in (DaycareAttendance.query
        .filter(db.func.date(DaycareAttendance.check_in_time) == today)
        .order_by(DaycareAttendance.check_in_time.asc())
        .all())
        if a is not None and a.enrollment is not None and a.enrollment.pet is not None]

    # Current boarding guests — only physically checked in
    boarding_active = (Boarding.query
        .filter_by(status='active', checked_in=True)
        .filter(Boarding.check_in_date <= today)
        .filter(Boarding.check_out_date >= today)
        .order_by(Boarding.check_in_date.asc())
        .all())

    # Build set of attendance IDs that have a sent report card today.
    # Use pet_id as the key — if any card was sent for this pet today, mark it.
    pets_with_sent_cards = {
        rc.pet_id for rc in ReportCard.query
        .filter_by(card_date=today)
        .filter(ReportCard.sent_at.isnot(None))
        .all()
    }

    # Map to attendance IDs — only the most recent attendance per pet gets the badge
    latest_att_per_pet = {}
    for att in daycare_today:
        if att.enrollment and att.enrollment.pet:
            pet_id = att.enrollment.pet.id
            if pet_id not in latest_att_per_pet:
                latest_att_per_pet[pet_id] = att
            elif att.check_in_time > latest_att_per_pet[pet_id].check_in_time:
                latest_att_per_pet[pet_id] = att

    sent_today = {
        att.id
        for pet_id, att in latest_att_per_pet.items()
        if pet_id in pets_with_sent_cards and att.id is not None
    }
    # Also include pet_ids directly so boarding section (which has no att variable) works
    sent_today |= pets_with_sent_cards

    return render_template('admin/report_cards.html',
                           daycare_today=daycare_today,
                           boarding_active=boarding_active,
                           sent_today=sent_today,
                           today=today)


@bp.route('/report-cards/create/<string:card_type>/<int:pet_id>', methods=['GET', 'POST'])
@login_required
@admin_required
def create_report_card(card_type, pet_id):
    """Create or edit a report card for a pet."""
    from app.models import Pet, ReportCard
    from datetime import date
    import secrets

    pet   = Pet.query.get_or_404(pet_id)
    today = date.today()

    # Check if one already exists for today
    existing = ReportCard.query.filter_by(
        pet_id=pet_id, card_date=today, card_type=card_type
    ).first()

    if request.method == 'POST':
        rc = existing or ReportCard(
            pet_id    = pet_id,
            card_type = card_type,
            card_date = today,
            token     = secrets.token_urlsafe(32)
        )

        rc.mood         = request.form.get('mood')
        rc.energy       = request.form.get('energy')
        rc.played_well  = request.form.get('played_well')
        rc.hydrated     = request.form.get('hydrated') == '1'
        rc.notes        = request.form.get('notes', '').strip() or None

        if card_type == 'boarding':
            rc.appetite          = request.form.get('appetite')
            rc.sleep             = request.form.get('sleep')
            rc.temperament       = request.form.get('temperament')
            rc.medications_given = request.form.get('medications_given') == '1'
            rc.bathroom          = request.form.get('bathroom')

        # Handle photo upload
        photo = request.files.get('photo')
        if photo and photo.filename:
            import os
            from werkzeug.utils import secure_filename
            from datetime import datetime as dt
            rc_dir = os.path.join(current_app.root_path, 'static', 'uploads', 'report_cards')
            os.makedirs(rc_dir, exist_ok=True)
            filename = f'{dt.now().strftime("%Y%m%d%H%M%S")}_{secure_filename(photo.filename)}'
            photo.save(os.path.join(rc_dir, filename))
            rc.photo_filename = filename

        if not existing:
            db.session.add(rc)
        db.session.commit()

        # Send SMS if requested
        if request.form.get('send_sms') == '1':
            from app.sms_service import _send, _normalize_phone
            from app.models import SmsMessage
            from datetime import datetime as dt
            try:
                owner      = pet.owner
                from_number = current_app.config.get('TWILIO_PHONE_NUMBER', '')
                to_e164     = _normalize_phone(owner.phone) if owner and owner.phone else None

                if to_e164:
                    from twilio.rest import Client
                    account_sid = current_app.config.get('TWILIO_ACCOUNT_SID')
                    auth_token  = current_app.config.get('TWILIO_AUTH_TOKEN')
                    card_type_label = 'daycare' if card_type == 'daycare' else 'boarding'
                    body = (
                        f"\U0001f43e {pet.name}'s {card_type_label} report card is in! "
                        f"See how their day went: https://rufflife.app/report/{rc.token}"
                    )
                    client  = Client(account_sid, auth_token)
                    message = client.messages.create(body=body, from_=from_number, to=to_e164)

                    # Log to SmsMessage
                    sms_log = SmsMessage(
                        user_id     = owner.id if owner else None,
                        direction   = 'outbound',
                        from_number = from_number,
                        to_number   = to_e164,
                        body        = body,
                        twilio_sid  = message.sid,
                        is_read     = True
                    )
                    db.session.add(sms_log)
                    rc.sent_at = dt.now()
                    db.session.commit()
                    try:
                        from app.audit_service import audit
                        audit('report_card.sent', 'report_card', rc.id, pet.name,
                              f'Report card sent for {pet.name} by {current_user.first_name} {current_user.last_name}')
                    except Exception: pass
                    flash(f'Report card for {pet.name} saved and SMS sent! 🐾', 'success')
                else:
                    flash(f'Report card saved. No phone number on file — SMS not sent.', 'warning')
            except Exception as e:
                current_app.logger.error(f'Report card SMS failed for pet {pet_id}: {e}')
                flash(f'Report card saved but SMS failed: {e}', 'warning')
        else:
            flash(f'Report card for {pet.name} saved.', 'success')

        return redirect(url_for('admin.report_cards'))

    return render_template('admin/report_card_form.html',
                           pet=pet,
                           card_type=card_type,
                           existing=existing,
                           today=today)


@bp.route('/report-cards/history/<int:pet_id>')
@login_required
@admin_required
def report_card_history(pet_id):
    """View all report cards for a pet."""
    from app.models import Pet, ReportCard
    pet   = Pet.query.get_or_404(pet_id)
    cards = ReportCard.query.filter_by(pet_id=pet_id).order_by(ReportCard.card_date.desc()).all()
    return render_template('admin/report_card_history.html', pet=pet, cards=cards)


@bp.route('/report-cards/view/<int:card_id>')
@login_required
@admin_required
def view_report_card(card_id):
    """View a single report card."""
    from app.models import ReportCard
    rc  = ReportCard.query.get_or_404(card_id)
    pet = rc.pet
    return render_template('admin/view_report_card.html', rc=rc, pet=pet)

# ============================================================
# BROADCAST SMS
# ============================================================

@bp.route('/inbox/broadcast', methods=['GET', 'POST'])
@login_required
@admin_required
def sms_broadcast():
    """Send a mass SMS to a selected group of customers."""
    from app.models import SmsMessage
    from datetime import date

    # Build audience options
    today = date.today()

    # All opted-in customers
    opted_in = User.query.filter_by(sms_opt_in=True, is_admin=False, is_active=True).all()

    # Active daycare enrollments (unique owners)
    daycare_owners = (db.session.query(User)
        .join(Pet, Pet.user_id == User.id)
        .join(DaycareEnrollment, DaycareEnrollment.pet_id == Pet.id)
        .filter(DaycareEnrollment.active == True)
        .distinct()
        .all())

    # Current boarding guests (unique owners)
    from app.models import Boarding
    boarding_owners = (db.session.query(User)
        .join(Pet, Pet.user_id == User.id)
        .join(Boarding, Boarding.pet_id == Pet.id)
        .filter(Boarding.status == 'active', Boarding.check_in_date <= today, Boarding.check_out_date >= today)
        .distinct()
        .all())

    if request.method == 'POST':
        audience   = request.form.get('audience')
        message    = request.form.get('message', '').strip()
        confirm    = request.form.get('confirm') == '1'

        if not message:
            flash('Message cannot be empty.', 'danger')
            return redirect(url_for('admin.sms_broadcast'))

        # Resolve recipient list
        if audience == 'opted_in':
            recipients = opted_in
            label      = 'All opted-in customers'
        elif audience == 'daycare':
            recipients = daycare_owners
            label      = 'Active daycare enrollments'
        elif audience == 'boarding':
            recipients = boarding_owners
            label      = 'Current boarding guests'
        else:
            flash('Invalid audience selection.', 'danger')
            return redirect(url_for('admin.sms_broadcast'))

        # Preview step — show who will receive it before sending
        if not confirm:
            return render_template('admin/sms_broadcast.html',
                                   opted_in=opted_in,
                                   daycare_owners=daycare_owners,
                                   boarding_owners=boarding_owners,
                                   preview_recipients=recipients,
                                   preview_message=message,
                                   preview_audience=audience,
                                   preview_label=label)

        # Send step — confirmed, fire messages
        from twilio.rest import Client
        from app.sms_service import _normalize_phone
        account_sid = current_app.config.get('TWILIO_ACCOUNT_SID')
        auth_token  = current_app.config.get('TWILIO_AUTH_TOKEN')
        from_number = current_app.config.get('TWILIO_PHONE_NUMBER')
        client      = Client(account_sid, auth_token)

        sent  = 0
        skipped = 0
        for user in recipients:
            if not user.phone:
                skipped += 1
                continue
            to_e164 = _normalize_phone(user.phone)
            if not to_e164:
                skipped += 1
                continue
            try:
                msg = client.messages.create(body=message, from_=from_number, to=to_e164)
                log = SmsMessage(
                    user_id     = user.id,
                    direction   = 'outbound',
                    from_number = from_number,
                    to_number   = to_e164,
                    body        = message,
                    twilio_sid  = msg.sid,
                    is_read     = True
                )
                db.session.add(log)
                sent += 1
            except Exception as e:
                current_app.logger.error(f'Broadcast SMS failed for user {user.id}: {e}')
                skipped += 1

        db.session.commit()
        try:
            from app.audit_service import audit
            audit('sms.broadcast', 'sms', None, audience,
                  f'Broadcast SMS sent to {audience} — {sent} delivered, {skipped} skipped by {current_user.first_name} {current_user.last_name}')
        except Exception: pass
        flash(f'Broadcast sent! {sent} message(s) delivered, {skipped} skipped (no phone/error).', 'success')
        return redirect(url_for('admin.sms_inbox'))

    return render_template('admin/sms_broadcast.html',
                           opted_in=opted_in,
                           daycare_owners=daycare_owners,
                           boarding_owners=boarding_owners,
                           preview_recipients=None,
                           preview_message=None,
                           preview_audience=None,
                           preview_label=None)


# ============================================================
# KNOWLEDGE BASE
# ============================================================

KB_CATEGORIES = [
    'Getting Started',
    'Daycare',
    'Boarding',
    'Customers',
    'SMS & Messaging',
    'Report Cards',
    'Vaccinations',
    'Payments',
    'Troubleshooting',
]

@bp.route('/kb')
@login_required
@admin_required
def kb_index():
    """Knowledge base home — browse and search articles."""
    from app.models import KnowledgeArticle
    q = request.args.get('q', '').strip()
    category = request.args.get('category', '').strip()

    query = KnowledgeArticle.query

    if q:
        search = f'%{q}%'
        query = query.filter(
            db.or_(
                KnowledgeArticle.title.ilike(search),
                KnowledgeArticle.content.ilike(search)
            )
        )
    if category:
        query = query.filter_by(category=category)

    articles = query.order_by(
        KnowledgeArticle.pinned.desc(),
        KnowledgeArticle.category.asc(),
        KnowledgeArticle.title.asc()
    ).all()

    pinned   = [a for a in articles if a.pinned and not q and not category]
    unpinned = [a for a in articles if not a.pinned or q or category]

    # Group unpinned by category
    from itertools import groupby
    grouped = {}
    for a in sorted(unpinned, key=lambda x: x.category):
        grouped.setdefault(a.category, []).append(a)

    return render_template('admin/kb_index.html',
                           pinned=pinned,
                           grouped=grouped,
                           categories=KB_CATEGORIES,
                           q=q,
                           category=category,
                           total=len(articles))


@bp.route('/kb/article/<int:article_id>')
@login_required
@admin_required
def kb_article(article_id):
    """View a single knowledge base article."""
    from app.models import KnowledgeArticle
    article = KnowledgeArticle.query.get_or_404(article_id)
    # Related articles in same category
    related = (KnowledgeArticle.query
               .filter_by(category=article.category)
               .filter(KnowledgeArticle.id != article_id)
               .order_by(KnowledgeArticle.title.asc())
               .limit(5).all())
    return render_template('admin/kb_article.html',
                           article=article,
                           related=related)


@bp.route('/kb/new', methods=['GET', 'POST'])
@login_required
@admin_required
def kb_new():
    """Create a new knowledge base article."""
    from app.models import KnowledgeArticle
    if request.method == 'POST':
        article = KnowledgeArticle(
            title      = request.form.get('title', '').strip(),
            category   = request.form.get('category', '').strip(),
            content    = request.form.get('content', '').strip(),
            pinned     = request.form.get('pinned') == '1',
            created_by = current_user.id
        )
        db.session.add(article)
        db.session.commit()
        flash(f'Article "{article.title}" created.', 'success')
        return redirect(url_for('admin.kb_article', article_id=article.id))

    return render_template('admin/kb_edit.html',
                           article=None,
                           categories=KB_CATEGORIES)


@bp.route('/kb/article/<int:article_id>/edit', methods=['GET', 'POST'])
@login_required
@admin_required
def kb_edit(article_id):
    """Edit an existing knowledge base article."""
    from app.models import KnowledgeArticle
    from datetime import datetime as dt
    article = KnowledgeArticle.query.get_or_404(article_id)

    if request.method == 'POST':
        article.title    = request.form.get('title', '').strip()
        article.category = request.form.get('category', '').strip()
        article.content  = request.form.get('content', '').strip()
        article.pinned   = request.form.get('pinned') == '1'
        article.updated_at = dt.now()
        db.session.commit()
        flash(f'Article updated.', 'success')
        return redirect(url_for('admin.kb_article', article_id=article.id))

    return render_template('admin/kb_edit.html',
                           article=article,
                           categories=KB_CATEGORIES)


@bp.route('/kb/article/<int:article_id>/delete', methods=['POST'])
@login_required
@admin_required
def kb_delete(article_id):
    """Delete a knowledge base article."""
    from app.models import KnowledgeArticle
    article = KnowledgeArticle.query.get_or_404(article_id)
    title   = article.title
    db.session.delete(article)
    db.session.commit()
    flash(f'Article "{title}" deleted.', 'success')
    return redirect(url_for('admin.kb_index'))


@bp.route('/kb/seed', methods=['POST'])
@login_required
@admin_required
def kb_seed():
    """Seed the knowledge base with runbook content."""
    from app.models import KnowledgeArticle
    if KnowledgeArticle.query.count() > 0:
        flash('Knowledge base already has articles — seed skipped.', 'warning')
        return redirect(url_for('admin.kb_index'))

    articles = [
        # ── Getting Started ──
        dict(category='Getting Started', pinned=True, title='How to Log In',
             content='''<p>Open a browser and go to <strong>rufflife.app</strong>. Enter your email address and password and click Login. You will land on the Admin Dashboard.</p>
<p>If you cannot log in, contact Frances. See the article <em>How to Reset a Customer Password</em> if a customer needs a reset.</p>
<h3>Admin Navigation</h3>
<ul>
<li><strong>Operations</strong> — Daycare Dashboard, Boarding Dashboard, Service Blocks, Report Cards</li>
<li><strong>Reports</strong> — Revenue, attendance, and service summaries</li>
<li><strong>Inbox</strong> — SMS messages from customers (red badge = unread)</li>
<li><strong>Vaccinations</strong> — Pets with expiring records</li>
<li><strong>KB</strong> — This knowledge base</li>
<li><strong>User avatar</strong> — Admin Dashboard and Logout</li>
</ul>
<p><strong>Tip:</strong> Bookmark <strong>rufflife.app/kiosk</strong> on the front-desk tablet for customer self check-in and check-out. No login required.</p>'''),

        dict(category='Getting Started', pinned=False, title='Morning Opening Checklist',
             content='''<p>Complete these steps each morning before the first drop-off.</p>
<ol>
<li>Log in to rufflife.app</li>
<li>Check the <strong>Inbox</strong> for any overnight customer messages — reply to urgent ones.</li>
<li>Open the <strong>Daycare Dashboard</strong> — confirm today\'s expected attendees.</li>
<li>Open the <strong>Boarding Dashboard</strong> — confirm any check-ins or check-outs scheduled for today.</li>
<li>Check <strong>Vaccinations</strong> for any pets expiring today or this week.</li>
<li>Make sure the kiosk tablet is charged and rufflife.app/kiosk is open and ready.</li>
</ol>'''),

        # ── Daycare ──
        dict(category='Daycare', pinned=False, title='Daycare Schedule & Hours',
             content='''<h3>Operating Days & Hours</h3>
<ul>
<li>Daycare operates <strong>Monday through Thursday</strong></li>
<li><strong>Fridays</strong> are reserved for trial days for new students only</li>
<li>Operating hours: <strong>7:00 AM to 3:30 PM</strong></li>
</ul>
<h3>Pickup Policy</h3>
<ul>
<li>Standard pickup: <strong>3:30 PM</strong></li>
<li>Late pickup boarding block: <strong>3:30 PM – 5:00 PM</strong></li>
<li>Pets not picked up by 3:30 PM transition to boarding. Notify the owner via the SMS Inbox.</li>
</ul>'''),

        dict(category='Daycare', pinned=False, title='How to Check In a Daycare Pet (Manual)',
             content='''<p>Use this if the kiosk is unavailable or a customer needs help checking in.</p>
<ol>
<li>Go to <strong>Operations → Daycare Dashboard</strong></li>
<li>Click <strong>Check In</strong> next to the pet\'s name</li>
<li>Confirm the check-in time is correct</li>
</ol>
<h3>If the Kiosk Says Pet Not Found</h3>
<ol>
<li>Verify the owner is spelling their last name exactly as it appears in the system</li>
<li>Check the customer record for typos in the pet name</li>
<li>Verify the enrollment is marked <strong>Active</strong> on the customer profile</li>
<li>If not enrolled, contact Frances before proceeding</li>
</ol>'''),

        dict(category='Daycare', pinned=False, title='End of Day Daycare Checklist',
             content='''<p>Complete these steps before 3:00 PM each daycare day.</p>
<ol>
<li>Go to <strong>Operations → Report Cards</strong></li>
<li>Write a report card for every pet in the Daycare section showing <strong>Pending</strong></li>
<li>Include a photo if possible. Make sure <strong>Send SMS</strong> is ticked</li>
<li>Click <strong>Send Report Card</strong> for each pet — confirm all show green Sent badges</li>
<li>At 3:30 PM — begin checkout. Pets not collected by 3:30 PM transition to boarding</li>
<li>For any late pickup pets — send a quick SMS from the Inbox notifying the owner</li>
<li>Collect payment via JIM and log it on the customer\'s profile</li>
</ol>'''),

        # ── Boarding ──
        dict(category='Boarding', pinned=False, title='How to Check In a Boarding Guest',
             content='''<ol>
<li>Look up the customer at <strong>rufflife.app/admin/customers</strong></li>
<li>Open their profile and click <strong>View</strong> next to the pet</li>
<li>Verify all vaccinations are current (green badges). If any are expired — do not admit.</li>
<li>Go to <strong>Operations → Boarding Dashboard</strong> and find the reservation</li>
<li>Confirm status is <strong>Confirmed</strong>. If Pending, click Confirm first</li>
<li>Click <strong>Check In</strong> to record arrival</li>
<li>Note any feeding instructions, medications, or special requirements</li>
</ol>
<p><strong>⚠️ Do not admit pets with expired vaccinations. Contact Frances if a customer disputes this.</strong></p>'''),

        dict(category='Boarding', pinned=False, title='How to Check Out a Boarding Guest',
             content='''<ol>
<li>Go to <strong>Operations → Boarding Dashboard</strong></li>
<li>Find the pet in the active boarding list and click <strong>Check Out</strong></li>
<li>Provide the owner with a verbal summary of their pet\'s stay</li>
<li>Collect payment via JIM</li>
<li>Log the payment on the customer\'s profile under <strong>Payment History → + Add Payment</strong></li>
</ol>'''),

        dict(category='Boarding', pinned=False, title='How to Confirm or Cancel an Appointment',
             content='''<ol>
<li>Go to <strong>Admin Dashboard → Appointments</strong></li>
<li>Find the pending appointment</li>
<li>Click <strong>Confirm</strong> — the customer automatically receives a confirmation SMS</li>
<li>To cancel, click <strong>Cancel</strong> — the customer receives a cancellation SMS</li>
</ol>
<p><strong>Always confirm or cancel appointments within 24 hours of the request.</strong></p>'''),

        # ── Customers ──
        dict(category='Customers', pinned=False, title='How to Find and Edit a Customer',
             content='''<h3>Finding a Customer</h3>
<ol>
<li>Go to <strong>rufflife.app/admin/customers</strong></li>
<li>Use Ctrl+F to search by name, or scroll the list</li>
<li>Click <strong>View</strong> to open their profile</li>
</ol>
<h3>Editing a Customer</h3>
<ol>
<li>Open the customer profile</li>
<li>Click the <strong>Edit</strong> button in the Customer Info card header</li>
<li>Update the relevant fields and click <strong>Save Changes</strong></li>
</ol>
<p><strong>Note:</strong> Phone numbers must be in standard format (e.g. 9125551234) for SMS to work correctly.</p>'''),

        dict(category='Customers', pinned=False, title='How to Reset a Customer Password',
             content='''<ol>
<li>Open the customer profile</li>
<li>Click the <strong>Edit</strong> button in the Customer Info card header</li>
<li>In the modal footer, click <strong>Reset Password</strong> (yellow button)</li>
<li>Type a temporary password — minimum 6 characters</li>
<li>Click <strong>Reset Password</strong> to confirm</li>
<li><strong>Call the customer</strong> to share their temporary password — never send it via SMS or email</li>
<li>Advise them to update their password after logging in</li>
</ol>'''),

        dict(category='Customers', pinned=False, title='How to View Pet Records and Vaccinations',
             content='''<ol>
<li>Open the customer profile</li>
<li>Scroll to the <strong>Pets</strong> section</li>
<li>Click <strong>View</strong> next to the pet to open the pet detail page</li>
<li>Vaccination Records are shown with color-coded status badges:
  <ul>
    <li>🟢 <strong>Green</strong> — Current</li>
    <li>🟡 <strong>Yellow</strong> — Expiring within 30 days</li>
    <li>🔴 <strong>Red</strong> — Expiring within 7 days or expired</li>
  </ul>
</li>
</ol>'''),

        # ── SMS & Messaging ──
        dict(category='SMS & Messaging', pinned=True, title='⚠️ IMPORTANT — Always Reply Through the App',
             content='''<p>When a customer replies to a Ruff Life SMS, Ashley and Frances both receive a forwarded alert on their personal phones. <strong>This forwarding is for visibility only.</strong></p>
<h3>🚫 Do NOT reply from your personal phone</h3>
<p>The forwarded message comes from the Twilio system number, not the customer directly. If you reply from your personal phone:</p>
<ul>
<li>Your reply will NOT reach the customer via the Ruff Life number</li>
<li>No record will be kept in the app</li>
<li>The customer will receive a message from an unknown number</li>
</ul>
<h3>✅ Always reply from the Inbox</h3>
<ol>
<li>Go to <strong>rufflife.app/admin/inbox</strong></li>
<li>Find the customer conversation</li>
<li>Type your reply and click <strong>Send</strong></li>
</ol>'''),

        dict(category='SMS & Messaging', pinned=False, title='How to Reply to a Customer SMS',
             content='''<ol>
<li>Click <strong>Inbox</strong> in the top navigation bar</li>
<li>The red badge shows how many unread messages are waiting</li>
<li>Click the yellow <strong>Reply</strong> button or the customer\'s name</li>
<li>The left panel shows customer details, pets, and emergency contact</li>
<li>Type your message in the reply box and click <strong>Send</strong></li>
</ol>
<p>All replies are logged and visible to all admin staff.</p>'''),

        dict(category='SMS & Messaging', pinned=False, title='How to Send a Broadcast SMS',
             content='''<p>A broadcast sends the same SMS to all members of a selected group at once.</p>
<ol>
<li>Click <strong>Inbox</strong> in the top navigation bar</li>
<li>Click the yellow <strong>Broadcast SMS</strong> button in the top right</li>
<li>Select your audience:
  <ul>
    <li><strong>All Opted-In Customers</strong> — everyone with SMS enabled</li>
    <li><strong>Active Daycare Enrollments</strong> — daycare pet owners</li>
    <li><strong>Current Boarding Guests</strong> — owners of pets currently boarding</li>
  </ul>
</li>
<li>Type your message (keep under 160 characters if possible)</li>
<li>Click <strong>Preview Broadcast</strong> — review the full recipient list</li>
<li>Click <strong>Send</strong> to confirm — messages cannot be undone</li>
</ol>'''),

        # ── Report Cards ──
        dict(category='Report Cards', pinned=False, title='How to Send a Daycare Report Card',
             content='''<ol>
<li>Go to <strong>Operations → Report Cards</strong></li>
<li>Find the pet in the <strong>Daycare</strong> section showing <strong>Pending</strong></li>
<li>Click <strong>Write Card</strong></li>
<li>Select: <strong>Mood</strong>, <strong>Energy Level</strong>, <strong>Played Well With Others</strong>, <strong>Stayed Hydrated</strong></li>
<li>Optionally upload a photo and add a staff note</li>
<li>Make sure <strong>Send SMS</strong> is ticked</li>
<li>Click <strong>Send Report Card</strong></li>
</ol>
<p>The owner receives an SMS with a clickable link to view the card. No login required.</p>
<p><strong>Best practice:</strong> Aim to send all daycare cards before 3:00 PM so owners have them before pickup.</p>'''),

        dict(category='Report Cards', pinned=False, title='How to Send a Boarding Report Card',
             content='''<p>Boarding cards include more detail than daycare cards — fill these out once per day for each boarding guest.</p>
<ol>
<li>Go to <strong>Operations → Report Cards</strong></li>
<li>Find the pet in the <strong>Boarding</strong> section</li>
<li>Click <strong>Write Card</strong></li>
<li>Complete all fields: Mood, Energy, Played Well, Hydrated, <strong>Appetite</strong>, <strong>Sleep</strong>, <strong>Temperament</strong>, <strong>Medications Given</strong>, <strong>Bathroom Habits</strong></li>
<li>Add a photo and a personal staff note — boarding owners especially appreciate these</li>
<li>Click <strong>Send Report Card</strong></li>
</ol>
<p><strong>Best practice:</strong> Send boarding report cards around midday.</p>'''),

        # ── Vaccinations ──
        dict(category='Vaccinations', pinned=False, title='How to Update an Expiring Vaccine Record',
             content='''<ol>
<li>Receive the updated vaccination certificate from the customer</li>
<li>Go to <strong>rufflife.app/admin/customers</strong> and open the customer\'s profile</li>
<li>Click <strong>View</strong> next to the pet</li>
<li>Find the expired or expiring record in the <strong>Vaccination Records</strong> section</li>
<li>Click the <strong>pencil icon</strong> on the record</li>
<li>Update the <strong>Date Given</strong> and <strong>Expiration Date</strong> from the certificate</li>
<li>Add the vet name and clinic if shown on the certificate</li>
<li>Click <strong>Save Changes</strong> — the badge will update to green</li>
</ol>'''),

        dict(category='Vaccinations', pinned=False, title='Vaccination Expiration Alerts',
             content='''<p>The system checks for expiring vaccinations daily at <strong>8:00 AM</strong> and sends SMS alerts to staff and pet owners automatically.</p>
<h3>To run a manual check:</h3>
<ol>
<li>Click <strong>Vaccinations</strong> in the top navigation bar</li>
<li>Review the report — red rows expire within 7 days, yellow within 30 days</li>
<li>Click <strong>Run Check Now</strong> to send alerts immediately</li>
</ol>
<h3>Required Vaccinations</h3>
<ul>
<li>Rabies</li>
<li>DHPP (Distemper/Parvo)</li>
<li>Bordetella (Kennel Cough)</li>
</ul>
<p><strong>Do not admit pets with expired vaccinations.</strong></p>'''),

        # ── Payments ──
        dict(category='Payments', pinned=False, title='How to Log a Payment',
             content='''<ol>
<li>Collect payment via <strong>JIM</strong> (tap to pay on your phone)</li>
<li>Open the customer profile at <strong>rufflife.app/admin/customers</strong></li>
<li>Scroll to <strong>Payment History</strong> and click <strong>+ Add Payment</strong></li>
<li>Enter the amount, service type, and date</li>
<li>Click <strong>Save</strong></li>
</ol>
<p><strong>Always log the payment immediately after collecting it.</strong> This is the source of truth for all revenue reports.</p>'''),

        # ── Troubleshooting ──
        dict(category='Troubleshooting', pinned=False, title='Kiosk Says Pet Not Found',
             content='''<ol>
<li>Ask the owner to confirm they are spelling their <strong>last name</strong> exactly as it appears in the system</li>
<li>Check the customer record for typos in the pet name</li>
<li>Verify the daycare enrollment is marked <strong>Active</strong> on the customer profile</li>
<li>If the enrollment is inactive or missing, contact Frances</li>
</ol>'''),

        dict(category='Troubleshooting', pinned=False, title='Customer Not Receiving SMS Messages',
             content='''<ol>
<li>Check that the customer has a <strong>phone number</strong> on file in their profile</li>
<li>Automated messages require <strong>SMS opt-in</strong> — check the customer profile. Staff-initiated messages (inbox replies, report cards) send regardless of opt-in</li>
<li>Check the Twilio account balance — messages will fail if the account is out of funds</li>
<li>If messages are still failing after the above, contact Frances</li>
</ol>'''),

        dict(category='Troubleshooting', pinned=False, title='App Is Down or Showing Errors',
             content='''<ol>
<li>Note the <strong>error message</strong> and the <strong>page URL</strong></li>
<li>Try a hard refresh: <strong>Ctrl + Shift + R</strong></li>
<li>If the issue persists, contact Frances immediately with the error details</li>
</ol>'''),

        dict(category='Troubleshooting', pinned=False, title='Received Forwarded SMS But Cannot Find the Message',
             content='''<p>The forwarded alert is a notification only — the customer texted the Ruff Life number, not your personal number.</p>
<ol>
<li>Go to <strong>rufflife.app/admin/inbox</strong> to view and reply</li>
<li>If the customer appears under <strong>Unknown Senders</strong>, their phone number may not match their account — check and update their profile</li>
</ol>
<p><strong>Remember:</strong> Never reply from your personal phone. Always use the Inbox.</p>'''),

        # ── Boarding request workflow ──
        dict(category='Boarding', pinned=False, title='How to Review and Approve a Boarding Request',
             content='''<p>When a customer books a boarding appointment through the customer portal, it lands in the <strong>Pending Boarding Requests</strong> section at the top of the Boarding Dashboard for staff to review before a reservation is created.</p>

<h3>Reviewing a Request</h3>
<ol>
<li>Go to <strong>Operations → Boarding Dashboard</strong></li>
<li>Check the <strong>Pending Boarding Requests</strong> section at the top — a yellow banner with a count badge appears when requests are waiting</li>
<li>The table shows the pet name, owner, requested date, and owner phone number</li>
</ol>

<h3>Approving a Request</h3>
<ol>
<li>Click the green <strong>Approve</strong> button next to the request</li>
<li>A modal opens pre-filled with the customer\'s requested check-in date</li>
<li>Confirm or adjust the <strong>Check-In Date</strong> and <strong>Check-In Time</strong></li>
<li>Set the <strong>Check-Out Date</strong> and <strong>Check-Out Time</strong></li>
<li>Add any special notes — feeding instructions, medications, etc.</li>
<li>Click <strong>Approve &amp; Create Reservation</strong></li>
</ol>
<p>On approval, a boarding reservation is created automatically and the customer receives a confirmation SMS immediately.</p>

<h3>Rejecting a Request</h3>
<ol>
<li>Click the red <strong>Reject</strong> button next to the request</li>
<li>Optionally enter a reason (e.g. "Fully booked for those dates") — this is included in the SMS to the customer</li>
<li>Click <strong>Reject Request</strong></li>
</ol>
<p>The customer receives a cancellation SMS with the reason if one was provided.</p>

<h3>Boarding Calendar</h3>
<p>Below the pending requests section, a 2-month calendar shows blue circles on days when boarding guests are staying. Hover over a blue date to see which pets are checked in on that day. Use this to check availability before approving date ranges.</p>

<p><strong>Note:</strong> Always check vaccination records are current before approving a boarding request — open the customer profile and click View next to the pet to verify.</p>'''),

        # ── SMS reference article ──
        dict(category='SMS & Messaging', pinned=False, title='Complete Guide — Which Events Send SMS to Customers',
             content='''<p>This article lists every event in the app that triggers an automatic SMS to a customer, and which events require staff action to send.</p>

<h3>Automatic SMS — No Staff Action Required</h3>
<p>These messages send automatically when the event occurs:</p>

<table style="width:100%;border-collapse:collapse;font-size:0.9rem;">
<thead>
<tr style="background:#1a1a2e;color:white;">
<th style="padding:8px 12px;text-align:left;">Event</th>
<th style="padding:8px 12px;text-align:left;">Message Sent</th>
<th style="padding:8px 12px;text-align:left;">Requires Opt-In?</th>
</tr>
</thead>
<tbody>
<tr style="background:#f8f9fa;">
<td style="padding:8px 12px;border-bottom:1px solid #dee2e6;">Customer registers &amp; opts in to SMS</td>
<td style="padding:8px 12px;border-bottom:1px solid #dee2e6;">Opt-in confirmation + Welcome message</td>
<td style="padding:8px 12px;border-bottom:1px solid #dee2e6;">Yes</td>
</tr>
<tr>
<td style="padding:8px 12px;border-bottom:1px solid #dee2e6;">Appointment confirmed (staff approves)</td>
<td style="padding:8px 12px;border-bottom:1px solid #dee2e6;">Confirmation with pet name, service, date, and time</td>
<td style="padding:8px 12px;border-bottom:1px solid #dee2e6;">Yes</td>
</tr>
<tr style="background:#f8f9fa;">
<td style="padding:8px 12px;border-bottom:1px solid #dee2e6;">Appointment cancelled (staff cancels)</td>
<td style="padding:8px 12px;border-bottom:1px solid #dee2e6;">Cancellation notice with optional reason</td>
<td style="padding:8px 12px;border-bottom:1px solid #dee2e6;">Yes</td>
</tr>
<tr>
<td style="padding:8px 12px;border-bottom:1px solid #dee2e6;">Boarding request approved</td>
<td style="padding:8px 12px;border-bottom:1px solid #dee2e6;">Confirmation SMS with dates</td>
<td style="padding:8px 12px;border-bottom:1px solid #dee2e6;">Yes</td>
</tr>
<tr style="background:#f8f9fa;">
<td style="padding:8px 12px;border-bottom:1px solid #dee2e6;">Boarding request rejected</td>
<td style="padding:8px 12px;border-bottom:1px solid #dee2e6;">Cancellation SMS with optional reason</td>
<td style="padding:8px 12px;border-bottom:1px solid #dee2e6;">Yes</td>
</tr>
<tr>
<td style="padding:8px 12px;border-bottom:1px solid #dee2e6;">Appointment reminder (daily at 8 AM)</td>
<td style="padding:8px 12px;border-bottom:1px solid #dee2e6;">24-hour reminder for next day\'s appointments</td>
<td style="padding:8px 12px;border-bottom:1px solid #dee2e6;">Yes</td>
</tr>
<tr style="background:#f8f9fa;">
<td style="padding:8px 12px;border-bottom:1px solid #dee2e6;">Daycare check-in (kiosk or admin)</td>
<td style="padding:8px 12px;border-bottom:1px solid #dee2e6;">Check-in alert with time</td>
<td style="padding:8px 12px;border-bottom:1px solid #dee2e6;">Yes</td>
</tr>
<tr>
<td style="padding:8px 12px;border-bottom:1px solid #dee2e6;">Daycare check-out (kiosk or admin)</td>
<td style="padding:8px 12px;border-bottom:1px solid #dee2e6;">Check-out alert with time</td>
<td style="padding:8px 12px;border-bottom:1px solid #dee2e6;">Yes</td>
</tr>
<tr style="background:#f8f9fa;">
<td style="padding:8px 12px;border-bottom:1px solid #dee2e6;">Daycare waitlist form submitted</td>
<td style="padding:8px 12px;border-bottom:1px solid #dee2e6;">Waitlist confirmation with selected days</td>
<td style="padding:8px 12px;border-bottom:1px solid #dee2e6;">No — sent to all submissions</td>
</tr>
<tr>
<td style="padding:8px 12px;border-bottom:1px solid #dee2e6;">Vaccination expiring (daily at 8 AM)</td>
<td style="padding:8px 12px;border-bottom:1px solid #dee2e6;">Expiration alert with vaccine name and date</td>
<td style="padding:8px 12px;border-bottom:1px solid #dee2e6;">Yes</td>
</tr>
<tr style="background:#f8f9fa;">
<td style="padding:8px 12px;border-bottom:1px solid #dee2e6;">Customer replies to any SMS</td>
<td style="padding:8px 12px;border-bottom:1px solid #dee2e6;">Forwarded alert to Ashley &amp; Frances (not to customer)</td>
<td style="padding:8px 12px;border-bottom:1px solid #dee2e6;">N/A</td>
</tr>
</tbody>
</table>

<h3>Staff-Initiated SMS — Requires Staff Action</h3>
<p>These messages only send when a staff member explicitly triggers them:</p>

<table style="width:100%;border-collapse:collapse;font-size:0.9rem;margin-top:8px;">
<thead>
<tr style="background:#1a1a2e;color:white;">
<th style="padding:8px 12px;text-align:left;">Action</th>
<th style="padding:8px 12px;text-align:left;">How to Send</th>
<th style="padding:8px 12px;text-align:left;">Bypasses Opt-In?</th>
</tr>
</thead>
<tbody>
<tr style="background:#f8f9fa;">
<td style="padding:8px 12px;border-bottom:1px solid #dee2e6;">Report card sent</td>
<td style="padding:8px 12px;border-bottom:1px solid #dee2e6;">Operations → Report Cards → Send Report Card</td>
<td style="padding:8px 12px;border-bottom:1px solid #dee2e6;">Yes — always sends</td>
</tr>
<tr>
<td style="padding:8px 12px;border-bottom:1px solid #dee2e6;">Incident notification</td>
<td style="padding:8px 12px;border-bottom:1px solid #dee2e6;">Check "Notify Owner" when logging an incident</td>
<td style="padding:8px 12px;border-bottom:1px solid #dee2e6;">Yes — always sends</td>
</tr>
<tr style="background:#f8f9fa;">
<td style="padding:8px 12px;border-bottom:1px solid #dee2e6;">Direct inbox reply</td>
<td style="padding:8px 12px;border-bottom:1px solid #dee2e6;">Inbox → open conversation → type and Send</td>
<td style="padding:8px 12px;border-bottom:1px solid #dee2e6;">Yes — always sends</td>
</tr>
<tr>
<td style="padding:8px 12px;border-bottom:1px solid #dee2e6;">Broadcast SMS</td>
<td style="padding:8px 12px;border-bottom:1px solid #dee2e6;">Inbox → Broadcast SMS → select audience → Preview → Send</td>
<td style="padding:8px 12px;border-bottom:1px solid #dee2e6;">No — only opted-in customers</td>
</tr>
<tr style="background:#f8f9fa;">
<td style="padding:8px 12px;border-bottom:1px solid #dee2e6;">Vaccination alert (manual)</td>
<td style="padding:8px 12px;border-bottom:1px solid #dee2e6;">Vaccinations → Run Check Now</td>
<td style="padding:8px 12px;border-bottom:1px solid #dee2e6;">Yes — always sends</td>
</tr>
</tbody>
</table>

<h3>SMS Opt-In Explained</h3>
<p>Customers opt in to SMS during registration by checking the consent box. Staff can view and update a customer\'s opt-in status from their profile (Edit button) or from the left panel in any inbox conversation.</p>
<p><strong>Automated messages</strong> (confirmations, reminders, check-in/out alerts) only send to opted-in customers.</p>
<p><strong>Staff-initiated messages</strong> (inbox replies, report cards, incidents) send regardless of opt-in status — these are considered direct service communications.</p>'''),

        # ── Satisfaction Surveys ──
        dict(category='Getting Started', pinned=False, title='Customer Satisfaction Surveys — Overview',
             content='''<p>Ruff Life Retreat automatically collects customer feedback through short satisfaction surveys sent via SMS. Surveys help identify happy customers, catch issues early, and track service quality over time.</p>

<h3>How Surveys Are Triggered</h3>
<p>Surveys fire automatically in two situations, and can also be sent manually at any time:</p>

<table style="width:100%;border-collapse:collapse;font-size:0.9rem;">
<thead>
<tr style="background:#1a1a2e;color:white;">
<th style="padding:8px 12px;">Trigger</th>
<th style="padding:8px 12px;">When It Fires</th>
<th style="padding:8px 12px;">Automated?</th>
</tr>
</thead>
<tbody>
<tr style="background:#f8f9fa;">
<td style="padding:8px 12px;border-bottom:1px solid #dee2e6;">Boarding checkout</td>
<td style="padding:8px 12px;border-bottom:1px solid #dee2e6;">When staff marks a boarding reservation as completed</td>
<td style="padding:8px 12px;border-bottom:1px solid #dee2e6;">Yes — automatic</td>
</tr>
<tr>
<td style="padding:8px 12px;border-bottom:1px solid #dee2e6;">Daycare milestone</td>
<td style="padding:8px 12px;border-bottom:1px solid #dee2e6;">After every 5th daycare visit for a customer</td>
<td style="padding:8px 12px;border-bottom:1px solid #dee2e6;">Yes — automatic</td>
</tr>
<tr style="background:#f8f9fa;">
<td style="padding:8px 12px;border-bottom:1px solid #dee2e6;">Weekly unsurveyed batch</td>
<td style="padding:8px 12px;border-bottom:1px solid #dee2e6;">Every Sunday — sends to customers not surveyed in 90+ days</td>
<td style="padding:8px 12px;border-bottom:1px solid #dee2e6;">Yes — scheduled</td>
</tr>
<tr>
<td style="padding:8px 12px;">Manual send</td>
<td style="padding:8px 12px;">Staff clicks Send Survey on a customer profile</td>
<td style="padding:8px 12px;">No — staff action</td>
</tr>
</tbody>
</table>

<h3>What the Customer Receives</h3>
<p>The customer gets an SMS: <em>"Hi Sarah! How was your recent Boarding experience at Ruff Life Retreat? We'd love your feedback: https://rufflife.app/survey/[link]"</em></p>
<p>The link opens a mobile-friendly form with four questions — no login required. After submitting, they see a thank you page.</p>

<h3>What Staff Sees</h3>
<p>Go to <strong>Operations → Satisfaction</strong> to view the full dashboard including average ratings, response history, low-rating alerts, and customers due for follow-up.</p>'''),

        dict(category='Getting Started', pinned=False, title='How to View and Act on Survey Results',
             content='''<h3>Accessing the Dashboard</h3>
<ol>
<li>Click <strong>Operations</strong> in the top navigation bar</li>
<li>Select <strong>Satisfaction</strong> from the dropdown</li>
</ol>

<h3>Dashboard Sections</h3>
<ul>
<li><strong>Stats row</strong> — Overall rating, Communication rating, Net Promoter Score, and total responses at a glance</li>
<li><strong>Rating Breakdown</strong> — Bar chart showing how many 1, 2, 3, 4, and 5 star ratings you have received</li>
<li><strong>By Service</strong> — Average rating broken down by Boarding, Daycare, Grooming</li>
<li><strong>Low Rating Alerts</strong> — Any 1 or 2 star responses appear here in red for immediate follow-up</li>
<li><strong>Recent Responses</strong> — All submitted surveys with ratings, recommendation status, and customer comments</li>
<li><strong>Not Surveyed in 90+ Days</strong> — Customers overdue for follow-up with a quick Send button</li>
</ul>

<h3>Following Up on Low Ratings</h3>
<ol>
<li>Open the low rating alert in the Satisfaction dashboard</li>
<li>Click <strong>View Customer</strong> to open their profile</li>
<li>Contact the customer directly by phone — do not respond via SMS for complaints</li>
<li>Discuss what happened and how you can make it right</li>
<li>Frances should handle all 1-star follow-up calls personally</li>
</ol>

<h3>Manually Sending a Survey</h3>
<ol>
<li>Open the customer profile at rufflife.app/admin/customers</li>
<li>Click the yellow <strong>Survey</strong> button in the Customer Info card header</li>
<li>Select the service type (Boarding, Daycare, Grooming, or General)</li>
<li>Click <strong>Send Survey</strong></li>
</ol>'''),

        # ── Automated Schedules ──
        dict(category='Getting Started', pinned=True, title='Complete Guide — What Runs Automatically',
             content='''<p>This article documents every automated process in the Ruff Life Retreat app — what runs, when it runs, and what it does. No staff action is needed for any of these unless noted.</p>

<h3>Daily Scheduled Tasks (Windows Task Scheduler)</h3>
<p>These run every day via Windows Task Scheduler on the production server:</p>

<table style="width:100%;border-collapse:collapse;font-size:0.9rem;">
<thead>
<tr style="background:#1a1a2e;color:white;">
<th style="padding:8px 12px;">Task</th>
<th style="padding:8px 12px;">Time</th>
<th style="padding:8px 12px;">What It Does</th>
<th style="padding:8px 12px;">Log File</th>
</tr>
</thead>
<tbody>
<tr style="background:#f8f9fa;">
<td style="padding:8px 12px;border-bottom:1px solid #dee2e6;">Vaccination Alerts</td>
<td style="padding:8px 12px;border-bottom:1px solid #dee2e6;">8:00 AM daily</td>
<td style="padding:8px 12px;border-bottom:1px solid #dee2e6;">Checks all vaccination records. Sends SMS to staff and pet owners for any expiring within 7 or 30 days.</td>
<td style="padding:8px 12px;border-bottom:1px solid #dee2e6;">vaccination_alerts.log</td>
</tr>
<tr>
<td style="padding:8px 12px;border-bottom:1px solid #dee2e6;">Appointment Reminders</td>
<td style="padding:8px 12px;border-bottom:1px solid #dee2e6;">8:00 AM daily</td>
<td style="padding:8px 12px;border-bottom:1px solid #dee2e6;">Sends a 24-hour reminder SMS to customers with appointments the following day.</td>
<td style="padding:8px 12px;border-bottom:1px solid #dee2e6;">appointment_reminders.log</td>
</tr>
</tbody>
</table>

<h3>Weekly Scheduled Task</h3>
<table style="width:100%;border-collapse:collapse;font-size:0.9rem;margin-top:8px;">
<thead>
<tr style="background:#1a1a2e;color:white;">
<th style="padding:8px 12px;">Task</th>
<th style="padding:8px 12px;">Time</th>
<th style="padding:8px 12px;">What It Does</th>
<th style="padding:8px 12px;">Log File</th>
</tr>
</thead>
<tbody>
<tr style="background:#f8f9fa;">
<td style="padding:8px 12px;">Survey Follow-Up</td>
<td style="padding:8px 12px;">Sunday 10:00 AM</td>
<td style="padding:8px 12px;">Sends satisfaction surveys to all customers who have not been surveyed in the past 90 days and have a phone number on file.</td>
<td style="padding:8px 12px;">survey_batch.log</td>
</tr>
</tbody>
</table>

<h3>Event-Driven Automations (No Schedule Needed)</h3>
<p>These fire automatically when a specific action occurs in the app:</p>

<table style="width:100%;border-collapse:collapse;font-size:0.9rem;margin-top:8px;">
<thead>
<tr style="background:#1a1a2e;color:white;">
<th style="padding:8px 12px;">Event</th>
<th style="padding:8px 12px;">Automatic Action</th>
</tr>
</thead>
<tbody>
<tr style="background:#f8f9fa;"><td style="padding:8px 12px;border-bottom:1px solid #dee2e6;">Customer registers</td><td style="padding:8px 12px;border-bottom:1px solid #dee2e6;">Welcome email + welcome SMS (if opted in)</td></tr>
<tr><td style="padding:8px 12px;border-bottom:1px solid #dee2e6;">Appointment confirmed</td><td style="padding:8px 12px;border-bottom:1px solid #dee2e6;">Confirmation SMS to customer</td></tr>
<tr style="background:#f8f9fa;"><td style="padding:8px 12px;border-bottom:1px solid #dee2e6;">Appointment cancelled</td><td style="padding:8px 12px;border-bottom:1px solid #dee2e6;">Cancellation SMS to customer</td></tr>
<tr><td style="padding:8px 12px;border-bottom:1px solid #dee2e6;">Boarding request approved</td><td style="padding:8px 12px;border-bottom:1px solid #dee2e6;">Confirmation SMS + reservation created</td></tr>
<tr style="background:#f8f9fa;"><td style="padding:8px 12px;border-bottom:1px solid #dee2e6;">Boarding checkout completed</td><td style="padding:8px 12px;border-bottom:1px solid #dee2e6;">Satisfaction survey SMS sent to owner</td></tr>
<tr><td style="padding:8px 12px;border-bottom:1px solid #dee2e6;">Daycare check-in (kiosk)</td><td style="padding:8px 12px;border-bottom:1px solid #dee2e6;">Check-in SMS to owner</td></tr>
<tr style="background:#f8f9fa;"><td style="padding:8px 12px;border-bottom:1px solid #dee2e6;">Daycare check-out (kiosk)</td><td style="padding:8px 12px;border-bottom:1px solid #dee2e6;">Check-out SMS + milestone survey check</td></tr>
<tr><td style="padding:8px 12px;border-bottom:1px solid #dee2e6;">Every 5th daycare visit</td><td style="padding:8px 12px;border-bottom:1px solid #dee2e6;">Satisfaction survey SMS sent to owner</td></tr>
<tr style="background:#f8f9fa;"><td style="padding:8px 12px;border-bottom:1px solid #dee2e6;">Waitlist form submitted</td><td style="padding:8px 12px;border-bottom:1px solid #dee2e6;">Waitlist confirmation email + SMS</td></tr>
<tr><td style="padding:8px 12px;border-bottom:1px solid #dee2e6;">Incident logged (notify on)</td><td style="padding:8px 12px;border-bottom:1px solid #dee2e6;">Incident notification SMS to owner</td></tr>
<tr style="background:#f8f9fa;"><td style="padding:8px 12px;border-bottom:1px solid #dee2e6;">Customer replies to SMS</td><td style="padding:8px 12px;border-bottom:1px solid #dee2e6;">Forwarded alert to Ashley &amp; Frances</td></tr>
<tr><td style="padding:8px 12px;">Report card sent</td><td style="padding:8px 12px;">SMS with link to customer (staff-triggered)</td></tr>
</tbody>
</table>

<h3>Checking Scheduled Task Health</h3>
<p>To verify the daily tasks are running correctly, check the log files at:</p>
<ul>
<li><code>C:/RuffLifeRetreat/logs/vaccination_alerts.log</code></li>
<li><code>C:/RuffLifeRetreat/logs/appointment_reminders.log</code></li>
<li><code>C:/RuffLifeRetreat/logs/survey_batch.log</code></li>
</ul>
<p>Or open <strong>Windows Task Scheduler</strong> and check the Last Run Time and Last Run Result for each task. A result of 0 means success.</p>
<p>If a scheduled task hasn\'t run or shows an error, contact Frances.</p>'''),
    ]

    for a in articles:
        db.session.add(KnowledgeArticle(
            title      = a['title'],
            category   = a['category'],
            content    = a['content'],
            pinned     = a.get('pinned', False),
            created_by = current_user.id
        ))
    db.session.commit()
    flash(f'Knowledge base seeded with {len(articles)} articles!', 'success')
    return redirect(url_for('admin.kb_index'))


# ============================================================
# BOARDING APPOINTMENT APPROVAL
# ============================================================

@bp.route('/boarding/approve/<int:appt_id>', methods=['POST'])
@login_required
@admin_required
def approve_boarding_request(appt_id):
    """
    Approve a pending boarding appointment request.
    Creates a Boarding record and confirms the appointment.
    """
    from app.models import Appointment
    from app.sms_service import send_appointment_confirmed_sms

    appt = Appointment.query.get_or_404(appt_id)

    # Get check-in/out dates and times from form (staff fills these in on approval)
    check_in_date_str  = request.form.get('check_in_date')
    check_in_time      = request.form.get('check_in_time', '08:00')
    check_out_date_str = request.form.get('check_out_date')
    check_out_time     = request.form.get('check_out_time', '17:00')
    special_notes      = request.form.get('special_notes', '')
    kennel_number      = request.form.get('kennel_number', '').strip() or None
    kennel_type        = request.form.get('kennel_type', 'kennel')

    if not check_in_date_str or not check_out_date_str:
        flash('Check-in and check-out dates are required to approve.', 'danger')
        return redirect(url_for('admin.boarding_dashboard'))

    try:
        check_in_date  = datetime.strptime(check_in_date_str, '%Y-%m-%d').date()
        check_out_date = datetime.strptime(check_out_date_str, '%Y-%m-%d').date()
    except ValueError:
        flash('Invalid date format.', 'danger')
        return redirect(url_for('admin.boarding_dashboard'))

    # Conflict check — prevent double-booking the same pet
    conflict = _check_boarding_conflict(appt.pet_id, check_in_date, check_out_date)
    if conflict:
        if appt.needs_reapproval:
            # Customer edited an existing confirmed booking — silently cancel the
            # old boarding so the updated one can be created without a cancel SMS.
            conflict.status = 'cancelled'
            db.session.flush()
        else:
            flash(
                f'{appt.pet.name} already has an active boarding reservation from '
                f'{conflict.check_in_date.strftime("%b %d")} to '
                f'{conflict.check_out_date.strftime("%b %d, %Y")}. '
                f'Adjust the dates or complete the existing reservation before approving.',
                'danger'
            )
            return redirect(url_for('admin.boarding_dashboard'))

    # Create Boarding record
    booking = Boarding(
        pet_id          = appt.pet_id,
        user_id         = appt.user_id,
        check_in_date   = check_in_date,
        check_in_time   = check_in_time,
        check_out_date  = check_out_date,
        check_out_time  = check_out_time,
        special_notes   = special_notes,
        kennel_number   = kennel_number,
        kennel_type     = kennel_type,
        status          = 'active',
        booking_number  = _next_board_number()
    )
    db.session.add(booking)

    # Confirm the appointment
    appt.status = 'confirmed'
    db.session.commit()

    # Notify customer via SMS — direct Twilio call bypasses opt-in check
    try:
        from app.sms_service import _normalize_phone
        from app.models import SmsMessage
        from twilio.rest import Client
        owner       = appt.user
        to_e164     = _normalize_phone(owner.phone) if owner and owner.phone else None
        from_number = current_app.config.get('TWILIO_PHONE_NUMBER')
        if to_e164:
            def _fmt_t(t):
                try:
                    from datetime import datetime as _dt
                    return _dt.strptime(str(t)[:5], '%H:%M').strftime('%I:%M %p').lstrip('0')
                except Exception:
                    return str(t)
            if appt.needs_reapproval:
                body = (
                    f"Hi {owner.first_name}, your boarding reservation for "
                    f"{appt.pet.name} has been updated. "
                    f"Ref: {booking.booking_number}. "
                    f"Check-in: {check_in_date.strftime('%a, %b %d')} at {_fmt_t(check_in_time)}. "
                    f"Check-out: {check_out_date.strftime('%a, %b %d')} at {_fmt_t(check_out_time)}. "
                    f"Questions? Reply to this message. \u2014 Ruff Life Retreat"
                )
            else:
                body = (
                    f"\u2705 Great news, {owner.first_name}! Your boarding request for "
                    f"{appt.pet.name} has been approved. "
                    f"Ref: {booking.booking_number}. "
                    f"Check-in: {check_in_date.strftime('%a, %b %d')} at {_fmt_t(check_in_time)}. "
                    f"Check-out: {check_out_date.strftime('%a, %b %d')} at {_fmt_t(check_out_time)}. "
                    f"Questions? Reply to this message. \u2014 Ruff Life Retreat"
                )
            client  = Client(current_app.config.get('TWILIO_ACCOUNT_SID'),
                             current_app.config.get('TWILIO_AUTH_TOKEN'))
            message = client.messages.create(body=body, from_=from_number, to=to_e164)
            log = SmsMessage(user_id=owner.id, direction='outbound',
                             from_number=from_number, to_number=to_e164,
                             body=body, twilio_sid=message.sid, is_read=True)
            db.session.add(log)
            db.session.commit()
    except Exception as e:
        current_app.logger.error(f'SMS failed on boarding approval: {e}')

    try:
        from app.audit_service import audit
        audit('boarding.approved', 'boarding', booking.id, appt.pet.name,
              f'Boarding request approved for {appt.pet.name} ({check_in_date} to {check_out_date}) by {current_user.first_name} {current_user.last_name}')
    except Exception: pass
    if appt.needs_reapproval:
        flash(f'Boarding reservation for {appt.pet.name} updated and customer notified.', 'success')
    else:
        flash(f'Boarding request for {appt.pet.name} approved! Reservation created.', 'success')
    return redirect(url_for('admin.boarding_dashboard'))


def _kennel_dt(d, time_str, default_hour=12):
    """Combine a date and 'HH:MM' string into a datetime; fallback to default_hour."""
    from datetime import datetime
    try:
        h, m = (time_str or '').split(':')
        return datetime(d.year, d.month, d.day, int(h), int(m))
    except Exception:
        return datetime(d.year, d.month, d.day, default_hour, 0)


def _kennel_conflicts(kennel_type, kennel_number,
                      check_in_date, check_out_date,
                      check_in_time, check_out_time,
                      exclude_id=None):
    """
    Return active Boarding records that time-overlap with the given kennel + datetime window.
    Uses strict datetime comparison so same-day checkout before check-in is NOT a conflict.
    Default assumption when times are missing: check-in = noon, check-out = noon.
    """
    from app.models import Boarding
    new_in  = _kennel_dt(check_in_date,  check_in_time,  12)
    new_out = _kennel_dt(check_out_date, check_out_time, 12)

    candidates = Boarding.query.filter(
        Boarding.status        == 'active',
        Boarding.kennel_type   == kennel_type,
        Boarding.kennel_number == kennel_number,
        Boarding.check_in_date  <= check_out_date,
        Boarding.check_out_date >= check_in_date,
    )
    if exclude_id:
        candidates = candidates.filter(Boarding.id != exclude_id)

    conflicts = []
    for b in candidates.all():
        b_in  = _kennel_dt(b.check_in_date,  b.check_in_time,  12)
        b_out = _kennel_dt(b.check_out_date, b.check_out_time, 12)
        # True overlap: new window starts before existing ends AND ends after existing starts
        if new_in < b_out and new_out > b_in:
            conflicts.append(b)
    return conflicts


@bp.route('/boarding/kennel-slots')
@login_required
@admin_required
def kennel_slots():
    """
    AJAX: return all active kennel slots with occupancy status for a date range.
    Query params: check_in, check_out (ISO dates), check_in_time, check_out_time (HH:MM),
                  exclude (booking_id to omit).
    Response groups by type: { suites: [...], kennels: [...] }
    Each entry: { id, kennel_number, available, occupants: [pet_name, ...] }
    Occupancy uses time-aware overlap when times are provided.
    """
    from app.models import KennelSlot, Boarding
    from datetime import date as _date

    try:
        check_in  = _date.fromisoformat(request.args.get('check_in',  ''))
        check_out = _date.fromisoformat(request.args.get('check_out', ''))
        has_dates = True
    except (ValueError, TypeError):
        has_dates = False

    check_in_time  = request.args.get('check_in_time',  '').strip() or None
    check_out_time = request.args.get('check_out_time', '').strip() or None
    exclude_id     = request.args.get('exclude', type=int)

    # Build occupancy map: (kennel_type, kennel_number) -> [pet_name, ...]
    occupancy = {}
    if has_dates:
        # Broad date candidates first
        active_boardings = Boarding.query.filter(
            Boarding.status == 'active',
            Boarding.kennel_number.isnot(None),
            Boarding.check_in_date  <= check_out,
            Boarding.check_out_date >= check_in,
        ).all()
        new_in  = _kennel_dt(check_in,  check_in_time,  12)
        new_out = _kennel_dt(check_out, check_out_time, 12)
        for b in active_boardings:
            if exclude_id and b.id == exclude_id:
                continue
            b_in  = _kennel_dt(b.check_in_date,  b.check_in_time,  12)
            b_out = _kennel_dt(b.check_out_date, b.check_out_time, 12)
            # Time-aware overlap check
            if new_in < b_out and new_out > b_in:
                key = (b.kennel_type or 'kennel', b.kennel_number)
                pet_name = b.pet.name if b.pet else '—'
                occupancy.setdefault(key, []).append(pet_name)

    slots = KennelSlot.query.filter_by(active=True)\
                .order_by(KennelSlot.kennel_type, KennelSlot.sort_order, KennelSlot.kennel_number)\
                .all()

    suites  = []
    kennels = []
    for s in slots:
        key = (s.kennel_type, s.kennel_number)
        occupants = occupancy.get(key, [])
        entry = {
            'id':            s.id,
            'kennel_number': s.kennel_number,
            'notes':         s.notes or '',
            'available':     len(occupants) == 0,
            'occupants':     occupants,
        }
        if s.kennel_type == 'suite':
            suites.append(entry)
        else:
            kennels.append(entry)

    return {'suites': suites, 'kennels': kennels}


@bp.route('/settings/kennels')
@login_required
@admin_required
def kennel_settings():
    """Kennel/suite board page."""
    from datetime import date
    return render_template('admin/kennel_settings.html', today=date.today())


@bp.route('/boarding/kennel-board')
@login_required
@admin_required
def kennel_board():
    """
    AJAX: return all active kennel slots with full occupancy for a date.
    Each slot includes booking details (pet, owner, dates) for that day.
    """
    from app.models import KennelSlot, Boarding
    from datetime import date as _date

    try:
        d = _date.fromisoformat(request.args.get('date', ''))
    except (ValueError, TypeError):
        d = _date.today()

    slots = KennelSlot.query.filter_by(active=True) \
                .order_by(KennelSlot.sort_order, KennelSlot.kennel_number).all()

    boardings = Boarding.query.filter(
        Boarding.status == 'active',
        Boarding.kennel_number.isnot(None),
        Boarding.check_in_date  <= d,
        Boarding.check_out_date >= d,
    ).all()

    # Map (kennel_type, kennel_number) -> [booking info, ...]
    occupancy = {}
    for b in boardings:
        key = (b.kennel_type or 'kennel', b.kennel_number)
        owner = b.pet.owner if b.pet else None
        occupancy.setdefault(key, []).append({
            'booking_id':     b.id,
            'booking_number': b.booking_number or '—',
            'pet_name':       b.pet.name if b.pet else '—',
            'owner_name':     f'{owner.first_name} {owner.last_name}' if owner else '—',
            'check_in':       b.check_in_date.isoformat(),
            'check_out':      b.check_out_date.isoformat(),
            'check_in_time':  b.check_in_time  or '—',
            'check_out_time': b.check_out_time or '—',
        })

    suites  = []
    kennels = []
    for s in slots:
        key = (s.kennel_type, s.kennel_number)
        entry = {
            'id':            s.id,
            'kennel_type':   s.kennel_type,
            'kennel_number': s.kennel_number,
            'notes':         s.notes or '',
            'bookings':      occupancy.get(key, []),
        }
        if s.kennel_type == 'suite':
            suites.append(entry)
        else:
            kennels.append(entry)

    return {'date': d.isoformat(), 'suites': suites, 'kennels': kennels}


@bp.route('/settings/kennels/add', methods=['POST'])
@login_required
@admin_required
def kennel_settings_add():
    """Add a new kennel or suite slot."""
    from app.models import KennelSlot
    kennel_type   = request.form.get('kennel_type', 'kennel')
    kennel_number = request.form.get('kennel_number', '').strip()
    notes         = request.form.get('notes', '').strip() or None
    if not kennel_number:
        flash('Kennel/suite number is required.', 'danger')
        return redirect(url_for('admin.kennel_settings'))
    existing = KennelSlot.query.filter_by(
        kennel_type=kennel_type, kennel_number=kennel_number).first()
    if existing:
        existing.active = True
        existing.notes  = notes
        db.session.commit()
        flash(f'{"Suite" if kennel_type == "suite" else "Kennel"} #{kennel_number} re-activated.', 'success')
    else:
        try:
            sort_order = int(kennel_number)
        except ValueError:
            sort_order = 9999
        slot = KennelSlot(
            kennel_type=kennel_type,
            kennel_number=kennel_number,
            notes=notes,
            active=True,
            sort_order=sort_order,
        )
        db.session.add(slot)
        db.session.commit()
        flash(f'{"Suite" if kennel_type == "suite" else "Kennel"} #{kennel_number} added.', 'success')
    return redirect(url_for('admin.kennel_settings'))


@bp.route('/settings/kennels/<int:slot_id>/toggle', methods=['POST'])
@login_required
@admin_required
def kennel_settings_toggle(slot_id):
    """Toggle a kennel slot active/inactive."""
    from app.models import KennelSlot
    slot = KennelSlot.query.get_or_404(slot_id)
    slot.active = not slot.active
    db.session.commit()
    state = 'activated' if slot.active else 'deactivated'
    flash(f'{slot.display_label} {state}.', 'success')
    return redirect(url_for('admin.kennel_settings'))


@bp.route('/boarding/occupied-kennels')
@login_required
@admin_required
def occupied_kennels():
    """
    AJAX: return kennels already occupied during a date range.
    Groups multiple pets sharing the same kennel into one entry.
    Query params: check_in, check_out (ISO dates), exclude (booking_id to skip).
    """
    from app.models import Boarding
    from datetime import date as _date

    try:
        check_in  = _date.fromisoformat(request.args.get('check_in',  ''))
        check_out = _date.fromisoformat(request.args.get('check_out', ''))
    except (ValueError, TypeError):
        return []

    exclude_id = request.args.get('exclude', type=int)

    boardings = Boarding.query.filter(
        Boarding.status == 'active',
        Boarding.kennel_number.isnot(None),
        Boarding.check_in_date  <= check_out,
        Boarding.check_out_date >= check_in,
    ).order_by(Boarding.kennel_type, Boarding.kennel_number).all()

    # Group by (kennel_type, kennel_number) so shared kennels appear once
    groups = {}
    for b in boardings:
        if exclude_id and b.id == exclude_id:
            continue
        key = (b.kennel_type or 'kennel', b.kennel_number)
        pet_name = b.pet.name if b.pet else '—'
        if key in groups:
            groups[key]['pet_names'].append(pet_name)
        else:
            groups[key] = {
                'kennel_type':   b.kennel_type or 'kennel',
                'kennel_number': b.kennel_number,
                'pet_names':     [pet_name],
            }

    result = []
    for (ktype, knum), g in groups.items():
        result.append({
            'kennel_type':   ktype,
            'kennel_number': knum,
            'label':         f'{"Suite" if ktype == "suite" else "Kennel"} #{knum} — {" & ".join(g["pet_names"])}',
        })

    return result


@bp.route('/boarding/<int:booking_id>/assign-kennel', methods=['POST'])
@login_required
@admin_required
def assign_kennel(booking_id):
    """Assign or update kennel/suite number on an existing boarding record."""
    from app.models import Boarding
    booking = Boarding.query.get_or_404(booking_id)
    kennel_number = request.form.get('kennel_number', '').strip() or None
    kennel_type   = request.form.get('kennel_type', 'kennel')
    return_date   = request.form.get('return_date', '').strip()

    def _back():
        if return_date:
            return redirect(url_for('admin.kennel_settings') + f'?date={return_date}')
        return redirect(url_for('admin.boarding_dashboard'))

    if not kennel_number:
        flash('Please select a kennel or suite.', 'danger')
        return _back()

    # Time-aware conflict check — block genuine overlaps (not just same-day checkout/checkin)
    conflicts = _kennel_conflicts(
        kennel_type, kennel_number,
        booking.check_in_date, booking.check_out_date,
        booking.check_in_time, booking.check_out_time,
        exclude_id=booking_id,
    )
    if conflicts:
        names = ', '.join(
            f'{b.pet.name} (out {b.check_out_date.strftime("%m/%d")} @ {b.check_out_time})'
            for b in conflicts
        )
        flash(
            f'Cannot assign — {kennel_type.title()} #{kennel_number} has a time conflict with: {names}. '
            f'Resolve the existing reservation first or choose a different slot.',
            'danger'
        )
        return _back()

    booking.kennel_number = kennel_number
    booking.kennel_type   = kennel_type
    db.session.commit()
    flash(
        f'{(kennel_type or "Kennel").title()} #{kennel_number} assigned to {booking.pet.name}.',
        'success'
    )
    if return_date:
        return redirect(url_for('admin.kennel_settings') + f'?date={return_date}')
    return redirect(url_for('admin.boarding_dashboard'))


@bp.route('/boarding/reject/<int:appt_id>', methods=['POST'])
@login_required
@admin_required
def reject_boarding_request(appt_id):
    """Reject a pending boarding appointment request."""
    from app.models import Appointment
    from app.sms_service import send_appointment_cancelled_sms

    appt   = Appointment.query.get_or_404(appt_id)
    reason = request.form.get('reason', '').strip()

    appt.status = 'cancelled'
    db.session.commit()

    try:
        send_appointment_cancelled_sms(appt, reason=reason)
    except Exception as e:
        current_app.logger.error(f'SMS failed on boarding rejection: {e}')

    try:
        from app.audit_service import audit
        audit('boarding.rejected', 'appointment', appt_id, appt.pet.name,
              f'Boarding request rejected for {appt.pet.name} by {current_user.first_name} {current_user.last_name}')
    except Exception: pass
    flash(f'Boarding request for {appt.pet.name} rejected.', 'warning')
    return redirect(url_for('admin.boarding_dashboard'))


# ============================================================
# SATISFACTION SURVEYS
# ============================================================

@bp.route('/surveys')
@login_required
@admin_required
def surveys():
    """Admin satisfaction survey dashboard."""
    from app.models import SurveyResponse
    from sqlalchemy import func

    # All completed responses
    responses = (SurveyResponse.query
        .filter(SurveyResponse.submitted_at.isnot(None))
        .order_by(SurveyResponse.submitted_at.desc())
        .all())

    # Aggregate stats
    total       = len(responses)
    avg_overall = round(sum(r.overall_rating for r in responses) / total, 1) if total else 0
    avg_comm    = round(sum(r.comm_rating for r in responses) / total, 1) if total else 0
    promoters   = sum(1 for r in responses if r.recommend == 'yes')
    detractors  = sum(1 for r in responses if r.recommend == 'no')
    nps         = round(((promoters - detractors) / total) * 100) if total else 0

    # Rating breakdown
    rating_counts = {i: sum(1 for r in responses if r.overall_rating == i) for i in range(1, 6)}

    # By service
    service_stats = {}
    for r in responses:
        svc = r.service_type or 'General'
        service_stats.setdefault(svc, {'count': 0, 'total': 0})
        service_stats[svc]['count'] += 1
        service_stats[svc]['total'] += r.overall_rating
    for svc in service_stats:
        c = service_stats[svc]['count']
        service_stats[svc]['avg'] = round(service_stats[svc]['total'] / c, 1) if c else 0

    # Pending (sent but not submitted)
    pending = (SurveyResponse.query
        .filter(SurveyResponse.submitted_at.is_(None))
        .order_by(SurveyResponse.sent_at.desc())
        .all())

    # Customers not surveyed in 90+ days
    from datetime import date, timedelta
    ninety_days_ago = datetime.now() - timedelta(days=90)
    surveyed_user_ids = {r.user_id for r in SurveyResponse.query
        .filter(SurveyResponse.sent_at >= ninety_days_ago).all()}
    unsurveyed = User.query.filter(
        User.role == 'customer',
        User.is_active == True,
        User.phone.isnot(None),
        ~User.id.in_(surveyed_user_ids)
    ).order_by(User.last_name).all()

    return render_template('admin/surveys.html',
                           responses=responses,
                           pending=pending,
                           unsurveyed=unsurveyed,
                           total=total,
                           avg_overall=avg_overall,
                           avg_comm=avg_comm,
                           nps=nps,
                           promoters=promoters,
                           detractors=detractors,
                           rating_counts=rating_counts,
                           service_stats=service_stats)


@bp.route('/surveys/send/<int:user_id>', methods=['POST'])
@login_required
@admin_required
def send_survey(user_id):
    """Manually send a satisfaction survey to a customer."""
    from app.survey_service import create_and_send_survey
    user         = User.query.get_or_404(user_id)
    service_type = request.form.get('service_type', 'General')
    success      = create_and_send_survey(user, service_type, trigger='manual')
    if success:
        flash(f'Survey sent to {user.first_name} {user.last_name}!', 'success')
    else:
        flash(f'Failed to send survey — check phone number and Twilio config.', 'danger')
    return redirect(request.referrer or url_for('admin.surveys'))


# ============================================================
# PLAY GROUP MANAGEMENT
# ============================================================

# Size thresholds (lbs)
SIZE_SMALL  = 25
SIZE_MEDIUM = 50

def get_size_category(weight):
    """Return size category based on weight in lbs."""
    if weight is None: return 'medium'
    weight = float(weight)
    if weight < SIZE_SMALL:  return 'small'
    if weight <= SIZE_MEDIUM: return 'medium'
    return 'large'

def auto_assign_play_group(pet, attendance):
    """
    Automatically assign a play group to a daycare attendance record.
    Uses pet's default group if set, otherwise finds best match by
    size category and temperament. Falls back to any active group
    of matching size.
    """
    from app.models import PlayGroup

    # Use pet's default group if configured
    if pet.default_play_group_id:
        attendance.play_group_id = pet.default_play_group_id
        return

    size     = get_size_category(pet.weight)
    temp     = pet.temperament or 'calm'

    # Try exact size + temperament match first
    group = PlayGroup.query.filter_by(
        size_category=size, temperament=temp, active=True
    ).first()

    # Fall back to mixed temperament group of same size
    if not group:
        group = PlayGroup.query.filter_by(
            size_category=size, temperament='mixed', active=True
        ).first()

    # Fall back to any active group of that size
    if not group:
        group = PlayGroup.query.filter_by(
            size_category=size, active=True
        ).first()

    if group:
        attendance.play_group_id = group.id


@bp.route('/play-groups')
@login_required
@admin_required
def play_groups():
    """Play group management page."""
    from app.models import PlayGroup, DaycareAttendance
    from datetime import date

    today  = date.today()
    groups = PlayGroup.query.order_by(
        PlayGroup.size_category.asc(),
        PlayGroup.temperament.asc()
    ).all()

    # Today's attendance per group
    today_by_group = {}
    for g in groups:
        attendances = (DaycareAttendance.query
            .filter_by(play_group_id=g.id)
            .filter(db.func.date(DaycareAttendance.check_in_time) == today)
            .filter(DaycareAttendance.check_out_time.is_(None))
            .all())
        today_by_group[g.id] = attendances

    return render_template('admin/play_groups.html',
                           groups=groups,
                           today_by_group=today_by_group,
                           today=today)


@bp.route('/play-groups/create', methods=['POST'])
@login_required
@admin_required
def create_play_group():
    from app.models import PlayGroup
    group = PlayGroup(
        name          = request.form.get('name', '').strip(),
        size_category = request.form.get('size_category', 'medium'),
        temperament   = request.form.get('temperament', 'calm'),
        max_capacity  = request.form.get('max_capacity', 10, type=int),
        color         = request.form.get('color', '#0d6efd'),
        active        = True
    )
    db.session.add(group)
    db.session.commit()
    flash(f'Play group "{group.name}" created.', 'success')
    return redirect(url_for('admin.play_groups'))


@bp.route('/play-groups/<int:group_id>/edit', methods=['POST'])
@login_required
@admin_required
def edit_play_group(group_id):
    from app.models import PlayGroup
    group = PlayGroup.query.get_or_404(group_id)
    group.name          = request.form.get('name', '').strip() or group.name
    group.size_category = request.form.get('size_category', group.size_category)
    group.temperament   = request.form.get('temperament', group.temperament)
    group.max_capacity  = request.form.get('max_capacity', group.max_capacity, type=int)
    group.color         = request.form.get('color', group.color)
    group.active        = request.form.get('active') == '1'
    db.session.commit()
    flash(f'Play group "{group.name}" updated.', 'success')
    return redirect(url_for('admin.play_groups'))


@bp.route('/play-groups/<int:group_id>/delete', methods=['POST'])
@login_required
@admin_required
def delete_play_group(group_id):
    from app.models import PlayGroup
    group = PlayGroup.query.get_or_404(group_id)
    if group.today_count > 0:
        flash('Cannot delete a group with pets currently checked in.', 'danger')
        return redirect(url_for('admin.play_groups'))
    db.session.delete(group)
    db.session.commit()
    flash('Play group deleted.', 'success')
    return redirect(url_for('admin.play_groups'))


@bp.route('/play-groups/reassign/<int:attendance_id>', methods=['POST'])
@login_required
@admin_required
def reassign_play_group(attendance_id):
    """Manually reassign a pet to a different play group."""
    from app.models import DaycareAttendance
    att      = DaycareAttendance.query.get_or_404(attendance_id)
    group_id = request.form.get('play_group_id', type=int)
    att.play_group_id = group_id if group_id else None
    db.session.commit()
    return ('', 204)


# ============================================================
# STAFF NOTICES
# ============================================================

@bp.route('/notices/create', methods=['POST'])
@login_required
@admin_required
def create_notice():
    from app.models import StaffNotice
    from datetime import datetime as dt

    title      = request.form.get('title', '').strip()
    body       = request.form.get('body', '').strip()
    priority   = request.form.get('priority', 'normal')
    expires_in = request.form.get('expires_in', '1', type=int)  # days

    if not title or not body:
        flash('Title and message are required.', 'danger')
        return redirect(url_for('admin.dashboard'))

    expires_at = dt.now().replace(hour=23, minute=59, second=59) + \
                 __import__('datetime').timedelta(days=expires_in - 1)

    notice = StaffNotice(
        title      = title,
        body       = body,
        priority   = priority,
        expires_at = expires_at,
        created_by = current_user.id
    )
    db.session.add(notice)
    db.session.commit()
    flash('Notice posted.', 'success')
    return redirect(url_for('admin.dashboard'))


@bp.route('/notices/<int:notice_id>/dismiss', methods=['POST'])
@login_required
@admin_required
def dismiss_notice(notice_id):
    from app.models import StaffNotice
    notice = StaffNotice.query.get_or_404(notice_id)
    notice.dismiss_for(current_user.id)
    db.session.commit()
    return ('', 204)


@bp.route('/notices/<int:notice_id>/delete', methods=['POST'])
@login_required
@admin_required
def delete_notice(notice_id):
    from app.models import StaffNotice
    notice = StaffNotice.query.get_or_404(notice_id)
    db.session.delete(notice)
    db.session.commit()
    flash('Notice deleted.', 'success')
    return redirect(url_for('admin.dashboard'))


# ============================================================
# SUPPORT TICKETS
# ============================================================

@bp.route('/support', methods=['GET', 'POST'])
@login_required
@admin_required
def support():
    """Staff support ticket submission and history."""
    from app.models import SupportTicket

    if request.method == 'POST':
        ticket_type = request.form.get('ticket_type', '').strip()
        subject     = request.form.get('subject', '').strip()
        description = request.form.get('description', '').strip()

        if not all([ticket_type, subject, description]):
            flash('All fields are required.', 'danger')
            return redirect(url_for('admin.support'))

        ticket = SupportTicket(
            ticket_type  = ticket_type,
            subject      = subject,
            description  = description,
            submitted_by = current_user.id,
            status       = 'open'
        )
        db.session.add(ticket)
        db.session.commit()

        support_phone = current_app.config.get('SUPPORT_PHONE', '')
        if not support_phone:
            current_app.logger.warning('SUPPORT_PHONE not configured — support ticket SMS skipped.')
        else:
            try:
                from app.sms_service import _normalize_phone
                from twilio.rest import Client
                type_labels = {
                    'feature_request': 'Feature Request',
                    'account_issue':   'Account Issue',
                    'standard':        'Standard Request'
                }
                label   = type_labels.get(ticket_type, ticket_type)
                to_e164 = _normalize_phone(support_phone)
                if to_e164:
                    body = (
                        f"\U0001f3ab Ruff Life Support Ticket #{ticket.id}\n"
                        f"Type: {label}\n"
                        f"From: {current_user.first_name} {current_user.last_name}\n"
                        f"Subject: {subject}\n"
                        f"{description[:120]}{'...' if len(description) > 120 else ''}"
                    )
                    client = Client(
                        current_app.config.get('TWILIO_ACCOUNT_SID'),
                        current_app.config.get('TWILIO_AUTH_TOKEN')
                    )
                    client.messages.create(
                        body=body,
                        from_=current_app.config.get('TWILIO_PHONE_NUMBER'),
                        to=to_e164
                    )
            except Exception as e:
                current_app.logger.error(f'Support ticket SMS failed: {e}')

        try:
            from app.audit_service import audit
            audit('ticket.created', 'support_ticket', ticket.id, subject,
                  f'Support ticket "{subject}" submitted by {current_user.first_name} {current_user.last_name}')
        except Exception: pass
        flash(f'Support ticket #{ticket.id} submitted successfully!', 'success')
        return redirect(url_for('admin.support'))

    # ── GET ───────────────────────────────────────────────────────────────────
    status_filter = request.args.get('status', '')

    if current_user.role == 'admin':
        all_tickets = SupportTicket.query.order_by(SupportTicket.created_at.desc()).all()
    else:
        all_tickets = SupportTicket.query.filter_by(
            submitted_by=current_user.id
        ).order_by(SupportTicket.created_at.desc()).all()

    counts = {
        'open':        sum(1 for t in all_tickets if t.status == 'open'),
        'in_progress': sum(1 for t in all_tickets if t.status == 'in_progress'),
        'resolved':    sum(1 for t in all_tickets if t.status == 'resolved'),
        'total':       len(all_tickets),
    }

    if status_filter in ('open', 'in_progress', 'resolved'):
        tickets = [t for t in all_tickets if t.status == status_filter]
    else:
        tickets = all_tickets

    # ── MTD time ticker ───────────────────────────────────────────────────────
    from datetime import datetime as _dt
    from app.models import TicketTimeSession
    _now       = _dt.now()
    _mtd_start = _now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    mtd_sessions = TicketTimeSession.query.filter(
        TicketTimeSession.ended_at >= _mtd_start
    ).all()
    mtd_minutes = sum(s.minutes for s in mtd_sessions if s.minutes)

    # Include any currently running session started this month
    active_tickets = SupportTicket.query.filter(
        SupportTicket.active_session_started.isnot(None)
    ).all()
    for t in active_tickets:
        if t.active_session_started and t.active_session_started >= _mtd_start:
            elapsed = int((_now - t.active_session_started).total_seconds() // 60)
            mtd_minutes += max(0, elapsed)

    mtd_hours   = mtd_minutes // 60
    mtd_mins    = mtd_minutes % 60
    mtd_display = f'{mtd_hours}h {mtd_mins}m' if mtd_hours else f'{mtd_mins}m'
    mtd_label   = _now.strftime('%B %Y')
    # ── END MTD ───────────────────────────────────────────────────────────────

    return render_template('admin/support.html',
                           tickets=tickets,
                           counts=counts,
                           status_filter=status_filter,
                           mtd_display=mtd_display,
                           mtd_label=mtd_label,
                           mtd_minutes=mtd_minutes)
@bp.route('/support/<int:ticket_id>/status', methods=['POST'])
@login_required
@admin_required
def update_ticket_status(ticket_id):
    from app.models import SupportTicket
    from datetime import datetime as dt
    ticket     = SupportTicket.query.get_or_404(ticket_id)
    old_status = ticket.status
    new_status = request.form.get('status', ticket.status)
    if old_status == 'working' and new_status != 'working' and ticket.is_active_session:
        _close_active_session(ticket, note='Session closed on status change')
    ticket.status     = new_status
    ticket.updated_at = dt.now()
    db.session.commit()
    if new_status == 'resolved' and old_status != 'resolved':
        try:
            submitter = ticket.submitter
            if submitter and submitter.phone:
                from app.sms_service import _normalize_phone
                from app.models import SmsMessage
                from twilio.rest import Client
                to_e164     = _normalize_phone(submitter.phone)
                from_number = current_app.config.get('TWILIO_PHONE_NUMBER')
                if to_e164:
                    sms_body = (
                        f"Hi {submitter.first_name}, your support ticket "
                        f"#{ticket.id} '{ticket.subject}' has been resolved. "
                        f"Total time spent: {ticket.format_time()}. "
                        f"View it at rufflife.app/admin/support/{ticket.id}"
                    )
                    client  = Client(current_app.config.get('TWILIO_ACCOUNT_SID'),
                                     current_app.config.get('TWILIO_AUTH_TOKEN'))
                    message = client.messages.create(body=sms_body, from_=from_number, to=to_e164)
                    log = SmsMessage(user_id=submitter.id, direction='outbound',
                                     from_number=from_number, to_number=to_e164,
                                     body=sms_body, twilio_sid=message.sid, is_read=True)
                    db.session.add(log)
                    db.session.commit()
        except Exception as e:
            current_app.logger.error(f'Ticket resolved SMS failed: {e}')
    flash(f'Ticket #{ticket_id} updated to {ticket.status.replace("_", " ").title()}.', 'success')
    return redirect(url_for('admin.support'))


@bp.route('/support/<int:ticket_id>', methods=['GET'])
@login_required
@admin_required
def support_ticket_detail(ticket_id):
    from app.models import SupportTicket
    ticket = SupportTicket.query.get_or_404(ticket_id)
    if current_user.role != 'admin' and ticket.submitted_by != current_user.id:
        flash('You do not have permission to view that ticket.', 'danger')
        return redirect(url_for('admin.support'))
    return render_template('admin/support_ticket.html', ticket=ticket)


@bp.route('/support/<int:ticket_id>/reply', methods=['POST'])
@login_required
@admin_required
def support_ticket_reply(ticket_id):
    from app.models import SupportTicket, TicketComment
    from datetime import datetime as dt
    ticket = SupportTicket.query.get_or_404(ticket_id)
    body   = request.form.get('body', '').strip()
    if not body:
        flash('Reply cannot be empty.', 'danger')
        return redirect(url_for('admin.support_ticket_detail', ticket_id=ticket_id))
    comment = TicketComment(
        ticket_id  = ticket_id,
        user_id    = current_user.id,
        body       = body,
        created_at = dt.now()
    )
    db.session.add(comment)
    if ticket.status == 'open':
        ticket.status     = 'in_progress'
        ticket.updated_at = dt.now()
    db.session.commit()
    flash('Reply added.', 'success')
    return redirect(url_for('admin.support_ticket_detail', ticket_id=ticket_id))

# ============================================================
# INCIDENT MANAGEMENT
# ============================================================

@bp.route('/incidents')
@login_required
@admin_required
def incidents():
    """Incident log dashboard."""
    from app.models import Incident, Pet
    severity_filter = request.args.get('severity', 'all')
    status_filter   = request.args.get('status', 'all')

    query = Incident.query
    if severity_filter != 'all':
        query = query.filter_by(severity=severity_filter)
    if status_filter != 'all':
        query = query.filter_by(status=status_filter)

    all_incidents = query.order_by(Incident.incident_date.desc()).all()
    all_pets      = Pet.query.filter_by(is_active=True).order_by(Pet.name).all()

    return render_template('admin/incidents.html',
                           incidents=all_incidents,
                           all_pets=all_pets,
                           severity_filter=severity_filter,
                           status_filter=status_filter,
                           now=datetime.now())


@bp.route('/incidents/log', methods=['POST'])
@login_required
@admin_required
def log_incident():
    """Log a new incident."""
    from app.models import Incident, Pet
    from datetime import datetime as dt

    pet_id        = request.form.get('pet_id', type=int)
    incident_type = request.form.get('incident_type', '').strip()
    severity      = request.form.get('severity', 'minor')
    description   = request.form.get('description', '').strip()
    action_taken  = request.form.get('action_taken', '').strip() or None
    notify_owner  = request.form.get('notify_owner') == '1'

    date_str = request.form.get('incident_date', '').strip()
    time_str = request.form.get('incident_time', '').strip()
    if date_str and time_str:
        try:
            incident_date = dt.strptime(f'{date_str} {time_str}', '%Y-%m-%d %H:%M')
        except ValueError:
            incident_date = dt.now()
    else:
        incident_date = dt.now()

    if not all([pet_id, incident_type, description]):
        flash('Pet, incident type, and description are required.', 'danger')
        return redirect(url_for('admin.incidents'))

    pet = Pet.query.get_or_404(pet_id)

    incident = Incident(
        pet_id        = pet_id,
        reported_by   = current_user.id,
        incident_type = incident_type,
        severity      = severity,
        description   = description,
        action_taken  = action_taken,
        owner_notified = False,
        status        = 'open',
        incident_date = incident_date
    )
    db.session.add(incident)
    db.session.commit()

    # Send SMS to owner if requested
    if notify_owner:
        try:
            owner = pet.owner
            if owner and owner.phone:
                from app.sms_service import send_incident_notification_sms
                send_incident_notification_sms(incident)
                incident.owner_notified = True
                db.session.commit()
        except Exception as e:
            current_app.logger.error(f'Incident SMS failed: {e}')

    try:
        from app.audit_service import audit
        audit('incident.created', 'incident', incident.id, pet.name,
              f'{severity.title()} incident ({incident_type}) logged for {pet.name} by {current_user.first_name} {current_user.last_name}')
    except Exception: pass
    flash(f'Incident logged for {pet.name}.', 'success')
    return redirect(url_for('admin.incident_detail', incident_id=incident.id))


@bp.route('/incidents/<int:incident_id>')
@login_required
@admin_required
def incident_detail(incident_id):
    """View a single incident."""
    from app.models import Incident
    incident = Incident.query.get_or_404(incident_id)
    return render_template('admin/incident_detail.html', incident=incident)


@bp.route('/incidents/<int:incident_id>/resolve', methods=['POST'])
@login_required
@admin_required
def resolve_incident(incident_id):
    """Mark an incident as resolved."""
    from app.models import Incident
    from datetime import datetime as dt
    incident = Incident.query.get_or_404(incident_id)
    incident.status      = 'resolved'
    incident.resolved_at = dt.now()
    resolution = request.form.get('resolution_notes', '').strip()
    if resolution:
        incident.action_taken = (incident.action_taken or '') + f'\n\nResolution: {resolution}'
    db.session.commit()
    try:
        from app.audit_service import audit
        audit('incident.resolved', 'incident', incident_id, f'Incident #{incident_id}',
              f'Incident #{incident_id} resolved by {current_user.first_name} {current_user.last_name}')
    except Exception: pass
    flash(f'Incident #{incident.id} marked as resolved.', 'success')
    return redirect(url_for('admin.incidents'))


@bp.route('/incidents/<int:incident_id>/notify', methods=['POST'])
@login_required
@admin_required
def notify_incident_owner(incident_id):
    """Send SMS notification to pet owner about an incident."""
    from app.models import Incident
    incident = Incident.query.get_or_404(incident_id)
    try:
        from app.sms_service import send_incident_notification_sms
        send_incident_notification_sms(incident)
        incident.owner_notified = True
        db.session.commit()
        flash('Owner notified via SMS.', 'success')
    except Exception as e:
        flash(f'SMS failed: {e}', 'danger')
    return redirect(url_for('admin.incident_detail', incident_id=incident_id))


# ── Promo Code Management ─────────────────────────────────────────────────────

@bp.route('/promo-codes')
@login_required
@admin_required
def promo_codes():
    from app.models import PromoCode
    codes = PromoCode.query.order_by(PromoCode.created_at.desc()).all()
    return render_template('admin/promo_codes.html', codes=codes)


@bp.route('/promo-codes/create', methods=['POST'])
@login_required
@admin_required
def create_promo_code():
    from app.models import PromoCode
    code_str = request.form.get('code', '').strip().upper()
    if not code_str:
        flash('Code is required.', 'danger')
        return redirect(url_for('admin.promo_codes'))

    existing = PromoCode.query.filter_by(code=code_str).first()
    if existing:
        flash(f'Code {code_str} already exists.', 'danger')
        return redirect(url_for('admin.promo_codes'))

    expires_raw = request.form.get('expires_at', '').strip()
    expires_at  = None
    if expires_raw:
        try:
            expires_at = datetime.strptime(expires_raw, '%Y-%m-%d')
        except ValueError:
            pass

    code = PromoCode(
        code           = code_str,
        description    = request.form.get('description', '').strip() or None,
        discount_type  = request.form.get('discount_type', 'fixed'),
        discount_value = float(request.form.get('discount_value', 0)),
        active         = True,
        expires_at     = expires_at,
        created_by     = current_user.id,
        created_at     = datetime.now(),
    )
    db.session.add(code)
    db.session.commit()
    try:
        from app.audit_service import audit
        audit('promo.created', 'promo_code', code.id, code_str,
              f'Promo code {code_str} created by {current_user.first_name} {current_user.last_name}')
    except Exception: pass
    flash(f'Promo code {code_str} created.', 'success')
    return redirect(url_for('admin.promo_codes'))


@bp.route('/promo-codes/<int:code_id>/toggle', methods=['POST'])
@login_required
@admin_required
def toggle_promo_code(code_id):
    from app.models import PromoCode
    code = PromoCode.query.get_or_404(code_id)
    code.active = not code.active
    db.session.commit()
    flash(f'Code {code.code} {"activated" if code.active else "deactivated"}.', 'info')
    return redirect(url_for('admin.promo_codes'))


@bp.route('/promo-codes/<int:code_id>/delete', methods=['POST'])
@login_required
@admin_required
def delete_promo_code(code_id):
    from app.models import PromoCode, PromoCodeUse
    code = PromoCode.query.get_or_404(code_id)
    PromoCodeUse.query.filter_by(promo_code_id=code.id).delete()
    db.session.delete(code)
    db.session.commit()
    flash(f'Code {code.code} deleted.', 'info')
    return redirect(url_for('admin.promo_codes'))


# ── Apply promo code to customer invoice ──────────────────────────────────────

@bp.route('/customers/<int:customer_id>/apply-promo', methods=['POST'])
@login_required
@admin_required
def apply_promo_to_customer(customer_id):
    from app.loyalty_service import validate_promo_code, apply_promo_code
    customer  = User.query.get_or_404(customer_id)
    code_str  = request.form.get('promo_code', '').strip()
    base_amt  = float(request.form.get('base_amount', 0) or 0)

    code, err = validate_promo_code(code_str, customer.id)
    if err:
        flash(err, 'danger')
        return redirect(url_for('admin.customer_detail', customer_id=customer_id))

    apply_promo_code(code, customer, base_amt, db)
    flash(f'Promo code {code.code} applied — {code.display_value()}.', 'success')
    return redirect(url_for('admin.customer_detail', customer_id=customer_id))


# ── Apply loyalty credit ──────────────────────────────────────────────────────

@bp.route('/customers/<int:customer_id>/apply-credit/<int:credit_id>', methods=['POST'])
@login_required
@admin_required
def apply_loyalty_credit_route(customer_id, credit_id):
    from app.models import LoyaltyCredit
    from app.loyalty_service import apply_loyalty_credit
    customer = User.query.get_or_404(customer_id)
    credit   = LoyaltyCredit.query.get_or_404(credit_id)
    if credit.customer_id != customer.id:
        flash('Credit does not belong to this customer.', 'danger')
        return redirect(url_for('admin.customer_detail', customer_id=customer_id))
    if not credit.is_pending:
        flash('This credit has already been applied.', 'warning')
        return redirect(url_for('admin.customer_detail', customer_id=customer_id))
    apply_loyalty_credit(credit, customer, db)
    flash(f'Loyalty credit of ${float(credit.amount):.2f} applied to invoice adjustments.', 'success')
    return redirect(url_for('admin.customer_detail', customer_id=customer_id))


# ── Loyalty overview (all customers with pending credits) ─────────────────────

@bp.route('/loyalty')
@login_required
@admin_required
def loyalty_overview():
    from app.models import LoyaltyCredit
    from app.loyalty_service import get_boarding_progress, get_daycare_progress
    pending = (LoyaltyCredit.query
               .filter_by(status='pending')
               .order_by(LoyaltyCredit.earned_at.desc())
               .all())
    return render_template('admin/loyalty_overview.html', pending=pending)


# ── Ticket Time Tracking ──────────────────────────────────────────────────────

@bp.route('/support/<int:ticket_id>/start-work', methods=['POST'])
@login_required
@admin_required
def ticket_start_work(ticket_id):
    """Start a work session on a ticket — status becomes 'working'."""
    from app.models import SupportTicket, TicketTimeSession
    ticket = SupportTicket.query.get_or_404(ticket_id)
    if ticket.is_active_session:
        flash('A work session is already active on this ticket.', 'warning')
        return redirect(url_for('admin.support_ticket_detail', ticket_id=ticket_id))
    ticket.status                 = 'working'
    ticket.active_session_started = datetime.now()
    ticket.active_session_user_id = current_user.id
    ticket.updated_at             = datetime.now()
    db.session.commit()
    flash('Work session started — timer is running.', 'success')
    return redirect(url_for('admin.support_ticket_detail', ticket_id=ticket_id))


@bp.route('/support/<int:ticket_id>/pause-work', methods=['POST'])
@login_required
@admin_required
def ticket_pause_work(ticket_id):
    """End the active work session and log elapsed time."""
    from app.models import SupportTicket, TicketTimeSession
    ticket = SupportTicket.query.get_or_404(ticket_id)
    if not ticket.is_active_session:
        flash('No active work session to pause.', 'warning')
        return redirect(url_for('admin.support_ticket_detail', ticket_id=ticket_id))
    _close_active_session(ticket, note=request.form.get('note', '').strip() or None)
    ticket.status = 'in_progress'
    db.session.commit()
    flash(f'Work session paused. Total time: {ticket.format_time()}.', 'info')
    return redirect(url_for('admin.support_ticket_detail', ticket_id=ticket_id))


def _close_active_session(ticket, note=None):
    """Close the active timer session, log it, and add minutes to total."""
    from app.models import TicketTimeSession
    if not ticket.active_session_started:
        return
    ended_at = datetime.now()
    delta    = ended_at - ticket.active_session_started
    minutes  = max(1, int(delta.total_seconds() // 60))
    session  = TicketTimeSession(
        ticket_id  = ticket.id,
        user_id    = ticket.active_session_user_id,
        started_at = ticket.active_session_started,
        ended_at   = ended_at,
        minutes    = minutes,
        note       = note,
    )
    db.session.add(session)
    ticket.total_minutes           = (ticket.total_minutes or 0) + minutes
    ticket.active_session_started  = None
    ticket.active_session_user_id  = None

@bp.route('/reports/waiver-acceptance')
@login_required
@admin_required
def waiver_report():
    from app.models import User
    all_customers = User.query.filter_by(role='customer', is_active=True).order_by(User.last_name).all()
    
    # Safely check for waiver_accepted attribute
    accepted = []
    not_accepted = []
    
    for c in all_customers:
        # Use getattr with default False to safely check
        if getattr(c, 'waiver_accepted', False):
            accepted.append(c)
        else:
            not_accepted.append(c)
    
    return render_template('admin/waiver_report.html',
        all_customers=all_customers,
        accepted=accepted,
        not_accepted=not_accepted,
        total=len(all_customers))

@bp.route('/customer/<int:customer_id>/waiver-reminder-sms', methods=['POST'])
@login_required
@admin_required
def send_waiver_reminder_sms(customer_id):
    """Send a waiver reminder SMS to a customer who hasn't signed yet."""
    from app.models import User, SmsMessage
    from app.sms_service import _normalize_phone
    from twilio.rest import Client

    customer = User.query.get_or_404(customer_id)

    if getattr(customer, 'waiver_accepted', False):
        flash(f'{customer.first_name} {customer.last_name} has already accepted the waiver.', 'info')
        return redirect(url_for('admin.waiver_report'))

    if not customer.phone:
        flash(f'{customer.first_name} {customer.last_name} has no phone number on file.', 'danger')
        return redirect(url_for('admin.waiver_report'))

    try:
        to_e164     = _normalize_phone(customer.phone)
        from_number = current_app.config.get('TWILIO_PHONE_NUMBER')
        body = (
            f"Hi {customer.first_name}! This is Ruff Life Retreat. "
            f"Please log in to your customer portal to review and sign your service waiver: "
            f"https://rufflife.app/login . "
            f"Questions? Reply to this message or call us. — Ruff Life Retreat"
        )
        client  = Client(current_app.config.get('TWILIO_ACCOUNT_SID'),
                         current_app.config.get('TWILIO_AUTH_TOKEN'))
        message = client.messages.create(body=body, from_=from_number, to=to_e164)
        log = SmsMessage(
            user_id     = customer.id,
            direction   = 'outbound',
            from_number = from_number,
            to_number   = to_e164,
            body        = body,
            twilio_sid  = message.sid,
            is_read     = True
        )
        db.session.add(log)
        db.session.commit()
        flash(f'Waiver reminder sent to {customer.first_name} {customer.last_name}.', 'success')
    except Exception as e:
        current_app.logger.error(f'Waiver reminder SMS failed for customer {customer_id}: {e}')
        flash(f'Failed to send reminder: {e}', 'danger')

    return redirect(url_for('admin.waiver_report') + '#pending')


@bp.route('/reports/boarding-occupancy')
@login_required
@admin_required
def boarding_occupancy_report():
    """Daily boarding drop-off and pickup report with kennel assignments."""
    from app.models import Boarding, Pet
    from datetime import date, timedelta

    today = date.today()

    # Date range â€” default to current week (Monâ€“Sun) or use query params
    try:
        start_date = date.fromisoformat(request.args.get('start', ''))
    except (ValueError, TypeError):
        start_date = today - timedelta(days=today.weekday())  # Monday

    try:
        end_date = date.fromisoformat(request.args.get('end', ''))
    except (ValueError, TypeError):
        end_date = start_date + timedelta(days=13)  # 2 weeks

    # Clamp range to max 60 days
    if (end_date - start_date).days > 60:
        end_date = start_date + timedelta(days=59)

    # Pull all boardings that overlap the date range
    boardings = Boarding.query.filter(
        Boarding.status.in_(['active', 'completed']),
        Boarding.check_in_date  <= end_date,
        Boarding.check_out_date >= start_date,
    ).order_by(Boarding.check_in_date, Boarding.check_in_time).all()

    # Build day-by-day structure
    days = []
    d = start_date
    while d <= end_date:
        dropoffs = []
        pickups  = []
        staying  = []

        for b in boardings:
            owner = b.pet.owner if b.pet else None
            entry = {
                'id':           b.id,
                'pet_name':     b.pet.name if b.pet else 'â€”',
                'pet_breed':    b.pet.breed or '' if b.pet else '',
                'owner_name':   f'{owner.first_name} {owner.last_name}' if owner else 'â€”',
                'owner_phone':  owner.phone or 'â€”' if owner else 'â€”',
                'check_in_time':  b.check_in_time  or 'â€”',
                'check_out_time': b.check_out_time or 'â€”',
                'kennel_type':  (b.kennel_type or 'kennel').title(),
                'kennel_number': b.kennel_number or 'â€”',
                'kennel_label': f'{(b.kennel_type or "Kennel").title()} #{b.kennel_number}' if b.kennel_number else 'Unassigned',
                'status':       b.status,
                'nights':       (b.check_out_date - b.check_in_date).days,
            }
            if b.check_in_date == d:
                dropoffs.append(entry)
            elif b.check_out_date == d:
                pickups.append(entry)
            elif b.check_in_date < d < b.check_out_date:
                staying.append(entry)

        # Sort by time
        def sort_time(e):
            t = e['check_in_time'] if e in dropoffs else e['check_out_time']
            return t if t and t != 'â€”' else '99:99'

        dropoffs.sort(key=lambda e: e['check_in_time']  or '99:99')
        pickups.sort( key=lambda e: e['check_out_time'] or '99:99')
        staying.sort( key=lambda e: e['kennel_label'])

        days.append({
            'date':         d,
            'is_today':     d == today,
            'is_past':      d < today,
            'dropoffs':     dropoffs,
            'pickups':      pickups,
            'staying':      staying,
            'total_guests': len(dropoffs) + len(staying),
        })
        d += timedelta(days=1)

    # Navigation â€” prev/next 2-week windows
    prev_start = start_date - timedelta(days=14)
    next_start = start_date + timedelta(days=14)

    from datetime import timedelta as _td
    return render_template('admin/boarding_occupancy.html',
        days=days,
        start_date=start_date,
        end_date=end_date,
        prev_start=prev_start,
        next_start=next_start,
        today=today,
        timedelta=_td,
    )





# ============================================================
# BOARDING CAPACITY VIEW
# ============================================================

@bp.route('/boarding/capacity')
@login_required
@admin_required
def boarding_capacity():
    """Boarding capacity page — pie chart + date picker."""
    from datetime import date
    return render_template('admin/boarding_capacity.html', today=date.today())


@bp.route('/boarding/capacity-data')
@login_required
@admin_required
def boarding_capacity_data():
    """AJAX: return capacity breakdown JSON for a given date."""
    from datetime import date as _date
    from app.models import Boarding
    from app.settings_service import get_kennel_capacity

    try:
        d = _date.fromisoformat(request.args.get('date', ''))
    except (ValueError, TypeError):
        d = _date.today()

    capacity = get_kennel_capacity()

    boardings = Boarding.query.filter(
        Boarding.status == 'active',
        Boarding.check_in_date  <= d,
        Boarding.check_out_date >= d,
    ).order_by(Boarding.check_in_date).all()

    arriving  = []
    staying   = []
    departing = []

    for b in boardings:
        owner = b.pet.owner if b.pet else None
        entry = {
            'id':            b.id,
            'pet_name':      b.pet.name if b.pet else '—',
            'pet_breed':     (b.pet.breed or '') if b.pet else '',
            'owner_name':    f'{owner.first_name} {owner.last_name}' if owner else '—',
            'booking_number': b.booking_number or '—',
            'check_in_date':  b.check_in_date.isoformat(),
            'check_out_date': b.check_out_date.isoformat(),
            'check_in_time':  b.check_in_time  or '—',
            'check_out_time': b.check_out_time or '—',
            'nights':         (b.check_out_date - b.check_in_date).days,
            'kennel_label':   f'{(b.kennel_type or "Kennel").title()} #{b.kennel_number}'
                              if b.kennel_number else 'Unassigned',
        }
        if b.check_in_date == d:
            arriving.append(entry)
        elif b.check_out_date == d:
            departing.append(entry)
        else:
            staying.append(entry)

    total     = len(arriving) + len(staying) + len(departing)
    available = max(0, capacity - total)

    return {
        'date':      d.isoformat(),
        'capacity':  capacity,
        'total':     total,
        'available': available,
        'arriving':  arriving,
        'staying':   staying,
        'departing': departing,
    }


# ============================================================
# FACILITY SETTINGS
# ============================================================

@bp.route('/settings/kennel-capacity', methods=['POST'])
@login_required
@admin_required
def save_kennel_capacity():
    """Save kennel capacity setting from boarding dashboard."""
    from app.settings_service import set_setting, get_kennel_capacity
    try:
        capacity = int(request.form.get('kennel_capacity', 40))
        if capacity < 1 or capacity > 500:
            flash('Capacity must be between 1 and 500.', 'danger')
            return redirect(url_for('admin.boarding_dashboard'))
        old = get_kennel_capacity()
        set_setting('kennel_capacity', capacity, user_id=current_user.id)
        try:
            from app.audit_service import audit
            audit('settings.kennel_capacity', 'facility_setting', None, 'Kennel Capacity',
                  f'Kennel capacity changed from {old} to {capacity} by {current_user.first_name} {current_user.last_name}')
        except Exception: pass
        flash(f'Kennel capacity updated to {capacity}.', 'success')
    except (ValueError, TypeError):
        flash('Invalid capacity value.', 'danger')
    return redirect(url_for('admin.boarding_dashboard'))

# ============================================================
# AUDIT LOG — owner-only, not linked from any nav
# ============================================================
@bp.route('/audit-log')
@login_required
def audit_log():
    if current_user.email != 'admin@ruffliferetreat.com':
        flash('Access denied.', 'danger')
        return redirect(url_for('admin.dashboard'))
    from app.models import AuditLog
    PAGE_SIZE = 100
    page = request.args.get('page', 1, type=int)
    filters = {
        'from':   request.args.get('from',   ''),
        'to':     request.args.get('to',     ''),
        'user':   request.args.get('user',   ''),
        'entity': request.args.get('entity', ''),
        'q':      request.args.get('q',      ''),
    }
    query = AuditLog.query
    if filters['from']:
        try:
            from datetime import datetime as _dt
            query = query.filter(AuditLog.timestamp >= _dt.strptime(filters['from'], '%Y-%m-%d'))
        except ValueError: pass
    if filters['to']:
        try:
            from datetime import datetime as _dt, timedelta
            query = query.filter(AuditLog.timestamp < _dt.strptime(filters['to'], '%Y-%m-%d') + timedelta(days=1))
        except ValueError: pass
    if filters['user']:
        query = query.filter(AuditLog.user_id == int(filters['user']))
    if filters['entity']:
        query = query.filter(AuditLog.entity_type == filters['entity'])
    if filters['q']:
        like = f"%{filters['q']}%"
        query = query.filter(
            db.or_(AuditLog.description.ilike(like),
                   AuditLog.entity_name.ilike(like),
                   AuditLog.action.ilike(like),
                   AuditLog.user_name.ilike(like))
        )
    total   = query.count()
    pages   = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)
    entries = query.order_by(AuditLog.timestamp.desc()).offset((page-1)*PAGE_SIZE).limit(PAGE_SIZE).all()
    entity_types = [r[0] for r in db.session.query(AuditLog.entity_type).distinct().all() if r[0]]
    users    = User.query.filter(User.role.in_(['staff','admin'])).order_by(User.last_name).all()
    filtered = any(v for v in filters.values())
    return render_template('admin/audit_log.html',
        entries=entries, total=total, pages=pages, page=page,
        filters=filters, entity_types=sorted(entity_types),
        users=users, filtered=filtered)


@bp.route('/audit-log/export')
@login_required
def audit_log_export():
    if current_user.email != 'admin@ruffliferetreat.com':
        flash('Access denied.', 'danger')
        return redirect(url_for('admin.dashboard'))
    from app.models import AuditLog
    import csv, io
    from flask import Response
    entries = AuditLog.query.order_by(AuditLog.timestamp.desc()).limit(10000).all()
    output  = io.StringIO()
    writer  = csv.writer(output)
    writer.writerow(['Timestamp','User','Email','Action','Entity Type','Entity ID',
                     'Entity Name','Description','IP Address','Extra'])
    for e in entries:
        writer.writerow([
            e.timestamp.strftime('%Y-%m-%d %H:%M:%S'),
            e.user_name or '', e.user_email or '',
            e.action, e.entity_type or '', e.entity_id or '',
            e.entity_name or '', e.description or '',
            e.ip_address or '', e.extra_data or '',
        ])
    return Response(output.getvalue(), mimetype='text/csv',
        headers={'Content-Disposition': 'attachment;filename=rufflife_audit_log.csv'})


@bp.route('/reports/grooming')
@login_required
@admin_required
def grooming_report():
    """
    Daily Grooming Report — shows boarding guests checking out the day AFTER
    the selected prep date. Selecting 6/17 shows 6/18 pickups so staff know
    what grooming to complete today. Defaults to today → shows tomorrow's pickups.
    """
    from app.models import Boarding, Pet, User, Appointment, ServiceType
    from datetime import date, timedelta, datetime
    import re

    today = date.today()

    # ?date = the PREP date (day staff are doing grooming).
    # report_date = prep_date + 1  (the actual pickup / checkout day).
    date_str = request.args.get('date', '').strip()
    try:
        prep_date = date.fromisoformat(date_str) if date_str else today
    except ValueError:
        prep_date = today
    report_date = prep_date + timedelta(days=1)
    
    # Get all active boardings checking out on the selected date
    checkouts = (Boarding.query
        .filter_by(status='active')
        .filter(Boarding.check_out_date == report_date)
        .order_by(Boarding.check_out_time.asc())
        .all())
    
    # For each boarding, find add-ons from associated appointment notes
    grooming_items = []
    _bsvc = ServiceType.query.filter(ServiceType.name.ilike('%boarding%')).first()
    
    for b in checkouts:
        pet      = Pet.query.get(b.pet_id)
        customer = User.query.get(b.user_id)
        if not pet or not customer:
            continue
        
        addons = []
        notes_src = b.special_notes or ''
        
        if _bsvc:
            appt = (Appointment.query
                .filter_by(pet_id=b.pet_id, service_type_id=_bsvc.id)
                .filter(Appointment.appointment_date == b.check_in_date)
                .order_by(Appointment.id.desc())
                .first())
            if appt and appt.notes:
                notes_src = appt.notes
        
        m = re.search(r'Add-ons?:\s*(.+)', notes_src, re.IGNORECASE)
        if m:
            for item in m.group(1).split(','):
                item = item.strip()
                if item:
                    addons.append(item)
        
        if not addons and b.special_notes:
            m2 = re.search(r'Add-ons?:\s*(.+)', b.special_notes, re.IGNORECASE)
            if m2:
                for item in m2.group(1).split(','):
                    item = item.strip()
                    if item:
                        addons.append(item)
        
        grooming_addons = [a for a in addons if any(
            kw in a.lower() for kw in ['bath', 'nail', 'spa', 'groom']
        )]
        
        if grooming_addons:
            pickup_time = None
            pickup_hour = None
            if b.check_out_time:
                try:
                    # If it's a time/datetime object, format it
                    pickup_time = b.check_out_time.strftime('%I:%M %p')
                    pickup_hour = b.check_out_time.hour
                except AttributeError:
                    # If it's already a string, try to parse and reformat it
                    time_str = str(b.check_out_time).strip()
                    try:
                        # Try parsing as HH:MM:SS or HH:MM (24-hour format)
                        if ':' in time_str:
                            parts = time_str.split(':')
                            hour = int(parts[0])
                            minute = int(parts[1])
                            pickup_hour = hour

                            # Convert to 12-hour format
                            period = 'AM' if hour < 12 else 'PM'
                            display_hour = hour if hour <= 12 else hour - 12
                            if display_hour == 0:
                                display_hour = 12

                            pickup_time = f"{display_hour:02d}:{minute:02d} {period}"
                        else:
                            # If no colon, use as-is
                            pickup_time = time_str
                    except (ValueError, IndexError):
                        # If parsing fails, use the string as-is
                        pickup_time = time_str
                except Exception:
                    # Fallback to string representation
                    pickup_time = str(b.check_out_time)

            grooming_items.append({
                'boarding':     b,
                'pet':          pet,
                'customer':     customer,
                'addons':       grooming_addons,
                'pickup_time':  pickup_time,
                'pickup_hour':  pickup_hour,
                'kennel':       (f'{(b.kennel_type or "Kennel").title()} #{b.kennel_number}'
                                 if b.kennel_number else 'Unassigned'),
                'notes':        b.special_notes or '',
            })
    
    grooming_items.sort(key=lambda x: (
        x['pickup_time'] is None,
        x['pickup_time'] or ''
    ))

    # Early pickup filter — only show pets picked up before 10 AM
    early_only = request.args.get('early', '0') == '1'
    if early_only:
        grooming_items = [i for i in grooming_items
                          if i['pickup_hour'] is not None and i['pickup_hour'] < 10]

    return render_template('admin/grooming_report.html',
                           grooming_items=grooming_items,
                           report_date=report_date,
                           prep_date=prep_date,
                           early_only=early_only,
                           today=today,
                           generated_at=datetime.now().strftime('%B %d, %Y at %I:%M %p'))


# ── RESTORED: delete_customer_photo (lost in full deploy) ────────────────────
@bp.route('/customers/<int:customer_id>/photos/<int:photo_id>/delete', methods=['POST'])
@login_required
@admin_required
def delete_customer_photo(customer_id, photo_id):
    """Delete a photo from a customer's gallery (file + DB record)."""
    from app.models import CustomerPhoto

    photo = CustomerPhoto.query.get_or_404(photo_id)

    # Ensure the photo actually belongs to this customer
    if photo.user_id != customer_id:
        flash('Photo does not belong to this customer.', 'danger')
        return redirect(url_for('admin.customer_detail', customer_id=customer_id))

    # Resolve the stored filename regardless of column naming
    file_ref = (getattr(photo, 'file_path', None)
                or getattr(photo, 'photo_path', None)
                or getattr(photo, 'filename', None))

    if file_ref:
        try:
            full_path = os.path.join('app/static/uploads', file_ref)
            if os.path.exists(full_path):
                os.remove(full_path)
        except Exception:
            pass  # DB record removal still proceeds even if file is gone

    db.session.delete(photo)
    db.session.commit()

    # Audit log
    try:
        from app.audit_service import audit
        audit('customer_photo.deleted', 'customer_photo', photo_id,
              f'Photo #{photo_id}',
              f'Photo #{photo_id} deleted from customer #{customer_id} by '
              f'{current_user.first_name} {current_user.last_name}')
    except Exception:
        pass

    flash('Photo deleted.', 'success')
    return redirect(url_for('admin.customer_detail', customer_id=customer_id))


# ── RESTORED: send_balance_reminder (lost in full deploy) ────────────────────
@bp.route('/customers/<int:customer_id>/send-balance-reminder', methods=['POST'])
@login_required
@admin_required
def send_balance_reminder(customer_id):
    """Send an outstanding balance reminder SMS to a customer."""
    from app.models import Payment, SmsMessage
    from app.sms_service import _normalize_phone
    from twilio.rest import Client
    from flask import current_app

    customer = User.query.get_or_404(customer_id)

    outstanding = Payment.query.filter_by(
        customer_id=customer_id, status='outstanding'
    ).all()
    total = sum(p.amount for p in outstanding)

    if not customer.phone:
        flash('No phone number on file — SMS not sent.', 'danger')
        return redirect(url_for('admin.customer_detail', customer_id=customer_id))

    if total <= 0:
        flash('No outstanding balance to remind about.', 'warning')
        return redirect(url_for('admin.customer_detail', customer_id=customer_id))

    try:
        to_e164     = _normalize_phone(customer.phone)
        from_number = current_app.config.get('TWILIO_PHONE_NUMBER')
        body = (
            f"Hi {customer.first_name}, this is a friendly reminder that you have "
            f"an outstanding balance of ${total:.2f} with Ruff Life Retreat. "
            f"Please contact us at {current_app.config.get('BUSINESS_PHONE', '(912) 648-2295')} "
            f"at your earliest convenience. Thank you!"
        )
        client  = Client(current_app.config.get('TWILIO_ACCOUNT_SID'),
                         current_app.config.get('TWILIO_AUTH_TOKEN'))
        message = client.messages.create(body=body, from_=from_number, to=to_e164)

        log = SmsMessage(
            user_id     = customer.id,
            direction   = 'outbound',
            from_number = from_number,
            to_number   = to_e164,
            body        = body,
            twilio_sid  = message.sid,
            is_read     = True
        )
        db.session.add(log)
        db.session.commit()
        flash(f'Balance reminder sent to {customer.first_name} for ${total:.2f}.', 'success')
    except Exception as e:
        current_app.logger.error(f'Balance reminder SMS failed: {e}')
        flash(f'Failed to send reminder: {e}', 'danger')

    return redirect(request.referrer or url_for('admin.customer_detail', customer_id=customer_id))


@bp.route('/customer/<int:customer_id>/waiver-reset', methods=['POST'])
@login_required
@admin_required
def customer_waiver_reset(customer_id):
    """Clear a customer's waiver acceptance so they must re-sign."""
    customer = User.query.get_or_404(customer_id)
    customer.waiver_accepted    = False
    customer.waiver_accepted_at = None
    db.session.commit()
    flash(f'Waiver acceptance cleared for {customer.first_name} {customer.last_name}. '
          'They will need to re-sign the next time they log in.', 'success')
    return redirect(url_for('admin.customer_detail', customer_id=customer_id))


@bp.route('/customer/<int:customer_id>/waiver-accept', methods=['POST'])
@login_required
@admin_required
def customer_waiver_accept(customer_id):
    """Mark a customer's waiver as accepted on behalf of staff (e.g. paper waiver collected)."""
    from datetime import datetime as _dt
    customer = User.query.get_or_404(customer_id)
    customer.waiver_accepted    = True
    customer.waiver_accepted_at = _dt.now()
    db.session.commit()
    flash(f'Waiver marked as accepted for {customer.first_name} {customer.last_name}.', 'success')
    return redirect(url_for('admin.customer_detail', customer_id=customer_id))
