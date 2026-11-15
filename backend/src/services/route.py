"""Route between sites, as ordered legs.

`planner="straight_line"` (default) interpolates great-circle segments and ignores terrain.
`planner="terrain"` plans each leg with the bounded A* rover planner over the mounted LOLA
DEMs and fails clearly when no dataset is mounted. Terrain results are suggested candidate
routes at the stated resolution, not validated driving instructions.
"""

import logging
import math
import os

from ..rover_path import plan_rover_route
from ..schemas import (EndpointCheck, RoverSettings, RouteLeg, RoutePoint, RouteRequest, RouteResponse,
                       Site, TerrainCandidate)
from .errors import InvalidInputError, LimitExceededError, TerrainUnavailableError
from .horizon import open_dem

log = logging.getLogger(__name__)

MOON_RADIUS_M = 1_737_400.0
MAX_PATH_POINTS = 100_000
# Total terrain cells sampled across all legs of one request. A leg is planned whole, so the
# actual count can overshoot by at most one leg; this bounds a multi-stop route's runtime.
MAX_TERRAIN_CELLS = 1_000_000
# Detour space for the one automatic retry of a leg that found no route in the requested corridor.
WIDE_PADDING_M = 5_000.0


def _unit_vector(lat_deg: float, lon_deg: float) -> tuple[float, float, float]:
    lat, lon = math.radians(lat_deg), math.radians(lon_deg)
    return (math.cos(lat) * math.cos(lon), math.cos(lat) * math.sin(lon), math.sin(lat))


def _lat_lon(v: tuple[float, float, float]) -> tuple[float, float]:
    x, y, z = v
    lat = math.degrees(math.atan2(z, math.hypot(x, y)))
    lon = math.degrees(math.atan2(y, x)) if math.hypot(x, y) > 1e-15 else 0.0
    return lat, lon


def central_angle(a: Site, b: Site) -> float:
    """Angle (radians) between two sites seen from the Moon's centre."""
    u, v = _unit_vector(a.latitude_deg, a.longitude_deg), _unit_vector(b.latitude_deg, b.longitude_deg)
    cross = (u[1] * v[2] - u[2] * v[1], u[2] * v[0] - u[0] * v[2], u[0] * v[1] - u[1] * v[0])
    dot = u[0] * v[0] + u[1] * v[1] + u[2] * v[2]
    return math.atan2(math.sqrt(sum(c * c for c in cross)), dot)


def _arc_m(a: RoutePoint, b: RoutePoint) -> float:
    """Reference-sphere distance between consecutive terrain points, as the planner reports it."""
    chord = math.dist(_unit_vector(a.latitude_deg, a.longitude_deg),
                      _unit_vector(b.latitude_deg, b.longitude_deg))
    return 2 * MOON_RADIUS_M * math.asin(min(1.0, chord / 2))


def _slerp(a: Site, b: Site, angle: float, t: float) -> tuple[float, float]:
    """Point a fraction `t` of the way along the great circle from a to b."""
    u, v = _unit_vector(a.latitude_deg, a.longitude_deg), _unit_vector(b.latitude_deg, b.longitude_deg)
    if angle < 1e-12:
        return a.latitude_deg, a.longitude_deg
    s = math.sin(angle)
    wa, wb = math.sin((1 - t) * angle) / s, math.sin(t * angle) / s
    return _lat_lon(tuple(wa * p + wb * q for p, q in zip(u, v)))


