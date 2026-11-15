"""POST /route: ordered legs between the given sites.

`planner="straight_line"` (default) is the mock interpolation; `planner="terrain"` uses the
bounded A* rover planner over the mounted LOLA DEMs and needs `LOLA_DEM_DIR`.
"""

from fastapi import APIRouter

from ..schemas import RouteRequest, RouteResponse
from ..services import catalogue
from ..services.route import plan_route

router = APIRouter(tags=["route"])


@router.post("/route", response_model=RouteResponse)
def route(req: RouteRequest):
    """Waypoints are visited in the given order. Straight-line legs are densified at least every
    `step_m` metres; terrain legs return one point per planned grid cell."""
    sites = [catalogue.resolve_site(ref) for ref in req.waypoints]
    return plan_route(sites, req)
