"""GET /sites: the catalogue, or one site with its analysis."""

from typing import Annotated, Union

from fastapi import APIRouter, Query

from ..schemas import Site, SitesQuery, SiteWithAnalysis
from ..services import catalogue
from ..services.analysis import SiteSeries

router = APIRouter(tags=["sites"])


@router.get("/sites", response_model=Union[SiteWithAnalysis, list[Site]])
def get_sites(q: Annotated[SitesQuery, Query()]):
    """No site parameters: the catalogue. With a site and a window: that site plus `analysis`.

    `timeseries` and `windows` span window_start → window_end + days_on_surface.
    `metrics` and `fit` are for a landing at window_start (per-landing values come from /compare).
    """
    if not q.wants_analysis:
        return catalogue.SITES
    site = catalogue.resolve_site(q.site_ref())
    series = SiteSeries(site, q.window_start_utc, q.window_end_utc, q.constraints(), q.timestep_seconds)
    return SiteWithAnalysis(**site.model_dump(), analysis=series.analysis(q.sun_visibility, q.earth_visibility))
