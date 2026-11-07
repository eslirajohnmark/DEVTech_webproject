"""Manual On Repair -> Ready -> Released stages with an error banner, technician
certificates, the customer's technician card, the admin Technician Activity
roster and the live sidebar counts."""
import os
from io import BytesIO

from app import (app as flask_app, db, Booking, Transaction, Customer, TechnicianCredential)
from models.technician_models import ServiceReport
from tests.conftest import login_as

PNG = b'\x89PNG\r\n\x1a\n' + b'\0' * 64


def _in_repair(booking, report=None):
    booking.status = 'in_progress'
    if report:
        db.session.add(ServiceReport(booking_id=booking.id, technician_id=booking.technician_id,
                                     diagnosis='Broken hinge', status=report, submitted_at='2026-10-28 10:00:00'))
    db.session.commit()


def _pay(booking, method, status='pending'):
    db.session.add(Transaction(transaction_number=f'TRX-{booking.id}', booking_id=booking.id,
                               user_id=booking.user_id, amount=1000, payment_method=method,
                               payment_status=status))
    db.session.commit()


def _advance(client, booking, **form):
    return client.post(f'/technician/api/jobs/{booking.id}/advance', data=form, follow_redirects=True)


# ---- manual stages and the error banner ------------------------------------------

def test_advance_without_the_report_shows_an_error_banner(tech_logged_in, assigned_booking):
    _in_repair(assigned_booking)
    html = _advance(tech_logged_in, assigned_booking).get_data(as_text=True)
    assert 'tech-banner--danger' in html and 'submit your service report first' in html
    assert db.session.get(Booking, assigned_booking.id).status == 'in_progress'
    assert 'Advance to Ready for Collection' in html and 'Service report submitted' in html


def test_submitting_the_report_does_not_move_the_job(tech_logged_in, assigned_booking):
    _in_repair(assigned_booking, report='draft')
    tech_logged_in.post(f'/technician/api/jobs/{assigned_booking.id}/report', data={
        'action': 'submit', 'diagnosis': 'Broken hinge', 'workPerformed': 'Replaced hinge', 'outcome': 'fixed',
        'hoursSpent': '1'})
    assert db.session.get(Booking, assigned_booking.id).status == 'in_progress'
    html = _advance(tech_logged_in, assigned_booking).get_data(as_text=True)
    assert 'tech-banner--ok' in html and db.session.get(Booking, assigned_booking.id).status == 'completed'


def test_gcash_job_is_released_only_after_an_admin_confirms_payment(tech_logged_in, assigned_booking):
    _in_repair(assigned_booking, report='submitted')
    _advance(tech_logged_in, assigned_booking)
    _pay(assigned_booking, 'GCash')
    html = _advance(tech_logged_in, assigned_booking).get_data(as_text=True)
    assert 'been confirmed by an admin' in html
    assert db.session.get(Booking, assigned_booking.id).status == 'completed'
    Transaction.query.update({'payment_status': 'confirmed'})
    db.session.commit()
    _advance(tech_logged_in, assigned_booking)
    assert db.session.get(Booking, assigned_booking.id).status == 'released'


def test_cash_after_repair_needs_the_cash_confirmed(tech_logged_in, assigned_booking):
    _in_repair(assigned_booking, report='submitted')
    _advance(tech_logged_in, assigned_booking)
    _pay(assigned_booking, 'C.A.R')
    page = tech_logged_in.get(f'/technician/jobs/{assigned_booking.id}').get_data(as_text=True)
    assert 'I collected ₱1,000.00 cash' in page and 'Release device to customer' in page
    assert 'tick the box' in _advance(tech_logged_in, assigned_booking).get_data(as_text=True)
    _advance(tech_logged_in, assigned_booking, cash_received='1')
    assert db.session.get(Booking, assigned_booking.id).status == 'released'
    txn = Transaction.query.one()
    assert txn.payment_status == 'confirmed' and 'cash at release' in txn.reviewed_by


def test_earlier_stages_show_what_moves_them_automatically(tech_logged_in, assigned_booking):
    page = tech_logged_in.get(f'/technician/jobs/{assigned_booking.id}').get_data(as_text=True)
    assert 'moves automatically' in page and 'Device intake recorded' in page
    assert 'Advance to' not in page                               # no manual button before On Repair


# ---- certificates & achievements -------------------------------------------------

