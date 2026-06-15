"""
rate_resolver.py — Resolves effective pricing for a customer and/or pet.

Priority chain (highest to lowest):
  1. Pet-level custom rate       (set on individual pet record)
  2. Customer-level custom rate  (set on customer profile)
  3. Facility default rate       (from app config)

Usage:
    from app.rate_resolver import get_rates, get_pet_boarding_rate

    # Full rate dict for a customer (no specific pet)
    rates = get_rates(customer)

    # Effective boarding rate for a specific pet in a stay
    rate = get_pet_boarding_rate(pet, customer, is_additional=False)

    # Effective daycare rate for a specific pet
    rate = get_pet_daycare_rate(pet, customer)

Place at: C:\\RuffLifeRetreat\\app\\rate_resolver.py
         C:\\SniffHQDemo\\app\\rate_resolver.py
"""

from flask import current_app


def _cfg(key, default):
    """Read a numeric value from app config with fallback."""
    try:
        val = current_app.config.get(key)
        return float(val) if val is not None else default
    except (TypeError, ValueError):
        return default


def _resolve(value, fallback):
    """Use value if set and >= 0, else use fallback."""
    try:
        if value is not None:
            v = float(value)
            if v >= 0:
                return v
    except (TypeError, ValueError):
        pass
    return fallback


def get_facility_defaults():
    """Return facility-level default rates from app config."""
    base    = _cfg('BOARDING_RATE_PRIMARY',    40.0)
    add_on  = _cfg('BOARDING_RATE_ADDITIONAL', 25.0)
    return {
        'boarding':             base,
        'boarding_add':         add_on,
        'boarding_add_ratio':   add_on / base if base > 0 else 0.625,
        'daycare':              _cfg('DAYCARE_RATE_MULTI',       20.0),
        'addon_spa_bath_nails': _cfg('ADDON_SPA_BATH_NAILS',     20.0),
        'addon_spa_bath':       _cfg('ADDON_SPA_BATH',           15.0),
        'addon_nail_trim':      _cfg('ADDON_NAIL_TRIM',          10.0),
    }


def get_rates(customer=None):
    """
    Return a dict of effective rates for a customer.
    Does NOT factor in per-pet rates — use get_pet_boarding_rate() for that.

    Falls back to app config defaults if no customer custom rate is set.
    """
    defaults = get_facility_defaults()

    if not customer:
        return {**defaults, 'has_custom': False, 'note': ''}

    return {
        'boarding':             _resolve(customer.custom_boarding_rate,            defaults['boarding']),
        'boarding_add':         _resolve(customer.custom_boarding_rate_additional, defaults['boarding_add']),
        'boarding_add_ratio':   defaults['boarding_add_ratio'],
        'daycare':              _resolve(customer.custom_daycare_rate,             defaults['daycare']),
        'addon_spa_bath_nails': _resolve(customer.custom_addon_spa_bath_nails,     defaults['addon_spa_bath_nails']),
        'addon_spa_bath':       _resolve(customer.custom_addon_spa_bath,           defaults['addon_spa_bath']),
        'addon_nail_trim':      _resolve(customer.custom_addon_nail_trim,          defaults['addon_nail_trim']),
        'has_custom':           any([
            customer.custom_boarding_rate,
            customer.custom_boarding_rate_additional,
            customer.custom_daycare_rate,
            customer.custom_addon_spa_bath_nails,
            customer.custom_addon_spa_bath,
            customer.custom_addon_nail_trim,
        ]),
        'note': customer.custom_rate_note or '',
    }


