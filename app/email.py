from flask import render_template, current_app
from flask_mail import Message
from app import mail
from threading import Thread

def send_async_email(app, msg):
    """Send email asynchronously"""
    with app.app_context():
        mail.send(msg)

def send_email(subject, recipients, text_body, html_body):
    """Send email with both text and HTML versions"""
    msg = Message(subject, recipients=recipients)
    msg.body = text_body
    msg.html = html_body
    
    Thread(target=send_async_email, 
           args=(current_app._get_current_object(), msg)).start()

def send_welcome_email(user):
    """Send welcome email to new user"""
    subject = f"Welcome to {current_app.config['BUSINESS_NAME']}!"
    
    text_body = f"""
Hello {user.first_name},

Welcome to {current_app.config['BUSINESS_NAME']}! We're excited to have you and your furry friend join our family.

Your account has been successfully created with the email: {user.email}

What's Next?
- Add your pet's information to your profile
- Book your first appointment for boarding, grooming, or daycare
- Upload vaccination records and photos

If you have any questions, contact us:
Phone: {current_app.config['BUSINESS_PHONE']}
Email: {current_app.config['MAIL_DEFAULT_SENDER']}

Thank you for choosing {current_app.config['BUSINESS_NAME']}!

Best regards,
The {current_app.config['BUSINESS_NAME']} Team
"""
    
    html_body = render_template('emails/welcome.html', user=user)
    send_email(subject, [user.email], text_body, html_body)

def send_appointment_approved_email(appointment):
    """Send email when appointment is approved"""
    user = appointment.user
    pet = appointment.pet
    service = appointment.service_type
    
    subject = f"Appointment Confirmed - {service.name} for {pet.name}"
    
    text_body = f"""
Hello {user.first_name},

Your appointment has been confirmed!

Details:
- Service: {service.name}
- Pet: {pet.name}
- Date: {appointment.appointment_date.strftime('%A, %B %d, %Y')}
- Time: {appointment.start_time.strftime('%I:%M %p')}

Please arrive 5-10 minutes early. Contact us with any questions.

Best regards,
The {current_app.config['BUSINESS_NAME']} Team
"""
    
    html_body = render_template('emails/appointment_approved.html', 
                                appointment=appointment, user=user, pet=pet, service=service)
    send_email(subject, [user.email], text_body, html_body)

def send_appointment_cancelled_email(appointment):
    """Send email when appointment is cancelled"""
    user = appointment.user
    pet = appointment.pet
    service = appointment.service_type
    
    subject = f"Appointment Cancelled - {service.name} for {pet.name}"
    
    text_body = f"""
Hello {user.first_name},

Your appointment has been cancelled.

Cancelled Appointment:
- Service: {service.name}
- Pet: {pet.name}
- Date: {appointment.appointment_date.strftime('%A, %B %d, %Y')}
- Time: {appointment.start_time.strftime('%I:%M %p')}

Contact us to reschedule: {current_app.config['BUSINESS_PHONE']}

Best regards,
The {current_app.config['BUSINESS_NAME']} Team
"""
    
    html_body = render_template('emails/appointment_cancelled.html', 
                                appointment=appointment, user=user, pet=pet, service=service)
    send_email(subject, [user.email], text_body, html_body)

def send_waitlist_confirmation_email(waitlist_entry):
    """Send confirmation email for waitlist submission"""
    subject = f"Daycare Waitlist Confirmation - {current_app.config['BUSINESS_NAME']}"
    
    days = []
    if waitlist_entry.monday:
        days.append('Monday')
    if waitlist_entry.wednesday:
        days.append('Wednesday')
    if waitlist_entry.friday:
        days.append('Friday')
    days_text = ', '.join(days)
    
    text_body = f"""
Hello {waitlist_entry.first_name},

Thank you for joining our daycare waitlist!

Days Interested: {days_text}

We'll contact you at {waitlist_entry.email} or {waitlist_entry.phone} when spots are available.

Best regards,
The {current_app.config['BUSINESS_NAME']} Team
"""
    
    html_body = render_template('emails/waitlist_confirmation.html', 
                                entry=waitlist_entry, days_text=days_text)
    send_email(subject, [waitlist_entry.email], text_body, html_body)


def send_password_reset_email(user, token):
    """Send a password reset link to the customer's email address."""
    reset_url = f"https://rufflife.app/reset-password/{token}"
    subject   = f"Reset Your {current_app.config['BUSINESS_NAME']} Password"

    text_body = f"""Hi {user.first_name},

We received a request to reset your {current_app.config['BUSINESS_NAME']} password.

Reset your password here: {reset_url}

This link expires in 1 hour. If you didn't request this, you can safely ignore this email.

— {current_app.config['BUSINESS_NAME']}
{current_app.config['BUSINESS_ADDRESS']}
{current_app.config['BUSINESS_PHONE']} | rufflife.app
"""

    html_body = f"""<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"></head>
<body style="margin:0;padding:0;background:#f0f2f5;font-family:Arial,sans-serif;">
  <div style="max-width:560px;margin:40px auto;background:white;border-radius:16px;overflow:hidden;box-shadow:0 4px 20px rgba(0,0,0,0.08);">
    <div style="background:#1a1a2e;padding:32px 40px;text-align:center;">
      <div style="font-size:2rem;margin-bottom:8px;">🐾</div>
      <div style="color:#FFC107;font-size:1.4rem;font-weight:800;letter-spacing:1px;">{current_app.config['BUSINESS_NAME'].upper()}</div>
      <div style="color:rgba(255,255,255,0.6);font-size:0.85rem;margin-top:4px;">Password Reset Request</div>
    </div>
    <div style="padding:36px 40px;">
      <p style="font-size:1rem;color:#333;margin-top:0;">Hi {user.first_name},</p>
      <p style="color:#555;line-height:1.6;">
        We received a request to reset the password for your {current_app.config['BUSINESS_NAME']} account.
        Click the button below to choose a new password.
      </p>
      <div style="text-align:center;margin:32px 0;">
        <a href="{reset_url}"
           style="background:#FFC107;color:#1a1a2e;padding:14px 36px;border-radius:8px;
                  text-decoration:none;font-weight:800;font-size:1rem;display:inline-block;">
          Reset My Password
        </a>
      </div>
      <p style="color:#888;font-size:0.85rem;line-height:1.6;">
        This link will expire in <strong>1 hour</strong>. If you did not request a password reset,
        you can safely ignore this email — your password will not be changed.
      </p>
      <p style="color:#888;font-size:0.8rem;word-break:break-all;">
        Or copy this link: <a href="{reset_url}" style="color:#0d6efd;">{reset_url}</a>
      </p>
    </div>
    <div style="background:#f8f9fa;padding:20px 40px;text-align:center;border-top:1px solid #eee;">
      <p style="color:#aaa;font-size:0.8rem;margin:0;">
        {current_app.config['BUSINESS_NAME']} &nbsp;|&nbsp; {current_app.config['BUSINESS_ADDRESS']}<br>
        {current_app.config['BUSINESS_PHONE']} &nbsp;|&nbsp; rufflife.app
      </p>
    </div>
  </div>
</body>
</html>"""

    send_email(subject, [user.email], text_body, html_body)