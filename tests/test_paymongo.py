"""Online payment through PayMongo, with PayMongo's API faked: QR Ph shown on our
own page (the main way to pay), the hosted card / e-wallet page (fallback),
confirming only what PayMongo says was paid, the signed webhook, and full
automatic refunds when a paid order is cancelled."""
import hashlib
import hmac
import json
import time
from decimal import Decimal

import pytest

from app import app as flask_app, db, Product, Order, Transaction, Refund
from services import paymongo_service
from tests.conftest import login_as


class FakePaymongo:
    """Stands in for PayMongo's REST API (services.paymongo_service._request)."""

    def __init__(self):
        self.sessions, self.intents, self.calls, self.fail_refund = {}, {}, [], False

    def __call__(self, app, method, path, payload=None):
        self.calls.append((method, path))
        if method == 'POST' and path == '/checkout_sessions':
            sid = f'cs_test_{len(self.sessions) + 1}'
            attrs = dict(payload['data']['attributes'], status='active', payments=[],
                         checkout_url=f'https://checkout.paymongo.com/{sid}')
            self.sessions[sid] = attrs
            return {'data': {'id': sid, 'type': 'checkout_session', 'attributes': attrs}}
        if method == 'GET' and path.startswith('/checkout_sessions/'):
            return {'data': {'id': path.rsplit('/', 1)[1], 'attributes': self.sessions[path.rsplit('/', 1)[1]]}}
        if method == 'POST' and path.endswith('/expire'):
            self.sessions[path.split('/')[2]]['status'] = 'expired'
            return {'data': {}}
        if method == 'POST' and path == '/payment_intents':
            pid = f'pi_test_{len(self.intents) + 1}'
            self.intents[pid] = dict(payload['data']['attributes'], status='awaiting_payment_method', payments=[])
            return {'data': {'id': pid, 'attributes': self.intents[pid]}}
        if method == 'POST' and path == '/payment_methods':
            assert payload['data']['attributes']['type'] == 'qrph'
            return {'data': {'id': 'pm_test_qr', 'attributes': {}}}
        if method == 'POST' and path.endswith('/attach'):
            pid = path.split('/')[2]
            self.intents[pid].update(status='awaiting_next_action', next_action={'type': 'consume_qr', 'code': {
                'image_url': 'data:image/png;base64,QR' + pid, 'expires_at': int(time.time()) + 1800,
                'test_url': f'https://test.paymongo.com/qr/{pid}'}})
            return {'data': {'id': pid, 'attributes': self.intents[pid]}}
        if method == 'GET' and path.startswith('/payment_intents/'):
            pid = path.rsplit('/', 1)[1]
            return {'data': {'id': pid, 'attributes': self.intents[pid]}}
        if method == 'POST' and path == '/refunds':
            if self.fail_refund:
                raise paymongo_service.PaymongoError('PayMongo rejected the request.', 400, {'errors': []})
            return {'data': {'id': 'ref_test_1', 'attributes': {'status': 'pending'}}}
        raise AssertionError(f'unexpected PayMongo call {method} {path}')

    def pay(self, sid, centavos=None):
        attrs = self.sessions[sid]
        amount = centavos if centavos is not None else attrs['line_items'][0]['amount']
        attrs['payments'] = [{'id': 'pay_test_1', 'attributes': {'status': 'paid', 'amount': amount}}]

    def scan_and_pay(self, pid, centavos=None):
        attrs = self.intents[pid]
        attrs['status'] = 'succeeded'
        attrs['payments'] = [{'id': 'pay_qr_1', 'attributes': {'status': 'paid',
                                                              'amount': centavos if centavos is not None else attrs['amount']}}]


@pytest.fixture
def paymongo(app, monkeypatch):
    fake = FakePaymongo()
    monkeypatch.setattr(paymongo_service, '_request', fake)
    flask_app.config.update(PAYMONGO_ENABLED=True, PAYMONGO_SECRET_KEY='sk_test_dummy', PAYMONGO_WEBHOOK_SECRET='')
    yield fake
    flask_app.config.update(PAYMONGO_ENABLED=False, PAYMONGO_WEBHOOK_SECRET='')


def _with_address(user):
    user.full_name = user.full_name or 'Cara Customer'
    user.phone, user.address, user.city = '09170000000', '1 Street', 'Cebu City'
    user.province, user.postal_code = 'Cebu', '6000'
    db.session.commit()


