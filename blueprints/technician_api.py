"""Technician portal — JSON API.

Each endpoint re-checks ownership on the row before touching it, so a
technician can never see or mutate another technician's work.
"""
from flask import (
    Blueprint, jsonify, request, session, abort, send_file,
    redirect, url_for, flash,
)
from datetime import datetime
from functools import wraps
import json
from models.technician_models import (
    IntakeRecord, ServiceReport, IncidentReport, JobLog,
    UploadedFile,
)
from app import db, User, Booking, create_notification
from services.job_status import NEXT_STATUS, STATUS_LABELS, FINISHED_STATUSES
from models.technician_models import technician_rating



technician_api_bp = Blueprint('technician_api', __name__)

def technician_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if 'user_id' not in session:
            return jsonify({'ok': False, 'reason': 'Not signed in.'}), 401
        user = User.query.get(session['user_id'])
        if not user or user.role != 'technician' or not user.is_active:
            return jsonify({'ok': False, 'reason': 'Not a technician.'}), 401
        return fn(*args, **kwargs)
    return wrapper


def _now():
    return datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')


def _job_to_dict(b):
    return {
        'id': b.id,
        'bookingId': b.booking_number,
        'customer': b.user.full_name if b.user else 'Unknown',
        'email':    b.user.email if b.user else '',
        'phone':    b.user.phone if b.user else '',
        'service':  b.service.name if b.service else '',
        'description': b.description,
        'address': b.address,
        'requestDate': b.created_at.strftime('%Y-%m-%d') if b.created_at else '',
        'amount': float(b.service.price) if b.service else 0,
        'paymentMethod': b.transaction.payment_method if b.transaction else 'unpaid',
        'repairStatus': b.status,
        'serviceMode': 'in_shop' if b.is_in_shop else 'home_service',
        'deviceType': b.device_type,
        'deviceModel': b.device_type,
        'scheduledDate': b.booking_date.strftime('%Y-%m-%d') if b.booking_date else '',
        'scheduledTime': b.booking_time.strftime('%I:%M %p') if b.booking_time else '',
        'priority': 'normal',
        'assignedAt': b.assigned_at.strftime('%Y-%m-%d %H:%M:%S') if b.assigned_at else '',
        'partsUsed': [],
        'releasedTo': None,
        'releasedAt': None,
    }


def _intake_dict(r):
    if not r:
        return None
    return {
        'id': r.id, 'jobId': r.booking_id, 'recordedAt': r.recorded_at,
        'deviceType': r.device_type, 'deviceModel': r.device_model,
        'serialNumber': r.serial_number, 'condition': r.condition,
        'conditionNotes': r.condition_notes,
        'accessories': json.loads(r.accessories or '[]'),
        'powersOn': r.powers_on, 'hasPassword': r.has_password,
        'passwordNote': r.password_note,
        'dataBackupConsent': r.data_backup_consent,
        'customerPresent': r.customer_present,
        'photosNote': r.photos_note,
    }


# ---------------------------------------------------------------------------
# SESSION
# ---------------------------------------------------------------------------

@technician_api_bp.route('/me')
@technician_required
def me():
    u = User.query.get(session['user_id'])
    rating, _rating_count = technician_rating(u.id)
    completed_jobs = Booking.query.filter(
        Booking.technician_id == u.id,
        Booking.status.in_(FINISHED_STATUSES)
    ).count()
    return jsonify({'ok': True, 'technician': {
        'id': u.id, 'username': u.username, 'name': u.full_name,
        'email': u.email, 'phone': u.phone, 'role': u.role,
        'rating': rating or 5.0,
        'completedJobs': completed_jobs,
        'availability': 'available',
        'avatarInitials': ''.join(
            w[0] for w in (u.full_name or '').split()[:2]).upper() or 'TT',
        'specialization': 'Computer Repair',
        'certifications': [],
        'id_verified': u.id_verified,
        'joined': u.created_at.strftime('%Y-%m-%d') if u.created_at else '',
    }})


