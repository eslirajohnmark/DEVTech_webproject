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
    r = client.post(link, data={'password': 'NewPass#456', 'confirm': 'NewPass#456'})
    assert r.status_code == 302 and r.headers['Location'].endswith('/login')
    assert db.session.get(Customer, real_customer.id).check_password('NewPass#456')

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


# ---- Resend, the reset emails and the reset page ----

class _Answer:
    def __init__(self, status, body):
        self.status_code, self.text, self.ok = status, body, 200 <= status < 300

    def json(self):
        import json
        return json.loads(self.text)


def test_resend_is_used_when_chosen_even_if_brevo_is_also_set(monkeypatch):
    sent = {}
    monkeypatch.setenv('RESEND_API_KEY', 're_test_key')
    monkeypatch.setenv('BREVO_API_KEY', 'xkeysib-test')
    monkeypatch.setenv('EMAIL_PROVIDER', 'resend')
    monkeypatch.setenv('MAIL_FROM', 'DEVTech <no-reply@devtech-demo.com>')
    monkeypatch.setattr(email_service.requests, 'post',
                        lambda url, json=None, headers=None, timeout=None: sent.update(url=url, json=json, headers=headers)
                        or _Answer(200, '{"id": "abc"}'))
    ok, provider, detail = email_service.send_with_detail('cara@gmail.com', 'S', '<p>x</p>', 'x')
    assert (ok, provider) == (True, 'resend') and 'abc' in detail
    assert sent['url'] == email_service.RESEND_URL and sent['headers']['Authorization'] == 'Bearer re_test_key'
    assert sent['json']['from'] == 'DEVTech <no-reply@devtech-demo.com>' and sent['json']['to'] == ['cara@gmail.com']


def test_a_resend_refusal_explains_the_sandbox_sender(monkeypatch):
    monkeypatch.setenv('RESEND_API_KEY', 're_test_key')
    monkeypatch.delenv('BREVO_API_KEY', raising=False)
    monkeypatch.setattr(email_service.requests, 'post', lambda *a, **k: _Answer(
        403, '{"statusCode":403,"message":"You can only send testing emails to your own email address (owner@x.com)."}'))
    ok, provider, detail = email_service.send_with_detail('cara@gmail.com', 'S', '<p>x</p>', 'x')
    assert not ok and provider == 'resend' and 'Verify a domain you own' in detail


def test_the_reset_email_is_a_security_email_with_a_copyable_link(outbox, client, real_customer):
    client.post('/forgot-password', data={'email': real_customer.email})
    mail = outbox[0]
    assert 'turn off email notifications' not in mail['html'] and 'security email' in mail['html']
    assert 'Or copy this link' in mail['html'] and _reset_link(mail) in mail['html']


def test_reset_needs_the_same_strong_password_as_registration_and_confirms_by_email(outbox, client, real_customer):
    client.post('/forgot-password', data={'email': real_customer.email})
    link = _reset_link(outbox[0])
    page = client.get(link).get_data(as_text=True)
    assert 'data-password-rules="password"' in page and 'password-rules.js' in page
    r = client.post(link, data={'password': 'newpass456', 'confirm': 'newpass456'})       # no capital, no symbol
    assert r.status_code == 400 and 'capital letter' in r.get_data(as_text=True)
    r = client.post(link, data={'password': 'oldpass123', 'confirm': 'oldpass123'})
    assert r.status_code == 400
    r = client.post(link, data={'password': 'NewPass#456', 'confirm': 'NewPass#456'})
    assert r.status_code == 302 and db.session.get(Customer, real_customer.id).check_password('NewPass#456')
    assert outbox[-1]['subject'].endswith('password was changed') and outbox[-1]['to'] == real_customer.email


def test_staff_go_back_to_their_own_sign_in_page(outbox, client):
    assert 'href="/technician/login"' in client.get('/forgot-password?portal=technician').get_data(as_text=True) \
        or '/technician/' in client.get('/forgot-password?portal=technician').get_data(as_text=True)
    page = client.get('/forgot-password?portal=nonsense').get_data(as_text=True)
    assert 'href="/login"' in page
