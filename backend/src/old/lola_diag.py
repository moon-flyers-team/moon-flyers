"""Prints COPC header/CRS info for a few LOLA tiles. Run: python lola_diag.py"""
import numpy as np
from laspy import CopcReader
from pystac_client import Client

STAC_URL = "https://stac.astrogeology.usgs.gov/api"
SITES = [(-89.9, 0.0), (0.0, 10.0), (60.0, 100.0)]  # (lat, lon)

cat = Client.open(STAC_URL)
for lat, lon in SITES:
    print(f"\n===== site lat {lat} lon {lon} =====")
    try:
        items = list(cat.search(collections=["lunar_orbiter_laser_altimeter"],
                                bbox=[lon - 0.01, lat - 0.01, lon + 0.01, lat + 0.01]).items())
        print("items found:", [i.id for i in items])
        it = items[0]
        print("item bbox:", it.bbox)
        print("assets:", {k: a.href for k, a in it.assets.items()})
        href = next(a.href for a in it.assets.values()
                    if a.href.lower().endswith(".laz") or "copc" in a.href.lower())
        if href.startswith("s3://"):
            b, _, k = href[5:].partition("/")
            href = f"https://{b}.s3.us-west-2.amazonaws.com/{k}"
        with CopcReader.open(href) as r:
            h = r.header
            print("mins:", h.mins, "\nmaxs:", h.maxs)
            print("scales:", h.scales, "offsets:", h.offsets)
            print("point_count:", h.point_count)
            print("dimensions:", list(h.point_format.dimension_names))
            try:
                print("crs:", h.parse_crs().to_wkt()[:400])
            except Exception as e:
                print("crs error:", repr(e))
            pts = r.query(level=0)
            n = min(5, len(pts))
            print("root node points:", len(pts))
            for name in ("x", "y", "z"):
                a = np.asarray(getattr(pts, name))
                print(f"{name}: first {a[:n]}  min {a.min():.4f} max {a.max():.4f}")
    except Exception as e:
        print("FAILED:", repr(e))