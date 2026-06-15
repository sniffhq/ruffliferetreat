from flask import Blueprint, render_template, request, flash, redirect, url_for, session
from flask_login import current_user
from app import db
from app.models import DaycareWaitlist
from app.sms_service import send_waitlist_confirmation_sms, forward_to_staff
import time
import re

bp = Blueprint('public', __name__)


def is_bot_submission(request, form_loaded_at):
    """
    Check for bot indicators:
    1. Honeypot field filled (bots fill all fields)
    2. Form submitted too fast (< 3 seconds)
    3. Gibberish name detection
    """
    # Check honeypot - if filled, it's a bot
    honeypot = request.form.get('website', '')
    if honeypot:
        print(f"BOT DETECTED: Honeypot filled with '{honeypot}'")
        return True
    
    # Check timing - if form submitted in under 3 seconds, likely a bot
    if form_loaded_at:
        try:
            load_time = float(form_loaded_at)
            elapsed = time.time() - load_time
            if elapsed < 3:
                print(f"BOT DETECTED: Form submitted in {elapsed:.2f} seconds")
                return True
        except (ValueError, TypeError):
            pass
    
    # Check for gibberish names (all lowercase, no vowels pattern, random strings)
    first_name = request.form.get('first_name', '').lower()
    last_name = request.form.get('last_name', '').lower()
    
    # Gibberish detection: consonant clusters without vowels
    gibberish_pattern = re.compile(r'[bcdfghjklmnpqrstvwxyz]{4,}')
    if gibberish_pattern.search(first_name) or gibberish_pattern.search(last_name):
        print(f"BOT DETECTED: Gibberish name '{first_name} {last_name}'")
        return True
    
    return False


@bp.route('/')
def index():
    return render_template('public/index.html')

@bp.route('/boarding')
def boarding():
    return render_template('public/boarding.html')

@bp.route('/grooming')
def grooming():
    return render_template('public/grooming.html')

@bp.route('/daycare')
def daycare():
    return render_template('public/daycare.html')

@bp.route('/about')
def about():
    return render_template('public/about.html')

@bp.route('/privacy')
def privacy():
    return render_template('public/privacy.html')

@bp.route('/terms')
def terms():
    return render_template('public/terms.html')

@bp.route('/gallery')
def gallery():
    from app.models import GalleryPhoto
    photos = GalleryPhoto.query.order_by(GalleryPhoto.created_at.desc()).all()
    return render_template('public/gallery.html', photos=photos)


@bp.route('/estimate/<string:token>')
def view_estimate(token):
    """Public tokenized estimate — shows active/upcoming charges before checkout."""
    from app.models import InvoiceToken, Boarding, DaycareAttendance, DaycareEnrollment, Payment
    from datetime import date, timedelta
    import re

    token_rec = InvoiceToken.query.filter_by(token=token).first_or_404()
    customer  = token_rec.customer
    today     = date.today()

    DAYCARE_MULTI  = 20.00
    DAYCARE_SINGLE = 25.00

    def _boarding_days(b):
        base = (b.check_out_date - b.check_in_date).days
        cout = str(b.check_out_time or '17:00')[:5]
        return base if cout <= '10:00' else base + 1

    def _parse_addon_price(s):
        m = re.search(r'\$(\d+)', s)
        return float(m.group(1)) if m else 0.0

    pet_sections = []
    for pet in sorted(customer.pets, key=lambda p: p.name):
        lines = []

        # Active boardings
        boardings = Boarding.query.filter(
            Boarding.pet_id == pet.id,
            Boarding.status == 'active'
        ).order_by(Boarding.check_in_date.asc()).all()

        for b in boardings:
            days     = _boarding_days(b)
            siblings = Boarding.query.filter_by(
                user_id=b.user_id,
                check_in_date=b.check_in_date,
                check_out_date=b.check_out_date,
            ).filter(Boarding.status == 'active').order_by(Boarding.pet_id.asc()).all()
            is_first = (not siblings) or siblings[0].pet_id == pet.id
            rate     = 40.00 if is_first else 25.00
            amount   = rate * days
            addons   = []

            try:
                from app.models import Appointment as _A, ServiceType as _ST
                _svc = _ST.query.filter(_ST.name.ilike('%boarding%')).first()
                if _svc:
                    _appt = _A.query.filter_by(
                        pet_id=pet.id, user_id=customer.id,
                        service_type_id=_svc.id
                    ).order_by(_A.id.desc()).first()
                    if _appt and _appt.notes:
                        from app.routes.admin import _parse_addons_from_notes
                        addons, _ = _parse_addons_from_notes(_appt.notes)
            except Exception:
                pass

            lines.append({
                'description': f'Boarding — {b.check_in_date.strftime("%b %d")} to {b.check_out_date.strftime("%b %d, %Y")}',
                'detail':      f'{days} day{"s" if days != 1 else ""} @ ${rate:.0f}/day{"  (additional pet)" if not is_first else ""}',
                'amount':      amount,
                'addons':      addons,
                'addon_total': sum(_parse_addon_price(a) for a in addons),
            })

        if lines:
            subtotal = sum(l['amount'] + l['addon_total'] for l in lines)
            pet_sections.append({'pet': pet, 'lines': lines, 'subtotal': subtotal})

    grand_total = sum(s['subtotal'] for s in pet_sections)

    return render_template('public/estimate.html',
        customer=customer,
        pet_sections=pet_sections,
        grand_total=grand_total,
        today=today)


