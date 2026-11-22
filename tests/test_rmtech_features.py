"""Features brought over from the RMTech project: per-service fees, the customer's
"I received my device", intake photos, the profile photo rule, live profile updates,
the Settings Danger Zone, reading a valid ID's printed text for the roster, the
amount to be paid on the service report, and confirmation prompts."""
import io
from datetime import date, datetime, timedelta

import pytest

from app import (db, app as flask_app, Booking, Customer, Notification, Service, ServiceCategory, SystemSetting,
                 Technician, Transaction, suggested_service_fee, _live_stamp)
from models.technician_models import ApprovalRequest, IntakeRecord, JobLog, ServiceReport, UploadedFile
from tests.conftest import payment_proof, login_as


def _category(name='Hardware Repair Services', slug='hardware-repair'):
    cat = ServiceCategory(name=name, slug=slug, is_active=True)
    db.session.add(cat)
    db.session.flush()
    return cat


def _service(price=700, fee=50, name='Laptop Overheating Repair', cat=None):
    cat = cat or _category()
    svc = Service(category_id=cat.id, name=name, price=price, service_fee=fee, estimated_hours=2, is_active=True)
    db.session.add(svc)
    db.session.commit()
    return svc


# ---- service fee ------------------------------------------------------------------

@pytest.mark.parametrize('price, fee', [(0, 50), (300, 50), (700, 50), (1000, 100), (1500, 150), (2500, 250),
                                        (8000, 500)])
def test_suggested_fee_is_ten_percent_rounded_and_kept_in_range(price, fee):
    assert suggested_service_fee(price) == fee


def test_catalog_services_get_the_suggested_fee_and_keep_one_the_admin_changed(app):
    from services.service_catalog import sync_service_catalog
    sync_service_catalog(db, ServiceCategory, Service)
    db.session.commit()
    battery = Service.query.filter_by(name='Laptop Battery Replacement').one()
    assert float(battery.service_fee) == suggested_service_fee(battery.price)
    battery.service_fee = 75
    db.session.commit()
    sync_service_catalog(db, ServiceCategory, Service)
    db.session.commit()
    assert float(db.session.get(Service, battery.id).service_fee) == 75


def test_admin_sets_a_fee_blank_means_suggested_and_negative_is_refused(admin_logged_in):
    cat = _category()
    db.session.commit()
    form = {'name': 'Laptop Screen Repair', 'category_id': cat.id, 'price': '1500', 'estimated_hours': '2'}
    admin_logged_in.post('/admin/services', data={**form, 'service_fee': ''})
    svc = Service.query.filter_by(name='Laptop Screen Repair').one()
    assert float(svc.service_fee) == 150
    admin_logged_in.post(f'/admin/services/{svc.id}', data={**form, 'service_fee': '0'})
    assert float(db.session.get(Service, svc.id).service_fee) == 0
    admin_logged_in.post(f'/admin/services/{svc.id}', data={**form, 'service_fee': '-5'})
    assert float(db.session.get(Service, svc.id).service_fee) == 0


def test_admin_sets_one_fee_for_a_category_or_resets_all_to_suggested(admin_logged_in):
    cat = _category()
    other = _category('Software Repair', 'software')
    a = _service(1000, 100, 'A', cat)
    b = _service(3000, 300, 'B', other)
    admin_logged_in.post('/admin/services/fees', data={'scope': str(cat.id), 'mode': 'fixed', 'amount': '120'})
    assert (float(db.session.get(Service, a.id).service_fee), float(db.session.get(Service, b.id).service_fee)) == (120, 300)
    admin_logged_in.post('/admin/services/fees', data={'scope': 'all', 'mode': 'suggested'})
    assert (float(db.session.get(Service, a.id).service_fee), float(db.session.get(Service, b.id).service_fee)) == (100, 300)
    r = admin_logged_in.post('/admin/services/fees', data={'scope': 'all', 'mode': 'fixed', 'amount': 'abc'},
                             follow_redirects=True)
    assert 'Enter a service fee' in r.get_data(as_text=True)


