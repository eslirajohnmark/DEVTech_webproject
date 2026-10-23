"""Technician portal — server-rendered pages.

A technician is a row in the `technicians` table; a job they work
on is a `Booking` row with technician_id pointing at them. Nothing
here duplicates the admin's own views — it just gives the assigned
technician their own working surface for the same bookings.
"""
from flask import (
    Blueprint, render_template, redirect, url_for,
    session, flash, abort, request,
)
from datetime import datetime
from functools import wraps
from services.job_status import ACTIVE_STATUSES, FINISHED_STATUSES
from models.technician_models import technician_rating
from app import db, Technician, Booking, limiter, current_account
from models.technician_models import (
    IntakeRecord, ServiceReport, IncidentReport, JobLog, ApprovalRequest,
)


technician_bp = Blueprint(
    'technician', __name__,
    template_folder='../templates',
    static_folder='../static',
)




def technician_required(fn):
    """Guards every page in this blueprint. Requires a signed-in
    technician whose account is still active."""
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please sign in as a technician.', 'warning')
            return redirect(url_for('technician.login'))
        user = current_account() if session.get('role') == 'technician' else None
        if not user or not user.is_active:
            session.clear()
            flash('Technician access required.', 'danger')
            return redirect(url_for('technician.login'))
        return fn(*args, **kwargs)
    return wrapper


# ---------------------------------------------------------------------------
# AUTH
# ---------------------------------------------------------------------------

@technician_bp.route('/login', methods=['GET', 'POST'])
@limiter.limit('5 per minute', methods=['POST'])
def login():
    if session.get('role') == 'technician' and current_account():
        return redirect(url_for('technician.dashboard'))

    if request.method == 'POST':
        tech_id  = (request.form.get('technician_id') or '').strip().upper()
        password = request.form.get('password') or ''

        user = Technician.query.filter(db.func.upper(Technician.username) == tech_id).first()
        if not user or not user.check_password(password):
            flash('Incorrect Tech ID or password.', 'danger')
            return render_template('technician/login.html',
                                   prefill_id=tech_id), 401

        if not user.is_active:
            flash('This technician account is not active. It may be awaiting '
                  'admin approval or has been deactivated.', 'danger')
            return render_template('technician/login.html',
                                   prefill_id=tech_id), 403

        from app import login_account
        login_account(user, remember=bool(request.form.get('remember_me')))
        user.last_active = datetime.utcnow()
        db.session.commit()
        return redirect(url_for('technician.dashboard'))

    return render_template('technician/login.html',
                           prefill_id=request.args.get('registered', ''))


@technician_bp.route('/register', methods=['GET', 'POST'])
@limiter.limit('5 per hour', methods=['POST'])
def register():
    if request.method == 'POST':
        from services.technician_service import register_technician
        result = register_technician(request.form)
        if not result['ok']:
            flash(result['reason'], 'danger')
            return render_template('technician/registration.html',
                                   form=request.form), 400
        flash('Registration received. An administrator must activate your '
              'account before you can sign in.', 'success')
        return redirect(url_for('technician.login',
                                registered=result['technician_id']))
    return render_template('technician/registration.html', form={})


@technician_bp.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('technician.login'))


# ---------------------------------------------------------------------------
# PAGES
# ---------------------------------------------------------------------------

@technician_bp.route('/dashboard')
@technician_required
def dashboard():
    tid = session['user_id']
    technician = current_account()

    all_jobs = Booking.query.filter_by(technician_id=tid)\
        .order_by(Booking.created_at.desc()).all()
    
    total = len(all_jobs)
    on_repair = sum(1 for j in all_jobs if j.status in ('diagnosis_pending', 'in_progress'))
    ready     = sum(1 for j in all_jobs if j.status == 'completed')
    released  = sum(1 for j in all_jobs if j.status == 'released')
    active    = [j for j in all_jobs if j.status in ACTIVE_STATUSES]

    today = datetime.utcnow().date()
    todays_jobs = [j for j in all_jobs if j.booking_date == today]

    return render_template('technician/dashboard.html',
                           technician=technician,
                           total=total, on_repair=on_repair, ready=ready, released=released,
                           active=active, active_count=len(active),
                           todays_jobs=todays_jobs)


@technician_bp.route('/jobs')
@technician_required
def my_jobs():
    tid = session['user_id']
    status = request.args.get('status', 'all')

    q = Booking.query.filter_by(technician_id=tid)
    if status != 'all':
        q = q.filter_by(status=status)

    jobs = q.order_by(
        Booking.assigned_at.is_(None),
        Booking.assigned_at.desc(),
        Booking.created_at.desc()
    ).all()

    return render_template('technician/my_jobs.html', jobs=jobs)

