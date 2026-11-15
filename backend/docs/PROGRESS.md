# Progress log

Single source of truth for where the work stands. Update at the end of every
work chunk. Newest info at the top of each section. Dates are YYYY-MM-DD.

## Now
- **Default POI-adjacent references (2026-11-15, branch `feat/poi-default-sites`).** Preserved
  the seven original sites; added Athena's published observed landing location plus 13
  explicitly unvetted exploration references at published feature centres. NASA candidate
  region context informed Nobile/Faustini; their centres are not candidate rim points.
  All additions are in 80°S–90°S. The 21-site catalogue covers 49/61 POIs (80.3%) within
  40 km versus 14/61 before, using the POI endpoint's area/point distance semantics.
  Sources, remaining gaps and frontend loading impact: root `docs/poi-sources.md`.
  No frontend/mock catalogue changes; App currently enables every returned site, increasing
  initial analysis work. References are not certified landing locations or reachable routes.
- **Real `slope_deg` (2026-11-15, branch `feat/real-slope`).** `DemHorizon` carries the DEM's
  site slope (`lunar_horizon_dem.horizon()["slope_deg"]`, 0.1°); `metrics.slope_deg` reports it,
  `null` without a DEM (mock hills never invent a slope). `fit` adds `"slope_deg"` to
  `violations` when over `max_slope_deg` but keeps `status` (power/comms only). The frontend
  already renders it (Terrain column + ⚠ from violations). Tested on the synthetic fixture only:
  no local copy of the real dataset.
- **No ranking; `POST /landing-windows` removed (2026-11-15, branch `chore/remove-landing-windows`).**
  User decision: the choice of site and landing time is manual, from the `/compare` data (whole
  window in one response; slider and ◀ ▶ arrows are frontend-only). Removed the router,
  `services/ranking.py`, `LandingWindow`/`LandingWindowsRequest` and the test. The UI never
  called it (`api.landingWindows` in `frontend/src/api.ts` is dead code; tell the frontend to drop it).
  A headroom ranking (per-constraint margins) was built and dropped; it is in `git stash`
  ("compare-rank (discarded)") if ever needed.
- **`POST /recommended-sites` published POIs (2026-11-15, branch `feat/real-poi-recommendations`).**
  Replaces the mocked mission ranking, including its request/response contract. Takes a landing
  `site` (catalogue ID or coordinates) and optional `radius_km` (40); returns all nearby POIs
  nearest first without scores/ranks. Bundled 61-record NASA Moon Trek/NASA/LROC snapshot:
  55 natural features, four impacts, two landers; footprint intersection with 80°S–90°S.
  Circular feature extents are explicitly approximate; hardware points have unquantified
  uncertainty. No in-cap caves/pits in the checked 278-entry LROC atlas; not evidence of absence.
  No synthetic fallback or ephemeris/terrain dependency. Sources: root `docs/poi-sources.md`.
  Frontend integration is out of scope. Root `API.md` owns this revised endpoint contract.
- **`POST /route` mock (2026-11-15, branch `make-mock-path`).** Ordered waypoints (SiteRef) →
  densified path every `step_m` m, legs, total distance. `method: "straight_line"` = great-circle
  segments, terrain ignored. Logic in `services/route.py`; contract in API.md section 5.
- **Earth eclipse windows (2026-11-15).** `timeline.eclipse` / `windows.eclipse`: Sun–Earth
  separation < 0.267° + 0.95° and Earth visible. Live Horizons shows the 2027-08-17 penumbral
  lunar eclipse (06:00–10:00Z) at near-side sites. Hourly sampling can miss very short events.
- **LOLA DEM dataset is provisioned, verified and deployable (2026-11-14, branch
  `feat/beelink-lola-terrain`, rebased on `main`).** The real archive (`lola_dem.rar`: eight
  IMG/LBL pairs + `calibration.json`, 15.9 GB) passes `tools/lola_data.py verify`: polar vs global
  terrain agree to 0.9-2.5 m median (14 m worst), so the recorded polar variants are correct.
  `deploy.sh` mounts it read-only per environment (`LOLA_DEM_DIR=/data/lola`) and startup refuses a
  broken dataset. Real timings at the site: 22-69 ms per `horizon()` call, and
  `tests/test_calculation_data.py -k live_terrain` passes against live JPL in 1.5 s.
  **The API now serves that terrain horizon.** `services/horizon.py` returns a `DemHorizon`
  built from `lunar_horizon_dem.horizon()` whenever `LOLA_DEM_DIR` is set, cached per site
  (22-69 ms per site; `/sites` with mock ephemeris answers in 0.01 s). Without the variable it
  keeps `MockTerrainHorizon`, so existing deployments are unchanged. At (-89.9, 0) the skyline
  runs -3.2 to +23.8 deg and the first hourly sample is in shadow.
