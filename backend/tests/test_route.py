"""POST /route: straight-line legs (default) and terrain A* legs over a mounted LOLA DEM."""

import json
import math

import numpy as np
import pytest
from fastapi.testclient import TestClient

from src.main import app
from src.services import horizon
from src.services.route import MOON_RADIUS_M
from tools.lola_fixture import write_dataset

client = TestClient(app)

# Fixture coordinates inside the synthetic dataset's polar coverage. The heights are a smooth
# analytic function, not lunar observations: these routes are loader/contract checks only.
START = (-88.0, 45.0)
GOAL = (-88.0, 45.05)


@pytest.fixture
def dataset(tmp_path):
    return write_dataset(tmp_path / "lola_dem")


@pytest.fixture(autouse=True)
def clear_dem_cache(monkeypatch):
    """The DEM stack is cached per directory; tests must not share or leak it."""
    monkeypatch.delenv("LOLA_DEM_DIR", raising=False)
    horizon.open_dem.cache_clear()
    yield
    horizon.open_dem.cache_clear()


def custom(name, coordinates):
    return {"name": name, "latitude_deg": coordinates[0], "longitude_deg": coordinates[1]}


def body(waypoints, **extra):
    return {"waypoints": waypoints, "step_m": 500, **extra}


# ---------- straight_line (default) ----------

def test_straight_line_route_through_catalogue_and_custom_sites():
    payload = body([{"id": "shackleton_rim"}, {"id": "connecting_ridge"},
                    {"name": "Spot", "latitude_deg": -89.0, "longitude_deg": 10.0}])
    r = client.post("/route", json=payload)
    assert r.status_code == 200
    data = r.json()
    assert data["method"] == "straight_line"
    assert data["status"] == "not_evaluated"
    assert data["terrain_source"] is None and data["rover"] is None and data["failing_leg"] is None
    assert [w["id"] for w in data["waypoints"]] == ["shackleton_rim", "connecting_ridge", None]
    assert len(data["legs"]) == 2
    assert all(leg["status"] == "not_evaluated" and leg["max_terrain_slope_deg"] is None
               for leg in data["legs"])
    assert math.isclose(data["total_distance_m"], sum(leg["distance_m"] for leg in data["legs"]))

    path = data["path"]
    assert [p["waypoint_index"] for p in path if p["waypoint_index"] is not None] == [0, 1, 2]
    assert all(p["elevation_m"] is None for p in path)
    assert path[0]["distance_m"] == 0 and math.isclose(path[-1]["distance_m"], data["total_distance_m"])
    assert path[-1]["latitude_deg"] == -89.0 and path[-1]["longitude_deg"] == 10.0
    gaps = [b["distance_m"] - a["distance_m"] for a, b in zip(path, path[1:])]
    assert all(0 < g <= 500 + 1e-6 for g in gaps)


def test_straight_line_points_lie_on_the_great_circle():
    # Two points on the same meridian: the straight line stays on that meridian.
    payload = body([custom("A", (-80.0, 30.0)), custom("B", (-85.0, 30.0))], step_m=1000)
    data = client.post("/route", json=payload).json()
    assert math.isclose(data["total_distance_m"], math.radians(5) * MOON_RADIUS_M, rel_tol=1e-9)
    assert all(math.isclose(p["longitude_deg"], 30.0, abs_tol=1e-9) for p in data["path"])


def test_route_errors_are_unchanged_for_straight_lines():
    assert client.post("/route", json={"waypoints": [{"id": "shackleton_rim"}]}).status_code == 422
    assert client.post("/route", json={"waypoints": [{"id": "nope"}, {"id": "shackleton_rim"}]}).status_code == 404
    far = body([{"id": "shackleton_rim"}, custom("Far-side reference", (-41.64, -153.99))], step_m=1)
    assert client.post("/route", json=far).status_code == 422


# ---------- terrain A* over the mounted DEM ----------