@technician_bp.route('/jobs/<int:job_id>')
@technician_required
def job_detail(job_id):
    booking = Booking.query.get_or_404(job_id)
    if booking.technician_id != session['user_id']:
        abort(403)
    intake = IntakeRecord.query.filter_by(booking_id=booking.id).first()
    report = ServiceReport.query.filter_by(booking_id=booking.id)\
        .order_by(ServiceReport.id.desc()).first()
    logs = JobLog.query.filter_by(booking_id=booking.id)\
        .order_by(JobLog.at.desc()).all()
    approvals = ApprovalRequest.query.filter_by(booking_id=booking.id)\
        .order_by(ApprovalRequest.id.desc()).all()
    pending_approval = next((a for a in approvals if a.status == 'pending'), None)
    return render_template('technician/job_detail.html',
                           job=booking, intake=intake, report=report, logs=logs,
                           approvals=approvals, pending_approval=pending_approval)


@technician_bp.route('/intake')
@technician_required
def intake_picker():
    tid = session['user_id']
    jobs = Booking.query.filter_by(technician_id=tid)\
        .filter(Booking.status.notin_(['cancelled']))\
        .order_by(Booking.created_at.desc()).all()

    recorded_ids = set()
    if jobs:
        recorded_ids = {
            r.booking_id for r in
            IntakeRecord.query.filter(
                IntakeRecord.booking_id.in_([j.id for j in jobs])
            ).all()
        }

    return render_template('technician/device_intake.html',
                           current=None, jobs=jobs,
                           recorded_ids=recorded_ids)


@technician_bp.route('/intake/<int:job_id>')
@technician_required
def intake_form(job_id):
    booking = Booking.query.get_or_404(job_id)
    if booking.technician_id != session['user_id']:
        abort(403)
    record = IntakeRecord.query.filter_by(booking_id=job_id).first()
    jobs = Booking.query.filter_by(technician_id=session['user_id'])\
        .filter(Booking.status.notin_(['cancelled'])).all()
    return render_template('technician/device_intake.html',
                           current=job_id, job=booking, record=record,
                           jobs=jobs, recorded_ids=set())


@technician_bp.route('/reports')
@technician_required
def reports_picker():
    tid = session['user_id']
    jobs = Booking.query.filter_by(technician_id=tid)\
        .order_by(Booking.created_at.desc()).all()
    reports = {j.id: ServiceReport.query.filter_by(booking_id=j.id)
               .order_by(ServiceReport.id.desc()).first() for j in jobs}
    return render_template('technician/service_report.html',
                           current=None, jobs=jobs, reports=reports)


@technician_bp.route('/reports/new/<int:job_id>')
@technician_required
def report_form(job_id):
    booking = Booking.query.get_or_404(job_id)
    if booking.technician_id != session['user_id']:
        abort(403)
    report = ServiceReport.query.filter_by(booking_id=job_id)\
        .order_by(ServiceReport.id.desc()).first()
    return render_template('technician/service_report.html',
                           current=job_id, job=booking, report=report)


@technician_bp.route('/incidents')
@technician_required
def incidents():
    tid = session['user_id']
    reports = IncidentReport.query.filter_by(technician_id=tid)\
        .order_by(IncidentReport.reported_at.desc()).all()
    jobs = Booking.query.filter_by(technician_id=tid)\
        .order_by(Booking.created_at.desc()).all()
    return render_template('technician/incident_report.html',
                           reports=reports, jobs=jobs,
                           prefill_job=request.args.get('job'))


# ---------------------------------------------------------------------------
# MESSAGES
# ---------------------------------------------------------------------------

def _tech_thread(conv):
    """Shape an inbox entry from app._load_inbox for the technician template."""
    initials = ''.join(w[0] for w in (conv['name'] or '?').split()[:2]).upper() or '?'
    return dict(conv, initials=initials,
                role_label='Administrator' if conv['role'] == 'admin' else 'Customer',
                last_message=conv['last_message'] or 'No messages yet',
                last_time=conv['last_time'].strftime('%b %d, %I:%M %p') if conv['last_message'] else '')


@technician_bp.route('/messages')
@technician_required
def messages():
    from app import _load_inbox, _account_from_key
    me = current_account()
    thread_param = request.args.get('thread')
    selected = _account_from_key(thread_param) if thread_param else None
    if thread_param and not selected:
        abort(404)

    conversations, active, rows = _load_inbox(me, selected)
    if selected is not None and not active:
        abort(403)

    thread_messages = [{
        'content': m.content,
        'created_at': m.created_at.strftime('%b %d, %I:%M %p'),
        'is_sent': m.is_sent,
        'attachments': m.attachments,
    } for m in rows]
    return render_template('technician/messages.html',
                           conversations=[_tech_thread(c) for c in conversations],
                           active_thread=_tech_thread(active) if active else None,
                           thread_messages=thread_messages)


