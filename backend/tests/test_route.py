"""POST /route (mock: straight great-circle lines)."""

import math

from fastapi.testclient import TestClient

from src.main import app
from src.services.route import MOON_RADIUS_M

client = TestClient(app)


def test_route_through_catalogue_and_custom_sites():
    body = {"waypoints": [{"id": "shackleton_rim"}, {"id": "connecting_ridge"},
                          {"name": "Spot", "latitude_deg": -89.0, "longitude_deg": 10.0}],
            "step_m": 500}
    r = client.post("/route", json=body)
    assert r.status_code == 200
    data = r.json()
    assert data["method"] == "straight_line"
    assert [w["id"] for w in data["waypoints"]] == ["shackleton_rim", "connecting_ridge", None]
    assert len(data["legs"]) == 2
    assert math.isclose(data["total_distance_m"], sum(leg["distance_m"] for leg in data["legs"]))

    path = data["path"]
    assert [p["waypoint_index"] for p in path if p["waypoint_index"] is not None] == [0, 1, 2]
    assert path[0]["distance_m"] == 0 and math.isclose(path[-1]["distance_m"], data["total_distance_m"])
    assert path[-1]["latitude_deg"] == -89.0 and path[-1]["longitude_deg"] == 10.0
    gaps = [b["distance_m"] - a["distance_m"] for a, b in zip(path, path[1:])]
    assert all(0 < g <= 500 + 1e-6 for g in gaps)


def test_points_lie_on_the_great_circle():
    # Two points on the same meridian: the straight line stays on that meridian.
    body = {"waypoints": [{"name": "A", "latitude_deg": -80.0, "longitude_deg": 30.0},
                          {"name": "B", "latitude_deg": -85.0, "longitude_deg": 30.0}], "step_m": 1000}
    data = client.post("/route", json=body).json()
    assert math.isclose(data["total_distance_m"], math.radians(5) * MOON_RADIUS_M, rel_tol=1e-9)
    assert all(math.isclose(p["longitude_deg"], 30.0, abs_tol=1e-9) for p in data["path"])


def test_route_errors():
    assert client.post("/route", json={"waypoints": [{"id": "shackleton_rim"}]}).status_code == 422
    assert client.post("/route", json={"waypoints": [{"id": "nope"}, {"id": "shackleton_rim"}]}).status_code == 404
    far = {"waypoints": [{"id": "shackleton_rim"}, {"id": "change6_apollo_basin"}], "step_m": 1}
    assert client.post("/route", json=far).status_code == 422
