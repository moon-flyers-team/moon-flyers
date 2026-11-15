"""POST /recommended-sites: catalogue sites ranked for the app's window and constraints (mock)."""

from fastapi import APIRouter

from ..schemas import RecommendedSitesRequest, RecommendedSitesResponse
from ..services.recommendation import recommend

router = APIRouter(tags=["recommended-sites"])


@router.post("/recommended-sites", response_model=RecommendedSitesResponse)
def recommended_sites(req: RecommendedSitesRequest):
    """Sorted by fit, then sunlight %, then Earth contact %, for a landing at window_start."""
    return recommend(req.window_start_utc, req.constraints, req.limit)
