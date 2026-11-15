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

- Python `POST /recommended-sites` now searches a real bundled POI catalogue near a landing
  site, not the former mocked mission ranking. Request: `site` (landing-site ID or coordinates)
  and optional `radius_km` (40 default). Response: published POIs and point/approximate-area
  distances, no scores/ranks. The 80°S–90°S cap includes boundary-crossing features. Successful
  responses use data-source header `catalogue`, independent of ephemerides. Frontend client
  now uses this contract. Mission Planner owns an applied search radius (40 km default);
  Route Planner explicitly searches nearby POIs and displays names/footprint distances.
  Radius changes hide prior results without reloading mission analysis. Node mock has no implementation. Root `API.md` owns the revised contract;
  `docs/poi-sources.md` records sources, cave/pit coverage limits and regeneration. POI IDs are
  not landing-site IDs. Do not invent cave, rover or suitability data for missing records.
- Python `GET /sites` has 21 entries (seven preserved plus 14 sourced location additions),
  covering 49/61 POIs within 40 km. Most additions are explicitly unvetted exploration
  references at published feature centres, not selected landing points. Sources/coverage are
  in `docs/poi-sources.md`; Node mock/offline catalogues are unchanged. App currently enables
  every returned site by default, so the larger catalogue increases initial analysis work.
- Python `POST /route` now serves the terrain planner as well as the mock. `planner`
  (`straight_line` default, or `terrain`) plus an optional `rover` block; `terrain` runs the
  bounded A* in `backend/src/rover_path.py` over the DEMs at `LOLA_DEM_DIR` (moved out of
  `app/Functions` so the Dockerfile ships it) and returns `method: astar_terrain`, per-point
  `elevation_m`, per-leg status/metrics and endpoint checks. It returns **503** rather than
  substituting terrain when no dataset is mounted, and 422 for planner limits/geometry or a
  request over 1,000,000 sampled cells. Rover limits are illustrative, not a vehicle spec;
  results are suggested candidate routes, with no travel-time, energy, illumination,
  keep-out or waypoint-order model. The frontend still requests `straight_line` and must be
  updated (types, `planner`, failure/503 rendering) before using it; root `API.md` documents
  both modes and the required frontend work.

- The frontend is React 18, TypeScript, and Vite, using custom CSS and SVG charts.
- The frontend now implements the request and response formats in `API.md`, including
  comparison results, visibility timelines and sampled Earth-eclipse intervals. Ranked
  landing times remain available through the client/API, but no best-times UI is mounted.
- MainPanel has Profiles and Map tabs, plus a Route Planner tab after explicitly choosing
  a landing site by double-clicking a comparison row (Shift+Enter on its site button).
  TouristRoutePanel lives only in Route Planner; selecting another landing site resets it.
  Profiles retains the existing dashboard and the
  contributor-added time slider; Map shows the 80°S–90°S lunar south-polar cap. Analysis
  preloads every enabled site over the mission window plus its stay. Scrubbing filters
  locally; the horizon axis stays fixed across the full loaded site batch.
- API loading/error messages and retry controls are implemented. The offline banner occupies
  its own layout row above the dashboard and must never cover content.
- Profiles shows an accessible loading popup while comparison or site-analysis batches are
  pending, including retries. It clears after both requests settle so errors/retry controls
  remain accessible. The overlay is confined to Profiles; tabs and settings remain available.
- FastAPI defaults to live JPL Horizons ephemerides; `MOON_FLYERS_EPHEMERIS=mock`
  selects synthetic positions. Terrain independently uses synthetic hills without a mounted
  DEM, a LOLA skyline with one, or flat fallback for uncovered sites/runtime DEM errors.
  The data-source header identifies ephemerides only, not terrain provenance or fallback.
- App's settings dialog owns draft mission/constraint edits. SET MISSION applies them to
  MainPanel; editing a draft does not request analysis. Sidebar owns site inputs and settings access.