- **Real Sun/Earth positions from JPL Horizons are live (2026-11-14, branch `plug-positions-py`).**
  `services/ephemeris.py` calls `positions.positions()`; header `X-Moon-Flyers-Data-Source: horizons`.
  Terrain is still the mock hills. `MOON_FLYERS_EPHEMERIS=mock` switches back to synthetic data
  (`services/mock_ephemeris.py`), and `tests/conftest.py` sets it, so pytest stays offline.
  19 tests pass, plus 1 live test opt-in via `MOON_FLYERS_LIVE=1`.
  Live timing: `GET /sites` (1 site, 3 weeks) ≈ 2.3 s; a 3-month, 7-site `/compare` ≈ 24 s (14 sequential
  Horizons calls), ≈ 0.7 MB. The frontend's parallel burst (`/compare` + 7 `GET /sites`) ≈ 33 s, all 200.

## Next up (backend)
2. Check the terrain defaults against the team's PDF: `horizon()` uses `max_range_km=50`,
   `min_range_m=20`, `height_above_terrain=0`; catalogue sites are rim/massif sites, so the
   observer height and clearance conventions deserve a review.
1. Open a PR for `plug-positions-py`. Tell the frontend team: header is now `horizons`,
   `/compare` takes about 25 s, there's a new 502, and the frontend fires `/compare` plus one `GET /sites`
   per site in parallel (≈ 28 Horizons calls per param change).
2. Verify the site coordinates in `services/catalogue.py` (currently approximate, from the frontend mock
   and memory).
3. Deferred: LOLA terrain. Add a `HorizonModel` class in `services/horizon.py` and return it from
   `for_site()` instead of `MockTerrainHorizon`; everything else follows.
4. Possible improvement: interpolated rise/set crossings from the teammate's `origin/sun_earth_visibility_calc`
   branch (ours count whole sample steps).

## API contract
**The shared source of truth is root [API.md](../../API.md)**; [backend API notes](API.md)
retain backend-specific route documentation. The POI contract was revised on 2026-11-15.
Endpoints: `GET /sites` (catalogue, plus single-site `analysis` over the whole window),
`POST /compare` (per-site `window_metrics` for every `candidate_step_hours` landing, plus
`timeline`), `POST /landing-windows`, `GET /health`, `POST /route` (mock, straight lines),
`POST /recommended-sites` (published POI proximity, not mission ranking).

`docs/API.md` was replaced with the team's new contract on 2026-11-14 (it had been my outdated v0
draft). Error policy (user decision): **only the HTTP status codes matter**. 400 = malformed JSON,
404 = unknown `site_id`, 422 = invalid input or request too large, 502 = JPL Horizons failed or unreachable. Bodies keep FastAPI's default
`{"detail": ...}`, and we don't promise a body shape.

To raise with the frontend team:
- API.md still says the mock lives in `frontend/src/mock/` (Node) and the backend is the bare
  scaffold. There are now two mocks (theirs in Node, ours in Python), so agree which one they use.
- Site IDs/list: seven legacy approximate entries remain, now supplemented by 14 sourced
  location additions (21 total). The Node mock/offline catalogues are unchanged. App enables
  all returned entries by default; review initial loading cost and selection policy separately.
- The Node mock's 0.4 s artificial delay isn't in the Python mock.
- With LOLA terrain mounted, horizon elevations reach about -3 to +24 deg; the mock hills
  stayed within 0-1.5 deg. Check the chart's y-axis range, clearance labels and any
  hard-coded 0 deg assumptions against real profiles.

Decisions:
- 2026-11-15: no backend ranking of sites or landing times; the person chooses manually.
  `/landing-windows` removed (the UI never called it).

Implementation choices where API.md is silent:
- `GET /sites` analysis: `timeseries`/`windows` span window_start → window_end + days.
  `metrics`/`fit` are for a landing at window_start.
- `sun_visibility=false` / `earth_visibility=false` set those timeseries fields to `null`.
  Metrics are still computed.
- A custom site comes back with `id: null` and `group: "Custom"`. An unknown `site_id` gives 404.
- Limits: 90k samples per series (the Horizons maximum; it rejects more), 2,000 landing candidates, 1M mission samples, otherwise 422.
- Visible = `elevation − angular_radius ≥ horizon(az) + horizon_clearance_deg`
  (Sun 0.267°, Earth 0.95°).
