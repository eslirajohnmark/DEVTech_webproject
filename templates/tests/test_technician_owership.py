import pytest


@pytest.fixture
def other_tech_client(client, app):
    u = User(username='TECH-0099', email='other@test.local',
             full_name='Other Tech', role='technician',
             is_active=True, id_verified=True)
    u.set_password('otherpass99')
    db.session.add(u)
    db.session.commit()

    with client.session_transaction() as s:
        s['user_id'] = u.id
        s['username'] = u.username
        s['role'] = 'technician'
    return client


def test_tech_sees_only_own_jobs(tech_logged_in, assigned_booking):
    r = tech_logged_in.get('/technician/api/jobs')
    assert len(r.get_json()['jobs']) == 1


def test_other_tech_sees_nothing(other_tech_client, assigned_booking):
    r = other_tech_client.get('/technician/api/jobs')
    assert r.get_json()['jobs'] == []


def test_other_tech_cannot_view_job(other_tech_client, assigned_booking):
    r = other_tech_client.get('/technician/api/jobs/' + str(assigned_booking.id))
    assert r.status_code == 404


def test_other_tech_cannot_advance(other_tech_client, assigned_booking):
    r = other_tech_client.post(
        '/technician/api/jobs/' + str(assigned_booking.id) + '/advance')
    assert r.status_code == 404