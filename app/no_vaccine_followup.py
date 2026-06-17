"""
no_vaccine_followup.py
Checks for pets that were added 1+ day ago but have no vaccination records
on file, and sends the owner a friendly SMS nudge to upload them.

Triggered two ways:
  1. Windows Task Scheduler (daily) — runs this script directly
  2. Admin panel on-demand button — calls run_no_vaccine_check() via Flask route

Place this file at: C:\\RuffLifeRetreat\\app\\no_vaccine_followup.py
"""

import logging
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

DAYS_THRESHOLD = 1
NUDGE_MARKER   = '[no-vaccine-nudge]'


def get_pets_without_vaccines(app):
    """
    Returns a list of (pet, owner) tuples where:
    - Pet was created at least DAYS_THRESHOLD days ago
    - Pet has no vaccination records
    - Owner has a phone number on file
    - Owner has not already received a nudge for this pet
    """
    from app.models import Pet, VaccinationRecord, SmsMessage

    with app.app_context():
        cutoff = datetime.now() - timedelta(days=DAYS_THRESHOLD)

        pets = (Pet.query
                .filter_by(is_active=True)
                .filter(Pet.created_at <= cutoff)
                .all())

        results = []
        for pet in pets:
            owner = pet.owner
            if not owner or not owner.phone:
                continue

            # Skip if pet already has at least one vaccination record
            if pet.vaccination_records:
                continue

            # Skip if we've already sent the nudge for this pet
            marker = f'{NUDGE_MARKER}:{pet.id}:'
            already_sent = SmsMessage.query.filter(
                SmsMessage.user_id   == owner.id,
                SmsMessage.direction == 'outbound',
                SmsMessage.body.like(f'%{marker}%')
            ).first()
            if already_sent:
                continue

            results.append((pet, owner))

        return results


def send_nudge(app, pet, owner):
    """Send the no-vaccine nudge SMS for a specific pet."""
    from app.models import SmsMessage
    from app import db

    with app.app_context():
        try:
            from twilio.rest import Client
            from app.sms_service import _normalize_phone

            account_sid = app.config.get('TWILIO_ACCOUNT_SID')
            auth_token  = app.config.get('TWILIO_AUTH_TOKEN')
            from_number = app.config.get('TWILIO_PHONE_NUMBER')
            business    = app.config.get('BUSINESS_NAME', 'Ruff Life Retreat')
            to_e164     = _normalize_phone(owner.phone)

            if not to_e164:
                logger.warning(f'Skipping {owner.email} — could not normalise phone {owner.phone}')
                return False

            # Marker includes pet ID so each pet gets its own unique nudge tracking
            marker = f'{NUDGE_MARKER}:{pet.id}:'

            body = (
                f"Hi {owner.first_name}! Just a reminder that {pet.name}'s vaccination "
                f"records haven't been uploaded to their {business} profile yet. "
                f"Current Rabies, DHPP, and Bordetella records are required before "
                f"{pet.name} can attend daycare or boarding. "
                f"Log in at rufflife.app to upload them. "
                f"Questions? Just reply! {marker}"
            )

            client  = Client(account_sid, auth_token)
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
            logger.info(f'No-vaccine nudge sent for {pet.name} to {owner.first_name} {owner.last_name}')
            return True

        except Exception as e:
            logger.error(f'Failed to send vaccine nudge for pet {pet.id}: {e}')
            return False


def run_no_vaccine_check(app):
    """
    Main entry point — find eligible pets and send nudges.
    Returns a summary dict.
    """
    pets = get_pets_without_vaccines(app)
    sent    = 0
    skipped = 0

    for pet, owner in pets:
        success = send_nudge(app, pet, owner)
        if success:
            sent += 1
        else:
            skipped += 1

    summary = {'sent': sent, 'skipped': skipped, 'total': len(pets)}
    logger.info(f'No-vaccine followup complete: {summary}')
    return summary


# ── Standalone execution (Task Scheduler) ────────────────────────────────────
if __name__ == '__main__':
    import os
    import sys

    log_path = os.path.join(os.path.dirname(__file__), '..', 'logs', 'no_vaccine_followup.log')
    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    logging.basicConfig(
        level    = logging.INFO,
        format   = '%(asctime)s %(levelname)s %(message)s',
        handlers = [
            logging.FileHandler(log_path),
            logging.StreamHandler(sys.stdout),
        ]
    )

    sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
    from app import create_app
    flask_app = create_app()

    summary = run_no_vaccine_check(flask_app)
    print(f"Done — sent={summary['sent']} skipped={summary['skipped']} total={summary['total']}")
