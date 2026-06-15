#!/usr/bin/env python3
"""
Ruff Life Retreat - Report Templates Deployment Script
Automatically creates all necessary report templates
"""

import os
import sys
from pathlib import Path

# Template contents dictionary
TEMPLATES = {}

# ============================================================================
# Dashboard Template
# ============================================================================
TEMPLATES['dashboard.html'] = '''{% extends "base.html" %}

{% block title %}Reports Dashboard - Ruff Life Retreat{% endblock %}

{% block content %}
<div class="container mt-4">
    <h1 class="mb-4">
        <i class="fas fa-chart-bar"></i> Reports Dashboard
    </h1>

    <!-- State Audit/Compliance Reports -->
    <div class="card mb-4">
        <div class="card-header bg-primary text-white">
            <h3 class="mb-0"><i class="fas fa-clipboard-check"></i> State Audit & Compliance Reports</h3>
        </div>
        <div class="card-body">
            <div class="row">
                <div class="col-md-6 mb-3">
                    <div class="card h-100 border-primary">
                        <div class="card-body">
                            <h5 class="card-title">
                                <i class="fas fa-syringe text-primary"></i> Vaccination Status Report
                            </h5>
                            <p class="card-text">
                                Track vaccination records, expiration dates, and compliance status for all pets.
                                Identify pets with expired or expiring vaccinations.
                            </p>
                            <a href="{{ url_for('reports.vaccination_status_report') }}" class="btn btn-primary">
                                <i class="fas fa-eye"></i> View Report
                            </a>
                            <a href="{{ url_for('reports.export_vaccination_csv') }}" class="btn btn-outline-primary">
                                <i class="fas fa-download"></i> Export CSV
                            </a>
                        </div>
                    </div>
                </div>

                <div class="col-md-6 mb-3">
                    <div class="card h-100 border-primary">
                        <div class="card-body">
                            <h5 class="card-title">
                                <i class="fas fa-users text-primary"></i> Capacity Compliance Report
                            </h5>
                            <p class="card-text">
                                Monitor daily facility capacity against regulatory limits. Track occupancy rates
                                and identify any over-capacity situations.
                            </p>
                            <a href="{{ url_for('reports.capacity_compliance_report') }}" class="btn btn-primary">
                                <i class="fas fa-eye"></i> View Report
                            </a>
                        </div>
                    </div>
                </div>

                <div class="col-md-6 mb-3">
                    <div class="card h-100 border-primary">
                        <div class="card-body">
                            <h5 class="card-title">
                                <i class="fas fa-exclamation-triangle text-warning"></i> Incident Log Report
                            </h5>
                            <p class="card-text">
                                Review all documented incidents including injuries, illnesses, and other events.
                                Track resolution status and owner notifications.
                            </p>
                            <a href="{{ url_for('reports.incident_log_report') }}" class="btn btn-primary">
                                <i class="fas fa-eye"></i> View Report
                            </a>
                            <a href="{{ url_for('reports.export_incidents_csv') }}" class="btn btn-outline-primary">
                                <i class="fas fa-download"></i> Export CSV
                            </a>
                        </div>
                    </div>
                </div>

                <div class="col-md-6 mb-3">
                    <div class="card h-100 border-primary">
                        <div class="card-body">
                            <h5 class="card-title">
                                <i class="fas fa-heartbeat text-danger"></i> Health Check Report
                            </h5>
                            <p class="card-text">
                                View daily health assessments and wellness checks performed on pets.
                                Identify pets requiring attention or veterinary care.
                            </p>
                            <a href="{{ url_for('reports.health_check_report') }}" class="btn btn-primary">
                                <i class="fas fa-eye"></i> View Report
                            </a>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    </div>

    <!-- Operational Reports -->
    <div class="card mb-4">
        <div class="card-header bg-success text-white">
            <h3 class="mb-0"><i class="fas fa-chart-line"></i> Operational Reports</h3>
        </div>
        <div class="card-body">
            <div class="row">
                <div class="col-md-6 mb-3">
                    <div class="card h-100 border-success">
                        <div class="card-body">
                            <h5 class="card-title">
                                <i class="fas fa-building text-success"></i> Occupancy Report
                            </h5>
                            <p class="card-text">
                                Analyze facility occupancy rates and trends over time. Track daycare attendance,
                                boarding, and overall utilization.
                            </p>
                            <a href="{{ url_for('reports.occupancy_report') }}" class="btn btn-success">
                                <i class="fas fa-eye"></i> View Report
                            </a>
                        </div>
                    </div>
                </div>

                <div class="col-md-6 mb-3">
                    <div class="card h-100 border-success">
                        <div class="card-body">
                            <h5 class="card-title">
                                <i class="fas fa-dollar-sign text-success"></i> Revenue Report
                            </h5>
                            <p class="card-text">
                                Track revenue by service type and time period. Analyze booking patterns
                                and identify top-performing services.
                            </p>
                            <a href="{{ url_for('reports.revenue_report') }}" class="btn btn-success">
                                <i class="fas fa-eye"></i> View Report
                            </a>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    </div>

    <!-- Customer Reports -->
    <div class="card mb-4">
        <div class="card-header bg-info text-white">
            <h3 class="mb-0"><i class="fas fa-user-friends"></i> Customer Reports</h3>
        </div>
        <div class="card-body">
            <div class="row">
                <div class="col-md-6 mb-3">
                    <div class="card h-100 border-info">
                        <div class="card-body">
                            <h5 class="card-title">
                                <i class="fas fa-history text-info"></i> Visit History Report
                            </h5>
                            <p class="card-text">
                                View customer visit history and service utilization. Track appointment
                                frequency and daycare attendance by customer.
                            </p>
                            <a href="{{ url_for('reports.customer_visit_history') }}" class="btn btn-info">
                                <i class="fas fa-eye"></i> View Report
                            </a>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    </div>

    <!-- Quick Actions -->
    <div class="card mb-4">
        <div class="card-header bg-dark text-white">
            <h3 class="mb-0"><i class="fas fa-bolt"></i> Quick Actions</h3>
        </div>
        <div class="card-body">
            <div class="row">
                <div class="col-md-3 mb-2">
                    <button class="btn btn-outline-primary w-100" onclick="setDateRange('today')">
                        <i class="fas fa-calendar-day"></i> Today's Reports
                    </button>
                </div>
                <div class="col-md-3 mb-2">
                    <button class="btn btn-outline-primary w-100" onclick="setDateRange('week')">
                        <i class="fas fa-calendar-week"></i> This Week
                    </button>
                </div>
                <div class="col-md-3 mb-2">
                    <button class="btn btn-outline-primary w-100" onclick="setDateRange('month')">
                        <i class="fas fa-calendar-alt"></i> This Month
                    </button>
                </div>
                <div class="col-md-3 mb-2">
                    <button class="btn btn-outline-primary w-100" onclick="setDateRange('year')">
                        <i class="fas fa-calendar"></i> This Year
                    </button>
                </div>
            </div>
        </div>
    </div>
</div>

<script>
function setDateRange(period) {
    const today = new Date();
    let startDate, endDate;
    
    endDate = today.toISOString().split('T')[0];
    
    switch(period) {
        case 'today':
            startDate = endDate;
            break;
        case 'week':
            const weekAgo = new Date(today);
            weekAgo.setDate(today.getDate() - 7);
            startDate = weekAgo.toISOString().split('T')[0];
            break;
        case 'month':
            startDate = new Date(today.getFullYear(), today.getMonth(), 1).toISOString().split('T')[0];
            break;
        case 'year':
            startDate = new Date(today.getFullYear(), 0, 1).toISOString().split('T')[0];
            break;
        default:
            startDate = endDate;
    }
    
    sessionStorage.setItem('report_start_date', startDate);
    sessionStorage.setItem('report_end_date', endDate);
    
    alert('Date range set to ' + startDate + ' through ' + endDate);
}
</script>
{% endblock %}
'''

