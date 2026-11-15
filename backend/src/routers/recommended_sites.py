"""POST /recommended-sites: published POIs within surface distance of a landing site."""

from fastapi import APIRouter, Response

from ..schemas import RecommendedSitesRequest, RecommendedSitesResponse
from ..services.catalogue import resolve_site
from ..services.recommendation import recommend

router = APIRouter(tags=["recommended-sites"])


@router.post("/recommended-sites", response_model=RecommendedSitesResponse)
def recommended_sites(req: RecommendedSitesRequest, response: Response):
    """Nearby published POIs, nearest first; no suitability score or terrain reachability."""
    response.headers["X-Moon-Flyers-Data-Source"] = "catalogue"
    return recommend(resolve_site(req.site.site_ref()), req.radius_km)
