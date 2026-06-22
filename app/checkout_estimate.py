"""
checkout_estimate.py
On the morning of a pet's scheduled checkout day, automatically sends the
owner a single estimated balance SMS covering all pets checking out today.

Runs daily at 7:00 AM via Windows Task Scheduler.
Only fires for active boarding reservations checking out TODAY.
Will not send duplicate estimates (tracked via SMS log marker).

Place this file at: C:\\RuffLifeRetreat\\app\\checkout_estimate.py
"""

import logging
from datetime import datetime, date
from collections import defaultdict

logger = logging.getLogger(__name__)

MARKER = '[checkout-estimate]'


def _boarding_days(b):
    base = (b.check_out_date - b.check_in_date).days
    cout = str(b.check_out_time or '17:00')[:5]
    return base if cout <= '10:00' else base + 1


def get_checkouts_today(app):
    """
    Returns boardings checking out today, grouped by customer.
    Skips customers who already received an estimate SMS today.
    Returns: dict of {user_id: [boarding, ...]}
    """
    from app.models import Boarding, SmsMessage

    with app.app_context():
        today = date.today()

        boardings = (Boarding.query
                     .filter_by(status='active')
                     .filter(Boarding.check_out_date == today)
                     .all())

        # Group by customer, skipping those already sent today
        grouped = defaultdict(list)
        seen_customers = set()

        for b in boardings:
            owner = b.pet.owner if b.pet else None
            if not owner or not owner.phone:
                continue

            if owner.id in seen_customers:
                grouped[owner.id].append(b)
                continue

            already_sent = SmsMessage.query.filter(
                SmsMessage.user_id   == owner.id,
                SmsMessage.direction == 'outbound',
                SmsMessage.body.like(f'%{MARKER}%'),
                SmsMessage.created_at >= datetime.combine(today, datetime.min.time())
            ).first()

            if not already_sent:
                grouped[owner.id].append(b)
                seen_customers.add(owner.id)

        return grouped


def calculate_customer_estimate(app, boardings):
    """
    Calculate the combined estimate for all a customer's boardings today.
    Returns (total, pet_lines, checkout_time_str)
    """
    with app.app_context():
        try:
            from app.rate_resolver import get_pet_boarding_rate
            from app.routes.admin import _parse_addons_from_notes
        except Exception as e:
            logger.warning(f'Import error in calculate_customer_estimate: {e}')
            return 0.0, [], '5:00 PM'

        from app.models import Boarding

        total     = 0.0
        pet_lines = []
        cout_fmt  = '5:00 PM'

        # Sort boardings so primary pet (lowest pet_id in the stay group) is first
        boardings = sorted(boardings, key=lambda b: b.pet_id)

        for b in boardings:
            pet      = b.pet
            customer = pet.owner

            days = _boarding_days(b)

            siblings = (Boarding.query
                        .filter_by(user_id=b.user_id,
                                   check_in_date=b.check_in_date,
                                   check_out_date=b.check_out_date)
                        .filter(Boarding.status == 'active')
                        .order_by(Boarding.pet_id.asc()).all())
            is_first = (not siblings) or siblings[0].pet_id == pet.id

            try:
                rate = get_pet_boarding_rate(pet, customer, is_additional=not is_first)
            except Exception:
                rate = 40.00 if is_first else 25.00

            amount = rate * days

            # Add-ons: check special_notes first, fall back to appointment notes
            addon_total = 0.0
            addon_names = []
            try:
                _addons, addon_total = _parse_addons_from_notes(b.special_notes or '')
                if not _addons:
                    from app.models import Appointment as _A, ServiceType as _ST
                    _svc = _ST.query.filter(_ST.name.ilike('%boarding%')).first()
                    if _svc:
                        _a = _A.query.filter_by(
                            pet_id=pet.id, user_id=customer.id,
                            service_type_id=_svc.id
                        ).order_by(_A.id.desc()).first()
                        if _a and _a.notes:
                            _addons, addon_total = _parse_addons_from_notes(_a.notes)
                addon_names = [a.split('(')[0].strip() for a in _addons]
            except Exception as e:
                logger.warning(f'Could not parse add-ons for boarding {b.id}: {e}')

            amount += addon_total
            total  += amount

            addon_str = f' + {", ".join(addon_names)}' if addon_names else ''
            pet_lines.append(f'{pet.name}: {days} night{"s" if days != 1 else ""}{addon_str} = ${amount:.2f}')

            # Use the latest checkout time among all pets
            cout = str(b.check_out_time or '17:00')[:5]
            try:
                t = datetime.strptime(cout, '%H:%M')
                cout_fmt = t.strftime('%I:%M %p').lstrip('0')
            except ValueError:
                pass

        return total, pet_lines, cout_fmt


def send_customer_estimate(app, customer_id, boardings):
    """Send one estimate SMS covering all of a customer's pets checking out today."""
    from app.models import SmsMessage, InvoiceToken, User
    from app import db
    import secrets

    with app.app_context():
        try:
            from twilio.rest import Client
            from app.sms_service import _normalize_phone

            customer = User.query.get(customer_id)
            if not customer:
                return False

            total, pet_lines, cout_fmt = calculate_customer_estimate(app, boardings)

            if total <= 0:
                logger.info(f'No estimate amount for customer {customer_id}, skipping')
                return False

            # Get or create invoice token
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

            # Build pet name list
            pet_names = [b.pet.name for b in boardings if b.pet]
            if len(pet_names) == 1:
                pet_str = pet_names[0] + ' is'
            elif len(pet_names) == 2:
                pet_str = f'{pet_names[0]} & {pet_names[1]} are'
            else:
                pet_str = ', '.join(pet_names[:-1]) + f' & {pet_names[-1]} are'

            body = (
                f"Good morning {customer.first_name}! {pet_str} scheduled "
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

            pet_summary = ', '.join(pet_lines)
            logger.info(
                f'Checkout estimate sent: {customer.first_name} {customer.last_name} '
                f'— ${total:.2f} ({pet_summary})'
            )
            return True

        except Exception as e:
            logger.error(f'Failed to send checkout estimate for customer {customer_id}: {e}')
            return False


def run_checkout_estimates(app):
    """
    Main entry point — group checkouts by customer and send one SMS each.
    Returns a summary dict.
    """
    grouped = get_checkouts_today(app)
    sent    = 0
    skipped = 0

    for customer_id, boardings in grouped.items():
        success = send_customer_estimate(app, customer_id, boardings)
        if success:
            sent += 1
        else:
            skipped += 1

    summary = {'sent': sent, 'skipped': skipped, 'total': len(grouped)}
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
