"""Published south-polar POIs near a landing site; no ephemeris or synthetic metrics.

The catalogue is bundled and versioned. Failure to load/validate it is an error, never
an invitation to invent locations. See docs/poi-sources.md at the repository root.
"""

import json
import math
from pathlib import Path

from ..schemas import PointOfInterest, Recommendation, RecommendedSitesResponse, Site

MOON_RADIUS_KM = 1737.4
CAP_RADIUS_KM = math.radians(10) * MOON_RADIUS_KM
CATALOGUE_PATH = Path(__file__).resolve().parents[1] / "data/points_of_interest.json"


def intersects_cap(poi: PointOfInterest) -> bool:
    """Include full footprints touching the 80 S cap, not just in-cap centres."""
    return math.radians(poi.latitude_deg + 90) * MOON_RADIUS_KM - poi.boundary.radius_km <= CAP_RADIUS_KM


def load_catalogue(path: Path) -> tuple[str, tuple[PointOfInterest, ...]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    version = data["version"]
    if not isinstance(version, str) or not version:
        raise ValueError("POI catalogue requires a version")
    pois = tuple(PointOfInterest.model_validate(p) for p in data["points_of_interest"])
    if not pois or len({p.id for p in pois}) != len(pois):
        raise ValueError("POI catalogue must be nonempty with unique IDs")
    if not all(intersects_cap(p) for p in pois):
        raise ValueError("POI catalogue contains a footprint outside the south-polar cap")
    return version, pois


CATALOGUE_VERSION, POINTS_OF_INTEREST = load_catalogue(CATALOGUE_PATH)


def distance_km(site: Site, poi: PointOfInterest) -> float:
    """Great-circle distance to published point or approximate circular *area*.

    Inside an approximate footprint the distance is zero, not distance to its rim.
    Haversine handles the pole and longitude seam without projected-map distortions.
    """
    lat1, lat2 = math.radians(site.latitude_deg), math.radians(poi.latitude_deg)
    dlon = math.radians(poi.longitude_deg - site.longitude_deg)
    a = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    centre_distance = 2 * MOON_RADIUS_KM * math.asin(math.sqrt(max(0, min(1, a))))
    return max(0.0, centre_distance - poi.boundary.radius_km)


def recommend(site: Site, radius_km: float) -> RecommendedSitesResponse:
    matches = []
    for poi in POINTS_OF_INTEREST:
        distance = distance_km(site, poi)
        if distance <= radius_km:
            matches.append(Recommendation(poi=poi, distance_km=distance))
    # Distance ordering is a convenience, not a mission-suitability rank. IDs break ties.
    matches.sort(key=lambda row: (row.distance_km, row.poi.id))
    return RecommendedSitesResponse(catalogue_version=CATALOGUE_VERSION, site=site,
                                    radius_km=radius_km, recommendations=matches)
