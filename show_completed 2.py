from app import create_app, db
from app.models import Boarding
app = create_app()
with app.app_context():
    # Show recently completed boardings so you can find the right one
    boardings = Boarding.query.filter_by(status="completed").order_by(Boarding.completed_at.desc()).limit(10).all()
    for b in boardings:
        print(f"id={b.id} | {b.pet.name} | {b.check_in_date} to {b.check_out_date} | completed={b.completed_at}")
