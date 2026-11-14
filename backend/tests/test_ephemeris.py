"""The Horizons adapter in services/ephemeris.py, offline (fake positions()) plus one opt-in live call."""

import os
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from src.main import app
from src.schemas import Site
from src.services import ephemeris
from src.services.errors import EphemerisUnavailableError, InvalidInputError, LimitExceededError

SITE = Site(id="x", name="x", group="x", latitude_deg=-89.667, longitude_deg=129.783)
START = datetime(2027, 8, 1, tzinfo=timezone.utc)
END = START + timedelta(hours=3)


@pytest.fixture
def live_mode(monkeypatch):
    monkeypatch.setattr(ephemeris, "DATA_SOURCE", "horizons")


def fake_positions(times):
    def positions(lat, lon, start, end, step):
        assert (lat, lon, start, end, step) == (-89.667, 129.783, "2027-08-01T00:00:00", "2027-08-01T03:00:00", 3600)
        n = len(times)
        return {"time_utc": times, "sun_azimuth_deg": [10.0] * n, "sun_elevation_deg": [1.0] * n,
                "earth_azimuth_deg": [350.0] * n, "earth_elevation_deg": [-2.0] * n}
    return positions


def test_horizons_rows_become_utc_series(live_mode, monkeypatch):
    times = [f"2027-08-01T0{h}:00:00" for h in range(4)]
    monkeypatch.setattr(ephemeris.positions, "positions", fake_positions(times))
    d = ephemeris.generate(SITE, START, END, 3600)
    assert d["times"] == [START + timedelta(hours=h) for h in range(4)]
    assert d["times"][0].tzinfo == timezone.utc
    assert d["sun_el"] == [1.0] * 4 and d["earth_az"] == [350.0] * 4


def test_grid_mismatch_is_upstream_error(live_mode, monkeypatch):
    monkeypatch.setattr(ephemeris.positions, "positions", fake_positions(["2027-08-01T00:00:00"]))
    with pytest.raises(EphemerisUnavailableError):
        ephemeris.generate(SITE, START, END, 3600)


def test_horizons_failure_is_502(live_mode, monkeypatch):
    def broken(*args):
        raise RuntimeError("Horizons error: boom")
    monkeypatch.setattr(ephemeris.positions, "positions", broken)
    r = TestClient(app).get("/sites", params={"site_id": "shackleton_rim", "window_start_utc": "2027-08-01T00:00:00Z",
                                              "window_end_utc": "2027-08-02T00:00:00Z", "days_on_surface": 1})
    assert r.status_code == 502
    assert r.headers["X-Moon-Flyers-Data-Source"] == "horizons"


def test_unsupported_step_is_invalid_input(live_mode):
    # 90 s isn't whole minutes and doesn't divide a 100 s span: positions() raises ValueError.
    with pytest.raises(InvalidInputError):
        ephemeris.generate(SITE, START, START + timedelta(seconds=100), 90)


def test_sample_limit_is_checked_before_any_request(live_mode):
    with pytest.raises(LimitExceededError):
        ephemeris.generate(SITE, START, START + timedelta(days=400), 60)


@pytest.mark.skipif(os.environ.get("MOON_FLYERS_LIVE") != "1", reason="hits JPL Horizons; set MOON_FLYERS_LIVE=1")
def test_live_horizons(live_mode):
    d = ephemeris.generate(SITE, START, END, 3600)
    assert d["times"] == [START + timedelta(hours=h) for h in range(4)]
    assert all(-90 <= e <= 90 for e in d["sun_el"] + d["earth_el"])
    assert all(0 <= a < 360 for a in d["sun_az"] + d["earth_az"])
