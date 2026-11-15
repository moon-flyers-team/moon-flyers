"""Route between sites. MOCK: straight great-circle segments on a sphere, terrain ignored.

A real planner (slope, shadow, DEM obstacles) replaces `plan_route` later; the response shape stays.
"""

import math

from ..schemas import RouteLeg, RoutePoint, RouteResponse, Site
from .errors import LimitExceededError

MOON_RADIUS_M = 1_737_400.0
MAX_PATH_POINTS = 100_000


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


def _slerp(a: Site, b: Site, angle: float, t: float) -> tuple[float, float]:
    """Point a fraction `t` of the way along the great circle from a to b."""
    u, v = _unit_vector(a.latitude_deg, a.longitude_deg), _unit_vector(b.latitude_deg, b.longitude_deg)
    if angle < 1e-12:
        return a.latitude_deg, a.longitude_deg
    s = math.sin(angle)
    wa, wb = math.sin((1 - t) * angle) / s, math.sin(t * angle) / s
    return _lat_lon(tuple(wa * p + wb * q for p, q in zip(u, v)))


def plan_route(sites: list[Site], step_m: float) -> RouteResponse:
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

    legs = [RouteLeg(from_index=i, to_index=i + 1, distance_m=d) for i, d in enumerate(distances)]
    return RouteResponse(method="straight_line", waypoints=sites, legs=legs,
                         total_distance_m=travelled, path=path)
