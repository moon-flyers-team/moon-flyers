"""POST /route and /route/stops: ordered legs between sites, plus stop preflight.

`planner="straight_line"` (default) is the mock interpolation; `planner="terrain"` uses the
bounded A* rover planner over the mounted LOLA DEMs and needs `LOLA_DEM_DIR`.
"""

from fastapi import APIRouter

from ..schemas import RouteRequest, RouteResponse, RouteStopsRequest, RouteStopsResponse
from ..services import catalogue
from ..services.route import plan_route, plan_stops

router = APIRouter(tags=["route"])


@router.post("/route", response_model=RouteResponse)
def route(req: RouteRequest):
    """Waypoints are visited in the given order. Straight-line legs are densified at least every
    `step_m` metres; terrain legs return one point per planned grid cell."""
    sites = [catalogue.resolve_site(ref) for ref in req.waypoints]
    return plan_route(sites, req)


@router.post("/route/stops", response_model=RouteStopsResponse)
def route_stops(req: RouteStopsRequest):
    """Terrain usability of each stop, without planning a leg.

    Lets the frontend say "this location is not practical" before a route is calculated. Returns
    503 without a mounted dataset, like `POST /route` with `planner: "terrain"`.
    """
    return plan_stops([catalogue.resolve_site(ref) for ref in req.waypoints], req)
