"""Tacloban City's real outline (not a box) for home-service and delivery pins, and
the downtown shop shown for in-shop repairs."""
import json
from datetime import date, timedelta

from app import db, Booking, Service, ServiceCategory, shop_location
from services import geo

TOMORROW = (date.today() + timedelta(days=1)).isoformat()

INSIDE = {'downtown shop': (11.24366, 125.00337), 'Robinsons Marasbaras': (11.2136, 124.9955),
          'the airport': (11.2275, 125.0270), 'Sagkahan': (11.2391, 124.9925)}
OUTSIDE = {'Palo town': (11.1580, 124.9900), 'Basey, Samar': (11.2820, 125.0680), 'Cancabato Bay water': (11.2300, 125.0600),
           'Babatngon': (11.4210, 124.8440), 'Alangalang': (11.2070, 124.8480),
           # inside the old 11.10-11.36 / 124.90-125.12 box, outside the city
           'Santa Fe (was inside the old box)': (11.1880, 124.9150)}


def test_the_outline_is_the_city_not_a_box():
    data = json.load(open(geo.BOUNDARY_FILE, encoding='utf-8'))
    geom = data['features'][0]['geometry']
    parts = geom['coordinates'] if geom['type'] == 'MultiPolygon' else [geom['coordinates']]
    assert sum(len(ring) for poly in parts for ring in poly) > 150 and data['features'][0]['properties']['psgc'] == '0831600000'
    for name, (lat, lng) in INSIDE.items():
        assert geo.inside_tacloban(lat, lng), name
    for name, (lat, lng) in OUTSIDE.items():
        assert not geo.inside_tacloban(lat, lng), name
    assert not geo.inside_tacloban('x', None)


def _book_home(client, lat, lng):
    cat = ServiceCategory(name='Repair', slug='repair', is_active=True)
    db.session.add(cat)
    db.session.flush()
    svc = Service(category_id=cat.id, name='Laptop No Power Repair', price=800, is_active=True, device_types='laptop')
    db.session.add(svc)
    db.session.commit()
    return client.post('/user/service-request', data={
        'service_id': str(svc.id), 'device_type': 'Laptop', 'problem_description': 'The laptop does not turn on at all since yesterday',
        'booking_date': TOMORROW, 'booking_time': '10:00', 'service_address': '12 Real Street, Tacloban City',
        'pinned_lat': str(lat), 'pinned_lng': str(lng), 'payment_method': 'C.A.R', 'accept_terms': 'on'})


def test_home_service_outside_the_city_line_is_refused(customer_logged_in):
    _book_home(customer_logged_in, *OUTSIDE['Santa Fe (was inside the old box)'])
    assert Booking.query.count() == 0


def test_home_service_inside_the_city_is_booked(customer_logged_in):
    _book_home(customer_logged_in, *INSIDE['Sagkahan'])
    b = Booking.query.one()
    assert not b.is_in_shop and float(b.latitude) == INSIDE['Sagkahan'][0]


def test_delivery_pins_must_be_inside_the_city(customer_logged_in):
    form = {'full_name': 'Cara Customer', 'phone': '09170000000', 'address': '12 Real Street', 'city': 'Tacloban City',
            'province': 'Leyte', 'postal_code': '6500'}
    r = customer_logged_in.post('/api/user/address', json=dict(form, latitude=11.2820, longitude=125.0680))
    assert r.status_code == 400 and 'inside Tacloban City' in r.get_json()['message']
    r = customer_logged_in.post('/api/user/address', json=dict(form, latitude=11.2391, longitude=124.9925))
    assert r.get_json()['success']


def test_the_downtown_shop_is_the_default_shop(customer_logged_in, app):
    loc = shop_location()
    assert (loc['lat'], loc['lng']) == (geo.DEFAULT_SHOP['lat'], geo.DEFAULT_SHOP['lng'])
    assert geo.inside_tacloban(loc['lat'], loc['lng'])
    html = customer_logged_in.get('/user/book').get_data(as_text=True)
    assert 'id="shopCard"' in html and '118 Rizal Avenue' in html and 'Mon-Sat, 8:00 AM - 6:00 PM' in html
    assert f'destination={geo.DEFAULT_SHOP["lat"]},{geo.DEFAULT_SHOP["lng"]}' in html
    assert 'vendor/leaflet/leaflet.js' in html and 'unpkg.com/leaflet' not in html
