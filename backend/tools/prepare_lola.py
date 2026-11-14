#!/usr/bin/env python3
"""Prepare versioned local LOLA COGs on Debian. No Docker or web configuration changes.

Run `python3 backend/tools/prepare_lola.py --help`. Host dependencies: curl,
python3-rasterio (including the JP2OpenJPEG and COG drivers). Downloads are serial,
resumable and restricted to HTTPS; source files are retained for validation.
"""

import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np  # noqa: E402
import rasterio  # noqa: E402
from rasterio.shutil import copy as raster_copy  # noqa: E402
from rasterio.windows import Window  # noqa: E402

from src.services.terrain_data import (  # noqa: E402
    MOON_RADIUS_M, PRODUCTS, SCHEMA_VERSION, Product, cross_check,
    inspect_raster, sha256, verify_dataset,
)

GIB = 1024 ** 3


def download(url: str, destination: Path, expected_bytes: int | None = None) -> None:
    """Publish only completed downloads. A failed transfer leaves a resumable .part."""
    if destination.is_symlink():
        raise ValueError(f"Refusing linked download: {destination}")
    if destination.exists():
        if expected_bytes is not None and destination.stat().st_size != expected_bytes:
            raise ValueError(f"Unexpected size: {destination}; use a fresh dataset version")
        return
    partial = destination.with_name(destination.name + ".part")
    if partial.is_symlink():
        raise ValueError(f"Refusing linked partial download: {partial}")
    size = partial.stat().st_size if partial.exists() else 0
    if expected_bytes is not None and size > expected_bytes:
        raise ValueError(f"Oversized partial download: {partial}")
    if expected_bytes is None or size != expected_bytes:
        subprocess.run([
            "curl", "--proto", "=https", "--proto-redir", "=https", "--fail", "--location",
            "--retry", "5", "--connect-timeout", "30", "--max-time", "3600", "--continue-at", "-",
            "--output", str(partial), url,
        ], check=True)
    if not partial.is_file() or partial.stat().st_size == 0:
        raise ValueError(f"Empty download: {url}")
    if expected_bytes is not None and partial.stat().st_size != expected_bytes:
        raise ValueError(f"Truncated or changed archive product: {url}")
    partial.replace(destination)


def download_product(root: Path, product: Product) -> Path:
    source = root / "source" / f"{product.name}.JP2"
    base = product.url.removesuffix(f"{product.name}.JP2")
    download(product.url, source, product.download_bytes)
    download(f"{base}{product.name}_JP2.LBL", root / "metadata" / f"{product.name}_JP2.LBL")
    # The archive's _AUX.XML name is NOT GDAL's automatic sidecar name.
    auxiliary = source.with_name(source.name + ".aux.xml")
    download(f"{base}{product.name}_AUX.XML", auxiliary)
    band = ET.parse(auxiliary).getroot().find("PAMRasterBand")
    if band is None or (band.findtext("Scale"), band.findtext("Offset")) != ("0.5", "0"):
        raise ValueError(f"Unexpected height scale/offset in {auxiliary}")
    label = (root / "metadata" / f"{product.name}_JP2.LBL").read_text(encoding="ascii")
    if product.name not in label or "SCALING_FACTOR" not in label:
        raise ValueError(f"Invalid PDS label for {product.name}")
    return source


