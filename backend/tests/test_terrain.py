"""Offline terrain preparation, integrity, placement and optional startup checks."""

from dataclasses import replace
import json
from pathlib import Path
import math
import subprocess

from fastapi.testclient import TestClient
import numpy as np
import pytest
import rasterio
from rasterio.windows import Window

from src.main import app
from src.services import terrain_data
from tests.terrain_fixture import resized, small, write_dataset, write_raster
from tools import prepare_lola


@pytest.fixture
def inventory(monkeypatch):
    products = tuple(small(p) for p in terrain_data.PRODUCTS)
    by_name = {p.name: p for p in products}
    monkeypatch.setattr(terrain_data, "PRODUCTS", products)
    monkeypatch.setattr(terrain_data, "PRODUCT_BY_NAME", by_name)
    monkeypatch.setattr(prepare_lola, "PRODUCTS", products)
    return products


@pytest.fixture
def dataset(tmp_path, inventory):
    directory = tmp_path / "dem"
    write_dataset(directory, inventory)
    return directory


def test_manifest_validates_all_products_and_hashes(dataset):
    assert len(terrain_data.verify_dataset(dataset, hashes=True)["products"]) == 8


def test_manifest_rejects_missing_and_duplicate_products(dataset):
    path = dataset / "manifest.json"
    manifest = json.loads(path.read_text())
    manifest["products"].pop()
    path.write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="exactly"):
        terrain_data.verify_dataset(dataset)
    manifest["products"].append(manifest["products"][0])
    path.write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="exactly"):
        terrain_data.verify_dataset(dataset)


def test_manifest_rejects_path_traversal(dataset):
    path = dataset / "manifest.json"
    manifest = json.loads(path.read_text())
    manifest["products"][0]["file"] = "../outside.tif"
    path.write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="Invalid raster path"):
        terrain_data.verify_dataset(dataset)


def test_missing_truncated_and_modified_rasters_fail(dataset, inventory):
    path = dataset / f"{inventory[0].name}.tif"
    original = path.read_bytes()
    path.write_bytes(original[:-1])
    with pytest.raises(ValueError, match="truncated"):
        terrain_data.verify_dataset(dataset)
    path.write_bytes(original)
    manifest_path = dataset / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["products"][0]["sha256"] = "0" * 64
    manifest_path.write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="Checksum mismatch"):
        terrain_data.verify_dataset(dataset, hashes=True)
    path.unlink()
    with pytest.raises(ValueError, match="Missing"):
        terrain_data.verify_dataset(dataset)


def test_wrong_height_scale_is_rejected(tmp_path, inventory):
    product = inventory[0]
    path = tmp_path / "source.tif"
    write_raster(path, product)
    with rasterio.open(path, "r+") as ds:
        ds.scales = (1.0,)
    with pytest.raises(ValueError, match="band scale"):
        terrain_data.inspect_raster(path, product)


def test_wrong_datum_and_tile_placement_are_rejected(tmp_path, inventory):
    product = inventory[0]
    path = tmp_path / "source.tif"
    write_raster(path, product)
    with pytest.raises(ValueError, match="misplaced"):
        terrain_data.inspect_raster(path, replace(product, centre_lon=product.centre_lon + 90))
    with rasterio.open(path, "r+") as ds:
        ds.crs = "+proj=longlat +datum=WGS84 +no_defs +type=crs"
    with pytest.raises(ValueError, match="spherical 1737400 m lunar CRS"):
        terrain_data.inspect_raster(path, product)


def test_polar_and_geographic_products_are_not_interchangeable(tmp_path, inventory):
    polar = next(p for p in inventory if p.projected)
    cylindrical = next(p for p in inventory if not p.projected)
    path = tmp_path / "polar.tif"
    write_raster(path, polar)
    with pytest.raises(ValueError, match="geographic CRS"):
        terrain_data.inspect_raster(path, cylindrical)


