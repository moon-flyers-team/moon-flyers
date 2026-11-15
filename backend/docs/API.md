# Moon Flyers API: draft contract (v0)

**Status:** the v0 contract is implemented by a standalone **synthetic mock API** in
`frontend/src/mock/`. It runs with Node and requires no Python or changes under `backend/`.
The real backend (`backend/src/main.py`) remains the original scaffold. Mock data exercises
the UI and is not NASA ephemeris or terrain data.

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
accepted without being stored. Slope is `null` (no DEM). The standalone Node mock returns a
flat horizon and synthetic ephemerides; its eclipse intervals are synthetic fixtures.

**The Python backend (`backend/`) uses real Sun/Earth positions from JPL Horizons by
default** and returns `X-Moon-Flyers-Data-Source: horizons` (`mock` if started with
`MOON_FLYERS_EPHEMERIS=mock`). That header identifies only the **Sun/Earth ephemeris**,
not the terrain: the Python terrain model uses synthetic hills unless a startup-verified
LOLA DEM dataset is mounted (`LOLA_DEM_DIR`, `deploy/compose.terrain.yaml`), in which case
the backend computes the site's terrain skyline. Uncovered sites or runtime DEM errors
fall back to a flat horizon with a server warning; the response does not report this.
Ephemeris and terrain modes are independent, so mock ephemerides can use a real DEM.
Each site costs two
Horizons calls (about 2 s), and Horizons allows only about 2 requests in flight per IP, so the
backend queues them. The usual burst (one 7-site `/compare` plus 7 `GET /sites`, 3 months) finishes in
about 35 s: `GET /sites` responses arrive within 3–13 s, `/compare` last. Keep loading states visible.
Limits: 90,000 samples per series (the Horizons maximum), otherwise 422. A
`timestep_seconds` that isn't whole minutes must divide the requested span exactly, otherwise
422. If Horizons fails or is unreachable, the response is **502**.

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
- `slope_deg` is the **real terrain slope at the site** in degrees from horizontal, fitted from the
  LOLA DEM (rounded to 0.1°). It is a site property, so it is the same for every landing time.
  It is `null` when the server has no DEM mounted (or the site is outside its coverage); show "—".
- If `slope_deg > max_slope_deg`, `violations` includes `"slope_deg"` (show the ⚠), but
  `fit.status` is unchanged: status only describes power and comms. A `null` slope is never a
  violation.
- Earth visibility does not establish a communications link, sunlight is not an energy
  budget, and matching visibility limits does not establish mission safety.

---

## Data loading strategy

The frontend loads heavyweight analysis data **only** on:
1. App start (site catalogue via `GET /sites` with no parameters).
2. Any mission parameter change (window dates, constraints).
3. A site being toggled on or off.

On events 2–3, the frontend fires **one `POST /compare`** for all enabled sites and **one `GET /sites` per enabled site** in parallel to pre-load every horizon dataset.

The time slider **never** triggers an API call. It slices pre-loaded data client-side:
- `ComparisonTable` matches the selected numeric UTC instant in `window_metrics`, accepting
  equivalent timestamp spellings. Missing samples show “Not sampled”, never the first row.
  The native Landing time (UTC) field supports 6-hour, in-window keyboard selection.
- `HorizonChart` filters the pre-loaded `timeseries` to the one lunar day starting at the slider position — switching sites is instant.

## 1. `GET /sites`: the sites catalogue and per-site horizon data

*Without parameters* it returns the predefined catalogue:
```json
[{ "id": "malapert_massif", "name": "Malapert massif", "group": "Artemis III region",
   "latitude_deg": -86.0, "longitude_deg": 0.0, "notes": "..." }]
```