- The separate mock API lives entirely in `frontend/src/mock/` and implements every v0
  endpoint with deterministic synthetic data. Run `pnpm mock:api`; it uses Node and requires
  no Python environment. `data.mjs` generates consistent samples, metrics, windows, and fit.
  `/compare` and `/landing-windows` build one hourly series per site and slice per candidate
  (`candidateMetrics`) instead of rebuilding every stay, mirroring the real backend.
- The frontend identifies mock responses via `X-Moon-Flyers-Data-Source: mock` and labels
  them explicitly. Offline fallback data still contains example site metadata only. Do not
  present synthetic results as scientific predictions.

## Project structure

| Location | Responsibility |
| --- | --- |
| `API.md` | Endpoint contract, constraints, units, and response examples |
| `frontend/package.json`, `frontend/pnpm-lock.yaml` | Frontend scripts and dependencies |
| `frontend/src/main.tsx` | React entry point with StrictMode |
| `frontend/src/App.tsx` | Draft/applied mission settings, settings dialog, catalogue, enabled sites, banner |
| `frontend/src/Sidebar.tsx` | Settings launcher, site toggles and manual custom-site entry |
| `frontend/src/MainPanel.tsx` | Profiles/Map/Route Planner tabs, landing selection/time, comparison and batch analysis requests |
| `frontend/src/TouristRoutePanel.tsx` | Route Planner map, local waypoints, explicit round-trip request and exports |
| `frontend/src/MapPanel.tsx` | Polar map, overlay controls, floating cursor readout, reference layers, and click-to-add site dialog |
| `frontend/src/map/` | Stereographic math, heatmap validation/color ramps, bundled feature catalogue |
| `frontend/public/maps/south-pole/` | NASA Moon Trek basemap tiles and source/projection metadata |
| `frontend/tests/map.test.mjs` | Map projection, custom-site requests, heatmap contract, and tab/map rendering |
| `frontend/src/api.ts` | Shared HTTP client, typed endpoint methods, request payloads, FastAPI error handling |
| `frontend/src/types.ts` | API response types and UI parameter types |
| `frontend/src/useRequest.ts` | Debouncing, abort handling, retry state, and suppression of obsolete responses |
| `frontend/src/useSiteBatch.ts` | Per-site comparison/analysis cache so enabling a site fetches only that site |
| `frontend/src/time.ts` | UTC helpers and lunar-day constants |
| `frontend/src/ComparisonTable.tsx`, `FitBadge.tsx` | Backend metrics, fit statuses, and violation indicators |
| `frontend/src/TimelineBars.tsx` | Visibility intervals clipped to the displayed time range |
| `frontend/src/HorizonChart.tsx` | Horizon profile, Sun/Earth paths, first-sample markers, and stable altitude bounds |
| `frontend/src/Field.tsx`, `Section.tsx` | Shared sidebar primitives; section actions stay outside collapse buttons |
| `frontend/src/DateField.tsx` | UTC date inputs with browser-native calendar controls and error associations |
| `frontend/src/index.css` | Shared visual tokens and component styles |
| `frontend/src/mockData.ts` | Example catalogue used when the catalogue request fails |
| `frontend/tests/api.test.mjs` | Node contract tests and React server-rendering checks |
| `frontend/tests/mock-pipeline.mjs` | Live HTTP checks through Vite and the mock, using the real frontend client |
| `frontend/vite.config.ts` | React plugin, `@` alias, dev port, and API proxy |
| `backend/src/main.py`, `backend/requirements.txt` | FastAPI endpoints and Python runtime dependencies |
| `backend/src/services/route.py`, `backend/src/rover_path.py` | `/route` legs (straight-line default, terrain A*) and the bounded rover planner |
| `backend/app/Functions/rover_path.py`, `backend/docs/ROVER_PATH_REVIEW.md` | Standalone rover route calculations and algorithm review; no route endpoint/UI yet |
| `backend/src/lunar_horizon_dem.py`, `backend/tools/lola_data.py`, `deploy/compose.terrain.yaml` | LOLA DEM loader/verifier, host dataset checks, and the optional read-only deployment mount |
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
The separate FastAPI backend uses `backend/requirements.txt`.
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
- Comparison uses `sites`, `window_start_utc`, `window_end_utc`, nested
  `constraints`, `candidate_step_hours`, and `timestep_seconds` in a JSON body. Responses follow request-site order;
  the table currently associates them by index.
