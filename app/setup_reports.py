#!/usr/bin/env python3
"""
Ruff Life Retreat - Reports Setup Script
Automatically detects Flask app structure and installs reports.py in the correct location
"""

import os
import sys
from pathlib import Path

# The complete reports.py content
REPORTS_PY_CONTENT = '''from flask import Blueprint, render_template, request, send_file, flash, redirect, url_for
from flask_login import login_required, current_user
from datetime import datetime, timedelta, date
from sqlalchemy import func, and_, or_, extract
from app import db
from models import (
    User, Pet, Appointment, ServiceType, DaycareEnrollment, DaycareAttendance,
    VaccinationRecord, HealthCheck, IncidentLog, CapacityLog
)
import csv
import io
from decimal import Decimal
import json

reports_bp = Blueprint('reports', __name__, url_prefix='/reports')


# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================

def admin_required(f):
    """Decorator to require admin access"""
    from functools import wraps
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_admin:
            flash('Admin access required.', 'danger')
            return redirect(url_for('main.index'))
        return f(*args, **kwargs)
    return decorated_function


def parse_date_range(start_str, end_str):
    """Parse date range from request parameters"""
    try:
        start_date = datetime.strptime(start_str, '%Y-%m-%d').date() if start_str else None
        end_date = datetime.strptime(end_str, '%Y-%m-%d').date() if end_str else None
    except ValueError:
        start_date = end_date = None
    
    # Default to last 30 days if not specified
    if not start_date:
        start_date = date.today() - timedelta(days=30)
    if not end_date:
        end_date = date.today()
    
    return start_date, end_date


# ============================================================================
# STATE AUDIT/COMPLIANCE REPORTS
# ============================================================================

@reports_bp.route('/audit/vaccination-status')
@login_required
@admin_required
def vaccination_status_report():
    """Report on vaccination status and expiration"""
    # Get date range
    start_date_str = request.args.get('start_date')
    end_date_str = request.args.get('end_date')
    start_date, end_date = parse_date_range(start_date_str, end_date_str)
    
    # Get filter parameters
    status_filter = request.args.get('status', 'all')  # all, expiring, expired, current
    days_threshold = int(request.args.get('days', 30))  # Days until expiration threshold
    
    # Base query - get all active pets with their vaccinations
    query = db.session.query(
        Pet,
        User,
        VaccinationRecord
    ).join(
        User, Pet.user_id == User.id
    ).outerjoin(
        VaccinationRecord, Pet.id == VaccinationRecord.pet_id
    ).order_by(User.last_name, User.first_name, Pet.name)
    
    results = query.all()
    
    # Process results
    pet_vaccination_data = {}
    for pet, user, vax_record in results:
        pet_key = pet.id
        if pet_key not in pet_vaccination_data:
            pet_vaccination_data[pet_key] = {
                'pet': pet,
                'owner': user,
                'vaccinations': [],
                'has_expired': False,
                'has_expiring': False,
                'missing_required': []
            }
        
        if vax_record:
            vax_data = {
                'record': vax_record,
                'is_expired': vax_record.is_expired,
                'days_until_expiration': vax_record.days_until_expiration,
                'status': 'Expired' if vax_record.is_expired else 
                         'Expiring Soon' if vax_record.days_until_expiration <= days_threshold else 
                         'Current'
            }
            pet_vaccination_data[pet_key]['vaccinations'].append(vax_data)
            
            if vax_record.is_expired:
                pet_vaccination_data[pet_key]['has_expired'] = True
            elif vax_record.days_until_expiration <= days_threshold:
                pet_vaccination_data[pet_key]['has_expiring'] = True
    
    # Check for missing required vaccinations (Rabies, DHPP, Bordetella)
    required_vaccines = ['Rabies', 'DHPP', 'Bordetella']
    for pet_data in pet_vaccination_data.values():
        existing_vaccines = [v['record'].vaccine_name for v in pet_data['vaccinations']]
        for required in required_vaccines:
            if not any(required.lower() in existing.lower() for existing in existing_vaccines):
                pet_data['missing_required'].append(required)
    
    # Apply filters
    if status_filter != 'all':
        filtered_data = {}
        for pet_id, data in pet_vaccination_data.items():
            if status_filter == 'expired' and data['has_expired']:
                filtered_data[pet_id] = data
            elif status_filter == 'expiring' and data['has_expiring']:
                filtered_data[pet_id] = data
            elif status_filter == 'current' and not data['has_expired'] and not data['has_expiring']:
                filtered_data[pet_id] = data
            elif status_filter == 'missing' and data['missing_required']:
                filtered_data[pet_id] = data
        pet_vaccination_data = filtered_data
    
    # Calculate summary statistics
    total_pets = len(pet_vaccination_data)
    expired_count = sum(1 for d in pet_vaccination_data.values() if d['has_expired'])
    expiring_count = sum(1 for d in pet_vaccination_data.values() if d['has_expiring'] and not d['has_expired'])
    missing_count = sum(1 for d in pet_vaccination_data.values() if d['missing_required'])
    current_count = total_pets - expired_count - expiring_count
    
    summary = {
        'total_pets': total_pets,
        'expired_count': expired_count,
        'expiring_count': expiring_count,
        'missing_count': missing_count,
        'current_count': current_count,
        'days_threshold': days_threshold
    }
    
    return render_template('reports/vaccination_status.html',
                         pet_vaccination_data=pet_vaccination_data,
                         summary=summary,
                         start_date=start_date,
                         end_date=end_date,
                         status_filter=status_filter,
                         days_threshold=days_threshold)


@reports_bp.route('/audit/capacity-compliance')
@login_required
@admin_required
def capacity_compliance_report():
    """Report on facility capacity compliance"""
    # Get date range
    start_date_str = request.args.get('start_date')
    end_date_str = request.args.get('end_date')
    start_date, end_date = parse_date_range(start_date_str, end_date_str)
    
    # Get capacity logs for date range
    capacity_logs = CapacityLog.query.filter(
        and_(
            CapacityLog.log_date >= start_date,
            CapacityLog.log_date <= end_date
        )
    ).order_by(CapacityLog.log_date.desc()).all()
    
    # If no capacity logs exist, calculate from attendance/appointments
    if not capacity_logs:
        capacity_logs = calculate_capacity_from_data(start_date, end_date)
    
    # Calculate summary statistics
    total_days = len(capacity_logs)
    over_capacity_days = sum(1 for log in capacity_logs if log.over_capacity)
    avg_daycare = sum(log.daycare_count for log in capacity_logs) / total_days if total_days > 0 else 0
    avg_total = sum(log.total_count for log in capacity_logs) / total_days if total_days > 0 else 0
    max_daycare = max([log.daycare_count for log in capacity_logs]) if capacity_logs else 0
    max_total = max([log.total_count for log in capacity_logs]) if capacity_logs else 0
    
    summary = {
        'total_days': total_days,
        'over_capacity_days': over_capacity_days,
        'compliance_rate': ((total_days - over_capacity_days) / total_days * 100) if total_days > 0 else 100,
        'avg_daycare': avg_daycare,
        'avg_total': avg_total,
        'max_daycare': max_daycare,
        'max_total': max_total
    }
    
    return render_template('reports/capacity_compliance.html',
                         capacity_logs=capacity_logs,
                         summary=summary,
                         start_date=start_date,
                         end_date=end_date)


def calculate_capacity_from_data(start_date, end_date):
    """Calculate capacity from attendance and appointment data when logs don't exist"""
    capacity_data = []
    current_date = start_date
    
    while current_date <= end_date:
        # Count daycare attendance
        daycare_count = db.session.query(func.count(DaycareAttendance.id)).filter(
            func.date(DaycareAttendance.check_in_time) == current_date
        ).scalar() or 0
        
        # Count other appointments
        other_count = db.session.query(func.count(Appointment.id)).filter(
            and_(
                Appointment.appointment_date == current_date,
                Appointment.status.in_(['confirmed', 'checked_in'])
            )
        ).scalar() or 0
        
        total_count = daycare_count + other_count
        
        # Create temporary capacity log object
        log = type('obj', (object,), {
            'log_date': current_date,
            'daycare_count': daycare_count,
            'boarding_count': other_count,
            'grooming_count': 0,
            'total_count': total_count,
            'daycare_limit': 30,
            'boarding_limit': 20,
            'total_limit': 50,
            'over_capacity': total_count > 50,
            'notes': 'Calculated from attendance data',
            'daycare_percentage': (daycare_count / 30 * 100) if daycare_count > 0 else 0,
            'total_percentage': (total_count / 50 * 100) if total_count > 0 else 0
        })()
        
        capacity_data.append(log)
        current_date += timedelta(days=1)
    
    return capacity_data


@reports_bp.route('/audit/incident-log')
@login_required
@admin_required
def incident_log_report():
    """Report on all incidents"""
    # Get date range
    start_date_str = request.args.get('start_date')
    end_date_str = request.args.get('end_date')
    start_date, end_date = parse_date_range(start_date_str, end_date_str)
    
    # Get filter parameters
    incident_type = request.args.get('incident_type', 'all')
    severity = request.args.get('severity', 'all')
    resolved_filter = request.args.get('resolved', 'all')
    
    # Build query
    query = IncidentLog.query.filter(
        and_(
            IncidentLog.incident_date >= start_date,
            IncidentLog.incident_date <= end_date
        )
    )
    
    if incident_type != 'all':
        query = query.filter(IncidentLog.incident_type == incident_type)
    
    if severity != 'all':
        query = query.filter(IncidentLog.severity == severity)
    
    if resolved_filter == 'resolved':
        query = query.filter(IncidentLog.resolved == True)
    elif resolved_filter == 'unresolved':
        query = query.filter(IncidentLog.resolved == False)
    
    incidents = query.order_by(IncidentLog.incident_date.desc(), IncidentLog.incident_time.desc()).all()
    
    # Load pet and owner info for each incident
    for incident in incidents:
        if incident.pet_id:
            incident.pet = Pet.query.get(incident.pet_id)
            if incident.pet:
                incident.owner = User.query.get(incident.pet.user_id)
    
    # Calculate summary
    total_incidents = len(incidents)
    by_type = db.session.query(
        IncidentLog.incident_type, 
        func.count(IncidentLog.id)
    ).filter(
        and_(
            IncidentLog.incident_date >= start_date,
            IncidentLog.incident_date <= end_date
        )
    ).group_by(IncidentLog.incident_type).all()
    
    by_severity = db.session.query(
        IncidentLog.severity,
        func.count(IncidentLog.id)
    ).filter(
        and_(
            IncidentLog.incident_date >= start_date,
            IncidentLog.incident_date <= end_date
        )
    ).group_by(IncidentLog.severity).all()
    
    resolved_count = sum(1 for i in incidents if i.resolved)
    
    summary = {
        'total_incidents': total_incidents,
        'resolved_count': resolved_count,
        'unresolved_count': total_incidents - resolved_count,
        'by_type': dict(by_type),
        'by_severity': dict(by_severity)
    }
    
    return render_template('reports/incident_log.html',
                         incidents=incidents,
                         summary=summary,
                         start_date=start_date,
                         end_date=end_date,
                         incident_type=incident_type,
                         severity=severity,
                         resolved_filter=resolved_filter)


@reports_bp.route('/audit/health-checks')
@login_required
@admin_required
def health_check_report():
    """Report on health checks performed"""
    # Get date range
    start_date_str = request.args.get('start_date')
    end_date_str = request.args.get('end_date')
    start_date, end_date = parse_date_range(start_date_str, end_date_str)
    
    # Get filter parameters
    requires_attention = request.args.get('requires_attention', 'all')
    
    # Build query
    query = HealthCheck.query.filter(
        and_(
            HealthCheck.check_date >= start_date,
            HealthCheck.check_date <= end_date
        )
    )
    
    if requires_attention == 'yes':
        query = query.filter(HealthCheck.requires_attention == True)
    elif requires_attention == 'no':
        query = query.filter(HealthCheck.requires_attention == False)
    
    health_checks = query.order_by(HealthCheck.check_date.desc(), HealthCheck.check_time.desc()).all()
    
    # Load pet and owner info
    for check in health_checks:
        check.pet = Pet.query.get(check.pet_id)
        if check.pet:
            check.owner = User.query.get(check.pet.user_id)
    
    # Calculate summary
    total_checks = len(health_checks)
    attention_needed = sum(1 for c in health_checks if c.requires_attention)
    owner_notified = sum(1 for c in health_checks if c.owner_notified)
    
    summary = {
        'total_checks': total_checks,
        'attention_needed': attention_needed,
        'owner_notified': owner_notified,
        'completion_rate': (total_checks / ((end_date - start_date).days + 1)) if total_checks > 0 else 0
    }
    
    return render_template('reports/health_checks.html',
                         health_checks=health_checks,
                         summary=summary,
                         start_date=start_date,
                         end_date=end_date,
                         requires_attention=requires_attention)


# ============================================================================
# OPERATIONAL REPORTS
# ============================================================================

@reports_bp.route('/operational/occupancy')
@login_required
@admin_required
def occupancy_report():
    """Report on facility occupancy and trends"""
    # Get date range
    start_date_str = request.args.get('start_date')
    end_date_str = request.args.get('end_date')
    start_date, end_date = parse_date_range(start_date_str, end_date_str)
    
    # Get daily attendance counts
    daily_data = []
    current_date = start_date
    
    while current_date <= end_date:
        # Daycare attendance
        daycare_count = db.session.query(func.count(DaycareAttendance.id)).filter(
            func.date(DaycareAttendance.check_in_time) == current_date
        ).scalar() or 0
        
        # Other appointments
        appointments_count = db.session.query(func.count(Appointment.id)).filter(
            and_(
                Appointment.appointment_date == current_date,
                Appointment.status.in_(['confirmed', 'checked_in', 'completed'])
            )
        ).scalar() or 0
        
        # Revenue (if price data available)
        daily_revenue = db.session.query(func.sum(ServiceType.base_price)).join(
            Appointment, Appointment.service_type_id == ServiceType.id
        ).filter(
            and_(
                Appointment.appointment_date == current_date,
                Appointment.status == 'completed'
            )
        ).scalar() or Decimal('0.00')
        
        daily_data.append({
            'date': current_date,
            'daycare_count': daycare_count,
            'appointments_count': appointments_count,
            'total_count': daycare_count + appointments_count,
            'revenue': float(daily_revenue)
        })
        
        current_date += timedelta(days=1)
    
    # Calculate summary statistics
    total_days = len(daily_data)
    avg_daycare = sum(d['daycare_count'] for d in daily_data) / total_days if total_days > 0 else 0
    avg_appointments = sum(d['appointments_count'] for d in daily_data) / total_days if total_days > 0 else 0
    avg_total = sum(d['total_count'] for d in daily_data) / total_days if total_days > 0 else 0
    total_revenue = sum(d['revenue'] for d in daily_data)
    
    peak_day = max(daily_data, key=lambda x: x['total_count']) if daily_data else None
    
    summary = {
        'total_days': total_days,
        'avg_daycare': avg_daycare,
        'avg_appointments': avg_appointments,
        'avg_total': avg_total,
        'total_revenue': total_revenue,
        'avg_daily_revenue': total_revenue / total_days if total_days > 0 else 0,
        'peak_day': peak_day
    }
    
    return render_template('reports/occupancy.html',
                         daily_data=daily_data,
                         summary=summary,
                         start_date=start_date,
                         end_date=end_date)


@reports_bp.route('/operational/revenue')
@login_required
@admin_required
def revenue_report():
    """Report on revenue by service type"""
    # Get date range
    start_date_str = request.args.get('start_date')
    end_date_str = request.args.get('end_date')
    start_date, end_date = parse_date_range(start_date_str, end_date_str)
    
    # Revenue by service type
    revenue_by_service = db.session.query(
        ServiceType.name,
        func.count(Appointment.id).label('booking_count'),
        func.sum(ServiceType.base_price).label('total_revenue')
    ).join(
        Appointment, Appointment.service_type_id == ServiceType.id
    ).filter(
        and_(
            Appointment.appointment_date >= start_date,
            Appointment.appointment_date <= end_date,
            Appointment.status == 'completed'
        )
    ).group_by(ServiceType.name).all()
    
    # Monthly breakdown
    monthly_revenue = db.session.query(
        extract('year', Appointment.appointment_date).label('year'),
        extract('month', Appointment.appointment_date).label('month'),
        func.count(Appointment.id).label('booking_count'),
        func.sum(ServiceType.base_price).label('total_revenue')
    ).join(
        ServiceType, Appointment.service_type_id == ServiceType.id
    ).filter(
        and_(
            Appointment.appointment_date >= start_date,
            Appointment.appointment_date <= end_date,
            Appointment.status == 'completed'
        )
    ).group_by('year', 'month').order_by('year', 'month').all()
    
    # Calculate totals
    total_revenue = sum(float(r.total_revenue or 0) for r in revenue_by_service)
    total_bookings = sum(r.booking_count for r in revenue_by_service)
    
    summary = {
        'total_revenue': total_revenue,
        'total_bookings': total_bookings,
        'avg_booking_value': total_revenue / total_bookings if total_bookings > 0 else 0
    }
    
    return render_template('reports/revenue.html',
                         revenue_by_service=revenue_by_service,
                         monthly_revenue=monthly_revenue,
                         summary=summary,
                         start_date=start_date,
                         end_date=end_date)


# ============================================================================
# CUSTOMER REPORTS
# ============================================================================

@reports_bp.route('/customer/visit-history')
@login_required
@admin_required
def customer_visit_history():
    """Report on customer visit history"""
    # Get optional customer filter
    customer_id = request.args.get('customer_id', type=int)
    start_date_str = request.args.get('start_date')
    end_date_str = request.args.get('end_date')
    start_date, end_date = parse_date_range(start_date_str, end_date_str)
    
    # Build query
    query = db.session.query(
        User,
        Pet,
        func.count(Appointment.id).label('appointment_count'),
        func.count(DaycareAttendance.id).label('daycare_visits')
    ).outerjoin(
        Pet, User.id == Pet.user_id
    ).outerjoin(
        Appointment, and_(
            Pet.id == Appointment.pet_id,
            Appointment.appointment_date >= start_date,
            Appointment.appointment_date <= end_date
        )
    ).outerjoin(
        DaycareEnrollment, Pet.id == DaycareEnrollment.pet_id
    ).outerjoin(
        DaycareAttendance, and_(
            DaycareEnrollment.id == DaycareAttendance.enrollment_id,
            func.date(DaycareAttendance.check_in_time) >= start_date,
            func.date(DaycareAttendance.check_in_time) <= end_date
        )
    )
    
    if customer_id:
        query = query.filter(User.id == customer_id)
    
    results = query.group_by(User.id, Pet.id).all()
    
    # Organize by customer
    customer_data = {}
    for user, pet, apt_count, daycare_count in results:
        if user.id not in customer_data:
            customer_data[user.id] = {
                'user': user,
                'pets': [],
                'total_appointments': 0,
                'total_daycare': 0
            }
        
        if pet:
            customer_data[user.id]['pets'].append({
                'pet': pet,
                'appointment_count': apt_count,
                'daycare_visits': daycare_count
            })
            customer_data[user.id]['total_appointments'] += apt_count
            customer_data[user.id]['total_daycare'] += daycare_count
    
    # Get all customers for dropdown
    all_customers = User.query.order_by(User.last_name, User.first_name).all()
    
    return render_template('reports/visit_history.html',
                         customer_data=customer_data,
                         all_customers=all_customers,
                         selected_customer_id=customer_id,
                         start_date=start_date,
                         end_date=end_date)


# ============================================================================
# EXPORT FUNCTIONS
# ============================================================================

@reports_bp.route('/export/vaccination-status/csv')
@login_required
@admin_required
def export_vaccination_csv():
    """Export vaccination status to CSV"""
    # Get all pets with vaccinations
    pets = Pet.query.join(User).order_by(User.last_name, User.first_name, Pet.name).all()
    
    # Create CSV
    output = io.StringIO()
    writer = csv.writer(output)
    
    # Write header
    writer.writerow([
        'Owner Last Name', 'Owner First Name', 'Owner Email', 'Owner Phone',
        'Pet Name', 'Breed', 'Vaccine Name', 'Vaccination Date', 'Expiration Date',
        'Days Until Expiration', 'Status', 'Veterinarian', 'Clinic'
    ])
    
    # Write data
    for pet in pets:
        owner = pet.owner
        for vax in pet.vaccination_records:
            status = 'Expired' if vax.is_expired else 'Expiring Soon' if vax.days_until_expiration <= 30 else 'Current'
            writer.writerow([
                owner.last_name, owner.first_name, owner.email, owner.phone,
                pet.name, pet.breed, vax.vaccine_name, vax.vaccination_date,
                vax.expiration_date, vax.days_until_expiration, status,
                vax.veterinarian or '', vax.clinic_name or ''
            ])
    
    # Prepare response
    output.seek(0)
    return send_file(
        io.BytesIO(output.getvalue().encode('utf-8')),
        mimetype='text/csv',
        as_attachment=True,
        download_name=f'vaccination_status_{date.today()}.csv'
    )


@reports_bp.route('/export/incidents/csv')
@login_required
@admin_required
def export_incidents_csv():
    """Export incident log to CSV"""
    start_date_str = request.args.get('start_date')
    end_date_str = request.args.get('end_date')
    start_date, end_date = parse_date_range(start_date_str, end_date_str)
    
    incidents = IncidentLog.query.filter(
        and_(
            IncidentLog.incident_date >= start_date,
            IncidentLog.incident_date <= end_date
        )
    ).order_by(IncidentLog.incident_date.desc()).all()
    
    # Create CSV
    output = io.StringIO()
    writer = csv.writer(output)
    
    # Write header
    writer.writerow([
        'Date', 'Time', 'Type', 'Severity', 'Pet Name', 'Owner Name',
        'Description', 'Action Taken', 'Reported By', 'Owner Notified',
        'Vet Contacted', 'Resolved', 'Resolution'
    ])
    
    # Write data
    for incident in incidents:
        pet_name = incident.pet.name if incident.pet else 'N/A'
        owner_name = f"{incident.pet.owner.first_name} {incident.pet.owner.last_name}" if incident.pet else 'N/A'
        
        writer.writerow([
            incident.incident_date, incident.incident_time.strftime('%H:%M'),
            incident.incident_type, incident.severity, pet_name, owner_name,
            incident.description, incident.action_taken, incident.reported_by,
            'Yes' if incident.owner_notified else 'No',
            'Yes' if incident.vet_contacted else 'No',
            'Yes' if incident.resolved else 'No',
            incident.resolution or ''
        ])
    
    # Prepare response
    output.seek(0)
    return send_file(
        io.BytesIO(output.getvalue().encode('utf-8')),
        mimetype='text/csv',
        as_attachment=True,
        download_name=f'incident_log_{start_date}_to_{end_date}.csv'
    )


# ============================================================================
# MAIN REPORTS DASHBOARD
# ============================================================================

@reports_bp.route('/')
@login_required
@admin_required
def reports_dashboard():
    """Main reports dashboard"""
    return render_template('reports/dashboard.html')
'''