@bp.route('/invoice/<string:token>')
def view_invoice(token):
    """Public tokenized invoice view — no login required."""
    from app.models import InvoiceToken, Boarding, DaycareAttendance, DaycareEnrollment
    from app.models import Payment
    from datetime import date, timedelta
    import re

    token_rec = InvoiceToken.query.filter_by(token=token).first_or_404()
    customer  = token_rec.customer
    today     = date.today()

    DAYCARE_MULTI  = 20.00
    DAYCARE_SINGLE = 25.00

    def _boarding_days(b):
        base = (b.check_out_date - b.check_in_date).days
        cout = str(b.check_out_time or '17:00')[:5]
        return base if cout <= '10:00' else base + 1

    def _parse_addon_price(s):
        m = re.search(r'\$(\d+)', s)
        return float(m.group(1)) if m else 0.0

    pet_sections = []
    for pet in sorted(customer.pets, key=lambda p: p.name):
        lines = []

        boardings = Boarding.query.filter_by(
            pet_id=pet.id, status='completed'
        ).filter(Boarding.payment_id == None).order_by(
            Boarding.check_in_date.asc()
        ).all()

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
            cout     = str(b.check_out_time or '17:00')[:5]
            early    = ' (early checkout — no charge for departure day)' if cout <= '10:00' else ''

            addons = []
            try:
                from app.models import Appointment as _A, ServiceType as _ST
                _svc = _ST.query.filter(_ST.name.ilike('%boarding%')).first()
                if _svc:
                    _appt = _A.query.filter_by(
                        pet_id=pet.id, user_id=customer.id,
                        service_type_id=_svc.id
                    ).order_by(_A.id.desc()).first()
                    if _appt and _appt.notes:
                        from app.routes.admin import _parse_addons_from_notes
                        addons, _ = _parse_addons_from_notes(_appt.notes)
            except Exception:
                pass

            lines.append({
                'description': f'Boarding — {b.check_in_date.strftime("%b %d")} to {b.check_out_date.strftime("%b %d, %Y")}',
                'detail':      f'{days} day{"s" if days != 1 else ""} @ ${rate:.0f}/day{"  (additional pet)" if not is_first else ""}{early}',
                'amount':      amount,
                'addons':      addons,
                'addon_total': sum(_parse_addon_price(a) for a in addons),
            })

        for enr in DaycareEnrollment.query.filter_by(pet_id=pet.id).all():
            attendances = DaycareAttendance.query.filter_by(
                enrollment_id=enr.id
            ).filter(
                DaycareAttendance.check_out_time != None,
                DaycareAttendance.payment_id == None
            ).order_by(DaycareAttendance.check_in_time.asc()).all()

            for att in attendances:
                week_start = att.check_in_time.date() - timedelta(days=att.check_in_time.weekday())
                week_end   = week_start + timedelta(days=6)
                week_count = DaycareAttendance.query.filter(
                    DaycareAttendance.enrollment_id == enr.id,
                    DaycareAttendance.check_in_time >= week_start,
                    DaycareAttendance.check_in_time <= week_end
                ).count()
                rate = enr.special_rate if enr.special_rate else (DAYCARE_MULTI if week_count > 1 else DAYCARE_SINGLE)
                lines.append({
                    'description': f'Daycare — {att.check_in_time.strftime("%b %d, %Y")}',
                    'detail':      f'${rate:.0f}/day',
                    'amount':      rate,
                    'addons':      [],
                    'addon_total': 0,
                })

        if lines:
            subtotal = sum(l['amount'] + l['addon_total'] for l in lines)
            pet_sections.append({'pet': pet, 'lines': lines, 'subtotal': subtotal})

    payments          = Payment.query.filter_by(customer_id=customer.id).order_by(Payment.payment_date.desc()).all()
    total_paid        = sum(p.amount for p in payments if p.status == 'paid')
    total_outstanding = sum(s['subtotal'] for s in pet_sections)
    true_balance      = max(0.0, total_outstanding - total_paid)

    return render_template('public/invoice.html',
        customer=customer,
        pet_sections=pet_sections,
        payments=payments,
        total_paid=total_paid,
        total_outstanding=total_outstanding,
        true_balance=true_balance,
        grand_total=total_outstanding,
        today=today)


@bp.route('/report/<string:token>')
def view_report_card(token):
    """Public tokenized report card view — no login required."""
    from app.models import ReportCard
    card = ReportCard.query.filter_by(token=token).first_or_404()
    return render_template('public/report_card.html', card=card)