- Best-time search uses one `site`, the window bounds, nested `constraints`, and defaults of
  `candidate_step_hours: 6` and `limit: 5`. The client/API exist; no current UI invokes this search.
- Map clicks open a named custom-site form. App owns all sites; custom entries are enabled
  immediately and survive catalogue retries, but are not persisted across browser reloads.
  `siteReference()` in api.ts sends custom name/coordinates for GET analysis, comparison, and
  landing windows; their UUIDs are React identities only and must never be sent as server IDs.
- Send ISO 8601 UTC timestamps with a timezone suffix. Date-only settings bounds become
  midnight UTC. Angles are degrees; azimuth runs clockwise from north; longitude is east-positive.
- Use backend `fit.status` and `fit.violations` for badges and warnings, including communication
  violations. Render `slope_deg: null` as `—`, even with a DEM mounted. Slope is not
  evaluated by fit; terrain horizons may be DEM, synthetic hills or flat fallback.
  Visibility does not establish link availability, energy sufficiency or safety.
- Display timeline bars from `window_start_utc` through `window_end_utc + days_on_surface`.
  Clip intervals to that range and handle invalid or zero-length ranges without NaN values.
- The old `/analyze` and `/sites/:id/horizon` routes are obsolete; do not restore them.

## Lunar-day visualization and request lifecycle

Keep **mission scoring duration** separate from **visualization coverage**:

1. `/compare` and `/landing-windows` receive the user's `days_on_surface` unchanged
   (default 14). Mission constraints are assembled in `MainPanel.tsx`.
2. Visualization requests enabled sites with the mission window, mission duration, and
   hourly samples (`timestep_seconds: 3600`). The batch extends through the window end plus
   the mission stay. Switching sites uses the preloaded data. `useSiteBatch.ts` caches one
   entry per site: a changed mission window or constraint set invalidates every entry, while
   enabling or disabling a site reuses the cache and fetches only sites with no entry (one
   comparison request for those sites plus one analysis each). Disabling a site or
   re-enabling a cached site makes no request.
3. `HorizonChart.tsx` selects returned samples from the current time through one mean lunar
   day. Markers use the first available sample in that slice. The full site batch determines
   altitude-axis bounds. The custom timeline slider updates time locally; ±6 h buttons
   are no longer mounted.
4. Applied mission dates/constraints or enabled sites load new batches. A site with no cached
   entry renders as pending (`—`) until its own response arrives. Comparison returns
   `window_metrics`; the table matches numeric UTC instants exactly, accepting equivalent
   timestamp spellings. Missing samples show “Not sampled”, never first-candidate evidence.
   The native Landing time (UTC) field supports keyboard editing on the 6-hour grid and
   changes selection locally without fetching; retain the custom timeline as another input.
   The timeline marker turns green only for the exact selected candidate's passing backend
  fit (both_met with no violations), not instantaneous Sun/Earth visibility.
  `SurfaceStayWindow` in TimelineBars shades landing through `days_on_surface` on the
   slider and every site's timeline. It follows selection locally and clips to the visible
   range; a dashed right edge indicates the stay continues beyond view. Keep its duration
   tied to applied scoring constraints, not the lunar-day chart coverage.

Use each body's own azimuth/elevation and the current sample's `sun_visible`/`earth_visible`
flags. Do not label peak elevations as current positions or infer visibility from elevation
alone. Break paths at the 360°/0° seam to avoid lines spanning the chart.
Calculate the horizon chart's altitude bounds from the entire loaded site timeseries and
terrain profile, not the displayed lunar-day slice. Scrubbing must keep the scale fixed;
new site or mission batches may recalculate it.

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
frontend, the earlier 24-test suite/build/pipeline passed. This is historical, not current
acceptance. The verification repair adds current contract/component fixtures and an
isolated HTTP runner (`pnpm --dir frontend test:mock:isolated`); see
`docs/verification-repairs.md` for executed checks and limits. Re-run the suite/build/pipeline
for each change; browser interaction needs separate review.

