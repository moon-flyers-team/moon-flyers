"""Sun and Earth azimuth/elevation series for a site.

Currently MOCK: deterministic synthetic values (no network, not NASA data) that behave
plausibly:
- the Sun circles the sky once per synodic month; its elevation swings by about the site's
  colatitude, plus a ±1.54° seasonal term, so polar sites sit near the horizon;
- Earth hangs near the sub-Earth direction and wobbles with libration (±7°), so near-side polar
  sites get intermittent contact and far-side sites never see Earth.

To go live, make `generate()` call `positions.positions()` (JPL Horizons) and return the same
dict shape. Nothing else needs to change.
"""

import math
from datetime import datetime, timedelta, timezone

from ..schemas import Site
from .errors import LimitExceededError

DATA_SOURCE = "mock"  # sent as the X-Moon-Flyers-Data-Source header; set to "horizons" when live
MAX_SAMPLES = 100_000

_J2000 = datetime(2000, 1, 1, 12, tzinfo=timezone.utc)
_SYNODIC_H = 29.530589 * 24
_ANOMALISTIC_H = 27.554550 * 24
_DRACONIC_H = 27.212221 * 24
_ECLIPSE_YEAR_H = 346.62 * 24


def _angles(site: Site, t: datetime) -> tuple[float, float, float, float]:
    h = (t - _J2000).total_seconds() / 3600
    lat, lon = math.radians(site.latitude_deg), math.radians(site.longitude_deg)
    colat = 90 - abs(site.latitude_deg)

    syn = 2 * math.pi * h / _SYNODIC_H
    sun_az = (math.degrees(syn) + site.longitude_deg + 180) % 360
    sun_el = colat * math.cos(syn + lon) + 1.54 * math.sin(2 * math.pi * h / _ECLIPSE_YEAR_H)

    dist_to_sub_earth = math.degrees(math.acos(math.cos(lat) * math.cos(lon)))
    lib_lat = 6.7 * math.sin(2 * math.pi * h / _DRACONIC_H)
    lib_lon = 7.0 * math.sin(2 * math.pi * h / _ANOMALISTIC_H)
    earth_el = 90 - dist_to_sub_earth + lib_lat + lib_lon * math.sin(lon) * math.cos(lat)
    earth_az = (-site.longitude_deg + lib_lon) % 360

    return sun_az, sun_el, earth_az, earth_el


def sample_count(start: datetime, end: datetime, step_s: int) -> int:
    return int((end - start).total_seconds() // step_s) + 1


def generate(site: Site, start: datetime, end: datetime, step_s: int) -> dict:
    """Az/el series from `start` to `end` inclusive, every `step_s` seconds.

    Returns {"times": [datetime], "sun_az": [...], "sun_el": [...], "earth_az": [...], "earth_el": [...]}.
    """
    n = sample_count(start, end, step_s)
    if n > MAX_SAMPLES:
        raise LimitExceededError(f"request needs {n} samples per series; the limit is {MAX_SAMPLES}")
    times = [start + timedelta(seconds=i * step_s) for i in range(n)]
    cols = list(zip(*(_angles(site, t) for t in times)))
    return {"times": times, "sun_az": list(cols[0]), "sun_el": list(cols[1]),
            "earth_az": list(cols[2]), "earth_el": list(cols[3])}
