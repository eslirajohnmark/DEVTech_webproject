"""The password rule for new customer and technician accounts: at least 8
characters, with a capital letter, a small letter, a number and a special
character. static/js/password-rules.js shows the same rules as a live checklist."""
import re

RULES = (
    ('length', 'at least 8 characters', lambda p: len(p) >= 8),
    ('upper', 'a capital letter (A-Z)', lambda p: re.search(r'[A-Z]', p) is not None),
    ('lower', 'a small letter (a-z)', lambda p: re.search(r'[a-z]', p) is not None),
    ('digit', 'a number (0-9)', lambda p: re.search(r'\d', p) is not None),
    ('special', 'a special character such as ! @ # $ %', lambda p: re.search(r'[^A-Za-z0-9\s]', p) is not None),
)


def password_problem(password):
    """What the password still needs, as one sentence, or None when it is strong enough."""
    missing = [label for _key, label, ok in RULES if not ok(password or '')]
    if not missing:
        return None
    return 'Your password needs ' + (', '.join(missing[:-1]) + ' and ' + missing[-1] if len(missing) > 1 else missing[0]) + '.'
