from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import UserMixin
from app import db

class User(UserMixin, db.Model):
    __tablename__ = 'user'
    
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(255))
    first_name = db.Column(db.String(50))
    last_name = db.Column(db.String(50))
    phone = db.Column(db.String(20))
    address = db.Column(db.String(200))
    city = db.Column(db.String(100))
    state = db.Column(db.String(2))
    zip_code = db.Column(db.String(10))
    emergency_contact_name = db.Column(db.String(100))
    emergency_contact_phone = db.Column(db.String(20))
    how_heard = db.Column(db.String(100))
    preferences = db.Column(db.Text)
    is_admin = db.Column(db.Boolean, default=False)
    role = db.Column(db.String(20), default='customer', nullable=False, server_default='customer')
    is_active = db.Column(db.Boolean, default=True)  # NEW: Soft delete flag
    onboarding_complete = db.Column(db.Boolean, default=False)
    
    # Waiver tracking
    waiver_accepted = db.Column(db.Boolean, default=False, nullable=False)
    waiver_accepted_at = db.Column(db.DateTime, nullable=True)
    
    created_at = db.Column(db.DateTime, default=datetime.now)
    archived_at = db.Column(db.DateTime)  # NEW: Track when archived
    sms_opt_in                  = db.Column(db.Boolean, default=False)
    custom_boarding_rate            = db.Column(db.Numeric(10, 2), nullable=True)
    custom_boarding_rate_additional = db.Column(db.Numeric(10, 2), nullable=True)
    custom_daycare_rate             = db.Column(db.Numeric(10, 2), nullable=True)
    custom_addon_spa_bath_nails     = db.Column(db.Numeric(10, 2), nullable=True)
    custom_addon_spa_bath           = db.Column(db.Numeric(10, 2), nullable=True)
    custom_addon_nail_trim          = db.Column(db.Numeric(10, 2), nullable=True)
    custom_rate_note                = db.Column(db.String(255), nullable=True)
    staff_notes = db.Column(db.Text, nullable=True)  # CRM — internal staff notes

    # Relationships
    pets = db.relationship('Pet', back_populates='owner', lazy=True, cascade='all, delete-orphan')
    appointments = db.relationship('Appointment', back_populates='user', lazy=True, cascade='all, delete-orphan')
    
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
    
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)
    
    def __repr__(self):
        return f'<User {self.email}>'


class ServiceType(db.Model):
    __tablename__ = 'service_type'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=False, unique=True)
    base_price = db.Column(db.Numeric(10, 2), nullable=False)
    duration_minutes = db.Column(db.Integer, nullable=False, default=60)
    
    # Relationships
    appointments = db.relationship('Appointment', back_populates='service_type', lazy=True)
    service_blocks = db.relationship('ServiceBlock', back_populates='service_type', lazy=True, cascade='all, delete-orphan')
    
    def __repr__(self):
        return f'<ServiceType {self.name}>'


class Pet(db.Model):
    __tablename__ = 'pet'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    breed = db.Column(db.String(100))
    age = db.Column(db.Integer)
    weight = db.Column(db.Numeric(5, 2))
    special_instructions = db.Column(db.Text)
    photo_filename = db.Column(db.String(255))
    vaccination_record = db.Column(db.String(255))
    vet_name = db.Column(db.String(100))
    vet_phone = db.Column(db.String(20))
    gender = db.Column(db.String(10))
    spayed_neutered = db.Column(db.Boolean, default=False)
    microchipped = db.Column(db.Boolean, default=False)
    microchip_number = db.Column(db.String(50))
    medical_notes = db.Column(db.Text)
    additional_notes = db.Column(db.Text)
    photo_path = db.Column(db.String(255))
    vaccination_record_path = db.Column(db.String(255))
    is_active = db.Column(db.Boolean, default=True)  # NEW: Soft delete flag
    created_at = db.Column(db.DateTime, default=datetime.now)
    archived_at = db.Column(db.DateTime)  # NEW: Track when archived
    temperament = db.Column(db.String(20), default='calm')  # calm, energetic, mixed
    default_play_group_id = db.Column(db.Integer, db.ForeignKey('play_group.id'), nullable=True)

    # Per-pet custom pricing — overrides customer and facility defaults
    custom_boarding_rate = db.Column(db.Numeric(10, 2), nullable=True)
    custom_daycare_rate  = db.Column(db.Numeric(10, 2), nullable=True)
    custom_rate_note     = db.Column(db.String(255), nullable=True)

    # Tags — comma-separated list of labels
    pet_tags = db.Column(db.Text, nullable=True)

    # Vaccination expiry alert acknowledgement
    vacc_alert_acknowledged = db.Column(db.Boolean, default=False, nullable=False, server_default='0')
    vacc_alert_ack_at       = db.Column(db.DateTime, nullable=True)
    vacc_alert_ack_by       = db.Column(db.String(100), nullable=True)

    @property
    def tags_list(self):
        """Return tags as a sorted list, empty list if none."""
        if not self.pet_tags:
            return []
        return [t.strip() for t in self.pet_tags.split(',') if t.strip()]

    @property
    def has_warning_tags(self):
        """True if any tag is in the warning category."""
        warnings = {'Not Dog Friendly', 'People Shy',
                    'Escape Artist', 'Dominant', 'Requires Separate Kennel',
                    'Needs Medication', 'Diabetic', 'Post-Surgery'}
        return bool(warnings & set(self.tags_list))

    @property
    def vacc_expiring_soon(self):
        """True if any active vaccination expires within 60 days and alert hasn't been acknowledged."""
        if self.vacc_alert_acknowledged:
            return False
        today = datetime.now().date()
        for rec in self.vaccination_records:
            if not rec.is_expired and rec.days_until_expiration <= 60:
                return True
        return False

    @property
    def vacc_expiring_records(self):
        """Return vaccination records expiring within 60 days (not yet expired)."""
        today = datetime.now().date()
        return [r for r in self.vaccination_records
                if not r.is_expired and r.days_until_expiration <= 60]

    # Relationships
    owner = db.relationship('User', back_populates='pets')
    appointments = db.relationship('Appointment', back_populates='pet', lazy=True, cascade='all, delete-orphan')
    vaccination_records = db.relationship('VaccinationRecord', back_populates='pet', lazy=True, cascade='all, delete-orphan')
    health_checks = db.relationship('HealthCheck', back_populates='pet', lazy=True, cascade='all, delete-orphan')
    incident_logs = db.relationship('IncidentLog', back_populates='pet', lazy=True, cascade='all, delete-orphan')
    
    def __repr__(self):
        return f'<Pet {self.name}>'


