"""
no_pet_followup.py
Checks for customers who registered 3+ days ago but have not added a pet,
and sends them a friendly SMS nudge to complete their profile.

Triggered two ways:
  1. Windows Task Scheduler (daily) — runs this script directly
  2. Admin panel on-demand button — calls run_no_pet_check() via Flask route

Place this file at: C:\\RuffLifeRetreat\\app\\no_pet_followup.py
"""

import logging
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

# How many days after registration before sending the nudge
DAYS_THRESHOLD = 3

# Only send the nudge once (track by checking SMS log)
NUDGE_MARKER = '[no-pet-nudge]'


def get_customers_without_pets(app):
    """
    Returns customers who:
    - Registered at least DAYS_THRESHOLD days ago
    - Have no active pets
    - Have a phone number on file
    - Have not already received this nudge SMS
    """
    from app.models import User, Pet, SmsMessage

    with app.app_context():
        cutoff = datetime.now() - timedelta(days=DAYS_THRESHOLD)

        customers = (User.query
                     .filter_by(role='customer', is_active=True)
                     .filter(User.created_at <= cutoff)
                     .filter(User.phone.isnot(None))
                     .all())

        results = []
        for customer in customers:
            # Skip if they already have at least one active pet
            has_pets = any(p.is_active for p in customer.pets)
            if has_pets:
                continue

            # Skip if we've already sent the nudge
            already_sent = SmsMessage.query.filter(
                SmsMessage.user_id  == customer.id,
                SmsMessage.direction == 'outbound',
                SmsMessage.body.like(f'%{NUDGE_MARKER}%')
            ).first()
            if already_sent:
                continue

            results.append(customer)

        return results


def send_nudge(app, customer):
    """Send the no-pet nudge SMS to a single customer."""
    from app.models import SmsMessage
    from app import db
    from flask import current_app

    with app.app_context():
        try:
            from twilio.rest import Client
            from app.sms_service import _normalize_phone

            account_sid = app.config.get('TWILIO_ACCOUNT_SID')
            auth_token  = app.config.get('TWILIO_AUTH_TOKEN')
            from_number = app.config.get('TWILIO_PHONE_NUMBER')
            business    = app.config.get('BUSINESS_NAME', 'Ruff Life Retreat')
            to_e164     = _normalize_phone(customer.phone)

            if not to_e164:
                logger.warning(f'Skipping {customer.email} — could not normalise phone {customer.phone}')
                return False

            body = (
                f"Hi {customer.first_name}! Welcome to {business}. "
                f"We noticed you haven't added a pet to your account yet. "
                f"Log in at rufflife.app to add your pet and get started with daycare or boarding. "
                f"Questions? Just reply to this message! {NUDGE_MARKER}"
            )

            client  = Client(account_sid, auth_token)
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
            logger.info(f'No-pet nudge sent to {customer.first_name} {customer.last_name} ({customer.email})')
            return True

        except Exception as e:
            logger.error(f'Failed to send nudge to {customer.id}: {e}')
            return False


def run_no_pet_check(app):
    """
    Main entry point — find eligible customers and send nudges.
    Returns a summary dict.
    """
    customers = get_customers_without_pets(app)
    sent    = 0
    skipped = 0

    for customer in customers:
        success = send_nudge(app, customer)
        if success:
            sent += 1
        else:
            skipped += 1

    summary = {'sent': sent, 'skipped': skipped, 'total': len(customers)}
    logger.info(f'No-pet followup complete: {summary}')
    return summary


# ── Standalone execution (Task Scheduler) ────────────────────────────────────
if __name__ == '__main__':
    import os
    import sys

    log_path = os.path.join(os.path.dirname(__file__), '..', 'logs', 'no_pet_followup.log')
    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    logging.basicConfig(
        level    = logging.INFO,
        format   = '%(asctime)s %(levelname)s %(message)s',
        handlers = [
            logging.FileHandler(log_path),
            logging.StreamHandler(sys.stdout),
        ]
    )

    # Bootstrap Flask app
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
    from app import create_app
    flask_app = create_app()

    summary = run_no_pet_check(flask_app)
    print(f"Done — sent={summary['sent']} skipped={summary['skipped']} total={summary['total']}")