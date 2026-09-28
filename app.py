from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_bcrypt import Bcrypt
from functools import wraps
import os
import sys
import logging
from logging.handlers import RotatingFileHandler
from datetime import datetime, timedelta
import re
import secrets
from werkzeug.utils import secure_filename
from sqlalchemy import text, or_, and_
from markupsafe import escape as escape_markupsafe
import json
from flask import json
from dotenv import load_dotenv
from authlib.integrations.flask_client import OAuth
from flask_wtf import CSRFProtect
from flask_wtf.csrf import CSRFError
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_caching import Cache
from flask_talisman import Talisman
import secrets as _setup_secrets
from commands import register_commands

load_dotenv()

# ==================== ENVIRONMENT ====================
# FLASK_ENV drives every security-sensitive default below. Locally this is
# 'development' (matching everything set up earlier in this project - HTTP
# fallback, relaxed cookies, verbose errors). In production it MUST be set
# to 'production' in the real .env file - that one flag switches on secure
# cookies, forced HTTPS, and hides stack traces from visitors.
IS_PRODUCTION = os.environ.get('FLASK_ENV', 'development') == 'production'


app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'admin@DEVTech094630.com')
if IS_PRODUCTION and app.config['SECRET_KEY'] == 'admin@DEVTech094630.com':
    raise RuntimeError(
        'Refusing to start in production with the default SECRET_KEY. '
        'Set a real random SECRET_KEY in your production .env file.'
    )

app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get(
    'DATABASE_URL', 'mysql+pymysql://root:admin123@localhost/devtech_db'
)
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
# Recycle stale DB connections and verify them before use - without this, a
# production app left running for hours will start throwing
# "MySQL server has gone away" errors once idle connections time out.
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
    'pool_recycle': 280,
    'pool_pre_ping': True,
}
app.config['UPLOAD_FOLDER'] = 'static/uploads'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024
app.config['DEBUG'] = not IS_PRODUCTION

# ---- Session cookie hardening ----
app.config['SESSION_COOKIE_HTTPONLY'] = True          # JS can never read the session cookie
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'         # blocks it being sent on cross-site requests
app.config['SESSION_COOKIE_SECURE'] = IS_PRODUCTION   # browser refuses to send it over plain HTTP
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=7)

# ==================== LOGGING ====================
# Real deployments should never rely on print() - it's invisible once the
# process is backgrounded under gunicorn/systemd. This writes rotating
# logs (5MB x 5 files) alongside stdout, and only shows Flask's interactive
# debugger/tracebacks when NOT running in production.
if not app.debug:
    os.makedirs('logs', exist_ok=True)
    file_handler = RotatingFileHandler('logs/devtech.log', maxBytes=5 * 1024 * 1024, backupCount=5)
    file_handler.setFormatter(logging.Formatter(
        '%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]'
    ))
    file_handler.setLevel(logging.INFO)
    app.logger.addHandler(file_handler)
    app.logger.setLevel(logging.INFO)
    app.logger.info('DEVTech startup (production mode)')

# ==================== CSRF PROTECTION ====================
# Protects every POST/PUT/PATCH/DELETE route (both plain <form> submissions
# and the JS fetch() calls used throughout the shop/orders/admin panel)
# against Cross-Site Request Forgery. Plain forms carry the token via the
# hidden csrf_token field added to each <form>; fetch() calls carry it via
# the X-CSRFToken header, attached automatically by the fetch patch in
# user.js/admin.js reading the <meta name="csrf-token"> tag in each base
# template.
csrf = CSRFProtect(app)

@app.errorhandler(CSRFError)
def handle_csrf_error(e):
    if request.path.startswith('/api/'):
        return jsonify({'success': False, 'message': 'Your session security token expired. Please refresh the page and try again.'}), 400
    flash('Your form session expired. Please try again.', 'danger')
    return redirect(request.referrer or url_for('home'))

# ==================== RATE LIMITING ====================
# Blunt but effective brute-force defense on the endpoints that matter most:
# login forms and account creation. Limits are per-IP. In production, point
# storage_uri at Redis (RATELIMIT_STORAGE_URI) so limits are shared across
# multiple worker processes - the in-memory default only tracks requests
# seen by that one process, which is fine for local development only.
limiter = Limiter(
    key_func=get_remote_address,
    app=app,
    default_limits=['200 per hour'],
    storage_uri=os.environ.get('RATELIMIT_STORAGE_URI', 'memory://'),
)

# ==================== CACHING ====================
# Cuts repeated database load for data that doesn't change every request -
# the shop's product listing and the admin dashboard's analytics queries
# are the two most expensive, most frequently hit reads in the app. Uses
# SimpleCache (in-process) by default; set CACHE_TYPE=RedisCache in .env
# for a real multi-worker production deployment, since SimpleCache is not
# shared between gunicorn worker processes.
cache = Cache(app, config={
    'CACHE_TYPE': os.environ.get('CACHE_TYPE', 'SimpleCache'),
    'CACHE_REDIS_URL': os.environ.get('CACHE_REDIS_URL', ''),
    'CACHE_DEFAULT_TIMEOUT': 60,
})

# ==================== SECURITY HEADERS ====================
# Sends the standard hardening headers a real browser-facing site needs:
# HSTS, X-Content-Type-Options, X-Frame-Options (clickjacking defense), and
# a Content-Security-Policy scoped to the exact third-party origins this
# app actually uses (Font Awesome + Google Fonts). force_https is only
# enabled in production so local HTTP/self-signed-HTTPS development (see
# the mkcert/adhoc setup earlier in this project) keeps working unchanged.
csp = {
    'default-src': "'self'",
    'style-src': ["'self'", "'unsafe-inline'", 'https://cdnjs.cloudflare.com', 'https://fonts.googleapis.com'],
    'font-src': ["'self'", 'https://cdnjs.cloudflare.com', 'https://fonts.gstatic.com'],
    'script-src': ["'self'", "'unsafe-inline'"],
    'img-src': ["'self'", 'data:', 'https:'],
    'connect-src': "'self'",
}
Talisman(
    app,
    force_https=IS_PRODUCTION,
    strict_transport_security=IS_PRODUCTION,
    session_cookie_secure=IS_PRODUCTION,
    content_security_policy=csp,
)

# ==================== HEALTH CHECK ====================
# Used by a load balancer, uptime monitor, or `docker healthcheck` to
# verify the app (and its database connection) are actually up - not just
# that the process is running. Deliberately unauthenticated and minimal.
@app.route('/healthz')
def healthz():
    try:
        db.session.execute(text('SELECT 1'))
        return jsonify({'status': 'ok', 'database': 'connected'}), 200
    except Exception as e:
        app.logger.error(f'Health check failed: {e}')
        return jsonify({'status': 'error', 'database': 'unreachable'}), 503

# ==================== OAUTH (Google / Facebook) ====================
oauth = OAuth(app)

oauth.register(
    name='google',
    client_id=os.environ.get('GOOGLE_CLIENT_ID'),
    client_secret=os.environ.get('GOOGLE_CLIENT_SECRET'),
    server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
    client_kwargs={'scope': 'openid email profile'},
)

oauth.register(
    name='facebook',
    client_id=os.environ.get('FACEBOOK_CLIENT_ID'),
    client_secret=os.environ.get('FACEBOOK_CLIENT_SECRET'),
    access_token_url='https://graph.facebook.com/v19.0/oauth/access_token',
    authorize_url='https://www.facebook.com/v19.0/dialog/oauth',
    api_base_url='https://graph.facebook.com/v19.0/',
    client_kwargs={'scope': 'email public_profile'},
)

app.jinja_env.filters['tojson'] = lambda obj: json.dumps(obj, default=str)
app.jinja_env.filters['escape'] = lambda s: escape_markupsafe(s) if s else ''


os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# Allowed file extensions for receipts
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'pdf'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# Real magic-byte signatures for each allowed type. Checking only the file
# extension (allowed_file above) is trivially spoofed - renaming
# malware.exe to receipt.jpg sails straight through an extension check.
# This reads the file's actual first bytes and confirms they match what
# the claimed extension promises before anything gets saved to disk.
FILE_SIGNATURES = {
    'png': [b'\x89PNG\r\n\x1a\n'],
    'jpg': [b'\xff\xd8\xff'],
    'jpeg': [b'\xff\xd8\xff'],
    'gif': [b'GIF87a', b'GIF89a'],
    'pdf': [b'%PDF-'],
}
MAX_RECEIPT_SIZE = 5 * 1024 * 1024  # 5MB - tighter than the 16MB global request cap

def validate_uploaded_file(file_storage, extension):
    """Returns (is_valid, error_message). Checks actual file content
    against the claimed extension's magic bytes, and enforces a per-file
    size cap independent of the app-wide MAX_CONTENT_LENGTH."""
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

db = SQLAlchemy(app)
bcrypt = Bcrypt(app)

# ==================== DATABASE MODELS ====================

class User(db.Model):
    __tablename__ = 'users'
    __table_args__ = (
        db.UniqueConstraint('oauth_provider', 'oauth_id', name='uq_users_oauth_identity'),
    )
    
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    full_name = db.Column(db.String(100), nullable=False)
    phone = db.Column(db.String(20))
    address = db.Column(db.String(255))
    city = db.Column(db.String(50))
    province = db.Column(db.String(50))
    postal_code = db.Column(db.String(10))
    latitude = db.Column(db.Numeric(10, 7))
    longitude = db.Column(db.Numeric(10, 7))
    birth_date = db.Column(db.Date)
    role = db.Column(db.String(20), default='customer')
    is_active = db.Column(db.Boolean, default=True)
    oauth_provider = db.Column(db.String(20), nullable=True)
    oauth_id = db.Column(db.String(255), nullable=True)
    last_active = db.Column(db.DateTime, nullable=True)
    # ---- Technician identity verification ----
    # id_number is stored ONLY for internal admin verification records - it
    # is never serialized to any customer-facing API response or template.
    # Customers only ever see the boolean id_verified badge, never the
    # number itself. Storing a government ID number is sensitive personal
    # data under most data-privacy laws (e.g. the Philippines' Data Privacy
    # Act, RA 10173) - real-world platforms verify identity internally and
    # expose only a verified/unverified status externally.
    id_type = db.Column(db.String(30), nullable=True)      # e.g. 'National ID', 'Driver's License', 'Passport'
    id_number = db.Column(db.String(50), nullable=True)    # admin-only, never exposed via API/templates to customers
    id_verified = db.Column(db.Boolean, default=False)
    id_verified_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    bookings = db.relationship('Booking', backref='user', lazy=True, foreign_keys='Booking.user_id')
    transactions = db.relationship('Transaction', backref='user', lazy=True, foreign_keys='Transaction.user_id')
    notifications = db.relationship('Notification', backref='user', lazy=True)
    sent_messages = db.relationship('Message', foreign_keys='Message.sender_id', backref='sender', lazy=True)
    received_messages = db.relationship('Message', foreign_keys='Message.recipient_id', backref='recipient', lazy=True)
    support_tickets = db.relationship('SupportTicket', backref='user', lazy=True)
    shopping_carts = db.relationship('ShoppingCart', backref='user', lazy=True)
    orders = db.relationship('Order', backref='user', lazy=True)
    preferences = db.relationship('UserPreference', backref='user', uselist=False)
    
    def set_password(self, password):
        self.password_hash = bcrypt.generate_password_hash(password).decode('utf-8')
    
    def check_password(self, password):
        return bcrypt.check_password_hash(self.password_hash, password)
    
    def to_dict(self):
        return {
            'id': self.id,
            'username': self.username,
            'email': self.email,
            'full_name': self.full_name,
            'phone': self.phone,
            'address': self.address,
            'city': self.city,
            'province': self.province,
            'postal_code': self.postal_code,
            'role': self.role,
            'is_active': self.is_active,
            'created_at': self.created_at.strftime('%Y-%m-%d %H:%M:%S') if self.created_at else None
        }