class Appointment(db.Model):
    __tablename__ = 'appointment'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    pet_id = db.Column(db.Integer, db.ForeignKey('pet.id'), nullable=False)
    service_type_id = db.Column(db.Integer, db.ForeignKey('service_type.id'), nullable=False)
    appointment_date = db.Column(db.Date)
    start_time = db.Column(db.DateTime)
    end_time = db.Column(db.DateTime)
    status = db.Column(db.String(20), default='pending')
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.now)
    archived = db.Column(db.Boolean, default=False)
    needs_reapproval = db.Column(db.Boolean, default=False, nullable=False, server_default='0')
    cancel_acknowledged = db.Column(db.Boolean, default=False, nullable=False, server_default='0')

    # Relationships
    user = db.relationship('User', back_populates='appointments')
    pet = db.relationship('Pet', back_populates='appointments')
    service_type = db.relationship('ServiceType', back_populates='appointments')
    
    def __repr__(self):
        return f'<Appointment {self.id} - {self.status}>'


class ServiceBlock(db.Model):
    __tablename__ = 'service_block'
    
    id = db.Column(db.Integer, primary_key=True)
    service_type_id = db.Column(db.Integer, db.ForeignKey('service_type.id'), nullable=False)
    start_date = db.Column(db.Date, nullable=False)
    end_date = db.Column(db.Date, nullable=False)
    reason = db.Column(db.String(200))
    created_at = db.Column(db.DateTime, default=datetime.now)
    
    # Relationships
    service_type = db.relationship('ServiceType', back_populates='service_blocks')
    
    def __repr__(self):
        return f'<ServiceBlock {self.service_type.name if self.service_type else "Unknown"} {self.start_date} to {self.end_date}>'


class DaycareEnrollment(db.Model):
    __tablename__ = 'daycare_enrollment'
    
    id = db.Column(db.Integer, primary_key=True)
    pet_id = db.Column(db.Integer, db.ForeignKey('pet.id'), nullable=False)
    enrollment_date = db.Column(db.Date, nullable=False)
    active = db.Column(db.Boolean, default=True)
    notes = db.Column(db.Text)
    
    # Schedule fields - which days pet attends daycare
    monday = db.Column(db.Boolean, default=False)
    tuesday  = db.Column(db.Boolean, default=False)
    wednesday = db.Column(db.Boolean, default=False)
    thursday = db.Column(db.Boolean, default=False)
    friday = db.Column(db.Boolean, default=False)

    # Special discounted rate — if set, overrides the standard multi/single day rate
    special_rate = db.Column(db.Float, nullable=True)  # e.g. 20.0 for $20/day flat

    created_at = db.Column(db.DateTime, default=datetime.now)
    
    # Relationships
    pet = db.relationship('Pet', backref=db.backref('daycare_enrollments', lazy=True))
    attendance_records = db.relationship('DaycareAttendance', back_populates='enrollment', lazy=True, cascade='all, delete-orphan')
    
    def __repr__(self):
        return f'<DaycareEnrollment Pet:{self.pet_id} Active:{self.active}>'


class DaycareAttendance(db.Model):
    __tablename__ = 'daycare_attendance'
    
    id            = db.Column(db.Integer, primary_key=True)
    enrollment_id = db.Column(db.Integer, db.ForeignKey('daycare_enrollment.id'), nullable=False)
    check_in_time = db.Column(db.DateTime, nullable=False)
    check_out_time = db.Column(db.DateTime)
    notes         = db.Column(db.Text)
    play_group_id = db.Column(db.Integer, db.ForeignKey('play_group.id'), nullable=True)
    payment_id    = db.Column(db.Integer, db.ForeignKey('payment.id'), nullable=True)
    created_at    = db.Column(db.DateTime, default=datetime.now)
    
    # Relationships
    enrollment = db.relationship('DaycareEnrollment', back_populates='attendance_records')
    
    def __repr__(self):
        return f'<DaycareAttendance Enrollment:{self.enrollment_id} CheckIn:{self.check_in_time}>'


