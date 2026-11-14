"""Local terrain horizon for a lunar surface site from official LOLA gridded DEMs.

Fast alternative to the raw-point (COPC) version: the DEM files live on local
disk and are memory-mapped, so a query takes tens of milliseconds once warm.

Usage:
    python lunar_horizon_dem.py setup      # one-off: download ~15.5 GB of LDEM IMG files
    python lunar_horizon_dem.py calibrate  # one-off: determine polar grid orientation
    python lunar_horizon_dem.py demo       # run horizon() twice and print timing

    from lunar_horizon_dem import horizon
    out = horizon(-89.9, 0.0)

Data (LOLA Gridded Data Records, 16-bit little-endian rasters, height in metres
= DN * 0.5 above the 1737.4 km reference sphere, same datum as Horizons):
    * 4 global tiles at 256 px/deg (118 m), simple cylindrical, pixel-registered
    * polar stereographic grids, 80 deg to pole at 20 m and 87.5 deg to pole at 5 m

Dependencies: numpy. Only `setup` needs requests; only `calibrate` needs
laspy[lazrs], pystac-client (it compares the DEMs against raw LOLA points).
Set LOLA_DEM_DIR to change where the files live (default ./lola_dem).

Method: the observer stands on the DEM at the site (+ height_above_terrain).
For each of 360 azimuths a ray is walked outward over the sphere; the DEM height
is looked up (finest grid first, bilinear) and the elevation angle above the
observer's local horizontal plane (perpendicular to the vector from the Moon's
centre, curvature included) is computed. The horizon is the max along each ray.
"""
import json
import math
import os
import sys
import time

import numpy as np

# --------------------------------------------------------------------------
# Constants
# --------------------------------------------------------------------------
DATA_DIR = os.environ.get("LOLA_DEM_DIR", "lola_dem")
MOON_RADIUS_M = 1_737_400.0

BASE_CYL = "https://imbrium.mit.edu/DATA/LOLA_GDR/CYLINDRICAL/IMG/"
BASE_POLAR = "https://imbrium.mit.edu/DATA/LOLA_GDR/POLAR/IMG/"

# (name, lat_min, lat_max, lon_min, lon_max); longitudes east-positive, 0..360
CYL_TILES = [
    ("LDEM_256_00N_90N_000_180", 0.0, 90.0, 0.0, 180.0),
    ("LDEM_256_00N_90N_180_360", 0.0, 90.0, 180.0, 360.0),
    ("LDEM_256_90S_00S_000_180", -90.0, 0.0, 0.0, 180.0),
    ("LDEM_256_90S_00S_180_360", -90.0, 0.0, 180.0, 360.0),
]
# (name, hemisphere sign, latitude limit in degrees, finest first)
POLAR_GRIDS = [
    ("LDEM_875N_5M", +1, 87.5),
    ("LDEM_875S_5M", -1, 87.5),
    ("LDEM_80N_20M", +1, 80.0),
    ("LDEM_80S_20M", -1, 80.0),
]

# Polar grid axis conventions: (swap_axes, sign_col, sign_row). The label does
# not say which one the files use, so `calibrate` picks the one that matches raw
# LOLA points.
VARIANTS = [(sw, sx, sy) for sw in (False, True) for sx in (1, -1) for sy in (1, -1)]

# Ray sampling: ground step = max(STEP_MIN_M, STEP_FRAC * distance).
STEP_MIN_M = 20.0
STEP_FRAC = 0.02

# Slope: fitted over a baseline (diameter of a ring of 8 DEM samples around the
# site) of max(SLOPE_MIN_BASELINE_M, SLOPE_BASELINE_PIXELS * pixel size of the
# finest grid at the site). That is 20 m on the 5 m polar grid, 40 m on the
# 20 m grid and about 237 m on the 118 m global grid. Below ~2 pixels the slope
# would only reflect the interpolation between pixels, not the terrain.
SLOPE_MIN_BASELINE_M = 20.0
SLOPE_BASELINE_PIXELS = 2.0
SLOPE_FLAT_DEG = 0.01  # below this the downslope azimuth is reported as None


