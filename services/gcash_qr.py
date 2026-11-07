"""GCash payment QR with the exact amount to pay.

GCash QR codes are QR Ph codes: an EMVCo "merchant-presented" payload made of
TLV fields (2-digit id, 2-digit length, value) ending in a CRC. The shop's own
QR (uploaded once by an admin, decoded in the browser) is stored as that text.
At checkout the amount is written into field 54, the code is switched from
static (01=11) to dynamic (01=12), and the CRC is recomputed, so the customer's
GCash app opens with the amount already filled in.
"""
from decimal import Decimal, ROUND_HALF_UP

import segno


class InvalidQrPayload(ValueError):
    pass


def crc16_ccitt(data):
    """CRC-16/CCITT-FALSE (poly 0x1021, init 0xFFFF), as EMVCo QR codes use."""
    crc = 0xFFFF
    for byte in data.encode('utf-8'):
        crc ^= byte << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) if crc & 0x8000 else crc << 1
            crc &= 0xFFFF
    return f'{crc:04X}'


def parse_tlv(payload):
    """[(id, value), ...] for a TLV string; raises InvalidQrPayload if malformed."""
    fields, i = [], 0
    while i < len(payload):
        tag, length = payload[i:i + 2], payload[i + 2:i + 4]
        if len(tag) < 2 or not tag.isdigit() or not length.isdigit():
            raise InvalidQrPayload('This is not a payment QR code.')
        end = i + 4 + int(length)
        if end > len(payload):
            raise InvalidQrPayload('This QR code is incomplete.')
        fields.append((tag, payload[i + 4:end]))
        i = end
    return fields


def _join(fields):
    return ''.join(f'{tag}{len(value):02d}{value}' for tag, value in fields)


def validate_payload(payload):
    """The cleaned payload if it is a QR Ph / EMVCo payment code with a correct CRC."""
    payload = (payload or '').strip()
    if not payload.startswith('000201') or len(payload) > 512:
        raise InvalidQrPayload('This is not a GCash / QR Ph payment code.')
    fields = parse_tlv(payload)
    if fields[-1][0] != '63' or len(fields[-1][1]) != 4:
        raise InvalidQrPayload('This QR code has no checksum.')
    if crc16_ccitt(payload[:-4]) != fields[-1][1].upper():
        raise InvalidQrPayload('This QR code is damaged (checksum mismatch). Upload a clearer image.')
    if not any(26 <= int(tag) <= 51 for tag, _ in fields):
        raise InvalidQrPayload('This QR code has no account to pay to.')
    currency = dict(fields).get('53')
    if currency and currency != '608':
        raise InvalidQrPayload('This QR code is not for Philippine peso payments.')
    return payload


def with_amount(payload, amount):
    """The shop's QR payload with the exact amount set and a fresh CRC."""
    amount = Decimal(str(amount)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    if amount <= 0:
        raise InvalidQrPayload('The amount must be more than zero.')
    fields = [(t, v) for t, v in parse_tlv(validate_payload(payload)) if t not in ('54', '63')]
    values = dict(fields)
    values['01'] = '12'                     # dynamic: a one-off code for this amount
    values.setdefault('53', '608')          # Philippine peso
    values['54'] = f'{amount:.2f}'
    body = _join([(t, values[t]) for t in sorted(values, key=int)]) + '6304'   # fields in id order
    return body + crc16_ccitt(body)


def qr_svg_data_uri(text):
    """An SVG data URI of the QR code, for an <img src>."""
    return segno.make(text, error='m', micro=False).svg_data_uri(scale=6, border=2, dark='#0f172a')
