#!/usr/bin/env python3
"""
apply_sort_patches.py
Run this once against your admin.py to apply all alphabetical sort fixes.
Usage:  python apply_sort_patches.py
Output: admin.py is patched in-place (backup written to admin.py.bak)
"""
import shutil, sys

SRC = 'admin.py'

shutil.copy(SRC, SRC + '.bak')
src = open(SRC, encoding='utf-8').read()
original = src

patches = [
    # 1. users() — staff list: add first_name tiebreaker
    (
        "users = User.query.filter(User.role.in_(['staff', 'admin'])).order_by(User.last_name).all()",
        "users = User.query.filter(User.role.in_(['staff', 'admin'])).order_by(User.last_name, User.first_name).all()"
    ),
    # 2. pets() — pet list: add order_by Pet.name
    (
        "    pets = Pet.query.filter_by(is_active=True).all()\n    return render_template('admin/pets.html', pets=pets)",
        "    pets = Pet.query.filter_by(is_active=True).order_by(Pet.name).all()\n    return render_template('admin/pets.html', pets=pets)"
    ),
    # 3. daycare_dashboard() — enrollments: sort by pet name instead of enrollment date
    (
        """    enrollments = DaycareEnrollment.query.filter_by(active=True).order_by(
        DaycareEnrollment.enrollment_date.desc()
    ).all()""",
        """    enrollments = (DaycareEnrollment.query
        .filter_by(active=True)
        .join(Pet, DaycareEnrollment.pet_id == Pet.id)
        .order_by(Pet.name)
        .all())"""
    ),
    # 4. customers() — customer list: add first_name tiebreaker to both branches
    (
        "        all_customers = [c for c in query.order_by(User.last_name).all()\n                         if sl in c.first_name.lower()\n                         or sl in c.last_name.lower()\n                         or sl in (c.email or '').lower()\n                         or sl in (c.phone or '').lower()]\n    else:\n        all_customers = query.order_by(User.last_name).all()",
        "        all_customers = [c for c in query.order_by(User.last_name, User.first_name).all()\n                         if sl in c.first_name.lower()\n                         or sl in c.last_name.lower()\n                         or sl in (c.email or '').lower()\n                         or sl in (c.phone or '').lower()]\n    else:\n        all_customers = query.order_by(User.last_name, User.first_name).all()"
    ),
    # 5. daycare_waitlist_admin() — waitlists: sort by last/first name
    (
        """    pending = DaycareWaitlist.query.filter_by(contacted=False).order_by(
        DaycareWaitlist.submitted_date.asc()
    ).all()
    contacted = DaycareWaitlist.query.filter_by(contacted=True).order_by(
        DaycareWaitlist.submitted_date.desc()
    ).all()""",
        """    pending = DaycareWaitlist.query.filter_by(contacted=False).order_by(
        DaycareWaitlist.last_name, DaycareWaitlist.first_name
    ).all()
    contacted = DaycareWaitlist.query.filter_by(contacted=True).order_by(
        DaycareWaitlist.last_name, DaycareWaitlist.first_name
    ).all()"""
    ),
]

applied = 0
for old, new in patches:
    if old in src:
        src = src.replace(old, new, 1)
        applied += 1
        print(f"  [OK] {old[:70].strip()!r}")
    else:
        print(f"  [MISS] {old[:70].strip()!r}")

if applied == len(patches):
    open(SRC, 'w', encoding='utf-8').write(src)
    print(f"\nAll {applied} patches applied. Backup: {SRC}.bak")
else:
    print(f"\nOnly {applied}/{len(patches)} patches matched — file NOT saved.")
    print("Check that admin.py matches the expected source.")
    sys.exit(1)