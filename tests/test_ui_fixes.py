"""Regression tests for the page/JS/design fixes."""
from app import app as flask_app, db, Customer, Technician, Admin, Notification
from models.technician_models import JobLog
from tests.conftest import login_as


def test_service_request_page_redirects_to_working_booking_page(customer_logged_in):
    r = customer_logged_in.get('/user/service-request')
    assert r.status_code == 302 and r.headers['Location'].endswith('/user/book')


def test_my_bookings_page_renders(customer_logged_in, assigned_booking):
    html = customer_logged_in.get('/total-bookings').get_data(as_text=True)
    assert 'BK-TEST-0001' in html
    # Data embedded for the details modal is valid JS (no HTML-escaped quotes).
    assert '&#34;' not in html.split('const bookingData')[1].split('};')[0]


def test_js_html_filter_escapes_for_script_and_html(app):
    with app.test_request_context():
        from flask import render_template_string
        out = render_template_string('{{ v|js_html }}|{{ n|js_html }}', v='Tom "T" <b>&\n', n=None)
    js, null = out.split('|')
    assert null == 'null'
    assert '\n' not in js and '<' not in js and js.startswith('"')


def test_remember_me_controls_session_lifetime(client, customer):
    client.post('/login', data={'email': customer.email, 'password': 'customerpass1', 'remember': 'on'})
    with client.session_transaction() as s:
        assert s.permanent is True
    client.get('/logout')
    client.post('/login', data={'email': customer.email, 'password': 'customerpass1'})
    with client.session_transaction() as s:
        assert s.permanent is False


def test_admin_can_reset_a_users_password(admin_logged_in, customer):
    r = admin_logged_in.post(f'/api/admin/users/customer/{customer.id}/reset-password')
    temp = r.get_json()['temporary_password']
    assert db.session.get(Customer, customer.id).check_password(temp)
    assert Notification.query.filter_by(user_role='customer', user_id=customer.id, title='Password Reset').count() == 1


def test_admin_cannot_reset_own_password_here(admin_logged_in, admin):
    assert admin_logged_in.post(f'/api/admin/users/admin/{admin.id}/reset-password').status_code == 400


def test_rejected_booking_detail_includes_reason(customer_logged_in, assigned_booking):
    assigned_booking.status = 'cancelled'
    db.session.add(JobLog(booking_id=assigned_booking.id, at='2026-10-01 10:00:00', by_name='admin',
                          action='status', text='Rejected by admin. Part unavailable.'))
    db.session.commit()
    data = customer_logged_in.get(f'/api/booking/{assigned_booking.id}').get_json()
    assert data['status_note'] == 'Rejected by admin. Part unavailable.'


def test_technician_dashboard_counts(tech_logged_in, assigned_booking):
    html = tech_logged_in.get('/technician/dashboard').get_data(as_text=True)
    assert 'Total Jobs' in html and 'Released' in html
    assert '>confirmed<' not in html          # raw status codes are not shown


def test_home_page_has_repair_animation(client):
    html = client.get('/').get_data(as_text=True)
    assert 'id="repairScene"' in html and 'href="#how-it-works"' in html


def test_background_polls_are_not_rate_limited(app, customer_logged_in):
    app.config["RATELIMIT_ENABLED"] = True
    try:
        from app import limiter
        limiter.reset()
        codes = {customer_logged_in.post("/api/ping").status_code for _ in range(260)}
        assert codes == {200}
        codes = {customer_logged_in.get("/api/notifications/unread-count").status_code for _ in range(50)}
        assert codes == {200}
    finally:
        app.config["RATELIMIT_ENABLED"] = False
