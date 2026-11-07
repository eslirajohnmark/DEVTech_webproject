"""Technician registration and identity verification.

Technicians have their own `technicians` table; the username column
holds the Tech ID they sign in with. Admins first record each hired
technician on the roster (TechnicianEmployee: Tech ID, name, birth date,
ID). A technician can only register with a roster Tech ID whose details
match the valid ID they upload. They then send a photo/scan of it, wait as 'pending' (and
inactive) until an admin approves, rejects or asks for a correction, and
can only take repair jobs once verified (Technician.can_take_jobs).

ID documents live in ID_UPLOAD_FOLDER under a random name, outside
static/, and are served only to admins and to the technician they belong
to. The ID number is never written to logs, notifications or events.
"""
import os
import re
import secrets
import unicodedata
from datetime import date, datetime

from flask import abort, current_app, send_file
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError

from app import (db, Technician, TechnicianVerificationEvent, TECH_VERIFICATION_STATUSES,
                 email_in_use, notify_admins, create_notification, _external_url)
from services.upload_service import check_file, strip_jpeg_metadata


TECH_ID_RE = re.compile(r'^TECH-\d{4}$')
EMAIL_RE   = re.compile(r'^[^\s@]+@[^\s@]+\.[^\s@]+$')
NAME_RE    = re.compile(r"^[A-Za-zÀ-ÖØ-öø-ÿ .,'-]+$")
PHONE_RE   = re.compile(r'^09\d{9}$')
ID_NUMBER_RE = re.compile(r'^[A-Z0-9][A-Z0-9 -]{3,49}$')

GENDERS = ('Male', 'Female', 'Other')
ID_TYPES = ('PhilSys National ID', "Driver's License", 'UMID', 'Passport', 'PRC ID',
            'Postal ID', "Voter's ID", 'SSS ID', 'PhilHealth ID', 'TIN ID')

ID_DOC_TYPES = {'image/jpeg', 'image/png', 'image/webp', 'application/pdf'}
ID_DOC_MAX_BYTES = 5 * 1024 * 1024
DOC_NAME_RE = re.compile(r'^[0-9a-f]{32}\.(jpg|png|webp|pdf)$')

# action: (new status, statuses it may come from, reason required, event action)
DECISIONS = {
    'approve':    ('verified', ('pending', 'needs_correction', 'rejected', 'suspended'), False, 'approved'),
    'reject':     ('rejected', ('pending', 'needs_correction'), True, 'rejected'),
    'correction': ('needs_correction', ('pending',), True, 'correction_requested'),
    'suspend':    ('suspended', ('verified',), True, 'suspended'),
}


# ---------------------------------------------------------------------------
# ID document storage
# ---------------------------------------------------------------------------

def check_id_document(file_storage):
    """Validate an uploaded ID: allowed type, size, content that matches the
    type. Returns (True, (data, mime, ext)) or (False, 'reason')."""
    if not file_storage or not file_storage.filename:
        return False, 'Upload a photo or scan of your ID.'
    if file_storage.mimetype not in ID_DOC_TYPES:
        return False, 'The ID must be a JPG, PNG or WEBP photo, or a PDF.'
    ok, checked = check_file(file_storage, max_bytes=ID_DOC_MAX_BYTES)
    if not ok:
        return False, checked
    data, mime, ext, _ = checked
    if mime == 'image/jpeg':
        data = strip_jpeg_metadata(data)
    return True, (data, mime, ext)


def _write_document(data, ext):
    folder = current_app.config['ID_UPLOAD_FOLDER']
    os.makedirs(folder, exist_ok=True)
    name = secrets.token_hex(16) + ext
    with open(os.path.join(folder, name), 'wb') as fh:
        fh.write(data)
    return name


def id_document_path(tech):
    """Absolute path of this technician's ID document, or None."""
    name = tech.id_document_file or ''
    if not DOC_NAME_RE.match(name):
        return None
    path = os.path.join(current_app.config['ID_UPLOAD_FOLDER'], name)
    return path if os.path.isfile(path) else None


