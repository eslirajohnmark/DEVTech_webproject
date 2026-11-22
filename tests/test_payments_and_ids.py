"""The booking fee paid with the shop's QR code (screenshot required), the bill paid
after the repair with approved extra work added, the shop QR setting, editing a whole
service category, ID front/back photos on the roster, and the order pages.
All people, IDs and payments here are made up."""
from datetime import date, time, timedelta
from decimal import Decimal
from io import BytesIO

from app import (app as flask_app, db, ActivityLog, Booking, Notification, Order, OrderItem, Product,
                 Service, ServiceCategory, SystemSetting, TechnicianEmployee, Transaction,
                 booking_balance, booking_fee_transaction)
from models.technician_models import ApprovalRequest
from tests.conftest import login_as, payment_proof, PROOF_PNG

TOMORROW = (date.today() + timedelta(days=1)).isoformat()


def _service(price=1500, fee=0, name='Screen Fix'):
    cat = ServiceCategory.query.filter_by(name='Repairs').first() or ServiceCategory(name='Repairs', is_active=True)
    db.session.add(cat)
    db.session.flush()
    svc = Service(category_id=cat.id, name=name, price=price, service_fee=fee, is_active=True, device_types='laptop')
    db.session.add(svc)
    db.session.commit()
    return svc


def _book(client, svc, **over):
    data = {'service_id': str(svc.id), 'device_type': 'Laptop', 'booking_date': TOMORROW, 'booking_time': '10:00',
            'problem_description': 'The laptop screen is cracked after it fell off the table', 'in_shop': 'on',
            'accept_terms': 'on', 'payment_method': 'GCash', 'fee_receipt': payment_proof()}
    data.update(over)
    return client.post('/user/service-request', data={k: v for k, v in data.items() if v is not None})


# ---------------------------------------------------------------- booking fee

def test_the_booking_fee_screenshot_must_be_an_image(customer_logged_in):
    svc = _service()
    _book(customer_logged_in, svc, fee_receipt=(BytesIO(b'%PDF-1.4 fake'), 'r.pdf', 'application/pdf'))
    _book(customer_logged_in, svc, fee_receipt=(BytesIO(b'not an image'), 'r.png', 'image/png'))
    assert Booking.query.count() == 0


def test_no_screenshot_is_needed_when_the_fee_is_off(customer_logged_in):
    db.session.add(SystemSetting(setting_key='booking_fee', value='0'))
    db.session.commit()
    _book(customer_logged_in, _service(), fee_receipt=None)
    b = Booking.query.one()
    assert b.booking_fee is None and booking_fee_transaction(b) is None


def test_a_booking_is_approved_only_after_its_fee_is_confirmed(client, customer, admin, technician):
    login_as(client, customer)
    _book(client, _service())
    b = Booking.query.one()
    login_as(client, admin)
    page = client.get('/admin/requests').get_data(as_text=True)
    assert 'Check the booking fee first' in page
    client.post(f'/admin/requests/{b.id}/status', data={'status': 'confirmed', 'technician_id': technician.id})
    assert db.session.get(Booking, b.id).status == 'pending'
    client.post(f'/admin/payments/{booking_fee_transaction(b).id}/confirm')
    client.post(f'/admin/requests/{b.id}/status', data={'status': 'confirmed', 'technician_id': technician.id})
    assert db.session.get(Booking, b.id).status == 'confirmed'


def test_a_price_set_on_diagnosis_still_takes_the_fee_off_the_bill(customer_logged_in, technician):
    svc = _service(price=0, fee=0, name='Diagnosis First')
    _book(customer_logged_in, svc)
    b = Booking.query.one()
    assert b.booking_fee == Decimal('100.00') and b.transaction.amount == Decimal('0.00')
    db.session.add(ApprovalRequest(booking_id=b.id, technician_id=technician.id, findings='Board', proposed_work='Replace board',
                                   additional_cost=900, status='approved', requested_at='2026-11-20 10:00:00'))
    db.session.commit()
    assert booking_balance(b) == Decimal('800.00')           # ₱900 extra less the ₱100 already paid


# ---------------------------------------------------------------- the bill after the repair

def test_approved_extra_work_is_added_to_the_unpaid_bill(client, customer, technician):
    login_as(client, customer)
    _book(client, _service(price=1500, fee=100))
    b = Booking.query.one()
    assert b.transaction.amount == Decimal('1500.00')                        # 1500 + 100 - 100 fee
    b.status, b.technician_id = 'on_hold', technician.id
    a = ApprovalRequest(booking_id=b.id, technician_id=technician.id, findings='Hinge broken',
                        proposed_work='Replace hinge', additional_cost=350, status='pending',
                        requested_at='2026-11-20 10:00:00')
    db.session.add(a)
    db.session.commit()
    r = client.post(f'/api/booking/{b.id}/approval/{a.id}/respond', json={'decision': 'approve'})
    assert r.get_json()['ok'] is True
    b = db.session.get(Booking, b.id)
    assert b.transaction.amount == Decimal('1850.00') and Transaction.query.count() == 2   # no separate charge
    b.status = 'completed'
    db.session.commit()
    page = client.get('/user/transactions').get_data(as_text=True)
    assert 'Extra work you approved: Replace hinge' in page and '₱1,850.00' in page
    assert 'Booking fee already paid' in page and 'Total to pay' in page


