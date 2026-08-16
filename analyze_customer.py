"""
analyze_customer.py — Pull all related data for a customer for analysis.
Run from the RuffLifeRetreat directory:
    python analyze_customer.py [customer_id]
Defaults to customer 119 if no argument given.
"""
import sys, os, json
sys.path.insert(0, os.path.dirname(__file__))

CUSTOMER_ID = int(sys.argv[1]) if len(sys.argv) > 1 else 119

from app import create_app
from app.models import db, User, Pet, Boarding, Payment, SmsMessage, DaycareAttendance, DaycareEnrollment, AuditLog

app = create_app()

def fmt(val, width=18):
    return str(val or '—').ljust(width)

def hr(char='─', width=90):
    print(char * width)

def section(title):
    print()
    hr('═')
    print(f'  {title}')
    hr('═')

with app.app_context():

    # ── Customer ──────────────────────────────────────────────────────────────
    customer = User.query.get(CUSTOMER_ID)
    if not customer:
        print(f'Customer {CUSTOMER_ID} not found.')
        sys.exit(1)

    section(f'CUSTOMER #{customer.id}')
    print(f'  Name   : {customer.first_name} {customer.last_name}')
    print(f'  Email  : {customer.email}')
    print(f'  Phone  : {customer.phone}')

    # ── Pets ──────────────────────────────────────────────────────────────────
    section('PETS')
    pets = Pet.query.filter_by(user_id=CUSTOMER_ID).all()
    for p in pets:
        print(f'  Pet #{p.id}: {p.name} ({p.breed or "unknown breed"})'
              f'  custom_boarding={p.custom_boarding_rate}  custom_daycare={p.custom_daycare_rate}')

    # ── Boardings ─────────────────────────────────────────────────────────────
    section('BOARDINGS (all, newest first)')
    pet_ids = [p.id for p in pets]
    boardings = (Boarding.query
                 .filter(Boarding.pet_id.in_(pet_ids))
                 .order_by(Boarding.check_in_date.desc())
                 .all())

    for b in boardings:
        pet = next((p for p in pets if p.id == b.pet_id), None)
        hr('-')
        print(f'  Boarding #{b.id}  [{getattr(b, "booking_number", None) or "no booking#"}]'
              f'  Pet: {pet.name if pet else b.pet_id}')
        print(f'  Dates   : {b.check_in_date} → {b.check_out_date}'
              f'  Status: {b.status}  Checked-in: {b.checked_in}')
        print(f'  Kennel  : {b.kennel_number or "unassigned"}')
        print(f'  Payment_id (legacy): {b.payment_id}')
        if b.special_notes:
            print(f'  Notes   : {b.special_notes[:120]}')

        # New Invoice model (if migration has been run)
        try:
            inv = b.invoice
            if inv:
                print(f'  ── Invoice #{inv.invoice_number} (id={inv.id})')
                print(f'     Status : {inv.status}  Total: ${inv.total:.2f}')
                print(f'     Created: {inv.created_at}')
                if inv.line_items:
                    try:
                        lines = json.loads(inv.line_items)
                        for li in lines:
                            print(f'     Line   : {li.get("description","?")} — ${li.get("amount",0):.2f}')
                    except Exception:
                        print(f'     Line items (raw): {inv.line_items}')
                if inv.notes:
                    print(f'     Notes  : {inv.notes}')
        except AttributeError:
            pass  # invoice table not yet migrated

    # ── Payments (legacy) ────────────────────────────────────────────────────
    section('PAYMENTS (legacy payment table, newest first)')
    payments = (Payment.query
                .filter_by(customer_id=CUSTOMER_ID)
                .order_by(Payment.payment_date.desc())
                .all())

    if not payments:
        print('  No payment records found.')
    else:
        total_paid = 0.0
        total_outstanding = 0.0
        for p in payments:
            print(f'  #{p.id}  {p.payment_date}  {fmt(p.service_type,12)}'
                  f'  {fmt(p.payment_method,10)}  ${p.amount:>8.2f}  [{p.status}]')
            print(f'       Notes: {p.notes}')
            if p.status == 'paid':
                total_paid += p.amount
            else:
                total_outstanding += p.amount
        hr()
        print(f'  Total Paid: ${total_paid:.2f}    Outstanding: ${total_outstanding:.2f}')

    # ── Daycare ───────────────────────────────────────────────────────────────
    section('DAYCARE ATTENDANCE (all, newest first)')
    attendance = (DaycareAttendance.query
                  .filter(DaycareAttendance.pet_id.in_(pet_ids))
                  .order_by(DaycareAttendance.date.desc())
                  .all())

    if not attendance:
        print('  No daycare attendance records.')
    else:
        for a in attendance:
            pet = next((p for p in pets if p.id == a.pet_id), None)
            waived = getattr(a, 'waived', False)
            addon  = getattr(a, 'addon_label', None)
            print(f'  #{a.id}  {a.date}  {pet.name if pet else a.pet_id}'
                  f'  rate=${a.rate:.2f}'
                  f'{"  WAIVED" if waived else ""}'
                  f'{f"  addon={addon}" if addon else ""}')

    # ── Enrollments ───────────────────────────────────────────────────────────
    section('DAYCARE ENROLLMENTS')
    enrollments = (DaycareEnrollment.query
                   .filter(DaycareEnrollment.pet_id.in_(pet_ids))
                   .all())
    if not enrollments:
        print('  No enrollments.')
    else:
        for e in enrollments:
            pet = next((p for p in pets if p.id == e.pet_id), None)
            print(f'  #{e.id}  {pet.name if pet else e.pet_id}  status={e.status}')

    # ── SMS History ───────────────────────────────────────────────────────────
    section('SMS MESSAGES (all, newest first)')
    sms_msgs = (SmsMessage.query
                .filter_by(user_id=CUSTOMER_ID)
                .order_by(SmsMessage.created_at.desc())
                .limit(30)
                .all())
    if not sms_msgs:
        print('  No SMS records.')
    else:
        for m in sms_msgs:
            direction = '→ OUT' if m.direction == 'outbound' else '← IN '
            print(f'  {direction}  {m.created_at}  [{m.status}]')
            print(f'         {m.body[:100]}')

    # ── Audit Log ─────────────────────────────────────────────────────────────
    section('AUDIT LOG (newest first, limit 30)')
    try:
        logs = (AuditLog.query
                .filter(
                    db.or_(
                        AuditLog.user_id == CUSTOMER_ID,
                        db.and_(
                            AuditLog.entity_type == 'Boarding',
                            AuditLog.entity_id.in_([str(b.id) for b in boardings])
                        )
                    )
                )
                .order_by(AuditLog.timestamp.desc())
                .limit(30)
                .all())
        if not logs:
            print('  No audit log entries.')
        else:
            for log in logs:
                print(f'  {log.timestamp}  [{log.action}]  {log.entity_type} #{log.entity_id}')
                print(f'       {log.description}')
    except Exception as e:
        print(f'  Could not query audit log: {e}')

    # ── Invoice Adjustments ───────────────────────────────────────────────────
    section('INVOICE ADJUSTMENTS')
    try:
        from app.models import InvoiceAdjustment
        adjs = InvoiceAdjustment.query.filter_by(customer_id=CUSTOMER_ID).all()
        if not adjs:
            print('  No adjustments.')
        else:
            for a in adjs:
                print(f'  #{a.id}  {a.created_at}  {a.adj_type}  {a.line_key}  ${a.amount:.2f}')
                print(f'       {a.description}')
    except Exception as e:
        print(f'  {e}')

    hr('═')
    print(f'\n  Analysis complete for customer #{CUSTOMER_ID}: {customer.first_name} {customer.last_name}')
    hr('═')
