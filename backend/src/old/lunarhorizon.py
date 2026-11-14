"""Local terrain horizon (azimuth/elevation mask) for a lunar surface site.

Data source: NASA/USGS LOLA Cloud Optimized Point Cloud (COPC) on AWS Open Data,
located through the USGS STAC API and read with HTTPS range requests.

The COPC files store each laser return as Moon-fixed Cartesian X, Y, Z in
METERS (IAU 2015 Moon sphere frame: X toward lon 0/lat 0, Y toward lon 90E,
Z toward the north pole). Verified from the tile headers.

Dependencies: numpy, laspy[lazrs] (>=2.4, for COPC), pystac-client, requests

Method (no gridding):
  1. Find the COPC tiles covering the area around the site (STAC bbox search).
  2. Range-read only the points inside a 3D box around the site.
  3. Estimate the terrain altitude at the site with a small weighted plane fit.
  4. Put the observer at that terrain radius + height_above_terrain.
  5. For every point, compute its azimuth and its elevation angle above the
     observer's local horizontal plane (perpendicular to the vector from the
     Moon's center). Curvature is included automatically because the points
     are real 3D positions on the sphere.
  6. Horizon elevation in each 1 degree azimuth bin = max elevation angle of
     the points in that bin. Empty bins are filled by circular interpolation.
"""
import math
import time
from concurrent.futures import ThreadPoolExecutor

import numpy as np

# --------------------------------------------------------------------------
# Constants
# --------------------------------------------------------------------------
MOON_RADIUS_M = 1_737_400.0  # LOLA / Horizons reference sphere
STAC_URL = "https://stac.astrogeology.usgs.gov/api"
STAC_COLLECTION = "lunar_orbiter_laser_altimeter"

# Points within this distance of the site are read at full resolution.
# Beyond it, only coarse COPC octree levels are read (the horizon only needs
# the highest point per bin, so far terrain does not need full density).
NEAR_FULL_RES_KM = 5.0
FAR_RESOLUTION_M = 100.0  # COPC "resolution" is in data units, i.e. metres

# Terrain can sit this far above/below the reference sphere (lunar relief is
# about +-10 km). The read box is padded along "up" by this amount.
RELIEF_MARGIN_M = 11_000.0

# Altitude plane fit: try increasing radii until the fit is well-posed.
FIT_RADII_M = (100.0, 200.0, 400.0, 800.0, 1600.0, 3200.0)
FIT_MIN_POINTS = 8
FIT_MIN_SHAPE_RATIO = 0.1  # reject near-collinear points (single orbit track)

CHUNK = 2_000_000  # points processed at a time, limits memory use
MAX_WORKERS = 8  # tiles read in parallel


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


def _search_boxes(lat, lon, radius_km):
    """Lon/lat boxes (lon_min, lat_min, lon_max, lat_max) covering a spherical
    cap of the given radius, used only to find tiles. Handles the antimeridian
    and the poles."""
    ang = math.degrees(radius_km * 1000.0 / MOON_RADIUS_M)
    lat_min, lat_max = lat - ang, lat + ang
    if lat_max >= 90.0 or lat_min <= -90.0:
        # Cap contains a pole: longitude is unbounded, take the whole band.
        return [(-180.0, max(lat_min, -90.0), 180.0, min(lat_max, 90.0))]
    s = math.sin(math.radians(ang)) / math.cos(math.radians(lat))
    half = math.degrees(math.asin(min(1.0, s)))
    lo, hi = lon - half, lon + half
    if lo < -180.0:
        return [(lo + 360.0, lat_min, 180.0, lat_max), (-180.0, lat_min, hi, lat_max)]
    if hi > 180.0:
        return [(lo, lat_min, 180.0, lat_max), (-180.0, lat_min, hi - 360.0, lat_max)]
    return [(lo, lat_min, hi, lat_max)]


