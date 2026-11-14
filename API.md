# Moon Flyers API: draft contract (v0)

**Status:** none of this is built yet. The first version will return correctly shaped **mock
data** from every endpoint, so you can integrate straight away. Real calculations will then replace
the mocks with no shape changes.

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

## 1. `GET /sites`: the sites sidebar, and the horizon chart for one site

*Without parameters* it returns the predefined catalogue:
```json
[{ "id": "malapert_massif", "name": "Malapert massif", "group": "Artemis III region",
   "latitude_deg": -86.0, "longitude_deg": 0.0, "notes": "..." }]
```

*With analysis parameters* it also returns `analysis` for the selected site, which feeds the
horizon chart.
- Choose the site with `site_id=malapert_massif`. For a custom site, send `name`, `latitude_deg`
  and `longitude_deg` instead.
- Also send `landing_utc`, any constraint fields, `timestep_seconds` (default 3600), and
  `sun_visibility` / `earth_visibility` (default true).

Example request:
```
GET /sites?site_id=malapert_massif&landing_utc=2027-08-07T06:00:00Z&days_on_surface=14
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
- `timeseries` covers the stay, from landing to landing + `days_on_surface`, at one point per
  `timestep_seconds`. Use it for the Sun and Earth paths and the "Sun visible 1.2°" markers.
- `horizon` is the horizon profile. **For now it's a flat 0° line.** The real terrain profile comes
  later in the same shape.

## 2. `POST /compare`: the comparison table and the timeline bars
```json
{
  "sites": [{ "id": "shackleton_rim" },
            { "name": "My site", "latitude_deg": -89.2, "longitude_deg": 45.0 }],
  "landing_utc": "2027-08-07T06:00:00Z",
  "window_start_utc": "2027-08-01T00:00:00Z",
  "window_end_utc": "2027-10-31T00:00:00Z",
  "constraints": { "...": "..." },
  "timestep_seconds": 3600
}
```
Response, one entry per site in the order you sent them:
```json
[{ "site": { "...": "..." }, "metrics": { "...": "..." }, "fit": { "...": "..." },
   "timeline": { "sun":   [{ "start_utc": "...", "end_utc": "..." }],
                 "earth": [{ "start_utc": "...", "end_utc": "..." }] } }]
```
- `metrics` and `fit` are for a mission landing at `landing_utc`. The ±6 h buttons simply resend
  the request with a new `landing_utc`.
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
