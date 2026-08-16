from flask import Blueprint, render_template, request, redirect, url_for, flash, session, current_app
from flask_login import login_user, logout_user, login_required, current_user
from app import db
from app.models import User
from werkzeug.security import generate_password_hash
import time
import re

bp = Blueprint('auth', __name__)

@bp.route('/')
def index():
    if current_user.is_authenticated:
        if current_user.is_admin:
            return redirect(url_for('admin.dashboard'))
        return redirect(url_for('customer.dashboard'))
    import random
    from app.models import SurveyResponse
    from flask import make_response
    hero_url = url_for('static', filename='img/homepage.jpg')
    all_reviews = (SurveyResponse.query
        .filter(SurveyResponse.submitted_at.isnot(None))
        .filter(SurveyResponse.comments.isnot(None))
        .filter(SurveyResponse.overall_rating >= 4)
        .all())
    random.shuffle(all_reviews)
    testimonials = all_reviews[:10]
    resp = make_response(render_template('public/index.html', hero_url=hero_url, testimonials=testimonials))
    resp.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    resp.headers['Pragma'] = 'no-cache'
    return resp

@bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('public.index'))
    
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        user = User.query.filter_by(email=email).first()
        
        if user and user.check_password(password):
            login_user(user, remember=True)
            flash('Welcome back!', 'success')
            if user.role == 'customer':
                if not user.onboarding_complete:
                    return redirect(url_for('customer.onboarding'))
                if not getattr(user, 'waiver_accepted', False):
                    return redirect(url_for('customer.waiver'))
            return redirect(url_for('public.index'))
        
        flash('Invalid email or password', 'danger')
    
    return render_template('auth/login.html')


def is_bot_submission(request, form_loaded_at):
    """
    Check for bot indicators:
    1. Honeypot field filled (bots fill all fields)
    2. Form submitted too fast (< 3 seconds)
    3. Gibberish / randomised name detection
    4. Heavily-dotted email address (bot-generated gmail patterns)
    """
    # 1. Honeypot — if filled, it's a bot
    honeypot = request.form.get('website', '')
    if honeypot:
        print(f"BOT DETECTED: Honeypot filled with '{honeypot}'")
        return True

    # 2. Timing — submitted under 3 seconds
    if form_loaded_at:
        try:
            elapsed = time.time() - float(form_loaded_at)
            if elapsed < 3:
                print(f"BOT DETECTED: Submitted in {elapsed:.2f}s")
                return True
        except (ValueError, TypeError):
            pass

    first_name = request.form.get('first_name', '').strip()
    last_name  = request.form.get('last_name',  '').strip()
    email      = request.form.get('email', '').strip().lower()

    # 3. Name checks
    fn_lower = first_name.lower()
    ln_lower = last_name.lower()

    # 3a. Very long names — real names rarely exceed 20 chars per part
    if len(first_name) > 20 or len(last_name) > 20:
        print(f"BOT DETECTED: Overly long name '{first_name} {last_name}'")
        return True

    # 3b. Mixed-case randomness — alternating caps mid-word (e.g. "BlOzFhfe", "waePYUjo")
    #     Real names capitalise only the first letter.
    #     Exception: Mc/Mac/O' prefixes are legitimate (McEwen, MacDonald, O'Brien).
    mixed_caps = re.compile(r'[a-z][A-Z]|[A-Z][a-z][A-Z]')
    def _strip_name_prefix(name):
        """Remove legitimate prefixes before mixed-case check."""
        for prefix in ("Mac", "Mc", "O'", "O'"):
            if name.startswith(prefix):
                return name[len(prefix):]
        return name
    fn_check = _strip_name_prefix(first_name)
    ln_check = _strip_name_prefix(last_name)
    if mixed_caps.search(fn_check[1:]) or mixed_caps.search(ln_check[1:]):
        print(f"BOT DETECTED: Mixed-case randomised name '{first_name} {last_name}'")
        return True

    # 3c. 7+ consecutive consonants (original check, kept for coverage)
    gibberish = re.compile(r'[^aeiouAEIOU\s\-\']{7,}')
    if gibberish.search(first_name) or gibberish.search(last_name):
        print(f"BOT DETECTED: Consonant cluster in name '{first_name} {last_name}'")
        return True

    # 4. Email — 5+ dots in the local part (e.g. m.a.d.ola.inb.e.n.d.e.ru.t9@gmail.com)
    local_part = email.split('@')[0] if '@' in email else email
    if local_part.count('.') >= 5:
        print(f"BOT DETECTED: Heavily-dotted email '{email}'")
        return True

    return False


