import pytest


@pytest.fixture
def rl_on(app):
    app.config['RATELIMIT_ENABLED'] = True
    try:
        app.extensions['limiter'].reset()
    except Exception:
        pass
    yield app
    app.config['RATELIMIT_ENABLED'] = False


def test_login_is_rate_limited(rl_on, client, technician):
    codes = []
    for _ in range(8):
        r = client.post('/technician/api/login', json={
            'technician_id': 'TECH-0001', 'password': 'wrong'})
        codes.append(r.status_code)
    assert 429 in codes, 'Codes: ' + str(codes)