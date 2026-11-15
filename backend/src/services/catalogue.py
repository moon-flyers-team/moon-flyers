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
    # Published landing/candidate-region context first, then geographic references.
    # Feature centres below are NOT vetted touchdown sites or necessarily traversable.
    # Coordinates and the measured 40 km POI coverage are documented in docs/poi-sources.md (root).
    Site(id="im2_mons_mouton", name="IM-2 Athena (Mons Mouton)", group="CLPS",
         latitude_deg=-84.7906, longitude_deg=29.1957,
         notes="Observed IM-2 landing, 2025; lander rested on its side, not a safety endorsement. "
               "Source: https://www.lroc.asu.edu/images/1408"),
    Site(id="nobile_reference", name="Nobile exploration reference", group="Candidate-region references (not vetted)",
         latitude_deg=-85.239498, longitude_deg=53.647625,
         notes="Published Nobile feature centre, not the VIPER landing point or an Artemis rim candidate. "
               "Exploration reference only; landing suitability unassessed. "
               "Source: https://planetarynames.wr.usgs.gov/Feature/4321 (Moon Trek snapshot)."),
    Site(id="faustini_reference", name="Faustini exploration reference",
         group="Candidate-region references (not vetted)", latitude_deg=-87.177099, longitude_deg=85.0241,
         notes="Published Faustini feature centre, not the historical Faustini Rim A candidate. "
               "Exploration reference only; landing suitability unassessed. "
               "Source: https://planetarynames.wr.usgs.gov/Feature/1919 (Moon Trek snapshot)."),
    Site(id="wiechert_reference", name="Wiechert exploration reference", group="Exploration references (not vetted)",
         latitude_deg=-84.042118, longitude_deg=164.612666,
         notes="Published feature centre; exploration reference only, landing suitability unassessed. "
               "Source: https://planetarynames.wr.usgs.gov/Feature/6541 (Moon Trek snapshot)."),
    Site(id="demonax_b_reference", name="Demonax B exploration reference", group="Exploration references (not vetted)",
         latitude_deg=-81.472904, longitude_deg=71.924005,
         notes="Published feature centre; exploration reference only, landing suitability unassessed. "
               "Source: https://planetarynames.wr.usgs.gov/Feature/8719 (Moon Trek snapshot)."),
    Site(id="schomberger_l_reference", name="Schomberger L exploration reference",
         group="Exploration references (not vetted)", latitude_deg=-80.67597, longitude_deg=17.213092,
         notes="Published feature centre; exploration reference only, landing suitability unassessed. "
               "Source: https://planetarynames.wr.usgs.gov/Feature/12948 (Moon Trek snapshot)."),
    Site(id="drygalski_p_reference", name="Drygalski P exploration reference",
         group="Exploration references (not vetted)", latitude_deg=-80.950624, longitude_deg=-99.621663,
         notes="Published feature centre; exploration reference only, landing suitability unassessed. "
               "Source: https://planetarynames.wr.usgs.gov/Feature/8838 (Moon Trek snapshot)."),
    Site(id="cabeus_reference", name="Cabeus exploration reference", group="Exploration references (not vetted)",
         latitude_deg=-85.277073, longitude_deg=-41.8055,
         notes="Published feature centre near LCROSS POIs; exploration reference only, landing suitability unassessed. "
               "Source: https://planetarynames.wr.usgs.gov/Feature/953 (Moon Trek snapshot)."),
    Site(id="newton_b_reference", name="Newton B exploration reference", group="Exploration references (not vetted)",
         latitude_deg=-81.386482, longitude_deg=-17.064487,
         notes="Published feature centre; exploration reference only, landing suitability unassessed. "
               "Source: https://planetarynames.wr.usgs.gov/Feature/11611 (Moon Trek snapshot)."),
    Site(id="idelson_reference", name="Idel son exploration reference", group="Exploration references (not vetted)",
         latitude_deg=-81.270524, longitude_deg=112.400911,
         notes="Published feature centre; exploration reference only, landing suitability unassessed. "
               "Source: https://planetarynames.wr.usgs.gov/Feature/2650 (Moon Trek snapshot)."),
    Site(id="cabeus_a_reference", name="Cabeus A exploration reference", group="Exploration references (not vetted)",
         latitude_deg=-82.044887, longitude_deg=-40.339792,
         notes="Published feature centre, not the Artemis Peak near Cabeus B candidate. "
               "Exploration reference only; landing suitability unassessed. "
               "Source: https://planetarynames.wr.usgs.gov/Feature/8057 (Moon Trek snapshot)."),
    Site(id="demonax_c_reference", name="Demonax C exploration reference", group="Exploration references (not vetted)",
         latitude_deg=-80.283681, longitude_deg=56.13802,
         notes="Published feature centre; exploration reference only, landing suitability unassessed. "
               "Source: https://planetarynames.wr.usgs.gov/Feature/8720 (Moon Trek snapshot)."),
    Site(id="idelson_l_reference", name="Idel son L exploration reference", group="Exploration references (not vetted)",
         latitude_deg=-83.991924, longitude_deg=118.563063,
         notes="Published feature centre; exploration reference only, landing suitability unassessed. "
               "Source: https://planetarynames.wr.usgs.gov/Feature/10114 (Moon Trek snapshot)."),
    Site(id="scott_e_reference", name="Scott E exploration reference", group="Exploration references (not vetted)",
         latitude_deg=-81.148551, longitude_deg=35.517237,
         notes="Published feature centre; exploration reference only, landing suitability unassessed. "
               "Source: https://planetarynames.wr.usgs.gov/Feature/13015 (Moon Trek snapshot)."),
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
