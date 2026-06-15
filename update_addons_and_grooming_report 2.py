"""
update_addons_and_grooming_report.py
1. Updates add-on prices throughout RuffLife Retreat
2. Adds daily grooming report route to admin.py
3. Adds grooming report template
4. Adds nav link to Operations menu

New prices:
  Spa Bath + Nail Trim: $20 -> $30
  Spa Bath:             $15 -> $20
  Nail Trim:            $10 -> $15

Run from C:\\RuffLifeRetreat:
    venv\\Scripts\\python update_addons_and_grooming_report.py
"""
import shutil
from pathlib import Path

BASE      = Path(r"C:\RuffLifeRetreat")
ADMIN     = BASE / "app" / "routes" / "admin.py"
CUSTOMER  = BASE / "app" / "routes" / "customer.py"
BASE_HTML = BASE / "app" / "templates" / "base.html"
BOOK_HTML = BASE / "app" / "templates" / "customer" / "book_appointment.html"
EDIT_HTML = BASE / "app" / "templates" / "customer" / "edit_appointment.html"

UTF8 = "utf-8"

def fix(src, old, new, label, path=""):
    if old in src:
        print("  [OK] %s" % label)
        return src.replace(old, new)
    print("  [--] NOT FOUND: %s%s" % (label, " in %s" % path if path else ""))
    return src

# ══════════════════════════════════════════════════════════════════════════════
# 1. UPDATE PRICES IN admin.py
# ══════════════════════════════════════════════════════════════════════════════
shutil.copy(ADMIN, ADMIN.with_suffix(".py.bak_addon_prices"))
src = ADMIN.read_text(encoding=UTF8)

# addon_map in create_boarding (line ~1247)
src = fix(src,
    "'addon_spa_bath_nails': 'Spa Bath + Nail Trim ($20)'",
    "'addon_spa_bath_nails': 'Spa Bath + Nail Trim ($30)'",
    "addon_map spa_bath_nails price")
src = fix(src,
    "'addon_spa_bath':       'Spa Bath ($15)'",
    "'addon_spa_bath':       'Spa Bath ($20)'",
    "addon_map spa_bath price")
src = fix(src,
    "'addon_nail_trim':      'Nail Trim ($10)'",
    "'addon_nail_trim':      'Nail Trim ($15)'",
    "addon_map nail_trim price")

# invoice_detail parse logic (line ~2515-2519)
src = fix(src,
    "addons.append('Spa Bath + Nail Trim ($20)'); total = 20.0",
    "addons.append('Spa Bath + Nail Trim ($30)'); total = 30.0",
    "invoice parse spa_bath_nails price")
src = fix(src,
    "addons.append('Spa Bath ($15)');  total = 15.0",
    "addons.append('Spa Bath ($20)');  total = 20.0",
    "invoice parse spa_bath price")
src = fix(src,
    "addons.append('Nail Trim ($10)'); total = 10.0",
    "addons.append('Nail Trim ($15)'); total = 15.0",
    "invoice parse nail_trim price")

# Any remaining display strings with old prices
src = src.replace("Spa Bath + Nail Trim ($20)", "Spa Bath + Nail Trim ($30)")
src = src.replace("Spa Bath ($15)",              "Spa Bath ($20)")
src = src.replace("Nail Trim ($10)",             "Nail Trim ($15)")

ADMIN.write_text(src, encoding=UTF8)
print("[OK] admin.py prices updated")

# ══════════════════════════════════════════════════════════════════════════════
# 2. UPDATE PRICES IN customer.py
# ══════════════════════════════════════════════════════════════════════════════
shutil.copy(CUSTOMER, CUSTOMER.with_suffix(".py.bak_addon_prices"))
src = CUSTOMER.read_text(encoding=UTF8)

src = src.replace("Spa Bath + Nail Trim ($20)", "Spa Bath + Nail Trim ($30)")
src = src.replace("Spa Bath + Nail Trim': '$20'","Spa Bath + Nail Trim': '$30'")
src = src.replace("'spa_bath_nails': 'Spa Bath + Nail Trim ($20)'",
                  "'spa_bath_nails': 'Spa Bath + Nail Trim ($30)'")