class DaycareWaitlist(db.Model):
    """Waitlist for daycare enrollment"""
    __tablename__ = 'daycare_waitlist'
    
    id = db.Column(db.Integer, primary_key=True)
    first_name = db.Column(db.String(100), nullable=False)
    last_name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), nullable=False)
    phone = db.Column(db.String(20), nullable=False)
    pet_name = db.Column(db.String(100), default='')
    breed = db.Column(db.String(100))
    
    # Days of interest
    monday = db.Column(db.Boolean, default=False)
    tuesday  = db.Column(db.Boolean, default=False)
    wednesday = db.Column(db.Boolean, default=False)
    thursday = db.Column(db.Boolean, default=False)
    friday = db.Column(db.Boolean, default=False)
    
    additional_info = db.Column(db.Text)
    submitted_date = db.Column(db.DateTime, nullable=False, default=datetime.now)
    contacted = db.Column(db.Boolean, default=False)
    
    def __repr__(self):
        return f'<DaycareWaitlist {self.last_name}, {self.first_name}>'


class Boarding(db.Model):
    """Boarding reservations for pets"""
    __tablename__ = 'boarding'
    
    id = db.Column(db.Integer, primary_key=True)
    pet_id = db.Column(db.Integer, db.ForeignKey('pet.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    
    # Check-in (Drop-off)
    check_in_date = db.Column(db.Date, nullable=False)
    check_in_time = db.Column(db.String(5), nullable=False)  # HH:MM format (e.g., "08:00", "14:30")
    
    # Check-out (Pick-up)
    check_out_date = db.Column(db.Date, nullable=False)
    check_out_time = db.Column(db.String(5), nullable=False)  # HH:MM format
    
    # Special care requirements
    medications = db.Column(db.Text)
    feeding_schedule = db.Column(db.Text)
    special_notes = db.Column(db.Text)
    kennel_number = db.Column(db.String(20))   # e.g. "4", "4A", "12"
    kennel_type   = db.Column(db.String(10))   # 'kennel' or 'suite'
    checked_in    = db.Column(db.Boolean, default=False)
    checked_in_at = db.Column(db.DateTime)
    
    # Status
    status = db.Column(db.String(20), default='active')  # active, completed, cancelled
    
    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.now)
    completed_at = db.Column(db.DateTime)
    payment_id   = db.Column(db.Integer, db.ForeignKey('payment.id'), nullable=True)
    
    # Relationships
    pet = db.relationship('Pet', backref=db.backref('boarding_reservations', lazy=True))
    user = db.relationship('User', backref=db.backref('boarding_reservations', lazy=True))
    
    @property
    def duration_days(self):
        """Calculate number of days booked"""
        delta = self.check_out_date - self.check_in_date
        return delta.days
    
    @property
    def is_active(self):
        """Check if booking is currently active"""
        today = datetime.now().date()
        return self.status == 'active' and self.check_in_date <= today <= self.check_out_date
    
    def __repr__(self):
        return f'<Boarding Pet:{self.pet_id} {self.check_in_date} {self.check_in_time} to {self.check_out_date} {self.check_out_time}>'


# ============================================================================
# NEW AUDIT/COMPLIANCE MODELS
# ============================================================================

class VaccinationRecord(db.Model):
    """Track individual vaccination records with expiration dates"""
    __tablename__ = 'vaccination_record'
    
    id = db.Column(db.Integer, primary_key=True)
    pet_id = db.Column(db.Integer, db.ForeignKey('pet.id'), nullable=False)
    vaccine_name = db.Column(db.String(100), nullable=False)  # e.g., Rabies, DHPP, Bordetella
    vaccination_date = db.Column(db.Date, nullable=False)
    expiration_date = db.Column(db.Date, nullable=False)
    veterinarian = db.Column(db.String(100))
    clinic_name = db.Column(db.String(200))
    lot_number = db.Column(db.String(50))
    notes = db.Column(db.Text)
    document_path = db.Column(db.String(255))  # Path to uploaded certificate
    created_at = db.Column(db.DateTime, default=datetime.now)
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)
    
    # Relationships
    pet = db.relationship('Pet', back_populates='vaccination_records')
    
    @property
    def is_expired(self):
        """Check if vaccination is expired"""
        return datetime.now().date() > self.expiration_date
    
    @property
    def days_until_expiration(self):
        """Calculate days until expiration"""
        delta = self.expiration_date - datetime.now().date()
        return delta.days
    
    def __repr__(self):
        return f'<VaccinationRecord {self.vaccine_name} for Pet:{self.pet_id}>'


