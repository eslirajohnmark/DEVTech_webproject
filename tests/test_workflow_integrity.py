"""Workflow and data-integrity fixes from the functionality audit:
booking validation, cancellation side effects, approval/payment races,
technician reassignment, technician input validation, duplicate checkout."""
import io
from datetime import date, datetime, time, timedelta
from decimal import Decimal

import pytest

from app import (db, Booking, Customer, Technician, Notification, Order, Product, Service,
                 ServiceCategory, Transaction)
from models.technician_models import ApprovalRequest, IncidentReport, IntakeRecord, JobLog, ServiceReport
from tests.conftest import login_as

TOMORROW = (date.today() + timedelta(days=1)).isoformat()


@pytest.fixture
def service(app):
    cat = ServiceCategory(name='Repairs', is_active=True)
    db.session.add(cat)
    db.session.flush()
    svc = Service(category_id=cat.id, name='Screen Repair', price=1500, is_active=True)
    db.session.add(svc)
    db.session.commit()
    return svc


def _book(client, service, **overrides):
    data = {'service_id': str(service.id), 'device_type': 'Laptop', 'problem_description': 'Cracked screen',
            'booking_date': TOMORROW, 'booking_time': '10:00', 'in_shop': 'on',
            'payment_method': 'GCash', 'accept_terms': 'on'}
    data.update(overrides)
    return client.post('/user/service-request', data={k: v for k, v in data.items() if v is not None})


def _admin_notes(title_part):
    return Notification.query.filter(Notification.user_role == 'admin',
                                     Notification.title.contains(title_part)).count()


# ---------------------------------------------------------------- booking rules

def test_valid_booking_records_terms_and_server_price(customer_logged_in, service):
    _book(customer_logged_in, service)
    b = Booking.query.one()
    assert b.terms_accepted_at is not None and b.status == 'pending'
    assert Transaction.query.filter_by(booking_id=b.id).one().amount == Decimal('1500.00')


@pytest.mark.parametrize('overrides, why', [
    ({'accept_terms': None}, 'terms not accepted'),
    ({'payment_method': 'Bitcoin'}, 'unknown payment method'),
    ({'booking_time': '10:30'}, 'not one of the hourly slots'),
    ({'booking_time': '19:00'}, 'outside opening hours'),
    ({'booking_date': (date.today() + timedelta(days=200)).isoformat()}, 'too far ahead'),
    ({'device_type': 'x' * 60}, 'device type too long'),
])
def test_invalid_bookings_are_refused(customer_logged_in, service, overrides, why):
    _book(customer_logged_in, service, **overrides)
    assert Booking.query.count() == 0, why


def test_inactive_service_cannot_be_booked(customer_logged_in, service):
    service.is_active = False
    db.session.commit()
    _book(customer_logged_in, service)
    assert Booking.query.count() == 0


def test_same_customer_cannot_double_book_a_slot(customer_logged_in, service):
    _book(customer_logged_in, service)
    _book(customer_logged_in, service)                       # double click / resubmit
    assert Booking.query.count() == 1


def test_slot_capacity_is_enforced(client, service):
    for i in range(6):
        c = Customer(username=f'c{i}', email=f'c{i}@test.local', full_name=f'Cust {i}', is_active=True)
        c.set_password('password123')
        db.session.add(c)
        db.session.commit()
        login_as(client, c)
        _book(client, service)
    assert Booking.query.count() == 5


def test_custom_service_stays_out_of_the_catalogue(customer_logged_in, service):
    _book(customer_logged_in, service, service_id='other', custom_service='Fan cleaning')
    custom = Service.query.filter_by(name='Custom Service').one()
    assert custom.is_active is False
    assert Booking.query.one().service_id == custom.id


# ---------------------------------------------------------------- cancellation side effects

def _txn(booking, status='pending', **kw):
    t = Transaction(transaction_number=f'TRX-{booking.id}-{status}', booking_id=booking.id,
                    user_id=booking.user_id, amount=1000, payment_method='GCash', payment_status=status, **kw)
    db.session.add(t)
    db.session.commit()
    return t


def test_customer_cancel_cancels_unpaid_charge_and_tells_admins(client, customer, admin, assigned_booking):
    t = _txn(assigned_booking)
    login_as(client, customer)
    assert client.post(f'/booking/{assigned_booking.id}/cancel').get_json()['success'] is True
    assert db.session.get(Transaction, t.id).payment_status == 'cancelled'
    assert _admin_notes('Booking Cancelled') == 1
    # ...and the admin can no longer confirm money for a cancelled job
    login_as(client, admin)
    client.post(f'/admin/payments/{t.id}/confirm')
    assert db.session.get(Transaction, t.id).payment_status == 'cancelled'


def test_cancel_after_payment_proof_asks_for_refund_check(client, customer, admin, assigned_booking):
    t = _txn(assigned_booking, gcash_reference='REF-123')
    login_as(client, customer)
    client.post(f'/booking/{assigned_booking.id}/cancel')
    assert db.session.get(Transaction, t.id).payment_status == 'cancelled'
    assert _admin_notes('Refund to process') == 1


