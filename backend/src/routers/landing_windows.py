"""POST /landing-windows: best landing times table."""

from fastapi import APIRouter

from ..schemas import LandingWindow, LandingWindowsRequest
from ..services import catalogue
from ..services.analysis import SiteSeries
from ..services.ranking import rank_landings

router = APIRouter(tags=["landing-windows"])


@router.post("/landing-windows", response_model=list[LandingWindow])
def landing_windows(req: LandingWindowsRequest):
    """Best landing times in the window, ranked by headroom on the tightest constraint."""
    site = catalogue.resolve_site(req.site)
    s = SiteSeries(site, req.window_start_utc, req.window_end_utc, req.constraints, req.timestep_seconds)
    return rank_landings(s.window_metrics(req.candidate_step_hours), req.constraints, req.limit)
