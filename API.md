# Moon Flyers API: draft contract (v0)

**Status:** the v0 contract is implemented by a standalone **synthetic mock API** in
`frontend/src/mock/`. It runs with Node and requires no Python or changes under `backend/`.
The separate FastAPI backend (`backend/src/main.py`) now also implements the v0 endpoints
with synthetic ephemerides and a flat horizon. Analysis mock data exercises the UI and is
not NASA ephemeris or terrain data. Map imagery is an independent observational basemap.

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
- `slope_deg` is `null` until terrain data is added. Show "—" for now.

---

## Data loading strategy

The frontend loads heavyweight analysis data **only** on:
1. App start (site catalogue via `GET /sites` with no parameters).
2. Any mission parameter change (window dates, constraints).
3. A site being toggled on or off.

On events 2–3, the frontend fires **one `POST /compare`** for all enabled sites and **one `GET /sites` per enabled site** in parallel to pre-load every horizon dataset.

The time slider **never** triggers an API call. It slices pre-loaded data client-side:
- `ComparisonTable` looks up the `window_metrics` entry whose `landing_utc` matches the slider.
- `HorizonChart` filters the pre-loaded `timeseries` to the one lunar day starting at the slider position — switching sites is instant.

## 1. `GET /sites`: the sites catalogue and per-site horizon data

*Without parameters* it returns the predefined catalogue:
```json
[{ "id": "malapert_massif", "name": "Malapert massif", "group": "Artemis III region",
   "latitude_deg": -86.0, "longitude_deg": 0.0, "notes": "..." }]
```

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
                 "earth": [{ "start_utc": "...", "end_utc": "..." }] },
    "metrics": { "...": "..." }, "fit": { "...": "..." } } }
```
- `timeseries` spans from `window_start_utc` to `window_end_utc + days_on_surface`, at one point
  per `timestep_seconds`. The client filters it to a one-lunar-day window starting at the slider
  position to show Sun and Earth paths without re-fetching.
- `horizon` is the horizon profile. **For now it's a flat 0° line.** The real terrain profile comes
  later in the same shape.

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
                 "earth": [{ "start_utc": "...", "end_utc": "..." }] } }]
```
- `window_metrics` pre-computes metrics and fit for every `candidate_step_hours` step in the
  window. The frontend looks up the entry matching the slider's current `landing_utc` to update
  the table instantly without a new request. The ±6 h buttons shift the slider position only.
- `timeline` gives the yellow and cyan bars, from `window_start_utc` to `window_end_utc` +
  `days_on_surface`.

## 3. `POST /landing-windows`: the best landing times table
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

## Not in v0
- Terrain-aware horizon (LOLA data).
- `slope_deg`.
- Error-response format. We'll use FastAPI's default `{"detail": ...}` for now.

Questions and change requests are welcome. This is a draft, and it's easier to change before we
build it.

## Proposed map heatmaps extension (frontend only; awaiting backend implementation)

The Map tab uses this **proposed** endpoint. Neither the current FastAPI backend nor the
standalone Node mock implements it. Enabling an overlay sends the request; 404/405/501
show an explicit unavailable message. The frontend generates no substitute heatmap values.
Backend contributors should agree this contract before implementing it.

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
