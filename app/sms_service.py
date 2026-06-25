"""
sms_service.py - Twilio SMS Notification Service for Ruff Life Retreat
Place this file at: C:\RuffLifeRetreat\app\sms_service.py
"""

import re
import logging
from flask import current_app

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _normalize_phone(raw: str) -> str | None:
    """Convert a stored phone number to E.164 format (+1XXXXXXXXXX)."""
    if not raw:
        return None
    digits = re.sub(r'\D', '', raw)
    if len(digits) == 10:
        return f'+1{digits}'
    if len(digits) == 11 and digits.startswith('1'):
        return f'+{digits}'
    return None


def _log_outbound(to_phone: str, body: str, twilio_sid: str, user_id=None):
    """Save an outbound message to the SmsMessage table."""
    try:
        from app import db
        from app.models import SmsMessage
        msg = SmsMessage(
            user_id=user_id,
            direction='outbound',
            from_number=current_app.config.get('TWILIO_PHONE_NUMBER', ''),
            to_number=to_phone,
            body=body,
            twilio_sid=twilio_sid,
            is_read=True  # Outbound messages are always read
        )
        db.session.add(msg)
        db.session.commit()
    except Exception as exc:
        logger.error(f'Failed to log outbound SMS: {exc}')


def _send(to_phone: str, body: str, user_id=None) -> bool:
    """Core send — sends via Twilio and logs to DB. Returns True on success."""
    # Check SMS opt-in consent if sending to a known user
    if user_id is not None:
        try:
            from app.models import User
            user = User.query.get(user_id)
            if user and not getattr(user, 'sms_opt_in', True):
                logger.info(f'SMS skipped for user {user_id} — no opt-in consent.')
                return False
        except Exception:
            pass  # If we can't check, allow the send
    try:
        from twilio.rest import Client
        account_sid = current_app.config.get('TWILIO_ACCOUNT_SID')
        auth_token  = current_app.config.get('TWILIO_AUTH_TOKEN')
        from_number = current_app.config.get('TWILIO_PHONE_NUMBER')

        if not all([account_sid, auth_token, from_number]):
            logger.warning('Twilio not fully configured — SMS skipped.')
            return False

        to_e164 = _normalize_phone(to_phone)
        if not to_e164:
            logger.warning(f'Could not normalise phone number: {to_phone!r} — SMS skipped.')
            return False

        client = Client(account_sid, auth_token)
        message = client.messages.create(body=body, from_=from_number, to=to_e164)
        logger.info(f'SMS sent to {to_e164} — SID: {message.sid}')

        _log_outbound(to_e164, body, message.sid, user_id=user_id)
        return True

    except Exception as exc:
        logger.error(f'Failed to send SMS to {to_phone!r}: {exc}')
        return False


def forward_to_staff(customer_name: str, customer_phone: str, message_body: str) -> bool:
    """Forward an inbound customer reply to all configured staff phone numbers."""
    staff_phones = current_app.config.get('STAFF_ALERT_PHONES', [])
    if not staff_phones:
        logger.warning('STAFF_ALERT_PHONES not configured — inbound forward skipped.')
        return False

    body = (
        f"\U0001f4ec New reply from {customer_name} ({customer_phone}):\n"
        f'"{message_body}"\n'
        f"View inbox: https://rufflife.app/admin/inbox"
    )
    # Pass no user_id so staff alerts don't pollute customer threads
    success = False
    for phone in staff_phones:
        if _send(phone, body):
            success = True
    return success


def send_staff_alert(body: str) -> bool:
    """Send an alert message to all configured staff phones (STAFF_ALERT_PHONES)."""
    staff_phones = current_app.config.get('STAFF_ALERT_PHONES', [])
    if not staff_phones:
        # Fallback to single business/support phone
        fallback = current_app.config.get('SUPPORT_PHONE') or current_app.config.get('BUSINESS_PHONE')
        if fallback:
            staff_phones = [fallback]
    if not staff_phones:
        logger.warning('No staff phones configured for alert.')
        return False
    success = False
    for phone in staff_phones:
        if _send(phone, body):
            success = True
    return success


# ---------------------------------------------------------------------------
# Notification Functions
# ---------------------------------------------------------------------------

def send_welcome_sms(user) -> bool:
    if not user.phone:
        return False
    body = (
        f"Welcome to Ruff Life Retreat, {user.first_name}! 🐾 "
        f"Your account is all set. We can't wait to meet your pup! "
        f"Questions? Reply to this message or visit https://rufflife.app."
    )
    return _send(user.phone, body, user_id=user.id)


def send_appointment_confirmed_sms(appointment) -> bool:
    user = appointment.user
    pet  = appointment.pet
    svc  = appointment.service_type
    if not user or not user.phone:
        return False
    date_str = appointment.appointment_date.strftime('%A, %B %d') if appointment.appointment_date else 'your scheduled date'
    time_str = appointment.start_time.strftime('%I:%M %p') if appointment.start_time else ''
    body = (
        f"Hi {user.first_name}! \u2705 Your {svc.name} appointment for {pet.name} "
        f"is confirmed for {date_str}"
        f"{' at ' + time_str if time_str else ''}. "
        f"See you then! \u2014 Ruff Life Retreat"
    )
    return _send(user.phone, body, user_id=user.id)


