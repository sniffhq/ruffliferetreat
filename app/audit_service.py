"""
audit_service.py — Centralised audit logging for SniffHQ.

Usage anywhere in routes:
    from app.audit_service import audit
    audit('boarding.approved', 'boarding', booking.id,
          f'{pet.name} ({check_in} – {check_out})',
          f'Approved by {current_user.first_name}')
"""
import json
import logging
from datetime import datetime
from flask import request
from flask_login import current_user

logger = logging.getLogger(__name__)


def audit(action: str,
          entity_type: str  = None,
          entity_id:   int  = None,
          entity_name: str  = None,
          description: str  = None,
          extra:       dict = None):
    """
    Write one audit log entry.

    Parameters
    ----------
    action      : dot-namespaced verb, e.g. 'boarding.approved', 'customer.edited'
    entity_type : table/model name, e.g. 'boarding', 'customer', 'pet'
    entity_id   : primary key of the affected row
    entity_name : human-readable label, e.g. 'Hank – Jun 08 → Jun 12'
    description : full human-readable sentence for the log viewer
    extra       : arbitrary dict stored as JSON (before/after values, etc.)
    """
    try:
        from app import db
        from app.models import AuditLog

        user_id    = None
        user_email = 'system'
        user_name  = 'System'

        try:
            if current_user and current_user.is_authenticated:
                user_id    = current_user.id
                user_email = current_user.email
                user_name  = f'{current_user.first_name} {current_user.last_name}'
        except Exception:
            pass

        ip = None
        try:
            ip = request.headers.get('X-Forwarded-For', request.remote_addr)
            if ip and ',' in ip:
                ip = ip.split(',')[0].strip()
        except Exception:
            pass

        entry = AuditLog(
            timestamp   = datetime.now(),
            user_id     = user_id,
            user_email  = user_email,
            user_name   = user_name,
            action      = action,
            entity_type = entity_type,
            entity_id   = entity_id,
            entity_name = entity_name,
            description = description,
            ip_address  = ip,
            extra_data  = json.dumps(extra) if extra else None,
        )
        db.session.add(entry)
        db.session.commit()
    except Exception as e:
        logger.error(f'Audit log failed for action={action}: {e}')