# --------------------------------------------------------------------------
# Geometry helpers
# --------------------------------------------------------------------------
def _frame(lat_deg, lon_deg):
    """East, north, up unit vectors (Moon-fixed Cartesian) at a lat/lon."""
    p, l = math.radians(lat_deg), math.radians(lon_deg)
    up = np.array([math.cos(p) * math.cos(l), math.cos(p) * math.sin(l), math.sin(p)])
    east = np.array([-math.sin(l), math.cos(l), 0.0])
    north = np.array([-math.sin(p) * math.cos(l), -math.sin(p) * math.sin(l), math.cos(p)])
    return east, north, up


def _bilinear(mm, fy, fx):
    """Bilinear interpolation in a 2D array at fractional (row, col) = (fy, fx),
    where integer coordinates are pixel centres. Indices are clamped to the edge."""
    h, w = mm.shape
    y0 = np.floor(fy).astype(np.int64)
    x0 = np.floor(fx).astype(np.int64)
    ty, tx = fy - y0, fx - x0
    y0c, y1c = np.clip(y0, 0, h - 1), np.clip(y0 + 1, 0, h - 1)
    x0c, x1c = np.clip(x0, 0, w - 1), np.clip(x0 + 1, 0, w - 1)
    v00 = mm[y0c, x0c].astype(np.float64)
    v01 = mm[y0c, x1c].astype(np.float64)
    v10 = mm[y1c, x0c].astype(np.float64)
    v11 = mm[y1c, x1c].astype(np.float64)
    return (v00 * (1 - tx) + v01 * tx) * (1 - ty) + (v10 * (1 - tx) + v11 * tx) * ty


# --------------------------------------------------------------------------
# PDS3 label + raster access
# --------------------------------------------------------------------------
def _parse_label(path):
    """Minimal PDS3 label parser. Returns {KEY: (value_string, unit_string)}
    using the first occurrence of each key."""
    vals = {}
    with open(path, "r", errors="ignore") as f:
        for line in f:
            if "=" not in line:
                continue
            key, _, rest = line.partition("=")
            rest = rest.split("/*")[0].strip()
            unit = ""
            if "<" in rest:
                rest, _, unit = rest.partition("<")
                unit = unit.strip(" >")
            vals.setdefault(key.strip(), (rest.strip().strip('"'), unit.upper()))
    return vals


def _num(label, key, default=None):
    if key not in label:
        return default
    try:
        return float(label[key][0])
    except ValueError:
        return default


def _open_raster(base):
    """Memory-map NAME.IMG using the dimensions in NAME.LBL.
    Returns (memmap, label, scaling_factor)."""
    lbl, img = base + ".LBL", base + ".IMG"
    for p in (lbl, img):
        if not os.path.exists(p):
            raise FileNotFoundError(f"{p} not found. Run: python lunar_horizon_dem.py setup")
    label = _parse_label(lbl)
    lines, samples = int(_num(label, "LINES")), int(_num(label, "LINE_SAMPLES"))
    if int(_num(label, "SAMPLE_BITS", 16)) != 16:
        raise RuntimeError(f"{lbl}: only 16-bit rasters are supported")
    dtype = ">i2" if "MSB" in label.get("SAMPLE_TYPE", ("LSB", ""))[0].upper() else "<i2"
    if os.path.getsize(img) != lines * samples * 2:
        raise RuntimeError(f"{img}: size {os.path.getsize(img)} != {lines}x{samples}x2 (incomplete download?)")
    mm = np.memmap(img, dtype=dtype, mode="r", shape=(lines, samples))
    return mm, label, _num(label, "SCALING_FACTOR", 0.5)


