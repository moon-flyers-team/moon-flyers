"""LOLA dataset inventory and validation, shared by host preparation and API startup.

Observed from the official archive products (not assumed from the PDS labels):

* cylindrical tiles are stored in *degrees* (GCS_Moon_2000, 1/256 degree pixels),
* polar tiles are polar stereographic metres centred on the pole,
* every product is signed Int16 with band scale 0.5, so ``raw * 0.5`` is terrain
  altitude in metres above the 1 737 400 m reference sphere. The label's radius
  OFFSET must NOT be added to terrain altitudes.

This module validates and samples; it does not calculate a horizon.
"""

from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path
import re
import statistics

import numpy as np
import rasterio
from rasterio.transform import rowcol
from rasterio.warp import transform

BASE_URL = "https://imbrium.mit.edu/DATA/LOLA_GDR"
MOON_RADIUS_M = 1_737_400.0
HEIGHT_SCALE = 0.5
SCHEMA_VERSION = 2
CYLINDRICAL_PIXEL_DEG = 1 / 256
LONLAT_SPHERE = (f"+proj=longlat +a={MOON_RADIUS_M} +b={MOON_RADIUS_M} "
                 "+no_defs +type=crs")

# Independent cross-product placement check: at these latitudes the polar and
# global products overlap, so the same lon/lat must give similar altitudes.
CROSS_CHECK_LON_STEP = 30
CROSS_CHECK_MIN_SAMPLES = 8
CROSS_CHECK_TOLERANCE_M = 1_000.0
CROSS_CHECK_LATITUDE = {"LDEM_875N_5M": 88.0, "LDEM_875S_5M": -88.0,
                        "LDEM_80N_20M": 83.0, "LDEM_80S_20M": -83.0}


@dataclass(frozen=True)
class Product:
    name: str
    region: str            # "CYLINDRICAL" (degrees) or "POLAR" (metres)
    download_bytes: int
    width: int
    height: int
    pixel: float           # degrees for cylindrical, metres for polar
    lon_min: float         # cylindrical west edge
    lat_max: float         # cylindrical north edge
    centre_lat: float
    centre_lon: float

    @property
    def url(self) -> str:
        return f"{BASE_URL}/{self.region}/JP2/{self.name}.JP2"

    @property
    def projected(self) -> bool:
        return self.region == "POLAR"

    @property
    def origin_x(self) -> float:
        return -self.width * self.pixel / 2 if self.projected else self.lon_min

    @property
    def origin_y(self) -> float:
        return self.height * self.pixel / 2 if self.projected else self.lat_max


# Download sizes come from the official archive index, so a changed or truncated
# release is rejected instead of silently producing a different dataset.
PRODUCTS = (
    Product("LDEM_256_00N_90N_000_180", "CYLINDRICAL", 427545233, 46080, 23040,
            CYLINDRICAL_PIXEL_DEG, 0, 90, 45, 90),
    Product("LDEM_256_00N_90N_180_360", "CYLINDRICAL", 418539506, 46080, 23040,
            CYLINDRICAL_PIXEL_DEG, 180, 90, 45, 270),
    Product("LDEM_256_90S_00S_000_180", "CYLINDRICAL", 500914193, 46080, 23040,
            CYLINDRICAL_PIXEL_DEG, 0, 0, -45, 90),
    Product("LDEM_256_90S_00S_180_360", "CYLINDRICAL", 500968345, 46080, 23040,
            CYLINDRICAL_PIXEL_DEG, 180, 0, -45, 270),
    Product("LDEM_80N_20M", "POLAR", 213752081, 30400, 30400, 20, 0, 90, 90, 0),
    Product("LDEM_80S_20M", "POLAR", 267689172, 30400, 30400, 20, 0, -90, -90, 0),
    Product("LDEM_875N_5M", "POLAR", 159380778, 30336, 30336, 5, 0, 90, 90, 0),
    Product("LDEM_875S_5M", "POLAR", 185186696, 30336, 30336, 5, 0, -90, -90, 0),
)
PRODUCT_BY_NAME = {p.name: p for p in PRODUCTS}


def cylindrical_product(lon_deg: float, lat_deg: float) -> Product:
    """The global cylindrical tile containing an east-positive lon/lat."""
    south = lat_deg < 0
    west = lon_deg % 360 >= 180
    return PRODUCT_BY_NAME[
        f"LDEM_256_{'90S_00S' if south else '00N_90N'}_"
        f"{'180_360' if west else '000_180'}"]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _lunar_sphere(crs) -> None:
    if crs is None:
        raise ValueError("missing CRS")
    wkt = crs.to_wkt()
    ellipsoid = re.search(r'(?:SPHEROID|ELLIPSOID)\["[^"]+",\s*([0-9.]+),\s*([0-9.]+)', wkt)
    if (ellipsoid is None or not math.isclose(float(ellipsoid[1]), MOON_RADIUS_M, abs_tol=0.01)
            or float(ellipsoid[2]) != 0):
        raise ValueError("expected a spherical 1737400 m lunar CRS")


