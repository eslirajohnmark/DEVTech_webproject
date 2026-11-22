"""Sign-in lockout for every portal (customer, technician, admin).

Five wrong passwords in a row for the same email or Tech ID lock that sign-in for
10 seconds. Every further lockout lasts twice as long (20 s, 40 s, 80 s ...), up to
15 minutes. A successful sign-in, or a day without failures, starts over.

Counted per email / Tech ID, whether or not the account exists, so the replies never
reveal which emails are registered."""
from datetime import datetime, timedelta

MAX_ATTEMPTS = 5
FIRST_LOCK_SECONDS = 10
MAX_LOCK_SECONDS = 15 * 60
FORGET_AFTER = timedelta(days=1)


def _key(portal, identifier):
    return f'{portal}:{(identifier or "").strip().lower()}'[:190]


def _row(portal, identifier):
    from app import LoginAttempt
    return LoginAttempt.query.filter_by(key=_key(portal, identifier)).first()


def seconds_left(portal, identifier, now=None):
    """Seconds this sign-in is still locked for (0 = it may try)."""
    if not identifier:
        return 0
    row = _row(portal, identifier)
    now = now or datetime.utcnow()
    if not row or not row.locked_until or row.locked_until <= now:
        return 0
    return max(1, int((row.locked_until - now).total_seconds() + 0.999))


def lock_seconds_for(lockouts):
    """How long the n-th lockout in a row lasts (1st = 10 s, 2nd = 20 s ...)."""
    return min(MAX_LOCK_SECONDS, FIRST_LOCK_SECONDS * 2 ** max(lockouts - 1, 0))


def record_failure(portal, identifier, now=None):
    """Count a wrong password. Returns (attempts left before a lockout, seconds locked or 0)."""
    from app import db, LoginAttempt
    now = now or datetime.utcnow()
    row = _row(portal, identifier)
    if row is None:
        row = LoginAttempt(key=_key(portal, identifier), failures=0, lockouts=0)
        db.session.add(row)
    elif row.last_failed_at and now - row.last_failed_at > FORGET_AFTER:
        row.failures, row.lockouts = 0, 0                 # long ago: start over
    row.failures = (row.failures or 0) + 1
    row.last_failed_at = now
    locked = 0
    if row.failures >= MAX_ATTEMPTS:
        row.lockouts = (row.lockouts or 0) + 1
        locked = lock_seconds_for(row.lockouts)
        row.locked_until = now + timedelta(seconds=locked)
        row.failures = 0                                  # after the wait: five more tries
    db.session.commit()
    return MAX_ATTEMPTS - row.failures if not locked else 0, locked


def clear(portal, identifier):
    """A successful sign-in: forget the failures."""
    from app import db
    row = _row(portal, identifier)
    if row is not None:
        db.session.delete(row)
        db.session.commit()


def wait_text(seconds):
    if seconds < 60:
        return f'{seconds} second{"s" if seconds != 1 else ""}'
    minutes = (seconds + 59) // 60
    return f'{minutes} minute{"s" if minutes != 1 else ""}'


def failure_message(base, attempts_left, locked):
    """The message after a wrong password: how many tries are left, or how long to wait."""
    if locked:
        return f'Too many failed sign-in attempts. Try again in {wait_text(locked)}.'
    if attempts_left <= 2:
        return f'{base} {attempts_left} attempt{"s" if attempts_left != 1 else ""} left before sign-in is paused.'
    return base


def locked_message(seconds):
    return f'Too many failed sign-in attempts. Try again in {wait_text(seconds)}.'
