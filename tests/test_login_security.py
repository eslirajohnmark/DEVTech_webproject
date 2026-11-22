"""Sign-in security: 5 tries then a pause that doubles, the email kept after a wrong
password, no "resubmit the form" on Back, no cached account pages, and an idle timeout."""
import time
from datetime import datetime, timedelta

import pytest

from app import db, LoginAttempt, app as flask_app
from services import login_guard
from tests.conftest import login_as


def _wrong(client, url, field, value, n=1):
    for _ in range(n):
        r = client.post(url, data={field: value, 'password': 'wrong-password'})
    return r


@pytest.mark.parametrize('url, field, value_of', [
    ('/login', 'email', lambda c, t, a: c.email),
    ('/admin/login', 'email', lambda c, t, a: a.email),
    ('/technician/login', 'technician_id', lambda c, t, a: t.username),
])
def test_five_wrong_passwords_pause_sign_in_even_with_the_right_one(client, customer, technician, admin,
                                                                    url, field, value_of):
    value = value_of(customer, technician, admin)
    right = {'/login': 'customerpass1', '/admin/login': 'adminpass123', '/technician/login': 'testpassword1'}[url]
    _wrong(client, url, field, value, 5)
    page = client.get(url).get_data(as_text=True)
    assert 'Too many failed sign-in attempts. Try again in 10 seconds.' in page
    assert 'data-lock-seconds="10"' in page or 'data-lock-seconds="9"' in page
    client.post(url, data={field: value, 'password': right})
    with client.session_transaction() as s:
        assert 'user_id' not in s                          # the right password waits too


def test_the_pause_doubles_each_time_and_a_success_starts_over(client, customer):
    _wrong(client, '/login', 'email', customer.email, 5)
    row = LoginAttempt.query.one()
    assert row.lockouts == 1 and 9 <= (row.locked_until - datetime.utcnow()).total_seconds() <= 10
    row.locked_until = datetime.utcnow() - timedelta(seconds=1)       # the 10 seconds have passed
    db.session.commit()
    _wrong(client, '/login', 'email', customer.email, 5)
    row = LoginAttempt.query.one()
    assert row.lockouts == 2 and 19 <= (row.locked_until - datetime.utcnow()).total_seconds() <= 20
    assert [login_guard.lock_seconds_for(n) for n in (1, 2, 3, 4)] == [10, 20, 40, 80]
    assert login_guard.lock_seconds_for(20) == 15 * 60                # never more than 15 minutes

    row.locked_until = datetime.utcnow() - timedelta(seconds=1)
    db.session.commit()
    client.post('/login', data={'email': customer.email, 'password': 'customerpass1'})
    assert LoginAttempt.query.count() == 0


def test_attempts_left_are_shown_near_the_end(client, customer):
    _wrong(client, '/login', 'email', customer.email, 3)
    assert '2 attempts left before sign-in is paused' in client.get('/login').get_data(as_text=True)


def test_unknown_emails_get_the_same_answer(client):
    _wrong(client, '/login', 'email', 'nobody@example.com', 5)
    assert 'Try again in 10 seconds' in client.get('/login').get_data(as_text=True)


@pytest.mark.parametrize('url, field, value, kept', [
    ('/login', 'email', 'Cara@Example.com', 'value="cara@example.com"'),
    ('/admin/login', 'email', 'boss@example.com', 'value="boss@example.com"'),
    ('/technician/login', 'technician_id', 'tech-0099', 'value="TECH-0099"'),
])
def test_a_wrong_password_keeps_the_email_and_clears_the_password(client, url, field, value, kept):
    r = client.post(url, data={field: value, 'password': 'my-secret-guess'})
    assert r.status_code == 302 and r.headers['Location'].endswith(url)   # Post/Redirect/Get: Back never resubmits
    page = client.get(url).get_data(as_text=True)
    assert kept in page and 'my-secret-guess' not in page
    assert kept not in client.get(url).get_data(as_text=True)            # only for the next page view


def test_account_and_sign_in_pages_are_never_cached(client, customer):
    assert 'no-store' in client.get('/login').headers['Cache-Control']
    login_as(client, customer)
    assert 'no-store' in client.get('/user/dashboard').headers['Cache-Control']
    client.get('/logout')
    r = client.get('/user/dashboard')                                     # what Back asks for after signing out
    assert r.status_code == 302 and '/login' in r.headers['Location']


def test_signed_in_people_skip_their_sign_in_page(client, customer, admin, technician):
    login_as(client, customer)
    assert client.get('/login').headers['Location'].endswith('/user/dashboard')
    login_as(client, admin)
    assert client.get('/admin/login').headers['Location'].endswith('/admin/dashboard')
    login_as(client, technician)
    assert client.get('/technician/login').headers['Location'].endswith('/technician/dashboard')


def test_idle_sessions_end_unless_remember_me(client, customer):
    client.post('/login', data={'email': customer.email, 'password': 'customerpass1'})
    assert client.get('/user/dashboard').status_code == 200
    with client.session_transaction() as s:
        s['seen'] = int(time.time()) - (flask_app.config['SESSION_IDLE_MINUTES'] * 60 + 5)
    r = client.get('/user/dashboard')
    assert r.status_code == 302 and '/login' in r.headers['Location']
    assert 'signed out after' in client.get('/login').get_data(as_text=True)

    client.post('/login', data={'email': customer.email, 'password': 'customerpass1', 'remember': 'on'})
    with client.session_transaction() as s:
        s['seen'] = int(time.time()) - 24 * 3600
    assert client.get('/user/dashboard').status_code == 200            # "Remember me": 7 days


def test_background_polling_does_not_keep_an_idle_session_alive(client, customer):
    client.post('/login', data={'email': customer.email, 'password': 'customerpass1'})
    stale = int(time.time()) - 600
    with client.session_transaction() as s:
        s['seen'] = stale
    client.post('/api/ping')
    with client.session_transaction() as s:
        assert s['seen'] == stale
    client.get('/user/dashboard')
    with client.session_transaction() as s:
        assert s['seen'] > stale


def test_technician_api_sign_in_is_paused_too(client, technician):
    for _ in range(5):
        r = client.post('/technician/api/login', json={'technician_id': technician.username, 'password': 'nope'})
    assert r.status_code == 401 and r.get_json()['retryAfter'] == 10
    r = client.post('/technician/api/login', json={'technician_id': technician.username, 'password': 'testpassword1'})
    assert r.status_code == 429 and 'Try again in' in r.get_json()['reason']


def test_every_kind_of_page_stops_double_submits(client, customer, admin, technician):
    """static/js/busy-guard.js locks a form's buttons until the server answers."""
    for url in ('/login', '/register', '/admin/login', '/technician/login', '/technician/register',
                '/forgot-password', '/'):
        assert 'js/busy-guard.js' in client.get(url).get_data(as_text=True), url
    for user, url in ((customer, '/user/book'), (admin, '/admin/orders'), (technician, '/technician/dashboard')):
        login_as(client, user)
        assert 'js/busy-guard.js' in client.get(url).get_data(as_text=True), url
