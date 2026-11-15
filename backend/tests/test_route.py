"""POST /route: straight-line legs (default) and terrain A* legs over a mounted LOLA DEM."""

import json
import math

import numpy as np
import pytest
from fastapi.testclient import TestClient

from src.main import app
from src.services import horizon
from src.services import route as route_service
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

    # Every requested stop is described once, independently of the legs that touch it.
    assert [s["index"] for s in data["stops"]] == [0, 1, 2]
    assert all(s["passable"] for s in data["stops"])
    assert all(s["terrain_slope_deg"] is not None for s in data["stops"])
    assert data["stops"][0]["latitude_deg"] == START[0] and data["stops"][1]["latitude_deg"] == GOAL[0]
    summary = data["summary"]
    assert summary["planned_legs"] == 2 and summary["failed_legs"] == 0
    assert summary["distance_m"] == pytest.approx(data["total_distance_m"])
    assert summary["max_slope_deg"] == 20 and summary["cell_size_m"] == 20
    assert summary["elevation_gain_m"] > 0 and summary["elevation_loss_m"] > 0
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
    assert data["failing_leg"] == 0 and data["failed_legs"] == [0] and data["reason"]
    assert data["total_distance_m"] == 0
    # The unplanned leg is still drawn, as a flagged straight placeholder between its waypoints.
    assert data["path"] and all(p["placeholder"] and p["elevation_m"] is None for p in data["path"])
    assert [p["waypoint_index"] for p in (data["path"][0], data["path"][-1])] == [0, 1]
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


def test_terrain_leg_beyond_the_search_radius_is_reported_per_leg(dataset, monkeypatch):
    """One unplannable leg must not turn the whole request into a 422."""
    monkeypatch.setenv("LOLA_DEM_DIR", str(dataset))

    def planner(dem, start, goal, **kw):
        if goal == C and start != goal:
            raise ValueError("Destination exceeds max_region_radius_m; only local routes are supported")
        return _fake_result(start, goal, "route_found", kw["padding_m"])
    monkeypatch.setattr(route_service, "plan_rover_route", planner)

    payload = body([custom("A", START), custom("B", GOAL), custom("C", C), custom("D", START)],
                   planner="terrain")
    r = client.post("/route", json=payload)
    assert r.status_code == 200
    data = r.json()
    assert [leg["status"] for leg in data["legs"]] == ["route_found", "region_too_large", "route_found"]
    assert data["failed_legs"] == [1] and data["status"] == "region_too_large"
    assert "leg 1 (B -> C)" in data["reason"]
    assert data["legs"][1]["distance_m"] is None
    assert data["summary"]["planned_legs"] == 2 and data["summary"]["failed_legs"] == 1
    assert data["legs"][0]["distance_m"] > 0 and data["legs"][2]["distance_m"] > 0


def test_terrain_route_beyond_the_region_radius_reports_region_too_large(dataset, monkeypatch):
    """A real planner rejection is a leg status, and its placeholder is still drawn."""
    monkeypatch.setenv("LOLA_DEM_DIR", str(dataset))
    payload = body([custom("A", START), custom("B", GOAL)], planner="terrain",
                   rover={"max_slope_deg": 20, "max_region_radius_m": 1_200})
    r = client.post("/route", json=payload)
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "region_too_large" and data["failed_legs"] == [0]
    assert "max_region_radius_m" in data["legs"][0]["reason"]
    assert data["path"] and all(p["placeholder"] for p in data["path"])
    assert data["stops"][0]["passable"] is True


def test_terrain_default_slope_limit_is_twenty_degrees():
    """The routing limit is its own setting; the mission constraint default stays 8."""
    from src.schemas import Constraints, RoverSettings
    assert RoverSettings().max_slope_deg == 20
    assert Constraints().max_slope_deg == 8


def test_terrain_settings_are_validated():
    waypoints = [custom("A", START), custom("B", GOAL)]
    for rover in ({"max_slope_deg": 0}, {"max_slope_deg": 90}, {"cell_size_m": 0},
                  {"slope_weight": -1}, {"max_region_radius_m": 50_001}, {"unknown": 1}):
        assert client.post("/route", json=body(waypoints, planner="terrain", rover=rover)).status_code == 422
    assert client.post("/route", json=body(waypoints, planner="great_circle")).status_code == 422