- An interval's `end_utc` is the first non-visible sample (or the series end + one step).

## Decisions
_(date: decision, then why)_
- 2026-11-15: Keep `/recommended-sites`, replace its mocked ranking with real POI discovery.
  No dates/constraints/synthetic metrics. Default 40 km = user scenario 10 km/h × eight total
  driving hours / two for return; not terrain-aware reachability. ID or coordinates accepted,
  extra/ambiguous/nonfinite inputs rejected. All matches returned, distance then ID order,
  no rank field. Successful provenance header is `catalogue`, overriding ephemeris default.
  Real POIs stay distinct from landing sites; no inferred cave or rover coordinates.
- 2026-11-15: Bundle a reviewed source snapshot, not per-request external lookups. Radius uses
  published point or explicitly approximate diameter-derived spherical area (zero inside).
  Full footprints that intersect the cap are retained. Known LCROSS layer discrepancies and
  lack of in-cap atlas pits are documented. Refresh tool stops on truncation or a new in-cap
  pit requiring review; missing/invalid runtime catalogue fails rather than inventing data.
- 2026-11-14: **Terrain data is the archive's IMG/LBL + calibration, read by `lunar_horizon_dem.py`;
  no conversion, no rasterio.** An earlier attempt on this branch downloaded JP2s and converted
  them to COGs, but `main` already had a loader (memmap + PDS labels) and the team had the IMG
  archive, so the pipeline validates and mounts what that loader reads. Drops the extra
  GDAL/libexpat dependency from the image.
- 2026-11-14: **`LOLA_DEM_DIR` is the one variable** (read by the loader, set by the compose
  overlay). The host path is snapshotted per release as `LOLA_DATA_DIR` in `.env`.
- 2026-11-14: **Verification is strict and offline.** `verify_dataset` fails on incomplete files,
  wrong scaling/sample type, non-published grids, bad calibration keys, and polar/global
  disagreement > 1 km. Startup runs the same checks (0.4 s) so a bad mount rolls the deploy back;
  SHA-256 stays in the CLI (`--hash`) because reading 15.9 GB does not belong in a boot.
- 2026-11-14: **The DEM horizon is opt-in and cached per site.** `for_site()` reads
  `LOLA_DEM_DIR` at call time, keeps one `DEM` per directory (memory-mapped) and one 360-value
  skyline per rounded coordinate. An uncovered coordinate or unreadable DEM falls back to a flat
  horizon with a warning instead of failing the request; startup has already refused broken
  datasets. `slope_deg` stays `null` until the contract question is settled.
- 2026-11-14: **Fixtures must not be mirror-symmetric in longitude.** A synthetic DEM that varies
  only as `cos(lon)` cannot distinguish axis variants 0 and 2 (lon negated); the fixture adds a
  `sin(2*lon)` term, and a test proves a wrong variant is caught by the cross-check.
- 2026-11-14: Ephemeris source is chosen by env var `MOON_FLYERS_EPHEMERIS` (default Horizons; `mock` for
  tests/offline), not FastAPI `Depends`. Why: simplest switch, and tests stay offline. Horizons failures → 502,
  and a step `positions()` can't express → 422.
- 2026-11-14: **Mock-first.** Ship contract-shaped mock data so the frontend can integrate,
  then swap in real ephemeris. **Ephemeris = live JPL Horizons** (via `src/positions.py`).
- 2026-11-14: **LOLA terrain is deferred.** The PDF rates it "Very High", but the user's call is
  to get the Musts working first on a flat 0° horizon. Terrain outputs (`slope_deg`, real
  `horizon_*`) come later.
- 2026-11-14: **Working over efficient.** No caching, no precomputation, no performance work.
  Compute everything on demand in the simplest correct way. Slow is fine; revisit only if
  something becomes unusable.
- 2026-11-14: The backend is a **hosted Python server exposing a REST API** (FastAPI, JSON),
  not a local-only demo. This affects the design:
  - Data files (SPICE kernels and/or the LOLA DEM) must ship with the deployment or download at
    startup. Keep them a sensible size (polar DEM tiles can be hundreds of MB).
  - CORS needs the production frontend origin from config, not only `localhost:5173`.
  - Config through env vars (`pydantic-settings`).
- 2026-11-14: Our files live only in `backend/` or stay local (untracked). Nothing new goes
  at the repo root or in `frontend/`, because those are shared with the frontend teammate.
- 2026-11-14: The user owns the backend; the frontend is out of scope unless asked.

