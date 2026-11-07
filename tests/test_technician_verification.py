"""Technician registration with an ID document, the admin verification
workflow, and the rule that only verified technicians get new jobs.
All IDs here are made up."""
import os
from datetime import date, time
from io import BytesIO

from app import (app as flask_app, db, Technician, Notification, Booking, Service, ServiceCategory,
                 ActivityLog, TechnicianVerificationEvent, TechnicianEmployee)
from services.upload_service import strip_jpeg_metadata
from tests.conftest import login_as

PNG = b'\x89PNG\r\n\x1a\n' + b'\0' * 64
PASSWORD = 'secretpass1'


def jpeg_with_location():
    app0 = b'\xff\xe0' + (16).to_bytes(2, 'big') + b'JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00'
    exif_body = b'Exif\x00\x00GPS-SECRET-LOCATION'
    app1 = b'\xff\xe1' + (len(exif_body) + 2).to_bytes(2, 'big') + exif_body
    scan = b'\xff\xda\x00\x08\x01\x01\x00\x00\x3f\x00' + b'imagedata' + b'\xff\xd9'
    return b'\xff\xd8' + app0 + app1 + scan


def form(**over):
    data = {'fullname': 'Maria Santos Cruz', 'email': 'maria@test.local', 'phone': '0917 123 4567',
            'gender': 'Female', 'dob': '1995-05-20', 'id_type': 'UMID', 'id_number': 'CRN-0111-2222-3333',
            'staffId': 'TECH-0042', 'password': PASSWORD, 'password2': PASSWORD, 'privacy_consent': '1',
            'id_document': (BytesIO(PNG), 'my id.png', 'image/png')}
    data.update(over)
    return {k: v for k, v in data.items() if v is not None}


# What the admin recorded on the Technician Roster when hiring the test technician.
HIRED = {'fullname': 'Maria Santos Cruz', 'dob': '1995-05-20', 'id_type': 'UMID', 'id_number': 'CRN-0111-2222-3333'}


def hire(tech_id='TECH-0042', **over):
    d = dict(HIRED, **over)
    if not TechnicianEmployee.query.filter_by(tech_id=tech_id).first():
        db.session.add(TechnicianEmployee(tech_id=tech_id, full_name=d['fullname'], birth_date=date.fromisoformat(d['dob']),
                                          id_type=d['id_type'], id_number=d['id_number']))
        db.session.commit()


def register(client, hired=True, **over):
    """Submit the registration form; by default the Tech ID is on the roster with HIRED's details."""
    if hired:
        hire(over.get('staffId', 'TECH-0042'))
    return client.post('/technician/register', data=form(**over), content_type='multipart/form-data')


def new_tech(username='TECH-0042'):
    return Technician.query.filter_by(username=username).first()


def id_files():
    folder = flask_app.config['ID_UPLOAD_FOLDER']
    return sorted(os.listdir(folder)) if os.path.isdir(folder) else []


def decide(client, tech, action, reason='', expected=None):
    return client.post(f'/admin/technician-verification/{tech.id}/decide',
                       data={'action': action, 'reason': reason, 'expected': expected or tech.verification_status})


def admin_client(admin):
    return login_as(flask_app.test_client(), admin)


def status_check(client, username='TECH-0042', password=PASSWORD):
    return client.post('/technician/register/status', data={'technician_id': username, 'password': password})


# ---- registration --------------------------------------------------------------

def test_registration_saves_a_pending_inactive_account_with_a_private_document(client, admin):
    r = register(client)
    assert r.status_code == 302
    t = new_tech()
    assert (t.is_active, t.id_verified, t.verification_status) == (False, False, 'pending')
    assert (t.gender, t.birth_date, t.phone) == ('Female', date(1995, 5, 20), '09171234567')
    assert t.check_password(PASSWORD) and PASSWORD not in t.password_hash
    assert t.verification_submitted_at is not None
    # stored under a random name in the private folder, not static/
    assert id_files() == [t.id_document_file] and t.id_document_file != 'my id.png'
    assert not os.path.abspath(flask_app.config['ID_UPLOAD_FOLDER']).startswith(os.path.abspath('static'))
    assert [e.action for e in t.verification_events] == ['submitted']
    note = Notification.query.filter_by(user_role='admin', user_id=admin.id).one()
    assert 'TECH-0042' in note.message and t.id_number not in note.message


