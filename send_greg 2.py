from app import create_app, db
from app.models import User, Boarding, SmsMessage
from twilio.rest import Client
app = create_app()
with app.app_context():
    c = User.query.get(118)
    b = Boarding.query.get(105)
    from_number = app.config.get("TWILIO_PHONE_NUMBER")
    body = (
        f"\u2705 Hi {c.first_name}! Your boarding reservation for {b.pet.name} is confirmed. "
        f"Check-in: {b.check_in_date.strftime('%a, %b %d')} at {b.check_in_time}. "
        f"Check-out: {b.check_out_date.strftime('%a, %b %d')} at {b.check_out_time}. "
        f"Questions? Reply to this message. \u2014 Ruff Life Retreat"
    )
    client = Client(app.config.get("TWILIO_ACCOUNT_SID"), app.config.get("TWILIO_AUTH_TOKEN"))
    msg = client.messages.create(body=body, from_=from_number, to="+19122895450")
    log = SmsMessage(user_id=c.id, direction="outbound", from_number=from_number,
                     to_number="+19122895450", body=body, twilio_sid=msg.sid, is_read=True)
    db.session.add(log)
    db.session.commit()
    print(f"Sent: {msg.sid}")