## Open questions
- From the requirements PDF (ask the team):
  - "Days on surface (lunar or Earth days?)": which unit? Proposal: return both Earth days
    (hours / 24) and lunar days (÷ 29.53).
  - "Horizon clearance": what is it? Proposal: min (body elevation − mask) over the window.
  - "Power: min/max sunlight/Earth": min/max of what? Visibility % per lunar day, or per
    sliding window?
  - `slope_deg` and `altitud…` need a DEM, so they're deferred with LOLA. The altitude row is
    unfinished in the PDF.
  - `options.*_visibility`: booleans that skip the Sun or Earth calculation? Assumed so.
- Implementation details to verify:
  - Longitude and step handling are done in the teammate's `positions.py` (normalises to 0..360;
    whole minutes as `N m`, otherwise unitless N steps).
  - Angular radius for the "entire disc" checks: request Horizons quantity 13 (angular diameter),
    or use constants (Sun ≈ 0.27°, Earth ≈ 0.95° seen from the Moon).
- (Deferred) DEM: which LOLA product and resolution for the south pole (for example 80°S+ polar
  stereographic at 20–60 m/px)? How large a horizon search radius?
- Hosting: answered. A teammate deploys Docker to "Beelink" via GitHub Actions. The frontend
  nginx proxies `/api` to the backend, so production is same-origin and CORS shouldn't matter
  there (to verify).

## Verified facts
- 2026-11-14: Horizons concurrency limit: about 2 open requests per IP. More → `HTTP 503 Service Temporarily
  Unavailable` after ≈1 s. Also max 90,000 times per request ("Output length exceeded").
- 2026-11-14: The Horizons API works for a lunar surface observer. Working query
  (Sun = `COMMAND='10'`, Earth = `'399'`):
  `https://ssd.jpl.nasa.gov/api/horizons.api?format=text&COMMAND='10'&EPHEM_TYPE=OBSERVER&CENTER='coord@301'&COORD_TYPE=GEODETIC&SITE_COORD='<E-lon deg>,<lat deg>,<h km>'&START_TIME=...&STOP_TIME=...&STEP_SIZE='6h'&QUANTITIES='4'`
  - Returns airless apparent azimuth (clockwise from north) and elevation in degrees of the
    target's **centre**. Elevation is "with respect to a plane perpendicular to the reference
    surface local zenith direction". The header shows reference radii 1737.4 km (sphere),
    MEAN_ME frame, DE441. The daylight flag `*` uses the Sun's **upper limb**.
  - **Confirmed: no terrain.** The manual (rise/set "RETS" section) defines its horizons as
    "TVH: horizon seen by an observer on the reference ellipsoid … but not local topography"
    and "GEO: plane perpendicular to the reference ellipsoid local zenith (no horizon dip)".
    For hills it only suggests one global elevation cut-off (for example 10°), which is useless
    for polar craters. So we need our own per-azimuth LOLA horizon mask.
    Source: https://ssd.jpl.nasa.gov/horizons/manual.html
  - Rows sit between `$$SOE` and `$$EOE`. Flag `*` means daylight, `i` means Earth up.
    It can return HTTP 200 with an error, so check the body or JSON `error`.
  - Limits: `TLIST` takes at most 10k times; steps must be at least 0.5 s.
  - Sample at (0°E, 89.5°S) on 2026-11-14: Sun az ≈ 127→114°, el ≈ +1.3° (grazing).
    Earth az ≈ 358.8°, el ≈ −4.1→−3.1°. Its centre is below the local horizontal plane, and
    Earth's angular radius is only about 1°, so it's fully hidden even before terrain.

## Done
- 2026-11-15: Added POI-adjacent catalogue defaults with source/safety labels and a measured
  >=80% coverage regression test. New IDs resolve through GET catalogue, site analysis and
  POI search without changing response shapes. Checked after rebasing onto current main
  (real-slope and landing-window removal preserved): backend pytest **107 passed, 2 skipped**;
  ruff on both changed Python files clean; `git diff --check` clean. Tests use offline
  ephemerides; no new real terrain or landing-safety validation is claimed. Frontend unchanged.
- 2026-11-15: Replaced the mocked `/recommended-sites` implementation with sourced POI
  proximity; added bundled catalogue, stdlib refresh/source-survey tool, source documentation,
  strict request/geometry models and 40 focused tests. Nonfinite validation inputs now serialize
  safely as 422 instead of crashing the error response. Explicit Docker-ignore exceptions keep
  the small POI catalogue shippable while terrain stays excluded.
  Verification: backend pytest **88 passed, 2 skipped** (opt-in live checks), changed-file ruff
  clean, `git diff --check` clean. Real local Uvicorn HTTP checks passed for default 40 km
  lookup, Athena point, 404/422, health and OpenAPI with default live ephemeris configuration.
  Whole-backend ruff reports **14 pre-existing violations in untouched files**; no unrelated
  lint cleanup. Docker build not run (Docker unavailable); frontend unchanged/not rebuilt.
