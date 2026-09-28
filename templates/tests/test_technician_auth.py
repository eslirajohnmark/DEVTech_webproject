def test_login_page_renders(client):
    r = client.get('/technician/login')
    assert r.status_code == 200
    assert b'Sign in' in r.data


def test_login_with_wrong_password_fails(client, technician):
    r = client.post('/technician/api/login', json={
        'technician_id': 'TECH-0001', 'password': 'wrong'})
    assert r.status_code == 401


def test_login_with_correct_password_succeeds(client, technician):
    r = client.post('/technician/api/login', json={
        'technician_id': 'TECH-0001', 'password': 'testpassword1'})
    assert r.status_code == 200
    assert r.get_json()['ok'] is True


def test_dashboard_requires_login(client):
    r = client.get('/technician/dashboard')
    assert r.status_code == 302
    assert '/technician/login' in r.headers['Location']


def test_me_endpoint_returns_technician(tech_logged_in):
    r = tech_logged_in.get('/technician/api/me')
    assert r.status_code == 200
    assert r.get_json()['technician']['username'] == 'TECH-0001'


def test_logout_clears_session(tech_logged_in):
    tech_logged_in.post('/technician/api/logout')
    assert tech_logged_in.get('/technician/api/me').status_code == 401