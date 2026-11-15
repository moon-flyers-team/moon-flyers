# Route Planner overhaul: findings and plan

Status: workstreams A (backend) and the first part of B (visibility, snapping) are in. Measurements below were taken on the production LOLA
dataset (`LOLA_DEM_DIR=/data/lola`, 8 polar products) with the current `main` planner, using a
read-only throwaway container so production was not touched. Re-run a probe before claiming a
number has not moved.

## Reverted 2026-11-15 (read this before re-adding B2-B8/C1)

Commits `9ec8f95` (route settings, path elevation column, elevation profile, stale-route state,
export marking, nginx timeout) and `39e0168` (draft-authoritative stale rendering) were reverted
after user testing: the panel got worse, not better.

- The stale-route work rendered the previous response wholesale. A `RouteResponse` carries its own
  `waypoints`, so after the first calculation a map click updated the draft while the map and table
  kept the old stop list: clicks looked ignored until Recalculate. The follow-up fix split geometry
  from stops, but the feature had already cost more than it returned.
- Auto-recalculation defaulting to on re-planned every leg after each edit (~1 s per leg at 60 m),
  which made the panel feel saturated rather than responsive.
- Path-sampled stop deltas and the profile were correct but changed numbers the user had learned to
  read, without a clear win in the reported problems.

Kept from the same work: hover preview and snapping (`4518c2f`), per-stop chips with the blocked
banner, per-leg limits, `stops[]`/`summary`, `POST /route/stops` and the 20° traversal default.

If any of it comes back: markers and table rows must always come from the draft, geometry may be
stale but must be visibly marked, auto-recalculation stays opt-in, and the elevation column only
switches to `path[].elevation_m` together with the profile so the two agree.

`frontend/nginx.conf` is back to the 60 s default read timeout, so a very long route (roughly 50+
legs) can still end in a 504. That timeout is worth re-adding on its own, without the rest.
## What the feature does today

`POST /route` with `planner: "terrain"` plans one A* search per leg over the mounted LOLA DEM at
`rover.cell_size_m` (frontend sends 60 m) inside a corridor of `rover.padding_m` (default 1 km)
on each side. Passability is a hard cut-off: a cell whose gradient magnitude exceeds
`max_slope_deg` (default 15°) cannot be entered. Cost is distance plus
`slope_weight * length * (steepness / 15°)^2`, so distance dominates. The frontend requests a
round trip `[landing, ...stops, landing]`, so the landing is an endpoint of the first and last
leg.

