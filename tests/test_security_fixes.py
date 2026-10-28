"""Regression tests for the security and correctness fixes in app.py."""
import io

from app import (app as flask_app, db, Customer, Technician, Admin, Product, Order, Transaction, ShoppingCart,
                 CartItem, Notification, _login_or_create_oauth_user)
from tests.conftest import login_as


# ---- XSS ----

def test_admin_users_page_escapes_user_names(admin_logged_in, customer):
    customer.full_name = '</script><script>alert(1)</script>'
    db.session.commit()
    html = admin_logged_in.get('/admin/users').get_data(as_text=True)
    assert '</script><script>alert(1)' not in html
    assert '\\u003c/script\\u003e' in html


def test_tojson_filter_escapes_quotes_and_tags(app):
    with app.test_request_context():
        from flask import render_template_string
        out = render_template_string("{{ v|tojson }}", v=["</script>", "it's"])
    assert '<' not in out and "'" not in out


# ---- Sessions / accounts ----

def test_deactivated_user_session_is_ended(customer_logged_in, customer):
    customer.is_active = False
    db.session.commit()
    r = customer_logged_in.get('/user/dashboard')
    assert r.status_code == 302
    with customer_logged_in.session_transaction() as s:
        assert 'user_id' not in s


def test_deactivated_admin_is_locked_out(admin_logged_in, admin):
    admin.is_active = False
    db.session.commit()
    assert admin_logged_in.get('/admin/dashboard').status_code == 302


def test_setup_route_disabled_without_token(client, monkeypatch):
    monkeypatch.delenv('SETUP_TOKEN', raising=False)
    assert client.get('/setup/first-admin').status_code == 404


def test_self_registered_technician_is_inactive(client, admin):
    r = client.post('/technician/register', data={
        'fullname': 'New Tech', 'email': 'new@test.local', 'staffId': 'TECH-0042',
        'password': 'password123', 'gender': 'male', 'dob': '1990-01-01'})
    assert r.status_code == 302
    u = Technician.query.filter_by(username='TECH-0042').first()
    assert u is not None and u.is_active is False
    assert Notification.query.filter_by(user_role='admin', user_id=admin.id).count() == 1


def test_customer_can_delete_account_with_history(customer_logged_in, customer):
    # Logging in creates an activity log; with a transaction on record the
    # account must be anonymized rather than failing on a foreign key.
    db.session.add(Transaction(transaction_number='TRX-T1', user_id=customer.id, amount=10,
                               payment_method='cod', payment_status='confirmed'))
    db.session.commit()
    r = customer_logged_in.post('/api/user/delete-account')
    assert r.get_json()['success'] is True
    u = db.session.get(Customer, customer.id)
    assert u.is_active is False and u.email.endswith('@deleted.invalid')


def test_customer_without_history_is_deleted(customer_logged_in, customer):
    uid = customer.id
    r = customer_logged_in.post('/api/user/delete-account')
    assert r.get_json()['success'] is True
    assert db.session.get(Customer, uid) is None


# ---- OAuth ----

def _oauth(email, verified, provider_id='g-1'):
    with flask_app.test_request_context('/login/google/callback'):
        from flask import session
        resp = _login_or_create_oauth_user('google', provider_id, email, 'Someone', verified)
        return resp, dict(session)


def test_oauth_rejects_unverified_email(customer):
    _, sess = _oauth(customer.email, False)
    assert 'user_id' not in sess


def test_oauth_never_logs_into_admin(admin):
    _, sess = _oauth(admin.email, True)
    assert 'user_id' not in sess
    assert Customer.query.filter_by(email=admin.email).count() == 0   # no shadow customer either


def test_oauth_links_verified_customer(customer):
    _, sess = _oauth(customer.email, True)
    assert sess.get('user_id') == customer.id


# ---- Shop ----

def _product(stock=2, price=100):
    p = Product(name='SSD', price=price, stock_quantity=stock, is_active=True)
    db.session.add(p)
    db.session.commit()
    return p


def _with_address(user):
    user.phone, user.address, user.city = '0917', '1 Street', 'Tacloban'
    user.province, user.postal_code = 'Leyte', '6500'
    db.session.commit()


def test_cart_rejects_negative_quantity(customer_logged_in):
    p = _product(stock=5)
    r = customer_logged_in.post('/api/cart/add', json={'product_id': p.id, 'quantity': -100})
    assert r.status_code == 400
    assert db.session.get(Product, p.id).stock_quantity == 5


def test_adding_to_cart_does_not_hold_stock(customer_logged_in):
    p = _product(stock=5)
    customer_logged_in.post('/api/cart/add', json={'product_id': p.id, 'quantity': 3})
    assert db.session.get(Product, p.id).stock_quantity == 5


def test_can_buy_the_last_units(customer_logged_in, customer):
    _with_address(customer)
    p = _product(stock=2, price=150)
    assert customer_logged_in.post('/api/cart/add', json={'product_id': p.id, 'quantity': 2}).status_code == 200
    r = customer_logged_in.post('/api/cart/checkout', json={'payment_method': 'cod'})
    assert r.get_json()['success'] is True, r.get_json()
    assert r.get_json()['total'] == 300.0
    assert db.session.get(Product, p.id).stock_quantity == 0
    order = Order.query.one()
    assert order.order_number.startswith('ORD')
    assert Transaction.query.filter_by(order_id=order.id).one().transaction_number.startswith('TRX')