src = src.replace("spa_bath_nails': 'Spa Bath + Nail Trim ($20)",
                  "spa_bath_nails': 'Spa Bath + Nail Trim ($30)")
src = src.replace("Spa Bath ($15)", "Spa Bath ($20)")
src = src.replace("'spa_bath': 'Spa Bath ($15)'", "'spa_bath': 'Spa Bath ($20)'")
src = src.replace("Nail Trim ($10)", "Nail Trim ($15)")
src = src.replace("'nail_trim': 'Nail Trim ($10)'", "'nail_trim': 'Nail Trim ($15)'")
# Fix addon prices in edit route
src = src.replace("spa_bath_nails': 'Spa Bath + Nail Trim ($20)",
                  "spa_bath_nails': 'Spa Bath + Nail Trim ($30)")
src = src.replace("'spa_bath':       'Spa Bath ($15)'",
                  "'spa_bath':       'Spa Bath ($20)'")
src = src.replace("'nail_trim':      'Nail Trim ($10)'",
                  "'nail_trim':      'Nail Trim ($15)'")

CUSTOMER.write_text(src, encoding=UTF8)
print("[OK] customer.py prices updated")

# ══════════════════════════════════════════════════════════════════════════════
# 3. UPDATE PRICES IN book_appointment.html
# ══════════════════════════════════════════════════════════════════════════════
if BOOK_HTML.exists():
    shutil.copy(BOOK_HTML, BOOK_HTML.with_suffix(".html.bak_prices"))
    src = BOOK_HTML.read_text(encoding=UTF8)
    src = src.replace("Spa Bath + Nail Trim", "Spa Bath + Nail Trim")  # name unchanged
    src = src.replace("$20/pet", "$30/pet").replace("$20 / pet", "$30 / pet")
    src = src.replace(">$20<", ">$30<").replace('"$20"', '"$30"')
    src = src.replace("$15/pet", "$20/pet").replace("$15 / pet", "$20 / pet")
    src = src.replace(">$15<", ">$20<").replace('"$15"', '"$20"')
    src = src.replace("$10/pet", "$15/pet").replace("$10 / pet", "$15 / pet")
    src = src.replace(">$10<", ">$15<").replace('"$10"', '"$15"')
    # Badge labels
    src = src.replace('bg-warning text-dark ms-2">$20<', 'bg-warning text-dark ms-2">$30<')
    src = src.replace('bg-warning text-dark ms-2">$15<', 'bg-warning text-dark ms-2">$20<')
    src = src.replace('bg-warning text-dark ms-2">$10<', 'bg-warning text-dark ms-2">$15<')
    BOOK_HTML.write_text(src, encoding=UTF8)
    print("[OK] book_appointment.html prices updated")

# ══════════════════════════════════════════════════════════════════════════════
# 4. UPDATE PRICES IN edit_appointment.html
# ══════════════════════════════════════════════════════════════════════════════
if EDIT_HTML.exists():
    shutil.copy(EDIT_HTML, EDIT_HTML.with_suffix(".html.bak_prices"))
    src = EDIT_HTML.read_text(encoding=UTF8)
    src = src.replace("$20/pet", "$30/pet").replace("$20 / pet", "$30 / pet")
    src = src.replace(">$20<", ">$30<")
    src = src.replace("$15/pet", "$20/pet").replace("$15 / pet", "$20 / pet")
    src = src.replace(">$15<", ">$20<")
    src = src.replace("$10/pet", "$15/pet").replace("$10 / pet", "$15 / pet")
    src = src.replace(">$10<", ">$15<")
    src = src.replace('ms-2">$20<', 'ms-2">$30<')
    src = src.replace('ms-2">$15<', 'ms-2">$20<')
    src = src.replace('ms-2">$10<', 'ms-2">$15<')
    EDIT_HTML.write_text(src, encoding=UTF8)
    print("[OK] edit_appointment.html prices updated")