class _CylGrid:
    """Simple cylindrical, pixel-registered tile covering [lat_min, lat_max] x
    [lon_min, lon_max]; row 0 is at lat_max, column 0 at lon_min."""

    def __init__(self, base, lat_min, lat_max, lon_min, lon_max):
        self.name = os.path.basename(base)
        self.mm, _, self.scaling = _open_raster(base)
        lines, samples = self.mm.shape
        self.ppd = samples / (lon_max - lon_min)
        if abs(lines / (lat_max - lat_min) - self.ppd) > 1e-6:
            raise RuntimeError(f"{self.name}: raster shape does not match its lat/lon bounds")
        self.lat_min, self.lat_max, self.lon_min, self.lon_max = lat_min, lat_max, lon_min, lon_max

    def pixel_size(self, lat, lon):
        """North-south pixel size in metres if this tile covers the point, else None."""
        lon = lon % 360.0
        if (self.lat_min <= lat <= self.lat_max) and (self.lon_min <= lon < self.lon_max):
            return MOON_RADIUS_M * math.pi / 180.0 / self.ppd
        return None

    def sample(self, lat, lon):
        out = np.full(lat.shape, np.nan)
        lon = lon % 360.0
        m = ((lat >= self.lat_min) & (lat <= self.lat_max)
             & (lon >= self.lon_min) & (lon < self.lon_max))
        if m.any():
            fy = (self.lat_max - lat[m]) * self.ppd - 0.5
            fx = (lon[m] - self.lon_min) * self.ppd - 0.5
            out[m] = _bilinear(self.mm, fy, fx) * self.scaling
        return out


class _PolarGrid:
    """Polar stereographic grid (true scale at the pole, sphere radius 1737.4 km),
    covering |lat| >= lat_limit in one hemisphere. The pole sits at the image
    centre. Axis orientation is one of VARIANTS."""

    def __init__(self, base, sign, lat_limit, variant=0):
        self.name = os.path.basename(base)
        self.mm, label, self.scaling = _open_raster(base)
        self.sign, self.lat_limit, self.variant = sign, lat_limit, variant
        lines, samples = self.mm.shape
        self.cy, self.cx = lines / 2.0 - 0.5, samples / 2.0 - 0.5  # pole at the geometric centre
        # Pixel size: label MAP_SCALE if sensible, else from the image extent.
        geom = 2 * MOON_RADIUS_M * math.tan(math.radians(90.0 - lat_limit) / 2) / (lines / 2.0)
        scale = _num(label, "MAP_SCALE")
        if scale is not None and "KM" in label["MAP_SCALE"][1]:
            scale *= 1000.0
        if scale is None or abs(scale / geom - 1.0) > 0.05:
            scale = geom
        self.scale = scale

    def pixel_size(self, lat, lon):
        """Pixel size in metres if this grid covers the point, else None."""
        return self.scale if self.sign * lat >= self.lat_limit else None

    def sample(self, lat, lon):
        out = np.full(lat.shape, np.nan)
        m = self.sign * lat >= self.lat_limit
        if not m.any():
            return out
        rho = 2 * MOON_RADIUS_M * np.tan(np.radians(90.0 - np.abs(lat[m])) / 2)
        lam = np.radians(lon[m])  # central longitude is 0
        u, v = rho * np.sin(lam), rho * np.cos(lam)
        swap, sx, sy = VARIANTS[self.variant]
        a, b = (v, u) if swap else (u, v)
        col, row = self.cx + sx * a / self.scale, self.cy + sy * b / self.scale
        lines, samples = self.mm.shape
        ok = (row >= -0.5) & (row <= lines - 0.5) & (col >= -0.5) & (col <= samples - 0.5)
        vals = np.full(rho.shape, np.nan)
        if ok.any():
            vals[ok] = _bilinear(self.mm, row[ok], col[ok]) * self.scaling
        out[m] = vals
        return out


