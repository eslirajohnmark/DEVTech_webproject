"""Technician portal — server-rendered pages.

A technician is a `User` row with role='technician'; a job they work
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
from app import db, User, Booking
from models.technician_models import (
    IntakeRecord, ServiceReport, IncidentReport, JobLog,
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
        user = User.query.get(session['user_id'])
        if not user or user.role != 'technician' or not user.is_active:
            session.clear()
            flash('Technician access required.', 'danger')
            return redirect(url_for('technician.login'))
        return fn(*args, **kwargs)
    return wrapper


# ---------------------------------------------------------------------------
# AUTH
# ---------------------------------------------------------------------------

@technician_bp.route('/login', methods=['GET', 'POST'])
def login():
    if session.get('user_id'):
        u = User.query.get(session['user_id'])
        if u and u.role == 'technician':
            return redirect(url_for('technician.dashboard'))

    if request.method == 'POST':
        tech_id  = (request.form.get('technician_id') or '').strip().upper()
        password = request.form.get('password') or ''

        user = User.query.filter_by(
            username=tech_id, role='technician').first()
        if not user or not user.check_password(password):
            flash('Incorrect Tech ID or password.', 'danger')
            return render_template('technician/login.html',
                                   prefill_id=tech_id), 401

        if not user.is_active:
            flash('This technician account has been deactivated.', 'danger')
            return render_template('technician/login.html',
                                   prefill_id=tech_id), 403

        session['user_id']  = user.id
        session['username'] = user.username
        session['role']     = 'technician'
        user.last_active    = datetime.utcnow()
        db.session.commit()
        return redirect(url_for('technician.dashboard'))

    return render_template('technician/login.html',
                           prefill_id=request.args.get('registered', ''))


@technician_bp.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        from services.technician_service import register_technician
        result = register_technician(request.form)
        if not result['ok']:
            flash(result['reason'], 'danger')
            return render_template('technician/registration.html',
                                   form=request.form), 400
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
    technician = User.query.get(tid)

    all_jobs = Booking.query.filter_by(technician_id=tid)\
        .order_by(Booking.created_at.desc()).all()
    
    total = sum(1 for j in all_jobs if j.status in ())
    on_repair = sum(1 for j in all_jobs if j.status in ('diagnosis_pending', 'in_progress'))
    ready     = sum(1 for j in all_jobs if j.status == 'completed')
    released  = sum(1 for j in all_jobs if j.status == 'released')
    active    = [j for j in all_jobs if j.status in ACTIVE_STATUSES]

    today = datetime.utcnow().date()
    todays_jobs = [j for j in all_jobs if j.booking_date == today]

    return render_template('technician/dashboard.html',
                           technician=technician,
                           total=total, on_repair=on_repair, ready=ready,
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
    return render_template('technician/job_detail.html',
                           job=booking, intake=intake, report=report, logs=logs)


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

@technician_bp.route('/messages')
@technician_required
def messages():
    from app import Message, or_, and_
    from app import create_notification 
    create_notification(other_user_id, 'New Message',
    f'You have a new message from {User.query.get(tid).full_name}', 'info')
    
    tid = session['user_id']

    sent_to = db.session.query(Message.recipient_id)\
        .filter_by(sender_id=tid).distinct().all()
    received_from = db.session.query(Message.sender_id)\
        .filter_by(recipient_id=tid).distinct().all()
    other_ids = {r[0] for r in sent_to} | {r[0] for r in received_from}

    conversations = []
    for other_id in other_ids:
        other = User.query.get(other_id)
        if not other:
            continue

        latest = Message.query.filter(
            or_(
                and_(Message.sender_id == tid, Message.recipient_id == other_id),
                and_(Message.sender_id == other_id, Message.recipient_id == tid),
            )
        ).order_by(Message.created_at.desc()).first()

        unread = Message.query.filter_by(
            sender_id=other_id, recipient_id=tid, is_read=False
        ).count()

        initials = ''.join(
            w[0] for w in (other.full_name or '?').split()[:2]
        ).upper() or '?'

        conversations.append({
            'other_user_id': other_id,
            'name': other.full_name,
            'initials': initials,
            'role_label': 'Administrator' if other.role == 'admin' else 'Customer',
            'last_message': latest.content if latest else 'No messages yet',
            'last_time': latest.created_at.strftime('%b %d, %I:%M %p')
                         if latest else '',
            'unread_count': unread,
            'is_active': False,
        })

    conversations.sort(key=lambda c: c['last_time'], reverse=True)

    thread_param = request.args.get('thread')
    active_thread = None
    thread_messages = []

    if thread_param:
        try:
            other_id = int(thread_param)
        except ValueError:
            other_id = None

        if other_id:
            other = User.query.get(other_id)
            if other:
                Message.query.filter_by(
                    sender_id=other_id, recipient_id=tid, is_read=False
                ).update({'is_read': True})
                db.session.commit()

                for c in conversations:
                    if c['other_user_id'] == other_id:
                        c['is_active'] = True
                        active_thread = c
                        break

                if not active_thread:
                    initials = ''.join(
                        w[0] for w in (other.full_name or '?').split()[:2]
                    ).upper() or '?'
                    active_thread = {
                        'other_user_id': other_id,
                        'name': other.full_name,
                        'initials': initials,
                        'role_label': 'Administrator' if other.role == 'admin' else 'Customer',
                        'job_id': None,
                        'job_number': None,
                    }

                rows = Message.query.filter(
                    or_(
                        and_(Message.sender_id == tid, Message.recipient_id == other_id),
                        and_(Message.sender_id == other_id, Message.recipient_id == tid),
                    )
                ).order_by(Message.created_at.asc()).all()

                thread_messages = [{
                    'content': m.content,
                    'created_at': m.created_at.strftime('%b %d, %I:%M %p'),
                    'is_sent': m.sender_id == tid,
                } for m in rows]

    return render_template('technician/messages.html',
                           conversations=conversations,
                           active_thread=active_thread,
                           thread_messages=thread_messages)


@technician_bp.route('/messages/<int:other_user_id>/send', methods=['POST'])
@technician_required
def message_send(other_user_id):
    from app import Message

    tid = session['user_id']
    content = (request.form.get('content') or '').strip()

    if not content:
        flash('Message cannot be empty.', 'danger')
        return redirect(url_for('technician.messages', thread=other_user_id))

    if not User.query.get(other_user_id):
        abort(404)

    db.session.add(Message(
        sender_id=tid, recipient_id=other_user_id,
        content=content, is_read=False,
    ))
    db.session.commit()

    return redirect(url_for('technician.messages', thread=other_user_id))


# ---------------------------------------------------------------------------
# PROFILE
# ---------------------------------------------------------------------------

@technician_bp.route('/profile')
@technician_required
def profile():
    tid = session['user_id']
    tech = User.query.get(tid)
    
    stats['active']   = Booking.query.filter_by(technician_id=tid)\
        .filter(Booking.status.notin_(FINISHED_STATUSES + ['cancelled'])).count()
    stats['released'] = Booking.query.filter(Booking.technician_id == tid, 
                                             Booking.status.in_(FINISHED_STATUSES)).count() 
    rating, rating_count = technician_rating(tid)   # pass to template, show as a chip

    stats = {
        'total':        Booking.query.filter_by(technician_id=tid).count(),
        'active':       Booking.query.filter_by(technician_id=tid)
                        .filter(Booking.status.notin_(['completed', 'cancelled']))
                        .count(),
        'released':     Booking.query.filter_by(technician_id=tid,
                                                status='completed').count(),
        'home_service': Booking.query.filter_by(technician_id=tid,
                                                is_in_shop=False).count(),
    }

    return render_template('technician/profile.html', tech=tech, stats=stats)


@technician_bp.route('/profile/password', methods=['POST'])
@technician_required
def change_password():
    tid = session['user_id']
    tech = User.query.get(tid)

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
    return {'tech_unread': Notification.query.filter_by(user_id=uid, is_read=False).count()}

@technician_bp.route('/notifications')
@technician_required
def notifications():
    from app import Notification
    rows = Notification.query.filter_by(user_id=session['user_id'])\
        .order_by(Notification.created_at.desc()).limit(50).all()
    Notification.query.filter_by(user_id=session['user_id'], is_read=False).update({'is_read': True})
    db.session.commit()
    return render_template('technician/notifications.html', rows=rows)