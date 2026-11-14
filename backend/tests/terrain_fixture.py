"""Tiny TEST-ONLY lunar rasters with the production inventory's grid metadata.

These are not lunar observations. They are sparse where possible so the full
production grid sizes cost kilobytes. Run from backend/:
    python -m tests.terrain_fixture /absolute/output/dem
"""

from dataclasses import replace
import json
from pathlib import Path
import sys

import numpy as np
import rasterio
from rasterio.transform import from_origin
from rasterio.warp import transform

from src.services import terrain_data


def resized(product: terrain_data.Product, size: int = 16,
            pixel: float | None = None) -> terrain_data.Product:
    """A resized product whose recorded centre still matches its own grid."""
    pixel = product.pixel if pixel is None else pixel
    if product.projected:
        centre_lat, centre_lon = product.centre_lat, product.centre_lon
    else:
        centre_lon = product.lon_min + size * pixel / 2
        centre_lat = product.lat_max - size * pixel / 2
    return replace(product, width=size, height=size, pixel=pixel,
                   centre_lat=centre_lat, centre_lon=centre_lon)


def small(product: terrain_data.Product) -> terrain_data.Product:
    return resized(product)


def crs_for(product: terrain_data.Product) -> str:
    radius = terrain_data.MOON_RADIUS_M
    if product.projected:
        return (f"+proj=stere +lat_0={product.centre_lat} +lon_0=0 +k=1 "
                f"+a={radius} +b={radius} +units=m +no_defs +type=crs")
    return terrain_data.LONLAT_SPHERE


def open_for_write(path: Path, product: terrain_data.Product):
    # Sparse unwritten blocks decode as nodata, so no full-sized array is allocated.
    return rasterio.open(
        path, "w", driver="GTiff", width=product.width, height=product.height,
        count=1, dtype="int16", crs=crs_for(product), nodata=-32768,
        transform=from_origin(product.origin_x, product.origin_y, product.pixel, product.pixel),
        tiled=True, blockxsize=512, blockysize=512, SPARSE_OK=True, compress="deflate",
    )


def write_raster(path: Path, product: terrain_data.Product, value_at=None) -> None:
    with open_for_write(path, product) as ds:
        ds.scales = (terrain_data.HEIGHT_SCALE,)
        ds.offsets = (0.0,)
        if value_at is not None:
            rows, cols = np.mgrid[0:product.height, 0:product.width]
            xs, ys = ds.transform @ (cols + 0.5, rows + 0.5)
            lons, lats = transform(ds.crs, terrain_data.LONLAT_SPHERE, xs.ravel(), ys.ravel())
            altitude = np.array([value_at(lon, lat) for lon, lat in zip(lons, lats)])
            raw = np.rint(altitude / terrain_data.HEIGHT_SCALE).astype("int16")
            ds.write(raw.reshape(rows.shape), 1)


def write_dataset(directory: Path, products=None) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    entries = []
    for product in products or terrain_data.PRODUCTS:
        path = directory / f"{product.name}.tif"
        write_raster(path, product)
        entries.append({
            "name": product.name, "file": path.name, "bytes": path.stat().st_size,
            "sha256": terrain_data.sha256(path),
            "raster": terrain_data.inspect_raster(path, product, tiled=True),
        })
    manifest = {
        "schema_version": terrain_data.SCHEMA_VERSION,
        "reference_radius_m": terrain_data.MOON_RADIUS_M,
        "test_fixture": True,
        "products": entries,
    }
    (directory / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")


if __name__ == "__main__":
    write_dataset(Path(sys.argv[1]))
