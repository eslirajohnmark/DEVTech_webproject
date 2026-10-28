"""Live updates (/api/live) and the Ctrl+Shift+L / Y / U portal shortcuts (/go/<side>)."""
from app import db, Booking, Notification, create_notification, send_message
from tests.conftest import login_as


def test_live_requires_sign_in(client):
    assert client.get('/api/live').status_code == 401


def test_live_reports_counts_and_new_items(client, customer, admin):
    login_as(client, customer)
    first = client.get('/api/live').get_json()
    assert first['ok'] and first['nu'] == 0 and first['mu'] == 0 and first['s']

    create_notification(customer.id, 'Booking Approved', 'See you Monday', 'success', email=False, role='customer')
    send_message(admin, customer, 'Your laptop is ready')
    r = client.get(f"/api/live?n={first['n']}&m={first['m']}").get_json()
    assert r['nu'] == 2 and r['mu'] == 1                       # message also creates a notification
    assert [n['title'] for n in r['new_notifications']][-1] == 'Booking Approved'
    assert r['new_messages'][0]['from'] == 'DEVTech Support'
    assert r['new_messages'][0]['preview'] == 'Your laptop is ready'
    assert r['new_messages'][0]['key'] == admin.key

    again = client.get(f"/api/live?n={r['n']}&m={r['m']}").get_json()
    assert 'new_notifications' not in again and 'new_messages' not in again


def test_live_items_never_leak_between_accounts_with_the_same_id(client, customer, technician):
    assert customer.id == technician.id
    create_notification(technician.id, 'Tech only', 'x', email=False, role='technician')
    login_as(client, customer)
    r = client.get('/api/live?n=0&m=0').get_json()
    assert r['nu'] == 0 and 'new_notifications' not in r


def test_stamp_changes_when_page_data_changes(client, customer, technician, assigned_booking):
    login_as(client, customer)
    before = client.get('/api/live').get_json()['s']
    assert client.get('/api/live').get_json()['s'] == before      # stable while nothing changes
    b = db.session.get(Booking, assigned_booking.id)
    b.status = 'in_progress'
    db.session.commit()
    assert client.get('/api/live').get_json()['s'] != before

    login_as(client, technician)
    tech_before = client.get('/api/live').get_json()['s']
    b.status = 'completed'
    db.session.commit()
    assert client.get('/api/live').get_json()['s'] != tech_before


def test_presence_pings_do_not_change_the_admin_stamp(client, admin, customer):
    login_as(client, admin)
    before = client.get('/api/live').get_json()['s']
    from datetime import datetime
    customer.last_active = datetime.utcnow()
    db.session.commit()
    assert client.get('/api/live').get_json()['s'] == before


def test_pages_carry_live_boot_and_regions(client, customer, technician, admin):
    for account, url in [(customer, '/user/dashboard'), (technician, '/technician/dashboard'),
                         (admin, '/admin/dashboard')]:
        login_as(client, account)
        html = client.get(url).get_data(as_text=True)
        assert 'id="devtechLiveBoot"' in html and 'js/live.js' in html and 'data-live-count' in html
    login_as(client, customer)
    assert 'data-live-region="chat"' in client.get(f'/messages?conv={admin.key}').get_data(as_text=True)


def test_go_routes_open_sign_in_or_dashboard(client, customer, technician, admin):
    assert client.get('/go/admin').headers['Location'].endswith('/admin/login')
    assert client.get('/go/technician').headers['Location'].endswith('/technician/login')
    assert client.get('/go/user').headers['Location'].endswith('/login')
    assert client.get('/go/nowhere').status_code == 404
    login_as(client, admin)
    assert client.get('/go/admin').headers['Location'].endswith('/admin/dashboard')
    assert client.get('/go/technician').headers['Location'].endswith('/technician/login')
    login_as(client, technician)
    assert client.get('/go/technician').headers['Location'].endswith('/technician/dashboard')
    login_as(client, customer)
    assert client.get('/go/user').headers['Location'].endswith('/user/dashboard')


def test_shortcut_script_on_every_kind_of_page(client, customer):
    for url in ('/', '/login', '/register', '/admin/login', '/technician/login', '/technician/register',
                '/forgot-password'):
        assert 'portal-shortcuts.js' in client.get(url).get_data(as_text=True), url
    login_as(client, customer)
    assert 'portal-shortcuts.js' in client.get('/user/dashboard').get_data(as_text=True)


# ---------------------------------------------------------------- waiting ("instant") updates

def _cfg(monkeypatch, app, **values):
    for k, v in values.items():
        monkeypatch.setitem(app.config, k, v)        # undone after the test


def _wait_url(state):
    return (f"/api/live?wait=1&n={state['n']}&m={state['m']}&nu={state['nu']}&mu={state['mu']}"
            f"&s={state['s']}")


def test_wait_returns_at_once_when_the_page_is_out_of_date(client, customer):
    import time as _t
    login_as(client, customer)
    stale = dict(client.get('/api/live').get_json(), nu=99)
    started = _t.monotonic()
    r = client.get(_wait_url(stale)).get_json()
    assert r['ok'] and r['nu'] == 0 and _t.monotonic() - started < 1


def test_wait_holds_until_timeout_when_nothing_changes(app, client, customer, monkeypatch):
    import time as _t
    _cfg(monkeypatch, app, LIVE_WAIT_SECONDS=0.6, LIVE_RECHECK_SECONDS=0.2)
    login_as(client, customer)
    state = client.get('/api/live').get_json()
    started = _t.monotonic()
    r = client.get(_wait_url(state)).get_json()
    assert r['waited'] is True and 0.5 < _t.monotonic() - started < 3


def test_wait_slots_are_capped(app, client, customer, monkeypatch):
    _cfg(monkeypatch, app, LIVE_MAX_WAITERS=0, LIVE_WAIT_SECONDS=5)
    login_as(client, customer)
    state = client.get('/api/live').get_json()
    assert client.get(_wait_url(state)).get_json()['waited'] is False


def test_a_commit_wakes_a_waiting_page_immediately(app, client, customer, monkeypatch):
    import threading
    import time as _t
    _cfg(monkeypatch, app, LIVE_WAIT_SECONDS=10, LIVE_RECHECK_SECONDS=5, LIVE_MAX_WAITERS=4)    # recheck slower than the wake-up
    login_as(client, customer)
    state = client.get('/api/live').get_json()
    result = {}

    def waiter():
        started = _t.monotonic()
        result['body'] = client.get(_wait_url(state)).get_json()
        result['seconds'] = _t.monotonic() - started

    t = threading.Thread(target=waiter)
    t.start()
    _t.sleep(0.4)
    create_notification(customer.id, 'Repair done', 'Ready for pickup', 'success', email=False, role='customer')
    t.join(timeout=8)
    assert result['body']['nu'] == 1, (result, state)
    assert result['body']['new_notifications'][0]['title'] == 'Repair done'
    assert result['seconds'] < 2.5                       # woken by the commit, not the 5 s recheck
