"""Predefined landing sites, and turning a SiteRef (id or custom coordinates) into a Site."""

from ..schemas import Site, SiteRef
from .errors import UnknownSiteError

# Coordinates are approximate. Verify before relying on real data.
SITES: list[Site] = [
    Site(id="shackleton_rim", name="Shackleton rim", group="Artemis III region",
         latitude_deg=-89.667, longitude_deg=129.783, notes="Rim of Shackleton crater."),
    Site(id="connecting_ridge", name="Connecting Ridge", group="Artemis III region",
         latitude_deg=-89.45, longitude_deg=-140.2, notes="Ridge between Shackleton and de Gerlache."),
    Site(id="de_gerlache_rim", name="de Gerlache rim", group="Artemis III region",
         latitude_deg=-88.67, longitude_deg=-68.0, notes="Rim of de Gerlache crater."),
    Site(id="malapert_massif", name="Malapert massif", group="Artemis III region",
         latitude_deg=-86.0, longitude_deg=0.0, notes="Near-side massif with good Earth view."),
    Site(id="im1_malapert_a", name="IM-1 Odysseus (Malapert A)", group="CLPS",
         latitude_deg=-80.13, longitude_deg=1.44, notes="Intuitive Machines IM-1 landing, 2024."),
    Site(id="chandrayaan3_shiv_shakti", name="Chandrayaan-3 (Shiv Shakti point)", group="ISRO landing",
         latitude_deg=-69.373, longitude_deg=32.319, notes="Chandrayaan-3 Vikram landing, 2023."),
    Site(id="change6_apollo_basin", name="Chang'e-6 (Apollo basin)", group="CNSA landing",
         latitude_deg=-41.64, longitude_deg=-153.99, notes="Far-side sample return, 2024. No Earth view."),
]
SITES_BY_ID = {s.id: s for s in SITES}


def resolve_site(ref: SiteRef) -> Site:
    if ref.id is not None:
        site = SITES_BY_ID.get(ref.id)
        if site is None:
            raise UnknownSiteError(f"unknown site id: {ref.id}")
        return site
    return Site(id=None, name=ref.name, group="Custom",
                latitude_deg=ref.latitude_deg, longitude_deg=ref.longitude_deg)