class HealthCheck(db.Model):
    """Daily health observations and assessments"""
    __tablename__ = 'health_check'
    
    id = db.Column(db.Integer, primary_key=True)
    pet_id = db.Column(db.Integer, db.ForeignKey('pet.id'), nullable=False)
    check_date = db.Column(db.Date, nullable=False)
    check_time = db.Column(db.DateTime, nullable=False, default=datetime.now)
    checked_by = db.Column(db.String(100), nullable=False)  # Staff member name
    
    # Health indicators
    appetite = db.Column(db.String(20))  # good, reduced, none
    energy_level = db.Column(db.String(20))  # normal, low, high
    behavior = db.Column(db.String(20))  # normal, anxious, aggressive, lethargic
    bathroom_normal = db.Column(db.Boolean, default=True)
    
    # Observations
    temperature = db.Column(db.Numeric(4, 1))  # If taken
    symptoms = db.Column(db.Text)  # Any symptoms observed
    treatment_given = db.Column(db.Text)  # Any treatment administered
    notes = db.Column(db.Text)
    
    # Follow-up
    requires_attention = db.Column(db.Boolean, default=False)
    owner_notified = db.Column(db.Boolean, default=False)
    
    created_at = db.Column(db.DateTime, default=datetime.now)
    
    # Relationships
    pet = db.relationship('Pet', back_populates='health_checks')
    
    def __repr__(self):
        return f'<HealthCheck Pet:{self.pet_id} Date:{self.check_date}>'


class IncidentLog(db.Model):
    """Log incidents that occur at the facility"""
    __tablename__ = 'incident_log'
    
    id = db.Column(db.Integer, primary_key=True)
    pet_id = db.Column(db.Integer, db.ForeignKey('pet.id'), nullable=True)  # Nullable for facility-wide incidents
    incident_date = db.Column(db.Date, nullable=False)
    incident_time = db.Column(db.DateTime, nullable=False, default=datetime.now)
    
    # Incident classification
    incident_type = db.Column(db.String(50), nullable=False)  # injury, illness, escape, aggression, property_damage, other
    severity = db.Column(db.String(20), nullable=False)  # minor, moderate, serious, critical
    
    # Details
    description = db.Column(db.Text, nullable=False)
    location = db.Column(db.String(100))  # Where it occurred
    witnesses = db.Column(db.Text)  # Staff/others who witnessed
    
    # Response
    action_taken = db.Column(db.Text, nullable=False)
    reported_by = db.Column(db.String(100), nullable=False)  # Staff member
    owner_notified = db.Column(db.Boolean, default=False)
    owner_notification_time = db.Column(db.DateTime)
    vet_contacted = db.Column(db.Boolean, default=False)
    vet_visit_required = db.Column(db.Boolean, default=False)
    
    # Follow-up
    resolution = db.Column(db.Text)
    resolved = db.Column(db.Boolean, default=False)
    resolved_date = db.Column(db.Date)
    
    # Documentation
    photos_taken = db.Column(db.Boolean, default=False)
    photo_paths = db.Column(db.Text)  # JSON array of paths
    
    created_at = db.Column(db.DateTime, default=datetime.now)
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)
    
    # Relationships
    pet = db.relationship('Pet', back_populates='incident_logs')
    
    def __repr__(self):
        return f'<IncidentLog {self.incident_type} {self.incident_date}>'


class CapacityLog(db.Model):
    """Track daily facility capacity for compliance"""
    __tablename__ = 'capacity_log'
    
    id = db.Column(db.Integer, primary_key=True)
    log_date = db.Column(db.Date, nullable=False, unique=True)
    
    # Capacity counts
    daycare_count = db.Column(db.Integer, default=0)
    boarding_count = db.Column(db.Integer, default=0)
    grooming_count = db.Column(db.Integer, default=0)
    total_count = db.Column(db.Integer, default=0)
    
    # Limits (these might come from a config, but storing for historical record)
    daycare_limit = db.Column(db.Integer, default=30)
    boarding_limit = db.Column(db.Integer, default=20)
    total_limit = db.Column(db.Integer, default=50)
    
    # Compliance
    over_capacity = db.Column(db.Boolean, default=False)
    notes = db.Column(db.Text)
    
    recorded_at = db.Column(db.DateTime, default=datetime.now)
    
    @property
    def daycare_percentage(self):
        """Calculate daycare capacity percentage"""
        if self.daycare_limit > 0:
            return (self.daycare_count / self.daycare_limit) * 100
        return 0
    
    @property
    def total_percentage(self):
        """Calculate total capacity percentage"""
        if self.total_limit > 0:
            return (self.total_count / self.total_limit) * 100
        return 0
    
    def __repr__(self):
        return f'<CapacityLog {self.log_date} Total:{self.total_count}/{self.total_limit}>'


class Payment(db.Model):
    __tablename__ = 'payment'
    id             = db.Column(db.Integer, primary_key=True)
    customer_id    = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    amount         = db.Column(db.Float, nullable=False)
    payment_date   = db.Column(db.Date, nullable=False, default=datetime.now)
    service_type   = db.Column(db.String(50))
    payment_method = db.Column(db.String(30))
    notes          = db.Column(db.Text)
    status         = db.Column(db.String(20), default='paid')  # paid, outstanding
    created_at     = db.Column(db.DateTime, default=datetime.now)

    customer = db.relationship('User', backref=db.backref('payments', lazy=True))




