"""
vaccination_alerts.py
Checks for expiring vaccinations and sends SMS alerts to staff and customers.

Triggered two ways:
  1. Windows Task Scheduler (daily) — runs this script directly
  2. Admin panel on-demand button — calls run_vaccination_check() via Flask route

Place this file at: C:\RuffLifeRetreat\app\vaccination_alerts.py
"""

import logging
from datetime import date

logger = logging.getLogger(__name__)

# Alert thresholds in days
ALERT_THRESHOLDS = [30, 7]


def get_expiring_vaccinations(app):
    """
    Query all vaccinations expiring within the alert thresholds.
    Returns a dict keyed by threshold: {30: [...], 7: [...]}
    Eager-loads pet and owner to avoid detached instance errors outside session.
    """
    from app.models import VaccinationRecord, Pet
    from sqlalchemy.orm import joinedload

    with app.app_context():
        results = {threshold: [] for threshold in ALERT_THRESHOLDS}
        today = date.today()

        records = (VaccinationRecord.query
                   .options(
                       joinedload(VaccinationRecord.pet)
                       .joinedload(Pet.owner)
                   )
                   .filter(VaccinationRecord.expiration_date >= today)
                   .all())

        # Build serialisable dicts so data survives outside the session
        serialised = []
        for record in records:
            pet   = record.pet
            owner = pet.owner if pet else None
            serialised.append({
                'id':              record.id,
                'vaccine_name':    record.vaccine_name,
                'expiration_date': record.expiration_date,
                'days_left':       record.days_until_expiration,
                'pet_name':        pet.name if pet else 'Unknown',
                'owner_name':      f'{owner.first_name} {owner.last_name}' if owner else 'Unknown',
                'owner_phone':     owner.phone if owner else None,
                'owner_id':        owner.id if owner else None,
                'owner_first':     owner.first_name if owner else '',
                'sms_opt_in':      getattr(owner, 'sms_opt_in', False) if owner else False,
            })

        for item in serialised:
            for threshold in ALERT_THRESHOLDS:
                if item['days_left'] == threshold:
                    results[threshold].append(item)

        return results


def send_staff_alert(app, threshold, records):
    """Send a single batched SMS to staff listing all expiring vaccinations."""
    if not records:
        return

    with app.app_context():
        from app.sms_service import _send

        lines = [f"⚠️ Vaccinations expiring in {threshold} days:\n"]
        for rec in records:
            lines.append(
                f"• {rec['pet_name']} ({rec['owner_name']}) — "
                f"{rec['vaccine_name']} expires {rec['expiration_date'].strftime('%m/%d/%Y')}"
            )

        body  = '\n'.join(lines)
        body += f"\n\nView details: {app.config.get('BUSINESS_DOMAIN', 'rufflife.app')}/admin/vaccinations/expiring"

        staff_phones = app.config.get('STAFF_ALERT_PHONES', [])
        for phone in staff_phones:
            try:
                _send(phone, body)
            except Exception as e:
                logger.error(f'Failed to send staff vaccination alert to {phone}: {e}')


def send_customer_alerts(app, threshold, records):
    """Send individual SMS alerts to each pet owner."""
    if not records:
        return

    with app.app_context():
        from app.sms_service import _send

        # Group by owner so one customer with multiple pets gets one message
        owner_records = {}
        for rec in records:
            if not rec['owner_phone'] or not rec['sms_opt_in']:
                continue
            owner_records.setdefault(rec['owner_id'], [])
            owner_records[rec['owner_id']].append(rec)

        business = app.config.get('BUSINESS_NAME', 'Ruff Life Retreat')

        for owner_id, recs in owner_records.items():
            first_name = recs[0]['owner_first']
            phone      = recs[0]['owner_phone']

            if len(recs) == 1:
                rec  = recs[0]
                body = (
                    f"Hi {first_name}! 🐾 This is a reminder that "
                    f"{rec['pet_name']}'s {rec['vaccine_name']} vaccination expires in "
                    f"{threshold} days ({rec['expiration_date'].strftime('%m/%d/%Y')}). "
                    f"Please schedule a vet visit soon. — {business}"
                )
            else:
                pet_lines = ', '.join(
                    f"{r['pet_name']}'s {r['vaccine_name']}" for r in recs
                )
                body = (
                    f"Hi {first_name}! 🐾 Reminder from {business}: "
                    f"the following vaccinations expire in {threshold} days: {pet_lines}. "
                    f"Please schedule vet visits soon."
                )

            try:
                _send(phone, body, user_id=owner_id)
            except Exception as e:
                logger.error(f'Failed to send vaccination alert to owner {owner_id}: {e}')


def run_vaccination_check(app):
    """
    Main entry point. Runs all threshold checks and sends all alerts.
    Returns a summary dict for use in admin panel responses.
    """
    summary = {}

    with app.app_context():
        expiring = get_expiring_vaccinations(app)

        for threshold, records in expiring.items():
            send_staff_alert(app, threshold, records)
            send_customer_alerts(app, threshold, records)
            summary[threshold] = len(records)
            logger.info(f'Vaccination alert: {len(records)} records expiring in {threshold} days — alerts sent.')

    return summary


# ---------------------------------------------------------------------------
# Standalone entry point for Windows Task Scheduler
# ---------------------------------------------------------------------------
if __name__ == '__main__':
    import sys
    import os

    # Add the project root to the path
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

    from app import create_app
    flask_app = create_app()

    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s %(levelname)s %(message)s',
        handlers=[
            logging.FileHandler(r'C:\RuffLifeRetreat\logs\vaccination_alerts.log'),
            logging.StreamHandler()
        ]
    )

    summary = run_vaccination_check(flask_app)
    for threshold, count in summary.items():
        print(f'{threshold}-day alerts: {count} vaccination(s) expiring')