def test_terrain_round_trip_returns_elevations_and_diagnostics(dataset, monkeypatch):
    monkeypatch.setenv("LOLA_DEM_DIR", str(dataset))
    payload = body([custom("A", START), custom("B", GOAL), custom("A2", START)],
                   planner="terrain", rover={"max_slope_deg": 20, "cell_size_m": 20,
                                             "padding_m": 200, "climb_weight": 2})
    r = client.post("/route", json=payload)
    assert r.status_code == 200
    data = r.json()

    assert data["method"] == "astar_terrain" and data["status"] == "route_found"
    assert data["reason"] is None and data["failing_leg"] is None
    assert data["terrain_source"] == "lola_dem"
    assert data["rover"]["max_slope_deg"] == 20 and data["rover"]["climb_weight"] == 2
    assert len(data["legs"]) == 2 and all(leg["status"] == "route_found" for leg in data["legs"])

    path = data["path"]
    assert [p["waypoint_index"] for p in path if p["waypoint_index"] is not None] == [0, 1, 2]
    assert (path[0]["latitude_deg"], path[0]["longitude_deg"]) == START
    assert (path[-1]["latitude_deg"], path[-1]["longitude_deg"]) == START
    junction = next(p for p in path if p["waypoint_index"] == 1)
    assert (junction["latitude_deg"], junction["longitude_deg"]) == GOAL

    distances = [p["distance_m"] for p in path]
    assert distances[0] == 0 and distances == sorted(distances)
    assert math.isclose(distances[-1], data["total_distance_m"], rel_tol=1e-9)
    leg_total = sum(leg["distance_m"] for leg in data["legs"])
    assert math.isclose(data["total_distance_m"], leg_total, rel_tol=1e-9)
    assert data["total_distance_m"] > 0

    # Elevations come from the mounted DEM and are consistent with the reported gap-free route.
    from src.lunar_horizon_dem import DEM
    dem = DEM(str(dataset))
    lat = np.array([p["latitude_deg"] for p in path])
    lon = np.array([p["longitude_deg"] for p in path])
    assert all(p["elevation_m"] is not None for p in path)
    assert [p["elevation_m"] for p in path] == pytest.approx(dem.sample(lat, lon), rel=1e-12)

    for leg in data["legs"]:
        assert leg["max_terrain_slope_deg"] <= 20 + 1e-9
        assert leg["max_uphill_grade_deg"] >= 0 and leg["max_downhill_grade_deg"] >= 0
        assert leg["terrain_distance_m"] >= leg["distance_m"]
        assert leg["elevation_gain_m"] >= 0 and leg["elevation_loss_m"] >= 0
        assert leg["expanded_nodes"] > 0 and leg["cost"] >= leg["distance_m"]
        assert leg["start_check"]["passable"] and leg["goal_check"]["passable"]
        assert leg["start_check"]["blocked_reasons"] == []
    json.dumps(data, allow_nan=False)


def test_terrain_leg_distances_match_the_planner_metric(dataset, monkeypatch):
    """Cumulative path distances must agree with the planner's own chord-based metric."""
    monkeypatch.setenv("LOLA_DEM_DIR", str(dataset))
    payload = body([custom("A", START), custom("B", GOAL)],
                   planner="terrain", rover={"max_slope_deg": 20, "padding_m": 200})
    data = client.post("/route", json=payload).json()
    assert data["status"] == "route_found"
    assert math.isclose(data["legs"][0]["distance_m"],
                        _chords(data["path"]), rel_tol=1e-9)


def _chords(path):
    total = 0.0
    for a, b in zip(path, path[1:]):
        u, v = _unit(a), _unit(b)
        total += 2 * MOON_RADIUS_M * math.asin(min(1.0, math.dist(u, v) / 2))
    return total


def _unit(point):
    lat, lon = math.radians(point["latitude_deg"]), math.radians(point["longitude_deg"])
    return (math.cos(lat) * math.cos(lon), math.cos(lat) * math.sin(lon), math.sin(lat))


