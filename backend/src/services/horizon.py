"""Local horizon models: elevation of the horizon (terrain) per azimuth, for one site.

To add LOLA terrain: write a class with `elevation_deg(az_deg)` that reads the DEM for the
site, and return it from `for_site()`. Nothing else needs to change.
"""

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


def for_site(site: Site) -> HorizonModel:
    """The horizon model to use for `site`. Flat until LOLA terrain is added."""
    return FlatHorizon()


def profile(model: HorizonModel, step_deg: float = 1.0) -> dict:
    """Horizon sampled every `step_deg` around the compass, in the API's `horizon` shape."""
    az = [i * step_deg for i in range(int(360 / step_deg))]
    return {"horizon_azimuth_deg": az, "horizon_elevation_deg": [model.elevation_deg(a) for a in az]}