def test_checkout_fails_when_stock_ran_out(customer_logged_in, customer):
    _with_address(customer)
    p = _product(stock=2)
    customer_logged_in.post('/api/cart/add', json={'product_id': p.id, 'quantity': 2})
    p.stock_quantity = 1  # someone else bought one meanwhile
    db.session.commit()
    r = customer_logged_in.post('/api/cart/checkout', json={'payment_method': 'cod'})
    assert r.status_code == 400
    assert db.session.get(Product, p.id).stock_quantity == 1


def test_admin_confirm_updates_order_and_blocks_self_cancel(client, customer, admin):
    _with_address(customer)
    p = _product(stock=3)
    login_as(client, customer)
    client.post('/api/cart/add', json={'product_id': p.id, 'quantity': 1})
    client.post('/api/cart/checkout', json={'payment_method': 'gcash', 'gcash_reference': 'REF1'})
    order = Order.query.one()
    txn = Transaction.query.filter_by(order_id=order.id).one()

    login_as(client, admin)
    client.post(f'/admin/payments/{txn.id}/confirm')
    assert db.session.get(Order, order.id).payment_status == 'confirmed'

    # Once the paid order is being prepared, the customer can't cancel it themselves...
    db.session.get(Order, order.id).status = 'processing'
    db.session.commit()
    login_as(client, customer)
    r = client.post(f'/api/order/{order.id}/cancel')
    assert r.status_code == 400 and db.session.get(Order, order.id).status == 'processing'
    # ...but while it is still pending they can, and the payment goes to Refunds.
    db.session.get(Order, order.id).status = 'pending'
    db.session.commit()
    r = client.post(f'/api/order/{order.id}/cancel').get_json()
    assert r['success'] and r['refund_opened']
    from app import Refund
    assert Refund.query.filter_by(transaction_id=txn.id, status='pending').count() == 1
    assert db.session.get(Product, p.id).stock_quantity == 3


def test_admin_can_progress_and_cancel_orders(client, customer, admin):
    _with_address(customer)
    p = _product(stock=3)
    login_as(client, customer)
    client.post('/api/cart/add', json={'product_id': p.id, 'quantity': 2})
    client.post('/api/cart/checkout', json={'payment_method': 'cod'})
    order = Order.query.one()

    login_as(client, admin)
    assert client.get('/admin/orders').status_code == 200
    client.post(f'/admin/orders/{order.id}/status', data={'status': 'processing'})
    assert db.session.get(Order, order.id).status == 'processing'
    client.post(f'/admin/orders/{order.id}/status', data={'status': 'cancelled'})
    assert db.session.get(Order, order.id).status == 'cancelled'
    assert db.session.get(Product, p.id).stock_quantity == 3


# ---- Receipts ----

def test_receipt_only_visible_to_owner_and_admin(app, client, customer, admin):
    name = 'receipt_test.png'
    with open(f"{app.config['RECEIPT_UPLOAD_FOLDER']}/{name}", 'wb') as fh:
        fh.write(b'\x89PNG\r\n\x1a\n')
    txn = Transaction(transaction_number='TRX-R1', user_id=customer.id, amount=10,
                      payment_method='GCash', receipt_image=name)
    stranger = Customer(username='s', email='s@test.local', full_name='Stranger')
    stranger.set_password('strangerpass')
    db.session.add_all([txn, stranger])
    db.session.commit()
    url = f'/receipts/{txn.id}/{name}'

    assert client.get(url).status_code == 302           # not logged in
    login_as(client, stranger)
    assert client.get(url).status_code == 404
    login_as(client, customer)
    assert client.get(url).status_code == 200
    login_as(client, admin)
    assert client.get(url).status_code == 200


# ---- Messages / settings / pages ----

def test_message_new_rejects_arbitrary_role(customer_logged_in):
    r = customer_logged_in.post('/messages/new', json={
        'recipient': 'customer', 'subject': 'hi', 'content': 'hello'})
    assert r.status_code == 400


def test_settings_update_whitelists_keys(admin_logged_in):
    from app import SystemSetting
    r = admin_logged_in.post('/admin/settings/update', json={
        'system_name': 'Shop', 'csrf_token': 'x', 'evil': 'y'})
    assert r.get_json()['success'] is True
    keys = {s.setting_key for s in SystemSetting.query.all()}
    assert 'system_name' in keys and 'csrf_token' not in keys and 'evil' not in keys


def test_admin_pages_render(admin_logged_in):
    for url in ('/admin/payments', '/admin/settings', '/admin/orders', '/admin/users',
                '/admin/analytics', '/admin/dashboard', '/admin/products',
                '/admin/services', '/admin/support', '/admin/messages'):
        assert admin_logged_in.get(url).status_code == 200, url


def test_cli_commands_registered(app):
    assert 'create-admin' in app.cli.commands


def test_init_db_seeds_settings_even_after_migration_flag(app):
    from app import init_db, release_reserved_cart_stock, SystemSetting
    release_reserved_cart_stock()          # writes its flag row first, like upgrade-db
    init_db()
    keys = {s.setting_key for s in SystemSetting.query.all()}
    assert {'gcash_account', 'enable_gcash', 'system_name'} <= keys
    assert Admin.query.count() == 0   # never a default admin