def test_services_page_offers_the_fee_tools_with_confirmations(admin_logged_in):
    _service()
    page = admin_logged_in.get('/admin/services').get_data(as_text=True)
    assert 'Set service fees' in page and 'name="service_fee"' in page
    assert 'data-confirm-title="Change the service fee?"' in page
    assert 'data-confirm-title="Hide Laptop Overheating Repair?"' in page
    assert 'onclick="return confirm(' not in page


def test_customers_see_the_fee_in_the_api_catalog_and_booking_form(customer_logged_in):
    svc = _service(700, 50)
    data = customer_logged_in.get('/api/services').get_json()
    assert data[0]['service_fee'] == 50 and data[0]['starting_total'] == 750
    assert '+ ₱50 service fee' in customer_logged_in.get('/user/services').get_data(as_text=True)
    form = customer_logged_in.get('/user/book').get_data(as_text=True)
    assert f'data-service-fee="{svc.service_fee}"' in form and '+ ₱50 service fee' in form


def test_the_bill_includes_the_service_fee(customer_logged_in, customer):
    svc = _service(700, 50)
    customer_logged_in.post('/user/book', data={
        'service_id': svc.id, 'device_type': 'Laptop', 'problem_description': 'The laptop shuts down when it gets hot.',
        'in_shop': 'on', 'booking_date': (date.today() + timedelta(days=3)).isoformat(), 'booking_time': '10:00',
        'payment_method': 'C.A.R', 'accept_terms': 'on', 'fee_receipt': payment_proof()})
    booking = Booking.query.filter_by(customer_id=customer.id).one()
    assert float(booking.transaction.amount) == 650                 # ₱750 less the ₱100 booking fee
    assert booking.charges()['total'] == 750


# ---- amount to be paid (service report) -----------------------------------------------

def _approval(booking, status, work, cost):
    db.session.add(ApprovalRequest(booking_id=booking.id, technician_id=booking.technician_id, findings=work,
                                   proposed_work=work, additional_cost=cost, status=status))


def test_only_approved_extra_work_is_added_to_the_total(assigned_booking):
    assigned_booking.service.price, assigned_booking.service.service_fee = 1500, 150
    _approval(assigned_booking, 'approved', 'Replace the hinge as well', 800)
    _approval(assigned_booking, 'declined', 'Replace the keyboard', 900)
    _approval(assigned_booking, 'pending', 'New battery', 500)
    db.session.commit()
    charges = assigned_booking.charges()
    assert (charges['service_price'], charges['service_fee'], charges['additional_total'], charges['total']) == \
        (1500, 150, 800, 2450)
    assert charges['additional'] == [{'work': 'Replace the hinge as well', 'cost': 800}]
    assigned_booking.service.price = 0
    db.session.commit()
    charges = assigned_booking.charges()
    assert charges['price_on_diagnosis'] and charges['total'] == 950


def test_the_service_report_pdf_shows_the_amount_to_be_paid(assigned_booking, technician):
    from services import report_pdf
    assigned_booking.service.service_fee = 100
    _approval(assigned_booking, 'approved', 'Replace the hinge as well', 800)
    report = ServiceReport(booking_id=assigned_booking.id, technician_id=technician.id, status='submitted',
                           diagnosis='Cracked LCD panel', work_performed='Replaced the panel', outcome='fixed')
    db.session.add(report)
    db.session.commit()
    pdf = report_pdf.build(report, assigned_booking, technician.full_name, 'DEVTech')
    assert pdf[:4] == b'%PDF' and len(pdf) > 1000


# ---- the customer confirms they received the device -------------------------------------

def _ready(booking):
    booking.status = 'completed'
    db.session.add(Transaction(transaction_number='TXN-R1', booking_id=booking.id, user_id=booking.user_id,
                               amount=1000, payment_method='paymongo', payment_status='confirmed'))
    db.session.commit()


