"""Tests for the admin management pages, support/contact, admin inbox, and the
customer-approval (on_hold) flow."""
from decimal import Decimal

from app import (db, Customer, Technician, Admin, Product, Service, ServiceCategory, SupportTicket, ContactInquiry,
                 Message, Notification, Transaction, Booking)
from models.technician_models import ApprovalRequest, ServiceReport
from tests.conftest import login_as


# ---- Admin: products ----

def test_admin_creates_updates_and_hides_product(admin_logged_in, client, customer):
    r = admin_logged_in.post('/admin/products', data={
        'name': 'USB Hub', 'price': '450', 'stock_quantity': '7', 'category': 'Accessory'})
    assert r.status_code == 302
    p = Product.query.filter_by(name='USB Hub').one()
    assert p.price == Decimal('450.00') and p.stock_quantity == 7 and p.category == 'accessory'

    admin_logged_in.post(f'/admin/products/{p.id}', data={
        'name': 'USB Hub 4-port', 'price': '499.50', 'stock_quantity': '3'})
    assert db.session.get(Product, p.id).name == 'USB Hub 4-port'
    assert admin_logged_in.get('/admin/products').status_code == 200

    admin_logged_in.post(f'/admin/products/{p.id}/toggle')
    assert db.session.get(Product, p.id).is_active is False
    login_as(client, customer)
    assert all(x['id'] != p.id for x in client.get('/api/products').get_json())


def test_admin_product_validation(admin_logged_in):
    for bad in ({'name': 'X', 'price': 'abc', 'stock_quantity': '1'},
                {'name': 'X', 'price': '10', 'stock_quantity': '-1'},
                {'name': 'X', 'price': '10', 'stock_quantity': '1', 'image_url': 'javascript:alert(1)'}):
        admin_logged_in.post('/admin/products', data=bad)
    assert Product.query.count() == 0


# ---- Admin: services ----

def test_admin_manages_categories_and_services(admin_logged_in):
    admin_logged_in.post('/admin/categories', data={'name': 'Phone Repair', 'icon': 'fa-mobile'})
    cat = ServiceCategory.query.filter_by(name='Phone Repair').one()
    assert cat.slug == 'phone-repair'

    admin_logged_in.post('/admin/services', data={
        'name': 'Screen swap', 'category_id': cat.id, 'price': '1500', 'estimated_hours': '2'})
    svc = Service.query.filter_by(name='Screen swap').one()
    admin_logged_in.post(f'/admin/services/{svc.id}', data={
        'name': 'Screen swap', 'category_id': cat.id, 'price': '1750', 'estimated_hours': '2'})
    assert db.session.get(Service, svc.id).price == Decimal('1750.00')
    assert admin_logged_in.get('/admin/services').status_code == 200

    admin_logged_in.post(f'/admin/services/{svc.id}/toggle')
    assert db.session.get(Service, svc.id).is_active is False


# ---- Support tickets & contact form ----

def test_admin_answers_support_ticket(client, customer, admin):
    login_as(client, customer)
    client.post('/support', data={'subject': 'Late repair', 'message': 'Where is my laptop?'})
    ticket = SupportTicket.query.one()

    login_as(client, admin)
    assert 'Late repair' in client.get('/admin/support').get_data(as_text=True)
    client.post(f'/admin/support/{ticket.id}/respond',
                data={'admin_response': 'It is ready today.', 'status': 'resolved'})
    ticket = db.session.get(SupportTicket, ticket.id)
    assert ticket.status == 'resolved' and ticket.admin_response == 'It is ready today.'
    assert Notification.query.filter_by(user_role='customer', user_id=customer.id, title='Support Ticket Updated').count() == 1


def test_contact_form_stores_inquiry_and_notifies_admin(client, admin):
    r = client.post('/contact', json={'name': 'Ana', 'email': 'ana@example.com',
                                      'subject': 'Hours?', 'message': 'Are you open Sunday?'})
    assert r.get_json()['success'] is True
    assert ContactInquiry.query.one().email == 'ana@example.com'
    assert Notification.query.filter_by(user_role='admin', user_id=admin.id).count() == 1

    assert client.post('/contact', json={'name': 'A', 'email': 'nope', 'subject': 's',
                                         'message': 'm'}).status_code == 400

    login_as(client, admin)
    inquiry = ContactInquiry.query.one()
    client.post(f'/admin/inquiries/{inquiry.id}/status')
    assert db.session.get(ContactInquiry, inquiry.id).status == 'handled'


# ---- Admin inbox ----

def test_admin_messages_customer_and_customer_sees_it(client, admin, customer):
    login_as(client, admin)
    assert client.get('/messages').status_code == 302          # admins go to their own inbox
    client.post('/admin/messages/send', data={'recipient_email': customer.email, 'content': 'Hi there'})
    assert Message.query.filter_by(sender_role='admin', sender_id=admin.id, recipient_role='customer', recipient_id=customer.id).count() == 1
    html = client.get(f'/admin/messages?conv={customer.key}').get_data(as_text=True)
    assert 'Hi there' in html

    login_as(client, customer)
    html = client.get(f'/messages?conv={admin.key}').get_data(as_text=True)
    assert 'Hi there' in html


def test_customer_nav_has_messages_and_notifications(customer_logged_in):
    html = customer_logged_in.get('/user/dashboard').get_data(as_text=True)
    assert 'href="/messages"' in html and 'href="/notifications"' in html


# ---- Customer approval (on_hold) flow ----