# ══════════════════════════════════════════════════════════════════════════════
# 5. ADD GROOMING REPORT ROUTE to admin.py
# ══════════════════════════════════════════════════════════════════════════════
src = ADMIN.read_text(encoding=UTF8)

if "def grooming_report" not in src:
    route = '''

@bp.route('/reports/grooming')
@login_required
@admin_required
def grooming_report():
    """
    Daily Grooming Report — shows all boarding guests
    checking out TOMORROW who have add-ons requiring grooming.
    Designed to be printed at the start of each day.
    """
    from app.models import Boarding, Pet, User, Appointment, ServiceType
    from datetime import date, timedelta
    import re

    today    = date.today()
    tomorrow = today + timedelta(days=1)

    # Get all active boardings checking out tomorrow
    checkouts_tomorrow = (Boarding.query
        .filter_by(status='active')
        .filter(Boarding.check_out_date == tomorrow)
        .order_by(Boarding.check_out_time.asc())
        .all())

    # For each boarding, find add-ons from associated appointment notes
    grooming_items = []
    _bsvc = ServiceType.query.filter(ServiceType.name.ilike('%boarding%')).first()

    for b in checkouts_tomorrow:
        pet      = Pet.query.get(b.pet_id)
        customer = User.query.get(b.user_id)
        if not pet or not customer:
            continue

        # Find associated appointment for add-on notes
        addons = []
        notes_src = b.special_notes or ''

        # Also check most recent appointment
        if _bsvc:
            appt = (Appointment.query
                .filter_by(pet_id=b.pet_id, service_type_id=_bsvc.id)
                .filter(Appointment.appointment_date == b.check_in_date)
                .order_by(Appointment.id.desc())
                .first())
            if appt and appt.notes:
                notes_src = appt.notes

        # Parse add-ons from notes
        m = re.search(r'Add-ons?:\s*(.+)', notes_src, re.IGNORECASE)
        if m:
            raw = m.group(1)
            for item in raw.split(','):
                item = item.strip()
                if item:
                    addons.append(item)

        # Also check special_notes directly
        if not addons and b.special_notes:
            m2 = re.search(r'Add-ons?:\s*(.+)', b.special_notes, re.IGNORECASE)
            if m2:
                for item in m2.group(1).split(','):
                    item = item.strip()
                    if item:
                        addons.append(item)

        # Only include if there are grooming add-ons
        grooming_addons = [a for a in addons if any(
            kw in a.lower() for kw in ['bath', 'nail', 'spa', 'groom']
        )]

        if grooming_addons:
            pickup_time = None
            if b.check_out_time:
                try:
                    pickup_time = b.check_out_time.strftime('%I:%M %p')
                except Exception:
                    pass

            grooming_items.append({
                'boarding':     b,
                'pet':          pet,
                'customer':     customer,
                'addons':       grooming_addons,
                'pickup_time':  pickup_time,
                'kennel':       (f'{(b.kennel_type or "Kennel").title()} #{b.kennel_number}'
                                 if b.kennel_number else 'Unassigned'),
                'notes':        b.special_notes or '',
            })

    # Sort by pickup time (None last)
    grooming_items.sort(key=lambda x: (
        x['pickup_time'] is None,
        x['pickup_time'] or ''
    ))

    return render_template('admin/grooming_report.html',
                           grooming_items=grooming_items,
                           report_date=tomorrow,
                           today=today,
                           generated_at=datetime.now().strftime('%B %d, %Y at %I:%M %p'))
'''
    src += route
    ADMIN.write_text(src, encoding=UTF8)
    print("[OK] grooming_report route appended to admin.py")
else:
    print("[--] grooming_report route already exists")

# ══════════════════════════════════════════════════════════════════════════════
# 6. WRITE GROOMING REPORT TEMPLATE
# ══════════════════════════════════════════════════════════════════════════════
GROOMING_TMPL = BASE / "app" / "templates" / "admin" / "grooming_report.html"

