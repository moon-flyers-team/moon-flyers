"""Recommended landing sites. MOCK: metrics estimated from site geometry, no ephemeris or terrain.

The estimates are rough but point the right way: polar sites get more sunlight, near-side sites
more Earth contact, far-side sites none. The real version would rank `SiteSeries.window_metrics()`
for every catalogue site; the response shape stays.
"""

import math
from datetime import datetime

from ..schemas import Constraints, Metrics, Recommendation, RecommendedSitesResponse, Site
from .catalogue import SITES
from .visibility import FIT_ORDER, fit, iso

SYNODIC_HOURS = 29.53 * 24
DRACONIC_YEAR_DAYS = 346.62  # period of the Sun's ±1.5° swing in the lunar sky (polar "seasons")
LIBRATION_DEG = 7.0


def _clamp(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))


def estimate_metrics(site: Site, landing: datetime, c: Constraints) -> Metrics:
    stay_h = c.days_on_surface * 24
    lat, lon = math.radians(site.latitude_deg), math.radians(site.longitude_deg)

    # Sun: half a lunation dark at low latitudes; near the pole much more light, varying with season.
    polar = _clamp((abs(site.latitude_deg) - 60) / 30)
    season = math.sin(2 * math.pi * landing.timetuple().tm_yday / DRACONIC_YEAR_DAYS)
    sun_pct = 100 * _clamp(0.5 + polar * (0.38 + 0.08 * season))
    darkness_h = min(stay_h, (1 - sun_pct / 100) * SYNODIC_HOURS * (1 - 0.6 * polar))

    # Earth: its mean elevation is asin(cos(lat)cos(lon)); libration swings it about ±7°.
    earth_el = math.degrees(math.asin(math.cos(lat) * math.cos(lon)))
    earth_pct = 100 * _clamp((earth_el + LIBRATION_DEG) / (2 * LIBRATION_DEG))
    blackout_h = min(stay_h, (1 - earth_pct / 100) * 27.32 * 24)

    return Metrics(sun_visible_pct=round(sun_pct, 1), longest_darkness_hours=round(darkness_h, 1),
                   earth_visible_pct=round(earth_pct, 1), longest_earth_blackout_hours=round(blackout_h, 1))


def recommend(window_start: datetime, c: Constraints, limit: int) -> RecommendedSitesResponse:
    scored = []
    for site in SITES:
        m = estimate_metrics(site, window_start, c)
        scored.append((site, m, fit(m, c)))
    scored.sort(key=lambda x: (FIT_ORDER[x[2].status], -x[1].sun_visible_pct, -x[1].earth_visible_pct))
    return RecommendedSitesResponse(method="mock_heuristic", recommendations=[
        Recommendation(rank=i + 1, site=site, landing_utc=iso(window_start), metrics=m, fit=f)
        for i, (site, m, f) in enumerate(scored[:limit])])
