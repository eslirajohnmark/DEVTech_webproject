"""Single source of truth for booking/job statuses."""
STAGES = [  # (key, label, icon)
    ('pending',           'Requested',            'fa-inbox'),
    ('confirmed',         'Assigned',             'fa-clipboard-check'),
    ('diagnosis_pending', 'Diagnosis',            'fa-stethoscope'),
    ('in_progress',       'On Repair',            'fa-screwdriver-wrench'),
    ('completed',         'Ready for Collection', 'fa-box-open'),
    ('released',          'Released',             'fa-hand-holding-heart'),
]
STATUS_LABELS = {k: l for k, l, _ in STAGES}
STATUS_LABELS.update({'on_hold': 'On Hold', 'cancelled': 'Cancelled'})

ACTIVE_STATUSES   = ['pending', 'confirmed', 'diagnosis_pending', 'in_progress', 'on_hold']
FINISHED_STATUSES = ['completed', 'released']
SLOT_STATUSES     = ['pending', 'confirmed', 'diagnosis_pending', 'in_progress']

# Technician-driven transitions
NEXT_STATUS = {
    'confirmed': 'diagnosis_pending',   # needs intake record
    'diagnosis_pending': 'in_progress', # needs diagnosis text
    'in_progress': 'completed',
    'completed': 'released',
}