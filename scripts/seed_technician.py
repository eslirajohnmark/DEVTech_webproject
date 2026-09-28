"""Seed demo technician accounts and one sample booking chain.

Usage:
    python -m scripts.seed_technician           # create if missing
    python -m scripts.seed_technician --reset   # wipe tech data first

Safe to re-run — every insert checks for an existing row first.
"""
import argparse
from datetime import datetime

from app import app, db, User, Booking, ServiceCategory, Service


DEFAULT_TECHS = [
    {
        'username': 'TECH-0001',
        'email':    'carlos@devtech.local',
        'full_name': 'Carlos Mendoza',
        'password': '1234',
    },
    {
        'username': 'TECH-0002',
        'email':    'sarah@devtech.local',
        'full_name': 'Sarah Lim',
        'password': '1234',
    },
]

DEFAULT_CUSTOMER = {
    'username': 'customer1',
    'email':    'customer@devtech.local',
    'full_name': 'Maria Santos',
    'password': 'customer1234',
}


def _ensure_tech(spec):
    existing = User.query.filter_by(username=spec['username']).first()
    if existing:
        print(f'  skip  {spec["username"]} (already exists)')
        return existing
    u = User(
        username=spec['username'],
        email=spec['email'],
        full_name=spec['full_name'],
        role='technician',
        is_active=True,
        id_verified=True,
    )
    u.set_password(spec['password'])
    db.session.add(u)
    db.session.commit()
    print(f'  add   {spec["username"]}  pw={spec["password"]}')
    return u


def _ensure_customer(spec):
    existing = User.query.filter_by(username=spec['username']).first()
    if existing:
        print(f'  skip  {spec["username"]} (already exists)')
        return existing
    u = User(
        username=spec['username'],
        email=spec['email'],
        full_name=spec['full_name'],
        role='customer',
        is_active=True,
    )
    u.set_password(spec['password'])
    db.session.add(u)
    db.session.commit()
    print(f'  add   {spec["username"]}  pw={spec["password"]}')
    return u


def _ensure_sample_booking(tech, customer):
    if not tech or not customer:
        return
    if Booking.query.filter_by(booking_number='BK-SEED-0001').first():
        print('  skip  sample booking (already exists)')
        return

    cat = ServiceCategory.query.first()
    if not cat:
        cat = ServiceCategory(name='Hardware Repair',
                              icon='fa-server', is_active=True)
        db.session.add(cat)
        db.session.flush()

    svc = Service.query.filter_by(category_id=cat.id).first()
    if not svc:
        svc = Service(category_id=cat.id, name='Screen Repair',
                      price=1000, estimated_hours=1, is_active=True)
        db.session.add(svc)
        db.session.flush()

    b = Booking(
        booking_number='BK-SEED-0001',
        user_id=customer.id,
        service_id=svc.id,
        device_type='Laptop',
        description='Cracked screen',
        address='123 Rizal Ave',
        booking_date=datetime.utcnow().date(),
        booking_time=datetime.utcnow().time(),
        status='confirmed',
        is_in_shop=True,
        technician_id=tech.id,
        assigned_at=datetime.utcnow(),
    )
    db.session.add(b)
    db.session.commit()
    print(f'  add   sample booking {b.booking_number}')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--reset', action='store_true',
                        help='Delete all existing tech data first')
    args = parser.parse_args()

    with app.app_context():
        if args.reset:
            from models.technician_models import (
                IntakeRecord, ServiceReport, IncidentReport,
                ApprovalRequest, JobLog, UploadedFile, ServiceRating,
            )
            for model in (ServiceRating, UploadedFile, JobLog,
                          ApprovalRequest, IncidentReport,
                          ServiceReport, IntakeRecord):
                model.query.delete()
            Booking.query.filter(
                Booking.booking_number.like('BK-SEED-%')
            ).delete()
            User.query.filter(User.username.like('TECH-%')).delete()
            db.session.commit()
            print('Reset: removed existing tech data.')

        print('Seeding technicians...')
        techs = [_ensure_tech(s) for s in DEFAULT_TECHS]

        print('Seeding customer...')
        customer = _ensure_customer(DEFAULT_CUSTOMER)

        print('Seeding sample booking...')
        _ensure_sample_booking(techs[0], customer)

        print()
        print('Done.')
        print()
        print('Technician logins:')
        for s in DEFAULT_TECHS:
            print(f'  {s["username"]} / {s["password"]}')
        print(f'  {DEFAULT_CUSTOMER["username"]} / {DEFAULT_CUSTOMER["password"]}  (customer)')
        print()
        print('Sign in at /technician/login')


if __name__ == '__main__':
    main()