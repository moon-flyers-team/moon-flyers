"""Refresh the published POI snapshot. Network is used ONLY by this explicit offline build.

Run from the repository root as documented in docs/poi-sources.md.
No scientific or HTTP dependencies are required.
"""

import hashlib
import json
import math
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import urlopen

MOON_RADIUS_KM = 1737.4
SERVICE = "https://trek.nasa.gov/moon/trekarcgis/rest/services/CombinedNomenclatureS/MapServer/0"
QUERY = SERVICE + "/query?" + urlencode({
    "where": "1=1", "outFields": "*", "returnGeometry": "false", "f": "json",
})
OUTPUT = Path(__file__).resolve().parents[1] / "src/data/points_of_interest.json"
PITS_URL = "https://www.lroc.asu.edu/atlases/pits/list"


class PitTable(HTMLParser):
    """Read the published atlas table without adding a scraping dependency."""

    def __init__(self):
        super().__init__()
        self.rows = []
        self.row = None
        self.cell = None

    def handle_starttag(self, tag, attrs):
        if tag == "tr":
            self.row = []
        elif tag in ("td", "th"):
            self.cell = ""

    def handle_data(self, data):
        if self.cell is not None:
            self.cell += data

    def handle_endtag(self, tag):
        if tag in ("td", "th") and self.cell is not None:
            if self.row is not None:
                self.row.append(self.cell.strip())
            self.cell = None
        if tag == "tr" and self.row:
            self.rows.append(self.row)
            self.row = None


def survey_pits(raw: bytes) -> dict:
    table = PitTable()
    table.feed(raw.decode("utf-8"))
    if not table.rows or table.rows[0][:4] != ["Host Feat.", "Name", "Lat.", "Long."]:
        raise ValueError("LROC pit table format changed; review before refreshing")
    rows = table.rows[1:]
    if not rows:
        raise ValueError("LROC pit table is empty")
    # This snapshot currently has no in-cap pits. A new candidate requires source and
    # geometry review, not silent classification as a confirmed cave.
    for row in rows:
        latitude, longitude = float(row[2]), float(row[3])
        if not (-90 <= latitude <= 90 and 0 <= longitude <= 360):
            raise ValueError("Invalid LROC pit coordinates")
        radius_km = float(row[4]) / 2000 if row[4] != "N/A" else 0
        if math.radians(latitude + 80) * MOON_RADIUS_KM <= radius_km:
            raise ValueError("New in-cap pit candidate: review and add a sourced record before refreshing")
    return {"url": PITS_URL, "sha256": hashlib.sha256(raw).hexdigest(),
            "records_checked": len(rows), "in_cap_records": 0,
            "southernmost_latitude_deg": min(float(row[2]) for row in rows)}


def build(raw: bytes) -> list[dict]:
    data = json.loads(raw)
    if "error" in data or data.get("exceededTransferLimit") or not data.get("features"):
        raise ValueError("Moon Trek query failed, returned no records or was truncated")
    records = []
    for feature in data["features"]:
        a = feature["attributes"]
        # Exclude unofficial duplicate impact labels and unsourced informal place names.
        if a["type"] not in {"Crater, craters", "Satellite Feature", "Mons, montes", "Impact"}:
            continue
        lat, lon = a["center_lat"], a["center_lon"]
        radius = a["diameter"] / 2 if a["type"] != "Impact" else 0
        if not all(math.isfinite(v) for v in (lat, lon, radius)) or radius < 0:
            raise ValueError("Invalid coordinates/diameter in source")
        # A circular footprint can intersect the cap even with its centre north of 80 S.
        if math.radians(lat + 90) * MOON_RADIUS_KM - radius > math.radians(10) * MOON_RADIUS_KM:
            continue
        url = a["link"].strip().replace("http://", "https://", 1)
        if not url:
            raise ValueError("Missing source link")
        impact = a["type"] == "Impact"
        identity = ("trek-impact-" + str(a["FID"]) if impact
                    else "iau-" + url.rsplit("/", 1)[-1] if "/Feature/" in url else "trek-" + str(a["FID"]))
        records.append({
            "id": identity,
            "name": a["LABEL"].strip(),
            "category": "impact" if impact else "natural_feature",
            "feature_type": a["type"],
            "latitude_deg": lat,
            "longitude_deg": (lon + 180) % 360 - 180,
            "boundary": {"kind": "approximate_circle" if radius else "point", "radius_km": radius},
            "location_uncertainty_km": None,
            "notes": ("Published Moon Trek impact location, not a verified hardware footprint. "
                      "Location uncertainty is not quantified in this source."
                      if impact else "Moon Trek nomenclature centre and diameter; circular extent is approximate, "
                      "not a surveyed boundary. Label spelling follows Moon Trek."),
            "sources": [
                {"title": "NASA Moon Trek combined south-polar nomenclature", "url": SERVICE,
                 "record_id": str(a["FID"])},
                {"title": "Mission reference" if impact else "Feature reference", "url": url},
            ],
        })
        if impact and a["FID"] in (3, 4):
            records[-1]["notes"] += (
                " The source layer also contains a differing unofficial LCROSS label; "
                "this record preserves the explicit Impact entry, not a highest-accuracy reconstruction."
            )
    # Supplemental verified locations absent/outdated in the February 2024 Trek layer.
    records.extend([
        {
            "id": "im1-odysseus", "name": "IM-1 Odysseus lander", "category": "lander",
            "feature_type": "Robotic lander", "latitude_deg": -80.13, "longitude_deg": 1.44,
            "boundary": {"kind": "point", "radius_km": 0}, "location_uncertainty_km": None,
            "notes": "LRO-observed landing location, February 2024. Coordinates published to 0.01 degree; "
                     "precision is not a quantified uncertainty. No separate payload/rover locations inferred.",
            "sources": [{"title": "NASA: LRO images Odysseus (2024-02-26)",
                         "url": "https://www.nasa.gov/missions/lro/"
                                "nasas-lro-images-intuitive-machines-odysseus-lander/"}],
        },
        {
            "id": "im2-athena", "name": "IM-2 Athena lander", "category": "lander",
            "feature_type": "Robotic lander", "latitude_deg": -84.7906, "longitude_deg": 29.1957,
            "boundary": {"kind": "point", "radius_km": 0}, "location_uncertainty_km": None,
            "notes": "LROC-observed landing location, March 2025; lander came to rest on its side. "
                     "Location uncertainty is not quantified. No separate payload/rover locations inferred.",
            "sources": [{"title": "NASA/GSFC/ASU LROC: IM-2 Athena Seen Obliquely (2025-03-10)",
                         "url": "https://www.lroc.asu.edu/images/1408"}],
        },
    ])
    return sorted(records, key=lambda p: p["id"])


def main():
    with urlopen(QUERY, timeout=60) as response:
        raw = response.read()
    records = build(raw)
    with urlopen(PITS_URL, timeout=60) as response:
        pit_survey = survey_pits(response.read())
    now = datetime.now(timezone.utc)
    output = {
        "version": "south-pole-" + now.strftime("%Y%m%d"),
        "retrieved_at_utc": now.isoformat(),
        "source_query_url": QUERY,
        "source_sha256": hashlib.sha256(raw).hexdigest(),
        "pit_atlas_survey": pit_survey,
        "coverage": {"south_latitude_deg": -90, "north_latitude_deg": -80,
                     "selection": "footprint_intersects_cap", "complete": False},
        "points_of_interest": records,
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(output, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Wrote {len(records)} POIs to {OUTPUT}")


if __name__ == "__main__":
    main()
