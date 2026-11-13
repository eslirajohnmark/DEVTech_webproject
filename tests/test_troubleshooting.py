"""Troubleshooting assistant (services/troubleshooter.py + /api/troubleshoot) and the
booking rules that come with it: a specific description and a service that fits the device."""
from datetime import date, timedelta

from app import db, Booking, Service, ServiceCategory
from services import troubleshooter
from services.service_catalog import sync_service_catalog

TOMORROW = (date.today() + timedelta(days=1)).isoformat()


def _post(client, device, category, text):
    return client.post('/api/troubleshoot', json={'device': device, 'category': category, 'description': text})


def test_random_letters_and_vague_text_are_refused(customer_logged_in):
    for text in ('hjsdhfdfsdf', 'asdf qwer zxcv asdfgh', 'it is broken', 'sdfsdf sdfsdf sdfsdf sdfsd fs'):
        r = _post(customer_logged_in, 'desktop', 'startup', text)
        assert r.status_code == 422 and r.get_json()['message'].startswith('Please be specific'), text


def test_specific_symptoms_give_high_confidence_and_a_priced_service(customer_logged_in):
    sync_service_catalog(db, ServiceCategory, Service)
    r = _post(customer_logged_in, 'laptop', 'startup',
              "My laptop won't turn on, no lights when I press the power button").get_json()
    assert r['confidence'] == 'high' and r['title'] == 'No power at all' and r['steps']
    assert "won't turn on" in r['evidence'] and r['service']['name'] == 'Laptop No-Power Troubleshooting'
    assert r['service']['price'] == 700 and 'device=Laptop' in r['service']['book_url']


def test_not_knowing_the_cause_gives_low_confidence_and_no_diy_steps(customer_logged_in):
    sync_service_catalog(db, ServiceCategory, Service)
    r = _post(customer_logged_in, 'laptop', 'other',
              "I don't know what happened, it just stopped working yesterday").get_json()
    assert r['confidence'] == 'low' and r['steps'] == [] and 'technician' in r['advice']
    assert r['service']['name'] == 'RAM Detection and Hardware Fault Diagnosis'


def test_urgent_problems_stop_the_customer(customer_logged_in):
    r = troubleshooter.diagnose('smartphone', 'other', 'nabasa ng tubig kahapon tapos ayaw na mag on')
    assert r['urgent'] and r['title'] == 'Liquid damage' and not r['diy']


def test_a_different_problem_type_lowers_confidence():
    r = troubleshooter.diagnose('laptop', 'screen', 'wifi keeps dropping and says no internet even when connected')
    assert r['confidence'] == 'medium' and r['category_mismatch'] == 'Wi-Fi or internet'


def _book(client, service, device='Laptop', text='The laptop screen is cracked after it fell off the table'):
    return client.post('/user/service-request', data={
        'service_id': str(service.id), 'device_type': device, 'problem_description': text,
        'booking_date': TOMORROW, 'booking_time': '10:00', 'in_shop': 'on', 'payment_method': 'C.A.R',
        'accept_terms': 'on'})


def test_booking_needs_a_specific_description_and_a_matching_device(customer_logged_in):
    sync_service_catalog(db, ServiceCategory, Service)
    phone_screen = Service.query.filter_by(name='Smartphone Screen Replacement').one()
    _book(customer_logged_in, phone_screen, device='Smartphone', text='hjsdhfdfsdf')
    assert Booking.query.count() == 0
    _book(customer_logged_in, phone_screen, device='Laptop', text='The phone screen is cracked and touch does not work')
    assert Booking.query.count() == 0                              # a phone service for a laptop
    _book(customer_logged_in, phone_screen, device='All-in-One PC', text='The phone screen is cracked and touch does not work')
    assert Booking.query.count() == 0                              # device type no longer offered
    _book(customer_logged_in, phone_screen, device='Smartphone', text='The phone screen is cracked and touch does not work')
    assert Booking.query.one().device_type == 'Smartphone'


def test_troubleshooting_page_prefills_the_booking_form(customer_logged_in):
    sync_service_catalog(db, ServiceCategory, Service)
    html = customer_logged_in.get('/user/troubleshooting').get_data(as_text=True)
    assert 'data-device="smartphone"' in html and 'Check my device' in html
    svc = Service.query.filter_by(name='Laptop No-Power Troubleshooting').one()
    page = customer_logged_in.get(f'/user/book/{svc.category.slug}?service={svc.id}&device=Tablet&issue=It+will+not+turn+on+at+all')
    body = page.get_data(as_text=True)
    assert 'value="Tablet" checked' in body and 'It will not turn on at all</textarea>' in body
