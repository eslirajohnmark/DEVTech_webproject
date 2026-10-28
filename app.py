import sys
# Make `from app import db, Customer` (used by blueprints/commands/models) resolve to THIS
# module even when started with `python app.py` (otherwise app.py is imported twice
# and the blueprint imports fail circularly).
sys.modules.setdefault('app', sys.modules[__name__])
 
from flask import (Flask, render_template, request, redirect, url_for, session,
                   flash, jsonify, g, abort, json)
from flask_sqlalchemy import SQLAlchemy
from flask_bcrypt import Bcrypt
from functools import wraps
import os
import hashlib
import hmac
import logging
from logging.handlers import RotatingFileHandler
from datetime import datetime, timedelta
from types import SimpleNamespace
import re
import secrets
import shutil
from werkzeug.utils import secure_filename
from sqlalchemy import text, or_, and_, func, case as sa_case
from sqlalchemy.exc import IntegrityError
from sqlalchemy import event as sa_event
from sqlalchemy.orm import Session as SASession
import threading
import time
from markupsafe import escape as escape_markupsafe
from jinja2.utils import htmlsafe_json_dumps
from dotenv import load_dotenv
from authlib.integrations.flask_client import OAuth
from flask_wtf import CSRFProtect
from flask_wtf.csrf import CSRFError
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_caching import Cache
from flask_talisman import Talisman
from commands import register_commands
from flask import send_file
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired
from services import email_service, profile_presets
from services.job_status import (STAGES, STATUS_LABELS, ACTIVE_STATUSES,
                                 FINISHED_STATUSES, SLOT_STATUSES)
 
load_dotenv()

# ==================== ENVIRONMENT ====================
IS_PRODUCTION = os.environ.get('FLASK_ENV', 'development') == 'production'
 
app = Flask(__name__)
# No secrets in source. SECRET_KEY and DATABASE_URL come from the environment / .env.
_secret_key = os.environ.get('SECRET_KEY', '')
if not _secret_key:
    if IS_PRODUCTION:
        raise RuntimeError('SECRET_KEY is not set. Put a long random value in your production .env file.')
    # Dev only: a throwaway key, so sessions reset whenever the server restarts.
    _secret_key = secrets.token_urlsafe(64)
    print('WARNING: SECRET_KEY is not set; using a temporary key. Set it in .env.')
app.config['SECRET_KEY'] = _secret_key

if not os.environ.get('DATABASE_URL'):
    raise RuntimeError('DATABASE_URL is not set. Copy .env.example to .env and fill it in.')
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ['DATABASE_URL']
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {'pool_recycle': 280, 'pool_pre_ping': True}
app.config['UPLOAD_FOLDER'] = 'static/uploads'
# Payment receipts are private: kept outside static/ and served by receipt_file().
app.config['RECEIPT_UPLOAD_FOLDER'] = os.path.join(app.instance_path, 'uploads', 'receipts')
app.config['MESSAGE_UPLOAD_FOLDER'] = os.path.join(app.instance_path, 'uploads', 'messages')
app.config['AVATAR_UPLOAD_FOLDER'] = os.path.join(app.instance_path, 'uploads', 'avatars')
app.config['TECH_UPLOAD_FOLDER'] = os.path.join(app.instance_path, 'uploads', 'tech')
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024
app.config['DEBUG'] = not IS_PRODUCTION
 
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['SESSION_COOKIE_SECURE'] = IS_PRODUCTION
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=7)
 
# ==================== LOGGING ====================
if not app.debug:
    os.makedirs('logs', exist_ok=True)
    file_handler = RotatingFileHandler('logs/devtech.log', maxBytes=5 * 1024 * 1024, backupCount=5)
    file_handler.setFormatter(logging.Formatter(
        '%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]'))
    file_handler.setLevel(logging.INFO)
    app.logger.addHandler(file_handler)
    app.logger.setLevel(logging.INFO)
    app.logger.info('DEVTech startup (production mode)')

# ==================== CSRF PROTECTION ====================
# ==================== CSRF ====================
csrf = CSRFProtect(app)
 
@app.errorhandler(CSRFError)
def handle_csrf_error(e):
    if request.path.startswith('/technician/api/'):
        return jsonify({'ok': False, 'reason': 'Security token missing or expired. Refresh and retry.'}), 400
    if request.path.startswith('/api/'):
        return jsonify({'success': False, 'ok': False,
                        'message': 'Your session security token expired. Please refresh the page and try again.',
                        'reason': 'Your session security token expired. Please refresh the page and try again.'}), 400
    flash('Your form session expired. Please try again.', 'danger')
    return redirect(request.referrer or url_for('home'))
 
# ==================== RATE LIMITING ====================
# The default is generous on purpose: many customers share one public IP
# (mobile data, school Wi-Fi). Login/registration/contact have their own strict
# limits, and the pages' background polls are exempt (see @limiter.exempt).
limiter = Limiter(key_func=get_remote_address, app=app, default_limits=['3000 per hour'],
                  storage_uri=os.environ.get('RATELIMIT_STORAGE_URI', 'memory://'))
 
# ==================== CACHING ====================
cache = Cache(app, config={
    'CACHE_TYPE': os.environ.get('CACHE_TYPE', 'SimpleCache'),
    'CACHE_REDIS_URL': os.environ.get('CACHE_REDIS_URL', ''),
    'CACHE_DEFAULT_TIMEOUT': 60,
})

# ==================== TECHNICIAN CSP NONCE ====================
# Registered BEFORE Talisman on purpose: after_request hooks run in reverse order,
# so this one runs last and its strict CSP replaces Talisman's on /technician/* only.
@app.before_request
def _make_tech_nonce():
    g.tech_nonce = secrets.token_urlsafe(16)
 
@app.context_processor
def _inject_tech_nonce():
    return {'tech_nonce': getattr(g, 'tech_nonce', '')}

@app.context_processor
def _inject_technician_globals():
    return {
        'today_str': datetime.utcnow().strftime('%a, %b %d'),
    }

@app.context_processor
def _inject_job_status():
    return {'job_stages': STAGES, 'status_labels': STATUS_LABELS}

@app.context_processor
def _inject_nav_counts():
    """nav_counts() for sidebar badges. A function, so the count queries only
    run on pages whose template actually calls it."""
    def nav_counts():
        uid, role = session.get('user_id'), session.get('role')
        if not uid or role not in ('customer', 'technician', 'admin'):
            return {}
        counts = {
            'notifications': Notification.query.filter_by(user_role=role, user_id=uid, is_read=False).count(),
            'messages': Message.query.filter_by(recipient_role=role, recipient_id=uid, is_read=False).count(),
        }
        if session.get('role') == 'admin':
            counts['tickets'] = SupportTicket.query.filter(SupportTicket.status != 'resolved').count()
            counts['inquiries'] = ContactInquiry.query.filter_by(status='new').count()
            counts['refunds'] = Refund.query.filter_by(status='pending').count()
        return counts
    return {'nav_counts': nav_counts}

@app.context_processor
def _inject_profile():
    """signed_in() -> the current account (or None), for avatars in the layouts."""
    def signed_in():
        try:
            return current_account()
        except Exception:
            db.session.rollback()
            return None
    return {'signed_in': signed_in}

# A global (not context) so imported macros like partials/profile_studio.html see it too.
app.jinja_env.globals['profile_presets'] = profile_presets

@app.context_processor
def _inject_site_details():
    """site() -> business details from System Settings (one query per request)."""
    def site():
        if 'site_details' not in g:
            try:
                values = {s.setting_key: (s.value or '').strip() for s in SystemSetting.query.all()}
            except Exception:
                db.session.rollback()
                values = {}
            g.site_details = {
                'name': values.get('system_name') or 'DEVTech Computer Services',
                'phone': values.get('contact_phone', ''),
                'email': values.get('contact_email') or values.get('system_email', ''),
                'address': values.get('contact_address', ''),
                'hours': values.get('business_hours', ''),
                'gcash_account': values.get('gcash_account', ''),
                'gcash_name': values.get('gcash_name') or values.get('system_name') or 'DEVTech Computer Services',
                'gcash_enabled': values.get('enable_gcash', 'true') == 'true',
                'cod_enabled': values.get('enable_cod', 'true') == 'true',
            }
        return g.site_details
    return {'site': site, 'current_year': datetime.utcnow().year}

MONITOR_STAGES = STAGES  
 
@app.after_request
def _technician_csp(resp):
    if request.path.startswith('/technician'):
        n = getattr(g, 'tech_nonce', '')
        resp.headers['Content-Security-Policy'] = (
            "default-src 'self'; "
            f"script-src 'self' 'nonce-{n}'; "
            "style-src 'self' 'unsafe-inline' https://cdnjs.cloudflare.com https://fonts.googleapis.com; "
            "font-src 'self' https://cdnjs.cloudflare.com https://fonts.gstatic.com; "
            "img-src 'self' data: https:; connect-src 'self'; frame-ancestors 'none'")
    return resp
 
# ==================== SECURITY HEADERS ====================
csp = {
    'default-src': "'self'",
    'style-src': ["'self'", "'unsafe-inline'", 'https://cdnjs.cloudflare.com',
                  'https://fonts.googleapis.com', 'https://unpkg.com'],
    'font-src': ["'self'", 'https://cdnjs.cloudflare.com', 'https://fonts.gstatic.com'],
    'script-src': ["'self'", "'unsafe-inline'", 'https://unpkg.com', 'https://cdn.jsdelivr.net'],
    'img-src': ["'self'", 'data:', 'https:'],
    'connect-src': ["'self'", 'https://nominatim.openstreetmap.org'],
}
Talisman(app, force_https=IS_PRODUCTION, strict_transport_security=IS_PRODUCTION,
         session_cookie_secure=IS_PRODUCTION, content_security_policy=csp)
 

# ==================== DATABASE / BCRYPT (created early: /healthz needs db) ====================
db = SQLAlchemy(app)
bcrypt = Bcrypt(app)
 
@app.route('/healthz')
def healthz():
    try:
        db.session.execute(text('SELECT 1'))
        return jsonify({'status': 'ok', 'database': 'connected'}), 200
    except Exception as e:
        app.logger.error(f'Health check failed: {e}')
        return jsonify({'status': 'error', 'database': 'unreachable'}), 503

PORTAL_ENTRY = {'admin': ('admin', 'admin_dashboard', 'admin_login'),
                'technician': ('technician', 'technician.dashboard', 'technician.login'),
                'user': ('customer', 'user_dashboard', 'login')}

@app.route('/go/<side>')
def go_to_portal(side):
    """Target of the Ctrl+Shift+L / Y / U shortcuts: that portal's dashboard when
    already signed in there, otherwise its sign-in page."""
    if side not in PORTAL_ENTRY:
        abort(404)
    role, dashboard, sign_in = PORTAL_ENTRY[side]
    signed_in_here = session.get('role') == role and current_account() is not None
    return redirect(url_for(dashboard if signed_in_here else sign_in))

@app.route('/favicon.ico')
def favicon():
    # Browsers ask for /favicon.ico on pages without a <link rel="icon">.
    return redirect(url_for('static', filename='images/favicon.svg'), code=301)

# ==================== OAUTH(google/facebook) ====================
oauth = OAuth(app)
oauth.register(name='google',
               client_id=os.environ.get('GOOGLE_CLIENT_ID'),
               client_secret=os.environ.get('GOOGLE_CLIENT_SECRET'),
               server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
               client_kwargs={'scope': 'openid email profile'})
oauth.register(name='facebook',
               client_id=os.environ.get('FACEBOOK_CLIENT_ID'),
               client_secret=os.environ.get('FACEBOOK_CLIENT_SECRET'),
               access_token_url='https://graph.facebook.com/v19.0/oauth/access_token',
               authorize_url='https://www.facebook.com/v19.0/dialog/oauth',
               api_base_url='https://graph.facebook.com/v19.0/',
               client_kwargs={'scope': 'email public_profile'})
 
# HTML-safe: escapes < > & ' so the output can't break out of a <script> block
# or a single-quoted attribute. Never replace this with a plain json.dumps.
app.jinja_env.filters['tojson'] = lambda obj: htmlsafe_json_dumps(obj, default=str)
app.jinja_env.filters['escape'] = lambda s: escape_markupsafe(s) if s else ''
# For values a <script> later drops into innerHTML: HTML-escape the text, then
# JSON-encode it so quotes/newlines can't break out of the script. None -> null.
app.jinja_env.filters['js_html'] = lambda v: htmlsafe_json_dumps(
    None if v is None else str(escape_markupsafe(v)))
app.jinja_env.filters['fromjson'] = lambda s: json.loads(s) if s else []
 
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(app.config['TECH_UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(app.config['RECEIPT_UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(app.config['MESSAGE_UPLOAD_FOLDER'], exist_ok=True)
 
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'pdf'}
 
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS
 
FILE_SIGNATURES = {
    'png': [b'\x89PNG\r\n\x1a\n'], 'jpg': [b'\xff\xd8\xff'], 'jpeg': [b'\xff\xd8\xff'],
    'gif': [b'GIF87a', b'GIF89a'], 'pdf': [b'%PDF-'],
}
MAX_RECEIPT_SIZE = 5 * 1024 * 1024
 
def validate_uploaded_file(file_storage, extension):
    signatures = FILE_SIGNATURES.get(extension, [])
    if not signatures:
        return False, 'Unsupported file type.'
    file_storage.stream.seek(0, os.SEEK_END)
    size = file_storage.stream.tell()
    file_storage.stream.seek(0)
    if size > MAX_RECEIPT_SIZE:
        return False, 'File is too large. Maximum size is 5MB.'
    if size == 0:
        return False, 'The uploaded file is empty.'
    header = file_storage.stream.read(8)
    file_storage.stream.seek(0)
    if not any(header.startswith(sig) for sig in signatures):
        return False, 'The file content does not match its extension. Please upload a genuine JPG, PNG, GIF, or PDF.'
    return True, None

# ==================== DATABASE MODELS ====================
 
# ==================== ACCOUNTS: three separate tables ====================
# Customers, technicians and admins each have their own table and their own
# login. An account is identified by (role, id): ids are only unique within a
# table, so customer 1 and admin 1 are different people. The session stores
# both session['role'] and session['user_id'].

class AccountMixin:
    ROLE = None

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    full_name = db.Column(db.String(100), nullable=False)
    phone = db.Column(db.String(20))
    is_active = db.Column(db.Boolean, default=True)
    last_active = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    # Profile look, chosen by the account holder (see services/profile_presets.py).
    display_name = db.Column(db.String(60))
    headline = db.Column(db.String(120))
    avatar_file = db.Column(db.String(64))
    avatar_icon = db.Column(db.String(30))
    avatar_color = db.Column(db.String(20))
    avatar_frame = db.Column(db.String(20))
    banner = db.Column(db.String(20))

    @property
    def role(self):
        return self.ROLE

    @property
    def shown_name(self):
        """What the account wants to be called; falls back to the full name."""
        return (self.display_name or '').strip() or self.full_name or ''

    @property
    def initials(self):
        parts = self.shown_name.split()
        return ''.join(p[0] for p in parts[:2]).upper() or '?'

    @property
    def avatar_color_key(self):
        return profile_presets.pick(self.avatar_color, profile_presets.AVATAR_COLORS,
                                    profile_presets.DEFAULT_COLOR[self.ROLE])

    @property
    def avatar_frame_key(self):
        return profile_presets.pick(self.avatar_frame, profile_presets.AVATAR_FRAMES,
                                    profile_presets.DEFAULT_FRAME)

    @property
    def banner_key(self):
        return profile_presets.pick(self.banner, profile_presets.BANNERS,
                                    profile_presets.DEFAULT_BANNER[self.ROLE])

    @property
    def avatar_mode(self):
        if self.avatar_file:
            return 'photo'
        return 'icon' if self.avatar_icon in profile_presets.AVATAR_ICONS else 'initials'

    @property
    def avatar_url(self):
        return url_for('account_avatar', filename=self.avatar_file) if self.avatar_file else None

    @property
    def key(self):
        """'customer-5' / 'technician-2' / 'admin-1': unique across all three tables."""
        return f'{self.ROLE}-{self.id}'

    def set_password(self, password):
        self.password_hash = bcrypt.generate_password_hash(password).decode('utf-8')

    def check_password(self, password):
        stored = self.password_hash or ''
        # Older databases may hold Werkzeug hashes ("pbkdf2:..." / "scrypt:...").
        # Accept them once and upgrade to bcrypt so the next check is the normal path.
        if stored.startswith(('pbkdf2:', 'scrypt:')):
            from werkzeug.security import check_password_hash as werkzeug_check
            if not werkzeug_check(stored, password):
                return False
            self.set_password(password)
            db.session.commit()
            return True
        try:
            return bcrypt.check_password_hash(stored, password)
        except ValueError:          # not a bcrypt hash at all: never matches
            return False

    def to_dict(self):
        return {'id': self.id, 'role': self.ROLE, 'username': getattr(self, 'username', None),
                'email': self.email, 'full_name': self.full_name, 'phone': self.phone,
                'address': getattr(self, 'address', None), 'city': getattr(self, 'city', None),
                'province': getattr(self, 'province', None), 'postal_code': getattr(self, 'postal_code', None),
                'is_active': self.is_active,
                'created_at': self.created_at.strftime('%Y-%m-%d %H:%M:%S') if self.created_at else None}


class Customer(AccountMixin, db.Model):
    __tablename__ = 'customers'
    __table_args__ = (db.UniqueConstraint('oauth_provider', 'oauth_id', name='uq_customers_oauth_identity'),)
    ROLE = 'customer'

    username = db.Column(db.String(80), unique=True, nullable=False)
    address = db.Column(db.String(255))
    city = db.Column(db.String(50))
    province = db.Column(db.String(50))
    postal_code = db.Column(db.String(10))
    latitude = db.Column(db.Numeric(10, 7))
    longitude = db.Column(db.Numeric(10, 7))
    birth_date = db.Column(db.Date)
    oauth_provider = db.Column(db.String(20), nullable=True)
    oauth_id = db.Column(db.String(255), nullable=True)

    bookings = db.relationship('Booking', back_populates='customer', lazy=True)
    transactions = db.relationship('Transaction', back_populates='customer', lazy=True)
    support_tickets = db.relationship('SupportTicket', back_populates='customer', lazy=True)
    shopping_carts = db.relationship('ShoppingCart', back_populates='customer', lazy=True)
    orders = db.relationship('Order', back_populates='customer', lazy=True)
    preferences = db.relationship('UserPreference', back_populates='customer', uselist=False)

    # Technician-only fields, so templates can ask any account safely.
    id_verified = None
    id_type = None


class Technician(AccountMixin, db.Model):
    __tablename__ = 'technicians'
    ROLE = 'technician'

    username = db.Column(db.String(80), unique=True, nullable=False)   # Tech ID, e.g. TECH-0001
    address = db.Column(db.String(255))
    city = db.Column(db.String(50))
    province = db.Column(db.String(50))
    # id_number: admin-only audit record, never serialized to customers.
    id_type = db.Column(db.String(30), nullable=True)
    id_number = db.Column(db.String(50), nullable=True)
    id_verified = db.Column(db.Boolean, default=False)
    id_verified_at = db.Column(db.DateTime, nullable=True)

    jobs = db.relationship('Booking', back_populates='technician', lazy=True)


class Admin(AccountMixin, db.Model):
    __tablename__ = 'admins'
    ROLE = 'admin'

    username = db.Column(db.String(80), unique=True, nullable=False)

    id_verified = None
    id_type = None


ACCOUNT_MODELS = {'customer': Customer, 'technician': Technician, 'admin': Admin}
ROLES = tuple(ACCOUNT_MODELS)


def get_account(role, account_id):
    """The Customer/Technician/Admin with this id, or None."""
    model = ACCOUNT_MODELS.get(role)
    if not model or not account_id:
        return None
    try:
        return db.session.get(model, int(account_id))
    except (TypeError, ValueError):
        return None


def current_account():
    """The signed-in account (any role), cached for the request."""
    # Keyed by the session identity: g can outlive one request (e.g. an app
    # context held open around several test-client requests).
    ident = (session.get('role'), session.get('user_id'))
    cached = g.get('current_account')
    if cached is None or cached[0] != ident:
        cached = g.current_account = (ident, get_account(*ident))
    return cached[1]


def find_account_by_email(email):
    """Account with this email in any of the three tables (emails are unique overall)."""
    email = (email or '').strip().lower()
    if not email:
        return None
    for model in ACCOUNT_MODELS.values():
        account = model.query.filter(func.lower(model.email) == email).first()
        if account:
            return account
    return None


def email_in_use(email, exclude=None):
    """True if another account (in any table) already uses this email."""
    other = find_account_by_email(email)
    return bool(other and (exclude is None or other.key != exclude.key))


def parse_account_key(key):
    """'technician-3' -> ('technician', 3); anything invalid -> (None, None)."""
    role, _, raw_id = (key or '').partition('-')
    if role in ACCOUNT_MODELS and raw_id.isdigit():
        return role, int(raw_id)
    return None, None


def all_accounts():
    """Every account from all three tables, newest first."""
    rows = Customer.query.all() + Technician.query.all() + Admin.query.all()
    return sorted(rows, key=lambda a: a.created_at or datetime.min, reverse=True)


def login_account(account, remember=False):
    """Start a fresh session for this account."""
    session.clear()
    session.permanent = bool(remember)
    session['user_id'] = account.id
    session['role'] = account.ROLE
    session['username'] = getattr(account, 'username', None) or account.full_name
    g.pop('current_account', None)


def home_endpoint_for(role):
    return {'admin': 'admin_dashboard', 'technician': 'technician.dashboard'}.get(role, 'user_dashboard')


class ServiceCategory(db.Model):
    __tablename__ = 'service_categories'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True, nullable=False)
    description = db.Column(db.Text)
    icon = db.Column(db.String(50))
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    # catalog visuals (match database/migrate_service_categories.sql)
    slug = db.Column(db.String(50), unique=True, nullable=True)
    color = db.Column(db.String(20), nullable=False, default='#2563eb')
    display_order = db.Column(db.Integer, nullable=False, default=100)
    tagline = db.Column(db.String(200))

    services = db.relationship('Service', backref='category', lazy=True)

class Service(db.Model):
    __tablename__ = 'services'

    id = db.Column(db.Integer, primary_key=True)
    category_id = db.Column(db.Integer, db.ForeignKey('service_categories.id'), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)
    price = db.Column(db.Numeric(10, 2), nullable=False)
    estimated_hours = db.Column(db.Integer, default=1)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    bookings = db.relationship('Booking', backref='service', lazy=True)

class Booking(db.Model):
    __tablename__ = 'bookings'
    # Slot capacity checks count bookings per (date, time); the index also lets
    # MySQL lock just that slot while a new booking is being placed.
    __table_args__ = (db.Index('ix_bookings_slot', 'booking_date', 'booking_time'),)

    id = db.Column(db.Integer, primary_key=True)
    booking_number = db.Column(db.String(50), unique=True, nullable=False)
    customer_id = db.Column(db.Integer, db.ForeignKey('customers.id'), nullable=False, index=True)
    service_id = db.Column(db.Integer, db.ForeignKey('services.id'), nullable=False)
    device_type = db.Column(db.String(50), nullable=False)
    description = db.Column(db.Text, nullable=False)
    address = db.Column(db.String(255))
    booking_date = db.Column(db.Date, nullable=False)
    booking_time = db.Column(db.Time, nullable=False)
    status = db.Column(db.String(20), default='pending')
    is_in_shop = db.Column(db.Boolean, default=False)
    technician_id = db.Column(db.Integer, db.ForeignKey('technicians.id'), nullable=True, index=True)
    assigned_at = db.Column(db.DateTime, nullable=True)
    terms_accepted_at = db.Column(db.DateTime, nullable=True)   # customer ticked the Terms box
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    transaction = db.relationship('Transaction', backref='booking', uselist=False, foreign_keys='Transaction.booking_id')
    customer = db.relationship('Customer', back_populates='bookings')
    technician = db.relationship('Technician', back_populates='jobs')
    # Older code says booking.user / booking.user_id for the customer.
    user_id = db.synonym('customer_id')
    user = db.synonym('customer')

class Transaction(db.Model):
    __tablename__ = 'transactions'

    id = db.Column(db.Integer, primary_key=True)
    transaction_number = db.Column(db.String(50), unique=True, nullable=False)
    booking_id = db.Column(db.Integer, db.ForeignKey('bookings.id'), nullable=True)
    order_id = db.Column(db.Integer, db.ForeignKey('orders.id'), nullable=True)
    customer_id = db.Column(db.Integer, db.ForeignKey('customers.id'), nullable=False, index=True)
    amount = db.Column(db.Numeric(10, 2), nullable=False)
    payment_method = db.Column(db.String(50), nullable=False)
    payment_status = db.Column(db.String(20), default='pending')
    reference_number = db.Column(db.String(50))
    gcash_reference = db.Column(db.String(50))
    receipt_image = db.Column(db.String(255))
    rejection_reason = db.Column(db.Text)
    reviewed_by = db.Column(db.String(120))         # admin who confirmed / rejected it
    reviewed_at = db.Column(db.DateTime)
    transaction_date = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    order = db.relationship('Order', backref='transactions')
    customer = db.relationship('Customer', back_populates='transactions')
    user_id = db.synonym('customer_id')
    user = db.synonym('customer')

class Refund(db.Model):
    """Money owed back to a customer for a payment (a cancelled paid booking or
    order, or one an admin opens by hand). An admin marks it refunded (how and
    with what reference) or declines it (e.g. the money never arrived)."""
    __tablename__ = 'refunds'

    id = db.Column(db.Integer, primary_key=True)
    transaction_id = db.Column(db.Integer, db.ForeignKey('transactions.id'), nullable=False, index=True)
    customer_id = db.Column(db.Integer, db.ForeignKey('customers.id'), nullable=False, index=True)
    booking_id = db.Column(db.Integer, db.ForeignKey('bookings.id'), nullable=True)
    order_id = db.Column(db.Integer, db.ForeignKey('orders.id'), nullable=True)
    amount = db.Column(db.Numeric(10, 2), nullable=False)        # what is owed; set to what was paid back
    reason = db.Column(db.String(255), nullable=False)
    status = db.Column(db.String(20), nullable=False, default='pending', index=True)  # pending|refunded|declined
    method = db.Column(db.String(30))                             # GCash | Cash | Bank transfer
    reference = db.Column(db.String(80))
    note = db.Column(db.Text)
    created_by = db.Column(db.String(120), nullable=False, default='system')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    processed_by = db.Column(db.String(120))
    processed_at = db.Column(db.DateTime)

    transaction = db.relationship('Transaction', backref=db.backref('refunds', order_by='Refund.id'))
    customer = db.relationship('Customer')

class Product(db.Model):
    __tablename__ = 'products'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)
    price = db.Column(db.Numeric(10, 2), nullable=False)
    category = db.Column(db.String(50))
    stock_quantity = db.Column(db.Integer, default=0)
    compatibility = db.Column(db.String(100))
    image_url = db.Column(db.String(255))
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    cart_items = db.relationship('CartItem', backref='product', lazy=True)
    order_items = db.relationship('OrderItem', backref='product', lazy=True)

class Notification(db.Model):
    """For any account: (user_role, user_id) says whose it is."""
    __tablename__ = 'notifications'
    __table_args__ = (db.Index('ix_notifications_owner', 'user_role', 'user_id', 'is_read'),)

    id = db.Column(db.Integer, primary_key=True)
    user_role = db.Column(db.String(20), nullable=False)
    user_id = db.Column(db.Integer, nullable=False)
    title = db.Column(db.String(100), nullable=False)
    message = db.Column(db.Text, nullable=False)
    type = db.Column(db.String(20), default='info')
    is_read = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Message(db.Model):
    """Sender and recipient can be any kind of account, so each side is (role, id)."""
    __tablename__ = 'messages'
    __table_args__ = (db.Index('ix_messages_recipient', 'recipient_role', 'recipient_id', 'is_read'),
                      db.Index('ix_messages_sender', 'sender_role', 'sender_id'))

    id = db.Column(db.Integer, primary_key=True)
    sender_role = db.Column(db.String(20), nullable=False)
    sender_id = db.Column(db.Integer, nullable=False)
    recipient_role = db.Column(db.String(20), nullable=False)
    recipient_id = db.Column(db.Integer, nullable=False)
    subject = db.Column(db.String(200))
    content = db.Column(db.Text, nullable=False)
    is_read = db.Column(db.Boolean, default=False)
    parent_id = db.Column(db.Integer, db.ForeignKey('messages.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    replies = db.relationship('Message', backref=db.backref('parent', remote_side=[id]), lazy=True)

    @property
    def sender(self):
        return get_account(self.sender_role, self.sender_id)

    @property
    def recipient(self):
        return get_account(self.recipient_role, self.recipient_id)

class MessageAttachment(db.Model):
    """Image or PDF attached to a message. Stored privately under
    instance/uploads/messages and served only to the sender and recipient."""
    __tablename__ = 'message_attachments'

    id = db.Column(db.Integer, primary_key=True)
    message_id = db.Column(db.Integer, db.ForeignKey('messages.id'), nullable=False, index=True)
    filename = db.Column(db.String(64), nullable=False)
    original_name = db.Column(db.String(255), nullable=False)
    mime_type = db.Column(db.String(80), nullable=False)
    size_bytes = db.Column(db.Integer)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class SupportTicket(db.Model):
    __tablename__ = 'support_tickets'

    id = db.Column(db.Integer, primary_key=True)
    customer_id = db.Column(db.Integer, db.ForeignKey('customers.id'), nullable=False, index=True)
    subject = db.Column(db.String(200), nullable=False)
    message = db.Column(db.Text, nullable=False)
    category = db.Column(db.String(50), default='general')
    status = db.Column(db.String(20), default='open')
    admin_response = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    customer = db.relationship('Customer', back_populates='support_tickets')
    user_id = db.synonym('customer_id')
    user = db.synonym('customer')

class ContactInquiry(db.Model):
    """Message sent from the public landing-page contact form (no account needed)."""
    __tablename__ = 'contact_inquiries'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), nullable=False)
    subject = db.Column(db.String(200), nullable=False)
    message = db.Column(db.Text, nullable=False)
    status = db.Column(db.String(20), default='new')   # new | handled
    ip_address = db.Column(db.String(45))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class ActivityLog(db.Model):
    """Who did what. (user_role, user_id) is the actor; both empty for anonymous events."""
    __tablename__ = 'activity_logs'

    id = db.Column(db.Integer, primary_key=True)
    user_role = db.Column(db.String(20), nullable=True)
    user_id = db.Column(db.Integer, nullable=True)
    action = db.Column(db.String(100), nullable=False)
    details = db.Column(db.Text)
    ip_address = db.Column(db.String(45))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    @property
    def actor(self):
        return get_account(self.user_role, self.user_id)

