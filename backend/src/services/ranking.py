"""Ranking landings by headroom: how far the tightest constraint is from failing.

Each constraint gets a margin in [-1, 1], scaled by the room on its side of the threshold:
0 = exactly on the limit, +1 = best possible value, -1 = worst possible value. Order:
  1. fit tier (both_met first),
  2. highest minimum margin (the landing furthest from breaking any requirement),
  3. highest mean margin,
  4. power margin before comms margin (losing power can end a mission; losing comms delays data),
  5. earliest landing.
"""

from ..schemas import Constraints, Fit, LandingWindow, Metrics, WindowMetric
from .visibility import FIT_ORDER


def _ratio(num: float, room: float) -> float:
    if room <= 0:
        return 0.0 if num == 0 else -1.0
    return max(-1.0, min(1.0, num / room))


def _at_least(value: float, minimum: float, best: float) -> float:
    """Margin for `value >= minimum`, where `best` is the highest possible value (e.g. 100 %)."""
    return _ratio(value - minimum, best - minimum if value >= minimum else minimum)


def _at_most(value: float, maximum: float, worst: float) -> float:
    """Margin for `value <= maximum`, where 0 is best and `worst` is the highest possible value."""
    return _ratio(maximum - value, maximum if value <= maximum else worst - maximum)


def margins(m: Metrics, c: Constraints) -> tuple[float, float, float, float]:
    """(sun %, darkness, Earth %, blackout) margins for one landing."""
    stay_h = c.days_on_surface * 24
    return (_at_least(m.sun_visible_pct, c.min_sun_visible_pct, 100),
            _at_most(m.longest_darkness_hours, c.max_darkness_hours, stay_h),
            _at_least(m.earth_visible_pct, c.min_earth_visible_pct, 100),
            _at_most(m.longest_earth_blackout_hours, c.max_earth_blackout_hours, stay_h))


def sort_key(m: Metrics, f: Fit, c: Constraints) -> tuple:
    """Smaller sorts first. The caller appends the landing time as the last tie-break."""
    sun, dark, earth, blackout = margins(m, c)
    power, comms = min(sun, dark), min(earth, blackout)
    return (FIT_ORDER[f.status], -min(power, comms), -(sun + dark + earth + blackout) / 4, -power, -comms)


def rank_landings(candidates: list[WindowMetric], c: Constraints, limit: int) -> list[LandingWindow]:
    ordered = sorted(candidates, key=lambda w: (*sort_key(w.metrics, w.fit, c), w.landing_utc))
    return [LandingWindow(rank=i + 1, landing_utc=w.landing_utc, metrics=w.metrics, fit=w.fit)
            for i, w in enumerate(ordered[:limit])]