def _fake_result(start, goal, status, padding_m):
    """Minimal planner output in the shape `plan_rover_route` returns."""
    found = status == "route_found"
    check = {"grid_cell": [0, 0], "latitude_deg": start[0], "longitude_deg": start[1], "elevation_m": 0.0,
             "terrain_slope_deg": 1.0, "max_slope_deg": 15.0, "passable": True, "blocked_reasons": [],
             "nearby_terrain_candidates": []}
    path = [{"latitude_deg": lat, "longitude_deg": lon, "elevation_m": 0.0} for lat, lon in (start, goal)]
    return {"status": status, "reason": None if found else "no route here", "path": path if found else [],
            "endpoint_checks": {"start": check, "goal": {**check, "latitude_deg": goal[0],
                                                          "longitude_deg": goal[1]}},
            "terrain_distance_m": 1.0 if found else None, "elevation_gain_m": 0.0 if found else None,
            "elevation_loss_m": 0.0 if found else None, "max_terrain_slope_deg": 1.0 if found else None,
            "max_uphill_grade_deg": 0.0 if found else None, "max_downhill_grade_deg": 0.0 if found else None,
            "expanded_nodes": 10, "cost": 1.0 if found else None,
            "search": {"grid_shape": [3, 3], "padding_m": padding_m}}


def test_terrain_blocked_stop_is_reported_once_and_blocks_its_legs(dataset, monkeypatch):
    """The stop list, not just the leg verdict, has to say a location is impractical."""
    monkeypatch.setenv("LOLA_DEM_DIR", str(dataset))
    payload = body([custom("A", START), custom("B", GOAL), custom("A2", START)], planner="terrain",
                   rover={"max_slope_deg": 0.5, "padding_m": 200})
    data = client.post("/route", json=payload).json()

    assert [s["passable"] for s in data["stops"]] == [False, False, False]
    assert all("terrain_slope_exceeds_limit" in s["blocked_reasons"] for s in data["stops"])
    assert all(s["max_slope_deg"] == 0.5 for s in data["stops"])
    assert [leg["status"] for leg in data["legs"]] == ["start_blocked", "start_blocked"]
    assert data["failed_legs"] == [0, 1] and data["summary"]["planned_legs"] == 0
    # The leg's checkpoint agrees with the stop verdict instead of contradicting it.
    assert data["legs"][0]["start_check"]["passable"] is False
    assert data["legs"][1]["goal_check"]["passable"] is False
    assert "exceeds 0.5" in data["reason"]


C = (-88.0, 45.1)


def test_terrain_plans_every_leg_after_a_failed_one(dataset, monkeypatch):
    """A failed middle leg must not hide the legs after it; it becomes a placeholder."""
    monkeypatch.setenv("LOLA_DEM_DIR", str(dataset))
    calls = []

    def planner(dem, start, goal, **kw):
        calls.append(kw["padding_m"])
        return _fake_result(start, goal, "no_route" if start == GOAL else "route_found", kw["padding_m"])
    monkeypatch.setattr(route_service, "plan_rover_route", planner)

    payload = body([custom("A", START), custom("B", GOAL), custom("C", C), custom("A", START)],
                   planner="terrain", rover={"padding_m": 200, "cell_size_m": 60})
    data = client.post("/route", json=payload).json()
    assert [leg["status"] for leg in data["legs"]] == ["route_found", "no_route", "route_found"]
    assert data["status"] == "no_route" and data["failing_leg"] == 1 and data["failed_legs"] == [1]
    assert "leg 1 (B -> C)" in data["reason"]
    assert data["legs"][1]["distance_m"] is None and data["legs"][2]["distance_m"] > 0
    assert data["total_distance_m"] == pytest.approx(data["legs"][0]["distance_m"] + data["legs"][2]["distance_m"])
    stop_calls = [c for c in calls if c == route_service.STOP_CHECK_PADDING_M]
    assert len(stop_calls) == 3  # one check per unique stop, before any leg
    leg_calls = [c for c in calls if c != route_service.STOP_CHECK_PADDING_M]
    # The failed leg walks the whole corridor ladder; found legs are planned once.
    assert leg_calls == [200, 200, *route_service.CORRIDOR_STEPS_M, 200]
    assert data["legs"][1]["padding_m"] == route_service.CORRIDOR_STEPS_M[-1]
    assert data["summary"]["padding_m"] == route_service.CORRIDOR_STEPS_M[-1]
    markers = [p["waypoint_index"] for p in data["path"] if p["waypoint_index"] is not None]
    assert markers == [0, 1, 2, 3]
    flags = {p["placeholder"] for p in data["path"][1:-1]}
    assert flags == {True, False}
    distances = [p["distance_m"] for p in data["path"]]
    assert distances == sorted(distances)


def test_terrain_wider_retry_can_find_the_route(dataset, monkeypatch):
    monkeypatch.setenv("LOLA_DEM_DIR", str(dataset))
    calls = []

    def planner(dem, start, goal, **kw):
        calls.append(kw["padding_m"])
        wide = kw["padding_m"] >= 10_000
        return _fake_result(start, goal, "route_found" if wide else "no_route", kw["padding_m"])
    monkeypatch.setattr(route_service, "plan_rover_route", planner)

    data = client.post("/route", json=body([custom("A", START), custom("B", GOAL)], planner="terrain",
                                            rover={"cell_size_m": 60, "padding_m": 200})).json()
    assert data["status"] == "route_found" and data["failed_legs"] == []
    # The ladder stops at the first corridor that works instead of always trying the widest one.
    assert data["legs"][0]["padding_m"] == 10_000
    assert [c for c in calls if c != route_service.STOP_CHECK_PADDING_M] == [200, 5000, 10_000]
    assert not any(p["placeholder"] for p in data["path"])


