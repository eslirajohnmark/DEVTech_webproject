"""Shop (sale / low price / hot, add to cart, GCash QR + screenshot checkout,
delivery estimate) and My Orders (tracking, cancel with full GCash refund)."""
import io
import os
from datetime import datetime
from decimal import Decimal

from app import (app as flask_app, db, Product, Order, OrderItem, Transaction, Refund, DeliveryRider,
                 SystemSetting, CartItem)
from services import delivery_eta, gcash_qr
from tests.conftest import login_as

PNG = b'\x89PNG\r\n\x1a\n' + b'0' * 64
REFUND_TO = '09171234567'


def _product(name='SSD 512GB', price=1000, stock=10, sale=None, category='storage'):
    p = Product(name=name, price=price, sale_price=sale, stock_quantity=stock, is_active=True, category=category)
    db.session.add(p)
    db.session.commit()
    return p


def _with_address(user, lat=None, lng=None):
    user.full_name = user.full_name or 'Cara Customer'
    user.phone, user.address, user.city = '09170000000', '1 Street', 'Cebu City'
    user.province, user.postal_code = 'Cebu', '6000'
    user.latitude, user.longitude = lat, lng
    db.session.commit()


def _setting(key, value):
    row = SystemSetting.query.filter_by(setting_key=key).first()
    if row:
        row.value = value
    else:
        db.session.add(SystemSetting(setting_key=key, value=value))
    db.session.commit()


def _shop_qr():
    acct = gcash_qr._join([('00', 'ph.ppmi.p2p'), ('01', 'DEMO12345'), ('04', 'DEMO')])
    body = gcash_qr._join([('00', '01'), ('01', '11'), ('26', acct), ('53', '608'), ('58', 'PH'),
                           ('59', 'DEVTech Demo'), ('60', 'Cebu City')]) + '6304'
    return body + gcash_qr.crc16_ccitt(body)


def _gcash_checkout(client, proof=PNG, name='paid.png'):
    data = {'payment_method': 'gcash'}
    if proof is not None:
        data['payment_proof'] = (io.BytesIO(proof), name)
    return client.post('/api/cart/checkout', data=data, content_type='multipart/form-data')


# ------------------------------------------------------------------ GCash QR

def test_gcash_qr_gets_the_exact_amount_and_a_valid_checksum():
    dyn = gcash_qr.with_amount(_shop_qr(), Decimal('2799.5'))
    fields = dict(gcash_qr.parse_tlv(dyn))
    assert fields['54'] == '2799.50' and fields['01'] == '12' and fields['53'] == '608'
    assert gcash_qr.validate_payload(dyn) == dyn                       # CRC recomputed correctly
    assert gcash_qr.qr_svg_data_uri(dyn).startswith('data:image/svg+xml')


def test_gcash_qr_rejects_damaged_or_foreign_codes():
    good = _shop_qr()
    for bad in (good[:-1] + ('0' if good[-1] != '0' else '1'), 'https://example.com', ''):
        try:
            gcash_qr.validate_payload(bad)
            assert False, bad
        except gcash_qr.InvalidQrPayload:
            pass


def test_admin_can_save_only_a_real_gcash_qr(admin_logged_in):
    r = admin_logged_in.post('/admin/settings/update', json={'gcash_qr_payload': '000201nonsense'})
    assert r.status_code == 400
    r = admin_logged_in.post('/admin/settings/update', json={'gcash_qr_payload': _shop_qr(),
                                                            'shop_latitude': '10.3157', 'shop_longitude': '123.8854'})
    assert r.get_json()['success']
    assert SystemSetting.query.filter_by(setting_key='gcash_qr_payload').one().value == _shop_qr()


# ------------------------------------------------------------------ delivery estimate

def _utc(text):
    return datetime.strptime(text, '%Y-%m-%d %H:%M')


