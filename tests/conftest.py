"""Pytest fixtures. Runs against in-memory SQLite; never touches MySQL."""
import os
from datetime import date, time

import pytest

os.environ['DATABASE_URL'] = 'sqlite:///:memory:'
os.environ['FLASK_ENV'] = 'testing'
os.environ['SECRET_KEY'] = 'test-secret-not-for-production'

from app import (app as flask_app, db, Customer, Technician, Admin,  # noqa: E402
                 Booking, ServiceCategory, Service)
from models.technician_models import (  # noqa: E402
    IntakeRecord, ServiceReport, IncidentReport,
    ApprovalRequest, JobLog, UploadedFile, ServiceRating,
)


@pytest.fixture
def app(tmp_path):
    flask_app.config['TESTING'] = True
    flask_app.config['WTF_CSRF_ENABLED'] = False
    flask_app.config['RATELIMIT_ENABLED'] = False
    flask_app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
    flask_app.config['TECH_UPLOAD_FOLDER'] = str(tmp_path / 'tech')
    flask_app.config['RECEIPT_UPLOAD_FOLDER'] = str(tmp_path / 'receipts')
    flask_app.config['MESSAGE_UPLOAD_FOLDER'] = str(tmp_path / 'messages')
    for key in ('TECH_UPLOAD_FOLDER', 'RECEIPT_UPLOAD_FOLDER', 'MESSAGE_UPLOAD_FOLDER'):
        os.makedirs(flask_app.config[key], exist_ok=True)

    with flask_app.app_context():
        db.drop_all()
        db.create_all()
        yield flask_app
        db.session.remove()
        db.drop_all()


@pytest.fixture
def client(app):
    return app.test_client()


def login_as(client, user):
    with client.session_transaction() as s:
        s['user_id'] = user.id
        s['username'] = user.username
        s['role'] = user.role
    return client


@pytest.fixture
def technician(app):
    u = Technician(username='TECH-0001', email='tech@test.local',
                   full_name='Test Technician', is_active=True, id_verified=True)
    u.set_password('testpassword1')
    db.session.add(u)
    db.session.commit()
    return u


@pytest.fixture
def customer(app):
    u = Customer(username='customer1', email='customer@test.local',
                 full_name='Test Customer', is_active=True)
    u.set_password('customerpass1')
    db.session.add(u)
    db.session.commit()
    return u


@pytest.fixture
def admin(app):
    u = Admin(username='admin1', email='admin@test.local',
              full_name='Test Admin', is_active=True)
    u.set_password('adminpass123')
    db.session.add(u)
    db.session.commit()
    return u


@pytest.fixture
def assigned_booking(app, technician, customer):
    cat = ServiceCategory(name='Test Cat', is_active=True)
    db.session.add(cat)
    db.session.flush()
    svc = Service(category_id=cat.id, name='Screen Repair',
                  price=1000.00, is_active=True)
    db.session.add(svc)
    db.session.flush()
    b = Booking(booking_number='BK-TEST-0001', user_id=customer.id,
                service_id=svc.id, device_type='Laptop',
                description='Cracked screen',
                booking_date=date(2025, 1, 15), booking_time=time(10, 0),
                status='confirmed', is_in_shop=True,
                technician_id=technician.id)
    db.session.add(b)
    db.session.commit()
    return b


@pytest.fixture
def tech_logged_in(client, technician):
    return login_as(client, technician)


@pytest.fixture
def customer_logged_in(client, customer):
    return login_as(client, customer)


@pytest.fixture
def admin_logged_in(client, admin):
    return login_as(client, admin)
