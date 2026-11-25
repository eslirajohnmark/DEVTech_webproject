"""Philippine mobile numbers for customer registration.

Accepted as typed (spaces and dashes between the digits are fine):
    local          09171234567     (11 digits, starts with 09)
    international  +639171234567   (+63, then 9 and nine more digits)
Saved in one format, E.164: +639171234567.

Two checks, in order:
 1. Structure, with a clear message for each mistake (letters, symbols, wrong start,
    too short, too long). static/js/ph-phone.js shows the same messages while typing.
 2. The network prefix (0917, 0995, ...): it must be a range assigned to a Philippine
    mobile network. This uses Google's libphonenumber data (the `phonenumbers` package),
    which is kept up to date as new prefixes are assigned, instead of a hand-made list.
"""
import re

try:
    import phonenumbers
    from phonenumbers import PhoneNumberType
except ImportError:            # the structure check still runs; requirements.txt installs it
    phonenumbers = None

EXAMPLE_LOCAL, EXAMPLE_INTL = '09171234567', '+639171234567'
_SEPARATORS = re.compile(r'[\s-]')


def check_ph_mobile(raw):
    """(e164, None) for a valid Philippine mobile number, else (None, message)."""
    typed = (raw or '').strip()
    if not typed:
        return None, f'Enter your mobile number, e.g. {EXAMPLE_LOCAL}.'
    if re.search(r'[A-Za-z]', typed):
        return None, 'The mobile number can only contain numbers, not letters.'
    compact = _SEPARATORS.sub('', typed)
    if re.search(r'[^\d+]', compact) or '+' in compact[1:]:
        return None, 'Use numbers only. Spaces, dashes and a + at the start are the only other characters allowed.'

    if compact.startswith('+'):
        if not compact.startswith('+639'):
            return None, f'An international number must start with +639, e.g. {EXAMPLE_INTL}.'
        digits = len(compact) - 1
        if digits < 12:
            return None, f'Too short: +63 numbers have 12 digits after the + (you typed {digits}), e.g. {EXAMPLE_INTL}.'
        if digits > 12:
            return None, f'Too long: +63 numbers have 12 digits after the + (you typed {digits}), e.g. {EXAMPLE_INTL}.'
        e164 = compact
    else:
        if not compact.startswith('09'):
            return None, f'Incorrect prefix: a mobile number starts with 09 ({EXAMPLE_LOCAL}) or +639 ({EXAMPLE_INTL}).'
        if len(compact) < 11:
            return None, f'Too short: a mobile number has 11 digits (you typed {len(compact)}), e.g. {EXAMPLE_LOCAL}.'
        if len(compact) > 11:
            return None, f'Too long: a mobile number has 11 digits (you typed {len(compact)}), e.g. {EXAMPLE_LOCAL}.'
        e164 = '+63' + compact[1:]

    if phonenumbers is not None:
        number = phonenumbers.parse(e164, 'PH')
        if not phonenumbers.is_valid_number(number) or \
                phonenumbers.number_type(number) not in (PhoneNumberType.MOBILE, PhoneNumberType.FIXED_LINE_OR_MOBILE):
            return None, (f'0{e164[3:6]} is not a Philippine mobile network prefix. '
                          'Check the number and try again.')
    return e164, None


def stored_forms(e164):
    """Every way an earlier version of the site may have saved this number
    (+639..., 09..., 639...), to find an account that already uses it."""
    return [e164, '0' + e164[3:], e164[1:]]