def compare_samples(source: Path, output: Path) -> None:
    """Conversion must preserve raw samples and masks, not just plausible metadata."""
    with rasterio.open(source) as src, rasterio.open(output) as dst:
        for col, row in ((0, 0), (src.width // 2, src.height // 2), (src.width - 8, src.height - 8)):
            window = Window(col, row, 8, 8)
            if not np.array_equal(src.read(1, window=window), dst.read(1, window=window)):
                raise ValueError(f"Pixel values changed in conversion: {output.name}")
            if not np.array_equal(src.read_masks(1, window=window), dst.read_masks(1, window=window)):
                raise ValueError(f"Nodata mask changed in conversion: {output.name}")


def convert(source: Path, output: Path, product: Product, threads: int, scratch: Path) -> dict:
    inspect_raster(source, product)
    if output.is_symlink():
        raise ValueError(f"Refusing linked output: {output}")
    if not output.exists():
        partial = output.with_name(output.stem + ".partial.tif")
        if partial.is_symlink():
            raise ValueError(f"Refusing linked partial output: {partial}")
        # COG conversion may need an intermediate image. Leave the final filename
        # untouched until both metadata and decoded sample comparisons pass.
        with rasterio.Env(
            GDAL_CACHEMAX=128 * 1024 ** 2, GDAL_NUM_THREADS=str(threads), CPL_TMPDIR=str(scratch),
        ):
            raster_copy(
                source, partial, driver="COG", COMPRESS="DEFLATE", BLOCKSIZE=512,
                NUM_THREADS=str(threads), BIGTIFF="IF_SAFER", OVERVIEWS="NONE",
            )
        inspect_raster(partial, product, tiled=True)
        compare_samples(source, partial)
        # Rasters must be self-contained: a PAM sidecar would not be shipped to Beelink.
        sidecar = partial.with_name(partial.name + ".aux.xml")
        if sidecar.exists():
            raise ValueError(f"Conversion left a PAM sidecar; raster metadata must live in the COG: {sidecar.name}")
        partial.replace(output)
    metadata = inspect_raster(output, product, tiled=True)
    compare_samples(source, output)
    return metadata


@contextmanager
def preparation_lock(root: Path):
    """Debian flock is released even if the process is interrupted or killed."""
    import fcntl

    with (root / "prepare.lock").open("a") as stream:
        try:
            fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise ValueError("Another preparation process is using this dataset root") from exc
        yield


def prepare(root: Path, threads: int) -> None:
    if (root / "dem" / "manifest.json").exists():
        verify_dataset(root / "dem", hashes=True)
        print("Dataset already complete and verified; no files changed.")
        return
    with rasterio.Env() as env:
        missing = {"JP2OpenJPEG", "GTiff", "COG"} - env.drivers().keys()
        if missing:
            raise ValueError(f"Missing GDAL drivers: {', '.join(sorted(missing))}")
    if shutil.which("curl") is None:
        raise ValueError("Install curl before preparing LOLA data")
    entries = []
    cylindrical: dict[str, Path] = {}
    for product in PRODUCTS:
        # Budget conservatively for this compressed input, a full uncompressed
        # Int16 output and a conversion intermediate; do not exhaust the live host.
        required = product.download_bytes + 4 * product.width * product.height + GIB
        if shutil.disk_usage(root).free < required:
            raise ValueError(f"Need at least {required / GIB:.1f} GiB free for {product.name}")
        print(f"Preparing {product.name}", flush=True)
        source = download_product(root, product)
        output = root / "dem" / f"{product.name}.tif"
        metadata = convert(source, output, product, threads, root / "tmp")
        output.chmod(0o644)
        entry = {
            "name": product.name, "file": output.name, "bytes": output.stat().st_size,
            "sha256": sha256(output), "source_url": product.url, "source_sha256": sha256(source),
            "label_sha256": sha256(root / "metadata" / f"{product.name}_JP2.LBL"),
            "auxiliary_sha256": sha256(source.with_name(source.name + ".aux.xml")),
            "raster": metadata,
        }
        if product.projected:
            entry["cross_check"] = cross_check(product, output, cylindrical)
            print(f"  cross-check: {entry['cross_check']}", flush=True)
        else:
            cylindrical[product.name] = output
        entries.append(entry)
    manifest = {
        "schema_version": SCHEMA_VERSION, "reference_radius_m": MOON_RADIUS_M,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "height_units": "metres above reference sphere; raw * scale + offset",
        "rasterio_version": rasterio.__version__, "gdal_version": rasterio.__gdal_version__,
        "products": entries,
    }
    partial = root / "dem" / "manifest.partial.json"
    partial.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    partial.chmod(0o644)
    partial.replace(root / "dem" / "manifest.json")
    verify_dataset(root / "dem", hashes=True)
    print(f"Ready: {root / 'dem'} (8 rasters + manifest.json)")
    print("No running containers were changed. Terrain calculations are not enabled by this tool.")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("prepare", "inspect", "verify"))
    parser.add_argument("--root", type=Path, default=Path.home() / "moon-flyers/data/lola/v1")
    parser.add_argument("--threads", type=int, choices=range(1, 9), default=2)
    args = parser.parse_args()
    root = args.root.expanduser().resolve()
    try:
        if args.action == "verify":
            verify_dataset(root / "dem", hashes=True)
            cylindrical = {p.name: root / "dem" / f"{p.name}.tif" for p in PRODUCTS if not p.projected}
            for product in PRODUCTS:
                if product.projected:
                    result = cross_check(product, root / "dem" / f"{product.name}.tif", cylindrical)
                    print(product.name, json.dumps(result))
            print("All eight rasters match their manifest and checksums; polar placement agrees "
                  "with the independent global products.")
        elif args.action == "inspect":
            for product in PRODUCTS:
                source = root / "source" / f"{product.name}.JP2"
                if source.exists():
                    print(product.name, json.dumps(inspect_raster(source, product)))
        else:
            if sys.platform != "linux":
                raise ValueError("Run preparation on the Debian Beelink (Linux flock required)")
            os.umask(0o022)
            for name in ("source", "dem", "metadata", "tmp"):
                (root / name).mkdir(parents=True, exist_ok=True)
            (root / "dem").chmod(0o755)
            os.environ["OPJ_NUM_THREADS"] = str(args.threads)
            with preparation_lock(root):
                prepare(root, args.threads)
    except (ValueError, OSError, subprocess.CalledProcessError, ET.ParseError, rasterio.errors.RasterioError) as exc:
        print(f"LOLA preparation failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
