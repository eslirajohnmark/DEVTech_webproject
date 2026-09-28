"""File upload handling for technician intake photos, report evidence,
and incident attachments.

Validation pipeline:
  1. Filename must be present.
  2. MIME type must be in the allow-list.
  3. Size must not exceed 8 MB.
  4. File must not be empty.

Files are written to disk under app.config['TECH_UPLOAD_FOLDER'] with
a random hex name (the original name is preserved in the DB). The file
is only servable through the authenticated
/technician/api/uploads/<id> route — never through Flask's static
handler.
"""
import os
import secrets
from datetime import datetime

from flask import current_app
from werkzeug.utils import secure_filename

from app import db
from models.technician_models import UploadedFile


ALLOWED_MIME = {
    'image/jpeg',
    'image/png',
    'image/webp',
    'image/gif',
    'application/pdf',
}

MAX_BYTES = 8 * 1024 * 1024   # 8 MB per file


def _now():
    return datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')


def save_upload(file_storage, owner_type, owner_id, booking_id,
                technician_id, caption=''):
    """Validate and store one uploaded file.

    Returns (True, dict) on success, or (False, 'reason') on failure.
    """
    if not file_storage or not file_storage.filename:
        return False, 'No file provided.'

    mime = file_storage.mimetype or ''
    if mime not in ALLOWED_MIME:
        return False, 'File type not allowed: ' + (mime or 'unknown')

    data = file_storage.read()
    if len(data) > MAX_BYTES:
        return False, 'File is larger than 8 MB.'
    if len(data) == 0:
        return False, 'The uploaded file is empty.'

    safe = secure_filename(file_storage.filename)
    ext = os.path.splitext(safe)[1].lower()
    stored = secrets.token_hex(12) + ext

    folder = current_app.config['TECH_UPLOAD_FOLDER']
    os.makedirs(folder, exist_ok=True)
    with open(os.path.join(folder, stored), 'wb') as fh:
        fh.write(data)

    r = UploadedFile(
        owner_type=owner_type,
        owner_id=int(owner_id) if owner_id else 0,
        booking_id=int(booking_id) if booking_id else None,
        technician_id=technician_id,
        filename=stored,
        original_name=safe,
        mime_type=mime,
        size_bytes=len(data),
        caption=caption[:255],
        uploaded_at=_now(),
    )
    db.session.add(r)
    db.session.commit()

    return True, {
        'id': r.id,
        'ownerType': r.owner_type,
        'ownerId': r.owner_id,
        'jobId': r.booking_id,
        'filename': r.filename,
        'originalName': r.original_name,
        'mimeType': r.mime_type,
        'sizeBytes': r.size_bytes,
        'caption': r.caption,
        'uploadedAt': r.uploaded_at,
        'url': '/technician/api/uploads/' + str(r.id),
        'isImage': r.mime_type.startswith('image/'),
    }


def path_for(record):
    """Absolute path to a stored file, given its UploadedFile row."""
    return os.path.join(current_app.config['TECH_UPLOAD_FOLDER'],
                        record.filename)