def test_admin_cancel_withdraws_pending_approval(client, technician, customer, admin, assigned_booking):
    assigned_booking.status = 'in_progress'
    db.session.add(ServiceReport(booking_id=assigned_booking.id, technician_id=technician.id,
                                 status='draft', diagnosis='Board fault.'))
    t = _txn(assigned_booking)
    login_as(client, technician)
    client.post(f'/technician/api/jobs/{assigned_booking.id}/approval',
                data={'findings': 'Shorted charging IC on the board.', 'proposedWork': 'Replace the charging IC.',
                      'additionalCost': '1200', 'extraDays': '2'})
    approval = ApprovalRequest.query.one()
    assert db.session.get(Booking, assigned_booking.id).status == 'on_hold'

    login_as(client, admin)
    client.post(f'/admin/requests/{assigned_booking.id}/status', data={'status': 'cancelled', 'reason': 'Duplicate'})
    assert db.session.get(ApprovalRequest, approval.id).status == 'withdrawn'

    login_as(client, customer)
    r = client.post(f'/api/booking/{assigned_booking.id}/approval/{approval.id}/respond', json={'decision': 'approve'})
    assert r.status_code == 400
    assert db.session.get(Transaction, t.id).amount == Decimal('1000.00')     # nothing billed


def test_approval_cannot_be_answered_twice(client, technician, customer, assigned_booking):
    assigned_booking.status = 'in_progress'
    db.session.add(ServiceReport(booking_id=assigned_booking.id, technician_id=technician.id,
                                 status='draft', diagnosis='Board fault.'))
    t = _txn(assigned_booking)
    login_as(client, technician)
    client.post(f'/technician/api/jobs/{assigned_booking.id}/approval',
                data={'findings': 'Shorted charging IC on the board.', 'proposedWork': 'Replace the charging IC.',
                      'additionalCost': '1200', 'extraDays': '2'})
    approval = ApprovalRequest.query.one()
    login_as(client, customer)
    url = f'/api/booking/{assigned_booking.id}/approval/{approval.id}/respond'
    assert client.post(url, json={'decision': 'approve'}).get_json()['ok'] is True
    assert client.post(url, json={'decision': 'approve'}).status_code == 400
    assert db.session.get(Transaction, t.id).amount == Decimal('2200.00')     # billed once


# ---------------------------------------------------------------- payment review

def test_payment_confirm_records_reviewer_and_is_idempotent(client, admin, customer, assigned_booking):
    t = _txn(assigned_booking)
    login_as(client, admin)
    client.post(f'/admin/payments/{t.id}/confirm')
    t = db.session.get(Transaction, t.id)
    assert t.payment_status == 'confirmed' and t.reviewed_at and 'Test Admin' in t.reviewed_by
    client.post(f'/admin/payments/{t.id}/confirm')
    client.post(f'/admin/payments/{t.id}/reject', data={'reason': 'oops'})
    assert db.session.get(Transaction, t.id).payment_status == 'confirmed'
    assert Notification.query.filter_by(user_role='customer', title='Payment Confirmed').count() == 1


def test_customer_payment_submission_is_validated(client, customer, admin, assigned_booking):
    t = _txn(assigned_booking, status='rejected')
    login_as(client, customer)
    client.post(f'/user/payments/{t.id}', data={'payment_method': 'Bitcoin', 'reference_number': 'X1'})
    assert db.session.get(Transaction, t.id).payment_status == 'rejected'
    client.post(f'/user/payments/{t.id}', data={'payment_method': 'GCash', 'reference_number': ''})
    assert db.session.get(Transaction, t.id).payment_status == 'rejected'           # needs reference or receipt
    client.post(f'/user/payments/{t.id}', data={'payment_method': 'GCash', 'reference_number': 'R' * 51})
    assert db.session.get(Transaction, t.id).payment_status == 'rejected'
    client.post(f'/user/payments/{t.id}', data={'payment_method': 'GCash', 'reference_number': 'GC-778899'})
    t = db.session.get(Transaction, t.id)
    assert t.payment_status == 'pending' and t.gcash_reference == 'GC-778899'
    assert _admin_notes('Payment Awaiting') == 1


# ---------------------------------------------------------------- reassignment

def _tech(username, verified=True, active=True):
    t = Technician(username=username, email=f'{username.lower()}@test.local', full_name=f'Tech {username}',
                   is_active=active, id_verified=verified)
    t.set_password('techpass123')
    db.session.add(t)
    db.session.commit()
    return t


