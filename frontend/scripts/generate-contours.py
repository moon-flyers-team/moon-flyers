"""Generate the bundled 500 m contour paths from NASA's F32 south-polar LOLA crop.

Offline build tool only; no Python is needed to run the frontend.
Usage: uv run --with pillow --with numpy --with contourpy generate-contours.py input.tif output.json
Download URL, extent, reference surface and provenance: public/maps/south-pole/README.md.
"""
import json
import math
import sys
from pathlib import Path

import contourpy
import numpy as np
from PIL import Image


def generate(input_path, output_path):
    with Image.open(input_path) as image:
        if image.mode != "F":
            raise ValueError("Expected a floating-point metre-elevation TIFF, not a rendered tile")
        step_x, step_y, _ = image.tag_v2[33550]
        _, _, _, left, top, _ = image.tag_v2[33922]
        values = np.asarray(image, dtype=float)
    rows, columns = values.shape
    radius = 2 * 1737400 * math.tan(math.radians(5))
    if not (math.isclose(left, -radius, abs_tol=0.01)
            and math.isclose(top, radius, abs_tol=0.01)
            and math.isclose(step_x * columns, 2 * radius, abs_tol=0.01)
            and math.isclose(step_y * rows, 2 * radius, abs_tol=0.01)):
        raise ValueError("DEM extent does not match the map's 80 degrees south cap")
    # TIFF tiepoint is the outer corner; values are at pixel centres.
    x = 350 + (left + (np.arange(columns) + 0.5) * step_x) * 300 / radius
    y = 350 - (top - (np.arange(rows) + 0.5) * step_y) * 300 / radius
    values = np.ma.masked_where(~np.isfinite(values) | (np.abs(values) > 20000), values)
    generator = contourpy.contour_generator(x=x, y=y, z=values, name="serial")
    layers = []
    for elevation in range(-9000, 7501, 500):
        segments = generator.lines(elevation)
        path = " ".join("M" + " L".join(f"{a:.2f},{b:.2f}" for a, b in points)
                        for points in segments if len(points) >= 3)
        if path:
            layers.append({"elevation_m": elevation, "path": path})
    result = {"interval_m": 500, "reference_radius_m": 1737400,
              "dem_size": [columns, rows], "layers": layers}
    Path(output_path).write_text(json.dumps(result, separators=(",", ":")) + "\n")
    print(f"Wrote {len(layers)} contour levels to {output_path}")


if __name__ == "__main__":
    generate(sys.argv[1], sys.argv[2])
