from flask import Blueprint, render_template, request, redirect, url_for, flash, session
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
    
    # Check for gibberish names (all lowercase, no vowels pattern, random strings)
    first_name = request.form.get('first_name', '').lower()
    last_name = request.form.get('last_name', '').lower()
    
    # Gibberish detection: consonant clusters without vowels
    gibberish_pattern = re.compile(r'^[^aeiou]{4,}|[^aeiou]{5,}')
    if gibberish_pattern.search(first_name) or gibberish_pattern.search(last_name):
        print(f"BOT DETECTED: Gibberish name '{first_name} {last_name}'")
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
