"""File upload handling for technician intake photos, report evidence,
and incident attachments.

Validation pipeline:
  1. Filename must be present.
  2. Declared MIME type must be in the allow-list.
  3. Size must not exceed 8 MB.
  4. File must not be empty.
  5. The file's leading bytes must match the declared type (the
     browser-supplied MIME type alone is trivially spoofed).

Files are written to disk under app.config['TECH_UPLOAD_FOLDER'] with
a random hex name and an extension derived from the verified type (the
original name is preserved in the DB). The file
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

OWNER_TYPES = {'intake', 'report', 'incident'}

# mime -> (extension, check on the file's first bytes)
SIGNATURES = {
    'image/jpeg':      ('.jpg',  lambda b: b.startswith(b'\xff\xd8\xff')),
    'image/png':       ('.png',  lambda b: b.startswith(b'\x89PNG\r\n\x1a\n')),
    'image/gif':       ('.gif',  lambda b: b[:6] in (b'GIF87a', b'GIF89a')),
    'image/webp':      ('.webp', lambda b: b[:4] == b'RIFF' and b[8:12] == b'WEBP'),
    'application/pdf': ('.pdf',  lambda b: b.startswith(b'%PDF-')),
}


def _now():
    return datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')


def check_file(file_storage, max_bytes=MAX_BYTES):
    """Validate an uploaded file without storing it: allowed type, size, and a
    signature that matches the declared type.
    Returns (True, (data, mime, ext, safe_name)) or (False, 'reason')."""
    if not file_storage or not file_storage.filename:
        return False, 'No file provided.'
    mime = file_storage.mimetype or ''
    if mime not in ALLOWED_MIME:
        return False, 'Only JPG, PNG, GIF, WEBP images and PDF files are allowed.'
    data = file_storage.read()
    if len(data) > max_bytes:
        return False, f'File is larger than {max_bytes // (1024 * 1024)} MB.'
    if len(data) == 0:
        return False, 'The uploaded file is empty.'
    ext, matches = SIGNATURES[mime]
    if not matches(data[:16]):
        return False, 'The file content does not match its type.'
    safe = secure_filename(file_storage.filename) or 'upload' + ext
    return True, (data, mime, ext, safe)


def save_upload(file_storage, owner_type, owner_id, booking_id,
                technician_id, caption=''):
    """Validate and store one uploaded file.

    Returns (True, dict) on success, or (False, 'reason') on failure.
    """
    if not file_storage or not file_storage.filename:
        return False, 'No file provided.'
    if owner_type not in OWNER_TYPES:
        return False, 'Unknown attachment type.'
    try:
        owner_id = int(owner_id) if owner_id else None
        booking_id = int(booking_id) if booking_id else None
    except (TypeError, ValueError):
        return False, 'Invalid job or owner id.'
    if booking_id is not None:
        from app import Booking
        booking = db.session.get(Booking, booking_id)
        if not booking or booking.technician_id != technician_id:
            return False, 'You can only attach files to your own jobs.'

    ok, checked = check_file(file_storage)
    if not ok:
        return False, checked
    data, mime, ext, safe = checked
    stored = secrets.token_hex(12) + ext

    folder = current_app.config['TECH_UPLOAD_FOLDER']
    os.makedirs(folder, exist_ok=True)
    with open(os.path.join(folder, stored), 'wb') as fh:
        fh.write(data)

    r = UploadedFile(
        owner_type=owner_type,
        owner_id=owner_id or 0,
        booking_id=booking_id,
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