def test_admin_reassigns_an_active_job(client, admin, technician, customer, assigned_booking):
    new = _tech('TECH-0002')
    login_as(client, admin)
    client.post(f'/admin/requests/{assigned_booking.id}/assign', data={'technician_id': new.id, 'reason': 'On leave'})
    b = db.session.get(Booking, assigned_booking.id)
    assert b.technician_id == new.id
    assert JobLog.query.filter_by(booking_id=b.id, action='assign').one().text.startswith('Reassigned from')
    assert Notification.query.filter_by(user_role='technician', user_id=new.id).count() == 1
    assert Notification.query.filter_by(user_role='technician', user_id=technician.id, title='Job Reassigned').count() == 1
    assert Notification.query.filter_by(user_role='customer', title='New Technician Assigned').count() == 1
    # the old technician loses access, the new one gains it
    login_as(client, technician)
    assert client.get(f'/technician/jobs/{b.id}').status_code == 403
    login_as(client, new)
    assert client.get(f'/technician/jobs/{b.id}').status_code == 200


@pytest.mark.parametrize('case', ['unverified', 'inactive', 'finished', 'pending'])
def test_reassignment_rules(client, admin, assigned_booking, case):
    target = _tech('TECH-0003', verified=(case != 'unverified'), active=(case != 'inactive'))
    if case == 'finished':
        assigned_booking.status = 'released'
    if case == 'pending':
        assigned_booking.status = 'pending'
    db.session.commit()
    before = assigned_booking.technician_id
    login_as(client, admin)
    client.post(f'/admin/requests/{assigned_booking.id}/assign', data={'technician_id': target.id})
    assert db.session.get(Booking, assigned_booking.id).technician_id == before


def test_only_admins_can_reassign(client, customer, technician, assigned_booking):
    target = _tech('TECH-0004')
    for who in (customer, technician):
        login_as(client, who)
        client.post(f'/admin/requests/{assigned_booking.id}/assign', data={'technician_id': target.id})
    assert db.session.get(Booking, assigned_booking.id).technician_id == technician.id


# ---------------------------------------------------------------- technician input

INCIDENT = {'type': 'safety', 'severity': 'high', 'location': 'Rizal St',
            'description': 'A dog attacked me at the gate of the house.'}


def test_incident_cannot_point_at_another_technicians_job(client, technician, assigned_booking):
    other = _tech('TECH-0005')
    login_as(client, other)
    r = client.post('/technician/api/incidents', json=dict(INCIDENT, jobId=assigned_booking.id))
    assert r.status_code == 400 and IncidentReport.query.count() == 0
    r = client.post('/technician/api/incidents', json=dict(INCIDENT, jobId=999999))
    assert r.status_code == 400 and IncidentReport.query.count() == 0


def test_incident_values_are_validated_and_not_duplicated(client, technician, assigned_booking):
    login_as(client, technician)
    assert client.post('/technician/api/incidents', json=dict(INCIDENT, type='alien')).status_code == 400
    assert client.post('/technician/api/incidents', json=dict(INCIDENT, severity='extreme')).status_code == 400
    assert client.post('/technician/api/incidents', json=dict(INCIDENT, location='x' * 300)).status_code == 400
    first = client.post('/technician/api/incidents', json=dict(INCIDENT, jobId=assigned_booking.id)).get_json()
    again = client.post('/technician/api/incidents', json=dict(INCIDENT, jobId=assigned_booking.id)).get_json()
    assert first['ok'] and again.get('duplicate') and again['incident']['id'] == first['incident']['id']
    assert IncidentReport.query.count() == 1


def test_intake_rules(client, technician, assigned_booking):
    login_as(client, technician)
    url = f'/technician/api/jobs/{assigned_booking.id}/intake'
    assert client.post(url, json={'deviceType': '', 'condition': 'good'}).status_code == 400
    assert client.post(url, json={'deviceType': 'Laptop', 'condition': 'shiny'}).status_code == 400
    assert client.post(url, json={'deviceType': 'L' * 41, 'condition': 'good'}).status_code == 400
    assert IntakeRecord.query.count() == 0
    assert client.post(url, json={'deviceType': 'Laptop', 'condition': 'fair'}).get_json()['ok'] is True
    b = db.session.get(Booking, assigned_booking.id)
    b.status = 'cancelled'
    db.session.commit()
    assert client.post(url, json={'deviceType': 'Desktop', 'condition': 'good'}).status_code == 400
    assert IntakeRecord.query.one().device_type == 'Laptop'


# ---------------------------------------------------------------- shop

def test_repeated_checkout_does_not_create_a_second_order(customer_logged_in, customer):
    customer.phone, customer.address, customer.city = '0917', '1 Rizal St', 'Tacloban'
    customer.province, customer.postal_code = 'Leyte', '6500'
    p = Product(name='SSD 512GB', price=2500, stock_quantity=3, is_active=True)
    db.session.add(p)
    db.session.commit()
    customer_logged_in.post('/api/cart/add', json={'product_id': p.id, 'quantity': 1})
    first = customer_logged_in.post('/api/cart/checkout', json={'payment_method': 'cod'}).get_json()
    again = customer_logged_in.post('/api/cart/checkout', json={'payment_method': 'cod'}).get_json()
    assert first['success'] and again['success'] and again.get('duplicate')
    assert again['order_number'] == first['order_number']
    assert Order.query.count() == 1 and db.session.get(Product, p.id).stock_quantity == 2
