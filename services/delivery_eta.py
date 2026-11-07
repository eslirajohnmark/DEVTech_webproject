"""Estimated delivery time for shop orders.

The estimate comes from two things the shop actually knows:
  * distance: the shop's pinned location to the customer's pinned location
    (straight line x a road factor), or, without pins, same city / same
    province / elsewhere;
  * rider availability: how many delivery riders are on duty and how many
    orders are already waiting for them or out on the road.

Riders cover RIDER_RADIUS_KM around the shop; farther addresses go by courier
and get a range of business days instead of a time window. All times here are
Philippine time (UTC+8). The shop opens Monday to Saturday.
"""
import math
from datetime import datetime, timedelta, timezone

PH_TZ = timezone(timedelta(hours=8))
OPEN_HOUR, CLOSE_HOUR = 9, 18        # riders deliver 9 AM - 6 PM
CUTOFF_HOUR = 16                     # orders after 4 PM are prepared the next business day
PREP_MINUTES = 60                    # picking and packing
SPEED_KMH = 25                       # motorcycle in city traffic
ROAD_FACTOR = 1.3                    # roads are longer than the straight line
HANDOFF_MINUTES = 10                 # finding the door, handing over, collecting COD
ORDERS_PER_TRIP = 3                  # a rider carries up to 3 nearby orders per trip
RIDER_RADIUS_KM = 40
SAME_CITY_KM, SAME_PROVINCE_KM = 8, 25


def haversine_km(lat1, lon1, lat2, lon2):
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def _norm(text):
    return ' '.join((text or '').lower().replace('city of', '').replace('city', '').split())


def road_distance_km(shop, dest):
    """(km or None, basis). shop / dest: dicts with lat, lng, city, province.
    basis is 'pin' (both pinned), 'city', 'province', or 'unknown'."""
    try:
        if None not in (shop.get('lat'), shop.get('lng'), dest.get('lat'), dest.get('lng')):
            km = haversine_km(float(shop['lat']), float(shop['lng']), float(dest['lat']), float(dest['lng']))
            return round(max(km * ROAD_FACTOR, 0.5), 1), 'pin'
    except (TypeError, ValueError):
        pass
    if shop.get('city') and _norm(shop['city']) == _norm(dest.get('city')):
        return SAME_CITY_KM, 'city'
    if shop.get('province') and _norm(shop['province']) == _norm(dest.get('province')):
        return SAME_PROVINCE_KM, 'province'
    return None, 'unknown'


def _is_open_day(d):
    return d.weekday() != 6                          # closed on Sundays


def _next_open(t):
    """t if the shop is open then, else the next opening time."""
    if _is_open_day(t) and OPEN_HOUR <= t.hour < CLOSE_HOUR:
        return t
    day = t if t.hour < OPEN_HOUR else t + timedelta(days=1)
    day = day.replace(hour=OPEN_HOUR, minute=0, second=0, microsecond=0)
    while not _is_open_day(day):
        day += timedelta(days=1)
    return day


def _next_business_morning(t):
    """Opening time on the first open day after t's date."""
    day = (t + timedelta(days=1)).replace(hour=OPEN_HOUR, minute=0, second=0, microsecond=0)
    while not _is_open_day(day):
        day += timedelta(days=1)
    return day


def _add_business_days(t, days):
    d = t
    while days > 0:
        d += timedelta(days=1)
        if _is_open_day(d):
            days -= 1
    return d


def _round_up(t, minutes=15):
    t = t.replace(second=0, microsecond=0)
    extra = (-t.minute) % minutes
    return t + timedelta(minutes=extra)


def _fmt_time(t):
    return t.strftime('%I:%M %p').lstrip('0')


def _day_word(t, today):
    if t.date() == today:
        return 'Today'
    if t.date() == today + timedelta(days=1):
        return 'Tomorrow'
    return t.strftime('%a, %b %d').replace(' 0', ' ')