def detect_flask_structure():
    """Detect the Flask app structure"""
    current_dir = Path.cwd()
    
    # Check for different patterns
    if (current_dir / 'app.py').exists():
        return 'flat', current_dir, 'app.py'
    elif (current_dir / '__init__.py').exists() and (current_dir / 'models.py').exists():
        return 'flat', current_dir, '__init__.py'
    elif (current_dir / 'app' / '__init__.py').exists():
        return 'package', current_dir / 'app', 'app/__init__.py'
    elif (current_dir / 'application' / '__init__.py').exists():
        return 'package', current_dir / 'application', 'application/__init__.py'
    else:
        # Try to find models.py to determine structure
        for root, dirs, files in os.walk(current_dir):
            if 'models.py' in files:
                models_path = Path(root)
                if (models_path / '__init__.py').exists():
                    return 'package', models_path, str(models_path / '__init__.py')
                else:
                    main_file = None
                    if (models_path / 'app.py').exists():
                        main_file = 'app.py'
                    elif (models_path / '__init__.py').exists():
                        main_file = '__init__.py'
                    return 'flat', models_path, main_file
    
    return None, None, None


def create_reports_file(target_dir):
    """Create the reports.py file"""
    reports_path = target_dir / 'reports.py'
    
    if reports_path.exists():
        response = input(f"\n⚠️  {reports_path} already exists. Overwrite? (y/n): ")
        if response.lower() != 'y':
            print("Skipping reports.py creation.")
            return False
    
    with open(reports_path, 'w', encoding='utf-8') as f:
        f.write(REPORTS_PY_CONTENT)
    
    return True


