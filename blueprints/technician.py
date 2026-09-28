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

from app import db, User, Booking


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
    return render_template('technician/dashboard.html')


@technician_bp.route('/jobs')
@technician_required
def my_jobs():
    return render_template('technician/my_jobs.html')


@technician_bp.route('/jobs/<int:job_id>')
@technician_required
def job_detail(job_id):
    booking = Booking.query.get_or_404(job_id)
    if booking.technician_id != session['user_id']:
        abort(403)
    return render_template('technician/job_detail.html', job_id=job_id)


@technician_bp.route('/intake')
@technician_required
def intake_picker():
    return render_template('technician/device_intake.html', current=None)


@technician_bp.route('/intake/<int:job_id>')
@technician_required
def intake_form(job_id):
    booking = Booking.query.get_or_404(job_id)
    if booking.technician_id != session['user_id']:
        abort(403)
    return render_template('technician/device_intake.html', current=job_id)


@technician_bp.route('/reports')
@technician_required
def reports_picker():
    return render_template('technician/service_report.html', current=None)


@technician_bp.route('/reports/new/<int:job_id>')
@technician_required
def report_form(job_id):
    booking = Booking.query.get_or_404(job_id)
    if booking.technician_id != session['user_id']:
        abort(403)
    return render_template('technician/service_report.html', current=job_id)


@technician_bp.route('/incidents')
@technician_required
def incidents():
    return render_template('technician/incident_report.html',
                           prefill_job=request.args.get('job'))


@technician_bp.route('/messages')
@technician_required
def messages():
    return render_template('technician/messages.html',
                           active_thread=request.args.get('thread'))


@technician_bp.route('/messages/<thread_id>')
@technician_required
def message_thread(thread_id):
    return render_template('technician/messages.html',
                           active_thread=thread_id)


@technician_bp.route('/profile')
@technician_required
def profile():
    return render_template('technician/profile.html')