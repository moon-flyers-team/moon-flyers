# Moon Flyers API: draft contract (v0)

**Status:** the v0 contract is implemented by a standalone **synthetic mock API** in
`frontend/src/mock/`. It runs with Node and requires no Python or changes under `backend/`.
The separate FastAPI backend (`backend/src/main.py`) also implements the v0 endpoints.
Its Sun/Earth positions come live from NASA JPL Horizons by default, or from a
deterministic synthetic generator when started with
`MOON_FLYERS_EPHEMERIS=mock`. Its terrain horizon is **not** JPL data either: it is
synthetic mock hills when no DEM is mounted, or the real terrain computed from a
host-mounted, startup-validated LOLA DEM dataset (`LOLA_DEM_DIR`). The `X-Moon-Flyers-Data-Source`
header (`horizons`/`mock`) tells you which **Sun/Earth ephemeris** produced a response; it
does not identify the terrain source, so a `horizons` response is not proof of real
terrain. Uncovered sites or runtime DEM errors can fall back to a flat horizon with a
server warning; the response does not report that fallback. Ephemeris and terrain modes
are independent: mock ephemerides can be combined with a mounted DEM. Synthetic outputs
exercise the UI; they are not scientific predictions. Map imagery is an independent
observational basemap.

## Run the mock API

From the repository root, run these in separate terminals:

```sh
pnpm mock:api
pnpm --dir frontend dev
```

The root command delegates to `pnpm --dir frontend mock:api`, which starts
`frontend/src/mock/server.mjs` on `http://127.0.0.1:8000`. Open `http://localhost:5173`
for the frontend. The existing `/api` development proxy points at port 8000. If
`frontend/.env` sets `VITE_API_URL`, point it at this server and restart Vite.
Do not run the mock and real backends on the same port simultaneously. No Python environment,
Python dependencies, or backend files are needed to run or test the mock.

The mock returns `X-Moon-Flyers-Data-Source: mock`, exposed through CORS. The frontend reads
that header from the catalogue response to show a synthetic-data banner; the catalogue JSON
shape is unchanged. Data is deterministic, varies with site/date, and recomputes visibility
metrics, fit violations, and timelines from the same generated samples. Custom sites are
accepted without being stored. Slope remains `null`, and the horizon is flat.

There is a 0.4-second artificial analysis delay so loading states are visible. For slower
responses, use `MOCK_API_DELAY_SECONDS=3 pnpm mock:api`; set it to `0` to disable the delay.
Health checks have no artificial delay. Demo requests are limited to 100,000 samples per
series; landing-time searches allow up to 2,000 candidates and 1,000,000 sampled mission
points. Larger requests return 422 errors with a `detail` field. Invalid JSON returns 400.

All mock and frontend unit/contract tests run without servers:

```sh
pnpm --dir frontend test
```

With both servers running, verify the complete HTTP path and frontend rendering with:

```sh
pnpm --dir frontend test:mock
```

This sends real requests through the Vite proxy using the frontend API client, checks all
analysis endpoints, and renders the returned data in the table and chart. It does not automate
browser interaction. The mock has no FastAPI `/docs` page; use the endpoint examples below
and the browser Network panel to inspect requests.

## Conventions
- Angles are in degrees. Azimuth is measured clockwise from north (N = 0, E = 90, S = 180, W = 270).
- Latitude runs from −90 to 90. Longitude runs from −180 to 180, east-positive.
- Times are ISO 8601 UTC, for example `2027-08-07T06:00:00Z`.
- Field names follow the team requirements doc.
- A custom site is just a name plus coordinates, and nothing is stored on the server. Keep the
  user's custom sites on your side and send them with each request.
- Responses are slow: several seconds, sometimes 10–30 s for a comparison, because positions come
  live from NASA JPL Horizons. Please show a loading state.

