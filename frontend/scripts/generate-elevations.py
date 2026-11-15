"""Bundle metre elevations from the same F32 LOLA crop used by generate-contours.py.
Usage: uv run --with pillow --with numpy generate-elevations.py input.tif output.json
"""
import hashlib
import json
import math
import sys
from pathlib import Path
import numpy as np
from PIL import Image

source, output = map(Path, sys.argv[1:])
with Image.open(source) as image:
    if image.mode != 'F':
        raise ValueError('Expected numeric F32 LOLA GeoTIFF')
    step_x, step_y, _ = image.tag_v2[33550]
    _, _, _, left, top, _ = image.tag_v2[33922]
    data = np.asarray(image, dtype=float)
height, width = data.shape
radius = 2 * 1737400 * math.tan(math.radians(5))
for actual, expected in [(left, -radius), (top, radius), (step_x * width, 2 * radius), (step_y * height, 2 * radius)]:
    if not math.isclose(actual, expected, abs_tol=0.01):
        raise ValueError('Unexpected DEM extent')
values = [round(v) if math.isfinite(v) and abs(v) <= 20000 else None for v in data.flat]
output.write_text(json.dumps(dict(width=width, height=height, bounds_m=[-radius, -radius, radius, radius],
    reference_radius_m=1737400, resolution_m=step_x, source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
    values=values), separators=(',', ':')) + '\n')
print(f'Wrote {width} x {height} elevations to {output}')
