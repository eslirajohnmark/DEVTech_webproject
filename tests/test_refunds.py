"""Refund workflow: refunds opened by cancellations or by hand, processed (or
declined) once by an admin, and shown to the customer."""
from decimal import Decimal

import pytest

from app import db, Booking, Notification, Order, OrderItem, Product, Refund, Transaction
from tests.conftest import login_as


def _txn(booking=None, order=None, status='confirmed', amount=1500, method='GCash', **kw):
    t = Transaction(transaction_number=f'TRX-R{Transaction.query.count() + 1}',
                    booking_id=booking.id if booking else None, order_id=order.id if order else None,
                    user_id=(booking or order).user_id, amount=amount, payment_method=method,
                    payment_status=status, **kw)
    db.session.add(t)
    db.session.commit()
    return t


def _order(customer, status='pending', payment_status='confirmed', method='gcash', stock=5):
    p = Product(name='RAM 8GB', price=1200, stock_quantity=stock, is_active=True)
    db.session.add(p)
    db.session.flush()
    o = Order(user_id=customer.id, order_number=f'ORD-{Order.query.count() + 1}', total_amount=1200,
              status=status, payment_method=method, payment_status=payment_status)
    db.session.add(o)
    db.session.flush()
    db.session.add(OrderItem(order_id=o.id, product_id=p.id, quantity=1, price=1200))
    db.session.commit()
    return o, p


def _notes(role, title):
    return Notification.query.filter_by(user_role=role, title=title).count()


# ---------------------------------------------------------------- opened automatically

def test_cancelling_a_paid_booking_opens_a_refund(client, customer, admin, assigned_booking):
    t = _txn(assigned_booking)
    login_as(client, customer)
    client.post(f'/booking/{assigned_booking.id}/cancel')
    r = Refund.query.one()
    assert (r.transaction_id, r.status, r.amount, r.customer_id) == (t.id, 'pending', Decimal('1500.00'), customer.id)
    assert db.session.get(Transaction, t.id).payment_status == 'confirmed'      # until the money goes back
    assert _notes('admin', 'Refund to process') == 1 and _notes('customer', 'Refund requested') == 1


def test_payment_proof_on_a_cancelled_booking_opens_a_refund_to_check(client, customer, assigned_booking):
    t = _txn(assigned_booking, status='pending', gcash_reference='GC-1')
    login_as(client, customer)
    client.post(f'/booking/{assigned_booking.id}/cancel')
    assert db.session.get(Transaction, t.id).payment_status == 'cancelled'
    assert 'Check the money arrived' in Refund.query.one().reason


def test_unpaid_cancelled_booking_needs_no_refund(client, customer, assigned_booking):
    _txn(assigned_booking, status='pending')
    login_as(client, customer)
    client.post(f'/booking/{assigned_booking.id}/cancel')
    assert Refund.query.count() == 0


def test_admin_cancelling_a_paid_order_opens_a_refund_and_restores_stock(client, admin, customer):
    o, p = _order(customer, status='processing')
    t = _txn(order=o, method='gcash', gcash_reference='GC-9')
    login_as(client, admin)
    client.post(f'/admin/orders/{o.id}/status', data={'status': 'cancelled'})
    assert Refund.query.one().transaction_id == t.id
    assert db.session.get(Product, p.id).stock_quantity == 6


def test_customer_may_cancel_a_paid_order_only_before_it_is_prepared(client, customer):
    pending, _ = _order(customer, status='pending')
    _txn(order=pending, method='gcash')
    preparing, _ = _order(customer, status='processing')
    _txn(order=preparing, method='gcash')
    login_as(client, customer)
    ok = client.post(f'/api/order/{pending.id}/cancel').get_json()
    assert ok['success'] and ok['refund_opened']
    refused = client.post(f'/api/order/{preparing.id}/cancel')
    assert refused.status_code == 400 and db.session.get(Order, preparing.id).status == 'processing'
    assert Refund.query.count() == 1


def test_gcash_order_with_reference_cancelled_before_verification(client, customer):
    o, _ = _order(customer, payment_status='pending')
    t = _txn(order=o, status='pending', method='gcash', gcash_reference='GC-77')
    login_as(client, customer)
    client.post(f'/api/order/{o.id}/cancel')
    assert db.session.get(Transaction, t.id).payment_status == 'cancelled'
    assert Refund.query.one().transaction_id == t.id


# ---------------------------------------------------------------- processing

