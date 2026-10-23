"""Message attachments: validation, storage, access control, and display."""
import io

from app import db, Customer, Technician, Admin, Message, MessageAttachment
from tests.conftest import login_as

PNG = b'\x89PNG\r\n\x1a\n' + b'\x00' * 64


def _png(name='photo.png'):
    return (io.BytesIO(PNG), name, 'image/png')


def test_customer_sends_image_to_admin(client, customer, admin):
    login_as(client, customer)
    r = client.post(f'/messages/{admin.key}/send', data={'content': 'See the crack', 'attachment': _png()},
                    content_type='multipart/form-data')
    body = r.get_json()
    assert body['success'] is True
    assert body['attachments'][0]['is_image'] is True
    att = MessageAttachment.query.one()
    assert att.original_name == 'photo.png' and att.mime_type == 'image/png'

    url = body['attachments'][0]['url']
    assert client.get(url).status_code == 200                 # sender
    login_as(client, admin)
    assert client.get(url).status_code == 200                 # recipient
    html = client.get(f'/admin/messages?conv={customer.key}').get_data(as_text=True)
    assert url in html


def test_attachment_hidden_from_third_party(client, customer, admin):
    login_as(client, customer)
    url = client.post(f'/messages/{admin.key}/send', data={'attachment': _png()},
                      content_type='multipart/form-data').get_json()['attachments'][0]['url']
    stranger = Customer(username='s', email='s@test.local', full_name='Stranger')
    stranger.set_password('strangerpass')
    db.session.add(stranger)
    db.session.commit()
    login_as(client, stranger)
    assert client.get(url).status_code == 404
    client.get('/logout')
    assert client.get(url).status_code == 302                 # not signed in


def test_attachment_only_message_and_preview(client, customer, admin):
    login_as(client, customer)
    r = client.post(f'/messages/{admin.key}/send', data={'attachment': _png()},
                    content_type='multipart/form-data')
    assert r.get_json()['success'] is True
    assert Message.query.one().content == ''
    login_as(client, admin)
    assert '📎 Attachment' in client.get('/admin/messages', follow_redirects=True).get_data(as_text=True)


def test_rejects_spoofed_and_empty_messages(client, customer, admin):
    login_as(client, customer)
    r = client.post(f'/messages/{admin.key}/send',
                    data={'attachment': (io.BytesIO(b'<script>x</script>'), 'x.png', 'image/png')},
                    content_type='multipart/form-data')
    assert r.status_code == 400
    r = client.post(f'/messages/{admin.key}/send', data={'content': ''}, content_type='multipart/form-data')
    assert r.status_code == 400
    assert Message.query.count() == 0 and MessageAttachment.query.count() == 0


def test_admin_and_technician_can_attach(client, admin, technician, customer, assigned_booking):
    login_as(client, admin)
    client.post('/admin/messages/send', data={'recipient_key': customer.key, 'attachment': _png('a.png')},
                content_type='multipart/form-data')
    login_as(client, technician)
    client.post(f'/technician/messages/{customer.key}/send',
                data={'content': 'Before photo', 'attachment': _png('t.png')},
                content_type='multipart/form-data')
    names = sorted(a.original_name for a in MessageAttachment.query.all())
    assert names == ['a.png', 't.png']
    html = client.get(f'/technician/messages?thread={customer.key}').get_data(as_text=True)
    assert '/messages/attachments/' in html