## Constraints
This block maps to the Mission sidebar and goes with every analysis request. All fields are
optional, and the defaults match the mock UI:
```json
{
  "days_on_surface": 14,
  "horizon_clearance_deg": 0.3,
  "min_sun_visible_pct": 60,
  "max_darkness_hours": 96,
  "min_earth_visible_pct": 45,
  "max_earth_blackout_hours": 240,
  "max_slope_deg": 8
}
```
- A body counts as visible only when its whole disc is at least `horizon_clearance_deg` above the
  horizon.

## Shared response blocks
```json
"metrics": {
  "sun_visible_pct": 89, "longest_darkness_hours": 36,
  "earth_visible_pct": 100, "longest_earth_blackout_hours": 0,
  "slope_deg": null
},
"fit": { "status": "both_met", "violations": [] }
```
- `fit.status` is one of `both_met`, `power_short`, `comms_short` or `neither_met`.
- `violations` lists the metric names that broke a limit, so you can show the red ⚠ markers, for
  example `["sun_visible_pct", "longest_darkness_hours"]`.
- Power covers sunlight % and longest night. Comms covers Earth contact % and longest gap.
- `slope_deg` is always `null` in the current implementation, including with a DEM mounted.
  Show "—"; `max_slope_deg` is accepted but is not evaluated by `fit`.
- Earth visibility is geometric visibility, not a verified communications link. Sunlight
  fractions are not an energy budget. Meeting these limits does not establish mission safety.

---

## Data loading strategy

The frontend loads heavyweight analysis data **only** on:
1. App start (site catalogue via `GET /sites` with no parameters).
2. Any mission parameter change (window dates, constraints).
3. A site being toggled on or off.

Current UI: mission settings are edited in App's settings dialog and take effect on
**SET MISSION**, not on each draft keystroke. The nearby-POI radius is separate from
scoring constraints: applying it does not reload comparison or horizon analysis. Catalogue loads at startup; comparison and
site analysis run when applied settings or enabled sites change.

On events 2–3, the frontend fires **one `POST /compare`** for all enabled sites and **one `GET /sites` per enabled site** in parallel to pre-load every horizon dataset.

The time slider **never** triggers an API call. It slices pre-loaded data client-side:
- `ComparisonTable` matches `window_metrics` by numeric UTC instant, accepting equivalent
  `Z`/`.000Z`/offset forms. A missing candidate says “Not sampled”; it never substitutes
  the first candidate. The labeled Landing time (UTC) input provides a native keyboard
  alternative to the custom timeline, bounded to the window and 6-hour samples.
- `HorizonChart` filters the pre-loaded `timeseries` to the one lunar day starting at the slider position — switching sites is instant.

## 1. `GET /sites`: the sites catalogue and per-site horizon data

*Without parameters* it returns the predefined catalogue:
```json
[{ "id": "malapert_massif", "name": "Malapert massif", "group": "Artemis III region",
   "latitude_deg": -86.0, "longitude_deg": 0.0, "notes": "..." }]
```