def test_delivery_estimate_follows_hours_riders_and_distance():
    friday_10am = _utc('2026-10-30 02:00')                              # 10:00 in the Philippines
    same_day = delivery_eta.estimate(friday_10am, 5, riders_on_duty=2, orders_ahead=0)
    assert same_day['method'] == 'rider' and same_day['label'].startswith('Today')
    late = delivery_eta.estimate(_utc('2026-10-30 09:00'), 5, 1, 0)       # Friday 5 PM -> Saturday
    assert late['label'].startswith('Tomorrow') and '4 PM' in late['note']
    saturday_late = delivery_eta.estimate(_utc('2026-10-31 09:00'), 5, 1, 0)
    assert saturday_late['earliest'].weekday() == 0                     # closed Sunday -> Monday
    no_rider = delivery_eta.estimate(friday_10am, 5, 0, 0)
    assert no_rider['label'].startswith('Tomorrow') and 'rider' in no_rider['note']
    busy = delivery_eta.estimate(friday_10am, 5, 1, 6)
    assert busy['earliest'] > same_day['earliest']                      # a queue pushes it later
    far = delivery_eta.estimate(friday_10am, 120, 2, 0)
    assert far['method'] == 'courier'


def test_distance_from_pins_or_city():
    shop = {'lat': 10.3157, 'lng': 123.8854, 'city': 'Cebu City', 'province': 'Cebu'}
    km, basis = delivery_eta.road_distance_km(shop, {'lat': 10.2970, 'lng': 123.8960})
    assert basis == 'pin' and 2 < km < 5
    assert delivery_eta.road_distance_km(shop, {'city': 'cebu', 'province': 'Cebu'}) == (8, 'city')
    assert delivery_eta.road_distance_km(shop, {'city': 'Davao', 'province': 'Davao'})[1] == 'unknown'


# ------------------------------------------------------------------ shop page and cart

def test_shop_shows_sale_hot_low_price_and_banner(customer_logged_in, customer):
    cheap = _product('USB Mouse', price=300, category='accessory')
    _product('RAM 8GB', price=1500, category='memory')
    _product('SSD 1TB', price=4000)
    sale = _product('Laptop Battery', price=2000, sale=1500, category='battery')
    hot = _product('RTX 3060', price=12000, category='gpu')
    order = Order(customer_id=customer.id, order_number='ORD-HOT', total_amount=36000, status='completed')
    db.session.add(order)
    db.session.flush()
    db.session.add(OrderItem(order_id=order.id, product_id=hot.id, quantity=3, price=12000))
    db.session.commit()

    html = customer_logged_in.get('/user/shop').get_data(as_text=True)
    assert 'Up to 25% off on 1 item' in html                           # banner
    assert 'Sale −25%' in html and '₱1,500.00' in html and '<s class="shop-was">₱2,000.00</s>' in html
    assert f'data-id="{hot.id}"' in html and 'data-hot="1"' in html and '3 sold this month' in html
    assert f'data-id="{cheap.id}"' in html and 'data-low="1"' in html
    assert sale.effective_price == Decimal('1500.00')


def test_cart_and_checkout_charge_the_sale_price(customer_logged_in, customer):
    _with_address(customer)
    p = _product(price=2000, sale=1500)
    r = customer_logged_in.post('/api/cart/add', json={'product_id': p.id, 'quantity': 2}).get_json()
    assert r['success'] and r['cart_count'] == 1
    cart = customer_logged_in.get('/api/cart').get_json()
    assert cart['total'] == 3000 and cart['items'][0]['on_sale'] and cart['items'][0]['regular_price'] == 2000
    out = customer_logged_in.post('/api/cart/checkout', json={'payment_method': 'cod'}).get_json()
    assert out['success'] and out['total'] == 3000 and out['eta']
    order = Order.query.one()
    assert order.items[0].price == Decimal('1500.00') and order.eta_from and order.eta_to


def test_adding_more_than_the_stock_is_refused(customer_logged_in):
    p = _product(stock=2)
    assert customer_logged_in.post('/api/cart/add', json={'product_id': p.id, 'quantity': 2}).status_code == 200
    r = customer_logged_in.post('/api/cart/add', json={'product_id': p.id, 'quantity': 1})
    assert r.status_code == 400 and 'Only 0 more' in r.get_json()['message']


# ------------------------------------------------------------------ GCash checkout

def test_checkout_summary_has_the_qr_for_the_exact_total(customer_logged_in, customer):
    _with_address(customer)
    _setting('gcash_qr_payload', _shop_qr())
    _setting('gcash_account', '0917 555 0000')
    p = _product(price=1250.5)
    customer_logged_in.post('/api/cart/add', json={'product_id': p.id, 'quantity': 2})
    data = customer_logged_in.get('/api/checkout/summary').get_json()
    assert data['total'] == 2501 and data['gcash']['amount'] == '2,501.00'
    assert data['gcash']['qr'].startswith('data:image/svg+xml') and data['gcash']['account'] == '0917 555 0000'
    assert data['eta']['label']

    _setting('gcash_qr_payload', '')
    assert customer_logged_in.get('/api/checkout/summary').get_json()['gcash']['qr'] is None