def send_id_document(tech):
    """Response with the ID document, shown inline and never cached. The caller
    has already checked that the viewer may see it."""
    path = id_document_path(tech)
    if not path:
        abort(404)
    resp = send_file(path, mimetype=tech.id_document_mime, max_age=0,
                     download_name='id-document' + os.path.splitext(path)[1])
    resp.headers['Cache-Control'] = 'no-store, private'
    resp.headers['X-Content-Type-Options'] = 'nosniff'
    return resp


def delete_id_document(name):
    if name and DOC_NAME_RE.match(name):
        try:
            os.remove(os.path.join(current_app.config['ID_UPLOAD_FOLDER'], name))
        except FileNotFoundError:
            pass


# ---------------------------------------------------------------------------
# Certificates and achievements (shown to admins and the technician's customers)
# ---------------------------------------------------------------------------

MAX_CREDENTIALS = 12


def _credential_folder():
    return current_app.config['CREDENTIAL_UPLOAD_FOLDER']


def credential_path(cred):
    name = cred.file or ''
    if not DOC_NAME_RE.match(name):
        return None
    path = os.path.join(_credential_folder(), name)
    return path if os.path.isfile(path) else None


def delete_credential_file(name):
    if name and DOC_NAME_RE.match(name):
        try:
            os.remove(os.path.join(_credential_folder(), name))
        except FileNotFoundError:
            pass


def add_credential(tech, form, upload):
    """Validate and store one certificate/achievement. Returns (True, cred) or (False, reason)."""
    from app import TechnicianCredential
    title = ' '.join((form.get('title') or '').split())
    issuer = ' '.join((form.get('issuer') or '').split())
    if not 3 <= len(title) <= 120:
        return False, 'Give the certificate or achievement a title (3 to 120 characters).'
    if len(issuer) > 120:
        return False, 'The issuer name is too long (120 characters at most).'
    issued_on = None
    if form.get('issued_on'):
        try:
            issued_on = date.fromisoformat(form.get('issued_on'))
        except ValueError:
            return False, 'Enter a valid date.'
        if issued_on > date.today():
            return False, 'The date cannot be in the future.'
    if TechnicianCredential.query.filter_by(technician_id=tech.id).count() >= MAX_CREDENTIALS:
        return False, f'You can show up to {MAX_CREDENTIALS} certificates. Remove one to add another.'
    ok, doc = check_id_document(upload)       # same rules: JPG/PNG/WEBP/PDF, 5 MB, real content
    if not ok:
        return False, doc.replace('of your ID', 'of the certificate').replace('The ID', 'The file')
    data, mime, ext = doc
    os.makedirs(_credential_folder(), exist_ok=True)
    name = secrets.token_hex(16) + ext
    with open(os.path.join(_credential_folder(), name), 'wb') as fh:
        fh.write(data)
    cred = TechnicianCredential(technician_id=tech.id, title=title, issuer=issuer or None,
                                issued_on=issued_on, file=name, mime=mime)
    db.session.add(cred)
    db.session.commit()
    return True, cred


def can_view_credential(viewer, cred):
    """Admins, the technician themselves, and customers with a job assigned to them."""
    from app import Booking
    if not viewer:
        return False
    if viewer.role == 'admin':
        return True
    if viewer.role == 'technician':
        return viewer.id == cred.technician_id
    return db.session.query(Booking.query.filter_by(user_id=viewer.id,
                                                    technician_id=cred.technician_id).exists()).scalar()


# ---------------------------------------------------------------------------
# Registration details
# ---------------------------------------------------------------------------

def registration_details(tech):
    """The saved details of an existing technician, in the form's field names."""
    return {'fullname': tech.full_name, 'email': tech.email, 'phone': tech.phone or '',
            'gender': tech.gender or '', 'dob': tech.birth_date.isoformat() if tech.birth_date else '',
            'id_type': tech.id_type or '', 'id_number': tech.id_number or ''}


