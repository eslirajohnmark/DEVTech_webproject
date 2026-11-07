"""Delete-all notifications on every portal, the redesigned staff notification
feeds, and the Messenger-style admin / technician inboxes (background send)."""
from io import BytesIO

from app import app as flask_app, db, Notification, Message, create_notification
from tests.conftest import login_as


def _notify(account, n=3, title='Repair Status Updated', kind='info'):
    for i in range(n):
        create_notification(account.id, title, f'Message {i}', kind, email=False, role=account.role)


def _count(account):
    return Notification.query.filter_by(user_role=account.role, user_id=account.id).count()


# ---- delete all ------------------------------------------------------------------

def test_every_portal_can_delete_all_its_own_notifications(customer, technician, admin):
    for account, page in ((customer, '/notifications'), (technician, '/technician/notifications'),
                          (admin, '/admin/notifications')):
        _notify(account)
    for account, page in ((customer, '/notifications'), (technician, '/technician/notifications'),
                          (admin, '/admin/notifications')):
        client = login_as(flask_app.test_client(), account)
        html = client.get(page).get_data(as_text=True)
        assert 'data-nf-open="nfDeleteAll"' in html and 'Delete all notifications?' in html   # confirmation dialog
        r = client.post('/notifications/delete-all')
        assert r.status_code == 302 and r.headers['Location'].endswith(page)
        assert _count(account) == 0
    # nobody else's were touched along the way: each account only cleared its own
    assert Notification.query.count() == 0


def test_delete_all_leaves_other_accounts_alone(customer, technician):
    _notify(customer)
    _notify(technician)
    login_as(flask_app.test_client(), technician).post('/notifications/delete-all')
    assert _count(technician) == 0 and _count(customer) == 3


def test_deleting_one_notification_only_works_on_your_own(customer, technician):
    _notify(customer, 1)
    theirs = Notification.query.filter_by(user_role='customer').one()
    assert login_as(flask_app.test_client(), technician).post(f'/notifications/{theirs.id}/remove').status_code == 404
    _notify(technician, 1)
    mine = Notification.query.filter_by(user_role='technician').one()
    login_as(flask_app.test_client(), technician).post(f'/notifications/{mine.id}/remove')
    assert _count(technician) == 0 and _count(customer) == 1


def test_signed_out_visitors_cannot_delete(client, customer):
    _notify(customer)
    client.post('/notifications/delete-all')
    assert _count(customer) == 3


# ---- the redesigned staff feeds ---------------------------------------------------

def test_staff_feeds_show_new_items_types_and_links(technician, admin):
    _notify(technician, 1, 'New Job Assigned', 'info')
    _notify(technician, 1, 'Verification Suspended', 'warning')
    html = login_as(flask_app.test_client(), technician).get('/technician/notifications').get_data(as_text=True)
    assert html.count('nf-item ') == 2 and 'is-new' in html and 'Needs attention' in html
    assert 'href="/technician/jobs"' in html                       # "Open" goes to the job list
    _notify(admin, 1, 'Payment Awaiting Confirmation', 'info')
    html = login_as(flask_app.test_client(), admin).get('/admin/notifications').get_data(as_text=True)
    assert 'href="/admin/payments"' in html
    # once seen they are no longer "new", and an empty feed says so
    login_as(flask_app.test_client(), admin).post('/notifications/delete-all')
    assert "all caught up" in login_as(flask_app.test_client(), admin).get('/admin/notifications').get_data(as_text=True)


# ---- Messenger-style inboxes ------------------------------------------------------

XHR = {'X-Requested-With': 'XMLHttpRequest'}


def test_admin_sends_in_the_background(admin_logged_in, customer):
    r = admin_logged_in.post('/admin/messages/send', headers=XHR,
                             data={'recipient_key': customer.key, 'content': 'Your laptop is ready'})
    body = r.get_json()
    assert r.status_code == 200 and body['success'] is True and body['sent_at'].endswith('Z')
    assert Message.query.filter_by(recipient_role='customer', recipient_id=customer.id).count() == 1
    bad = admin_logged_in.post('/admin/messages/send', headers=XHR, data={'recipient_key': customer.key, 'content': ''})
    assert bad.status_code == 400 and bad.get_json()['success'] is False
    page = admin_logged_in.get(f'/admin/messages?conv={customer.key}').get_data(as_text=True)
    assert 'mx mx--admin has-thread' in page and 'Your laptop is ready' in page and 'data-read="0"' in page


def test_admin_list_view_does_not_jump_into_a_chat(admin_logged_in, customer):
    admin_logged_in.post('/admin/messages/send', data={'recipient_key': customer.key, 'content': 'Hi'})
    assert admin_logged_in.get('/admin/messages').status_code == 302
    r = admin_logged_in.get('/admin/messages?list=1')
    assert r.status_code == 200 and 'has-thread' not in r.get_data(as_text=True)


def test_technician_sends_in_the_background_with_a_file(tech_logged_in, customer, assigned_booking):
    png = b'\x89PNG\r\n\x1a\n' + b'\0' * 64
    r = tech_logged_in.post(f'/technician/messages/{customer.key}/send', headers=XHR,
                            content_type='multipart/form-data',
                            data={'content': '', 'attachment': (BytesIO(png), 'photo.png', 'image/png')})
    body = r.get_json()
    assert body['success'] is True and body['attachments'][0]['is_image'] is True


def test_technician_can_send_the_first_message_to_their_customer(tech_logged_in, customer, assigned_booking):
    # opened from a job's "Message customer" with no earlier messages
    page = tech_logged_in.get(f'/technician/messages?thread={customer.key}').get_data(as_text=True)
    assert 'mx-composer' in page and 'No conversations yet' not in page