def _cube(site, up, range_m):
    """Axis-aligned 3D box (lo, hi) in Moon-fixed metres that contains every
    point within range_m of any position up to RELIEF_MARGIN_M above or below
    the reference sphere at the site. The relief margin is applied along "up"
    (projected on each axis), so the box stays thin where no terrain exists."""
    pad = range_m + RELIEF_MARGIN_M * np.abs(up)
    return site - pad, site + pad


# --------------------------------------------------------------------------
# Data access (STAC + COPC)
# --------------------------------------------------------------------------
def _http_url(href):
    if href.startswith("s3://"):
        bucket, _, key = href[5:].partition("/")
        return f"https://{bucket}.s3.us-west-2.amazonaws.com/{key}"
    return href


def _asset_url(item):
    asset = item.assets.get("data")
    if asset is not None:
        return _http_url(asset.href)
    for asset in item.assets.values():
        href = asset.href.lower()
        if href.endswith(".laz") or "copc" in href:
            return _http_url(asset.href)
    raise RuntimeError(f"No COPC asset found in STAC item {item.id}: {list(item.assets)}")


def _find_tiles(boxes):
    """STAC bbox search. Returns list of COPC URLs."""
    from pystac_client import Client

    catalog = Client.open(STAC_URL)
    urls = {}
    for box in boxes:
        search = catalog.search(collections=[STAC_COLLECTION], bbox=list(box))
        for item in search.items():
            if item.id not in urls:
                urls[item.id] = _asset_url(item)
    if not urls:
        raise RuntimeError("STAC search returned no LOLA tiles for this location")
    return list(urls.values())


def _read_tile(url, near_cube, far_cube):
    """Range-read one tile. Returns {"near": Nx3 or None, "far": Nx3 or None}
    in Moon-fixed metres. near = full resolution, far = coarse octree levels."""
    from laspy import CopcReader
    from laspy.copc import Bounds

    # t_* are per-tile durations in seconds (open = header + hierarchy fetch,
    # near/far = range reads + LAZ decompression).
    out = {"near": None, "far": None, "t_open": 0.0, "t_near": 0.0, "t_far": 0.0}
    t0 = time.perf_counter()
    with CopcReader.open(url) as reader:
        out["t_open"] = time.perf_counter() - t0
        tmin, tmax = np.asarray(reader.header.mins), np.asarray(reader.header.maxs)
        for key, cube, res in (("near", near_cube, None), ("far", far_cube, FAR_RESOLUTION_M)):
            if cube is None:
                continue
            lo, hi = cube
            if np.any(hi < tmin) or np.any(lo > tmax):
                continue  # this tile does not touch the box
            t1 = time.perf_counter()
            pts = reader.query(Bounds(mins=lo, maxs=hi), resolution=res)
            if len(pts) > 0:
                out[key] = np.column_stack([np.asarray(pts.x), np.asarray(pts.y), np.asarray(pts.z)])
            out["t_" + key] = time.perf_counter() - t1
    return out


def _read_points(urls, near_cube, far_cube):
    """Read all tiles in parallel. Returns (near_xyz, far_xyz, timing); the
    arrays may be None. timing = summed per-tile seconds (not wall-clock, since
    tiles run in parallel)."""
    with ThreadPoolExecutor(max_workers=min(MAX_WORKERS, len(urls))) as pool:
        results = list(pool.map(lambda u: _read_tile(u, near_cube, far_cube), urls))

    def cat(key):
        parts = [r[key] for r in results if r[key] is not None]
        return np.concatenate(parts) if parts else None

    timing = {k: sum(r[k] for r in results) for k in ("t_open", "t_near", "t_far")}
    return cat("near"), cat("far"), timing


