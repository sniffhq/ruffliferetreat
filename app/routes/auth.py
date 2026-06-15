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
    return render_template('index.html')

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
    
    # Check for gibberish names — only flag obvious bot patterns
    # Use a high threshold to avoid false positives on unusual surnames
    first_name = request.form.get('first_name', '').lower()
    last_name  = request.form.get('last_name', '').lower()

    # Only check first names — last names are too varied (German, Slavic, etc.)
    # Flag if first name has 7+ consecutive consonants or is all consonants
    gibberish_pattern = re.compile(r'[^aeiou]{7,}')
    all_consonants    = re.compile(r'^[^aeiou]+$')
    if gibberish_pattern.search(first_name) or (len(first_name) > 3 and all_consonants.search(first_name)):
        print(f"BOT DETECTED: Gibberish first name '{first_name} {last_name}'")
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

        # Save waiver acceptance if signed during registration
        if request.form.get('waiver_accepted') == '1':
            from datetime import datetime
            user.waiver_accepted    = True
            user.waiver_accepted_at = datetime.now()

        db.session.add(user)
        db.session.commit()
        
        # Send welcome email
        from app.email import send_welcome_email
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