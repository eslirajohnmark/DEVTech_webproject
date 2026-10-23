from app import db


INTAKE = {
    'deviceType': 'Laptop', 'deviceModel': 'Test X',
    'condition': 'good', 'conditionNotes': 'No damage.',
    'accessories': ['Charger / Adapter'],
    'powersOn': True, 'hasPassword': False,
    'dataBackupConsent': True, 'customerPresent': True,
    'photosNote': '2 photos.',
}

REPORT = {
    'action': 'submit',
    'diagnosis': 'Screen panel cracked. Backlight OK.',
    'workPerformed': 'Replaced LCD assembly and verified.',
    'outcome': 'fixed', 'hoursSpent': 2.5,
}


def _api(jid, path=''):
    return '/technician/api/jobs/' + str(jid) + path


def test_advance_is_blocked_until_intake_recorded(tech_logged_in, assigned_booking):
    r = tech_logged_in.post(_api(assigned_booking.id, '/advance'), json={})
    assert r.status_code == 400
    assert r.get_json()['ok'] is False


def test_full_workflow_auto_advances(tech_logged_in, assigned_booking):
    jid = assigned_booking.id

    r = tech_logged_in.post(_api(jid, '/intake'), json=INTAKE)
    assert r.get_json()['new_status'] == 'diagnosis_pending'

    r = tech_logged_in.post(_api(jid, '/diagnosis'), json={'diagnosis': 'Cracked LCD panel.'})
    assert r.get_json()['new_status'] == 'in_progress'

    r = tech_logged_in.post(_api(jid, '/report'), json=REPORT)
    assert r.status_code == 200
    assert r.get_json()['new_status'] == 'completed'

    r = tech_logged_in.post(_api(jid, '/advance'), json={})
    assert r.get_json()['job']['repairStatus'] == 'released'

    r = tech_logged_in.post(_api(jid, '/advance'), json={})
    assert r.get_json()['ok'] is False


def test_save_intake(tech_logged_in, assigned_booking):
    r = tech_logged_in.post(_api(assigned_booking.id, '/intake'), json=INTAKE)
    assert r.status_code == 200
    assert r.get_json()['record']['deviceModel'] == 'Test X'


def test_report_cannot_be_submitted_before_repair_starts(tech_logged_in, assigned_booking):
    r = tech_logged_in.post(_api(assigned_booking.id, '/report'), json=REPORT)
    assert r.status_code == 400


def test_submit_service_report(tech_logged_in, assigned_booking):
    assigned_booking.status = 'in_progress'
    db.session.commit()
    r = tech_logged_in.post(_api(assigned_booking.id, '/report'), json=REPORT)
    assert r.status_code == 200
    assert r.get_json()['report']['status'] == 'submitted'


def test_report_rejects_non_numeric_hours(tech_logged_in, assigned_booking):
    assigned_booking.status = 'in_progress'
    db.session.commit()
    r = tech_logged_in.post(_api(assigned_booking.id, '/report'),
                            json=dict(REPORT, hoursSpent='two'))
    assert r.status_code == 400


def test_draft_without_diagnosis_keeps_saved_diagnosis(tech_logged_in, assigned_booking):
    jid = assigned_booking.id
    tech_logged_in.post(_api(jid, '/diagnosis'), json={'diagnosis': 'Keep me.'})
    tech_logged_in.post(_api(jid, '/report'), json={'action': 'draft', 'workPerformed': 'x'})
    r = tech_logged_in.get(_api(jid, '/report'))
    assert r.get_json()['report']['diagnosis'] == 'Keep me.'


def test_notes_do_not_overwrite_customer_description(tech_logged_in, assigned_booking):
    tech_logged_in.post(_api(assigned_booking.id, '/notes'), json={'note': 'Ordered a panel.'})
    db.session.refresh(assigned_booking)
    assert assigned_booking.description == 'Cracked screen'


def test_file_incident(tech_logged_in):
    r = tech_logged_in.post('/technician/api/incidents', json={
        'type': 'access', 'severity': 'medium',
        'location': 'Tacloban',
        'description': 'Gate was locked and customer could not be reached for 30 minutes.',
        'actionTaken': 'Called customer and left.',
        'authoritiesNotified': False,
    })
    assert r.status_code == 200
    assert r.get_json()['ok'] is True