def _add_cert(client, **over):
    data = {'title': 'TESDA CSS NC II', 'issuer': 'TESDA', 'issued_on': '2024-03-01',
            'file': (BytesIO(PNG), 'cert.png', 'image/png')}
    data.update(over)
    return client.post('/technician/profile/credentials', data=data, content_type='multipart/form-data',
                       follow_redirects=True)


def test_technician_adds_and_removes_a_certificate(tech_logged_in, technician):
    _add_cert(tech_logged_in)
    cred = TechnicianCredential.query.one()
    path = os.path.join(flask_app.config['CREDENTIAL_UPLOAD_FOLDER'], cred.file)
    assert os.path.isfile(path) and cred.title == 'TESDA CSS NC II'
    assert 'TESDA CSS NC II' in tech_logged_in.get('/technician/profile').get_data(as_text=True)
    tech_logged_in.post(f'/technician/profile/credentials/{cred.id}/delete')
    assert TechnicianCredential.query.count() == 0 and not os.path.exists(path)


def test_bad_certificates_are_refused(tech_logged_in):
    assert 'title' in _add_cert(tech_logged_in, title='x').get_data(as_text=True)
    assert 'must be a JPG' in _add_cert(tech_logged_in, file=(BytesIO(b'MZ'), 'a.exe', 'application/octet-stream'))\
        .get_data(as_text=True)
    assert 'future' in _add_cert(tech_logged_in, issued_on='2999-01-01').get_data(as_text=True)
    assert TechnicianCredential.query.count() == 0


def test_certificates_are_seen_by_admins_and_the_technicians_customers_only(
        client, technician, customer, admin, assigned_booking):
    login_as(client, technician)
    _add_cert(client)
    url = f'/credentials/{TechnicianCredential.query.one().id}'
    assert flask_app.test_client().get(url).status_code == 302                       # anonymous
    assert login_as(flask_app.test_client(), admin).get(url).status_code == 200
    assert login_as(flask_app.test_client(), customer).get(url).data == PNG          # has a job with them
    stranger = Customer(username='other', email='other@test.local', full_name='Other Person', is_active=True)
    stranger.set_password('otherpass12')
    db.session.add(stranger)
    db.session.commit()
    assert login_as(flask_app.test_client(), stranger).get(url).status_code == 404


# ---- customer's technician card ----------------------------------------------------

def test_monitor_shows_the_technicians_photo_certificates_and_honest_rating(
        client, technician, customer, assigned_booking):
    login_as(client, technician)
    _add_cert(client)
    technician.avatar_file = 'a' * 32 + '.png'
    db.session.commit()
    data = login_as(flask_app.test_client(), customer).get(
        f'/api/booking/{assigned_booking.id}/monitor').get_json()
    tech = data['technician']
    assert tech['avatar'] and tech['credentials'][0]['title'] == 'TESDA CSS NC II'
    assert tech['rating'] is None and tech['rating_count'] == 0      # no fake 5.0
    assert data['rateLater'] is True and data['canRate'] is False


# ---- admin Technician Activity ------------------------------------------------------

def test_activity_page_shows_each_technicians_workload(admin_logged_in, technician, assigned_booking):
    _in_repair(assigned_booking, report='draft')
    page = admin_logged_in.get('/admin/technician-activity').get_data(as_text=True)
    assert 'Test Technician' in page and 'Working on' in page
    one = admin_logged_in.get(f'/admin/technician-activity?tech={technician.id}').get_data(as_text=True)
    assert 'Working on now' in one and 'BK-TEST-0001' in one
    assert 'Broken hinge' in one and 'draft' in one                    # their reports, drafts included


# ---- live sidebar counts --------------------------------------------------------------

def test_live_updates_carry_the_sidebar_counts(client, technician, admin, customer, assigned_booking):
    tech = login_as(flask_app.test_client(), technician).get('/api/live').get_json()
    assert tech['c']['jobs'] == 1                                     # assigned, not started
    adm = login_as(flask_app.test_client(), admin).get('/api/live').get_json()
    assert {'requests', 'payments', 'activity', 'verifications', 'refunds', 'support'} <= set(adm['c'])
    cust = login_as(flask_app.test_client(), customer).get('/api/live').get_json()
    assert cust['c']['approvals'] == 0
    page = login_as(flask_app.test_client(), technician).get('/technician/dashboard').get_data(as_text=True)
    assert 'data-live-count="jobs"' in page