def _straight_line(sites: list[Site], step_m: float) -> RouteResponse:
    angles = [central_angle(a, b) for a, b in zip(sites, sites[1:])]
    distances = [ang * MOON_RADIUS_M for ang in angles]
    steps = [max(1, math.ceil(d / step_m)) for d in distances]
    if sum(steps) + 1 > MAX_PATH_POINTS:
        raise LimitExceededError(f"route needs {sum(steps) + 1} points (max {MAX_PATH_POINTS}); raise step_m")

    path = [RoutePoint(latitude_deg=sites[0].latitude_deg, longitude_deg=sites[0].longitude_deg,
                       distance_m=0.0, waypoint_index=0)]
    travelled = 0.0
    for i, (a, b) in enumerate(zip(sites, sites[1:])):
        for k in range(1, steps[i] + 1):
            t = k / steps[i]
            is_end = k == steps[i]
            lat, lon = (b.latitude_deg, b.longitude_deg) if is_end else _slerp(a, b, angles[i], t)
            path.append(RoutePoint(latitude_deg=lat, longitude_deg=lon,
                                   distance_m=travelled + t * distances[i],
                                   waypoint_index=i + 1 if is_end else None))
        travelled += distances[i]

    legs = [RouteLeg(from_index=i, to_index=i + 1, distance_m=d, status="not_evaluated")
            for i, d in enumerate(distances)]
    return RouteResponse(method="straight_line", status="not_evaluated",
                         reason="straight-line legs ignore terrain, slope and shadow", waypoints=sites,
                         legs=legs, total_distance_m=travelled, path=path)


def _endpoint_check(raw: dict | None) -> EndpointCheck | None:
    """Wrap the planner's diagnostic dict; values are already JSON-safe."""
    if raw is None:
        return None
    return EndpointCheck(
        grid_cell=raw["grid_cell"], latitude_deg=raw["latitude_deg"], longitude_deg=raw["longitude_deg"],
        elevation_m=raw["elevation_m"], terrain_slope_deg=raw["terrain_slope_deg"],
        max_slope_deg=raw["max_slope_deg"], passable=raw["passable"],
        blocked_reasons=raw["blocked_reasons"],
        nearby_terrain_candidates=[TerrainCandidate(**c) for c in raw["nearby_terrain_candidates"]])


def _region_cells(distance_m: float, cell_size_m: float, padding_m: float) -> int:
    """Grid cells the planner samples for one leg (same arithmetic as `plan_rover_route`)."""
    pad = max(1, math.ceil(padding_m / cell_size_m))
    segments = max(1, math.ceil(distance_m / cell_size_m))
    return (2 * pad + 1) * (segments + 2 * pad + 1)


def _plan_leg(dem, a: Site, b: Site, rover: RoverSettings, padding_m: float) -> dict:
    return plan_rover_route(
        dem, (a.latitude_deg, a.longitude_deg), (b.latitude_deg, b.longitude_deg),
        max_slope_deg=rover.max_slope_deg, cell_size_m=rover.cell_size_m,
        padding_m=padding_m, max_uphill_grade_deg=rover.max_uphill_grade_deg,
        max_downhill_grade_deg=rover.max_downhill_grade_deg,
        climb_weight=rover.climb_weight, slope_weight=rover.slope_weight,
        max_region_radius_m=rover.max_region_radius_m)


def _placeholder_points(a: Site, b: Site, step_m: float) -> list[RoutePoint]:
    """Straight great-circle filler for a leg without a terrain route; never a drivable path."""
    angle = central_angle(a, b)
    steps = max(1, math.ceil(angle * MOON_RADIUS_M / step_m))
    points = []
    for k in range(steps + 1):
        lat, lon = ((b.latitude_deg, b.longitude_deg) if k == steps
                    else _slerp(a, b, angle, k / steps))
        points.append(RoutePoint(latitude_deg=lat, longitude_deg=lon, distance_m=0.0, placeholder=True))
    return points


