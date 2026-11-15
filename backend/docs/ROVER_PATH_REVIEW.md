# Rover path planner — algorithm review

Prepared 2026-11-15. This document is the standalone algorithm handoff for review.
Implementation: `backend/app/Functions/rover_path.py`.
Tests: `backend/app/Functions/Tests/test_rover_path.py` and
`backend/tests/test_rover_dem.py`.

## Purpose and scope

Given a selected landing site and a landmark viewpoint, return a terrain-feasible
candidate rover route between their coordinates. Use a bounded elevation grid and
A* search. There is no worldwide optimization, automatic destination selection,
travel-time estimate, illumination scheduling, communications constraint, battery
model, or API/frontend integration in this change.

The route is feasible only under the supplied model and thresholds. Elevation maps
cannot establish actual driving safety or resolve hazards below their resolution.
The rover's footprint, turning radius, soil traction, wheel clearance, boulders,
heritage protection boundaries, and operational validation remain separate inputs
or later work. A result should be labelled a **suggested terrain route**, not a
certified driving route.

## Public functions

### `plan_rover_grid(...)`: search an existing metre grid

Inputs:

- `elevation_m`: 2D heights in metres, at least 3 × 3. NaN/inf means unknown terrain.
- `start_rc`, `goal_rc`: integer `(row, column)` inside the array.
- Required `cell_size_m` and `max_slope_deg`.
- Optional `max_uphill_grade_deg`, `max_downhill_grade_deg`, each defaulting to
  `max_slope_deg`. Limits range from 0° through 89°; equality is allowed with a
  1e-10 degree numerical comparison tolerance.
- `climb_weight=0`: nonnegative added cost per metre of ascent, expressed as
  equivalent metres. It is a preference, not a physical energy calculation.
- `slope_weight=1`: direction-independent preference for gentler terrain. The
  steepness for each move is the maximum of the two endpoint terrain slopes and
  the absolute movement grade. It penalizes downhill and cross-slope travel too.
  The reference scale is fixed at 15°, independently of the hard limits. At weight
  1, a 15° edge costs twice its distance and a 7.5° edge costs 1.25 times its
  distance, before any climbing charge. Set 0 to disable this preference.
- `blocked`: optional same-shape boolean mask, True = excluded.
- Resource limits: `max_cells=250000`, `max_expansions=250000`.

### `plan_rover_route(...)`: sample a DEM and search geographic endpoints

Inputs:

- `dem`: existing loader object exposing `sample(latitude_array, longitude_array)`.
- `start`, `goal`: `(latitude_deg, longitude_deg)`, longitude east-positive.
- Required `max_slope_deg`; the other rover settings above also apply.
- `cell_size_m=20`: requested sampling step, not a claim of source-map resolution.
- `padding_m=1000`: detour space beyond the direct start/goal corridor, rounded up
  to whole cells on all four sides. Must be positive.
- `exclusion_mask`: optional callable receiving the sampled latitude/longitude
  arrays and returning a boolean mask. The caller can rasterize keep-out zones here.
- `max_region_radius_m=25000`: maximum radius from start to any sampled point;
  cannot exceed the prototype's hard 50000 m cap.
- The same cell/expansion budgets as the grid entry point.

No real dataset is downloaded or created by the planner. Supply the actual `DEM`
object; there is no fallback to flat terrain or synthetic hills if data is missing.
The horizon skyline and per-site slope returned by `horizon()` are not route maps;
this planner needs elevations across the entire two-dimensional search area.

## Algorithm, step by step

### 1. Build a bounded local coordinate grid

Use the same reference-sphere radius as the existing terrain loader: 1737400 m.
The start point is the origin of a spherical azimuthal-equidistant projection.
The local x direction is the initial great-circle direction toward the destination;
y is its perpendicular tangent direction. A unit-vector construction avoids
longitude-wrap problems and works at the geographic poles.

A point `(x, y)` with `rho = hypot(x, y)` is mapped to the sphere by:

