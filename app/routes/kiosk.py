import re
import logging
from flask import Blueprint, render_template, request, flash, redirect, url_for
from app import db
from app.models import Pet, User, DaycareEnrollment, DaycareAttendance
from datetime import datetime

bp = Blueprint('kiosk', __name__, url_prefix='/kiosk')
logger = logging.getLogger(__name__)


@bp.route('/', methods=['GET', 'POST'])
def index():
    """Single page for check-in and check-out — supports multiple pets per submission."""
    if request.method == 'POST':
        phone      = request.form.get('phone', '').strip()
        pet_names  = [n.strip() for n in request.form.get('pet_names', '').split(',') if n.strip()]
        action     = request.form.get('action')

        if not phone or not pet_names:
            flash('Please look up a phone number and select at least one pet.', 'warning')
            return redirect(url_for('kiosk.index'))

        phone_digits = re.sub(r'\D', '', phone)

        # Find owner by phone
        owner = None
        for u in User.query.filter(User.phone.isnot(None)).all():
            if re.sub(r'\D', '', u.phone or '') == phone_digits:
                owner = u
                break

        if not owner:
            flash(f'No account found for phone number "{phone}". Please contact staff.', 'danger')
            return redirect(url_for('kiosk.index'))

        # Process each selected pet
        successes = []
        warnings  = []

        for pet_name in pet_names:
            pet = Pet.query.filter(
                Pet.user_id == owner.id,
                db.func.lower(Pet.name) == pet_name.lower(),
                Pet.is_active == True
            ).first()

            if not pet:
                warnings.append(f'No pet named "{pet_name}" found.')
                continue

            enrollment = DaycareEnrollment.query.filter_by(
                pet_id=pet.id, active=True
            ).first()

            if not enrollment:
                warnings.append(f'{pet.name} is not enrolled in daycare.')
                continue

            if action == 'checkin':
                ok, msg = _do_checkin(enrollment, pet)
            elif action == 'checkout':
                ok, msg = _do_checkout(enrollment, pet)
            else:
                warnings.append('Invalid action.')
                continue

            (successes if ok else warnings).append(msg)

        # Flash combined results
        if successes:
            flash(' · '.join(successes), 'success')
        for w in warnings:
            flash(w, 'warning')

        return redirect(url_for('kiosk.index'))

    return render_template('kiosk/index.html')


@bp.route('/lookup-pets')
def lookup_pets():
    """AJAX: return daycare-enrolled pets for a given phone number."""
    from flask import jsonify

    phone = request.args.get('phone', '').strip()
    phone_digits = re.sub(r'\D', '', phone)

    if len(phone_digits) < 10:
        return jsonify({'error': 'Enter a full phone number', 'pets': []})

    owner = None
    for u in User.query.filter(User.phone.isnot(None)).all():
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


# ── Internal helpers — return (success: bool, message: str) ──────────────────

def _do_checkin(enrollment, pet):
    """Check in one pet. Returns (ok, message)."""
    today = datetime.now().date()

    existing = DaycareAttendance.query.filter(
        DaycareAttendance.enrollment_id == enrollment.id,
        db.func.date(DaycareAttendance.check_in_time) == today,
        DaycareAttendance.check_out_time == None
    ).first()

    if existing:
        return False, f'{pet.name} is already checked in'

    check_in_time = datetime.now()
    attendance = DaycareAttendance(
        enrollment_id=enrollment.id,
        check_in_time=check_in_time
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
        group  = (PlayGroup.query.filter_by(size_category=size, temperament=temp,    active=True).first()
               or PlayGroup.query.filter_by(size_category=size, temperament='mixed', active=True).first()
               or PlayGroup.query.filter_by(size_category=size,                      active=True).first())
        if group:
            DaycareAttendance.query.filter_by(id=attendance_id).update({'play_group_id': group.id})
            db.session.commit()
    except Exception as e:
        db.session.rollback()
        logger.error(f'Play group auto-assign failed for {pet.name}: {e}')

    return True, f'✓ {pet.name} checked in at {check_in_time.strftime("%I:%M %p")}'


def _do_checkout(enrollment, pet):
    """Check out one pet. Returns (ok, message)."""
    attendance = DaycareAttendance.query.filter(
        DaycareAttendance.enrollment_id == enrollment.id,
        DaycareAttendance.check_out_time == None
    ).order_by(DaycareAttendance.check_in_time.desc()).first()

    if not attendance:
        return False, f'{pet.name} is not currently checked in'

    check_out_time = datetime.now()
    attendance.check_out_time = check_out_time
    db.session.commit()

    # Milestone survey check
    try:
        from app.survey_service import check_daycare_milestone
        if pet.owner:
            check_daycare_milestone(pet.owner.id)
    except Exception as e:
        logger.error(f'Survey milestone check failed for {pet.name}: {e}')

    duration = (check_out_time - attendance.check_in_time).total_seconds() / 3600
    return True, f'✓ {pet.name} checked out ({duration:.1f} hrs)'
