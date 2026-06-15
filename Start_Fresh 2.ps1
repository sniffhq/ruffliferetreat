cd C:\RuffLifeRetreat
.\venv\Scripts\Activate.ps1
python -c "
from app import create_app, db
from app.models import (User, Pet, Appointment, Boarding, DaycareEnrollment,
    DaycareAttendance, DaycareWaitlist, SmsMessage, ReportCard, SurveyResponse,
    GalleryPhoto, PasswordResetToken)
app = create_app()
with app.app_context():
    # Delete in dependency order
    SurveyResponse.query.delete()
    SmsMessage.query.delete()
    ReportCard.query.delete()
    PasswordResetToken.query.delete()
    DaycareAttendance.query.delete()
    DaycareEnrollment.query.delete()
    DaycareWaitlist.query.delete()
    Boarding.query.delete()
    Appointment.query.delete()
    Pet.query.delete()
    # Delete non-admin users only
    User.query.filter_by(is_admin=False).delete()
    db.session.commit()
    print('Done — all customer data wiped. Admin accounts preserved.')
"