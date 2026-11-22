"""Outgoing email through Brevo (https://brevo.com) or Resend (https://resend.com).

Configured from .env:
    RESEND_API_KEY   Resend API key (re_...).
    BREVO_API_KEY    Brevo API key (xkeysib-...). Free plan: 300 emails a day.
    EMAIL_PROVIDER   "resend" or "brevo": which one to use when both keys are set
                     (default: Brevo, as before).
    MAIL_FROM        Sender, e.g. "DEVTech <no-reply@yourdomain.com>".
                     Brevo: the address must be a verified sender in Brevo.
                     Resend: the domain must be verified in Resend (Domains page,
                     DNS records). Until then only onboarding@resend.dev works,
                     and it can only deliver to the address that owns the Resend
                     account.
No key = email is switched off. `flask send-test-email you@example.com` sends
one email straight away and prints the provider's answer. Both are HTTPS APIs, so hosts that block the
email (SMTP) ports can still send.

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
BREVO_URL = 'https://api.brevo.com/v3/smtp/email'
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
    return bool(os.environ.get('BREVO_API_KEY') or os.environ.get('RESEND_API_KEY'))


def deliverable(address):
    address = (address or '').strip().lower()
    return '@' in address and not address.endswith(_UNDELIVERABLE_SUFFIXES)


def provider():
    """'resend', 'brevo' or None: the service the next email goes through."""
    resend, brevo = os.environ.get('RESEND_API_KEY'), os.environ.get('BREVO_API_KEY')
    chosen = (os.environ.get('EMAIL_PROVIDER') or '').strip().lower()
    if chosen == 'resend' and resend:
        return 'resend'
    if chosen == 'brevo' and brevo:
        return 'brevo'
    return 'brevo' if brevo else ('resend' if resend else None)


ACCOUNT_FOOTER = ('You are receiving this because you have an account with {site}.\n'
                  'You can turn off email notifications in your profile settings.')
SECURITY_FOOTER = 'This is a security email about your {site} account, so it is sent even when notifications are off.'


def render(title, message, action_url=None, action_label=None, site_name='DEVTech', footer=None):
    """Simple branded HTML + plain-text bodies. All text is escaped. `footer` replaces
    the notifications line (SECURITY_FOOTER for password emails)."""
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
    __LINK__
  </div>
  <p style="font-size:12px;color:#64748b;margin-top:16px;">__FOOTER__</p>
</div></body></html>"""
    text = f"{title}\n\n{message}\n" + (f"\n{action_label or 'Open'}: {action_url}\n" if action_url else '')
    note = (footer or ACCOUNT_FOOTER).format(site=site_name)
    link = ''
    if action_url:   # some mail apps hide buttons: give the link as text too
        link = ('<p style="font-size:12px;color:#64748b;margin:14px 0 0;word-break:break-all;">'
                'Or copy this link into your browser:<br>'
                f'<a href="{html.escape(action_url, quote=True)}" style="color:#2563eb;">{html.escape(action_url)}</a></p>')
    body = body.replace('__LINK__', link).replace('__FOOTER__', html.escape(note).replace('\n', '<br>'))
    return body, text + f"\n{note}\n"


def _send_brevo(key, to, subject, html_body, text_body):
    """(sent, detail). Never raises."""
    from email.utils import parseaddr
    name, address = parseaddr(os.environ.get('MAIL_FROM') or '')
    if not address:
        log.warning('MAIL_FROM is not set: Brevo needs a verified sender address.')
        return False, 'MAIL_FROM is not set: Brevo needs a verified sender address.'
    try:
        r = requests.post(BREVO_URL, timeout=15,
                          headers={'api-key': key, 'accept': 'application/json'},
                          json={'sender': {'name': name or 'DEVTech', 'email': address},
                                'to': [{'email': to}], 'subject': subject,
                                'htmlContent': html_body, 'textContent': text_body})
        if r.ok:
            return True, 'Brevo accepted the email.'
        log.warning('Brevo rejected email to %s: %s %s', to, r.status_code, r.text[:300])
        return False, f'Brevo answered {r.status_code}: {r.text[:300]}'
    except requests.RequestException as e:
        log.warning('Could not reach Brevo for %s: %s', to, e)
        return False, f'Could not reach Brevo: {e}'


