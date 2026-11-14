"""The service catalog: replacing the old list in place (ids and bookings kept),
adding the rest without duplicates, the customer catalog page and its booking link."""
from datetime import date, time, timedelta
from decimal import Decimal

from app import db, Booking, Service, ServiceCategory, init_db
from services.service_catalog import CATALOG, sync_service_catalog

TOMORROW = (date.today() + timedelta(days=1)).isoformat()
TOTAL = sum(len(c['services']) for c in CATALOG)

# What the live database had before the list was replaced (categories, services, prices).
OLD = [
    ('hardware-repair', 'Hardware Repair', [('Laptop No-Power Troubleshooting', 700), ('Motherboard Troubleshooting', 900)]),
    ('software-fix', 'Software Fix', [('Slow Computer Optimization', 600), ('Virus and Malware Removal', 800)]),
    ('hardware-upgrade', 'Hardware Upgrade', [('Laptop RAM Upgrade', 2500), ('SSD Installation', 3200)]),
    ('data-recovery', 'Data Recovery and Backup', [('HDD File Recovery', 5000)]),
    ('storage-upgrade', 'Storage Upgrade', [('HDD-to-SSD Migration', 3200)]),
    ('accessory-replacement', 'Accessory Replacement', [('Laptop Screen / LCD Replacement', 3500), ('Webcam Replacement', 800)]),
]


def _old_catalog():
    ids = {}
    for slug, name, services in OLD:
        cat = ServiceCategory(name=name, slug=slug, is_active=True)
        db.session.add(cat)
        db.session.flush()
        for svc_name, price in services:
            svc = Service(category_id=cat.id, name=svc_name, price=price, estimated_hours=2, is_active=True)
            db.session.add(svc)
            db.session.flush()
            ids[svc_name] = svc.id
    db.session.commit()
    return ids


def _sync(replace=False):
    return sync_service_catalog(db, ServiceCategory, Service, replace=replace)


def _shown():
    return Service.query.filter_by(is_active=True)


def test_the_list_has_every_service_once_with_a_starting_price():
    names = [s['name'].lower() for c in CATALOG for s in c['services']]
    assert len(names) == len(set(names)) == 166
    assert all(s['price'] > 0 and s['devices'] for c in CATALOG for s in c['services'])
    assert [c['name'] for c in CATALOG] == [
        'Accessory Replacement Services', 'Data Recovery and Backup Services', 'Hardware Repair Services',
        'Hardware Upgrade and Installation', 'Smartphone and Tablet Repair', 'Software Repair and Operating System Fixes']


def test_replacing_keeps_ids_and_bookings_and_hides_what_is_not_listed(customer):
    ids = _old_catalog()
    booking = Booking(booking_number='BK-OLD-1', user_id=customer.id, service_id=ids['Laptop Screen / LCD Replacement'],
                      device_type='Laptop', description='x', booking_date=date.today(), booking_time=time(9, 0),
                      status='released', is_in_shop=True)
    db.session.add(booking)
    db.session.commit()
    category_ids = {c.slug: c.id for c in ServiceCategory.query.all()}

    _sync(replace=True)
    assert _shown().count() == TOTAL
    names = [s.name.lower() for s in Service.query.all()]
    assert len(names) == len(set(names))                             # nothing duplicated
    after = {c.slug: c.id for c in ServiceCategory.query.all()}
    assert {slug: after[slug] for slug in category_ids} == category_ids   # same category ids
    assert not ServiceCategory.query.filter_by(slug='storage-upgrade').one().is_active   # not on the new list

    screen = db.session.get(Service, ids['Laptop Screen / LCD Replacement'])        # renamed in place
    assert (screen.name, screen.price, screen.is_active) == ('Laptop LCD / LED Screen Replacement', Decimal('1000.00'), True)
    assert db.session.get(Booking, booking.id).service_id == screen.id   # the booking still points at it
    assert db.session.get(Service, ids['Laptop RAM Upgrade']).price == Decimal('300.00')   # the listed price wins
    assert db.session.get(Service, ids['HDD-to-SSD Migration']).name == 'Laptop SSD Upgrade'
    webcam = db.session.get(Service, ids['Webcam Replacement'])
    assert not webcam.is_active and webcam.name == 'Webcam Replacement'   # not listed: hidden, not deleted
    assert db.session.get(Service, ids['SSD Installation']).is_active is False

    assert _sync(replace=True) == []                                  # running it again changes nothing


