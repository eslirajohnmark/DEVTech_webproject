"""Server-side pagination of the admin Service Requests / Payment Confirmation lists,
and incident evidence files (technician upload, admin viewing)."""
import io
import re
from datetime import date, time, timedelta

import pytest

from app import db, Booking, Customer, Service, ServiceCategory, Technician, Transaction
from models.technician_models import IncidentReport, UploadedFile
from tests.conftest import login_as

PNG = (b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00'
       b'\x1f\x15\xc4\x89\x00\x00\x00\rIDATx\x9cc\xf8\x0f\x00\x00\x01\x01\x00\x05\x18\xd8N\x00'
       b'\x00\x00\x00IEND\xaeB`\x82')


@pytest.fixture
def many_bookings(app, customer):
    cat = ServiceCategory(name='Repairs', is_active=True)
    db.session.add(cat)
    db.session.flush()
    svc = Service(category_id=cat.id, name='Screen Repair', price=1000, is_active=True)
    db.session.add(svc)
    db.session.flush()
    statuses = ['pending'] * 10 + ['in_progress'] * 8 + ['released'] * 7 + ['cancelled'] * 5
    rows = []
    for i, st in enumerate(statuses):
        b = Booking(booking_number=f'BK-P{i:03d}', user_id=customer.id, service_id=svc.id, device_type='Laptop',
                    description='x', booking_date=date.today() + timedelta(days=i % 20),
                    booking_time=time(8 + i % 10, 0), status=st, is_in_shop=True)
        db.session.add(b)
        db.session.flush()
        db.session.add(Transaction(transaction_number=f'TRX-P{i:03d}', booking_id=b.id, user_id=customer.id,
                                   amount=1000, payment_method='GCash',
                                   payment_status='cancelled' if st == 'cancelled' else 'pending',
                                   gcash_reference=f'GREF{i:03d}'))
        rows.append(b)
    db.session.commit()
    return rows


def _cards(html, cls):
    return len(re.findall(rf'class="{cls}"', html))


def test_requests_are_paginated_on_the_server(admin_logged_in, many_bookings):
    page1 = admin_logged_in.get('/admin/requests').get_data(as_text=True)
    page2 = admin_logged_in.get('/admin/requests?page=2').get_data(as_text=True)
    assert _cards(page1, 'admin-request-card') == 25 and _cards(page2, 'admin-request-card') == 5
    assert '1–25 of 30' in page1 and 'Page 2 of 2' in page2
    clamped = admin_logged_in.get('/admin/requests?page=99').get_data(as_text=True)
    assert 'Page 2 of 2' in clamped


def test_request_stats_count_every_approved_job(admin_logged_in, many_bookings):
    html = admin_logged_in.get('/admin/requests?status=cancelled').get_data(as_text=True)
    numbers = re.findall(r'class="admin-stat-number">(\d+)<', html)
    assert numbers[:4] == ['30', '10', '15', '5']     # total, pending, approved (in repair + released), cancelled


def test_request_filters_and_search(admin_logged_in, many_bookings):
    html = admin_logged_in.get('/admin/requests?status=in_progress').get_data(as_text=True)
    assert _cards(html, 'admin-request-card') == 8 and 'selected>On Repair' in html
    html = admin_logged_in.get('/admin/requests?q=BK-P007').get_data(as_text=True)
    assert _cards(html, 'admin-request-card') == 1
    html = admin_logged_in.get('/admin/requests?q=Test%20Customer&status=pending').get_data(as_text=True)
    assert _cards(html, 'admin-request-card') == 10
    assert admin_logged_in.get('/admin/requests?status=hacked').status_code == 200    # unknown status -> all