def send_appointment_cancelled_sms(appointment, reason: str = '') -> bool:
    user = appointment.user
    pet  = appointment.pet
    svc  = appointment.service_type
    if not user or not user.phone:
        return False
    date_str = appointment.appointment_date.strftime('%B %d') if appointment.appointment_date else 'your appointment'
    reason_clause = f' Reason: {reason}.' if reason else ''
    body = (
        f"Hi {user.first_name}, your {svc.name} appointment for {pet.name} "
        f"on {date_str} has been cancelled.{reason_clause} "
        f"Please visit https://rufflife.app to reschedule. \u2014 Ruff Life Retreat"
    )
    return _send(user.phone, body, user_id=user.id)


def send_appointment_reminder_sms(appointment) -> bool:
    user = appointment.user
    pet  = appointment.pet
    svc  = appointment.service_type
    if not user or not user.phone:
        return False
    date_str = appointment.appointment_date.strftime('%A, %B %d') if appointment.appointment_date else 'tomorrow'
    time_str = appointment.start_time.strftime('%I:%M %p') if appointment.start_time else ''
    body = (
        f"Reminder \U0001f436 {pet.name}'s {svc.name} at Ruff Life Retreat is "
        f"tomorrow{' at ' + time_str if time_str else ''}. "
        f"Questions? Reply or call us. See you soon!"
    )
    return _send(user.phone, body, user_id=user.id)


def send_daycare_checkin_sms(attendance) -> bool:
    try:
        enrollment = attendance.enrollment
        pet        = enrollment.pet
        owner      = pet.owner
    except AttributeError:
        logger.warning('Could not resolve owner from attendance record.')
        return False
    if not owner or not owner.phone:
        return False
    time_str = attendance.check_in_time.strftime('%I:%M %p')
    body = (
        f"\U0001f43e {pet.name} has checked in to Ruff Life Retreat daycare at {time_str}. "
        f"We'll send another message at pick-up time!"
    )
    return _send(owner.phone, body, user_id=owner.id)


def send_daycare_checkout_sms(attendance) -> bool:
    try:
        enrollment = attendance.enrollment
        pet        = enrollment.pet
        owner      = pet.owner
    except AttributeError:
        logger.warning('Could not resolve owner from attendance record.')
        return False
    if not owner or not owner.phone:
        return False
    time_str = attendance.check_out_time.strftime('%I:%M %p') if attendance.check_out_time else 'just now'
    body = (
        f"\U0001f43e {pet.name} has checked out of Ruff Life Retreat daycare at {time_str}. "
        f"Hope they had a great day! See you next time. \U0001f436"
    )
    return _send(owner.phone, body, user_id=owner.id)


def send_waitlist_confirmation_sms(waitlist_entry) -> bool:
    if not waitlist_entry.phone:
        return False
    days = [d.capitalize() for d in ['monday','tuesday','wednesday','thursday','friday']
            if getattr(waitlist_entry, d, False)]
    days_str = ', '.join(days) if days else 'your selected days'
    body = (
        f"Hi {waitlist_entry.first_name}! You're on the Ruff Life Retreat daycare waitlist "
        f"for {days_str}. We'll reach out as soon as a spot opens up. "
        f"Questions? Reply here or visit https://rufflife.app. \U0001f43e"
    )
    return _send(waitlist_entry.phone, body)


def send_incident_notification_sms(incident) -> bool:
    try:
        pet   = incident.pet
        owner = pet.owner if pet else None
    except AttributeError:
        return False
    if not owner or not owner.phone:
        return False
    severity_note = ' Please call us as soon as possible.' if incident.severity in ('serious', 'critical') else ''
    body = (
        f"Hi {owner.first_name}, this is Ruff Life Retreat. "
        f"We wanted to let you know that {pet.name} had a {incident.severity} {incident.incident_type} incident today. "
        f"Our team has taken action.{severity_note} "
        f"Reply or call us for details."
    )
    return _send(owner.phone, body, user_id=owner.id)


def send_optin_confirmation_sms(user) -> bool:
    """
    Trigger: immediately after a new customer checks the SMS opt-in box and registers.
    This is the confirmation message TCR requires as proof of opt-in consent.

    Usage:
        from app.sms_service import send_optin_confirmation_sms
        send_optin_confirmation_sms(user)
    """
    if not user.phone or not getattr(user, 'sms_opt_in', False):
        return False

    body = (
        f"You're now subscribed to SMS notifications from Ruff Life Retreat. "
        f"You'll receive appointment confirmations, reminders, and daycare alerts. "
        f"Msg & data rates may apply. Reply STOP to unsubscribe or HELP for help."
    )
    # Use _send directly — bypasses opt-in check since this IS the opt-in confirmation
    return _send(user.phone, body, user_id=user.id)


def send_report_card_sms(report_card) -> bool:
    """
    Trigger: staff sends a completed report card.
    Sends a link to the public tokenized report card page.
    """
    try:
        pet   = report_card.pet
        owner = pet.owner
    except AttributeError:
        return False

    if not owner or not owner.phone:
        return False

    card_type = 'daycare' if report_card.card_type == 'daycare' else 'boarding'
    body = (
        f"\U0001f43e {pet.name}'s {card_type} report card is in! "
        f"See how their day went: https://rufflife.app/report/{report_card.token}"
    )
    return _send(owner.phone, body, user_id=owner.id)