"""Contract tests for the v0 mock API (backend/docs/API.md). Run from backend/: pytest"""

from fastapi.testclient import TestClient

from src.main import app

client = TestClient(app)

WINDOW = {"window_start_utc": "2027-08-01T00:00:00Z", "window_end_utc": "2027-08-08T00:00:00Z"}
METRIC_KEYS = {"sun_visible_pct", "longest_darkness_hours", "earth_visible_pct",
               "longest_earth_blackout_hours", "slope_deg"}
FIT_STATUSES = {"both_met", "power_short", "comms_short", "neither_met"}


def test_health_and_mock_header():
    r = client.get("/health")
    assert r.json() == {"status": "ok"}
    assert r.headers["X-Moon-Flyers-Data-Source"] == "mock"
    assert "/health" in client.get("/openapi.json").json()["paths"]


def test_catalogue():
    sites = client.get("/sites").json()
    assert len(sites) >= 5
    assert set(sites[0]) == {"id", "name", "group", "latitude_deg", "longitude_deg", "notes"}


def test_site_analysis_spans_window_plus_stay():
    r = client.get("/sites", params={"site_id": "malapert_massif", "days_on_surface": 14, **WINDOW})
    assert r.status_code == 200
    a = r.json()["analysis"]
    ts = a["timeseries"]
    assert ts[0]["time_utc"] == "2027-08-01T00:00:00Z"
    assert ts[-1]["time_utc"] == "2027-08-22T00:00:00Z"  # window_end + 14 days
    assert len(ts) == 21 * 24 + 1
    assert set(ts[0]) == {"time_utc", "sun_azimuth_deg", "sun_elevation_deg", "sun_visible",
                          "earth_azimuth_deg", "earth_elevation_deg", "earth_visible"}
    assert len(a["horizon"]["horizon_azimuth_deg"]) == len(a["horizon"]["horizon_elevation_deg"]) == 360
    assert set(a["metrics"]) == METRIC_KEYS and a["metrics"]["slope_deg"] is None
    assert a["fit"]["status"] in FIT_STATUSES
    assert set(a["windows"]) == {"sun", "earth", "eclipse"}


def test_site_analysis_is_deterministic():
    p = {"site_id": "shackleton_rim", **WINDOW}
    assert client.get("/sites", params=p).json() == client.get("/sites", params=p).json()


def test_custom_site_and_errors():
    r = client.get("/sites", params={"name": "My site", "latitude_deg": -89.2, "longitude_deg": 45, **WINDOW})
    assert r.status_code == 200 and r.json()["id"] is None and r.json()["group"] == "Custom"
    assert client.get("/sites", params={"site_id": "nope", **WINDOW}).status_code == 404
    assert client.get("/sites", params={"site_id": "malapert_massif"}).status_code == 422
    assert client.get("/sites", params={"name": "x", **WINDOW}).status_code == 422


def test_sun_visibility_off_nulls_sun_fields():
    r = client.get("/sites", params={"site_id": "malapert_massif", "sun_visibility": "false", **WINDOW})
    p = r.json()["analysis"]["timeseries"][0]
    assert p["sun_elevation_deg"] is None and p["earth_elevation_deg"] is not None


def test_compare():
    body = {"sites": [{"id": "shackleton_rim"},
                      {"name": "My site", "latitude_deg": -89.2, "longitude_deg": 45.0}],
            **WINDOW, "candidate_step_hours": 6}
    r = client.post("/compare", json=body)
    assert r.status_code == 200
    res = r.json()
    assert [x["site"]["name"] for x in res] == ["Shackleton rim", "My site"]
    wm = res[0]["window_metrics"]
    assert len(wm) == 7 * 4 + 1  # every 6 h across 7 days, inclusive
    assert wm[1]["landing_utc"] == "2027-08-01T06:00:00Z"
    assert set(wm[0]["metrics"]) == METRIC_KEYS and wm[0]["fit"]["status"] in FIT_STATUSES
    assert set(res[0]["timeline"]) == {"sun", "earth", "eclipse"}


def test_far_side_site_never_sees_earth():
    r = client.post("/compare", json={"sites": [{"id": "change6_apollo_basin"}], **WINDOW})
    first = r.json()[0]["window_metrics"][0]
    assert first["metrics"]["earth_visible_pct"] == 0
    assert "earth_visible_pct" in first["fit"]["violations"]


def test_landing_windows_sorted_and_limited():
    r = client.post("/landing-windows", json={"site": {"id": "malapert_massif"}, **WINDOW, "limit": 3})
    res = r.json()
    assert [x["rank"] for x in res] == [1, 2, 3]
    order = {"both_met": 0, "power_short": 1, "comms_short": 1, "neither_met": 2}
    assert [order[x["fit"]["status"]] for x in res] == sorted(order[x["fit"]["status"]] for x in res)


def test_error_status_codes():
    bad_json = client.post("/compare", content="{not json", headers={"content-type": "application/json"})
    assert bad_json.status_code == 400
    assert client.post("/compare", json={"sites": [{"id": "nope"}], **WINDOW}).status_code == 404
    assert client.post("/compare", json={"sites": [], **WINDOW}).status_code == 422


def test_limits_and_validation():
    big = {"site_id": "malapert_massif", "window_start_utc": "2027-01-01T00:00:00Z",
           "window_end_utc": "2028-01-01T00:00:00Z", "timestep_seconds": 60}
    assert client.get("/sites", params=big).status_code == 422
    bad = {"sites": [{"id": "malapert_massif"}], "window_start_utc": "2027-08-08T00:00:00Z",
           "window_end_utc": "2027-08-01T00:00:00Z"}
    assert client.post("/compare", json=bad).status_code == 422


def test_eclipse_needs_overlap_and_visible_earth():
    from src.services.visibility import eclipse_flags
    assert eclipse_flags([10, 10, 10], [5, 5, 5], [10.5, 10.5, 20], [5, 5, 5], [True, False, True]) == [True, False, False]