def test_gcash_checkout_needs_a_payment_screenshot(customer_logged_in, customer):
    _with_address(customer)
    p = _product()
    customer_logged_in.post('/api/cart/add', json={'product_id': p.id, 'quantity': 1})
    r = _gcash_checkout(customer_logged_in, proof=None)
    assert r.status_code == 400 and r.get_json()['error'] == 'proof_required'
    r = _gcash_checkout(customer_logged_in, proof=b'not an image', name='paid.png')
    assert r.status_code == 400
    r = _gcash_checkout(customer_logged_in, proof=b'%PDF-1.4', name='paid.pdf')
    assert r.status_code == 400
    assert Order.query.count() == 0 and db.session.get(Product, p.id).stock_quantity == 10

    r = _gcash_checkout(customer_logged_in)
    assert r.get_json()['success']
    txn = Transaction.query.one()
    assert txn.payment_status == 'pending' and txn.receipt_image
    assert os.path.isfile(os.path.join(flask_app.config['RECEIPT_UPLOAD_FOLDER'], txn.receipt_image))


def test_admin_sees_the_screenshot_on_payments(client, customer, admin):
    _with_address(customer)
    login_as(client, customer)
    client.post('/api/cart/add', json={'product_id': _product().id, 'quantity': 1})
    _gcash_checkout(client)
    txn = Transaction.query.one()
    login_as(client, admin)
    assert f'/receipts/{txn.id}/' in client.get(f'/admin/payments/{txn.id}').get_data(as_text=True) or \
        client.get(f'/receipts/{txn.id}/{txn.receipt_image}').status_code == 200


# ------------------------------------------------------------------ riders, dispatch, tracking

def test_dispatch_needs_a_rider_on_duty_and_a_confirmed_gcash_payment(client, customer, admin):
    _with_address(customer)
    login_as(client, customer)
    client.post('/api/cart/add', json={'product_id': _product().id, 'quantity': 1})
    _gcash_checkout(client)
    order, txn = Order.query.one(), Transaction.query.one()

    login_as(client, admin)
    client.post('/admin/riders', data={'name': 'Rico Rider', 'phone': '0917 111 2222'})
    rider = DeliveryRider.query.one()
    assert rider.on_duty
    client.post(f'/admin/orders/{order.id}/status', data={'status': 'processing'})
    client.post(f'/admin/orders/{order.id}/status', data={'status': 'out_for_delivery', 'rider_id': rider.id})
    assert db.session.get(Order, order.id).status == 'processing'      # GCash not confirmed yet

    client.post(f'/admin/payments/{txn.id}/confirm')
    client.post(f'/admin/riders/{rider.id}/duty')                      # off duty
    client.post(f'/admin/orders/{order.id}/status', data={'status': 'out_for_delivery', 'rider_id': rider.id})
    assert db.session.get(Order, order.id).status == 'processing'
    client.post(f'/admin/riders/{rider.id}/duty')                      # back on duty
    client.post(f'/admin/orders/{order.id}/status', data={'status': 'out_for_delivery', 'rider_id': rider.id})
    o = db.session.get(Order, order.id)
    assert o.status == 'out_for_delivery' and o.rider_id == rider.id and o.dispatched_at and o.eta_to

    login_as(client, customer)
    detail = client.get(f'/api/order/{order.id}').get_json()
    assert detail['status_label'] == 'Out for delivery' and detail['rider']['name'] == 'Rico Rider'
    assert detail['eta']['label'] and not detail['can_cancel'] and 'on its way' in detail['cancel_blocked_reason']
    keys = [s['key'] for s in detail['tracking']]
    assert keys == ['placed', 'payment', 'processing', 'out_for_delivery', 'completed']
    assert [s['done'] for s in detail['tracking']] == [True, True, True, True, False]
    assert client.post(f'/api/order/{order.id}/cancel', json={}).status_code == 400

    login_as(client, admin)
    client.post(f'/admin/orders/{order.id}/status', data={'status': 'completed'})
    assert db.session.get(Order, order.id).delivered_at
    login_as(client, customer)
    detail = client.get(f'/api/order/{order.id}').get_json()
    assert detail['status_label'] == 'Delivered' and detail['eta'] is None and detail['delivered_at']
    assert 'Delivered' in client.get('/user/orders').get_data(as_text=True)