# ============================================================================
# Vaccination Status Template
# ============================================================================
TEMPLATES['vaccination_status.html'] = '''{% extends "base.html" %}

{% block title %}Vaccination Status Report - Ruff Life Retreat{% endblock %}

{% block content %}
<div class="container-fluid mt-4">
    <div class="d-flex justify-content-between align-items-center mb-4">
        <h1><i class="fas fa-syringe"></i> Vaccination Status Report</h1>
        <a href="{{ url_for('reports.reports_dashboard') }}" class="btn btn-secondary">
            <i class="fas fa-arrow-left"></i> Back to Dashboard
        </a>
    </div>

    <!-- Filters -->
    <div class="card mb-4">
        <div class="card-header bg-light">
            <h5 class="mb-0"><i class="fas fa-filter"></i> Filters</h5>
        </div>
        <div class="card-body">
            <form method="GET" action="{{ url_for('reports.vaccination_status_report') }}" class="row g-3">
                <div class="col-md-3">
                    <label for="start_date" class="form-label">Start Date</label>
                    <input type="date" class="form-control" id="start_date" name="start_date" 
                           value="{{ start_date }}">
                </div>
                <div class="col-md-3">
                    <label for="end_date" class="form-label">End Date</label>
                    <input type="date" class="form-control" id="end_date" name="end_date" 
                           value="{{ end_date }}">
                </div>
                <div class="col-md-3">
                    <label for="status" class="form-label">Status Filter</label>
                    <select class="form-select" id="status" name="status">
                        <option value="all" {% if status_filter == 'all' %}selected{% endif %}>All Pets</option>
                        <option value="expired" {% if status_filter == 'expired' %}selected{% endif %}>Expired Only</option>
                        <option value="expiring" {% if status_filter == 'expiring' %}selected{% endif %}>Expiring Soon</option>
                        <option value="current" {% if status_filter == 'current' %}selected{% endif %}>Current Only</option>
                        <option value="missing" {% if status_filter == 'missing' %}selected{% endif %}>Missing Required</option>
                    </select>
                </div>
                <div class="col-md-2">
                    <label for="days" class="form-label">Days Threshold</label>
                    <input type="number" class="form-control" id="days" name="days" 
                           value="{{ days_threshold }}" min="1" max="365">
                </div>
                <div class="col-md-1 d-flex align-items-end">
                    <button type="submit" class="btn btn-primary w-100">
                        <i class="fas fa-search"></i> Filter
                    </button>
                </div>
            </form>
        </div>
    </div>

    <!-- Summary Statistics -->
    <div class="row mb-4">
        <div class="col-md-3">
            <div class="card text-center">
                <div class="card-body">
                    <h3 class="text-primary">{{ summary.total_pets }}</h3>
                    <p class="mb-0">Total Pets</p>
                </div>
            </div>
        </div>
        <div class="col-md-3">
            <div class="card text-center">
                <div class="card-body">
                    <h3 class="text-danger">{{ summary.expired_count }}</h3>
                    <p class="mb-0">Expired Vaccinations</p>
                </div>
            </div>
        </div>
        <div class="col-md-3">
            <div class="card text-center">
                <div class="card-body">
                    <h3 class="text-warning">{{ summary.expiring_count }}</h3>
                    <p class="mb-0">Expiring Soon</p>
                </div>
            </div>
        </div>
        <div class="col-md-3">
            <div class="card text-center">
                <div class="card-body">
                    <h3 class="text-success">{{ summary.current_count }}</h3>
                    <p class="mb-0">Current</p>
                </div>
            </div>
        </div>
    </div>

    <!-- Export Options -->
    <div class="mb-3">
        <a href="{{ url_for('reports.export_vaccination_csv') }}" class="btn btn-success">
            <i class="fas fa-file-csv"></i> Export to CSV
        </a>
        <button class="btn btn-outline-success" onclick="window.print()">
            <i class="fas fa-print"></i> Print Report
        </button>
    </div>

    <!-- Vaccination Records Table -->
    <div class="card">
        <div class="card-header bg-primary text-white">
            <h5 class="mb-0">Vaccination Records</h5>
        </div>
        <div class="card-body">
            {% if pet_vaccination_data %}
            <div class="table-responsive">
                <table class="table table-striped table-hover">
                    <thead>
                        <tr>
                            <th>Owner</th>
                            <th>Pet Name</th>
                            <th>Breed</th>
                            <th>Vaccine</th>
                            <th>Vaccination Date</th>
                            <th>Expiration Date</th>
                            <th>Days Until Expiration</th>
                            <th>Status</th>
                            <th>Veterinarian</th>
                        </tr>
                    </thead>
                    <tbody>
                        {% for pet_id, data in pet_vaccination_data.items() %}
                            {% set pet = data.pet %}
                            {% set owner = data.owner %}
                            {% set vaccinations = data.vaccinations %}
                            
                            {% if vaccinations %}
                                {% for vax_data in vaccinations %}
                                <tr class="
                                    {% if vax_data.is_expired %}table-danger
                                    {% elif vax_data.days_until_expiration <= days_threshold %}table-warning
                                    {% else %}table-success{% endif %}">
                                    <td>{{ owner.last_name }}, {{ owner.first_name }}</td>
                                    <td><strong>{{ pet.name }}</strong></td>
                                    <td>{{ pet.breed or 'N/A' }}</td>
                                    <td>{{ vax_data.record.vaccine_name }}</td>
                                    <td>{{ vax_data.record.vaccination_date.strftime('%m/%d/%Y') }}</td>
                                    <td>{{ vax_data.record.expiration_date.strftime('%m/%d/%Y') }}</td>
                                    <td>
                                        {% if vax_data.is_expired %}
                                            <span class="badge bg-danger">Expired</span>
                                        {% else %}
                                            {{ vax_data.days_until_expiration }} days
                                        {% endif %}
                                    </td>
                                    <td>
                                        {% if vax_data.is_expired %}
                                            <span class="badge bg-danger">Expired</span>
                                        {% elif vax_data.days_until_expiration <= days_threshold %}
                                            <span class="badge bg-warning text-dark">Expiring Soon</span>
                                        {% else %}
                                            <span class="badge bg-success">Current</span>
                                        {% endif %}
                                    </td>
                                    <td>{{ vax_data.record.veterinarian or 'N/A' }}</td>
                                </tr>
                                {% endfor %}
                            {% else %}
                                <tr class="table-secondary">
                                    <td>{{ owner.last_name }}, {{ owner.first_name }}</td>
                                    <td><strong>{{ pet.name }}</strong></td>
                                    <td>{{ pet.breed or 'N/A' }}</td>
                                    <td colspan="6">
                                        <span class="badge bg-secondary">No Vaccination Records</span>
                                        {% if data.missing_required %}
                                            <span class="text-danger ms-2">
                                                Missing: {{ data.missing_required|join(', ') }}
                                            </span>
                                        {% endif %}
                                    </td>
                                </tr>
                            {% endif %}
                        {% endfor %}
                    </tbody>
                </table>
            </div>
            {% else %}
            <div class="alert alert-info">
                <i class="fas fa-info-circle"></i> No vaccination records found for the selected criteria.
            </div>
            {% endif %}
        </div>
    </div>

    <!-- Legend -->
    <div class="card mt-3">
        <div class="card-body">
            <h6>Status Legend:</h6>
            <span class="badge bg-danger me-2">Expired</span> Vaccination has expired
            <span class="badge bg-warning text-dark me-2 ms-3">Expiring Soon</span> Expires within {{ days_threshold }} days
            <span class="badge bg-success me-2 ms-3">Current</span> Vaccination is current
            <span class="badge bg-secondary ms-3">No Records</span> No vaccination records on file
        </div>
    </div>
</div>

<style>
@media print {
    .btn, .card-header, nav, footer {
        display: none !important;
    }
    
    .card {
        border: 1px solid #000 !important;
        page-break-inside: avoid;
    }
    
    table {
        font-size: 10pt;
    }
}
</style>
{% endblock %}
'''