class ServiceCategory(db.Model):
    __tablename__ = 'service_categories'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True, nullable=False)
    description = db.Column(db.Text)
    icon = db.Column(db.String(50))
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
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
    
    id = db.Column(db.Integer, primary_key=True)
    booking_number = db.Column(db.String(50), unique=True, nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    service_id = db.Column(db.Integer, db.ForeignKey('services.id'), nullable=False)
    device_type = db.Column(db.String(50), nullable=False)
    description = db.Column(db.Text, nullable=False)
    address = db.Column(db.String(255))
    booking_date = db.Column(db.Date, nullable=False)
    booking_time = db.Column(db.Time, nullable=False)
    status = db.Column(db.String(20), default='pending')
    is_in_shop = db.Column(db.Boolean, default=False)
    technician_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    assigned_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    transaction = db.relationship('Transaction', backref='booking', uselist=False, foreign_keys='Transaction.booking_id')
    technician = db.relationship('User', foreign_keys=[technician_id])

class Transaction(db.Model):
    __tablename__ = 'transactions'
    
    id = db.Column(db.Integer, primary_key=True)
    transaction_number = db.Column(db.String(50), unique=True, nullable=False)
    booking_id = db.Column(db.Integer, db.ForeignKey('bookings.id'), nullable=True)
    order_id = db.Column(db.Integer, db.ForeignKey('orders.id'), nullable=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    amount = db.Column(db.Numeric(10, 2), nullable=False)
    payment_method = db.Column(db.String(50), nullable=False)
    payment_status = db.Column(db.String(20), default='pending')
    reference_number = db.Column(db.String(50))
    gcash_reference = db.Column(db.String(50))
    receipt_image = db.Column(db.String(255))
    rejection_reason = db.Column(db.Text)
    transaction_date = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    order = db.relationship('Order', backref='transactions')

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
    __tablename__ = 'notifications'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    title = db.Column(db.String(100), nullable=False)
    message = db.Column(db.Text, nullable=False)
    type = db.Column(db.String(20), default='info')
    is_read = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Message(db.Model):
    __tablename__ = 'messages'
    
    id = db.Column(db.Integer, primary_key=True)
    sender_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    recipient_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    subject = db.Column(db.String(200))
    content = db.Column(db.Text, nullable=False)
    is_read = db.Column(db.Boolean, default=False)
    parent_id = db.Column(db.Integer, db.ForeignKey('messages.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    replies = db.relationship('Message', backref=db.backref('parent', remote_side=[id]), lazy=True)

class SupportTicket(db.Model):
    __tablename__ = 'support_tickets'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    subject = db.Column(db.String(200), nullable=False)
    message = db.Column(db.Text, nullable=False)
    category = db.Column(db.String(50), default='general')
    status = db.Column(db.String(20), default='open')
    admin_response = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class ActivityLog(db.Model):
    __tablename__ = 'activity_logs'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    action = db.Column(db.String(100), nullable=False)
    details = db.Column(db.Text)
    ip_address = db.Column(db.String(45))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

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
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    status = db.Column(db.String(20), default='active')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    items = db.relationship('CartItem', backref='cart', lazy=True, cascade='all, delete-orphan')

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
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    order_number = db.Column(db.String(50), unique=True, nullable=False)
    total_amount = db.Column(db.Numeric(10, 2), nullable=False)
    status = db.Column(db.String(20), default='pending')
    # Legacy single-line formatted address, kept for backward compatibility
    # with any code/reports that already read this column directly.
    shipping_address = db.Column(db.String(255))
    # Structured delivery-address snapshot, captured at the moment the order
    # is placed. This deliberately duplicates data that also lives on the
    # User row: if the customer edits their profile address later, past
    # orders must keep showing the address the rider was actually given.
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

class OrderItem(db.Model):
    __tablename__ = 'order_items'
    
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey('orders.id'), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False)
    quantity = db.Column(db.Integer, default=1)
    price = db.Column(db.Numeric(10, 2), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class UserPreference(db.Model):
    __tablename__ = 'user_preferences'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, unique=True)
    language = db.Column(db.String(10), default='en')
    theme = db.Column(db.String(20), default='light')
    email_notifications = db.Column(db.Boolean, default=True)
    sms_notifications = db.Column(db.Boolean, default=False)
    booking_reminders = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

# ==================== DECORATORS ====================

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
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
        user = User.query.get(session['user_id'])
        if not user or user.role != 'admin':
            flash('Admin access required.', 'danger')
            return redirect(url_for('home'))
        return f(*args, **kwargs)
    return decorated_function

@app.before_request
def track_user_presence():
    """Stamp last_active on every request from a logged-in session, so
    User Management can show accurate online/offline status. Cheap
    single-column UPDATE, not a full model load."""
    if request.endpoint == 'static':
        return
    user_id = session.get('user_id')
    if not user_id:
        return
    try:
        User.query.filter_by(id=user_id).update({'last_active': datetime.utcnow()})
        db.session.commit()
    except Exception:
        db.session.rollback()

@app.route('/api/ping', methods=['POST'])
def api_ping():
    """Lightweight heartbeat the frontend calls periodically. The actual
    last_active stamp happens in track_user_presence() above - this just
    guarantees a request goes out even on an otherwise idle page."""
    return jsonify({'ok': True})

@app.route('/api/admin/session-check')
def api_admin_session_check():
    """Used by the admin auto-refresh before it reloads a page. Sessions
    are one cookie per browser, so logging in/out as a different account
    in another tab silently changes what this tab is authenticated as
    too. Without this check, auto-refresh would just blindly reload and
    the admin would get bounced to the public homepage every few seconds
    with no explanation - this lets the frontend detect that and show a
    clear message instead."""
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({'ok': False, 'reason': 'logged_out'}), 401
    user = User.query.get(user_id)
    if not user or user.role != 'admin' or not user.is_active:
        return jsonify({'ok': False, 'reason': 'not_admin'}), 401
    return jsonify({'ok': True})

# ==================== HELPER FUNCTIONS ====================

def generate_booking_number():
    prefix = 'BK'
    date_str = datetime.utcnow().strftime('%y%m%d')
    last_booking = Booking.query.order_by(Booking.id.desc()).first()
    if last_booking:
        try:
            num = int(last_booking.booking_number[8:]) + 1
        except:
            num = 1
    else:
        num = 1
    if num > 9999:
        num = 1
    return f"{prefix}{date_str}{str(num).zfill(4)}"

def generate_transaction_number():
    prefix = 'TRX'
    date_str = datetime.utcnow().strftime('%y%m%d')
    last_transaction = Transaction.query.order_by(Transaction.id.desc()).first()
    if last_transaction:
        try:
            num = int(last_transaction.transaction_number[9:]) + 1
        except:
            num = 1
    else:
        num = 1
    if num > 9999:
        num = 1
    return f"{prefix}{date_str}{str(num).zfill(4)}"

def calculate_trend(model, date_column, extra_filter=None, days=7):
    """Real, data-driven trend for a dashboard stat card.

    Rather than a raw week-over-week ratio (which explodes to things like
    '1300%' when last week only had 1 record), this reports what share of
    the ENTIRE dataset arrived in the current window - a bounded 0-100%
    figure that scales sensibly however small or large the real user base
    is. Direction (up/down/flat) still reflects whether this window grew
    or shrank versus the one before it.
    """
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
    return {'percent': percent, 'direction': direction}

def create_notification(user_id, title, message, type='info'):
    notification = Notification(
        user_id=user_id,
        title=title,
        message=message,
        type=type
    )
    db.session.add(notification)
    db.session.commit()
    return notification

def log_activity(user_id, action, details=None, ip_address=None):
    log = ActivityLog(
        user_id=user_id,
        action=action,
        details=details,
        ip_address=ip_address or request.remote_addr
    )
    db.session.add(log)
    db.session.commit()

# ==================== CREATE TABLES FUNCTION ====================

def create_messages_table():
    """Create messages table if it doesn't exist"""
    with app.app_context():
        try:
            result = db.session.execute(text("SHOW TABLES LIKE 'messages'")).fetchone()
            
            if not result:
                db.session.execute(text("""
                    CREATE TABLE messages (
                        id INT PRIMARY KEY AUTO_INCREMENT,
                        sender_id INT NOT NULL,
                        recipient_id INT NOT NULL,
                        subject VARCHAR(200),
                        content TEXT NOT NULL,
                        is_read BOOLEAN DEFAULT FALSE,
                        parent_id INT NULL,
                        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (sender_id) REFERENCES users(id),
                        FOREIGN KEY (recipient_id) REFERENCES users(id),
                        FOREIGN KEY (parent_id) REFERENCES messages(id)
                    )
                """))
                db.session.commit()
                print("✅ Messages table created successfully!")
                return True
            else:
                print("ℹ️ Messages table already exists.")
                return True
        except Exception as e:
            print(f"❌ Error creating messages table: {e}")
            db.session.rollback()
            return False

def create_support_tickets_table():
    """Create support_tickets table if it doesn't exist"""
    with app.app_context():
        try:
            result = db.session.execute(text("SHOW TABLES LIKE 'support_tickets'")).fetchone()
            
            if not result:
                db.session.execute(text("""
                    CREATE TABLE support_tickets (
                        id INT PRIMARY KEY AUTO_INCREMENT,
                        user_id INT NOT NULL,
                        subject VARCHAR(200) NOT NULL,
                        message TEXT NOT NULL,
                        category VARCHAR(50) DEFAULT 'general',
                        status VARCHAR(20) DEFAULT 'open',
                        admin_response TEXT,
                        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                        FOREIGN KEY (user_id) REFERENCES users(id)
                    )
                """))
                db.session.commit()
                print("✅ Support tickets table created successfully!")
                return True
            else:
                print("ℹ️ Support tickets table already exists.")
                return True
        except Exception as e:
            print(f"❌ Error creating support tickets table: {e}")
            db.session.rollback()
            return False

def update_payment_method_column():
    """Update payment_method column to VARCHAR(50)"""
    with app.app_context():
        try:
            db.session.execute(text(
                "ALTER TABLE transactions MODIFY COLUMN payment_method VARCHAR(50) NOT NULL"
            ))
            db.session.commit()
            print("✅ Payment method column updated to VARCHAR(50)!")
            return True
        except Exception as e:
            print(f"ℹ️ Payment method column already updated or error: {e}")
            return False

def add_receipt_image_column():
    """Add receipt_image column to transactions if it doesn't exist"""
    with app.app_context():
        try:
            db.session.execute(text(
                "ALTER TABLE transactions ADD COLUMN receipt_image VARCHAR(255) NULL"
            ))
            db.session.commit()
            print("✅ Receipt image column added to transactions!")
            return True
        except Exception as e:
            print(f"ℹ️ Receipt image column already exists or error: {e}")
            return False

def add_oauth_columns():
    """Add Google/Facebook login columns to users if they don't exist.
    Required by /login/google and /login/facebook - without these, OAuth
    sign-in raises 'Unknown column' errors on any database created before
    social login was added."""
    with app.app_context():
        try:
            db.session.execute(text(
                "ALTER TABLE users ADD COLUMN oauth_provider VARCHAR(20) NULL, "
                "ADD COLUMN oauth_id VARCHAR(255) NULL"
            ))
            db.session.commit()
            print("✅ OAuth columns added to users!")
        except Exception as e:
            db.session.rollback()
            print(f"ℹ️ OAuth columns already exist or error: {e}")
        try:
            db.session.execute(text(
                "ALTER TABLE users ADD CONSTRAINT uq_users_oauth_identity "
                "UNIQUE (oauth_provider, oauth_id)"
            ))
            db.session.commit()
            print("✅ OAuth uniqueness constraint added to users!")
        except Exception as e:
            db.session.rollback()
            print(f"ℹ️ OAuth uniqueness constraint already exists or error: {e}")

def add_order_address_columns():
    """Add the delivery-address snapshot columns to orders if they don't
    exist. Required by the order-details view in /user/orders - without
    these, every past order shows a blank delivery address."""
    with app.app_context():
        columns = [
            ("recipient_name", "VARCHAR(100) NULL"),
            ("recipient_phone", "VARCHAR(20) NULL"),
            ("address_line", "VARCHAR(255) NULL"),
            ("city", "VARCHAR(50) NULL"),
            ("province", "VARCHAR(50) NULL"),
            ("postal_code", "VARCHAR(10) NULL"),
            ("latitude", "DECIMAL(10,7) NULL"),
            ("longitude", "DECIMAL(10,7) NULL"),
        ]
        added_any = False
        for col_name, col_def in columns:
            try:
                db.session.execute(text(
                    f"ALTER TABLE orders ADD COLUMN {col_name} {col_def}"
                ))
                db.session.commit()
                added_any = True
            except Exception as e:
                db.session.rollback()
                # Column already exists - expected on every run after the first.
        if added_any:
            print("✅ Delivery-address snapshot columns added to orders!")
            # Backfill existing rows from the user's current profile so
            # orders placed before this migration aren't left blank.
            try:
                db.session.execute(text("""
                    UPDATE orders o
                    JOIN users u ON u.id = o.user_id
                    SET
                        o.recipient_name = COALESCE(o.recipient_name, u.full_name),
                        o.recipient_phone = COALESCE(o.recipient_phone, u.phone),
                        o.address_line = COALESCE(o.address_line, u.address),
                        o.city = COALESCE(o.city, u.city),
                        o.province = COALESCE(o.province, u.province),
                        o.postal_code = COALESCE(o.postal_code, u.postal_code),
                        o.latitude = COALESCE(o.latitude, u.latitude),
                        o.longitude = COALESCE(o.longitude, u.longitude)
                    WHERE o.address_line IS NULL
                """))
                db.session.commit()
                print("✅ Backfilled delivery addresses for existing orders!")
            except Exception as e:
                db.session.rollback()
                print(f"ℹ️ Backfill skipped or error: {e}")
        else:
            print("ℹ️ Order address columns already exist")

def add_user_presence_columns():
    """Add the last_active tracking column to users if it doesn't exist.
    Powers the online/offline status and 'time ago' display in User
    Management. Safe to run every startup - no-op once it's there."""
    with app.app_context():
        try:
            db.session.execute(text(
                "ALTER TABLE users ADD COLUMN last_active DATETIME NULL"
            ))
            db.session.commit()
            print("✅ last_active column added to users!")
        except Exception as e:
            db.session.rollback()
            print(f"ℹ️ last_active column already exists or error: {e}")

# How recently a user must have pinged the server to count as "online".
# Paired with a ~25s heartbeat from the browser, so this comfortably
# covers one missed beat without flickering between online/offline.
PRESENCE_ONLINE_WINDOW_SECONDS = 60

def format_time_ago(dt):
    """Human-readable elapsed time - seconds/minutes/hours/days/weeks/
    months/years ago - for a UTC datetime. Mirrors the JS formatter used
    for live (no-refresh) updates in User Management."""
    if not dt:
        return None
    seconds = int((datetime.utcnow() - dt).total_seconds())
    if seconds < 0:
        seconds = 0
    if seconds < 5:
        return 'just now'
    if seconds < 60:
        return f"{seconds} second{'s' if seconds != 1 else ''} ago"
    minutes = seconds // 60
    if minutes < 60:
        return f"{minutes} minute{'s' if minutes != 1 else ''} ago"
    hours = minutes // 60
    if hours < 24:
        return f"{hours} hour{'s' if hours != 1 else ''} ago"
    days = hours // 24
    if days < 7:
        return f"{days} day{'s' if days != 1 else ''} ago"
    weeks = days // 7
    if weeks < 5:
        return f"{weeks} week{'s' if weeks != 1 else ''} ago"
    months = days // 30
    if months < 12:
        return f"{months} month{'s' if months != 1 else ''} ago"
    years = days // 365
    return f"{years} year{'s' if years != 1 else ''} ago"

def is_user_online(last_active):
    if not last_active:
        return False
    return (datetime.utcnow() - last_active).total_seconds() <= PRESENCE_ONLINE_WINDOW_SECONDS

def get_user_presence(user):
    online = is_user_online(user.last_active)
    return {
        'is_online': online,
        'status': 'online' if online else 'offline',
        'last_active': user.last_active.strftime('%Y-%m-%dT%H:%M:%SZ') if user.last_active else None,
        'last_active_display': 'Online now' if online else (
            format_time_ago(user.last_active) if user.last_active else 'Never logged in'
        )
    }

# ==================== AUTH ROUTES ====================

@app.route('/')
def home():
    services = Service.query.filter_by(is_active=True).limit(6).all()
    categories = ServiceCategory.query.filter_by(is_active=True).all()
    return render_template('home.html', services=services, categories=categories)

@app.route('/login', methods=['GET', 'POST'])
@limiter.limit('10 per minute')
def login():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        
        user = User.query.filter_by(email=email).first()
        if user and user.check_password(password):
            if not user.is_active:
                flash('Your account has been deactivated. Please contact support.', 'danger')
                return render_template('auth/login.html')
            
            session['user_id'] = user.id
            session['username'] = user.username
            session['role'] = user.role
            
            log_activity(user.id, 'login', f'User logged in from {request.remote_addr}')
            
            if user.role == 'admin':
                return redirect(url_for('admin_dashboard'))
            return redirect(url_for('user_dashboard'))
        else:
            flash('Invalid email or password.', 'danger')
    
    return render_template('auth/login.html')

@app.route('/register', methods=['GET', 'POST'])
@limiter.limit('5 per minute')
def register():
    if request.method == 'POST':
        full_name = request.form.get('fullName')
        email = request.form.get('email')
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
        
        if User.query.filter_by(email=email).first():
            flash('Email already registered.', 'danger')
            return render_template('auth/register.html')
        
        username = email.split('@')[0]
        if User.query.filter_by(username=username).first():
            username = f"{username}{datetime.utcnow().strftime('%d%m%Y')}"
        
        user = User(
            username=username,
            email=email,
            full_name=full_name,
            phone=phone,
            role='customer'
        )
        user.set_password(password)
        
        db.session.add(user)
        db.session.commit()
        
        create_notification(
            user.id,
            'Welcome to DEVTech!',
            'Thank you for registering. Start booking your repair services today!',
            'success'
        )
        
        flash('Registration successful! Please log in.', 'success')
        return redirect(url_for('login'))
    
    return render_template('auth/register.html')

@app.route('/logout')
def logout():
    if 'user_id' in session:
        log_activity(session['user_id'], 'logout', 'User logged out')
    session.clear()
    flash('You have been logged out.', 'info')
    return redirect(url_for('home'))

# ==================== SOCIAL LOGIN (Google / Facebook) ====================

def _unique_username_from_email(email):
    """Build a username from an email, disambiguating on collision."""
    base = email.split('@')[0]
    username = base
    if User.query.filter_by(username=username).first():
        username = f"{base}{secrets.token_hex(3)}"
    return username

def _login_or_create_oauth_user(provider, provider_id, email, full_name):
    """Find (or create) the local user tied to a Google/Facebook identity,
    then log them in the same way the normal email/password login does."""
    if not email:
        flash('We could not get an email address from your account. Please try a different sign-in method.', 'danger')
        return redirect(url_for('login'))

    user = User.query.filter_by(oauth_provider=provider, oauth_id=provider_id).first()

    is_new_user = False
    if not user:
        # If someone already registered with this email the normal way,
        # link this social identity to that existing account instead of
        # creating a duplicate one.
        user = User.query.filter_by(email=email).first()
        if user:
            user.oauth_provider = user.oauth_provider or provider
            user.oauth_id = user.oauth_id or provider_id
        else:
            user = User(
                username=_unique_username_from_email(email),
                email=email,
                full_name=full_name or email.split('@')[0],
                role='customer',
                oauth_provider=provider,
                oauth_id=provider_id,
            )
            # OAuth accounts don't have a local password; store an unusable
            # random hash so password_hash stays non-null and the account
            # can never be logged into with a guessed password.
            user.password_hash = bcrypt.generate_password_hash(secrets.token_urlsafe(32)).decode('utf-8')
            db.session.add(user)
            is_new_user = True
        db.session.commit()

        if is_new_user:
            create_notification(
                user.id,
                'Welcome to DEVTech!',
                'Thank you for registering. Start booking your repair services today!',
                'success'
            )

    if not user.is_active:
        flash('Your account has been deactivated. Please contact support.', 'danger')
        return redirect(url_for('login'))

    session['user_id'] = user.id
    session['username'] = user.username
    session['role'] = user.role

    log_activity(user.id, 'login', f'User logged in via {provider} from {request.remote_addr}')
    flash(f'Logged in with {provider.title()}.', 'success')

    if user.role == 'admin':
        return redirect(url_for('admin_dashboard'))
    return redirect(url_for('user_dashboard'))

@app.route('/login/google')
def google_login():
    redirect_uri = url_for('google_callback', _external=True)
    return oauth.google.authorize_redirect(redirect_uri)

@app.route('/login/google/callback')
def google_callback():
    try:
        token = oauth.google.authorize_access_token()
    except Exception:
        flash('Google sign-in was cancelled or failed. Please try again.', 'danger')
        return redirect(url_for('login'))

    userinfo = token.get('userinfo')
    if not userinfo:
        userinfo = oauth.google.parse_id_token(token, nonce=None)

    return _login_or_create_oauth_user(
        provider='google',
        provider_id=userinfo['sub'],
        email=userinfo.get('email'),
        full_name=userinfo.get('name'),
    )

@app.route('/login/facebook')
def facebook_login():
    redirect_uri = url_for('facebook_callback', _external=True)
    return oauth.facebook.authorize_redirect(redirect_uri)

@app.route('/login/facebook/callback')
def facebook_callback():
    try:
        token = oauth.facebook.authorize_access_token()
        profile = oauth.facebook.get('me?fields=id,name,email', token=token).json()
    except Exception:
        flash('Facebook sign-in was cancelled or failed. Please try again.', 'danger')
        return redirect(url_for('login'))

    return _login_or_create_oauth_user(
        provider='facebook',
        provider_id=profile['id'],
        email=profile.get('email'),
        full_name=profile.get('name'),
    )

@app.route('/admin/login', methods=['GET', 'POST'])
@limiter.limit('5 per minute')
def admin_login():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        
        user = User.query.filter_by(email=email).first()
        if user and user.check_password(password) and user.role == 'admin' and user.is_active:
            session['user_id'] = user.id
            session['username'] = user.username
            session['role'] = user.role
            
            log_activity(user.id, 'admin_login', f'Admin logged in from {request.remote_addr}')
            flash('Welcome to Admin Dashboard!', 'success')
            return redirect(url_for('admin_dashboard'))
        else:
            flash('Invalid admin credentials or unauthorized access.', 'danger')
    
    return render_template('auth/admin_login.html')

# ==================== USER DASHBOARD ROUTES ====================

@app.route('/user/dashboard')
@login_required
def user_dashboard():
    user_id = session.get('user_id')
    user = User.query.get(user_id)
    bookings = Booking.query.filter_by(user_id=user_id).order_by(Booking.created_at.desc()).limit(5).all()
    transactions = Transaction.query.filter_by(user_id=user_id).order_by(Transaction.transaction_date.desc()).limit(5).all()
    notifications = Notification.query.filter_by(user_id=user_id, is_read=False).order_by(Notification.created_at.desc()).limit(5).all()
    
    unread_messages = 0
    try:
        unread_messages = Message.query.filter_by(recipient_id=user_id, is_read=False).count()
    except Exception as e:
        pass
    
    return render_template('user/user_dashboard.html',
                         user=user,
                         bookings=bookings,
                         transactions=transactions,
                         notifications=notifications,
                         unread_messages=unread_messages)

# ==================== BOOKING STATUS ROUTES ====================

@app.route('/total-bookings')
@login_required
def total_bookings():
    user_id = session.get('user_id')
    bookings = Booking.query.filter_by(user_id=user_id).order_by(Booking.created_at.desc()).all()
    notifications = Notification.query.filter_by(user_id=user_id, is_read=False).order_by(Notification.created_at.desc()).limit(5).all()
    
    return render_template('user/total_bookings.html', 
                         bookings=bookings, 
                         notifications=notifications)

@app.route('/completed-bookings')
@login_required
def completed_bookings():
    user_id = session.get('user_id')
    bookings = Booking.query.filter_by(user_id=user_id, status='completed').order_by(Booking.created_at.desc()).all()
    notifications = Notification.query.filter_by(user_id=user_id, is_read=False).order_by(Notification.created_at.desc()).limit(5).all()
    
    return render_template('user/completed_bookings.html', 
                         bookings=bookings, 
                         notifications=notifications)

@app.route('/inprogress-bookings')
@login_required
def inprogress_bookings():
    user_id = session.get('user_id')
    bookings = Booking.query.filter(
        Booking.user_id == user_id,
        Booking.status.in_(['pending', 'confirmed', 'in_progress'])
    ).order_by(Booking.created_at.desc()).all()
    
    notifications = Notification.query.filter_by(user_id=user_id, is_read=False).order_by(Notification.created_at.desc()).limit(5).all()
    
    return render_template('user/inprogress_bookings.html', 
                         bookings=bookings, 
                         notifications=notifications)

@app.route('/pending-bookings')
@login_required
def pending_bookings():
    user_id = session.get('user_id')
    bookings = Booking.query.filter_by(user_id=user_id, status='pending').order_by(Booking.created_at.desc()).all()
    notifications = Notification.query.filter_by(user_id=user_id, is_read=False).order_by(Notification.created_at.desc()).limit(5).all()
    
    return render_template('user/pending_bookings.html', 
                         bookings=bookings, 
                         notifications=notifications)

@app.route('/rejected-requests')
@login_required
def rejected_requests():
    user_id = session.get('user_id')
    bookings = Booking.query.filter_by(user_id=user_id, status='cancelled').order_by(Booking.created_at.desc()).all()
    notifications = Notification.query.filter_by(user_id=user_id, is_read=False).order_by(Notification.created_at.desc()).limit(5).all()
    
    return render_template('user/rejected_requests.html', 
                         bookings=bookings, 
                         notifications=notifications)

@app.route('/booking/<int:booking_id>/cancel', methods=['POST'])
@login_required
def cancel_booking(booking_id):
    user_id = session.get('user_id')
    booking = Booking.query.get_or_404(booking_id)
    
    if booking.user_id != user_id:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403
    
    if booking.status not in ['pending', 'confirmed']:
        return jsonify({'success': False, 'message': 'This booking cannot be cancelled'}), 400
    
    booking.status = 'cancelled'
    booking.updated_at = datetime.utcnow()
    db.session.commit()
    
    create_notification(
        user_id,
        'Booking Cancelled',
        f'Your booking {booking.booking_number} has been cancelled.',
        'warning'
    )
    
    return jsonify({'success': True, 'message': 'Booking cancelled successfully'})

# ==================== NOTIFICATION ROUTES ====================

@app.route('/notifications')
@login_required
def notifications():
    user_id = session.get('user_id')
    notifications = Notification.query.filter_by(user_id=user_id).order_by(Notification.created_at.desc()).all()
    
    for notif in notifications:
        if not notif.is_read:
            notif.is_read = True
    db.session.commit()
    
    return render_template('user/notification.html', notifications=notifications)

# Add this to app.py after the notification routes

@app.route('/api/notifications/unread-count')
@login_required
def api_notification_unread_count():
    """Get unread notification count for the current user"""
    user_id = session.get('user_id')
    count = Notification.query.filter_by(user_id=user_id, is_read=False).count()
    return jsonify({'count': count})

@app.route('/notification/<int:notification_id>/read', methods=['POST'])
@login_required
def notification_read(notification_id):
    user_id = session.get('user_id')
    notification = Notification.query.get_or_404(notification_id)
    
    if notification.user_id != user_id:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403
    
    notification.is_read = True
    db.session.commit()
    
    return jsonify({'success': True, 'message': 'Notification marked as read'})

@app.route('/notification/mark-all-read', methods=['POST'])
@login_required
def notification_mark_all_read():
    user_id = session.get('user_id')
    notifications = Notification.query.filter_by(user_id=user_id, is_read=False).all()
    
    for notif in notifications:
        notif.is_read = True
    db.session.commit()
    
    return jsonify({'success': True, 'message': 'All notifications marked as read'})

@app.route('/notification/<int:notification_id>/delete', methods=['DELETE'])
@login_required
def notification_delete(notification_id):
    user_id = session.get('user_id')
    notification = Notification.query.get_or_404(notification_id)
    
    if notification.user_id != user_id:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403
    
    db.session.delete(notification)
    db.session.commit()
    
    return jsonify({'success': True, 'message': 'Notification deleted'})

# ==================== MESSAGE ROUTES ====================

@app.route('/messages')
@login_required
def messages():
    user_id = session.get('user_id')
    
    try:
        sent_to = db.session.query(Message.recipient_id).filter_by(sender_id=user_id).distinct().all()
        received_from = db.session.query(Message.sender_id).filter_by(recipient_id=user_id).distinct().all()
        
        conversation_ids = set([r[0] for r in sent_to] + [r[0] for r in received_from])
        conversations = []
        
        for uid in conversation_ids:
            other_user = User.query.get(uid)
            if other_user:
                latest = Message.query.filter(
                    or_(
                        and_(Message.sender_id == user_id, Message.recipient_id == uid),
                        and_(Message.sender_id == uid, Message.recipient_id == user_id)
                    )
                ).order_by(Message.created_at.desc()).first()
                
                unread_count = Message.query.filter_by(sender_id=uid, recipient_id=user_id, is_read=False).count()
                
                conversations.append({
                    'id': uid,
                    'name': other_user.full_name,
                    'last_message': latest.content if latest else 'No messages',
                    'last_time': latest.created_at if latest else datetime.utcnow(),
                    'unread_count': unread_count,
                    'is_active': False,
                    'is_online': False
                })
        
        conversations.sort(key=lambda x: x['last_time'], reverse=True)
        
        selected_id = request.args.get('conv_id', type=int)
        selected_conversation = None
        messages_data = []
        
        if selected_id:
            selected_conversation = next((c for c in conversations if c['id'] == selected_id), None)
            if selected_conversation:
                selected_conversation['is_active'] = True
                unread_messages = Message.query.filter_by(sender_id=selected_id, recipient_id=user_id, is_read=False).all()
                for msg in unread_messages:
                    msg.is_read = True
                db.session.commit()
                
                messages_data = Message.query.filter(
                    or_(
                        and_(Message.sender_id == user_id, Message.recipient_id == selected_id),
                        and_(Message.sender_id == selected_id, Message.recipient_id == user_id)
                    )
                ).order_by(Message.created_at.asc()).all()
        
        if not selected_conversation and conversations:
            selected_conversation = conversations[0]
            selected_conversation['is_active'] = True
            return redirect(url_for('messages', conv_id=selected_conversation['id']))
        
        return render_template('user/messages.html', 
                             conversations=conversations,
                             selected_conversation=selected_conversation,
                             messages=messages_data)
    except Exception as e:
        flash('Messaging feature is being set up. Please try again later.', 'info')
        return render_template('user/messages.html', 
                             conversations=[], 
                             selected_conversation=None, 
                             messages=[])

@app.route('/messages/<int:conv_id>')
@login_required
def messages_conversation(conv_id):
    return redirect(url_for('messages', conv_id=conv_id))

@app.route('/messages/<int:conv_id>/send', methods=['POST'])
@login_required
def message_send(conv_id):
    user_id = session.get('user_id')
    data = request.get_json()
    content = data.get('content', '').strip()
    
    if not content:
        return jsonify({'success': False, 'message': 'Message content is required'}), 400
    
    try:
        message = Message(
            sender_id=user_id,
            recipient_id=conv_id,
            content=content,
            is_read=False
        )
        db.session.add(message)
        db.session.commit()
        
        create_notification(
            conv_id,
            'New Message',
            f'You have a new message from {User.query.get(user_id).full_name}',
            'info'
        )
        
        return jsonify({
            'success': True, 
            'message': 'Message sent',
            'time': datetime.utcnow().strftime('%I:%M %p')
        })
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/messages/new', methods=['POST'])
@login_required
def message_new():
    user_id = session.get('user_id')
    data = request.get_json()
    recipient = data.get('recipient')
    subject = data.get('subject')
    content = data.get('content')
    
    if not recipient or not subject or not content:
        return jsonify({'success': False, 'message': 'All fields are required'}), 400
    
    try:
        recipient_user = User.query.filter_by(role=recipient).first()
        if not recipient_user:
            return jsonify({'success': False, 'message': 'Recipient not found'}), 404
        
        message = Message(
            sender_id=user_id,
            recipient_id=recipient_user.id,
            subject=subject,
            content=content,
            is_read=False
        )
        db.session.add(message)
        db.session.commit()
        
        create_notification(
            recipient_user.id,
            'New Message',
            f'You have a new message from {User.query.get(user_id).full_name}: {subject}',
            'info'
        )
        
        return jsonify({'success': True, 'message': 'Message sent successfully'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

# ==================== API ROUTES ====================

@app.route('/api/available-slots')
def api_available_slots():
    """Get available time slots for a specific date"""
    date = request.args.get('date')
    
    if not date:
        return jsonify({'error': 'Date parameter required'}), 400
    
    try:
        booking_date = datetime.strptime(date, '%Y-%m-%d').date()
        
        bookings = Booking.query.filter(
            Booking.booking_date == booking_date,
            Booking.status.in_(['pending', 'confirmed', 'in_progress'])
        ).all()
        
        slot_counts = {}
        for booking in bookings:
            slot_key = booking.booking_time.strftime('%H:%M')
            slot_counts[slot_key] = slot_counts.get(slot_key, 0) + 1
        
        all_slots = []
        for hour in range(9, 18):
            time_str = f"{hour:02d}:00"
            display_hour = hour
            am_pm = "AM" if hour < 12 else "PM"
            if hour > 12:
                display_hour = hour - 12
            elif hour == 0:
                display_hour = 12
            
            count = slot_counts.get(time_str, 0)
            all_slots.append({
                'time': time_str,
                'booked_count': count,
                'max_slots': 5,
                'available': count < 5,
                'display': f"{display_hour}:00 {am_pm}"
            })
        
        return jsonify({
            'date': date,
            'slots': all_slots,
            'total_bookings': len(bookings)
        })
        
    except ValueError:
        return jsonify({'error': 'Invalid date format'}), 400
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/service-categories')
def api_service_categories():
    """Get all service categories with their services"""
    categories = ServiceCategory.query.filter_by(is_active=True).all()
    result = []
    for cat in categories:
        services = Service.query.filter_by(category_id=cat.id, is_active=True).all()
        result.append({
            'id': cat.id,
            'name': cat.name,
            'icon': cat.icon or 'fa-tools',
            'services': [{
                'id': s.id,
                'name': s.name,
                'description': s.description,
                'price': float(s.price),
                'estimated_hours': s.estimated_hours
            } for s in services]
        })
    return jsonify(result)

@app.route('/api/service/<int:service_id>')
def api_service_detail(service_id):
    """Get service details by ID"""
    service = Service.query.get_or_404(service_id)
    return jsonify({
        'id': service.id,
        'name': service.name,
        'description': service.description,
        'price': float(service.price),
        'estimated_hours': service.estimated_hours,
        'category': service.category.name if service.category else None
    })

@app.route('/api/check-availability', methods=['POST'])
def api_check_availability():
    """Check if a time slot is available"""
    data = request.get_json()
    date = data.get('date')
    time = data.get('time')
    service_id = data.get('service_id')
    
    if not date or not time or not service_id:
        return jsonify({'error': 'Date, time, and service_id required'}), 400
    
    try:
        booking_date = datetime.strptime(date, '%Y-%m-%d').date()
        booking_time = datetime.strptime(time, '%H:%M').time()
        
        count = Booking.query.filter(
            Booking.booking_date == booking_date,
            Booking.booking_time == booking_time,
            Booking.status.in_(['pending', 'confirmed', 'in_progress'])
        ).count()
        
        return jsonify({
            'available': count < 5,
            'booked_count': count,
            'max_slots': 5,
            'remaining': 5 - count
        })
        
    except ValueError:
        return jsonify({'error': 'Invalid date or time format'}), 400
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/check-slot')
def api_check_slot():
    date = request.args.get('date')
    time = request.args.get('time')
    
    if not date or not time:
        return jsonify({'error': 'Date and time parameters required'}), 400
    
    try:
        booking_date = datetime.strptime(date, '%Y-%m-%d').date()
        booking_time = datetime.strptime(time, '%H:%M').time()
        
        booking = Booking.query.filter(
            Booking.booking_date == booking_date,
            Booking.booking_time == booking_time,
            Booking.status.in_(['pending', 'confirmed', 'in_progress'])
        ).first()
        
        return jsonify({
            'date': date,
            'time': time,
            'is_booked': booking is not None,
            'booking_id': booking.id if booking else None
        })
        
    except ValueError:
        return jsonify({'error': 'Invalid date or time format'}), 400
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/booked-slots')
def api_booked_slots():
    date = request.args.get('date')
    
    if not date:
        return jsonify({'error': 'Date parameter required'}), 400
    
    try:
        booking_date = datetime.strptime(date, '%Y-%m-%d').date()
        
        bookings = Booking.query.filter(
            Booking.booking_date == booking_date,
            Booking.status.in_(['pending', 'confirmed', 'in_progress'])
        ).all()
        
        booked_times = [b.booking_time.strftime('%H:%M') for b in bookings]
        
        return jsonify({
            'date': date,
            'booked_slots': booked_times,
            'total_bookings': len(bookings)
        })
        
    except ValueError:
        return jsonify({'error': 'Invalid date format'}), 400
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/services')
def api_services():
    services = Service.query.filter_by(is_active=True).all()
    return jsonify([{
        'id': s.id,
        'name': s.name,
        'description': s.description,
        'price': float(s.price),
        'category': s.category.name if s.category else None,
        'estimated_hours': s.estimated_hours
    } for s in services])

# ==================== SERVICE REQUEST ROUTE ====================

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
        # No payment method is collected on the booking form itself - the
        # customer picks GCash/COD later, when they actually submit
        # payment for this booking (see the /transactions payment route).
        # The previous default here was the literal string 'C.A.R' (a
        # leftover/typo, not a real payment method), which was getting
        # permanently written into every new Transaction row and showing
        # up as the payment method in the admin panel before any payment
        # had even been made.
        payment_method = request.form.get('payment_method', 'unpaid')
        
        # Handle "Other" service
        if service_id == 'other':
            custom_service = request.form.get('custom_service', '').strip()
            if not custom_service:
                flash('Please specify your service requirement.', 'danger')
                return redirect(url_for('request_service'))
            
            custom_service_obj = Service.query.filter_by(name='Custom Service').first()
            if not custom_service_obj:
                default_category = ServiceCategory.query.first()
                if not default_category:
                    default_category = ServiceCategory(
                        name='Custom Services',
                        description='Custom service requests',
                        icon='fa-tools',
                        is_active=True
                    )
                    db.session.add(default_category)
                    db.session.commit()
                
                custom_service_obj = Service(
                    category_id=default_category.id,
                    name='Custom Service',
                    description='Custom service requested by user.',
                    price=0.00,
                    estimated_hours=1,
                    is_active=True
                )
                db.session.add(custom_service_obj)
                db.session.commit()
            
            service_id_for_booking = custom_service_obj.id
            
            if description:
                description = f"{description}\n\n📝 Custom Service: {custom_service}"
            else:
                description = f"📝 Custom Service: {custom_service}"
            
        else:
            service = Service.query.get(service_id)
            if not service:
                flash('Invalid service selected.', 'danger')
                return redirect(url_for('request_service'))
            service_id_for_booking = service_id
        
        # Handle "Other" device
        if device_type == 'Other':
            custom_device = request.form.get('custom_device', '').strip()
            if not custom_device:
                flash('Please specify your device type.', 'danger')
                return redirect(url_for('request_service'))
            device_type = custom_device
        
        # Validate required fields
        if not service_id_for_booking:
            flash('Please select a service.', 'danger')
            return redirect(url_for('request_service'))
        
        if not device_type:
            flash('Please select a device type.', 'danger')
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
        
        # Check slot availability (max 5 per slot)
        slot_count = Booking.query.filter(
            Booking.booking_date == booking_date_obj,
            Booking.booking_time == booking_time_obj,
            Booking.status.in_(['pending', 'confirmed', 'in_progress'])
        ).count()
        
        if slot_count >= 5:
            flash('This time slot is fully booked. Please choose another time.', 'danger')
            return redirect(url_for('request_service'))
        
        # Get the service for price
        service_obj = Service.query.get(service_id_for_booking)
        if not service_obj:
            flash('Invalid service selected.', 'danger')
            return redirect(url_for('request_service'))
        
        booking_number = generate_booking_number()
        booking = Booking(
            booking_number=booking_number,
            user_id=user_id,
            service_id=service_id_for_booking,
            device_type=device_type,
            description=description or 'No description provided',
            address=address if not is_in_shop else 'In-shop repair',
            booking_date=booking_date_obj,
            booking_time=booking_time_obj,
            is_in_shop=is_in_shop,
            status='pending'
        )
        db.session.add(booking)
        db.session.flush()
        
        transaction_number = generate_transaction_number()
        transaction = Transaction(
            transaction_number=transaction_number,
            booking_id=booking.id,
            user_id=user_id,
            amount=service_obj.price,
            payment_method=payment_method,
            payment_status='pending'
        )
        db.session.add(transaction)
        db.session.commit()
        
        create_notification(
            user_id,
            'Booking Created',
            f'Your booking #{booking_number} has been created. Please complete the payment.',
            'info'
        )
        
        flash(f'Booking created successfully! Booking #: {booking_number}', 'success')
        return redirect(url_for('user_transactions'))
    
    services = Service.query.filter_by(is_active=True).all()
    categories = ServiceCategory.query.filter_by(is_active=True).all()
    return render_template('user/request_service.html', services=services, categories=categories)

# ==================== SERVICE CATALOG / BOOKING / DEVICE MONITOR ====================
# These endpoints are referenced by templates/base/user_base.html (sidebar)
# and the new user/*.html templates. request_service (above) is kept so any
# older link or template that still points to it keeps working.

@app.route('/user/services')
@login_required
def service_catalog():
    category_id = request.args.get('category', type=int)
    query = Service.query.filter_by(is_active=True)
    if category_id:
        query = query.filter_by(category_id=category_id)
    services = query.order_by(Service.name).all()
    categories = ServiceCategory.query.filter_by(is_active=True).all()
    return render_template('user/service_catalog.html',
                           services=services,
                           categories=categories,
                           selected_category=category_id)

@app.route('/user/book', methods=['GET', 'POST'])
@app.route('/user/book/<int:service_id>', methods=['GET', 'POST'])
@login_required
def book_appointment(service_id=None):
    if request.method == 'POST':
        # Same validation, slot check, Booking + Transaction creation as before.
        return request_service()
    selected_service = Service.query.get(service_id) if service_id else None
    services = Service.query.filter_by(is_active=True).all()
    categories = ServiceCategory.query.filter_by(is_active=True).all()
    return render_template('user/book_appointment.html',
                           services=services,
                           categories=categories,
                           selected_service=selected_service,
                           service=selected_service)

@app.route('/user/monitor-device')
@login_required
def monitor_device():
    return render_template('user/monitor_device.html')

# ==================== TRANSACTION ROUTES ====================

@app.route('/user/transactions')
@login_required
def user_transactions():
    user_id = session.get('user_id')
    transactions = Transaction.query.filter_by(user_id=user_id).order_by(Transaction.transaction_date.desc()).all()
    notifications = Notification.query.filter_by(user_id=user_id, is_read=False).order_by(Notification.created_at.desc()).limit(5).all()
    return render_template('user/transactions.html', transactions=transactions, notifications=notifications)

@app.route('/user/payments/<int:transaction_id>', methods=['POST'])
@login_required
def user_payment(transaction_id):
    user_id = session.get('user_id')
    transaction = Transaction.query.get_or_404(transaction_id)
    
    if transaction.user_id != user_id:
        flash('Unauthorized access.', 'danger')
        return redirect(url_for('user_transactions'))
    
    payment_method = request.form.get('payment_method')
    reference = request.form.get('reference_number')
    receipt_file = request.files.get('receipt_image')
    
    if payment_method:
        transaction.payment_method = payment_method
    
    if reference:
        if payment_method == 'GCash':
            transaction.gcash_reference = reference
        transaction.reference_number = reference
    
    # Handle receipt upload
    if receipt_file and receipt_file.filename:
        if allowed_file(receipt_file.filename):
            extension = receipt_file.filename.rsplit('.', 1)[1].lower()
            is_valid, error_message = validate_uploaded_file(receipt_file, extension)
            if not is_valid:
                flash(error_message, 'danger')
                return redirect(url_for('user_transactions'))

            receipts_dir = os.path.join(app.config['UPLOAD_FOLDER'], 'receipts')
            os.makedirs(receipts_dir, exist_ok=True)
            
            timestamp = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
            # secrets.token_hex adds an unguessable component - without it,
            # two receipts uploaded in the same second for the same
            # transaction would silently overwrite each other on disk.
            filename = secure_filename(
                f"receipt_{transaction.transaction_number}_{timestamp}_{secrets.token_hex(4)}.{extension}"
            )
            filepath = os.path.join(receipts_dir, filename)
            
            receipt_file.save(filepath)
            transaction.receipt_image = f"/static/uploads/receipts/{filename}"
            flash('Receipt uploaded successfully.', 'success')
        else:
            flash('Invalid file format. Please upload JPG, PNG, GIF, or PDF.', 'danger')
            return redirect(url_for('user_transactions'))
    
    transaction.payment_status = 'pending'
    transaction.updated_at = datetime.utcnow()
    db.session.commit()
    
    create_notification(
        user_id,
        'Payment Submitted',
        f'Your payment for transaction #{transaction.transaction_number} has been submitted for verification.',
        'info'
    )
    
    flash('Payment submitted. Please wait for admin confirmation.', 'success')
    return redirect(url_for('user_transactions'))

# ==================== SUPPORT ROUTE ====================

@app.route('/support', methods=['GET', 'POST'])
@login_required
def support():
    if request.method == 'POST':
        user_id = session.get('user_id')
        subject = request.form.get('subject')
        message = request.form.get('message')
        category = request.form.get('category')
        
        if not subject or not message:
            flash('Please fill in all required fields.', 'danger')
            return redirect(url_for('support'))
        
        ticket = SupportTicket(
            user_id=user_id,
            subject=subject,
            message=message,
            category=category or 'general'
        )
        db.session.add(ticket)
        db.session.commit()
        
        admin = User.query.filter_by(role='admin').first()
        if admin:
            create_notification(
                admin.id,
                'New Support Ticket',
                f'New support ticket from {User.query.get(user_id).full_name}: {subject}',
                'info'
            )
        
        flash('Your support ticket has been submitted. We will get back to you shortly.', 'success')
        return redirect(url_for('support'))
    
    user_id = session.get('user_id')
    tickets = SupportTicket.query.filter_by(user_id=user_id).order_by(SupportTicket.created_at.desc()).all()
    notifications = Notification.query.filter_by(user_id=user_id, is_read=False).order_by(Notification.created_at.desc()).limit(5).all()
    
    return render_template('user/support.html', tickets=tickets, notifications=notifications)

# ==================== PROFILE ROUTE ====================

@app.route('/user/profile', methods=['GET', 'POST'])
@login_required
def user_profile():
    user_id = session.get('user_id')
    user = User.query.get(user_id)
    
    if request.method == 'POST':
        full_name = request.form.get('full_name', '').strip()
        phone = request.form.get('phone', '').strip()
        address = request.form.get('address', '').strip()
        city = request.form.get('city', '').strip()
        province = request.form.get('province', '').strip()
        postal_code = request.form.get('postal_code', '').strip()
        birth_date = request.form.get('birth_date', '')
        
        current_password = request.form.get('current_password', '')
        new_password = request.form.get('new_password', '')
        confirm_password = request.form.get('confirm_password', '')
        
        if not full_name:
            flash('Full name is required.', 'danger')
            return redirect(url_for('user_profile'))
        
        user.full_name = full_name
        user.phone = phone
        user.address = address
        user.city = city
        user.province = province
        user.postal_code = postal_code
        
        if birth_date:
            try:
                user.birth_date = datetime.strptime(birth_date, '%Y-%m-%d').date()
            except ValueError:
                flash('Invalid birth date format.', 'danger')
                return redirect(url_for('user_profile'))
        
        if new_password or confirm_password or current_password:
            if not current_password:
                flash('Current password is required to change password.', 'danger')
                return redirect(url_for('user_profile'))
            
            if not user.check_password(current_password):
                flash('Current password is incorrect.', 'danger')
                return redirect(url_for('user_profile'))
            
            if not new_password or not confirm_password:
                flash('New password and confirmation are required.', 'danger')
                return redirect(url_for('user_profile'))
            
            if new_password != confirm_password:
                flash('New passwords do not match.', 'danger')
                return redirect(url_for('user_profile'))
            
            if len(new_password) < 6:
                flash('New password must be at least 6 characters long.', 'danger')
                return redirect(url_for('user_profile'))
            
            user.set_password(new_password)
            flash('Password updated successfully!', 'success')
        
        db.session.commit()
        
        create_notification(
            user_id,
            'Profile Updated',
            'Your profile information has been updated successfully.',
            'success'
        )
        
        flash('Profile updated successfully!', 'success')
        log_activity(user_id, 'profile_update', 'User updated profile information')
        return redirect(url_for('user_profile'))
    
    notifications = Notification.query.filter_by(user_id=user_id, is_read=False).order_by(Notification.created_at.desc()).limit(5).all()
    return render_template('user/profile.html', user=user, notifications=notifications)

# ==================== API USER ROUTES ====================

@app.route('/api/user/activity-log')
@login_required
def api_user_activity_log():
    user_id = session.get('user_id')
    logs = ActivityLog.query.filter_by(user_id=user_id)\
        .order_by(ActivityLog.created_at.desc()).limit(50).all()
    
    return jsonify([{
        'action': log.action,
        'details': log.details,
        'ip_address': log.ip_address,
        'created_at': log.created_at.strftime('%Y-%m-%d %H:%M:%S')
    } for log in logs])

@app.route('/api/user/download-data')
@login_required
def api_user_download_data():
    user_id = session.get('user_id')
    user = User.query.get(user_id)
    
    data = {
        'user': user.to_dict(),
        'bookings': [{
            'booking_number': b.booking_number,
            'service': b.service.name,
            'device_type': b.device_type,
            'status': b.status,
            'booking_date': b.booking_date.strftime('%Y-%m-%d'),
            'booking_time': b.booking_time.strftime('%H:%M'),
            'created_at': b.created_at.strftime('%Y-%m-%d %H:%M:%S')
        } for b in user.bookings],
        'transactions': [{
            'transaction_number': t.transaction_number,
            'amount': float(t.amount),
            'payment_method': t.payment_method,
            'payment_status': t.payment_status,
            'transaction_date': t.transaction_date.strftime('%Y-%m-%d %H:%M:%S')
        } for t in user.transactions]
    }
    
    return jsonify(data)

@app.route('/api/user/delete-account', methods=['POST'])
@login_required
def api_user_delete_account():
    user_id = session.get('user_id')
    user = User.query.get(user_id)
    
    active_bookings = Booking.query.filter_by(user_id=user_id).filter(
        Booking.status.in_(['pending', 'confirmed', 'in_progress'])
    ).count()
    
    if active_bookings > 0:
        return jsonify({
            'success': False,
            'message': 'Cannot delete account with active bookings. Please cancel all bookings first.'
        }), 400
    
    log_activity(user_id, 'account_deleted', 'User deleted account')
    db.session.delete(user)
    db.session.commit()
    session.clear()
    
    return jsonify({
        'success': True,
        'message': 'Account deleted successfully.'
    })

@app.route('/api/user/update-preferences', methods=['POST'])
@login_required
def api_user_update_preferences():
    user_id = session.get('user_id')
    data = request.get_json()
    
    preferences = UserPreference.query.filter_by(user_id=user_id).first()
    if not preferences:
        preferences = UserPreference(user_id=user_id)
        db.session.add(preferences)
    
    preferences.language = data.get('language', 'en')
    preferences.theme = data.get('theme', 'light')
    preferences.email_notifications = data.get('email_notifications', True)
    preferences.sms_notifications = data.get('sms_notifications', False)
    preferences.booking_reminders = data.get('booking_reminders', True)
    
    db.session.commit()
    
    return jsonify({
        'success': True,
        'message': 'Preferences updated successfully.'
    })

@app.route('/api/user/verify-email', methods=['POST'])
@login_required
def api_user_verify_email():
    user_id = session.get('user_id')
    user = User.query.get(user_id)
    
    token = secrets.token_urlsafe(32)
    
    return jsonify({
        'success': True,
        'message': 'Verification email sent. Please check your inbox.'
    })

@app.route('/api/user/theme', methods=['POST'])
@login_required
def api_user_update_theme():
    user_id = session.get('user_id')
    data = request.get_json()
    theme = data.get('theme', 'light')
    
    if theme not in ['light', 'dark', 'system']:
        return jsonify({'success': False, 'message': 'Invalid theme'}), 400
    
    preferences = UserPreference.query.filter_by(user_id=user_id).first()
    if not preferences:
        preferences = UserPreference(user_id=user_id)
        db.session.add(preferences)
    
    preferences.theme = theme
    db.session.commit()
    
    return jsonify({
        'success': True,
        'message': 'Theme updated successfully',
        'theme': theme
    })

@app.route('/api/user/preferences', methods=['GET'])
@login_required
def api_user_get_preferences():
    user_id = session.get('user_id')
    preferences = UserPreference.query.filter_by(user_id=user_id).first()
    
    if not preferences:
        return jsonify({
            'language': 'en',
            'theme': 'light',
            'email_notifications': True,
            'sms_notifications': False,
            'booking_reminders': True
        })
    
    return jsonify({
        'language': preferences.language,
        'theme': preferences.theme,
        'email_notifications': preferences.email_notifications,
        'sms_notifications': preferences.sms_notifications,
        'booking_reminders': preferences.booking_reminders
    })

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
    user = User.query.get(session.get('user_id'))
    products = get_cached_active_products()
    notifications = Notification.query.filter_by(user_id=session.get('user_id'), is_read=False).order_by(Notification.created_at.desc()).limit(5).all()
    
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
    user = User.query.get(session.get('user_id'))
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
    user = User.query.get(session.get('user_id'))
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

    log_activity(user.id, 'address_update', 'User updated delivery address during checkout')

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

@app.route('/api/cart/add', methods=['POST'])
@login_required
def api_cart_add():
    data = request.get_json()
    product_id = data.get('product_id')
    quantity = data.get('quantity', 1)
    
    if not product_id:
        return jsonify({'success': False, 'message': 'Product ID required'}), 400
    
    product = Product.query.get(product_id)
    if not product or not product.is_active:
        return jsonify({'success': False, 'message': 'Product not found'}), 404
    
    if product.stock_quantity < quantity:
        return jsonify({'success': False, 'message': f'Insufficient stock. Only {product.stock_quantity} units available.'}), 400
    
    user_id = session.get('user_id')
    
    cart = ShoppingCart.query.filter_by(user_id=user_id, status='active').first()
    if not cart:
        cart = ShoppingCart(user_id=user_id, status='active')
        db.session.add(cart)
        db.session.commit()
    
    cart_item = CartItem.query.filter_by(cart_id=cart.id, product_id=product_id).first()
    if cart_item:
        if cart_item.quantity + quantity > product.stock_quantity:
            return jsonify({'success': False, 'message': f'Not enough stock. Only {product.stock_quantity - cart_item.quantity} more available.'}), 400
        cart_item.quantity += quantity
    else:
        cart_item = CartItem(
            cart_id=cart.id,
            product_id=product_id,
            quantity=quantity,
            price=product.price
        )
        db.session.add(cart_item)
    
    product.stock_quantity -= quantity
    db.session.commit()
    cache.delete('active_products')  # stock just changed - don't serve a stale count
    
    cart_count = CartItem.query.filter_by(cart_id=cart.id).count()
    
    return jsonify({
        'success': True,
        'message': f'{product.name} added to cart',
        'cart_count': cart_count
    })

@app.route('/api/cart/update', methods=['POST'])
@login_required
def api_cart_update():
    data = request.get_json()
    item_id = data.get('item_id')
    quantity = data.get('quantity')
    
    if not item_id:
        return jsonify({'success': False, 'message': 'Item ID required'}), 400
    
    cart_item = CartItem.query.get(item_id)
    if not cart_item:
        return jsonify({'success': False, 'message': 'Item not found'}), 404
    
    cart = ShoppingCart.query.get(cart_item.cart_id)
    if cart.user_id != session.get('user_id'):
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403
    
    product = Product.query.get(cart_item.product_id)
    if not product:
        return jsonify({'success': False, 'message': 'Product not found'}), 404
    
    if quantity <= 0:
        product.stock_quantity += cart_item.quantity
        db.session.delete(cart_item)
        db.session.commit()
        cache.delete('active_products')
        return jsonify({'success': True, 'message': 'Item removed from cart'})
    
    if product.stock_quantity < (quantity - cart_item.quantity):
        return jsonify({'success': False, 'message': f'Insufficient stock. Only {product.stock_quantity + cart_item.quantity} available.'}), 400
    
    product.stock_quantity -= (quantity - cart_item.quantity)
    cart_item.quantity = quantity
    db.session.commit()
    cache.delete('active_products')  # stock just changed - don't serve a stale count
    
    return jsonify({'success': True, 'message': 'Cart updated'})

@app.route('/api/cart/remove/<int:item_id>', methods=['DELETE'])
@login_required
def api_cart_remove(item_id):
    cart_item = CartItem.query.get(item_id)
    if not cart_item:
        return jsonify({'success': False, 'message': 'Item not found'}), 404
    
    cart = ShoppingCart.query.get(cart_item.cart_id)
    if cart.user_id != session.get('user_id'):
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403
    
    product = Product.query.get(cart_item.product_id)
    if product:
        product.stock_quantity += cart_item.quantity
    
    db.session.delete(cart_item)
    db.session.commit()
    cache.delete('active_products')
    
    return jsonify({'success': True, 'message': 'Item removed from cart'})

@app.route('/api/cart/clear', methods=['POST'])
@login_required
def api_cart_clear():
    cart = ShoppingCart.query.filter_by(user_id=session.get('user_id'), status='active').first()
    if cart:
        for item in cart.items:
            product = Product.query.get(item.product_id)
            if product:
                product.stock_quantity += item.quantity
            db.session.delete(item)
        db.session.commit()
        cache.delete('active_products')
    
    return jsonify({'success': True, 'message': 'Cart cleared'})

@app.route('/api/cart/checkout', methods=['POST'])
@login_required
def api_cart_checkout():
    user_id = session.get('user_id')
    user = User.query.get(user_id)
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

    cart = ShoppingCart.query.filter_by(user_id=user_id, status='active').first()
    
    if not cart:
        return jsonify({'success': False, 'message': 'Cart is empty'}), 400
    
    cart_items = CartItem.query.filter_by(cart_id=cart.id).all()
    if not cart_items:
        return jsonify({'success': False, 'message': 'Cart is empty'}), 400
    
    # Check stock one more time before checkout
    for item in cart_items:
        product = Product.query.get(item.product_id)
        if not product or product.stock_quantity < item.quantity:
            return jsonify({
                'success': False,
                'message': f'Insufficient stock for {product.name if product else "Unknown product"}.'
            }), 400
    
    total_amount = sum(item.quantity * float(item.price if item.price else Product.query.get(item.product_id).price) for item in cart_items)
    
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
        product = Product.query.get(item.product_id)
        order_item = OrderItem(
            order_id=order.id,
            product_id=item.product_id,
            quantity=item.quantity,
            price=item.price if item.price else product.price
        )
        db.session.add(order_item)
        # Stock is already decreased when added to cart
        db.session.delete(item)
    
    cart.status = 'completed'

    transaction = Transaction(
        transaction_number=generate_transaction_number(),
        order_id=order.id,
        user_id=user_id,
        amount=total_amount,
        payment_method=payment_method,
        payment_status='pending',
        gcash_reference=gcash_reference if payment_method == 'gcash' else None
    )
    db.session.add(transaction)

    db.session.commit()

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
    create_notification(user_id, 'Order Placed', notif_message, 'success')
    
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
    user = User.query.get(user_id)
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

    notifications = Notification.query.filter_by(user_id=user_id, is_read=False).order_by(Notification.created_at.desc()).limit(5).all()
    return render_template(
        'user/orders.html',
        orders=orders,
        status_filter=status_filter,
        status_counts=status_counts,
        notifications=notifications,
        user=user
    )

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

    # If a GCash payment has already been verified by an admin, money has
    # actually changed hands - self-service cancellation would silently
    # drop that without a refund. Route those to support instead.
    if order.payment_method == 'gcash' and order.payment_status == 'confirmed':
        return jsonify({
            'success': False,
            'message': 'This order has a confirmed GCash payment. Please contact support to cancel and process a refund.'
        }), 400
    
    # Restore stock for each item in the order
    for item in order.items:
        product = Product.query.get(item.product_id)
        if product:
            product.stock_quantity += item.quantity
            db.session.add(product)
    
    # Update order status
    order.status = 'cancelled'
    order.updated_at = datetime.utcnow()
    db.session.commit()
    cache.delete('active_products')
    
    # Create notification for user
    create_notification(
        user_id,
        'Order Cancelled',
        f'Your order #{order.order_number} has been cancelled. Stock has been restored.',
        'warning'
    )
    
    return jsonify({
        'success': True,
        'message': f'Order #{order.order_number} cancelled successfully. Stock restored.'
    })

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
    notifications = Notification.query.filter_by(user_id=session.get('user_id'), is_read=False).order_by(Notification.created_at.desc()).limit(5).all()
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
    total_users = User.query.filter_by(role='customer').count()
    total_technicians = User.query.filter_by(role='technician').count()
    total_bookings = Booking.query.count()
    pending_bookings = Booking.query.filter_by(status='pending').count()
    total_transactions = Transaction.query.count()
    pending_payments = Transaction.query.filter_by(payment_status='pending').count()
    total_revenue = db.session.query(db.func.sum(Transaction.amount)).filter_by(payment_status='confirmed').scalar() or 0

    users_trend = calculate_trend(User, User.created_at, User.role == 'customer')
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

    recent_bookings = Booking.query.order_by(Booking.created_at.desc()).limit(5).all()
    recent_users = User.query.order_by(User.created_at.desc()).limit(5).all()
    recent_activities = ActivityLog.query.order_by(ActivityLog.created_at.desc()).limit(10).all()
    recent_pending_payments = Transaction.query.filter_by(payment_status='pending').order_by(Transaction.transaction_date.desc()).limit(3).all()

    return render_template('admin/admin_dashboard.html',
                         total_users=stats['total_users'],
                         total_technicians=stats['total_technicians'],
                         total_bookings=stats['total_bookings'],
                         pending_bookings=stats['pending_bookings'],
                         total_transactions=stats['total_transactions'],
                         pending_payments=stats['pending_payments'],
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
    """Row-level shape for the User Management table - list view + live polling."""
    presence = get_user_presence(user)
    return {
        'id': user.id,
        'full_name': user.full_name,
        'email': user.email,
        'phone': user.phone,
        'role': user.role,
        'is_active': user.is_active,
        'id_verified': user.id_verified if user.role == 'technician' else None,
        'created_at': user.created_at.strftime('%Y-%m-%d') if user.created_at else None,
        **presence
    }

def build_admin_user_detail(user):
    """Full-detail shape for the eye-icon modal: profile + presence + activity stats."""
    presence = get_user_presence(user)
    orders_count = Order.query.filter_by(user_id=user.id).count()
    bookings_count = Booking.query.filter_by(user_id=user.id).count()
    total_spent = db.session.query(db.func.sum(Transaction.amount)).filter_by(
        user_id=user.id, payment_status='confirmed'
    ).scalar() or 0

    recent_orders = Order.query.filter_by(user_id=user.id).order_by(Order.created_at.desc()).limit(5).all()
    recent_bookings = Booking.query.filter_by(user_id=user.id).order_by(Booking.created_at.desc()).limit(5).all()

    return {
        'id': user.id,
        'username': user.username,
        'full_name': user.full_name,
        'email': user.email,
        'phone': user.phone,
        'address': user.address,
        'city': user.city,
        'province': user.province,
        'postal_code': user.postal_code,
        'birth_date': user.birth_date.strftime('%Y-%m-%d') if user.birth_date else None,
        'role': user.role,
        'is_active': user.is_active,
        'id_type': user.id_type if user.role == 'technician' else None,
        'id_verified': user.id_verified if user.role == 'technician' else None,
        'id_verified_at': user.id_verified_at.strftime('%Y-%m-%d %H:%M:%S') if user.id_verified_at else None,
        'created_at': user.created_at.strftime('%Y-%m-%d %H:%M:%S') if user.created_at else None,
        'updated_at': user.updated_at.strftime('%Y-%m-%d %H:%M:%S') if user.updated_at else None,
        **presence,
        'stats': {
            'orders_count': orders_count,
            'bookings_count': bookings_count,
            'total_spent': float(total_spent)
        },
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

@app.route('/admin/users')
@admin_required
def admin_users():
    users = User.query.order_by(User.created_at.desc()).all()
    users_json = [build_admin_user_summary(u) for u in users]
    return render_template('admin/users_management.html', users=users, users_json=users_json)

@app.route('/api/admin/users')
@admin_required
def api_admin_users():
    """Polled by the User Management page to refresh online status and
    'time ago' text without a page reload."""
    users = User.query.order_by(User.created_at.desc()).all()
    return jsonify({'users': [build_admin_user_summary(u) for u in users]})

@app.route('/api/admin/users/<int:user_id>')
@admin_required
def api_admin_user_detail(user_id):
    user = User.query.get_or_404(user_id)
    return jsonify({'user': build_admin_user_detail(user)})

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

    missing = [label for label, value in [
        ('username', username), ('email', email), ('password', password), ('full name', full_name)
    ] if not value]
    if missing:
        return jsonify({'success': False, 'message': f"Please fill in: {', '.join(missing)}."}), 400

    if role not in ('customer', 'technician', 'admin'):
        return jsonify({'success': False, 'message': 'Invalid role.'}), 400

    if len(password) < 6:
        return jsonify({'success': False, 'message': 'Password must be at least 6 characters.'}), 400

    if User.query.filter_by(username=username).first():
        return jsonify({'success': False, 'message': 'That username is already taken.'}), 400

    if User.query.filter_by(email=email).first():
        return jsonify({'success': False, 'message': 'That email is already registered.'}), 400

    user = User(
        username=username,
        email=email,
        full_name=full_name,
        phone=phone or None,
        role=role,
        is_active=True
    )
    user.set_password(password)
    db.session.add(user)
    db.session.commit()

    log_activity(session.get('user_id'), 'user_create', f'Created user account: {full_name} ({email})')

    return jsonify({'success': True, 'message': f'{full_name} was added.', 'user': build_admin_user_summary(user)})

@app.route('/api/admin/users/<int:user_id>/verify-id', methods=['POST'])
@admin_required
def api_admin_verify_technician_id(user_id):
    """Records identity-verification for a technician account. The ID
    number is stored so the shop has a real audit record on file (the
    same way any employer keeps a copy of a hired worker's ID), but it is
    never returned by any other endpoint in this app - only this route
    accepts it, and no GET endpoint anywhere serializes id_number back
    out. Every other view of a technician only ever sees the boolean
    id_verified flag."""
    user = User.query.get_or_404(user_id)
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
        'success'
    )

    return jsonify({'success': True, 'message': f"{user.full_name}'s identity has been verified."})

@app.route('/api/admin/users/<int:user_id>/verify-id', methods=['DELETE'])
@admin_required
def api_admin_revoke_technician_verification(user_id):
    """Lets an admin revoke a verification (e.g. an ID turned out to be
    fraudulent, or expired) without deleting the account outright."""
    user = User.query.get_or_404(user_id)
    user.id_verified = False
    db.session.commit()
    log_activity(session.get('user_id'), 'technician_verify_revoke', f'Revoked identity verification for: {user.full_name}')
    return jsonify({'success': True, 'message': f"{user.full_name}'s verification has been revoked."})

@app.route('/api/admin/users/<int:user_id>', methods=['PUT'])
@admin_required
def api_admin_update_user(user_id):
    user = User.query.get_or_404(user_id)
    data = request.get_json(silent=True) or {}

    full_name = (data.get('full_name') or '').strip()
    email = (data.get('email') or '').strip().lower()
    phone = (data.get('phone') or '').strip()
    address = (data.get('address') or '').strip()
    city = (data.get('city') or '').strip()
    province = (data.get('province') or '').strip()
    postal_code = (data.get('postal_code') or '').strip()
    role = (data.get('role') or user.role).strip()

    if not full_name or not email:
        return jsonify({'success': False, 'message': 'Full name and email are required.'}), 400

    if role not in ('customer', 'technician', 'admin'):
        return jsonify({'success': False, 'message': 'Invalid role.'}), 400

    if user_id == session.get('user_id') and role != 'admin':
        return jsonify({'success': False, 'message': "You can't change your own role while logged in."}), 400

    existing = User.query.filter(User.email == email, User.id != user_id).first()
    if existing:
        return jsonify({'success': False, 'message': 'That email is already used by another account.'}), 400

    if user.role == 'admin' and role != 'admin' and User.query.filter_by(role='admin').count() <= 1:
        return jsonify({'success': False, 'message': 'Cannot change the role of the last remaining admin.'}), 400

    user.full_name = full_name
    user.email = email
    user.phone = phone or None
    user.address = address or None
    user.city = city or None
    user.province = province or None
    user.postal_code = postal_code or None
    user.role = role
    db.session.commit()

    if session.get('user_id') == user.id:
        session['role'] = user.role
        session['username'] = user.username

    log_activity(session.get('user_id'), 'user_update', f'Updated user account: {user.full_name} (#{user.id})')

    return jsonify({'success': True, 'message': 'User updated.', 'user': build_admin_user_summary(user)})

@app.route('/api/admin/users/<int:user_id>/status', methods=['POST'])
@admin_required
def api_admin_toggle_user_status(user_id):
    if user_id == session.get('user_id'):
        return jsonify({'success': False, 'message': "You can't deactivate your own account while logged in."}), 400

    user = User.query.get_or_404(user_id)
    data = request.get_json(silent=True) or {}

    if user.role == 'admin' and user.is_active and User.query.filter_by(role='admin', is_active=True).count() <= 1:
        return jsonify({'success': False, 'message': 'Cannot deactivate the last active admin account.'}), 400

    if 'is_active' in data:
        user.is_active = bool(data['is_active'])
    else:
        user.is_active = not user.is_active
    db.session.commit()

    log_activity(session.get('user_id'), 'user_status_change',
                 f'{"Activated" if user.is_active else "Deactivated"} user: {user.full_name} (#{user.id})')

    return jsonify({'success': True, 'is_active': user.is_active})

@app.route('/api/admin/users/<int:user_id>/role', methods=['POST'])
@admin_required
def api_admin_update_role(user_id):
    user = User.query.get_or_404(user_id)
    data = request.get_json(silent=True) or {}
    new_role = (data.get('role') or '').strip()

    if new_role not in ('customer', 'technician', 'admin'):
        return jsonify({'success': False, 'message': 'Invalid role.'}), 400

    # An admin must never be able to change their OWN role away from
    # 'admin' - doing so instantly locks them out of every /admin/* page
    # on their very next click, since admin_required re-checks the role
    # from the database on every request.
    if user_id == session.get('user_id') and new_role != 'admin':
        return jsonify({'success': False, 'message': "You can't change your own role while logged in."}), 400

    if user.role == 'admin' and new_role != 'admin' and User.query.filter_by(role='admin').count() <= 1:
        return jsonify({'success': False, 'message': 'Cannot change the role of the last remaining admin.'}), 400

    user.role = new_role
    db.session.commit()

    if session.get('user_id') == user.id:
        session['role'] = user.role

    log_activity(session.get('user_id'), 'user_role_change', f'Changed role of {user.full_name} (#{user.id}) to {new_role}')

    return jsonify({'success': True, 'role': user.role})

@app.route('/api/admin/users/<int:user_id>', methods=['DELETE'])
@admin_required
def api_admin_delete_user(user_id):
    if user_id == session.get('user_id'):
        return jsonify({'success': False, 'message': "You can't delete your own account while logged in."}), 400

    user = User.query.get_or_404(user_id)

    if user.role == 'admin' and User.query.filter_by(role='admin').count() <= 1:
        return jsonify({'success': False, 'message': 'Cannot delete the last remaining admin account.'}), 400

    has_history = (
        Booking.query.filter_by(user_id=user_id).first() is not None or
        Order.query.filter_by(user_id=user_id).first() is not None or
        Transaction.query.filter_by(user_id=user_id).first() is not None or
        SupportTicket.query.filter_by(user_id=user_id).first() is not None
    )
    if has_history:
        return jsonify({
            'success': False,
            'message': 'This user has bookings, orders, or transactions on record and cannot be deleted. '
                       'Deactivate the account instead to preserve that history.'
        }), 400

    try:
        Notification.query.filter_by(user_id=user_id).delete()
        Message.query.filter_by(sender_id=user_id).delete()
        Message.query.filter_by(recipient_id=user_id).delete()
        ActivityLog.query.filter_by(user_id=user_id).delete()
        for cart in ShoppingCart.query.filter_by(user_id=user_id).all():
            CartItem.query.filter_by(cart_id=cart.id).delete()
            db.session.delete(cart)
        UserPreference.query.filter_by(user_id=user_id).delete()

        full_name = user.full_name
        db.session.delete(user)
        db.session.commit()

        log_activity(session.get('user_id'), 'user_delete', f'Deleted user account: {full_name} (#{user_id})')

        return jsonify({'success': True, 'message': f'{full_name} has been deleted.'})
    except Exception:
        db.session.rollback()
        return jsonify({'success': False, 'message': 'Could not delete user due to a database error.'}), 500

@app.route('/admin/users/<int:user_id>/toggle', methods=['POST'])
@admin_required
def admin_user_toggle(user_id):
    user = User.query.get_or_404(user_id)
    user.is_active = not user.is_active
    db.session.commit()
    flash(f'User status updated to {"Active" if user.is_active else "Inactive"}.', 'success')
    return redirect(url_for('admin_users'))

@app.route('/admin/users/<int:user_id>/role', methods=['POST'])
@admin_required
def admin_user_role(user_id):
    user = User.query.get_or_404(user_id)
    new_role = request.form.get('role')
    if user_id == session.get('user_id') and new_role != 'admin':
        flash("You can't change your own role while logged in.", 'danger')
        return redirect(url_for('admin_users'))
    if new_role in ['customer', 'technician', 'admin']:
        user.role = new_role
        db.session.commit()
        flash(f'User role updated to {new_role}.', 'success')
    return redirect(url_for('admin_users'))

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

@app.route('/admin/requests')
@admin_required
def admin_requests():
    bookings = Booking.query.order_by(Booking.created_at.desc()).all()
    technicians = User.query.filter_by(role='technician').order_by(User.full_name).all()
    return render_template('admin/request_management.html', bookings=bookings, technicians=technicians)

@app.route('/admin/requests/<int:booking_id>/status', methods=['POST'])
@admin_required
def admin_request_status(booking_id):
    booking = Booking.query.get_or_404(booking_id)
    new_status = request.form.get('status')
    rejection_reason = request.form.get('reason', '')
    technician_id = request.form.get('technician_id', type=int)
    
    if new_status in ['pending', 'confirmed', 'in_progress', 'completed', 'cancelled']:

        # Approving a request requires assigning a technician who has
        # actually passed identity verification - this is the real-world
        # safety rule: an unverified account should never be dispatched to
        # a customer's home or handed their device.
        if new_status == 'confirmed':
            if not technician_id:
                flash('Please select a technician to assign before approving this request.', 'danger')
                return redirect(url_for('admin_requests'))

            technician = User.query.filter_by(id=technician_id, role='technician').first()
            if not technician:
                flash('Selected technician not found.', 'danger')
                return redirect(url_for('admin_requests'))
            if not technician.id_verified:
                flash(f'{technician.full_name} has not completed identity verification yet and cannot be assigned. Verify their ID in User Management first.', 'danger')
                return redirect(url_for('admin_requests'))

            booking.technician_id = technician.id
            booking.assigned_at = datetime.utcnow()

        booking.status = new_status
        booking.updated_at = datetime.utcnow()
        db.session.commit()
        
        # Create notification for the user
        if new_status == 'cancelled':
            notification_title = 'Booking Rejected'
            notification_message = f'Your booking #{booking.booking_number} has been rejected.'
            if rejection_reason:
                notification_message += f'\n\nReason: {rejection_reason}'
            notification_type = 'error'
        elif new_status == 'confirmed' and booking.technician:
            tech = booking.technician
            # Note what's deliberately left out: the technician's ID number
            # or ID type is never included here. Customers see a name, a
            # verified badge, and a contact number - never the document
            # itself, matching how Grab/TaskRabbit-style platforms handle
            # this in practice.
            verified_badge = 'Verified ✓' if tech.id_verified else 'Pending verification'
            notification_title = 'Booking Approved - Technician Assigned'
            notification_message = (
                f'Your booking #{booking.booking_number} has been approved!\n\n'
                f'Assigned Technician: {tech.full_name} ({verified_badge})\n'
                f'Contact: {tech.phone or "Available through the app messages"}\n\n'
                f'They will reach out to coordinate the service.'
            )
            notification_type = 'success'
        else:
            notification_title = 'Booking Status Updated'
            notification_message = f'Your booking #{booking.booking_number} status is now: {new_status.capitalize()}'
            notification_type = 'info'
        
        create_notification(
            booking.user_id,
            notification_title,
            notification_message,
            notification_type
        )
        
        flash(f'Booking status updated to {new_status.capitalize()}.', 'success')
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

@app.route('/admin/payments')
@admin_required
def admin_payments():
    transactions = Transaction.query.order_by(Transaction.transaction_date.desc()).all()
    return render_template('admin/payment_confirmation.html', transactions=transactions)

@app.route('/admin/payments/<int:transaction_id>/confirm', methods=['POST'])
@admin_required
def admin_payment_confirm(transaction_id):
    transaction = Transaction.query.get_or_404(transaction_id)
    transaction.payment_status = 'confirmed'
    transaction.updated_at = datetime.utcnow()
    db.session.commit()
    
    if transaction.booking_id:
        booking = Booking.query.get(transaction.booking_id)
        if booking:
            booking.status = 'confirmed'
            booking.updated_at = datetime.utcnow()
            db.session.commit()
    
    create_notification(
        transaction.user_id,
        'Payment Confirmed',
        f'Your payment for transaction #{transaction.transaction_number} has been confirmed.',
        'success'
    )
    
    flash('Payment confirmed successfully.', 'success')
    return redirect(url_for('admin_payments'))

@app.route('/admin/payments/<int:transaction_id>/reject', methods=['POST'])
@admin_required
def admin_payment_reject(transaction_id):
    transaction = Transaction.query.get_or_404(transaction_id)
    reason = request.form.get('reason', 'Payment rejected by admin.')
    transaction.payment_status = 'rejected'
    transaction.rejection_reason = reason
    transaction.updated_at = datetime.utcnow()
    db.session.commit()
    
    create_notification(
        transaction.user_id,
        'Payment Rejected',
        f'Your payment for transaction #{transaction.transaction_number} was rejected. Reason: {reason}',
        'error'
    )
    
    flash('Payment rejected.', 'warning')
    return redirect(url_for('admin_payments'))

@app.route('/admin/analytics')
@admin_required
@cache.cached(timeout=60, query_string=True)
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
    
    # Total Users
    total_users = User.query.filter_by(role='customer').count()
    new_users = User.query.filter(User.created_at >= start_date, User.role == 'customer').count()
    user_growth_percent = round((new_users / total_users * 100) if total_users > 0 else 0)
    
    # Total Bookings
    total_bookings = Booking.query.count()
    new_bookings = Booking.query.filter(Booking.created_at >= start_date).count()
    bookings_growth_percent = round((new_bookings / total_bookings * 100) if total_bookings > 0 else 0)
    
    # Total Revenue (confirmed payments only)
    total_revenue = db.session.query(func.sum(Transaction.amount)).filter_by(payment_status='confirmed').scalar() or 0
    revenue_this_period = db.session.query(func.sum(Transaction.amount)).filter(
        Transaction.payment_status == 'confirmed',
        Transaction.transaction_date >= start_date
    ).scalar() or 0
    revenue_growth_percent = round((revenue_this_period / total_revenue * 100) if total_revenue > 0 else 0)
    
    # Average Rating (if you have a ratings system, otherwise use completion rate)
    completed_bookings = Booking.query.filter_by(status='completed').count()
    completion_rate = round((completed_bookings / total_bookings * 100) if total_bookings > 0 else 0)
    
    # ============================================
    # MONTHLY REVENUE (Last 12 months)
    # ============================================
    
    monthly_revenue = db.session.query(
        func.date_format(Transaction.transaction_date, '%Y-%m').label('month'),
        func.sum(Transaction.amount).label('total')
    ).filter(Transaction.payment_status == 'confirmed')\
     .group_by('month')\
     .order_by('month')\
     .limit(12).all()
    
    revenue_labels = []
    revenue_data = []
    for item in monthly_revenue:
        # Format: Jan 2024
        year_month = item.month.split('-')
        month_name = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'][int(year_month[1]) - 1]
        revenue_labels.append(f"{month_name} {year_month[0]}")
        revenue_data.append(float(item.total) if item.total else 0)
    
    # If no revenue data, fill with zeros for the last 12 months
    if len(revenue_labels) < 12:
        # Get the last 12 months
        months = []
        for i in range(11, -1, -1):
            d = now - timedelta(days=30 * i)
            month_name = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'][d.month - 1]
            months.append(f"{month_name} {d.year}")
        
        # Create a dict from existing data
        revenue_dict = dict(zip(revenue_labels, revenue_data))
        revenue_labels = months
        revenue_data = [revenue_dict.get(m, 0) for m in months]
    
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
    
    user_growth = db.session.query(
        func.date_format(User.created_at, '%Y-%m').label('month'),
        func.count(User.id).label('count')
    ).group_by('month')\
     .order_by('month')\
     .limit(6).all()
    
    growth_labels = []
    growth_data = []
    for item in user_growth:
        year_month = item.month.split('-')
        month_name = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'][int(year_month[1]) - 1]
        growth_labels.append(f"{month_name} {year_month[0]}")
        growth_data.append(item.count)
    
    # Fill missing months
    if len(growth_labels) < 6:
        months = []
        for i in range(5, -1, -1):
            d = now - timedelta(days=30 * i)
            month_name = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'][d.month - 1]
            months.append(f"{month_name} {d.year}")
        
        growth_dict = dict(zip(growth_labels, growth_data))
        growth_labels = months
        growth_data = [growth_dict.get(m, 0) for m in months]
    
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
    
    day_labels = [b.date.strftime('%b %d') for b in bookings_by_day]
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
    
    revenue_day_labels = [r.date.strftime('%b %d') for r in revenue_by_day]
    revenue_day_data = [float(r.total) if r.total else 0 for r in revenue_by_day]

    # ============================================
    # SHOP PERFORMANCE (real e-commerce data - this
    # entire feature had zero analytics coverage before)
    # ============================================

    shop_revenue = db.session.query(func.sum(Order.total_amount)).filter(
        Order.status != 'cancelled'
    ).scalar() or 0
    booking_revenue_confirmed = db.session.query(func.sum(Transaction.amount)).filter(
        Transaction.payment_status == 'confirmed',
        Transaction.booking_id.isnot(None)
    ).scalar() or 0

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
        User.full_name,
        User.id_verified,
        func.count(Booking.id).label('assigned_count'),
        func.sum(db.case((Booking.status == 'completed', 1), else_=0)).label('completed_count')
    ).join(Booking, Booking.technician_id == User.id)\
     .filter(User.role == 'technician')\
     .group_by(User.id)\
     .order_by(func.count(Booking.id).desc())\
     .all()

    technician_labels = [t.full_name for t in technician_stats]
    technician_assigned_data = [int(t.assigned_count) for t in technician_stats]
    technician_completed_data = [int(t.completed_count or 0) for t in technician_stats]

    total_technicians_all = User.query.filter_by(role='technician').count()
    verified_technicians = User.query.filter_by(role='technician', id_verified=True).count()
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
        User.full_name,
        func.sum(Transaction.amount).label('total_spent'),
        func.count(Transaction.id).label('txn_count')
    ).join(Transaction, Transaction.user_id == User.id)\
     .filter(Transaction.payment_status == 'confirmed')\
     .group_by(User.id)\
     .order_by(func.sum(Transaction.amount).desc())\
     .limit(5).all()

    return render_template('admin/analytics.html',
                         total_users=total_users,
                         user_growth_percent=user_growth_percent,
                         total_bookings=total_bookings,
                         bookings_growth_percent=bookings_growth_percent,
                         total_revenue=float(total_revenue),
                         revenue_growth_percent=revenue_growth_percent,
                         completion_rate=completion_rate,
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
    
@app.route('/admin/settings')
@admin_required
def admin_settings():
    settings = SystemSetting.query.all()
    return render_template('admin/settings.html', settings=settings)

@app.route('/admin/settings/update', methods=['POST'])
@admin_required
def admin_settings_update():
    for setting_key, value in request.form.items():
        setting = SystemSetting.query.filter_by(setting_key=setting_key).first()
        if setting:
            setting.value = value
            setting.updated_at = datetime.utcnow()
        else:
            setting = SystemSetting(setting_key=setting_key, value=value)
            db.session.add(setting)
    db.session.commit()
    flash('Settings updated successfully.', 'success')
    return redirect(url_for('admin_settings'))

# ==================== ERROR HANDLERS ====================

@app.errorhandler(404)
def page_not_found(error):
    return render_template('errors/404.html'), 404

@app.errorhandler(500)
def internal_error(error):
    db.session.rollback()
    return render_template('errors/500.html'), 500

# ==================== INIT DATABASE ====================

def init_db():
    with app.app_context():
        try:
            db.session.execute(text('DROP TABLE IF EXISTS system_settings'))
            db.session.commit()
            print("Dropped existing system_settings table")
        except Exception as e:
            print(f"Note: {e}")
        
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
        add_oauth_columns()
        add_order_address_columns()
        add_user_presence_columns()
        
        # Create admin user
        admin = User.query.filter_by(email='admin@devtech.com').first()
        if not admin:
            admin = User(
                username='admin',
                email='admin@devtech.com',
                full_name='System Administrator',
                phone='09171234567',
                role='admin',
                is_active=True
            )
            admin.set_password('admin123')
            db.session.add(admin)
            print("Admin user created: admin@devtech.com / admin123")
        
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
        
        # Add sample products
        if Product.query.count() == 0:
            products = [
                Product(name='DDR4 RAM 16GB', description='High-performance 3200MHz memory module', price=2500.00, category='memory', stock_quantity=12, compatibility='DDR4'),
                Product(name='SSD 512GB', description='NVMe M.2 SSD with read speeds up to 3500MB/s', price=3200.00, category='storage', stock_quantity=8, compatibility='M.2 NVMe'),
                Product(name='Laptop Battery', description='Replacement lithium-ion battery 5200mAh', price=1800.00, category='battery', stock_quantity=5, compatibility='Universal'),
                Product(name='Charger Adapter', description='65W USB-C fast charger', price=1200.00, category='accessory', stock_quantity=15, compatibility='USB-C'),
                Product(name='Intel i5-12400', description='6-core 12-thread processor with 4.4GHz boost', price=8500.00, category='cpu', stock_quantity=3, compatibility='LGA1700'),
                Product(name='RTX 3060', description='12GB GDDR6 graphics card with ray tracing', price=12500.00, category='gpu', stock_quantity=2, compatibility='PCIe 4.0')
            ]
            db.session.add_all(products)
            print("Sample products added successfully!")
        
        # Add system settings
        if SystemSetting.query.count() == 0:
            settings = [
                SystemSetting(setting_key='system_name', value='DEVTech Computer Services', description='System name displayed throughout'),
                SystemSetting(setting_key='system_email', value='admin@devtech.com', description='Primary system email'),
                SystemSetting(setting_key='default_currency', value='PHP', description='Default currency for transactions'),
                SystemSetting(setting_key='timezone', value='Asia/Manila', description='System timezone'),
                SystemSetting(setting_key='service_fee', value='5', description='Service fee percentage'),
                SystemSetting(setting_key='gcash_account', value='0917 123 4567', description='GCash account number'),
                SystemSetting(setting_key='enable_gcash', value='true', description='Enable GCash payments'),
                SystemSetting(setting_key='enable_cod', value='true', description='Enable Cash on Delivery')
            ]
            db.session.add_all(settings)
            print("Default settings added successfully!")
        
        db.session.commit()
        print("Database initialized successfully!")

# ==================== TECHNICIAN BLUEPRINTS ====================
# Registered here (after app, db, csrf, limiter and all models exist) so the
# blueprints can import from this module without a circular-import error.
from blueprints.technician import technician_bp
from blueprints.technician_api import technician_api_bp

app.register_blueprint(technician_bp, url_prefix='/technician')
app.register_blueprint(technician_api_bp, url_prefix='/technician/api')


if __name__ == '__main__':
    with app.app_context():
        init_db()
        
    dev_host = os.environ.get('DEV_HOST', '127.0.0.1')
    app.run(debug=app.config['DEBUG'], host=dev_host, port=5000, ssl_context='adhoc')