class SystemSetting(db.Model):
    __tablename__ = 'system_settings'

    id = db.Column(db.Integer, primary_key=True)
    setting_key = db.Column(db.String(50), unique=True, nullable=False)
    value = db.Column(db.Text)
    description = db.Column(db.String(200))
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class ShoppingCart(db.Model):
    __tablename__ = 'shopping_carts'

    id = db.Column(db.Integer, primary_key=True)
    customer_id = db.Column(db.Integer, db.ForeignKey('customers.id'), nullable=False, index=True)
    status = db.Column(db.String(20), default='active')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    items = db.relationship('CartItem', backref='cart', lazy=True, cascade='all, delete-orphan')
    customer = db.relationship('Customer', back_populates='shopping_carts')
    user_id = db.synonym('customer_id')
    user = db.synonym('customer')

class CartItem(db.Model):
    __tablename__ = 'cart_items'

    id = db.Column(db.Integer, primary_key=True)
    cart_id = db.Column(db.Integer, db.ForeignKey('shopping_carts.id'), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False)
    quantity = db.Column(db.Integer, default=1)
    price = db.Column(db.Numeric(10, 2))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class Order(db.Model):
    __tablename__ = 'orders'

    id = db.Column(db.Integer, primary_key=True)
    customer_id = db.Column(db.Integer, db.ForeignKey('customers.id'), nullable=False, index=True)
    order_number = db.Column(db.String(50), unique=True, nullable=False)
    total_amount = db.Column(db.Numeric(10, 2), nullable=False)
    status = db.Column(db.String(20), default='pending')
    shipping_address = db.Column(db.String(255))
    recipient_name = db.Column(db.String(100))
    recipient_phone = db.Column(db.String(20))
    address_line = db.Column(db.String(255))
    city = db.Column(db.String(50))
    province = db.Column(db.String(50))
    postal_code = db.Column(db.String(10))
    latitude = db.Column(db.Numeric(10, 7))
    longitude = db.Column(db.Numeric(10, 7))
    payment_method = db.Column(db.String(20))
    payment_status = db.Column(db.String(20), default='pending')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    items = db.relationship('OrderItem', backref='order', lazy=True, cascade='all, delete-orphan')
    customer = db.relationship('Customer', back_populates='orders')
    user_id = db.synonym('customer_id')
    user = db.synonym('customer')

