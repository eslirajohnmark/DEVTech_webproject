def test_advance_through_track(tech_logged_in, assigned_booking):
    jid = str(assigned_booking.id)

    r1 = tech_logged_in.post('/technician/api/jobs/' + jid + '/advance')
    assert r1.get_json()['job']['repairStatus'] == 'in_progress'

    r2 = tech_logged_in.post('/technician/api/jobs/' + jid + '/advance')
    assert r2.get_json()['job']['repairStatus'] == 'completed'

    r3 = tech_logged_in.post('/technician/api/jobs/' + jid + '/advance')
    assert r3.get_json()['ok'] is False


def test_save_intake(tech_logged_in, assigned_booking):
    r = tech_logged_in.post(
        '/technician/api/jobs/' + str(assigned_booking.id) + '/intake',
        json={
            'deviceType': 'Laptop', 'deviceModel': 'Test X',
            'condition': 'good', 'conditionNotes': 'No damage.',
            'accessories': ['Charger / Adapter'],
            'powersOn': True, 'hasPassword': False,
            'dataBackupConsent': True, 'customerPresent': True,
            'photosNote': '2 photos.',
        })
    assert r.status_code == 200
    assert r.get_json()['record']['deviceModel'] == 'Test X'


def test_submit_service_report(tech_logged_in, assigned_booking):
    r = tech_logged_in.post(
        '/technician/api/jobs/' + str(assigned_booking.id) + '/report',
        json={
            'action': 'submit',
            'diagnosis': 'Screen panel cracked. Backlight OK.',
            'workPerformed': 'Replaced LCD assembly and verified.',
            'outcome': 'fixed', 'hoursSpent': 2.5,
        })
    assert r.status_code == 200
    assert r.get_json()['report']['status'] == 'submitted'


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