def _online_order(client, customer, price=1499.5, qty=2):
    _with_address(customer)
    login_as(client, customer)
    p = Product(name='SSD 512GB', price=price, stock_quantity=10, is_active=True)
    db.session.add(p)
    db.session.commit()
    client.post('/api/cart/add', json={'product_id': p.id, 'quantity': qty})
    return client.post('/api/cart/checkout', data={'payment_method': 'paymongo'},
                       content_type='multipart/form-data').get_json(), p


# ------------------------------------------------------------------ QR Ph (main way to pay)

def test_qr_checkout_shows_a_qr_code_for_the_exact_amount(client, customer, paymongo):
    out, _ = _online_order(client, customer)
    txn = Transaction.query.one()
    assert out['success'] and out['transaction_id'] == txn.id and txn.payment_method == 'paymongo'
    qr = client.post(f'/api/payments/{txn.id}/qr').get_json()
    assert qr['status'] == 'pending' and qr['qr'].startswith('data:image/png') and qr['amount'] == '2,999.00'
    assert qr['test_url'] and qr['card_url'].endswith(f'/user/payments/{txn.id}/paymongo')
    intent = paymongo.intents[db.session.get(Transaction, txn.id).paymongo_intent_id]
    assert intent['amount'] == 299900 and intent['payment_method_allowed'] == ['qrph']


def test_the_same_qr_is_reused_until_it_expires(client, customer, paymongo):
    _online_order(client, customer)
    txn = Transaction.query.one()
    first = client.post(f'/api/payments/{txn.id}/qr').get_json()['qr']
    assert client.post(f'/api/payments/{txn.id}/qr').get_json()['qr'] == first and len(paymongo.intents) == 1
    paymongo.intents['pi_test_1']['next_action']['code']['expires_at'] = int(time.time()) - 5
    assert client.post(f'/api/payments/{txn.id}/qr').get_json()['qr'] != first and len(paymongo.intents) == 2


def test_status_turns_paid_once_the_qr_is_paid(client, customer, paymongo):
    _online_order(client, customer)
    txn = Transaction.query.one()
    client.post(f'/api/payments/{txn.id}/qr')
    assert client.get(f'/api/payments/{txn.id}/status').get_json()['status'] == 'pending'
    paymongo.scan_and_pay('pi_test_1')
    assert client.get(f'/api/payments/{txn.id}/status').get_json()['status'] == 'paid'
    t = db.session.get(Transaction, txn.id)
    assert (t.payment_status, t.paymongo_payment_id) == ('confirmed', 'pay_qr_1')
    assert db.session.get(Order, t.order_id).payment_status == 'confirmed'


def test_a_wrong_qr_amount_is_never_confirmed(client, customer, paymongo):
    _online_order(client, customer)
    txn = Transaction.query.one()
    client.post(f'/api/payments/{txn.id}/qr')
    paymongo.scan_and_pay('pi_test_1', centavos=100)
    assert client.get(f'/api/payments/{txn.id}/status').get_json()['status'] == 'pending'


def test_qr_is_refused_when_online_payment_is_off(client, customer, app):
    _with_address(customer)
    login_as(client, customer)
    r = client.post('/api/cart/checkout', data={'payment_method': 'paymongo'}, content_type='multipart/form-data')
    assert r.status_code == 400


# ------------------------------------------------------------------ hosted page (card / e-wallet fallback)

def test_card_fallback_opens_paymongos_page_and_reuses_it(client, customer, paymongo):
    _online_order(client, customer)
    txn = Transaction.query.one()
    r = client.post(f'/user/payments/{txn.id}/paymongo')
    assert r.status_code == 302 and r.headers['Location'] == 'https://checkout.paymongo.com/cs_test_1'
    assert client.post(f'/user/payments/{txn.id}/paymongo').headers['Location'] == 'https://checkout.paymongo.com/cs_test_1'
    sent = paymongo.sessions['cs_test_1']
    assert sent['line_items'][0]['amount'] == 299900 and sent['reference_number'] == txn.transaction_number
    assert sent['success_url'].endswith(f'/paymongo/return/{txn.id}')


def test_return_page_confirms_only_after_paymongo_says_paid(client, customer, paymongo):
    _online_order(client, customer)
    txn = Transaction.query.one()
    client.post(f'/user/payments/{txn.id}/paymongo')
    client.get(f'/paymongo/return/{txn.id}')                              # came back without paying
    assert db.session.get(Transaction, txn.id).payment_status == 'pending'
    paymongo.pay('cs_test_1')
    r = client.get(f'/paymongo/return/{txn.id}')
    assert r.status_code == 302 and 'placed=' in r.headers['Location']
    assert db.session.get(Transaction, txn.id).payment_status == 'confirmed'