class InvoiceAdjustment(db.Model):
    """
    Per-customer invoice overrides and custom line items.
    Allows staff to edit amounts or add manual charges/discounts
    without altering the underlying boarding/daycare records.
    """
    __tablename__ = 'invoice_adjustment'

    id          = db.Column(db.Integer, primary_key=True)
    customer_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    # 'override' ties to a specific auto-calculated line via a key (e.g. 'boarding_105')
    # 'custom' is a free-form additional line item
    adj_type    = db.Column(db.String(20), nullable=False, default='custom')
    line_key    = db.Column(db.String(100))     # e.g. 'boarding_105' or 'daycare_att_77'
    service_type = db.Column(db.String(20), nullable=True, default='boarding')  # 'boarding' or 'daycare'
    description = db.Column(db.String(200), nullable=False)
    amount      = db.Column(db.Float, nullable=False)  # negative = discount
    created_by  = db.Column(db.Integer, db.ForeignKey('user.id'))
    created_at  = db.Column(db.DateTime, default=datetime.now)

    customer = db.relationship('User', foreign_keys=[customer_id],
                               backref=db.backref('invoice_adjustments', lazy=True))


class InvoiceToken(db.Model):
    """Tokenized public link for customer invoice viewing — no login required."""
    __tablename__ = 'invoice_token'

    id          = db.Column(db.Integer, primary_key=True)
    customer_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    token       = db.Column(db.String(64), unique=True, nullable=False, index=True)
    created_at  = db.Column(db.DateTime, default=datetime.now)
    last_sent   = db.Column(db.DateTime)

    customer = db.relationship('User', backref=db.backref('invoice_tokens', lazy=True))


class SmsMessage(db.Model):
    """Inbound and outbound SMS messages."""
    __tablename__ = 'sms_message'
    id          = db.Column(db.Integer, primary_key=True)
    user_id     = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    direction   = db.Column(db.String(10), nullable=False)
    from_number = db.Column(db.String(20))
    to_number   = db.Column(db.String(20))
    body        = db.Column(db.Text)
    twilio_sid  = db.Column(db.String(40))
    is_read     = db.Column(db.Boolean, default=False)
    created_at  = db.Column(db.DateTime, default=datetime.now)
    user = db.relationship('User', backref=db.backref('sms_messages', lazy=True))


class GalleryPhoto(db.Model):
    __tablename__ = 'gallery_photo'
    id         = db.Column(db.Integer, primary_key=True)
    filename   = db.Column(db.String(255), nullable=False)
    caption    = db.Column(db.String(200))
    category   = db.Column(db.String(50), default='General')
    created_at = db.Column(db.DateTime, default=datetime.now)
    @property
    def url(self):
        return f'/static/uploads/gallery/{self.filename}'


class ReportCard(db.Model):
    __tablename__ = 'report_card'
    id           = db.Column(db.Integer, primary_key=True)
    pet_id       = db.Column(db.Integer, db.ForeignKey('pet.id'), nullable=False)
    card_type    = db.Column(db.String(10), nullable=False)
    card_date    = db.Column(db.Date, nullable=False)
    token        = db.Column(db.String(64), unique=True, nullable=False)
    mood         = db.Column(db.String(20))
    energy       = db.Column(db.String(20))
    played_well  = db.Column(db.String(20))
    hydrated     = db.Column(db.Boolean)
    notes        = db.Column(db.Text)
    photo_filename = db.Column(db.String(255))
    appetite     = db.Column(db.String(20))
    sleep        = db.Column(db.String(20))
    temperament  = db.Column(db.String(20))
    medications_given = db.Column(db.Boolean)
    bathroom     = db.Column(db.String(20))
    sent_at      = db.Column(db.DateTime)
    created_at   = db.Column(db.DateTime, default=datetime.now)
    pet = db.relationship('Pet', backref=db.backref('report_cards', lazy=True, order_by='ReportCard.card_date.desc()'))
    @property
    def photo_url(self):
        return f'/static/uploads/report_cards/{self.photo_filename}' if self.photo_filename else None


class KnowledgeArticle(db.Model):
    __tablename__ = 'knowledge_article'
    id         = db.Column(db.Integer, primary_key=True)
    title      = db.Column(db.String(200), nullable=False)
    category   = db.Column(db.String(50), nullable=False)
    content    = db.Column(db.Text, nullable=False)
    pinned     = db.Column(db.Boolean, default=False)
    created_by = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.now)
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)
    author = db.relationship('User', backref=db.backref('kb_articles', lazy=True))


class PasswordResetToken(db.Model):
    __tablename__ = 'password_reset_token'
    id         = db.Column(db.Integer, primary_key=True)
    user_id    = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    token      = db.Column(db.String(64), unique=True, nullable=False)
    expires_at = db.Column(db.DateTime, nullable=False)
    used       = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.now)
    user = db.relationship('User', backref=db.backref('reset_tokens', lazy=True))
    @property
    def is_valid(self):
        from datetime import datetime as dt
        return not self.used and self.expires_at > dt.now()


