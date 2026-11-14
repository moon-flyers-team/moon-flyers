# Moon Flyers contributor handoff

## Purpose and scope

Moon Flyers is a NASA Space Apps Challenge 2026 entry for
[Lunar Landing Site Navigator](https://www.spaceappschallenge.org/2026/challenges/lunar-landing-site-navigator/).
The interface compares lunar landing sites and dates using sunlight, Earth visibility,
mission constraints, and a Sun/Earth horizon visualization.

These instructions apply throughout the repository. Read `API.md` before changing any
frontend/backend integration. It is the source of truth for the draft v0 wire contract;
this file explains how the current implementation uses it. Keep both documents current
when agreed behavior changes.

## Current handoff state

- The frontend is React 18, TypeScript, and Vite, using custom CSS and SVG charts.
- The frontend now implements the request and response formats in `API.md`, including
  comparison results, visibility timelines, and an on-demand best-landing-times table.
- Selected-site analysis fetches a whole lunar-day batch. The time slider was removed at the
  user's request because another contributor will implement it. The chart currently shows
  paths across the batch and markers/visibility for its first sample; do not add the slider
  back unless requested.
- API loading/error messages and retry controls are implemented. The offline banner occupies
  its own layout row above the dashboard and must never cover content.
- The real backend remains the original FastAPI scaffold in `backend/src/main.py`.
  `backend/src/positions.py` is a placeholder. Keep `backend/` clear of frontend/mock work.
- The separate mock API lives entirely in `frontend/src/mock/` and implements every v0
  endpoint with deterministic synthetic data. Run `pnpm mock:api`; it uses Node and requires
  no Python environment. `data.mjs` generates consistent samples, metrics, windows, and fit.
- The frontend identifies mock responses via `X-Moon-Flyers-Data-Source: mock` and labels
  them explicitly. Offline fallback data still contains example site metadata only. Do not
  present synthetic results as scientific predictions.

## Project structure

| Location | Responsibility |
| --- | --- |
| `API.md` | Endpoint contract, constraints, units, and response examples |
| `frontend/package.json`, `frontend/pnpm-lock.yaml` | Frontend scripts and dependencies |
| `frontend/src/main.tsx` | React entry point with StrictMode |
| `frontend/src/App.tsx` | Mission/constraint state, site catalogue, enabled sites, connection banner |
| `frontend/src/Sidebar.tsx` | Mission, power, communications, terrain, and site inputs |
| `frontend/src/MainPanel.tsx` | Landing time, validation, comparison and selected-site analysis requests |
| `frontend/src/api.ts` | Shared HTTP client, typed endpoint methods, request payloads, FastAPI error handling |
| `frontend/src/types.ts` | API response types and UI parameter types |
| `frontend/src/useRequest.ts` | Debouncing, abort handling, retry state, and suppression of obsolete responses |
| `frontend/src/time.ts` | UTC helpers and lunar-day constants |
| `frontend/src/ComparisonTable.tsx`, `FitBadge.tsx` | Backend metrics, fit statuses, and violation indicators |
| `frontend/src/TimelineBars.tsx` | Visibility intervals clipped to the displayed time range |
| `frontend/src/HorizonChart.tsx` | Horizon profile, Sun/Earth paths, and first-sample markers; slider deferred |
| `frontend/src/LandingWindows.tsx` | Explicit best-time search and applying a returned landing time |
| `frontend/src/Field.tsx`, `Section.tsx` | Shared sidebar primitives |
| `frontend/src/index.css` | Shared visual tokens and component styles |
| `frontend/src/mockData.ts` | Example catalogue used when the catalogue request fails |
| `frontend/tests/api.test.mjs` | Node contract tests and React server-rendering checks |
| `frontend/tests/mock-pipeline.mjs` | Live HTTP checks through Vite and the mock, using the real frontend client |
| `frontend/vite.config.ts` | React plugin, `@` alias, dev port, and API proxy |
| `backend/src/main.py`, `backend/requirements.txt` | Real API scaffold and Python runtime dependencies |
| `frontend/src/mock/server.mjs` | Standalone Node HTTP mock API on port 8000 |
| `frontend/src/mock/api.mjs`, `data.mjs` | Validated mock routes and deterministic generators |
| `frontend/tests/mock-api.test.mjs` | Mock contract/consistency tests with no server or Python dependency |

Keep frontend implementation inside `frontend/` and real backend implementation inside `backend/`.
All mock/demo API source belongs in `frontend/src/mock/`, and its tests belong in `frontend/tests/`.
Do not add mock code, Python environments, or generated test files under `backend/`.
The root `package.json` provides the `mock:api` convenience script; it is not the frontend application or a configured workspace.
Use the existing component files and shared helpers before introducing another abstraction or
moving files. Keep frontend dependency and lockfile changes together in `frontend/`.

## Local commands

Run from the repository root:

```sh
pnpm --dir frontend install
pnpm --dir frontend dev
pnpm --dir frontend test
pnpm --dir frontend build
```

The frontend declares pnpm 9.15.0 in its `packageManager` field. Vite serves development on
port 5173. The build checks both application and Vite-config TypeScript, then bundles the app.
Keep the two type checks; the earlier project-reference configuration failed to build.

For the standalone mock API:

```sh
pnpm mock:api
# Equivalent: pnpm --dir frontend mock:api
```

It uses Node's built-in HTTP server and needs no extra runtime dependencies. The configurable
analysis delay defaults to 0.4 seconds (`MOCK_API_DELAY_SECONDS`). `API.md` documents setup
and request examples. Unit/contract tests are included in `pnpm --dir frontend test`.
The original real backend scaffold is separate and uses `backend/requirements.txt`.
Stop the mock before starting a real backend on port 8000.

Without `VITE_API_URL`, requests use `/api`; the Vite development proxy forwards them to
`http://localhost:8000` and removes `/api`. Alternatively, set `VITE_API_URL` in
`frontend/.env` using `frontend/.env.example`. The current backend permits CORS from
`http://localhost:5173`. Production needs an API base URL or a corresponding reverse proxy;
the Vite development proxy is not production hosting configuration. Keep local environment
files out of commits.

## API integration rules

Route HTTP requests through `frontend/src/api.ts`. Preserve snake_case names on the wire and
the underscore fit statuses: `both_met`, `power_short`, `comms_short`, `neither_met`.

| Client method | HTTP request | Use |
| --- | --- | --- |
| `getSites` | `GET /sites` without parameters | Catalogue only |
| `getCatalogue` | `GET /sites` without parameters | App catalogue plus mock header metadata; same server response shape |
| `getSiteAnalysis` | `GET /sites?...` | Selected site, time series, horizon, metrics, windows, fit |
| `compare` | `POST /compare` | Enabled sites, mission metrics, and visibility timeline bars |
| `getLandingWindows` | `POST /landing-windows` | Ranked candidate landing times |
| `health` | `GET /health` | Available health check; not currently used for polling |

- Site analysis uses `site_id` in the query, or custom `name`, `latitude_deg`, and
  `longitude_deg`. Constraints are flattened into its query parameters.
- Comparison uses `sites`, `landing_utc`, `window_start_utc`, `window_end_utc`, nested
  `constraints`, and `timestep_seconds` in a JSON body. Responses follow request-site order;
  the table currently associates them by index.
- Best-time search uses one `site`, the window bounds, nested `constraints`, and defaults of
  `candidate_step_hours: 6` and `limit: 5`. It runs only when the user requests it.
- The client supports custom-site request objects; there is no custom-site editor or persistence
  UI yet. Custom sites belong on the client and must be sent with each request.
- Send ISO 8601 UTC timestamps with a timezone suffix. Date-only sidebar bounds become
  midnight UTC. Angles are degrees; azimuth runs clockwise from north; longitude is east-positive.
- Use backend `fit.status` and `fit.violations` for badges and warnings, including communication
  violations. Render `slope_deg: null` as `—`. API v0 has a flat 0° horizon and no terrain slope.
- Display timeline bars from `window_start_utc` through `window_end_utc + days_on_surface`.
  Clip intervals to that range and handle invalid or zero-length ranges without NaN values.
- The old `/analyze` and `/sites/:id/horizon` routes are obsolete; do not restore them.

## Lunar-day visualization and request lifecycle

Keep **mission scoring duration** separate from **visualization coverage**:

1. `/compare` and `/landing-windows` receive the user's `days_on_surface` unchanged
   (default 14). Mission constraints are assembled in `MainPanel.tsx`.
2. Selected-site visualization requests `days_on_surface: 30` with hourly samples
   (`timestep_seconds: 3600`). This whole-day batch covers the mean lunar solar day of
   29.5306 Earth days; constants and the NASA reference live in `time.ts`.
3. `HorizonChart.tsx` sorts and selects returned samples from landing through one mean lunar
   day. Markers, visibility, and the displayed timestamp currently use its first sample.
   Another contributor will add time-slider controls. That future slider should select samples
   locally without issuing requests or changing the mission landing time when scrubbing.
4. Changing the actual landing time, selected site, or relevant constraints may load a new batch.
   The comparison's ±6 h buttons change landing time and rerun analysis within the window.

Use each body's own azimuth/elevation and the current sample's `sun_visible`/`earth_visible`
flags. Do not label peak elevations as current positions or infer visibility from elevation
alone. Break paths at the 360°/0° seam to avoid lines spanning the chart.

Memoize request callbacks passed to `useRequest`; callback identity controls its lifecycle.
The hook debounces by 350 ms (catalogue loading uses zero), aborts superseded requests, and
hides obsolete data immediately. Preserve this behavior when inputs change or StrictMode
remounts effects. Keep loading states visible for the expected 10–30-second API responses.
The hook does not cache earlier site/date batches across requests.

## Checks and remaining work

Verification commands are `pnpm --dir frontend test` and `pnpm --dir frontend build`.
Tests cover payloads, custom-site serialization, UTC values, API failures, abort propagation,
timeline clipping, fit/violation rendering, first-sample markers, and chart path wrapping.
Frontend component tests use Vite SSR and React server rendering. Mock API tests exercise its
request handler directly, including cross-endpoint consistency, custom sites, validation, fit
ranking, CORS, and the default frontend request window. The mock needs no Python tests or dependencies.

With both servers running, `pnpm --dir frontend test:mock` checks real HTTP requests through
Vite and renders mock responses in the frontend components. After moving the mock to the
frontend, all 24 tests, the production build, and the live HTTP pipeline check passed. Browser
interaction still needs manual review.

For frontend integration changes, rerun these commands and update focused contract tests when
behavior changes. `pnpm --dir frontend lint` exists, but there is currently no ESLint config;
do not report lint as passing without configuring and running it. Documentation-only edits
do not require rebuilding the application.

Next integration work is to replace synthetic calculations with the real backend while keeping
v0 response shapes stable. Check the UI against the running mock, including slow responses, retries,
rapid site/constraint changes, best-time selection, and banner layout in a browser. Time-slider
implementation is assigned to another contributor. Terrain-aware horizons and slope calculations
remain outside API v0. Coordinate
contract changes across `API.md`, TypeScript types, the client, backend models, and tests.

Preserve the existing dark dashboard, amber sunlight and cyan Earth colors, keyboard-accessible
controls, and the banner's normal document flow. Keep changes scoped to the requested work and
preserve unrelated working-tree edits. Update this handoff when structure or integration
decisions change.
