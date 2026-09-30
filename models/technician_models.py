"""Technician-specific tables.

Everything keys off existing bookings.id and users.id, so the technician
portal and the customer/admin side share one source of truth for jobs
and identities.

Importing `db` from app.py — never creating a second SQLAlchemy
instance — is what makes that sharing work. If this file ever does
`db = SQLAlchemy()`, you've got two independent metadata registries
and the two halves of the app silently disagree about which tables
exist.
"""
from datetime import datetime
from app import db


class IntakeRecord(db.Model):
    """Device intake. One per booking. Records the condition and
    accessories as handed over by the customer."""
    __tablename__ = 'tech_intake_records'

    id                   = db.Column(db.Integer, primary_key=True)
    booking_id           = db.Column(db.Integer,
                                     db.ForeignKey('bookings.id'),
                                     unique=True, nullable=False)
    recorded_at          = db.Column(db.String(20))
    device_type          = db.Column(db.String(40))
    device_model         = db.Column(db.String(120))
    serial_number        = db.Column(db.String(80))
    condition            = db.Column(db.String(20))
    condition_notes      = db.Column(db.Text)
    accessories          = db.Column(db.Text, default='[]')     # JSON array
    powers_on            = db.Column(db.Boolean, default=False)
    has_password         = db.Column(db.Boolean, default=False)
    password_note        = db.Column(db.String(255))
    data_backup_consent  = db.Column(db.Boolean, default=False)
    customer_present     = db.Column(db.Boolean, default=False)
    photos_note          = db.Column(db.Text)


class ServiceReport(db.Model):
    """Written report the technician submits to the admin after
    completing a job. Starts as a draft, then submitted.

    One active report per booking at a time — the app archives
    submitted reports when a new one is started, so historical
    reports don't get lost.
    """
    __tablename__ = 'tech_service_reports'

    id               = db.Column(db.Integer, primary_key=True)
    booking_id       = db.Column(db.Integer,
                                 db.ForeignKey('bookings.id'),
                                 nullable=False)
    technician_id    = db.Column(db.Integer,
                                 db.ForeignKey('users.id'),
                                 nullable=False)
    status           = db.Column(db.String(20), default='draft')
    created_at       = db.Column(db.String(20))
    updated_at       = db.Column(db.String(20))
    submitted_at     = db.Column(db.String(20))
    diagnosis        = db.Column(db.Text)
    tests            = db.Column(db.Text)
    work_performed   = db.Column(db.Text)
    hours_spent      = db.Column(db.Float, default=0)
    outcome          = db.Column(db.String(32))
    outcome_notes    = db.Column(db.Text)
    recommendations  = db.Column(db.Text)
    photos_note      = db.Column(db.Text)
    admin_note       = db.Column(db.Text)
    reviewed_by      = db.Column(db.String(120))
    reviewed_at      = db.Column(db.String(20))
    review_status    = db.Column(db.String(20), default='pending')


class IncidentReport(db.Model):
    """Safety or security incident filed by a technician. Can be tied
    to a booking or stand alone.

    Filed by the technician; reviewed by an admin. The technician
    cannot close their own report — only an admin updates `status`
    and `reviewed_by`.
    """
    __tablename__ = 'tech_incident_reports'

    id                   = db.Column(db.Integer, primary_key=True)
    booking_id           = db.Column(db.Integer,
                                     db.ForeignKey('bookings.id'),
                                     nullable=True)
    technician_id        = db.Column(db.Integer,
                                     db.ForeignKey('users.id'),
                                     nullable=False)
    reported_at          = db.Column(db.String(20))
    type                 = db.Column(db.String(32))
    severity             = db.Column(db.String(16))
    location             = db.Column(db.String(255))
    description          = db.Column(db.Text)
    action_taken         = db.Column(db.Text)
    authorities_notified = db.Column(db.Boolean, default=False)
    status               = db.Column(db.String(20), default='open')
    reviewed_by          = db.Column(db.String(120))
    reviewed_at          = db.Column(db.String(20))


