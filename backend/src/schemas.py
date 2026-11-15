"""Request and response models for the v0 API contract (backend/docs/API.md)."""

from datetime import datetime, timezone
from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator, model_validator

FitStatus = Literal["both_met", "power_short", "comms_short", "neither_met"]


def as_utc(value: datetime) -> datetime:
    """Treat naive datetimes as UTC and normalise aware ones to UTC."""
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


# ---------- shared request blocks ----------

class Constraints(BaseModel):
    days_on_surface: float = Field(14, gt=0)
    horizon_clearance_deg: float = Field(0.3, ge=0)
    min_sun_visible_pct: float = Field(60, ge=0, le=100)
    max_darkness_hours: float = Field(96, ge=0)
    min_earth_visible_pct: float = Field(45, ge=0, le=100)
    max_earth_blackout_hours: float = Field(240, ge=0)
    max_slope_deg: float = Field(8, ge=0)


class SiteRef(BaseModel):
    """A predefined site by `id`, or a custom site by name + coordinates."""
    id: Optional[str] = None
    name: Optional[str] = None
    latitude_deg: Optional[float] = Field(None, ge=-90, le=90)
    longitude_deg: Optional[float] = Field(None, ge=-180, le=180)

    @model_validator(mode="after")
    def id_or_coordinates(self):
        if self.id is None and None in (self.name, self.latitude_deg, self.longitude_deg):
            raise ValueError("give either `id`, or `name`, `latitude_deg` and `longitude_deg`")
        return self


class WindowRequest(BaseModel):
    window_start_utc: datetime
    window_end_utc: datetime
    constraints: Constraints = Constraints()
    candidate_step_hours: float = Field(6, gt=0)
    timestep_seconds: int = Field(3600, gt=0)

    @field_validator("window_start_utc", "window_end_utc")
    @classmethod
    def utc(cls, v: datetime) -> datetime:
        return as_utc(v)

    @model_validator(mode="after")
    def ordered(self):
        if self.window_end_utc <= self.window_start_utc:
            raise ValueError("window_end_utc must be after window_start_utc")
        return self


class SitesQuery(Constraints):
    """Query parameters of GET /sites. Inherits every Constraints field and its default.

    No site fields → catalogue. A site (`site_id`, or `name` + coordinates) → analysis, which
    then needs the window.
    """
    site_id: Optional[str] = None
    name: Optional[str] = None
    latitude_deg: Optional[float] = Field(None, ge=-90, le=90)
    longitude_deg: Optional[float] = Field(None, ge=-180, le=180)
    window_start_utc: Optional[datetime] = None
    window_end_utc: Optional[datetime] = None
    timestep_seconds: int = Field(3600, gt=0)
    sun_visibility: bool = True
    earth_visibility: bool = True

    @field_validator("window_start_utc", "window_end_utc")
    @classmethod
    def utc(cls, v: Optional[datetime]) -> Optional[datetime]:
        return None if v is None else as_utc(v)

    @property
    def wants_analysis(self) -> bool:
        return any(v is not None for v in (self.site_id, self.name, self.latitude_deg, self.longitude_deg))

    @model_validator(mode="after")
    def analysis_needs_site_and_window(self):
        if not self.wants_analysis:
            return self
        if self.site_id is None and None in (self.name, self.latitude_deg, self.longitude_deg):
            raise ValueError("give either `site_id`, or `name`, `latitude_deg` and `longitude_deg`")
        if self.window_start_utc is None or self.window_end_utc is None:
            raise ValueError("window_start_utc and window_end_utc are required for analysis")
        if self.window_end_utc <= self.window_start_utc:
            raise ValueError("window_end_utc must be after window_start_utc")
        return self

    def site_ref(self) -> "SiteRef":
        return SiteRef(id=self.site_id, name=self.name,
                       latitude_deg=self.latitude_deg, longitude_deg=self.longitude_deg)

    def constraints(self) -> Constraints:
        return Constraints(**self.model_dump(include=set(Constraints.model_fields)))


class CompareRequest(WindowRequest):
    sites: list[SiteRef] = Field(min_length=1)


class RecommendedSitesRequest(WindowRequest):
    """The app's current window and constraints; recommends from the catalogue."""
    limit: int = Field(5, ge=1, le=100)


class RouteRequest(BaseModel):
    """Sites to visit, in order. The route is densified to one point every `step_m` metres."""
    waypoints: list[SiteRef] = Field(min_length=2, max_length=100)
    step_m: float = Field(100, gt=0)


# ---------- shared response blocks ----------

class Site(BaseModel):
    id: Optional[str]
    name: str
    group: str
    latitude_deg: float
    longitude_deg: float
    notes: str = ""


class Metrics(BaseModel):
    sun_visible_pct: float
    longest_darkness_hours: float
    earth_visible_pct: float
    longest_earth_blackout_hours: float
    slope_deg: Optional[float] = None


class Fit(BaseModel):
    status: FitStatus
    violations: list[str]


class Interval(BaseModel):
    start_utc: str
    end_utc: str


class Windows(BaseModel):
    sun: list[Interval]
    earth: list[Interval]
    eclipse: list[Interval] = []  # Earth covering the Sun, while Earth is visible


class TimeseriesPoint(BaseModel):
    time_utc: str
    sun_azimuth_deg: Optional[float]
    sun_elevation_deg: Optional[float]
    sun_visible: Optional[bool]
    earth_azimuth_deg: Optional[float]
    earth_elevation_deg: Optional[float]
    earth_visible: Optional[bool]


class Horizon(BaseModel):
    horizon_azimuth_deg: list[float]
    horizon_elevation_deg: list[float]


class Analysis(BaseModel):
    timeseries: list[TimeseriesPoint]
    horizon: Horizon
    windows: Windows
    metrics: Metrics
    fit: Fit


class SiteWithAnalysis(Site):
    analysis: Analysis


class WindowMetric(BaseModel):
    landing_utc: str
    metrics: Metrics
    fit: Fit


class CompareResult(BaseModel):
    site: Site
    window_metrics: list[WindowMetric]
    timeline: Windows


RouteMethod = Literal["straight_line"]


class RoutePoint(BaseModel):
    latitude_deg: float
    longitude_deg: float
    distance_m: float  # cumulative from the first waypoint
    waypoint_index: Optional[int] = None  # set when this point is one of the requested waypoints


class RouteLeg(BaseModel):
    from_index: int
    to_index: int
    distance_m: float


class RouteResponse(BaseModel):
    method: RouteMethod  # "straight_line" = mock: great-circle segments, terrain ignored
    waypoints: list[Site]
    legs: list[RouteLeg]
    total_distance_m: float
    path: list[RoutePoint]


class Recommendation(BaseModel):
    rank: int
    site: Site
    landing_utc: str
    metrics: Metrics
    fit: Fit


class RecommendedSitesResponse(BaseModel):
    method: Literal["mock_heuristic"]  # mock: estimates from latitude/longitude, no ephemeris or terrain
    recommendations: list[Recommendation]
