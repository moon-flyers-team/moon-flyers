"""POST /compare: comparison table and timeline bars."""

from fastapi import APIRouter

from ..schemas import CompareRequest, CompareResult
from ..services import catalogue
from ..services.analysis import SiteSeries

router = APIRouter(tags=["compare"])


@router.post("/compare", response_model=list[CompareResult])
def compare(req: CompareRequest):
    """Per site: metrics + fit for every landing candidate in the window, and timeline bars."""
    results = []
    for ref in req.sites:
        site = catalogue.resolve_site(ref)
        s = SiteSeries(site, req.window_start_utc, req.window_end_utc, req.constraints, req.timestep_seconds)
        results.append(CompareResult(site=site, window_metrics=s.window_metrics(req.candidate_step_hours),
                                     timeline=s.timeline()))
    return results
