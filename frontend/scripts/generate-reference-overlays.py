"""Create georeferenced display PNGs from the official LOLA average-visibility IMG/LBL files.

uv run --with numpy --with pillow frontend/scripts/generate-reference-overlays.py SOURCE_DIR OUTPUT_DIR
Source URLs and interpretation: public/maps/south-pole/README.md. No runtime Python is required.
"""
import hashlib
import json
import math
import re
import shutil
import sys
from pathlib import Path

import numpy as np
from PIL import Image

PRODUCTS = [
    ("sunlight", "AVGVISIB_65S_240M_201608", (245, 166, 35)),
    ("earth-visibility", "AVGVISIB_65S_240M_201608_EARTH", (79, 195, 247)),
]
SIZE = 1024
RADIUS = 2 * 1737400 * math.tan(math.radians(5))


def field(label, name):
    match = re.search(rf"^\s*{name}\s*=\s*([-+0-9.eE]+)", label, re.MULTILINE)
    if not match:
        raise ValueError(f"Missing PDS label field: {name}")
    return float(match[1])


def generate(source_directory, output_directory):
    source, output = Path(source_directory), Path(output_directory)
    output.mkdir(parents=True, exist_ok=True)
    metadata = {"projection": "lunar_south_polar_stereographic", "reference_radius_m": 1737400,
                "bounds_m": [-RADIUS, -RADIUS, RADIUS, RADIUS], "width": SIZE, "height": SIZE,
                "average_period_years": 18.6, "data_type": "long_term_reference", "layers": []}
    sample_axis = -RADIUS + (np.arange(SIZE) + 0.5) * 2 * RADIUS / SIZE
    in_cap = sample_axis[:, None] ** 2 + sample_axis[None, :] ** 2 <= RADIUS ** 2
    for name, product, high_color in PRODUCTS:
        label_path = source / f"{product}.LBL"
        label = label_path.read_text()
        rows, columns = int(field(label, "LINES")), int(field(label, "LINE_SAMPLES"))
        if (field(label, "CENTER_LATITUDE") != -90 or field(label, "CENTER_LONGITUDE") != 0
                or field(label, "A_AXIS_RADIUS") != 1737.4 or field(label, "SAMPLE_BITS") != 16
                or 'LSB_INTEGER' not in label):
            raise ValueError("Unexpected source projection, reference radius, or pixel encoding")
        path = source / f"{product}.IMG"
        if path.stat().st_size != rows * columns * 2:
            raise ValueError("Source IMG size does not match its PDS label")
        scale = field(label, "MAP_SCALE")
        column_offset = field(label, "SAMPLE_PROJECTION_OFFSET")
        row_offset = field(label, "LINE_PROJECTION_OFFSET")
        # PDS offsets identify the zero-indexed pixel centre at the projection origin.
        # PIL's EXTENT coordinates use pixel edges, hence the +0.5 centre correction.
        left, right = column_offset + 0.5 - RADIUS / scale, column_offset + 0.5 + RADIUS / scale
        top, bottom = row_offset + 0.5 - RADIUS / scale, row_offset + 0.5 + RADIUS / scale
        col0, row0 = math.floor(left) - 1, math.floor(top) - 1
        col1, row1 = math.ceil(right) + 1, math.ceil(bottom) + 1
        raw = np.memmap(path, dtype='<i2', mode='r', shape=(rows, columns))[row0:row1, col0:col1]
        values = np.asarray(raw, dtype=np.float32) * field(label, "SCALING_FACTOR") * 100 + field(label, "OFFSET") * 100
        valid = np.isfinite(values) & (values >= 0) & (values <= 100)
        extent = (left - col0, top - row0, right - col0, bottom - row0)

        def resample(array):
            image = Image.fromarray(np.asarray(array, dtype=np.float32))
            return np.asarray(image.transform((SIZE, SIZE), Image.Transform.EXTENT, extent,
                                             resample=Image.Resampling.BILINEAR))

        weights = resample(valid)
        percentages = resample(np.where(valid, values, 0)) / np.maximum(weights, 1e-6)
        visible = in_cap & (weights >= 0.999)
        low = np.array([25, 27, 42])
        rgb = np.rint(low + np.clip(percentages[..., None] / 100, 0, 1) * (np.array(high_color) - low))
        rgba = np.zeros((SIZE, SIZE, 4), dtype=np.uint8)
        rgba[..., :3] = rgb.astype(np.uint8)
        rgba[..., 3] = np.where(visible, 255, 0)
        Image.fromarray(rgba).save(output / f"{name}.png", optimize=True)
        shutil.copyfile(label_path, output / f"{product}.LBL")
        metadata['layers'].append({"id": name, "product": product, "source_scale_m": scale,
                                   "source_scaling_factor": field(label, "SCALING_FACTOR"),
                                   "source_sha256": hashlib.file_digest(path.open('rb'), 'sha256').hexdigest(),
                                   "min_pct": float(percentages[visible].min()),
                                   "max_pct": float(percentages[visible].max()),
                                   "visible_disc_definition": "any_fraction", "unit": "%"})
        print(name, metadata['layers'][-1]['min_pct'], metadata['layers'][-1]['max_pct'])
    (output / 'metadata.json').write_text(json.dumps(metadata, indent=2) + '\n')


if __name__ == '__main__':
    generate(sys.argv[1], sys.argv[2])