def _id_number_taken(id_type, id_number, exclude_id=None):
    """Same document (type + number, ignoring spaces and dashes) on another technician."""
    plain = re.sub(r'[\s-]', '', id_number)
    stored = func.upper(func.replace(func.replace(Technician.id_number, '-', ''), ' ', ''))
    q = Technician.query.filter(Technician.id_type == id_type, stored == plain)
    if exclude_id:
        q = q.filter(Technician.id != exclude_id)
    return db.session.query(q.exists()).scalar()


def _validate_details(form, tech=None):
    """Personal and ID details shared by registration and resubmission.
    Returns (values, errors) where errors maps field name -> message."""
    v = {
        'fullname': ' '.join((form.get('fullname') or '').split()),
        'email': (form.get('email') or '').strip().lower(),
        'phone': re.sub(r'[\s()-]', '', form.get('phone') or ''),
        'gender': (form.get('gender') or '').strip().capitalize(),
        'dob': (form.get('dob') or '').strip(),
        'id_type': (form.get('id_type') or '').strip(),
        'id_number': ' '.join((form.get('id_number') or '').split()).upper(),
    }
    if v['phone'].startswith('+63'):
        v['phone'] = '0' + v['phone'][3:]
    errors = {}
    if len(v['fullname'].split()) < 2 or len(v['fullname']) > 100 or not NAME_RE.match(v['fullname']):
        errors['fullname'] = 'Enter your full name as it appears on your ID.'
    if not EMAIL_RE.match(v['email']) or len(v['email']) > 120:
        errors['email'] = 'Enter a valid email address.'
    elif email_in_use(v['email'], exclude=tech):
        errors['email'] = 'That email is already registered.'
    if not PHONE_RE.match(v['phone']):
        errors['phone'] = 'Enter a mobile number like 09171234567.'
    if v['gender'] not in GENDERS:
        errors['gender'] = 'Select a gender.'
    try:
        born = date.fromisoformat(v['dob'])
        today = date.today()
        age = today.year - born.year - ((today.month, today.day) < (born.month, born.day))
        if not 18 <= age <= 100:
            errors['dob'] = 'You must be at least 18 years old.'
        v['birth_date'] = born
    except ValueError:
        errors['dob'] = 'Enter your date of birth.'
    if v['id_type'] not in ID_TYPES:
        errors['id_type'] = 'Choose the type of ID you are uploading.'
    if not ID_NUMBER_RE.match(v['id_number']):
        errors['id_number'] = 'Enter the ID number exactly as printed (letters, numbers, spaces, dashes).'
    elif 'id_type' not in errors and _id_number_taken(v['id_type'], v['id_number'], tech.id if tech else None):
        errors['id_number'] = 'This ID is already linked to another technician account.'
    return v, errors


def _add_event(tech, action, actor, reason=None, admin=None):
    db.session.add(TechnicianVerificationEvent(
        technician_id=tech.id, action=action, status=tech.verification_status,
        reason=reason, admin_id=admin.id if admin else None, actor=actor[:120]))


# ---------------------------------------------------------------------------
# Employee roster: only hired technicians (added by an admin) can register
# ---------------------------------------------------------------------------

NO_MATCH = ("We couldn't match these details to a DEVTech employee record. Check that your Tech ID, "
            "full name, date of birth, ID type and ID number are exactly as printed on your ID, "
            "or ask the DEVTech admin who hired you.")
MATCH_FIELDS = ('fullname', 'dob', 'id_type', 'id_number')


def _plain_name(name):
    """'TAGAÑA-ESLIRA, John  Mark' -> 'tagana eslira john mark' (accents, case, punctuation ignored)."""
    text = unicodedata.normalize('NFKD', name or '')
    text = ''.join(ch for ch in text if not unicodedata.combining(ch)).casefold()
    return ' '.join(re.sub(r'[^a-z ]', ' ', text).split())


def _plain_id(number):
    return re.sub(r'[\s-]', '', number or '').upper()