@technician_api_bp.route('/login', methods=['POST'])
def login():
    body = request.get_json(silent=True) or {}
    tech_id  = (body.get('technician_id') or '').strip().upper()
    password = body.get('password') or ''
    user = User.query.filter_by(username=tech_id, role='technician').first()
    if not user or not user.check_password(password):
        return jsonify({'ok': False,
                        'reason': 'Incorrect Tech ID or password.'}), 401
    session['user_id']  = user.id
    session['username'] = user.username
    session['role']     = 'technician'
    return jsonify({'ok': True, 'technician': {
        'id': user.id, 'name': user.full_name,
        'avatarInitials': ''.join(
            w[0] for w in (user.full_name or '').split()[:2]).upper() or 'TT',
    }})


@technician_api_bp.route('/logout', methods=['POST'])
def logout():
    session.clear()
    return jsonify({'ok': True})


# ---------------------------------------------------------------------------
# DYNAMIC CONFIG
# ---------------------------------------------------------------------------

@technician_api_bp.route('/config')
def config():
    return jsonify({'ok': True, 'config': {
        'deviceTypes': [
            {'label': 'Laptop',  'icon': 'fa-laptop'},
            {'label': 'Desktop', 'icon': 'fa-desktop'},
            {'label': 'Tablet',  'icon': 'fa-tablet'},
            {'label': 'Printer', 'icon': 'fa-print'},
            {'label': 'Other',   'icon': 'fa-circle-question'},
        ],
        'accessories': [
            {'label': 'Charger / Adapter'}, {'label': 'Power Cable'},
            {'label': 'Battery'}, {'label': 'Carrying Bag'},
            {'label': 'Mouse'}, {'label': 'Keyboard'},
            {'label': 'External Drive'}, {'label': 'Manual / Box'},
        ],
        'serviceTypes': [
            {'label': 'Hardware Repair'}, {'label': 'Software Fix'},
            {'label': 'Hardware Upgrade'}, {'label': 'Storage Upgrade'},
            {'label': 'Accessory Replacement'}, {'label': 'Data Recovery'},
        ],
        'incidentTypes': [
            {'key': 'safety',     'label': 'Safety Concern',    'icon': 'fa-shield-halved'},
            {'key': 'electrical', 'label': 'Electrical Hazard', 'icon': 'fa-bolt'},
            {'key': 'animal',     'label': 'Aggressive Animal', 'icon': 'fa-dog'},
            {'key': 'access',     'label': 'Cannot Access',     'icon': 'fa-door-closed'},
            {'key': 'customer',   'label': 'Customer Dispute',  'icon': 'fa-user-xmark'},
            {'key': 'other',      'label': 'Other',             'icon': 'fa-circle-question'},
        ],
        'incidentSeverities': [
            {'key': 'low',      'label': 'Low',      'tone': 'ok'},
            {'key': 'medium',   'label': 'Medium',   'tone': 'warn'},
            {'key': 'high',     'label': 'High',     'tone': 'danger'},
            {'key': 'critical', 'label': 'Critical', 'tone': 'danger'},
        ],
        'outcomes': [
            {'key': 'fixed',            'label': 'Fixed',             'sub': 'Working as expected',          'icon': 'fa-circle-check'},
            {'key': 'partial',          'label': 'Partially fixed',   'sub': 'Improvement but not resolved', 'icon': 'fa-circle-half-stroke'},
            {'key': 'not_repairable',   'label': 'Not repairable',    'sub': 'Beyond repair',                'icon': 'fa-circle-xmark'},
            {'key': 'for_parts',        'label': 'Awaiting parts',    'sub': 'Paused waiting on stock',      'icon': 'fa-truck-fast'},
            {'key': 'customer_declined','label': 'Customer declined', 'sub': 'Customer refused the repair',  'icon': 'fa-hand'},
        ],
        'conditions': [
            {'key': 'good',    'label': 'Good',    'sub': 'No visible damage'},
            {'key': 'fair',    'label': 'Fair',    'sub': 'Cosmetic wear or minor damage'},
            {'key': 'poor',    'label': 'Poor',    'sub': 'Significant wear affecting use'},
            {'key': 'damaged', 'label': 'Damaged', 'sub': 'Cracked, bent, or liquid exposed'},
        ],
        'serviceModes': [
            {'key': 'in_shop',      'label': 'In-Shop',      'icon': 'fa-store'},
            {'key': 'home_service', 'label': 'Home Service', 'icon': 'fa-house-chimney'},
        ],
        'statusMeta': {
            'pending':     {'label': 'Accepted',  'tone': 'info',   'icon': 'fa-clipboard-check'},
            'confirmed':   {'label': 'Confirmed', 'tone': 'info',   'icon': 'fa-clipboard-check'},
            'in_progress': {'label': 'On Repair', 'tone': 'warn',   'icon': 'fa-screwdriver-wrench'},
            'completed':   {'label': 'Ready',     'tone': 'ok',     'icon': 'fa-box-open'},
            'cancelled':   {'label': 'Cancelled', 'tone': 'danger', 'icon': 'fa-circle-xmark'},
            'on_hold':     {'label': 'On Hold',   'tone': 'danger', 'icon': 'fa-pause'},
        },
        'track': ['confirmed', 'in_progress', 'completed'],
        'onHoldKey': 'on_hold',
    }})