@bp.route('/survey/<string:token>', methods=['GET', 'POST'])
def survey(token):
    """Public tokenized satisfaction survey — no login required."""
    from app.models import SurveyResponse
    from datetime import datetime as dt
    survey = SurveyResponse.query.filter_by(token=token).first_or_404()

    if survey.is_complete:
        return render_template('public/survey_thanks.html', survey=survey)

    if request.method == 'POST':
        survey.overall_rating = request.form.get('overall_rating', type=int)
        survey.comm_rating    = request.form.get('comm_rating', type=int)
        survey.recommend      = request.form.get('recommend')
        survey.comments       = request.form.get('comments', '').strip() or None
        survey.submitted_at   = dt.now()
        from app import db
        db.session.commit()
        return render_template('public/survey_thanks.html', survey=survey)

    return render_template('public/survey.html', survey=survey)

@bp.route('/daycare/waitlist', methods=['GET', 'POST'])
def daycare_waitlist():
    """Daycare waitlist form - redirects to registration with pre-filled data"""
    if request.method == 'POST':
        # Bot protection checks
        form_loaded_at = request.form.get('_timestamp', None)
        if is_bot_submission(request, form_loaded_at):
            # Silently reject - don't tell bots why they failed
            flash('Added to waitlist! Check your email for confirmation. Now complete your registration.', 'info')
            return redirect(url_for('auth.register'))
        
        # Get form data
        first_name = request.form.get('first_name')
        last_name = request.form.get('last_name')
        email = request.form.get('email')
        phone = request.form.get('phone')
        monday = request.form.get('monday') == '1'
        wednesday = request.form.get('wednesday') == '1'
        friday = request.form.get('friday') == '1'
        
        # Validate at least one day is selected
        if not (monday or wednesday or friday):
            flash('Please select at least one day you are interested in.', 'warning')
            return redirect(url_for('public.daycare_waitlist'))
        
        # Store waitlist entry in database
        waitlist_entry = DaycareWaitlist(
            first_name=first_name,
            last_name=last_name,
            email=email,
            phone=phone,
            pet_name='',  # Will be filled during registration
            monday=monday,
            wednesday=wednesday,
            friday=friday
        )
        
        db.session.add(waitlist_entry)
        db.session.commit()

        # Send SMS confirmation
        try:
            send_waitlist_confirmation_sms(waitlist_entry)
        except Exception as e:
            print(f"Failed to send waitlist SMS: {e}")

        # Send confirmation email
        from app.email import send_waitlist_confirmation_email
        try:
            send_waitlist_confirmation_email(waitlist_entry)
        except Exception as e:
            print(f"Failed to send waitlist confirmation email: {e}")
        
        # Store data in session for pre-populating registration form
        session['waitlist_data'] = {
            'first_name': first_name,
            'last_name': last_name,
            'email': email,
            'phone': phone,
            'monday': monday,
            'wednesday': wednesday,
            'friday': friday
        }
        
        flash('Added to waitlist! Check your email for confirmation. Now complete your registration.', 'info')
        return redirect(url_for('auth.register'))
    
    # GET request - show form with timestamp for bot detection
    return render_template('public/daycare_waitlist.html', form_timestamp=time.time())


# ---------------------------------------------------------------------------
# Twilio Inbound SMS Webhook
# Configure this URL in Twilio console:
#   https://rufflife.app/sms/webhook  (HTTP POST)
# ---------------------------------------------------------------------------

@bp.route('/sms/webhook', methods=['POST'])
def sms_webhook():
    """
    Twilio calls this endpoint when a customer replies to an SMS.
    Saves the message to the DB, then forwards to staff phone.
    """
    from twilio.twiml.messaging_response import MessagingResponse
    from app.models import SmsMessage, User
    from app.sms_service import _normalize_phone

    from_number = request.form.get('From', '')
    to_number   = request.form.get('To', '')
    body        = request.form.get('Body', '').strip()
    twilio_sid  = request.form.get('MessageSid', '')

    # Try to match to a customer account by phone number
    user = None
    if from_number:
        # Normalise stored phones and compare
        all_users = User.query.filter(User.phone.isnot(None)).all()
        for u in all_users:
            if _normalize_phone(u.phone) == from_number:
                user = u
                break

    customer_name = f'{user.first_name} {user.last_name}' if user else from_number

    # Save inbound message
    try:
        msg = SmsMessage(
            user_id=user.id if user else None,
            direction='inbound',
            from_number=from_number,
            to_number=to_number,
            body=body,
            twilio_sid=twilio_sid,
            is_read=False
        )
        db.session.add(msg)
        db.session.commit()
    except Exception as e:
        print(f'Failed to save inbound SMS: {e}')

    # Forward to staff disabled — staff do not require reply notifications
    forward_to_staff(customer_name, from_number, body)

    # Return empty TwiML — no auto-reply
    resp = MessagingResponse()
    return str(resp), 200, {'Content-Type': 'text/xml'}