def test_registration_reports_every_invalid_field(client):
    r = register(client, fullname='Maria', phone='12345', dob='2015-01-01', password2='different1',
                 privacy_consent=None, id_type='Library card')
    assert r.status_code == 400
    html = r.get_data(as_text=True)
    for message in ('Enter your full name', 'mobile number like', 'at least 18 years',
                    'passwords do not match', 'must agree', 'Choose the type of ID'):
        assert message in html
    assert Technician.query.count() == 0 and id_files() == []


def test_duplicate_tech_id_email_and_id_number_are_refused(client, technician):
    assert 'already has an account' in register(client, staffId='TECH-0001').get_data(as_text=True)
    assert 'already registered' in register(client, email='tech@test.local').get_data(as_text=True)
    assert register(client).status_code == 302
    # the same ID written differently, by someone else
    r = register(client, staffId='TECH-0043', email='other@test.local', id_number='crn 0111 2222 3333')
    assert r.status_code == 400 and 'already linked to another technician' in r.get_data(as_text=True)
    assert Technician.query.count() == 2


def test_bad_id_uploads_are_refused(client):
    cases = [
        (None, 'Upload a photo or scan'),
        ((BytesIO(b'just some text'), 'id.png', 'image/png'), 'does not match its type'),
        ((BytesIO(b'MZ\x90\x00'), 'id.exe', 'application/octet-stream'), 'must be a JPG, PNG or WEBP'),
        ((BytesIO(PNG + b'0' * (5 * 1024 * 1024)), 'big.png', 'image/png'), 'larger than 5 MB'),
    ]
    for upload, message in cases:
        r = register(client, id_document=upload)
        assert r.status_code == 400 and message in r.get_data(as_text=True), message
    assert Technician.query.count() == 0 and id_files() == []


def test_location_data_is_removed_from_jpeg_photos(client):
    register(client, id_document=(BytesIO(jpeg_with_location()), 'id.jpg', 'image/jpeg'))
    stored = open(os.path.join(flask_app.config['ID_UPLOAD_FOLDER'], new_tech().id_document_file), 'rb').read()
    assert b'GPS-SECRET' not in stored and b'imagedata' in stored and stored.startswith(b'\xff\xd8')
    assert strip_jpeg_metadata(b'not a jpeg') == b'not a jpeg'


# ---- who can see the ID ----------------------------------------------------------

def test_only_admins_and_the_owner_can_open_the_id(client, admin, customer, technician):
    register(client)
    t = new_tech()
    url = f'/admin/technician-verification/{t.id}/document'
    assert flask_app.test_client().get(url).status_code != 200                         # anonymous
    assert login_as(flask_app.test_client(), customer).get(url).status_code != 200      # customer
    other = login_as(flask_app.test_client(), technician)                              # another technician
    assert other.get(url).status_code != 200
    assert other.get('/technician/register/status/document').status_code == 404        # only their own (none)
    assert flask_app.test_client().get('/technician/register/status/document').status_code == 403

    r = admin_client(admin).get(url)
    assert r.status_code == 200 and r.data == PNG
    assert 'no-store' in r.headers['Cache-Control'] and r.headers['X-Content-Type-Options'] == 'nosniff'
    assert ActivityLog.query.filter_by(action='id_document_view').count() == 1

    owner = flask_app.test_client()
    assert status_check(owner, password='wrong-password').status_code == 401
    assert owner.get('/technician/register/status/document').status_code == 403
    assert status_check(owner).status_code == 302
    assert owner.get('/technician/register/status/document').data == PNG


# ---- admin decisions --------------------------------------------------------------