# ---------------------------------------------------------------------------
# JOBS
# ---------------------------------------------------------------------------

@technician_api_bp.route('/jobs')
@technician_required
def list_jobs():
    scope = request.args.get('scope', 'all')
    q = Booking.query.filter_by(technician_id=session['user_id'])
    if scope == 'active':
        q = q.filter(Booking.status.notin_(['completed', 'cancelled']))
    jobs = q.order_by(Booking.assigned_at.desc()).all()
    return jsonify({'ok': True, 'jobs': [_job_to_dict(b) for b in jobs]})


@technician_api_bp.route('/jobs/stats')
@technician_required
def job_stats():
    tid = session['user_id']
    all_jobs = Booking.query.filter_by(technician_id=tid).all()
    return jsonify({'ok': True, 'stats': {
        'total':       len(all_jobs),
        'active':      sum(1 for b in all_jobs
                           if b.status not in ('completed', 'cancelled')),
        'accepted':    sum(1 for b in all_jobs
                           if b.status in ('pending', 'confirmed')),
        'on_repair':   sum(1 for b in all_jobs if b.status == 'in_progress'),
        'ready':       sum(1 for b in all_jobs if b.status == 'completed'),
        'released':    sum(1 for b in all_jobs if b.status == 'completed'),
        'on_hold':     0,
        'homeService': sum(1 for b in all_jobs if not b.is_in_shop),
        'inShop':      sum(1 for b in all_jobs if b.is_in_shop),
        'highPriority': 0,
    }})


@technician_api_bp.route('/jobs/<int:job_id>')
@technician_required
def get_job(job_id):
    b = Booking.query.get_or_404(job_id)
    if b.technician_id != session['user_id']:
        return jsonify({'ok': False, 'reason': 'Not found.'}), 404
    return jsonify({'ok': True, 'job': _job_to_dict(b)})


@technician_api_bp.route('/jobs/<int:job_id>/advance', methods=['POST'])
@technician_required
def advance_job(job_id):
    b = Booking.query.get_or_404(job_id)
    if b.technician_id != session['user_id']:
        return jsonify({'ok': False, 'reason': 'Not found.'}), 404

    def fail(msg):
        if request.is_json:
            return jsonify({'ok': False, 'reason': msg}), 400
        flash(msg, 'danger')
        return redirect(url_for('technician.job_detail', job_id=b.id))

    nxt = NEXT_STATUS.get(b.status)
    if not nxt:
        return fail('This job cannot be advanced from its current status.')
    if b.status == 'confirmed' and not IntakeRecord.query.filter_by(booking_id=b.id).first():
        return fail('Record the device intake first.')
    report = ServiceReport.query.filter_by(booking_id=b.id)\
        .order_by(ServiceReport.id.desc()).first()
    if b.status == 'diagnosis_pending' and not (report and (report.diagnosis or '').strip()):
        return fail('Write a diagnosis before starting the repair.')

    texts = {'diagnosis_pending': 'Device received and recorded. Diagnosis in progress.',
             'in_progress': 'Diagnosis complete. Repair started.',
             'completed': 'Repair complete. Device ready for collection.',
             'released': 'Device released to customer.'}
    actions = {'diagnosis_pending': 'intake', 'in_progress': 'status',
               'completed': 'status', 'released': 'release'}
    if b.status == 'in_progress' and not (report and report.status == 'submitted'):
        return fail('Submit your service report before marking the device ready.')

    b.status = nxt
    b.updated_at = datetime.utcnow()
    db.session.add(JobLog(booking_id=b.id, at=_now(),
                          by_name=session.get('username', 'Technician'),
                          action=actions[nxt], text=texts[nxt]))
    db.session.commit()

    from app import create_notification
    create_notification(b.user_id, 'Repair Status Updated',
                        f'Your booking {b.booking_number} is now: {STATUS_LABELS[nxt]}.', 'info')
    if not request.is_json:
        return redirect(url_for('technician.job_detail', job_id=b.id))
    return jsonify({'ok': True, 'job': _job_to_dict(b)})