GROOMING_TMPL.write_text('''\
{% extends "base.html" %}
{% block title %}Daily Grooming Report — {{ report_date.strftime('%B %d, %Y') }}{% endblock %}

{% block content %}
<style>
@media print {
    .no-print { display: none !important; }
    .card { border: 1px solid #dee2e6 !important; box-shadow: none !important; }
    body { font-size: 12pt; }
    .print-header { display: block !important; }
    a { color: inherit !important; text-decoration: none !important; }
}
.print-header { display: none; }
.addon-badge {
    display: inline-block;
    padding: 4px 12px;
    border-radius: 50px;
    font-size: 0.8rem;
    font-weight: 700;
    margin: 2px 4px 2px 0;
}
.addon-spa-nails { background: #fff3cd; color: #856404; border: 1px solid #ffc107; }
.addon-spa       { background: #cff4fc; color: #055160; border: 1px solid #0dcaf0; }
.addon-nail      { background: #d1e7dd; color: #0a3622; border: 1px solid #198754; }
.addon-other     { background: #e2e3e5; color: #383d41; border: 1px solid #adb5bd; }
.checklist-box {
    width: 22px; height: 22px;
    border: 2px solid #dee2e6;
    border-radius: 4px;
    display: inline-block;
    flex-shrink: 0;
}
</style>

<div class="container-fluid mt-3">

    <!-- Screen header -->
    <div class="no-print d-flex align-items-center justify-content-between mb-3">
        <div class="d-flex align-items-center gap-3">
            <a href="{{ url_for('admin.boarding_dashboard') }}"
               class="btn btn-outline-secondary btn-sm">
                <i class="fas fa-arrow-left"></i> Back
            </a>
            <h4 class="mb-0">
                <i class="fas fa-cut me-2 text-warning"></i>
                Daily Grooming Report —
                <span class="text-warning">{{ report_date.strftime('%A, %B %d, %Y') }}</span>
            </h4>
        </div>
        <div class="d-flex gap-2">
            <a href="{{ url_for('admin.grooming_report') }}"
               class="btn btn-outline-secondary btn-sm">
                <i class="fas fa-sync-alt me-1"></i> Refresh
            </a>
            <button onclick="window.print()" class="btn btn-warning text-dark fw-bold btn-sm">
                <i class="fas fa-print me-2"></i>Print Report
            </button>
        </div>
    </div>

    <!-- Print header -->
    <div class="print-header mb-4">
        <div style="display:flex; justify-content:space-between; align-items:flex-start; border-bottom: 2px solid #1a1a2e; padding-bottom: 10px; margin-bottom: 16px;">
            <div>
                <div style="font-size:1.4rem; font-weight:800; color:#1a1a2e;">
                    🐾 Ruff Life Retreat
                </div>
                <div style="font-size:1rem; color:#555;">Daily Grooming Prep Report</div>
            </div>
            <div style="text-align:right;">
                <div style="font-size:1.1rem; font-weight:700;">
                    {{ report_date.strftime('%A, %B %d, %Y') }}
                </div>
                <div style="font-size:0.8rem; color:#888;">Generated: {{ generated_at }}</div>
            </div>
        </div>
    </div>

    <!-- Summary banner -->
    {% if grooming_items %}
    <div class="alert {% if grooming_items|length > 0 %}alert-warning{% endif %} py-2 mb-4 no-print"
         style="font-size:0.9rem;">
        <i class="fas fa-cut me-2"></i>
        <strong>{{ grooming_items|length }} pet{{ 's' if grooming_items|length != 1 }}</strong>
        need grooming services before pickup tomorrow.
    </div>
    {% endif %}

    {% if grooming_items %}

    <!-- Quick summary table (print-friendly) -->
    <div class="card shadow-sm mb-4">
        <div class="card-header d-flex align-items-center justify-content-between"
             style="background:#1a1a2e;">
            <strong class="text-white">
                <i class="fas fa-list-check me-2 text-warning"></i>
                Grooming Checklist — {{ report_date.strftime('%m/%d/%Y') }}
            </strong>
            <span class="badge bg-warning text-dark">
                {{ grooming_items|length }} pet{{ 's' if grooming_items|length != 1 }}
            </span>
        </div>
        <div class="card-body p-0">
            <table class="table table-hover mb-0" style="font-size:0.9rem;">
                <thead class="table-light">
                    <tr>
                        <th style="width:40px;" class="text-center">✓</th>
                        <th>Pet</th>
                        <th>Breed</th>
                        <th>Owner</th>
                        <th>Kennel</th>
                        <th>Pickup Time</th>
                        <th>Services Needed</th>
                        <th>Notes</th>
                    </tr>
                </thead>
                <tbody>
                    {% for item in grooming_items %}
                    <tr>
                        <td class="text-center align-middle">
                            <div class="checklist-box"></div>
                        </td>
                        <td class="align-middle">
                            <strong>{{ item.pet.name }}</strong>
                        </td>
                        <td class="align-middle text-muted small">
                            {{ item.pet.breed or '—' }}
                            {% if item.pet.weight %}
                            <div>{{ item.pet.weight }} lbs</div>
                            {% endif %}
                        </td>
                        <td class="align-middle">
                            {{ item.customer.first_name }} {{ item.customer.last_name }}
                            {% if item.customer.phone %}
                            <div class="text-muted small">{{ item.customer.phone }}</div>
                            {% endif %}
                        </td>
                        <td class="align-middle">
                            <span class="badge bg-secondary">{{ item.kennel }}</span>
                        </td>
                        <td class="align-middle">
                            {% if item.pickup_time %}
                            <strong class="text-warning">{{ item.pickup_time }}</strong>
                            {% else %}
                            <span class="text-muted">TBD</span>
                            {% endif %}
                        </td>
                        <td class="align-middle">
                            {% for addon in item.addons %}
                            {% set al = addon.lower() %}
                            {% if 'bath' in al and 'nail' in al %}
                            <span class="addon-badge addon-spa-nails">
                                <i class="fas fa-shower me-1"></i>{{ addon }}
                            </span>
                            {% elif 'bath' in al or 'spa' in al %}
                            <span class="addon-badge addon-spa">
                                <i class="fas fa-shower me-1"></i>{{ addon }}
                            </span>
                            {% elif 'nail' in al %}
                            <span class="addon-badge addon-nail">
                                <i class="fas fa-cut me-1"></i>{{ addon }}
                            </span>
                            {% else %}
                            <span class="addon-badge addon-other">{{ addon }}</span>
                            {% endif %}
                            {% endfor %}
                        </td>
                        <td class="align-middle text-muted small">
                            {% if item.pet.medical_notes %}
                            <div><i class="fas fa-notes-medical me-1 text-danger"></i>{{ item.pet.medical_notes[:80] }}{% if item.pet.medical_notes|length > 80 %}…{% endif %}</div>
                            {% endif %}
                            {% if item.pet.special_instructions %}
                            <div><i class="fas fa-star me-1 text-warning"></i>{{ item.pet.special_instructions[:80] }}{% if item.pet.special_instructions|length > 80 %}…{% endif %}</div>
                            {% endif %}
                        </td>
                    </tr>
                    {% endfor %}
                </tbody>
            </table>
        </div>
    </div>

    <!-- Summary totals -->
    <div class="row g-3 mb-4">
        {% set spa_nails_count = grooming_items | selectattr('addons') | list %}
        <div class="col-md-4">
            <div class="card text-center py-3">
                <div class="h2 mb-1 text-warning">{{ grooming_items|length }}</div>
                <div class="text-muted small text-uppercase fw-bold">Total Pets</div>
            </div>
        </div>
        <div class="col-md-4">
            <div class="card text-center py-3">
                {% set bath_count = namespace(n=0) %}
                {% for item in grooming_items %}
                    {% for a in item.addons %}
                        {% if 'bath' in a.lower() or 'spa' in a.lower() %}
                            {% set bath_count.n = bath_count.n + 1 %}
                        {% endif %}
                    {% endfor %}
                {% endfor %}
                <div class="h2 mb-1 text-info">{{ bath_count.n }}</div>
                <div class="text-muted small text-uppercase fw-bold">Baths / Spa</div>
            </div>
        </div>
        <div class="col-md-4">
            <div class="card text-center py-3">
                {% set nail_count = namespace(n=0) %}
                {% for item in grooming_items %}
                    {% for a in item.addons %}
                        {% if 'nail' in a.lower() %}
                            {% set nail_count.n = nail_count.n + 1 %}
                        {% endif %}
                    {% endfor %}
                {% endfor %}
                <div class="h2 mb-1 text-success">{{ nail_count.n }}</div>
                <div class="text-muted small text-uppercase fw-bold">Nail Trims</div>
            </div>
        </div>
    </div>

    {% else %}

    <!-- Empty state -->
    <div class="card shadow-sm">
        <div class="card-body text-center py-5">
            <i class="fas fa-check-circle text-success fa-3x mb-3 d-block"></i>
            <h5 class="text-muted">No grooming services needed for tomorrow</h5>
            <p class="text-muted mb-0" style="font-size:0.875rem;">
                No boarding guests checking out on
                <strong>{{ report_date.strftime('%A, %B %d') }}</strong>
                have grooming add-ons.
            </p>
        </div>
    </div>

    {% endif %}

    <!-- Footer note (print only) -->
    <div class="print-header mt-4 pt-3" style="border-top:1px solid #dee2e6; font-size:0.8rem; color:#888;">
        <strong>Ruff Life Retreat</strong> — Daily Grooming Report printed {{ generated_at }}.
        All services should be completed before scheduled pickup time.
    </div>

</div>
{% endblock %}
''', encoding=UTF8)
print("[OK] grooming_report.html template written")

