"""LOLA DEM dataset checks and optional startup validation.

The dataset itself is host data (`LOLA_DEM_DIR`), never committed or baked into an
image: eight IMG/LBL pairs plus calibration.json, prepared by copying the archive
files and verified with `tools/lola_data.py`. The heavy lifting lives in
`src/lunar_horizon_dem.py`, which owns the file format.
"""


import pytest

from src.lunar_horizon_dem import verify_dataset
from tools.lola_fixture import write_dataset


@pytest.fixture
def dataset(tmp_path):
    return write_dataset(tmp_path / "lola_dem")


def test_complete_dataset_passes_metadata_and_cross_checks(dataset):
    summary = verify_dataset(dataset)
    assert len(summary["products"]) == 8
    assert set(summary["calibration"]) == {"LDEM_875N_5M", "LDEM_875S_5M", "LDEM_80N_20M", "LDEM_80S_20M"}
    assert set(summary["cross_check"]) == set(summary["calibration"])
    assert all(v["samples"] >= 8 for v in summary["cross_check"].values())


def test_published_release_check_rejects_other_grids(dataset):
    """The CLI's stricter mode must reject a grid that is not the published release."""
    with pytest.raises(RuntimeError, match="published release"):
        verify_dataset(dataset, cross_check=False, published_shapes=True)


def test_metadata_only_check_skips_terrain_comparison(dataset):
    assert verify_dataset(dataset, cross_check=False)["cross_check"] == {}


def test_missing_file_names_the_file(dataset):
    (dataset / "LDEM_80N_20M.IMG").unlink()
    with pytest.raises(FileNotFoundError, match="LDEM_80N_20M.IMG"):
        verify_dataset(dataset, cross_check=False)


def test_truncated_raster_is_rejected(dataset):
    path = dataset / "LDEM_875S_5M.IMG"
    path.write_bytes(path.read_bytes()[:-2])
    with pytest.raises(RuntimeError, match="incomplete"):
        verify_dataset(dataset, cross_check=False)


def test_wrong_scaling_and_sample_type_are_rejected(dataset):
    label = dataset / "LDEM_256_00N_90N_000_180.LBL"
    text = label.read_text()
    label.write_text(text.replace("SCALING_FACTOR = 0.5", "SCALING_FACTOR = 1.0"))
    with pytest.raises(RuntimeError, match="SCALING_FACTOR"):
        verify_dataset(dataset, cross_check=False)
    label.write_text(text.replace("SAMPLE_TYPE = LSB_INTEGER", "SAMPLE_TYPE = MSB_INTEGER"))
    with pytest.raises(RuntimeError, match="little-endian"):
        verify_dataset(dataset, cross_check=False)


def test_wrong_projection_and_shape_are_rejected(dataset):
    label = dataset / "LDEM_875N_5M.LBL"
    text = label.read_text()
    label.write_text(text.replace("POLAR STEREOGRAPHIC", "SIMPLE CYLINDRICAL"))
    with pytest.raises(RuntimeError, match="POLAR STEREOGRAPHIC"):
        verify_dataset(dataset, cross_check=False)
    label.write_text(text.replace("LINES = 64", "LINES = 65"))
    with pytest.raises(RuntimeError, match="incomplete"):
        verify_dataset(dataset, cross_check=False)


def test_calibration_must_cover_exactly_the_polar_products(dataset):
    path = dataset / "calibration.json"
    path.write_text('{"LDEM_875N_5M": 0}')
    with pytest.raises(RuntimeError, match="exactly the polar products"):
        verify_dataset(dataset, cross_check=False)
    path.write_text('{"LDEM_875N_5M": 0, "LDEM_875S_5M": 1, "LDEM_80N_20M": 0, "LDEM_80S_20M": 8}')
    with pytest.raises(RuntimeError, match="not an integer in 0..7"):
        verify_dataset(dataset, cross_check=False)


def test_mis_calibrated_polar_grid_is_caught_by_the_cross_check(dataset):
    # Variant 2 mirrors the grid: metadata still looks perfect, terrain does not agree.
    path = dataset / "calibration.json"
    path.write_text('{"LDEM_875N_5M": 2, "LDEM_875S_5M": 1, "LDEM_80N_20M": 0, "LDEM_80S_20M": 1}')
    assert verify_dataset(dataset, cross_check=False)["cross_check"] == {}
    with pytest.raises(RuntimeError, match="calibration.json"):
        verify_dataset(dataset)


def test_api_validates_the_mounted_dataset_at_startup(dataset, monkeypatch):
    from fastapi.testclient import TestClient

    from src.main import app

    monkeypatch.delenv("LOLA_DEM_DIR", raising=False)
    with TestClient(app) as client:
        assert app.state.lola_dem_dir is None
        assert client.get("/health").json() == {"status": "ok"}
    monkeypatch.setenv("LOLA_DEM_DIR", str(dataset))
    with TestClient(app) as client:
        assert app.state.lola_dem_dir == dataset
        assert client.get("/health").headers["X-Moon-Flyers-Data-Source"] == "mock"


def test_configured_missing_dataset_fails_startup(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from src.main import app

    monkeypatch.setenv("LOLA_DEM_DIR", str(tmp_path))
    with pytest.raises(FileNotFoundError), TestClient(app):
        pass