# ------------------------------------------------------------------ cancel and refund

def test_cancelling_a_gcash_paid_order_refunds_the_full_amount(client, customer, admin):
    _with_address(customer)
    login_as(client, customer)
    p = _product(price=1999, stock=5)
    client.post('/api/cart/add', json={'product_id': p.id, 'quantity': 2})
    _gcash_checkout(client)
    order = Order.query.one()

    detail = client.get(f'/api/order/{order.id}').get_json()
    assert detail['can_cancel'] and detail['refund_on_cancel'] == 3998
    r = client.post(f'/api/order/{order.id}/cancel', json={'refund_to': '12345'})
    assert r.status_code == 400 and r.get_json()['error'] == 'refund_number_required'
    r = client.post(f'/api/order/{order.id}/cancel', json={'refund_to': '0917-123-4567'}).get_json()
    assert r['success'] and r['refund_opened'] and '₱3,998.00' in r['message']

    refund = Refund.query.one()
    assert refund.amount == Decimal('3998.00') and refund.payout_account == REFUND_TO
    assert db.session.get(Product, p.id).stock_quantity == 5
    detail = client.get(f'/api/order/{order.id}').get_json()
    assert detail['status'] == 'cancelled' and detail['refunds'][0]['payout_account'] == REFUND_TO
    assert detail['tracking'][-1]['key'] == 'cancelled'

    # The admin must send back exactly what was paid.
    login_as(client, admin)
    assert REFUND_TO in client.get('/admin/refunds').get_data(as_text=True)
    client.post(f'/admin/refunds/{refund.id}/complete', data={'method': 'GCash', 'reference': 'R1', 'amount': '1000'})
    assert db.session.get(Refund, refund.id).status == 'pending'
    client.post(f'/admin/refunds/{refund.id}/complete', data={'method': 'GCash', 'reference': 'R1', 'amount': '3998.00'})
    assert db.session.get(Refund, refund.id).status == 'refunded'
    login_as(client, customer)
    assert client.get(f'/api/order/{order.id}').get_json()['refunds'][0]['status'] == 'refunded'


def test_cancelling_an_unpaid_cod_order_needs_no_refund_number(customer_logged_in, customer):
    _with_address(customer)
    customer_logged_in.post('/api/cart/add', json={'product_id': _product().id, 'quantity': 1})
    customer_logged_in.post('/api/cart/checkout', json={'payment_method': 'cod'})
    order = Order.query.one()
    assert customer_logged_in.get(f'/api/order/{order.id}').get_json()['refund_on_cancel'] == 0
    r = customer_logged_in.post(f'/api/order/{order.id}/cancel', json={}).get_json()
    assert r['success'] and not r['refund_opened'] and Refund.query.count() == 0


def test_order_detail_survives_a_removed_product(customer_logged_in, customer):
    _with_address(customer)
    p = _product()
    customer_logged_in.post('/api/cart/add', json={'product_id': p.id, 'quantity': 1})
    customer_logged_in.post('/api/cart/checkout', json={'payment_method': 'cod'})
    order = Order.query.one()
    OrderItem.query.filter_by(order_id=order.id).update({'product_id': 999999})
    db.session.commit()
    r = customer_logged_in.get(f'/api/order/{order.id}')
    assert r.status_code == 200 and r.get_json()['items'][0]['product_name'] == 'Removed product'


def test_admin_product_sale_price_must_be_lower(admin_logged_in):
    p = _product(price=1000)
    form = {'name': p.name, 'price': '1000', 'stock_quantity': '10', 'sale_price': '1200'}
    admin_logged_in.post(f'/admin/products/{p.id}', data=form)
    assert db.session.get(Product, p.id).sale_price is None
    form['sale_price'] = '850'
    admin_logged_in.post(f'/admin/products/{p.id}', data=form)
    assert db.session.get(Product, p.id).discount_percent == 15
    form['sale_price'] = ''
    admin_logged_in.post(f'/admin/products/{p.id}', data=form)
    assert not db.session.get(Product, p.id).on_sale
