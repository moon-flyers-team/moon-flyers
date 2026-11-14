"""Sun and Earth azimuth/elevation series for a site.

Live data comes from JPL Horizons via the teammate's `positions.positions()`. That is two HTTP
calls per site per request, with no caching (working over efficient). Angles are for the centre
of each body, airless, relative to the local horizontal plane of the reference sphere (no terrain).

Set the env var `MOON_FLYERS_EPHEMERIS=mock` for offline synthetic data (`mock_ephemeris.py`).
The tests do this in `tests/conftest.py`.
"""

import os
from datetime import datetime, timedelta, timezone

from .. import positions
from ..schemas import Site
from . import mock_ephemeris
from .errors import EphemerisUnavailableError, InvalidInputError, LimitExceededError

# Sent as the X-Moon-Flyers-Data-Source header: "horizons" or "mock".
DATA_SOURCE = "mock" if os.environ.get("MOON_FLYERS_EPHEMERIS") == "mock" else "horizons"
MAX_SAMPLES = 90_000  # Horizons rejects longer tables ("max. is 90000")


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


def _horizons(site: Site, start: datetime, end: datetime, step_s: int, n: int) -> dict:
    try:
        raw = positions.positions(site.latitude_deg, site.longitude_deg,
                                  _naive_utc(start), _naive_utc(end), step_s)
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