def test_release_waits_for_the_customer_to_confirm(client, assigned_booking, customer, technician):
    _ready(assigned_booking)
    login_as(client, technician)
    page = client.get(f'/technician/jobs/{assigned_booking.id}').get_data(as_text=True)
    assert 'Customer confirmed they received the device' in page
    assert 'Waiting for the customer to confirm they received the device.' in page
    client.post(f'/technician/api/jobs/{assigned_booking.id}/advance')
    assert db.session.get(Booking, assigned_booking.id).status == 'completed'

    login_as(client, customer)
    monitor = client.get(f'/api/booking/{assigned_booking.id}/monitor').get_json()
    assert monitor['receipt'] == {'canConfirm': True, 'confirmedAt': '', 'released': False}
    assert client.post(f'/api/booking/{assigned_booking.id}/received').get_json() == {'ok': True}
    assert client.post(f'/api/booking/{assigned_booking.id}/received').get_json()['already'] is True
    assert JobLog.query.filter_by(booking_id=assigned_booking.id, action='received').count() == 1
    assert Notification.query.filter_by(user_role='technician', user_id=technician.id,
                                        title='Customer received the device').count() == 1

    login_as(client, technician)
    client.post(f'/technician/api/jobs/{assigned_booking.id}/advance')
    assert db.session.get(Booking, assigned_booking.id).status == 'released'
    login_as(client, customer)
    receipt = client.get(f'/api/booking/{assigned_booking.id}/monitor').get_json()['receipt']
    assert receipt['canConfirm'] is False and receipt['released'] is True


def test_confirming_only_when_ready_and_only_by_the_bookings_customer(client, assigned_booking, customer):
    login_as(client, customer)
    assert client.post(f'/api/booking/{assigned_booking.id}/received').status_code == 400
    _ready(assigned_booking)
    other = Customer(username='maria', email='maria@test.local', full_name='Maria', is_active=True)
    other.set_password('Secret#123')
    db.session.add(other)
    db.session.commit()
    login_as(client, other)
    assert client.post(f'/api/booking/{assigned_booking.id}/received').status_code == 404
    assert db.session.get(Booking, assigned_booking.id).customer_received_at is None


# ---- intake photos ----------------------------------------------------------------------

def _photo(client, job_id):
    from PIL import Image
    buf = io.BytesIO()
    Image.new('RGB', (40, 30), (200, 30, 30)).save(buf, 'JPEG')
    buf.seek(0)
    return client.post('/technician/api/uploads', data={'file': (buf, 'side.jpg', 'image/jpeg'),
                                                       'ownerType': 'intake', 'jobId': str(job_id)},
                       content_type='multipart/form-data')


def test_intake_photos_are_saved_with_the_record_and_their_notes(client, assigned_booking, technician, admin):
    login_as(client, technician)
    page = client.get(f'/technician/intake/{assigned_booking.id}').get_data(as_text=True)
    assert 'data-owner-type="intake"' in page and 'Take or add photos of the device' in page
    photo_id = _photo(client, assigned_booking.id).get_json()['file']['id']
    client.post(f'/technician/api/jobs/{assigned_booking.id}/intake', data={
        'deviceType': 'Laptop', 'condition': 'fair', 'photosNote': 'Front and lid',
        f'caption_{photo_id}': 'Crack on the top-left corner'})
    record = IntakeRecord.query.filter_by(booking_id=assigned_booking.id).one()
    photo = db.session.get(UploadedFile, photo_id)
    assert (photo.owner_id, photo.caption) == (record.id, 'Crack on the top-left corner')
    job = client.get(f'/technician/jobs/{assigned_booking.id}').get_data(as_text=True)
    assert f'/technician/api/uploads/{photo_id}' in job and 'Crack on the top-left corner' in job

    login_as(client, admin)
    detail = client.get(f'/api/admin/booking/{assigned_booking.id}').get_json()
    assert detail['intake']['condition'] == 'Fair'
    assert detail['intake']['photos'][0]['url'] == f'/admin/uploads/{photo_id}'


