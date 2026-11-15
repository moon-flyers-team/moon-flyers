"""Visibility flags, visibility intervals, metrics and fit.

Works on any az/el series (mock or real Horizons data) and any horizon model.
"""

import math
from datetime import datetime, timedelta

from ..schemas import Constraints, Fit, Interval, Metrics
from .horizon import HorizonModel

SUN_RADIUS_DEG = 0.267   # angular radius seen from the Moon
EARTH_RADIUS_DEG = 0.95

FIT_ORDER = {"both_met": 0, "power_short": 1, "comms_short": 1, "neither_met": 2}


def iso(t: datetime) -> str:
    return t.strftime("%Y-%m-%dT%H:%M:%SZ")


def visible_flags(az: list[float], el: list[float], radius: float, clearance: float,
                  horizon: HorizonModel) -> list[bool]:
    """Whole disc at least `clearance` above the horizon."""
    return [e - radius >= horizon.elevation_deg(a) + clearance for a, e in zip(az, el)]


def separation_deg(az1: float, el1: float, az2: float, el2: float) -> float:
    a1, e1, a2, e2 = map(math.radians, (az1, el1, az2, el2))
    c = math.sin(e1) * math.sin(e2) + math.cos(e1) * math.cos(e2) * math.cos(a1 - a2)
    return math.degrees(math.acos(max(-1.0, min(1.0, c))))


def eclipse_flags(sun_az: list[float], sun_el: list[float], earth_az: list[float], earth_el: list[float],
                  earth_visible: list[bool]) -> list[bool]:
    """Earth's disc overlaps the Sun's (partial or total), and Earth is visible from the site."""
    limit = SUN_RADIUS_DEG + EARTH_RADIUS_DEG
    return [v and separation_deg(sa, se, ea, ee) < limit
            for sa, se, ea, ee, v in zip(sun_az, sun_el, earth_az, earth_el, earth_visible)]


def intervals(times: list[datetime], flags: list[bool], step_s: int) -> list[Interval]:
    """Runs of visible samples. `end_utc` is the first non-visible sample, or the series end + one step."""
    out, run_start = [], None
    for t, f in zip(times, flags):
        if f and run_start is None:
            run_start = t
        elif not f and run_start is not None:
            out.append(Interval(start_utc=iso(run_start), end_utc=iso(t)))
            run_start = None
    if run_start is not None:
        out.append(Interval(start_utc=iso(run_start), end_utc=iso(times[-1] + timedelta(seconds=step_s))))
    return out


def _longest_false_run(flags: list[bool]) -> int:
    best = cur = 0
    for f in flags:
        cur = 0 if f else cur + 1
        best = max(best, cur)
    return best


def metrics(sun: list[bool], earth: list[bool], step_s: int) -> Metrics:
    step_h = step_s / 3600
    return Metrics(
        sun_visible_pct=round(100 * sum(sun) / len(sun), 1),
        longest_darkness_hours=round(_longest_false_run(sun) * step_h, 1),
        earth_visible_pct=round(100 * sum(earth) / len(earth), 1),
        longest_earth_blackout_hours=round(_longest_false_run(earth) * step_h, 1),
        slope_deg=None,
    )


def fit(m: Metrics, c: Constraints) -> Fit:
    power = [k for k, bad in (("sun_visible_pct", m.sun_visible_pct < c.min_sun_visible_pct),
                              ("longest_darkness_hours", m.longest_darkness_hours > c.max_darkness_hours)) if bad]
    comms = [k for k, bad in (("earth_visible_pct", m.earth_visible_pct < c.min_earth_visible_pct),
                              ("longest_earth_blackout_hours",
                               m.longest_earth_blackout_hours > c.max_earth_blackout_hours)) if bad]
    status = ("neither_met" if power and comms else "power_short" if power
              else "comms_short" if comms else "both_met")
    return Fit(status=status, violations=power + comms)
