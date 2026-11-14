"""Fill a technician's service report from what the job record already knows:
the customer's description, the intake check, the recorded diagnosis, the extra
work the customer approved, progress notes and the time the repair took.

Only empty fields are filled; whatever the technician has typed is kept.
"""
import json
from datetime import datetime

# Advice to pass on, by device type (what the booking form calls it).
RECOMMENDATIONS = {
    'Laptop': 'Keep the vents clear and use the laptop on a hard surface. Back up your files every week. '
              'Use the original or a correctly rated charger.',
    'Desktop PC': 'Keep the PC off the floor and away from dust, and clean it every 6 to 12 months. '
                  'Use a surge protector or UPS. Back up your files every week.',
    'Tablet': 'Use a case and screen protector, charge with a rated adapter, and keep the system updated. '
              'Back up photos and documents regularly.',
    'Smartphone': 'Use a case and screen protector, avoid charging overnight on soft surfaces, and keep the system '
                  'updated. Back up your phone regularly.',
    'Monitor': 'Connect it through a surge protector, keep the vents clear, and use the cable that came with it.',
    'Storage Device': 'Keep two copies of important files on different devices, and eject the drive safely before unplugging.',
}
DEFAULT_RECOMMENDATION = 'Back up your files regularly and bring the device in if the problem returns.'


def _when(text):
    try:
        return datetime.strptime(text or '', '%Y-%m-%d %H:%M:%S')
    except ValueError:
        return None


def hours_on_job(logs, now=None):
    """Hours from the start of the repair (or the first status change) to now,
    in quarter hours. None when the log has no usable time."""
    starts = [_when(l.at) for l in logs if l.action in ('status', 'diagnosis', 'intake')]
    starts = [s for s in starts if s]
    if not starts:
        return None
    repair = [_when(l.at) for l in logs if l.action == 'status' and 'repair' in (l.text or '').lower()]
    repair = [s for s in repair if s]
    start = min(repair) if repair else min(starts)
    hours = ((now or datetime.utcnow()) - start).total_seconds() / 3600
    if hours <= 0:
        return None
    return min(round(hours * 4) / 4 or 0.25, 72.0)       # a long wait is not repair time


def suggest(booking, report=None, intake=None, approvals=(), logs=()):
    """{form field: suggested text} for every field the report still has empty."""
    service = booking.service.name if booking.service else 'the booked service'
    device = ' '.join(x for x in (booking.device_type, booking.device_brand, booking.device_model) if x)

    findings = [a.findings.strip() for a in approvals if a.findings and a.findings.strip()]
    diagnosis = []
    if booking.description and booking.description != 'No description provided':
        diagnosis.append(f'Customer reported: {booking.description.strip()}')
    diagnosis += [f'Found: {f}' for f in findings]

    tests = []
    if intake:
        tests.append(f'At intake: {"powered on" if intake.powers_on else "did not power on"}, '
                     f'condition {intake.condition or "not recorded"}.')
        if intake.condition_notes:
            tests.append(f'Condition notes: {intake.condition_notes.strip()}')
        try:
            accessories = json.loads(intake.accessories or '[]')
        except ValueError:
            accessories = []
        if accessories:
            tests.append('Received with: ' + ', '.join(str(a) for a in accessories) + '.')
    tests.append(f'Tested the {booking.device_type.lower() if booking.device_type else "device"} after the work.')

    work = [f'{service} on the {device or "device"}.']
    for a in approvals:
        if a.status == 'approved' and a.proposed_work:
            cost = f' (customer approved PHP {float(a.additional_cost or 0):,.2f})' if a.additional_cost else ''
            work.append(f'Extra work: {a.proposed_work.strip()}{cost}.')
    notes = [l.text.strip() for l in logs if l.action == 'note' and l.text]
    work += notes

    hours = hours_on_job(logs)
    if hours is None:
        hours = float(booking.service.estimated_hours or 1) if booking.service else 1.0

    values = {
        'diagnosis': '\n'.join(diagnosis),
        'tests': '\n'.join(tests),
        'workPerformed': '\n'.join(work),
        'hoursSpent': hours,
        'recommendations': RECOMMENDATIONS.get(booking.device_type, DEFAULT_RECOMMENDATION),
    }
    current = {
        'diagnosis': report.diagnosis if report else '',
        'tests': report.tests if report else '',
        'workPerformed': report.work_performed if report else '',
        'hoursSpent': report.hours_spent if report else 0,
        'recommendations': report.recommendations if report else '',
    }
    def empty(value):
        return not value or (isinstance(value, str) and not value.strip())
    return {k: v for k, v in values.items() if v and empty(current[k])}