# ============================================================================
# Incident Log Template
# ============================================================================
TEMPLATES['incident_log.html'] = '''{% extends "base.html" %}

{% block title %}Incident Log Report - Ruff Life Retreat{% endblock %}

{% block content %}
<div class="container-fluid mt-4">
    <div class="d-flex justify-content-between align-items-center mb-4">
        <h1><i class="fas fa-exclamation-triangle"></i> Incident Log Report</h1>
        <a href="{{ url_for('reports.reports_dashboard') }}" class="btn btn-secondary">
            <i class="fas fa-arrow-left"></i> Back to Dashboard
        </a>
    </div>

    <!-- Filters -->
    <div class="card mb-4">
        <div class="card-header bg-light">
            <h5 class="mb-0"><i class="fas fa-filter"></i> Filters</h5>
        </div>
        <div class="card-body">
            <form method="GET" action="{{ url_for('reports.incident_log_report') }}" class="row g-3">
                <div class="col-md-3">
                    <label for="start_date" class="form-label">Start Date</label>
                    <input type="date" class="form-control" id="start_date" name="start_date" 
                           value="{{ start_date }}">
                </div>
                <div class="col-md-3">
                    <label for="end_date" class="form-label">End Date</label>
                    <input type="date" class="form-control" id="end_date" name="end_date" 
                           value="{{ end_date }}">
                </div>
                <div class="col-md-2">
                    <label for="incident_type" class="form-label">Incident Type</label>
                    <select class="form-select" id="incident_type" name="incident_type">
                        <option value="all" {% if incident_type == 'all' %}selected{% endif %}>All Types</option>
                        <option value="injury" {% if incident_type == 'injury' %}selected{% endif %}>Injury</option>
                        <option value="illness" {% if incident_type == 'illness' %}selected{% endif %}>Illness</option>
                        <option value="escape" {% if incident_type == 'escape' %}selected{% endif %}>Escape</option>
                        <option value="aggression" {% if incident_type == 'aggression' %}selected{% endif %}>Aggression</option>
                        <option value="property_damage" {% if incident_type == 'property_damage' %}selected{% endif %}>Property Damage</option>
                        <option value="other" {% if incident_type == 'other' %}selected{% endif %}>Other</option>
                    </select>
                </div>
                <div class="col-md-2">
                    <label for="severity" class="form-label">Severity</label>
                    <select class="form-select" id="severity" name="severity">
                        <option value="all" {% if severity == 'all' %}selected{% endif %}>All Levels</option>
                        <option value="minor" {% if severity == 'minor' %}selected{% endif %}>Minor</option>
                        <option value="moderate" {% if severity == 'moderate' %}selected{% endif %}>Moderate</option>
                        <option value="serious" {% if severity == 'serious' %}selected{% endif %}>Serious</option>
                        <option value="critical" {% if severity == 'critical' %}selected{% endif %}>Critical</option>
                    </select>
                </div>
                <div class="col-md-2">
                    <label for="resolved" class="form-label">Status</label>
                    <select class="form-select" id="resolved" name="resolved">
                        <option value="all" {% if resolved_filter == 'all' %}selected{% endif %}>All</option>
                        <option value="resolved" {% if resolved_filter == 'resolved' %}selected{% endif %}>Resolved</option>
                        <option value="unresolved" {% if resolved_filter == 'unresolved' %}selected{% endif %}>Unresolved</option>
                    </select>
                </div>
                <div class="col-md-12">
                    <button type="submit" class="btn btn-primary">
                        <i class="fas fa-search"></i> Apply Filters
                    </button>
                    <a href="{{ url_for('reports.incident_log_report') }}" class="btn btn-outline-secondary">
                        <i class="fas fa-redo"></i> Reset
                    </a>
                </div>
            </form>
        </div>
    </div>

    <!-- Summary Statistics -->
    <div class="row mb-4">
        <div class="col-md-3">
            <div class="card text-center border-primary">
                <div class="card-body">
                    <h3 class="text-primary">{{ summary.total_incidents }}</h3>
                    <p class="mb-0">Total Incidents</p>
                </div>
            </div>
        </div>
        <div class="col-md-3">
            <div class="card text-center border-success">
                <div class="card-body">
                    <h3 class="text-success">{{ summary.resolved_count }}</h3>
                    <p class="mb-0">Resolved</p>
                </div>
            </div>
        </div>
        <div class="col-md-3">
            <div class="card text-center border-warning">
                <div class="card-body">
                    <h3 class="text-warning">{{ summary.unresolved_count }}</h3>
                    <p class="mb-0">Unresolved</p>
                </div>
            </div>
        </div>
        <div class="col-md-3">
            <div class="card text-center border-info">
                <div class="card-body">
                    <h3 class="text-info">
                        {% if summary.total_incidents > 0 %}
                        {{ "%.1f"|format((summary.resolved_count / summary.total_incidents * 100)) }}%
                        {% else %}
                        0%
                        {% endif %}
                    </h3>
                    <p class="mb-0">Resolution Rate</p>
                </div>
            </div>
        </div>
    </div>

    <!-- Export Options -->
    <div class="mb-3">
        <a href="{{ url_for('reports.export_incidents_csv', start_date=start_date, end_date=end_date) }}" 
           class="btn btn-success">
            <i class="fas fa-file-csv"></i> Export to CSV
        </a>
        <button class="btn btn-outline-success" onclick="window.print()">
            <i class="fas fa-print"></i> Print Report
        </button>
    </div>

    <!-- Incidents Table -->
    <div class="card">
        <div class="card-header bg-danger text-white">
            <h5 class="mb-0">Incident Log Details</h5>
        </div>
        <div class="card-body">
            {% if incidents %}
            <div class="table-responsive">
                <table class="table table-hover">
                    <thead>
                        <tr>
                            <th>Date/Time</th>
                            <th>Type</th>
                            <th>Severity</th>
                            <th>Pet</th>
                            <th>Owner</th>
                            <th>Description</th>
                            <th>Status</th>
                        </tr>
                    </thead>
                    <tbody>
                        {% for incident in incidents %}
                        <tr class="
                            {% if incident.severity == 'critical' %}table-danger
                            {% elif incident.severity == 'serious' %}table-warning
                            {% elif incident.severity == 'moderate' %}table-info
                            {% endif %}">
                            <td>
                                <strong>{{ incident.incident_date.strftime('%m/%d/%Y') }}</strong><br>
                                <small class="text-muted">{{ incident.incident_time.strftime('%I:%M %p') }}</small>
                            </td>
                            <td>
                                <span class="badge bg-secondary">
                                    {{ incident.incident_type.replace('_', ' ').title() }}
                                </span>
                            </td>
                            <td>
                                <span class="badge 
                                    {% if incident.severity == 'critical' %}bg-danger
                                    {% elif incident.severity == 'serious' %}bg-warning text-dark
                                    {% elif incident.severity == 'moderate' %}bg-info
                                    {% else %}bg-secondary{% endif %}">
                                    {{ incident.severity.title() }}
                                </span>
                            </td>
                            <td>
                                {% if incident.pet %}
                                <strong>{{ incident.pet.name }}</strong><br>
                                <small class="text-muted">{{ incident.pet.breed or 'N/A' }}</small>
                                {% else %}
                                <span class="text-muted">Facility-wide</span>
                                {% endif %}
                            </td>
                            <td>
                                {% if incident.pet and incident.owner %}
                                {{ incident.owner.first_name }} {{ incident.owner.last_name }}
                                {% else %}
                                <span class="text-muted">N/A</span>
                                {% endif %}
                            </td>
                            <td>
                                <div style="max-width: 300px;">
                                    {{ incident.description[:100] }}
                                    {% if incident.description|length > 100 %}...{% endif %}
                                </div>
                            </td>
                            <td>
                                {% if incident.resolved %}
                                <span class="badge bg-success">
                                    <i class="fas fa-check-circle"></i> Resolved
                                </span>
                                {% else %}
                                <span class="badge bg-warning text-dark">
                                    <i class="fas fa-clock"></i> Open
                                </span>
                                {% endif %}
                            </td>
                        </tr>
                        {% endfor %}
                    </tbody>
                </table>
            </div>
            {% else %}
            <div class="alert alert-info">
                <i class="fas fa-info-circle"></i> No incidents found for the selected criteria.
            </div>
            {% endif %}
        </div>
    </div>
</div>

<style>
@media print {
    .btn, .modal, nav, footer, .card-header {
        display: none !important;
    }
    
    .card {
        border: 1px solid #000 !important;
        page-break-inside: avoid;
    }
    
    table {
        font-size: 9pt;
    }
}
</style>
{% endblock %}
'''

