"""Local horizon models: elevation of the horizon (terrain) per azimuth, for one site.

To add LOLA terrain: write a class with `elevation_deg(az_deg)` that reads the DEM for the
site, and return it from `for_site()`. Nothing else needs to change.
"""

import hashlib
import math
from typing import Protocol

from ..schemas import Site


class HorizonModel(Protocol):
    def elevation_deg(self, az_deg: float) -> float:
        """Horizon elevation in degrees at azimuth `az_deg` (clockwise from north)."""
        ...


class FlatHorizon:
    """No terrain: the horizon is at 0° in every direction."""

    def elevation_deg(self, az_deg: float) -> float:
        return 0.0


class MockTerrainHorizon:
    """MOCK terrain (not LOLA data): smooth hills between 0° and `max_deg`, fixed per site.

    The site's coordinates seed the shape, so the same site always gets the same horizon and
    different sites look different. Sites nearer the pole get taller terrain (up to 1.5°);
    low-latitude sites stay under 0.5°. Kept low because the mock Sun only reaches about 2° at
    the pole, and real rim sites (Shackleton, Connecting Ridge) are chosen for their low horizons.
    """

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


def for_site(site: Site) -> HorizonModel:
    """The horizon model to use for `site`. Mock terrain until LOLA terrain is added."""
    return MockTerrainHorizon(site)


def profile(model: HorizonModel, step_deg: float = 1.0) -> dict:
    """Horizon sampled every `step_deg` around the compass, in the API's `horizon` shape."""
    az = [i * step_deg for i in range(int(360 / step_deg))]
    return {"horizon_azimuth_deg": az, "horizon_elevation_deg": [model.elevation_deg(a) for a in az]}