def test_someone_else_cannot_pay_or_check_another_customers_payment(client, customer, paymongo):
    from app import Customer
    _online_order(client, customer)
    txn = Transaction.query.one()
    other = Customer(username='other', email='other@x.test', full_name='Other', is_active=True)
    other.set_password('pass12345')
    db.session.add(other)
    db.session.commit()
    login_as(client, other)
    assert client.get(f'/paymongo/return/{txn.id}').status_code == 404
    assert client.post(f'/user/payments/{txn.id}/paymongo').status_code == 404
    assert client.post(f'/api/payments/{txn.id}/qr').status_code == 404
    assert client.get(f'/api/payments/{txn.id}/status').status_code == 404


# ------------------------------------------------------------------ webhook

def _event(kind, resource):
    return {'data': {'id': 'evt_1', 'type': 'event', 'attributes': {'type': kind, 'livemode': False, 'data': resource}}}


def _checkout_paid(reference, amount):
    return _event('checkout_session.payment.paid', {'id': 'cs_test_1', 'type': 'checkout_session', 'attributes': {
        'reference_number': reference, 'payments': [{'id': 'pay_hook_1', 'attributes': {'status': 'paid', 'amount': amount}}]}})


def _signed(body, secret, ts=None):
    ts = ts or int(time.time())
    sig = hmac.new(secret.encode(), f'{ts}.'.encode() + body, hashlib.sha256).hexdigest()
    return f't={ts},te={sig},li='


def test_signed_webhook_confirms_once_and_needs_no_csrf_token(client, customer, paymongo):
    _online_order(client, customer)
    txn = Transaction.query.one()
    flask_app.config.update(PAYMONGO_WEBHOOK_SECRET='whsk_test', WTF_CSRF_ENABLED=True)
    try:
        body = json.dumps(_checkout_paid(txn.transaction_number, 299900)).encode()
        assert client.post('/paymongo/webhook', data=body, content_type='application/json',
                           headers={'Paymongo-Signature': 'bad'}).status_code == 400
        old = _signed(body, 'whsk_test', ts=int(time.time()) - 3600)          # replayed hour-old event
        assert client.post('/paymongo/webhook', data=body, content_type='application/json',
                           headers={'Paymongo-Signature': old}).status_code == 400
        assert db.session.get(Transaction, txn.id).payment_status == 'pending'
        r = client.post('/paymongo/webhook', data=body, content_type='application/json',
                        headers={'Paymongo-Signature': _signed(body, 'whsk_test')})
        assert r.status_code == 200 and r.get_json()['result'] == 'confirmed'
        again = client.post('/paymongo/webhook', data=body, content_type='application/json',
                            headers={'Paymongo-Signature': _signed(body, 'whsk_test')})
        assert again.get_json()['result'] == 'already'
    finally:
        flask_app.config.update(PAYMONGO_WEBHOOK_SECRET='', WTF_CSRF_ENABLED=False)


def test_qr_payment_webhook_finds_the_payment_by_its_intent(client, customer, paymongo):
    _online_order(client, customer)
    txn = Transaction.query.one()
    client.post(f'/api/payments/{txn.id}/qr')
    body = json.dumps(_event('payment.paid', {'id': 'pay_qr_hook', 'type': 'payment', 'attributes': {
        'status': 'paid', 'amount': 299900, 'payment_intent_id': 'pi_test_1'}})).encode()
    r = client.post('/paymongo/webhook', data=body, content_type='application/json')
    assert r.get_json()['result'] == 'confirmed'
    assert db.session.get(Transaction, txn.id).paymongo_payment_id == 'pay_qr_hook'


def test_webhook_ignores_live_events_on_a_test_setup(client, customer, paymongo):
    _online_order(client, customer)
    txn = Transaction.query.one()
    event = _checkout_paid(txn.transaction_number, 299900)
    event['data']['attributes']['livemode'] = True
    assert client.post('/paymongo/webhook', data=json.dumps(event).encode(),
                       content_type='application/json').get_json()['ignored']
    assert db.session.get(Transaction, txn.id).payment_status == 'pending'


# ------------------------------------------------------------------ cancel and refund