def to_ph(dt):
    """A naive-UTC or aware datetime in Philippine time."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(PH_TZ)


def to_utc_naive(dt):
    """An aware datetime as naive UTC, the way the database stores times."""
    return dt.astimezone(timezone.utc).replace(tzinfo=None)


def label_for(earliest, latest, now=None):
    """'Today, 2:00 PM – 3:00 PM' for a stored (naive UTC) window."""
    if not (earliest and latest):
        return 'to be confirmed'
    a, b = to_ph(earliest), to_ph(latest)
    today = to_ph(now or datetime.utcnow()).date()
    if a.date() == b.date() and (b - a) < timedelta(hours=12):
        return f"{_day_word(a, today)}, {_fmt_time(a)} – {_fmt_time(b)}"
    return f"{_day_word(a, today)} – {_day_word(b, today)}"


def estimate(now, distance_km, riders_on_duty, orders_ahead, dispatched_at=None):
    """The delivery estimate for one order.

    now: naive UTC (or aware) time; distance_km: km or None (unknown);
    riders_on_duty: riders available today; orders_ahead: orders waiting for
    or out with a rider before this one; dispatched_at: when this order left
    the shop, if it has.
    Returns {'earliest', 'latest' (aware PH datetimes), 'label', 'method', 'note'}.
    """
    now = to_ph(now)
    today = now.date()

    if distance_km is None or distance_km > RIDER_RADIUS_KM:
        far = distance_km is not None and distance_km > 150
        lo, hi = (3, 6) if far else (2, 4)
        start = now if now.hour < CUTOFF_HOUR else now + timedelta(days=1)
        earliest = _add_business_days(start, lo).replace(hour=OPEN_HOUR, minute=0, second=0, microsecond=0)
        latest = _add_business_days(start, hi).replace(hour=CLOSE_HOUR, minute=0, second=0, microsecond=0)
        note = ('Your address is outside our riders\' area, so it ships by courier.'
                if distance_km is not None else
                'We could not work out the distance to your address, so this is a courier estimate. '
                'Pin your location on the map for a more exact time.')
        return {'earliest': earliest, 'latest': latest, 'method': 'courier', 'note': note,
                'label': f"{_day_word(earliest, today)} – {_day_word(latest, today)}"}

    travel = max(10, distance_km / SPEED_KMH * 60)                  # minutes, one way
    if dispatched_at is not None:                                    # already on the way
        left = to_ph(dispatched_at)
        earliest = left + timedelta(minutes=travel * 0.8)
        latest = left + timedelta(minutes=travel * 1.6 + 30)
        if latest < now + timedelta(minutes=15):
            earliest, latest = now, now + timedelta(minutes=45)
        earliest, latest = _round_up(earliest), _round_up(latest)
        return {'earliest': earliest, 'latest': latest, 'method': 'rider',
                'note': 'Your order is with the rider.',
                'label': f"{_day_word(earliest, today)}, {_fmt_time(earliest)} – {_fmt_time(latest)}"}

    note = ''
    if riders_on_duty <= 0:
        start = _next_business_morning(now)
        note = 'No delivery rider is on duty right now, so it goes out on the next business day.'
    elif not _is_open_day(now) or now.hour >= CUTOFF_HOUR:
        start = _next_business_morning(now)
        note = 'Orders placed after 4 PM or on Sunday are sent on the next business day.'
    elif now.hour < OPEN_HOUR:
        start = now.replace(hour=OPEN_HOUR, minute=0, second=0, microsecond=0)
    else:
        start = now
    ready = start + timedelta(minutes=PREP_MINUTES)
    riders = max(riders_on_duty, 1)
    trip = 2 * travel + HANDOFF_MINUTES * ORDERS_PER_TRIP           # out and back with a full load
    waves = orders_ahead // (riders * ORDERS_PER_TRIP)
    depart = _next_open(ready + timedelta(minutes=waves * trip))
    if waves:
        note = (note + ' ' if note else '') + \
            f'{orders_ahead} order{"s" if orders_ahead != 1 else ""} ahead of yours with ' \
            f'{riders} rider{"s" if riders != 1 else ""} on duty.'
    earliest = depart + timedelta(minutes=travel)
    latest = earliest + timedelta(minutes=max(60, travel + HANDOFF_MINUTES * ORDERS_PER_TRIP))
    if latest.hour >= CLOSE_HOUR + 1:                                # would arrive after hours
        depart = _next_open(latest.replace(hour=CLOSE_HOUR) + timedelta(hours=1))
        note = note or 'It can no longer reach you before 6 PM today, so it arrives on the next business day.'
        earliest = depart + timedelta(minutes=travel)
        latest = earliest + timedelta(minutes=max(60, travel + HANDOFF_MINUTES * ORDERS_PER_TRIP))
    earliest, latest = _round_up(earliest), _round_up(latest)
    return {'earliest': earliest, 'latest': latest, 'method': 'rider', 'note': note.strip(),
            'label': f"{_day_word(earliest, today)}, {_fmt_time(earliest)} – {_fmt_time(latest)}"}