```text
unit_position = cos(rho/R) * origin_unit_vector
              + sin(rho/R) * (x * along + y * across) / rho
```

At rho = 0 use the origin itself. Recover latitude/longitude from that unit vector.

The direct start-to-goal distance is divided into `ceil(distance / cell_size)`
intervals. Both endpoints are included exactly; no endpoint is silently snapped
to an unrelated grid cell. Along-track intervals can be slightly shorter than the
requested step. Padding and cross-track intervals retain the requested step.

For identical physical endpoints the route may contain one point and zero distance.
The surrounding grid is still sampled to validate the endpoint's terrain.

Reject excessive extent or node counts before sampling the DEM. The region never
expands automatically. A failed bounded search does not establish that the landmark
is globally unreachable.

### 2. Sample and classify terrain

Call `dem.sample(latitudes, longitudes)` for the grid. Heights must have the same
shape as the coordinate arrays.

Estimate local terrain slope as:

```text
slope = degrees(atan(sqrt((dh/dx)^2 + (dh/dy)^2)))
```

Finite differences use actual local grid spacings; central differences inside and
one-sided differences at the region boundary. Gradient magnitude matters because
moving along a contour can still expose a rover to excessive cross-slope.

A node is blocked when its elevation or estimated slope is unknown, the estimated
slope exceeds the configured limit, or the exclusion mask blocks it. Missing
neighbour elevations may also make slope unknown and block neighbouring cells.
This is intentionally conservative around missing data.

Slope estimation uses the local projection's metric approximation. Geographic move
distances use spherical arcs instead. The extent cap keeps this a local planner,
but it does not establish an operational error bound for the slope model.

### 3. Construct valid moves

Consider the eight adjacent cells. A move must stay within the grid and end on a
passable node. Calculate its signed grade:

```text
grade = degrees(atan2(next_height - current_height, horizontal_distance))
```

Positive grade must not exceed the uphill limit; negative grade magnitude must not
exceed the downhill limit. For the geographic entry point horizontal distance is
the great-circle arc between the node unit vectors; for a regular test grid it is
the metre-based Euclidean step length.

For a diagonal move, both side-adjacent cells must be passable, and both two-edge
orthogonal approaches must meet the directional grade limits. This prevents
squeezing through an obstacle corner or bypassing a steep side approach. It is a
conservative grid rule, not continuous collision checking for a finite-size rover.

### 4. Minimize route cost using A*

```text
steepness = max(current_terrain_slope, next_terrain_slope, abs(movement_grade))
slope_penalty = slope_weight * horizontal_distance * (steepness / 15 degrees)**2
edge_cost = horizontal_distance + slope_penalty + climb_weight * max(0, height_change)
f(node) = best_known_cost_from_start(node) + heuristic(node)
```

For a regular grid the heuristic is straight-line metric distance to the goal.
For geographic routing it is the three-dimensional chord distance on the reference
sphere. A chord is no longer than an arc; added slope and climbing costs are nonnegative.
Both heuristics lower-bound remaining cost and are consistent with these edges.

Pseudocode:

```text
best[start] = 0
push (heuristic(start), 0, start)
while queue not empty:
    pop the smallest (f, cost, node)
    discard entry if a better arrival to node is already known
    if node is goal: reconstruct route through parent pointers; return route
    if expansion budget exhausted: return search_limit_reached
    count this expansion
    for each allowed neighbouring move:
        new_cost = cost + edge_cost
        if new_cost improves best[neighbour]:
            update best and parent
            push (new_cost + heuristic(neighbour), new_cost, neighbour)
return no_route
```

A found route is optimal for this sampled graph and cost function. It is not a
continuous-terrain or global optimum. Equal-priority heap entries have deterministic
cost/row/column tie ordering. Increasing climb weight can select a longer route
that climbs less. Increasing slope weight favours gentler terrain in either
travel direction, including level travel across a hillside. The slope term is
symmetric for reversing an edge; only the optional ascent term is directional.
These weights are prototype preferences, not calibrated estimates of energy or
vehicle risk. Hard limits still exclude excessive slopes even at zero weight.

