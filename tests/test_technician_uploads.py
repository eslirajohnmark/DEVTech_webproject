import io


def test_upload_rejects_bad_mime(tech_logged_in, assigned_booking):
    r = tech_logged_in.post('/technician/api/uploads', data={
        'ownerType': 'intake', 'ownerId': '1',
        'jobId': str(assigned_booking.id),
        'file': (io.BytesIO(b'MZ\x90\x00'), 'evil.exe',
                 'application/x-msdownload'),
    }, content_type='multipart/form-data')
    assert r.status_code == 400


def test_upload_accepts_jpeg(tech_logged_in, assigned_booking, app):
    tiny = io.BytesIO(b'\xff\xd8\xff\xe0' + b'\x00' * 512)
    r = tech_logged_in.post('/technician/api/uploads', data={
        'ownerType': 'intake', 'ownerId': '1',
        'jobId': str(assigned_booking.id),
        'file': (tiny, 'photo.jpg', 'image/jpeg'),
    }, content_type='multipart/form-data')
    assert r.status_code == 200
    assert r.get_json()['file']['mimeType'] == 'image/jpeg'


def test_unauthenticated_upload_rejected(client, assigned_booking):
    r = client.post('/technician/api/uploads', data={})
    assert r.status_code == 401

def test_upload_rejects_spoofed_mime(tech_logged_in, assigned_booking):
    # Declares image/png but the bytes are HTML.
    r = tech_logged_in.post('/technician/api/uploads', data={
        'ownerType': 'intake', 'ownerId': '1',
        'jobId': str(assigned_booking.id),
        'file': (io.BytesIO(b'<html><script>alert(1)</script></html>'), 'x.html', 'image/png'),
    }, content_type='multipart/form-data')
    assert r.status_code == 400


def test_upload_rejects_other_techs_job(client, app, assigned_booking):
    from app import db, Technician
    from tests.conftest import login_as
    other = Technician(username='TECH-0099', email='o@test.local', full_name='Other Tech', is_active=True)
    other.set_password('otherpass99')
    db.session.add(other)
    db.session.commit()
    login_as(client, other)
    r = client.post('/technician/api/uploads', data={
        'ownerType': 'intake', 'ownerId': '1',
        'jobId': str(assigned_booking.id),
        'file': (io.BytesIO(b'\xff\xd8\xff\xe0' + b'\x00' * 64), 'p.jpg', 'image/jpeg'),
    }, content_type='multipart/form-data')
    assert r.status_code == 400