# --------------------------------------------------------------------------
# Calculations
# --------------------------------------------------------------------------
def _fit_altitude(lat0, lon0, xyz):
    """Terrain altitude (m above the 1737.4 km reference sphere) at the site.

    Weighted least-squares plane through nearby points, evaluated at the site.
    This removes the bias a plain average would have on a slope. Only the
    intercept is used (no slope is reported). Falls back to a distance-weighted
    mean of the nearest points when the points are too few or collinear.
    Returns (altitude_m, description)."""
    east, north, up = _frame(lat0, lon0)
    d = xyz - MOON_RADIUS_M * up
    e, n = d @ east, d @ north
    h = np.linalg.norm(xyz, axis=1) - MOON_RADIUS_M
    dist = np.hypot(e, n)

    for rad in FIT_RADII_M:
        m = dist <= rad
        if m.sum() < FIT_MIN_POINTS:
            continue
        pts = np.column_stack([e[m], n[m]])
        s = np.linalg.svd(pts - pts.mean(axis=0), compute_uv=False)
        if s[1] < FIT_MIN_SHAPE_RATIO * s[0]:
            continue  # points lie along a single track: plane is ill-posed
        sw = np.sqrt(np.exp(-0.5 * (dist[m] / (rad / 2.0)) ** 2))
        A = np.column_stack([np.ones(m.sum()), pts])
        coef, *_ = np.linalg.lstsq(A * sw[:, None], h[m] * sw, rcond=None)
        return float(coef[0]), f"plane fit, radius {rad:.0f} m, {int(m.sum())} points"

    k = min(4, len(dist))
    idx = np.argsort(dist)[:k]
    w = 1.0 / np.maximum(dist[idx], 1.0)
    return float(np.sum(w * h[idx]) / np.sum(w)), f"fallback: mean of nearest {k} points"


def _horizon_profile(lat0, lon0, observer_alt_m, xyz, min_range_m, max_range_km):
    """Per 1 degree azimuth bin, the max elevation angle (deg) of the points.
    Bin i is centred on azimuth i (covers i-0.5 .. i+0.5). Empty bins = NaN.

    max_range_km: points farther than this (3D distance from the observer)
    are ignored, so terrain beyond it cannot raise the horizon.
    min_range_m: points closer than this are ignored, because LOLA's ~1 m
    vertical error would give huge angular error at tiny range."""
    east, north, up = _frame(lat0, lon0)
    obs = (MOON_RADIUS_M + observer_alt_m) * up
    prof = np.full(360, np.nan)

    for i in range(0, len(xyz), CHUNK):
        d = xyz[i:i + CHUNK] - obs  # metres
        dist = np.linalg.norm(d, axis=1)
        keep = (dist >= min_range_m) & (dist <= max_range_km * 1000.0)
        if not keep.any():
            continue
        d, dist = d[keep], dist[keep]
        # Elevation above the plane perpendicular to "up" at the observer.
        elev = np.degrees(np.arcsin(np.clip((d @ up) / dist, -1.0, 1.0)))
        az = np.degrees(np.arctan2(d @ east, d @ north)) % 360.0
        bins = np.floor(az + 0.5).astype(int) % 360
        order = np.argsort(elev)  # ascending, so the last write per bin is the max
        chunk_prof = np.full(360, np.nan)
        chunk_prof[bins[order]] = elev[order]
        prof = np.fmax(prof, chunk_prof)  # fmax ignores NaN
    return prof