class SurveyResponse(db.Model):
    __tablename__ = 'survey_response'
    id             = db.Column(db.Integer, primary_key=True)
    user_id        = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    token          = db.Column(db.String(64), unique=True, nullable=False)
    service_type   = db.Column(db.String(50))
    trigger        = db.Column(db.String(50))
    overall_rating = db.Column(db.Integer)
    comm_rating    = db.Column(db.Integer)
    recommend      = db.Column(db.String(10))
    comments       = db.Column(db.Text)
    submitted_at   = db.Column(db.DateTime)
    sent_at        = db.Column(db.DateTime, default=datetime.now)
    created_at     = db.Column(db.DateTime, default=datetime.now)
    user = db.relationship('User', backref=db.backref('survey_responses', lazy=True))
    @property
    def is_complete(self):
        return self.submitted_at is not None


class PlayGroup(db.Model):
    __tablename__ = 'play_group'
    id            = db.Column(db.Integer, primary_key=True)
    name          = db.Column(db.String(100), nullable=False)
    size_category = db.Column(db.String(20), nullable=False)
    temperament   = db.Column(db.String(20), nullable=False)
    max_capacity  = db.Column(db.Integer, default=10)
    active        = db.Column(db.Boolean, default=True)
    color         = db.Column(db.String(7), default='#0d6efd')
    created_at    = db.Column(db.DateTime, default=datetime.now)
    attendances   = db.relationship('DaycareAttendance', foreign_keys='DaycareAttendance.play_group_id',
                                    backref='play_group', lazy=True)
    @property
    def today_count(self):
        from datetime import datetime as dt
        today = dt.now().date()
        return sum(1 for a in self.attendances
                   if a.check_in_time and a.check_in_time.date() == today and a.check_out_time is None)
    @property
    def capacity_pct(self):
        if not self.max_capacity: return 0
        return round((self.today_count / self.max_capacity) * 100)
    @property
    def capacity_status(self):
        pct = self.capacity_pct
        if pct >= 100: return 'full'
        if pct >= 80:  return 'warning'
        return 'ok'


class StaffNotice(db.Model):
    __tablename__ = 'staff_notice'
    id           = db.Column(db.Integer, primary_key=True)
    title        = db.Column(db.String(200), nullable=False)
    body         = db.Column(db.Text, nullable=False)
    priority     = db.Column(db.String(10), default='normal')
    expires_at   = db.Column(db.DateTime, nullable=False)
    created_by   = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    dismissed_by = db.Column(db.Text)
    created_at   = db.Column(db.DateTime, default=datetime.now)
    author = db.relationship('User', foreign_keys=[created_by],
                             backref=db.backref('notices_created', lazy=True))
    @property
    def is_active(self):
        from datetime import datetime as dt
        return self.expires_at > dt.now()
    def is_dismissed_by(self, user_id):
        if not self.dismissed_by: return False
        return str(user_id) in self.dismissed_by.split(',')
    def dismiss_for(self, user_id):
        ids = self.dismissed_by.split(',') if self.dismissed_by else []
        if str(user_id) not in ids:
            ids.append(str(user_id))
        self.dismissed_by = ','.join(filter(None, ids))


class SupportTicket(db.Model):
    __tablename__ = 'support_ticket'
    id           = db.Column(db.Integer, primary_key=True)
    ticket_type  = db.Column(db.String(50), nullable=False)
    subject      = db.Column(db.String(200), nullable=False)
    description  = db.Column(db.Text, nullable=False)
    status       = db.Column(db.String(20), default='open')
    submitted_by = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    created_at   = db.Column(db.DateTime, default=datetime.now)
    updated_at   = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)
    total_minutes           = db.Column(db.Integer, default=0)
    active_session_started  = db.Column(db.DateTime, nullable=True)
    active_session_user_id  = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    submitter = db.relationship('User', foreign_keys=[submitted_by],
                                backref=db.backref('support_tickets', lazy=True))
    active_worker = db.relationship('User', foreign_keys=[active_session_user_id])
    time_sessions = db.relationship('TicketTimeSession', backref='ticket', lazy=True,
                                    order_by='TicketTimeSession.started_at.asc()')
    @property
    def type_label(self):
        return {'feature_request': 'Feature Request', 'account_issue': 'User Account Issue',
                'standard': 'Standard Request'}.get(self.ticket_type, self.ticket_type.replace('_', ' ').title())
    @property
    def status_color(self):
        return {'open': 'warning', 'in_progress': 'primary',
                'working': 'success', 'resolved': 'secondary'}.get(self.status, 'secondary')
    @property
    def is_active_session(self):
        return self.status == 'working' and self.active_session_started is not None
    @property
    def current_session_minutes(self):
        if not self.is_active_session:
            return 0
        delta = datetime.now() - self.active_session_started
        return int(delta.total_seconds() // 60)
    @property
    def total_minutes_including_active(self):
        return (self.total_minutes or 0) + self.current_session_minutes
    def format_time(self, minutes=None):
        m = minutes if minutes is not None else self.total_minutes_including_active
        if not m:
            return '0m'
        h, rem = divmod(m, 60)
        return f'{h}h {rem}m' if h else f'{rem}m'


class TicketComment(db.Model):
    """Comments/replies on a support ticket."""
    __tablename__ = 'ticket_comment'

    id         = db.Column(db.Integer, primary_key=True)
    ticket_id  = db.Column(db.Integer, db.ForeignKey('support_ticket.id'), nullable=False)
    user_id    = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    body       = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.now)

    ticket  = db.relationship('SupportTicket', backref=db.backref('comments', lazy=True,
                              order_by='TicketComment.created_at.asc()'))
    author  = db.relationship('User', backref=db.backref('ticket_comments', lazy=True))



