from app import create_app, db
from app.models import User
app = create_app()
with app.app_context():
    customers = User.query.filter_by(role="customer").order_by(User.last_name).all()
    for c in customers:
        print(f"id={c.id} | {c.first_name} {c.last_name} | phone: {c.phone}")