class ApprovalRequest(db.Model):
    """Approval a technician requests when the actual fault differs
    from what the customer reported, or when extra work is needed.

    While an approval is pending, the booking sits at `on_hold`. The
    app enforces that at the service layer, not here — this model
    only tracks the request itself.
    """
    __tablename__ = 'tech_approval_requests'

    id                = db.Column(db.Integer, primary_key=True)
    booking_id        = db.Column(db.Integer,
                                  db.ForeignKey('bookings.id'),
                                  nullable=False)
    technician_id     = db.Column(db.Integer,
                                  db.ForeignKey('users.id'),
                                  nullable=False)
    requested_at      = db.Column(db.String(20))
    findings          = db.Column(db.Text)
    proposed_work     = db.Column(db.Text)
    additional_cost   = db.Column(db.Float, default=0)
    extra_days        = db.Column(db.Integer, default=0)
    status            = db.Column(db.String(20), default='pending')
    responded_at      = db.Column(db.String(20))
    customer_response = db.Column(db.Text)


class JobLog(db.Model):
    """Every meaningful action taken on a job. Displayed as the
    timeline on both the technician's job detail page and the
    customer's monitor page."""
    __tablename__ = 'tech_job_logs'

    id          = db.Column(db.Integer, primary_key=True)
    booking_id  = db.Column(db.Integer,
                            db.ForeignKey('bookings.id'),
                            nullable=False,
                            index=True)
    at          = db.Column(db.String(20))
    by_name     = db.Column(db.String(120))
    action      = db.Column(db.String(32))
    text        = db.Column(db.Text)


class UploadedFile(db.Model):
    """Photo, PDF, or other evidence file attached to an intake
    record, service report, or incident.

    `owner_type` is 'intake' | 'report' | 'incident'. `owner_id` is
    the id of the owning row. The file itself lives on disk under
    instance/uploads/tech/ and is only servable through the
    authenticated /technician/api/uploads/<id> route.
    """
    __tablename__ = 'tech_uploaded_files'

    id             = db.Column(db.Integer, primary_key=True)
    owner_type     = db.Column(db.String(20))
    owner_id       = db.Column(db.Integer)
    booking_id     = db.Column(db.Integer,
                               db.ForeignKey('bookings.id'),
                               nullable=True)
    technician_id  = db.Column(db.Integer,
                               db.ForeignKey('users.id'),
                               nullable=False)
    filename       = db.Column(db.String(255))
    original_name  = db.Column(db.String(255))
    mime_type      = db.Column(db.String(80))
    size_bytes     = db.Column(db.Integer)
    caption        = db.Column(db.String(255))
    uploaded_at    = db.Column(db.String(20))


class ServiceRating(db.Model):
    """Customer's rating of a completed repair.

    One per booking, enforced by the UNIQUE constraint on
    booking_id. Immutable once written — no UPDATE endpoint
    exists. `technician_id` is indexed so the average rating
    computation on every monitor-page load is cheap.
    """
    __tablename__ = 'service_ratings'

    id             = db.Column(db.Integer, primary_key=True)
    booking_id     = db.Column(db.Integer,
                               db.ForeignKey('bookings.id'),
                               unique=True, nullable=False)
    technician_id  = db.Column(db.Integer,
                               db.ForeignKey('users.id'),
                               nullable=False,
                               index=True)
    customer_id    = db.Column(db.Integer,
                               db.ForeignKey('users.id'),
                               nullable=False)
    stars          = db.Column(db.SmallInteger)
    experience     = db.Column(db.Text)
    improvement    = db.Column(db.Text)
    submitted_at   = db.Column(db.DateTime, default=datetime.utcnow)
    
def technician_rating(tech_id):
    from sqlalchemy import func
    avg, cnt = db.session.query(func.avg(ServiceRating.stars), func.count(ServiceRating.id))\
        .filter(ServiceRating.technician_id == tech_id).one()
    return (round(float(avg), 1) if avg else None), cnt