class DEM:
    """Stack of grids, finest first. sample(lat, lon) -> height (m above the
    1737.4 km sphere), NaN where no grid covers the location."""

    def __init__(self, data_dir=DATA_DIR, cyl_tiles=CYL_TILES, polar_grids=POLAR_GRIDS,
                 calibration=None):
        if calibration is None:
            cal_path = os.path.join(data_dir, "calibration.json")
            if not os.path.exists(cal_path):
                raise FileNotFoundError(f"{cal_path} not found. Run: python lunar_horizon_dem.py calibrate")
            with open(cal_path) as f:
                calibration = json.load(f)
        self.grids = []
        for name, sign, lim in polar_grids:
            self.grids.append(_PolarGrid(os.path.join(data_dir, name), sign, lim,
                                         variant=int(calibration[name])))
        for name, la0, la1, lo0, lo1 in cyl_tiles:
            self.grids.append(_CylGrid(os.path.join(data_dir, name), la0, la1, lo0, lo1))
        self.last_counts = {}

    def pixel_size(self, lat, lon):
        """Pixel size (m) of the finest grid covering the point, or None."""
        for g in self.grids:
            px = g.pixel_size(lat, lon)
            if px is not None:
                return px
        return None

    def sample(self, lat, lon):
        lat, lon = np.asarray(lat, dtype=np.float64), np.asarray(lon, dtype=np.float64)
        shape = lat.shape
        lat, lon = lat.ravel(), lon.ravel()
        out = np.full(lat.shape, np.nan)
        self.last_counts = {}
        for g in self.grids:
            todo = np.isnan(out)
            if not todo.any():
                break
            vals = g.sample(lat[todo], lon[todo])
            got = ~np.isnan(vals)
            if got.any():
                idx = np.flatnonzero(todo)[got]
                out[idx] = vals[got]
                self.last_counts[g.name] = int(got.sum())
        return out.reshape(shape)


_DEM_CACHE = None


def _get_dem():
    global _DEM_CACHE
    if _DEM_CACHE is None:
        _DEM_CACHE = DEM(DATA_DIR)
    return _DEM_CACHE


# --------------------------------------------------------------------------
# Public function
# --------------------------------------------------------------------------
def _ray_distances(min_range_m, max_range_m):
    """Ground distances along a ray: 20 m steps near the observer, then 2% steps."""
    s = [max(min_range_m, STEP_MIN_M)]
    while s[-1] < max_range_m:
        s.append(s[-1] + max(STEP_MIN_M, STEP_FRAC * s[-1]))
    return np.array(s)


def _site_slope(dem, lat0, lon0, baseline_m):
    """Slope and downslope azimuth at the site from the DEM.

    Heights are sampled on a ring of 8 points (every 45 degrees) of diameter
    baseline_m around the site, and a plane is least-squares fitted through
    them. The plane's gradient (dh/dEast, dh/dNorth) gives the slope angle;
    the downslope azimuth is the direction of -gradient, which is also the
    horizontal part of the surface normal. Azimuth: north = 0, east = 90.
    Returns (slope_deg, slope_az_deg); slope_az_deg is None on flat ground and
    both are None if the ring is not fully covered by the DEM."""
    east, north, up = _frame(lat0, lon0)
    r = baseline_m / 2.0
    az = np.radians(np.arange(0.0, 360.0, 45.0))
    dirs = np.sin(az)[:, None] * east + np.cos(az)[:, None] * north
    theta = r / MOON_RADIUS_M
    u = np.cos(theta) * up + np.sin(theta) * dirs
    lat = np.degrees(np.arcsin(np.clip(u[:, 2], -1.0, 1.0)))
    lon = np.degrees(np.arctan2(u[:, 1], u[:, 0]))
    h = dem.sample(lat, lon)
    if np.isnan(h).any():
        return None, None
    x, y = r * np.sin(az), r * np.cos(az)  # east, north offsets (m); both sum to zero
    g_east = float((h * x).sum() / (x * x).sum())
    g_north = float((h * y).sum() / (y * y).sum())
    slope = math.degrees(math.atan(math.hypot(g_east, g_north)))
    if slope < SLOPE_FLAT_DEG:
        return slope, None
    return slope, round(math.degrees(math.atan2(-g_east, -g_north)), 6) % 360.0