The Python catalogue includes five original in-cap sites plus 14 published-location additions
(19 total), all within the route map's 80°S–90°S coverage, covering 49/61 bundled POIs
within the default 40 km proximity radius. Chandrayaan-3 and Chang'e-6 have been removed
because they are outside that cap; their former IDs now return 404. Custom coordinates
outside the cap remain valid for analysis, but are not displayed on the polar route map. Most additions
are explicitly labelled **exploration references, not vetted landing sites**; feature centres
are not selected candidate rim points. Existing site IDs/coordinates and the response shape
are unchanged. Coordinate sources and coverage limits: [`docs/poi-sources.md`](docs/poi-sources.md#default-landing-site--exploration-reference-coverage).
The current frontend enables all returned sites by default, so this increases initial
analysis work. Node mock/offline catalogues are unchanged.

*With analysis parameters* it also returns `analysis` for one site, which feeds the horizon
chart. The frontend calls this **once per enabled site in parallel** on mission params change
or site toggle — not on slider moves, and not only for the selected site.
- Choose the site with `site_id=malapert_massif`. For a custom site, send `name`, `latitude_deg`
  and `longitude_deg` instead.
- Also send `window_start_utc`, `window_end_utc`, any constraint fields, `timestep_seconds`
  (default 3600), and `sun_visibility` / `earth_visibility` (default true).

Example request:
```
GET /sites?site_id=malapert_massif&window_start_utc=2027-08-01T00:00:00Z&window_end_utc=2027-10-31T00:00:00Z&days_on_surface=14
```
Response:
```json
{ "id": "malapert_massif", "name": "Malapert massif", "...": "...",
  "analysis": {
    "timeseries": [{ "time_utc": "2027-08-07T06:00:00Z",
        "sun_azimuth_deg": 95.2, "sun_elevation_deg": 1.2, "sun_visible": true,
        "earth_azimuth_deg": 358.1, "earth_elevation_deg": 3.7, "earth_visible": true }],
    "horizon": { "horizon_azimuth_deg": [0, 1, 2, "..."], "horizon_elevation_deg": [0, 0, 0, "..."] },
    "windows": { "sun":   [{ "start_utc": "...", "end_utc": "..." }],
                 "earth": [{ "start_utc": "...", "end_utc": "..." }],
                 "eclipse": [{ "start_utc": "...", "end_utc": "..." }] },
    "metrics": { "...": "..." }, "fit": { "...": "..." } } }
```
- `timeseries` spans from `window_start_utc` to `window_end_utc + days_on_surface`, at one point
  per `timestep_seconds`. The client filters it to a one-lunar-day window starting at the slider
  position to show Sun and Earth paths without re-fetching.
- `horizon` is the horizon profile. The **standalone mock API** returns a flat 0° line.
  The Python backend returns synthetic mock hills (smooth 0–1.5°, fixed per site; the
  Sun and Earth are blocked by it) unless a verified LOLA DEM dataset is mounted at
  `LOLA_DEM_DIR`, in which case it returns the real terrain skyline for the site (which
  can be negative for a rim site). Uncovered sites or runtime DEM errors fall back to a
  flat horizon; terrain mode/fallback is not included in the wire response.

## 2. `POST /compare`: the comparison table and the timeline bars

**Called once per mission params change or site toggle, not on slider moves.**
```json
{
  "sites": [{ "id": "shackleton_rim" },
            { "name": "My site", "latitude_deg": -89.2, "longitude_deg": 45.0 }],
  "window_start_utc": "2027-08-01T00:00:00Z",
  "window_end_utc": "2027-10-31T00:00:00Z",
  "constraints": { "...": "..." },
  "candidate_step_hours": 6,
  "timestep_seconds": 3600
}
```
Response, one entry per site in the order you sent them:
```json
[{ "site": { "...": "..." },
   "window_metrics": [
     { "landing_utc": "2027-08-01T00:00:00Z", "metrics": { "...": "..." }, "fit": { "...": "..." } },
     { "landing_utc": "2027-08-01T06:00:00Z", "metrics": { "...": "..." }, "fit": { "...": "..." } }
   ],
   "timeline": { "sun":   [{ "start_utc": "...", "end_utc": "..." }],
                 "earth": [{ "start_utc": "...", "end_utc": "..." }],
                 "eclipse": [{ "start_utc": "...", "end_utc": "..." }] } }]
```
- `window_metrics` pre-computes metrics and fit for every `candidate_step_hours` step in the
  window. The frontend looks up the entry matching the selected UTC instant to update
  the table without a new request. Timeline seeking and the native Landing time (UTC)
  field update selection locally; the older ±6 h buttons are no longer mounted.
- The timeline landing marker is green only when the selected site's exact sampled
  candidate has `fit.status: both_met` and no violations, matching the comparison row.
  Simultaneous Sun/Earth visibility at landing alone is not a passing mission fit.
  Missing candidates stay neutral; the surface-stay shading indicates duration only.
- `timeline` gives the yellow and cyan bars, from `window_start_utc` to `window_end_utc` +
  `days_on_surface`.
- `eclipse` lists Earth eclipses (Earth's disc overlapping the Sun's, i.e. a lunar eclipse seen
  from the Moon) while Earth is visible from the site. Drawn in purple on top of the Earth
  (cyan) bar. Same interval rules as `sun`/`earth`; also present in `GET /sites` `windows`.

## 3. `POST /landing-windows`: ranked candidate times (API available; no current UI table)
```json
{ "site": { "id": "malapert_massif" },
  "window_start_utc": "2027-08-01T00:00:00Z", "window_end_utc": "2027-10-31T00:00:00Z",
  "constraints": { "...": "..." }, "candidate_step_hours": 6, "limit": 5 }
```
Response:
```json
[{ "rank": 1, "landing_utc": "2027-08-05T12:00:00Z", "metrics": { "...": "..." }, "fit": { "...": "..." } }]
```
- Results are sorted by fit first, then sunlight %, then Earth contact %.

## 4. `GET /health`
Returns `{"status": "ok"}`.

## 5. `POST /recommended-sites`: published POIs near a landing site (Python backend)

**Replaces the former mocked mission-ranking contract.** The path is retained, but the
request and response intentionally change. This is a catalogue proximity search, not
recommended landing coordinates or mission suitability. The standalone Node mock does
not implement this endpoint; it has no synthetic fallback.

Request using a predefined landing site:
```json
{ "site": { "id": "shackleton_rim" }, "radius_km": 40 }
```
Or explicit coordinates (name optional; no custom UUIDs):
```json
{ "site": { "name": "My landing", "latitude_deg": -89.2, "longitude_deg": 45 } }
```

- `site` is required: either an existing `GET /sites` catalogue ID, or both coordinates.
  Do not mix ID with name/coordinates. Coordinates may be anywhere on the Moon, but the
  **POI catalogue covers only footprints intersecting 80°S–90°S**. A far-away reference
  normally returns no matches; it does not broaden catalogue coverage.
- `radius_km` is optional, defaults to **40**, and must be a finite positive JSON number.
  Default rationale: user scenario of 10 km/h and eight hours total out-and-back driving.
  No claim of realistic terrain-aware reachability; stops, detours and reserve are excluded.
- Unknown fields are rejected, including old mission dates, constraints, candidate/sample
  steps and `limit`. No mission scoring or best-time search is performed.

Successful response shape (one illustrative match shown; actual results include all matches):
```json
{
  "method": "catalogue_proximity",
  "data_source": "published_catalogue",
  "catalogue_version": "south-pole-20261115",
  "site": {
    "id": "shackleton_rim", "name": "Shackleton rim", "group": "Artemis III region",
    "latitude_deg": -89.667, "longitude_deg": 129.783, "notes": "Rim of Shackleton crater."
  },
  "radius_km": 40,
  "recommendations": [{
    "poi": {
      "id": "iau-5450", "name": "Shackleton", "category": "natural_feature",
      "feature_type": "Crater, craters", "latitude_deg": -89.625776,
      "longitude_deg": 132.321845,
      "boundary": { "kind": "approximate_circle", "radius_km": 10.5 },
      "location_uncertainty_km": null,
      "notes": "Moon Trek nomenclature centre and diameter; circular extent is approximate, not a surveyed boundary. Label spelling follows Moon Trek.",
      "sources": [{
        "title": "NASA Moon Trek combined south-polar nomenclature",
        "url": "https://trek.nasa.gov/moon/trekarcgis/rest/services/CombinedNomenclatureS/MapServer/0",
        "record_id": "71"
      }, {
        "title": "Feature reference", "url": "https://planetarynames.wr.usgs.gov/Feature/5450",
        "record_id": null
      }]
    },
    "distance_km": 0
  }]
}
```

- `recommendations` contains **POIs**, not `Site` objects. POI IDs identify catalogue
  objects; do not send them as landing-site IDs to other endpoints. Explicit coordinates
  can be used for analysis, but a POI centre need not be safe or reachable for landing.
- Categories: `natural_feature`, `lander`, `rover`, `impact`. `feature_type` gives the source
  subtype. The initial snapshot has 55 natural features, two landers, four impacts, and no
  independently verified rover locations. No in-cap caves/collapse pits were found in the
  checked LROC Pits Atlas; do not relabel ordinary craters as caves.
- `boundary.kind: approximate_circle` means a spherical circular area derived from a
  published centre/diameter; **not an exact outline**. `point` means a published point,
  with `radius_km: 0`. Null location uncertainty is unquantified, not zero.
- `distance_km` is unrounded surface great-circle distance to that point/area on a
  1,737.4 km sphere. Inside an approximate footprint it is zero. The radius comparison is
  inclusive. Results include boundary-crossing features whose centres may be outside the
  cap; their full footprints are used, not clipped to the cap.
- All matches are returned, nearest first with POI ID breaking ties. There are **no rank,
  score, metrics, fit or landing-time fields**, no pagination and no silent truncation.
  An empty result is `recommendations: []` with HTTP 200.
- Successful responses use `X-Moon-Flyers-Data-Source: catalogue`, independently of the
  ephemeris/terrain configuration. For other existing endpoints the header retains its
  existing meaning. Data is bundled published-source information, not live ephemerides.
- 404: unknown landing-site ID. 422: invalid/ambiguous input, nonfinite coordinates/radius,
  or unknown fields. 400: malformed JSON. Missing/invalid bundled data is a server/deployment
  error, never a synthetic or empty substitute catalogue.
- Provenance, cave/pit research, source discrepancies, approximation limits and refresh
  instructions: [`docs/poi-sources.md`](docs/poi-sources.md). This catalogue is not exhaustive.

Current frontend: Mission Planner includes a positive **Search radius** in km (40 default).
After selecting a landing site, Route Planner's explicit **Find nearby POIs** action sends
that applied radius and landing reference to this endpoint. Custom landings send coordinates,
not local UUIDs. Results show published POI names and point/approximate-footprint distances;
they do not add waypoints or imply reachability. Changing radius hides previous results and
requires another explicit search. Errors remain visible; no synthetic fallback is used.

## Not in v0
- Terrain slope calculations (`slope_deg` remains null). Terrain-aware horizons are already
  supported by the Python backend with a mounted DEM; the standalone mock horizon is flat.
- Error-response format. We'll use FastAPI's default `{"detail": ...}` for now.

Questions and change requests are welcome. This is a draft, and it's easier to change before we
build it.

## Proposed map heatmaps extension (frontend only; awaiting backend implementation)

The Map tab uses this **proposed** endpoint. Neither the current FastAPI backend nor the
standalone Node mock implements it. Enabling a mission-dependent overlay sends the request; 404/405/501
show an explicit unavailable message. The frontend generates no substitute heatmap values.
Backend contributors should agree this contract before implementing it.

The current toolbar's Sunlight and Earth contact checkboxes instead display bundled NASA
LOLA **long-term reference averages**. They do not call this endpoint or change with mission
settings. Both can be overlaid together using transparency. Other heatmap checkboxes
(longest night, communications blackout and slope) use the proposed endpoint below. The
contract continues to describe future mission-dependent Sun/Earth maps too; the reference
products are not interchangeable with those outputs, particularly their any-disc visibility
criterion. Source metadata lives in `frontend/public/maps/south-pole/README.md`.

### `POST /map/heatmaps`

One batch for all enabled overlay criteria; no request while no overlays are enabled or the
Map tab is inactive. Sidebar mission dates, power/comms limits, slope limit, mission duration,
and horizon clearance are sent together. Relevant changes debounce by 350 ms, abort obsolete
requests, and hide stale overlays. Cursor movement, zoom and opacity adjustments are local.
Switching back to Map refetches enabled overlays. Sites and the Profiles time cursor do not
change map requests: the map represents mission-window analysis over the whole cap.

```json
{
  "projection": "lunar_south_polar_stereographic",
  "bounds_m": [-304005.6080198807, -304005.6080198807, 304005.6080198807, 304005.6080198807],
  "width": 128,
  "height": 128,
  "window_start_utc": "2027-08-01T00:00:00Z",
  "window_end_utc": "2027-10-31T00:00:00Z",
  "constraints": {
    "days_on_surface": 14,
    "horizon_clearance_deg": 0.3,
    "min_sun_visible_pct": 60,
    "max_darkness_hours": 96,
    "min_earth_visible_pct": 45,
    "max_earth_blackout_hours": 240,
    "max_slope_deg": 8
  },
  "criteria": ["sun_visible_pct", "earth_visible_pct"]
}
```

`bounds_m` is `[xmin, ymin, xmax, ymax]` in projected metres, **not geographic degrees**.
The exact cap radius is `2 × 1737400 × tan(5°)`; use that expression for exact bounds.
Projection is spherical lunar south-polar stereographic, radius 1,737,400 m, central meridian
0°, scale true at 90°S, zero false easting/northing. For longitude λ and latitude φ in radians:
`ρ = 2R × tan(π/4 + φ/2)`, `x = ρ sin λ`, `y = ρ cos λ`.
The map clips everything north of 80°S. The raster covers the bounding square; cells outside
the circular cap must be `null`.

Proposed aggregation: each cell is evaluated for candidate landings at six-hour intervals
across the mission window, with hourly samples for each `days_on_surface` stay. Choose the
candidate with fewest constraint violations, then highest sunlight %, then highest Earth
contact %, then earliest landing time. All returned criteria must describe that same candidate
at that cell. Slope describes the local surface and is independent of candidate time. This
makes power/comms constraints influence which landing is represented. This aggregation is a
proposal for backend review; the frontend does not calculate or infer it.

Response (abbreviated example with a 2×2 raster; a real response must match the requested
128×128 dimensions and extent):

```json
{
  "projection": "lunar_south_polar_stereographic",
  "bounds_m": [-304005.6080198807, -304005.6080198807, 304005.6080198807, 304005.6080198807],
  "width": 2,
  "height": 2,
  "data_source": "mock",
  "layers": [
    { "criterion": "sun_visible_pct", "unit": "%", "min": 0, "max": 100,
      "values": [null, 62.5, 84.2, null] },
    { "criterion": "earth_visible_pct", "unit": "%", "min": 0, "max": 100,
      "values": [null, 91.0, 78.5, null] }
  ]
}
```

- Criteria: `sun_visible_pct` / `%`, `earth_visible_pct` / `%`,
  `longest_darkness_hours` / `h`, `longest_earth_blackout_hours` / `h`, `slope_deg` / `deg`.
- Return exactly one layer for each requested criterion. No-data or unsupported terrain
  calculations use `null` cells (including an entirely null slope layer), never invented values.
- `values` is row-major, **north to south**, west to east, one value per pixel centre:
  `x = xmin + (column + 0.5) × (xmax − xmin)/width`,
  `y = ymax − (row + 0.5) × (ymax − ymin)/height`.
- `min` / `max` are finite display limits in the stated units; equality is allowed for constant
  fields. Null cells are transparent. Values outside the display limits saturate the color ramp.
- `data_source` is `mock` or `real`; mock overlays are explicitly labelled synthetic in the UI.
- The frontend rejects mismatched projection, extent, dimensions, units, incomplete layers,
  nonfinite values, and incorrect cell counts rather than misaligning a raster.
- The current client requests 128×128 cells. Backend implementations will likely need batching,
  caching, or asynchronous jobs before evaluating the entire cap with live ephemerides; these
  are not implemented by this frontend proposal.

## Route Planner: `POST /route` (existing FastAPI endpoint)

The frontend calls this explicitly after a landing site and additional waypoints
are chosen. Waypoints are visited in supplied order. For a round trip the landing site
is repeated at the end, giving two more request entries than the number of intermediate stops:

```json
{
  "waypoints": [
    { "id": "malapert_massif" },
    { "name": "Waypoint 1", "latitude_deg": -88.1, "longitude_deg": 12.5 },
    { "id": "malapert_massif" }
  ],
  "step_m": 100,
  "planner": "terrain",
  "rover": { "max_slope_deg": 15, "cell_size_m": 20, "padding_m": 1000 }
}
```

Use the same catalogue/custom `SiteReference` format as comparison. Custom UUIDs remain
local. The frontend allows up to 98 intermediate stops, reserving start and return entries.
FastAPI accepts 2–100 entries and a positive `step_m` (default 100 metres).

`planner` is `straight_line` (default) or `terrain`; `rover` is optional and only used by
`terrain`.

- **`straight_line`** — unchanged existing behavior. `method: "straight_line"`, great-circle
  segments densified every `step_m` metres, `status: "not_evaluated"`, `elevation_m: null`.
- **`terrain`** — bounded A* over the LOLA DEMs mounted at `LOLA_DEM_DIR`, one point per
  planned grid cell, `method: "astar_terrain"`, `terrain_source: "lola_dem"`, DEM
  `elevation_m` per point. Returns **503** when no dataset is mounted (it never substitutes
  flat or synthetic terrain) and 422 for geometry or limit problems. Terrain results are
  suggested candidate routes at the stated resolution, not validated driving instructions:
  no travel time, energy, illumination, communications or turning model.

Response fields: `method`, `status`, `reason`, `failing_leg`, `terrain_source`, `rover`,
resolved `waypoints`, `legs` (`from_index`, `to_index`, `distance_m`, `status`, `reason`,
terrain metrics, `expanded_nodes`, `cost`, `start_check`, `goal_check`), `total_distance_m`,
and a densified `path` (`latitude_deg`, `longitude_deg`, cumulative `distance_m`,
`elevation_m`, nullable `waypoint_index`).

`status` is `route_found`, `start_blocked`, `goal_blocked`, `no_route`,
`search_limit_reached`, or `not_evaluated` for `straight_line`. On a failed terrain leg,
`failing_leg` names it, that leg reports `distance_m: null`, and `path`/`total_distance_m`
keep only the planned prefix. `start_check`/`goal_check` list `blocked_reasons`
(`missing_elevation`, `unknown_slope`, `terrain_slope_exceeds_limit`, `excluded_by_mask`) and
`nearby_terrain_candidates`, which pass node terrain checks only — they are not a route and
never replace the endpoints. Neither planner optimizes waypoint order or scores mission
criteria. The frontend renders the returned path and invalidates it whenever draft waypoints
change. This endpoint is not implemented by the standalone Node mock.

`rover` fields (`max_slope_deg` 15, `max_uphill_grade_deg`/`max_downhill_grade_deg` null → the
same limit, `cell_size_m` 20, `padding_m` 1000, `climb_weight` 0, `slope_weight` 1,
`max_region_radius_m` 25000 capped at 50000) are illustrative defaults, not a vehicle
specification; limits describe the intended rover. A request may sample at most 1,000,000
terrain cells across all legs (422 beyond that), so very long multi-stop routes must be split
or run at a larger `cell_size_m`.

**Frontend work still needed to use `terrain`:** widen `RouteResponse.method` to
`'straight_line' | 'astar_terrain'`, add `status`/`reason`/`failing_leg`/`terrain_source`/
`rover` and the new leg/path fields, send `planner` (and optional `rover`), render a blocked
or failed leg from `legs[].status`/`reason` instead of a partial path, and surface the 503
"no dataset mounted" response. The existing elevation-change column can then read
`path[].elevation_m` instead of the bundled ~792 m grid. Terrain requests are slower than
straight lines (roughly 0.05 s for 1.5 km up to ~2 s for 9 km at 20 m cells on smooth
synthetic terrain), so keep the existing loading state and prefer 40–60 m cells for
multi-stop round trips.

Route-table elevation changes are currently calculated independently in the frontend from the
bundled LOLA elevation grid, because the `straight_line` response supplies no terrain
elevations. Each signed metre difference is destination elevation minus previous waypoint
elevation (including the return leg). Missing coverage shows a dash. These approximate
~792 m samples do not establish terrain-aware routing or cumulative ascent; a `terrain`
response supplies sampled `elevation_m` per path point instead.
