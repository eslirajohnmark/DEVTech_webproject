"""Tacloban City's boundary, for checking that a home-service or delivery pin is
inside the city. The outline is static/data/tacloban_boundary.geojson (the 138
barangays of PSGC 0831600000 merged, PSA 2023); the maps draw the same file, so
what the customer sees and what the server accepts always agree.
"""
import json
import os
from functools import lru_cache

BOUNDARY_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                             'static', 'data', 'tacloban_boundary.geojson')

# Downtown Tacloban, where the (fictional) DEVTech shop is: used when Settings has
# no shop pin yet, so in-shop directions and delivery estimates work from day one.
DEFAULT_SHOP = {
    'name': 'DEVTech Computer Services',
    'address': 'Unit 2, DEVTech Building, 118 Rizal Avenue (corner Zamora Street), Downtown, Tacloban City, 6500 Leyte',
    'short': '118 Rizal Avenue, Downtown Tacloban',
    'lat': 11.24366,
    'lng': 125.00337,
    'city': 'Tacloban City',
    'province': 'Leyte',
    'hours': 'Mon-Sat, 8:00 AM - 6:00 PM',
}


@lru_cache(maxsize=1)
def _polygons():
    """[(outer ring, [holes])] as (lng, lat) tuples, plus the bounding box."""
    with open(BOUNDARY_FILE, encoding='utf-8') as fh:
        data = json.load(fh)
    polys = []
    for feature in data['features']:
        geom = feature['geometry']
        parts = geom['coordinates'] if geom['type'] == 'MultiPolygon' else [geom['coordinates']]
        for rings in parts:
            rings = [[(float(x), float(y)) for x, y in ring] for ring in rings]
            polys.append((rings[0], rings[1:]))
    xs = [x for outer, _ in polys for x, _y in outer]
    ys = [y for outer, _ in polys for _x, y in outer]
    return polys, (min(xs), min(ys), max(xs), max(ys))


def _in_ring(x, y, ring):
    inside = False
    j = len(ring) - 1
    for i in range(len(ring)):
        xi, yi = ring[i]
        xj, yj = ring[j]
        if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / (yj - yi) + xi:
            inside = not inside
        j = i
    return inside


def inside_tacloban(lat, lng):
    """True when (lat, lng) is inside Tacloban City."""
    try:
        lat, lng = float(lat), float(lng)
    except (TypeError, ValueError):
        return False
    polys, (minx, miny, maxx, maxy) = _polygons()
    if not (minx <= lng <= maxx and miny <= lat <= maxy):
        return False
    return any(_in_ring(lng, lat, outer) and not any(_in_ring(lng, lat, h) for h in holes)
               for outer, holes in polys)


def bounds():
    """(south, west, north, east) of the city."""
    _, (minx, miny, maxx, maxy) = _polygons()
    return miny, minx, maxy, maxx