# ---------------------------------------------------------------- the shop's payment QR

def test_admin_uploads_the_payment_qr_and_customers_see_it(client, admin, customer):
    login_as(client, admin)
    r = client.post('/admin/settings/payment-qr', content_type='multipart/form-data',
                    data={'payment_qr': (BytesIO(PROOF_PNG), 'qr.png', 'image/png')})
    assert r.status_code == 302
    name = SystemSetting.query.filter_by(setting_key='payment_qr_file').one().value
    assert name.startswith('qr_') and name.endswith('.png')
    client.post('/admin/settings/update', json={'payment_account_name': 'DEVTech Shop',
                                                'payment_account_number': '0917 555 0101'})
    login_as(client, customer)
    assert client.get('/payment-qr').status_code == 200
    page = client.get('/user/book').get_data(as_text=True)
    assert 'src="/payment-qr"' in page and 'DEVTech Shop' in page and '0917 555 0101' in page
    assert flask_app.test_client().get('/payment-qr').status_code == 302               # signed-out: no

    login_as(client, admin)
    client.post('/admin/settings/payment-qr', data={'payment_qr': (BytesIO(b'GIF89a'), 'qr.gif', 'image/gif')},
                content_type='multipart/form-data')
    assert SystemSetting.query.filter_by(setting_key='payment_qr_file').one().value == name   # refused
    client.post('/admin/settings/payment-qr', data={'remove': '1'})
    assert SystemSetting.query.filter_by(setting_key='payment_qr_file').one().value == ''
    login_as(client, customer)
    assert client.get('/payment-qr').status_code == 404


# ---------------------------------------------------------------- edit a whole category

def test_admin_edits_every_price_in_a_category_at_once(admin_logged_in):
    a = _service(price=500, fee=50, name='Mouse Replacement')
    b = _service(price=800, fee=50, name='Keyboard Replacement')
    cat = a.category
    page = admin_logged_in.get('/admin/services').get_data(as_text=True)
    assert 'Edit category &amp; prices' in page and f'name="price_{a.id}"' in page
    r = admin_logged_in.post(f'/admin/categories/{cat.id}', data={
        'name': 'Accessory Replacement', 'icon': 'fa-keyboard', 'description': 'Mice, keyboards and more',
        f'name_{a.id}': 'Mouse Replacement', f'price_{a.id}': '550', f'fee_{a.id}': '75', f'hours_{a.id}': '1',
        f'name_{b.id}': 'Keyboard Swap', f'price_{b.id}': '900', f'fee_{b.id}': '75', f'hours_{b.id}': '2'})
    assert r.status_code == 302
    a, b = db.session.get(Service, a.id), db.session.get(Service, b.id)
    assert (a.price, a.service_fee, b.name, b.price, b.estimated_hours) == (550, 75, 'Keyboard Swap', 900, 2)
    assert db.session.get(ServiceCategory, cat.id).name == 'Accessory Replacement'

    # one bad row: nothing is saved
    admin_logged_in.post(f'/admin/categories/{cat.id}', data={
        'name': 'Accessory Replacement', f'name_{a.id}': 'Mouse Replacement', f'price_{a.id}': '1', f'fee_{a.id}': '0',
        f'name_{b.id}': 'Keyboard Swap', f'price_{b.id}': 'abc', f'fee_{b.id}': '75'})
    assert db.session.get(Service, a.id).price == 550


def test_customers_cannot_edit_a_category(customer_logged_in):
    a = _service(price=500, name='Mouse Replacement')
    customer_logged_in.post(f'/admin/categories/{a.category_id}', data={'name': 'Hacked', f'price_{a.id}': '1'})
    assert db.session.get(Service, a.id).price == 500


# ---------------------------------------------------------------- roster ID photos

def _roster(client, **over):
    data = {'tech_id': 'TECH-0042', 'full_name': 'Maria Santos Cruz', 'birth_date': '1995-05-20',
            'id_type': 'PhilSys National ID', 'id_number': '1234-5678-9012-3456', 'address': '12 Rizal Ave, Tacloban City',
            'id_front': (BytesIO(PROOF_PNG), 'front.png', 'image/png'),
            'id_back': (BytesIO(PROOF_PNG), 'back.png', 'image/png')}
    data.update(over)
    return client.post('/admin/technician-roster', content_type='multipart/form-data',
                       data={k: v for k, v in data.items() if v is not None})


def test_the_roster_needs_both_sides_of_an_id_with_a_back_and_an_address(admin_logged_in):
    r = _roster(admin_logged_in, id_back=None)
    assert r.status_code == 400 and 'details on the back too' in r.get_data(as_text=True)
    assert _roster(admin_logged_in, id_front=None).status_code == 400
    assert _roster(admin_logged_in, address='').status_code == 400
    # a passport has no back
    assert _roster(admin_logged_in, id_type='Passport', id_number='P1234567A', id_back=None).status_code == 302
    rec = TechnicianEmployee.query.one()
    assert rec.id_front_file and rec.id_back_file is None and rec.address == '12 Rizal Ave, Tacloban City'


