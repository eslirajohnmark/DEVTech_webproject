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

def test_tech_id_is_case_insensitive(client, app):
    # Older databases have technicians whose sign-in ID isn't upper-case (e.g. "jhenard").
    from app import db, Technician
    t = Technician(username='jhenard', email='jh@test.local', full_name='J Henard', is_active=True)
    t.set_password('jhenard123')
    db.session.add(t)
    db.session.commit()
    r = client.post('/technician/login', data={'technician_id': 'jhenard', 'password': 'jhenard123'})
    assert r.status_code == 302 and r.headers['Location'].endswith('/technician/dashboard')
