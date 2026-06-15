"""
rate_resolver.py — Resolves effective pricing for a customer.

Priority order:
  1. Customer-level custom rate (if set)
  2. App config default rate

Usage:
    from app.rate_resolver import get_rates
    rates = get_rates(customer)
    nightly = rates['boarding']          # per night, first pet
    nightly_add = rates['boarding_add']  # per night, additional pet
    daycare = rates['daycare']
    spa_nails = rates['addon_spa_bath_nails']
    spa = rates['addon_spa_bath']
    nails = rates['addon_nail_trim']

Place at: C:\\RuffLifeRetreat\\app\\rate_resolver.py
"""

from flask import current_app


def get_rates(customer=None):
    """
    Return a dict of effective rates for the given customer.
    Falls back to app config defaults if no custom rate is set.
    """
    def cfg(key, default):
        try:
            val = current_app.config.get(key)
            return float(val) if val is not None else default
        except (TypeError, ValueError):
            return default

    defaults = {
        'boarding':             cfg('BOARDING_RATE_PRIMARY',    40.0),
        'boarding_add':         cfg('BOARDING_RATE_ADDITIONAL', 25.0),
        'daycare':              cfg('DAYCARE_RATE_MULTI',       20.0),
        'addon_spa_bath_nails': cfg('ADDON_SPA_BATH_NAILS',     20.0),
        'addon_spa_bath':       cfg('ADDON_SPA_BATH',           15.0),
        'addon_nail_trim':      cfg('ADDON_NAIL_TRIM',          10.0),
    }

    if not customer:
        return defaults

    def resolve(custom_val, default):
        """Use custom value if set and > 0, else fall back to default."""
        try:
            if custom_val is not None:
                v = float(custom_val)
                if v >= 0:
                    return v
        except (TypeError, ValueError):
            pass
        return default

    return {
        'boarding':             resolve(customer.custom_boarding_rate,            defaults['boarding']),
        'boarding_add':         resolve(customer.custom_boarding_rate_additional, defaults['boarding_add']),
        'daycare':              resolve(customer.custom_daycare_rate,             defaults['daycare']),
        'addon_spa_bath_nails': resolve(customer.custom_addon_spa_bath_nails,     defaults['addon_spa_bath_nails']),
        'addon_spa_bath':       resolve(customer.custom_addon_spa_bath,           defaults['addon_spa_bath']),
        'addon_nail_trim':      resolve(customer.custom_addon_nail_trim,          defaults['addon_nail_trim']),
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


def get_boarding_night_rate(customer, is_additional=False):
    """Convenience — return the effective nightly rate for a pet."""
    rates = get_rates(customer)
    return rates['boarding_add'] if is_additional else rates['boarding']


def get_daycare_day_rate(customer):
    """Convenience — return the effective daycare daily rate."""
    return get_rates(customer)['daycare']