Every leg is attempted; a leg without a path becomes a straight `placeholder` polyline with its
own `status`/`reason`, and `failed_legs` lists it (`fix/route-all-legs`, PR #30).

## Findings

1. **The default landing site was the crater floor.** `shackleton_rim` sat at the IAU centre of
   Shackleton (−89.667, 129.783), a −2785 m permanently shadowed floor tile, and it is the UI's
   default landing. Every default round trip therefore failed on leg 0. The site now uses a
   DEM-derived rim crest at (−89.9297, −139.407): 10.58 km from the crater centre (crater radius
   10.45 km), 2.13 km from the south pole, +1438 m, terrain slope 0.4° at 60 m cells.
2. **11 of 61 POIs are unusable as route endpoints at 15°** (12 at 40, 100 and 150 m cells):
   Malapert A, Malapert E, de Gerlache, Laveran, Braude, Marvin, Drygalski, Ashbrook, Cabeus,
   Mons Mouton, plus Faustini or Malapert depending on cell size. They are published *feature
   centres*, i.e. crater floors and peaks. 5 remain blocked at 20°, 2 at 25°. The UI offers all
   of them as addable stops, so whether a route works depends on which POI the user picks.
3. **A hard 15° cut-off fragments the cap.** Shackleton rim → Connecting Ridge (19.5 km) returns
   `no_route` at 1, 2.5, 5 and 10 km padding — A* exhausts the region, so width is not the
   problem. `backend/docs/PROGRESS.md` records the same for ridge → de Gerlache rim (~19.6°
   needed at 60 m).
4. **One bad stop fails the whole request.** A leg beyond `max_region_radius_m` (50 km) raises
   422 for the entire request (`Destination exceeds max_region_radius_m`), reproducing with
   Shackleton rim → de Gerlache. Users can pick map points anywhere in the 80°S–90°S cap, which
   spans several hundred kilometres. The 1,000,000-cell budget behaves the same way.
5. **Runtime is per leg and unbounded in total.** 0.4–1.7 s per leg at 60 m with a 1 km corridor
   (`grid_shape` ≈ 35×360), 99 legs for a full route. `frontend/nginx.conf` sets no
   `proxy_read_timeout`, so nginx's 60 s default turns long routes into a 504 with an HTML body.
6. **"Plans like shit through craters" is two things.** (a) When a leg fails, the drawn dashed
   straight placeholder crosses whatever lies between the stops, craters included; at low zoom
   that reads as a planned crater crossing. (b) Where a crater wall is under 15° the planner
   legitimately descends into the floor and out again, because only slope is penalised and
   nothing expresses crater or keep-out avoidance.
7. **The elevation column does not describe the route.** `RouteView` computes stop deltas from
   the bundled ~792 m elevation grid, not from the response's sampled `path[].elevation_m`, so
   the table disagrees with the terrain the route actually traverses.
8. **The same stop is not consistently passable.** The search grid is oriented per leg, so one
   waypoint measured 14.4° as a goal and 16.0° as a start (recorded in `PROGRESS.md`): identical
   coordinates, different verdict depending on which leg evaluates them.
9. **Editing stops leaves a stale route on screen.** Only an aria-live announcement changes;
   there is no visible "stops changed, recalculate" state, and the map keeps the old path.
10. **Contract drift.** Root `API.md` still says a failed leg keeps only the planned prefix and
    omits `failed_legs`, `placeholder` and `legs[].padding_m`.

## Plan

Ordered by user impact. Each item is a reviewable increment with its own tests.

### A. Backend resilience (contract first) — done

- A1. Done: `region_too_large` for legs beyond the region radius, `search_limit_reached` for an
  exhausted cell budget; both are leg statuses with placeholders, never a 422.
- A2. Done: corridor ladder 5/10/20 km inside the region radius and cell budget, widest
  successful corridor reported in `legs[].padding_m` and `summary.padding_m`.
- A3. Done: each stop is evaluated once in a fixed local frame and gates its legs, so a stop
  cannot be blocked as a goal and passable as a start.
- A4. Done: `stops[]` and `summary` in the route response.
- A5. Done: `POST /route/stops` preflight (a few ms per stop, 503 without a dataset).
- A6. Done: routing default `max_slope_deg` raised 15° → 20°; the mission constraint stays 8° and
  the two are documented as unrelated.
- Measured after the change: ridge → Connecting Ridge was `no_route` at 15° and now plans 15.6 km
  in 1.26 s at 60 m (1.0 s budget per leg is the remaining risk for 99-leg routes). At 20° only
  5 of 61 POI centres remain unusable as stops; a blocked stop returns its slope and 3 nearby
  passable cells. Still open: 10/20 km corridors at 20 m cells exceed the 1M-cell budget, so the
  ladder stops early for high-resolution requests.

### B. Frontend UX

- B1. Done: the panel preflights the stops (debounced 350 ms) and shows a per-stop slope chip, a
  blocked banner and "Move to workable cell"; a map pick on impractical terrain is snapped
  automatically and the row records how far it moved. Published POI stops and the App-owned
  landing keep their coordinates.
- B1b. Done: hovering the route map probes the cursor position (120 ms debounce, one 30 m bucket
  per cached answer, aborted on move) and previews where a click would land: a dashed ring at the
  snapped position, a dotted connector from the cursor, and a cursor label stating the reason
  ("Steep 21° (limit 20°) · moves 120 m"). Enter/click uses the previewed position. Pointer moves
  are coalesced to one React update per animation frame so a long path does not jank.
- Open: the hover probe is one small `/route/stops` request per 30 m bucket rather than a local
  slope raster; a bundled slope grid would remove the latency and the server round trip if hover
  traffic ever matters. Keyboard picking (Enter at the map centre) has no preview yet.
- B2. Per-leg result in the table: distance, `no route` with the reason in text (not only a
  `title`), and the corridor width actually used.
- B3. Elevation profile of the returned path, with placeholder segments marked, replacing the
  hidden-accuracy grid deltas in the elevation column (B4).
- B4. Elevation change per stop from `path[].elevation_m`, labelled "terrain-sampled"; fall back
  to the bundled grid only for `straight_line`.
- B5. Visible stale state plus opt-in auto-recalculate (debounced), disabled above a leg count
  where the 60 s budget would be at risk.
- B6. Route settings in the panel: slope limit (15/20/25°), smoothness (`slope_weight`,
  `climb_weight`), and an advanced cell-size field, sent in `rover`.
- B7. Failure recovery actions: widen corridor, raise slope limit, snap stop, remove stop.
- B8. Legend and rendering distinguish planned terrain legs from straight placeholders; totals
  exclude placeholders (already true server-side).

### C. Delivery and docs

- C1. `proxy_read_timeout 300` for `/api/` in `frontend/nginx.conf` plus a client-side "still
  planning" state after 5 s.
- C2. Update root `API.md` (statuses, `stops`, `summary`, preflight endpoint, placeholder
  semantics), `AGENTS.md` and `backend/docs/PROGRESS.md`.
- C3. Keep `backend/tests/test_route.py` and `frontend/tests/*.test.mjs` in step with every
  contract change; verify with the terrain dataset in a throwaway container before deploying.

### Decisions needed

- Routing slope default: 15° connects almost nothing between sites; 20° leaves 5 blocked POIs,
  25° leaves 2. Appendix values are illustrative, not a rover spec.
- Whether the mission `max_slope_deg` constraint (default 8°) should drive routing; today they
  are unrelated numbers, and 8° blocks most stop pairs outright.
- Whether crater interiors/peaks deserve keep-out semantics or a stronger slope weight instead.

Out of scope unless re-agreed: waypoint-order optimisation, travel time, energy, illumination or
communications along the route.

## Done so far

- `shackleton_rim` moved from the crater centre to the rim crest (−89.9297, −139.407), with the
  derivation recorded in `catalogue.py`; the Node mock and both `API.md` examples updated; the
  POI-distance tests updated for the new geometry (backend 121 passed, 3 skipped; frontend 57
  passed; `tsc` + Vite build clean).