def test_approval_activates_and_lets_the_technician_sign_in(client, admin):
    register(client)
    t = new_tech()
    assert decide(admin_client(admin), t, 'approve').status_code == 302
    t = new_tech()
    assert (t.verification_status, t.is_active, t.id_verified, t.can_take_jobs) == ('verified', True, True, True)
    assert t.verification_decided_at and t.id_verified_at and t.verified_by_admin_id == admin.id
    assert t.verification_events[0].action == 'approved' and t.verification_events[0].admin_id == admin.id
    assert Notification.query.filter_by(user_role='technician', user_id=t.id, title='Registration Approved').count() == 1
    r = client.post('/technician/login', data={'technician_id': 'TECH-0042', 'password': PASSWORD})
    assert r.status_code == 302 and r.headers['Location'].endswith('/technician/dashboard')


def test_rejection_needs_a_reason_and_the_technician_sees_it(client, admin):
    register(client)
    t = new_tech()
    a = admin_client(admin)
    decide(a, t, 'reject', reason='')
    assert new_tech().verification_status == 'pending'
    decide(a, new_tech(), 'reject', reason='The ID photo does not match the name given')
    t = new_tech()
    assert (t.verification_status, t.is_active, t.id_verified) == ('rejected', False, False)
    note = Notification.query.filter_by(user_role='technician', user_id=t.id).one()
    assert 'does not match the name' in note.message
    r = client.post('/technician/login', data={'technician_id': 'TECH-0042', 'password': PASSWORD})
    assert r.status_code == 403 and 'does not match the name' in r.get_data(as_text=True)


def test_correction_request_and_resubmission(client, admin):
    register(client)
    decide(admin_client(admin), new_tech(), 'correction', reason='The photo is blurry, upload a clearer one')
    t = new_tech()
    old_file = t.id_document_file
    assert t.verification_status == 'needs_correction'

    tech = flask_app.test_client()
    assert tech.get('/technician/register/update').status_code == 302          # must prove who they are first
    status_check(tech)
    page = tech.get('/technician/register/status').get_data(as_text=True)
    assert 'The photo is blurry' in page and '•••• 3333' in page and 'CRN-0111-2222-3333' not in page
    prefilled = tech.get('/technician/register/update').get_data(as_text=True)
    assert 'value="Maria Santos Cruz"' in prefilled and 'value="maria@test.local"' in prefilled

    clearer = b'\x89PNG\r\n\x1a\n' + b'\1' * 64
    r = tech.post('/technician/register/update', content_type='multipart/form-data', data=form(
        phone='09998887777', staffId='TECH-9999', verification_status='verified',
        id_document=(BytesIO(clearer), 'clear.png', 'image/png')))
    assert r.status_code == 302
    t = new_tech()
    assert (t.verification_status, t.verification_reason, t.phone) == ('pending', None, '09998887777')
    assert t.username == 'TECH-0042' and not t.id_verified                      # protected fields unchanged
    assert id_files() == [t.id_document_file] and t.id_document_file != old_file
    assert [e.action for e in t.verification_events] == ['resubmitted', 'correction_requested', 'submitted']
    assert Notification.query.filter_by(user_role='admin', title='Technician Registration Updated').count() == 1
    # once sent again it can't be edited until the admin decides
    assert tech.get('/technician/register/update').status_code == 302


def test_stale_or_unauthorized_decisions_change_nothing(client, admin, customer, technician):
    register(client)
    t = new_tech()
    decide(admin_client(admin), t, 'reject', reason='Not a valid ID document')
    # a second admin still looking at the old 'pending' page
    decide(admin_client(admin), new_tech(), 'approve', expected='pending')
    assert new_tech().verification_status == 'rejected'
    for outsider in (login_as(flask_app.test_client(), customer), login_as(flask_app.test_client(), technician),
                     flask_app.test_client()):
        decide(outsider, new_tech(), 'approve', expected='rejected')
    assert new_tech().verification_status == 'rejected'


# ---- job assignment -----------------------------------------------------------------

def _booking(customer, number):
    cat = ServiceCategory.query.first() or ServiceCategory(name='Repairs', is_active=True)
    db.session.add(cat)
    db.session.flush()
    svc = Service.query.first() or Service(category_id=cat.id, name='Screen Repair', price=1000, is_active=True)
    db.session.add(svc)
    db.session.flush()
    b = Booking(booking_number=number, user_id=customer.id, service_id=svc.id, device_type='Laptop',
                description='Broken', booking_date=date(2026, 11, 2), booking_time=time(10, 0),
                status='pending', is_in_shop=True)
    db.session.add(b)
    db.session.commit()
    return b