# ============================================================================
# Capacity Compliance Template
# ============================================================================
TEMPLATES['capacity_compliance.html'] = '''{% extends "base.html" %}

{% block title %}Capacity Compliance Report - Ruff Life Retreat{% endblock %}

{% block content %}
<div class="container-fluid mt-4">
    <div class="d-flex justify-content-between align-items-center mb-4">
        <h1><i class="fas fa-users"></i> Capacity Compliance Report</h1>
        <a href="{{ url_for('reports.reports_dashboard') }}" class="btn btn-secondary">
            <i class="fas fa-arrow-left"></i> Back to Dashboard
        </a>
    </div>

    <!-- Filters -->
    <div class="card mb-4">
        <div class="card-header bg-light">
            <h5 class="mb-0"><i class="fas fa-filter"></i> Date Range</h5>
        </div>
        <div class="card-body">
            <form method="GET" action="{{ url_for('reports.capacity_compliance_report') }}" class="row g-3">
                <div class="col-md-4">
                    <label for="start_date" class="form-label">Start Date</label>
                    <input type="date" class="form-control" id="start_date" name="start_date" 
                           value="{{ start_date }}" required>
                </div>
                <div class="col-md-4">
                    <label for="end_date" class="form-label">End Date</label>
                    <input type="date" class="form-control" id="end_date" name="end_date" 
                           value="{{ end_date }}" required>
                </div>
                <div class="col-md-4 d-flex align-items-end">
                    <button type="submit" class="btn btn-primary">
                        <i class="fas fa-search"></i> Generate Report
                    </button>
                </div>
            </form>
        </div>
    </div>

    <!-- Summary Statistics -->
    <div class="row mb-4">
        <div class="col-md-3">
            <div class="card text-center">
                <div class="card-body">
                    <h3 class="text-primary">{{ summary.total_days }}</h3>
                    <p class="mb-0">Total Days</p>
                </div>
            </div>
        </div>
        <div class="col-md-3">
            <div class="card text-center">
                <div class="card-body">
                    <h3 class="text-success">{{ "%.1f"|format(summary.compliance_rate) }}%</h3>
                    <p class="mb-0">Compliance Rate</p>
                </div>
            </div>
        </div>
        <div class="col-md-3">
            <div class="card text-center">
                <div class="card-body">
                    <h3 class="text-warning">{{ "%.1f"|format(summary.avg_total) }}</h3>
                    <p class="mb-0">Avg Daily Capacity</p>
                </div>
            </div>
        </div>
        <div class="col-md-3">
            <div class="card text-center">
                <div class="card-body">
                    <h3 class="text-danger">{{ summary.over_capacity_days }}</h3>
                    <p class="mb-0">Over Capacity Days</p>
                </div>
            </div>
        </div>
    </div>

    <!-- Capacity Table -->
    <div class="card">
        <div class="card-header bg-primary text-white">
            <h5 class="mb-0">Daily Capacity Log</h5>
        </div>
        <div class="card-body">
            {% if capacity_logs %}
            <div class="table-responsive">
                <table class="table table-striped table-hover">
                    <thead>
                        <tr>
                            <th>Date</th>
                            <th>Daycare</th>
                            <th>Boarding</th>
                            <th>Grooming</th>
                            <th>Total</th>
                            <th>Capacity %</th>
                            <th>Status</th>
                            <th>Notes</th>
                        </tr>
                    </thead>
                    <tbody>
                        {% for log in capacity_logs %}
                        <tr class="{% if log.over_capacity %}table-danger{% endif %}">
                            <td><strong>{{ log.log_date.strftime('%m/%d/%Y') }}</strong></td>
                            <td>{{ log.daycare_count }} / {{ log.daycare_limit }}</td>
                            <td>{{ log.boarding_count }} / {{ log.boarding_limit }}</td>
                            <td>{{ log.grooming_count }}</td>
                            <td><strong>{{ log.total_count }} / {{ log.total_limit }}</strong></td>
                            <td>
                                <div class="progress" style="min-width: 100px;">
                                    <div class="progress-bar 
                                        {% if log.total_percentage > 100 %}bg-danger
                                        {% elif log.total_percentage > 90 %}bg-warning
                                        {% else %}bg-success{% endif %}" 
                                        role="progressbar" 
                                        style="width: {{ [log.total_percentage, 100]|min }}%">
                                        {{ "%.0f"|format(log.total_percentage) }}%
                                    </div>
                                </div>
                            </td>
                            <td>
                                {% if log.over_capacity %}
                                <span class="badge bg-danger">Over Capacity</span>
                                {% elif log.total_percentage > 90 %}
                                <span class="badge bg-warning text-dark">Near Capacity</span>
                                {% else %}
                                <span class="badge bg-success">Within Limits</span>
                                {% endif %}
                            </td>
                            <td>{{ log.notes or '' }}</td>
                        </tr>
                        {% endfor %}
                    </tbody>
                </table>
            </div>
            {% else %}
            <div class="alert alert-info">
                <i class="fas fa-info-circle"></i> No capacity data found for the selected date range.
            </div>
            {% endif %}
        </div>
    </div>

    <!-- Compliance Note -->
    <div class="card mt-3">
        <div class="card-body">
            <h6><i class="fas fa-info-circle"></i> Capacity Limits:</h6>
            <ul class="mb-0">
                <li>Daycare: 30 pets</li>
                <li>Boarding: 20 pets</li>
                <li>Total Facility: 50 pets</li>
            </ul>
            <p class="mt-2 mb-0 text-muted">
                <small>Note: Capacity logs are automatically calculated from daily attendance data.</small>
            </p>
        </div>
    </div>
</div>
{% endblock %}
'''