@technician_bp.route('/messages/<other_key>/send', methods=['POST'])
@technician_required
def message_send(other_key):
    from app import (check_message_attachment, MAX_MESSAGE_LENGTH, send_message,
                     _account_from_key, _can_message)

    content = (request.form.get('content') or '').strip()
    checked, file_error = check_message_attachment(request.files.get('attachment'))
    if file_error:
        flash(file_error, 'danger')
        return redirect(url_for('technician.messages', thread=other_key))
    if (not content and not checked) or len(content) > MAX_MESSAGE_LENGTH:
        flash('Write a message or attach a file.', 'danger')
        return redirect(url_for('technician.messages', thread=other_key))

    me = current_account()
    other = _account_from_key(other_key)
    if not other:
        abort(404)
    if not _can_message(me, other):
        abort(403)

    send_message(me, other, content, checked=checked)
    return redirect(url_for('technician.messages', thread=other.key))


# ---------------------------------------------------------------------------
# PROFILE
# ---------------------------------------------------------------------------

@technician_bp.route('/profile')
@technician_required
def profile():
    tid = session['user_id']
    tech = current_account()
    base = Booking.query.filter_by(technician_id=tid)
    stats = {
        'total': base.count(),
        'active': base.filter(Booking.status.in_(ACTIVE_STATUSES)).count(),
        'released': base.filter(Booking.status.in_(FINISHED_STATUSES)).count(),
        'home_service': base.filter_by(is_in_shop=False).count(),
    }
    rating, rating_count = technician_rating(tid)
    return render_template('technician/profile.html', tech=tech, stats=stats,
                           rating=rating, rating_count=rating_count)


@technician_bp.route('/profile/details', methods=['POST'])
@technician_required
def update_details():
    """Name and contact details. Email (sign-in identity) and Tech ID stay fixed."""
    tech = current_account()
    values = {f: (request.form.get(f) or '').strip()
              for f in ('full_name', 'phone', 'address', 'city', 'province')}
    limits = {'full_name': 100, 'phone': 20, 'address': 255, 'city': 50, 'province': 50}
    if not values['full_name']:
        flash('Full name is required.', 'danger')
        return redirect(url_for('technician.profile'))
    too_long = [f for f, n in limits.items() if len(values[f]) > n]
    if too_long:
        flash('Some details are too long. Please shorten them.', 'danger')
        return redirect(url_for('technician.profile'))
    tech.full_name = values['full_name']
    for f in ('phone', 'address', 'city', 'province'):
        setattr(tech, f, values[f] or None)
    db.session.commit()
    flash('Your details were saved.', 'success')
    return redirect(url_for('technician.profile'))


@technician_bp.route('/profile/password', methods=['POST'])
@technician_required
def change_password():
    tech = current_account()

    current = request.form.get('current_password', '')
    new = request.form.get('new_password', '')
    confirm = request.form.get('confirm_password', '')

    if not tech.check_password(current):
        flash('Current password is incorrect.', 'danger')
        return redirect(url_for('technician.profile'))

    if new != confirm:
        flash('New passwords do not match.', 'danger')
        return redirect(url_for('technician.profile'))

    if len(new) < 8 or not any(c.isalpha() for c in new) or not any(c.isdigit() for c in new):
        flash('Password must be at least 8 characters and include a letter and a number.', 'danger')
        return redirect(url_for('technician.profile'))

    tech.set_password(new)
    db.session.commit()
    flash('Password updated successfully.', 'success')
    return redirect(url_for('technician.profile'))

@technician_bp.app_context_processor
def _tech_notif_count():
    from app import Notification
    uid = session.get('user_id')
    if session.get('role') != 'technician' or not uid:
        return {}
    return {'tech_unread': Notification.query.filter_by(user_role='technician', user_id=uid,
                                                        is_read=False).count()}

@technician_bp.route('/notifications')
@technician_required
def notifications():
    from app import Notification
    mine = Notification.query.filter_by(user_role='technician', user_id=session['user_id'])
    rows = mine.order_by(Notification.created_at.desc()).limit(50).all()
    mine.filter_by(is_read=False).update({'is_read': True})
    db.session.commit()
    return render_template('technician/notifications.html', rows=rows)