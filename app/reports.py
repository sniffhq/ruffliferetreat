from flask import Blueprint, render_template, request, send_file, flash, redirect, url_for
from flask_login import login_required, current_user
from datetime import datetime, timedelta, date, time
from sqlalchemy import func, and_, or_, extract
from . import db
from .models import (
    User, Pet, Appointment, ServiceType, DaycareEnrollment, DaycareAttendance,
    VaccinationRecord, HealthCheck, IncidentLog, CapacityLog
)
import csv
import io
from decimal import Decimal
import json
import zipfile
import os
from PIL import Image

# Changed url_prefix from '/reports' to '/admin/reports'
reports_bp = Blueprint('reports', __name__, url_prefix='/admin/reports')


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


@reports_bp.route('/operational/daycare-attendance')
@login_required
@admin_required
def daycare_attendance_report():
    """Report on daycare check-ins and check-outs"""
    # Get date range
    start_date_str = request.args.get('start_date')
    end_date_str = request.args.get('end_date')
    start_date, end_date = parse_date_range(start_date_str, end_date_str)
    
    # Get filter parameters
    pet_id = request.args.get('pet_id', type=int)
    day_filter = request.args.get('day', 'all')  # all, monday, tuesday, wednesday, thursday, friday
    
    # Build query for attendance records
    query = db.session.query(DaycareAttendance).join(
        DaycareEnrollment, DaycareAttendance.enrollment_id == DaycareEnrollment.id
    ).join(
        Pet, DaycareEnrollment.pet_id == Pet.id
    ).join(
        User, Pet.user_id == User.id
    ).filter(
        func.date(DaycareAttendance.check_in_time) >= start_date,
        func.date(DaycareAttendance.check_in_time) <= end_date
    )
    
    # Apply pet filter if specified
    if pet_id:
        query = query.filter(Pet.id == pet_id)
    
    # Get all attendance records
    attendance_records = query.order_by(DaycareAttendance.check_in_time.desc()).all()
    
    # Apply day filter if specified
    if day_filter != 'all':
        day_map = {
            'monday': 0, 'tuesday': 1, 'wednesday': 2,
            'thursday': 3, 'friday': 4, 'saturday': 5, 'sunday': 6
        }
        target_weekday = day_map.get(day_filter)
        if target_weekday is not None:
            attendance_records = [
                record for record in attendance_records
                if record.check_in_time.weekday() == target_weekday
            ]
    
    # Enrich records with pet and owner info
    for record in attendance_records:
        record.enrollment = DaycareEnrollment.query.get(record.enrollment_id)
        record.pet = Pet.query.get(record.enrollment.pet_id) if record.enrollment else None
        record.owner = User.query.get(record.pet.user_id) if record.pet else None
        
        # Calculate duration if checked out
        if record.check_out_time:
            duration = record.check_out_time - record.check_in_time
            record.duration_hours = duration.total_seconds() / 3600
        else:
            record.duration_hours = None
    
    # Calculate summary statistics
    total_visits = len(attendance_records)
    checked_out_count = sum(1 for r in attendance_records if r.check_out_time)
    still_checked_in = total_visits - checked_out_count
    
    # Average duration for completed visits
    completed_durations = [r.duration_hours for r in attendance_records if r.duration_hours is not None]
    avg_duration = sum(completed_durations) / len(completed_durations) if completed_durations else 0
    
    # Daily attendance counts
    daily_counts = {}
    for record in attendance_records:
        check_in_date = record.check_in_time.date()
        if check_in_date not in daily_counts:
            daily_counts[check_in_date] = 0
        daily_counts[check_in_date] += 1
    
    avg_daily_attendance = sum(daily_counts.values()) / len(daily_counts) if daily_counts else 0
    peak_day = max(daily_counts.items(), key=lambda x: x[1]) if daily_counts else (None, 0)
    
    # Breakdown by day of week
    weekday_counts = {i: 0 for i in range(7)}
    for record in attendance_records:
        weekday = record.check_in_time.weekday()
        weekday_counts[weekday] += 1
    
    weekday_names = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
    weekday_breakdown = {weekday_names[i]: count for i, count in weekday_counts.items()}
    
    summary = {
        'total_visits': total_visits,
        'checked_out_count': checked_out_count,
        'still_checked_in': still_checked_in,
        'avg_duration': avg_duration,
        'avg_daily_attendance': avg_daily_attendance,
        'peak_day': peak_day,
        'weekday_breakdown': weekday_breakdown
    }
    
    # Get all pets for filter dropdown
    all_pets = Pet.query.join(
        DaycareEnrollment, Pet.id == DaycareEnrollment.pet_id
    ).filter(
        DaycareEnrollment.active == True
    ).order_by(Pet.name).all()
    
    return render_template('reports/daycare_attendance.html',
                         attendance_records=attendance_records,
                         summary=summary,
                         start_date=start_date,
                         end_date=end_date,
                         all_pets=all_pets,
                         selected_pet_id=pet_id,
                         day_filter=day_filter)


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


