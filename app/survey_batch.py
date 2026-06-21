"""
survey_batch.py — Weekly Survey Follow-Up Batch
Sends satisfaction surveys to customers not surveyed in the past 90 days.

Triggered by Windows Task Scheduler every Sunday at 10:00 AM.
Place at: C:\RuffLifeRetreat\app\survey_batch.py
"""

import sys
import os
import logging
from datetime import datetime, timedelta

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(message)s',
    handlers=[
        logging.FileHandler(r'C:\RuffLifeRetreat\logs\survey_batch.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


def run_survey_batch():
    from app import create_app, db
    from app.models import User, SurveyResponse, Boarding, DaycareAttendance, Pet
    from app.survey_service import create_and_send_survey

    app = create_app()

    with app.app_context():
        ninety_days_ago = datetime.utcnow() - timedelta(days=90)

        # Find customers recently surveyed
        recently_surveyed_ids = {
            r.user_id for r in SurveyResponse.query
            .filter(SurveyResponse.sent_at >= ninety_days_ago)
            .all()
        }

        # Customers with at least one completed boarding
        has_boarding = {
            b.user_id for b in Boarding.query
            .filter(Boarding.status == 'completed')
            .all()
        }

        # Customers with at least one daycare attendance
        has_daycare = {
            Pet.query.get(a.pet_id).user_id
            for a in DaycareAttendance.query.all()
            if Pet.query.get(a.pet_id)
        }

        has_stay = has_boarding | has_daycare

        # Customers eligible — active, have a phone, not recently surveyed,
        # and have actually completed at least one stay
        eligible = User.query.filter(
            User.role == 'customer',
            User.is_active == True,
            User.phone.isnot(None),
            ~User.id.in_(recently_surveyed_ids),
            User.id.in_(has_stay)
        ).all()

        sent    = 0
        skipped = 0

        for user in eligible:
            try:
                success = create_and_send_survey(user, 'General', trigger='weekly_batch')
                if success:
                    sent += 1
                    logger.info(f'Survey sent to {user.first_name} {user.last_name} ({user.id})')
                else:
                    skipped += 1
            except Exception as e:
                logger.error(f'Failed to send survey to user {user.id}: {e}')
                skipped += 1

        logger.info(f'Weekly survey batch complete — {sent} sent, {skipped} skipped')
        return sent, skipped


if __name__ == '__main__':
    sent, skipped = run_survey_batch()
    print(f'Done — {sent} surveys sent, {skipped} skipped.')