@pytest.fixture
def pending_refund(client, customer, assigned_booking):
    t = _txn(assigned_booking)
    login_as(client, customer)
    client.post(f'/booking/{assigned_booking.id}/cancel')
    return Refund.query.one(), t


def test_admin_marks_refund_sent(client, admin, customer, pending_refund):
    refund, t = pending_refund
    login_as(client, admin)
    url = f'/admin/refunds/{refund.id}/complete'
    client.post(url, data={'method': 'Carrier pigeon', 'reference': 'x'})
    client.post(url, data={'method': 'GCash', 'reference': ''})                       # GCash needs a reference
    client.post(url, data={'method': 'GCash', 'reference': 'GC-OUT-1', 'amount': '1600'})   # more than paid
    assert db.session.get(Refund, refund.id).status == 'pending'
    client.post(url, data={'method': 'GCash', 'reference': 'GC-OUT-1', 'amount': '1500.00'})
    r = db.session.get(Refund, refund.id)
    assert (r.status, r.method, r.reference, r.amount) == ('refunded', 'GCash', 'GC-OUT-1', Decimal('1500.00'))
    assert r.processed_at and 'Test Admin' in r.processed_by
    assert db.session.get(Transaction, t.id).payment_status == 'refunded'
    assert _notes('customer', 'Refund Sent') == 1
    # a second click does nothing
    client.post(url, data={'method': 'Cash'})
    assert db.session.get(Refund, refund.id).method == 'GCash' and _notes('customer', 'Refund Sent') == 1
    # the customer sees it
    login_as(client, customer)
    html = client.get('/user/transactions').get_data(as_text=True)
    assert 'Refunded:' in html and 'GC-OUT-1' in html


def test_partial_cash_refund_without_reference(client, admin, pending_refund):
    refund, _ = pending_refund
    login_as(client, admin)
    client.post(f'/admin/refunds/{refund.id}/complete', data={'method': 'Cash', 'amount': '500'})
    r = db.session.get(Refund, refund.id)
    assert r.status == 'refunded' and r.amount == Decimal('500.00')


def test_admin_declines_with_a_reason(client, admin, customer, pending_refund):
    refund, t = pending_refund
    login_as(client, admin)
    client.post(f'/admin/refunds/{refund.id}/decline', data={'note': 'no'})                 # too short
    assert db.session.get(Refund, refund.id).status == 'pending'
    client.post(f'/admin/refunds/{refund.id}/decline', data={'note': 'No payment with that reference arrived.'})
    assert db.session.get(Refund, refund.id).status == 'declined'
    assert db.session.get(Transaction, t.id).payment_status == 'confirmed'
    login_as(client, customer)
    assert 'No payment with that reference arrived.' in client.get('/user/transactions').get_data(as_text=True)


def test_refunded_order_payment_status_follows(client, admin, customer):
    o, _ = _order(customer, status='processing')
    _txn(order=o, method='gcash')
    login_as(client, admin)
    client.post(f'/admin/orders/{o.id}/status', data={'status': 'cancelled'})
    refund = Refund.query.one()
    client.post(f'/admin/refunds/{refund.id}/complete', data={'method': 'GCash', 'reference': 'GC-B'})
    assert db.session.get(Order, o.id).payment_status == 'refunded'


# ---------------------------------------------------------------- opened by hand

def test_admin_opens_a_refund_by_hand_once(client, admin, assigned_booking):
    paid = _txn(assigned_booking)
    unpaid = _txn(assigned_booking, status='pending')
    login_as(client, admin)
    client.post(f'/admin/payments/{unpaid.id}/refund', data={'reason': 'Goodwill refund'})
    client.post(f'/admin/payments/{paid.id}/refund', data={'reason': 'x'})                   # reason too short
    assert Refund.query.count() == 0
    client.post(f'/admin/payments/{paid.id}/refund', data={'reason': 'Replacement part never arrived'})
    client.post(f'/admin/payments/{paid.id}/refund', data={'reason': 'Replacement part never arrived'})
    assert Refund.query.count() == 1 and 'Test Admin' in Refund.query.one().created_by


def test_refunds_page_is_admin_only_and_filters(client, admin, customer, pending_refund):
    login_as(client, customer)
    assert client.get('/admin/refunds').status_code == 302
    login_as(client, admin)
    html = client.get('/admin/refunds').get_data(as_text=True)
    assert 'Mark as refunded' in html and '₱1,500.00' in html
    assert 'No refunds match' in client.get('/admin/refunds?status=declined').get_data(as_text=True)
    assert client.get('/admin/dashboard').get_data(as_text=True).count('Refunds') >= 1