def test_intake_photos_only_for_your_active_job_and_kept_once_it_moves_on(client, assigned_booking, technician):
    other = Technician(username='TECH-0002', email='other@test.local', full_name='Ana Reyes', is_active=True,
                       id_verified=True)
    other.set_password('Tech#12345')
    db.session.add(other)
    db.session.commit()
    login_as(client, other)
    assert _photo(client, assigned_booking.id).status_code == 400

    login_as(client, technician)
    photo_id = _photo(client, assigned_booking.id).get_json()['file']['id']
    assigned_booking.status = 'completed'
    db.session.commit()
    assert _photo(client, assigned_booking.id).status_code == 400
    assert client.delete(f'/technician/api/uploads/{photo_id}').status_code == 400
    assigned_booking.status = 'in_progress'
    db.session.commit()
    assert client.delete(f'/technician/api/uploads/{photo_id}').get_json() == {'ok': True}


# ---- profile photo rule ---------------------------------------------------------------------

def test_a_verified_technician_without_a_photo_gets_a_two_day_notice(client, technician):
    login_as(client, technician)
    page = client.get('/technician/dashboard').get_data(as_text=True)
    assert 'Add a photo of yourself as your profile picture.' in page and 'Add my photo' in page
    tech = db.session.get(Technician, technician.id)
    assert tech.photo_notice_at and tech.photo_notice_count == 1
    assert Notification.query.filter_by(user_role='technician', user_id=tech.id,
                                        title='Add a profile photo of yourself').count() == 1


def test_overdue_photo_tells_admins_once_and_admin_can_renotice_or_suspend(client, technician, admin):
    from services import profile_photo_rule
    profile_photo_rule.send_notice(technician)
    tech = db.session.get(Technician, technician.id)
    tech.photo_notice_at = datetime.utcnow() - timedelta(days=3)
    db.session.commit()
    assert profile_photo_rule.overdue(tech)

    login_as(client, admin)
    page = client.get('/admin/technician-verification').get_data(as_text=True)
    assert 'not added a profile photo' in page and 'Test Technician' in page
    client.get('/admin/technician-verification')
    assert Notification.query.filter_by(user_role='admin', title='Profile photo overdue').count() == 1
    detail = client.get(f'/admin/technician-verification/{tech.id}').get_data(as_text=True)
    assert 'Overdue.' in detail and 'Send another notice' in detail

    client.post(f'/admin/technician-verification/{tech.id}/photo-notice')
    tech = db.session.get(Technician, tech.id)
    assert tech.photo_notice_count == 2 and not profile_photo_rule.overdue(tech)
    assert Notification.query.filter_by(title='Reminder: add your profile photo').count() == 1

    tech.photo_notice_at = datetime.utcnow() - timedelta(days=3)
    db.session.commit()
    client.post(f'/admin/technician-verification/{tech.id}/decide', data={
        'action': 'suspend', 'expected': 'verified',
        'reason': 'No profile photo of yourself was added within 2 days of the notice.'})
    assert db.session.get(Technician, tech.id).verification_status == 'suspended'


def test_adding_a_photo_ends_the_notice(technician):
    from services import profile_photo_rule
    profile_photo_rule.send_notice(technician)
    technician.avatar_file = 'a' * 24 + '.jpg'
    db.session.commit()
    profile_photo_rule.photo_added(technician)
    assert db.session.get(Technician, technician.id).photo_notice_at is None
    assert not profile_photo_rule.applies(technician)


# ---- live profile updates -------------------------------------------------------------------

def test_pages_update_when_the_other_side_edits_their_profile(assigned_booking, customer, technician):
    before_customer, before_tech = _live_stamp(customer), _live_stamp(technician)
    technician.headline, technician.updated_at = 'Laptop specialist', datetime.utcnow() + timedelta(minutes=1)
    db.session.commit()
    assert _live_stamp(customer) != before_customer
    customer.full_name, customer.updated_at = 'Juan Santos Dela Cruz', datetime.utcnow() + timedelta(minutes=2)
    db.session.commit()
    assert _live_stamp(technician) != before_tech


