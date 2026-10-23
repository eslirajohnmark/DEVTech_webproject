"""No invented data on pages; business details come from System Settings."""
from datetime import datetime, timedelta

from app import db, SystemSetting, Notification, Booking, Transaction
from tests.conftest import login_as


def _set(key, value):
    row = SystemSetting.query.filter_by(setting_key=key).first()
    if row:
        row.value = value
    else:
        db.session.add(SystemSetting(setting_key=key, value=value))
    db.session.commit()


def test_home_has_no_invented_numbers_or_contacts(client):
    html = client.get('/').get_data(as_text=True)
    for fake in ('2,500+', '98%', '4.9★', 'Since 2018', '(053) 123-4567', 'support@devtech.ph', '0917 123 4567'):
        assert fake not in html, fake


def test_home_shows_real_stats_once_there_is_data(client, assigned_booking):
    assigned_booking.status = 'released'
    db.session.commit()
    html = client.get('/').get_data(as_text=True)
    assert 'Repairs Completed' in html and 'Verified Technician' in html


def test_contact_details_come_from_settings(client, customer):
    _set('contact_phone', '0999 111 2222')
    _set('business_hours', 'Mon-Fri, 9 AM - 5 PM')
    _set('gcash_account', '0999 333 4444')
    html = client.get('/').get_data(as_text=True)
    assert '0999 111 2222' in html and 'Mon-Fri, 9 AM - 5 PM' in html
    login_as(client, customer)
    assert '0999 111 2222' in client.get('/support').get_data(as_text=True)
    assert '0999 333 4444' in client.get('/user/transactions').get_data(as_text=True)


def test_blank_contact_phone_is_hidden(client):
    html = client.get('/').get_data(as_text=True)
    assert 'Call Us' not in html


def test_settings_accept_contact_fields(admin_logged_in):
    r = admin_logged_in.post('/admin/settings/update', json={
        'contact_phone': '0917 555 0000', 'contact_email': 'help@shop.ph', 'business_hours': 'Daily'})
    assert r.get_json()['success'] is True
    r = admin_logged_in.post('/admin/settings/update', json={'contact_phone': 'call me <script>'})
    assert r.status_code == 400


def test_admin_notifications_page(admin_logged_in, admin):
    db.session.add(Notification(user_role='admin', user_id=admin.id, title='New Support Ticket', message='Help please'))
    db.session.commit()
    html = admin_logged_in.get('/admin/notifications').get_data(as_text=True)
    assert 'New Support Ticket' in html
    assert Notification.query.filter_by(user_role='admin', user_id=admin.id, is_read=False).count() == 0


def test_admin_bells_link_to_notifications(admin_logged_in):
    for url in ('/admin/users', '/admin/settings', '/admin/payments', '/admin/requests'):
        html = admin_logged_in.get(url).get_data(as_text=True)
        assert "showAdminToast('Notifications')" not in html, url
        assert 'href="/admin/notifications"' in html, url


def test_analytics_kpis_and_monthly_bookings(admin_logged_in, assigned_booking, customer):
    db.session.add(Transaction(transaction_number='TRX-A1', booking_id=assigned_booking.id,
                               user_id=customer.id, amount=500, payment_method='GCash',
                               payment_status='confirmed', transaction_date=datetime.utcnow()))
    db.session.commit()
    html = admin_logged_in.get('/admin/analytics').get_data(as_text=True)
    assert 'Repair Bookings' in html and 'Customers' in html and 'Total Services' not in html
    assert '+₱500' in html
    # The comparison chart's booking series is monthly counts, not status counts.
    assert 'const bookingData = [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1]' in html


def test_technician_login_has_no_demo_accounts(client):
    html = client.get('/technician/login').get_data(as_text=True)
    assert 'Demo' not in html and '1234' not in html


def test_pages_render_items_without_descriptions(client, customer, assigned_booking):
    from app import Product
    assigned_booking.service.description = None
    db.session.add(Product(name="Mouse", price=100, stock_quantity=3, is_active=True, description=None))
    db.session.commit()
    assert client.get("/").status_code == 200
    login_as(client, customer)
    assert client.get("/user/shop").status_code == 200
