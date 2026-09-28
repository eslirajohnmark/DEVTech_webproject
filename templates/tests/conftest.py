"""Pytest fixtures. Runs against in-memory SQLite; never touches MySQL."""
import os
import pytest

os.environ['DATABASE_URL'] = 'sqlite:///:memory:'
os.environ['FLASK_ENV'] = 'testing'
os.environ['SECRET_KEY'] = 'test-secret-not-for-production'

from app import app as flask_app, db, User, Booking, ServiceCategory, Service  # noqa: E402
from models.technician_models import (  # noqa: E402
    IntakeRecord, ServiceReport, IncidentReport,
    ApprovalRequest, JobLog, UploadedFile, ServiceRating,
)


@pytest.fixture
def app():
    flask_app.config['TESTING'] = True
    flask_app.config['WTF_CSRF_ENABLED'] = False
    flask_app.config['RATELIMIT_ENABLED'] = False
    flask_app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
    flask_app.config['TECH_UPLOAD_FOLDER'] = '/tmp/devtech-test-uploads'
    os.makedirs(flask_app.config['TECH_UPLOAD_FOLDER'], exist_ok=True)

    with flask_app.app_context():
        db.drop_all()
        db.create_all()
        yield flask_app
        db.session.remove()
        db.drop_all()


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def technician(app):
    u = User(username='TECH-0001', email='tech@test.local',
             full_name='Test Technician', role='technician',
             is_active=True, id_verified=True)
    u.set_password('testpassword1')
    db.session.add(u)
    db.session.commit()
    return u


@pytest.fixture
def customer(app):
    u = User(username='customer1', email='customer@test.local',
             full_name='Test Customer', role='customer', is_active=True)
    u.set_password('customerpass1')
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
                booking_date='2025-01-15', booking_time='10:00:00',
                status='confirmed', is_in_shop=True,
                technician_id=technician.id)
    db.session.add(b)
    db.session.commit()
    return b


@pytest.fixture
def tech_logged_in(client, technician):
    with client.session_transaction() as s:
        s['user_id'] = technician.id
        s['username'] = technician.username
        s['role'] = 'technician'
    return client