def test_terrain_cell_budget_degrades_instead_of_failing_the_request(dataset, monkeypatch):
    """A request that runs out of cells keeps its planned legs and reports the rest."""
    monkeypatch.setenv("LOLA_DEM_DIR", str(dataset))
    monkeypatch.setattr(route_service, "MAX_TERRAIN_CELLS", 30_000)

    def planner(dem, start, goal, **kw):
        result = _fake_result(start, goal, "route_found", kw["padding_m"])
        result["search"]["grid_shape"] = [50, 50]
        return result
    monkeypatch.setattr(route_service, "plan_rover_route", planner)

    far = (-88.5, 45.1)
    payload = body([custom("A", START), custom("B", GOAL), custom("C", far)], planner="terrain",
                   rover={"cell_size_m": 20, "padding_m": 500})
    r = client.post("/route", json=payload)
    assert r.status_code == 200
    data = r.json()
    assert data["legs"][0]["status"] == "route_found"
    assert data["legs"][1]["status"] == "search_limit_reached"
    assert "cell budget" in data["legs"][1]["reason"]
    assert data["summary"]["planned_legs"] == 1 and data["summary"]["failed_legs"] == 1
    assert data["total_distance_m"] == data["legs"][0]["distance_m"]


def test_terrain_stop_checks_are_shared_by_every_leg(dataset, monkeypatch):
    """A repeated stop is evaluated once, so both legs see the same verdict."""
    monkeypatch.setenv("LOLA_DEM_DIR", str(dataset))
    calls = []

    def planner(dem, start, goal, **kw):
        calls.append((start, goal, kw["padding_m"]))
        return _fake_result(start, goal, "route_found", kw["padding_m"])
    monkeypatch.setattr(route_service, "plan_rover_route", planner)

    payload = body([custom("A", START), custom("B", GOAL), custom("A again", START)], planner="terrain")
    data = client.post("/route", json=payload).json()
    checks = [c for c in calls if c[0] == c[1]]
    assert len(checks) == 2
    assert [s["latitude_deg"] for s in data["stops"]] == [START[0], GOAL[0], START[0]]
    assert data["stops"][0]["terrain_slope_deg"] == data["stops"][2]["terrain_slope_deg"]


# ---------- stop preflight (no legs planned) ----------

def test_route_stops_reports_usability_without_planning_legs(dataset, monkeypatch):
    monkeypatch.setenv("LOLA_DEM_DIR", str(dataset))
    calls = []

    def planner(dem, start, goal, **kw):
        calls.append((start, goal))
        assert start == goal, "preflight must not plan a leg"
        return _fake_result(start, goal, "route_found", kw["padding_m"])
    monkeypatch.setattr(route_service, "plan_rover_route", planner)

    r = client.post("/route/stops", json={
        "waypoints": [custom("A", START), custom("B", GOAL), custom("A2", START)],
        "rover": {"max_slope_deg": 20},
    })
    assert r.status_code == 200
    data = r.json()
    assert [s["index"] for s in data["stops"]] == [0, 1, 2]
    assert all(s["passable"] for s in data["stops"])
    assert len(calls) == 2  # the repeated stop is evaluated once
    assert all(s["terrain_slope_deg"] is not None for s in data["stops"])


def test_route_stops_reports_a_blocked_location_with_candidates(dataset, monkeypatch):
    monkeypatch.setenv("LOLA_DEM_DIR", str(dataset))
    r = client.post("/route/stops", json={
        "waypoints": [custom("A", START), custom("B", GOAL)],
        "rover": {"max_slope_deg": 3.35},
    })
    assert r.status_code == 200
    stops = r.json()["stops"]
    assert [s["passable"] for s in stops] == [False, False]
    assert "terrain_slope_exceeds_limit" in stops[0]["blocked_reasons"]
    assert stops[0]["nearby_terrain_candidates"]


def test_route_stops_requires_a_mounted_dataset():
    r = client.post("/route/stops", json={"waypoints": [custom("A", START)]})
    assert r.status_code == 503 and "LOLA_DEM_DIR" in r.json()["detail"]


def test_route_stops_validates_input():
    assert client.post("/route/stops", json={"waypoints": []}).status_code == 422
    assert client.post("/route/stops", json={
        "waypoints": [custom("A", START)], "rover": {"max_slope_deg": 90}}).status_code == 422
