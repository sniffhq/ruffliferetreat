from flask import render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user
from datetime import datetime, date, timedelta
from functools import wraps
from app import db
from app.models import Pet, User, DaycareEnrollment, DaycareAttendance

def admin_required(f):
    @wraps(f)
    @login_required
    def decorated_function(*args, **kwargs):
        if not current_user.is_admin:
            flash('You must be an administrator to access this page.', 'danger')
            return redirect('/')
        return f(*args, **kwargs)
    return decorated_function


def register_daycare_routes(app):
    
    @app.route('/admin/daycare')
    @admin_required
    def admin_daycare():
        enrollments = DaycareEnrollment.query.filter_by(active=True).all()
        today = date.today()
        today_attendance = DaycareAttendance.query.filter_by(date=today).all()
        all_pets = Pet.query.join(User).order_by(User.last_name, Pet.name).all()
        
        return render_template('admin/daycare.html',
                             enrollments=enrollments,
                             today_attendance=today_attendance,
                             all_pets=all_pets,
                             today=today)
    
    @app.route('/admin/daycare/enroll/<int:pet_id>', methods=['POST'])
    @admin_required
    def enroll_daycare(pet_id):
        pet = Pet.query.get_or_404(pet_id)
        
        existing = DaycareEnrollment.query.filter_by(pet_id=pet_id, active=True).first()
        if existing:
            flash(f'{pet.name} is already enrolled in daycare.', 'info')
            return redirect(url_for('admin_daycare'))
        
        enrollment = DaycareEnrollment(
            pet_id=pet_id,
            monday=request.form.get('monday') == 'on',
            tuesday=request.form.get('tuesday') == 'on',
            wednesday=request.form.get('wednesday') == 'on',
            thursday=request.form.get('thursday') == 'on',
            friday=request.form.get('friday') == 'on',
            saturday=request.form.get('saturday') == 'on',
            sunday=request.form.get('sunday') == 'on',
            notes=request.form.get('notes', '')
        )
        
        db.session.add(enrollment)
        db.session.commit()
        
        flash(f'{pet.name} enrolled in daycare successfully!', 'success')
        return redirect(url_for('admin_daycare'))
    
    @app.route('/admin/daycare/unenroll/<int:enrollment_id>', methods=['POST'])
    @admin_required
    def unenroll_daycare(enrollment_id):
        enrollment = DaycareEnrollment.query.get_or_404(enrollment_id)
        enrollment.active = False
        db.session.commit()
        
        flash(f'{enrollment.pet.name} removed from daycare.', 'success')
        return redirect(url_for('admin_daycare'))
    
    @app.route('/admin/daycare/attendance')
    @admin_required
    def daycare_attendance():
        start_date = date.today() - timedelta(days=30)
        attendance_records = DaycareAttendance.query.filter(
            DaycareAttendance.date >= start_date
        ).order_by(DaycareAttendance.date.desc()).all()
        
        return render_template('admin/daycare_attendance.html',
                             attendance_records=attendance_records)


def register_daycare_kiosk_routes(app):
    
    @app.route('/kiosk/daycare-lookup', methods=['POST'])
    def kiosk_daycare_lookup():
        last_name = request.form.get('last_name', '').strip()
        pet_name = request.form.get('pet_name', '').strip()
        
        if not last_name or not pet_name:
            flash('Please enter both last name and pet name.', 'warning')
            return redirect(url_for('kiosk_home'))
        
        today = date.today()
        
        enrollments = db.session.query(DaycareEnrollment).join(
            Pet, DaycareEnrollment.pet_id == Pet.id
        ).join(
            User, Pet.owner_id == User.id
        ).filter(
            User.last_name.ilike(f'%{last_name}%'),
            Pet.name.ilike(f'%{pet_name}%'),
            DaycareEnrollment.active == True
        ).all()
        
        if not enrollments:
            flash(f'No daycare enrollment found for {pet_name} with last name {last_name}.', 'warning')
            return redirect(url_for('kiosk_home'))
        
        daycare_visits = []
        for enrollment in enrollments:
            attendance = DaycareAttendance.query.filter_by(
                pet_id=enrollment.pet_id,
                date=today
            ).first()
            
            if not attendance:
                attendance = DaycareAttendance(
                    pet_id=enrollment.pet_id,
                    date=today
                )
                db.session.add(attendance)
            
            daycare_visits.append({
                'attendance': attendance,
                'enrollment': enrollment
            })
        
        db.session.commit()
        
        return render_template('kiosk/daycare_visits.html',
                             daycare_visits=daycare_visits,
                             last_name=last_name,
                             pet_name=pet_name)
    
    @app.route('/kiosk/daycare-checkin/<int:attendance_id>', methods=['GET', 'POST'])
    def kiosk_daycare_checkin(attendance_id):
        attendance = DaycareAttendance.query.get_or_404(attendance_id)
        
        if attendance.checked_in:
            flash(f'{attendance.pet.name} has already been checked in.', 'info')
            return redirect(url_for('kiosk_home'))
        
        if request.method == 'POST':
            notes = request.form.get('notes', '')
            
            attendance.checked_in = True
            attendance.check_in_time = datetime.utcnow()
            attendance.check_in_notes = notes
            
            db.session.commit()
            
            flash(f'{attendance.pet.name} checked in for daycare!', 'success')
            return redirect(url_for('kiosk_home'))
        
        return render_template('kiosk/daycare_checkin.html', attendance=attendance)
    
    @app.route('/kiosk/daycare-checkout/<int:attendance_id>', methods=['GET', 'POST'])
    def kiosk_daycare_checkout(attendance_id):
        attendance = DaycareAttendance.query.get_or_404(attendance_id)
        
        if not attendance.checked_in:
            flash('You must check in before checking out.', 'warning')
            return redirect(url_for('kiosk_home'))
        
        if attendance.checked_out:
            flash(f'{attendance.pet.name} has already been checked out.', 'info')
            return redirect(url_for('kiosk_home'))
        
        if request.method == 'POST':
            notes = request.form.get('notes', '')
            
            attendance.checked_out = True
            attendance.check_out_time = datetime.utcnow()
            attendance.check_out_notes = notes
            
            db.session.commit()
            
            flash(f'{attendance.pet.name} checked out from daycare! Have a great day!', 'success')
            return redirect(url_for('kiosk_home'))
        
        return render_template('kiosk/daycare_checkout.html', attendance=attendance)
