"""Per-site analysis: one az/el series over [window_start, window_end + days], sliced per landing."""

import math
from datetime import datetime, timedelta

from ..schemas import Analysis, Constraints, Fit, Horizon, Metrics, Site, TimeseriesPoint, WindowMetric, Windows
from . import ephemeris, horizon, visibility
from .errors import LimitExceededError

MAX_CANDIDATES = 2_000
MAX_MISSION_POINTS = 1_000_000


class SiteSeries:
    def __init__(self, site: Site, start: datetime, end: datetime, c: Constraints, step_s: int):
        self.step_s = step_s
        self.c = c
        self.start = start
        self.end = end
        self.horizon = horizon.for_site(site)
        self.stay_samples = max(1, math.ceil(c.days_on_surface * 86400 / step_s))
        self.data = ephemeris.generate(site, start, end + timedelta(days=c.days_on_surface), step_s)
        d = self.data
        self.sun = visibility.visible_flags(d["sun_az"], d["sun_el"], visibility.SUN_RADIUS_DEG,
                                            c.horizon_clearance_deg, self.horizon)
        self.earth = visibility.visible_flags(d["earth_az"], d["earth_el"], visibility.EARTH_RADIUS_DEG,
                                              c.horizon_clearance_deg, self.horizon)

    def stay(self, landing: datetime) -> tuple[Metrics, Fit]:
        """Metrics and fit for a mission landing at `landing` and staying `days_on_surface`."""
        i = round((landing - self.start).total_seconds() / self.step_s)
        j = i + self.stay_samples
        m = visibility.metrics(self.sun[i:j], self.earth[i:j], self.step_s)
        return m, visibility.fit(m, self.c)

    def timeline(self) -> Windows:
        t = self.data["times"]
        return Windows(sun=visibility.intervals(t, self.sun, self.step_s),
                       earth=visibility.intervals(t, self.earth, self.step_s))

    def timeseries(self, sun_on: bool = True, earth_on: bool = True) -> list[TimeseriesPoint]:
        """Every sample; Sun or Earth fields are null when that body is switched off."""
        d = self.data
        return [
            TimeseriesPoint(
                time_utc=visibility.iso(t),
                sun_azimuth_deg=round(d["sun_az"][i], 3) if sun_on else None,
                sun_elevation_deg=round(d["sun_el"][i], 3) if sun_on else None,
                sun_visible=self.sun[i] if sun_on else None,
                earth_azimuth_deg=round(d["earth_az"][i], 3) if earth_on else None,
                earth_elevation_deg=round(d["earth_el"][i], 3) if earth_on else None,
                earth_visible=self.earth[i] if earth_on else None,
            )
            for i, t in enumerate(d["times"])
        ]

    def analysis(self, sun_on: bool = True, earth_on: bool = True) -> Analysis:
        """Full analysis for GET /sites. Metrics and fit are for a landing at window_start."""
        m, f = self.stay(self.start)
        return Analysis(timeseries=self.timeseries(sun_on, earth_on),
                        horizon=Horizon(**horizon.profile(self.horizon)),
                        windows=self.timeline(), metrics=m, fit=f)

    def window_metrics(self, candidate_step_hours: float) -> list[WindowMetric]:
        """Metrics and fit for every landing candidate in the window."""
        out = []
        for landing in landing_candidates(self.start, self.end, candidate_step_hours, self.stay_samples):
            m, f = self.stay(landing)
            out.append(WindowMetric(landing_utc=visibility.iso(landing), metrics=m, fit=f))
        return out


def landing_candidates(start: datetime, end: datetime, step_h: float, stay_samples: int) -> list[datetime]:
    n = int((end - start).total_seconds() // (step_h * 3600)) + 1
    if n > MAX_CANDIDATES:
        raise LimitExceededError(f"window has {n} landing candidates; the limit is {MAX_CANDIDATES}")
    if n * stay_samples > MAX_MISSION_POINTS:
        raise LimitExceededError(f"search needs {n * stay_samples} mission samples; the limit is {MAX_MISSION_POINTS}")
    return [start + timedelta(hours=k * step_h) for k in range(n)]
