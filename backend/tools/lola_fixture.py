"""Tiny synthetic LOLA DEM directory for offline tests.

**These are not lunar observations.** Shapes follow the published grid conventions
so the real loader parses them: cylindrical tiles keep the 2:1 longitude:latitude
aspect that `_CylGrid` checks, and polar grids keep their stereographic scale. Heights
come from one smooth function of lon/lat, so a polar grid whose axis orientation is
wrong disagrees with the global tiles - which is exactly what `verify_dataset` tests.

Stdlib only, so CI can build a dataset on a bare runner:

    python3 backend/tools/lola_fixture.py /tmp/lola_dem
"""

import array
import json
import math
from pathlib import Path
import sys

MOON_RADIUS_M = 1_737_400.0
CYL_SIZE = (128, 256)         # rows, cols for a 90 deg x 180 deg tile
POLAR_SIZE = 64
# Polar axis conventions, indexed like VARIANTS in lunar_horizon_dem. The values
# match the team's real calibration.json so the fixture exercises the same path.
VARIANTS = [(sw, sx, sy) for sw in (False, True) for sx in (1, -1) for sy in (1, -1)]
CALIBRATION = {"LDEM_875N_5M": 0, "LDEM_875S_5M": 1, "LDEM_80N_20M": 0, "LDEM_80S_20M": 1}


def terrain(lat_deg: float, lon_deg: float) -> float:
    """Smooth synthetic height in metres; varies with longitude and latitude.

    The odd harmonic matters: with only a cosine term, mirroring the longitude
    (variant 0 vs 2) would be undetectable, and the cross-check tests would pass
    for grids that are actually mis-oriented. Real lunar terrain is not
    mirror-symmetric either.
    """
    return (1000.0 + 5000.0 * math.cos(math.radians(lon_deg))
            + 3500.0 * math.sin(math.radians(2.0 * lon_deg))
            + 300.0 * math.sin(math.radians(4.0 * lat_deg)))


def _write(base: Path, rows: int, cols: int, heights, label: str) -> None:
    values = array.array("h", (int(round(h / 0.5)) for h in heights))
    if sys.byteorder != "little":
        values.byteswap()
    base.with_suffix(".IMG").write_bytes(values.tobytes())
    base.with_suffix(".LBL").write_text(
        "PDS_VERSION_ID = \"PDS3\"\n"
        f"LINES = {rows}\nLINE_SAMPLES = {cols}\n"
        "SAMPLE_TYPE = LSB_INTEGER\nSAMPLE_BITS = 16\nSCALING_FACTOR = 0.5\n"
        + label, encoding="ascii")


def write_cylindrical(directory: Path, name: str, lat_min: float, lat_max: float,
                      lon_min: float, lon_max: float) -> None:
    rows, cols = CYL_SIZE
    ppd = cols / (lon_max - lon_min)
    assert abs(rows / (lat_max - lat_min) - ppd) < 1e-9, "tile must keep the published 2:1 aspect"
    heights = [terrain(lat_max - (row + 0.5) / ppd, lon_min + (col + 0.5) / ppd)
               for row in range(rows) for col in range(cols)]
    _write(directory / name, rows, cols, heights, "MAP_PROJECTION_TYPE = \"SIMPLE CYLINDRICAL\"\n")


def write_polar(directory: Path, name: str, sign: int, lat_limit: float, variant: int) -> None:
    size = POLAR_SIZE
    scale = 2 * MOON_RADIUS_M * math.tan(math.radians(90.0 - lat_limit) / 2.0) / (size / 2.0)
    centre = size / 2.0 - 0.5
    swap, sign_col, sign_row = VARIANTS[variant]
    heights = []
    for row in range(size):
        for col in range(size):
            # Inverse of _PolarGrid.sample: col = cx + sign_col * a / scale, row = cy + sign_row * b / scale.
            a, b = (col - centre) * scale / sign_col, (row - centre) * scale / sign_row
            u, v = (b, a) if swap else (a, b)
            rho = math.hypot(u, v)
            lat = sign * (90.0 - math.degrees(2.0 * math.atan(rho / (2.0 * MOON_RADIUS_M))))
            heights.append(terrain(lat, math.degrees(math.atan2(u, v))))
    _write(directory / name, size, size, heights,
           f"MAP_PROJECTION_TYPE = \"POLAR STEREOGRAPHIC\"\nMAP_SCALE = {scale:.6f} <m/pix>\n")


def write_dataset(directory, calibration=None) -> Path:
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    for name, lat_min, lat_max, lon_min, lon_max in (
        ("LDEM_256_00N_90N_000_180", 0.0, 90.0, 0.0, 180.0),
        ("LDEM_256_00N_90N_180_360", 0.0, 90.0, 180.0, 360.0),
        ("LDEM_256_90S_00S_000_180", -90.0, 0.0, 0.0, 180.0),
        ("LDEM_256_90S_00S_180_360", -90.0, 0.0, 180.0, 360.0),
    ):
        write_cylindrical(directory, name, lat_min, lat_max, lon_min, lon_max)
    calibration = CALIBRATION if calibration is None else calibration
    for name, sign, lat_limit in (("LDEM_875N_5M", 1, 87.5), ("LDEM_875S_5M", -1, 87.5),
                                  ("LDEM_80N_20M", 1, 80.0), ("LDEM_80S_20M", -1, 80.0)):
        write_polar(directory, name, sign, lat_limit, calibration[name])
    (directory / "calibration.json").write_text(json.dumps(calibration), encoding="utf-8")
    return directory


if __name__ == "__main__":
    print(write_dataset(Path(sys.argv[1])))