def horizon(latitude_deg, longitude_deg, max_range_km=50.0,
            height_above_terrain=0.0, min_range_m=20.0, verbose=False, dem=None):
    """Terrain horizon seen from a lunar surface site.

    Args:
        latitude_deg: -90..90 (planetocentric).
        longitude_deg: -180..180, east positive.
        max_range_km: terrain farther than this (straight-line distance from the
            observer) is ignored, so mountains beyond it cannot raise the
            horizon. Rays are walked out to this distance. Larger values are
            more accurate for distant massifs but cost proportionally more.
        height_above_terrain: observer height (m) above the local terrain.
        min_range_m: terrain closer than this (m) is ignored and rays start at
            this distance. Features smaller than this are not resolved.
        verbose: print diagnostics and timing.

    Returns dict:
        horizon_azimuth_deg: [0.0 .. 359.0], north=0, east=90.
        horizon_elevation_deg: same length; elevation of the terrain relative to
            the plane perpendicular to the vector to the Moon's centre,
            measured from the observer. May be negative.
        altitude_m: terrain altitude of the coordinates above the 1737.4 km
            reference sphere (does NOT include height_above_terrain).
        horizon_gap_fraction: fraction of azimuths with no valid terrain samples
            (interpolated); normally 0.0 with a DEM.
        slope_deg: terrain slope at the site, degrees from horizontal, fitted
            over a baseline of 20 m to ~237 m depending on the DEM resolution
            at the site (see SLOPE_* constants). Computed from the DEM, not
            measured by the instrument.
        slope_az_deg: azimuth of the downslope direction (horizontal part of
            the surface normal), north = 0, east = 90. None on flat ground
            (slope below 0.01 degrees) where it is undefined.
    """
    if not -90.0 <= latitude_deg <= 90.0:
        raise ValueError("latitude_deg must be within -90..90")
    if max_range_km <= 0 or min_range_m < 0 or height_above_terrain < 0:
        raise ValueError("max_range_km must be > 0; min_range_m and height_above_terrain must be >= 0")
    t0 = time.perf_counter()
    dem = dem or _get_dem()
    lat0 = float(latitude_deg)
    lon0 = ((float(longitude_deg) + 180.0) % 360.0) - 180.0

    alt = dem.sample(np.array([lat0]), np.array([lon0]))[0]
    if np.isnan(alt):
        raise RuntimeError("No DEM coverage at the site")

    east, north, up = _frame(lat0, lon0)
    s = _ray_distances(min_range_m, max_range_km * 1000.0)
    az = np.radians(np.arange(360.0))
    dirs = np.sin(az)[:, None] * east + np.cos(az)[:, None] * north        # (360, 3)
    theta = s / MOON_RADIUS_M                                              # (nS,)
    # Unit vectors of the ray points on the sphere: (360, nS, 3)
    u = np.cos(theta)[None, :, None] * up + np.sin(theta)[None, :, None] * dirs[:, None, :]
    lat = np.degrees(np.arcsin(np.clip(u[..., 2], -1.0, 1.0)))
    lon = np.degrees(np.arctan2(u[..., 1], u[..., 0]))
    t1 = time.perf_counter()

    h = dem.sample(lat, lon)                                               # (360, nS)
    t2 = time.perf_counter()

    obs = (MOON_RADIUS_M + alt + height_above_terrain) * up
    d = (MOON_RADIUS_M + h)[..., None] * u - obs                           # metres
    dist = np.linalg.norm(d, axis=-1)
    elev = np.degrees(np.arcsin(np.clip((d @ up) / dist, -1.0, 1.0)))
    bad = np.isnan(h) | (dist > max_range_km * 1000.0) | (dist < min_range_m)
    elev = np.where(bad, -np.inf, elev)
    prof = elev.max(axis=1)
    gap = ~np.isfinite(prof)
    prof[gap] = np.nan
    if gap.all():
        raise RuntimeError("No valid terrain samples in the min/max range window")
    if gap.any():
        idx = np.arange(360)
        prof[gap] = np.interp(idx[gap], idx[~gap], prof[~gap], period=360)
    grids_used = dict(dem.last_counts)
    px = dem.pixel_size(lat0, lon0) if hasattr(dem, "pixel_size") else None
    baseline = max(SLOPE_MIN_BASELINE_M, SLOPE_BASELINE_PIXELS * (px or 0.0))
    slope, slope_az = _site_slope(dem, lat0, lon0, baseline)
    t3 = time.perf_counter()

    if verbose:
        print(f"altitude: {alt:.1f} m   samples: {h.size}   grids used: {grids_used}")
        print("slope: " + ("n/a" if slope is None else f"{slope:.2f} deg, downslope azimuth "
              f"{'undefined' if slope_az is None else f'{slope_az:.1f} deg'} "
              f"(baseline {baseline:.0f} m)"))
        print(f"empty azimuths: {int(gap.sum())}/360")
        print(f"horizon elevation: min {prof.min():.2f}  max {prof.max():.2f} deg")
        print(f"timing (s): geometry {t1 - t0:.3f} | DEM lookup {t2 - t1:.3f} | "
              f"elevation {t3 - t2:.3f} | total {t3 - t0:.3f}")

    return {
        "horizon_azimuth_deg": [float(i) for i in range(360)],
        "horizon_elevation_deg": [float(v) for v in prof],
        "altitude_m": float(alt),
        "horizon_gap_fraction": float(gap.mean()),
        "slope_deg": None if slope is None else float(slope),
        "slope_az_deg": None if slope_az is None else float(slope_az),
    }