def test_cog_conversion_preserves_scale_pixels_and_mask(tmp_path, inventory):
    product = inventory[0]
    source, output = tmp_path / "source.tif", tmp_path / "output.tif"
    write_raster(source, product)
    with rasterio.open(source, "r+") as ds:
        ds.write(np.full((8, 8), 1234, dtype="int16"), 1, window=Window(0, 0, 8, 8))
    metadata = prepare_lola.convert(source, output, product, 1, tmp_path)
    assert metadata["scale"] == 0.5 and metadata["projected"] is False
    with rasterio.open(output) as ds:
        assert ds.read(1)[0, 0] * ds.scales[0] == 617.0
        assert ds.read(1, masked=True).mask[-1, -1]
        assert ds.tags(ns="IMAGE_STRUCTURE")["LAYOUT"] == "COG"
    before = output.stat().st_mtime_ns
    prepare_lola.convert(source, output, product, 1, tmp_path)
    assert output.stat().st_mtime_ns == before


def test_interrupted_conversion_never_publishes_final_name(tmp_path, inventory, monkeypatch):
    product = inventory[0]
    source, output = tmp_path / "source.tif", tmp_path / "output.tif"
    write_raster(source, product)

    def fail(*args, **kwargs):
        Path(args[1]).write_bytes(b"interrupted")
        raise OSError("out of disk")

    monkeypatch.setattr(prepare_lola, "raster_copy", fail)
    with pytest.raises(OSError, match="out of disk"):
        prepare_lola.convert(source, output, product, 1, tmp_path)
    assert not output.exists()


def test_conversion_rejects_a_pam_sidecar(tmp_path, inventory, monkeypatch):
    product = inventory[0]
    source, output = tmp_path / "source.tif", tmp_path / "output.tif"
    write_raster(source, product)

    original = prepare_lola.raster_copy

    def writes_sidecar(src, dst, **kwargs):
        original(src, dst, **kwargs)
        Path(dst).with_name(Path(dst).name + ".aux.xml").write_text("<PAMDataset/>")

    monkeypatch.setattr(prepare_lola, "raster_copy", writes_sidecar)
    with pytest.raises(ValueError, match="PAM sidecar"):
        prepare_lola.convert(source, output, product, 1, tmp_path)
    assert not output.exists()


def test_download_is_resumable_size_checked_and_atomic(tmp_path, monkeypatch):
    destination = tmp_path / "data.JP2"
    partial = tmp_path / "data.JP2.part"
    partial.write_bytes(b"12")

    def complete(args, check):
        assert "--continue-at" in args and "--proto-redir" in args
        assert Path(args[args.index("--output") + 1]) == partial
        assert not destination.exists()
        partial.write_bytes(b"1234")

    monkeypatch.setattr(prepare_lola.subprocess, "run", complete)
    prepare_lola.download("https://example.test/data.JP2", destination, 4)
    assert destination.read_bytes() == b"1234"
    assert not partial.exists()
    prepare_lola.download("https://example.test/data.JP2", destination, 4)
    with pytest.raises(ValueError, match="Unexpected size"):
        prepare_lola.download("https://example.test/data.JP2", destination, 5)


def test_failed_download_keeps_partial_only(tmp_path, monkeypatch):
    destination = tmp_path / "data.JP2"

    def fail(args, check):
        destination.with_name(destination.name + ".part").write_bytes(b"12")
        raise subprocess.CalledProcessError(22, args)

    monkeypatch.setattr(prepare_lola.subprocess, "run", fail)
    with pytest.raises(subprocess.CalledProcessError):
        prepare_lola.download("https://example.test/data.JP2", destination, 4)
    assert not destination.exists()


def test_complete_partial_can_be_published_without_redownloading(tmp_path, monkeypatch):
    destination = tmp_path / "data.JP2"
    destination.with_name(destination.name + ".part").write_bytes(b"1234")
    monkeypatch.setattr(prepare_lola.subprocess, "run", lambda *a, **kw: pytest.fail("unexpected network"))
    prepare_lola.download("https://example.test/data.JP2", destination, 4)
    assert destination.read_bytes() == b"1234"


