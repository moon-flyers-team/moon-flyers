# Progress log

Single source of truth for where the work stands. Update at the end of every
work chunk. Newest info at the top of each section. Dates are YYYY-MM-DD.

## Now
- **Real Sun/Earth positions from JPL Horizons are live (2026-11-14, branch `plug-positions-py`).**
  `services/ephemeris.py` calls `positions.positions()`; header `X-Moon-Flyers-Data-Source: horizons`.
  Terrain is still the mock hills. `MOON_FLYERS_EPHEMERIS=mock` switches back to synthetic data
  (`services/mock_ephemeris.py`), and `tests/conftest.py` sets it, so pytest stays offline.
  19 tests pass, plus 1 live test opt-in via `MOON_FLYERS_LIVE=1`.
  Live timing: `GET /sites` (1 site, 3 weeks) ≈ 2.3 s; a 3-month, 7-site `/compare` ≈ 24 s (14 sequential
  Horizons calls), ≈ 0.7 MB. The frontend's parallel burst (`/compare` + 7 `GET /sites`) ≈ 33 s, all 200.

## Next up (backend)
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
**The source of truth is [API.md](API.md)** (v0, agreed with the frontend team on 2026-11-14).
Endpoints: `GET /sites` (catalogue, plus single-site `analysis` over the whole window),
`POST /compare` (per-site `window_metrics` for every `candidate_step_hours` landing, plus
`timeline`), `POST /landing-windows`, `GET /health`.

`docs/API.md` was replaced with the team's new contract on 2026-11-14 (it had been my outdated v0
draft). Error policy (user decision): **only the HTTP status codes matter**. 400 = malformed JSON,
404 = unknown `site_id`, 422 = invalid input or request too large, 502 = JPL Horizons failed or unreachable. Bodies keep FastAPI's default
`{"detail": ...}`, and we don't promise a body shape.

To raise with the frontend team:
- API.md still says the mock lives in `frontend/src/mock/` (Node) and the backend is the bare
  scaffold. There are now two mocks (theirs in Node, ours in Python), so agree which one they use.
- Site ids and list: ours (7 sites in `services/catalogue.py`) were invented. Their mock UI shows 10.
- The Node mock's 0.4 s artificial delay isn't in the Python mock.

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