- 2026-11-14: Measured request cost of the DEM horizon (mock ephemeris, real 15.9 GB archive,
  `TestClient`, so no HTTP overhead): `/compare` for 7 sites over 3 months is 0.88 s with a cold
  DEM cache and 0.18 s warm, versus 0.21 s for the mock hills; `/sites` for one site is 21-36 ms.
  Per site the first skyline costs roughly 30-95 ms (memory-mapped rasters, page cache cold), and
  repeats are free. Against ~24 s of live Horizons latency that is negligible; using real terrain
  is not a latency problem.
- 2026-11-14: **The API serves real terrain** when a dataset is mounted: `DemHorizon` in
  `services/horizon.py` plus `tests/test_horizon_dem.py` (mock without the variable, DEM profile
  through `/sites` with it, cache reuse, flat fallback). Real-data check: `/sites` 200 in 0.01 s.
- 2026-11-14: **Dataset provisioning, verification and read-only mount** (branch
  `feat/beelink-lola-terrain`, rebased onto `main`): `lunar_horizon_dem.verify_dataset()` (labels,
  sizes, scaling, published shapes, calibration, polar/global cross-check),
  `tools/lola_data.py verify|--hash`, `deploy/compose.terrain.yaml`, per-environment
  `terrain-directory` in `deploy.sh`, startup validation via `LOLA_DEM_DIR`, stdlib fixture
  (`tools/lola_fixture.py`) and a CI step that boots the real image on it. Verified on the real
  archive: cross-check medians 1.5/0.9/2.5/1.1 m, `horizon()` 22-69 ms, live JPL test passing.
- 2026-11-14: Fixed 502s in the UI ("HTTP Error 503" from Horizons). Horizons answers 503 when one IP has
  more than about 2 requests open (measured: 2 parallel OK, 4 → half fail). `ephemeris.py` now allows at most 2
  `positions()` calls in flight (process-wide semaphore) and retries 503 with 1/2/4/8 s backoff.
- 2026-11-14: Swapped in live JPL Horizons via `positions.py` (removed its debug `print`). The mock moved to
  `services/mock_ephemeris.py`. The adapter makes timestamps UTC, checks Horizons' time grid matches ours,
  and maps errors to 422/502. Tests: `tests/conftest.py` (forces mock), `tests/test_ephemeris.py`.
- 2026-11-14: Mock terrain horizon (`MockTerrainHorizon` in `services/horizon.py`): smooth
  0–1.5° hills seeded by site coordinates, taller near the pole, and it blocks the Sun/Earth.
  It was first up to 4°, but then the polar rim sites failed on power for every landing, so it was lowered.
  The test environment (https://moon-flyers.tail644248.ts.net:8443) serves the mock API since PR #4.
- 2026-11-14: Modifiability/testability pass. Horizon is now a per-site model (`services/horizon.py`).
  Services raise domain errors (`services/errors.py`) that are mapped to HTTP in `main.py`. Logic
  moved out of routers (timeseries and window metrics into `SiteSeries`, ranking into
  `services/ranking.py`). GET /sites reads one `SitesQuery` model that inherits `Constraints`.
  Added ruff (basic F/E rules) for typo checks.
- 2026-11-14: Split into `routers/` (one file per endpoint) and `services/` (catalogue,
  ephemeris, visibility, analysis); `main.py` is setup only.
- 2026-11-14: Mock API for the v0 contract: `src/schemas.py`, mock services, endpoints, `tests/test_api.py`, `requirements-dev.txt`.
- 2026-11-14: Added `docs/requirements.md` (transcribed team PDF) and re-planned around it.
- 2026-11-14: Checked resource links. Quickmap and Trek are JS apps (no fetchable content);
  Horizons, its API docs, CSA and PDS Geosciences all load.
- 2026-11-14: Initial scaffold (FastAPI `/` and `/health`, React/Vite app). Commit `f9319b6`.
- 2026-11-14: Added `backend/CLAUDE.md`, `backend/docs/PROGRESS.md`, `backend/docs/challenge.md` and a local-only root `CLAUDE.local.md` that imports it.

## Known issues
- (resolved 2026-11-14) Transient TLS cert error. All resource hosts are reachable now.