For frontend integration changes, rerun these commands and update focused contract tests when
behavior changes. `pnpm --dir frontend lint` exists, but there is currently no ESLint config;
do not report lint as passing without configuring and running it. Documentation-only edits
do not require rebuilding the application.

Live Horizons and terrain-aware horizons already exist. Remaining integration work includes
reporting per-analysis terrain provenance/fallback and implementing slope only after its
contract is agreed. A verified LOLA DEM is checked at startup (`deploy/README.md` section 5);
without it the backend uses synthetic hills. Mounted but uncovered sites can fall back to
flat. `slope_deg` remains null and its threshold is not enforced. Check slow responses,
retries, applied-settings changes and banner layout in a browser. Coordinate contract changes
across `API.md`, TypeScript types, client, backend models and tests.

Preserve the existing dark dashboard, amber sunlight and cyan Earth colors, keyboard-accessible
controls, and the banner's normal document flow. Keep changes scoped to the requested work and
preserve unrelated working-tree edits. Update this handoff when structure or integration
decisions change.

## Map handoff

- The map uses spherical lunar south-polar stereographic coordinates, radius 1,737,400 m,
  central meridian 0°, with 0°E at the top. Limit the surface and cursor picks to 80°S–90°S.
  Zoom follows the cursor; right/middle drag or two-finger scrolling pans. Reset view restores
  the entire cap. Out-of-cap sites remain
  in the sidebar and Profiles and are counted in a map notice.
- `frontend/src/map/navigation.ts` owns camera bounds (1×–16×), cursor-anchored zoom and
  wheel classification. Smooth pixel wheel deltas pan; coarse vertical/line wheel ticks zoom.
  Ctrl+wheel pinches zoom, Safari gesture events are supported, and Shift+scroll explicitly
  pans. Browsers expose no reliable mouse/trackpad device identifier, so wheel classification
  is heuristic; keep the Shift fallback and on-map instructions. Non-passive wheel handlers
  prevent browser/page zoom over the surface. Pointer capture keeps right-drag working
  outside the map; context menus are suppressed only on the map.
- Default site markers are red; custom markers are cyan and have keyboard-accessible
  edit tooltips. App owns rename/delete callbacks and guards them to custom sites only.
  Renaming/deleting updates Sidebar and Profiles too; coordinates and local IDs stay stable
  on rename. Both add/edit tooltips dismiss when navigating the map. Unnamed feature
  readouts are blank, with a fixed-width coordinate field.
- The Layers dropdown switches between local LROC satellite imagery and LOLA topography
  with 500 m elevation contours and an official elevation legend. Each basemap has 36 PNGs
  with identical NASA WMTS level-4 tile origins and scale. Switching layers preserves the
  camera, sites and overlay settings and does not call the analysis backend. Contours load
  lazily from a local JSON asset and use non-scaling strokes while navigating.
  `frontend/scripts/generate-contours.py` regenerates them from a real georeferenced LOLA DEM
  crop with temporary scientific Python dependencies; Python is not a frontend runtime dependency.
  The 36 PNGs per basemap retain NASA WMTS level-4 tile origins and scale. Source, tile dimensions,
  projection and catalogue provenance are in `frontend/public/maps/south-pole/README.md`.
  The basemap is observational imagery with fixed illumination, not a mission simulation.
- Feature names use a small Moon Trek IAU/USGS catalogue. Cursor hits approximate footprints
  with catalogue diameters; they are not exact crater boundaries or a complete gazetteer.
- Heatmaps use the **proposed**, unimplemented `POST /map/heatmaps` contract at the end of
  root `API.md`. Do not imply the backend already supports it. The toolbar can request
  sunlight, Earth contact, longest night, comms blackout, and slope. It sends all sidebar
  constraints plus UTC mission dates, projected extent, and raster dimensions.
- With no active criteria, no map request is made. Enabled overlays refetch on mission changes
  while Map is active; useRequest debounces/aborts and immediately hides stale results. Zoom,
  cursor motion and opacity never fetch. Returning to Map refetches enabled layers.