class OrderItem(db.Model):
    __tablename__ = 'order_items'

    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey('orders.id'), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False)
    quantity = db.Column(db.Integer, default=1)
    price = db.Column(db.Numeric(10, 2), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class UserPreference(db.Model):
    """Customer preferences (theme, email notifications, ...)."""
    __tablename__ = 'user_preferences'

    id = db.Column(db.Integer, primary_key=True)
    customer_id = db.Column(db.Integer, db.ForeignKey('customers.id'), nullable=False, unique=True)
    language = db.Column(db.String(10), default='en')
    theme = db.Column(db.String(20), default='light')
    email_notifications = db.Column(db.Boolean, default=True)
    sms_notifications = db.Column(db.Boolean, default=False)
    booking_reminders = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    customer = db.relationship('Customer', back_populates='preferences')
    user_id = db.synonym('customer_id')

# ==================== DECORATORS ====================

def _portal_redirect(role):
    """Where to send a signed-in person who opened another role's page."""
    if role in ('admin', 'technician'):
        return redirect(url_for(home_endpoint_for(role)))
    flash('Please log in to access this page.', 'warning')
    return redirect(url_for('login'))

def login_required(f):
    """Customer pages. Staff are sent to their own portal."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session or session.get('role') != 'customer':
            if request.path.startswith('/api/') and session.get('role') != 'customer':
                return jsonify({'success': False, 'ok': False, 'message': 'Please sign in as a customer.'}), 401
            return _portal_redirect(session.get('role'))
        return f(*args, **kwargs)
    return decorated_function

def account_required(f):
    """Pages any signed-in account may open (each checks access itself)."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_account():
            flash('Please log in to access this page.', 'warning')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please log in to access this page.', 'warning')
            return redirect(url_for('admin_login'))
        admin = current_account()
        if session.get('role') != 'admin' or not admin or not admin.is_active:
            flash('Admin access required.', 'danger')
            return redirect(url_for('home'))
        return f(*args, **kwargs)
    return decorated_function

PRESENCE_WRITE_INTERVAL_SECONDS = 30

@app.before_request
def check_session_user():
    """Ends the session of any account that was deleted or deactivated
    since it signed in, and records presence (throttled, not every request)."""
    if request.endpoint == 'static':
        return
    if not session.get('user_id'):
        return
    user = current_account()
    if not user or not user.is_active:
        session.clear()
        g.pop('current_account', None)
        if request.path.startswith(('/api/', '/technician/api/')) or request.is_json:
            msg = 'Your session has ended. Please sign in again.'
            return jsonify({'ok': False, 'success': False, 'reason': msg, 'message': msg}), 401
        flash('Your session has ended. Please sign in again.', 'warning')
        if request.path.startswith('/technician'):
            return redirect(url_for('technician.login'))
        if request.path.startswith('/admin'):
            return redirect(url_for('admin_login'))
        return redirect(url_for('login'))
    now = datetime.utcnow()
    if not user.last_active or (now - user.last_active).total_seconds() >= PRESENCE_WRITE_INTERVAL_SECONDS:
        try:
            user.last_active = now
            db.session.commit()
        except Exception:
            db.session.rollback()

@app.route('/api/ping', methods=['POST'])
@limiter.exempt
def api_ping():
    return jsonify({'ok': True})

@app.route('/api/admin/session-check')
@limiter.exempt
def api_admin_session_check():
    if not session.get('user_id'):
        return jsonify({'ok': False, 'reason': 'logged_out'}), 401
    admin = current_account()
    if session.get('role') != 'admin' or not admin or not admin.is_active:
        return jsonify({'ok': False, 'reason': 'not_admin'}), 401
    return jsonify({'ok': True})
# ==================== HELPER FUNCTIONS ====================

def placeholder_number():
    """Unique stand-in for a NOT NULL UNIQUE number column until the row has an id."""
    return 'TMP-' + secrets.token_hex(8)

# Numbers are built from the row's auto-increment id after flush(), so two
# simultaneous requests can never compute the same one.
def assign_booking_number(booking):
    booking.booking_number = f"BK{datetime.utcnow():%y%m%d}{booking.id:04d}"

EXTRA_TXN_PREFIX = 'EXTRA-'   # EXTRA-<booking number>-<id>: approved extra work on a paid booking

def extra_work_booking(transaction):
    """Booking number an extra-work charge belongs to, or None."""
    number = transaction.transaction_number or ''
    if not number.startswith(EXTRA_TXN_PREFIX):
        return None
    return number[len(EXTRA_TXN_PREFIX):].rsplit('-', 1)[0]

def assign_transaction_number(transaction):
    transaction.transaction_number = f"TRX{datetime.utcnow():%y%m%d}{transaction.id:04d}"

def calculate_trend(model, date_column, extra_filter=None, days=7):
    now = datetime.utcnow()
    current_start = now - timedelta(days=days)
    previous_start = now - timedelta(days=days * 2)
    query = model.query
    if extra_filter is not None:
        query = query.filter(extra_filter)
    total_count = query.count()
    current_count = query.filter(date_column >= current_start).count()
    previous_count = query.filter(date_column >= previous_start, date_column < current_start).count()
    if current_count == previous_count:
        direction = 'flat'
    else:
        direction = 'up' if current_count > previous_count else 'down'
    percent = round((current_count / total_count) * 100) if total_count > 0 else 0
    # 'current' = how many were added in the last `days` days; direction compares
    # that with the `days` before it.
    return {'percent': percent, 'direction': direction, 'current': current_count}

def create_notification(user_id, title, message, type='info', email=True, *, role):
    """In-app notification for the (role, user_id) account, also emailed unless
    they turned email off. `role` is required: ids repeat across the three tables."""
    if role not in ACCOUNT_MODELS:
        raise ValueError(f'unknown role {role!r}')
    notification = Notification(user_role=role, user_id=user_id, title=title, message=message, type=type)
    db.session.add(notification)
    db.session.commit()
    if email:
        email_notification(role, user_id, title, message)
    return notification

def notify_admins(title, message, type='info'):
    for admin in Admin.query.filter_by(is_active=True).all():
        create_notification(admin.id, title, message, type, role='admin')

def _external_url(endpoint, **values):
    """Absolute link for emails. APP_BASE_URL (e.g. https://devtech.ph) wins when set,
    which matters behind a proxy; otherwise the current request's host is used."""
    base = os.environ.get('APP_BASE_URL', '').rstrip('/')
    try:
        if base:
            return base + url_for(endpoint, **values)
        return url_for(endpoint, _external=True, **values)
    except RuntimeError:          # no request context (e.g. a CLI command)
        return base or None

def _site_name():
    row = SystemSetting.query.filter_by(setting_key='system_name').first()
    return (row.value if row and row.value else 'DEVTech Computer Services')

def email_notification(role, user_id, title, message):
    """Email a copy of a notification. Skipped when email is off, the account is
    inactive/placeholder, or a customer disabled email notifications."""
    if not email_service.is_enabled(app):
        return False
    user = get_account(role, user_id)
    if not user or not user.is_active or not email_service.deliverable(user.email):
        return False
    if role == 'customer':
        pref = UserPreference.query.filter_by(customer_id=user_id).first()
        if pref is not None and pref.email_notifications is False:
            return False
    endpoint = {'admin': 'admin_notifications', 'technician': 'technician.notifications'}.get(role, 'notifications')
    site_name = _site_name()
    html_body, text_body = email_service.render(title, message, _external_url(endpoint),
                                                'Open notifications', site_name)
    return email_service.queue_email(user.email, f'{title} - {site_name}', html_body, text_body, app)

def log_activity(user_id, action, details=None, ip_address=None, role=None):
    """Record an action. The actor's role defaults to the signed-in role;
    pass role= when logging for someone else (or None for anonymous)."""
    if user_id is not None and role is None:
        role = session.get('role')
    db.session.add(ActivityLog(user_role=role if user_id is not None else None, user_id=user_id,
                               action=action, details=details,
                               ip_address=ip_address or request.remote_addr))
    db.session.commit()
    
    
# ==================== SCHEMA SELF-HEAL (MySQL) ====================
 
def _try_sql(sql, ok_msg=None):
    try:
        db.session.execute(text(sql))
        db.session.commit()
        if ok_msg:
            print(ok_msg)
        return True
    except Exception as e:
        db.session.rollback()
        return False
 
def create_messages_table():
    with app.app_context():
        try:
            if not db.session.execute(text("SHOW TABLES LIKE 'messages'")).fetchone():
                db.create_all()
            return True
        except Exception as e:
            db.session.rollback()
            print(f"Note: messages table check skipped: {e}")
            return False
 
def create_support_tickets_table():
    with app.app_context():
        try:
            if not db.session.execute(text("SHOW TABLES LIKE 'support_tickets'")).fetchone():
                db.create_all()
            return True
        except Exception as e:
            db.session.rollback()
            print(f"Note: support_tickets check skipped: {e}")
            return False
 
def update_payment_method_column():
    with app.app_context():
        _try_sql("ALTER TABLE transactions MODIFY COLUMN payment_method VARCHAR(50) NOT NULL")
 
def add_receipt_image_column():
    with app.app_context():
        _try_sql("ALTER TABLE transactions ADD COLUMN receipt_image VARCHAR(255) NULL")
 
PROFILE_COLUMNS = [("display_name", "VARCHAR(60) NULL"), ("headline", "VARCHAR(120) NULL"),
                   ("avatar_file", "VARCHAR(64) NULL"), ("avatar_icon", "VARCHAR(30) NULL"),
                   ("avatar_color", "VARCHAR(20) NULL"), ("avatar_frame", "VARCHAR(20) NULL"),
                   ("banner", "VARCHAR(20) NULL")]

def add_profile_columns():
    """Profile look columns (avatar, banner, display name) on all three account tables."""
    with app.app_context():
        for table in ('customers', 'technicians', 'admins'):
            for name, d in PROFILE_COLUMNS:
                _try_sql(f"ALTER TABLE {table} ADD COLUMN {name} {d}")

def add_workflow_columns():
    """Columns and index added by the workflow audit (booking terms, payment
    reviewer, slot index). Safe to run repeatedly."""
    with app.app_context():
        _try_sql("ALTER TABLE bookings ADD COLUMN terms_accepted_at DATETIME NULL")
        _try_sql("ALTER TABLE transactions ADD COLUMN reviewed_by VARCHAR(120) NULL")
        _try_sql("ALTER TABLE transactions ADD COLUMN reviewed_at DATETIME NULL")
        _try_sql("CREATE INDEX ix_bookings_slot ON bookings (booking_date, booking_time)")

def add_service_category_columns():
    """Same columns as database/migrate_service_categories.sql, for DBs created before it."""
    with app.app_context():
        for name, d in [("slug", "VARCHAR(50) NULL UNIQUE"),
                        ("color", "VARCHAR(20) NOT NULL DEFAULT '#2563eb'"),
                        ("display_order", "INT NOT NULL DEFAULT 100"),
                        ("tagline", "VARCHAR(200) NULL")]:
            _try_sql(f"ALTER TABLE service_categories ADD COLUMN {name} {d}")
 
PRESENCE_ONLINE_WINDOW_SECONDS = 60
 
def format_time_ago(dt):
    if not dt:
        return None
    seconds = max(0, int((datetime.utcnow() - dt).total_seconds()))
    if seconds < 5: return 'just now'
    if seconds < 60: return f"{seconds} second{'s' if seconds != 1 else ''} ago"
    minutes = seconds // 60
    if minutes < 60: return f"{minutes} minute{'s' if minutes != 1 else ''} ago"
    hours = minutes // 60
    if hours < 24: return f"{hours} hour{'s' if hours != 1 else ''} ago"
    days = hours // 24
    if days < 7: return f"{days} day{'s' if days != 1 else ''} ago"
    weeks = days // 7
    if weeks < 5: return f"{weeks} week{'s' if weeks != 1 else ''} ago"
    months = days // 30
    if months < 12: return f"{months} month{'s' if months != 1 else ''} ago"
    years = days // 365
    return f"{years} year{'s' if years != 1 else ''} ago"
 
def is_user_online(last_active):
    return bool(last_active) and (datetime.utcnow() - last_active).total_seconds() <= PRESENCE_ONLINE_WINDOW_SECONDS
 
def get_user_presence(user):
    online = is_user_online(user.last_active)
    return {'is_online': online, 'status': 'online' if online else 'offline',
            'last_active': user.last_active.strftime('%Y-%m-%dT%H:%M:%SZ') if user.last_active else None,
            'last_active_display': 'Online now' if online else (
                format_time_ago(user.last_active) if user.last_active else 'Never logged in')}
  
# ==================== AUTH ROUTES ====================
@app.route('/')
def home():
    from models.technician_models import ServiceRating
    services = Service.query.filter_by(is_active=True).limit(6).all()
    categories = ServiceCategory.query.filter_by(is_active=True).all()
    avg, count = db.session.query(func.avg(ServiceRating.stars), func.count(ServiceRating.id)).one()
    # Real figures from the database; the template hides any that are still zero.
    stats = {
        'repairs_done': Booking.query.filter(Booking.status.in_(FINISHED_STATUSES)).count(),
        'avg_rating': round(float(avg), 1) if avg else None,
        'rating_count': count,
        'technicians': Technician.query.filter_by(is_active=True, id_verified=True).count(),
    }
    return render_template('home.html', services=services, categories=categories, stats=stats)

@app.route('/contact', methods=['POST'])
@limiter.limit('5 per hour')
def contact():
    """Public contact form on the home page. Stored for the admin Support page."""
    data = request.get_json(silent=True) or {}
    name = (data.get('name') or '').strip()
    email = (data.get('email') or '').strip().lower()
    subject = (data.get('subject') or '').strip()
    message = (data.get('message') or '').strip()
    if not (name and email and subject and message):
        return jsonify({'success': False, 'message': 'Please fill in all fields.'}), 400
    if not re.fullmatch(r'[^@\s]+@[^@\s]+\.[^@\s]+', email) or len(email) > 120:
        return jsonify({'success': False, 'message': 'Please enter a valid email address.'}), 400
    if len(name) > 100 or len(subject) > 200 or len(message) > 5000:
        return jsonify({'success': False, 'message': 'Your message is too long.'}), 400
    inquiry = ContactInquiry(name=name, email=email, subject=subject, message=message,
                             ip_address=request.remote_addr)
    db.session.add(inquiry)
    db.session.commit()
    notify_admins('New Website Inquiry', f'{name}: {subject}')
    return jsonify({'success': True, 'message': "Thank you for your message! We'll get back to you soon."})

@app.route('/login', methods=['GET', 'POST'])
@limiter.limit('10 per minute')
def login():
    """Customer sign-in. Technicians and admins who use their email here are
    signed in to their own portal (emails are unique across all accounts)."""
    if request.method == 'POST':
        email = (request.form.get('email') or '').strip().lower()
        password = request.form.get('password') or ''
        user = find_account_by_email(email)
        if user and user.check_password(password):
            if not user.is_active:
                flash('Your account has been deactivated. Please contact support.', 'danger')
                return render_template('auth/login.html')
            # "Remember me" keeps the session for PERMANENT_SESSION_LIFETIME (7 days);
            # otherwise it ends when the browser closes.
            login_account(user, remember=request.form.get('remember'))
            log_activity(user.id, 'login', f'Logged in from {request.remote_addr}')
            return redirect(url_for(home_endpoint_for(user.role)))
        flash('Invalid email or password.', 'danger')
    return render_template('auth/login.html')

# ==================== PASSWORD RESET BY EMAIL ====================
# The token carries the account (role + id) plus a fingerprint of the current
# password hash, so it stops working once the password changes (single use)
# and after 1 hour.
RESET_TOKEN_MAX_AGE = 3600

def _reset_serializer():
    return URLSafeTimedSerializer(app.config['SECRET_KEY'], salt='password-reset')

def make_reset_token(user):
    return _reset_serializer().dumps({'role': user.role, 'uid': user.id, 'pw': user.password_hash[-16:]})

def user_from_reset_token(token):
    try:
        data = _reset_serializer().loads(token, max_age=RESET_TOKEN_MAX_AGE)
    except (BadSignature, SignatureExpired):
        return None
    if not isinstance(data, dict):
        return None
    user = get_account(data.get('role'), data.get('uid'))
    if not user or not user.is_active:
        return None
    if not hmac.compare_digest(user.password_hash[-16:], str(data.get('pw', ''))):
        return None
    return user

@app.route('/forgot-password', methods=['GET', 'POST'])
@limiter.limit('5 per hour', methods=['POST'])
def forgot_password():
    enabled = email_service.is_enabled(app)
    if request.method == 'POST' and enabled:
        email = (request.form.get('email') or '').strip().lower()
        user = find_account_by_email(email)
        # Same response whether or not the account exists (no account probing).
        if user and user.is_active and email_service.deliverable(user.email):
            link = _external_url('reset_password', token=make_reset_token(user))
            site_name = _site_name()
            html_body, text_body = email_service.render(
                'Reset your password',
                f'Hi {user.full_name},\n\nWe received a request to reset the password for your '
                f'{site_name} account. The link below works once and expires in 1 hour.\n\n'
                'If you did not ask for this, you can ignore this email; your password stays the same.',
                link, 'Choose a new password', site_name)
            email_service.queue_email(user.email, f'Reset your {site_name} password', html_body, text_body, app)
            log_activity(user.id, 'password_reset_requested', 'Password reset link emailed', role=user.role)
        return render_template('auth/forgot_password.html', sent=True, email_enabled=enabled)
    return render_template('auth/forgot_password.html', sent=False, email_enabled=enabled)

@app.route('/reset-password/<token>', methods=['GET', 'POST'])
@limiter.limit('10 per hour', methods=['POST'])
def reset_password(token):
    user = user_from_reset_token(token)
    if not user:
        return render_template('auth/reset_password.html', valid=False), 400
    if request.method == 'POST':
        password = request.form.get('password') or ''
        confirm = request.form.get('confirm') or ''
        error = None
        if len(password) < 8 or not re.search(r'[A-Za-z]', password) or not re.search(r'\d', password):
            error = 'Use at least 8 characters, including a letter and a number.'
        elif password != confirm:
            error = 'The two passwords do not match.'
        if error:
            flash(error, 'danger')
            return render_template('auth/reset_password.html', valid=True, email=user.email), 400
        user.set_password(password)          # also invalidates this link
        db.session.commit()
        log_activity(user.id, 'password_reset', 'Password changed with an email reset link', role=user.role)
        create_notification(user.id, 'Your password was changed',
                            'Your password was just reset using a link sent to this email. '
                            'If this was not you, contact us right away.', 'warning', role=user.role)
        session.clear()
        flash('Password updated. Sign in with your new password.', 'success')
        if user.role == 'technician':
            return redirect(url_for('technician.login'))
        if user.role == 'admin':
            return redirect(url_for('admin_login'))
        return redirect(url_for('login'))
    return render_template('auth/reset_password.html', valid=True, email=user.email)

def _unique_customer_username(email):
    base = email.split('@')[0][:60] or 'customer'
    username = base
    while Customer.query.filter_by(username=username).first():
        username = f"{base}{secrets.token_hex(3)}"
    return username

@app.route('/register', methods=['GET', 'POST'])
@limiter.limit('5 per minute')
def register():
    if request.method == 'POST':
        full_name = (request.form.get('fullName') or '').strip()
        email = (request.form.get('email') or '').strip().lower()
        password = request.form.get('password')
        re_password = request.form.get('rePassword')
        phone = request.form.get('phone')

        if not full_name or not email or not password:
            flash('All fields are required.', 'danger')
            return render_template('auth/register.html')
        if password != re_password:
            flash('Passwords do not match.', 'danger')
            return render_template('auth/register.html')
        if len(password) < 6:
            flash('Password must be at least 6 characters long.', 'danger')
            return render_template('auth/register.html')
        if email_in_use(email):
            flash('Email already registered.', 'danger')
            return render_template('auth/register.html')

        user = Customer(username=_unique_customer_username(email), email=email,
                        full_name=full_name, phone=phone)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        create_notification(user.id, 'Welcome to DEVTech!',
                            'Thank you for registering. Start booking your repair services today!',
                            'success', role='customer')
        flash('Registration successful! Please log in.', 'success')
        return redirect(url_for('login'))
    return render_template('auth/register.html')

@app.route('/logout')
def logout():
    if 'user_id' in session and session.get('role') in ACCOUNT_MODELS:
        log_activity(session['user_id'], 'logout', 'Logged out')
    session.clear()
    flash('You have been logged out.', 'info')
    return redirect(url_for('home'))

# ---- Social login (customers only) ----
def _login_or_create_oauth_user(provider, provider_id, email, full_name, email_verified):
    if not email:
        flash('We could not get an email address from your account. Please try a different sign-in method.', 'danger')
        return redirect(url_for('login'))
    # Linking by email is only safe when the provider vouches for the address;
    # otherwise anyone could claim an existing account's email.
    if not email_verified:
        flash(f'Your {provider.title()} email address is not verified. Please verify it or sign in with your password.', 'danger')
        return redirect(url_for('login'))
    email = email.strip().lower()
    user = Customer.query.filter_by(oauth_provider=provider, oauth_id=provider_id).first()
    is_new_user = False
    if not user:
        existing = find_account_by_email(email)
        if existing and existing.role != 'customer':
            flash('Staff accounts must sign in with their password.', 'danger')
            return redirect(url_for('login'))
        user = existing
        if user:
            user.oauth_provider = user.oauth_provider or provider
            user.oauth_id = user.oauth_id or provider_id
        else:
            user = Customer(username=_unique_customer_username(email), email=email,
                            full_name=full_name or email.split('@')[0],
                            oauth_provider=provider, oauth_id=provider_id)
            user.password_hash = bcrypt.generate_password_hash(secrets.token_urlsafe(32)).decode('utf-8')
            db.session.add(user)
            is_new_user = True
        db.session.commit()
        if is_new_user:
            create_notification(user.id, 'Welcome to DEVTech!',
                                'Thank you for registering. Start booking your repair services today!',
                                'success', role='customer')
    if not user.is_active:
        flash('Your account has been deactivated. Please contact support.', 'danger')
        return redirect(url_for('login'))
    login_account(user)
    log_activity(user.id, 'login', f'Logged in via {provider} from {request.remote_addr}')
    flash(f'Logged in with {provider.title()}.', 'success')
    return redirect(url_for('user_dashboard'))

@app.route('/login/google')
def google_login():
    return oauth.google.authorize_redirect(url_for('google_callback', _external=True))

@app.route('/login/google/callback')
def google_callback():
    try:
        token = oauth.google.authorize_access_token()
    except Exception:
        flash('Google sign-in was cancelled or failed. Please try again.', 'danger')
        return redirect(url_for('login'))
    userinfo = token.get('userinfo') or oauth.google.parse_id_token(token, nonce=None)
    return _login_or_create_oauth_user('google', userinfo['sub'], userinfo.get('email'), userinfo.get('name'),
                                       userinfo.get('email_verified') is True)

@app.route('/login/facebook')
def facebook_login():
    return oauth.facebook.authorize_redirect(url_for('facebook_callback', _external=True))

@app.route('/login/facebook/callback')
def facebook_callback():
    try:
        token = oauth.facebook.authorize_access_token()
        profile = oauth.facebook.get('me?fields=id,name,email', token=token).json()
    except Exception:
        flash('Facebook sign-in was cancelled or failed. Please try again.', 'danger')
        return redirect(url_for('login'))
    # Facebook's Graph API only returns an email the user has confirmed.
    return _login_or_create_oauth_user('facebook', profile['id'], profile.get('email'), profile.get('name'), True)

@app.route('/admin/login', methods=['GET', 'POST'])
@limiter.limit('5 per minute')
def admin_login():
    if request.method == 'POST':
        email = (request.form.get('email') or '').strip().lower()
        password = request.form.get('password') or ''
        user = Admin.query.filter(func.lower(Admin.email) == email).first()
        if user and user.check_password(password) and user.is_active:
            login_account(user)
            log_activity(user.id, 'admin_login', f'Admin logged in from {request.remote_addr}')
            flash('Welcome to Admin Dashboard!', 'success')
            return redirect(url_for('admin_dashboard'))
        flash('Invalid admin credentials or unauthorized access.', 'danger')
    return render_template('auth/admin_login.html')

def _unique_admin_username(email):
    base = email.split('@')[0][:60] or 'admin'
    username = base
    while Admin.query.filter_by(username=username).first():
        username = f'{base}_{secrets.token_hex(3)}'
    return username

# ---- First-admin setup page (only exists while there is no admin) ----
@app.route('/setup/first-admin', methods=['GET', 'POST'])
@limiter.limit('10 per hour')
def setup_first_admin():
    if Admin.query.first():
        abort(404)
    # Disabled unless SETUP_TOKEN is set; a blank token must never mean "open to anyone".
    expected = os.environ.get('SETUP_TOKEN', '')
    if not expected or not hmac.compare_digest(request.values.get('token', ''), expected):
        abort(404)
    errors, email, name = [], '', ''
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        name = request.form.get('name', '').strip()
        pw, confirm = request.form.get('password', ''), request.form.get('confirm', '')
        if '@' not in email: errors.append('Enter a valid email.')
        if not name: errors.append('Enter your full name.')
        if len(pw) < 8: errors.append('Password must be at least 8 characters.')
        if pw != confirm: errors.append('Passwords do not match.')
        if email and email_in_use(email): errors.append('That email is already registered.')
        if not errors:
            u = Admin(username=_unique_admin_username(email), email=email, full_name=name, is_active=True)
            u.set_password(pw)
            db.session.add(u)
            db.session.commit()
            flash('Admin created. Sign in below.', 'success')
            return redirect(url_for('admin_login'))
    return render_template('setup_first_admin.html', errors=errors, email=email, name=name)


# ==================== USER DASHBOARD ROUTES ====================
def _notifications_for(role, user_id):
    return Notification.query.filter_by(user_role=role, user_id=user_id)

def _unread_messages_for(role, user_id):
    return Message.query.filter_by(recipient_role=role, recipient_id=user_id, is_read=False).count()

# ==================== LIVE UPDATES (polled by static/js/live.js) ====================
# Every few seconds each open page asks /api/live for a small summary: unread
# counts, the newest notification/message ids, and a fingerprint ("stamp") of the
# data that account's pages show. The page updates badges and pop-ups from the
# counts and refreshes itself when the stamp changes - no manual reload needed.

def _count_where(cond):
    return func.sum(sa_case((cond, 1), else_=0))

def _live_stamp(account):
    """Fingerprint of what this account's pages display (messages and notifications
    are tracked separately by id). Changes whenever any of it changes."""
    from models.technician_models import (ApprovalRequest, JobLog, ServiceReport, IncidentReport,
                                          ServiceRating, IntakeRecord)
    q = db.session.query
    role, aid = account.role, account.id
    parts = []

    def add(*columns, where=()):
        parts.append(tuple(q(*columns).filter(*where).one()))

    if role == 'customer':
        mine = q(Booking.id).filter(Booking.customer_id == aid)
        add(func.count(Booking.id), func.max(Booking.updated_at), where=[Booking.customer_id == aid])
        add(func.count(Order.id), func.max(Order.updated_at), where=[Order.customer_id == aid])
        add(func.count(Transaction.id), func.max(Transaction.updated_at), where=[Transaction.customer_id == aid])
        add(func.count(SupportTicket.id), func.max(SupportTicket.updated_at), where=[SupportTicket.customer_id == aid])
        add(func.count(ApprovalRequest.id), func.max(ApprovalRequest.responded_at),
            _count_where(ApprovalRequest.status == 'pending'), where=[ApprovalRequest.booking_id.in_(mine)])
        add(func.max(JobLog.id), where=[JobLog.booking_id.in_(mine)])
        add(func.count(ServiceReport.id), func.max(ServiceReport.updated_at), where=[ServiceReport.booking_id.in_(mine)])
        add(func.count(Refund.id), func.max(Refund.processed_at), where=[Refund.customer_id == aid])
    elif role == 'technician':
        jobs = q(Booking.id).filter(Booking.technician_id == aid)
        add(func.count(Booking.id), func.max(Booking.updated_at), func.max(Booking.assigned_at),
            where=[Booking.technician_id == aid])
        add(func.max(JobLog.id), where=[JobLog.booking_id.in_(jobs)])
        add(func.count(ApprovalRequest.id), func.max(ApprovalRequest.responded_at),
            _count_where(ApprovalRequest.status == 'pending'), where=[ApprovalRequest.technician_id == aid])
        add(func.count(ServiceReport.id), func.max(ServiceReport.updated_at), func.max(ServiceReport.reviewed_at),
            where=[ServiceReport.technician_id == aid])
        add(func.count(IncidentReport.id), func.max(IncidentReport.reviewed_at), where=[IncidentReport.technician_id == aid])
        add(func.count(IntakeRecord.id), func.max(IntakeRecord.id), where=[IntakeRecord.booking_id.in_(jobs)])
        add(func.count(ServiceRating.id), where=[ServiceRating.technician_id == aid])
        add(func.count(Technician.id), _count_where(Technician.id_verified.is_(True)), where=[Technician.id == aid])
    else:   # admin sees everything
        add(func.count(Booking.id), func.max(Booking.updated_at), func.max(Booking.assigned_at))
        add(func.count(Order.id), func.max(Order.updated_at))
        add(func.count(Transaction.id), func.max(Transaction.updated_at))
        add(func.count(SupportTicket.id), func.max(SupportTicket.updated_at))
        add(func.count(ContactInquiry.id), _count_where(ContactInquiry.status == 'new'))
        add(func.count(ApprovalRequest.id), func.max(ApprovalRequest.responded_at))
        add(func.max(JobLog.id))
        add(func.count(ServiceReport.id), func.max(ServiceReport.updated_at), func.max(ServiceReport.reviewed_at))
        add(func.count(IncidentReport.id), func.max(IncidentReport.reviewed_at), _count_where(IncidentReport.status == 'open'))
        add(func.count(ServiceRating.id))
        add(func.count(Refund.id), func.max(Refund.processed_at), _count_where(Refund.status == 'pending'))
        # accounts: not updated_at, which every presence ping touches
        for model in (Customer, Technician, Admin):
            add(func.count(model.id), func.max(model.id), _count_where(model.is_active.is_(True)))
        add(_count_where(Technician.id_verified.is_(True)))
    # shared catalogue and settings (shop, services, prices)
    add(func.count(Product.id), func.max(Product.updated_at))
    add(func.count(Service.id), func.max(Service.id), func.sum(Service.price), _count_where(Service.is_active.is_(True)))
    add(func.count(ServiceCategory.id), _count_where(ServiceCategory.is_active.is_(True)))
    add(func.max(SystemSetting.updated_at))
    return hashlib.sha1(repr(parts).encode()).hexdigest()[:16]

def live_state(account):
    role, aid = account.role, account.id
    mine = or_(and_(Message.recipient_role == role, Message.recipient_id == aid),
               and_(Message.sender_role == role, Message.sender_id == aid))
    return {
        'n': db.session.query(func.max(Notification.id))
               .filter(Notification.user_role == role, Notification.user_id == aid).scalar() or 0,
        'nu': _notifications_for(role, aid).filter_by(is_read=False).count(),
        'm': db.session.query(func.max(Message.id)).filter(mine).scalar() or 0,
        'mu': _unread_messages_for(role, aid),
        's': _live_stamp(account),
    }

# ---- Waiting ("long polling") so updates arrive at once -------------------
# With ?wait=1 the request is held open until this account's live state differs
# from what the page already has (or LIVE_WAIT_SECONDS pass). Any database commit
# in this process wakes waiters immediately; changes made by other worker
# processes are caught by re-checking every LIVE_RECHECK_SECONDS. At most
# LIVE_MAX_WAITERS requests wait per process - beyond that the request answers
# straight away and the page simply polls again a few seconds later.
app.config.setdefault('LIVE_WAIT_SECONDS', float(os.environ.get('LIVE_WAIT_SECONDS', 25)))
app.config.setdefault('LIVE_RECHECK_SECONDS', float(os.environ.get('LIVE_RECHECK_SECONDS', 1.5)))
app.config.setdefault('LIVE_MAX_WAITERS', int(os.environ.get('LIVE_MAX_WAITERS', 32)))
_live_changed = threading.Condition()
_live_generation = [0]
_live_waiters = [0]

def _live_bump(_session):
    with _live_changed:
        _live_generation[0] += 1
        _live_changed.notify_all()

sa_event.listen(SASession, 'after_commit', _live_bump)

def _live_client_state():
    """What the page says it already shows (None for a plain, non-waiting poll)."""
    if request.args.get('wait') != '1':
        return None
    return {'n': request.args.get('n', type=int), 'm': request.args.get('m', type=int),
            'nu': request.args.get('nu', type=int), 'mu': request.args.get('mu', type=int),
            's': request.args.get('s', '')}

def _live_differs(state, client):
    return any(state[k] != client[k] for k in ('n', 'm', 'nu', 'mu', 's'))

def _live_wait(account, state, client):
    """Block until state differs from client's view or the wait ends. Returns
    (state, waited) - waited is False when no waiting slot was free."""
    with _live_changed:
        if _live_waiters[0] >= app.config['LIVE_MAX_WAITERS']:
            return state, False
        _live_waiters[0] += 1
    try:
        deadline = time.monotonic() + app.config['LIVE_WAIT_SECONDS']
        role, account_id = account.role, account.id
        while not _live_differs(state, client):
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            # Never sleep inside a transaction: ending it returns the pooled DB
            # connection (waiting pages must not starve normal requests), releases
            # SQLite read locks that would block writers, and starts a fresh
            # snapshot for the next check so new rows are visible.
            with _live_changed:
                seen = _live_generation[0]
            db.session.rollback()
            with _live_changed:
                _live_changed.wait_for(lambda: _live_generation[0] != seen,
                                       timeout=min(app.config['LIVE_RECHECK_SECONDS'], remaining))
            fresh = get_account(role, account_id)
            if not fresh or not fresh.is_active:
                return None, True
            state = live_state(fresh)
        return state, True
    finally:
        with _live_changed:
            _live_waiters[0] -= 1

@app.route('/api/live')
@limiter.exempt
def api_live():
    account = current_account()
    if not account or not account.is_active:
        return jsonify({'ok': False}), 401
    state = live_state(account)
    client = _live_client_state()
    waited = False
    if client is not None and not _live_differs(state, client):
        state, waited = _live_wait(account, state, client)
        if state is None:                          # account removed or deactivated meanwhile
            session.clear()
            return jsonify({'ok': False}), 401
    since_n = request.args.get('n', type=int)
    since_m = request.args.get('m', type=int)
    if since_n is not None and state['n'] > since_n:
        rows = _notifications_for(account.role, account.id).filter(Notification.id > since_n)\
            .order_by(Notification.id.desc()).limit(5).all()
        state['new_notifications'] = [{'id': n.id, 'title': n.title, 'message': n.message, 'type': n.type}
                                      for n in rows]
    if since_m is not None and state['m'] > since_m:
        rows = Message.query.filter(Message.recipient_role == account.role, Message.recipient_id == account.id,
                                    Message.id > since_m).order_by(Message.id.desc()).limit(5).all()
        new_messages = []
        for m in rows:
            sender = m.sender
            new_messages.append({
                'id': m.id,
                'from': ('DEVTech Support' if m.sender_role == 'admin' and account.role != 'admin'
                         else (sender.shown_name if sender else 'Someone')),
                'preview': message_preview(m)[:140],
                'key': f'{m.sender_role}-{m.sender_id}',
            })
        state['new_messages'] = new_messages
    state['ok'] = True
    state['waited'] = waited
    resp = jsonify(state)
    resp.headers['Cache-Control'] = 'no-store'
    return resp

@app.context_processor
def _inject_live_boot():
    """live_boot() -> the starting live state for this page (or None when signed out)."""
    def live_boot():
        try:
            account = current_account()
            return live_state(account) if account and account.is_active else None
        except Exception:
            db.session.rollback()
            app.logger.exception('live_boot failed')
            return None
    return {'live_boot': live_boot}

@app.route('/user/dashboard')
@login_required
def user_dashboard():
    user_id = session.get('user_id')
    user = current_account()
    # Full list (was limited to 5, which capped every stat card at 5). Template slices [:3].
    bookings = Booking.query.filter_by(customer_id=user_id).order_by(Booking.created_at.desc()).all()
    transactions = Transaction.query.filter_by(customer_id=user_id).order_by(Transaction.transaction_date.desc()).limit(5).all()
    notifications = _notifications_for('customer', user_id).filter_by(is_read=False)\
        .order_by(Notification.created_at.desc()).limit(5).all()
    unread_messages = _unread_messages_for('customer', user_id)
    return render_template('user/user_dashboard.html', user=user, bookings=bookings,
                           transactions=transactions, notifications=notifications,
                           unread_messages=unread_messages)

# ==================== BOOKING STATUS ROUTES ====================
def _unread_notifs(user_id):
    return _notifications_for('customer', user_id).filter_by(is_read=False)\
        .order_by(Notification.created_at.desc()).limit(5).all()

@app.route('/total-bookings')
@login_required
def total_bookings():
    uid = session.get('user_id')
    bookings = Booking.query.filter_by(customer_id=uid).order_by(Booking.created_at.desc()).all()
    return render_template('user/total_bookings.html', bookings=bookings, notifications=_unread_notifs(uid))

@app.route('/completed-bookings')
@login_required
def completed_bookings():
    uid = session.get('user_id')
    bookings = Booking.query.filter_by(customer_id=uid, status='completed').order_by(Booking.created_at.desc()).all()
    return render_template('user/completed_bookings.html', bookings=bookings, notifications=_unread_notifs(uid))

@app.route('/inprogress-bookings')
@login_required
def inprogress_bookings():
    uid = session.get('user_id')
    bookings = Booking.query.filter(Booking.customer_id == uid,
                                    Booking.status.in_(['pending', 'confirmed', 'diagnosis_pending', 'in_progress', 'on_hold'])
                                    ).order_by(Booking.created_at.desc()).all()
    return render_template('user/inprogress_bookings.html', bookings=bookings, notifications=_unread_notifs(uid))

@app.route('/pending-bookings')
@login_required
def pending_bookings():
    uid = session.get('user_id')
    bookings = Booking.query.filter_by(customer_id=uid, status='pending').order_by(Booking.created_at.desc()).all()
    return render_template('user/pending_bookings.html', bookings=bookings, notifications=_unread_notifs(uid))

@app.route('/rejected-requests')
@login_required
def rejected_requests():
    uid = session.get('user_id')
    bookings = Booking.query.filter_by(customer_id=uid, status='cancelled').order_by(Booking.created_at.desc()).all()
    return render_template('user/rejected_requests.html', bookings=bookings, notifications=_unread_notifs(uid))

def _booking_transactions(booking):
    """The booking's own transaction plus any extra-work charges billed separately
    (those carry the booking number in their transaction number)."""
    return Transaction.query.filter(or_(
        Transaction.booking_id == booking.id,
        Transaction.transaction_number.like(f'{EXTRA_TXN_PREFIX}{booking.booking_number}-%'))).all()

def settle_cancelled_booking(booking):
    """Bring a cancelled booking's payments and approval requests in line with it.
    Unpaid charges are cancelled (so they can no longer be paid or confirmed) and
    pending extra-work requests are withdrawn. Returns the transactions that were
    already confirmed or had payment proof attached - those need a refund check.
    Does not commit."""
    from models.technician_models import ApprovalRequest
    now = datetime.utcnow()
    for a in ApprovalRequest.query.filter_by(booking_id=booking.id, status='pending').all():
        a.status = 'withdrawn'
        a.responded_at = now.strftime('%Y-%m-%d %H:%M:%S')
    needs_refund_check = []
    for txn in _booking_transactions(booking):
        if txn.payment_status == 'confirmed':
            needs_refund_check.append(txn)
        elif txn.payment_status in ('pending', 'rejected'):
            if txn.receipt_image or txn.gcash_reference or txn.reference_number:
                needs_refund_check.append(txn)      # customer may already have paid
            txn.payment_status = 'cancelled'
            txn.updated_at = now
    return needs_refund_check

REFUND_METHODS = ('GCash', 'Cash', 'Bank transfer')

def open_refund(txn, reason, created_by='system', booking=None, order=None):
    """Open a refund for a payment unless one is already pending or done.
    Returns (refund, created). Does not commit."""
    existing = Refund.query.filter(Refund.transaction_id == txn.id,
                                   Refund.status.in_(('pending', 'refunded'))).first()
    if existing:
        return existing, False
    booking = booking or txn.booking
    order = order or txn.order
    refund = Refund(transaction_id=txn.id, customer_id=txn.customer_id,
                    booking_id=booking.id if booking else None, order_id=order.id if order else None,
                    amount=txn.amount, reason=reason[:255], created_by=created_by[:120])
    db.session.add(refund)
    return refund, True

def notify_refund_check(booking, transactions):
    """Open refunds for a cancelled booking's paid (or possibly paid) charges and
    tell admins and the customer. Commits."""
    if not transactions:
        return
    opened = []
    for t in transactions:
        why = (f'Booking {booking.booking_number} cancelled after the payment was confirmed.'
               if t.payment_status == 'confirmed' else
               f'Booking {booking.booking_number} cancelled after the customer sent payment proof. '
               f'Check the money arrived before refunding.')
        refund, created = open_refund(t, why, booking=booking)
        if created:
            opened.append(t)
    db.session.commit()
    if not opened:
        return
    numbers = ', '.join(t.transaction_number for t in opened)
    notify_admins('Refund to process',
                  f'{booking.booking_number} was cancelled with a paid or possibly paid charge ({numbers}). '
                  f'See Refunds.', 'warning')
    create_notification(booking.customer_id, 'Refund requested',
                        f'Booking {booking.booking_number} was cancelled after a payment. A refund has been '
                        f'opened; you can follow it on your Transactions page.', 'info', role='customer')

@app.route('/booking/<int:booking_id>/cancel', methods=['POST'])
@login_required
def cancel_booking(booking_id):
    user_id = session.get('user_id')
    booking = Booking.query.get_or_404(booking_id)
    if booking.customer_id != user_id:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403
    if booking.status not in ['pending', 'confirmed']:
        return jsonify({'success': False, 'message': 'This booking cannot be cancelled'}), 400
    booking.status = 'cancelled'
    booking.updated_at = datetime.utcnow()
    refund_check = settle_cancelled_booking(booking)
    db.session.commit()
    notify_admins('Booking Cancelled', f'{booking.booking_number} was cancelled by the customer.', 'warning')
    notify_refund_check(booking, refund_check)
    if booking.technician_id:
        create_notification(booking.technician_id, 'Job Cancelled',
                            f'{booking.booking_number} was cancelled by the customer.', 'warning',
                            role='technician')
    create_notification(user_id, 'Booking Cancelled', f'Your booking {booking.booking_number} has been cancelled.',
                        'warning', role='customer')
    return jsonify({'success': True, 'message': 'Booking cancelled successfully'})

# ==================== NOTIFICATION ROUTES ====================
@app.route('/notifications')
@login_required
def notifications():
    user_id = session.get('user_id')
    notifs = _notifications_for('customer', user_id).order_by(Notification.created_at.desc()).all()
    view = list(notifs)                     # render read-state as it was on arrival
    rendered = render_template('user/notification.html', notifications=view)
    for n in notifs:
        if not n.is_read:
            n.is_read = True
    db.session.commit()
    return rendered

@app.route('/api/notifications/unread-count')
@limiter.exempt
@login_required
def api_notification_unread_count():
    count = _notifications_for('customer', session.get('user_id')).filter_by(is_read=False).count()
    return jsonify({'count': count})

def _own_customer_notification(notification_id):
    n = Notification.query.get_or_404(notification_id)
    if n.user_role != 'customer' or n.user_id != session.get('user_id'):
        return None
    return n

@app.route('/notification/<int:notification_id>/read', methods=['POST'])
@login_required
def notification_read(notification_id):
    n = _own_customer_notification(notification_id)
    if not n:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403
    n.is_read = True
    db.session.commit()
    return jsonify({'success': True, 'message': 'Notification marked as read'})

@app.route('/notification/mark-all-read', methods=['POST'])
@login_required
def notification_mark_all_read():
    _notifications_for('customer', session.get('user_id')).filter_by(is_read=False).update({'is_read': True})
    db.session.commit()
    return jsonify({'success': True, 'message': 'All notifications marked as read'})

@app.route('/notification/<int:notification_id>/delete', methods=['DELETE'])
@login_required
def notification_delete(notification_id):
    n = _own_customer_notification(notification_id)
    if not n:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403
    db.session.delete(n)
    db.session.commit()
    return jsonify({'success': True, 'message': 'Notification deleted'})


# ==================== MESSAGE ROUTES ====================
# Both sides of a message can be any kind of account, so every conversation is
# identified by the other person's account key ('technician-3', 'admin-1', ...).
MAX_MESSAGE_LENGTH = 5000
MESSAGE_ATTACHMENT_MAX_BYTES = 5 * 1024 * 1024

def check_message_attachment(file_storage):
    """(checked, error) for an optional attachment; (None, None) if none was sent."""
    if not file_storage or not file_storage.filename:
        return None, None
    from services.upload_service import check_file
    ok, result = check_file(file_storage, MESSAGE_ATTACHMENT_MAX_BYTES)
    return (result, None) if ok else (None, result)

def store_message_attachment(message_id, checked):
    """Write a file already validated by check_message_attachment. Does not commit."""
    data, mime, ext, safe_name = checked
    stored = secrets.token_hex(12) + ext
    folder = app.config['MESSAGE_UPLOAD_FOLDER']
    os.makedirs(folder, exist_ok=True)
    with open(os.path.join(folder, stored), 'wb') as fh:
        fh.write(data)
    attachment = MessageAttachment(message_id=message_id, filename=stored, original_name=safe_name[:255],
                                   mime_type=mime, size_bytes=len(data))
    db.session.add(attachment)
    return attachment

def attachment_info(a):
    return {'url': url_for('message_attachment', attachment_id=a.id), 'name': a.original_name,
            'is_image': a.mime_type.startswith('image/')}

def attachments_by_message(message_ids):
    """{message_id: [attachment_info, ...]} for the given messages."""
    out = {}
    message_ids = list(message_ids)
    if message_ids:
        for a in MessageAttachment.query.filter(MessageAttachment.message_id.in_(message_ids)).all():
            out.setdefault(a.message_id, []).append(attachment_info(a))
    return out

def message_preview(message):
    """Short text for conversation lists; attachment-only messages show a clip."""
    if message is None:
        return 'No messages'
    if message.content:
        return message.content
    return '📎 Attachment'

app.jinja_env.globals['message_preview'] = message_preview

def _is_party(message, account):
    return ((message.sender_role, message.sender_id) == (account.role, account.id) or
            (message.recipient_role, message.recipient_id) == (account.role, account.id))

@app.route('/messages/attachments/<int:attachment_id>')
@account_required
def message_attachment(attachment_id):
    """Only the two people in the conversation can open an attachment."""
    a = MessageAttachment.query.get_or_404(attachment_id)
    m = db.session.get(Message, a.message_id)
    if not m or not _is_party(m, current_account()):
        abort(404)
    path = os.path.join(app.config['MESSAGE_UPLOAD_FOLDER'], a.filename)
    if not os.path.isfile(path):
        abort(404)
    # Images display inline; anything else (PDF) downloads.
    return send_file(path, mimetype=a.mime_type, download_name=a.original_name,
                     as_attachment=not a.mime_type.startswith('image/'))

def _thread_filter(a, b):
    """Messages between accounts a and b, in either direction."""
    return or_(and_(Message.sender_role == a.role, Message.sender_id == a.id,
                    Message.recipient_role == b.role, Message.recipient_id == b.id),
               and_(Message.sender_role == b.role, Message.sender_id == b.id,
                    Message.recipient_role == a.role, Message.recipient_id == a.id))

def _can_message(me, other):
    """Admins can message anyone; customers and technicians can message each
    other only if the technician has (or had) one of the customer's jobs."""
    if not me or not other or me.key == other.key:
        return False
    if me.role == 'admin' or other.role == 'admin':
        return True
    roles = {me.role, other.role}
    if roles == {'customer', 'technician'}:
        customer = me if me.role == 'customer' else other
        tech = other if customer is me else me
        return Booking.query.filter_by(customer_id=customer.id, technician_id=tech.id).first() is not None
    return False

def send_message(sender, recipient, content, subject=None, checked=None):
    """Store a message (+ optional attachment) and notify the recipient. Commits."""
    message = Message(sender_role=sender.role, sender_id=sender.id,
                      recipient_role=recipient.role, recipient_id=recipient.id,
                      subject=subject, content=content, is_read=False)
    db.session.add(message)
    db.session.flush()
    attachment = store_message_attachment(message.id, checked) if checked else None
    db.session.commit()
    who = 'DEVTech Support' if sender.role == 'admin' else sender.full_name
    create_notification(recipient.id, 'New Message',
                        f'You have a new message from {who}' + (f': {subject}' if subject else ''),
                        'info', role=recipient.role)
    return message, attachment

def _conversation(other, me, latest=None):
    return {'id': other.id, 'key': other.key, 'name': other.full_name, 'role': other.role,
            'email': other.email,
            'last_message': message_preview(latest) if latest else '',
            'last_time': latest.created_at if latest else datetime.utcnow(),
            'unread_count': Message.query.filter_by(sender_role=other.role, sender_id=other.id,
                                                    recipient_role=me.role, recipient_id=me.id,
                                                    is_read=False).count(),
            'is_active': False, 'is_online': is_user_online(other.last_active)}

def _load_inbox(me, selected=None):
    """Conversations for account `me` (newest first) and, if `selected` (an account)
    is a valid partner, that thread with its unread messages marked read.
    Returns (conversations, selected_conversation, messages)."""
    partners = set()
    for role, uid in db.session.query(Message.recipient_role, Message.recipient_id)\
            .filter_by(sender_role=me.role, sender_id=me.id).distinct():
        partners.add((role, uid))
    for role, uid in db.session.query(Message.sender_role, Message.sender_id)\
            .filter_by(recipient_role=me.role, recipient_id=me.id).distinct():
        partners.add((role, uid))
    conversations = []
    for role, uid in partners:
        other = get_account(role, uid)
        if not other:
            continue
        latest = Message.query.filter(_thread_filter(me, other)).order_by(Message.created_at.desc()).first()
        conversations.append(_conversation(other, me, latest))
    conversations.sort(key=lambda x: x['last_time'], reverse=True)

    selected_conversation, messages_data = None, []
    if selected is not None:
        selected_conversation = next((c for c in conversations if c['key'] == selected.key), None)
        if not selected_conversation and _can_message(me, selected):
            selected_conversation = _conversation(selected, me)
        if selected_conversation:
            selected_conversation['is_active'] = True
            Message.query.filter_by(sender_role=selected.role, sender_id=selected.id,
                                    recipient_role=me.role, recipient_id=me.id, is_read=False)\
                .update({'is_read': True})
            db.session.commit()
            rows = Message.query.filter(_thread_filter(me, selected)).order_by(Message.created_at.asc()).all()
            files = attachments_by_message(m.id for m in rows)
            messages_data = [SimpleNamespace(content=m.content, created_at=m.created_at, subject=m.subject,
                                             is_sent=(m.sender_role, m.sender_id) == (me.role, me.id),
                                             attachments=files.get(m.id, [])) for m in rows]
    return conversations, selected_conversation, messages_data

def _account_from_key(key):
    role, account_id = parse_account_key(key)
    return get_account(role, account_id)

@app.route('/messages')
@account_required
def messages():
    # Staff have their own inboxes with their own layout.
    conv = request.args.get('conv')
    if session.get('role') == 'admin':
        return redirect(url_for('admin_messages', conv=conv))
    if session.get('role') == 'technician':
        return redirect(url_for('technician.messages', thread=conv))
    me = current_account()
    try:
        conversations, selected_conversation, messages_data = _load_inbox(me, _account_from_key(conv))
        if not selected_conversation and conversations:
            return redirect(url_for('messages', conv=conversations[0]['key']))
        return render_template('user/messages.html', conversations=conversations,
                               selected_conversation=selected_conversation, messages=messages_data)
    except Exception:
        db.session.rollback()
        app.logger.exception('Loading messages failed')
        flash('Messages could not be loaded. Please try again later.', 'info')
        return render_template('user/messages.html', conversations=[], selected_conversation=None, messages=[])

@app.route('/messages/<conv_key>/send', methods=['POST'])
@login_required
def message_send(conv_key):
    me = current_account()
    if request.mimetype == 'multipart/form-data':
        content = (request.form.get('content') or '').strip()
        upload = request.files.get('attachment')
    else:
        content = ((request.get_json(silent=True) or {}).get('content') or '').strip()
        upload = None
    checked, file_error = check_message_attachment(upload)
    if file_error:
        return jsonify({'success': False, 'message': file_error}), 400
    if not content and not checked:
        return jsonify({'success': False, 'message': 'Write a message or attach a file.'}), 400
    if len(content) > MAX_MESSAGE_LENGTH:
        return jsonify({'success': False, 'message': f'Messages can be at most {MAX_MESSAGE_LENGTH} characters.'}), 400
    recipient = _account_from_key(conv_key)
    if not _can_message(me, recipient):
        return jsonify({'success': False, 'message': 'You cannot message this user.'}), 403
    try:
        _, attachment = send_message(me, recipient, content, checked=checked)
        return jsonify({'success': True, 'message': 'Message sent',
                        'time': datetime.utcnow().strftime('%I:%M %p'),
                        'attachments': [attachment_info(attachment)] if attachment else []})
    except Exception:
        db.session.rollback()
        app.logger.exception('Sending message failed')
        return jsonify({'success': False, 'message': 'Your message could not be sent. Please try again.'}), 500

@app.route('/messages/new', methods=['POST'])
@login_required
def message_new():
    me = current_account()
    data = request.get_json(silent=True) or {}
    recipient = data.get('recipient')
    subject = (data.get('subject') or '').strip()
    content = (data.get('content') or '').strip()
    if not recipient or not subject or not content:
        return jsonify({'success': False, 'message': 'All fields are required'}), 400
    if len(subject) > 200 or len(content) > MAX_MESSAGE_LENGTH:
        return jsonify({'success': False, 'message': f'Subject must be under 200 characters and message under {MAX_MESSAGE_LENGTH}.'}), 400
    try:
        if recipient == 'technician':
            b = Booking.query.filter(Booking.customer_id == me.id, Booking.technician_id.isnot(None))\
                .order_by(Booking.created_at.desc()).first()
            recipient_user = b.technician if b else None
            if not recipient_user:
                return jsonify({'success': False,
                                'message': 'No technician has been assigned to your bookings yet.'}), 404
        elif recipient in ('support', 'admin'):
            recipient_user = Admin.query.filter_by(is_active=True).order_by(Admin.id).first()
            if not recipient_user:
                return jsonify({'success': False, 'message': 'Recipient not found'}), 404
        else:
            return jsonify({'success': False, 'message': 'Invalid recipient.'}), 400
        if not _can_message(me, recipient_user):
            return jsonify({'success': False, 'message': 'You cannot message this user.'}), 403
        send_message(me, recipient_user, content, subject=subject)
        return jsonify({'success': True, 'message': 'Message sent successfully'})
    except Exception:
        db.session.rollback()
        app.logger.exception('Sending message failed')
        return jsonify({'success': False, 'message': 'Your message could not be sent. Please try again.'}), 500

# ==================== PUBLIC-ISH API ====================
@app.route('/api/available-slots')
def api_available_slots():
    date = request.args.get('date')
    if not date:
        return jsonify({'error': 'Date parameter required'}), 400
    try:
        booking_date = datetime.strptime(date, '%Y-%m-%d').date()
        bookings = Booking.query.filter(Booking.booking_date == booking_date,
                                        Booking.status.in_(SLOT_STATUSES)).all()
        slot_counts = {}
        for b in bookings:
            k = b.booking_time.strftime('%H:%M')
            slot_counts[k] = slot_counts.get(k, 0) + 1
        slots = []
        for hour in range(8, 18):
            t = f"{hour:02d}:00"
            disp = hour - 12 if hour > 12 else hour
            count = slot_counts.get(t, 0)
            slots.append({'time': t, 'booked_count': count, 'max_slots': 5, 'available': count < 5,
                          'display': f"{disp}:00 {'AM' if hour < 12 else 'PM'}"})
        return jsonify({'date': date, 'slots': slots, 'total_bookings': len(bookings)})
    except ValueError:
        return jsonify({'error': 'Invalid date format'}), 400
 
@app.route('/api/service-categories')
def api_service_categories():
    result = []
    for cat in ServiceCategory.query.filter_by(is_active=True).order_by(ServiceCategory.display_order).all():
        services = Service.query.filter_by(category_id=cat.id, is_active=True).all()
        result.append({'id': cat.id, 'name': cat.name, 'icon': cat.icon or 'fa-tools',
                       'services': [{'id': s.id, 'name': s.name, 'description': s.description,
                                     'price': float(s.price), 'estimated_hours': s.estimated_hours}
                                    for s in services]})
    return jsonify(result)
 
@app.route('/api/service/<int:service_id>')
def api_service_detail(service_id):
    s = Service.query.get_or_404(service_id)
    return jsonify({'id': s.id, 'name': s.name, 'description': s.description, 'price': float(s.price),
                    'estimated_hours': s.estimated_hours, 'category': s.category.name if s.category else None})
 
@app.route('/api/check-availability', methods=['POST'])
def api_check_availability():
    data = request.get_json(silent=True) or {}
    date, time_, service_id = data.get('date'), data.get('time'), data.get('service_id')
    if not date or not time_ or not service_id:
        return jsonify({'error': 'Date, time, and service_id required'}), 400
    try:
        count = Booking.query.filter(Booking.booking_date == datetime.strptime(date, '%Y-%m-%d').date(),
                                     Booking.booking_time == datetime.strptime(time_, '%H:%M').time(),
                                     Booking.status.in_(SLOT_STATUSES)).count()
        return jsonify({'available': count < 5, 'booked_count': count, 'max_slots': 5, 'remaining': 5 - count})
    except ValueError:
        return jsonify({'error': 'Invalid date or time format'}), 400
 
@app.route('/api/check-slot')
def api_check_slot():
    date, time_ = request.args.get('date'), request.args.get('time')
    if not date or not time_:
        return jsonify({'error': 'Date and time parameters required'}), 400
    try:
        booking = Booking.query.filter(Booking.booking_date == datetime.strptime(date, '%Y-%m-%d').date(),
                                       Booking.booking_time == datetime.strptime(time_, '%H:%M').time(),
                                       Booking.status.in_(SLOT_STATUSES)).first()
        return jsonify({'date': date, 'time': time_, 'is_booked': booking is not None,
                        'booking_id': booking.id if booking else None})
    except ValueError:
        return jsonify({'error': 'Invalid date or time format'}), 400
 
@app.route('/api/booked-slots')
def api_booked_slots():
    date = request.args.get('date')
    if not date:
        return jsonify({'error': 'Date parameter required'}), 400
    try:
        booking_date = datetime.strptime(date, '%Y-%m-%d').date()
        bookings = Booking.query.filter(Booking.booking_date == booking_date,
                                        Booking.status.in_(SLOT_STATUSES)).all()
        return jsonify({'date': date, 'booked_slots': [b.booking_time.strftime('%H:%M') for b in bookings],
                        'total_bookings': len(bookings)})
    except ValueError:
        return jsonify({'error': 'Invalid date format'}), 400
 
@app.route('/api/services')
def api_services():
    return jsonify([{'id': s.id, 'name': s.name, 'description': s.description, 'price': float(s.price),
                     'category': s.category.name if s.category else None, 'estimated_hours': s.estimated_hours}
                    for s in Service.query.filter_by(is_active=True).all()])
 
# ==================== SERVICE REQUEST / CATALOG / BOOKING ====================
BOOKING_PAYMENT_METHODS = ('GCash', 'C.A.R')       # values of the booking form's radio buttons
BOOKING_SLOT_HOURS = range(8, 18)                  # 08:00 ... 17:00, on the hour
SLOT_CAPACITY = 5
BOOKING_MAX_DAYS_AHEAD = 90

@app.route('/user/service-request', methods=['GET', 'POST'])
@login_required
def request_service():
    if request.method == 'POST':
        user_id = session.get('user_id')
        service_id = request.form.get('service_id')
        device_type = request.form.get('device_type')
        description = request.form.get('problem_description', '')
        address = request.form.get('service_address')
        booking_date = request.form.get('booking_date')
        booking_time = request.form.get('booking_time')
        is_in_shop = request.form.get('in_shop') == 'on'
        payment_method = request.form.get('payment_method', '')

        if request.form.get('accept_terms') != 'on':
            flash('Please read and accept the Terms of Service to book a repair.', 'danger')
            return redirect(url_for('request_service'))
        if payment_method not in BOOKING_PAYMENT_METHODS:
            flash('Please choose a payment method.', 'danger')
            return redirect(url_for('request_service'))
 
        if service_id == 'other':
            custom_service = request.form.get('custom_service', '').strip()
            if not custom_service:
                flash('Please specify your service requirement.', 'danger')
                return redirect(url_for('request_service'))
            obj = Service.query.filter_by(name='Custom Service').first()
            if not obj:
                cat = ServiceCategory.query.first()
                if not cat:
                    cat = ServiceCategory(name='Custom Services', description='Custom service requests',
                                          icon='fa-tools', is_active=True)
                    db.session.add(cat)
                    db.session.commit()
                # Hidden from the catalogue: only reachable through "Other".
                obj = Service(category_id=cat.id, name='Custom Service',
                              description='Custom service requested by user.', price=0.00,
                              estimated_hours=1, is_active=False)
                db.session.add(obj)
                db.session.commit()
            service_id_for_booking = obj.id
            description = f"{description}\n\n📝 Custom Service: {custom_service}" if description \
                else f"📝 Custom Service: {custom_service}"
        else:
            chosen = db.session.get(Service, int(service_id)) if str(service_id or '').isdigit() else None
            if not chosen or not chosen.is_active:
                flash('That service is not available. Please choose another one.', 'danger')
                return redirect(url_for('request_service'))
            service_id_for_booking = chosen.id
 
        if device_type == 'Other':
            custom_device = request.form.get('custom_device', '').strip()
            if not custom_device:
                flash('Please specify your device type.', 'danger')
                return redirect(url_for('request_service'))
            device_type = custom_device
        device_type = (device_type or '').strip()
        if not device_type or len(device_type) > 50:
            flash('Please select a device type (up to 50 characters).', 'danger')
            return redirect(url_for('request_service'))
        if address and len(address) > 255:
            flash('Please shorten the service address (up to 255 characters).', 'danger')
            return redirect(url_for('request_service'))
        if not booking_date or not booking_time:
            flash('Please select a booking date and time.', 'danger')
            return redirect(url_for('request_service'))
        if not is_in_shop and not address:
            flash('Please provide an address for home service or select in-shop repair.', 'danger')
            return redirect(url_for('request_service'))
 
        try:
            booking_date_obj = datetime.strptime(booking_date, '%Y-%m-%d').date()
            booking_time_obj = datetime.strptime(booking_time, '%H:%M').time()
        except ValueError:
            flash('Invalid date or time format.', 'danger')
            return redirect(url_for('request_service'))
 
        # Server-side location check for home service (client check alone is bypassable)
        if not is_in_shop:
            try:
                lat = float(request.form.get('pinned_lat', ''))
                lng = float(request.form.get('pinned_lng', ''))
                if not (11.10 <= lat <= 11.36 and 124.90 <= lng <= 125.12):
                    raise ValueError
            except ValueError:
                flash('Please pin your location on the map, inside Tacloban City.', 'danger')
                return redirect(url_for('request_service'))
 
        if (booking_time_obj.minute or booking_time_obj.second
                or booking_time_obj.hour not in BOOKING_SLOT_HOURS):
            flash('Please choose one of the listed time slots (8:00 AM to 5:00 PM).', 'danger')
            return redirect(url_for('request_service'))
        if datetime.combine(booking_date_obj, booking_time_obj) < datetime.now():
            flash('That time has already passed. Please choose a later slot.', 'danger')
            return redirect(url_for('request_service'))
        if booking_date_obj > (datetime.now() + timedelta(days=BOOKING_MAX_DAYS_AHEAD)).date():
            flash(f'Bookings can be made up to {BOOKING_MAX_DAYS_AHEAD} days ahead.', 'danger')
            return redirect(url_for('request_service'))

        # Lock this slot's bookings so two requests can't both take the last place
        # (MySQL row/gap locks on ix_bookings_slot; a no-op on SQLite).
        in_slot = Booking.query.filter(Booking.booking_date == booking_date_obj,
                                       Booking.booking_time == booking_time_obj,
                                       Booking.status.in_(SLOT_STATUSES)).with_for_update().all()
        mine = next((b for b in in_slot if b.customer_id == user_id), None)
        if mine:
            db.session.rollback()
            flash(f'You already have booking #{mine.booking_number} at that time.', 'info')
            return redirect(url_for('total_bookings'))
        if len(in_slot) >= SLOT_CAPACITY:
            db.session.rollback()
            flash('This time slot is fully booked. Please choose another time.', 'danger')
            return redirect(url_for('request_service'))
 
        service_obj = Service.query.get(service_id_for_booking)
        booking = Booking(booking_number=placeholder_number(), user_id=user_id, service_id=service_id_for_booking,
                          device_type=device_type, description=description or 'No description provided',
                          address=address if not is_in_shop else 'In-shop repair',
                          booking_date=booking_date_obj, booking_time=booking_time_obj,
                          is_in_shop=is_in_shop, status='pending', terms_accepted_at=datetime.utcnow())
        db.session.add(booking)
        db.session.flush()
        assign_booking_number(booking)
        booking_number = booking.booking_number
        transaction = Transaction(transaction_number=placeholder_number(), booking_id=booking.id,
                                  user_id=user_id, amount=service_obj.price,
                                  payment_method=payment_method, payment_status='pending')
        db.session.add(transaction)
        db.session.flush()
        assign_transaction_number(transaction)
        db.session.commit()
        create_notification(user_id, 'Booking Created',
                            f'Your booking #{booking_number} has been created. Please complete the payment.', 'info',
                            role='customer')
        flash(f'Booking created successfully! Booking #: {booking_number}', 'success')
        return redirect(url_for('user_transactions'))
 
    # One booking page for everyone: /user/book (its form posts back here).
    return redirect(url_for('book_appointment'))

@app.route('/user/services')
@login_required
def service_catalog():
    categories = ServiceCategory.query.filter_by(is_active=True)\
        .order_by(ServiceCategory.display_order, ServiceCategory.name).all()
    return render_template('user/service_catalog.html', categories=categories,
                           notifications=_unread_notifs(session.get('user_id')))
 
@app.route('/user/book', methods=['GET', 'POST'])
@app.route('/user/book/<category_slug>', methods=['GET', 'POST'])
@login_required
def book_appointment(category_slug=None):
    if request.method == 'POST':
        return request_service()
    category = None
    if category_slug:
        category = ServiceCategory.query.filter_by(slug=category_slug, is_active=True).first()
        if not category and category_slug.startswith('cat-') and category_slug[4:].isdigit():
            category = ServiceCategory.query.get(int(category_slug[4:]))
        if not category:
            abort(404)
    q = Service.query.filter_by(is_active=True)
    if category:
        q = q.filter_by(category_id=category.id)
    return render_template('user/book_appointment.html', services=q.order_by(Service.name).all(),
                           category=category, notifications=_unread_notifs(session.get('user_id')))
 
# ==================== DEVICE MONITOR ====================
 
@app.route('/user/monitor-device')
@app.route('/user/monitor-device/<int:booking_id>')
@login_required
def monitor_device(booking_id=None):
    uid = session['user_id']
    if booking_id is None:
        b = Booking.query.filter_by(user_id=uid).filter(
                Booking.status.in_(['confirmed', 'in_progress', 'on_hold'])
            ).order_by(Booking.created_at.desc()).first() \
            or Booking.query.filter_by(user_id=uid).order_by(Booking.created_at.desc()).first()
        if not b:
            flash('You have no bookings to monitor yet.', 'info')
            return redirect(url_for('total_bookings'))
        return redirect(url_for('monitor_device', booking_id=b.id))
    booking = Booking.query.get_or_404(booking_id)
    if booking.user_id != uid:
        abort(403)
    return render_template('user/monitor_device.html', booking=booking, notifications=_unread_notifs(uid))
 
@app.route('/api/booking/<int:booking_id>/monitor')
@limiter.exempt
@login_required
def api_booking_monitor(booking_id):
    from models.technician_models import (JobLog, ServiceRating, ServiceReport, ApprovalRequest,
                                          technician_rating)
    from blueprints.technician_api import approval_dict
    b = Booking.query.get(booking_id)
    if not b or b.user_id != session['user_id']:
        return jsonify({'ok': False, 'reason': 'Not found.'}), 404

    keys = [s[0] for s in STAGES]
    if b.status == 'cancelled':   idx = 0
    elif b.status == 'on_hold':   idx = keys.index('in_progress')
    else:                         idx = keys.index(b.status) if b.status in keys else 0

    rep = ServiceReport.query.filter_by(booking_id=b.id).order_by(ServiceReport.id.desc()).first()
    done = bool(rep and rep.status == 'submitted')
    repair = {'diagnosis': rep.diagnosis,
              'outcome': rep.outcome if done else None,
              'recommendations': rep.recommendations if done else None} \
             if rep and rep.diagnosis else None

    tech = None
    if b.technician:
        t = b.technician
        avg, cnt = technician_rating(t.id)
        tech = {'id': t.id, 'key': t.key, 'name': t.full_name, 'verified': bool(t.id_verified),
                'role': 'Technician',
                'initials': ''.join(w[0] for w in (t.full_name or '').split()[:2]).upper() or 'T',
                'rating': avg or 5.0, 'rating_count': cnt,
                'phone': t.phone, 'email': t.email}

    rating = ServiceRating.query.filter_by(booking_id=b.id).first()
    logs = JobLog.query.filter_by(booking_id=b.id).order_by(JobLog.id.desc()).all()
    txn = b.transaction
    fmt = lambda d, f: d.strftime(f) if d else ''
    return jsonify({
        'ok': True,
        'booking': {'number': b.booking_number, 'status': b.status,
                    'statusLabel': STATUS_LABELS.get(b.status, b.status),
                    'service': b.service.name, 'description': b.description,
                    'deviceType': b.device_type, 'isInShop': b.is_in_shop,
                    'address': b.address,
                    'scheduledDate': fmt(b.booking_date, '%b %d, %Y'),
                    'scheduledTime': fmt(b.booking_time, '%I:%M %p'),
                    'createdAt': fmt(b.created_at, '%b %d, %Y %I:%M %p'),
                    'updatedAt': fmt(b.updated_at, '%b %d, %Y %I:%M %p')},
        'stages': [{'key': k, 'label': l, 'icon': i} for k, l, i in STAGES],
        'stageIndex': idx,
        'payment': {'method': txn.payment_method, 'status': txn.payment_status,
                    'amount': float(txn.amount)} if txn else None,
        'technician': tech,
        'repair': repair,
        'approval': approval_dict(ApprovalRequest.query.filter_by(booking_id=b.id, status='pending').first()),
        'canRate': bool(b.status in FINISHED_STATUSES and b.technician_id and not rating),
        'rating': {'stars': rating.stars, 'experience': rating.experience,
                   'improvement': rating.improvement,
                   'submittedAt': fmt(rating.submitted_at, '%b %d, %Y')} if rating else None,
        'timeline': [{'action': l.action, 'text': l.text, 'by': l.by_name, 'at': l.at}
                     for l in logs
                     if l.action in ('assign', 'status', 'intake', 'diagnosis', 'approval', 'release')],
    })
    
@app.route('/api/booking/<int:booking_id>/rate', methods=['POST'])
@login_required
def api_booking_rate(booking_id):
    from models.technician_models import ServiceRating
    b = Booking.query.get(booking_id)
    if not b or b.user_id != session['user_id']:
        return jsonify({'ok': False, 'reason': 'Not found.'}), 404
    if b.status not in FINISHED_STATUSES or not b.technician_id:
        return jsonify({'ok': False, 'reason': 'Only completed jobs can be rated.'}), 400
    if ServiceRating.query.filter_by(booking_id=b.id).first():
        return jsonify({'ok': False, 'reason': 'You already rated this repair.'}), 400
    d = request.get_json(silent=True) or {}
    try:
        stars = int(d.get('stars'))
    except (TypeError, ValueError):
        stars = 0
    exp = (d.get('experience') or '').strip()
    if not 1 <= stars <= 5:
        return jsonify({'ok': False, 'reason': 'Choose 1 to 5 stars.'}), 400
    if len(exp) < 15:
        return jsonify({'ok': False, 'reason': 'Please describe your experience (15+ characters).'}), 400
    db.session.add(ServiceRating(booking_id=b.id, technician_id=b.technician_id, customer_id=b.user_id,
                                 stars=stars, experience=exp[:2000],
                                 improvement=(d.get('improvement') or '').strip()[:2000]))
    try:
        db.session.commit()
    except IntegrityError:                       # rated a moment ago from another tab
        db.session.rollback()
        return jsonify({'ok': False, 'reason': 'You already rated this repair.'}), 400
    create_notification(b.technician_id, 'New Rating', f'{b.booking_number} was rated {stars}/5.', 'info',
                        role='technician')
    return jsonify({'ok': True})

@app.route('/api/booking/<int:booking_id>/approval/<int:approval_id>/respond', methods=['POST'])
@login_required
def api_booking_approval_respond(booking_id, approval_id):
    """Customer approves or declines extra work the technician asked about.
    Either answer takes the job off hold."""
    from decimal import Decimal
    from models.technician_models import ApprovalRequest, JobLog
    from blueprints.technician_api import resume_status, approval_dict
    b = db.session.get(Booking, booking_id)
    a = db.session.get(ApprovalRequest, approval_id)
    if not b or b.user_id != session['user_id'] or not a or a.booking_id != b.id:
        return jsonify({'ok': False, 'reason': 'Not found.'}), 404
    if a.status != 'pending':
        return jsonify({'ok': False, 'reason': 'This request was already answered.'}), 400
    if b.status != 'on_hold':
        return jsonify({'ok': False, 'reason': 'This job is no longer waiting for your answer.'}), 400
    data = request.get_json(silent=True) or {}
    decision = data.get('decision')
    if decision not in ('approve', 'decline'):
        return jsonify({'ok': False, 'reason': 'Choose approve or decline.'}), 400
    note = (data.get('note') or '').strip()[:1000]

    now_str = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
    # Claim the request in one UPDATE so a double click (or two tabs) can't
    # answer it twice and bill the extra cost twice.
    claimed = ApprovalRequest.query.filter_by(id=a.id, status='pending').update(
        {'status': 'approved' if decision == 'approve' else 'declined',
         'responded_at': now_str, 'customer_response': note or None}, synchronize_session=False)
    if claimed != 1:
        db.session.rollback()
        return jsonify({'ok': False, 'reason': 'This request was already answered.'}), 400
    db.session.refresh(a)
    if b.status == 'on_hold':
        b.status = resume_status(b)
    b.updated_at = datetime.utcnow()

    extra = Decimal(str(a.additional_cost or 0)).quantize(Decimal('0.01'))
    if decision == 'approve' and extra > 0:
        txn = b.transaction
        if txn and txn.payment_status in ('pending', 'rejected'):
            txn.amount = Decimal(txn.amount) + extra   # still unpaid: bill it together
        else:
            # Already paid: bill the extra separately. The booking number is kept
            # in the (never-edited) transaction number so it stays traceable.
            extra_txn = Transaction(transaction_number=placeholder_number(), user_id=b.user_id,
                                    amount=extra, payment_method='unpaid', payment_status='pending')
            db.session.add(extra_txn)
            db.session.flush()
            extra_txn.transaction_number = f'{EXTRA_TXN_PREFIX}{b.booking_number}-{extra_txn.id}'

    verb = 'approved' if decision == 'approve' else 'declined'
    db.session.add(JobLog(booking_id=b.id, at=now_str, by_name=b.user.full_name, action='approval',
                          text=f'Customer {verb} the proposed work.' + (f' Note: {note}' if note else '')))
    db.session.commit()
    if a.technician_id:
        create_notification(a.technician_id, f'Customer {verb.title()} Request',
                            f'{b.booking_number}: the customer {verb} your request. The job has resumed.',
                            'success' if decision == 'approve' else 'warning', role='technician')
    if decision == 'approve' and extra > 0:
        create_notification(b.user_id, 'Extra Charge Added',
                            f'₱{extra:,.2f} for the approved work on {b.booking_number} was added to your '
                            f'payments. See Transactions.', 'info', role='customer')
    return jsonify({'ok': True, 'approval': approval_dict(a), 'status': b.status})

# ==================== TRANSACTION ROUTES ====================
@app.route('/user/transactions')
@login_required
def user_transactions():
    uid = session.get('user_id')
    transactions = Transaction.query.filter_by(user_id=uid).order_by(Transaction.transaction_date.desc()).all()
    return render_template('user/transactions.html', transactions=transactions, notifications=_unread_notifs(uid))
 
@app.route('/user/payments/<int:transaction_id>', methods=['POST'])
@login_required
def user_payment(transaction_id):
    user_id = session.get('user_id')
    transaction = Transaction.query.get_or_404(transaction_id)
    if transaction.user_id != user_id:
        flash('Unauthorized access.', 'danger')
        return redirect(url_for('user_transactions'))
    if transaction.payment_status == 'confirmed':
        flash('This payment is already confirmed.', 'info')
        return redirect(url_for('user_transactions'))
    if transaction.payment_status == 'cancelled':
        flash('This payment belongs to a cancelled order.', 'info')
        return redirect(url_for('user_transactions'))

    payment_method = request.form.get('payment_method') or ''
    reference = (request.form.get('reference_number') or '').strip()
    receipt_file = request.files.get('receipt_image')

    # Orders are paid by GCash (or cash on delivery, which needs no submission);
    # bookings by GCash or C.A.R. Anything else is refused.
    allowed = ('GCash',) if transaction.order else BOOKING_PAYMENT_METHODS
    if payment_method and payment_method not in allowed:
        flash('Please choose a valid payment method.', 'danger')
        return redirect(url_for('user_transactions'))
    if len(reference) > 50:
        flash('The reference number is too long (50 characters at most).', 'danger')
        return redirect(url_for('user_transactions'))
    if payment_method == 'GCash' and not reference and not (receipt_file and receipt_file.filename):
        flash('Enter your GCash reference number or upload the receipt.', 'danger')
        return redirect(url_for('user_transactions'))

    if payment_method:
        if transaction.order:                    # keep the order and its payment in step
            transaction.payment_method = 'gcash'
            transaction.order.payment_method = 'gcash'
        else:
            transaction.payment_method = payment_method
    if reference:
        if payment_method == 'GCash':
            transaction.gcash_reference = reference
        transaction.reference_number = reference
 
    if receipt_file and receipt_file.filename:
        if not allowed_file(receipt_file.filename):
            flash('Invalid file format. Please upload JPG, PNG, GIF, or PDF.', 'danger')
            return redirect(url_for('user_transactions'))
        extension = receipt_file.filename.rsplit('.', 1)[1].lower()
        ok, err = validate_uploaded_file(receipt_file, extension)
        if not ok:
            flash(err, 'danger')
            return redirect(url_for('user_transactions'))
        receipts_dir = app.config['RECEIPT_UPLOAD_FOLDER']
        os.makedirs(receipts_dir, exist_ok=True)
        timestamp = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
        filename = secure_filename(f"receipt_{transaction.transaction_number}_{timestamp}_{secrets.token_hex(4)}.{extension}")
        receipt_file.save(os.path.join(receipts_dir, filename))
        transaction.receipt_image = filename
        flash('Receipt uploaded successfully.', 'success')
 
    transaction.payment_status = 'pending'
    transaction.rejection_reason = None
    transaction.updated_at = datetime.utcnow()
    if transaction.order:
        transaction.order.payment_status = 'pending'
    db.session.commit()
    create_notification(user_id, 'Payment Submitted',
                        f'Your payment for transaction #{transaction.transaction_number} has been submitted for verification.',
                        'info', role='customer')
    notify_admins('Payment Awaiting Confirmation',
                  f'{transaction.transaction_number} (₱{float(transaction.amount):,.2f}) was submitted for '
                  f'verification.', 'info')
    flash('Payment submitted. Please wait for admin confirmation.', 'success')
    return redirect(url_for('user_transactions'))

LEGACY_RECEIPT_FOLDER = os.path.join('static', 'uploads', 'receipts')

def receipt_url(transaction):
    """Authenticated URL for a transaction's receipt, or '' if it has none."""
    if not transaction.receipt_image or not transaction.receipt_image.strip():
        return ''
    return url_for('receipt_file', transaction_id=transaction.id,
                   name=os.path.basename(transaction.receipt_image))

app.jinja_env.globals['receipt_url'] = receipt_url
app.jinja_env.globals['extra_work_booking'] = extra_work_booking

@app.route('/receipts/<int:transaction_id>/<name>')
@account_required
def receipt_file(transaction_id, name):
    """Serves a receipt only to the customer who uploaded it or to an admin."""
    transaction = Transaction.query.get_or_404(transaction_id)
    viewer = current_account()
    is_owner = viewer.role == 'customer' and transaction.customer_id == viewer.id
    if not is_owner and viewer.role != 'admin':
        abort(404)
    stored = os.path.basename(transaction.receipt_image or '')
    if not stored or stored != name:
        abort(404)
    # Receipts uploaded before this route existed may still sit in the old folder.
    for folder in (app.config['RECEIPT_UPLOAD_FOLDER'], LEGACY_RECEIPT_FOLDER):
        path = os.path.abspath(os.path.join(folder, stored))
        if os.path.isfile(path):
            return send_file(path)
    abort(404)

# ==================== SUPPORT ROUTE ====================
@app.route('/support', methods=['GET', 'POST'])
@login_required
def support():
    user_id = session.get('user_id')
    if request.method == 'POST':
        subject, message = request.form.get('subject'), request.form.get('message')
        category = request.form.get('category')
        if not subject or not message:
            flash('Please fill in all required fields.', 'danger')
            return redirect(url_for('support'))
        db.session.add(SupportTicket(customer_id=user_id, subject=subject, message=message[:1000],
                                     category=category or 'general'))
        db.session.commit()
        notify_admins('New Support Ticket', f'New support ticket from {current_account().full_name}: {subject}')
        flash('Your support ticket has been submitted. We will get back to you shortly.', 'success')
        return redirect(url_for('support'))
    tickets = SupportTicket.query.filter_by(customer_id=user_id).order_by(SupportTicket.created_at.desc()).all()
    return render_template('user/support.html', tickets=tickets, notifications=_unread_notifs(user_id))

# ==================== PROFILE LOOK (all three account types) ====================
AVATAR_NAME_RE = re.compile(r'^[0-9a-f]{24}\.(jpg|png|webp|gif)$')
PROFILE_ENDPOINT = {'customer': 'user_profile', 'technician': 'technician.profile', 'admin': 'admin_profile'}

def password_problem(password, confirm):
    """Reason the new password is not acceptable, or None."""
    if len(password) < 8 or not re.search(r'[A-Za-z]', password) or not re.search(r'\d', password):
        return 'Use at least 8 characters, including a letter and a number.'
    if password != confirm:
        return 'The two new passwords do not match.'
    return None

def _avatar_path(filename):
    return os.path.join(app.config['AVATAR_UPLOAD_FOLDER'], filename)

def _remove_avatar_file(account):
    if account.avatar_file and AVATAR_NAME_RE.match(account.avatar_file):
        try:
            os.remove(_avatar_path(account.avatar_file))
        except OSError:
            pass
    account.avatar_file = None

def _save_avatar(account, file_storage):
    """Validate and store a profile photo. Returns an error message or None."""
    from services.upload_service import check_file
    if (file_storage.mimetype or '') not in profile_presets.AVATAR_MIME:
        return 'Profile photos must be JPG, PNG, WEBP or GIF images.'
    ok, result = check_file(file_storage, profile_presets.AVATAR_MAX_BYTES)
    if not ok:
        return result
    data, _mime, ext, _name = result
    filename = secrets.token_hex(12) + ext
    os.makedirs(app.config['AVATAR_UPLOAD_FOLDER'], exist_ok=True)
    with open(_avatar_path(filename), 'wb') as fh:
        fh.write(data)
    _remove_avatar_file(account)
    account.avatar_file = filename
    return None

@app.route('/avatars/<filename>')
@account_required
def account_avatar(filename):
    """Profile photos: visible to any signed-in account (they show up in messages
    and on job pages), never to anonymous visitors."""
    if not AVATAR_NAME_RE.match(filename) or not os.path.isfile(_avatar_path(filename)):
        abort(404)
    resp = send_file(_avatar_path(filename), max_age=3600)
    resp.headers['X-Content-Type-Options'] = 'nosniff'
    return resp

@app.route('/account/appearance', methods=['POST'])
@account_required
@limiter.limit('30 per hour')
def account_appearance():
    """Save the profile look: display name, headline, avatar (photo / icon /
    initials), avatar colour and frame, and banner."""
    account = current_account()
    back = redirect(url_for(PROFILE_ENDPOINT[account.role]) + '#look')
    form = request.form

    display_name = (form.get('display_name') or '').strip()
    headline = (form.get('headline') or '').strip()
    if len(display_name) > profile_presets.DISPLAY_NAME_MAX:
        flash(f'Display name can be at most {profile_presets.DISPLAY_NAME_MAX} characters.', 'danger')
        return back
    if len(headline) > profile_presets.HEADLINE_MAX:
        flash(f'Headline can be at most {profile_presets.HEADLINE_MAX} characters.', 'danger')
        return back

    mode = form.get('avatar_mode', 'initials')
    photo = request.files.get('avatar_photo')
    if mode == 'photo' and photo and photo.filename:
        error = _save_avatar(account, photo)
        if error:
            flash(error, 'danger')
            return back
    elif mode == 'photo' and not account.avatar_file:
        flash('Choose a photo to upload, or pick an icon or your initials instead.', 'danger')
        return back
    elif mode in ('icon', 'initials'):
        _remove_avatar_file(account)

    account.display_name = display_name or None
    account.headline = headline or None
    account.avatar_icon = (profile_presets.pick(form.get('avatar_icon'), profile_presets.AVATAR_ICONS, None)
                           if mode == 'icon' else None)
    account.avatar_color = profile_presets.pick(form.get('avatar_color'), profile_presets.AVATAR_COLORS,
                                                account.avatar_color_key)
    account.avatar_frame = profile_presets.pick(form.get('avatar_frame'), profile_presets.AVATAR_FRAMES,
                                                account.avatar_frame_key)
    account.banner = profile_presets.pick(form.get('banner'), profile_presets.BANNERS, account.banner_key)
    db.session.commit()
    if account.role != 'technician':      # the Tech ID stays the technician's sign-in name
        session['username'] = account.shown_name
    log_activity(account.id, 'profile_update', 'Updated profile look', role=account.role)
    flash('Your profile look was saved.', 'success')
    return back

@app.route('/admin/profile', methods=['GET', 'POST'])
@admin_required
def admin_profile():
    admin = current_account()
    if request.method == 'POST':
        action = request.form.get('action')
        if action == 'details':
            full_name = (request.form.get('full_name') or '').strip()
            phone = (request.form.get('phone') or '').strip()
            if not full_name or len(full_name) > 100 or len(phone) > 20:
                flash('Enter your full name (up to 100 characters) and a phone number up to 20 characters.', 'danger')
            else:
                admin.full_name, admin.phone = full_name, phone or None
                db.session.commit()
                session['username'] = admin.shown_name
                log_activity(admin.id, 'profile_update', 'Updated admin profile details')
                flash('Your details were saved.', 'success')
        elif action == 'password':
            current = request.form.get('current_password') or ''
            new = request.form.get('new_password') or ''
            problem = (None if admin.check_password(current) else 'Your current password is incorrect.') \
                or password_problem(new, request.form.get('confirm_password') or '')
            if problem:
                flash(problem, 'danger')
            else:
                admin.set_password(new)
                db.session.commit()
                log_activity(admin.id, 'password_change', 'Changed admin password')
                flash('Password updated.', 'success')
        return redirect(url_for('admin_profile'))
    stats = {
        'messages': Message.query.filter_by(sender_role='admin', sender_id=admin.id).count(),
        'notifications': Notification.query.filter_by(user_role='admin', user_id=admin.id).count(),
        'actions': ActivityLog.query.filter_by(user_role='admin', user_id=admin.id).count(),
    }
    recent = ActivityLog.query.filter_by(user_role='admin', user_id=admin.id)\
        .order_by(ActivityLog.created_at.desc()).limit(6).all()
    return render_template('admin/profile.html', admin=admin, stats=stats, recent=recent)

# ==================== PROFILE ROUTE ====================
@app.route('/user/profile', methods=['GET', 'POST'])
@login_required
def user_profile():
    user_id = session.get('user_id')
    user = current_account()
    if request.method == 'POST':
        full_name = request.form.get('full_name', '').strip()
        birth_date = request.form.get('birth_date', '')
        current_password = request.form.get('current_password', '')
        new_password = request.form.get('new_password', '')
        confirm_password = request.form.get('confirm_password', '')

        if not full_name:
            flash('Full name is required.', 'danger')
            return redirect(url_for('user_profile'))
        user.full_name = full_name
        user.phone = request.form.get('phone', '').strip()
        user.address = request.form.get('address', '').strip()
        user.city = request.form.get('city', '').strip()
        user.province = request.form.get('province', '').strip()
        user.postal_code = request.form.get('postal_code', '').strip()
        if birth_date:
            try:
                user.birth_date = datetime.strptime(birth_date, '%Y-%m-%d').date()
            except ValueError:
                flash('Invalid birth date format.', 'danger')
                return redirect(url_for('user_profile'))

        if new_password or confirm_password or current_password:
            if not current_password:
                flash('Current password is required to change password.', 'danger'); return redirect(url_for('user_profile'))
            if not user.check_password(current_password):
                flash('Current password is incorrect.', 'danger'); return redirect(url_for('user_profile'))
            if not new_password or not confirm_password:
                flash('New password and confirmation are required.', 'danger'); return redirect(url_for('user_profile'))
            problem = password_problem(new_password, confirm_password)
            if problem:
                flash(problem, 'danger'); return redirect(url_for('user_profile'))
            user.set_password(new_password)
            flash('Password updated successfully!', 'success')

        db.session.commit()
        create_notification(user_id, 'Profile Updated', 'Your profile information has been updated successfully.',
                            'success', email=False, role='customer')
        flash('Profile updated successfully!', 'success')
        log_activity(user_id, 'profile_update', 'Updated profile information')
        return redirect(url_for('user_profile'))
    return render_template('user/profile.html', user=user, notifications=_unread_notifs(user_id))

# ==================== API USER ROUTES ====================
@app.route('/api/user/activity-log')
@login_required
def api_user_activity_log():
    logs = ActivityLog.query.filter_by(user_role='customer', user_id=session.get('user_id'))\
        .order_by(ActivityLog.created_at.desc()).limit(50).all()
    return jsonify([{'action': l.action, 'details': l.details, 'ip_address': l.ip_address,
                     'created_at': l.created_at.strftime('%Y-%m-%d %H:%M:%S')} for l in logs])

@app.route('/api/user/download-data')
@login_required
def api_user_download_data():
    user = current_account()
    return jsonify({
        'user': user.to_dict(),
        'bookings': [{'booking_number': b.booking_number, 'service': b.service.name,
                      'device_type': b.device_type, 'status': b.status,
                      'booking_date': b.booking_date.strftime('%Y-%m-%d'),
                      'booking_time': b.booking_time.strftime('%H:%M'),
                      'created_at': b.created_at.strftime('%Y-%m-%d %H:%M:%S')} for b in user.bookings],
        'transactions': [{'transaction_number': t.transaction_number, 'amount': float(t.amount),
                          'payment_method': t.payment_method, 'payment_status': t.payment_status,
                          'transaction_date': t.transaction_date.strftime('%Y-%m-%d %H:%M:%S')}
                         for t in user.transactions]})

def _account_has_history(account):
    """True if business records reference this account, which means the row must
    be kept (anonymized) rather than deleted."""
    from models.technician_models import (ServiceReport, IncidentReport, ServiceRating,
                                          UploadedFile, ApprovalRequest)
    if account.role == 'customer':
        queries = [Booking.query.filter_by(customer_id=account.id),
                   Order.query.filter_by(customer_id=account.id),
                   Transaction.query.filter_by(customer_id=account.id),
                   SupportTicket.query.filter_by(customer_id=account.id),
                   ServiceRating.query.filter_by(customer_id=account.id)]
    elif account.role == 'technician':
        queries = [Booking.query.filter_by(technician_id=account.id),
                   ServiceReport.query.filter_by(technician_id=account.id),
                   IncidentReport.query.filter_by(technician_id=account.id),
                   ServiceRating.query.filter_by(technician_id=account.id),
                   UploadedFile.query.filter_by(technician_id=account.id),
                   ApprovalRequest.query.filter_by(technician_id=account.id)]
    else:
        queries = []
    return any(q.first() is not None for q in queries)

def _delete_account_private_rows(account):
    """Rows that only matter to this account. Does not commit."""
    Notification.query.filter_by(user_role=account.role, user_id=account.id).delete()
    ActivityLog.query.filter_by(user_role=account.role, user_id=account.id).delete()
    if account.role == 'customer':
        for cart in ShoppingCart.query.filter_by(customer_id=account.id).all():
            CartItem.query.filter_by(cart_id=cart.id).delete()
            db.session.delete(cart)
        UserPreference.query.filter_by(customer_id=account.id).delete()

def _delete_account_messages(account):
    """Messages to/from this account, with their attachment rows. Does not commit."""
    mine = Message.query.filter(or_(and_(Message.sender_role == account.role, Message.sender_id == account.id),
                                    and_(Message.recipient_role == account.role, Message.recipient_id == account.id)))
    ids = [m.id for m in mine.all()]
    if ids:
        MessageAttachment.query.filter(MessageAttachment.message_id.in_(ids)).delete(synchronize_session=False)
        Message.query.filter(Message.id.in_(ids)).delete(synchronize_session=False)

def _anonymize_account(account):
    """Strip personal data and lock the account, keeping the row so bookings,
    orders and payments that point at it stay intact. Does not commit."""
    _delete_account_private_rows(account)
    if hasattr(account, 'username'):
        account.username = f'deleted-{account.role}-{account.id}'
    account.email = f'deleted-{account.role}-{account.id}@deleted.invalid'
    account.full_name = 'Deleted user'
    columns = account.__table__.columns
    for field in ('phone', 'address', 'city', 'province', 'postal_code', 'latitude',
                  'longitude', 'birth_date', 'oauth_provider', 'oauth_id', 'id_type', 'id_number'):
        if field in columns:
            setattr(account, field, None)
    account.password_hash = bcrypt.generate_password_hash(secrets.token_urlsafe(32)).decode('utf-8')
    account.is_active = False

def close_account(account):
    """Delete the account, or anonymize it when the shop must keep its records.
    Returns 'account_deleted' or 'account_anonymized'. Commits."""
    if _account_has_history(account):
        _anonymize_account(account)
        action = 'account_anonymized'
    else:
        _delete_account_private_rows(account)
        _delete_account_messages(account)
        db.session.delete(account)
        action = 'account_deleted'
    db.session.commit()
    return action

@app.route('/api/user/delete-account', methods=['POST'])
@login_required
def api_user_delete_account():
    user = current_account()
    user_id = user.id
    active = Booking.query.filter(Booking.customer_id == user_id,
                                  Booking.status.in_(ACTIVE_STATUSES)).count()
    if active > 0:
        return jsonify({'success': False, 'message': 'Cannot delete account with active bookings. Please cancel all bookings first.'}), 400
    try:
        action = close_account(user)
    except Exception:
        db.session.rollback()
        app.logger.exception('Account deletion failed for customer %s', user_id)
        return jsonify({'success': False, 'message': 'Your account could not be deleted. Please contact support.'}), 500
    log_activity(None, action, f'Customer #{user_id} closed their account')
    session.clear()
    return jsonify({'success': True, 'message': 'Account deleted successfully.'})

@app.route('/api/user/update-preferences', methods=['POST'])
@login_required
def api_user_update_preferences():
    user_id = session.get('user_id')
    data = request.get_json(silent=True) or {}
    p = UserPreference.query.filter_by(user_id=user_id).first()
    if not p:
        p = UserPreference(user_id=user_id)
        db.session.add(p)
    p.language = data.get('language', 'en')
    p.theme = data.get('theme', 'light')
    p.email_notifications = data.get('email_notifications', True)
    p.sms_notifications = data.get('sms_notifications', False)
    p.booking_reminders = data.get('booking_reminders', True)
    db.session.commit()
    return jsonify({'success': True, 'message': 'Preferences updated successfully.'})
 
@app.route('/api/user/email-notifications', methods=['POST'])
@login_required
def api_user_email_notifications():
    """Turn notification emails on/off without touching other preferences.
    (Password-reset emails are always sent.)"""
    enabled = bool((request.get_json(silent=True) or {}).get('enabled'))
    p = UserPreference.query.filter_by(user_id=session['user_id']).first()
    if not p:
        p = UserPreference(user_id=session['user_id'])
        db.session.add(p)
    p.email_notifications = enabled
    db.session.commit()
    return jsonify({'success': True, 'enabled': enabled,
                    'message': 'Email notifications ' + ('on.' if enabled else 'off.')})

@app.route('/api/user/verify-email', methods=['POST'])
@login_required
def api_user_verify_email():
    # TODO: no mail backend is configured, so nothing is actually sent yet.
    return jsonify({'success': False, 'message': 'Email verification is not available yet.'}), 501
 
@app.route('/api/user/theme', methods=['POST'])
@login_required
def api_user_update_theme():
    user_id = session.get('user_id')
    theme = (request.get_json(silent=True) or {}).get('theme', 'light')
    if theme not in ['light', 'dark', 'system']:
        return jsonify({'success': False, 'message': 'Invalid theme'}), 400
    p = UserPreference.query.filter_by(user_id=user_id).first()
    if not p:
        p = UserPreference(user_id=user_id)
        db.session.add(p)
    p.theme = theme
    db.session.commit()
    return jsonify({'success': True, 'message': 'Theme updated successfully', 'theme': theme})
 
@app.route('/api/user/preferences', methods=['GET'])
@login_required
def api_user_get_preferences():
    p = UserPreference.query.filter_by(user_id=session.get('user_id')).first()
    if not p:
        return jsonify({'language': 'en', 'theme': 'light', 'email_notifications': True,
                        'sms_notifications': False, 'booking_reminders': True})
    return jsonify({'language': p.language, 'theme': p.theme, 'email_notifications': p.email_notifications,
                    'sms_notifications': p.sms_notifications, 'booking_reminders': p.booking_reminders})
# ==================== SHOP ROUTES ====================

@cache.cached(timeout=60, key_prefix='active_products')
def get_cached_active_products():
    """Product rows only have plain columns (no relationships), so it's
    safe to cache the ORM objects directly across requests - there's no
    lazy-loaded foreign key that could raise DetachedInstanceError once
    the request that fetched them has ended. Cutting this repeated,
    identical query (every shop page load, by every customer) down to
    once per minute is the single highest-value cache in the app."""
    return Product.query.filter_by(is_active=True).distinct().all()

@app.route('/user/shop')
@login_required
def user_shop():
    user = current_account()
    products = get_cached_active_products()
    notifications = _unread_notifs(session.get('user_id'))
    
    cart_count = 0
    try:
        cart = ShoppingCart.query.filter_by(user_id=session.get('user_id'), status='active').first()
        if cart:
            cart_count = CartItem.query.filter_by(cart_id=cart.id).count()
    except:
        pass
    
    return render_template('user/shop.html', products=products, cart_count=cart_count, notifications=notifications, user=user)

@app.route('/api/products')
@login_required
def api_products():
    category = request.args.get('category')
    search = request.args.get('search')
    sort = request.args.get('sort')
    
    query = Product.query.filter_by(is_active=True)
    
    if category and category != 'all':
        query = query.filter_by(category=category)
    
    if search:
        query = query.filter(
            or_(
                Product.name.ilike(f'%{search}%'),
                Product.description.ilike(f'%{search}%')
            )
        )
    
    if sort == 'price-low':
        query = query.order_by(Product.price.asc())
    elif sort == 'price-high':
        query = query.order_by(Product.price.desc())
    elif sort == 'newest':
        query = query.order_by(Product.created_at.desc())
    else:
        query = query.order_by(Product.name.asc())
    
    products = query.all()
    return jsonify([{
        'id': p.id,
        'name': p.name,
        'description': p.description,
        'price': float(p.price),
        'category': p.category,
        'stock_quantity': p.stock_quantity,
        'compatibility': p.compatibility,
        'image_url': p.image_url
    } for p in products])

@app.route('/api/product/<int:product_id>')
@login_required
def api_product_detail(product_id):
    product = Product.query.get_or_404(product_id)
    return jsonify({
        'id': product.id,
        'name': product.name,
        'description': product.description,
        'price': float(product.price),
        'category': product.category,
        'stock_quantity': product.stock_quantity,
        'compatibility': product.compatibility,
        'image_url': product.image_url,
        'is_active': product.is_active
    })

@app.route('/api/user/address', methods=['GET'])
@login_required
def api_get_user_address():
    """Return the delivery address currently saved on the user's account."""
    user = current_account()
    address = {
        'full_name': user.full_name or '',
        'phone': user.phone or '',
        'address': user.address or '',
        'city': user.city or '',
        'province': user.province or '',
        'postal_code': user.postal_code or '',
        'latitude': float(user.latitude) if user.latitude is not None else None,
        'longitude': float(user.longitude) if user.longitude is not None else None
    }
    has_address = bool(address['full_name'] and address['phone'] and address['address']
                        and address['city'] and address['province'] and address['postal_code'])
    return jsonify({'address': address, 'has_address': has_address})


@app.route('/api/user/address', methods=['POST'])
@login_required
def api_update_user_address():
    """Save/update the user's delivery address. Used by checkout when the
    account has no address on file yet, or when the user chooses to edit
    their existing address before placing an order."""
    user = current_account()
    data = request.get_json(silent=True) or {}

    full_name = (data.get('full_name') or '').strip()
    phone = (data.get('phone') or '').strip()
    address = (data.get('address') or '').strip()
    city = (data.get('city') or '').strip()
    province = (data.get('province') or '').strip()
    postal_code = (data.get('postal_code') or '').strip()

    # Optional map pin dropped by the user (from the Leaflet location picker).
    latitude = data.get('latitude')
    longitude = data.get('longitude')
    try:
        latitude = float(latitude) if latitude not in (None, '') else None
        longitude = float(longitude) if longitude not in (None, '') else None
    except (TypeError, ValueError):
        latitude = None
        longitude = None

    missing = [label for label, value in [
        ('full name', full_name), ('phone number', phone), ('street address', address),
        ('city', city), ('province', province), ('postal code', postal_code)
    ] if not value]
    if missing:
        return jsonify({'success': False, 'message': f"Please fill in: {', '.join(missing)}."}), 400

    user.full_name = full_name
    user.phone = phone
    user.address = address
    user.city = city
    user.province = province
    user.postal_code = postal_code
    if latitude is not None and longitude is not None:
        user.latitude = latitude
        user.longitude = longitude
    db.session.commit()

    log_activity(user.id, 'address_update', 'Updated delivery address during checkout')

    return jsonify({
        'success': True,
        'message': 'Delivery address saved.',
        'address': {
            'full_name': user.full_name,
            'phone': user.phone,
            'address': user.address,
            'city': user.city,
            'province': user.province,
            'postal_code': user.postal_code,
            'latitude': float(user.latitude) if user.latitude is not None else None,
            'longitude': float(user.longitude) if user.longitude is not None else None
        }
    })


@app.route('/api/cart', methods=['GET'])
@login_required
def api_get_cart():
    user_id = session.get('user_id')
    cart = ShoppingCart.query.filter_by(user_id=user_id, status='active').first()
    
    if not cart:
        return jsonify({'items': [], 'total': 0, 'count': 0})
    
    items = []
    total = 0
    
    cart_items = CartItem.query.filter_by(cart_id=cart.id).all()
    
    for item in cart_items:
        product = Product.query.get(item.product_id)
        if product and product.is_active:
            price = float(item.price if item.price else product.price)
            subtotal = price * item.quantity
            total += subtotal
            items.append({
                'id': item.id,
                'product_id': item.product_id,
                'product_name': product.name,
                'quantity': item.quantity,
                'price': price,
                'subtotal': subtotal
            })
    
    return jsonify({
        'items': items,
        'total': total,
        'count': len(items)
    })

MAX_CART_QUANTITY = 99

def _parse_quantity(value, minimum=1):
    """Whole number between `minimum` and MAX_CART_QUANTITY, else None.
    Rejects bools, floats, strings like '2.5', and negative numbers."""
    if isinstance(value, bool):
        return None
    if isinstance(value, str) and value.strip().isdigit():
        value = int(value.strip())
    if not isinstance(value, int) or not minimum <= value <= MAX_CART_QUANTITY:
        return None
    return value

def _owned_cart_item(item_id):
    """The cart item if it belongs to the signed-in user's cart, else None."""
    cart_item = CartItem.query.get(item_id) if item_id else None
    if not cart_item:
        return None
    cart = ShoppingCart.query.get(cart_item.cart_id)
    if not cart or cart.user_id != session.get('user_id'):
        return None
    return cart_item

# Stock is NOT reserved while items sit in a cart. Adding or updating only
# checks availability; api_cart_checkout() locks the product rows, checks
# again, and deducts stock in the same transaction that creates the order.
@app.route('/api/cart/add', methods=['POST'])
@login_required
def api_cart_add():
    data = request.get_json(silent=True) or {}
    product_id = data.get('product_id')
    quantity = _parse_quantity(data.get('quantity', 1))

    if not product_id:
        return jsonify({'success': False, 'message': 'Product ID required'}), 400
    if quantity is None:
        return jsonify({'success': False, 'message': f'Quantity must be a whole number from 1 to {MAX_CART_QUANTITY}.'}), 400

    product = Product.query.get(product_id)
    if not product or not product.is_active:
        return jsonify({'success': False, 'message': 'Product not found'}), 404

    user_id = session.get('user_id')
    cart = ShoppingCart.query.filter_by(user_id=user_id, status='active').first()
    if not cart:
        cart = ShoppingCart(user_id=user_id, status='active')
        db.session.add(cart)
        db.session.flush()

    cart_item = CartItem.query.filter_by(cart_id=cart.id, product_id=product.id).first()
    in_cart = cart_item.quantity if cart_item else 0
    if in_cart + quantity > product.stock_quantity:
        available = max(product.stock_quantity - in_cart, 0)
        return jsonify({'success': False, 'message': f'Not enough stock. Only {available} more available.'}), 400
    if in_cart + quantity > MAX_CART_QUANTITY:
        return jsonify({'success': False, 'message': f'You can order at most {MAX_CART_QUANTITY} of one item.'}), 400

    if cart_item:
        cart_item.quantity += quantity
        cart_item.price = product.price
    else:
        db.session.add(CartItem(cart_id=cart.id, product_id=product.id,
                                quantity=quantity, price=product.price))
    db.session.commit()

    cart_count = CartItem.query.filter_by(cart_id=cart.id).count()
    return jsonify({
        'success': True,
        'message': f'{product.name} added to cart',
        'cart_count': cart_count
    })

@app.route('/api/cart/update', methods=['POST'])
@login_required
def api_cart_update():
    data = request.get_json(silent=True) or {}
    quantity = _parse_quantity(data.get('quantity'), minimum=0)
    if quantity is None:
        return jsonify({'success': False, 'message': f'Quantity must be a whole number from 0 to {MAX_CART_QUANTITY}.'}), 400

    cart_item = _owned_cart_item(data.get('item_id'))
    if not cart_item:
        return jsonify({'success': False, 'message': 'Item not found'}), 404

    if quantity == 0:
        db.session.delete(cart_item)
        db.session.commit()
        return jsonify({'success': True, 'message': 'Item removed from cart'})

    product = Product.query.get(cart_item.product_id)
    if not product or not product.is_active:
        return jsonify({'success': False, 'message': 'Product not found'}), 404
    if quantity > product.stock_quantity:
        return jsonify({'success': False, 'message': f'Insufficient stock. Only {product.stock_quantity} available.'}), 400

    cart_item.quantity = quantity
    db.session.commit()
    return jsonify({'success': True, 'message': 'Cart updated'})

@app.route('/api/cart/remove/<int:item_id>', methods=['DELETE'])
@login_required
def api_cart_remove(item_id):
    cart_item = _owned_cart_item(item_id)
    if not cart_item:
        return jsonify({'success': False, 'message': 'Item not found'}), 404
    db.session.delete(cart_item)
    db.session.commit()
    return jsonify({'success': True, 'message': 'Item removed from cart'})

@app.route('/api/cart/clear', methods=['POST'])
@login_required
def api_cart_clear():
    cart = ShoppingCart.query.filter_by(user_id=session.get('user_id'), status='active').first()
    if cart:
        CartItem.query.filter_by(cart_id=cart.id).delete()
        db.session.commit()
    return jsonify({'success': True, 'message': 'Cart cleared'})

@app.route('/api/cart/checkout', methods=['POST'])
@login_required
def api_cart_checkout():
    user_id = session.get('user_id')
    user = db.session.get(Customer, user_id)
    data = request.get_json(silent=True) or {}

    payment_method = (data.get('payment_method') or '').strip().lower()
    gcash_reference = (data.get('gcash_reference') or '').strip()

    if payment_method not in ('cod', 'gcash'):
        return jsonify({'success': False, 'message': 'Please select a valid payment method.'}), 400

    if payment_method == 'gcash' and not gcash_reference:
        return jsonify({'success': False, 'message': 'Please enter your GCash reference number.'}), 400

    # The delivery address lives on the user's account (single saved address
    # per user, same as the profile page). It must be complete before an
    # order can be placed - checked here server-side since the client-side
    # checkout state can't be trusted on its own.
    if not (user.full_name and user.phone and user.address and user.city and user.province and user.postal_code):
        return jsonify({
            'success': False,
            'error': 'address_required',
            'message': 'Please add a complete delivery address before placing your order.'
        }), 400

    # Full formatted line, kept for backward compatibility with anything
    # that reads order.shipping_address directly.
    shipping_address = ', '.join(filter(None, [
        user.address, user.city, user.province, user.postal_code
    ]))

    # Lock the cart row: a second checkout sent at the same moment (double click,
    # two tabs) waits here, then finds the cart already completed.
    cart = ShoppingCart.query.filter_by(user_id=user_id, status='active').with_for_update().first()

    if not cart:
        db.session.rollback()
        recent = Order.query.filter(Order.customer_id == user_id,
                                    Order.created_at >= datetime.utcnow() - timedelta(minutes=2))\
            .order_by(Order.id.desc()).first()
        if recent:
            return jsonify({'success': True, 'message': 'Your order was already placed.',
                            'order_number': recent.order_number, 'total': float(recent.total_amount),
                            'duplicate': True})
        return jsonify({'success': False, 'message': 'Cart is empty'}), 400

    cart_items = CartItem.query.filter_by(cart_id=cart.id).all()
    if not cart_items:
        return jsonify({'success': False, 'message': 'Cart is empty'}), 400
    
    # Lock the product rows so two checkouts can't both take the last unit,
    # then check stock and price against the current product, not the cart.
    products = {}
    for item in cart_items:
        product = Product.query.filter_by(id=item.product_id).with_for_update().first()
        if not product or not product.is_active:
            db.session.rollback()
            return jsonify({'success': False,
                            'message': 'An item in your cart is no longer available. Please remove it and try again.'}), 400
        if item.quantity < 1 or product.stock_quantity < item.quantity:
            db.session.rollback()
            return jsonify({'success': False,
                            'message': f'Insufficient stock for {product.name}. Only {max(product.stock_quantity, 0)} available.'}), 400
        products[item.id] = product

    total_amount = sum(item.quantity * products[item.id].price for item in cart_items)
    
    order = Order(
        user_id=user_id,
        # order_number is filled in below, after flush(), using the row's
        # real auto-increment id. Generating it from a COUNT(*) query (the
        # previous approach) is a race condition: two checkouts happening
        # at the same time can read the same count and collide on the
        # unique constraint. The id is guaranteed unique by the database.
        order_number='PENDING',
        total_amount=total_amount,
        status='pending',
        shipping_address=shipping_address or None,
        # Snapshot of the delivery address exactly as it was when this
        # order was placed - independent of any later profile edits.
        recipient_name=user.full_name,
        recipient_phone=user.phone,
        address_line=user.address,
        city=user.city,
        province=user.province,
        postal_code=user.postal_code,
        latitude=user.latitude,
        longitude=user.longitude,
        payment_method=payment_method,
        # COD is only confirmed as paid once the order is delivered; GCash
        # payments sit as pending until an admin verifies the reference
        # number, same as the existing booking payment flow.
        payment_status='pending'
    )
    db.session.add(order)
    db.session.flush()
    order.order_number = f"ORD{datetime.utcnow().strftime('%y%m%d')}{order.id:04d}"
    
    for item in cart_items:
        product = products[item.id]
        db.session.add(OrderItem(
            order_id=order.id,
            product_id=product.id,
            quantity=item.quantity,
            price=product.price
        ))
        product.stock_quantity -= item.quantity
        db.session.delete(item)
    
    cart.status = 'completed'

    transaction = Transaction(
        transaction_number=placeholder_number(),
        order_id=order.id,
        user_id=user_id,
        amount=total_amount,
        payment_method=payment_method,
        payment_status='pending',
        gcash_reference=gcash_reference if payment_method == 'gcash' else None
    )
    db.session.add(transaction)
    db.session.flush()
    assign_transaction_number(transaction)

    db.session.commit()
    cache.delete('active_products')  # stock just changed

    if payment_method == 'gcash':
        notif_message = (
            f'Your order #{order.order_number} (₱{total_amount:.2f}) has been placed and is '
            f'awaiting GCash payment confirmation from our team.'
        )
    else:
        notif_message = (
            f'Your order #{order.order_number} (₱{total_amount:.2f}) has been placed. '
            f'Pay in cash when your order is delivered.'
        )
    create_notification(user_id, 'Order Placed', notif_message, 'success', role='customer')
    
    return jsonify({
        'success': True,
        'message': 'Order placed successfully!',
        'order_number': order.order_number,
        'total': float(total_amount)
    })
# Add this to app.py - Order Cancellation with Stock Restoration

@app.route('/user/orders')
@login_required
def user_orders():
    """View all orders for the current user"""
    user_id = session.get('user_id')
    user = db.session.get(Customer, user_id)
    status_filter = request.args.get('status', 'all')

    base_query = Order.query.filter_by(user_id=user_id)
    all_orders = base_query.order_by(Order.created_at.desc()).all()

    status_counts = {
        'all': len(all_orders),
        'pending': sum(1 for o in all_orders if o.status == 'pending'),
        'processing': sum(1 for o in all_orders if o.status == 'processing'),
        'completed': sum(1 for o in all_orders if o.status == 'completed'),
        'cancelled': sum(1 for o in all_orders if o.status == 'cancelled'),
    }

    if status_filter != 'all':
        orders = [o for o in all_orders if o.status == status_filter]
    else:
        orders = all_orders

    notifications = _unread_notifs(user_id)
    return render_template(
        'user/orders.html',
        orders=orders,
        status_filter=status_filter,
        status_counts=status_counts,
        notifications=notifications,
        user=user
    )

def _cancel_order(order, cancelled_by='system'):
    """Cancel an order: restore its stock, close unpaid payments, and open a refund
    for any payment that was confirmed or that the customer sent proof for.
    Commits. Returns the refunds it opened. Callers check whether the order may
    be cancelled first."""
    for item in order.items:
        product = Product.query.get(item.product_id)
        if product:
            product.stock_quantity += item.quantity
    now = datetime.utcnow()
    order.status = 'cancelled'
    order.updated_at = now
    to_refund = []
    for txn in order.transactions:
        if txn.payment_status == 'confirmed':
            to_refund.append(txn)
        elif txn.payment_status in ('pending', 'rejected'):
            if txn.receipt_image or txn.gcash_reference or txn.reference_number:
                to_refund.append(txn)               # customer says they paid
            txn.payment_status = 'cancelled'
            txn.updated_at = now
    if order.payment_status != 'confirmed':
        order.payment_status = 'cancelled'
    opened = []
    for txn in to_refund:
        why = (f'Order {order.order_number} cancelled after the payment was confirmed.'
               if txn.payment_status == 'confirmed' else
               f'Order {order.order_number} cancelled after the customer sent a GCash reference. '
               f'Check the money arrived before refunding.')
        refund, created = open_refund(txn, why, created_by=cancelled_by, order=order)
        if created:
            opened.append(refund)
    db.session.commit()
    cache.delete('active_products')
    if opened:
        notify_admins('Refund to process',
                      f'Order {order.order_number} was cancelled with a paid or possibly paid charge. See Refunds.',
                      'warning')
    return opened

@app.route('/api/order/<int:order_id>/cancel', methods=['POST'])
@login_required
def api_order_cancel(order_id):
    """Cancel an order and restore stock"""
    user_id = session.get('user_id')
    order = Order.query.get_or_404(order_id)
    
    # Check if order belongs to user
    if order.user_id != user_id:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403
    
    # Check if order can be cancelled
    if order.status in ['completed', 'cancelled']:
        return jsonify({'success': False, 'message': 'This order cannot be cancelled'}), 400

    # A paid order can be cancelled by the customer only before it is being
    # prepared; the payment then goes to Refunds. Later, they contact support.
    if order.payment_status == 'confirmed' and order.status != 'pending':
        return jsonify({
            'success': False,
            'message': 'This paid order is already being prepared. Please contact support to cancel it.'
        }), 400

    refunds = _cancel_order(order, cancelled_by=f'customer #{user_id}')
    msg = f'Your order #{order.order_number} has been cancelled.'
    if refunds:
        msg += ' A refund has been opened; you can follow it on your Transactions page.'
    create_notification(user_id, 'Order Cancelled', msg, 'warning', role='customer')
    return jsonify({'success': True, 'message': msg, 'refund_opened': bool(refunds)})

@app.route('/api/order/<int:order_id>', methods=['GET'])
@login_required
def api_order_detail(order_id):
    """Get order details"""
    user_id = session.get('user_id')
    order = Order.query.get_or_404(order_id)
    
    if order.user_id != user_id:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403
    
    has_pin = order.latitude is not None and order.longitude is not None

    return jsonify({
        'id': order.id,
        'order_number': order.order_number,
        'total_amount': float(order.total_amount),
        'status': order.status,
        'can_cancel': order.status in ('pending', 'processing') and not (
            order.payment_method == 'gcash' and order.payment_status == 'confirmed'
        ),
        # Legacy single-line string, still returned for compatibility.
        'shipping_address': order.shipping_address,
        # Structured address snapshot captured at checkout time.
        'address': {
            'recipient_name': order.recipient_name,
            'recipient_phone': order.recipient_phone,
            'address_line': order.address_line,
            'city': order.city,
            'province': order.province,
            'postal_code': order.postal_code,
            'latitude': float(order.latitude) if order.latitude is not None else None,
            'longitude': float(order.longitude) if order.longitude is not None else None,
            'has_pin': has_pin,
            'map_url': f'https://www.google.com/maps?q={order.latitude},{order.longitude}' if has_pin else None,
        },
        'payment_method': order.payment_method,
        'payment_status': order.payment_status,
        'created_at': order.created_at.strftime('%Y-%m-%d %H:%M:%S'),
        'items': [{
            'product_name': item.product.name,
            'quantity': item.quantity,
            'price': float(item.price),
            'subtotal': float(item.price * item.quantity)
        } for item in order.items]
    })
# ==================== TROUBLESHOOTING ROUTE ====================

@app.route('/user/troubleshooting')
@login_required
def user_troubleshooting():
    notifications = _unread_notifs(session.get('user_id'))
    return render_template('user/troubleshooting.html', notifications=notifications)

# ==================== ADMIN ROUTES ====================

@cache.cached(timeout=30, key_prefix='admin_dashboard_stats')
def get_cached_dashboard_stats():
    """Every count and trend below is a plain number - safe to cache, unlike
    the recent_* lists further down which carry SQLAlchemy relationships
    (booking.user, booking.service) that would raise DetachedInstanceError
    if reused across requests. The admin panel's own auto-refresh polls
    this route every 45 seconds from every open tab; without this cache,
    each poll re-runs 7 separate aggregate queries against the database
    for no new information 29 times out of 30."""
    total_users = Customer.query.count()
    total_technicians = Technician.query.count()
    total_bookings = Booking.query.count()
    pending_bookings = Booking.query.filter_by(status='pending').count()
    total_transactions = Transaction.query.count()
    pending_payments = Transaction.query.filter_by(payment_status='pending').count()
    total_revenue = db.session.query(db.func.sum(Transaction.amount)).filter_by(payment_status='confirmed').scalar() or 0

    users_trend = calculate_trend(Customer, Customer.created_at)
    requests_trend = calculate_trend(Booking, Booking.created_at, Booking.status == 'pending')
    payments_trend = calculate_trend(Transaction, Transaction.transaction_date, Transaction.payment_status == 'pending')
    services_trend = calculate_trend(Booking, Booking.created_at)

    return {
        'total_users': total_users,
        'total_technicians': total_technicians,
        'total_bookings': total_bookings,
        'pending_bookings': pending_bookings,
        'total_transactions': total_transactions,
        'pending_payments': pending_payments,
        'total_revenue': total_revenue,
        'users_trend': users_trend,
        'requests_trend': requests_trend,
        'payments_trend': payments_trend,
        'services_trend': services_trend,
    }

@app.route('/admin/dashboard')
@admin_required
def admin_dashboard():
    stats = get_cached_dashboard_stats()
    from models.technician_models import IncidentReport
    open_incidents = IncidentReport.query.filter_by(status='open').count()

    recent_bookings = Booking.query.order_by(Booking.created_at.desc()).limit(5).all()
    recent_users = all_accounts()[:5]
    recent_activities = ActivityLog.query.order_by(ActivityLog.created_at.desc()).limit(10).all()
    recent_pending_payments = Transaction.query.filter_by(payment_status='pending').order_by(Transaction.transaction_date.desc()).limit(3).all()

    return render_template('admin/admin_dashboard.html',
                         total_users=stats['total_users'],
                         total_technicians=stats['total_technicians'],
                         total_bookings=stats['total_bookings'],
                         pending_bookings=stats['pending_bookings'],
                         total_transactions=stats['total_transactions'],
                         pending_payments=stats['pending_payments'],
                         open_incidents=open_incidents,
                         total_revenue=stats['total_revenue'],
                         recent_bookings=recent_bookings,
                         recent_users=recent_users,
                         recent_activities=recent_activities,
                         recent_pending_payments=recent_pending_payments,
                         users_trend=stats['users_trend'],
                         requests_trend=stats['requests_trend'],
                         payments_trend=stats['payments_trend'],
                         services_trend=stats['services_trend'])

def build_admin_user_summary(user):
    """Row-level shape for the User Management table - list view + live polling.
    `key` ('customer-5') identifies the account; `id` alone repeats across tables."""
    presence = get_user_presence(user)
    return {
        'key': user.key,
        'id': user.id,
        'full_name': user.full_name,
        'email': user.email,
        'phone': user.phone,
        'role': user.role,
        'username': getattr(user, 'username', None),
        'is_active': user.is_active,
        'id_verified': user.id_verified if user.role == 'technician' else None,
        'created_at': user.created_at.strftime('%Y-%m-%d') if user.created_at else None,
        **presence
    }

def build_admin_user_detail(user):
    """Full-detail shape for the eye-icon modal: profile + presence + activity stats."""
    presence = get_user_presence(user)
    stats, recent_orders, recent_bookings = {}, [], []
    if user.role == 'customer':
        total_spent = db.session.query(db.func.sum(Transaction.amount)).filter_by(
            customer_id=user.id, payment_status='confirmed').scalar() or 0
        stats = {'orders_count': Order.query.filter_by(customer_id=user.id).count(),
                 'bookings_count': Booking.query.filter_by(customer_id=user.id).count(),
                 'total_spent': float(total_spent)}
        recent_orders = Order.query.filter_by(customer_id=user.id).order_by(Order.created_at.desc()).limit(5).all()
        recent_bookings = Booking.query.filter_by(customer_id=user.id).order_by(Booking.created_at.desc()).limit(5).all()
    elif user.role == 'technician':
        from models.technician_models import technician_rating
        rating, rating_count = technician_rating(user.id)
        stats = {'orders_count': 0,
                 'bookings_count': Booking.query.filter_by(technician_id=user.id).count(),
                 'jobs_finished': Booking.query.filter(Booking.technician_id == user.id,
                                                       Booking.status.in_(FINISHED_STATUSES)).count(),
                 'rating': rating, 'rating_count': rating_count, 'total_spent': 0.0}
        recent_bookings = Booking.query.filter_by(technician_id=user.id).order_by(Booking.created_at.desc()).limit(5).all()
    else:
        stats = {'orders_count': 0, 'bookings_count': 0, 'total_spent': 0.0}

    return {
        'key': user.key,
        'id': user.id,
        'username': getattr(user, 'username', None),
        'full_name': user.full_name,
        'email': user.email,
        'phone': user.phone,
        'address': getattr(user, 'address', None),
        'city': getattr(user, 'city', None),
        'province': getattr(user, 'province', None),
        'postal_code': getattr(user, 'postal_code', None),
        'birth_date': user.birth_date.strftime('%Y-%m-%d') if getattr(user, 'birth_date', None) else None,
        'role': user.role,
        'is_active': user.is_active,
        'id_type': user.id_type if user.role == 'technician' else None,
        'id_verified': user.id_verified if user.role == 'technician' else None,
        'id_verified_at': user.id_verified_at.strftime('%Y-%m-%d %H:%M:%S')
                          if user.role == 'technician' and user.id_verified_at else None,
        'created_at': user.created_at.strftime('%Y-%m-%d %H:%M:%S') if user.created_at else None,
        'updated_at': user.updated_at.strftime('%Y-%m-%d %H:%M:%S') if user.updated_at else None,
        **presence,
        'stats': stats,
        'recent_orders': [{
            'order_number': o.order_number,
            'total_amount': float(o.total_amount),
            'status': o.status,
            'created_at': o.created_at.strftime('%Y-%m-%d %H:%M')
        } for o in recent_orders],
        'recent_bookings': [{
            'booking_number': b.booking_number,
            'device_type': b.device_type,
            'status': b.status,
            'booking_date': b.booking_date.strftime('%Y-%m-%d') if b.booking_date else None
        } for b in recent_bookings]
    }

def _admin_target(role, user_id):
    """The account an admin action targets, or a 404."""
    account = get_account(role, user_id)
    if not account:
        abort(404)
    return account

def _is_me(account):
    return session.get('role') == account.role and session.get('user_id') == account.id

def _next_tech_id():
    nums = [int(t.username[5:]) for t in Technician.query.filter(Technician.username.like('TECH-%')).all()
            if t.username[5:].isdigit()]
    return f"TECH-{(max(nums) + 1 if nums else 1):04d}"

@app.route('/admin/users')
@admin_required
def admin_users():
    users = all_accounts()
    users_json = [build_admin_user_summary(u) for u in users]
    return render_template('admin/users_management.html', users=users, users_json=users_json,
                           current_admin_key=f"admin-{session.get('user_id')}")

@app.route('/api/admin/users')
@limiter.exempt
@admin_required
def api_admin_users():
    """Polled by the User Management page to refresh online status and
    'time ago' text without a page reload."""
    return jsonify({'users': [build_admin_user_summary(u) for u in all_accounts()]})

@app.route('/api/admin/users/<role>/<int:user_id>')
@admin_required
def api_admin_user_detail(role, user_id):
    return jsonify({'user': build_admin_user_detail(_admin_target(role, user_id))})

@app.route('/api/admin/users', methods=['POST'])
@admin_required
def api_admin_create_user():
    data = request.get_json(silent=True) or {}
    username = (data.get('username') or '').strip()
    email = (data.get('email') or '').strip().lower()
    password = data.get('password') or ''
    full_name = (data.get('full_name') or '').strip()
    phone = (data.get('phone') or '').strip()
    role = (data.get('role') or 'customer').strip()

    if role not in ACCOUNT_MODELS:
        return jsonify({'success': False, 'message': 'Invalid role.'}), 400
    model = ACCOUNT_MODELS[role]
    if role == 'technician':
        username = _next_tech_id()
    elif not username:
        username = email.split('@')[0] if email else ''

    missing = [label for label, value in [
        ('username', username), ('email', email), ('password', password), ('full name', full_name)
    ] if not value]
    if missing:
        return jsonify({'success': False, 'message': f"Please fill in: {', '.join(missing)}."}), 400

    if len(password) < 6:
        return jsonify({'success': False, 'message': 'Password must be at least 6 characters.'}), 400

    if model.query.filter_by(username=username).first():
        return jsonify({'success': False, 'message': 'That username is already taken.'}), 400

    if email_in_use(email):
        return jsonify({'success': False, 'message': 'That email is already registered.'}), 400

    user = model(username=username, email=email, full_name=full_name, phone=phone or None, is_active=True)
    user.set_password(password)
    db.session.add(user)
    db.session.commit()

    log_activity(session.get('user_id'), 'user_create', f'Created {role} account: {full_name} ({email})')

    return jsonify({'success': True, 'message': f'{full_name} was added.', 'user': build_admin_user_summary(user)})

@app.route('/api/admin/users/<role>/<int:user_id>/verify-id', methods=['POST'])
@admin_required
def api_admin_verify_technician_id(role, user_id):
    """Records identity-verification for a technician account. The ID
    number is stored so the shop has a real audit record on file (the
    same way any employer keeps a copy of a hired worker's ID), but it is
    never returned by any other endpoint in this app - only this route
    accepts it, and no GET endpoint anywhere serializes id_number back
    out. Every other view of a technician only ever sees the boolean
    id_verified flag."""
    user = _admin_target(role, user_id)
    if user.role != 'technician':
        return jsonify({'success': False, 'message': 'Identity verification only applies to technician accounts.'}), 400

    data = request.get_json(silent=True) or {}
    id_type = (data.get('id_type') or '').strip()
    id_number = (data.get('id_number') or '').strip()

    if not id_type or not id_number:
        return jsonify({'success': False, 'message': 'Please provide both an ID type and ID number.'}), 400
    if not re.fullmatch(r'[A-Za-z0-9\- ]{4,50}', id_number):
        return jsonify({'success': False, 'message': 'ID number looks invalid - letters, numbers, spaces, and dashes only.'}), 400

    user.id_type = id_type
    user.id_number = id_number
    user.id_verified = True
    user.id_verified_at = datetime.utcnow()
    db.session.commit()

    log_activity(session.get('user_id'), 'technician_verify', f'Verified identity for technician: {user.full_name} ({id_type})')
    create_notification(
        user.id,
        'Identity Verified',
        'Your identity document has been verified by an administrator. You can now be assigned to service bookings.',
        'success', role='technician'
    )

    return jsonify({'success': True, 'message': f"{user.full_name}'s identity has been verified."})

@app.route('/api/admin/users/<role>/<int:user_id>/verify-id', methods=['DELETE'])
@admin_required
def api_admin_revoke_technician_verification(role, user_id):
    """Lets an admin revoke a verification (e.g. an ID turned out to be
    fraudulent, or expired) without deleting the account outright."""
    user = _admin_target(role, user_id)
    if user.role != 'technician':
        return jsonify({'success': False, 'message': 'Only technicians have ID verification.'}), 400
    user.id_verified = False
    db.session.commit()
    log_activity(session.get('user_id'), 'technician_verify_revoke', f'Revoked identity verification for: {user.full_name}')
    return jsonify({'success': True, 'message': f"{user.full_name}'s verification has been revoked."})

ROLE_CHANGE_MESSAGE = ("Customers, technicians and admins are separate accounts, so an account's type "
                       "can't be changed. Create a new account of the other type instead.")

@app.route('/api/admin/users/<role>/<int:user_id>', methods=['PUT'])
@admin_required
def api_admin_update_user(role, user_id):
    user = _admin_target(role, user_id)
    data = request.get_json(silent=True) or {}

    full_name = (data.get('full_name') or '').strip()
    email = (data.get('email') or '').strip().lower()
    phone = (data.get('phone') or '').strip()
    address = (data.get('address') or '').strip()
    city = (data.get('city') or '').strip()
    province = (data.get('province') or '').strip()
    postal_code = (data.get('postal_code') or '').strip()
    new_role = (data.get('role') or user.role).strip()

    if not full_name or not email:
        return jsonify({'success': False, 'message': 'Full name and email are required.'}), 400
    if new_role != user.role:
        return jsonify({'success': False, 'message': ROLE_CHANGE_MESSAGE}), 400
    if email_in_use(email, exclude=user):
        return jsonify({'success': False, 'message': 'That email is already used by another account.'}), 400

    user.full_name = full_name
    user.email = email
    user.phone = phone or None
    columns = user.__table__.columns
    for field, value in (('address', address), ('city', city), ('province', province), ('postal_code', postal_code)):
        if field in columns:
            setattr(user, field, value or None)
    db.session.commit()

    log_activity(session.get('user_id'), 'user_update', f'Updated {user.role} account: {user.full_name} ({user.key})')

    return jsonify({'success': True, 'message': 'User updated.', 'user': build_admin_user_summary(user)})

@app.route('/api/admin/users/<role>/<int:user_id>/reset-password', methods=['POST'])
@admin_required
def api_admin_reset_password(role, user_id):
    """Give a user a one-time temporary password (shown to the admin once).
    Used when a customer contacts the shop because they forgot theirs."""
    user = _admin_target(role, user_id)
    if _is_me(user):
        return jsonify({'success': False, 'message': 'Change your own password from your profile.'}), 400
    temp = 'Temp-' + secrets.token_urlsafe(8)
    user.set_password(temp)
    db.session.commit()
    log_activity(session.get('user_id'), 'password_reset', f'Reset password for {user.full_name} ({user.key})')
    create_notification(user.id, 'Password Reset',
                        'An administrator reset your password. Sign in with the temporary password '
                        'they gave you, then change it in your profile.', 'warning', role=user.role)
    return jsonify({'success': True, 'temporary_password': temp,
                    'message': f"Temporary password created for {user.full_name}."})

@app.route('/api/admin/users/<role>/<int:user_id>/status', methods=['POST'])
@admin_required
def api_admin_toggle_user_status(role, user_id):
    user = _admin_target(role, user_id)
    if _is_me(user):
        return jsonify({'success': False, 'message': "You can't deactivate your own account while logged in."}), 400

    data = request.get_json(silent=True) or {}

    if user.role == 'admin' and user.is_active and Admin.query.filter_by(is_active=True).count() <= 1:
        return jsonify({'success': False, 'message': 'Cannot deactivate the last active admin account.'}), 400

    if 'is_active' in data:
        user.is_active = bool(data['is_active'])
    else:
        user.is_active = not user.is_active
    db.session.commit()

    log_activity(session.get('user_id'), 'user_status_change',
                 f'{"Activated" if user.is_active else "Deactivated"} {user.role}: {user.full_name} ({user.key})')

    return jsonify({'success': True, 'is_active': user.is_active})

@app.route('/api/admin/users/<role>/<int:user_id>/role', methods=['POST'])
@admin_required
def api_admin_update_role(role, user_id):
    """Account types are separate tables now; a role can't be changed in place."""
    _admin_target(role, user_id)
    return jsonify({'success': False, 'message': ROLE_CHANGE_MESSAGE}), 400

@app.route('/api/admin/users/<role>/<int:user_id>', methods=['DELETE'])
@admin_required
def api_admin_delete_user(role, user_id):
    user = _admin_target(role, user_id)
    if _is_me(user):
        return jsonify({'success': False, 'message': "You can't delete your own account while logged in."}), 400

    if user.role == 'admin' and Admin.query.count() <= 1:
        return jsonify({'success': False, 'message': 'Cannot delete the last remaining admin account.'}), 400

    if _account_has_history(user):
        return jsonify({
            'success': False,
            'message': 'This account has bookings, orders, jobs or payments on record and cannot be deleted. '
                       'Deactivate the account instead to preserve that history.'
        }), 400

    try:
        full_name, key = user.full_name, user.key
        _delete_account_private_rows(user)
        _delete_account_messages(user)
        db.session.delete(user)
        db.session.commit()

        log_activity(session.get('user_id'), 'user_delete', f'Deleted account: {full_name} ({key})')

        return jsonify({'success': True, 'message': f'{full_name} has been deleted.'})
    except Exception:
        db.session.rollback()
        app.logger.exception('Deleting %s-%s failed', role, user_id)
        return jsonify({'success': False, 'message': 'Could not delete user due to a database error.'}), 500

@app.route('/api/booking/<int:booking_id>')
@login_required
def api_booking_detail(booking_id):
    """Customer-facing booking detail - powers the 'View Details' button on
    the various booking-status pages (pending/in-progress/completed/etc).
    Ownership is checked below so one customer can never view another's
    booking just by guessing an ID."""
    booking = Booking.query.get_or_404(booking_id)
    if booking.user_id != session.get('user_id'):
        return jsonify({'success': False, 'message': 'Not authorized to view this booking.'}), 403

    service = booking.service
    txn = booking.transaction
    tech = booking.technician
    status_note = None
    if booking.status == 'cancelled':
        from models.technician_models import JobLog
        last = JobLog.query.filter_by(booking_id=booking.id, action='status')\
            .order_by(JobLog.id.desc()).first()
        status_note = last.text if last else None

    return jsonify({
        'id': booking.id,
        'booking_number': booking.booking_number,
        'status': booking.status,
        'status_note': status_note,
        'device_type': booking.device_type,
        'description': booking.description,
        'address': booking.address,
        'is_in_shop': booking.is_in_shop,
        'booking_date': booking.booking_date.strftime('%b %d, %Y') if booking.booking_date else None,
        'booking_time': booking.booking_time.strftime('%I:%M %p') if booking.booking_time else None,
        'service': {
            'name': service.name if service else 'N/A',
            'price': float(service.price) if service else 0,
        },
        'technician': {
            'full_name': tech.full_name,
            'phone': tech.phone,
            # Customers see ONLY a verified/unverified badge - never the ID
            # type or the ID number itself. That distinction (shown to
            # admin, hidden from customers) is the actual privacy boundary
            # this feature is built around.
            'id_verified': tech.id_verified,
        } if tech else None,
        'payment': {
            'method': txn.payment_method,
            'status': txn.payment_status,
        } if txn else None,
    })

ADMIN_PAGE_SIZE = 25

def paginate(query, page, per_page=ADMIN_PAGE_SIZE):
    """(items, pager) for one page of an ordered query. Out-of-range pages are
    clamped, so a stale link never shows an empty page."""
    total = query.order_by(None).count()
    pages = max(1, -(-total // per_page))
    page = min(max(page or 1, 1), pages)
    items = query.limit(per_page).offset((page - 1) * per_page).all()
    first = (page - 1) * per_page + 1 if total else 0
    return items, {'page': page, 'pages': pages, 'total': total,
                   'first': first, 'last': first + len(items) - 1 if items else 0}

def _list_filters(allowed_statuses):
    status = request.args.get('status', 'all')
    if status not in allowed_statuses:
        status = 'all'
    q = (request.args.get('q') or '').strip()[:100]
    return status, q, request.args.get('page', 1, type=int)

@app.route('/admin/requests')
@admin_required
def admin_requests():
    status, q, page = _list_filters(STATUS_LABELS)
    query = Booking.query
    if status != 'all':
        query = query.filter(Booking.status == status)
    if q:
        like = f'%{q}%'
        query = query.join(Customer, Booking.customer_id == Customer.id)\
            .join(Service, Booking.service_id == Service.id)\
            .filter(or_(Booking.booking_number.ilike(like), Customer.full_name.ilike(like),
                        Service.name.ilike(like)))
    bookings, pager = paginate(query.order_by(Booking.created_at.desc(), Booking.id.desc()), page)
    counts = dict(db.session.query(Booking.status, func.count(Booking.id)).group_by(Booking.status).all())
    stats = {'total': sum(counts.values()), 'pending': counts.get('pending', 0),
             'cancelled': counts.get('cancelled', 0)}
    stats['approved'] = stats['total'] - stats['pending'] - stats['cancelled']
    technicians = Technician.query.order_by(Technician.full_name).all()
    return render_template('admin/request_management.html', bookings=bookings, technicians=technicians,
                           pager=pager, stats=stats, status=status, q=q)

@app.route('/admin/requests/<int:booking_id>/status', methods=['POST'])
@admin_required
def admin_request_status(booking_id):
    from models.technician_models import JobLog
    booking = Booking.query.get_or_404(booking_id)
    new_status = request.form.get('status')
    reason = request.form.get('reason', '')
    technician_id = request.form.get('technician_id', type=int)
    now = datetime.utcnow()
    stamp = now.strftime('%Y-%m-%d %H:%M:%S')
    admin_name = session.get('username', 'Admin')

    if new_status not in ('confirmed', 'cancelled'):
        flash('Repair progress is updated by the assigned technician.', 'warning')
        return redirect(url_for('admin_requests'))

    if new_status == 'confirmed':
        if booking.status != 'pending':
            flash('Only pending requests can be approved.', 'danger')
            return redirect(url_for('admin_requests'))
        tech = Technician.query.filter_by(id=technician_id, is_active=True).first() if technician_id else None
        if not tech:
            flash('Please select a technician before approving.', 'danger')
            return redirect(url_for('admin_requests'))
        if not tech.id_verified:
            flash(f'{tech.full_name} is not identity-verified yet. Verify them in User Management first.', 'danger')
            return redirect(url_for('admin_requests'))
        booking.technician_id = tech.id
        booking.assigned_at = now
        db.session.add(JobLog(booking_id=booking.id, at=stamp, by_name=admin_name,
                              action='assign', text=f'Approved and assigned to {tech.full_name}.'))
        booking.status = 'confirmed'
        booking.updated_at = now
        db.session.commit()
        create_notification(booking.user_id, 'Booking Approved - Technician Assigned',
            f'Your booking #{booking.booking_number} has been approved!\n\n'
            f'Assigned Technician: {tech.full_name} (Verified ✓)\n'
            f'Contact: {tech.phone or "Available through Messages"}', 'success', role='customer')
        create_notification(tech.id, 'New Job Assigned',
            f'{booking.booking_number} - {booking.service.name} on '
            f'{booking.booking_date.strftime("%b %d")} at {booking.booking_time.strftime("%I:%M %p")}.', 'info', role='technician')
        flash('Request approved and technician notified.', 'success')
    else:
        if booking.status in FINISHED_STATUSES or booking.status == 'cancelled':
            flash('This booking can no longer be rejected.', 'danger')
            return redirect(url_for('admin_requests'))
        booking.status = 'cancelled'
        booking.updated_at = now
        db.session.add(JobLog(booking_id=booking.id, at=stamp, by_name=admin_name,
                              action='status', text=f'Rejected by admin. {reason}'.strip()))
        refund_check = settle_cancelled_booking(booking)
        db.session.commit()
        notify_refund_check(booking, refund_check)
        msg = f'Your booking #{booking.booking_number} has been rejected.'
        if reason:
            msg += f'\n\nReason: {reason}'
        create_notification(booking.user_id, 'Booking Rejected', msg, 'error', role='customer')
        if booking.technician_id:
            create_notification(booking.technician_id, 'Job Cancelled',
                                f'{booking.booking_number} was cancelled by an admin.', 'warning', role='technician')
        flash('Request rejected.', 'warning')
    return redirect(url_for('admin_requests'))

REASSIGNABLE_STATUSES = ('confirmed', 'diagnosis_pending', 'in_progress', 'on_hold')

@app.route('/admin/requests/<int:booking_id>/assign', methods=['POST'])
@admin_required
def admin_request_reassign(booking_id):
    """Move an approved, unfinished job to another verified technician."""
    from models.technician_models import JobLog, ApprovalRequest
    booking = Booking.query.get_or_404(booking_id)
    if booking.status not in REASSIGNABLE_STATUSES:
        flash('Only approved jobs that are not finished or cancelled can be reassigned.', 'danger')
        return redirect(url_for('admin_requests'))
    tech = Technician.query.filter_by(id=request.form.get('technician_id', type=int), is_active=True).first()
    if not tech:
        flash('Please choose an active technician.', 'danger')
        return redirect(url_for('admin_requests'))
    if not tech.id_verified:
        flash(f'{tech.full_name} is not identity-verified yet. Verify them in User Management first.', 'danger')
        return redirect(url_for('admin_requests'))
    if tech.id == booking.technician_id:
        flash(f'{booking.booking_number} is already assigned to {tech.full_name}.', 'info')
        return redirect(url_for('admin_requests'))

    previous = booking.technician
    reason = (request.form.get('reason') or '').strip()[:300]
    now = datetime.utcnow()
    booking.technician_id = tech.id
    booking.assigned_at = now
    booking.updated_at = now
    # Answers to open extra-work requests should reach the technician now doing the job.
    ApprovalRequest.query.filter_by(booking_id=booking.id, status='pending').update(
        {'technician_id': tech.id}, synchronize_session=False)
    db.session.add(JobLog(booking_id=booking.id, at=now.strftime('%Y-%m-%d %H:%M:%S'),
                          by_name=session.get('username', 'Admin'), action='assign',
                          text=(f'Reassigned from {previous.full_name} to {tech.full_name}.' if previous
                                else f'Assigned to {tech.full_name}.') + (f' Reason: {reason}' if reason else '')))
    db.session.commit()

    create_notification(tech.id, 'Job Assigned to You',
                        f'{booking.booking_number} - {booking.service.name} is now yours '
                        f'(status: {STATUS_LABELS.get(booking.status, booking.status)}).', 'info', role='technician')
    if previous:
        create_notification(previous.id, 'Job Reassigned',
                            f'{booking.booking_number} was reassigned to another technician.', 'warning',
                            role='technician')
    create_notification(booking.customer_id, 'New Technician Assigned',
                        f'{tech.full_name} (verified) is now handling booking {booking.booking_number}.', 'info',
                        role='customer')
    log_activity(session.get('user_id'), 'booking_reassign',
                 f'{booking.booking_number}: {previous.full_name if previous else "-"} -> {tech.full_name}')
    flash(f'{booking.booking_number} reassigned to {tech.full_name}.', 'success')
    return redirect(url_for('admin_requests'))

@app.route('/api/admin/booking/<int:booking_id>')
@admin_required
def api_admin_booking_detail(booking_id):
    booking = Booking.query.get_or_404(booking_id)
    user = booking.user
    service = booking.service
    txn = booking.transaction
    tech = booking.technician

    return jsonify({
        'id': booking.id,
        'booking_number': booking.booking_number,
        'status': booking.status,
        'device_type': booking.device_type,
        'description': booking.description,
        'address': booking.address,
        'is_in_shop': booking.is_in_shop,
        'booking_date': booking.booking_date.strftime('%b %d, %Y') if booking.booking_date else None,
        'booking_time': booking.booking_time.strftime('%I:%M %p') if booking.booking_time else None,
        'created_at': booking.created_at.strftime('%b %d, %Y at %I:%M %p') if booking.created_at else None,
        'customer': {
            'full_name': user.full_name if user else 'Unknown',
            'email': user.email if user else None,
            'phone': user.phone if user else None,
            'address': user.address if user else None,
        },
        'service': {
            'name': service.name if service else 'N/A',
            'price': float(service.price) if service else 0,
            'estimated_hours': service.estimated_hours if service else None,
            'description': service.description if service else None,
        },
        'technician': {
            'full_name': tech.full_name,
            'phone': tech.phone,
            'id_type': tech.id_type,
            'id_verified': tech.id_verified,
            # Deliberately no id_number here - even in this admin-only view,
            # the raw document number stays out of general API responses.
            # An admin who needs to audit the actual number uses the
            # dedicated verification action in User Management, which is
            # logged separately, rather than it showing up incidentally
            # every time someone opens a booking's details.
            'assigned_at': booking.assigned_at.strftime('%b %d, %Y at %I:%M %p') if booking.assigned_at else None,
        } if tech else None,
        'transaction': {
            'transaction_number': txn.transaction_number,
            'amount': float(txn.amount),
            'payment_method': txn.payment_method,
            'payment_status': txn.payment_status,
            'gcash_reference': txn.gcash_reference,
        } if txn else None
    })

ORDER_TRANSITIONS = {  # current status -> statuses an admin may move it to
    'pending': ('processing', 'cancelled'),
    'processing': ('completed', 'cancelled'),
}

@app.route('/admin/orders')
@admin_required
def admin_orders():
    status_filter = request.args.get('status', 'all')
    q = Order.query
    if status_filter != 'all':
        q = q.filter_by(status=status_filter)
    orders = q.order_by(Order.created_at.desc()).all()
    counts = dict(db.session.query(Order.status, func.count(Order.id)).group_by(Order.status).all())
    return render_template('admin/orders.html', orders=orders, counts=counts,
                           status_filter=status_filter, transitions=ORDER_TRANSITIONS)

@app.route('/admin/orders/<int:order_id>/status', methods=['POST'])
@admin_required
def admin_order_status(order_id):
    order = Order.query.get_or_404(order_id)
    new_status = request.form.get('status')
    if new_status not in ORDER_TRANSITIONS.get(order.status, ()):
        flash(f'An order that is {order.status} cannot be moved to {new_status}.', 'danger')
        return redirect(url_for('admin_orders'))

    if new_status == 'cancelled':
        refunds = _cancel_order(order, cancelled_by=_reviewer_label())
        msg = f'Your order #{order.order_number} was cancelled by our team.'
        if refunds:
            msg += ' A refund has been opened; you can follow it on your Transactions page.'
    else:
        order.status = new_status
        order.updated_at = datetime.utcnow()
        # Cash on delivery is paid when the order is handed over.
        if new_status == 'completed' and order.payment_method == 'cod':
            order.payment_status = 'confirmed'
            for txn in order.transactions:
                if txn.payment_status == 'pending':
                    txn.payment_status = 'confirmed'
                    txn.updated_at = datetime.utcnow()
        db.session.commit()
        msg = {'processing': f'Your order #{order.order_number} is being prepared.',
               'completed': f'Your order #{order.order_number} has been completed.'}[new_status]
    create_notification(order.user_id, 'Order Update', msg, 'warning' if new_status == 'cancelled' else 'info',
                        role='customer')
    log_activity(session.get('user_id'), 'order_status', f'Order {order.order_number} -> {new_status}')
    flash(f'Order {order.order_number} marked {new_status}.', 'success')
    return redirect(url_for('admin_orders', status=request.args.get('filter', 'all')))


# ==================== ADMIN: PRODUCTS ====================

def _slugify(text):
    return re.sub(r'[^a-z0-9]+', '-', (text or '').lower()).strip('-')[:50]

def _decimal_field(raw, label, minimum=0, maximum=10_000_000):
    """Parse a money field. Returns (value, error)."""
    from decimal import Decimal, InvalidOperation
    try:
        value = Decimal(str(raw).strip()).quantize(Decimal('0.01'))
    except (InvalidOperation, ValueError):
        return None, f'{label} must be a number.'
    if not minimum <= value <= maximum:
        return None, f'{label} must be between {minimum} and {maximum:,}.'
    return value, None

def _int_field(raw, label, minimum=0, maximum=1_000_000):
    try:
        value = int(str(raw).strip())
    except (TypeError, ValueError):
        return None, f'{label} must be a whole number.'
    if not minimum <= value <= maximum:
        return None, f'{label} must be between {minimum} and {maximum:,}.'
    return value, None

def _product_from_form(form):
    """Validated product fields from a submitted form. Returns (data, error)."""
    name = (form.get('name') or '').strip()
    if not name or len(name) > 100:
        return None, 'Product name is required (max 100 characters).'
    price, err = _decimal_field(form.get('price'), 'Price')
    if err:
        return None, err
    stock, err = _int_field(form.get('stock_quantity'), 'Stock')
    if err:
        return None, err
    image_url = (form.get('image_url') or '').strip()
    if image_url and not (image_url.startswith('https://') or image_url.startswith('/static/')):
        return None, 'Image URL must start with https:// or /static/.'
    return {
        'name': name,
        'description': (form.get('description') or '').strip()[:2000] or None,
        'price': price,
        'category': (form.get('category') or '').strip().lower()[:50] or None,
        'stock_quantity': stock,
        'compatibility': (form.get('compatibility') or '').strip()[:100] or None,
        'image_url': image_url[:255] or None,
    }, None

@app.route('/admin/products')
@admin_required
def admin_products():
    products = Product.query.order_by(Product.is_active.desc(), Product.name).all()
    categories = sorted({p.category for p in products if p.category})
    return render_template('admin/products.html', products=products, categories=categories,
                           low_stock=5)

@app.route('/admin/products', methods=['POST'])
@admin_required
def admin_product_create():
    data, err = _product_from_form(request.form)
    if err:
        flash(err, 'danger')
        return redirect(url_for('admin_products'))
    product = Product(is_active=True, **data)
    db.session.add(product)
    db.session.commit()
    cache.delete('active_products')
    log_activity(session.get('user_id'), 'product_create', f'Added product: {product.name}')
    flash(f'{product.name} added.', 'success')
    return redirect(url_for('admin_products'))

@app.route('/admin/products/<int:product_id>', methods=['POST'])
@admin_required
def admin_product_update(product_id):
    product = Product.query.get_or_404(product_id)
    data, err = _product_from_form(request.form)
    if err:
        flash(err, 'danger')
        return redirect(url_for('admin_products'))
    for key, value in data.items():
        setattr(product, key, value)
    db.session.commit()
    cache.delete('active_products')
    log_activity(session.get('user_id'), 'product_update', f'Updated product: {product.name}')
    flash(f'{product.name} updated.', 'success')
    return redirect(url_for('admin_products'))

@app.route('/admin/products/<int:product_id>/toggle', methods=['POST'])
@admin_required
def admin_product_toggle(product_id):
    product = Product.query.get_or_404(product_id)
    product.is_active = not product.is_active
    db.session.commit()
    cache.delete('active_products')
    state = 'listed in the shop' if product.is_active else 'hidden from the shop'
    log_activity(session.get('user_id'), 'product_toggle', f'{product.name} {state}')
    flash(f'{product.name} is now {state}.', 'success')
    return redirect(url_for('admin_products'))

# ==================== ADMIN: SERVICES & CATEGORIES ====================

@app.route('/admin/services')
@admin_required
def admin_services():
    categories = ServiceCategory.query.order_by(ServiceCategory.display_order, ServiceCategory.name).all()
    return render_template('admin/services.html', categories=categories)

def _service_from_form(form):
    name = (form.get('name') or '').strip()
    if not name or len(name) > 100:
        return None, 'Service name is required (max 100 characters).'
    category = db.session.get(ServiceCategory, form.get('category_id', type=int) or 0)
    if not category:
        return None, 'Choose a category.'
    price, err = _decimal_field(form.get('price'), 'Price')
    if err:
        return None, err
    hours, err = _int_field(form.get('estimated_hours') or 1, 'Estimated hours', 1, 200)
    if err:
        return None, err
    return {'name': name, 'category_id': category.id, 'price': price, 'estimated_hours': hours,
            'description': (form.get('description') or '').strip()[:2000] or None}, None

@app.route('/admin/services', methods=['POST'])
@admin_required
def admin_service_create():
    data, err = _service_from_form(request.form)
    if err:
        flash(err, 'danger')
        return redirect(url_for('admin_services'))
    service = Service(is_active=True, **data)
    db.session.add(service)
    db.session.commit()
    log_activity(session.get('user_id'), 'service_create', f'Added service: {service.name}')
    flash(f'{service.name} added.', 'success')
    return redirect(url_for('admin_services'))

@app.route('/admin/services/<int:service_id>', methods=['POST'])
@admin_required
def admin_service_update(service_id):
    service = Service.query.get_or_404(service_id)
    data, err = _service_from_form(request.form)
    if err:
        flash(err, 'danger')
        return redirect(url_for('admin_services'))
    for key, value in data.items():
        setattr(service, key, value)
    db.session.commit()
    log_activity(session.get('user_id'), 'service_update', f'Updated service: {service.name}')
    flash(f'{service.name} updated. New bookings use the new price.', 'success')
    return redirect(url_for('admin_services'))

@app.route('/admin/services/<int:service_id>/toggle', methods=['POST'])
@admin_required
def admin_service_toggle(service_id):
    service = Service.query.get_or_404(service_id)
    service.is_active = not service.is_active
    db.session.commit()
    flash(f'{service.name} is now {"bookable" if service.is_active else "hidden from customers"}.', 'success')
    return redirect(url_for('admin_services'))

@app.route('/admin/categories', methods=['POST'])
@admin_required
def admin_category_create():
    name = (request.form.get('name') or '').strip()
    if not name or len(name) > 50:
        flash('Category name is required (max 50 characters).', 'danger')
        return redirect(url_for('admin_services'))
    slug = _slugify(name)
    if ServiceCategory.query.filter(or_(ServiceCategory.name == name, ServiceCategory.slug == slug)).first():
        flash('A category with that name already exists.', 'danger')
        return redirect(url_for('admin_services'))
    icon = (request.form.get('icon') or 'fa-tools').strip()
    if not re.fullmatch(r'fa-[a-z0-9-]{1,40}', icon):
        icon = 'fa-tools'
    db.session.add(ServiceCategory(name=name, slug=slug, icon=icon, is_active=True,
                                   description=(request.form.get('description') or '').strip()[:500] or None))
    db.session.commit()
    flash(f'Category {name} added.', 'success')
    return redirect(url_for('admin_services'))

@app.route('/admin/categories/<int:category_id>/toggle', methods=['POST'])
@admin_required
def admin_category_toggle(category_id):
    category = ServiceCategory.query.get_or_404(category_id)
    category.is_active = not category.is_active
    db.session.commit()
    flash(f'{category.name} is now {"visible" if category.is_active else "hidden from customers"}.', 'success')
    return redirect(url_for('admin_services'))

# ==================== ADMIN: SUPPORT ====================

@app.route('/admin/support')
@admin_required
def admin_support():
    status_order = db.case((SupportTicket.status == 'open', 0), (SupportTicket.status == 'in_progress', 1), else_=2)
    tickets = SupportTicket.query.order_by(status_order, SupportTicket.created_at.desc()).limit(200).all()
    inquiries = ContactInquiry.query.order_by(
        (ContactInquiry.status == 'new').desc(), ContactInquiry.created_at.desc()).limit(200).all()
    return render_template('admin/support.html', tickets=tickets, inquiries=inquiries)

@app.route('/admin/support/<int:ticket_id>/respond', methods=['POST'])
@admin_required
def admin_ticket_respond(ticket_id):
    ticket = SupportTicket.query.get_or_404(ticket_id)
    response = (request.form.get('admin_response') or '').strip()
    status = request.form.get('status', 'resolved')
    if status not in ('open', 'in_progress', 'resolved'):
        status = 'resolved'
    if not response and status == ticket.status:
        flash('Write a reply or change the status.', 'danger')
        return redirect(url_for('admin_support'))
    if response:
        ticket.admin_response = response[:5000]
    ticket.status = status
    ticket.updated_at = datetime.utcnow()
    db.session.commit()
    msg = f'Your support ticket "{ticket.subject}" is now {status.replace("_", " ")}.'
    if response:
        msg += ' We replied: ' + (response[:300] + ('…' if len(response) > 300 else ''))
    create_notification(ticket.user_id, 'Support Ticket Updated', msg, 'info', role='customer')
    log_activity(session.get('user_id'), 'ticket_respond', f'Ticket #{ticket.id} -> {status}')
    flash('Ticket updated and the customer was notified.', 'success')
    return redirect(url_for('admin_support'))

@app.route('/admin/inquiries/<int:inquiry_id>/status', methods=['POST'])
@admin_required
def admin_inquiry_status(inquiry_id):
    inquiry = ContactInquiry.query.get_or_404(inquiry_id)
    inquiry.status = 'handled' if inquiry.status == 'new' else 'new'
    db.session.commit()
    flash('Inquiry updated.', 'success')
    return redirect(url_for('admin_support') + '#inquiries')

# ==================== ADMIN: MESSAGES ====================

@app.route('/admin/messages')
@admin_required
def admin_messages():
    conv = request.args.get('conv')
    conversations, selected, thread = _load_inbox(current_account(), _account_from_key(conv))
    if not selected and conversations and not conv:
        return redirect(url_for('admin_messages', conv=conversations[0]['key']))
    return render_template('admin/messages.html', conversations=conversations,
                           selected_conversation=selected, messages=thread)

@app.route('/admin/messages/send', methods=['POST'])
@admin_required
def admin_message_send():
    me = current_account()
    content = (request.form.get('content') or '').strip()
    recipient = None
    if request.form.get('recipient_key'):
        recipient = _account_from_key(request.form['recipient_key'])
    elif request.form.get('recipient_email'):
        recipient = find_account_by_email(request.form['recipient_email'])
    if not recipient or recipient.key == me.key:
        flash('Recipient not found.', 'danger')
        return redirect(url_for('admin_messages'))
    checked, file_error = check_message_attachment(request.files.get('attachment'))
    if file_error:
        flash(file_error, 'danger')
        return redirect(url_for('admin_messages', conv=recipient.key))
    if (not content and not checked) or len(content) > MAX_MESSAGE_LENGTH:
        flash(f'Write a message (up to {MAX_MESSAGE_LENGTH} characters) or attach a file.', 'danger')
        return redirect(url_for('admin_messages', conv=recipient.key))
    send_message(me, recipient, content, checked=checked)
    return redirect(url_for('admin_messages', conv=recipient.key))

@app.route('/admin/notifications')
@admin_required
def admin_notifications():
    uid = session['user_id']
    rows = _notifications_for('admin', uid).order_by(Notification.created_at.desc()).limit(100).all()
    unread_ids = {n.id for n in rows if not n.is_read}
    _notifications_for('admin', uid).filter_by(is_read=False).update({'is_read': True})
    db.session.commit()
    return render_template('admin/notifications.html', rows=rows, unread_ids=unread_ids)

@app.route('/admin/notifications/clear', methods=['POST'])
@admin_required
def admin_notifications_clear():
    _notifications_for('admin', session['user_id']).filter_by(is_read=True).delete()
    db.session.commit()
    flash('Read notifications cleared.', 'success')
    return redirect(url_for('admin_notifications'))

@app.route('/admin/payments')
@admin_required
def admin_payments():
    status, q, page = _list_filters(PAYMENT_STATUSES)
    query = Transaction.query
    if status != 'all':
        query = query.filter(Transaction.payment_status == status)
    if q:
        like = f'%{q}%'
        query = query.join(Customer, Transaction.customer_id == Customer.id)\
            .filter(or_(Transaction.transaction_number.ilike(like), Transaction.gcash_reference.ilike(like),
                        Transaction.reference_number.ilike(like), Customer.full_name.ilike(like)))
    transactions, pager = paginate(query.order_by(Transaction.transaction_date.desc(), Transaction.id.desc()), page)
    counts = dict(db.session.query(Transaction.payment_status, func.count(Transaction.id))
                  .group_by(Transaction.payment_status).all())
    stats = {'total': sum(counts.values()), **{s: counts.get(s, 0) for s in PAYMENT_STATUSES}}
    return render_template('admin/payment_confirmation.html', transactions=transactions,
                           pager=pager, stats=stats, status=status, q=q)

def _reviewer_label():
    admin = current_account()
    return f'{admin.full_name} (admin #{admin.id})'[:120] if admin else 'admin'

PAYMENT_STATUSES = ('pending', 'confirmed', 'rejected', 'cancelled', 'refunded')

def payment_method_label(method):
    """Display name for a stored payment method (bookings use 'GCash' / 'C.A.R',
    shop orders 'gcash' / 'cod', unpaid extra charges 'unpaid')."""
    return {'gcash': 'GCash', 'cod': 'Cash on delivery', 'c.a.r': 'C.A.R (Cash After Repair)',
            'unpaid': 'Not yet chosen', '': 'Not yet chosen'}.get((method or '').lower(), method)

app.jinja_env.globals['payment_method_label'] = payment_method_label

@app.route('/admin/payments/<int:transaction_id>/confirm', methods=['POST'])
@admin_required
def admin_payment_confirm(transaction_id):
    transaction = Transaction.query.get_or_404(transaction_id)
    if transaction.payment_status == 'confirmed':
        flash('This payment is already confirmed.', 'info')
        return redirect(url_for('admin_payments'))
    if transaction.payment_status == 'cancelled':
        flash('This payment was cancelled and cannot be confirmed.', 'danger')
        return redirect(url_for('admin_payments'))
    if (transaction.booking and transaction.booking.status == 'cancelled') or \
            (transaction.order and transaction.order.status == 'cancelled'):
        flash('This payment belongs to a cancelled booking or order and cannot be confirmed.', 'danger')
        return redirect(url_for('admin_payments'))
    now = datetime.utcnow()
    # One UPDATE that only succeeds while the payment is still open, so a
    # double click can't confirm (and notify) twice.
    claimed = Transaction.query.filter(Transaction.id == transaction.id,
                                       Transaction.payment_status.in_(('pending', 'rejected'))).update(
        {'payment_status': 'confirmed', 'updated_at': now, 'reviewed_at': now,
         'reviewed_by': _reviewer_label()}, synchronize_session=False)
    if claimed != 1:
        db.session.rollback()
        flash('This payment was already handled.', 'info')
        return redirect(url_for('admin_payments'))
    db.session.refresh(transaction)
    if transaction.order:
        transaction.order.payment_status = 'confirmed'
    db.session.commit()
    log_activity(session.get('user_id'), 'payment_confirm', f'Confirmed payment {transaction.transaction_number}')
    
    create_notification(
        transaction.user_id,
        'Payment Confirmed',
        f'Your payment for transaction #{transaction.transaction_number} has been confirmed.',
        'success', role='customer'
    )
    
    flash('Payment confirmed successfully.', 'success')
    return redirect(url_for('admin_payments'))

@app.route('/admin/payments/<int:transaction_id>/reject', methods=['POST'])
@admin_required
def admin_payment_reject(transaction_id):
    transaction = Transaction.query.get_or_404(transaction_id)
    if transaction.payment_status in ('confirmed', 'cancelled'):
        flash(f'A {transaction.payment_status} payment cannot be rejected.', 'danger')
        return redirect(url_for('admin_payments'))
    reason = (request.form.get('reason') or '').strip()[:1000] or 'Payment rejected by admin.'
    now = datetime.utcnow()
    claimed = Transaction.query.filter(Transaction.id == transaction.id,
                                       Transaction.payment_status == 'pending').update(
        {'payment_status': 'rejected', 'rejection_reason': reason, 'updated_at': now,
         'reviewed_at': now, 'reviewed_by': _reviewer_label()}, synchronize_session=False)
    if claimed != 1:
        db.session.rollback()
        flash('This payment was already handled.', 'info')
        return redirect(url_for('admin_payments'))
    db.session.refresh(transaction)
    if transaction.order:
        transaction.order.payment_status = 'rejected'
    db.session.commit()
    log_activity(session.get('user_id'), 'payment_reject', f'Rejected payment {transaction.transaction_number}')
    
    create_notification(
        transaction.user_id,
        'Payment Rejected',
        f'Your payment for transaction #{transaction.transaction_number} was rejected. Reason: {reason}',
        'error', role='customer'
    )
    
    flash('Payment rejected.', 'warning')
    return redirect(url_for('admin_payments'))

# ==================== ADMIN: REFUNDS ====================
REFUND_STATUSES = ('pending', 'refunded', 'declined')

@app.route('/admin/refunds')
@admin_required
def admin_refunds():
    status, q, page = _list_filters(REFUND_STATUSES)
    query = Refund.query
    if status != 'all':
        query = query.filter(Refund.status == status)
    if q:
        like = f'%{q}%'
        query = query.join(Transaction, Refund.transaction_id == Transaction.id)\
            .join(Customer, Refund.customer_id == Customer.id)\
            .filter(or_(Transaction.transaction_number.ilike(like), Customer.full_name.ilike(like),
                        Refund.reference.ilike(like), Refund.reason.ilike(like)))
    # open refunds first, then newest
    refunds, pager = paginate(query.order_by((Refund.status == 'pending').desc(), Refund.created_at.desc(),
                                             Refund.id.desc()), page)
    counts = dict(db.session.query(Refund.status, func.count(Refund.id)).group_by(Refund.status).all())
    owed = db.session.query(func.coalesce(func.sum(Refund.amount), 0)).filter(Refund.status == 'pending').scalar()
    stats = {'total': sum(counts.values()), 'owed': float(owed or 0),
             **{st: counts.get(st, 0) for st in REFUND_STATUSES}}
    return render_template('admin/refunds.html', refunds=refunds, pager=pager, stats=stats, status=status, q=q,
                           methods=REFUND_METHODS)

def _claim_refund(refund_id, new_status, **values):
    """Move a refund out of 'pending' in one UPDATE, so two admins (or a double
    click) can't process it twice. Returns the refund, or None if it was already handled."""
    refund = Refund.query.get_or_404(refund_id)
    claimed = Refund.query.filter_by(id=refund.id, status='pending').update(
        dict(status=new_status, processed_at=datetime.utcnow(), processed_by=_reviewer_label(), **values),
        synchronize_session=False)
    if claimed != 1:
        db.session.rollback()
        return None
    db.session.refresh(refund)
    return refund

@app.route('/admin/refunds/<int:refund_id>/complete', methods=['POST'])
@admin_required
def admin_refund_complete(refund_id):
    from decimal import Decimal, InvalidOperation
    refund = Refund.query.get_or_404(refund_id)
    method = request.form.get('method') or ''
    reference = (request.form.get('reference') or '').strip()
    note = (request.form.get('note') or '').strip()[:1000]
    if method not in REFUND_METHODS:
        flash('Choose how the money was returned.', 'danger')
        return redirect(url_for('admin_refunds'))
    if method != 'Cash' and not reference:
        flash(f'Enter the {method} reference number of the refund.', 'danger')
        return redirect(url_for('admin_refunds'))
    if len(reference) > 80:
        flash('The reference is too long (80 characters at most).', 'danger')
        return redirect(url_for('admin_refunds'))
    try:
        amount = Decimal(str(request.form.get('amount') or refund.amount)).quantize(Decimal('0.01'))
    except (InvalidOperation, ValueError):
        amount = None
    paid = Decimal(str(refund.transaction.amount))
    if amount is None or amount <= 0 or amount > paid:
        flash(f'The refunded amount must be more than ₱0 and at most ₱{paid:,.2f}.', 'danger')
        return redirect(url_for('admin_refunds'))

    refund = _claim_refund(refund.id, 'refunded', amount=amount, method=method,
                           reference=reference or None, note=note or None)
    if not refund:
        flash('This refund was already handled.', 'info')
        return redirect(url_for('admin_refunds'))
    txn = refund.transaction
    txn.payment_status = 'refunded'
    txn.updated_at = datetime.utcnow()
    if txn.order:
        txn.order.payment_status = 'refunded'
    db.session.commit()
    log_activity(session.get('user_id'), 'refund_complete',
                 f'Refunded ₱{amount:,.2f} for {txn.transaction_number} via {method}')
    create_notification(refund.customer_id, 'Refund Sent',
                        f'We refunded ₱{amount:,.2f} for transaction {txn.transaction_number} via {method}'
                        + (f' (reference {reference})' if reference else '') + '.', 'success', role='customer')
    flash(f'Refund for {txn.transaction_number} marked as sent.', 'success')
    return redirect(url_for('admin_refunds'))

@app.route('/admin/refunds/<int:refund_id>/decline', methods=['POST'])
@admin_required
def admin_refund_decline(refund_id):
    note = (request.form.get('note') or '').strip()[:1000]
    if len(note) < 5:
        flash('Explain why no refund is due (the customer will see this).', 'danger')
        return redirect(url_for('admin_refunds'))
    refund = _claim_refund(refund_id, 'declined', note=note)
    if not refund:
        flash('This refund was already handled.', 'info')
        return redirect(url_for('admin_refunds'))
    db.session.commit()
    txn = refund.transaction
    log_activity(session.get('user_id'), 'refund_decline', f'Declined refund for {txn.transaction_number}: {note}')
    create_notification(refund.customer_id, 'About your refund',
                        f'No refund was issued for transaction {txn.transaction_number}. Reason: {note}',
                        'warning', role='customer')
    flash(f'Refund for {txn.transaction_number} declined.', 'warning')
    return redirect(url_for('admin_refunds'))

@app.route('/admin/payments/<int:transaction_id>/refund', methods=['POST'])
@admin_required
def admin_payment_refund(transaction_id):
    """Open a refund by hand for a confirmed payment (e.g. goodwill or a partial refund)."""
    txn = Transaction.query.get_or_404(transaction_id)
    if txn.payment_status != 'confirmed':
        flash('Only confirmed payments can be refunded.', 'danger')
        return redirect(url_for('admin_payments'))
    reason = (request.form.get('reason') or '').strip()
    if len(reason) < 5:
        flash('Give a reason for the refund.', 'danger')
        return redirect(url_for('admin_payments'))
    refund, created = open_refund(txn, reason, created_by=_reviewer_label())
    db.session.commit()
    if not created:
        flash(f'{txn.transaction_number} already has a refund ({refund.status}).', 'info')
        return redirect(url_for('admin_refunds'))
    create_notification(txn.customer_id, 'Refund requested',
                        f'A refund was opened for transaction {txn.transaction_number}. '
                        f'You can follow it on your Transactions page.', 'info', role='customer')
    flash(f'Refund opened for {txn.transaction_number}.', 'success')
    return redirect(url_for('admin_refunds'))

MONTH_NAMES = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

def _last_n_months(now, n):
    """[(year, month), ...] for the n calendar months ending with now's month, oldest first."""
    year, month = now.year, now.month
    months = []
    for _ in range(n):
        months.append((year, month))
        month -= 1
        if month == 0:
            year, month = year - 1, 12
    return months[::-1]

def _monthly_series(date_col, value_expr, now, n, *filters):
    """Labels and values for the last n calendar months (zero-filled).
    Uses extract() so it runs on MySQL and SQLite alike."""
    from sqlalchemy import extract
    months = _last_n_months(now, n)
    since = datetime(months[0][0], months[0][1], 1)
    rows = db.session.query(extract('year', date_col), extract('month', date_col), value_expr)\
        .filter(date_col >= since, *filters)\
        .group_by(extract('year', date_col), extract('month', date_col)).all()
    totals = {(int(y), int(m)): v for y, m, v in rows}
    labels = [f"{MONTH_NAMES[m - 1]} {y}" for y, m in months]
    values = [float(totals.get((y, m)) or 0) for y, m in months]
    return labels, values

def _day_label(d):
    """func.date() gives a date on MySQL but a 'YYYY-MM-DD' string on SQLite."""
    if isinstance(d, str):
        d = datetime.strptime(d[:10], '%Y-%m-%d')
    return d.strftime('%b %d')

# Not page-cached: the rendered page embeds the viewer's CSRF token.
@app.route('/admin/analytics')
@admin_required
def admin_analytics():
    from sqlalchemy import func, extract
    
    # Get date range filter from query params
    date_range = request.args.get('range', '30d')
    
    # Calculate date ranges
    now = datetime.utcnow()
    if date_range == '7d':
        start_date = now - timedelta(days=7)
    elif date_range == '90d':
        start_date = now - timedelta(days=90)
    elif date_range == '1y':
        start_date = now - timedelta(days=365)
    else:  # 30d default
        start_date = now - timedelta(days=30)
    
    # ============================================
    # KEY METRICS
    # ============================================
    
    # Each KPI shows its all-time total plus how much was added in the selected
    # period, compared with the period of the same length just before it.
    period = now - start_date
    prev_start = start_date - period

    def period_change(current, previous):
        """% change vs the previous period, or None when there is nothing to compare."""
        if not previous:
            return None
        return round((float(current) - float(previous)) / float(previous) * 100)

    # Customers
    total_users = Customer.query.count()
    new_users = Customer.query.filter(Customer.created_at >= start_date).count()
    prev_users = Customer.query.filter(Customer.created_at >= prev_start,
                                       Customer.created_at < start_date).count()
    user_change = period_change(new_users, prev_users)

    # Bookings
    total_bookings = Booking.query.count()
    new_bookings = Booking.query.filter(Booking.created_at >= start_date).count()
    prev_bookings = Booking.query.filter(Booking.created_at >= prev_start, Booking.created_at < start_date).count()
    bookings_change = period_change(new_bookings, prev_bookings)

    # Revenue (confirmed payments only)
    confirmed = Transaction.payment_status == 'confirmed'
    total_revenue = db.session.query(func.sum(Transaction.amount)).filter(confirmed).scalar() or 0
    revenue_this_period = db.session.query(func.sum(Transaction.amount)).filter(
        confirmed, Transaction.transaction_date >= start_date).scalar() or 0
    revenue_prev_period = db.session.query(func.sum(Transaction.amount)).filter(
        confirmed, Transaction.transaction_date >= prev_start,
        Transaction.transaction_date < start_date).scalar() or 0
    revenue_change = period_change(revenue_this_period, revenue_prev_period)

    # Completion rate: finished jobs out of every booking that wasn't cancelled.
    finished_bookings = Booking.query.filter(Booking.status.in_(FINISHED_STATUSES)).count()
    open_or_done = Booking.query.filter(Booking.status != 'cancelled').count()
    completion_rate = round(finished_bookings / open_or_done * 100) if open_or_done else 0
    period_label = {'7d': 'last 7 days', '90d': 'last 90 days', '1y': 'last year'}.get(date_range, 'last 30 days')
    
    # ============================================
    # MONTHLY REVENUE (Last 12 months)
    # ============================================
    
    revenue_labels, revenue_data = _monthly_series(
        Transaction.transaction_date, func.sum(Transaction.amount), now, 12,
        Transaction.payment_status == 'confirmed')

    # ============================================
    # SERVICE DISTRIBUTION
    # ============================================
    
    service_distribution = db.session.query(
        Service.name,
        func.count(Booking.id).label('count')
    ).join(Booking, Booking.service_id == Service.id)\
     .group_by(Service.id)\
     .order_by(func.count(Booking.id).desc())\
     .all()
    
    service_labels = [s[0] for s in service_distribution]
    service_data = [s[1] for s in service_distribution]
    
    # Service colors
    service_colors = ['#00ff88', '#3b82f6', '#22c55e', '#f59e0b', '#8b5cf6', '#ef4444', '#ec4899', '#06b6d4']
    
    # ============================================
    # USER GROWTH (Last 6 months)
    # ============================================
    
    growth_labels, growth_data = _monthly_series(Customer.created_at, func.count(Customer.id), now, 6)
    growth_data = [int(v) for v in growth_data]

    # ============================================
    # PAYMENT METHODS
    # ============================================
    
    payment_methods = db.session.query(
        Transaction.payment_method,
        func.count(Transaction.id).label('count')
    ).group_by(Transaction.payment_method).all()
    
    payment_labels = []
    payment_data = []
    payment_colors = ['#0073e6', '#22c55e', '#8b5cf6', '#f59e0b']
    
    for item in payment_methods:
        if item.payment_method:
            label = item.payment_method.upper()
            if label == 'GCASH':
                label = 'GCash'
            elif label == 'COD':
                label = 'Cash on Delivery'
            elif label == 'C.A.R':
                label = 'Cash After Repair'
            payment_labels.append(label)
            payment_data.append(item.count)
    
    # ============================================
    # STATUS DISTRIBUTION
    # ============================================
    
    status_distribution = db.session.query(
        Booking.status,
        func.count(Booking.id).label('count')
    ).group_by(Booking.status).all()
    
    status_labels = [s[0].replace('_', ' ').title() for s in status_distribution]
    status_data = [s[1] for s in status_distribution]
    status_colors = {
        'pending': '#f59e0b',
        'confirmed': '#3b82f6',
        'in_progress': '#8b5cf6',
        'completed': '#22c55e',
        'cancelled': '#ef4444'
    }
    status_color_list = [status_colors.get(s[0], '#94a3b8') for s in status_distribution]
    
    # ============================================
    # RECENT TRANSACTIONS (for activity feed)
    # ============================================
    
    recent_transactions = Transaction.query.order_by(
        Transaction.transaction_date.desc()
    ).limit(10).all()
    
    # ============================================
    # BOOKINGS BY DAY (for chart)
    # ============================================
    
    bookings_by_day = db.session.query(
        func.date(Booking.created_at).label('date'),
        func.count(Booking.id).label('count')
    ).filter(Booking.created_at >= start_date)\
     .group_by('date')\
     .order_by('date')\
     .all()
    
    day_labels = [_day_label(b.date) for b in bookings_by_day]
    day_data = [b.count for b in bookings_by_day]
    
    # ============================================
    # REVENUE BY DAY (for chart)
    # ============================================
    
    revenue_by_day = db.session.query(
        func.date(Transaction.transaction_date).label('date'),
        func.sum(Transaction.amount).label('total')
    ).filter(
        Transaction.payment_status == 'confirmed',
        Transaction.transaction_date >= start_date
    ).group_by('date')\
     .order_by('date')\
     .all()
    
    revenue_day_labels = [_day_label(r.date) for r in revenue_by_day]
    revenue_day_data = [float(r.total) if r.total else 0 for r in revenue_by_day]

    # ============================================
    # SHOP PERFORMANCE (real e-commerce data - this
    # entire feature had zero analytics coverage before)
    # ============================================

    # Confirmed payments only, same as Total Revenue: shop = order payments,
    # repairs = everything else (bookings and approved extra work).
    shop_revenue = db.session.query(func.sum(Transaction.amount)).filter(
        Transaction.payment_status == 'confirmed',
        Transaction.order_id.isnot(None)
    ).scalar() or 0
    booking_revenue_confirmed = db.session.query(func.sum(Transaction.amount)).filter(
        Transaction.payment_status == 'confirmed',
        Transaction.order_id.is_(None)
    ).scalar() or 0
    monthly_booking_labels, monthly_booking_data = _monthly_series(
        Booking.created_at, func.count(Booking.id), now, 12)
    monthly_booking_data = [int(v) for v in monthly_booking_data]

    top_products = db.session.query(
        Product.name,
        func.sum(OrderItem.quantity).label('units_sold'),
        func.sum(OrderItem.quantity * OrderItem.price).label('revenue')
    ).join(OrderItem, OrderItem.product_id == Product.id)\
     .join(Order, Order.id == OrderItem.order_id)\
     .filter(Order.status != 'cancelled')\
     .group_by(Product.id)\
     .order_by(func.sum(OrderItem.quantity).desc())\
     .limit(8).all()

    top_product_labels = [p.name for p in top_products]
    top_product_data = [int(p.units_sold) for p in top_products]

    # Low-stock alert - the kind of thing a real shop owner actually
    # needs to see at a glance, not just a decorative chart.
    LOW_STOCK_THRESHOLD = 5
    low_stock_products = Product.query.filter(
        Product.is_active == True,
        Product.stock_quantity <= LOW_STOCK_THRESHOLD
    ).order_by(Product.stock_quantity.asc()).limit(10).all()

    # ============================================
    # TECHNICIAN PERFORMANCE (the other feature with
    # zero analytics coverage before - who's actually
    # doing the work, and how much of it)
    # ============================================

    technician_stats = db.session.query(
        Technician.full_name,
        Technician.id_verified,
        func.count(Booking.id).label('assigned_count'),
        func.sum(db.case((Booking.status == 'completed', 1), else_=0)).label('completed_count')
    ).join(Booking, Booking.technician_id == Technician.id)\
     .group_by(Technician.id)\
     .order_by(func.count(Booking.id).desc())\
     .all()

    technician_labels = [t.full_name for t in technician_stats]
    technician_assigned_data = [int(t.assigned_count) for t in technician_stats]
    technician_completed_data = [int(t.completed_count or 0) for t in technician_stats]

    total_technicians_all = Technician.query.count()
    verified_technicians = Technician.query.filter_by(id_verified=True).count()
    unassigned_bookings = Booking.query.filter(
        Booking.status.in_(['confirmed', 'in_progress']),
        Booking.technician_id.is_(None)
    ).count()

    # ============================================
    # CUSTOMER INSIGHTS (new vs. returning, and who
    # actually drives the most revenue - both useful
    # for real retention/loyalty decisions)
    # ============================================

    # A "returning" customer here means 2+ confirmed bookings OR orders -
    # i.e. they've come back for a second transaction, not just browsed.
    customer_txn_counts = db.session.query(
        Transaction.user_id,
        func.count(Transaction.id).label('txn_count')
    ).filter(Transaction.payment_status == 'confirmed')\
     .group_by(Transaction.user_id).subquery()

    returning_customers = db.session.query(func.count()).select_from(customer_txn_counts).filter(
        customer_txn_counts.c.txn_count >= 2
    ).scalar() or 0
    new_customers_count = db.session.query(func.count()).select_from(customer_txn_counts).filter(
        customer_txn_counts.c.txn_count == 1
    ).scalar() or 0

    top_customers = db.session.query(
        Customer.full_name,
        func.sum(Transaction.amount).label('total_spent'),
        func.count(Transaction.id).label('txn_count')
    ).join(Transaction, Transaction.customer_id == Customer.id)\
     .filter(Transaction.payment_status == 'confirmed')\
     .group_by(Customer.id)\
     .order_by(func.sum(Transaction.amount).desc())\
     .limit(5).all()

    return render_template('admin/analytics.html',
                         total_users=total_users,
                         new_users=new_users,
                         user_change=user_change,
                         total_bookings=total_bookings,
                         new_bookings=new_bookings,
                         bookings_change=bookings_change,
                         total_revenue=float(total_revenue),
                         revenue_this_period=float(revenue_this_period),
                         revenue_change=revenue_change,
                         completion_rate=completion_rate,
                         finished_bookings=finished_bookings,
                         period_label=period_label,
                         monthly_booking_data=monthly_booking_data,
                         revenue_labels=revenue_labels,
                         revenue_data=revenue_data,
                         service_labels=service_labels,
                         service_data=service_data,
                         service_colors=service_colors[:len(service_labels)],
                         growth_labels=growth_labels,
                         growth_data=growth_data,
                         payment_labels=payment_labels,
                         payment_data=payment_data,
                         payment_colors=payment_colors[:len(payment_labels)],
                         status_labels=status_labels,
                         status_data=status_data,
                         status_color_list=status_color_list,
                         recent_transactions=recent_transactions,
                         day_labels=day_labels,
                         day_data=day_data,
                         revenue_day_labels=revenue_day_labels,
                         revenue_day_data=revenue_day_data,
                         date_range=date_range,
                         shop_revenue=float(shop_revenue),
                         booking_revenue_confirmed=float(booking_revenue_confirmed),
                         top_product_labels=top_product_labels,
                         top_product_data=top_product_data,
                         low_stock_products=low_stock_products,
                         low_stock_threshold=LOW_STOCK_THRESHOLD,
                         technician_labels=technician_labels,
                         technician_assigned_data=technician_assigned_data,
                         technician_completed_data=technician_completed_data,
                         total_technicians_all=total_technicians_all,
                         verified_technicians=verified_technicians,
                         unassigned_bookings=unassigned_bookings,
                         new_customers_count=new_customers_count,
                         returning_customers=returning_customers,
                         top_customers=top_customers)
    
@app.route('/admin/technician-activity')
@admin_required
def admin_technician_activity():
    from models.technician_models import IncidentReport, ServiceReport, ServiceRating, ApprovalRequest
    from blueprints.technician import incident_files

    incidents = IncidentReport.query.order_by(IncidentReport.reported_at.desc()).limit(100).all()
    approvals = ApprovalRequest.query.order_by((ApprovalRequest.status == 'pending').desc(),
                                               ApprovalRequest.id.desc()).limit(50).all()
    reports = ServiceReport.query.filter_by(status='submitted')\
        .order_by(ServiceReport.submitted_at.desc()).limit(50).all()
    ratings = ServiceRating.query.order_by(ServiceRating.submitted_at.desc()).limit(50).all()

    tech_ids, customer_ids, bids = set(), set(), set()
    for i in incidents:
        tech_ids.add(i.technician_id)
        if i.booking_id:
            bids.add(i.booking_id)
    for r in reports:
        tech_ids.add(r.technician_id)
        if r.booking_id:
            bids.add(r.booking_id)
    for r in ratings:
        tech_ids.add(r.technician_id)
        customer_ids.add(r.customer_id)
        if r.booking_id:
            bids.add(r.booking_id)
    for a in approvals:
        tech_ids.add(a.technician_id)
        bids.add(a.booking_id)

    technicians = {t.id: t for t in Technician.query.filter(Technician.id.in_(tech_ids)).all()} if tech_ids else {}
    customers = {c.id: c for c in Customer.query.filter(Customer.id.in_(customer_ids)).all()} if customer_ids else {}
    bookings = {b.id: b for b in Booking.query.filter(Booking.id.in_(bids)).all()} if bids else {}

    return render_template(
        'admin/technician_activity.html',
        incidents=incidents, reports=reports, ratings=ratings, approvals=approvals,
        technicians=technicians, customers=customers, bookings=bookings,
        incident_files=incident_files([i.id for i in incidents])
    )

@app.route('/admin/uploads/<int:upload_id>')
@admin_required
def admin_upload_file(upload_id):
    """Technician uploads (incident evidence and the like) for administrators.
    Images open in the browser; anything else downloads."""
    from models.technician_models import UploadedFile
    from services.upload_service import path_for
    f = UploadedFile.query.get_or_404(upload_id)
    path = path_for(f)
    if not os.path.isfile(path):
        abort(404)
    resp = send_file(path, mimetype=f.mime_type, download_name=f.original_name,
                     as_attachment=not f.mime_type.startswith('image/'))
    resp.headers['X-Content-Type-Options'] = 'nosniff'
    return resp

@app.route('/admin/incidents/<int:incident_id>/review', methods=['POST'])
@admin_required
def admin_incident_review(incident_id):
    from models.technician_models import IncidentReport

    r = IncidentReport.query.get_or_404(incident_id)
    status = request.form.get('status')
    if status not in ('reviewing', 'resolved'):
        flash('Invalid status.', 'danger')
        return redirect(url_for('admin_technician_activity'))

    r.status = status
    r.reviewed_by = session.get('username')
    r.reviewed_at = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
    db.session.commit()
    create_notification(
        r.technician_id, 'Incident Report Updated',
        f'Your incident report #{r.id} is now: {status}.', 'info', role='technician'
    )
    flash('Incident updated.', 'success')
    return redirect(url_for('admin_technician_activity'))

# Settings the admin Settings page may write, with their validators.
# Anything else in the request (including csrf_token) is ignored.
EDITABLE_SETTINGS = {
    'system_name':      lambda v: 0 < len(v) <= 100,
    'system_email':     lambda v: len(v) <= 120 and re.fullmatch(r'[^@\s]+@[^@\s]+\.[^@\s]+', v),
    'default_currency': lambda v: v in ('PHP', 'USD', 'EUR'),
    'timezone':         lambda v: v in ('Asia/Manila', 'Asia/Singapore', 'America/New_York'),
    'gcash_account':    lambda v: len(v) <= 30,
    'service_fee':      lambda v: re.fullmatch(r'\d{1,2}(\.\d{1,2})?|100', v),
    'enable_gcash':     lambda v: v in ('true', 'false'),
    'enable_cod':       lambda v: v in ('true', 'false'),
    # Public business details shown on the home, support and payment pages.
    # Blank means "don't show it" - no placeholder numbers are ever displayed.
    'contact_phone':    lambda v: len(v) <= 40 and re.fullmatch(r'[0-9+()\- ]*', v),
    'contact_email':    lambda v: v == '' or (len(v) <= 120 and re.fullmatch(r'[^@\s]+@[^@\s]+\.[^@\s]+', v)),
    'contact_address':  lambda v: len(v) <= 200,
    'business_hours':   lambda v: len(v) <= 100,
    'gcash_name':       lambda v: len(v) <= 100,
}

@app.route('/admin/settings')
@admin_required
def admin_settings():
    values = {row.setting_key: row.value for row in SystemSetting.query.all()}
    return render_template('admin/settings.html', settings=values)

@app.route('/admin/settings/update', methods=['POST'])
@admin_required
def admin_settings_update():
    data = request.get_json(silent=True) or {}
    updates = {}
    for key, valid in EDITABLE_SETTINGS.items():
        if key not in data:
            continue
        value = str(data[key]).strip()
        if not valid(value):
            return jsonify({'success': False, 'message': f'Invalid value for {key.replace("_", " ")}.'}), 400
        updates[key] = value
    for key, value in updates.items():
        setting = SystemSetting.query.filter_by(setting_key=key).first()
        if setting:
            setting.value = value
            setting.updated_at = datetime.utcnow()
        else:
            db.session.add(SystemSetting(setting_key=key, value=value))
    db.session.commit()
    log_activity(session.get('user_id'), 'settings_update', f'Updated settings: {", ".join(sorted(updates)) or "none"}')
    return jsonify({'success': True, 'message': 'Settings saved.'})

# ==================== ERROR HANDLERS ====================

@app.errorhandler(404)
def page_not_found(error):
    return render_template('errors/404.html'), 404

@app.errorhandler(500)
def internal_error(error):
    db.session.rollback()
    return render_template('errors/500.html'), 500

# ==================== INIT DATABASE ====================

def move_legacy_receipts():
    """Receipts used to be saved under static/, where anyone could fetch them.
    Move them to the private folder that receipt_file() serves from."""
    if not os.path.isdir(LEGACY_RECEIPT_FOLDER):
        return
    for name in os.listdir(LEGACY_RECEIPT_FOLDER):
        src = os.path.join(LEGACY_RECEIPT_FOLDER, name)
        dst = os.path.join(app.config['RECEIPT_UPLOAD_FOLDER'], name)
        if os.path.isfile(src) and not os.path.exists(dst):
            shutil.move(src, dst)

CART_STOCK_MIGRATION_KEY = 'cart_stock_released_v1'

def release_reserved_cart_stock():
    """One-time migration. Stock used to be deducted when an item was added to
    a cart; it is now deducted at checkout. Give back what open carts were
    holding, exactly once (guarded by a system_settings flag).
    Returns the number of units released, or None if it already ran."""
    if SystemSetting.query.filter_by(setting_key=CART_STOCK_MIGRATION_KEY).first():
        return None
    released = 0
    open_items = CartItem.query.join(ShoppingCart, CartItem.cart_id == ShoppingCart.id)\
        .filter(ShoppingCart.status == 'active').all()
    for item in open_items:
        product = db.session.get(Product, item.product_id)
        if product and item.quantity and item.quantity > 0:
            product.stock_quantity += item.quantity
            released += item.quantity
    db.session.add(SystemSetting(setting_key=CART_STOCK_MIGRATION_KEY, value=str(released),
                                 description='Units returned to stock when cart reservations were removed'))
    db.session.commit()
    cache.delete('active_products')
    return released

def init_db():
    with app.app_context():
        move_legacy_receipts()
        db.create_all()
        print("Tables created successfully")
        
        # Create messages table
        create_messages_table()
        
        # Create support tickets table
        create_support_tickets_table()
        
        # Update payment_method column
        update_payment_method_column()

        # Self-healing schema patches for columns added after the initial
        # release. Safe to run every startup - each is a no-op once the
        # column/constraint already exists.
        add_receipt_image_column()
        add_service_category_columns()
        add_profile_columns()
        add_workflow_columns()
        
        # No default admin is ever created here. Create one with
        # `flask --app app create-admin` (or /setup/first-admin with SETUP_TOKEN).
        if not Admin.query.first():
            print("No admin account exists yet. Create one with: flask --app app create-admin")

        # Add service categories
        if ServiceCategory.query.count() == 0:
            categories = [
                ServiceCategory(name='Hardware Repair', description='Physical hardware issues and repairs', icon='fa-server'),
                ServiceCategory(name='Software Fix', description='Software issues and optimization', icon='fa-code'),
                ServiceCategory(name='Hardware Upgrade', description='Component upgrades and installation', icon='fa-microchip'),
                ServiceCategory(name='Data Recovery', description='Recover lost or corrupted data', icon='fa-search-plus'),
                ServiceCategory(name='Storage Upgrade', description='SSD and HDD upgrades', icon='fa-hdd'),
                ServiceCategory(name='Accessory Replacement', description='Replace damaged accessories', icon='fa-plug')
            ]
            db.session.add_all(categories)
            db.session.flush()
            
            services = [
                Service(category_id=categories[0].id, name='Laptop Screen Replacement', description='Replace cracked or damaged laptop screen', price=3500.00, estimated_hours=2),
                Service(category_id=categories[0].id, name='Battery Replacement', description='Replace faulty laptop or desktop battery', price=1800.00, estimated_hours=1),
                Service(category_id=categories[1].id, name='Virus Removal', description='Remove viruses and malware', price=1500.00, estimated_hours=2),
                Service(category_id=categories[1].id, name='System Optimization', description='Optimize system performance', price=1200.00, estimated_hours=1),
                Service(category_id=categories[2].id, name='RAM Upgrade', description='Install new RAM modules', price=2500.00, estimated_hours=1),
                Service(category_id=categories[2].id, name='SSD Installation', description='Install new SSD drive', price=3200.00, estimated_hours=2),
                Service(category_id=categories[3].id, name='Data Recovery', description='Recover lost files from hard drives', price=5000.00, estimated_hours=3),
                Service(category_id=categories[4].id, name='HDD to SSD Migration', description='Migrate data from HDD to SSD', price=3200.00, estimated_hours=2),
                Service(category_id=categories[5].id, name='Charger Adapter Replacement', description='Replace faulty charger adapter', price=1200.00, estimated_hours=1)
            ]
            db.session.add_all(services)
            print("Default services added successfully!")
        
        # No sample products: the shop's real inventory is added in Admin > Products.

        # Add system settings
        # Add each default that is missing (never overwrites an admin's value).
        # Checked per key, not "table is empty", because migration flags such
        # as CART_STOCK_MIGRATION_KEY also live in this table.
        default_settings = [
            ('system_name', 'DEVTech Computer Services', 'System name displayed throughout'),
            ('system_email', 'admin@devtech.com', 'Primary system email'),
            ('default_currency', 'PHP', 'Default currency for transactions'),
            ('timezone', 'Asia/Manila', 'System timezone'),
            ('service_fee', '5', 'Service fee percentage'),
            ('gcash_account', '0917 123 4567', 'GCash account number'),
            ('enable_gcash', 'true', 'Enable GCash payments'),
            ('enable_cod', 'true', 'Enable Cash on Delivery'),
            ('contact_address', 'Tacloban City, Leyte', 'Shop address shown to customers'),
        ]
        existing_keys = {s.setting_key for s in SystemSetting.query.all()}
        missing = [SystemSetting(setting_key=k, value=v, description=d)
                   for k, v, d in default_settings if k not in existing_keys]
        if missing:
            db.session.add_all(missing)
            print(f"Added {len(missing)} default setting(s).")
        
        db.session.commit()

        released = release_reserved_cart_stock()
        if released:
            print(f"Returned {released} unit(s) held in open carts to product stock.")
        print("Database initialized successfully!")

# ==================== TECHNICIAN BLUEPRINTS ====================
# Registered here (after app, db, csrf, limiter and all models exist) so the
# blueprints can import from this module without a circular-import error.
from blueprints.technician import technician_bp
from blueprints.technician_api import technician_api_bp

app.register_blueprint(technician_bp, url_prefix='/technician')
app.register_blueprint(technician_api_bp, url_prefix='/technician/api')

# CLI: flask --app app create-admin | list-admins | deactivate-admin | activate-admin | ...
register_commands(app)


if __name__ == '__main__':
    with app.app_context():
        init_db()
        
    dev_host = os.environ.get('DEV_HOST', '127.0.0.1')
    # DEV_SSL=1 serves a self-signed HTTPS cert (needed for OAuth callbacks).
    ssl_context = 'adhoc' if os.environ.get('DEV_SSL') == '1' else None
    app.run(debug=app.config['DEBUG'], host=dev_host, port=5000, ssl_context=ssl_context)