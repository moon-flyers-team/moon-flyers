"""POST /route: a detailed path visiting the given sites in order (mock: straight lines)."""

from fastapi import APIRouter

from ..schemas import RouteRequest, RouteResponse
from ..services import catalogue
from ..services.route import plan_route

router = APIRouter(tags=["route"])


@router.post("/route", response_model=RouteResponse)
def route(req: RouteRequest):
    """Waypoints are visited in the given order. `path` has a point at least every `step_m` metres."""
    sites = [catalogue.resolve_site(ref) for ref in req.waypoints]
    return plan_route(sites, req.step_m)