The Python catalogue now has 21 sites: seven preserved entries and 14 published-location
additions, mostly explicitly unvetted exploration references. They cover 49/61 POIs within
40 km using the proximity endpoint's area/point semantics. See root
[API.md](../../API.md) and [source/coverage notes](../../docs/poi-sources.md#default-landing-site--exploration-reference-coverage).
No wire-format change; Node mock and frontend fallback catalogues are unchanged. The current
frontend enables all returned catalogue sites by default, increasing initial analysis work.

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
- `horizon` is the horizon profile. **By default it's mock terrain:** smooth hills of
  0–1.5°, fixed per site, and the Sun and Earth are blocked by it. With a startup-verified
  LOLA DEM dataset mounted (`LOLA_DEM_DIR`) the backend returns the real terrain skyline
  for the site instead, in the same shape (it can be negative for a rim site).
  Uncovered sites or runtime DEM errors fall back to flat; no per-site terrain provenance
  or fallback field is returned.

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
  the table without a new request. Timeline seeking and the native UTC field update
  selection locally; the older ±6 h buttons are no longer mounted.
- **Everything for the whole window comes in one response.** Slider and ◀ ▶ span arrows are
  visualization only: no request. A new request is only needed when the sites, the window or
  the constraints (e.g. `days_on_surface`) change. No ranking: the user compares and chooses.
- `timeline` gives the yellow and cyan bars, from `window_start_utc` to `window_end_utc` +
  `days_on_surface`.
- `eclipse` lists Earth eclipses (Earth's disc overlapping the Sun's, i.e. a lunar eclipse seen
  from the Moon) while Earth is visible from the site. Drawn in purple on top of the Earth
  (cyan) bar. Same interval rules as `sun`/`earth`; also present in `GET /sites` `windows`.

## 3. `POST /landing-windows`: removed (2026-11-15)
The app does not rank; the user chooses the site and landing time from the `/compare` data.

## 4. `GET /health`
Returns `{"status": "ok"}`.

## 5. `POST /route`: a detailed path through several sites (MOCK)
```json
{ "waypoints": [{ "id": "shackleton_rim" }, { "id": "connecting_ridge" },
                { "name": "Spot", "latitude_deg": -89.0, "longitude_deg": 10.0 }],
  "step_m": 100 }
```
Response:
```json
{ "method": "straight_line",
  "waypoints": [{ "id": "shackleton_rim", "name": "...", "...": "..." }],
  "legs": [{ "from_index": 0, "to_index": 1, "distance_m": 12345.6 }],
  "total_distance_m": 23456.7,
  "path": [{ "latitude_deg": -89.667, "longitude_deg": 129.783, "distance_m": 0.0, "waypoint_index": 0 },
           { "latitude_deg": -89.66, "longitude_deg": 130.1, "distance_m": 100.0, "waypoint_index": null }] }
```
- Waypoints (2–100, same shape as `site` elsewhere) are visited in the given order.
- `path` has a point at least every `step_m` metres (default 100); `waypoint_index` marks the
  requested waypoints. `distance_m` is cumulative from the first waypoint.
- **Mock:** `method: "straight_line"` means great-circle segments on a 1737.4 km sphere; terrain,
  slope and shadow are ignored. A real planner will keep this shape and change `method`.
- 404 for an unknown site id; 422 for fewer than 2 waypoints or more than 100,000 path points.

## 6. `POST /recommended-sites`: published nearby points of interest

**The root [API.md](../../API.md#5-post-recommended-sites-published-pois-near-a-landing-site-python-backend)
now owns this revised contract.** The previous mocked window/constraint ranking body and
response are deliberately removed; frontend UI/client changes are out of this backend task.

```json
{ "site": { "id": "shackleton_rim" }, "radius_km": 40 }
```

Alternatively, `site` accepts `latitude_deg` and `longitude_deg` with optional `name`.
Radius defaults to 40 km (10 km/h, eight hours total out-and-back driving, no stops/reserve).
All matches from the bundled 80°S–90°S POI footprint catalogue are returned as
`recommendations: [{poi, distance_km}]`, nearest first, no ranks or suitability scores.
Response metadata: `method: catalogue_proximity`, `data_source: published_catalogue`,
`catalogue_version`, resolved landing `site`, and effective `radius_km`.

Published natural-feature diameters define explicitly approximate circles; hardware/impacts
are published points. Distances are great-circle distances to the area/point (zero inside),
not rover routes. Boundary-crossing features are included even with centres outside the cap.
No synthetic data, ephemeris calls, scoring, dates, slope or visibility constraints are used.
Header: `X-Moon-Flyers-Data-Source: catalogue`, independent of the ephemeris mode.

Sources and cave/pit research: [docs/poi-sources.md](../../docs/poi-sources.md).
The initial 61-record snapshot has no in-cap cave/pit entries in the checked LROC atlas;
ordinary craters are not caves. Unknown IDs give 404; invalid/ambiguous/extra inputs give 422;
malformed JSON gives 400. Empty searches give HTTP 200 with an empty list.

## Not implemented

- `slope_deg`.
- Error-response format. We'll use FastAPI's default `{"detail": ...}` for now.

Questions and change requests are welcome. This is a draft, and it's easier to change before we
build it.