def test_being_online_is_not_a_profile_change(client, assigned_booking, customer, technician):
    before = _live_stamp(customer)
    login_as(client, technician)
    client.get('/technician/dashboard')
    assert db.session.get(Technician, technician.id).last_active is not None
    assert _live_stamp(customer) == before


def test_the_technician_sees_the_customer_photo_on_the_job(client, assigned_booking, customer, technician):
    customer.avatar_file = 'b' * 24 + '.jpg'
    db.session.commit()
    login_as(client, technician)
    page = client.get(f'/technician/jobs/{assigned_booking.id}').get_data(as_text=True)
    assert customer.avatar_url in page and 'Use it to recognise them' in page


# ---- Settings > Danger Zone -----------------------------------------------------------------

def _danger(client, action, phrase, password='adminpass123'):
    return client.post(f'/admin/system/{action}', json={'phrase': phrase, 'password': password})


def test_the_danger_zone_starts_locked_and_checks_phrase_and_password(admin_logged_in):
    page = admin_logged_in.get('/admin/settings').get_data(as_text=True)
    assert 'Unlock to edit' in page and 'data-danger="clear" disabled' in page and 'notAvailable(); }' not in page
    r = _danger(admin_logged_in, 'deactivate', 'deactivate system')
    assert r.status_code == 422 and r.get_json()['field'] == 'phrase'
    r = _danger(admin_logged_in, 'deactivate', 'DEACTIVATE SYSTEM', 'wrong-password')
    assert r.status_code == 422 and r.get_json()['field'] == 'password'
    assert not SystemSetting.query.filter_by(setting_key='system_deactivated').first()


def test_only_admins_can_use_the_danger_zone(customer_logged_in):
    r = customer_logged_in.post('/admin/system/clear-data', json={'phrase': 'CLEAR ALL DATA', 'password': 'x'})
    assert r.status_code in (302, 401, 403)


def test_reset_all_settings_restores_the_defaults(admin_logged_in):
    db.session.add_all([SystemSetting(setting_key='system_name', value='My Renamed Shop'),
                        SystemSetting(setting_key='contact_phone', value='0917 000 0000')])
    db.session.commit()
    assert _danger(admin_logged_in, 'reset-settings', 'RESET ALL SETTINGS').get_json()['success'] is True
    values = {s.setting_key: s.value for s in SystemSetting.query.all()}
    assert values['system_name'] == 'DEVTech Computer Services' and 'contact_phone' not in values


def test_clear_all_data_keeps_accounts_and_services(admin_logged_in, assigned_booking, customer):
    from app import Message
    db.session.add(Message(sender_id=customer.id, sender_role='customer', recipient_id=1, recipient_role='admin',
                           content='Hello'))
    db.session.commit()
    r = _danger(admin_logged_in, 'clear-data', 'CLEAR ALL DATA')
    assert r.get_json()['counts']['bookings'] == 1
    assert Booking.query.count() == 0 and Message.query.count() == 0
    assert db.session.get(Customer, customer.id) and Service.query.count() == 1


def test_deactivating_shows_others_a_maintenance_page_and_reactivating_undoes_it(client, admin, customer):
    login_as(client, admin)
    assert _danger(client, 'deactivate', 'DEACTIVATE SYSTEM').get_json()['success'] is True
    assert 'The system is deactivated.' in client.get('/admin/dashboard').get_data(as_text=True)
    assert 'Reactivate System' in client.get('/admin/settings').get_data(as_text=True)
    client.get('/logout')
    assert client.get('/admin/login').status_code == 200
    r = client.get('/login')
    assert r.status_code == 503 and 'temporarily offline for maintenance' in r.get_data(as_text=True)
    assert client.get('/technician/login').status_code == 503
    assert client.get('/api/services').status_code == 503
    login_as(client, customer)
    assert client.get('/user/dashboard').status_code == 503

    login_as(client, admin)
    assert _danger(client, 'reactivate', 'REACTIVATE SYSTEM').get_json()['success'] is True
    login_as(client, customer)
    assert client.get('/user/dashboard').status_code == 200