# --------------------------------------------------------------------------
# One-off setup: download
# --------------------------------------------------------------------------
def _download(url, dest):
    import requests

    head = requests.head(url, allow_redirects=True, timeout=60)
    head.raise_for_status()
    total = int(head.headers.get("Content-Length", 0))
    if total and os.path.exists(dest) and os.path.getsize(dest) == total:
        print(f"have {os.path.basename(dest)}")
        return
    part = dest + ".part"
    done = os.path.getsize(part) if os.path.exists(part) else 0
    headers = {"Range": f"bytes={done}-"} if done else {}
    with requests.get(url, headers=headers, stream=True, timeout=60) as r:
        r.raise_for_status()
        if done and r.status_code != 206:  # server ignored the range request
            done = 0
        with open(part, "ab" if done else "wb") as f:
            last = time.time()
            for chunk in r.iter_content(chunk_size=8 * 1024 * 1024):
                f.write(chunk)
                done += len(chunk)
                if time.time() - last > 5:
                    print(f"  {os.path.basename(dest)}: {done / 1e6:.0f} / {total / 1e6:.0f} MB")
                    last = time.time()
    os.replace(part, dest)
    print(f"downloaded {os.path.basename(dest)}")


def setup(data_dir=DATA_DIR):
    """Download the LDEM IMG + LBL files (about 15.5 GB). Resumable."""
    os.makedirs(data_dir, exist_ok=True)
    jobs = []
    for name, _, _ in POLAR_GRIDS:
        jobs += [(BASE_POLAR + name + ext, os.path.join(data_dir, name + ext)) for ext in (".LBL", ".IMG")]
    for name, *_ in CYL_TILES:
        jobs += [(BASE_CYL + name + ext, os.path.join(data_dir, name + ext)) for ext in (".LBL", ".IMG")]
    for url, dest in jobs:
        _download(url, dest)
    for name, *_ in [*POLAR_GRIDS, *CYL_TILES]:  # verifies label vs file size
        _open_raster(os.path.join(data_dir, name))
    print("setup complete; next: python lunar_horizon_dem.py calibrate")


# --------------------------------------------------------------------------
# One-off calibration against raw LOLA points
# --------------------------------------------------------------------------
STAC_URL = "https://stac.astrogeology.usgs.gov/api"
STAC_COLLECTION = "lunar_orbiter_laser_altimeter"


def _search_boxes(lat, lon, radius_km):
    """Lon/lat boxes covering a spherical cap (used only to find tiles)."""
    ang = math.degrees(radius_km * 1000.0 / MOON_RADIUS_M)
    lat_min, lat_max = lat - ang, lat + ang
    if lat_max >= 90.0 or lat_min <= -90.0:
        return [(-180.0, max(lat_min, -90.0), 180.0, min(lat_max, 90.0))]
    s = math.sin(math.radians(ang)) / math.cos(math.radians(lat))
    half = math.degrees(math.asin(min(1.0, s)))
    lo, hi = lon - half, lon + half
    if lo < -180.0:
        return [(lo + 360.0, lat_min, 180.0, lat_max), (-180.0, lat_min, hi, lat_max)]
    if hi > 180.0:
        return [(lo, lat_min, 180.0, lat_max), (-180.0, lat_min, hi - 360.0, lat_max)]
    return [(lo, lat_min, hi, lat_max)]


