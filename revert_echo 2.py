from app import create_app, db
from app.models import Boarding
app = create_app()
with app.app_context():
    b = Boarding.query.get(32)
    b.status = "active"
    b.completed_at = None
    b.checked_in = True
    db.session.commit()
    print(f"Reverted: {b.pet.name} is now active again")