# --------------------------------------------------------------------------
# Public function
# --------------------------------------------------------------------------
def horizon(latitude_deg, longitude_deg, max_range_km=50.0,
            height_above_terrain=0.0, min_range_m=20.0, verbose=False):
    """Terrain horizon seen from a lunar surface site.

    Args:
        latitude_deg: -90..90 (planetocentric).
        longitude_deg: -180..180, east positive.
        max_range_km: how far from the observer terrain is considered. Points
            beyond this distance are discarded, so mountains farther away
            cannot appear in the horizon. Larger values are more accurate
            (distant massifs) but read and process more data.
        height_above_terrain: observer height (m) above the local terrain.
        min_range_m: points closer than this (m) are ignored (LOLA vertical
            noise of ~1 m makes very close points unreliable). Features
            smaller than this scale are not resolved.
        verbose: print diagnostics.

    Returns dict:
        horizon_azimuth_deg: [0.0 .. 359.0], north=0, east=90.
        horizon_elevation_deg: same length; elevation of terrain relative to
            the plane perpendicular to the vector to the Moon's centre,
            measured from the observer. May be negative.
        altitude_m: terrain altitude of the coordinates above the 1737.4 km
            reference sphere (does NOT include height_above_terrain).
        horizon_gap_fraction: fraction of azimuth bins with no data points
            (filled by interpolation); higher means less reliable.
    """
    if not -90.0 <= latitude_deg <= 90.0:
        raise ValueError("latitude_deg must be within -90..90")
    if max_range_km <= 0 or min_range_m < 0 or height_above_terrain < 0:
        raise ValueError("max_range_km must be > 0; min_range_m and height_above_terrain must be >= 0")
    lat0 = float(latitude_deg)
    lon0 = ((float(longitude_deg) + 180.0) % 360.0) - 180.0

    _, _, up = _frame(lat0, lon0)
    site = MOON_RADIUS_M * up
    near_km = min(max_range_km, NEAR_FULL_RES_KM)
    near_cube = _cube(site, up, near_km * 1000.0)
    far_cube = _cube(site, up, max_range_km * 1000.0) if max_range_km > near_km else None

    t_start = time.perf_counter()
    boxes = _search_boxes(lat0, lon0, max_range_km)
    urls = _find_tiles(boxes)
    t_stac = time.perf_counter()
    near, far, tile_t = _read_points(urls, near_cube, far_cube)
    t_read = time.perf_counter()
    if near is None and far is None:
        raise RuntimeError("No LOLA points found around this location")

    altitude_m, how = _fit_altitude(lat0, lon0, near if near is not None else far)
    xyz = np.concatenate([p for p in (near, far) if p is not None])
    t_fit = time.perf_counter()
    prof = _horizon_profile(lat0, lon0, altitude_m + height_above_terrain,
                            xyz, min_range_m, max_range_km)
    t_end = time.perf_counter()

    gap = np.isnan(prof)
    if gap.all():
        raise RuntimeError("No points fell within the min/max range window")
    if gap.any():
        idx = np.arange(360)
        prof[gap] = np.interp(idx[gap], idx[~gap], prof[~gap], period=360)

    if verbose:
        print(f"tiles: {len(urls)}  points read: {len(xyz)} "
              f"(near {0 if near is None else len(near)}, far {0 if far is None else len(far)})")
        print(f"altitude: {altitude_m:.1f} m ({how})")
        print(f"empty azimuth bins: {gap.sum()}/360")
        print(f"horizon elevation: min {prof.min():.2f}  max {prof.max():.2f} deg")
        print("timing (wall-clock s): "
              f"STAC {t_stac - t_start:.2f} | tile reads {t_read - t_stac:.2f} | "
              f"altitude fit {t_fit - t_read:.2f} | horizon {t_end - t_fit:.2f} | "
              f"total {t_end - t_start:.2f}")
        print("tile reads, summed over tiles (s, not wall-clock): "
              f"open {tile_t['t_open']:.2f} | near query {tile_t['t_near']:.2f} | "
              f"far query {tile_t['t_far']:.2f}")

    return {
        "horizon_azimuth_deg": [float(i) for i in range(360)],
        "horizon_elevation_deg": [float(v) for v in prof],
        "altitude_m": altitude_m,
        "horizon_gap_fraction": float(gap.mean()),
    }


if __name__ == "__main__":
    # Near the lunar south pole, inside the Shackleton crater region.
    out = horizon(-89.9, 0.0, max_range_km=50.0, height_above_terrain=2.0, verbose=False)
    print(out)