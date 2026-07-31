"""
Run from the RuffLifeRetreat folder:
  python debug_daycare_invoice.py <last_name>

Example:
  python debug_daycare_invoice.py Smith
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import create_app, db
from app.models import User, Pet, DaycareEnrollment, DaycareAttendance

app = create_app()

search = sys.argv[1].lower() if len(sys.argv) > 1 else ''

with app.app_context():
    customers = User.query.filter_by(role='customer', is_active=True).all()
    if search:
        customers = [c for c in customers
                     if search in c.last_name.lower() or search in c.first_name.lower()]

    if not customers:
        print(f'No customers found matching "{search}"')
        sys.exit(1)

    for c in customers:
        enrollments = []
        for pet in c.pets:
            for enr in DaycareEnrollment.query.filter_by(pet_id=pet.id).all():
                enrollments.append((pet, enr))

        if not enrollments:
            continue

        print(f'\n{"="*60}')
        print(f'Customer: {c.first_name} {c.last_name}  (id={c.id})')
        print(f'{"="*60}')

        for pet, enr in enrollments:
            all_atts = DaycareAttendance.query.filter_by(
                enrollment_id=enr.id
            ).order_by(DaycareAttendance.check_in_time.desc()).limit(20).all()

            print(f'\n  Pet: {pet.name}  |  Enrollment #{enr.id}  |  Rate: '
                  f'${enr.special_rate}/day' if enr.special_rate else f'  Pet: {pet.name}  |  Enrollment #{enr.id}  |  Rate: default')

            if not all_atts:
                print('    (no attendance records)')
                continue

            print(f'  {"Date":<14} {"Checked Out":<14} {"Paid?":<10} {"Waived?":<10} {"Add-ons":<30} {"Status"}')
            print(f'  {"-"*90}')

            for att in all_atts:
                date_str  = att.check_in_time.strftime('%b %d, %Y') if att.check_in_time else '?'
                cout_str  = att.check_out_time.strftime('%H:%M') if att.check_out_time else 'NOT CHECKED OUT'
                paid_str  = f'Yes (pay#{att.payment_id})' if att.payment_id else 'No'
                waiv_str  = 'Yes' if att.waived else 'No'
                addon_str = (att.addons or '')[:28]

                if att.check_out_time is None:
                    status = '⚠  OPEN (no checkout)'
                elif att.payment_id:
                    status = '✓  PAID'
                elif att.waived:
                    status = '✗  WAIVED'
                else:
                    status = '→  UNPAID (should appear on invoice)'

                print(f'  {date_str:<14} {cout_str:<14} {paid_str:<10} {waiv_str:<10} {addon_str:<30} {status}')