# ---- roster: reading a valid ID's printed text ------------------------------------------------

PHILSYS = """REPUBLIKA NG PILIPINAS
Republic of the Philippines
PAMBANSANG PAGKAKAKILANLAN
Philippine Identification Card
1234-5678-9012-3456
Apelyido/Last Name
DELA CRUZ
Mga Pangalan/Given Names
JUAN
Gitnang Apelyido/Middle Name
SANTOS
Petsa ng Kapanganakan/Date of Birth
JANUARY 31, 1990
Tirahan/Address
123 RIZAL ST, BRGY 5, TACLOBAN CITY, LEYTE"""


def test_reader_reads_a_philsys_id():
    from services.id_card_reader import read
    assert read(PHILSYS) == {'id_type': 'PhilSys National ID', 'full_name': 'JUAN SANTOS DELA CRUZ',
                             'birth_date': '1990-01-31', 'id_number': '1234-5678-9012-3456', 'warning': None}


def test_reader_takes_names_from_confident_words_on_a_noisy_photo():
    from services.id_card_reader import read
    text = '\n'.join(['REPUBLIKA NG PILIPINAS ; on oo', 'Republic of the Philippines J nee o',
                      'PAMBANSANG PAGKAKAKILANLAN : J :', 'Philippine identification Card Br: 3 ee A',
                      'i 3 SR 1234-5678-9012-3456 T', '[8 fees EERE ApolyidalLastNeme 5 5 Co', 'SAA DELA CRUZ Ph',
                      'Sel 5 \\iga Pangalan/Given Names: SR 2 :', 'Eee JUAN : Le dish',
                      ': EA _anang ApelyidoMiddie Name ha i; 3', ': i Sie Pisa ig Kapnganakan/Date SBIR. - : ah |',
                      'EE ; - JANUARY 31, 1990 : ;'])
    confident = '\n'.join(['REPUBLIKA NG PILIPINAS', 'Republic of the', 'PAMBANSANG PAGKAKAKILANLAN', 'Card',
                           '1234-5678-9012-3456', '', 'DELA CRUZ', '', 'JUAN', '', '', 'JANUARY 31, 1990'])
    assert read(text, None, confident) == {
        'id_type': 'PhilSys National ID', 'full_name': 'JUAN DELA CRUZ', 'birth_date': '1990-01-31',
        'id_number': '1234-5678-9012-3456', 'warning': "The middle name couldn't be read. Add it if the ID shows one."}


@pytest.mark.parametrize('text, expected', [
    ("REPUBLIC OF THE PHILIPPINES\nDEPARTMENT OF TRANSPORTATION\nLAND TRANSPORTATION OFFICE\nDRIVER’S LICENSE\n"
     "Last Name, First Name, Middle Name\nDELA CRUZ, JUAN SANTOS\nNationality Sex Date of Birth Weight (kg) Height(m)\n"
     "PHL M 1990/01/31 70 1.70\nLicense No. Expiration Date Agency Code\nA01-23-456789 2030/01/31 A01",
     ("Driver's License", 'JUAN SANTOS DELA CRUZ', '1990-01-31', 'A01-23-456789')),
    ("UNIFIED MULTI-PURPOSE ID\nCRN-O111-2345678-9\nSURNAME\nDELA CRUZ\nGIVEN NAME\nJUAN\nMIDDLE NAME\nSANTOS\n"
     "SEX M DATE OF BIRTH 1990/01/31", ('UMID', 'JUAN SANTOS DELA CRUZ', '1990-01-31', '0111-2345678-9')),
    ("PASAPORTE\nPASSPORT\nP<PHLDELA<CRUZ<<JUAN<<<<<<<<<<<<<<<<<<<<<<<<\nP1234567A0PHL9001314M3001012<<<<<<<<<<<<<<04",
     ('Passport', 'JUAN DELA CRUZ', '1990-01-31', 'P1234567A')),
    ("REPUBLIC OF THE PHILIPPINES\nPHILIPPINE HEALTH INSURANCE CORPORATION\n12-345678901-2\nDELA CRUZ, JUAN SANTOS\n"
     "JANUARY 31, 1990 - MALE\n123 RIZAL ST., BRGY 5, TACLOBAN CITY",
     ('PhilHealth ID', 'JUAN SANTOS DELA CRUZ', '1990-01-31', '12-345678901-2')),
    ("REPUBLIC OF THE PHILIPPINES\nSOCIAL SECURITY SYSTEM\n34-1234567-8\nJUAN S. DELA CRUZ\n",
     ('SSS ID', 'JUAN S. DELA CRUZ', None, '34-1234567-8')),
])
def test_reader_reads_other_valid_ids(text, expected):
    from services.id_card_reader import read
    fields = read(text, today=date(2026, 11, 19))
    assert (fields['id_type'], fields['full_name'], fields['birth_date'], fields['id_number']) == expected


