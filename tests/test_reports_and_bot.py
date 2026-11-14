"""Service reports that fill themselves in from the job, carry photos with notes and
reach the admin as a PDF; and the support assistant that answers common questions."""
import io

from PIL import Image

from app import db, Booking
from models.technician_models import ApprovalRequest, JobLog, ServiceReport, UploadedFile
from services import support_bot
from tests.conftest import login_as


def _png(color='red'):
    out = io.BytesIO()
    Image.new('RGB', (64, 48), color).save(out, 'PNG')
    return out.getvalue()


def _in_repair(b):
    b.status = 'in_progress'
    b.description = 'The screen flickers and shows green lines'
    b.device_type = 'Laptop'
    db.session.add(JobLog(booking_id=b.id, at='2026-11-13 09:00:00', by_name='Test Technician', action='status',
                          text='Repair started (on repair).'))
    db.session.add(JobLog(booking_id=b.id, at='2026-11-13 10:00:00', by_name='Test Technician', action='note',
                          text='Reseated the display cable; flicker gone.'))
    db.session.add(ApprovalRequest(booking_id=b.id, technician_id=b.technician_id, requested_at='2026-11-13 09:30:00',
                                   findings='Display cable worn at the hinge', proposed_work='Replace the screen cable',
                                   additional_cost=800, status='approved'))
    db.session.commit()


def _upload(client, b, data=None, name='before.png', mime='image/png'):
    return client.post('/technician/api/uploads', data={
        'file': (io.BytesIO(data or _png()), name, mime), 'ownerType': 'report', 'ownerId': '', 'jobId': str(b.id)},
        content_type='multipart/form-data')


# ---------------------------------------------------------------- service report

def test_the_report_form_fills_itself_in_from_the_job(tech_logged_in, assigned_booking):
    _in_repair(assigned_booking)
    html = tech_logged_in.get(f'/technician/reports/new/{assigned_booking.id}').get_data(as_text=True)
    assert 'Customer reported: The screen flickers and shows green lines' in html
    assert 'Found: Display cable worn at the hinge' in html
    assert 'Extra work: Replace the screen cable' in html and 'Reseated the display cable' in html
    assert 'Filled in from the job record' in html and 'Back up your files every week' in html
    assert 'id="rpDrop"' in html and 'File upload arrives with the Flask backend' not in html


def test_photos_with_notes_are_submitted_and_the_admin_gets_a_pdf(client, technician, admin, assigned_booking):
    _in_repair(assigned_booking)
    login_as(client, technician)
    first = _upload(client, assigned_booking).get_json()['file']
    second = _upload(client, assigned_booking, _png('blue'), 'screenshot.png').get_json()['file']
    assert client.delete(f'/technician/api/uploads/{second["id"]}').get_json()['ok']      # removed before submitting
    assert UploadedFile.query.filter_by(owner_type='report').count() == 1

    r = client.post(f'/technician/api/jobs/{assigned_booking.id}/report', data={
        'action': 'submit', 'diagnosis': 'Worn display cable', 'workPerformed': 'Replaced the display cable',
        'outcome': 'fixed', 'hoursSpent': '1.5', f'caption_{first["id"]}': 'Before: the worn cable'})
    assert r.status_code == 302
    report = ServiceReport.query.one()
    photo = db.session.get(UploadedFile, first['id'])
    assert report.status == 'submitted' and photo.owner_id == report.id and photo.caption == 'Before: the worn cable'
    pdf_row = UploadedFile.query.filter_by(owner_type='report_pdf', owner_id=report.id).one()
    assert pdf_row.original_name == 'service-report-BK-TEST-0001.pdf'
    # photos can no longer be removed or added once the report is in
    assert client.delete(f'/technician/api/uploads/{first["id"]}').status_code == 400
    assert _upload(client, assigned_booking).status_code == 400
    mine = client.get(f'/technician/api/jobs/{assigned_booking.id}/report.pdf')
    assert mine.status_code == 200 and mine.data.startswith(b'%PDF')

    login_as(client, admin)
    page = client.get('/admin/technician-activity').get_data(as_text=True)
    assert f'/admin/service-reports/{report.id}/pdf' in page and 'Before: the worn cable' in page
    pdf = client.get(f'/admin/service-reports/{report.id}/pdf')
    assert pdf.status_code == 200 and pdf.mimetype == 'application/pdf' and pdf.data.startswith(b'%PDF')
    assert len(pdf.data) > 2000                                   # the photo is in it


