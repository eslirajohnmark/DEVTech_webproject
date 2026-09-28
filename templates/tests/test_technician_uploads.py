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