def test_only_verified_technicians_can_be_assigned(client, admin, customer):
    register(client)
    t = new_tech()
    a = admin_client(admin)
    first = _booking(customer, 'BK-V-1')
    a.post(f'/admin/requests/{first.id}/status', data={'status': 'confirmed', 'technician_id': t.id})
    assert db.session.get(Booking, first.id).technician_id is None               # pending: refused

    decide(a, t, 'approve')
    a.post(f'/admin/requests/{first.id}/status', data={'status': 'confirmed', 'technician_id': t.id})
    assert db.session.get(Booking, first.id).technician_id == t.id

    decide(a, new_tech(), 'suspend', reason='ID reported as lost and reissued')
    assert db.session.get(Booking, first.id).technician_id == t.id               # existing job kept
    second = _booking(customer, 'BK-V-2')
    a.post(f'/admin/requests/{second.id}/status', data={'status': 'confirmed', 'technician_id': t.id})
    assert db.session.get(Booking, second.id).technician_id is None              # suspended: refused

    other = Technician(username='TECH-0050', email='o@test.local', full_name='Other Tech',
                       is_active=True, id_verified=True)
    other.set_password('otherpass1')
    db.session.add(other)
    db.session.commit()
    assert other.verification_status == 'verified'
    a.post(f'/admin/requests/{first.id}/assign', data={'technician_id': other.id})
    a.post(f'/admin/requests/{first.id}/assign', data={'technician_id': t.id})   # back to the suspended one
    assert db.session.get(Booking, first.id).technician_id == other.id


def test_user_management_verify_and_revoke_keep_the_status_in_step(admin):
    t = Technician(username='TECH-0060', email='m@test.local', full_name='Made By Admin', is_active=True)
    t.set_password('madebyadmin1')
    db.session.add(t)
    db.session.commit()
    assert t.verification_status == 'pending'
    a = admin_client(admin)
    r = a.post(f'/api/admin/users/technician/{t.id}/verify-id', json={'id_type': 'UMID', 'id_number': 'CRN-9999-0000'})
    assert r.get_json()['success'] is True
    t = db.session.get(Technician, t.id)
    assert t.can_take_jobs and t.verification_events[0].action == 'approved'
    assert a.delete(f'/api/admin/users/technician/{t.id}/verify-id').get_json()['success'] is True
    t = db.session.get(Technician, t.id)
    assert (t.verification_status, t.id_verified, t.can_take_jobs) == ('suspended', False, False)


def test_deleting_the_account_deletes_the_id(client, admin):
    register(client)
    t = new_tech()
    assert id_files()
    r = admin_client(admin).delete(f'/api/admin/users/technician/{t.id}')
    assert r.get_json()['success'] is True
    assert id_files() == [] and TechnicianVerificationEvent.query.count() == 0


def test_admin_pages_show_the_queue_and_the_review(client, admin):
    register(client)
    t = new_tech()
    a = admin_client(admin)
    page = a.get('/admin/technician-verification').get_data(as_text=True)
    assert 'Maria Santos Cruz' in page and 'TECH-0042' in page
    assert 'Technician Verification' in a.get('/admin/dashboard').get_data(as_text=True)
    detail = a.get(f'/admin/technician-verification/{t.id}').get_data(as_text=True)
    for text in ('CRN-0111-2222-3333', 'Request correction', 'Reject', f'/admin/technician-verification/{t.id}/document'):
        assert text in detail
    assert a.get('/admin/technician-verification?status=verified').get_data(as_text=True).count('Maria Santos Cruz') == 0


# ---- employee roster: only hired technicians can register --------------------------

def test_a_tech_id_not_on_the_roster_cannot_register(client):
    r = register(client, hired=False)
    html = r.get_data(as_text=True)
    assert r.status_code == 400 and "match these details to a DEVTech employee record" in html
    assert Technician.query.count() == 0 and id_files() == []


