"""Mock terrain horizon: shape, determinism, and that it really blocks the Sun/Earth."""

from fastapi.testclient import TestClient

from src.main import app
from src.schemas import Site
from src.services import horizon, visibility

client = TestClient(app)
WINDOW = {"window_start_utc": "2027-08-01T00:00:00Z", "window_end_utc": "2027-08-08T00:00:00Z"}


def site(lat: float, lon: float) -> Site:
    return Site(id=None, name="t", group="Custom", latitude_deg=lat, longitude_deg=lon)


def test_terrain_is_bounded_varied_and_deterministic():
    polar = horizon.MockTerrainHorizon(site(-89.5, 10))
    els = [polar.elevation_deg(a) for a in range(360)]
    assert all(0 <= e <= 1.5 for e in els)
    assert max(els) - min(els) > 0.3                      # not flat
    assert horizon.MockTerrainHorizon(site(-89.5, 10)).elevation_deg(123) == polar.elevation_deg(123)
    assert horizon.MockTerrainHorizon(site(-86, 0)).elevation_deg(123) != polar.elevation_deg(123)
    assert horizon.MockTerrainHorizon(site(-41, 0)).max_deg == 0.5   # low latitude stays low


def test_terrain_blocks_a_body_just_above_zero():
    terrain = horizon.MockTerrainHorizon(site(-89.5, 10))
    az = max(range(360), key=terrain.elevation_deg)      # tallest hill
    el = terrain.elevation_deg(az) - 0.1                 # body just below the hilltop
    assert visibility.visible_flags([az], [el], 0.0, 0.0, horizon.FlatHorizon()) == [True]
    assert visibility.visible_flags([az], [el], 0.0, 0.0, terrain) == [False]


def test_api_returns_the_terrain_profile():
    a = client.get("/sites", params={"site_id": "malapert_massif", **WINDOW}).json()["analysis"]
    els = a["horizon"]["horizon_elevation_deg"]
    assert len(els) == 360 and max(els) > 0
