"""Outgoing email through Resend (https://resend.com).

Configured from .env:
    RESEND_API_KEY   API key (re_...). Blank = email is switched off.
    MAIL_FROM        Sender, e.g. "DEVTech <no-reply@yourdomain.com>".
                     Until a domain is verified in Resend, only
                     onboarding@resend.dev works, and it can only deliver to
                     the address that owns the Resend account.

Emails go out from one background thread so a page never waits on the
network and an email failure can never break the request that triggered it.
Resend allows a couple of requests per second, so the worker spaces sends out.
"""
import html
import logging
import os
import queue
import threading
import time

import requests

RESEND_URL = 'https://api.resend.com/emails'
SEND_INTERVAL_SECONDS = 0.6   # stays under Resend's default rate limit
log = logging.getLogger('devtech.email')

_queue = queue.Queue()
_worker = None
_worker_lock = threading.Lock()

# Addresses that must never receive mail (anonymised / placeholder accounts).
_UNDELIVERABLE_SUFFIXES = ('.invalid', '.local', '.test', '.example')


def is_enabled(app=None):
    if app is not None and app.config.get('TESTING') and not app.config.get('EMAIL_IN_TESTS'):
        return False
    return bool(os.environ.get('RESEND_API_KEY'))


def deliverable(address):
    address = (address or '').strip().lower()
    return '@' in address and not address.endswith(_UNDELIVERABLE_SUFFIXES)


def render(title, message, action_url=None, action_label=None, site_name='DEVTech'):
    """Simple branded HTML + plain-text bodies. All text is escaped."""
    t, m = html.escape(title), html.escape(message).replace('\n', '<br>')
    button = ''
    if action_url:
        button = (f'<p style="margin:28px 0 8px;"><a href="{html.escape(action_url, quote=True)}" '
                  'style="background:#2563eb;color:#ffffff;text-decoration:none;padding:12px 22px;'
                  f'border-radius:10px;font-weight:600;display:inline-block;">{html.escape(action_label or "Open")}</a></p>')
    body = f"""<!doctype html><html><body style="margin:0;background:#f1f5f9;font-family:Segoe UI,Arial,sans-serif;color:#0f172a;">
<div style="max-width:560px;margin:0 auto;padding:28px 16px;">
  <div style="font-size:20px;font-weight:800;color:#2563eb;margin-bottom:16px;">{html.escape(site_name)}</div>
  <div style="background:#ffffff;border-radius:16px;padding:28px;border:1px solid #e2e8f0;">
    <h1 style="font-size:20px;margin:0 0 12px;">{t}</h1>
    <p style="font-size:15px;line-height:1.6;margin:0;color:#334155;">{m}</p>
    {button}
  </div>
  <p style="font-size:12px;color:#64748b;margin-top:16px;">You are receiving this because you have an account with {html.escape(site_name)}.
  You can turn off email notifications in your profile settings.</p>
</div></body></html>"""
    text = f"{title}\n\n{message}\n" + (f"\n{action_label or 'Open'}: {action_url}\n" if action_url else '')
    return body, text


def send_now(to, subject, html_body, text_body):
    """Send one email synchronously. Returns True on success. Never raises."""
    key = os.environ.get('RESEND_API_KEY')
    if not key or not deliverable(to):
        return False
    sender = os.environ.get('MAIL_FROM') or 'DEVTech <onboarding@resend.dev>'
    try:
        r = requests.post(RESEND_URL, timeout=15,
                          headers={'Authorization': f'Bearer {key}'},
                          json={'from': sender, 'to': [to], 'subject': subject,
                                'html': html_body, 'text': text_body})
        if r.ok:
            return True
        log.warning('Resend rejected email to %s: %s %s', to, r.status_code, r.text[:300])
    except requests.RequestException as e:
        log.warning('Could not reach Resend for %s: %s', to, e)
    return False


def _work():
    while True:
        to, subject, html_body, text_body = _queue.get()
        try:
            send_now(to, subject, html_body, text_body)
        finally:
            _queue.task_done()
        time.sleep(SEND_INTERVAL_SECONDS)


def queue_email(to, subject, html_body, text_body, app=None):
    """Hand an email to the background sender. Returns True if queued."""
    if not is_enabled(app) or not deliverable(to):
        return False
    global _worker
    with _worker_lock:
        if _worker is None or not _worker.is_alive():
            _worker = threading.Thread(target=_work, name='email-sender', daemon=True)
            _worker.start()
    _queue.put((to, subject, html_body, text_body))
    return True
