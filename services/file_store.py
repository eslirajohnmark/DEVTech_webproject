"""Uploaded files kept in Supabase Storage as well as on the server's disk.

Some hosts (Render's free plan) wipe the disk whenever the app restarts. With
SUPABASE_URL and SUPABASE_SECRET_KEY set, every file the app saves in an upload
folder (photos, ID documents, credentials, receipts, message attachments, report
PDFs) is also copied to a private Supabase Storage bucket (SUPABASE_BUCKET,
default "devtech-uploads"), and a file missing from the disk is fetched back
from the bucket before it is served. Without those settings files live on disk
only, as before.

Objects are stored as "<upload folder name>/<file name>", e.g. "tech/3f9a.jpg";
file names are random, so they never collide.
"""
import logging
import mimetypes
import os

import requests

log = logging.getLogger('devtech.files')
TIMEOUT = 30


def _config():
    url = (os.environ.get('SUPABASE_URL') or '').rstrip('/')
    key = os.environ.get('SUPABASE_SECRET_KEY') or os.environ.get('SUPABASE_SERVICE_KEY') or ''
    bucket = os.environ.get('SUPABASE_BUCKET') or 'devtech-uploads'
    return url, key, bucket


def enabled():
    url, key, _ = _config()
    return bool(url and key)


def _headers(key, extra=None):
    # New secret keys (sb_secret_...) go in "apikey" only; a legacy service_role
    # key is a JWT and is also sent as the bearer token.
    headers = {'apikey': key}
    if not key.startswith('sb_'):
        headers['Authorization'] = f'Bearer {key}'
    headers.update(extra or {})
    return headers


def object_key(path):
    path = os.path.abspath(path)
    return f'{os.path.basename(os.path.dirname(path))}/{os.path.basename(path)}'


def saved(path):
    """Call right after writing a file into an upload folder: copies it to the
    bucket. Returns True when copied. Never raises (the disk copy still works)."""
    if not enabled():
        return False
    url, key, bucket = _config()
    try:
        with open(path, 'rb') as fh:
            data = fh.read()
        mime = mimetypes.guess_type(path)[0] or 'application/octet-stream'
        r = requests.post(f'{url}/storage/v1/object/{bucket}/{object_key(path)}', data=data, timeout=TIMEOUT,
                          headers=_headers(key, {'Content-Type': mime, 'x-upsert': 'true'}))
        if r.ok:
            return True
        log.warning('Supabase Storage refused %s: %s %s', object_key(path), r.status_code, r.text[:200])
    except (OSError, requests.RequestException) as e:
        log.warning('Could not copy %s to Supabase Storage: %s', object_key(path), e)
    return False


def exists(path):
    """True when the file is on disk, fetching it back from the bucket first
    when the disk copy is gone (e.g. after a restart). Never raises."""
    if os.path.isfile(path):
        return True
    if not enabled():
        return False
    url, key, bucket = _config()
    try:
        r = requests.get(f'{url}/storage/v1/object/authenticated/{bucket}/{object_key(path)}',
                         headers=_headers(key), timeout=TIMEOUT)
        if r.status_code != 200:
            return False
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        part = path + '.part'
        with open(part, 'wb') as fh:
            fh.write(r.content)
        os.replace(part, path)
        return True
    except (OSError, requests.RequestException) as e:
        log.warning('Could not fetch %s from Supabase Storage: %s', object_key(path), e)
        return False


def removed(path):
    """Delete a file from the disk and from the bucket. Never raises."""
    try:
        os.remove(path)
    except OSError:
        pass
    if not enabled():
        return
    url, key, bucket = _config()
    try:
        requests.delete(f'{url}/storage/v1/object/{bucket}', json={'prefixes': [object_key(path)]},
                        headers=_headers(key), timeout=TIMEOUT)
    except requests.RequestException as e:
        log.warning('Could not delete %s from Supabase Storage: %s', object_key(path), e)