### 5. Return the full path and diagnostics

Both functions return `status`, `reason`, `path_rc`, `expanded_nodes`, metrics, and
`endpoint_checks`. Each endpoint check includes its sampled elevation, estimated
terrain slope, slope limit, passable flag, and precise `blocked_reasons`:
`missing_elevation`, `unknown_slope`, `terrain_slope_exceeds_limit`, or
`excluded_by_mask`. Missing values are JSON null, not NaN. More than one cause
can apply. Both endpoints are checked even if the start is blocked.

For blocked endpoints, up to three `nearby_terrain_candidates` are reported from
this same bounded grid, sorted by offset distance. They pass node terrain checks
only: access, edge grades, connectivity, and a route have NOT been established.
They do not replace the requested endpoint. Geographic results attach coordinates
to the checks and candidate cells; grid-only results use row/column indices.
The geographic function also returns `path` (latitude, longitude and elevation per
node) and `search` (grid shape, projection, resolution request, bounds configuration,
rover limits, and requested coordinates).

| Status | Meaning |
| --- | --- |
| `route_found` | A route satisfies this sampled model and its limits |
| `start_blocked` | Start is excluded, unknown, or exceeds terrain slope limit |
| `goal_blocked` | Destination is excluded, unknown, or exceeds terrain slope limit |
| `no_route` | Search exhausted; no route in this bounded sampled graph |
| `search_limit_reached` | Budget exhausted; route existence is unknown |

Malformed input and requests exceeding grid/extent limits raise `ValueError`.
Dataset loading/sampling exceptions propagate; no substitute terrain is used.
Unsuccessful searches have an empty path and null route metrics.

Metrics for a successful route:

- `distance_m`: summed horizontal distances (reference-sphere arcs geographically).
- `terrain_distance_m`: summed `hypot(horizontal_step, elevation_change)`; an
  estimate of the elevation-following polyline length, not measured driving distance.
- `elevation_gain_m`, `elevation_loss_m`.
- `max_terrain_slope_deg`: maximum estimated local slope at path nodes.
- `max_uphill_grade_deg`, `max_downhill_grade_deg`: maximum directed move grades.
- `slope_penalty_cost`, `climb_penalty_cost`: summed preference charges in
  equivalent metres. They are not physical route distances.
- `cost`: `distance_m + slope_penalty_cost + climb_penalty_cost`.

Keep the full polyline. Uniformly retaining ten waypoints and joining them directly
could cut across excluded terrain. Future simplification must revalidate every
replacement segment against the same terrain constraints.

## Usage with the current DEM loader

Run Python with `backend` as the working directory/import root:

```python
import os
from src.lunar_horizon_dem import DEM
from app.Functions.rover_path import plan_rover_route

# Read existing host files. No network calls or mock fallback.
dem = DEM(data_dir=os.environ['LOLA_DEM_DIR'])
result = plan_rover_route(
    dem,
    start=(-89.9, 0.0),
    goal=(-89.9, 1.0),
    max_slope_deg=15,
    max_uphill_grade_deg=15,
    max_downhill_grade_deg=15,
    cell_size_m=20,
    padding_m=200,
    climb_weight=2,
    slope_weight=1,
)
print(result['status'])
if result['status'] == 'route_found':
    print(result['distance_m'], result['path'])
```

**All rover limits and coordinates above are illustrative**, not a recommendation
for a particular rover. It is valid for that example to return no route or a blocked
endpoint on the real DEM. The team must choose rover limits and landmark access
points. A landmark's centre is not necessarily a suitable arrival coordinate.

A smaller cell size does not reveal terrain absent from the source DEM: global
LOLA tiles are roughly 118 m resolution, with finer polar products where covered.
Choose sampling/resolution and keep-out buffers with the data and rover owners.
For a finite rover footprint, callers need an appropriately buffered exclusion mask;
this version does not automatically inflate obstacles or validate turning geometry.

## Validation and reviewer checklist