def test_payments_are_paginated_and_filterable(admin_logged_in, many_bookings):
    page1 = admin_logged_in.get('/admin/payments').get_data(as_text=True)
    assert _cards(page1, 'admin-payment-card') + page1.count('class="admin-payment-card ') >= 1
    assert '1–25 of 30' in page1
    cancelled = admin_logged_in.get('/admin/payments?status=cancelled').get_data(as_text=True)
    assert '1–5 of 5' in cancelled
    found = admin_logged_in.get('/admin/payments?q=GREF012').get_data(as_text=True)
    assert '1–1 of 1' in found and 'TRX-P012' in found


def test_admin_lists_are_admin_only(client, customer):
    login_as(client, customer)
    assert client.get('/admin/requests').status_code == 302
    assert client.get('/admin/payments').status_code == 302


# ---------------------------------------------------------------- incident evidence

INCIDENT = {'type': 'animal', 'severity': 'medium', 'location': 'Gate',
            'description': 'Aggressive dog at the gate, could not enter the yard.'}


def _report(client, files, **extra):
    data = dict(INCIDENT, **extra)
    data['photos'] = files
    return client.post('/technician/api/incidents', data=data, content_type='multipart/form-data')


def test_technician_attaches_evidence_and_admin_can_open_it(client, technician, admin, assigned_booking, tmp_path):
    login_as(client, technician)
    _report(client, [(io.BytesIO(PNG), 'dog.png', 'image/png'),
                     (io.BytesIO(b'%PDF-1.4 statement'), 'statement.pdf', 'application/pdf')],
            jobId=str(assigned_booking.id))
    incident = IncidentReport.query.one()
    files = UploadedFile.query.filter_by(owner_type='incident', owner_id=incident.id).all()
    assert sorted(f.original_name for f in files) == ['dog.png', 'statement.pdf']
    img = next(f for f in files if f.mime_type == 'image/png')

    # technician sees and opens their own file
    page = client.get('/technician/incidents').get_data(as_text=True)
    assert f'/technician/api/uploads/{img.id}' in page
    assert client.get(f'/technician/api/uploads/{img.id}').status_code == 200

    # admin sees it in Technician Activity and can open it
    login_as(client, admin)
    activity = client.get('/admin/technician-activity').get_data(as_text=True)
    assert f'/admin/uploads/{img.id}' in activity
    r = client.get(f'/admin/uploads/{img.id}')
    assert r.status_code == 200 and r.mimetype == 'image/png' and r.data == PNG
    pdf = next(f for f in files if f.mime_type == 'application/pdf')
    assert 'attachment' in client.get(f'/admin/uploads/{pdf.id}').headers['Content-Disposition']


def test_evidence_is_private(client, technician, customer, assigned_booking):
    login_as(client, technician)
    _report(client, [(io.BytesIO(PNG), 'dog.png', 'image/png')])
    f = UploadedFile.query.one()
    other = Technician(username='TECH-0042', email='o@test.local', full_name='Other', is_active=True)
    other.set_password('otherpass1')
    db.session.add(other)
    db.session.commit()
    login_as(client, other)
    assert client.get(f'/technician/api/uploads/{f.id}').status_code == 404
    assert client.get(f'/admin/uploads/{f.id}').status_code == 302          # not an admin
    login_as(client, customer)
    assert client.get(f'/admin/uploads/{f.id}').status_code == 302
    client.get('/logout')
    assert client.get(f'/admin/uploads/{f.id}').status_code == 302


def test_bad_or_too_many_files_refuse_the_whole_report(client, technician):
    login_as(client, technician)
    r = _report(client, [(io.BytesIO(b'<script>alert(1)</script>'), 'x.png', 'image/png')])
    assert r.status_code == 302 and IncidentReport.query.count() == 0 and UploadedFile.query.count() == 0
    r = _report(client, [(io.BytesIO(PNG), f'p{i}.png', 'image/png') for i in range(6)])
    assert IncidentReport.query.count() == 0 and UploadedFile.query.count() == 0
    r = _report(client, [])                                                   # files are optional
    assert IncidentReport.query.count() == 1