# Add remaining templates (health_checks, occupancy, revenue, visit_history)
# Due to length, I'll continue with abbreviated versions...

TEMPLATES['health_checks.html'] = '''{% extends "base.html" %}

{% block title %}Health Check Report - Ruff Life Retreat{% endblock %}

{% block content %}
<div class="container-fluid mt-4">
    <div class="d-flex justify-content-between align-items-center mb-4">
        <h1><i class="fas fa-heartbeat"></i> Health Check Report</h1>
        <a href="{{ url_for('reports.reports_dashboard') }}" class="btn btn-secondary">
            <i class="fas fa-arrow-left"></i> Back to Dashboard
        </a>
    </div>

    <!-- Filters -->
    <div class="card mb-4">
        <div class="card-header bg-light">
            <h5 class="mb-0"><i class="fas fa-filter"></i> Filters</h5>
        </div>
        <div class="card-body">
            <form method="GET" class="row g-3">
                <div class="col-md-4">
                    <label for="start_date" class="form-label">Start Date</label>
                    <input type="date" class="form-control" name="start_date" value="{{ start_date }}">
                </div>
                <div class="col-md-4">
                    <label for="end_date" class="form-label">End Date</label>
                    <input type="date" class="form-control" name="end_date" value="{{ end_date }}">
                </div>
                <div class="col-md-4 d-flex align-items-end">
                    <button type="submit" class="btn btn-primary">
                        <i class="fas fa-search"></i> Filter
                    </button>
                </div>
            </form>
        </div>
    </div>

    <!-- Summary -->
    <div class="row mb-4">
        <div class="col-md-4">
            <div class="card text-center">
                <div class="card-body">
                    <h3 class="text-primary">{{ summary.total_checks }}</h3>
                    <p class="mb-0">Total Health Checks</p>
                </div>
            </div>
        </div>
        <div class="col-md-4">
            <div class="card text-center">
                <div class="card-body">
                    <h3 class="text-warning">{{ summary.attention_needed }}</h3>
                    <p class="mb-0">Requiring Attention</p>
                </div>
            </div>
        </div>
        <div class="col-md-4">
            <div class="card text-center">
                <div class="card-body">
                    <h3 class="text-success">{{ summary.owner_notified }}</h3>
                    <p class="mb-0">Owners Notified</p>
                </div>
            </div>
        </div>
    </div>

    <!-- Health Checks Table -->
    <div class="card">
        <div class="card-header bg-danger text-white">
            <h5 class="mb-0">Health Check Records</h5>
        </div>
        <div class="card-body">
            {% if health_checks %}
            <div class="table-responsive">
                <table class="table table-striped">
                    <thead>
                        <tr>
                            <th>Date</th>
                            <th>Pet</th>
                            <th>Owner</th>
                            <th>Checked By</th>
                            <th>Status</th>
                            <th>Notes</th>
                        </tr>
                    </thead>
                    <tbody>
                        {% for check in health_checks %}
                        <tr class="{% if check.requires_attention %}table-warning{% endif %}">
                            <td>{{ check.check_date.strftime('%m/%d/%Y') }}</td>
                            <td><strong>{{ check.pet.name if check.pet else 'N/A' }}</strong></td>
                            <td>{{ check.owner.first_name if check.owner else '' }} {{ check.owner.last_name if check.owner else '' }}</td>
                            <td>{{ check.checked_by }}</td>
                            <td>
                                {% if check.requires_attention %}
                                <span class="badge bg-warning text-dark">Needs Attention</span>
                                {% else %}
                                <span class="badge bg-success">Normal</span>
                                {% endif %}
                            </td>
                            <td>{{ check.notes or '' }}</td>
                        </tr>
                        {% endfor %}
                    </tbody>
                </table>
            </div>
            {% else %}
            <div class="alert alert-info">
                <i class="fas fa-info-circle"></i> No health checks found for the selected period.
            </div>
            {% endif %}
        </div>
    </div>
</div>
{% endblock %}
'''