def employee_matches(record, values):
    """Do the details typed (or read from the ID's QR code) match the employee record?"""
    return (_plain_name(record.full_name) == _plain_name(values.get('fullname'))
            and record.birth_date == values.get('birth_date')
            and record.id_type == values.get('id_type')
            and _plain_id(record.id_number) == _plain_id(values.get('id_number')))


def save_employee(form, admin_name, record=None):
    """Add or edit an employee record from the admin form. Once the technician
    has registered, only the hire date and note can change (their account was
    matched against the rest). Returns (True, record) or (False, {field: message})."""
    from app import TechnicianEmployee
    registered = bool(record and record.technician_id)
    errors, v = {}, {}
    if not registered:
        v['tech_id'] = (form.get('tech_id') or '').strip().upper()
        v['full_name'] = ' '.join((form.get('full_name') or '').split())
        v['id_type'] = (form.get('id_type') or '').strip()
        v['id_number'] = ' '.join((form.get('id_number') or '').split()).upper()
        if not TECH_ID_RE.match(v['tech_id']):
            errors['tech_id'] = 'Tech ID must look like TECH-0001.'
        else:
            clash = TechnicianEmployee.query.filter(func.upper(TechnicianEmployee.tech_id) == v['tech_id'])
            if record:
                clash = clash.filter(TechnicianEmployee.id != record.id)
            if clash.first() or Technician.query.filter(func.upper(Technician.username) == v['tech_id']).first():
                errors['tech_id'] = 'That Tech ID is already in use.'
        if len(v['full_name'].split()) < 2 or len(v['full_name']) > 100 or not NAME_RE.match(v['full_name']):
            errors['full_name'] = 'Enter the full name exactly as printed on their ID.'
        try:
            v['birth_date'] = date.fromisoformat((form.get('birth_date') or '').strip())
            today = date.today()
            age = today.year - v['birth_date'].year - \
                ((today.month, today.day) < (v['birth_date'].month, v['birth_date'].day))
            if not 18 <= age <= 100:
                errors['birth_date'] = 'Technicians must be at least 18 years old.'
        except ValueError:
            errors['birth_date'] = 'Enter their date of birth.'
        if v['id_type'] not in ID_TYPES:
            errors['id_type'] = 'Choose the type of ID.'
        if not ID_NUMBER_RE.match(v['id_number']):
            errors['id_number'] = 'Enter the ID number exactly as printed (letters, numbers, spaces, dashes).'
        elif 'id_type' not in errors:
            same = [e for e in TechnicianEmployee.query.filter_by(id_type=v['id_type']).all()
                    if _plain_id(e.id_number) == _plain_id(v['id_number']) and (not record or e.id != record.id)]
            if same or _id_number_taken(v['id_type'], v['id_number']):
                errors['id_number'] = 'This ID is already recorded for another technician.'
    v['note'] = ' '.join((form.get('note') or '').split())[:255] or None
    v['hired_on'] = None
    if form.get('hired_on'):
        try:
            v['hired_on'] = date.fromisoformat(form.get('hired_on'))
            if v['hired_on'] > date.today():
                errors['hired_on'] = 'The hire date cannot be in the future.'
        except ValueError:
            errors['hired_on'] = 'Enter a valid date.'
    if errors:
        return False, errors
    if record is None:
        record = TechnicianEmployee(created_by=admin_name)
        db.session.add(record)
    for field, value in v.items():
        setattr(record, field, value)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return False, {'tech_id': 'That Tech ID was just used. Try another.'}
    return True, record