def resend_hint(status, text):
    """What to change when Resend refuses an email (written to the log and shown by the CLI)."""
    low = (text or '').lower()
    if status == 403 and ('testing emails' in low or 'own email' in low):
        return ('MAIL_FROM uses onboarding@resend.dev, which only delivers to the email that owns the Resend '
                'account. Verify a domain you own in Resend (Domains) and set MAIL_FROM to an address on it.')
    if status == 403 and 'domain' in low:
        return ('The domain in MAIL_FROM is not verified in Resend yet. Add the DNS records shown on '
                'Resend > Domains and wait until it says Verified.')
    if status in (401, 403) and 'api' in low and 'key' in low:
        return 'RESEND_API_KEY is wrong, revoked, or only allowed to send from another domain.'
    if status == 422 and '`to`' in low:
        return 'Resend refused the recipient address (test domains such as example.com are blocked).'
    if status == 422 and ('`from`' in low or 'from' in low):
        return 'Check MAIL_FROM: it must look like "DEVTech <no-reply@yourdomain.com>".'
    if status == 429:
        return 'Too many emails at once (Resend rate limit or daily quota). Try again in a moment.'
    return ''


def _send_resend(key, to, subject, html_body, text_body):
    """(sent, detail). Never raises."""
    sender = os.environ.get('MAIL_FROM') or 'DEVTech <onboarding@resend.dev>'
    try:
        r = requests.post(RESEND_URL, timeout=15,
                          headers={'Authorization': f'Bearer {key}', 'User-Agent': 'devtech-mailer/1.0'},
                          json={'from': sender, 'to': [to], 'subject': subject,
                                'html': html_body, 'text': text_body})
        if r.ok:
            try:
                ref = (r.json() or {}).get('id', '')
            except ValueError:
                ref = ''
            return True, 'Resend accepted the email' + (f' (id {ref}).' if ref else '.')
        hint = resend_hint(r.status_code, r.text)
        log.warning('Resend rejected email to %s: %s %s%s', to, r.status_code, r.text[:300],
                    f' -> {hint}' if hint else '')
        return False, f'Resend answered {r.status_code}: {r.text[:300]}' + (f'\nFix: {hint}' if hint else '')
    except requests.RequestException as e:
        log.warning('Could not reach Resend for %s: %s', to, e)
        return False, f'Could not reach Resend: {e}'


def send_with_detail(to, subject, html_body, text_body):
    """Send one email now: (sent, provider, detail). Never raises."""
    if not deliverable(to):
        return False, None, f'{to} is not a deliverable address.'
    which = provider()
    if which == 'brevo':
        sent, detail = _send_brevo(os.environ['BREVO_API_KEY'], to, subject, html_body, text_body)
    elif which == 'resend':
        sent, detail = _send_resend(os.environ['RESEND_API_KEY'], to, subject, html_body, text_body)
    else:
        return False, None, 'Email is off: set RESEND_API_KEY (or BREVO_API_KEY) in .env.'
    return sent, which, detail


def send_now(to, subject, html_body, text_body):
    """Send one email synchronously. Returns True on success. Never raises."""
    return send_with_detail(to, subject, html_body, text_body)[0]


def _work():
    while True:
        to, subject, html_body, text_body = _queue.get()
        try:
            send_now(to, subject, html_body, text_body)
        finally:
            _queue.task_done()
        time.sleep(SEND_INTERVAL_SECONDS)


def queue_email(to, subject, html_body, text_body, app=None):
    """Hand an email to the background sender. Returns True if queued (sent, on Vercel)."""
    if not is_enabled(app) or not deliverable(to):
        return False
    if os.environ.get('VERCEL') == '1':
        # Serverless: a background thread may be frozen once the response is sent,
        # so the email goes out now, before the page finishes.
        return send_now(to, subject, html_body, text_body)
    global _worker
    with _worker_lock:
        if _worker is None or not _worker.is_alive():
            _worker = threading.Thread(target=_work, name='email-sender', daemon=True)
            _worker.start()
    _queue.put((to, subject, html_body, text_body))
    return True