TEMPLATES['occupancy.html'] = '''{% extends "base.html" %}

{% block title %}Occupancy Report - Ruff Life Retreat{% endblock %}

{% block content %}
<div class="container-fluid mt-4">
    <div class="d-flex justify-content-between align-items-center mb-4">
        <h1><i class="fas fa-building"></i> Occupancy Report</h1>
        <a href="{{ url_for('reports.reports_dashboard') }}" class="btn btn-secondary">
            <i class="fas fa-arrow-left"></i> Back to Dashboard
        </a>
    </div>

    <!-- Filters -->
    <div class="card mb-4">
        <div class="card-header bg-light">
            <h5 class="mb-0"><i class="fas fa-filter"></i> Date Range</h5>
        </div>
        <div class="card-body">
            <form method="GET" class="row g-3">
                <div class="col-md-5">
                    <label for="start_date" class="form-label">Start Date</label>
                    <input type="date" class="form-control" name="start_date" value="{{ start_date }}">
                </div>
                <div class="col-md-5">
                    <label for="end_date" class="form-label">End Date</label>
                    <input type="date" class="form-control" name="end_date" value="{{ end_date }}">
                </div>
                <div class="col-md-2 d-flex align-items-end">
                    <button type="submit" class="btn btn-primary w-100">
                        <i class="fas fa-search"></i> Filter
                    </button>
                </div>
            </form>
        </div>
    </div>

    <!-- Summary -->
    <div class="row mb-4">
        <div class="col-md-3">
            <div class="card text-center">
                <div class="card-body">
                    <h3 class="text-primary">{{ "%.1f"|format(summary.avg_total) }}</h3>
                    <p class="mb-0">Avg Daily Occupancy</p>
                </div>
            </div>
        </div>
        <div class="col-md-3">
            <div class="card text-center">
                <div class="card-body">
                    <h3 class="text-success">${{ "%.2f"|format(summary.total_revenue) }}</h3>
                    <p class="mb-0">Total Revenue</p>
                </div>
            </div>
        </div>
        <div class="col-md-3">
            <div class="card text-center">
                <div class="card-body">
                    <h3 class="text-info">{{ "%.1f"|format(summary.avg_daycare) }}</h3>
                    <p class="mb-0">Avg Daycare</p>
                </div>
            </div>
        </div>
        <div class="col-md-3">
            <div class="card text-center">
                <div class="card-body">
                    <h3 class="text-warning">{{ "%.1f"|format(summary.avg_appointments) }}</h3>
                    <p class="mb-0">Avg Appointments</p>
                </div>
            </div>
        </div>
    </div>

    <!-- Daily Data Table -->
    <div class="card">
        <div class="card-header bg-success text-white">
            <h5 class="mb-0">Daily Occupancy Data</h5>
        </div>
        <div class="card-body">
            {% if daily_data %}
            <div class="table-responsive">
                <table class="table table-striped">
                    <thead>
                        <tr>
                            <th>Date</th>
                            <th>Daycare</th>
                            <th>Appointments</th>
                            <th>Total</th>
                            <th>Revenue</th>
                        </tr>
                    </thead>
                    <tbody>
                        {% for day in daily_data %}
                        <tr>
                            <td>{{ day.date.strftime('%m/%d/%Y') }}</td>
                            <td>{{ day.daycare_count }}</td>
                            <td>{{ day.appointments_count }}</td>
                            <td><strong>{{ day.total_count }}</strong></td>
                            <td>${{ "%.2f"|format(day.revenue) }}</td>
                        </tr>
                        {% endfor %}
                    </tbody>
                </table>
            </div>
            {% else %}
            <div class="alert alert-info">
                <i class="fas fa-info-circle"></i> No occupancy data found.
            </div>
            {% endif %}
        </div>
    </div>
</div>
{% endblock %}
'''