def test_cancelling_a_qr_paid_order_refunds_it_in_full_automatically(client, customer, paymongo):
    _, p = _online_order(client, customer)
    order, txn = Order.query.one(), Transaction.query.one()
    client.post(f'/api/payments/{txn.id}/qr')
    paymongo.scan_and_pay('pi_test_1')                                    # paid; nobody checked yet
    assert client.get(f'/api/order/{order.id}').get_json()['can_cancel']
    r = client.post(f'/api/order/{order.id}/cancel', json={}).get_json()  # no GCash number needed
    assert r['success'] and 'refunded to the card or e-wallet' in r['message']
    refund = Refund.query.one()
    assert (refund.status, refund.method, refund.reference, refund.amount) == \
        ('refunded', 'PayMongo', 'ref_test_1', Decimal('2999.00'))
    assert db.session.get(Transaction, txn.id).payment_status == 'refunded'
    assert db.session.get(Product, p.id).stock_quantity == 10


def test_cancelling_an_unpaid_online_order_closes_the_payment_link(client, customer, paymongo):
    _online_order(client, customer)
    order, txn = Order.query.one(), Transaction.query.one()
    detail = client.get(f'/api/order/{order.id}').get_json()
    assert detail['pay_transaction_id'] == txn.id
    client.post(f'/user/payments/{txn.id}/paymongo')
    assert client.post(f'/api/order/{order.id}/cancel', json={}).get_json()['success']
    assert paymongo.sessions['cs_test_1']['status'] == 'expired' and Refund.query.count() == 0


def test_a_failed_automatic_refund_waits_for_an_admin(client, customer, paymongo):
    _online_order(client, customer)
    order, txn = Order.query.one(), Transaction.query.one()
    client.post(f'/api/payments/{txn.id}/qr')
    paymongo.scan_and_pay('pi_test_1')
    paymongo.fail_refund = True
    assert client.post(f'/api/order/{order.id}/cancel', json={}).get_json()['success']
    refund = Refund.query.one()
    assert refund.status == 'pending' and 'PayMongo dashboard' in refund.note


# ------------------------------------------------------------------ pages

def test_pay_by_qr_is_offered_in_the_shop_and_on_transactions(client, customer, paymongo):
    _online_order(client, customer)
    assert 'value="paymongo"' in client.get('/user/shop').get_data(as_text=True)
    txn = Transaction.query.one()
    page = client.get('/user/transactions').get_data(as_text=True)
    assert f'data-pay-online="{txn.id}"' in page and 'Pay online (instant)' not in page
    assert 'data-receipt-action=""' in page                     # shop orders: no receipt step, like the shop
    flask_app.config['PAYMONGO_ENABLED'] = False
    from flask import g
    g.pop('site_details', None)      # the test keeps one app context open across requests
    assert 'value="paymongo"' not in client.get('/user/shop').get_data(as_text=True)


def test_signature_check_accepts_live_signatures_too():
    body = b'{"a":1}'
    ts = int(time.time())
    sig = hmac.new(b'whsk_x', f'{ts}.'.encode() + body, hashlib.sha256).hexdigest()
    assert paymongo_service.signature_matches('whsk_x', body, f't={ts},te=,li={sig}')
    assert not paymongo_service.signature_matches('whsk_x', body + b' ', f't={ts},te=,li={sig}')


# ------------------------------------------------------------------ the booking fee, paid before booking

def _fee_service():
    from app import Service, ServiceCategory
    cat = ServiceCategory(name='Repairs', is_active=True)
    db.session.add(cat)
    db.session.flush()
    svc = Service(category_id=cat.id, name='Screen Fix', price=1500, is_active=True, device_types='laptop')
    db.session.add(svc)
    db.session.commit()
    return svc


def _submit_booking(client, svc, **extra):
    from datetime import date, timedelta
    data = {'service_id': str(svc.id), 'device_type': 'Laptop', 'in_shop': 'on', 'accept_terms': 'on',
            'booking_date': (date.today() + timedelta(days=1)).isoformat(), 'booking_time': '10:00',
            'problem_description': 'The laptop screen is cracked after it fell off the table', 'payment_method': 'GCash'}
    data.update(extra)
    return client.post('/user/service-request', data={k: v for k, v in data.items() if v is not None},
                       content_type='multipart/form-data')


