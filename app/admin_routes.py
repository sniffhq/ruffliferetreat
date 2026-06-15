# Fixed admin_routes.py without circular import
# Replace C:\RuffLifeRetreat\app\admin_routes.py with this content

from flask import render_template, redirect, url_for, flash, request, current_app
from flask_login import login_required, current_user
from datetime import datetime
from functools import wraps

def admin_required(f):
    """Decorator to require admin access"""
    @wraps(f)
    @login_required
    def decorated_function(*args, **kwargs):
        if not current_user.is_admin:
            flash('You must be an administrator to access this page.', 'danger')
            return redirect('/')
        return f(*args, **kwargs)
    return decorated_function


def register_admin_routes(app):
    """Register admin routes with the Flask app"""
    from app import db
    from app.models import ServiceType, ServiceBlock
    
    @app.route('/admin/blocks')
    @admin_required
    def admin_blocks():
        """View all service blocks"""
        blocks = ServiceBlock.query.order_by(ServiceBlock.created_at.desc()).all()
        service_types = ServiceType.query.all()
        
        # Separate by type
        date_blocks = [b for b in blocks if b.start_date and b.end_date]
        day_blocks = [b for b in blocks if b.day_of_week is not None]
        
        return render_template('admin/blocks.html',
                             date_blocks=date_blocks,
                             day_blocks=day_blocks,
                             service_types=service_types)


    @app.route('/admin/blocks/add-date', methods=['POST'])
    @admin_required
    def add_date_block():
        """Add a date range block"""
        try:
            service_type_id = request.form.get('service_type_id')
            start_date = datetime.strptime(request.form.get('start_date'), '%Y-%m-%d').date()
            end_date = datetime.strptime(request.form.get('end_date'), '%Y-%m-%d').date()
            reason = request.form.get('reason')
            
            if end_date < start_date:
                flash('End date must be after start date.', 'danger')
                return redirect(url_for('admin_blocks'))
            
            block = ServiceBlock(
                service_type_id=service_type_id,
                start_date=start_date,
                end_date=end_date,
                reason=reason,
                created_by=current_user.id
            )
            
            db.session.add(block)
            db.session.commit()
            
            service = ServiceType.query.get(service_type_id)
            flash(f'Date range block added successfully for {service.name}.', 'success')
        except Exception as e:
            flash(f'Error adding block: {str(e)}', 'danger')
        
        return redirect(url_for('admin_blocks'))


    @app.route('/admin/blocks/add-day', methods=['POST'])
    @admin_required
    def add_day_block():
        """Add a recurring day-of-week block"""
        try:
            service_type_id = request.form.get('service_type_id')
            day_of_week = int(request.form.get('day_of_week'))
            reason = request.form.get('reason')
            
            block = ServiceBlock(
                service_type_id=service_type_id,
                day_of_week=day_of_week,
                reason=reason,
                created_by=current_user.id
            )
            
            db.session.add(block)
            db.session.commit()
            
            service = ServiceType.query.get(service_type_id)
            flash(f'Recurring day block added successfully for {service.name}.', 'success')
        except Exception as e:
            flash(f'Error adding block: {str(e)}', 'danger')
        
        return redirect(url_for('admin_blocks'))


    @app.route('/admin/blocks/delete/<int:block_id>', methods=['POST'])
    @admin_required
    def delete_block(block_id):
        """Delete a service block"""
        try:
            block = ServiceBlock.query.get_or_404(block_id)
            db.session.delete(block)
            db.session.commit()
            flash('Service block deleted successfully.', 'success')
        except Exception as e:
            flash(f'Error deleting block: {str(e)}', 'danger')
        
        return redirect(url_for('admin_blocks'))


def is_service_available(service_type_id, appointment_date):
    """Check if a service is available on a given date"""
    from app.models import ServiceBlock
    blocks = ServiceBlock.query.filter_by(service_type_id=service_type_id).all()
    
    for block in blocks:
        if block.is_date_blocked(appointment_date):
            return False, block.reason
    
    return True, None