def test_submitting_needs_the_findings_and_the_work(tech_logged_in, assigned_booking):
    _in_repair(assigned_booking)
    r = tech_logged_in.post(f'/technician/api/jobs/{assigned_booking.id}/report',
                            json={'action': 'submit', 'diagnosis': 'Worn cable', 'workPerformed': '  '})
    assert r.status_code == 400 and 'work performed' in r.get_json()['reason']
    assert ServiceReport.query.count() == 0
    r = tech_logged_in.post(f'/technician/api/jobs/{assigned_booking.id}/report',
                            json={'action': 'draft', 'workPerformed': ''})
    assert r.get_json()['report']['status'] == 'draft'           # a draft can be incomplete


def test_photos_belong_to_the_technician_on_the_job(client, assigned_booking, technician):
    from app import Technician
    other = Technician(username='TECH-0002', email='t2@test.local', full_name='Other Tech', is_active=True, id_verified=True)
    other.set_password('testpassword1')
    db.session.add(other)
    db.session.commit()
    login_as(client, other)
    r = _upload(client, assigned_booking)
    assert r.status_code == 400 and UploadedFile.query.count() == 0


# ---------------------------------------------------------------- support assistant

def _ask(client, text):
    return client.post('/api/support/bot', json={'message': text}).get_json()


def test_the_assistant_answers_common_questions(customer_logged_in):
    from app import app as flask_app
    flask_app.config['PAYMONGO_ENABLED'] = True              # the fee exists only with online payments
    fee = _ask(customer_logged_in, 'magkano ang booking fee?')
    assert fee['id'] == 'fee' and 'PHP 100' in fee['answer'] and 'deducted from your final bill' in fee['answer']
    pay = _ask(customer_logged_in, 'How can I pay with GCash?')
    assert pay['id'] == 'pay' and {'label': 'My transactions', 'url': '/user/transactions'} in pay['links']
    assert _ask(customer_logged_in, 'is my laptop ready?')['id'] == 'track'
    assert _ask(customer_logged_in, 'where is your shop')['id'] == 'shop'
    assert _ask(customer_logged_in, 'paano mag cancel ng booking')['id'] == 'cancel'


def test_the_assistant_hands_over_to_a_person_when_unsure(customer_logged_in):
    r = _ask(customer_logged_in, 'what is the weather in cebu today')
    assert r['id'] is None and r['confident'] is False and 'Message our team' in r['answer']
    # it only answers FAQs: a repair problem goes to the team, not a guess
    assert _ask(customer_logged_in, "my phone won't charge even with a new cable")['confident'] is False
    assert _ask(customer_logged_in, 'sdkfj')['confident'] is False
    assert _ask(customer_logged_in, 'can I talk to a real person')['human'] is True


def test_the_faq_chatbot_is_always_on_the_support_page(customer_logged_in, customer):
    from app import SupportTicket
    db.session.add(SupportTicket(customer_id=customer.id, subject='Booking', message='Is my laptop ready?', status='open'))
    db.session.commit()
    html = customer_logged_in.get('/support').get_data(as_text=True)    # even with a conversation open
    assert 'id="faqBot"' in html and 'FAQ chatbot' in html and 'data-ask="What is the booking fee?"' in html
    assert 'js/faq-bot.js' in html and 'id="supStart"' in html and 'id="supBot"' not in html


def test_every_answer_link_points_to_a_real_page(app):
    with app.test_request_context():
        from flask import url_for
        for faq in support_bot.FAQS:
            for _, endpoint in faq['links']:
                assert url_for(endpoint)