class TicketTimeSession(db.Model):
    """Logged work sessions on a support ticket."""
    __tablename__ = 'ticket_time_session'
    id         = db.Column(db.Integer, primary_key=True)
    ticket_id  = db.Column(db.Integer, db.ForeignKey('support_ticket.id'), nullable=False)
    user_id    = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    started_at = db.Column(db.DateTime, nullable=False)
    ended_at   = db.Column(db.DateTime, nullable=True)
    minutes    = db.Column(db.Integer, nullable=True)
    note       = db.Column(db.String(200), nullable=True)
    worker = db.relationship('User', backref=db.backref('time_sessions', lazy=True))

class Incident(db.Model):
    """Incident reports for pets in care."""
    __tablename__ = 'incident'

    id            = db.Column(db.Integer, primary_key=True)
    pet_id        = db.Column(db.Integer, db.ForeignKey('pet.id'), nullable=False)
    reported_by   = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    incident_type = db.Column(db.String(50), nullable=False)
    # injury, fight, escape_attempt, illness, medication_error, behavioral, property_damage, other
    severity      = db.Column(db.String(20), nullable=False)
    # minor, moderate, serious, critical
    description   = db.Column(db.Text, nullable=False)
    action_taken  = db.Column(db.Text)
    owner_notified = db.Column(db.Boolean, default=False)
    status        = db.Column(db.String(20), default='open')  # open, resolved
    incident_date = db.Column(db.DateTime, nullable=False, default=datetime.now)
    resolved_at   = db.Column(db.DateTime)
    created_at    = db.Column(db.DateTime, default=datetime.now)

    pet      = db.relationship('Pet', backref=db.backref('incidents', lazy=True,
                               order_by='Incident.incident_date.desc()'))
    reporter = db.relationship('User', foreign_keys=[reported_by],
                               backref=db.backref('reported_incidents', lazy=True))

    @property
    def severity_color(self):
        return {'minor': 'success', 'moderate': 'warning',
                'serious': 'danger', 'critical': 'dark'}.get(self.severity, 'secondary')

    @property
    def type_label(self):
        return {
            'injury':           'Injury',
            'fight':            'Fight / Altercation',
            'escape_attempt':   'Escape Attempt',
            'illness':          'Illness',
            'medication_error': 'Medication Error',
            'behavioral':       'Behavioral Issue',
            'property_damage':  'Property Damage',
            'other':            'Other'
        }.get(self.incident_type, self.incident_type.replace('_', ' ').title())

    def __repr__(self):
        return f'<Incident {self.id} {self.incident_type} {self.severity}>'


class CustomerPhoto(db.Model):
    """Photos uploaded by staff for a specific customer."""
    __tablename__ = 'customer_photo'

    id          = db.Column(db.Integer, primary_key=True)
    user_id     = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    filename    = db.Column(db.String(255), nullable=False)
    caption     = db.Column(db.String(255))
    uploaded_by = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    uploaded_at = db.Column(db.DateTime, default=datetime.now)

    customer = db.relationship('User', foreign_keys=[user_id],
                               backref=db.backref('customer_photos', lazy=True,
                                                  order_by='CustomerPhoto.uploaded_at.desc()'))
    uploader = db.relationship('User', foreign_keys=[uploaded_by])


class DailyLog(db.Model):
    """End-of-day staff log with notes and pet flags."""
    __tablename__ = 'daily_log'

    id           = db.Column(db.Integer, primary_key=True)
    log_date     = db.Column(db.Date, nullable=False, index=True)
    author_id    = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    notes        = db.Column(db.Text)                       # General end-of-day notes
    incidents    = db.Column(db.Text)                       # Any incidents today
    staffing     = db.Column(db.Text)                       # Staffing observations
    created_at   = db.Column(db.DateTime, default=datetime.now)
    updated_at   = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)

    author = db.relationship('User', foreign_keys=[author_id],
                             backref=db.backref('daily_logs', lazy=True))


class DailyLogPetFlag(db.Model):
    """Pets flagged in a daily log entry for follow-up."""
    __tablename__ = 'daily_log_pet_flag'

    id         = db.Column(db.Integer, primary_key=True)
    log_id     = db.Column(db.Integer, db.ForeignKey('daily_log.id'), nullable=False)
    pet_id     = db.Column(db.Integer, db.ForeignKey('pet.id'), nullable=False)
    flag_type  = db.Column(db.String(50))   # 'needs_followup', 'health_concern', 'behavioral', 'positive'
    note       = db.Column(db.String(255))

    log = db.relationship('DailyLog', backref=db.backref('pet_flags', lazy=True,
                                                          cascade='all, delete-orphan'))
    pet = db.relationship('Pet', backref=db.backref('daily_flags', lazy=True))

