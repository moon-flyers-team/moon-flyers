#!/usr/bin/env python3
"""Verify a LOLA DEM directory for Moon Flyers. No download, no Docker, no sudo.

The directory is the one `lunar_horizon_dem.py` reads, i.e. `LOLA_DEM_DIR`:
eight `LDEM_*.IMG`/`.LBL` pairs plus `calibration.json`.

    python3 backend/tools/lola_data.py verify --root ~/moon-flyers/data/lola/v1
    python3 backend/tools/lola_data.py verify --root ... --hash      # slower, also sha256
    python3 backend/tools/lola_data.py verify --root ... --no-cross-check

`verify` fails loudly rather than warning: a deploy should not serve a half-copied or
mis-calibrated dataset. Checks: every file present and complete, labels matching the
published shapes (and 0.5 m scaling), calibration covering exactly the polar products,
and polar terrain agreeing with the independent global tiles at 83/88 degrees.
"""

import argparse
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.lunar_horizon_dem import PRODUCT_SHAPES, verify_dataset  # noqa: E402


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("action", choices=("verify",), help="verify an existing dataset directory")
    parser.add_argument("--root", type=Path, default=Path.home() / "moon-flyers/data/lola/v1",
                        help="directory holding the LDEM_*.IMG/.LBL files and calibration.json")
    parser.add_argument("--no-cross-check", action="store_true",
                        help="skip the polar/global terrain comparison (metadata checks only)")
    parser.add_argument("--hash", action="store_true",
                        help="also record SHA-256 for every raster (reads all ~16 GB)")
    parser.add_argument("--allow-any-shape", action="store_true",
                        help="accept grids that are not the published release (synthetic fixtures only)")
    args = parser.parse_args()
    root = args.root.expanduser().resolve()
    try:
        summary = verify_dataset(root, cross_check=not args.no_cross_check,
                                 published_shapes=not args.allow_any_shape)
        if args.hash:
            summary["sha256"] = {
                name: sha256(root / f"{name}.IMG") for name in PRODUCT_SHAPES
            }
    except (OSError, ValueError, RuntimeError) as exc:
        print(f"LOLA dataset check failed: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(summary, indent=2))
    total = sum(p["image_bytes"] for p in summary["products"].values())
    print(f"OK: {root} ({len(summary['products'])} products, {total / 1e9:.1f} GB)", file=sys.stderr)
    if summary["cross_check"]:
        worst = max(v["median_abs_difference_m"] for v in summary["cross_check"].values())
        print(f"OK: polar/global agreement, worst median {worst:.0f} m", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