def test_the_fee_is_paid_by_paymongo_qr_and_proven_by_a_screenshot_before_booking(client, customer, admin, paymongo):
    from app import Booking, booking_fee_transaction
    from tests.conftest import payment_proof
    svc = _fee_service()
    login_as(client, customer)
    page = client.get('/user/book').get_data(as_text=True)
    assert 'data-fee-online="1"' in page and 'name="fee_transaction_id"' in page and 'Submit booking' in page

    # nothing paid yet: the request can't be sent, even with a screenshot
    _submit_booking(client, svc, fee_receipt=payment_proof())
    start = client.post('/api/booking-fee', json={'service_id': svc.id}).get_json()
    assert start['status'] == 'pending' and start['amount'] == '100.00'
    hold_id = start['transaction_id']
    _submit_booking(client, svc, fee_transaction_id=str(hold_id), fee_receipt=payment_proof())
    assert Booking.query.count() == 0
    assert client.post('/api/booking-fee', json={'service_id': svc.id}).get_json()['transaction_id'] == hold_id

    # an unpaid fee payment is not something for an admin to check
    login_as(client, admin)
    assert f'FEE-NEW-{hold_id}' not in client.get('/admin/payments').get_data(as_text=True)
    login_as(client, customer)

    # scan PayMongo's QR and pay
    assert client.post(f'/api/payments/{hold_id}/qr').get_json()['amount'] == '100.00'
    paymongo.scan_and_pay(db.session.get(Transaction, hold_id).paymongo_intent_id)
    assert client.get(f'/api/payments/{hold_id}/status').get_json()['status'] == 'paid'
    assert client.post('/api/booking-fee', json={'service_id': svc.id}).get_json()['status'] == 'paid'

    # paid, but no screenshot: still refused
    _submit_booking(client, svc, fee_transaction_id=str(hold_id))
    assert Booking.query.count() == 0
    # paid and the screenshot attached: the booking is sent with the fee on it
    r = _submit_booking(client, svc, fee_transaction_id=str(hold_id), fee_receipt=payment_proof(),
                        fee_reference='PM-123')
    assert '/total-bookings?booked=' in r.headers['Location']          # the page clears the form's draft
    b = Booking.query.one()
    fee = booking_fee_transaction(b)
    assert fee.id == hold_id and fee.transaction_number == f'FEE-{b.booking_number}-{hold_id}'
    assert (fee.payment_status, fee.receipt_image is not None, fee.gcash_reference) == ('confirmed', True, 'PM-123')
    assert b.booking_fee == Decimal('100.00') and b.transaction.amount == Decimal('1400.00')

    # the same payment can't pay for a second booking
    _submit_booking(client, svc, fee_transaction_id=str(hold_id), fee_receipt=payment_proof(), booking_time='11:00')
    assert Booking.query.count() == 1


def test_someone_else_cannot_use_my_paid_booking_fee(client, customer, paymongo):
    from app import Booking, Customer
    from tests.conftest import payment_proof
    svc = _fee_service()
    login_as(client, customer)
    hold_id = client.post('/api/booking-fee', json={'service_id': svc.id}).get_json()['transaction_id']
    client.post(f'/api/payments/{hold_id}/qr')
    paymongo.scan_and_pay(db.session.get(Transaction, hold_id).paymongo_intent_id)
    client.get(f'/api/payments/{hold_id}/status')
    other = Customer(username='other', email='other@test.local', full_name='Other Person', is_active=True)
    other.set_password('password123')
    db.session.add(other)
    db.session.commit()
    login_as(client, other)
    _submit_booking(client, svc, fee_transaction_id=str(hold_id), fee_receipt=payment_proof())
    assert Booking.query.count() == 0


def test_returning_from_paymongos_page_with_a_booking_fee_goes_back_to_the_form(client, customer, paymongo):
    svc = _fee_service()
    login_as(client, customer)
    hold_id = client.post('/api/booking-fee', json={'service_id': svc.id}).get_json()['transaction_id']
    r = client.get(f'/paymongo/cancelled/{hold_id}')
    assert r.status_code == 302 and r.headers['Location'].endswith('/user/book')
    page = client.get('/user/book').get_data(as_text=True)
    assert 'devtech.bookingDraft' in page and 'We kept what you entered' in page