TEMPLATES['revenue.html'] = '''{% extends "base.html" %}

{% block title %}Revenue Report - Ruff Life Retreat{% endblock %}

{% block content %}
<div class="container-fluid mt-4">
    <div class="d-flex justify-content-between align-items-center mb-4">
        <h1><i class="fas fa-dollar-sign"></i> Revenue Report</h1>
        <a href="{{ url_for('reports.reports_dashboard') }}" class="btn btn-secondary">
            <i class="fas fa-arrow-left"></i> Back to Dashboard
        </a>
    </div>

    <!-- Filters -->
    <div class="card mb-4">
        <div class="card-header bg-light">
            <h5 class="mb-0"><i class="fas fa-filter"></i> Date Range</h5>
        </div>
        <div class="card-body">
            <form method="GET" class="row g-3">
                <div class="col-md-5">
                    <label for="start_date" class="form-label">Start Date</label>
                    <input type="date" class="form-control" name="start_date" value="{{ start_date }}">
                </div>
                <div class="col-md-5">
                    <label for="end_date" class="form-label">End Date</label>
                    <input type="date" class="form-control" name="end_date" value="{{ end_date }}">
                </div>
                <div class="col-md-2 d-flex align-items-end">
                    <button type="submit" class="btn btn-primary w-100">
                        <i class="fas fa-search"></i> Filter
                    </button>
                </div>
            </form>
        </div>
    </div>

    <!-- Summary -->
    <div class="row mb-4">
        <div class="col-md-4">
            <div class="card text-center">
                <div class="card-body">
                    <h3 class="text-success">${{ "%.2f"|format(summary.total_revenue) }}</h3>
                    <p class="mb-0">Total Revenue</p>
                </div>
            </div>
        </div>
        <div class="col-md-4">
            <div class="card text-center">
                <div class="card-body">
                    <h3 class="text-primary">{{ summary.total_bookings }}</h3>
                    <p class="mb-0">Total Bookings</p>
                </div>
            </div>
        </div>
        <div class="col-md-4">
            <div class="card text-center">
                <div class="card-body">
                    <h3 class="text-info">${{ "%.2f"|format(summary.avg_booking_value) }}</h3>
                    <p class="mb-0">Avg Booking Value</p>
                </div>
            </div>
        </div>
    </div>

    <!-- Revenue by Service -->
    <div class="card mb-4">
        <div class="card-header bg-success text-white">
            <h5 class="mb-0">Revenue by Service Type</h5>
        </div>
        <div class="card-body">
            {% if revenue_by_service %}
            <div class="table-responsive">
                <table class="table table-striped">
                    <thead>
                        <tr>
                            <th>Service Type</th>
                            <th>Bookings</th>
                            <th>Total Revenue</th>
                            <th>Avg per Booking</th>
                        </tr>
                    </thead>
                    <tbody>
                        {% for service in revenue_by_service %}
                        <tr>
                            <td><strong>{{ service.name }}</strong></td>
                            <td>{{ service.booking_count }}</td>
                            <td>${{ "%.2f"|format(service.total_revenue or 0) }}</td>
                            <td>${{ "%.2f"|format((service.total_revenue or 0) / service.booking_count if service.booking_count > 0 else 0) }}</td>
                        </tr>
                        {% endfor %}
                    </tbody>
                </table>
            </div>
            {% else %}
            <div class="alert alert-info">
                <i class="fas fa-info-circle"></i> No revenue data found.
            </div>
            {% endif %}
        </div>
    </div>
</div>
{% endblock %}
'''