@bp.route('/register', methods=['GET', 'POST'])
def register():
    """User registration with waitlist pre-population and bot protection"""
    if current_user.is_authenticated:
        return redirect(url_for('public.index'))
    
    # Get waitlist data from session if available
    waitlist_data = session.get('waitlist_data', None)
    
    if request.method == 'POST':
        # Bot protection checks
        form_loaded_at = request.form.get('_timestamp', None)
        if is_bot_submission(request, form_loaded_at):
            # Silently reject - don't tell bots why they failed
            flash('Registration successful! Check your email for a welcome message.', 'success')
            return redirect(url_for('auth.login'))
        
        email = request.form.get('email')
        password = request.form.get('password')
        
        # Validate password exists
        if not password:
            flash('Password is required', 'danger')
            return redirect(url_for('auth.register'))
        
        # Check if email already registered
        if User.query.filter_by(email=email).first():
            flash('Email already registered', 'danger')
            return redirect(url_for('auth.register'))
        
        # Create new user
        user = User(
            email=email,
            first_name=request.form.get('first_name'),
            last_name=request.form.get('last_name'),
            phone=request.form.get('phone')
        )
        user.set_password(password)

        # Enforce waiver acceptance — must be checked to proceed
        if request.form.get('waiver_accepted') != '1':
            flash('You must read and accept the waiver to create an account.', 'danger')
            return redirect(url_for('auth.register'))

        # Save waiver acceptance
        from datetime import datetime
        user.waiver_accepted    = True
        user.waiver_accepted_at = datetime.now()

        # Save SMS opt-in
        if request.form.get('sms_opt_in') == '1':
            user.sms_opt_in = True

        db.session.add(user)
        db.session.commit()

        # Audit log — self-registration
        try:
            from app.audit_service import audit
            audit('customer.registered', 'customer', user.id,
                  f'{user.first_name} {user.last_name}',
                  f'Customer {user.first_name} {user.last_name} self-registered via portal')
        except Exception:
            pass

        # Send welcome email
        from app.mail_service import send_welcome_email
        try:
            send_welcome_email(user)
        except Exception as e:
            print(f"Failed to send welcome email: {e}")
        
        # Clear waitlist data from session after successful registration
        session.pop('waitlist_data', None)
        
        flash('Registration successful! Check your email for a welcome message.', 'success')
        return redirect(url_for('auth.login'))
    
    # GET request - render form with pre-populated waitlist data and timestamp
    return render_template('auth/register.html', 
                          waitlist_data=waitlist_data,
                          form_timestamp=time.time())

@bp.route('/logout')
@login_required
def logout():
    logout_user()
    flash('You have been logged out.', 'info')
    return redirect(url_for('public.index'))


@bp.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    """Send a password reset link via SMS."""
    if current_user.is_authenticated:
        return redirect(url_for('public.index'))

    if request.method == 'POST':
        phone = request.form.get('phone', '').strip()

        # Normalize phone — strip everything except digits
        digits = re.sub(r'\D', '', phone)
        if len(digits) == 10:
            digits = '1' + digits
        normalized = '+' + digits if not digits.startswith('+') else digits

        user = User.query.filter(
            db.or_(
                User.phone == phone,
                User.phone == digits,
                User.phone == normalized,
            )
        ).first()

        # Always show success — don't reveal whether phone is registered
        if user:
            from app.models import PasswordResetToken
            from datetime import datetime, timedelta
            import secrets

            # Invalidate any existing tokens for this user
            PasswordResetToken.query.filter_by(
                user_id=user.id, used=False
            ).update({'used': True})
            db.session.flush()

            # Create new token — expires in 30 minutes
            token = secrets.token_urlsafe(32)
            reset_token = PasswordResetToken(
                user_id   = user.id,
                token     = token,
                expires_at = datetime.now() + timedelta(minutes=30)
            )
            db.session.add(reset_token)
            db.session.commit()

            # Build reset URL
            domain = current_app.config.get('BUSINESS_DOMAIN', 'rufflife.app')
            reset_url = f'https://{domain}/reset-password/{token}'

            # Send SMS
            try:
                from twilio.rest import Client as TwilioClient
                client = TwilioClient(
                    current_app.config['TWILIO_ACCOUNT_SID'],
                    current_app.config['TWILIO_AUTH_TOKEN']
                )
                client.messages.create(
                    body=(
                        f'Hi {user.first_name}, you requested a password reset for your '
                        f'{current_app.config.get("BUSINESS_NAME", "Ruff Life Retreat")} account.\n\n'
                        f'Reset your password here (link expires in 30 minutes):\n{reset_url}\n\n'
                        f'If you did not request this, ignore this message.'
                    ),
                    from_=current_app.config['TWILIO_PHONE_NUMBER'],
                    to=normalized
                )
            except Exception as e:
                print(f'Password reset SMS failed: {e}')

        flash(
            'If that phone number is on file, you\'ll receive a reset link via SMS shortly.',
            'info'
        )
        return redirect(url_for('auth.login'))

    return render_template('auth/forgot_password.html')


@bp.route('/reset-password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    """Handle password reset via token."""
    if current_user.is_authenticated:
        return redirect(url_for('public.index'))

    from app.models import PasswordResetToken
    from datetime import datetime

    reset_token = PasswordResetToken.query.filter_by(
        token=token, used=False
    ).first()

    # Validate token
    if not reset_token or reset_token.expires_at < datetime.now():
        flash('This reset link is invalid or has expired. Please request a new one.', 'danger')
        return redirect(url_for('auth.forgot_password'))

    if request.method == 'POST':
        password  = request.form.get('password', '')
        password2 = request.form.get('password2', '')

        if len(password) < 8:
            flash('Password must be at least 8 characters.', 'danger')
            return render_template('auth/reset_password.html', token=token)

        if password != password2:
            flash('Passwords do not match.', 'danger')
            return render_template('auth/reset_password.html', token=token)

        # Update password and mark token used
        reset_token.user.set_password(password)
        reset_token.used = True
        db.session.commit()

        flash('Your password has been reset. Please log in.', 'success')
        return redirect(url_for('auth.login'))

    return render_template('auth/reset_password.html', token=token)