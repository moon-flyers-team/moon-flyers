# Integrating the calculation functions into main

Reviewed against `origin/main` commit `c5a9e81` (14 November 2026).
This is a handoff, not an implementation of API integration.

## Where they fit

Main's `backend/src/services/analysis.py` orchestrates ephemeris, horizon, visibility,
mission scoring, and candidate searches. Keep its routers and response schemas.
Replace the calculation implementations behind `backend/src/services/visibility.py`
with calls to these functions, using a small adapter for existing service signatures.
Avoid maintaining two independent sets of calculation rules.

| Main service | Calculation function | Conversion needed |
| --- | --- | --- |
| `visible_flags` | `calculate_visibility_margin` / `calculate_visibility` | Obtain azimuth/elevation arrays from the horizon model; supply body radius and clearance |
| `intervals` | `extract_visibility_windows` | Convert aware datetimes to ISO strings; pass the explicit requested interval end; wrap returned dictionaries as `Interval` |
| `metrics` | `calculate_metrics` | Supply actual timestamps and mission end, not only flags and timestep; wrap result as `Metrics` |
| `fit` | `evaluate_fit` | Pass `m.model_dump()` and the four power/comms thresholds; wrap result as `Fit` |

The adapter can use `horizon.profile(model)` for the current flat horizon. For future
terrain, agree on sampling resolution: interpolating a sampled skyline may differ
from directly evaluating a higher-resolution horizon model.

## Integration decisions the backend team must handle

- **Package and deployment:** these functions are in `backend/app/Functions`, while
  main uses `backend/src`. Main's Dockerfile copies only `src`, so these files would
  be absent from the container. Move the calculation package under `src` and update
  imports/tests, or explicitly package/copy `app` too. Include NumPy in main's runtime
  requirements; this branch already declares it. (`app/Functions/rover_path.py` has
  already moved to `src/rover_path.py` for that reason and is now served by `POST /route`.)
- **Explicit mission bounds:** main generates samples including the history end.
  These window functions require every supplied timestamp to be strictly before the
  explicit end. Slice consistently to `[landing, mission_end)`; do not extend the end
  by a timestep to satisfy validation. Main currently rounds candidate indices and
  rounds duration up to full samples. Nonaligned landings and partial final steps
  need exact boundary samples or a documented interpolation policy.
- **Crossing policy:** main counts whole timesteps; these functions support that
  behavior when margins are omitted, or interpolate threshold crossings when margins
  are supplied. Use one policy consistently for metrics and windows. Interpolation
  changes numerical results and requires corresponding API test expectations.
- **Precision:** main rounds metrics to one decimal before evaluating fit. These
  functions return full precision. Prefer evaluating fit from full-precision metrics
  and rounding only for display; agree on boundary behavior before switching.
- **Disabled bodies:** main currently hides a body's timeseries fields but continues
  scoring both bodies. Its `Metrics` and `Analysis.fit` require non-null values.
  These functions also support genuinely disabled bodies with null metrics, for
  which fit must be skipped. Preserve main's display-only behavior or deliberately
  update the schemas and API contract; do not pass null metrics into `evaluate_fit`.
- **Time and real positions:** main's synthetic generator returns aware datetimes,
  which work when serialized with timezone offsets. Its separate `positions.py`
  helper returns timezone-free strings and no angular radii. Before connecting that
  provider, normalize real timestamps to UTC and supply verified body radii (or
  documented approximations). These functions deliberately reject naive timestamps.
- **Thresholds:** pass only `min_sun_visible_pct`, `max_darkness_hours`,
  `min_earth_visible_pct`, and `max_earth_blackout_hours` to `evaluate_fit`.
  Mission duration, clearance, and maximum slope belong to other stages. Slope is
  not scored here, matching main's current fit behavior.

## Evidence and acceptance

All 14 local calculation tests pass. An isolated check against main's actual schemas
and visibility module confirmed matching flags, metrics, windows, and fit for a
four-hour flat-horizon sample-and-hold example. Interpolated metrics also validate
against main's `Metrics` schema. This establishes interface compatibility for that
case, not full endpoint or deployment compatibility.

Before merging the integration, the backend owner should run main's API suite and
add cases for nonaligned candidate times, fractional mission durations, final-window
clipping, threshold boundaries before rounding, disabled-body semantics, and container
imports. Compare API responses with the function pipeline's expected values. Real
Horizons data and frontend verification remain separate later steps.
