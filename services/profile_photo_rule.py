"""A verified technician must add a photo of themselves as their profile picture, so
customers can recognise who handles their device. Once they are verified without one
they get a notice with a 2-day deadline. After it passes, the admins are told once and
an admin can send another notice or suspend the account.

Notice bookkeeping is not a profile edit, so it never bumps the technician's
updated_at (the live updates watch it)."""
from datetime import datetime, timedelta

DAYS = 2


def applies(tech):
    """Verified, but no photo (an icon or initials do not count)."""
    return tech.verification_status == 'verified' and not tech.avatar_file


def deadline(tech):
    return tech.photo_notice_at + timedelta(days=DAYS) if tech.photo_notice_at else None


def overdue(tech, now=None):
    due = deadline(tech)
    return bool(applies(tech) and due and (now or datetime.utcnow()) > due)


def _quietly(tech, **values):
    from app import db, Technician
    values['updated_at'] = tech.updated_at
    Technician.query.filter_by(id=tech.id).update(values, synchronize_session=False)
    db.session.commit()
    db.session.refresh(tech)


def due_text(tech):
    """The deadline in Philippine time (UTC+8, no daylight saving), e.g. "Nov 21, 3:05 PM"."""
    due = deadline(tech)
    if not due:
        return ''
    local = due + timedelta(hours=8)
    return f"{local.strftime('%b')} {local.day}, {local.strftime('%I:%M %p').lstrip('0')}"


def send_notice(tech, reminder=False):
    """Start (or restart) the 2-day notice and tell the technician."""
    from app import create_notification
    _quietly(tech, photo_notice_at=datetime.utcnow(), photo_notice_count=(tech.photo_notice_count or 0) + 1,
             photo_overdue_reported_at=None)
    create_notification(
        tech.id, 'Reminder: add your profile photo' if reminder else 'Add a profile photo of yourself',
        f'Your account is verified. Add a clear photo of yourself as your profile picture by {due_text(tech)}, '
        'so customers can recognise who is handling their device. If it is not added by then, '
        'the admin may suspend your account.', 'warning', role='technician')


def ensure_notice(tech):
    """The first notice, for a verified technician without a photo who has not been told yet."""
    if applies(tech) and not tech.photo_notice_at:
        send_notice(tech)


def photo_added(tech):
    """The technician added a photo: the requirement is met, so the notice ends."""
    from app import notify_admins
    if not tech.avatar_file or not tech.photo_notice_at:
        return
    was_overdue = datetime.utcnow() > deadline(tech) or bool(tech.photo_overdue_reported_at)
    _quietly(tech, photo_notice_at=None, photo_overdue_reported_at=None)
    if was_overdue:
        notify_admins('Profile photo added', f'{tech.full_name} ({tech.username}) added their profile photo.', 'success')


def overdue_query(now=None):
    from app import Technician
    cutoff = (now or datetime.utcnow()) - timedelta(days=DAYS)
    return Technician.query.filter(Technician.verification_status == 'verified', Technician.avatar_file.is_(None),
                                   Technician.photo_notice_at.isnot(None), Technician.photo_notice_at < cutoff)


def report_overdue():
    """Tell the admins, once per notice, about technicians whose deadline has passed."""
    from app import Technician, notify_admins
    for tech in overdue_query().filter(Technician.photo_overdue_reported_at.is_(None)).all():
        _quietly(tech, photo_overdue_reported_at=datetime.utcnow())
        notify_admins('Profile photo overdue',
                      f'{tech.full_name} ({tech.username}) has not added a profile photo {DAYS} days after the '
                      'notice. Open their verification page to send another notice or suspend the account.',
                      'warning')