def test_reader_warns_on_a_mismatched_type_and_leaves_unreadable_text_empty():
    from services.id_card_reader import read
    assert read(PHILSYS, 'UMID')['warning'] == 'This looks like a PhilSys National ID, not a UMID. Check the ID type.'
    assert read('~~ |ll ;: ee\n0 . a') == {'id_type': None, 'full_name': None, 'birth_date': None,
                                           'id_number': None, 'warning': None}


def test_admin_gets_roster_fields_from_text_and_the_page_offers_it(admin_logged_in):
    page = admin_logged_in.get('/admin/technician-roster').get_data(as_text=True)
    assert 'Front of their valid ID' in page and 'js/id-scan.js' in page and '/admin/technician-roster/read-id' in page
    assert 'data-confirm-title="Add this technician to the roster?"' in page
    r = admin_logged_in.post('/admin/technician-roster/read-id', json={'text': PHILSYS, 'id_type': ''})
    assert r.get_json()['fields']['full_name'] == 'JUAN SANTOS DELA CRUZ'
    assert admin_logged_in.post('/admin/technician-roster/read-id', json={'text': '  '}).status_code == 422


def test_guests_cannot_read_ids(client):
    r = client.post('/admin/technician-roster/read-id', json={'text': 'PHILSYS'})
    assert r.status_code != 200


# ---- confirmations, home page and login pages -------------------------------------------------

def test_registration_and_booking_ask_before_sending(client, customer):
    page = client.get('/technician/register').get_data(as_text=True)
    assert 'js/confirm.js' in page and 'Are you sure you want to submit your information?' in page
    login_as(client, customer)
    assert 'Are you sure you want to submit this repair request?' in client.get('/user/book').get_data(as_text=True)


def test_dashboard_support_quick_action_opens_the_support_page(customer_logged_in):
    html = customer_logged_in.get('/user/dashboard').get_data(as_text=True)
    assert '<a href="/support" class="user-quick-btn">' in html


def test_home_page_does_not_link_to_the_staff_logins(client):
    html = client.get('/').get_data(as_text=True)
    for url in ('/technician/login', '/technician/register', '/admin/login'):
        assert f'href="{url}"' not in html


def test_staff_logins_stand_on_their_own(client):
    tech = client.get('/technician/login').get_data(as_text=True)
    assert 'href="/login"' not in tech and 'href="/admin/login"' not in tech
    admin = client.get('/admin/login').get_data(as_text=True)
    assert 'href="/login"' not in admin and 'href="/technician/login"' not in admin


def test_faq_bot_answers_the_service_fee(customer_logged_in):
    _service(700, 50)
    r = customer_logged_in.post('/api/support/bot', json={'message': 'how much is the service fee'}).get_json()
    assert r['id'] == 'service_fee' and 'PHP 50' in r['answer']
