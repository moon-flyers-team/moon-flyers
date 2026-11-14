"""Ranking landing times: by fit, then sunlight %, then Earth contact %."""

from ..schemas import LandingWindow, WindowMetric
from .visibility import FIT_ORDER


def rank_landings(candidates: list[WindowMetric], limit: int) -> list[LandingWindow]:
    ordered = sorted(candidates, key=lambda w: (FIT_ORDER[w.fit.status], -w.metrics.sun_visible_pct,
                                                -w.metrics.earth_visible_pct, w.landing_utc))
    return [LandingWindow(rank=i + 1, landing_utc=w.landing_utc, metrics=w.metrics, fit=w.fit)
            for i, w in enumerate(ordered[:limit])]