# ══════════════════════════════════════════════════════════════════════════════
# 7. ADD NAV LINK TO base.html Operations menu
# ══════════════════════════════════════════════════════════════════════════════
src = BASE_HTML.read_text(encoding=UTF8)

# Find the boarding_occupancy link and insert grooming report after it
src = fix(src,
    "url_for('admin.boarding_occupancy_report')",
    "url_for('admin.boarding_occupancy_report')",
    "base.html nav check",
    "base.html"
)

# Insert after the boarding occupancy report nav item
old_nav = """url_for('admin.boarding_occupancy_report') }}\">"""
# Find the full li block containing boarding_occupancy_report
# and add grooming report after it
target = "admin.boarding_occupancy_report"
if target in src:
    # Find the closing </li> after boarding_occupancy_report and insert after it
    idx = src.index(target)
    # Find the next </li> after this point
    li_end = src.index("</li>", idx) + len("</li>")
    grooming_nav = """
                            <li>
                                <a class="dropdown-item py-2" href="{{ url_for('admin.grooming_report') }}">
                                    <i class="fas fa-cut me-2 text-mauve"></i> Daily Grooming Report
                                </a>
                            </li>"""
    src = src[:li_end] + grooming_nav + src[li_end:]
    print("[OK] Grooming Report nav link added to base.html")
else:
    print("  [--] boarding_occupancy_report not found in base.html nav — add manually")

BASE_HTML.write_text(src, encoding=UTF8)

print("""
All done. Restart Waitress to activate:
    .\\Restart-RuffLife.ps1

New add-on prices:
  Spa Bath + Nail Trim: $30/pet
  Spa Bath:             $20/pet
  Nail Trim:            $15/pet

Daily Grooming Report:
  URL: /admin/reports/grooming
  Nav: Operations -> Daily Grooming Report
  Shows: Tomorrow's pickups with grooming add-ons
  Print: Click Print Report button
""")