class PromoCode(db.Model):
    """Promotional discount codes — one-time use per customer."""
    __tablename__ = 'promo_code'
    id             = db.Column(db.Integer, primary_key=True)
    code           = db.Column(db.String(50),    unique=True, nullable=False)
    description    = db.Column(db.String(200),   nullable=True)
    discount_type  = db.Column(db.String(10),    nullable=False)   # 'percent' or 'fixed'
    discount_value = db.Column(db.Numeric(10,2), nullable=False)
    active         = db.Column(db.Boolean,       default=True)
    expires_at     = db.Column(db.DateTime,      nullable=True)
    created_by     = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    created_at     = db.Column(db.DateTime, default=datetime.now)
    uses           = db.relationship('PromoCodeUse', backref='promo_code', lazy=True)
    creator        = db.relationship('User', foreign_keys=[created_by],
                                     backref=db.backref('promo_codes_created', lazy=True))

    @property
    def is_valid(self):
        from datetime import datetime as dt
        if not self.active:
            return False
        if self.expires_at and self.expires_at < dt.now():
            return False
        return True

    @property
    def use_count(self):
        return len(self.uses)

    def has_been_used_by(self, customer_id):
        return any(u.customer_id == customer_id for u in self.uses)

    def display_value(self):
        if self.discount_type == 'percent':
            return f'{int(self.discount_value)}% off'
        return f'${float(self.discount_value):.2f} off'

    def __repr__(self):
        return f'<PromoCode {self.code}>'


class PromoCodeUse(db.Model):
    """Tracks which customers have used which promo codes."""
    __tablename__ = 'promo_code_use'
    id             = db.Column(db.Integer, primary_key=True)
    promo_code_id  = db.Column(db.Integer, db.ForeignKey('promo_code.id'), nullable=False)
    customer_id    = db.Column(db.Integer, db.ForeignKey('user.id'),       nullable=False)
    used_at        = db.Column(db.DateTime, default=datetime.now)
    invoice_adj_id = db.Column(db.Integer, nullable=True)
    customer       = db.relationship('User', backref=db.backref('promo_uses', lazy=True))

    def __repr__(self):
        return f'<PromoCodeUse code={self.promo_code_id} customer={self.customer_id}>'


class LoyaltyCredit(db.Model):
    """Earned loyalty credits — free nights or free daycare days."""
    __tablename__ = 'loyalty_credit'
    id             = db.Column(db.Integer, primary_key=True)
    customer_id    = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    credit_type    = db.Column(db.String(20),    nullable=False)   # 'boarding' or 'daycare'
    amount         = db.Column(db.Numeric(10,2), nullable=False)
    description    = db.Column(db.String(200),   nullable=True)
    status         = db.Column(db.String(20),    nullable=False, default='pending')
    earned_at      = db.Column(db.DateTime,      default=datetime.now)
    applied_at     = db.Column(db.DateTime,      nullable=True)
    applied_by     = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    invoice_adj_id = db.Column(db.Integer,       nullable=True)
    customer       = db.relationship('User', foreign_keys=[customer_id],
                                     backref=db.backref('loyalty_credits', lazy=True))
    applier        = db.relationship('User', foreign_keys=[applied_by])

    @property
    def is_pending(self):
        return self.status == 'pending'

    def __repr__(self):
        return f'<LoyaltyCredit {self.credit_type} ${self.amount} {self.status}>'

class AuditLog(db.Model):
    """Complete activity audit trail."""
    __tablename__ = 'audit_log'
    id          = db.Column(db.Integer,     primary_key=True)
    timestamp   = db.Column(db.DateTime,    nullable=False, index=True)
    user_id     = db.Column(db.Integer,     db.ForeignKey('user.id'), nullable=True)
    user_email  = db.Column(db.String(120), nullable=True)
    user_name   = db.Column(db.String(100), nullable=True)
    action      = db.Column(db.String(80),  nullable=False, index=True)
    entity_type = db.Column(db.String(50),  nullable=True,  index=True)
    entity_id   = db.Column(db.Integer,     nullable=True)
    entity_name = db.Column(db.String(200), nullable=True)
    description = db.Column(db.Text,        nullable=True)
    ip_address  = db.Column(db.String(45),  nullable=True)
    extra_data  = db.Column(db.Text,        nullable=True)
    actor = db.relationship('User', foreign_keys=[user_id],
                            backref=db.backref('audit_entries', lazy=True))
    @property
    def extra(self):
        import json
        if self.extra_data:
            try: return json.loads(self.extra_data)
            except Exception: return {}
        return {}
    @property
    def action_color(self):
        a = self.action.split('.')[-1]
        return {
            'created': 'success', 'approved': 'success', 'checkin': 'success',
            'checkout': 'warning', 'completed': 'primary', 'edited': 'info',
            'deleted': 'danger', 'cancelled': 'danger', 'reverted': 'warning',
            'login': 'secondary', 'logout': 'secondary', 'sent': 'info', 'paid': 'success',
        }.get(a, 'secondary')


class FacilitySetting(db.Model):
    """Key/value store for facility-wide configuration."""
    __tablename__ = 'facility_setting'

    id         = db.Column(db.Integer, primary_key=True)
    key        = db.Column(db.String(80), unique=True, nullable=False)
    value      = db.Column(db.String(255), nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    updated_by = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)

    def __repr__(self):
        return '<FacilitySetting %s=%s>' % (self.key, self.value)