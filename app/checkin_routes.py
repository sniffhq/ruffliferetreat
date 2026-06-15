from flask import render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user
from datetime import datetime, date

def register_checkin_routes(app):
    """Register check-in/check-out routes"""
    from app import db
    from app.models import Appointment, Pet, ServiceType
    
    @app.route('/my-appointments')
    @login_required
    def my_appointments():
        """View user appointments with check-in/out status"""
        today = date.today()
        
        todays_appointments = Appointment.query.filter(
            Appointment.user_id == current_user.id,
            Appointment.appointment_date == today
        ).all()
        
        upcoming_appointments = Appointment.query.filter(
            Appointment.user_id == current_user.id,
            Appointment.appointment_date > today
        ).order_by(Appointment.appointment_date).limit(5).all()
        
        past_appointments = Appointment.query.filter(
            Appointment.user_id == current_user.id,
            Appointment.appointment_date < today
        ).order_by(Appointment.appointment_date.desc()).limit(10).all()
        
        return render_template('checkin/my_appointments.html',
                             todays_appointments=todays_appointments,
                             upcoming_appointments=upcoming_appointments,
                             past_appointments=past_appointments)
    
    @app.route('/check-in/<int:appointment_id>', methods=['GET', 'POST'])
    @login_required
    def check_in(appointment_id):
        """Check in for an appointment"""
        appointment = Appointment.query.get_or_404(appointment_id)
        
        if appointment.user_id != current_user.id:
            flash('You do not have permission to check in this appointment.', 'danger')
            return redirect(url_for('my_appointments'))
        
        if appointment.checked_in:
            flash('This appointment has already been checked in.', 'warning')
            return redirect(url_for('my_appointments'))
        
        if request.method == 'POST':
            notes = request.form.get('notes', '')
            
            appointment.checked_in = True
            appointment.check_in_time = datetime.utcnow()
            appointment.check_in_notes = notes
            appointment.status = 'in-progress'
            
            db.session.commit()
            
            flash(f'Successfully checked in {appointment.pet.name}!', 'success')
            return redirect(url_for('my_appointments'))
        
        return render_template('checkin/check_in.html', appointment=appointment)
    
    @app.route('/check-out/<int:appointment_id>', methods=['GET', 'POST'])
    @login_required
    def check_out(appointment_id):
        """Check out from an appointment"""
        appointment = Appointment.query.get_or_404(appointment_id)
        
        if appointment.user_id != current_user.id:
            flash('You do not have permission to check out this appointment.', 'danger')
            return redirect(url_for('my_appointments'))
        
        if not appointment.checked_in:
            flash('You must check in before checking out.', 'warning')
            return redirect(url_for('my_appointments'))
        
        if appointment.checked_out:
            flash('This appointment has already been checked out.', 'info')
            return redirect(url_for('my_appointments'))
        
        if request.method == 'POST':
            notes = request.form.get('notes', '')
            
            appointment.checked_out = True
            appointment.check_out_time = datetime.utcnow()
            appointment.check_out_notes = notes
            appointment.status = 'completed'
            
            db.session.commit()
            
            flash(f'Successfully checked out {appointment.pet.name}!', 'success')
            return redirect(url_for('my_appointments'))
        
        return render_template('checkin/check_out.html', appointment=appointment)


def register_public_kiosk_routes(app):
    """Register public kiosk routes for on-site check-in/out"""
    from flask import render_template, redirect, url_for, flash, request
    from datetime import datetime, date
    from app import db
    from app.models import Appointment, Pet, User
    
    @app.route('/kiosk')
    def kiosk_home():
        """Public kiosk landing page"""
        return render_template('kiosk/kiosk_home.html')
    
    @app.route('/kiosk/lookup', methods=['POST'])
    def kiosk_lookup():
        """Look up appointments by last name and pet name"""
        last_name = request.form.get('last_name', '').strip()
        pet_name = request.form.get('pet_name', '').strip()
        
        if not last_name or not pet_name:
            flash('Please enter both last name and pet name.', 'warning')
            return redirect(url_for('kiosk_home'))
        
        today = date.today()
        
        appointments = db.session.query(Appointment).join(
            Pet, Appointment.pet_id == Pet.id
        ).join(
            User, Appointment.user_id == User.id
        ).filter(
            User.last_name.ilike(f'%{last_name}%'),
            Pet.name.ilike(f'%{pet_name}%'),
            Appointment.appointment_date == today
        ).all()
        
        if not appointments:
            flash(f'No appointments found for {pet_name} with last name {last_name} today.', 'warning')
            return redirect(url_for('kiosk_home'))
        
        return render_template('kiosk/kiosk_appointments.html',
                             appointments=appointments,
                             last_name=last_name,
                             pet_name=pet_name)
    
    @app.route('/kiosk/check-in/<int:appointment_id>', methods=['GET', 'POST'])
    def kiosk_check_in(appointment_id):
        """Public kiosk check-in"""
        appointment = Appointment.query.get_or_404(appointment_id)
        
        if appointment.appointment_date != date.today():
            flash('This appointment is not scheduled for today.', 'danger')
            return redirect(url_for('kiosk_home'))
        
        if appointment.checked_in:
            flash(f'{appointment.pet.name} has already been checked in.', 'info')
            return redirect(url_for('kiosk_home'))
        
        if request.method == 'POST':
            notes = request.form.get('notes', '')
            
            appointment.checked_in = True
            appointment.check_in_time = datetime.utcnow()
            appointment.check_in_notes = notes
            appointment.status = 'in-progress'
            
            db.session.commit()
            
            flash(f'{appointment.pet.name} successfully checked in!', 'success')
            return redirect(url_for('kiosk_home'))
        
        return render_template('kiosk/kiosk_check_in.html', appointment=appointment)
    
    @app.route('/kiosk/check-out/<int:appointment_id>', methods=['GET', 'POST'])
    def kiosk_check_out(appointment_id):
        """Public kiosk check-out"""
        appointment = Appointment.query.get_or_404(appointment_id)
        
        if appointment.appointment_date != date.today():
            flash('This appointment is not scheduled for today.', 'danger')
            return redirect(url_for('kiosk_home'))
        
        if not appointment.checked_in:
            flash('You must check in before checking out.', 'warning')
            return redirect(url_for('kiosk_home'))
        
        if appointment.checked_out:
            flash(f'{appointment.pet.name} has already been checked out.', 'info')
            return redirect(url_for('kiosk_home'))
        
        if request.method == 'POST':
            notes = request.form.get('notes', '')
            
            appointment.checked_out = True
            appointment.check_out_time = datetime.utcnow()
            appointment.check_out_notes = notes
            appointment.status = 'completed'
            
            db.session.commit()
            
            flash(f'{appointment.pet.name} successfully checked out! Have a great day!', 'success')
            return redirect(url_for('kiosk_home'))
        
        return render_template('kiosk/kiosk_check_out.html', appointment=appointment)