def get_pet_boarding_rate(pet, customer=None, is_additional=False):
    """
    Resolve the effective boarding rate for a specific pet.

    Priority:
      1. Pet custom_boarding_rate (if set)
      2. Customer custom_boarding_rate / custom_boarding_rate_additional (if set)
      3. Facility default

    For additional pets:
      - If the pet has its own custom rate, use it directly
      - If no pet-level rate, use the customer/facility additional rate
      - If a customer has a custom base rate but no custom additional rate,
        calculate additional rate proportionally from the custom base
    """
    defaults = get_facility_defaults()

    # Step 1 — check pet-level override
    if pet and pet.custom_boarding_rate is not None:
        try:
            pet_rate = float(pet.custom_boarding_rate)
            if pet_rate >= 0:
                return pet_rate
        except (TypeError, ValueError):
            pass

    # Step 2 — customer-level rate
    if customer:
        if is_additional:
            # Check for explicit customer additional rate
            if customer.custom_boarding_rate_additional is not None:
                try:
                    rate = float(customer.custom_boarding_rate_additional)
                    if rate >= 0:
                        return rate
                except (TypeError, ValueError):
                    pass
            # No explicit additional rate — if customer has custom base, scale proportionally
            if customer.custom_boarding_rate is not None:
                try:
                    base = float(customer.custom_boarding_rate)
                    if base >= 0:
                        return round(base * defaults['boarding_add_ratio'], 2)
                except (TypeError, ValueError):
                    pass
        else:
            if customer.custom_boarding_rate is not None:
                try:
                    rate = float(customer.custom_boarding_rate)
                    if rate >= 0:
                        return rate
                except (TypeError, ValueError):
                    pass

    # Step 3 — facility default
    return defaults['boarding_add'] if is_additional else defaults['boarding']


def get_pet_daycare_rate(pet, customer=None, enrollment=None):
    """
    Resolve the effective daycare rate for a specific pet.

    Priority:
      1. Enrollment special_rate (set per enrollment)
      2. Pet custom_daycare_rate
      3. Customer custom_daycare_rate
      4. Facility default (multi-day rate)
    """
    defaults = get_facility_defaults()

    # Enrollment-level override (highest priority for daycare)
    if enrollment and enrollment.special_rate:
        try:
            rate = float(enrollment.special_rate)
            if rate >= 0:
                return rate
        except (TypeError, ValueError):
            pass

    # Pet-level override
    if pet and pet.custom_daycare_rate is not None:
        try:
            rate = float(pet.custom_daycare_rate)
            if rate >= 0:
                return rate
        except (TypeError, ValueError):
            pass

    # Customer-level override
    if customer and customer.custom_daycare_rate is not None:
        try:
            rate = float(customer.custom_daycare_rate)
            if rate >= 0:
                return rate
        except (TypeError, ValueError):
            pass

    return defaults['daycare']


def get_boarding_night_rate(customer=None, is_additional=False, pet=None):
    """Convenience wrapper — returns effective nightly boarding rate."""
    return get_pet_boarding_rate(pet, customer, is_additional)


def get_daycare_day_rate(customer=None, pet=None, enrollment=None):
    """Convenience wrapper — returns effective daycare daily rate."""
    return get_pet_daycare_rate(pet, customer, enrollment)


def rate_source(pet, customer, rate_type='boarding'):
    """
    Return a string describing where the rate came from.
    Useful for invoice tooltips and admin UI.
    """
    if rate_type == 'boarding':
        if pet and pet.custom_boarding_rate is not None:
            note = pet.custom_rate_note or ''
            return f'Per-pet rate{" — " + note if note else ""}'
        if customer and customer.custom_boarding_rate is not None:
            note = customer.custom_rate_note or ''
            return f'Customer rate{" — " + note if note else ""}'
        return 'Facility default'
    elif rate_type == 'daycare':
        if pet and pet.custom_daycare_rate is not None:
            note = pet.custom_rate_note or ''
            return f'Per-pet rate{" — " + note if note else ""}'
        if customer and customer.custom_daycare_rate is not None:
            note = customer.custom_rate_note or ''
            return f'Customer rate{" — " + note if note else ""}'
        return 'Facility default'
    return 'Facility default'