Run from the repository root with the project's Python environment:

```sh
python -m pytest backend/app/Functions/Tests/test_rover_path.py backend/tests/test_rover_dem.py -v
```

There are 29 focused offline tests, plus one opt-in real-raster test. They check known distances, terrain gradients versus
travel grades, independent uphill/downhill limits, blocked corners, missing data,
ascent and direction-independent slope costs, gentler detours, explicit failure
statuses, resource caps, exact endpoints,
small displacements, the pole, and the longitude seam. An independent Dijkstra
implementation checks A* costs on reproducible obstacle and weighted-terrain maps.
The existing LOLA loader is exercised through its small synthetic IMG/LBL fixture.
The offline checks do not establish real rover or real-raster route validation.
Diagnostic tests also distinguish excessive slope, missing elevation, incomplete
slope stencils and exclusions; check nearby candidates and unchanged endpoints;
and check JSON serialization with missing data.

The teammate reviewing this should check:

1. Does the node-slope plus directed-edge-grade model match the intended rover limits?
2. Are the chosen grid size, padding, and source DEM resolution appropriate for local visits?
3. Which exclusion areas and footprint buffers must be supplied for landmarks?
4. Are the prototype slope weight of 1 and illustrative ascent weight of 2 suitable preferences?
5. Are the route statuses and metrics sufficient for a future map endpoint?

No endpoint/schema changes are included. The functions currently live in the
calculation package `app/Functions`; backend deployment must package this code before
an endpoint can import it (the existing Dockerfile copies only `src`).

## Real LOLA check before API integration

The data owner should run the opt-in test in `backend/tests/test_rover_dem.py`.
This tests the existing planner-to-DEM connection; it needs no API or internet.
Run from the repository root in the Python environment with dependencies installed.

**Windows Command Prompt:**

```bat
set "LOLA_DEM_DIR=C:\path\to\lola_dem"
set "MOON_FLYERS_REAL_ROVER=1"
python -m pytest backend/tests/test_rover_dem.py -k on_real_lola_dataset -v -s
```

**macOS/Linux:**

```sh
LOLA_DEM_DIR=/path/to/lola_dem MOON_FLYERS_REAL_ROVER=1 \
python -m pytest backend/tests/test_rover_dem.py -k on_real_lola_dataset -v -s
```

Replace the data path. Expected: **1 passed, 1 deselected**. The test is skipped in
normal offline runs. The teammate reported a pass on real LOLA data using the
new default coordinates below; it has **not been rerun on real rasters in this
checkout**, which does not contain the dataset.

It uses 20 m spacing, 15° terrain/uphill/downhill limits, climbing weight 2 and
slope weight 1. Padding is 200 m for this short integration test. It prints a
JSON report location containing the full route, costs, metrics and status. It
independently re-reads path heights from the DEM and checks distances, movement
grades, elevation gain/loss, and cost accounting. Terrain slope is checked against
the returned model's maximum; this does not independently certify sub-grid terrain.
Missing files, blocked endpoints, and no-route results fail the enabled test;
there is no synthetic fallback.

### Diagnosing a blocked endpoint

The enabled test now prints `endpoint_checks` before asserting that a route was
found. The original example (-89.9, 0) to (-89.899, 0) returned `start_blocked`.
The subsequent diagnostics showed endpoint slopes of about 21.74° and 20.67°,
both exceeding the unchanged 15° limit. Those examples have been replaced by the
teammate's reported passing case. For any future blocked result, inspect the
actual elevation, slope, limit and reasons.
The full details are also in the printed JSON report file.

- `terrain_slope_exceeds_limit`: compare the reported slope with 15°; do not loosen
  the limit just to pass the test.
- `missing_elevation`: check coordinates and DEM coverage.
- `unknown_slope`: the endpoint may have a height, but its surrounding samples do
  not provide a finite slope estimate. Check coverage around the point too.
- `excluded_by_mask`: the supplied exclusion mask explicitly blocks the point.

