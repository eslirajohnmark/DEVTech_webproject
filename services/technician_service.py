"""Technician registration.

Uses the existing User model — a technician is a User row with
role='technician' whose username doubles as their login ID. No
separate Technician table exists.
"""
import re
from app import db, User


TECH_ID_RE = re.compile(r'^TECH-\d{4}$')
EMAIL_RE   = re.compile(r'^[^\s@]+@[^\s@]+\.[^\s@]+$')


def register_technician(form):
    """Validate and register a new technician.

    Accepts a Werkzeug MultiDict (form data from a POST) or a plain
    dict with the same keys.

    Returns {'ok': True, 'technician_id': 'TECH-0042'} on success,
    or {'ok': False, 'reason': '...'} on failure.
    """
    full_name = (form.get('fullname') or '').strip()
    email     = (form.get('email') or '').strip().lower()
    staff_id  = (form.get('staffId') or '').strip().upper()
    password  = form.get('password') or ''
    gender    = form.get('gender') or ''
    dob       = form.get('dob') or ''

    errors = []
    if len(full_name.split()) < 2:
        errors.append('Enter your complete name.')
    if not EMAIL_RE.match(email):
        errors.append('Enter a valid email address.')
    if not TECH_ID_RE.match(staff_id):
        errors.append('Tech ID must look like TECH-0001.')
    if not gender:
        errors.append('Select a gender.')
    if not dob:
        errors.append('Enter your date of birth.')
    if (len(password) < 8
            or not re.search(r'[A-Za-z]', password)
            or not re.search(r'\d', password)):
        errors.append('Password must be 8+ characters with a letter and a number.')

    if errors:
        return {'ok': False, 'reason': errors[0]}

    if User.query.filter_by(username=staff_id).first():
        return {'ok': False, 'reason': 'That Tech ID is already registered.'}
    if User.query.filter_by(email=email).first():
        return {'ok': False, 'reason': 'That email is already registered.'}

    user = User(
        username=staff_id,
        email=email,
        full_name=full_name,
        role='technician',
        is_active=True,
    )
    user.set_password(password)
    db.session.add(user)
    db.session.commit()

    return {'ok': True, 'technician_id': staff_id}