def test_terrain_endpoint_blocked_reports_status_and_cause(dataset, monkeypatch):
    monkeypatch.setenv("LOLA_DEM_DIR", str(dataset))
    payload = body([custom("A", START), custom("B", GOAL)],
                   planner="terrain", rover={"max_slope_deg": 0.5, "padding_m": 200})
    r = client.post("/route", json=payload)
    assert r.status_code == 200
    data = r.json()

    assert data["status"] in {"start_blocked", "goal_blocked"}
    assert data["failing_leg"] == 0 and data["reason"]
    assert data["path"] == [] and data["total_distance_m"] == 0
    leg = data["legs"][0]
    assert leg["status"] == data["status"] and leg["distance_m"] is None
    check = leg["start_check"] if data["status"] == "start_blocked" else leg["goal_check"]
    assert check["passable"] is False
    assert "terrain_slope_exceeds_limit" in check["blocked_reasons"]


def test_terrain_blocked_endpoint_lists_nearby_passable_cells(dataset, monkeypatch):
    """3.35 deg is just under this fixture's analytic slope at the endpoint (about 3.36)."""
    monkeypatch.setenv("LOLA_DEM_DIR", str(dataset))
    payload = body([custom("A", START), custom("B", GOAL)],
                   planner="terrain", rover={"max_slope_deg": 3.35, "padding_m": 200})
    data = client.post("/route", json=payload).json()
    check = data["legs"][0]["start_check"]
    assert data["status"] == "start_blocked" and check["passable"] is False
    # Suggestions pass node terrain checks only; they are never a route or proof of access.
    assert check["nearby_terrain_candidates"]
    assert all(c["terrain_slope_deg"] <= 3.35 for c in check["nearby_terrain_candidates"])
    assert all(c["offset_m"] > 0 for c in check["nearby_terrain_candidates"])


def test_terrain_repeated_waypoint_keeps_one_marker_per_real_waypoint(dataset, monkeypatch):
    monkeypatch.setenv("LOLA_DEM_DIR", str(dataset))
    payload = body([custom("A", START), custom("A again", START), custom("B", GOAL)],
                   planner="terrain", rover={"max_slope_deg": 20, "padding_m": 200})
    data = client.post("/route", json=payload).json()
    assert data["status"] == "route_found" and len(data["legs"]) == 2
    assert data["legs"][0]["distance_m"] == 0 and data["legs"][1]["distance_m"] > 0
    markers = [p["waypoint_index"] for p in data["path"] if p["waypoint_index"] is not None]
    assert markers[0] == 0 and markers[-1] == 2
    assert sorted(markers) == markers


def test_terrain_requires_a_mounted_dataset():
    r = client.post("/route", json=body([custom("A", START), custom("B", GOAL)], planner="terrain"))
    assert r.status_code == 503
    assert "LOLA_DEM_DIR" in r.json()["detail"]


def test_terrain_leg_beyond_the_search_radius_is_rejected(dataset, monkeypatch):
    monkeypatch.setenv("LOLA_DEM_DIR", str(dataset))
    payload = body([{"id": "shackleton_rim"}, {"id": "malapert_massif"}], planner="terrain")
    r = client.post("/route", json=payload)
    assert r.status_code == 422
    assert "max_region_radius_m" in r.json()["detail"]


def test_terrain_settings_are_validated():
    waypoints = [custom("A", START), custom("B", GOAL)]
    for rover in ({"max_slope_deg": 0}, {"max_slope_deg": 90}, {"cell_size_m": 0},
                  {"slope_weight": -1}, {"max_region_radius_m": 50_001}, {"unknown": 1}):
        assert client.post("/route", json=body(waypoints, planner="terrain", rover=rover)).status_code == 422
    assert client.post("/route", json=body(waypoints, planner="great_circle")).status_code == 422
