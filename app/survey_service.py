"""
survey_service.py — Customer Satisfaction Survey for Ruff Life Retreat
Place at: C:/RuffLifeRetreat/app/survey_service.py
"""
import secrets
import logging
from datetime import datetime

logger = logging.getLogger(__name__)


def create_and_send_survey(user, service_type: str, trigger: str = 'manual') -> bool:
    """
    Create a survey token, save to DB, and send the SMS link to the customer.
    Returns True if SMS was sent successfully.

    Usage:
        from app.survey_service import create_and_send_survey
        create_and_send_survey(user, 'Boarding', trigger='boarding_complete')
    """
    try:
        from flask import current_app
        from app import db
        from app.models import SurveyResponse
        from app.sms_service import _send, _normalize_phone

        if not user.phone:
            logger.warning(f'Survey skipped for user {user.id} — no phone number.')
            return False

        # Generate unique token
        token = secrets.token_urlsafe(32)

        survey = SurveyResponse(
            user_id      = user.id,
            token        = token,
            service_type = service_type,
            trigger      = trigger,
            sent_at      = datetime.utcnow()
        )
        db.session.add(survey)
        db.session.commit()

        # Send SMS — bypasses opt-in (service communication)
        body = (
            f"Hi {user.first_name}! How was your recent {service_type} experience at "
            f"Ruff Life Retreat? We'd love your feedback: "
            f"https://rufflife.app/survey/{token}"
        )

        from twilio.rest import Client
        account_sid = current_app.config.get('TWILIO_ACCOUNT_SID')
        auth_token  = current_app.config.get('TWILIO_AUTH_TOKEN')
        from_number = current_app.config.get('TWILIO_PHONE_NUMBER')
        to_e164     = _normalize_phone(user.phone)

        if not to_e164:
            logger.warning(f'Survey SMS skipped — could not normalise phone for user {user.id}')
            return False

        client  = Client(account_sid, auth_token)
        message = client.messages.create(body=body, from_=from_number, to=to_e164)

        from app.models import SmsMessage
        log = SmsMessage(
            user_id     = user.id,
            direction   = 'outbound',
            from_number = from_number,
            to_number   = to_e164,
            body        = body,
            twilio_sid  = message.sid,
            is_read     = True
        )
        db.session.add(log)
        db.session.commit()

        logger.info(f'Survey sent to user {user.id} ({service_type}) — token {token[:8]}...')
        return True

    except Exception as e:
        logger.error(f'Failed to send survey to user {user.id}: {e}')
        return False


def check_daycare_milestone(user_id: int) -> bool:
    """
    Check if a customer has hit a 5-visit milestone today and send a survey if so.
    Call this after every daycare checkout.
    Returns True if a survey was sent.
    """
    try:
        from app.models import DaycareAttendance, DaycareEnrollment, Pet, User, SurveyResponse
        from app import db

        user = User.query.get(user_id)
        if not user:
            return False

        # Count total completed daycare visits for this customer
        total_visits = (DaycareAttendance.query
            .join(DaycareEnrollment, DaycareAttendance.enrollment_id == DaycareEnrollment.id)
            .join(Pet, DaycareEnrollment.pet_id == Pet.id)
            .filter(Pet.user_id == user_id)
            .filter(DaycareAttendance.check_out_time.isnot(None))
            .count())

        # Fire survey on every 5th visit
        if total_visits > 0 and total_visits % 5 == 0:
            # Don't double-send — check if survey already sent for this milestone
            existing = (SurveyResponse.query
                .filter_by(user_id=user_id, service_type='Daycare', trigger='daycare_milestone')
                .filter(SurveyResponse.sent_at.isnot(None))
                .count())
            if existing < (total_visits // 5):
                return create_and_send_survey(user, 'Daycare', trigger='daycare_milestone')

        return False

    except Exception as e:
        logger.error(f'Daycare milestone check failed for user {user_id}: {e}')
        return False