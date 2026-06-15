import sys
from app import create_app, db
from app.models import User, ServiceType, ServiceBlock, Pet, Appointment

print("Creating fresh database with service_blocks table...")
app = create_app()

with app.app_context():
    # Create all tables
    db.create_all()
    print("✓ All tables created successfully")
    
    # Verify service_blocks table exists
    from sqlalchemy import inspect
    inspector = inspect(db.engine)
    tables = inspector.get_table_names()
    
    if 'service_blocks' in tables:
        print("✓ service_blocks table confirmed")
    else:
        print("✗ ERROR: service_blocks table not created!")
        sys.exit(1)
    
    print("\n✓✓✓ Database structure created successfully! ✓✓✓")
