"""
settings_service.py
Helpers for reading and writing FacilitySetting values.
"""
from app import db


def get_setting(key, default=None):
    """Return the string value of a setting, or default if not found."""
    from app.models import FacilitySetting
    rec = FacilitySetting.query.filter_by(key=key).first()
    if rec is None:
        return default
    return rec.value


def get_setting_int(key, default=0):
    """Return the integer value of a setting."""
    val = get_setting(key, None)
    if val is None:
        return default
    try:
        return int(val)
    except (ValueError, TypeError):
        return default


def set_setting(key, value, user_id=None):
    """Create or update a setting. value is stored as string."""
    from app.models import FacilitySetting
    from datetime import datetime
    rec = FacilitySetting.query.filter_by(key=key).first()
    if rec is None:
        rec = FacilitySetting(key=key, value=str(value), updated_by=user_id)
        db.session.add(rec)
    else:
        rec.value      = str(value)
        rec.updated_by = user_id
        rec.updated_at = datetime.utcnow()
    db.session.commit()
    return rec


def get_kennel_capacity():
    """Shorthand — returns current kennel capacity as int."""
    return get_setting_int('kennel_capacity', default=40)


def get_business_setting(key, default=None):
    """
    Read a business info value.
    Checks FacilitySetting DB first (key is lowercase, e.g. 'business_name'),
    then falls back to app.config (uppercase key, e.g. 'BUSINESS_NAME').
    """
    val = get_setting(key.lower())
    if val is not None:
        return val
    try:
        from flask import current_app
        return current_app.config.get(key.upper(), default)
    except Exception:
        return default


def sms_enabled(key):
    """
    Return True if the named SMS notification type is enabled.
    Defaults to True (on) if the setting has never been saved.
    key examples: 'sms_boarding_approval', 'sms_estimate', etc.
    """
    val = get_setting(key)
    if val is None:
        return True  # not configured → default on
    return val.strip() in ('1', 'true', 'on', 'yes')
