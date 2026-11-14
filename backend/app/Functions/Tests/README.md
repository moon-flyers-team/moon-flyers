# Calculation tests

Run from the repository root; no running API or frontend is needed:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r backend/requirements.txt
.venv/bin/python -m unittest discover -s backend/app/Functions/Tests -v
```

Expected: 14 tests, all `OK`.

`test_core.py` checks individual functions: whole-disc clearance, horizon wrapping,
interpolated crossings, visibility intervals, percentages, longest outages, missing
bodies, invalid inputs, and fit statuses.

`test_pipeline.py` passes known angles through visibility → windows → metrics → fit.
In its two-hour example, the Sun sets at 00:30 and Earth rises at 00:30. Expected
sunlight is 25%, Earth visibility 75%, longest darkness 1.5 hours, and longest Earth
blackout 0.5 hours. This checks the functions work together without a mock server.

## Connecting the real backend later

The API layer should orchestrate these functions; keep calculation logic here:

1. Obtain real per-timestamp Sun/Earth azimuths, elevations and angular radii,
   plus a complete terrain skyline in the same local horizontal frame. Validate
   units, coordinate conventions, and missing data before calculation.
2. Calculate each body's signed visibility margins with `calculate_visibility_margin`.
   Visibility flags are `margin >= 0`; `calculate_visibility` provides the same check.
3. Pass timestamps, flags, explicit interval end, and the same margins to
   `extract_visibility_windows` and `calculate_metrics` for consistent interpolated
   crossings. The final sample is held to the end; choose sampling accordingly.
4. Start the mission history exactly at landing, and score only its mission interval.
   Calculate any longer visualization or search timeline separately.
5. Call `evaluate_fit` with complete mission metrics and the requested thresholds.
   Disabled bodies have null metrics; skip fit when required metrics are unavailable.
   Slope is optional and is not scored by suitability.
6. Once real API endpoints exist, add endpoint contract tests and verify their
   responses against these function results. Then connect and test the frontend.

These tests verify calculation behavior using known inputs. They do not validate
real ephemerides, terrain accuracy, HTTP endpoints, or browser behavior.
