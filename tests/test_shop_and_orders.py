"""Shop (sale / low price / hot, add to cart, checkout, delivery estimate) and
My Orders (tracking, cancel with a full refund). QR Ph payments are covered in
test_paymongo.py; orders paid by GCash before it was removed still get refunded."""
from datetime import datetime
from decimal import Decimal

from app import (app as flask_app, db, Product, Order, OrderItem, Transaction, Refund, DeliveryRider,
                 SystemSetting, CartItem)
from services import delivery_eta
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


def _order(customer, method, price=1000, qty=1, receipt=None):
    """An order placed earlier with the given payment method (GCash ones are from
    before GCash was removed; receipt = the screenshot the customer sent)."""
    _with_address(customer)
    p = _product(price=price, stock=10)
    n = Order.query.count() + 1
    o = Order(customer_id=customer.id, order_number=f'ORD-T{n}', total_amount=price * qty, status='pending',
              payment_method=method, payment_status='pending', recipient_name='Cara Customer',
              recipient_phone='09170000000', address_line='1 Street', city='Cebu City', province='Cebu', postal_code='6000')
    db.session.add(o)
    db.session.flush()
    db.session.add(OrderItem(order_id=o.id, product_id=p.id, quantity=qty, price=price))
    p.stock_quantity -= qty
    t = Transaction(transaction_number=f'TRX-T{n}', order_id=o.id, customer_id=customer.id, amount=price * qty,
                    payment_method=method, payment_status='pending', receipt_image=receipt)
    db.session.add(t)
    db.session.commit()
    return o, t, p


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

def test_checkout_summary_has_the_total_and_delivery_estimate(customer_logged_in, customer):
    _with_address(customer)
    p = _product(price=1250.5)
    customer_logged_in.post('/api/cart/add', json={'product_id': p.id, 'quantity': 2})
    data = customer_logged_in.get('/api/checkout/summary').get_json()
    assert data['total'] == 2501 and data['eta']['label'] and 'gcash' not in data


def test_gcash_is_no_longer_a_checkout_option(customer_logged_in, customer):
    _with_address(customer)
    p = _product()
    customer_logged_in.post('/api/cart/add', json={'product_id': p.id, 'quantity': 1})
    r = customer_logged_in.post('/api/cart/checkout', json={'payment_method': 'gcash'})
    assert r.status_code == 400 and Order.query.count() == 0
    html = customer_logged_in.get('/user/shop').get_data(as_text=True)
    assert 'value="gcash"' not in html and 'payment_proof' not in html
    assert customer_logged_in.post('/api/cart/checkout', json={'payment_method': 'cod'}).get_json()['success']


# ------------------------------------------------------------------ riders, dispatch, tracking

def test_dispatch_needs_a_rider_on_duty_and_a_confirmed_online_payment(client, customer, admin):
    order, txn, _ = _order(customer, 'paymongo')

    login_as(client, admin)
    client.post('/admin/riders', data={'name': 'Rico Rider', 'phone': '0917 111 2222'})
    rider = DeliveryRider.query.one()
    assert rider.on_duty
    client.post(f'/admin/orders/{order.id}/status', data={'status': 'processing'})
    client.post(f'/admin/orders/{order.id}/status', data={'status': 'out_for_delivery', 'rider_id': rider.id})
    assert db.session.get(Order, order.id).status == 'processing'      # QR payment not received yet

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

def test_cancelling_an_old_gcash_paid_order_refunds_the_full_amount(client, customer, admin):
    order, _, p = _order(customer, 'gcash', price=1999, qty=2, receipt='receipt_old.png')
    login_as(client, customer)

    detail = client.get(f'/api/order/{order.id}').get_json()
    assert detail['can_cancel'] and detail['refund_on_cancel'] == 3998
    r = client.post(f'/api/order/{order.id}/cancel', json={'refund_to': '12345'})
    assert r.status_code == 400 and r.get_json()['error'] == 'refund_number_required'
    r = client.post(f'/api/order/{order.id}/cancel', json={'refund_to': '0917-123-4567'}).get_json()
    assert r['success'] and r['refund_opened'] and '₱3,998.00' in r['message']

    refund = Refund.query.one()
    assert refund.amount == Decimal('3998.00') and refund.payout_account == REFUND_TO
    assert db.session.get(Product, p.id).stock_quantity == 10
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
