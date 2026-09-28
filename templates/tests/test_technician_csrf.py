
import pytest


@pytest.fixture
def csrf_on(app):
    app.config['WTF_CSRF_ENABLED'] = True
    yield app
    app.config['WTF_CSRF_ENABLED'] = False


def test_advance_without_token_rejected(csrf_on, tech_logged_in, assigned_booking):
    r = tech_logged_in.post(
        '/technician/api/jobs/' + str(assigned_booking.id) + '/advance', json={})
    assert r.status_code in (400, 403)


def test_login_does_not_require_csrf(csrf_on, client, technician):
    r = client.post('/technician/api/login', json={
        'technician_id': 'TECH-0001', 'password': 'testpassword1'})
    assert r.status_code in (200, 401)