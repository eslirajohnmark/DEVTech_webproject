"""Render + Supabase + Brevo: PostgreSQL links, uploads kept in Supabase Storage,
and email through Brevo. Supabase and Brevo are faked; nothing leaves the machine."""
import io
import os

import pytest
from PIL import Image

from app import database_url
from services import email_service, file_store


class FakeResponse:
    def __init__(self, status=200, content=b'', text=''):
        self.status_code, self.content, self.text = status, content, text

    @property
    def ok(self):
        return 200 <= self.status_code < 300


@pytest.fixture
def bucket(monkeypatch):
    """A fake Supabase Storage bucket: {object key: bytes}, plus the requests made."""
    store, calls = {}, []
    monkeypatch.setenv('SUPABASE_URL', 'https://abc.supabase.co')
    monkeypatch.setenv('SUPABASE_SECRET_KEY', 'sb_secret_test')
    monkeypatch.setenv('SUPABASE_BUCKET', 'devtech-uploads')

    def post(url, data=None, headers=None, timeout=None):
        calls.append(('POST', url, headers))
        store[url.split('/devtech-uploads/', 1)[1]] = data
        return FakeResponse(200)

    def get(url, headers=None, timeout=None):
        calls.append(('GET', url, headers))
        key = url.split('/devtech-uploads/', 1)[1]
        return FakeResponse(200, store[key]) if key in store else FakeResponse(404)

    def delete(url, json=None, headers=None, timeout=None):
        calls.append(('DELETE', url, headers))
        for key in json['prefixes']:
            store.pop(key, None)
        return FakeResponse(200)

    monkeypatch.setattr(file_store.requests, 'post', post)
    monkeypatch.setattr(file_store.requests, 'get', get)
    monkeypatch.setattr(file_store.requests, 'delete', delete)
    return store, calls


def test_supabase_and_render_links_use_psycopg():
    assert database_url('postgresql://postgres.abc:pw@aws-0-ap-southeast-1.pooler.supabase.com:5432/postgres') == \
        'postgresql+psycopg://postgres.abc:pw@aws-0-ap-southeast-1.pooler.supabase.com:5432/postgres'
    assert database_url('postgres://u:p@h/db') == 'postgresql+psycopg://u:p@h/db'
    assert database_url('mysql+pymysql://u:p@h/db') == 'mysql+pymysql://u:p@h/db'      # unchanged
    assert database_url('sqlite:///x.db') == 'sqlite:///x.db'


def test_files_go_to_the_bucket_and_come_back_after_a_restart(tmp_path, bucket):
    store, calls = bucket
    path = tmp_path / 'tech' / 'abc123.jpg'
    path.parent.mkdir()
    path.write_bytes(b'photo bytes')
    assert file_store.saved(str(path)) and store['tech/abc123.jpg'] == b'photo bytes'
    assert calls[0][2] == {'apikey': 'sb_secret_test', 'Content-Type': 'image/jpeg', 'x-upsert': 'true'}

    path.unlink()                                       # the host wiped its disk
    assert file_store.exists(str(path)) and path.read_bytes() == b'photo bytes'

    file_store.removed(str(path))
    assert not path.exists() and 'tech/abc123.jpg' not in store
    assert not file_store.exists(str(path))


def test_a_legacy_service_role_key_is_also_sent_as_bearer(tmp_path, bucket, monkeypatch):
    monkeypatch.setenv('SUPABASE_SECRET_KEY', 'eyJhbGciOi.legacy.jwt')
    store, calls = bucket
    p = tmp_path / 'avatars' / 'f.png'
    p.parent.mkdir()
    p.write_bytes(b'x')
    file_store.saved(str(p))
    assert calls[-1][2]['Authorization'] == 'Bearer eyJhbGciOi.legacy.jwt'


def test_without_supabase_files_stay_on_disk_only(tmp_path, monkeypatch):
    monkeypatch.delenv('SUPABASE_URL', raising=False)
    monkeypatch.delenv('SUPABASE_SECRET_KEY', raising=False)
    monkeypatch.delenv('SUPABASE_SERVICE_KEY', raising=False)
    p = tmp_path / 'x.pdf'
    assert not file_store.enabled() and not file_store.saved(str(p)) and not file_store.exists(str(p))


def _png():
    out = io.BytesIO()
    Image.new('RGB', (20, 20), 'red').save(out, 'PNG')
    return out.getvalue()


def test_a_report_photo_survives_a_wiped_disk(client, technician, assigned_booking, bucket):
    from tests.conftest import login_as
    from models.technician_models import UploadedFile
    from services.upload_service import path_for
    store, _ = bucket
    login_as(client, technician)
    r = client.post('/technician/api/uploads', content_type='multipart/form-data', data={
        'file': (io.BytesIO(_png()), 'before.png', 'image/png'), 'ownerType': 'report', 'ownerId': '',
        'jobId': str(assigned_booking.id)})
    f = UploadedFile.query.get(r.get_json()['file']['id'])
    assert f'tech/{f.filename}' in store
    os.remove(path_for(f))                              # restart: disk is empty again
    shown = client.get(f'/technician/api/uploads/{f.id}')
    assert shown.status_code == 200 and shown.data == _png()


def test_email_goes_through_brevo_when_its_key_is_set(monkeypatch):
    sent = {}

    def post(url, json=None, headers=None, timeout=None):
        sent.update(url=url, json=json, headers=headers)
        return FakeResponse(201)

    monkeypatch.setenv('BREVO_API_KEY', 'xkeysib-test')
    monkeypatch.setenv('MAIL_FROM', 'DEVTech <hello@devtech.example.com>')
    monkeypatch.setattr(email_service.requests, 'post', post)
    assert email_service.is_enabled()
    assert email_service.send_now('cara@gmail.com', 'Booking confirmed', '<p>Hi</p>', 'Hi')
    assert sent['url'] == 'https://api.brevo.com/v3/smtp/email' and sent['headers']['api-key'] == 'xkeysib-test'
    assert sent['json']['sender'] == {'name': 'DEVTech', 'email': 'hello@devtech.example.com'}
    assert sent['json']['to'] == [{'email': 'cara@gmail.com'}] and sent['json']['htmlContent'] == '<p>Hi</p>'


def test_brevo_needs_a_sender_address(monkeypatch):
    monkeypatch.setenv('BREVO_API_KEY', 'xkeysib-test')
    monkeypatch.delenv('MAIL_FROM', raising=False)
    monkeypatch.setattr(email_service.requests, 'post', lambda *a, **k: pytest.fail('must not send'))
    assert not email_service.send_now('cara@gmail.com', 'S', '<p>x</p>', 'x')
