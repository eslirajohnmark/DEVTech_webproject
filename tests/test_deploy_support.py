"""Hosting support: the init-db command for hosts without a shell, and BEHIND_PROXY."""
import os
import subprocess
import sys

from app import Service, ServiceCategory, SystemSetting


def test_init_db_command_sets_up_an_empty_database(app):
    result = app.test_cli_runner().invoke(args=['init-db'])
    assert result.exit_code == 0 and 'Database ready.' in result.output
    assert Service.query.filter_by(is_active=True).count() == 166 and ServiceCategory.query.count() == 6
    assert SystemSetting.query.filter_by(setting_key='booking_fee').one().value == '100'
    again = app.test_cli_runner().invoke(args=['init-db'])           # safe on every build
    assert again.exit_code == 0 and Service.query.count() == 166


def _wsgi_class(env_extra, tmp_path):
    env = dict(os.environ, DATABASE_URL='sqlite:///' + str(tmp_path / 'p.db').replace('\\', '/'),
               SECRET_KEY='x' * 40, FLASK_ENV='development', **env_extra)
    env.pop('BEHIND_PROXY', None) if 'BEHIND_PROXY' not in env_extra else None
    out = subprocess.run([sys.executable, '-c', 'import app; print(type(app.app.wsgi_app).__name__)'],
                         capture_output=True, text=True, env=env, cwd=os.path.dirname(os.path.dirname(__file__)))
    return out.stdout.strip().splitlines()[-1]


def test_behind_proxy_trusts_the_hosts_forwarded_headers(tmp_path):
    assert _wsgi_class({'BEHIND_PROXY': '1'}, tmp_path) == 'ProxyFix'
    assert _wsgi_class({}, tmp_path) != 'ProxyFix'                    # off unless asked for


def test_https_links_behind_a_proxy(app):
    from werkzeug.middleware.proxy_fix import ProxyFix
    original = app.wsgi_app
    app.wsgi_app = ProxyFix(original, x_for=1, x_proto=1, x_host=1)
    try:
        client = app.test_client()
        r = client.get('/login/google', headers={'X-Forwarded-Proto': 'https', 'X-Forwarded-Host': 'devtech.onrender.com'})
        assert r.status_code == 302
        assert 'redirect_uri=https%3A%2F%2Fdevtech.onrender.com%2Flogin%2Fgoogle%2Fcallback' in r.headers['Location']
    finally:
        app.wsgi_app = original


def test_without_online_payments_bookings_use_cash_after_repair_and_no_fee(customer_logged_in):
    from datetime import date, timedelta
    from decimal import Decimal
    from app import db, Booking, Transaction
    cat = ServiceCategory(name='Repair', slug='repair', is_active=True)
    db.session.add(cat)
    db.session.flush()
    service = Service(category_id=cat.id, name='Screen Fix', price=1500, is_active=True, device_types='laptop')
    db.session.add(service)
    db.session.commit()
    page = customer_logged_in.get('/user/book').get_data(as_text=True)      # PayMongo is off in tests
    assert 'id="payment-qr"' not in page and 'value="C.A.R" checked' in page and 'data-fee=' not in page
    data = {'service_id': str(service.id), 'device_type': 'Laptop', 'booking_date': (date.today() + timedelta(days=1)).isoformat(),
            'problem_description': 'The laptop screen is cracked after it fell off the table', 'booking_time': '10:00',
            'in_shop': 'on', 'accept_terms': 'on'}
    customer_logged_in.post('/user/service-request', data=dict(data, payment_method='QR Ph'))
    assert Booking.query.count() == 0                                        # QR cannot be paid right now
    customer_logged_in.post('/user/service-request', data=dict(data, payment_method='C.A.R'))
    b = Booking.query.one()
    assert b.booking_fee is None and Transaction.query.one().amount == Decimal('1500.00')


def test_on_vercel_the_app_writes_only_to_the_temp_folder(tmp_path):
    """VERCEL=1: temp-folder uploads, console logs, proxy headers trusted, pages poll."""
    env = dict(os.environ, VERCEL='1', FLASK_ENV='production', SECRET_KEY='x' * 64,
               DATABASE_URL='sqlite:///' + (tmp_path / 'v.db').as_posix())
    env.pop('BEHIND_PROXY', None)
    env.pop('LIVE_MAX_WAITERS', None)
    code = ('import tempfile, logging, app\n'
            'print(app.app.instance_path.startswith(tempfile.gettempdir()))\n'
            'print(app.app.config["TECH_UPLOAD_FOLDER"].startswith(tempfile.gettempdir()))\n'
            'print(type(app.app.wsgi_app).__name__)\n'
            'print(app.app.config["LIVE_MAX_WAITERS"])\n'
            'print(any(type(h) is logging.StreamHandler for h in app.app.logger.handlers))\n')
    out = subprocess.run([sys.executable, '-c', code], capture_output=True, text=True, env=env,
                         cwd=os.path.dirname(os.path.dirname(__file__)))
    assert out.stdout.strip().splitlines()[-5:] == ['True', 'True', 'ProxyFix', '0', 'True'], out.stderr[-500:]


def test_on_vercel_emails_go_out_before_the_page_ends(monkeypatch):
    from services import email_service
    sent = []
    monkeypatch.setenv('VERCEL', '1')
    monkeypatch.setenv('BREVO_API_KEY', 'xkeysib-test')
    monkeypatch.setattr(email_service, 'send_now', lambda *a: sent.append(a) or True)
    assert email_service.queue_email('cara@gmail.com', 'Hi', '<p>x</p>', 'x')
    assert sent and sent[0][0] == 'cara@gmail.com'          # sent now, not handed to a thread