@technician_api_bp.route('/jobs/<int:job_id>/notes', methods=['POST'])
@technician_required
def save_notes(job_id):
    b = Booking.query.get_or_404(job_id)
    if b.technician_id != session['user_id']:
        return jsonify({'ok': False, 'reason': 'Not found.'}), 404

    body = request.get_json(silent=True) or {}
    if body.get('diagnosis'):
        b.description = body['diagnosis']
    db.session.add(JobLog(
        booking_id=b.id, at=_now(),
        by_name=session.get('username', 'Technician'),
        action='note', text='Repair notes updated.',
    ))
    db.session.commit()
    return jsonify({'ok': True})

@technician_api_bp.route('/jobs/<int:job_id>/diagnosis', methods=['POST'])
@technician_required
def save_diagnosis(job_id):
    b = Booking.query.get_or_404(job_id)
    if b.technician_id != session['user_id']:
        return jsonify({'ok': False, 'reason': 'Not found.'}), 404
    is_form = not request.is_json
    body = request.form if is_form else (request.get_json(silent=True) or {})
    diagnosis = (body.get('diagnosis') or '').strip()

    def fail(msg):
        if is_form:
            flash(msg, 'danger')
            return redirect(url_for('technician.job_detail', job_id=b.id))
        return jsonify({'ok': False, 'reason': msg}), 400

    if not diagnosis:
        return fail('Diagnosis text is required.')
    if b.status not in ('confirmed', 'diagnosis_pending'):
        return fail('Diagnosis can only be edited before the repair starts.')

    r = ServiceReport.query.filter_by(booking_id=b.id)\
        .order_by(ServiceReport.id.desc()).first()
    if not r:
        r = ServiceReport(booking_id=b.id, technician_id=session['user_id'],
                          status='draft', created_at=_now())
        db.session.add(r)
    r.diagnosis = diagnosis
    r.updated_at = _now()
    db.session.add(JobLog(booking_id=b.id, at=_now(),
                          by_name=session.get('username', 'Technician'),
                          action='diagnosis', text='Diagnosis recorded.'))
    db.session.commit()

    if is_form:
        flash('Diagnosis saved.', 'success')
        return redirect(url_for('technician.job_detail', job_id=b.id))
    return jsonify({'ok': True, 'diagnosis': diagnosis})


@technician_api_bp.route('/jobs/<int:job_id>/logs')
@technician_required
def job_logs(job_id):
    b = Booking.query.get_or_404(job_id)
    if b.technician_id != session['user_id']:
        return jsonify({'ok': False, 'reason': 'Not found.'}), 404
    logs = JobLog.query.filter_by(booking_id=b.id).order_by(JobLog.id.desc()).all()
    return jsonify({'ok': True, 'logs': [
        {'action': l.action, 'text': l.text, 'by': l.by_name, 'at': l.at} for l in logs]})