def update_main_app_file(app_file_path, structure_type, app_dir):
    """Add blueprint registration to main app file"""
    if not app_file_path or not Path(app_file_path).exists():
        return False
    
    with open(app_file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Check if already registered
    if 'reports_bp' in content or 'from reports import' in content:
        print("✓ Blueprint registration already exists in main app file")
        return True
    
    # Determine import statement based on structure
    if structure_type == 'package':
        if 'app/' in str(app_file_path):
            import_line = "from app.reports import reports_bp"
        else:
            import_line = "from reports import reports_bp"
    else:
        import_line = "from reports import reports_bp"
    
    registration_line = "app.register_blueprint(reports_bp)"
    
    print(f"\n{'='*60}")
    print("MANUAL STEP REQUIRED: Register the Blueprint")
    print('='*60)
    print(f"\nAdd these lines to your {app_file_path}:\n")
    print(f"1. Add this import at the top (with other imports):")
    print(f"   {import_line}\n")
    print(f"2. Add this registration (after app = Flask(__name__) or create_app()):")
    print(f"   {registration_line}\n")
    print('='*60)
    
    return False


def create_templates_directory(base_dir):
    """Create templates/reports directory if it doesn't exist"""
    templates_dir = base_dir / 'templates' / 'reports'
    templates_dir.mkdir(parents=True, exist_ok=True)
    return templates_dir


def main():
    print("=" * 60)
    print("Ruff Life Retreat - Reports Setup Script")
    print("=" * 60)
    print("\nDetecting Flask application structure...")
    
    structure_type, target_dir, main_app_file = detect_flask_structure()
    
    if not structure_type:
        print("\n❌ Could not detect Flask application structure!")
        print("\nPlease ensure you're running this script from your Flask project root.")
        print("Looking for: app.py, __init__.py, or app/models.py")
        sys.exit(1)
    
    print(f"\n✓ Detected structure: {structure_type.upper()}")
    print(f"✓ Target directory: {target_dir}")
    print(f"✓ Main app file: {main_app_file or 'Not found'}")
    
    # Confirm with user
    print(f"\nReports module will be created at:")
    print(f"  {target_dir / 'reports.py'}")
    
    response = input("\nProceed? (y/n): ")
    if response.lower() != 'y':
        print("Setup cancelled.")
        sys.exit(0)
    
    print("\n" + "=" * 60)
    print("Creating files...")
    print("=" * 60)
    
    # Create reports.py
    if create_reports_file(target_dir):
        print(f"✓ Created {target_dir / 'reports.py'}")
    else:
        print(f"⚠️  Skipped {target_dir / 'reports.py'}")
    
    # Create templates directory
    if structure_type == 'package':
        templates_base = target_dir.parent / 'templates'
    else:
        templates_base = target_dir / 'templates'
    
    templates_dir = create_templates_directory(templates_base)
    print(f"✓ Created/verified {templates_dir}")
    
    # Try to update main app file
    if main_app_file:
        update_main_app_file(target_dir / main_app_file if structure_type == 'flat' else main_app_file, 
                           structure_type, target_dir)
    
    print("\n" + "=" * 60)
    print("✅ Setup Complete!")
    print("=" * 60)
    
    print("\nNext steps:")
    print("1. ✓ reports.py has been created")
    print("2. ✓ templates/reports/ directory created")
    print("3. ⚠️  Register the blueprint in your main app file (see instructions above)")
    print("4. 📝 Create report templates (see REPORTING_INTEGRATION_GUIDE.md)")
    print("5. 🗃️  Run database migration: python add_audit_tables_migration.py")
    print("6. 🚀 Start your Flask app and navigate to /reports")
    
    print("\n" + "=" * 60)
    print("Files created:")
    print("=" * 60)
    print(f"  {target_dir / 'reports.py'}")
    print(f"  {templates_dir}/ (directory)")
    
    print("\n💡 Tip: Run the database migration next:")
    print("   python add_audit_tables_migration.py")


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nSetup cancelled by user.")
        sys.exit(0)
    except Exception as e:
        print(f"\n❌ Error: {str(e)}")
        import traceback
        traceback.print_exc()
        sys.exit(1)