def register_technician(form, files):
    """Validate and register a new technician with their ID document.

    Returns {'ok': True, 'technician_id': 'TECH-0042'} on success,
    or {'ok': False, 'errors': {field: message}} on failure.
    """
    values, errors = _validate_details(form)
    staff_id = (form.get('staffId') or '').strip().upper()
    password = form.get('password') or ''
    record = None
    if not TECH_ID_RE.match(staff_id):
        errors['staffId'] = 'Tech ID must look like TECH-0001.'
    elif not any(f in errors for f in MATCH_FIELDS):
        # The Tech ID must be on the roster and the ID details must match it.
        # One message for "no such Tech ID" and "details differ", so the form
        # can't be used to find out who works here.
        from app import TechnicianEmployee
        record = TechnicianEmployee.query.filter(func.upper(TechnicianEmployee.tech_id) == staff_id).first()
        if not record or not employee_matches(record, values):
            errors['staffId'] = "These details don't match a DEVTech employee record."
            errors['form'] = NO_MATCH
        elif record.technician_id or Technician.query.filter(func.upper(Technician.username) == staff_id).first():
            errors['staffId'] = 'This Tech ID already has an account.'
            errors['form'] = 'This Tech ID already has an account. Sign in, or check your registration status.'
    if (len(password) < 8
            or not re.search(r'[A-Za-z]', password)
            or not re.search(r'\d', password)):
        errors['password'] = 'Password must be 8+ characters with a letter and a number.'
    elif password != (form.get('password2') or ''):
        errors['password2'] = 'The passwords do not match.'
    if not form.get('privacy_consent'):
        errors['privacy_consent'] = 'You must agree to how your ID is used before registering.'
    ok, doc = check_id_document(files.get('id_document'))
    if not ok:
        errors['id_document'] = doc
    if errors:
        return {'ok': False, 'errors': errors}

    data, mime, ext = doc
    stored = _write_document(data, ext)
    user = Technician(
        username=record.tech_id, email=values['email'], full_name=record.full_name,
        phone=values['phone'], gender=values['gender'], birth_date=values['birth_date'],
        id_type=values['id_type'], id_number=values['id_number'],
        id_document_file=stored, id_document_mime=mime,
        # Stays inactive (cannot sign in) until an admin approves the ID.
        is_active=False, id_verified=False, verification_status='pending',
        verification_submitted_at=datetime.utcnow(),
    )
    user.set_password(password)
    db.session.add(user)
    try:
        db.session.flush()
        record.technician_id, record.registered_at = user.id, datetime.utcnow()
        _add_event(user, 'submitted', staff_id)
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        delete_id_document(stored)
        return {'ok': False, 'errors': {'staffId': 'That Tech ID or email was just registered. Try another.'}}

    notify_admins('Technician Awaiting Verification',
                  f'{user.full_name} ({staff_id}) registered and sent an ID for verification. '
                  'Review it in Technician Verification.', 'warning')
    return {'ok': True, 'technician_id': staff_id}


def can_resubmit(tech):
    """A technician may send new details when an admin asked for a correction,
    or when they have never sent an ID (accounts an admin created)."""
    return (tech.verification_status == 'needs_correction'
            or (tech.verification_status == 'pending' and not tech.id_document_file))


def resubmit_registration(tech, form, files):
    """Corrected details and/or a new ID from an existing technician. The Tech ID,
    password and verification status can't be changed here. Same return shape
    as register_technician."""
    if not can_resubmit(tech):
        return {'ok': False, 'errors': {'form': 'Your registration cannot be changed right now.'}}
    values, errors = _validate_details(form, tech=tech)
    record = tech.employee_record
    if record and not any(f in errors for f in MATCH_FIELDS) and not employee_matches(record, values):
        errors['form'] = ("These details don't match your DEVTech employee record. Enter your name, "
                          "date of birth and ID exactly as printed on your ID, or ask the admin.")
    upload = files.get('id_document')
    doc = None
    if upload and upload.filename:
        ok, doc = check_id_document(upload)
        if not ok:
            errors['id_document'] = doc
    elif not id_document_path(tech):
        errors['id_document'] = 'Upload a photo or scan of your ID.'
    if errors:
        return {'ok': False, 'errors': errors}

    old_file = None
    if doc:
        data, mime, ext = doc
        old_file = tech.id_document_file
        tech.id_document_file, tech.id_document_mime = _write_document(data, ext), mime
    first_time = tech.verification_submitted_at is None
    tech.full_name = record.full_name if record else values['fullname']
    tech.email, tech.phone = values['email'], values['phone']
    tech.gender, tech.birth_date = values['gender'], values['birth_date']
    tech.id_type, tech.id_number = values['id_type'], values['id_number']
    tech.verification_status, tech.verification_reason = 'pending', None
    tech.id_verified = False
    tech.verification_submitted_at = datetime.utcnow()
    _add_event(tech, 'submitted' if first_time else 'resubmitted', tech.username)
    db.session.commit()
    delete_id_document(old_file)

    notify_admins('Technician Registration Updated' if not first_time else 'Technician Awaiting Verification',
                  f'{tech.full_name} ({tech.username}) sent '
                  f'{"an ID" if first_time else "corrected details"} for verification. '
                  'Review it in Technician Verification.', 'warning')
    return {'ok': True, 'technician_id': tech.username}


