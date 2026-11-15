"""Published POI proximity lookup; all tests are offline, never synthetic science data."""

import json
import math

import pytest
from fastapi.testclient import TestClient

from src.main import app
from src.schemas import PointOfInterest, Site
from src.services import ephemeris, recommendation
from tools.build_poi_catalogue import build, survey_pits

client = TestClient(app)


def landing(lat=-89, lon=0):
    return Site(id=None, name="Landing", group="Custom", latitude_deg=lat, longitude_deg=lon)


def poi(lat=-89, lon=0, radius=0):
    return PointOfInterest(
        id="geometry-fixture", name="Geometry test only", category="natural_feature", feature_type="Test",
        latitude_deg=lat, longitude_deg=lon,
        boundary={"kind": "approximate_circle" if radius else "point", "radius_km": radius},
        notes="Geometry-only fixture, never part of the shipped catalogue",
        sources=[{"title": "Test", "url": "https://example.com"}],
    )


def test_default_and_explicit_radius_match():
    body = {"site": {"id": "shackleton_rim"}}
    response = client.post("/recommended-sites", json=body)
    assert response.status_code == 200
    assert response.headers["X-Moon-Flyers-Data-Source"] == "catalogue"
    data = response.json()
    assert data == client.post("/recommended-sites", json={**body, "radius_km": 40}).json()
    assert data["method"] == "catalogue_proximity"
    assert data["data_source"] == "published_catalogue"
    assert data["catalogue_version"] == recommendation.CATALOGUE_VERSION
    assert data["site"]["id"] == "shackleton_rim"
    assert data["radius_km"] == 40
    rows = data["recommendations"]
    assert rows
    assert [(r["distance_km"], r["poi"]["id"]) for r in rows] == sorted(
        (r["distance_km"], r["poi"]["id"]) for r in rows)
    assert all(r["distance_km"] <= 40 for r in rows)
    assert all(set(r) == {"poi", "distance_km"} for r in rows)
    shackleton = next(r for r in rows if r["poi"]["id"] == "iau-5450")
    assert shackleton["distance_km"] == 0
    assert shackleton["poi"]["boundary"]["kind"] == "approximate_circle"


def test_coordinates_with_optional_name_match_catalogue_reference():
    known = client.post("/recommended-sites", json={"site": {"id": "shackleton_rim"}}).json()
    coords = {k: known["site"][k] for k in ("latitude_deg", "longitude_deg")}
    custom = client.post("/recommended-sites", json={"site": coords}).json()
    assert custom["site"]["id"] is None
    assert custom["recommendations"] == known["recommendations"]
    named = client.post("/recommended-sites", json={"site": {**coords, "name": "My landing"}}).json()
    assert named["site"]["name"] == "My landing"
    assert named["recommendations"] == known["recommendations"]


@pytest.mark.parametrize("identity", ["im1-odysseus", "im2-athena", "trek-impact-0", "trek-impact-3"])
def test_hardware_and_impacts_are_published_points(identity):
    point = next(p for p in recommendation.POINTS_OF_INTEREST if p.id == identity)
    response = client.post("/recommended-sites", json={
        "site": {"latitude_deg": point.latitude_deg, "longitude_deg": point.longitude_deg}, "radius_km": 0.001,
    })
    row = next(r for r in response.json()["recommendations"] if r["poi"]["id"] == identity)
    assert row["distance_km"] == 0
    assert row["poi"]["boundary"] == {"kind": "point", "radius_km": 0}
    assert row["poi"]["sources"]
    assert row["poi"]["location_uncertainty_km"] is None


