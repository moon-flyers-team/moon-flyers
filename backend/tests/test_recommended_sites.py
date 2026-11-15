"""POST /recommended-sites (mock heuristic)."""

from fastapi.testclient import TestClient

from src.main import app
from src.services.catalogue import SITES
from src.services.visibility import FIT_ORDER

client = TestClient(app)

WINDOW = {"window_start_utc": "2027-08-01T00:00:00Z", "window_end_utc": "2027-08-08T00:00:00Z"}


def test_recommendations_are_ranked_catalogue_sites():
    r = client.post("/recommended-sites", json={**WINDOW, "limit": 3})
    assert r.status_code == 200
    data = r.json()
    assert data["method"] == "mock_heuristic"
    recs = data["recommendations"]
    assert [x["rank"] for x in recs] == [1, 2, 3]
    assert all(x["site"]["id"] in {s.id for s in SITES} for x in recs)
    assert all(x["landing_utc"] == "2027-08-01T00:00:00Z" for x in recs)
    statuses = [FIT_ORDER[x["fit"]["status"]] for x in recs]
    assert statuses == sorted(statuses)


def test_far_side_has_no_earth_and_ranks_last():
    recs = client.post("/recommended-sites", json={**WINDOW, "limit": 100}).json()["recommendations"]
    assert len(recs) == len(SITES)
    last = recs[-1]
    assert last["site"]["id"] == "change6_apollo_basin"
    assert last["metrics"]["earth_visible_pct"] == 0
    assert "earth_visible_pct" in last["fit"]["violations"]


def test_constraints_change_the_fit():
    loose = {**WINDOW, "constraints": {"min_sun_visible_pct": 0, "max_darkness_hours": 1000,
                                       "min_earth_visible_pct": 0, "max_earth_blackout_hours": 1000}}
    recs = client.post("/recommended-sites", json={**loose, "limit": 100}).json()["recommendations"]
    assert all(x["fit"]["status"] == "both_met" for x in recs)


def test_invalid_window():
    bad = {"window_start_utc": "2027-08-08T00:00:00Z", "window_end_utc": "2027-08-01T00:00:00Z"}
    assert client.post("/recommended-sites", json=bad).status_code == 422
