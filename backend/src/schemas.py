"""Request and response models for the v0 API contract (backend/docs/API.md)."""

from datetime import datetime, timezone
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

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


class LandingWindowsRequest(WindowRequest):
    site: SiteRef
    limit: int = Field(5, ge=1, le=100)


class POISiteRef(BaseModel):
    """Existing landing-site ID or explicit coordinates (name optional)."""
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False, strict=True)

    id: Optional[str] = Field(None, min_length=1)
    name: Optional[str] = Field(None, min_length=1)
    latitude_deg: Optional[float] = Field(None, ge=-90, le=90)
    longitude_deg: Optional[float] = Field(None, ge=-180, le=180)

    @model_validator(mode="after")
    def id_or_coordinates(self):
        if self.id is not None:
            if any(v is not None for v in (self.name, self.latitude_deg, self.longitude_deg)):
                raise ValueError("give id or coordinates, not both")
        elif self.latitude_deg is None or self.longitude_deg is None:
            raise ValueError("latitude_deg and longitude_deg are required without id")
        if self.name is not None and not self.name.strip():
            raise ValueError("name must not be blank")
        return self

    def site_ref(self) -> SiteRef:
        if self.id is not None:
            return SiteRef(id=self.id)
        return SiteRef(name=self.name or "Landing site",
                       latitude_deg=self.latitude_deg, longitude_deg=self.longitude_deg)


class RecommendedSitesRequest(BaseModel):
    """Published south-polar POIs near a landing location, not mission suitability."""
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False, strict=True)

    site: POISiteRef
    radius_km: float = Field(40, gt=0)


class RoverSettings(BaseModel):
    """Terrain-planner limits for one rover. Defaults are illustrative, not a vehicle specification.

    `max_slope_deg` bounds the estimated terrain gradient; the uphill/downhill limits bound
    each directed move and default to it. `climb_weight` and `slope_weight` are route
    preferences in equivalent metres, not energy or risk models. Hard limits apply regardless.
    """
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False, strict=True)

    max_slope_deg: float = Field(15, gt=0, lt=90)
    max_uphill_grade_deg: Optional[float] = Field(None, gt=0, lt=90)
    max_downhill_grade_deg: Optional[float] = Field(None, gt=0, lt=90)
    cell_size_m: float = Field(20, gt=0)
    padding_m: float = Field(1000, gt=0)
    climb_weight: float = Field(0, ge=0)
    slope_weight: float = Field(1, ge=0)
    max_region_radius_m: float = Field(25_000, gt=0, le=50_000)


Planner = Literal["straight_line", "terrain"]


class RouteRequest(BaseModel):
    """Sites to visit, in order. `straight_line` densifies to one point every `step_m` metres;
    `terrain` plans each leg over the mounted LOLA DEM at `rover.cell_size_m` spacing."""
    waypoints: list[SiteRef] = Field(min_length=2, max_length=100)
    step_m: float = Field(100, gt=0)
    planner: Planner = "straight_line"
    rover: RoverSettings = RoverSettings()


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


RouteMethod = Literal["straight_line", "astar_terrain"]

# "not_evaluated" means terrain was never checked (straight_line); the rest are planner outcomes.
RouteStatus = Literal["not_evaluated", "route_found", "start_blocked", "goal_blocked",
                      "no_route", "search_limit_reached"]


class TerrainCandidate(BaseModel):
    """A passable cell near a blocked endpoint. Not a route and not proof of access."""
    grid_cell: list[int]
    latitude_deg: float
    longitude_deg: float
    elevation_m: float
    terrain_slope_deg: float
    offset_m: float


class EndpointCheck(BaseModel):
    """Why a leg endpoint was accepted or blocked, at the planner's resolution."""
    grid_cell: list[int]
    latitude_deg: float
    longitude_deg: float
    elevation_m: Optional[float] = None
    terrain_slope_deg: Optional[float] = None
    max_slope_deg: float
    passable: bool
    blocked_reasons: list[str] = []
    nearby_terrain_candidates: list[TerrainCandidate] = []


class RoutePoint(BaseModel):
    latitude_deg: float
    longitude_deg: float
    distance_m: float  # cumulative from the first waypoint
    elevation_m: Optional[float] = None  # terrain planner samples; null for straight_line
    waypoint_index: Optional[int] = None  # set when this point is one of the requested waypoints


class RouteLeg(BaseModel):
    from_index: int
    to_index: int
    distance_m: Optional[float] = None  # null when this leg could not be planned
    status: RouteStatus = "not_evaluated"
    reason: Optional[str] = None
    # Terrain diagnostics; null for straight_line and for unplanned legs.
    terrain_distance_m: Optional[float] = None
    elevation_gain_m: Optional[float] = None
    elevation_loss_m: Optional[float] = None
    max_terrain_slope_deg: Optional[float] = None
    max_uphill_grade_deg: Optional[float] = None
    max_downhill_grade_deg: Optional[float] = None
    expanded_nodes: Optional[int] = None
    cost: Optional[float] = None  # distance + slope/climb preference charges, not physical
    start_check: Optional[EndpointCheck] = None
    goal_check: Optional[EndpointCheck] = None


class RouteResponse(BaseModel):
    method: RouteMethod
    status: RouteStatus
    reason: Optional[str] = None
    failing_leg: Optional[int] = None  # index into `legs` whose planning stopped the route
    terrain_source: Optional[Literal["lola_dem"]] = None  # null when terrain was not used
    rover: Optional[RoverSettings] = None
    waypoints: list[Site]
    legs: list[RouteLeg]
    total_distance_m: float  # planned prefix only when status != "route_found"
    path: list[RoutePoint]


class POISource(BaseModel):
    title: str
    url: str
    record_id: Optional[str] = None


class POIBoundary(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    kind: Literal["point", "approximate_circle"]
    radius_km: float = Field(0, ge=0)

    @model_validator(mode="after")
    def consistent_radius(self):
        if (self.kind == "point" and self.radius_km != 0
                or self.kind == "approximate_circle" and self.radius_km <= 0):
            raise ValueError("points require zero radius; approximate circles require positive radius")
        return self


class PointOfInterest(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    category: Literal["lander", "rover", "impact", "natural_feature"]
    feature_type: str
    latitude_deg: float = Field(ge=-90, le=90)
    longitude_deg: float = Field(ge=-180, le=180)
    boundary: POIBoundary
    location_uncertainty_km: Optional[float] = Field(None, ge=0)
    notes: str
    sources: list[POISource] = Field(min_length=1)


class Recommendation(BaseModel):
    poi: PointOfInterest
    distance_km: float = Field(ge=0)


class RecommendedSitesResponse(BaseModel):
    method: Literal["catalogue_proximity"] = "catalogue_proximity"
    data_source: Literal["published_catalogue"] = "published_catalogue"
    catalogue_version: str
    site: Site
    radius_km: float
    recommendations: list[Recommendation]
