# Moon Flyers — agent context

Auto-loaded every session. Keep it short and stable; put day-to-day state in
[docs/PROGRESS.md](docs/PROGRESS.md) (paths here are relative to `backend/`).

## Start of every session
1. Read `backend/docs/PROGRESS.md` (current status, next steps, decisions, open questions).
2. Check `git log --oneline -15` and `git status` for anything newer than the log.
3. Continue from "Next up" unless the user says otherwise.

## End of every work chunk (before the user switches sessions)
Update `backend/docs/PROGRESS.md`: move finished items to Done (with date), refresh
"Now / Next up", log any decision with its reason, add new open questions.
Keep it terse and factual; no narration.

## Project
NASA Space Apps Challenge 2026, **"Lunar Landing Site Navigator"**.
Build an intuitive tool to compare lunar landing sites (focus: south pole) and
dates by showing **Sun and Earth positions relative to the local horizon**, to judge:
- **Power**: solar elevation, sunlight duration, time to sunset.
- **Comms**: direct-to-Earth visibility windows, time to Earthset.

Audience: mission planners (fast what-if comparison when dates/sites slip),
educators, and the public.

Key domain facts:
- No atmosphere, so no refraction. The horizon is local terrain plus the edge of the lunar sphere.
- At the south pole the Sun and Earth sit near the horizon, so **terrain (LOLA DEM) dominates**
  visibility and small location or date changes matter a lot.
- Earth is never far from the same spot in the lunar sky, but **libration** moves it a few
  degrees, which decides Earth visibility at polar sites.
- Ephemeris sources: JPL Horizons, or SPICE kernels (DE440, lunar PA frame).
  Reference tools: NASA Quickmap, Moon Trek.
- Full challenge text: [docs/challenge.md](docs/challenge.md).
- **Team requirements (field names, priorities): [docs/requirements.md](docs/requirements.md).**
  The API must use those field names.

## Team split
- **The user owns the backend** (Python/FastAPI, `backend/`). Default to backend work.
- The frontend (React + TS + Vite, `frontend/`) is someone else's. Don't change it unless asked,
  but keep the API contract in `backend/docs/PROGRESS.md` up to date for them.

## Stack and commands
- Architecture: **hosted Python server, REST API (JSON)**. The frontend consumes it over HTTP.
- Priority: **working over efficient.** No caching or optimisation. Simplest correct code,
  computed on demand.
- Backend: FastAPI + Pydantic v2 in `backend/src/`. Files:
  - `main.py`: app setup only (CORS, data-source header, include routers).
  - `schemas.py`: Pydantic models for the API contract.
  - `routers/`: **one file per endpoint**: `health.py`, `sites.py`, `compare.py`,
    `landing_windows.py`. Keep them thin; logic goes in `services/`.
  - `services/`: **one file per piece of logic**. Services never import FastAPI.
    - `catalogue.py`: predefined sites, `resolve_site`.
    - `ephemeris.py`: Sun/Earth az/el series from live JPL Horizons (`positions.py`). `MOON_FLYERS_EPHEMERIS=mock`
      switches to `mock_ephemeris.py` (tests set this in `tests/conftest.py`).
    - `horizon.py`: `HorizonModel` per site (`for_site`). Mock terrain (`MockTerrainHorizon`, 0–1.5°) now; LOLA plugs in here.
    - `visibility.py`: visible flags, intervals, metrics, fit.
    - `analysis.py`: `SiteSeries` (timeseries, analysis, window metrics, timeline), landing candidates.
    - `ranking.py`: best-landing ordering.
    - `errors.py`: domain errors (`UnknownSiteError` → 404, `LimitExceededError`/`InvalidInputError` → 422,
      `EphemerisUnavailableError` → 502), mapped
      to HTTP in `main.py` only.
  - `schemas.py` also has `SitesQuery`: GET /sites query params as one model that inherits
    `Constraints`, so defaults live in one place.
  - `positions.py`: a teammate's live JPL Horizons client, wrapped by `services/ephemeris.py`.
  Contract: `docs/API.md`.
- Run from `backend/` with the **Windows Python** (`py -3.12`), not the MSYS one first on PATH
  (`C:\msys64\mingw64\bin\python.exe`), which has no wheels and fails to build pydantic-core:
  `py -3.12 -m venv .venv`, then `.venv\Scripts\python -m pip install -r requirements-dev.txt`.
  - Server: `.venv\Scripts\python -m uvicorn src.main:app --reload --port 8000`
  - Tests: `.venv\Scripts\python -m pytest -q`
  - Lint (typos, undefined names, unused imports): `.venv\Scripts\python -m ruff check .` (config: `pyproject.toml`)
  - Before finishing a change: ruff clean and pytest green.
- Deployment, set up by a teammate: on push to `main`, `.github/workflows/deploy.yml` builds
  `backend/Dockerfile` (runs `src.main:app` with `--root-path /api`) and deploys to "Beelink"
  over Tailscale. The CI smoke test (`deploy/smoke-test.py`) requires `/health` → `{"status":"ok"}`
  and `/health` in OpenAPI, so don't break those. Dev-only dependencies go in
  `requirements-dev.txt`, never in `requirements.txt` (the image).
- **LOLA terrain is host data, not repo data.** The dataset is eight `LDEM_*.IMG`/`.LBL` pairs
  plus `calibration.json` (15.9 GB) provided on the server; `src/lunar_horizon_dem.py` owns the
  format and `LOLA_DEM_DIR` points at it. It is mounted read-only at `/data/lola` only when that
  environment opted in, and `verify_dataset()` runs at startup. Verify a copy with
  `python3 backend/tools/lola_data.py verify --root DIR` (see `deploy/README.md` section 5).
  Never add rasters to Git, images, or CI artifacts; tests use the stdlib fixture
  `tools/lola_fixture.py`. With `LOLA_DEM_DIR` set, `src/services/horizon.py` serves a
  `DemHorizon` (cached per site); otherwise it serves `MockTerrainHorizon`. `slope_deg` is still
  always `null` until the frontend contract is settled.
- Frontend (pnpm): `pnpm --dir frontend dev` (port 5173, proxies `/api` to `:8000`).
- CORS allows `http://localhost:5173`.

## Environment gotchas
- 2026-11-14: one HTTPS fetch failed with an untrusted-root cert error (curl `SEC_E_UNTRUSTED_ROOT`).
  It was transient: later that day Horizons, Quickmap, Trek, CSA and PDS all loaded fine.
  If it comes back, don't disable cert checks without asking.