def _raw_points(lat, lon, half_km=15.0, resolution_m=100.0):
    """Raw LOLA points (Moon-fixed Cartesian metres) near a site, from the AWS COPC data."""
    from laspy import CopcReader
    from laspy.copc import Bounds
    from pystac_client import Client

    _, _, up = _frame(lat, lon)
    site = MOON_RADIUS_M * up
    pad = half_km * 1000.0 + 11_000.0 * np.abs(up)
    lo, hi = site - pad, site + pad
    catalog = Client.open(STAC_URL)
    urls = {}
    for box in _search_boxes(lat, lon, half_km):
        for item in catalog.search(collections=[STAC_COLLECTION], bbox=list(box)).items():
            urls[item.id] = item.assets["data"].href
    pts = []
    for url in urls.values():
        with CopcReader.open(url) as rd:
            if np.any(hi < np.asarray(rd.header.mins)) or np.any(lo > np.asarray(rd.header.maxs)):
                continue
            p = rd.query(Bounds(mins=lo, maxs=hi), resolution=resolution_m)
            if len(p):
                pts.append(np.column_stack([np.asarray(p.x), np.asarray(p.y), np.asarray(p.z)]))
    if not pts:
        raise RuntimeError(f"No raw points near {lat}, {lon}")
    return np.concatenate(pts)


def _lat_lon_height(xyz):
    r = np.linalg.norm(xyz, axis=1)
    return (np.degrees(np.arcsin(xyz[:, 2] / r)), np.degrees(np.arctan2(xyz[:, 1], xyz[:, 0])),
            r - MOON_RADIUS_M)


def calibrate_orientation(grid, lat, lon, h):
    """Try all 8 axis conventions on a polar grid; return (best_variant, mean_abs_errors)."""
    errs = []
    for v in range(len(VARIANTS)):
        grid.variant = v
        dh = grid.sample(lat, lon) - h
        errs.append(float(np.nanmean(np.abs(dh))) if np.isfinite(dh).any() else float("inf"))
    best = int(np.argmin(errs))
    grid.variant = best
    return best, errs


def calibrate(data_dir=DATA_DIR):
    """Determine each polar grid's axis orientation by comparing DEM heights with
    raw LOLA points, write calibration.json, then spot-check the global tiles."""
    sites = {+1: [(89.0, 0.0), (88.5, 120.0)], -1: [(-89.0, 0.0), (-88.5, 120.0)]}
    raw = {}
    for sign, lst in sites.items():
        pts = [_raw_points(la, lo) for la, lo in lst]
        raw[sign] = _lat_lon_height(np.concatenate(pts))
        print(f"{'north' if sign > 0 else 'south'}: {len(raw[sign][0])} raw points")
    cal = {}
    for name, sign, lim in POLAR_GRIDS:
        grid = _PolarGrid(os.path.join(data_dir, name), sign, lim)
        best, errs = calibrate_orientation(grid, *raw[sign])
        srt = sorted(errs)
        print(f"{name}: best variant {best} (mean |dh| {errs[best]:.1f} m; "
              f"next best {srt[1]:.1f} m; all: {[round(e, 1) for e in errs]})")
        if not srt[1] > 3 * srt[0]:
            print("  WARNING: orientation is not clearly distinguished, check this grid by hand")
        cal[name] = best
    with open(os.path.join(data_dir, "calibration.json"), "w") as f:
        json.dump(cal, f)

    dem = DEM(data_dir, calibration=cal)
    for la, lo in [(5.0, 20.0), (-40.0, 250.0), (60.0, 100.0), (-78.0, 300.0)]:
        pts = _raw_points(la, lo, half_km=10.0, resolution_m=50.0)
        lat, lon, h = _lat_lon_height(pts)
        dh = dem.sample(lat, lon) - h
        print(f"global check ({la}, {lo}): median |dh| {np.nanmedian(np.abs(dh)):.1f} m, "
              f"p95 {np.nanpercentile(np.abs(dh), 95):.1f} m over {len(h)} points")
    print("calibration saved")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "demo"
    if cmd == "setup":
        setup()
    elif cmd == "calibrate":
        calibrate()
    else:
        for _ in range(2):  # second call shows warm timing
            out = horizon(-89.9, 0.0, max_range_km=50.0, height_above_terrain=2.0, verbose=True)
        print({k: v for k, v in out.items() if not isinstance(v, list)})