# ---------------------------------------------------------------------------
# Admin decisions
# ---------------------------------------------------------------------------

def decide_verification(tech, action, admin, reason='', expected=None, require_document=True):
    """Approve, reject, request a correction for, or suspend a technician's
    verification. `expected` is the status the admin was looking at; if it
    changed meanwhile nothing is saved. Commits and notifies the technician.
    Returns (True, message) or (False, error)."""
    if action not in DECISIONS:
        return False, 'Unknown action.'
    status, allowed_from, needs_reason, event_action = DECISIONS[action]
    current = expected or tech.verification_status
    reason = ' '.join((reason or '').split())[:500]
    if current not in allowed_from:
        return False, f'A registration that is {TECH_VERIFICATION_STATUSES.get(current, current)} cannot be changed that way.'
    if needs_reason and len(reason) < 5:
        return False, 'Give a reason of at least 5 characters. The technician will see it.'
    if action == 'approve' and require_document and not id_document_path(tech):
        return False, 'There is no ID document on file to check, so this registration cannot be approved here.'
    if action == 'approve' and not (tech.id_type and tech.id_number):
        return False, 'The ID type and number are missing, so this registration cannot be approved.'

    now = datetime.utcnow()
    values = {'verification_status': status, 'verification_reason': reason or None,
              'verification_decided_at': now, 'verified_by_admin_id': admin.id,
              'id_verified': status == 'verified', 'updated_at': now}
    if status == 'verified':
        values.update(id_verified_at=now, is_active=True)
    elif status == 'rejected':
        values['is_active'] = False
    # Conditional UPDATE: two admins (or a double click) can't both decide.
    claimed = Technician.query.filter_by(id=tech.id, verification_status=current)\
        .update(values, synchronize_session=False)
    if not claimed:
        db.session.rollback()
        return False, 'This registration was changed while you were reviewing it. Reload and try again.'
    db.session.refresh(tech)
    _add_event(tech, event_action, admin.full_name, reason or None, admin)
    db.session.commit()

    status_url = _external_url('technician.registration_status')
    if status == 'verified':
        create_notification(tech.id, 'Registration Approved',
                            'Your identity has been verified and your technician account is active. '
                            'You can now sign in and be assigned to repair jobs.', 'success', role='technician')
        return True, f'{tech.full_name} is verified and can now be assigned to jobs.'
    if status == 'rejected':
        create_notification(tech.id, 'Registration Not Approved',
                            f'Your technician registration was not approved.\n\nReason: {reason}',
                            'error', role='technician')
        return True, f"{tech.full_name}'s registration was rejected."
    if status == 'needs_correction':
        create_notification(tech.id, 'Correction Needed',
                            f'An administrator asked you to correct your registration.\n\nWhat to fix: {reason}\n\n'
                            f'Open {status_url or "the registration status page"} and sign in with your Tech ID '
                            'and password to update it.', 'warning', role='technician')
        return True, f'{tech.full_name} was asked to correct their registration.'
    create_notification(tech.id, 'Verification Suspended',
                        'Your identity verification has been suspended, so you will not be assigned new jobs. '
                        f'Jobs already assigned to you stay with you.\n\nReason: {reason}', 'warning', role='technician')
    return True, f'{tech.full_name} is suspended and will not get new jobs.'
