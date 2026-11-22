"""Sidebar badges: a number appears when something new arrives, disappears once its
page has been opened, and appears again for the next new thing (every portal)."""
from datetime import date, datetime, time, timedelta

from app import (db, Booking, Notification, Service, ServiceCategory, Transaction, create_notification,
                 nav_count_values)
from models.technician_models import ApprovalRequest
from tests.conftest import login_as


def _pending_booking(customer, when=None, number='BK-NEW-1'):
    cat = ServiceCategory.query.first() or ServiceCategory(name='Repairs', is_active=True)
    db.session.add(cat)
    db.session.flush()
    svc = Service.query.first() or Service(category_id=cat.id, name='Screen Fix', price=1000, is_active=True)
    db.session.add(svc)
    db.session.flush()
    b = Booking(booking_number=number, user_id=customer.id, service_id=svc.id, device_type='Laptop',
                description='Cracked screen after a fall', booking_date=date.today() + timedelta(days=1),
                booking_time=time(10, 0), status='pending', created_at=when or datetime.utcnow())
    db.session.add(b)
    db.session.commit()
    return b


def _badges(client):
    return client.get('/api/live').get_json()['c']


def test_admin_badge_clears_when_the_page_is_opened_and_returns_for_something_new(client, admin, customer):
    _pending_booking(customer)
    login_as(client, admin)
    assert _badges(client)['requests'] == 1
    page = client.get('/admin/requests').get_data(as_text=True)
    assert 'data-live-count="requests" hidden' in page          # cleared on the page being opened
    assert _badges(client)['requests'] == 0
    _pending_booking(customer, when=datetime.utcnow() + timedelta(seconds=2), number='BK-NEW-2')
    assert _badges(client)['requests'] == 1                       # something new: it appears again


def test_notification_badge_clears_on_opening_notifications_without_deleting_them(client, customer):
    login_as(client, customer)
    create_notification(customer.id, 'Repair Status Updated', 'Your laptop is ready.', 'info', email=False,
                        role='customer')
    live = client.get('/api/live').get_json()
    assert live['nu'] == 1 and live['c']['notifications'] == 1
    client.get('/notifications')
    live = client.get('/api/live').get_json()
    assert live['nu'] == 0 and live['c']['notifications'] == 0
    n = Notification(user_role='customer', user_id=customer.id, title='Payment Confirmed', message='Thanks!',
                     type='success', created_at=datetime.utcnow() + timedelta(seconds=2))
    db.session.add(n)
    db.session.commit()
    assert client.get('/api/live').get_json()['nu'] == 1


def test_a_badge_change_in_another_tab_wakes_the_waiting_pages(client, admin, customer):
    _pending_booking(customer)
    login_as(client, admin)
    before = client.get('/api/live').get_json()
    client.get('/admin/requests')
    after = client.get('/api/live').get_json()
    assert before['b'] != after['b'] and before['s'] == after['s']


def test_technician_and_customer_badges_follow_the_same_rule(client, technician, customer, assigned_booking):
    login_as(client, technician)
    assert _badges(client)['jobs'] == 1                            # a confirmed job assigned to them
    client.get('/technician/jobs')
    assert _badges(client)['jobs'] == 0

    db.session.add(ApprovalRequest(booking_id=assigned_booking.id, technician_id=technician.id,
                                   requested_at=(datetime.utcnow() - timedelta(minutes=1)).strftime('%Y-%m-%d %H:%M:%S'),
                                   findings='Hinge broken', additional_cost=350, status='pending'))
    db.session.commit()
    login_as(client, customer)
    assert _badges(client)['approvals'] == 1
    client.get(f'/user/monitor-device/{assigned_booking.id}')
    assert nav_count_values('customer', customer.id)['approvals'] == 0


def test_payments_badge_shows_a_new_screenshot_until_payments_is_opened(client, admin, customer, assigned_booking):
    from app import mark_seen
    login_as(client, admin)
    mark_seen('admin', admin.id, 'payments', datetime.utcnow() - timedelta(minutes=5))    # opened 5 minutes ago
    t = Transaction(transaction_number='TRX-B1', booking_id=assigned_booking.id, user_id=customer.id, amount=500,
                    payment_method='GCash', payment_status='pending',
                    updated_at=datetime.utcnow() - timedelta(minutes=1))                 # screenshot sent since
    db.session.add(t)
    db.session.commit()
    assert _badges(client)['payments'] == 1
    client.get('/admin/payments')
    assert _badges(client)['payments'] == 0