@reports_bp.route('/export/vaccination-images/zip')
@login_required
@admin_required
def export_vaccination_images():
    """Export all vaccination certificate images as a ZIP file"""
    # Get filter parameters (same as vaccination status report)
    status_filter = request.args.get('status', 'all')
    days_threshold = int(request.args.get('days', 30))
    
    # Get all pets with vaccinations
    query = db.session.query(
        Pet,
        User,
        VaccinationRecord
    ).join(
        User, Pet.user_id == User.id
    ).join(
        VaccinationRecord, Pet.id == VaccinationRecord.pet_id
    ).order_by(User.last_name, User.first_name, Pet.name)
    
    results = query.all()
    
    # Filter records based on status
    filtered_records = []
    for pet, user, vax_record in results:
        # Apply status filter
        if status_filter == 'expired' and not vax_record.is_expired:
            continue
        elif status_filter == 'expiring' and (vax_record.is_expired or vax_record.days_until_expiration > days_threshold):
            continue
        elif status_filter == 'current' and (vax_record.is_expired or vax_record.days_until_expiration <= days_threshold):
            continue
        
        # Only include records that have document_path
        if vax_record.document_path and os.path.exists(vax_record.document_path):
            filtered_records.append((pet, user, vax_record))
    
    if not filtered_records:
        flash('No vaccination images found matching the selected filters.', 'warning')
        return redirect(url_for('reports.vaccination_status_report'))
    
    # Create ZIP file in memory
    zip_buffer = io.BytesIO()
    
    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
        processed_count = 0
        error_count = 0
        
        for pet, user, vax_record in filtered_records:
            try:
                # Clean names for filename (remove special characters)
                pet_name = ''.join(c for c in pet.name if c.isalnum() or c in (' ', '-', '_')).strip().replace(' ', '_')
                owner_last = ''.join(c for c in user.last_name if c.isalnum() or c in (' ', '-', '_')).strip().replace(' ', '_')
                vaccine_name = ''.join(c for c in vax_record.vaccine_name if c.isalnum() or c in (' ', '-', '_')).strip().replace(' ', '_')
                
                # Create filename
                filename = f"{pet_name}_{owner_last}_{vaccine_name}.jpeg"
                
                # Handle duplicate filenames by appending number
                base_filename = filename
                counter = 1
                while filename in [name for name in zip_file.namelist()]:
                    filename = f"{pet_name}_{owner_last}_{vaccine_name}_{counter}.jpeg"
                    counter += 1
                
                # Read and convert image to JPEG
                img_buffer = io.BytesIO()
                
                try:
                    # Open image with PIL
                    img = Image.open(vax_record.document_path)
                    
                    # Convert to RGB if necessary (for PNG with transparency, etc.)
                    if img.mode in ('RGBA', 'LA', 'P'):
                        # Create white background
                        background = Image.new('RGB', img.size, (255, 255, 255))
                        if img.mode == 'P':
                            img = img.convert('RGBA')
                        background.paste(img, mask=img.split()[-1] if img.mode in ('RGBA', 'LA') else None)
                        img = background
                    elif img.mode != 'RGB':
                        img = img.convert('RGB')
                    
                    # Save as JPEG
                    img.save(img_buffer, format='JPEG', quality=95)
                    img_buffer.seek(0)
                    
                    # Add to ZIP
                    zip_file.writestr(filename, img_buffer.getvalue())
                    processed_count += 1
                    
                except Exception as img_error:
                    # If image conversion fails, try to copy original file
                    try:
                        with open(vax_record.document_path, 'rb') as f:
                            file_data = f.read()
                        zip_file.writestr(filename, file_data)
                        processed_count += 1
                    except:
                        error_count += 1
                        continue
                        
            except Exception as e:
                error_count += 1
                continue
    
    # Prepare ZIP for download
    zip_buffer.seek(0)
    
    # Flash message about results
    if error_count > 0:
        flash(f'Exported {processed_count} vaccination images. {error_count} images could not be processed.', 'warning')
    
    return send_file(
        zip_buffer,
        mimetype='application/zip',
        as_attachment=True,
        download_name=f'vaccination_images_{date.today()}.zip'
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


@reports_bp.route('/export/occupancy/csv')
@login_required
@admin_required
def export_occupancy_csv():
    """Export occupancy report to CSV"""
    start_date_str = request.args.get('start_date')
    end_date_str = request.args.get('end_date')
    start_date, end_date = parse_date_range(start_date_str, end_date_str)
    
    # Get daily attendance counts (same logic as occupancy_report)
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
        
        # Revenue
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
    
    # Create CSV
    output = io.StringIO()
    writer = csv.writer(output)
    
    # Write header
    writer.writerow([
        'Date', 'Day of Week', 'Daycare Attendance', 'Appointments', 
        'Total Occupancy', 'Daily Revenue'
    ])
    
    # Write data
    weekday_names = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
    for day_data in daily_data:
        writer.writerow([
            day_data['date'],
            weekday_names[day_data['date'].weekday()],
            day_data['daycare_count'],
            day_data['appointments_count'],
            day_data['total_count'],
            f"${day_data['revenue']:.2f}"
        ])
    
    # Prepare response
    output.seek(0)
    return send_file(
        io.BytesIO(output.getvalue().encode('utf-8')),
        mimetype='text/csv',
        as_attachment=True,
        download_name=f'occupancy_report_{start_date}_to_{end_date}.csv'
    )


@reports_bp.route('/export/revenue/csv')
@login_required
@admin_required
def export_revenue_csv():
    """Export revenue report to CSV"""
    start_date_str = request.args.get('start_date')
    end_date_str = request.args.get('end_date')
    start_date, end_date = parse_date_range(start_date_str, end_date_str)
    
    # Revenue by service type (same logic as revenue_report)
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
    
    # Create CSV
    output = io.StringIO()
    writer = csv.writer(output)
    
    # Write header
    writer.writerow([
        'Service Type', 'Number of Bookings', 'Total Revenue', 'Average Per Booking'
    ])
    
    # Write data
    for service in revenue_by_service:
        avg_revenue = float(service.total_revenue) / service.booking_count if service.booking_count > 0 else 0
        writer.writerow([
            service.name,
            service.booking_count,
            f"${float(service.total_revenue or 0):.2f}",
            f"${avg_revenue:.2f}"
        ])
    
    # Write summary row
    total_revenue = sum(float(r.total_revenue or 0) for r in revenue_by_service)
    total_bookings = sum(r.booking_count for r in revenue_by_service)
    writer.writerow([])
    writer.writerow([
        'TOTAL',
        total_bookings,
        f"${total_revenue:.2f}",
        f"${total_revenue / total_bookings if total_bookings > 0 else 0:.2f}"
    ])
    
    # Prepare response
    output.seek(0)
    return send_file(
        io.BytesIO(output.getvalue().encode('utf-8')),
        mimetype='text/csv',
        as_attachment=True,
        download_name=f'revenue_report_{start_date}_to_{end_date}.csv'
    )


@reports_bp.route('/export/daycare-attendance/csv')
@login_required
@admin_required
def export_daycare_attendance_csv():
    """Export daycare attendance report to CSV"""
    start_date_str = request.args.get('start_date')
    end_date_str = request.args.get('end_date')
    start_date, end_date = parse_date_range(start_date_str, end_date_str)
    
    pet_id = request.args.get('pet_id', type=int)
    day_filter = request.args.get('day', 'all')
    
    # Build query for attendance records (same logic as daycare_attendance_report)
    query = db.session.query(DaycareAttendance).join(
        DaycareEnrollment, DaycareAttendance.enrollment_id == DaycareEnrollment.id
    ).join(
        Pet, DaycareEnrollment.pet_id == Pet.id
    ).join(
        User, Pet.user_id == User.id
    ).filter(
        func.date(DaycareAttendance.check_in_time) >= start_date,
        func.date(DaycareAttendance.check_in_time) <= end_date
    )
    
    if pet_id:
        query = query.filter(Pet.id == pet_id)
    
    attendance_records = query.order_by(DaycareAttendance.check_in_time.desc()).all()
    
    # Apply day filter
    if day_filter != 'all':
        day_map = {
            'monday': 0, 'tuesday': 1, 'wednesday': 2,
            'thursday': 3, 'friday': 4, 'saturday': 5, 'sunday': 6
        }
        target_weekday = day_map.get(day_filter)
        if target_weekday is not None:
            attendance_records = [
                record for record in attendance_records
                if record.check_in_time.weekday() == target_weekday
            ]
    
    # Enrich records
    for record in attendance_records:
        record.enrollment = DaycareEnrollment.query.get(record.enrollment_id)
        record.pet = Pet.query.get(record.enrollment.pet_id) if record.enrollment else None
        record.owner = User.query.get(record.pet.user_id) if record.pet else None
        
        if record.check_out_time:
            duration = record.check_out_time - record.check_in_time
            record.duration_hours = duration.total_seconds() / 3600
        else:
            record.duration_hours = None
    
    # Create CSV
    output = io.StringIO()
    writer = csv.writer(output)
    
    # Write header
    writer.writerow([
        'Date', 'Day of Week', 'Pet Name', 'Owner Last Name', 'Owner First Name',
        'Check-In Time', 'Check-Out Time', 'Duration (Hours)', 'Status',
        'Notes'
    ])
    
    # Write data
    weekday_names = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
    for record in attendance_records:
        check_in_date = record.check_in_time.date()
        check_in_time_str = record.check_in_time.strftime('%I:%M %p')
        check_out_time_str = record.check_out_time.strftime('%I:%M %p') if record.check_out_time else 'Still Checked In'
        duration_str = f"{record.duration_hours:.2f}" if record.duration_hours else 'N/A'
        status = 'Checked Out' if record.check_out_time else 'Checked In'
        
        writer.writerow([
            check_in_date,
            weekday_names[check_in_date.weekday()],
            record.pet.name if record.pet else 'Unknown',
            record.owner.last_name if record.owner else 'Unknown',
            record.owner.first_name if record.owner else 'Unknown',
            check_in_time_str,
            check_out_time_str,
            duration_str,
            status,
            record.notes or ''
        ])
    
    # Prepare response
    output.seek(0)
    return send_file(
        io.BytesIO(output.getvalue().encode('utf-8')),
        mimetype='text/csv',
        as_attachment=True,
        download_name=f'daycare_attendance_{start_date}_to_{end_date}.csv'
    )


# ============================================================================
# MAIN REPORTS DASHBOARD
# ============================================================================


@reports_bp.route('/')
@login_required
@admin_required
def reports_dashboard():
    """Main reports dashboard with analytics overview."""
    from .models import Boarding, Payment
    from collections import defaultdict

    today = date.today()

    TOTAL_KENNELS  = 20
    DAYCARE_MULTI  = 20.0
    DAYCARE_SINGLE = 25.0

    def _boarding_days(b):
        base = (b.check_out_date - b.check_in_date).days
        cout = str(b.check_out_time or '17:00')[:5]
        return base if cout <= '10:00' else base + 1

    # ── 1. Monthly Revenue (last 12 months) ─────────────────────────────
    revenue_months   = []
    revenue_boarding = []
    revenue_daycare  = []
    revenue_addons   = []

    for i in range(11, -1, -1):
        ref = date(today.year, today.month, 1)
        for _ in range(i):
            ref = (ref - timedelta(days=1)).replace(day=1)
        revenue_months.append(ref.strftime('%b %Y'))

        mo_payments = Payment.query.filter(
            Payment.status == 'paid',
            extract('month', Payment.payment_date) == ref.month,
            extract('year',  Payment.payment_date) == ref.year
        ).all()

        b_rev  = sum(p.amount for p in mo_payments if p.service_type and 'board'   in p.service_type.lower())
        dc_rev = sum(p.amount for p in mo_payments if p.service_type and 'daycare' in p.service_type.lower())
        other  = sum(p.amount for p in mo_payments
                     if p.service_type
                     and 'board'   not in p.service_type.lower()
                     and 'daycare' not in p.service_type.lower())

        revenue_boarding.append(round(b_rev, 2))
        revenue_daycare.append(round(dc_rev, 2))
        revenue_addons.append(round(other, 2))

    # ── 2. Outstanding Balances (top 10) ────────────────────────────────
    outstanding_raw = (db.session.query(
        Payment.customer_id,
        func.sum(Payment.amount).label('total')
    ).filter_by(status='outstanding')
     .group_by(Payment.customer_id)
     .order_by(func.sum(Payment.amount).desc())
     .limit(10).all())

    outstanding_labels  = [
        f'{User.query.get(r.customer_id).first_name} {User.query.get(r.customer_id).last_name}'
        for r in outstanding_raw if User.query.get(r.customer_id)
    ]
    outstanding_amounts = [float(r.total) for r in outstanding_raw if User.query.get(r.customer_id)]

    # ── 3. Add-on Attach Rate ────────────────────────────────────────────
    _bsvc = ServiceType.query.filter(ServiceType.name.ilike('%boarding%')).first()
    total_boarding_appts = 0
    addons_count = spa_bath_count = nails_count = both_count = 0

    if _bsvc:
        appts = Appointment.query.filter_by(service_type_id=_bsvc.id).all()
        total_boarding_appts = len(appts)
        for a in appts:
            if not a.notes or 'Add-ons:' not in a.notes:
                continue
            addons_count += 1
            n = a.notes.lower()
            has_bath  = 'spa bath' in n
            has_nails = 'nail' in n
            if has_bath and has_nails:  both_count += 1
            elif has_bath:              spa_bath_count += 1
            elif has_nails:             nails_count += 1

    attach_rate = round((addons_count / total_boarding_appts * 100) if total_boarding_appts else 0, 1)

    # ── 4. Revenue per Customer (top 10) ────────────────────────────────
    top_raw = (db.session.query(
        Payment.customer_id,
        func.sum(Payment.amount).label('total')
    ).filter_by(status='paid')
     .group_by(Payment.customer_id)
     .order_by(func.sum(Payment.amount).desc())
     .limit(10).all())

    top_customer_labels  = [
        f'{User.query.get(r.customer_id).first_name} {User.query.get(r.customer_id).last_name}'
        for r in top_raw if User.query.get(r.customer_id)
    ]
    top_customer_amounts = [float(r.total) for r in top_raw if User.query.get(r.customer_id)]

    # ── 5. Occupancy (last 60 days) ──────────────────────────────────────
    occ_labels, occ_values = [], []
    for i in range(59, -1, -1):
        d = today - timedelta(days=i)
        count = Boarding.query.filter(
            Boarding.check_in_date  <= d,
            Boarding.check_out_date >= d,
            Boarding.status.in_(['active', 'completed'])
        ).count()
        occ_labels.append(d.strftime('%b %d'))
        occ_values.append(min(round(count / TOTAL_KENNELS * 100, 1), 100))

    # ── 6. Average Length of Stay ────────────────────────────────────────
    stay_buckets = {'1 day': 0, '2–3 days': 0, '4–6 days': 0, '7–13 days': 0, '14+ days': 0}
    stays = []
    for b in Boarding.query.filter_by(status='completed').all():
        days = _boarding_days(b)
        stays.append(days)
        if   days <= 1:  stay_buckets['1 day']    += 1
        elif days <= 3:  stay_buckets['2–3 days']  += 1
        elif days <= 6:  stay_buckets['4–6 days']  += 1
        elif days <= 13: stay_buckets['7–13 days'] += 1
        else:            stay_buckets['14+ days']  += 1

    avg_stay = round(sum(stays) / len(stays), 1) if stays else 0

    # ── 7. Daycare Heatmap ───────────────────────────────────────────────
    day_counts = defaultdict(int)
    day_weeks  = defaultdict(set)
    for att in DaycareAttendance.query.filter(DaycareAttendance.check_out_time != None).all():
        wd = att.check_in_time.strftime('%A')
        wk = att.check_in_time.strftime('%Y-W%U')
        day_counts[wd] += 1
        day_weeks[wd].add(wk)

    days_order     = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday']
    heatmap_values = [round(day_counts[d] / (len(day_weeks[d]) or 1), 1) for d in days_order]

    # ── 8. Customer Growth ───────────────────────────────────────────────
    growth_values = []
    for label in revenue_months:
        ref = datetime.strptime(label, '%b %Y')
        growth_values.append(User.query.filter(
            User.role == 'customer',
            extract('month', User.created_at) == ref.month,
            extract('year',  User.created_at) == ref.year
        ).count())

    # ── 9. Retention ─────────────────────────────────────────────────────
    active_count = at_risk_count = churned_count = 0
    for c in User.query.filter_by(role='customer', is_active=True).all():
        last_b = Boarding.query.join(Pet).filter(Pet.user_id == c.id).order_by(Boarding.check_in_date.desc()).first()
        enr_ids = [e.id for p in c.pets for e in p.daycare_enrollments]
        last_d  = None
        if enr_ids:
            att = DaycareAttendance.query.filter(
                DaycareAttendance.enrollment_id.in_(enr_ids)
            ).order_by(DaycareAttendance.check_in_time.desc()).first()
            if att:
                last_d = att.check_in_time.date()

        last_act = None
        if last_b:  last_act = last_b.check_in_date
        if last_d:  last_act = max(last_act, last_d) if last_act else last_d

        if   last_act is None:                       churned_count += 1
        elif last_act >= today - timedelta(days=90): active_count  += 1
        elif last_act >= today - timedelta(days=180):at_risk_count += 1
        else:                                        churned_count += 1

    # ── KPIs ─────────────────────────────────────────────────────────────
    total_revenue     = sum(p.amount for p in Payment.query.filter_by(status='paid').all())
    total_outstanding = sum(p.amount for p in Payment.query.filter_by(status='outstanding').all())
    total_boardings   = Boarding.query.filter_by(status='completed').count()
    total_customers   = User.query.filter_by(role='customer', is_active=True).count()
    total_pets        = Pet.query.filter_by(is_active=True).count()

    return render_template('reports/dashboard.html',
        today=today,
        revenue_months=json.dumps(revenue_months),
        revenue_boarding=json.dumps(revenue_boarding),
        revenue_daycare=json.dumps(revenue_daycare),
        revenue_addons=json.dumps(revenue_addons),
        outstanding_labels=json.dumps(outstanding_labels),
        outstanding_amounts=json.dumps(outstanding_amounts),
        attach_rate=attach_rate,
        total_boarding_appts=total_boarding_appts,
        addons_count=addons_count,
        spa_bath_count=spa_bath_count,
        nails_count=nails_count,
        both_count=both_count,
        top_customer_labels=json.dumps(top_customer_labels),
        top_customer_amounts=json.dumps(top_customer_amounts),
        occ_labels=json.dumps(occ_labels),
        occ_values=json.dumps(occ_values),
        stay_buckets=json.dumps(list(stay_buckets.keys())),
        stay_values=json.dumps(list(stay_buckets.values())),
        heatmap_labels=json.dumps(days_order),
        heatmap_values=json.dumps(heatmap_values),
        growth_months=json.dumps(revenue_months),
        growth_values=json.dumps(growth_values),
        active_count=active_count,
        at_risk_count=at_risk_count,
        churned_count=churned_count,
        total_revenue=total_revenue,
        total_outstanding=total_outstanding,
        total_boardings=total_boardings,
        total_customers=total_customers,
        total_pets=total_pets,
        avg_stay=avg_stay,
        TOTAL_KENNELS=TOTAL_KENNELS,
    )