def _terrain(sites: list[Site], rover: RoverSettings) -> RouteResponse:
    """Plan every leg; a leg without a terrain route keeps its status and is drawn as a
    flagged straight placeholder so later legs are still planned and shown."""
    directory = os.environ.get("LOLA_DEM_DIR")
    if not directory:
        raise TerrainUnavailableError(
            "terrain routing needs a verified LOLA DEM dataset; set LOLA_DEM_DIR "
            "(see deploy/README.md) or request planner=straight_line")
    dem = open_dem(directory)

    legs: list[RouteLeg] = []
    path: list[RoutePoint] = []
    planned_distance = 0.0
    sampled_cells = 0
    failed: list[int] = []
    reasons: list[str] = []

    for i, (a, b) in enumerate(zip(sites, sites[1:])):
        if sampled_cells > MAX_TERRAIN_CELLS:
            raise LimitExceededError(
                f"route already samples {sampled_cells} terrain cells (max {MAX_TERRAIN_CELLS}); "
                "split the route into fewer stops per request or increase cell_size_m")
        padding = rover.padding_m
        try:
            result = _plan_leg(dem, a, b, rover, padding)
        except ValueError as exc:
            raise InvalidInputError(f"leg {i} ({a.name} -> {b.name}): {exc}") from exc
        sampled_cells += result["search"]["grid_shape"][0] * result["search"]["grid_shape"][1]

        # A narrow corridor often has no way around a crater or down a slope. Retry once with
        # more detour space when it fits the region radius and the request's cell budget.
        distance = central_angle(a, b) * MOON_RADIUS_M
        if result["status"] == "no_route" and WIDE_PADDING_M > padding:
            wide_cells = _region_cells(distance, rover.cell_size_m, WIDE_PADDING_M)
            if sampled_cells + wide_cells <= MAX_TERRAIN_CELLS:
                try:
                    wide = _plan_leg(dem, a, b, rover, WIDE_PADDING_M)
                except ValueError:
                    wide = None  # region radius or per-leg cell limit: keep the narrow result
                if wide is not None:
                    sampled_cells += wide_cells
                    result, padding = wide, WIDE_PADDING_M

        found = result["status"] == "route_found"
        leg = RouteLeg(from_index=i, to_index=i + 1, status=result["status"], reason=result["reason"],
                       terrain_distance_m=result["terrain_distance_m"],
                       elevation_gain_m=result["elevation_gain_m"],
                       elevation_loss_m=result["elevation_loss_m"],
                       max_terrain_slope_deg=result["max_terrain_slope_deg"],
                       max_uphill_grade_deg=result["max_uphill_grade_deg"],
                       max_downhill_grade_deg=result["max_downhill_grade_deg"],
                       expanded_nodes=result["expanded_nodes"], cost=result["cost"],
                       padding_m=result["search"]["padding_m"],
                       start_check=_endpoint_check(result["endpoint_checks"]["start"]),
                       goal_check=_endpoint_check(result["endpoint_checks"]["goal"]))
        legs.append(leg)
        if found:
            points = [RoutePoint(latitude_deg=p["latitude_deg"], longitude_deg=p["longitude_deg"],
                                 distance_m=0.0, elevation_m=p["elevation_m"]) for p in result["path"]]
        else:
            failed.append(i)
            reasons.append(f"leg {i} ({a.name} -> {b.name}): {result['reason']}")
            points = _placeholder_points(a, b, rover.cell_size_m)

        end = points[-1]
        if path:
            # Legs share the waypoint exactly; the junction already carries `waypoint_index == i`.
            points = points[1:]
        else:
            points[0].waypoint_index = 0
        travelled = path[-1].distance_m if path else 0.0
        leg_distance = 0.0
        for point in points:
            if path:
                leg_distance += _arc_m(path[-1], point)
            point.distance_m = travelled + leg_distance
            path.append(point)
        # A zero-length leg (repeated waypoint) keeps the earlier marker instead of overwriting it.
        end.waypoint_index = i + 1 if end.waypoint_index is None else end.waypoint_index
        if found:
            leg.distance_m = leg_distance
            planned_distance += leg_distance

    status = legs[failed[0]].status if failed else "route_found"
    return RouteResponse(method="astar_terrain", status=status, reason="; ".join(reasons) or None,
                         failing_leg=failed[0] if failed else None, failed_legs=failed,
                         terrain_source="lola_dem", rover=rover, waypoints=sites, legs=legs,
                         total_distance_m=planned_distance, path=path)


def plan_route(sites: list[Site], req: RouteRequest) -> RouteResponse:
    """Plan the legs in the given waypoint order with the requested planner."""
    response = _terrain(sites, req.rover) if req.planner == "terrain" else _straight_line(sites, req.step_m)
    if len(response.path) > MAX_PATH_POINTS:
        raise LimitExceededError(
            f"route needs {len(response.path)} points (max {MAX_PATH_POINTS}); increase cell_size_m")
    return response
