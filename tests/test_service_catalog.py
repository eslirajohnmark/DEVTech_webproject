"""The improved service catalog: renaming the existing records in place, adding
the rest without duplicates, the customer catalog page and its booking link."""
from datetime import date, time, timedelta
from decimal import Decimal

from app import db, Booking, Service, ServiceCategory, init_db
from services.service_catalog import CATALOG, sync_service_catalog

TOMORROW = (date.today() + timedelta(days=1)).isoformat()
TOTAL = sum(len(c['services']) for c in CATALOG)

# What the live database had before this change (categories, services, prices).
OLD = [
    ('hardware-repair', 'Hardware Repair', [('Laptop Screen Replacement', 3500), ('Battery Replacement', 1800)]),
    ('software-fix', 'Software Fix', [('Virus Removal', 1500), ('System Optimization', 1200)]),
    ('hardware-upgrade', 'Hardware Upgrade', [('RAM Upgrade', 2500), ('SSD Installation', 3200)]),
    ('data-recovery', 'Data Recovery', [('Data Recovery', 5000)]),
    ('storage-upgrade', 'Storage Upgrade', [('HDD to SSD Migration', 3200)]),
    ('accessory-replacement', 'Accessory Replacement', [('Charger Adapter Replacement', 1200)]),
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


def _sync():
    return sync_service_catalog(db, ServiceCategory, Service)


def test_existing_records_are_renamed_in_place_and_keep_prices(customer):
    ids = _old_catalog()
    booking = Booking(booking_number='BK-OLD-1', user_id=customer.id, service_id=ids['Laptop Screen Replacement'],
                      device_type='Laptop', description='x', booking_date=date.today(), booking_time=time(9, 0),
                      status='released', is_in_shop=True)
    db.session.add(booking)
    db.session.commit()
    category_ids = {c.slug: c.id for c in ServiceCategory.query.all()}

    _sync()
    assert ServiceCategory.query.count() == len(CATALOG)                       # renamed, not duplicated
    after = {c.slug: c.id for c in ServiceCategory.query.all()}
    assert {slug: after[slug] for slug in category_ids} == category_ids   # same ids, plus the new phone/tablet category
    assert Service.query.count() == TOTAL
    screen = db.session.get(Service, ids['Laptop Screen Replacement'])
    assert (screen.name, screen.price, screen.estimated_hours) == ('Laptop Screen / LCD Replacement', Decimal('3500.00'), 2)
    assert db.session.get(Booking, booking.id).service_id == screen.id   # the booking still points at it
    battery = db.session.get(Service, ids['Battery Replacement'])
    assert battery.name == 'Laptop Battery Replacement' and battery.category.slug == 'accessory-replacement'
    assert db.session.get(Service, ids['Data Recovery']).name == 'HDD File Recovery'
    new = Service.query.filter_by(name='Deleted File Recovery').one()
    assert new.price == 1000 and new.device_list == ['laptop', 'desktop', 'storage']   # a starting price for every service
    assert ServiceCategory.query.filter_by(slug='data-recovery').one().name == 'Data Recovery and Backup'
    names = [s.name.lower() for s in Service.query.all()]
    assert len(names) == len(set(names))                             # no duplicate services


def test_running_it_again_changes_nothing_and_keeps_admin_additions(app):
    _old_catalog()
    cat = ServiceCategory.query.filter_by(slug='hardware-repair').one()
    db.session.add(Service(category_id=cat.id, name='Printer Head Cleaning', price=450, is_active=True))
    db.session.commit()
    _sync()
    assert _sync() == []
    assert Service.query.count() == TOTAL + 1
    assert Service.query.filter_by(name='Printer Head Cleaning').one().price == Decimal('450.00')


def test_a_new_database_gets_the_catalog_with_the_original_default_prices(app):
    init_db()
    assert ServiceCategory.query.count() == len(CATALOG) and Service.query.count() == TOTAL
    assert Service.query.filter_by(name='Laptop Screen / LCD Replacement').one().price == Decimal('3500.00')


def test_catalog_page_lists_only_bookable_services(customer_logged_in):
    _old_catalog()
    _sync()
    Service.query.filter_by(name='Webcam Replacement').one().is_active = False
    hidden_cat = ServiceCategory(name='Old Stuff', slug='old-stuff', is_active=True)
    db.session.add(hidden_cat)
    db.session.commit()
    html = customer_logged_in.get('/user/services').get_data(as_text=True)
    assert 'Laptop Screen / LCD Replacement' in html and 'From ₱3,500' in html
    assert 'Price upon diagnosis' not in html and 'not guaranteed' in html and 'For laptops' in html
    assert 'Webcam Replacement' not in html                          # hidden service
    assert 'Old Stuff' not in html                                    # category with nothing bookable
    svc = Service.query.filter_by(name='SSD Installation').one()
    assert f'/user/book/hardware-upgrade?service={svc.id}' in html
    assert 'id="catalogSearch"' in html and 'id="catalogNoResults"' in html


def test_booking_page_preselects_the_service_and_saves_brand_and_model(customer_logged_in):
    _old_catalog()
    _sync()
    svc = Service.query.filter_by(name='Laptop RAM Upgrade').one()
    page = customer_logged_in.get(f'/user/book/hardware-upgrade?service={svc.id}').get_data(as_text=True)
    assert f'value="{svc.id}"' in page and 'selected' in page.split(f'value="{svc.id}"')[1][:400]
    for device in ('Tablet', 'Smartphone', 'Monitor', 'Storage Device'):
        assert f'value="{device}"' in page
    assert 'All-in-One PC' not in page and 'Printer / Peripheral' not in page
    customer_logged_in.post('/user/service-request', data={
        'service_id': str(svc.id), 'device_type': 'Laptop', 'device_brand': ' Acer ', 'device_model': 'Aspire 5',
        'problem_description': 'The laptop is slow and I want to add 16 GB of memory', 'booking_date': TOMORROW, 'booking_time': '10:00', 'in_shop': 'on',
        'payment_method': 'QR Ph', 'accept_terms': 'on'})
    b = Booking.query.one()
    assert (b.device_type, b.device_brand, b.device_model) == ('Laptop', 'Acer', 'Aspire 5')


def test_admin_sets_a_starting_price_and_devices(admin_logged_in):
    _old_catalog()
    _sync()
    html = admin_logged_in.get('/admin/services').get_data(as_text=True)
    assert 'Upon diagnosis' not in html and 'name="device_types" value="smartphone"' in html
    svc = Service.query.filter_by(name='Webcam Replacement').one()
    form = {'name': svc.name, 'category_id': svc.category_id, 'price': '0', 'estimated_hours': '1'}
    admin_logged_in.post(f'/admin/services/{svc.id}', data=form)
    assert db.session.get(Service, svc.id).price == 800          # a zero price is refused