def inspect_raster(path: Path, product: Product, *, tiled: bool = False) -> dict:
    """Check CRS, exact grid placement, height scale and a few decoded samples.

    Placement is verified from the embedded georeferencing, not from the PDS
    label text: some archive labels have inconsistent longitude fields.
    """
    with rasterio.open(path) as ds:
        try:
            _lunar_sphere(ds.crs)
        except ValueError as exc:
            raise ValueError(f"{path.name}: {exc}") from exc
        if ds.crs.is_projected != product.projected:
            raise ValueError(f"{path.name}: expected a {'projected' if product.projected else 'geographic'} CRS")
        if ds.count != 1 or ds.dtypes != ("int16",) or (ds.width, ds.height) != (product.width, product.height):
            raise ValueError(f"{path.name}: unexpected band type or dimensions")
        t = ds.transform
        expected = (product.pixel, 0.0, product.origin_x, 0.0, -product.pixel, product.origin_y)
        if any(not math.isclose(got, want, rel_tol=1e-9, abs_tol=1e-12) for got, want in zip(tuple(t)[:6], expected)):
            raise ValueError(f"{path.name}: unexpected grid origin or pixel size {tuple(t)[:6]}")
        if ds.scales != (HEIGHT_SCALE,) or ds.offsets != (0.0,):
            raise ValueError(f"{path.name}: expected band scale 0.5 and offset 0")
        if ds.nodata is not None and float(ds.nodata) != -32768:
            raise ValueError(f"{path.name}: unexpected nodata value {ds.nodata}")
        if tiled and not ds.profile.get("tiled", False):
            raise ValueError(f"{path.name}: output must be tiled")

        x, y = t @ (ds.width / 2, ds.height / 2)
        lon, lat = transform(ds.crs, LONLAT_SPHERE, [x], [y])
        lon_error = abs((lon[0] - product.centre_lon + 180) % 360 - 180)
        if abs(lat[0] - product.centre_lat) > 0.01 or (not product.projected and lon_error > 0.01):
            raise ValueError(f"{path.name}: raster is misplaced (centre lon={lon[0]}, lat={lat[0]})")

        # Decode only small windows, never a whole raster, so API startup stays cheap.
        for col, row in ((0, 0), (ds.width // 2, ds.height // 2), (ds.width - 8, ds.height - 8)):
            valid = ds.read(1, window=((row, row + 8), (col, col + 8)), masked=True).compressed()
            if valid.size and np.max(np.abs(valid.astype(float) * HEIGHT_SCALE)) > 20000:
                raise ValueError(f"{path.name}: implausible decoded terrain altitude")
        # Record the pixel-to-lon/lat mapping instead of a CRS WKT string: WKT text
        # varies between GDAL/PROJ versions, while this mapping is what readers depend
        # on and is reproduced by the container's own GDAL at startup.
        pixel_lonlat = []
        for col, row in ((0, 0), (ds.width / 2, ds.height / 2), (ds.width - 1, ds.height - 1)):
            cx, cy = t @ (col + 0.5, row + 0.5)
            clon, clat = transform(ds.crs, LONLAT_SPHERE, [cx], [cy])
            pixel_lonlat.append([round(clon[0], 9), round(clat[0], 9)])
        return {
            "transform": [float(v) for v in tuple(t)[:6]],
            "width": ds.width, "height": ds.height, "scale": ds.scales[0],
            "offset": ds.offsets[0], "nodata": float(ds.nodata) if ds.nodata is not None else None,
            "projected": bool(ds.crs.is_projected), "pixel_lonlat": pixel_lonlat,
        }


def metadata_matches(recorded: dict, actual: dict) -> bool:
    """Compare manifest metadata with a fresh inspection, tolerating float noise."""
    for key in ("width", "height", "scale", "offset", "nodata", "projected"):
        if recorded.get(key) != actual.get(key):
            return False
    recorded_transform = recorded.get("transform") or []
    if len(recorded_transform) != 6 or any(
            not math.isclose(a, b, rel_tol=1e-12, abs_tol=1e-12)
            for a, b in zip(recorded_transform, actual["transform"])):
        return False
    recorded_points = recorded.get("pixel_lonlat") or []
    if len(recorded_points) != len(actual["pixel_lonlat"]):
        return False
    return all(abs(a[0] - b[0]) <= 1e-6 and abs(a[1] - b[1]) <= 1e-6
               for a, b in zip(recorded_points, actual["pixel_lonlat"]))


def sample_altitude(path: Path, product: Product, lon_deg: float, lat_deg: float) -> float | None:
    """Terrain altitude in metres at one east-positive lon/lat, or None outside the raster."""
    with rasterio.open(path) as ds:
        if product.projected:
            xs, ys = transform(LONLAT_SPHERE, ds.crs, [lon_deg % 360], [lat_deg])
            x, y = xs[0], ys[0]
        else:
            x, y = lon_deg % 360, lat_deg  # native degrees, 0..360 east as stored
        row, col = rowcol(ds.transform, x, y)
        if not (0 <= row < ds.height and 0 <= col < ds.width):
            return None
        value = ds.read(1, window=((row, row + 1), (col, col + 1)), masked=True)
        if value.mask.all():
            return None
        return float(value[0, 0]) * (ds.scales[0] or 1.0)


def cross_check(polar: Product, polar_path: Path, cylindrical: dict[str, Path]) -> dict:
    """Compare a polar product with the independent global product at the same lon/lat.

    A wrong projection, rotation or pixel-to-latitude mapping shows up as kilometre-scale
    disagreement. This is the placement check that metadata alone cannot provide.
    """
    if polar.name not in CROSS_CHECK_LATITUDE:
        raise ValueError(f"No cross-check latitude for {polar.name}")
    latitude = CROSS_CHECK_LATITUDE[polar.name]
    differences = []
    for lon in range(0, 360, CROSS_CHECK_LON_STEP):
        tile = cylindrical_product(lon, latitude).name
        if tile not in cylindrical:
            continue
        here = sample_altitude(polar_path, polar, lon, latitude)
        there = sample_altitude(cylindrical[tile], PRODUCT_BY_NAME[tile], lon, latitude)
        if here is not None and there is not None:
            differences.append(abs(here - there))
    if len(differences) < CROSS_CHECK_MIN_SAMPLES:
        raise ValueError(f"{polar.name}: only {len(differences)} usable cross-check samples")
    median = statistics.median(differences)
    if median > CROSS_CHECK_TOLERANCE_M:
        raise ValueError(
            f"{polar.name}: polar and global products disagree at {latitude} deg "
            f"(median {median:.0f} m > {CROSS_CHECK_TOLERANCE_M:.0f} m); check CRS handling")
    return {"latitude_deg": latitude, "samples": len(differences),
            "median_abs_difference_m": round(median, 1),
            "max_abs_difference_m": round(max(differences), 1)}


def verify_dataset(directory: Path, *, hashes: bool = False) -> dict:
    """Require a complete manifest and all eight local rasters; never fetch data.

    Full hashing is for explicit offline verification, not application startup.
    Symlinks are rejected so a versioned dataset cannot escape its mount.
    """
    manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    if manifest.get("schema_version") != SCHEMA_VERSION or manifest.get("reference_radius_m") != MOON_RADIUS_M:
        raise ValueError("Unsupported LOLA manifest or reference radius")
    entries = manifest.get("products", [])
    if not isinstance(entries, list) or len(entries) != len(PRODUCTS):
        raise ValueError("Manifest must contain exactly the eight expected LOLA products")
    if {entry.get("name") for entry in entries} != set(PRODUCT_BY_NAME):
        raise ValueError("Manifest must contain exactly the eight expected LOLA products")
    by_name = {entry["name"]: entry for entry in entries}
    for product in PRODUCTS:
        entry = by_name[product.name]
        filename = f"{product.name}.tif"
        if entry.get("file") != filename:
            raise ValueError(f"Invalid raster path for {product.name}")
        path = directory / filename
        if path.is_symlink() or not path.is_file() or path.stat().st_size != entry.get("bytes"):
            raise ValueError(f"Missing, linked or truncated raster: {filename}")
        if not metadata_matches(entry.get("raster") or {}, inspect_raster(path, product, tiled=True)):
            raise ValueError(f"Raster metadata differs from manifest: {filename}")
        if not re.fullmatch(r"[0-9a-f]{64}", str(entry.get("sha256", ""))):
            raise ValueError(f"Invalid checksum for {filename}")
        if hashes and sha256(path) != entry["sha256"]:
            raise ValueError(f"Checksum mismatch: {filename}")
    return manifest
