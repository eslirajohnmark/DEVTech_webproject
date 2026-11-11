"""
PayMongo integration (Hosted Checkout).

Everything that touches PAYMONGO_SECRET_KEY lives in this file. Routes call
create_checkout_session() and hand the customer's browser the returned
checkout_url. A payment is confirmed in two independent ways, whichever comes
first (both ask PayMongo, neither trusts the browser):
  * the customer returns to our success page, which retrieves the session from
    PayMongo and checks it has a paid payment (works on a local PC too);
  * PayMongo calls /paymongo/webhook (needs a public URL), verified by signature.

Docs: https://docs.paymongo.com/reference/create-a-checkout
      https://docs.paymongo.com/reference/retrieve-a-checkout
      https://docs.paymongo.com/docs/developer-tools-webhooks-events
"""

import base64
import hashlib
import hmac
import json
import logging
import os
import time
from decimal import Decimal, ROUND_HALF_UP

import requests

log = logging.getLogger(__name__)

PAYMONGO_API = 'https://api.paymongo.com/v1'
TIMEOUT = 15  # seconds

# Payment options shown on PayMongo's checkout page (all enabled on test accounts).
PAYMENT_METHOD_TYPES = ['card', 'gcash', 'paymaya', 'grab_pay', 'qrph']

# The only event we act on. It carries the checkout session (with our
# reference_number) and its paid payment.
PAID_EVENT = 'checkout_session.payment.paid'

# Webhook signatures older than this are refused (replay protection).
SIGNATURE_MAX_AGE = 5 * 60


class PaymongoError(Exception):
    """Raised when PayMongo rejects a request or cannot be reached."""

    def __init__(self, message, status=None, body=None):
        super().__init__(message)
        self.status = status
        self.body = body


# --------------------------------------------------------------------------- #
# Configuration and HTTP
# --------------------------------------------------------------------------- #

def is_enabled(app):
    """True only when the feature flag AND the secret key are both present."""
    return bool(app.config.get('PAYMONGO_ENABLED') and app.config.get('PAYMONGO_SECRET_KEY'))


def is_test_mode(app):
    return (app.config.get('PAYMONGO_SECRET_KEY') or '').startswith('sk_test_')


def _auth_header(app):
    secret = app.config.get('PAYMONGO_SECRET_KEY') or ''
    if not secret:
        raise PaymongoError('PAYMONGO_SECRET_KEY is not configured.')
    # HTTP Basic: the secret key is the username, the password is blank.
    token = base64.b64encode(f'{secret}:'.encode('utf-8')).decode('ascii')
    return {'Authorization': f'Basic {token}', 'Content-Type': 'application/json',
            'Accept': 'application/json'}


def _request(app, method, path, payload=None):
    try:
        resp = requests.request(method, PAYMONGO_API + path, headers=_auth_header(app),
                                json=payload, timeout=TIMEOUT)
    except requests.RequestException as exc:
        raise PaymongoError(f'Network error calling PayMongo: {exc.__class__.__name__}') from exc
    if resp.status_code >= 400:
        # PayMongo's error body is safe to log; the Authorization header never is.
        try:
            body = resp.json()
        except ValueError:
            body = {'raw': resp.text[:500]}
        raise PaymongoError('PayMongo rejected the request.', resp.status_code, body)
    return resp.json()