# ---------------------------------------------------------------------------
# INTAKE
# ---------------------------------------------------------------------------
@technician_api_bp.route('/jobs/<int:job_id>/intake', methods=['GET', 'POST'])
@technician_required
def job_intake(job_id):
    b = Booking.query.get_or_404(job_id)
    if b.technician_id != session['user_id']:
        return jsonify({'ok': False, 'reason': 'Not found.'}), 404

    if request.method == 'POST':
        is_form = not request.is_json
        body = request.form if is_form else (request.get_json(silent=True) or {})

        r = IntakeRecord.query.filter_by(booking_id=job_id).first()
        if not r:
            r = IntakeRecord(booking_id=job_id)
            db.session.add(r)

        r.recorded_at         = _now()
        r.device_type         = body.get('deviceType', '')
        r.device_model        = body.get('deviceModel', '')
        r.serial_number       = body.get('serialNumber', '')
        r.condition           = body.get('condition', 'good')
        r.condition_notes     = body.get('conditionNotes', '')
        r.accessories         = json.dumps(
            body.getlist('accessories') if is_form
            else body.get('accessories', [])
        )
        r.powers_on           = bool(body.get('powersOn'))
        r.has_password        = bool(body.get('hasPassword'))
        r.password_note       = body.get('passwordNote', '')
        r.data_backup_consent = bool(body.get('dataBackupConsent'))
        r.customer_present    = bool(body.get('customerPresent'))
        r.photos_note         = body.get('photosNote', '')

        db.session.add(JobLog(
            booking_id=job_id, at=_now(),
            by_name=session.get('username', 'Technician'),
            action='intake', text='Intake recorded.',
        ))
        db.session.commit()

        if is_form:
            flash('Intake record saved.', 'success')
            return redirect(url_for('technician.job_detail', job_id=job_id))
        return jsonify({'ok': True, 'record': _intake_dict(r)})

    r = IntakeRecord.query.filter_by(booking_id=job_id).first()
    return jsonify({'ok': True, 'record': _intake_dict(r)})

# ---------------------------------------------------------------------------
# SERVICE REPORT
# ---------------------------------------------------------------------------

@technician_api_bp.route('/jobs/<int:job_id>/report', methods=['GET', 'POST'])
@technician_required
def job_report(job_id):
    b = Booking.query.get_or_404(job_id)
    if b.technician_id != session['user_id']:
        return jsonify({'ok': False, 'reason': 'Not found.'}), 404

    if request.method == 'POST':
        is_form = not request.is_json
        body = request.form if is_form else (request.get_json(silent=True) or {})
        action = body.get('action', 'submit')

        r = ServiceReport.query.filter_by(booking_id=job_id).first()

        # Submitted reports are permanently read-only.
        if r and r.status == 'submitted':
            msg = 'This report was already submitted and is read-only.'
            if is_form:
                flash(msg, 'danger')
                return redirect(url_for('technician.report_form', job_id=job_id))
            return jsonify({'ok': False, 'reason': msg}), 400

        if not r:
            r = ServiceReport(booking_id=job_id, created_at=_now())
            db.session.add(r)

        r.technician_id = session['user_id']
        r.status = 'submitted' if action == 'submit' else 'draft'
        r.updated_at = _now()
        if r.status == 'submitted' and not r.submitted_at:
            r.submitted_at = _now()
        r.diagnosis = body.get('diagnosis', '')
        r.tests = body.get('tests', '')
        r.work_performed = body.get('workPerformed', '')
        r.hours_spent = float(body.get('hoursSpent') or 0)
        r.outcome = body.get('outcome', 'fixed')
        r.outcome_notes = body.get('outcomeNotes', '')
        r.recommendations = body.get('recommendations', '')
        r.photos_note = body.get('photosNote', '')
        r.admin_note = body.get('adminNote', '')

        db.session.add(JobLog(
            booking_id=job_id, at=_now(),
            by_name=session.get('username', 'Technician'),
            action='report', text=f'Service report {r.status}.',
        ))
        db.session.commit()

        if r.status == 'submitted':
            for a in User.query.filter_by(role='admin', is_active=True).all():
                create_notification(
                    a.id,
                    'Service Report Submitted',
                    f'{b.booking_number}: report submitted by {session.get("username")}.',
                    'info'
                )

        if is_form:
            flash(f'Report {r.status}.', 'success')
            return redirect(url_for('technician.job_detail', job_id=job_id))
        return jsonify({'ok': True, 'report': {'id': r.id, 'status': r.status}})

    r = ServiceReport.query.filter_by(booking_id=job_id).first()
    if not r:
        return jsonify({'ok': True, 'report': None})
    return jsonify({'ok': True, 'report': {
        'id': r.id, 'jobId': r.booking_id, 'status': r.status,
        'submittedAt': r.submitted_at, 'diagnosis': r.diagnosis,
        'tests': r.tests, 'workPerformed': r.work_performed,
        'hoursSpent': r.hours_spent, 'outcome': r.outcome,
        'outcomeNotes': r.outcome_notes,
        'recommendations': r.recommendations,
        'photosNote': r.photos_note, 'adminNote': r.admin_note,
    }})


