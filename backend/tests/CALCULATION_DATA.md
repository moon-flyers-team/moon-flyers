# Checking the functions with current terrain code and JPL data

From the repository root, in your Python environment:

```sh
python3 -m pip install -r backend/requirements-dev.txt
python3 -m pytest backend/tests backend/app/Functions/Tests -q
```

Use `.venv/bin/python` instead of `python3` if needed. Expected: **57 passed,
2 skipped**. Default tests are offline.

## What the default tests verify

`test_calculation_data.py` calls the current `src.lunar_horizon_dem.horizon()`
function. Its offline DEM is a controlled reference sphere, explicitly not real
lunar terrain. This lets us run the actual ray/horizon/slope algorithm without
large raster downloads, check the returned coordinates, and match the observer
altitude to the recorded JPL query. The old teammate sample is no longer an input
to these integration checks; it remains only as a historical unit-test fixture.

The recorded live JPL response in
`app/Functions/Tests/fixtures/horizons_positions.json` contains request/retrieval
metadata: Shackleton catalogue coordinates, 1–31 August 2027, hourly steps,
altitude 0 m above the reference sphere. It was obtained through this repository's
`src.positions.positions()` with an actual network request, not a mock generator.

Tests check:

- Provider field conversion, explicit UTC, and removal of the inclusive stop sample.
- A complete 30-day evaluation with flat and function-generated sphere horizons.
- Independent skyline interpolation, disc clearance, crossing times, visible durations,
  longest gaps, default suitability violations, and API schema compatibility.
- Landing searches at half-hour offsets and fractional-day mission durations.
- Returned terrain coordinates, altitude, slope, coverage, and array sizes.

## Full real-terrain + live JPL check

After installing/calibrating the LOLA rasters using `src/lunar_horizon_dem.py`, run:

```sh
LOLA_DEM_DIR=/absolute/path/to/lola_dem MOON_FLYERS_LIVE_TERRAIN=1 \
  python3 -m pytest backend/tests/test_calculation_data.py \
  -k live_terrain_and_jpl_for_same_observer -v
```

This calls `horizon(latitude, longitude, height_above_terrain=2)` on the real DEM,
then calls `positions()` using the returned coordinates and
`altitude_m + height_above_terrain`. It runs a three-hour evaluation with the
returned skyline and slope, checks the response schema, and checks metrics against
window durations. Missing raster files, missing coverage, and JPL failures fail the
test when enabled; no synthetic fallback is used. The test is skipped by default.

Only the calibration file is present in this checkout; the real-raster test has not
been run here. The other skipped test is the pre-existing live ephemeris-provider
check (`MOON_FLYERS_LIVE=1`).

## Remaining integration limits

- The running API's `src/services/analysis.py` still uses its separate calculations,
  not `app/Functions/evaluate_site.py`; its horizon service still uses mock terrain.
- Body angular radii are the existing backend approximations (Sun .267°, Earth .95°),
  not values returned by the current JPL query.
- Disabled-body function outputs do not currently match the API's non-null metric/fit
  schema; an adapter or deliberate contract change is needed for that mode.
- The Dockerfile copies only `src`, so it does not deploy `app/Functions` yet.

These changes add verification, not production endpoint wiring. No calculation
behavior was changed.