def test_only_admins_open_roster_id_photos_and_each_view_is_logged(client, admin, customer):
    login_as(client, admin)
    _roster(client)
    rec = TechnicianEmployee.query.one()
    page = client.get('/admin/technician-roster').get_data(as_text=True)
    assert f'/admin/technician-roster/{rec.id}/id/front' in page and f'/admin/technician-roster/{rec.id}/id/back' in page
    r = client.get(f'/admin/technician-roster/{rec.id}/id/back')
    assert r.status_code == 200 and r.headers['Cache-Control'].startswith('no-store')
    assert ActivityLog.query.filter_by(action='id_document_view').count() == 1
    login_as(client, customer)
    assert client.get(f'/admin/technician-roster/{rec.id}/id/front').status_code == 302


# ---------------------------------------------------------------- order pages

def _order(customer, status='processing'):
    p = Product(name='USB Mouse', price=350, stock_quantity=4, is_active=True)
    db.session.add(p)
    db.session.flush()
    o = Order(user_id=customer.id, order_number='ORD-9001', total_amount=700, status=status, payment_method='cod',
              recipient_name='Cara', address_line='1 Rizal St', city='Tacloban')
    db.session.add(o)
    db.session.flush()
    db.session.add(OrderItem(order_id=o.id, product_id=p.id, quantity=2, price=350))
    db.session.commit()
    return o


def test_admin_orders_show_progress_items_and_search(client, admin, customer):
    _order(customer)
    page = login_as(client, admin).get('/admin/orders').get_data(as_text=True)
    assert 'class="ao-card ao-card--processing"' in page and 'id="aoSearch"' in page
    assert 'is-done is-now">Preparing' in page and '2×</span> USB Mouse' in page


def test_my_orders_cards_track_each_order(customer_logged_in, customer):
    _order(customer, status='out_for_delivery')
    page = customer_logged_in.get('/user/orders').get_data(as_text=True)
    assert 'ordm-track' in page and 'is-done is-now"><span>On the way' in page
    assert '<span>2×</span> USB Mouse' in page and 'on the way' in page


def test_customer_sign_in_uses_the_portal_layout(client):
    page = client.get('/login').get_data(as_text=True)
    assert 'data-portal="customer"' in page and 'staff-login.css' in page and 'Create an account' in page


# ---------------------------------------------------------------- booking fee in Services & Prices

def test_admin_changes_the_booking_fee_in_services_and_prices(client, admin, customer):
    login_as(client, admin)
    page = client.get('/admin/services').get_data(as_text=True)
    assert 'id="bookingFee"' in page and 'name="booking_fee"' in page and 'value="100"' in page
    r = client.post('/admin/services/booking-fee', data={'booking_fee': '150'})
    assert r.status_code == 302
    assert SystemSetting.query.filter_by(setting_key='booking_fee').one().value == '150'
    for bad in ('-5', '99.5', 'abc', '6000', ''):
        client.post('/admin/services/booking-fee', data={'booking_fee': bad})
        assert SystemSetting.query.filter_by(setting_key='booking_fee').one().value == '150', bad
    assert 'value="150"' in client.get('/admin/settings').get_data(as_text=True)     # one setting, both pages
    login_as(client, customer)
    assert '₱150.00' in client.get('/user/book').get_data(as_text=True)
    client.post('/admin/services/booking-fee', data={'booking_fee': '1'})            # customers can't change it
    assert SystemSetting.query.filter_by(setting_key='booking_fee').one().value == '150'
    login_as(client, admin)
    client.post('/admin/services/booking-fee', data={'booking_fee': '0'})            # 0 turns it off
    login_as(client, customer)
    _book(client, _service(), fee_receipt=None)
    assert Booking.query.one().booking_fee is None


# ---------------------------------------------------------------- live updates (customer side)

def test_customer_pages_update_when_the_shop_changes_prices_or_the_fee(app, customer):
    from app import _live_stamp
    svc = _service()
    before = _live_stamp(customer)
    svc.price = 1999
    db.session.commit()
    after_price = _live_stamp(customer)
    assert after_price != before
    row = SystemSetting(setting_key='booking_fee', value='120')
    db.session.add(row)
    db.session.commit()
    assert _live_stamp(customer) != after_price


def test_monitor_and_notifications_refresh_by_themselves(customer_logged_in):
    for url in ('/user/monitor-device', '/notifications'):
        page = customer_logged_in.get(url, follow_redirects=True).get_data(as_text=True)
        assert 'onclick="window.location.reload()"' not in page and 'id="refreshBtn"' not in page, url
    page = customer_logged_in.get('/notifications').get_data(as_text=True)
    assert 'user-live-badge' in page and 'js/live.js' in page
