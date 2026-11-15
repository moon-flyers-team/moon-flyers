"""Local horizon models: elevation of the horizon (terrain) per azimuth, for one site.

`for_site()` returns the real LOLA terrain horizon when the server has a verified DEM
dataset mounted (`LOLA_DEM_DIR`), and the mock hills otherwise. Consumers call
`elevation_deg(az)`, and read `slope_deg`: the real terrain slope at the site from the DEM,
or None when there is no DEM (the mock hills and the flat horizon never invent a slope).
"""

import hashlib
import logging
import math
import os
from functools import lru_cache
from typing import Protocol

from .. import lunar_horizon_dem
from ..schemas import Site

log = logging.getLogger(__name__)


class HorizonModel(Protocol):
    slope_deg: float | None  # terrain slope at the site, degrees from horizontal; None = unknown

    def elevation_deg(self, az_deg: float) -> float:
        """Horizon elevation in degrees at azimuth `az_deg` (clockwise from north)."""
        ...


class FlatHorizon:
    """No terrain: the horizon is at 0° in every direction."""

    slope_deg = None

    def elevation_deg(self, az_deg: float) -> float:
        return 0.0


class MockTerrainHorizon:
    """MOCK terrain (not LOLA data): smooth hills between 0° and `max_deg`, fixed per site.

    The site's coordinates seed the shape, so the same site always gets the same horizon and
    different sites look different. Sites nearer the pole get taller terrain (up to 1.5°);
    low-latitude sites stay under 0.5°. Kept low because the mock Sun only reaches about 2° at
    the pole, and real rim sites (Shackleton, Connecting Ridge) are chosen for their low horizons.
    """

    slope_deg = None  # no real terrain, so no slope

    _HARMONICS = (1, 2, 3, 5)  # whole cycles per 360°, so the profile joins up at north
    _WEIGHTS = (0.40, 0.30, 0.20, 0.10)

    def __init__(self, site: Site):
        polar = min(1.0, max(0.0, (abs(site.latitude_deg) - 70) / 20))
        self.max_deg = 0.5 + 1.0 * polar
        seed = hashlib.sha256(f"{site.latitude_deg:.4f},{site.longitude_deg:.4f}".encode()).digest()
        self._phases = [b / 255 * 2 * math.pi for b in seed[: len(self._HARMONICS)]]

    def elevation_deg(self, az_deg: float) -> float:
        a = math.radians(az_deg)
        wave = sum(w * math.sin(k * a + p) for k, w, p in zip(self._HARMONICS, self._WEIGHTS, self._phases))
        return round(self.max_deg * (0.5 + 0.5 * wave), 3)  # wave is in [-1, 1] → [0, max_deg]


class DemHorizon:
    """Terrain horizon from the LOLA DEMs mounted at `LOLA_DEM_DIR`.

    Holds the 360-value skyline and the site slope computed once per site (see `_dem_site`),
    so a request that asks for the horizon at many azimuths does not touch the rasters
    again. Negative values are real: a site on a rim sees terrain below its horizon.
    """

    def __init__(self, profile_deg: tuple[float, ...], slope_deg: float | None):
        self._profile = profile_deg
        self.slope_deg = slope_deg

    def elevation_deg(self, az_deg: float) -> float:
        return self._profile[int(round(az_deg)) % 360]


@lru_cache(maxsize=4)
def _dem(directory: str) -> "lunar_horizon_dem.DEM":
    """Open a DEM stack once per directory; it memory-maps the rasters."""
    return lunar_horizon_dem.DEM(directory)


@lru_cache(maxsize=512)
def _dem_site(directory: str, latitude_deg: float, longitude_deg: float) -> tuple[tuple[float, ...], float | None]:
    """Skyline and slope for one site, rounded to the precision the API reports."""
    out = lunar_horizon_dem.horizon(latitude_deg, longitude_deg,
                                    height_above_terrain=0.0, dem=_dem(directory))
    slope = out["slope_deg"]
    return tuple(round(v, 3) for v in out["horizon_elevation_deg"]), None if slope is None else round(slope, 1)


def for_site(site: Site) -> HorizonModel:
    """Terrain from the mounted LOLA DEMs, else the mock hills.

    Opt-in: deployments only set `LOLA_DEM_DIR` through `deploy/compose.terrain.yaml`.
    An uncovered coordinate or an unreadable dataset falls back to a flat horizon with a
    warning rather than failing the request; the deploy already refuses a broken dataset
    at startup, so this only guards custom coordinates outside the rasters' coverage.
    """
    directory = os.environ.get("LOLA_DEM_DIR")
    if not directory:
        return MockTerrainHorizon(site)
    try:
        return DemHorizon(*_dem_site(directory, round(site.latitude_deg, 6), round(site.longitude_deg, 6)))
    except RuntimeError as exc:  # e.g. "No DEM coverage at the site"
        log.warning("DEM horizon unavailable for %s (%.4f, %.4f): %s; reporting a flat horizon",
                    site.name, site.latitude_deg, site.longitude_deg, exc)
        return FlatHorizon()


def profile(model: HorizonModel, step_deg: float = 1.0) -> dict:
    """Horizon sampled every `step_deg` around the compass, in the API's `horizon` shape."""
    az = [i * step_deg for i in range(int(360 / step_deg))]
    return {"horizon_azimuth_deg": az, "horizon_elevation_deg": [model.elevation_deg(a) for a in az]}