def test_full_preparation_is_resumable_and_manifest_last(tmp_path, inventory, monkeypatch):
    for name in ("source", "dem", "metadata", "tmp"):
        (tmp_path / name).mkdir()

    def local_download(root, product):
        assert not (root / "dem" / "manifest.json").exists()
        source = root / "source" / f"{product.name}.JP2"
        write_raster(source, product)
        source.with_name(source.name + ".aux.xml").write_text("fixture")
        (root / "metadata" / f"{product.name}_JP2.LBL").write_text("fixture")
        return source

    monkeypatch.setattr(prepare_lola, "download_product", local_download)
    monkeypatch.setattr(prepare_lola, "cross_check", lambda product, path, cylindrical: {"fixture": True})
    prepare_lola.prepare(tmp_path, 1)
    manifest = terrain_data.verify_dataset(tmp_path / "dem", hashes=True)
    assert len(manifest["products"]) == 8
    monkeypatch.setattr(prepare_lola, "download_product", lambda *a: pytest.fail("redownload of frozen dataset"))
    prepare_lola.prepare(tmp_path, 1)


def _terrain(lon, lat):
    return 1000 + 3000 * math.cos(math.radians(6 * lon)) + 200 * math.sin(math.radians(10 * lat))


@pytest.fixture
def cross_check_products(monkeypatch):
    """Small products with a coarse grid, so the overlap region is a few pixels."""
    polar = resized(terrain_data.PRODUCT_BY_NAME["LDEM_875N_5M"], size=64, pixel=2000.0)
    cylindrical = tuple(resized(p, pixel=1.0) for p in terrain_data.PRODUCTS
                        if p.region == "CYLINDRICAL" and p.lat_max == 90)
    products = (polar, *cylindrical)
    by_name = {p.name: p for p in products}
    monkeypatch.setattr(terrain_data, "PRODUCTS", products)
    monkeypatch.setattr(terrain_data, "PRODUCT_BY_NAME", by_name)
    monkeypatch.setattr(terrain_data, "CROSS_CHECK_LATITUDE", {"LDEM_875N_5M": 89.7})
    monkeypatch.setattr(terrain_data, "CROSS_CHECK_LON_STEP", 4)
    monkeypatch.setattr(terrain_data, "CROSS_CHECK_MIN_SAMPLES", 3)
    return products


def _write_cross_check_set(tmp_path, products):
    paths = {}
    for product in products:
        path = tmp_path / f"{product.name}.tif"
        write_raster(path, product, _terrain)
        paths[product.name] = path
    return paths


def test_cross_check_accepts_matching_polar_and_global_products(tmp_path, cross_check_products):
    paths = _write_cross_check_set(tmp_path, cross_check_products)
    polar = terrain_data.PRODUCT_BY_NAME["LDEM_875N_5M"]
    cylindrical = {p.name: paths[p.name] for p in cross_check_products if not p.projected}
    result = terrain_data.cross_check(polar, paths[polar.name], cylindrical)
    assert result["samples"] >= 3
    assert result["median_abs_difference_m"] < terrain_data.CROSS_CHECK_TOLERANCE_M


def test_cross_check_rejects_a_rotated_polar_grid(tmp_path, cross_check_products):
    paths = _write_cross_check_set(tmp_path, cross_check_products)
    polar = terrain_data.PRODUCT_BY_NAME["LDEM_875N_5M"]
    cylindrical = {p.name: paths[p.name] for p in cross_check_products if not p.projected}
    with rasterio.open(paths[polar.name], "r+") as ds:
        ds.crs = (f"+proj=stere +lat_0=90 +lon_0=15 +k=1 +a={terrain_data.MOON_RADIUS_M} "
                  f"+b={terrain_data.MOON_RADIUS_M} +units=m +no_defs +type=crs")
    with pytest.raises(ValueError, match="disagree"):
        terrain_data.cross_check(polar, paths[polar.name], cylindrical)


def test_application_mount_is_opt_in_and_does_not_claim_real_predictions(dataset, monkeypatch):
    monkeypatch.delenv("MOON_FLYERS_DEM_DIR", raising=False)
    with TestClient(app) as client:
        assert app.state.terrain_directory is None
        assert client.get("/health").json() == {"status": "ok"}
    monkeypatch.setenv("MOON_FLYERS_DEM_DIR", str(dataset))
    with TestClient(app) as client:
        assert app.state.terrain_directory == dataset
        assert client.get("/health").headers["X-Moon-Flyers-Data-Source"] == "mock"


def test_configured_missing_dataset_fails_startup(tmp_path, monkeypatch):
    monkeypatch.setenv("MOON_FLYERS_DEM_DIR", str(tmp_path))
    with pytest.raises(FileNotFoundError), TestClient(app):
        pass