def test_a_repair_bill_is_paid_by_paymongo_qr_then_the_receipt_is_attached(client, customer, technician, assigned_booking, paymongo):
    from app import Booking
    from tests.conftest import payment_proof
    txn = Transaction(transaction_number='TRX-BILL-1', booking_id=assigned_booking.id, user_id=customer.id, amount=1000,
                      payment_method='GCash', payment_status='pending')
    db.session.add(txn)
    db.session.commit()
    login_as(client, customer)
    page = client.get('/user/transactions').get_data(as_text=True)
    assert f'data-pay-online="{txn.id}"' not in page and 'once the repair is done' in page   # still being repaired

    db.session.get(Booking, assigned_booking.id).status = 'completed'
    db.session.commit()
    page = client.get('/user/transactions').get_data(as_text=True)
    assert f'data-pay-online="{txn.id}"' in page and f'data-gcash="{txn.id}"' not in page     # one way to pay: PayMongo
    assert 'Pay online (instant)' not in page
    client.post(f'/user/payments/{txn.id}/receipt', data={'receipt_image': payment_proof()},
                content_type='multipart/form-data')
    assert not db.session.get(Transaction, txn.id).receipt_image                               # not paid yet
    client.post(f'/api/payments/{txn.id}/qr')
    paymongo.scan_and_pay(db.session.get(Transaction, txn.id).paymongo_intent_id)
    assert client.get(f'/api/payments/{txn.id}/status').get_json()['status'] == 'paid'
    assert 'Attach receipt screenshot' in client.get('/user/transactions').get_data(as_text=True)
    client.post(f'/user/payments/{txn.id}/receipt', data={'receipt_image': payment_proof(), 'reference_number': 'PM-9'},
                content_type='multipart/form-data')
    t = db.session.get(Transaction, txn.id)
    assert (t.payment_status, t.payment_method, t.reference_number) == ('confirmed', 'paymongo', 'PM-9') and t.receipt_image
    assert 'Attach receipt screenshot' not in client.get('/user/transactions').get_data(as_text=True)


def test_a_bill_the_booking_fee_fully_covers_asks_for_nothing_and_the_device_can_be_released(
        client, customer, technician, assigned_booking, paymongo):
    """Found while testing: a ₱2 job with a ₱2 booking fee left a ₱0 bill. The page
    offered "Pay with GCash", PayMongo can't make a ₱0 QR, and the dialog never
    finished; the technician couldn't release the device either."""
    from datetime import datetime
    from app import Booking
    txn = Transaction(transaction_number='TRX-ZERO-1', booking_id=assigned_booking.id, user_id=customer.id,
                      amount=0, payment_method='GCash', payment_status='pending')
    db.session.add(txn)
    b = db.session.get(Booking, assigned_booking.id)
    b.status, b.customer_received_at = 'completed', datetime.utcnow()
    db.session.commit()

    login_as(client, customer)
    page = client.get('/user/transactions').get_data(as_text=True)
    assert 'Nothing to pay' in page
    assert f'data-pay-online="{txn.id}"' not in page and f'data-gcash="{txn.id}"' not in page
    r = client.post(f'/api/payments/{txn.id}/qr')                 # an old tab still asks: a clear answer, no call to PayMongo
    assert r.status_code == 400 and 'Nothing to pay' in r.get_json()['message']
    assert not paymongo.calls
    client.post(f'/user/payments/{txn.id}', data={'payment_method': 'GCash'})
    assert db.session.get(Transaction, txn.id).payment_status == 'pending'

    client.get('/logout')
    login_as(client, technician)
    r = client.post(f'/technician/api/jobs/{assigned_booking.id}/advance', json={})
    assert r.get_json()['job']['repairStatus'] == 'released'
    t = db.session.get(Transaction, txn.id)
    assert t.payment_status == 'confirmed' and 'booking fee' in t.reviewed_by


def test_the_qr_dialog_gets_an_answer_even_when_starting_the_payment_crashes(client, customer, assigned_booking,
                                                                              paymongo, monkeypatch):
    import app as app_module
    from app import Booking
    txn = Transaction(transaction_number='TRX-CRASH-1', booking_id=assigned_booking.id, user_id=customer.id,
                      amount=500, payment_method='GCash', payment_status='pending')
    db.session.add(txn)
    db.session.get(Booking, assigned_booking.id).status = 'completed'
    db.session.commit()

    def boom(_):
        raise ValueError('unexpected')
    monkeypatch.setattr(app_module, 'start_qr_payment', boom)
    login_as(client, customer)
    r = client.post(f'/api/payments/{txn.id}/qr')
    assert r.status_code == 500 and r.is_json and 'could not be created' in r.get_json()['message']
