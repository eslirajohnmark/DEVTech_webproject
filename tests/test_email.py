"""Email notifications and the forgot-password flow (no real emails are sent)."""
import re

import pytest

from app import db, Customer, Technician, Admin, UserPreference
from services import email_service
from tests.conftest import login_as


@pytest.fixture
def outbox(app, monkeypatch):
    """Turn email on for this test and capture what would be sent."""
    sent = []
    monkeypatch.setenv('RESEND_API_KEY', 're_test_key')
    app.config['EMAIL_IN_TESTS'] = True
    monkeypatch.setattr(email_service, 'queue_email',
                        lambda to, subject, html_body, text_body, app=None: sent.append(
                            {'to': to, 'subject': subject, 'html': html_body, 'text': text_body}) or True)
    yield sent
    app.config['EMAIL_IN_TESTS'] = False


@pytest.fixture
def real_customer(app):
    u = Customer(username='ana', email='ana@example.com', full_name='Ana Reyes', is_active=True)
    u.set_password('oldpass123')
    db.session.add(u)
    db.session.commit()
    return u


def _reset_link(mail):
    return re.search(r'http://localhost(/reset-password/[^\s"<]+)', mail['text']).group(1)


# ---- notifications ----

def test_notifications_are_emailed(outbox, client, real_customer):
    from app import create_notification
    with client.application.test_request_context():
        create_notification(real_customer.id, 'Booking Approved', 'Your booking was approved.', role='customer')
    assert len(outbox) == 1 and outbox[0]['to'] == 'ana@example.com'
    assert 'Booking Approved' in outbox[0]['subject']


def test_no_email_when_user_turned_it_off(outbox, client, real_customer):
    from app import create_notification
    db.session.add(UserPreference(user_id=real_customer.id, email_notifications=False))
    db.session.commit()
    with client.application.test_request_context():
        create_notification(real_customer.id, 'Hello', 'Hi', role='customer')
    assert outbox == []


def test_no_email_to_placeholder_addresses(outbox, client, customer):
    from app import create_notification   # customer fixture uses @test.local
    with client.application.test_request_context():
        create_notification(customer.id, 'Hello', 'Hi', role='customer')
    assert outbox == []


def test_email_toggle_endpoint(client, real_customer):
    login_as(client, real_customer)
    assert client.post('/api/user/email-notifications', json={'enabled': False}).get_json()['enabled'] is False
    assert UserPreference.query.filter_by(user_id=real_customer.id).one().email_notifications is False


def test_email_html_is_escaped():
    html_body, _ = email_service.render('<b>Hi</b>', '<script>x</script>')
    assert '<script>' not in html_body and '&lt;b&gt;Hi' in html_body


# ---- forgot / reset password ----

def test_forgot_password_emails_a_working_one_time_link(outbox, client, real_customer):
    r = client.post('/forgot-password', data={'email': 'ANA@example.com'})
    assert r.status_code == 200 and 'Check your email' in r.get_data(as_text=True)
    assert len(outbox) == 1
    link = _reset_link(outbox[0])

    assert client.get(link).status_code == 200
    r = client.post(link, data={'password': 'newpass456', 'confirm': 'newpass456'})
    assert r.status_code == 302 and r.headers['Location'].endswith('/login')
    assert db.session.get(Customer, real_customer.id).check_password('newpass456')

    # The same link can't be used twice.
    assert client.get(link).status_code == 400


def test_forgot_password_same_answer_for_unknown_email(outbox, client):
    r = client.post('/forgot-password', data={'email': 'nobody@example.com'})
    assert 'Check your email' in r.get_data(as_text=True)
    assert outbox == []


def test_reset_rejects_weak_or_mismatched_passwords(outbox, client, real_customer):
    client.post('/forgot-password', data={'email': real_customer.email})
    link = _reset_link(outbox[0])
    assert client.post(link, data={'password': 'short', 'confirm': 'short'}).status_code == 400
    assert client.post(link, data={'password': 'longenough1', 'confirm': 'different1'}).status_code == 400
    assert db.session.get(Customer, real_customer.id).check_password('oldpass123')


def test_tampered_link_is_rejected(client):
    assert client.get('/reset-password/not-a-real-token').status_code == 400


def test_forgot_password_without_email_service(client):
    html = client.get('/forgot-password').get_data(as_text=True)
    assert 'contact us' in html.lower()