def test_a_normal_sync_keeps_admin_prices_and_additions(app):
    _old_catalog()
    cat = ServiceCategory.query.filter_by(slug='hardware-repair').one()
    db.session.add(Service(category_id=cat.id, name='Printer Head Cleaning', price=450, is_active=True))
    db.session.commit()
    _sync()
    assert _sync() == []
    assert Service.query.filter_by(name='Laptop RAM Upgrade').one().price == Decimal('2500.00')   # admin price kept
    assert Service.query.filter_by(name='Printer Head Cleaning').one().is_active


def test_a_new_database_gets_the_catalog_with_its_starting_prices(app):
    init_db()
    assert ServiceCategory.query.count() == len(CATALOG) and _shown().count() == TOTAL
    assert Service.query.filter_by(name='Motherboard Component-Level Repair').one().price == Decimal('2000.00')


def test_catalog_page_lists_only_bookable_services(customer_logged_in):
    from app import app as flask_app
    flask_app.config['PAYMONGO_ENABLED'] = True              # shows the booking fee fact
    _old_catalog()
    _sync(replace=True)
    Service.query.filter_by(name='Laptop Webcam Replacement').one().is_active = False
    hidden_cat = ServiceCategory(name='Old Stuff', slug='old-stuff', is_active=True)
    db.session.add(hidden_cat)
    db.session.commit()
    html = customer_logged_in.get('/user/services').get_data(as_text=True)
    assert 'Laptop LCD / LED Screen Replacement' in html and 'From ₱1,000' in html
    assert 'Price upon diagnosis' not in html and 'not guaranteed' in html and 'For laptops' in html
    assert 'Laptop Webcam Replacement' not in html                   # hidden service
    assert 'Old Stuff' not in html and 'Storage Upgrade' not in html  # nothing bookable
    assert f'<strong>{TOTAL - 1}</strong><span>services</span>' in html and 'booking fee' in html
    svc = Service.query.filter_by(name='Laptop RAM Upgrade').one()
    assert f'/user/book/hardware-upgrade?service={svc.id}' in html
    assert 'id="catalogSearch"' in html and 'id="catalogNoResults"' in html


def test_booking_page_preselects_the_service_and_saves_brand_and_model(customer_logged_in):
    _old_catalog()
    _sync(replace=True)
    from app import app as flask_app
    flask_app.config['PAYMONGO_ENABLED'] = True              # the QR booking fee needs online payments
    svc = Service.query.filter_by(name='Laptop RAM Upgrade').one()
    page = customer_logged_in.get(f'/user/book/hardware-upgrade?service={svc.id}').get_data(as_text=True)
    assert f'value="{svc.id}"' in page and 'selected' in page.split(f'value="{svc.id}"')[1][:400]
    for device in ('Tablet', 'Smartphone', 'Monitor', 'Storage Device'):
        assert f'value="{device}"' in page
    assert 'All-in-One PC' not in page and 'Printer / Peripheral' not in page
    assert 'data-fee="100"' in page and 'deducted from your final bill' in page
    customer_logged_in.post('/user/service-request', data={
        'service_id': str(svc.id), 'device_type': 'Laptop', 'device_brand': ' Acer ', 'device_model': 'Aspire 5',
        'problem_description': 'The laptop is slow and I want to add 16 GB of memory', 'booking_date': TOMORROW, 'booking_time': '10:00', 'in_shop': 'on',
        'payment_method': 'QR Ph', 'accept_terms': 'on'})
    b = Booking.query.one()
    assert (b.device_type, b.device_brand, b.device_model) == ('Laptop', 'Acer', 'Aspire 5')
    assert b.booking_fee == Decimal('100.00') and b.transaction.amount == Decimal('200.00')   # ₱300 - ₱100


def test_admin_sets_a_starting_price_and_devices(admin_logged_in):
    _old_catalog()
    _sync(replace=True)
    html = admin_logged_in.get('/admin/services').get_data(as_text=True)
    assert 'Upon diagnosis' not in html and 'name="device_types" value="smartphone"' in html
    svc = Service.query.filter_by(name='Laptop Webcam Replacement').one()
    form = {'name': svc.name, 'category_id': svc.category_id, 'price': '0', 'estimated_hours': '1'}
    admin_logged_in.post(f'/admin/services/{svc.id}', data=form)
    assert db.session.get(Service, svc.id).price == 700          # a zero price is refused