APPROVAL = {'findings': 'Charging IC is shorted on the board.',
            'proposedWork': 'Replace the charging IC and the battery.',
            'additionalCost': '1200', 'extraDays': '2'}


def _job_in_repair(booking, transaction_status='pending'):
    booking.status = 'in_progress'
    db.session.add(ServiceReport(booking_id=booking.id, technician_id=booking.technician_id,
                                 status='draft', diagnosis='Board fault.'))
    db.session.add(Transaction(transaction_number='TRX-AP1', booking_id=booking.id,
                               user_id=booking.user_id, amount=1000, payment_method='GCash',
                               payment_status=transaction_status))
    db.session.commit()


def _request_approval(client, technician, booking):
    login_as(client, technician)
    return client.post(f'/technician/api/jobs/{booking.id}/approval', data=APPROVAL)


def test_technician_request_puts_job_on_hold(client, technician, assigned_booking):
    _job_in_repair(assigned_booking)
    _request_approval(client, technician, assigned_booking)
    assert db.session.get(Booking, assigned_booking.id).status == 'on_hold'
    assert ApprovalRequest.query.filter_by(status='pending').count() == 1
    # Work can't move on while waiting.
    r = client.post(f'/technician/api/jobs/{assigned_booking.id}/advance', json={})
    assert r.status_code == 400
    page = client.get(f'/technician/jobs/{assigned_booking.id}').get_data(as_text=True)
    assert 'Waiting for customer' in page
    # A second request while one is pending is refused.
    client.post(f'/technician/api/jobs/{assigned_booking.id}/approval', data=APPROVAL)
    assert ApprovalRequest.query.count() == 1


def test_customer_approves_and_cost_is_added(client, technician, customer, assigned_booking):
    _job_in_repair(assigned_booking)
    _request_approval(client, technician, assigned_booking)
    approval = ApprovalRequest.query.one()

    login_as(client, customer)
    monitor = client.get(f'/api/booking/{assigned_booking.id}/monitor').get_json()
    assert monitor['approval']['id'] == approval.id

    r = client.post(f'/api/booking/{assigned_booking.id}/approval/{approval.id}/respond',
                    json={'decision': 'approve', 'note': 'Go ahead'})
    assert r.get_json()['ok'] is True
    assert db.session.get(Booking, assigned_booking.id).status == 'in_progress'
    assert Transaction.query.filter_by(booking_id=assigned_booking.id).one().amount == Decimal('2200.00')
    assert db.session.get(ApprovalRequest, approval.id).customer_response == 'Go ahead'
    # Answering twice is refused.
    r = client.post(f'/api/booking/{assigned_booking.id}/approval/{approval.id}/respond',
                    json={'decision': 'decline'})
    assert r.status_code == 400


def test_extra_cost_on_paid_booking_is_billed_separately(client, technician, customer, assigned_booking):
    _job_in_repair(assigned_booking, transaction_status='confirmed')
    _request_approval(client, technician, assigned_booking)
    approval = ApprovalRequest.query.one()
    login_as(client, customer)
    client.post(f'/api/booking/{assigned_booking.id}/approval/{approval.id}/respond',
                json={'decision': 'approve'})
    extra = Transaction.query.filter(Transaction.transaction_number.like('EXTRA-%')).one()
    assert extra.amount == Decimal('1200.00') and extra.payment_status == 'pending'
    assert assigned_booking.booking_number in extra.transaction_number
    assert 'Approved Extra Work' in client.get('/user/transactions').get_data(as_text=True)


def test_customer_declines(client, technician, customer, assigned_booking):
    _job_in_repair(assigned_booking)
    _request_approval(client, technician, assigned_booking)
    approval = ApprovalRequest.query.one()
    login_as(client, customer)
    client.post(f'/api/booking/{assigned_booking.id}/approval/{approval.id}/respond',
                json={'decision': 'decline'})
    assert db.session.get(ApprovalRequest, approval.id).status == 'declined'
    assert db.session.get(Booking, assigned_booking.id).status == 'in_progress'
    assert Transaction.query.filter_by(booking_id=assigned_booking.id).one().amount == Decimal('1000.00')


def test_other_customer_cannot_answer(client, technician, assigned_booking):
    _job_in_repair(assigned_booking)
    _request_approval(client, technician, assigned_booking)
    approval = ApprovalRequest.query.one()
    other = Customer(username='c2', email='c2@test.local', full_name='Other')
    other.set_password('otherpass1')
    db.session.add(other)
    db.session.commit()
    login_as(client, other)
    r = client.post(f'/api/booking/{assigned_booking.id}/approval/{approval.id}/respond',
                    json={'decision': 'approve'})
    assert r.status_code == 404


def test_technician_can_withdraw(client, technician, assigned_booking):
    _job_in_repair(assigned_booking)
    _request_approval(client, technician, assigned_booking)
    approval = ApprovalRequest.query.one()
    client.post(f'/technician/api/approvals/{approval.id}/withdraw')
    assert db.session.get(ApprovalRequest, approval.id).status == 'withdrawn'
    assert db.session.get(Booking, assigned_booking.id).status == 'in_progress'


def test_admin_sees_approval_requests(client, technician, admin, assigned_booking):
    _job_in_repair(assigned_booking)
    _request_approval(client, technician, assigned_booking)
    login_as(client, admin)
    html = client.get('/admin/technician-activity').get_data(as_text=True)
    assert 'Replace the charging IC' in html


# ---- Technician pages ----

def test_technician_login_script_has_csp_nonce(client):
    html = client.get('/technician/login').get_data(as_text=True)
    assert '<script nonce="' in html and '<script>' not in html