def to_centavos(amount):
    """Decimal pesos -> integer centavos (PayMongo amounts are in centavos)."""
    value = Decimal(str(amount)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    if value <= 0:
        raise ValueError('Amount must be greater than zero.')
    return int(value * 100)


# --------------------------------------------------------------------------- #
# Checkout sessions
# --------------------------------------------------------------------------- #

def create_checkout_session(app, *, amount, description, reference_number,
                            success_url, cancel_url, metadata=None):
    """Create a Hosted Checkout session. Returns (session_id, checkout_url)."""
    attributes = {
        'line_items': [{'currency': 'PHP', 'amount': to_centavos(amount),
                        'name': (description or 'Payment')[:255], 'quantity': 1}],
        'payment_method_types': PAYMENT_METHOD_TYPES,
        'success_url': success_url,
        'cancel_url': cancel_url,
        'reference_number': (reference_number or '')[:100],
        'description': (description or '')[:255],
        'send_email_receipt': True,
        'show_description': True,
        'show_line_items': True,
    }
    if metadata:
        attributes['metadata'] = {str(k)[:40]: str(v)[:255] for k, v in metadata.items()}
    body = _request(app, 'POST', '/checkout_sessions', {'data': {'attributes': attributes}})
    data = body.get('data') or {}
    url = (data.get('attributes') or {}).get('checkout_url')
    if not data.get('id') or not url:
        raise PaymongoError('PayMongo did not return a checkout link.', body=body)
    return data['id'], url


def retrieve_checkout_session(app, session_id):
    """The session's attributes (status, reference_number, payments, ...)."""
    body = _request(app, 'GET', f'/checkout_sessions/{session_id}')
    return (body.get('data') or {}).get('attributes') or {}


def expire_checkout_session(app, session_id):
    """Close an unpaid session so it can no longer be paid (e.g. order cancelled)."""
    _request(app, 'POST', f'/checkout_sessions/{session_id}/expire')


def paid_payment(session_attributes):
    """(payment_id, amount_centavos) of the session's paid payment, or None.
    A checkout session has at most one payment with status 'paid'."""
    for p in session_attributes.get('payments') or []:
        attrs = p.get('attributes') or {}
        if attrs.get('status') == 'paid':
            return p.get('id') or '', int(attrs.get('amount') or 0)
    return None


# --------------------------------------------------------------------------- #
# Refunds
# --------------------------------------------------------------------------- #

def create_refund(app, *, payment_id, amount, notes=''):
    """Refund (part of) a paid payment back to the customer's card / e-wallet.
    Returns (refund_id, status)."""
    body = _request(app, 'POST', '/refunds', {'data': {'attributes': {
        'amount': to_centavos(amount), 'payment_id': payment_id,
        'reason': 'requested_by_customer', 'notes': (notes or '')[:255]}}})
    data = body.get('data') or {}
    return data.get('id') or '', (data.get('attributes') or {}).get('status') or ''


# --------------------------------------------------------------------------- #
# Webhooks
# --------------------------------------------------------------------------- #

def signature_matches(secret, raw_body, header_value, now=None):
    """Paymongo-Signature is 't=<unix ts>,te=<test sig>,li=<live sig>'; the
    signature is HMAC-SHA256(secret, '<t>.<raw body>') in hex. Either te or li
    must match (one is always empty) and the timestamp must be recent."""
    if not header_value:
        return False
    parts = dict(p.split('=', 1) for p in header_value.split(',') if '=' in p)
    ts = parts.get('t', '')
    if not ts.isdigit() or abs((now or time.time()) - int(ts)) > SIGNATURE_MAX_AGE:
        return False
    expected = hmac.new(secret.encode('utf-8'), f'{ts}.'.encode('utf-8') + raw_body,
                        hashlib.sha256).hexdigest()
    return any(parts.get(key) and hmac.compare_digest(expected, parts[key]) for key in ('te', 'li'))


def parse_webhook(app, raw_body, signature_header):
    """Verify and decode a webhook body. Raises PaymongoError when invalid."""
    secret = app.config.get('PAYMONGO_WEBHOOK_SECRET') or ''
    if secret:
        if not signature_matches(secret, raw_body, signature_header):
            raise PaymongoError('Webhook signature did not verify.')
    elif os.environ.get('FLASK_ENV') == 'production':
        # A production site must never accept unsigned "paid" events.
        raise PaymongoError('PAYMONGO_WEBHOOK_SECRET is not set; refusing webhook in production.')
    else:
        log.warning('Accepting unsigned PayMongo webhook (PAYMONGO_WEBHOOK_SECRET is empty).')
    try:
        event = json.loads(raw_body.decode('utf-8'))
    except (ValueError, UnicodeDecodeError) as exc:
        raise PaymongoError('Webhook body is not valid JSON.') from exc
    if not isinstance(event, dict) or not isinstance(event.get('data'), dict):
        raise PaymongoError('Webhook body has an unexpected shape.')
    return event


def event_summary(event):
    """The parts of a webhook we use. The event envelope is
    data.attributes.{type, livemode, data=<resource>}; for checkout events the
    resource is the checkout session."""
    attrs = (event.get('data') or {}).get('attributes') or {}
    resource = attrs.get('data') or {}
    r_attrs = resource.get('attributes') or {}
    metadata = r_attrs.get('metadata') or {}
    paid = paid_payment(r_attrs)
    return {
        'event_type': attrs.get('type') or '',
        'livemode': bool(attrs.get('livemode')),
        'checkout_session_id': resource.get('id') if resource.get('type') == 'checkout_session' else '',
        'reference_number': r_attrs.get('reference_number') or metadata.get('transaction_number') or '',
        'payment_id': paid[0] if paid else '',
        'amount_centavos': paid[1] if paid else 0,
    }