- Validate raster alignment, dimensions, layer units and cell counts before drawing. Null
  cells stay transparent. Mock responses must have a synthetic label. Multiple overlays
  blend in toolbar order; legends explain each ramp. The current backend returns an explicit
  unavailable state; do not invent scientific-looking heatmaps as fallback.
- Tests: `pnpm --dir frontend exec node --test tests/map.test.mjs`. Browser QA covered
  local imagery, coordinate readout width, custom sites in Profiles, missing endpoint state,
  intercepted fixture overlay rendering, multi-layer requests, mission updates, and mobile.
  The old-contract fixtures are repaired in the verification baseline; rerun the full suite
  rather than relying on historical counts.

## Sidebar site entry and calendars

- The Sites section's `+ Add` action opens a manual name/decimal-coordinate form, including
  when the section is collapsed. Section header actions are sibling controls, never buttons
  nested in the section-collapse button. Empty/whitespace names, missing/nonfinite numbers,
  latitude outside −90…90 and longitude outside −180…180 cannot be submitted. Decimal
  precision is preserved; do not round manually entered coordinates to the map click precision.
- Sidebar and Map both call App's `addSite`, so manual sites immediately appear in Profiles
  and on the map where inside the cap. Out-of-cap coordinates remain valid for Profiles.
  Entries use local UUIDs, custom coordinate payloads, and session-only storage, just like
  map-created sites. Cancel/Escape discards the form and returns focus to its Add button.
- `DateField` keeps `YYYY-MM-DD` mission values and the browser-native `type="date"`
  calendar inside each input. Do not add a second external calendar button or custom calendar.
  The shared `landingWindowError()` helper in time.ts requires real calendar dates and an
  end date strictly later than the start date. Equal dates are invalid for the backend.
- Mission dates now live in App's settings dialog, not Sidebar. Invalid date drafts show
  an associated alert and disable SET MISSION; the previous applied analysis remains valid.
  MainPanel and Map independently validate applied dates before requests. Profiles suppresses
  duplicate date notices; invalid applied props disable time seeking. Settings-draft changes
  do not invalidate the previous applied analysis until SET MISSION succeeds.
- `frontend/tests/dates.test.mjs` covers equality, reversed/missing/invalid dates, leap days,
  alert placement, native-only date controls, and disabled time controls. Browser checks
  verify no invalid API calls, both tabs, and recovery when a valid range is restored.

## Published reference overlays and cursor readout

- The Sunlight and Earth contact toolbar checkboxes display bundled, real NASA LOLA long-term
  averages from `frontend/public/maps/south-pole/reference/`. Their projection matches the
  map and their meaning is documented in the local README and official PDS labels. They are
  independent of mission dates and constraints and remain viewable with invalid mission dates.
  Do not pass their values to the mission scoring table or claim mission-dependent results.
- Both reference layers can be enabled simultaneously. They alpha-blend in sunlight then
  Earth-visibility order; the toolbar opacity applies to each image. Separate legends show
  0–100% ramps and a note explains combined colors and the any-disc visibility definition.
  Backend mission overlays render above them and retain independent request/error states.
- `map/referenceOverlays.ts` identifies these two criteria. Keep their selection state separate
  from backend criteria so toggling a reference layer never refetches analysis. The remaining
  three criteria still use the unimplemented `POST /map/heatmaps` contract.
- `frontend/scripts/generate-reference-overlays.py` creates the colorized PNGs from the real
  little-endian INT16 IMG files and PDS label scaling. It crops/resamples to the cap, masks
  outside-cap/no-data pixels, and records source checksums. Original large IMG files remain
  outside the repo. Scientific Python dependencies are only for offline regeneration.
- The fixed-width cursor box is positioned inside `.map-viewport` at bottom-right with a
  stable name line, blank for unnamed features. It ignores pointer events so map gestures
  pass through. The topographic elevation legend sits at top-right to avoid overlapping it.

## Heatmap presentation

