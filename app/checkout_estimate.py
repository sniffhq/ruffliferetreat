"""
checkout_estimate.py
On the morning of a pet's scheduled checkout day, automatically sends the
owner an estimated balance SMS so they know what to expect at pickup.

Runs daily at 7:00 AM via Windows Task Scheduler.
Only fires for active boarding reservations checking out TODAY.
Will not send duplicate estimates (tracked via SMS log marker).

Place this file at: C:\\RuffLifeRetreat\\app\\checkout_estimate.py
"""

import logging
import re
from datetime import datetime, timedelta, date

logger = logging.getLogger(__name__)

MARKER = '[checkout-estimate]'


def get_checkouts_today(app):
    """
    Returns all active Boarding records whose check_out_date is today
    and whose owner has not already received an estimate SMS today.
    """
    from app.models import Boarding, SmsMessage

    with app.app_context():
        today = date.today()

        boardings = (Boarding.query
                     .filter_by(status='active')
                     .filter(Boarding.check_out_date == today)
                     .all())

        results = []
        for b in boardings:
            owner = b.pet.owner if b.pet else None
            if not owner or not owner.phone:
                continue

            # Skip if we already sent one today
            already_sent = SmsMessage.query.filter(
                SmsMessage.user_id   == owner.id,
                SmsMessage.direction == 'outbound',
                SmsMessage.body.like(f'%{MARKER}%'),
                SmsMessage.created_at >= datetime.combine(today, datetime.min.time())
            ).first()
            if already_sent:
                continue

            results.append(b)

        return results


def calculate_estimate(app, boarding):
    """Calculate estimated total for a single boarding record — boarding only."""
    from app.models import Boarding, Appointment, ServiceType

    with app.app_context():
        def _boarding_days(b):
            base = (b.check_out_date - b.check_in_date).days
            cout = str(b.check_out_time or '17:00')[:5]
            return base if cout <= '10:00' else base + 1

        pet      = boarding.pet
        customer = pet.owner
        total    = 0.0
        lines    = []

        # ── Boarding cost ─────────────────────────────────────────────────
        days     = _boarding_days(boarding)
        siblings = (Boarding.query
                    .filter_by(user_id=boarding.user_id,
                               check_in_date=boarding.check_in_date,
                               check_out_date=boarding.check_out_date)
                    .filter(Boarding.status == 'active')
                    .order_by(Boarding.pet_id.asc()).all())
        is_first = (not siblings) or siblings[0].pet_id == pet.id
        rate     = 40.00 if is_first else 25.00
        amount   = rate * days

        # Add-ons
        addon_total = 0.0
        addon_names = []
        try:
            _svc = ServiceType.query.filter(ServiceType.name.ilike('%boarding%')).first()
            if _svc:
                _appt = (Appointment.query
                         .filter_by(pet_id=pet.id, user_id=customer.id,
                                    service_type_id=_svc.id)
                         .order_by(Appointment.id.desc()).first())
                if _appt and _appt.notes:
                    from app.routes.admin import _parse_addons_from_notes
                    _addons, addon_total = _parse_addons_from_notes(_appt.notes)
                    addon_names = [a.split('(')[0].strip() for a in _addons]
        except Exception as e:
            logger.warning(f'Could not parse add-ons for boarding {boarding.id}: {e}')

        amount += addon_total
        total  += amount

        stay_str  = f'{days} day{"s" if days != 1 else ""}'
        addon_str = f' + {", ".join(addon_names)}' if addon_names else ''
        lines.append(f'{pet.name}: {stay_str} boarding{addon_str} = ${amount:.2f}')

        return total, lines


def send_estimate(app, boarding):
    """Send the checkout-day estimate SMS for a single boarding record."""
    from app.models import SmsMessage, InvoiceToken
    from app import db
    import secrets

    with app.app_context():
        try:
            from twilio.rest import Client
            from app.sms_service import _normalize_phone

            customer    = boarding.pet.owner
            total, lines = calculate_estimate(app, boarding)

            if total <= 0:
                logger.info(f'No estimate amount for boarding {boarding.id}, skipping')
                return False

            # Get or create token for the estimate link
            token_rec = InvoiceToken.query.filter_by(customer_id=customer.id).first()
            if not token_rec:
                token_rec = InvoiceToken(
                    customer_id = customer.id,
                    token       = secrets.token_urlsafe(32)
                )
                db.session.add(token_rec)
                db.session.commit()

            to_e164     = _normalize_phone(customer.phone)
            from_number = app.config.get('TWILIO_PHONE_NUMBER')
            business    = app.config.get('BUSINESS_NAME', 'Ruff Life Retreat')
            link        = f'https://rufflife.app/estimate/{token_rec.token}'

            # Build checkout time string
            cout = str(boarding.check_out_time or '17:00')[:5]
            try:
                cout_fmt = datetime.strptime(cout, '%H:%M').strftime('%I:%M %p').lstrip('0')
            except ValueError:
                cout_fmt = '5:00 PM'

            body = (
                f"Good morning {customer.first_name}! {boarding.pet.name} is scheduled "
                f"to check out today by {cout_fmt}. "
                f"Your estimated balance is ${total:.2f}. "
                f"View the full breakdown: {link} "
                f"We look forward to seeing you! {MARKER}"
            )

            client  = Client(app.config.get('TWILIO_ACCOUNT_SID'),
                             app.config.get('TWILIO_AUTH_TOKEN'))
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

            logger.info(
                f'Checkout estimate sent: {boarding.pet.name} / '
                f'{customer.first_name} {customer.last_name} — ${total:.2f}'
            )
            return True

        except Exception as e:
            logger.error(f'Failed to send checkout estimate for boarding {boarding.id}: {e}')
            return False


def run_checkout_estimates(app):
    """
    Main entry point — find all checkouts today and send estimates.
    Returns a summary dict.
    """
    boardings = get_checkouts_today(app)
    sent    = 0
    skipped = 0

    for b in boardings:
        success = send_estimate(app, b)
        if success:
            sent += 1
        else:
            skipped += 1

    summary = {'sent': sent, 'skipped': skipped, 'total': len(boardings)}
    logger.info(f'Checkout estimate run complete: {summary}')
    return summary


# ── Standalone execution (Task Scheduler) ────────────────────────────────────
if __name__ == '__main__':
    import os
    import sys

    log_path = os.path.join(os.path.dirname(__file__), '..', 'logs', 'checkout_estimate.log')
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

    summary = run_checkout_estimates(flask_app)
    print(f"Done — sent={summary['sent']} skipped={summary['skipped']} total={summary['total']}")