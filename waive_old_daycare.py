"""
Run this once on the VPS to write off all daycare sessions
that predate the payment-tracking system.

Usage:
  python waive_old_daycare.py

Edit CUTOFF_DATE to the date you started using the "Mark as Paid"
button in the system. Sessions BEFORE that date (and still unpaid)
will be marked as waived so they no longer show on invoices.
"""

from datetime import datetime, date

# ── EDIT THIS ─────────────────────────────────────────────────────────────────
CUTOFF_DATE = date(2026, 5, 1)   # sessions before this date will be waived
STAFF_NAME  = 'System (historical write-off)'
# ─────────────────────────────────────────────────────────────────────────────

from app import create_app, db
from app.models import DaycareAttendance

app = create_app()
with app.app_context():
    old_unpaid = DaycareAttendance.query.filter(
        DaycareAttendance.check_out_time != None,
        DaycareAttendance.payment_id == None,
        DaycareAttendance.waived != True,
        DaycareAttendance.check_in_time < datetime.combine(CUTOFF_DATE, datetime.min.time()),
    ).all()

    print(f'Found {len(old_unpaid)} session(s) to write off (before {CUTOFF_DATE}).')

    now = datetime.now()
    for att in old_unpaid:
        pet_name = att.enrollment.pet.name if att.enrollment and att.enrollment.pet else '?'
        print(f'  Waiving: {pet_name} — {att.check_in_time.strftime("%Y-%m-%d")}')
        att.waived    = True
        att.waived_by = STAFF_NAME
        att.waived_at = now

    db.session.commit()
    print('Done. All listed sessions are now excluded from invoices.')
