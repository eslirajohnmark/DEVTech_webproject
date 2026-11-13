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
    assert f'data-pay="{txn.id}"' in client.get('/user/transactions').get_data(as_text=True)
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
