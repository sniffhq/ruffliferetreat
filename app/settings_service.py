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
