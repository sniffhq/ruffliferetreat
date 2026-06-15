#!/usr/bin/env python3
"""
Ruff Life Retreat - Create Admin User
Adds a new admin user to the database
Run with: python create_admin.py
"""

import sys
import os
from pathlib import Path

app_dir = Path(__file__).parent
sys.path.insert(0, str(app_dir))

def main():
    print("\n" + "="*70)
    print("Ruff Life Retreat - Create Admin User")
    print("="*70)
    
    try:
        from app import create_app, db
        from app.models import User
    except ImportError as e:
        print(f"\nERROR: Could not import app: {e}")
        print("Make sure you run this from: C:\\RuffLifeRetreat")
        return 1
    
    print("\nEnter new admin user information:")
    print("-" * 70)
    
    email = input("\nEmail address: ").strip()
    if not email or "@" not in email:
        print("ERROR: Invalid email address")
        return 1
    
    first_name = input("First name: ").strip()
    if not first_name:
        print("ERROR: First name required")
        return 1
    
    last_name = input("Last name: ").strip()
    if not last_name:
        print("ERROR: Last name required")
        return 1
    
    password = input("Password (min 8 characters): ").strip()
    if len(password) < 8:
        print("ERROR: Password must be at least 8 characters")
        return 1
    
    confirm_password = input("Confirm password: ").strip()
    if password != confirm_password:
        print("ERROR: Passwords do not match")
        return 1
    
    app = create_app()
    
    with app.app_context():
        existing_user = User.query.filter_by(email=email).first()
        if existing_user:
            print(f"\nERROR: User with email '{email}' already exists")
            return 1
        
        try:
            new_admin = User(
                email=email,
                first_name=first_name,
                last_name=last_name,
                is_admin=True
            )
            
            new_admin.set_password(password)
            db.session.add(new_admin)
            db.session.commit()
            
            print("\n" + "="*70)
            print("SUCCESS! Admin User Created")
            print("="*70)
            print(f"\nEmail: {email}")
            print(f"Name: {first_name} {last_name}")
            print(f"Role: Admin")
            
            print("\nLogin at: https://rufflife.app/login")
            print("="*70 + "\n")
            
            return 0
        
        except Exception as e:
            print(f"\nERROR: Could not create user: {e}")
            db.session.rollback()
            return 1

if __name__ == '__main__':
    exit_code = main()
    sys.exit(exit_code)