If nearby candidate coordinates are present, the data owner can inspect them and
choose suitable test endpoints explicitly. If none are present, no nodes within
this region pass the terrain checks. Neither case proves global inaccessibility.

The defaults now reproduce the short case the teammate reported passing:
`(-89.90461690407035, 0.0)` to
`(-89.90461462373575, -0.3961843417649203)`. Limits and algorithm are unchanged.
This verifies a single sampled connection, not a full excursion or general rover
safety. Environment overrides are still supported for additional locations:

```bat
set "MOON_FLYERS_ROVER_START=[-89.90461690407035, 0.0]"
set "MOON_FLYERS_ROVER_GOAL=[-89.90461462373575, -0.3961843417649203]"
```

Replace these example values with the chosen coordinates (latitude, longitude).
The JSON arrays work as quoted environment values on macOS/Linux as well.
A blocked result can be correct; the successful-route integration test specifically
requires a nontrivial route so it cannot pass without checking any actual path.
The reported real-data pass supports handing off endpoint and deployment integration
to the backend team. Broader route and rover validation remain separate.

## Quick visual inspection

The optional plotting tool saves a PNG containing terrain elevation, estimated slope
with over-limit cells hatched, the complete cyan A* route, start/destination markers,
and a route elevation profile. Dashed grey is a direct reference, **not** a computed
route. Unknown elevation/slope cells are grey. Failed searches show the terrain and
reason but never draw a substitute route.

From the project root, in your Python environment:

```sh
python -m pip install -r backend/requirements-visualization.txt
python backend/tools/plot_rover_path.py --demo --output rover_demo.png
```

Demo mode uses a labelled artificial hill to demonstrate a detour; it is not real
lunar data. It works without LOLA files or a frontend server. For the real dataset,
Windows Command Prompt example:

```bat
python backend/tools/plot_rover_path.py --dem-dir "C:\path\to\lola_dem" --padding-m 60 --output rover_real.png
```

Replace the directory. With no coordinate arguments this uses the teammate's
reported passing test pair. It is a short smoke-test connection, not an excursion.
The 60 m padding provides a closer view; it still searches that entire smaller
region, so changing padding can change a route or feasibility. To inspect other
locations, supply both coordinate pairs:

```bat
python backend/tools/plot_rover_path.py --dem-dir "C:\path\to\lola_dem" --start -89.9 0 --goal -89.899 0 --output rover_other.png
```

These latter coordinates previously exceeded the 15° slope limit; expect a
blocked-start plot, not a successful route. Use your own coordinates for further
inspection. Options include `--cell-size-m`, `--padding-m`, `--max-slope-deg`,
`--climb-weight`, and `--slope-weight`. Defaults are 20 m, 300 m padding, 15°, 2 and
1 respectively. All three hard slope/grade checks use that same 15° setting unless
changed through the plotting option. This tool does not modify planner defaults.

Open the saved PNG normally or send it to a teammate; no DEM is needed to view it.
A same-name JSON report records source and planner output. Exit code 0 means a
route was drawn; 2 means a legitimate unsuccessful route result was plotted (or
an argparse usage error, which prints no success message). DEM errors propagate
without synthetic fallback. Keep generated PNG/JSON outputs out of Git unless
specifically choosing them as documented review artifacts.

Look for a sensible detour around steep areas, correct endpoints, and elevations
consistent with the map. The hatched map shows node terrain-slope exclusions,
not a complete directional-edge traversability map. Visual inspection supplements
tests; it does not establish continuous traversability or real driving safety.

## References

- A* lower-bound heuristic and graph-search background: Carnegie Mellon,
  [Robotic Motion Planning — A* and D* Search](https://www.cs.cmu.edu/~motionplanning/lecture/AppH-astar-dstar_howie.pdf).
- Projection family, spherical support and radius convention:
  [PROJ: Azimuthal Equidistant](https://proj.org/en/stable/operations/projections/aeqd.html).
- Dataset conventions and sampling implementation: this repository's
  `backend/src/lunar_horizon_dem.py`.
