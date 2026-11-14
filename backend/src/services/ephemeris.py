"""Sun and Earth azimuth/elevation series for a site.

Live data comes from JPL Horizons via the teammate's `positions.positions()`. That is two HTTP
calls per site per request, with no caching (working over efficient). Angles are for the centre
of each body, airless, relative to the local horizontal plane of the reference sphere (no terrain).

Set the env var `MOON_FLYERS_EPHEMERIS=mock` for offline synthetic data (`mock_ephemeris.py`).
The tests do this in `tests/conftest.py`.
"""

import os
import threading
import time
import urllib.error
from datetime import datetime, timedelta, timezone

from .. import positions
from ..schemas import Site
from . import mock_ephemeris
from .errors import EphemerisUnavailableError, InvalidInputError, LimitExceededError

# Sent as the X-Moon-Flyers-Data-Source header: "horizons" or "mock".
DATA_SOURCE = "mock" if os.environ.get("MOON_FLYERS_EPHEMERIS") == "mock" else "horizons"
MAX_SAMPLES = 90_000  # Horizons rejects longer tables ("max. is 90000")
HORIZONS_CONCURRENCY = 2  # Horizons returns 503 beyond about 2 open requests per IP
RETRY_DELAYS_S = (1, 2, 4, 8)  # backoff between retries after a 503; then one last try

# Sync endpoints run in FastAPI's thread pool, so a threading semaphore covers the whole process.
_horizons_slots = threading.BoundedSemaphore(HORIZONS_CONCURRENCY)


def generate(site: Site, start: datetime, end: datetime, step_s: int) -> dict:
    """Az/el series from `start` to `end` inclusive, every `step_s` seconds.

    Returns {"times": [datetime], "sun_az": [...], "sun_el": [...], "earth_az": [...], "earth_el": [...]}.
    """
    n = int((end - start).total_seconds() // step_s) + 1
    if n > MAX_SAMPLES:
        raise LimitExceededError(f"request needs {n} samples per series; the limit is {MAX_SAMPLES}")
    if DATA_SOURCE == "mock":
        return mock_ephemeris.generate(site, start, end, step_s)
    return _horizons(site, start, end, step_s, n)


def _naive_utc(t: datetime) -> str:
    """positions() wants ISO strings without an offset, meaning UTC."""
    return t.astimezone(timezone.utc).replace(tzinfo=None).isoformat()


def _call_positions(*args) -> dict:
    """positions() with at most HORIZONS_CONCURRENCY calls in flight, retrying Horizons' 503.

    Horizons answers 503 when one IP has more than about 2 requests open (measured 2026-11-14:
    2 parallel OK, 4 parallel → half fail). The frontend fires /compare plus one GET /sites per
    site at once, so without this most of them fail.
    """
    for delay in RETRY_DELAYS_S:
        with _horizons_slots:
            try:
                return positions.positions(*args)
            except urllib.error.HTTPError as e:
                if e.code != 503:
                    raise
        time.sleep(delay)  # outside the slot, so others can proceed
    with _horizons_slots:
        return positions.positions(*args)


def _horizons(site: Site, start: datetime, end: datetime, step_s: int, n: int) -> dict:
    try:
        raw = _call_positions(site.latitude_deg, site.longitude_deg, _naive_utc(start), _naive_utc(end), step_s)
    except ValueError as e:  # e.g. a non-whole-minute step that doesn't divide the span
        raise InvalidInputError(str(e)) from e
    except Exception as e:  # network failure, Horizons error, unparseable table
        raise EphemerisUnavailableError(f"JPL Horizons request failed: {e}") from e

    times = [datetime.fromisoformat(t).replace(tzinfo=timezone.utc) for t in raw["time_utc"]]
    expected = [start + timedelta(seconds=i * step_s) for i in range(n)]
    if times != expected:
        raise EphemerisUnavailableError(
            f"Horizons returned {len(times)} samples that don't match the requested {n}-sample time grid")
    return {"times": times, "sun_az": raw["sun_azimuth_deg"], "sun_el": raw["sun_elevation_deg"],
            "earth_az": raw["earth_azimuth_deg"], "earth_el": raw["earth_elevation_deg"]}