# ---------------------------------------------------------------------------
# INCIDENTS
# ---------------------------------------------------------------------------
@technician_api_bp.route('/incidents', methods=['GET', 'POST'])
@technician_required
def incidents():
    tid = session['user_id']

    if request.method == 'POST':
        is_form = not request.is_json
        body = request.form if is_form else (request.get_json(silent=True) or {})

        desc = (body.get('description') or '').strip()
        if len(desc) < 20:
            if is_form:
                flash('Describe what happened (at least 20 characters).', 'danger')
                return redirect(url_for('technician.incidents'))
            return jsonify({
                'ok': False,
                'reason': 'Describe what happened (at least 20 characters).'
            }), 400

        job_id = body.get('jobId') or None
        if job_id in ('', 'None', 'null'):
            job_id = None
        else:
            try:
                job_id = int(job_id)
            except (TypeError, ValueError):
                job_id = None

        r = IncidentReport(
            technician_id=tid,
            booking_id=job_id,
            reported_at=_now(),
            type=body.get('type', 'other'),
            severity=body.get('severity', 'low'),
            location=body.get('location', ''),
            description=desc,
            action_taken=body.get('actionTaken', ''),
            authorities_notified=bool(body.get('authoritiesNotified')),
        )
        db.session.add(r)
        db.session.commit()

        for a in User.query.filter_by(role='admin', is_active=True).all():
            create_notification(
                a.id,
                'Incident Reported',
                f'Incident #{r.id} was reported by {session.get("username", "Technician")}.',
                'warning'
            )

        if is_form:
            flash(f'Incident {r.id} submitted to management.', 'success')
            return redirect(url_for('technician.incidents'))
        return jsonify({'ok': True, 'incident': {'id': r.id}})

    rows = IncidentReport.query.filter_by(technician_id=tid) \
        .order_by(IncidentReport.reported_at.desc()).all()
    return jsonify({'ok': True, 'incidents': [{
        'id': r.id, 'jobId': r.booking_id, 'type': r.type,
        'severity': r.severity, 'location': r.location,
        'description': r.description, 'reportedAt': r.reported_at,
        'status': r.status,
        'authoritiesNotified': r.authorities_notified,
        'reviewedBy': r.reviewed_by, 'reviewedAt': r.reviewed_at,
    } for r in rows]})

# ---------------------------------------------------------------------------
# UPLOADS
# ---------------------------------------------------------------------------

@technician_api_bp.route('/uploads', methods=['POST'])
@technician_required
def upload():
    from services.upload_service import save_upload
    file = request.files.get('file')
    ok, result = save_upload(
        file,
        request.form.get('ownerType', ''),
        request.form.get('ownerId', ''),
        request.form.get('jobId'),
        session['user_id'],
        request.form.get('caption', ''),
    )
    if ok:
        return jsonify({'ok': True, 'file': result})
    return jsonify({'ok': False, 'reason': result}), 400


@technician_api_bp.route('/uploads/<int:upload_id>')
@technician_required
def serve_upload(upload_id):
    r = UploadedFile.query.get_or_404(upload_id)
    if r.technician_id != session['user_id']:
        abort(404)
    from services.upload_service import path_for
    return send_file(path_for(r), mimetype=r.mime_type)


# ---------------------------------------------------------------------------
# NOTIFICATIONS
# ---------------------------------------------------------------------------

@technician_api_bp.route('/notifications')
@technician_required
def notifications():
    from app import Notification
    rows = Notification.query.filter_by(user_id=session['user_id']) \
        .order_by(Notification.created_at.desc()).limit(20).all()
    return jsonify({'ok': True, 'notifications': [{
        'id': n.id, 'title': n.title, 'message': n.message,
        'type': n.type, 'read': n.is_read,
        'at': n.created_at.strftime('%Y-%m-%d %H:%M:%S') if n.created_at else '',
    } for n in rows]})


@technician_api_bp.route('/notifications/read', methods=['POST'])
@technician_required
def notifications_read():
    from app import Notification
    Notification.query.filter_by(
        user_id=session['user_id'], is_read=False
    ).update({'is_read': True})
    db.session.commit()
    return jsonify({'ok': True})