def test_no_ephemeris_terrain_network_or_mock_dependency(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("POI lookup must not invoke ephemerides, mock data or network")
    import urllib.request
    from src.services import horizon, mock_ephemeris
    monkeypatch.setattr(ephemeris, "generate", forbidden)
    monkeypatch.setattr(mock_ephemeris, "generate", forbidden)
    monkeypatch.setattr(horizon, "for_site", forbidden)
    monkeypatch.setattr(urllib.request, "urlopen", forbidden)
    for mode in ("mock", "horizons"):
        monkeypatch.setattr(ephemeris, "DATA_SOURCE", mode)
        response = client.post("/recommended-sites", json={"site": {"id": "shackleton_rim"}})
        assert response.status_code == 200
        assert response.headers["X-Moon-Flyers-Data-Source"] == "catalogue"


def test_spherical_distances_pole_seam_and_antipode():
    scale = math.pi / 180 * recommendation.MOON_RADIUS_KM
    assert recommendation.distance_km(landing(-90, 123), poi(-90, -45)) == pytest.approx(0, abs=1e-10)
    assert recommendation.distance_km(landing(-90), poi(-89, 178)) == pytest.approx(scale)
    assert recommendation.distance_km(landing(0, 179), poi(0, -179)) == pytest.approx(2 * scale)
    assert recommendation.distance_km(landing(0, 0), poi(0, 180)) == pytest.approx(180 * scale)


def test_distance_to_area_not_centre_or_rim():
    centre_distance = math.radians(1) * recommendation.MOON_RADIUS_KM
    assert recommendation.distance_km(landing(-89), poi(-88, radius=5)) == pytest.approx(centre_distance - 5)
    assert recommendation.distance_km(landing(-89), poi(-89, radius=5)) == 0
    assert recommendation.distance_km(landing(-89), poi(-88.99, radius=5)) == 0


def test_radius_threshold_is_inclusive_and_unrounded(monkeypatch):
    point = poi(-88)
    monkeypatch.setattr(recommendation, "POINTS_OF_INTEREST", (point,))
    site = landing(-89)
    distance = recommendation.distance_km(site, point)
    assert len(recommendation.recommend(site, distance).recommendations) == 1
    assert not recommendation.recommend(site, distance - 1e-8).recommendations


def test_coverage_includes_crossing_footprints():
    assert recommendation.intersects_cap(poi(-79.9, radius=4))
    assert not recommendation.intersects_cap(poi(-79.9, radius=1))
    assert recommendation.intersects_cap(poi(-80))
    crossing = next(p for p in recommendation.POINTS_OF_INTEREST if p.id == "iau-1645")
    assert crossing.latitude_deg > -80  # Drygalski centre is outside, footprint intersects.
    response = client.post("/recommended-sites", json={
        "site": {"latitude_deg": -80, "longitude_deg": crossing.longitude_deg}, "radius_km": 0.001,
    })
    assert crossing.id in {r["poi"]["id"] for r in response.json()["recommendations"]}


def test_global_reference_is_allowed_but_catalogue_is_cap_only():
    response = client.post("/recommended-sites", json={
        "site": {"latitude_deg": 0, "longitude_deg": 0}, "radius_km": 1,
    })
    assert response.status_code == 200
    assert response.json()["recommendations"] == []
    all_pois = client.post("/recommended-sites", json={
        "site": {"latitude_deg": -90, "longitude_deg": 0}, "radius_km": 10000,
    }).json()["recommendations"]
    assert len(all_pois) == len(recommendation.POINTS_OF_INTEREST)  # No silent limit/truncation.


@pytest.mark.parametrize("body", [
    {}, {"radius_km": 40}, {"site": {}}, {"site": {"latitude_deg": -89}},
    {"site": {"latitude_deg": -91, "longitude_deg": 0}},
    {"site": {"latitude_deg": -89, "longitude_deg": 181}},
    {"site": {"latitude_deg": True, "longitude_deg": 0}},
    {"site": {"id": "shackleton_rim", "latitude_deg": -89, "longitude_deg": 0}},
    {"site": {"id": "shackleton_rim", "name": "Ambiguous"}},
    {"site": {"id": ""}}, {"site": {"id": "shackleton_rim", "unknown": 1}},
    {"site": {"latitude_deg": -89, "longitude_deg": 0, "name": "   "}},
    *[{"site": {"id": "shackleton_rim"}, "radius_km": r} for r in [0, -1, None, True, "Infinity", "40"]],
    {"site": {"id": "shackleton_rim"}, "constraints": {}},
    {"site": {"id": "shackleton_rim"}, "window_start_utc": "2027-08-01T00:00:00Z"},
    {"site": {"id": "shackleton_rim"}, "limit": 5},
])
def test_invalid_requests(body):
    assert client.post("/recommended-sites", json=body).status_code == 422


@pytest.mark.parametrize("raw", [
    '{"site":{"latitude_deg":NaN,"longitude_deg":0}}',
    '{"site":{"id":"shackleton_rim"},"radius_km":Infinity}',
])
def test_nonfinite_json_numbers(raw):
    assert client.post("/recommended-sites", content=raw,
                       headers={"Content-Type": "application/json"}).status_code == 422


def test_unknown_site_malformed_json_and_method():
    assert client.post("/recommended-sites", json={"site": {"id": "not-real"}}).status_code == 404
    assert client.post("/recommended-sites", content="{").status_code == 400
    assert client.get("/recommended-sites").status_code == 405


def test_shipped_catalogue_integrity_and_pit_survey():
    metadata = json.loads(recommendation.CATALOGUE_PATH.read_text(encoding="utf-8"))
    version, records = recommendation.load_catalogue(recommendation.CATALOGUE_PATH)
    assert version == metadata["version"]
    assert len({p.id for p in records}) == len(records) == 61
    assert all(recommendation.intersects_cap(p) for p in records)
    assert all(s.url.startswith("https://") for p in records for s in p.sources)
    assert {p.category for p in records} == {"natural_feature", "lander", "impact"}
    assert metadata["pit_atlas_survey"]["records_checked"] == 278
    assert metadata["pit_atlas_survey"]["in_cap_records"] == 0
    assert metadata["pit_atlas_survey"]["southernmost_latitude_deg"] == -78.0579
    assert len(metadata["source_sha256"]) == 64


def test_catalogue_errors_do_not_generate_fallback(tmp_path):
    missing = tmp_path / "missing.json"
    with pytest.raises(FileNotFoundError):
        recommendation.load_catalogue(missing)
    path = tmp_path / "bad.json"
    path.write_text('{"version":"test","points_of_interest":[]}', encoding="utf-8")
    with pytest.raises(ValueError):
        recommendation.load_catalogue(path)
    path.write_text(json.dumps({"version": "test", "points_of_interest": [poi().model_dump()] * 2}))
    with pytest.raises(ValueError):
        recommendation.load_catalogue(path)


def test_builder_refuses_partial_source_and_preserves_boundary_crossers():
    for source in ({"error": {}}, {"features": [{}], "exceededTransferLimit": True}):
        with pytest.raises(ValueError):
            build(json.dumps(source).encode())
    source = {"features": [{"attributes": {
        "FID": 33, "type": "Crater, craters", "center_lat": -79.573782, "center_lon": -87.176984,
        "diameter": 162.489, "link": "https://planetarynames.wr.usgs.gov/Feature/1645", "LABEL": "Drygalski",
    }}]}
    records = build(json.dumps(source).encode())
    assert next(r for r in records if r["id"] == "iau-1645")["boundary"]["radius_km"] == 162.489 / 2


def test_pit_survey_fails_closed_on_changed_source_or_new_candidate():
    with pytest.raises(ValueError):
        survey_pits(b"<html>no table</html>")
    header = "<tr><th>Host Feat.</th><th>Name</th><th>Lat.</th><th>Long.</th><th>Funnel Max</th></tr>"
    outside = "<tr><td>Host</td><td>Pit</td><td>-78.0579</td><td>25.3441</td><td>13</td></tr>"
    assert survey_pits((header + outside).encode())["in_cap_records"] == 0
    with pytest.raises(ValueError, match="New in-cap"):
        survey_pits((header + outside.replace("-78.0579", "-85")).encode())
