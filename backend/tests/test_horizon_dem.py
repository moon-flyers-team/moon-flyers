"""The API uses the mounted LOLA DEMs when LOLA_DEM_DIR is set, else the mock hills."""

import pytest

from src import lunar_horizon_dem
from src.schemas import Site
from src.services import horizon
from tools.lola_fixture import write_dataset


def site(lat: float, lon: float, name: str = "t") -> Site:
    return Site(id=None, name=name, group="Custom", latitude_deg=lat, longitude_deg=lon)


@pytest.fixture
def dataset(tmp_path):
    return write_dataset(tmp_path / "lola_dem")


@pytest.fixture(autouse=True)
def clear_caches():
    """The DEM stack and skylines are cached per directory; tests must not share them."""
    horizon._dem.cache_clear()
    horizon._dem_site.cache_clear()
    yield
    horizon._dem.cache_clear()
    horizon._dem_site.cache_clear()


def test_without_the_variable_the_mock_hills_are_used(monkeypatch):
    monkeypatch.delenv("LOLA_DEM_DIR", raising=False)
    assert isinstance(horizon.for_site(site(-89.5, 10)), horizon.MockTerrainHorizon)


def test_mounted_dataset_drives_the_api_horizon(dataset, monkeypatch):
    monkeypatch.setenv("LOLA_DEM_DIR", str(dataset))
    model = horizon.for_site(site(-88.0, 45.0))
    assert isinstance(model, horizon.DemHorizon)
    expected = lunar_horizon_dem.horizon(-88.0, 45.0, dem=horizon._dem(str(dataset)))
    assert [model.elevation_deg(a) for a in range(360)] == [
        round(v, 3) for v in expected["horizon_elevation_deg"]]
    # A terrain horizon is not the mock shape: it must be able to sit below 0 degrees.
    assert min(model.elevation_deg(a) for a in range(360)) < 0


def test_profile_is_reused_for_repeated_requests(dataset, monkeypatch):
    monkeypatch.setenv("LOLA_DEM_DIR", str(dataset))
    first = horizon.for_site(site(-88.0, 45.0))
    second = horizon.for_site(site(-88.0, 45.0))
    assert first.elevation_deg(123) == second.elevation_deg(123)
    assert horizon._dem_site.cache_info().hits >= 1


def test_coordinates_outside_the_rasters_fall_back_to_flat(monkeypatch):
    class EmptyDem:
        def sample(self, lat, lon):
            import numpy as np
            return np.full(np.asarray(lat).shape, np.nan)

    monkeypatch.setenv("LOLA_DEM_DIR", "/does/not/matter")
    monkeypatch.setattr(horizon, "_dem", lambda directory: EmptyDem())
    assert isinstance(horizon.for_site(site(0.0, 0.0)), horizon.FlatHorizon)


def test_api_serves_the_terrain_profile(dataset, monkeypatch):
    from fastapi.testclient import TestClient

    from src.main import app

    monkeypatch.setenv("LOLA_DEM_DIR", str(dataset))
    window = {"window_start_utc": "2027-08-01T00:00:00Z", "window_end_utc": "2027-08-02T00:00:00Z"}
    with TestClient(app) as client:
        analysis = client.get("/sites", params={
            "name": "Test site", "latitude_deg": -88.0, "longitude_deg": 45.0, **window}).json()["analysis"]
    elevations = analysis["horizon"]["horizon_elevation_deg"]
    assert len(elevations) == 360
    profile, slope = horizon._dem_site(str(dataset), -88.0, 45.0)
    assert elevations == [profile[a] for a in range(360)]
    assert slope is not None and analysis["metrics"]["slope_deg"] == slope


def test_slope_comes_from_the_dem(dataset, monkeypatch):
    monkeypatch.setenv("LOLA_DEM_DIR", str(dataset))
    model = horizon.for_site(site(-88.0, 45.0))
    expected = lunar_horizon_dem.horizon(-88.0, 45.0, dem=horizon._dem(str(dataset)))["slope_deg"]
    assert model.slope_deg == round(expected, 1) and model.slope_deg > 0


def test_no_dem_means_no_slope(monkeypatch):
    monkeypatch.delenv("LOLA_DEM_DIR", raising=False)
    assert horizon.for_site(site(-89.5, 10)).slope_deg is None
    assert horizon.FlatHorizon().slope_deg is None
