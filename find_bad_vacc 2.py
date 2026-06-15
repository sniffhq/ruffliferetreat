from app import create_app, db
from app.models import VaccinationRecord
app = create_app()
with app.app_context():
    from datetime import date
    bad = [v for v in VaccinationRecord.query.all()
           if v.expiration_date and v.expiration_date.year < 1900]
    for v in bad:
        print(f"id={v.id} | pet_id={v.pet_id} | {v.vaccine_name} | exp={v.expiration_date}")