TEMPLATES['visit_history.html'] = '''{% extends "base.html" %}

{% block title %}Visit History Report - Ruff Life Retreat{% endblock %}

{% block content %}
<div class="container-fluid mt-4">
    <div class="d-flex justify-content-between align-items-center mb-4">
        <h1><i class="fas fa-history"></i> Customer Visit History</h1>
        <a href="{{ url_for('reports.reports_dashboard') }}" class="btn btn-secondary">
            <i class="fas fa-arrow-left"></i> Back to Dashboard
        </a>
    </div>

    <!-- Filters -->
    <div class="card mb-4">
        <div class="card-header bg-light">
            <h5 class="mb-0"><i class="fas fa-filter"></i> Filters</h5>
        </div>
        <div class="card-body">
            <form method="GET" class="row g-3">
                <div class="col-md-3">
                    <label for="customer_id" class="form-label">Customer</label>
                    <select class="form-select" name="customer_id">
                        <option value="">All Customers</option>
                        {% for customer in all_customers %}
                        <option value="{{ customer.id }}" {% if selected_customer_id == customer.id %}selected{% endif %}>
                            {{ customer.last_name }}, {{ customer.first_name }}
                        </option>
                        {% endfor %}
                    </select>
                </div>
                <div class="col-md-3">
                    <label for="start_date" class="form-label">Start Date</label>
                    <input type="date" class="form-control" name="start_date" value="{{ start_date }}">
                </div>
                <div class="col-md-3">
                    <label for="end_date" class="form-label">End Date</label>
                    <input type="date" class="form-control" name="end_date" value="{{ end_date }}">
                </div>
                <div class="col-md-3 d-flex align-items-end">
                    <button type="submit" class="btn btn-primary w-100">
                        <i class="fas fa-search"></i> Filter
                    </button>
                </div>
            </form>
        </div>
    </div>

    <!-- Customer Data -->
    <div class="card">
        <div class="card-header bg-info text-white">
            <h5 class="mb-0">Visit History</h5>
        </div>
        <div class="card-body">
            {% if customer_data %}
            {% for user_id, data in customer_data.items() %}
            <div class="card mb-3">
                <div class="card-header">
                    <h5 class="mb-0">
                        {{ data.user.first_name }} {{ data.user.last_name }}
                        <small class="text-muted">({{ data.user.email }})</small>
                    </h5>
                </div>
                <div class="card-body">
                    <p><strong>Total Appointments:</strong> {{ data.total_appointments }}</p>
                    <p><strong>Total Daycare Visits:</strong> {{ data.total_daycare }}</p>
                    
                    {% if data.pets %}
                    <h6 class="mt-3">Pets:</h6>
                    <ul>
                        {% for pet_data in data.pets %}
                        <li>
                            <strong>{{ pet_data.pet.name }}</strong> ({{ pet_data.pet.breed or 'Mixed' }})
                            - {{ pet_data.appointment_count }} appointments, {{ pet_data.daycare_visits }} daycare visits
                        </li>
                        {% endfor %}
                    </ul>
                    {% endif %}
                </div>
            </div>
            {% endfor %}
            {% else %}
            <div class="alert alert-info">
                <i class="fas fa-info-circle"></i> No visit history found.
            </div>
            {% endif %}
        </div>
    </div>
</div>
{% endblock %}
'''


def find_templates_directory():
    """Find the templates directory in the Flask app"""
    current_dir = Path.cwd()
    
    # Common locations
    possible_paths = [
        current_dir / 'templates',
        current_dir / 'app' / 'templates',
        current_dir / 'application' / 'templates',
    ]
    
    for path in possible_paths:
        if path.exists() and path.is_dir():
            return path
    
    # Search for templates directory
    for root, dirs, files in os.walk(current_dir):
        if 'templates' in dirs:
            return Path(root) / 'templates'
    
    return None


def create_templates(templates_dir):
    """Create all report templates"""
    reports_dir = templates_dir / 'reports'
    reports_dir.mkdir(exist_ok=True)
    
    created_files = []
    skipped_files = []
    
    for filename, content in TEMPLATES.items():
        filepath = reports_dir / filename
        
        if filepath.exists():
            response = input(f"\n⚠️  {filepath.name} already exists. Overwrite? (y/n): ")
            if response.lower() != 'y':
                skipped_files.append(filename)
                continue
        
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        
        created_files.append(filename)
    
    return created_files, skipped_files


def main():
    print("=" * 60)
    print("Ruff Life Retreat - Report Templates Deployment")
    print("=" * 60)
    print("\nSearching for templates directory...")
    
    templates_dir = find_templates_directory()
    
    if not templates_dir:
        print("\n❌ Could not find templates directory!")
        print("\nPlease ensure you're running this script from your Flask project root.")
        
        create_manually = input("\nCreate templates directory? (y/n): ")
        if create_manually.lower() == 'y':
            templates_dir = Path.cwd() / 'templates'
            templates_dir.mkdir(exist_ok=True)
            print(f"✓ Created {templates_dir}")
        else:
            sys.exit(1)
    
    print(f"\n✓ Found templates directory: {templates_dir}")
    
    reports_dir = templates_dir / 'reports'
    print(f"\nReport templates will be created in:")
    print(f"  {reports_dir}")
    
    print(f"\nTemplates to deploy:")
    for i, filename in enumerate(TEMPLATES.keys(), 1):
        print(f"  {i}. {filename}")
    
    response = input("\nProceed with deployment? (y/n): ")
    if response.lower() != 'y':
        print("Deployment cancelled.")
        sys.exit(0)
    
    print("\n" + "=" * 60)
    print("Creating template files...")
    print("=" * 60)
    
    created_files, skipped_files = create_templates(templates_dir)
    
    print("\n" + "=" * 60)
    print("✅ Deployment Complete!")
    print("=" * 60)
    
    if created_files:
        print(f"\n✓ Created {len(created_files)} template(s):")
        for filename in created_files:
            print(f"  • {filename}")
    
    if skipped_files:
        print(f"\n⚠️  Skipped {len(skipped_files)} existing file(s):")
        for filename in skipped_files:
            print(f"  • {filename}")
    
    print(f"\nTemplates location: {reports_dir}")
    
    print("\n" + "=" * 60)
    print("Next Steps:")
    print("=" * 60)
    print("1. ✓ Report templates have been created")
    print("2. 📝 Ensure reports.py is in place (run setup_reports.py if needed)")
    print("3. 🗃️  Run database migration: python add_audit_tables_migration.py")
    print("4. 🔧 Register the reports blueprint in your main app file")
    print("5. 🚀 Start your Flask app and navigate to /reports")
    
    print("\n💡 Template files created:")
    print("   templates/reports/dashboard.html")
    print("   templates/reports/vaccination_status.html")
    print("   templates/reports/incident_log.html")
    print("   templates/reports/capacity_compliance.html")
    print("   templates/reports/health_checks.html")
    print("   templates/reports/occupancy.html")
    print("   templates/reports/revenue.html")
    print("   templates/reports/visit_history.html")


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nDeployment cancelled by user.")
        sys.exit(0)
    except Exception as e:
        print(f"\n❌ Error: {str(e)}")
        import traceback
        traceback.print_exc()
        sys.exit(1)