- Any selected reference or mission heatmap hides all basemap imagery, terrain contours,
  and the elevation legend, including while loading, unavailable, or opacity is zero.
  A neutral surface remains with the coordinate grid, feature names, sites, and cursor box.
  The Layers dropdown remembers the user's choice; clearing the last heatmap restores it
  without resetting the camera. Topographic contour requests stop while the basemap is hidden.
- `map/HeatmapLegends.tsx` renders one legend per selected criterion in a top-left map card.
  Reference scales are 0–100%; mission scales use the response's units and bounds. Pending,
  invalid and unavailable mission data show a status instead of invented numeric limits.
  Distinguish reference averages, synthetic responses and actual mission outputs.
- Legends scroll within a bounded height on small maps, leaving the bottom-right cursor box
  unobscured. Keep individual labels and ranges visible when multiple maps are enabled.

## Map label sizing and introductory text

- Feature, waypoint, latitude-grid and compass labels use inverse-zoom font sizes and
  `strokeWidth={2 / zoom}` so outlines stay constant in screen pixels. Do not override these
  label stroke widths with a fixed CSS pixel value: that scales with the SVG viewBox and
  produces thick outlines when zoomed in. Browser checks verified 1× through 16×.
- Group pre-map notices/help in `.map-preamble`, with a 3px gap and 1.25 line height. Keep
  navigation hints and site color keys on a wrapping row, and keep reference-data caveats
  concise while preserving their long-term/any-disc meaning. Errors remain conspicuous.

## Route Planner

- MainPanel owns an explicit landing-site ID, separate from ordinary profile selection.
  Single clicks still compare; double-click/Shift+Enter selects the landing and reveals Route Planner
  without changing tabs or focus. The landing row has a green glow and explicit label; both
  maps highlight it in green. With no landing
  selected the tab is absent. Closing clears it, and deleting the landing site removes it.
- TouristRoutePanel is keyed by landing ID/coordinates, so a different landing resets all
  waypoints and requests. Switching tabs preserves the current plan. Site visibility toggles
  do not add sites to this map: only the landing and locally picked waypoints are rendered.
- Left-click picks up to 98 additional waypoints in visit order. Arrow keys pan and Enter
  picks the map center. Right/middle drag pans; wheel/pinch zooms and smooth scrolling pans.
  Draft edits immediately hide obsolete routes and abort pending requests. No automatic
  recommendations are fetched. Waypoints are session-only and separate from Sidebar sites.
- Calculate round trip calls `api.getRoute` with `[landing, ...waypoints, landing]` and
  `step_m: 100`. Custom stops send names/decimal coordinates, never local UUIDs. The existing
  FastAPI `/route` returns great-circle segments; retain its terrain/slope/shadow limitation.
  The Node mock does not implement `/route`: show its error instead of inventing a path.
- The map starts centered on the landing. Picking stops preserves the camera; calculation
  fits the returned route, and Fit can frame draft markers. Fit includes returned path points
  and compensates for `xMidYMid slice` cropping using the measured viewport aspect ratio. KML/CSV appear only for a current
  successful response. Route distances and path come from the backend, not draft geometry.

- Intermediate route-table rows support native drag-and-drop; there is no separate waypoint list.
  Coordinates appear beneath each stop name, with a Remove button for intermediate waypoints.
  Up/down buttons provide keyboard/touch reordering. Start/return entries stay fixed.
  Reordering updates draft state and invalidates the previous path just like adding/removing.
- Route table columns are Stop, Leg, Total and signed Elevation change (plus index/order
  controls). No Sun/Earth/Fit columns or mission scoring legend appear in the planner.
  `map/elevations.ts` bilinearly samples bundled real LOLA metre elevations (~792 m grid),
  subtracting the previous endpoint from the current one. No-data/out-of-coverage values
  show a dash. This is approximate net endpoint change, not accumulated ascent or route safety.
  `scripts/generate-elevations.py` regenerates the JSON from the same validated F32 crop as
  the contour tool. All data remain frontend assets; `/route` payload/response is unchanged.

- The frontend caps intermediate waypoints at 98, matching FastAPI's 100 request entries
  with start/return included. Mouse and keyboard additions share the same guard. The
  counter shows the limit; remove a stop to make room when it is reached.