def test_the_ids_details_must_match_the_employee_record(client):
    hire()
    for wrong in ({'fullname': 'Maria Santos Reyes'}, {'dob': '1995-05-21'}, {'id_number': 'CRN-0111-2222-3334'},
                  {'id_type': 'Passport'}):
        r = register(client, **wrong)
        assert r.status_code == 400 and 'employee record' in r.get_data(as_text=True), wrong
    assert Technician.query.count() == 0
    # Capitals, accents and spacing/dashes in the ID number don't matter.
    assert register(client, fullname='MARIA  SANTOS CRUZ', id_number='crn 0111 2222 3333').status_code == 302
    t, record = new_tech(), TechnicianEmployee.query.one()
    assert record.technician_id == t.id and record.registered_at is not None
    assert t.full_name == 'Maria Santos Cruz'                   # the roster's spelling is kept


def test_a_correction_must_still_match_the_employee_record(client, admin):
    register(client)
    decide(admin_client(admin), new_tech(), 'correction', reason='Please upload a clearer photo')
    tech = flask_app.test_client()
    status_check(tech)
    r = tech.post('/technician/register/update', content_type='multipart/form-data',
                  data=form(fullname='Somebody Else Entirely'))
    assert r.status_code == 400 and 'employee record' in r.get_data(as_text=True)
    assert new_tech().verification_status == 'needs_correction'


def test_admin_manages_the_roster(admin_logged_in, client, customer):
    r = admin_logged_in.post('/admin/technician-roster', data={
        'tech_id': 'TECH-0042', 'full_name': 'Maria Santos Cruz', 'birth_date': '1995-05-20',
        'id_type': 'UMID', 'id_number': 'CRN-0111-2222-3333', 'hired_on': '2026-10-01'})
    assert r.status_code == 302
    page = admin_logged_in.get('/admin/technician-roster').get_data(as_text=True)
    assert 'TECH-0042' in page and 'Not registered' in page and 'TECH-0043' in page    # next free ID suggested
    dup = admin_logged_in.post('/admin/technician-roster', data={
        'tech_id': 'TECH-0042', 'full_name': 'Juan Dela Cruz', 'birth_date': '1990-01-01',
        'id_type': 'UMID', 'id_number': 'CRN-0111-2222-3333'})
    assert dup.status_code == 400 and 'already in use' in dup.get_data(as_text=True)
    assert 'already recorded for another technician' in dup.get_data(as_text=True)
    record = TechnicianEmployee.query.one()

    # once registered, the matched details are locked and the record can't be removed
    assert register(client).status_code == 302
    admin_logged_in.post(f'/admin/technician-roster/{record.id}', data={
        'full_name': 'Changed Name Here', 'birth_date': '2000-01-01', 'note': 'Hardware team'})
    record = db.session.get(TechnicianEmployee, record.id)
    assert record.full_name == 'Maria Santos Cruz' and record.note == 'Hardware team'
    admin_logged_in.post(f'/admin/technician-roster/{record.id}/delete')
    assert TechnicianEmployee.query.count() == 1

    # a record nobody registered with can be removed
    hire('TECH-0050', fullname='Pedro Reyes Santos', id_number='CRN-9999-0000-1111')
    spare = TechnicianEmployee.query.filter_by(tech_id='TECH-0050').one()
    admin_logged_in.post(f'/admin/technician-roster/{spare.id}/delete')
    assert TechnicianEmployee.query.count() == 1

    # customers can't see or change the roster
    outsider = login_as(flask_app.test_client(), customer)
    assert outsider.get('/admin/technician-roster').status_code == 302
    outsider.post('/admin/technician-roster', data={'tech_id': 'TECH-0077', 'full_name': 'X Y'})
    assert TechnicianEmployee.query.count() == 1


def test_review_page_shows_the_roster_match(client, admin):
    register(client)
    page = admin_client(admin).get(f'/admin/technician-verification/{new_tech().id}').get_data(as_text=True)
    assert 'Matches roster entry TECH-0042' in page
