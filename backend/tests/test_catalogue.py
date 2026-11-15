"""Default exploration references: real source coordinates and useful POI coverage."""

import pytest
from fastapi.testclient import TestClient

from src.main import app
from src.services.catalogue import SITES, SITES_BY_ID, resolve_site
from src.schemas import SiteRef
from src.services.recommendation import POINTS_OF_INTEREST, distance_km

# Explicit source mapping: default landing-site identities are distinct from POI IDs.
ADDED_SOURCES = {
    "im2_mons_mouton": "im2-athena",
    "nobile_reference": "iau-4321",
    "faustini_reference": "iau-1919",
    "wiechert_reference": "iau-6541",
    "demonax_b_reference": "iau-8719",
    "schomberger_l_reference": "iau-12948",
    "drygalski_p_reference": "iau-8838",
    "cabeus_reference": "iau-953",
    "newton_b_reference": "iau-11611",
    "idelson_reference": "iau-2650",
    "cabeus_a_reference": "iau-8057",
    "demonax_c_reference": "iau-8720",
    "idelson_l_reference": "iau-10114",
    "scott_e_reference": "iau-13015",
}
LEGACY_IDS = [
    "shackleton_rim", "connecting_ridge", "de_gerlache_rim", "malapert_massif", "im1_malapert_a",
    "chandrayaan3_shiv_shakti", "change6_apollo_basin",
]
client = TestClient(app)


@pytest.mark.parametrize("site_id,poi_id", ADDED_SOURCES.items())
def test_added_defaults_use_published_in_cap_coordinates(site_id, poi_id):
    site = resolve_site(SiteRef(id=site_id))
    source = next(p for p in POINTS_OF_INTEREST if p.id == poi_id)
    assert site.latitude_deg == pytest.approx(source.latitude_deg, abs=1e-10)
    assert site.longitude_deg == pytest.approx(source.longitude_deg, abs=1e-10)
    assert -90 <= site.latitude_deg <= -80
    assert "https://" in site.notes
    if site_id.endswith("_reference"):
        assert "not vetted" in site.group
        assert "reference" in site.name
        assert "landing suitability unassessed" in site.notes
    response = client.post("/recommended-sites", json={"site": {"id": site_id}})
    assert response.status_code == 200
    match = next(r for r in response.json()["recommendations"] if r["poi"]["id"] == poi_id)
    assert match["distance_km"] == pytest.approx(0, abs=1e-10)


def test_catalogue_preserves_old_sites_and_public_shape():
    assert [s.id for s in SITES[:7]] == LEGACY_IDS
    assert len(SITES) == len(SITES_BY_ID) == 21
    assert SITES_BY_ID["shackleton_rim"].latitude_deg == -89.667
    assert SITES_BY_ID["chandrayaan3_shiv_shakti"].latitude_deg == -69.373
    response = client.get("/sites")
    assert response.status_code == 200
    assert {s["id"] for s in response.json()} == set(SITES_BY_ID)
    assert all(set(s) == {"id", "name", "group", "latitude_deg", "longitude_deg", "notes"}
               for s in response.json())


def test_defaults_cover_at_least_eighty_percent_of_published_pois():
    covered = {p.id for p in POINTS_OF_INTEREST if any(distance_km(s, p) <= 40 for s in SITES)}
    assert len(covered) / len(POINTS_OF_INTEREST) >= 0.8
    assert len(covered) == 49  # Documented snapshot measurement; update deliberately on source refresh.
    # Point-like mission hardware must be genuinely close, not only inside a broad crater footprint.
    assert {"im1-odysseus", "im2-athena", "trek-impact-1", "trek-impact-3", "trek-impact-4"} <= covered
    # Check the public endpoint agrees with the geometric coverage calculation, using its default radius.
    returned = set()
    for site in SITES:
        response = client.post("/recommended-sites", json={"site": {"id": site.id}})
        assert response.status_code == 200
        returned.update(r["poi"]["id"] for r in response.json()["recommendations"])
    assert returned == covered


def test_new_reference_can_use_existing_site_analysis_endpoint():
    response = client.get("/sites", params={
        "site_id": "cabeus_reference", "window_start_utc": "2027-08-01T00:00:00Z",
        "window_end_utc": "2027-08-02T00:00:00Z", "days_on_surface": 1,
    })
    assert response.status_code == 200
    assert response.json()["id"] == "cabeus_reference"
    assert response.json()["analysis"]["timeseries"]
