"""Support as a live chat between a customer and the admin team."""
from app import db, Customer, SupportTicket, SupportMessage, Notification, add_support_chat_columns, nav_count_values
from tests.conftest import login_as


def _start(client, body='My laptop repair BK-0001 is late, any update?', topic='booking'):
    return client.post('/api/support/conversations', json={'topic': topic, 'body': body}).get_json()


def test_a_full_conversation_between_customer_and_admin(client, customer, admin):
    login_as(client, customer)
    out = _start(client)
    t = db.session.get(SupportTicket, out['id'])
    assert out['success'] and t.status == 'open' and t.category == 'booking' and len(t.messages) == 1
    assert nav_count_values('admin', admin.id)['tickets'] == 1                 # sidebar badge: needs a reply

    login_as(client, admin)
    items = client.get('/api/admin/support/conversations?view=open').get_json()['items']
    assert items[0]['id'] == t.id and items[0]['unread'] and items[0]['topic'] == 'Repair booking'
    thread = client.get(f'/api/admin/support/conversations/{t.id}').get_json()
    assert thread['customer']['email'] == customer.email and thread['messages'][0]['role'] == 'customer'
    assert not client.get('/api/admin/support/conversations?view=open').get_json()['items'][0]['unread']   # seen

    r = client.post(f'/api/admin/support/conversations/{t.id}/messages', json={'body': 'It is ready today at 3 PM.'})
    assert r.get_json()['success']
    t = db.session.get(SupportTicket, t.id)
    assert t.status == 'waiting' and t.assigned_admin_id == admin.id
    assert Notification.query.filter_by(user_role='customer', user_id=customer.id, title='Support replied').count() == 1

    login_as(client, customer)
    msgs = client.get(f'/api/support/conversations/{t.id}').get_json()['messages']
    assert [m['role'] for m in msgs] == ['customer', 'admin'] and msgs[1]['body'] == 'It is ready today at 3 PM.'
    after = msgs[-1]['id']
    client.post(f'/api/support/conversations/{t.id}/messages', json={'body': 'Thanks! See you then.'})
    assert db.session.get(SupportTicket, t.id).status == 'open'
    new = client.get(f'/api/support/conversations/{t.id}?after={after}').get_json()['messages']
    assert [m['body'] for m in new] == ['Thanks! See you then.']               # only what is new

    login_as(client, admin)
    client.post(f'/api/admin/support/conversations/{t.id}/status', json={'status': 'resolved'})
    t = db.session.get(SupportTicket, t.id)
    assert t.status == 'resolved' and t.messages[-1].sender_role == 'system'
    login_as(client, customer)
    client.post(f'/api/support/conversations/{t.id}/messages', json={'body': 'One more question please'})
    assert db.session.get(SupportTicket, t.id).status == 'open'                # a reply reopens it


def test_customers_only_see_their_own_conversations(client, customer):
    login_as(client, customer)
    t_id = _start(client)['id']
    other = Customer(username='other', email='other@x.test', full_name='Other', is_active=True)
    other.set_password('pass12345')
    db.session.add(other)
    db.session.commit()
    login_as(client, other)
    assert client.get(f'/api/support/conversations/{t_id}').status_code == 404
    assert client.post(f'/api/support/conversations/{t_id}/messages', json={'body': 'hi there'}).status_code == 404


def test_customers_cannot_use_the_admin_desk(client, customer):
    login_as(client, customer)
    t_id = _start(client)['id']
    assert client.get('/api/admin/support/conversations').status_code in (302, 401, 403)
    assert client.post(f'/api/admin/support/conversations/{t_id}/messages', json={'body': 'x'}).status_code in (302, 401, 403)


def test_an_empty_message_is_refused(client, customer):
    login_as(client, customer)
    assert client.post('/api/support/conversations', json={'topic': 'general', 'body': 'hi'}).status_code == 400
    t_id = _start(client)['id']
    assert client.post(f'/api/support/conversations/{t_id}/messages', json={'body': '   '}).status_code == 400


def test_old_tickets_become_conversations(app, customer):
    t = SupportTicket(customer_id=customer.id, subject='Late repair', message='Where is my laptop?',
                      category='general', status='in_progress', admin_response='Ready tomorrow.')
    db.session.add(t)
    db.session.commit()
    add_support_chat_columns()
    t = db.session.get(SupportTicket, t.id)
    assert [m.sender_role for m in t.messages] == ['customer', 'admin'] and t.status == 'waiting'
    add_support_chat_columns()                                                   # safe to repeat
    assert SupportMessage.query.count() == 2


def test_support_pages_show_the_chat(client, customer, admin):
    login_as(client, customer)
    html = client.get('/support').get_data(as_text=True)
    assert 'id="supChat"' in html and 'Send a Support Request' not in html
    login_as(client, admin)
    assert 'id="deskChat"' in client.get('/admin/support').get_data(as_text=True)
