"""Customers, technicians and admins live in separate tables, so the same id
can belong to three different people. These tests make sure nothing mixes
them up."""
from app import db, Customer, Technician, Admin, Notification, Message, create_notification
from tests.conftest import login_as


def test_ids_repeat_across_tables(customer, technician, admin):
    assert customer.id == technician.id == admin.id == 1
    assert {customer.key, technician.key, admin.key} == {'customer-1', 'technician-1', 'admin-1'}


def test_notifications_stay_with_their_owner(client, customer, technician, admin):
    create_notification(customer.id, 'For customer', 'x', email=False, role='customer')
    login_as(client, technician)
    assert client.get('/technician/notifications').status_code == 200
    assert Notification.query.filter_by(user_role='customer', is_read=False).count() == 1
    login_as(client, admin)
    html = client.get('/admin/notifications').get_data(as_text=True)
    assert 'For customer' not in html


def test_message_reaches_the_right_account(client, customer, technician, admin, assigned_booking):
    login_as(client, customer)
    r = client.post(f'/messages/{technician.key}/send', data={'content': 'Hello tech'},
                    content_type='multipart/form-data')
    assert r.get_json()['success'] is True
    m = Message.query.one()
    assert (m.sender_role, m.recipient_role) == ('customer', 'technician')
    login_as(client, admin)
    assert 'Hello tech' not in client.get('/admin/messages', follow_redirects=True).get_data(as_text=True)
    login_as(client, technician)
    html = client.get(f'/technician/messages?thread={customer.key}').get_data(as_text=True)
    assert 'Hello tech' in html


def test_technician_cannot_message_unrelated_customer(client, technician):
    stranger = Customer(username='s', email='s@test.local', full_name='Stranger')
    stranger.set_password('strangerpass')
    db.session.add(stranger)
    db.session.commit()
    login_as(client, technician)
    r = client.post(f'/technician/messages/{stranger.key}/send', data={'content': 'hi'})
    assert r.status_code == 403
    assert Message.query.count() == 0


def test_email_unique_across_tables(admin_logged_in, technician):
    r = admin_logged_in.post('/api/admin/users', json={
        'username': 'dup', 'email': technician.email, 'password': 'secret123',
        'full_name': 'Dup Customer', 'role': 'customer'})
    assert r.status_code == 400
    assert Customer.query.count() == 0


def test_admin_creates_account_in_its_table(admin_logged_in):
    r = admin_logged_in.post('/api/admin/users', json={
        'email': 'newtech@test.local', 'password': 'secret123',
        'full_name': 'New Tech', 'role': 'technician'})
    body = r.get_json()
    assert body['success'] is True and body['user']['key'].startswith('technician-')
    assert Technician.query.filter_by(email='newtech@test.local').count() == 1
    assert Customer.query.filter_by(email='newtech@test.local').count() == 0


def test_account_type_cannot_change(admin_logged_in, customer):
    r = admin_logged_in.post(f'/api/admin/users/customer/{customer.id}/role', json={'role': 'admin'})
    assert r.status_code == 400
    r = admin_logged_in.put(f'/api/admin/users/customer/{customer.id}', json={
        'full_name': customer.full_name, 'email': customer.email, 'role': 'admin'})
    assert r.status_code == 400
    assert Admin.query.count() == 1


def test_customer_session_cannot_open_staff_pages(client, customer, technician, admin):
    # Same id (1) in every table: the session role decides who you are.
    login_as(client, customer)
    assert client.get('/admin/dashboard').status_code == 302
    assert client.get('/technician/dashboard').status_code == 302
    assert client.get('/technician/api/me').status_code == 401


def test_old_werkzeug_hashes_still_sign_in_and_get_upgraded(customer):
    from werkzeug.security import generate_password_hash
    customer.password_hash = generate_password_hash('legacyPass1')
    db.session.commit()
    assert customer.check_password('wrong') is False
    assert customer.check_password('legacyPass1') is True
    assert customer.password_hash.startswith('$2')              # now bcrypt
    assert customer.check_password('legacyPass1') is True


def test_garbage_hash_never_matches(customer):
    customer.password_hash = 'x'
    assert customer.check_password('x') is False
