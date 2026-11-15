# Rover path planner — algorithm review

Prepared 2026-11-15. This document is the standalone algorithm handoff for review.
Implementation: `backend/src/rover_path.py`.
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

Both functions return `status`, `reason`, `path_rc`, `expanded_nodes` and metrics.
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
from src.rover_path import plan_rover_route

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
python -m pytest backend/app/Functions/Tests/test_rover_path.py backend/tests/test_rover_dem.py backend/tests/test_route.py -v
```

There are 24 focused tests. They check known distances, terrain gradients versus
travel grades, independent uphill/downhill limits, blocked corners, missing data,
ascent and direction-independent slope costs, gentler detours, explicit failure
statuses, resource caps, exact endpoints,
small displacements, the pole, and the longitude seam. An independent Dijkstra
implementation checks A* costs on reproducible obstacle and weighted-terrain maps.
The existing LOLA loader is exercised through its small synthetic IMG/LBL fixture.
These are offline tests, not real rover or real-raster route validation.

The teammate reviewing this should check:

1. Does the node-slope plus directed-edge-grade model match the intended rover limits?
2. Are the chosen grid size, padding, and source DEM resolution appropriate for local visits?
3. Which exclusion areas and footprint buffers must be supplied for landmarks?
4. Are the prototype slope weight of 1 and illustrative ascent weight of 2 suitable preferences?
5. Are the route statuses and metrics sufficient for a future map endpoint?

## API integration (done)

The planner now lives in `backend/src/rover_path.py`, so the existing Dockerfile (which
copies `src`) deploys it and the earlier packaging blocker is gone. `POST /route` exposes
it through `src/services/route.py`:

- `planner: "straight_line"` (default) keeps the previous mock contract exactly.
- `planner: "terrain"` plans every leg with `plan_rover_route` over the DEMs mounted at
  `LOLA_DEM_DIR` (opened once per directory and shared with the horizon service), returns
  `elevation_m` per path point plus per-leg statuses/metrics/endpoint checks, and returns
  **503** when no dataset is mounted rather than substituting terrain.
- Rover limits come from the request's `rover` block, are echoed in the response, and are
  422 when the planner rejects them; per-request work is bounded by a 1,000,000-cell cap
  across all legs plus the existing planner cell/expansion budgets.

Not implemented (deliberate): exclusion masks/keep-out buffers, footprint inflation,
waypoint-order optimization, travel time/energy/illumination/communications constraints,
and any automatic fallback when terrain blocks a leg. `tests/test_route.py` covers the
contract on the synthetic LOLA fixture; the opt-in real-raster test below remains the
scientific check.

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
normal offline runs and has **not been run on real rasters in this checkout**.

It uses 20 m spacing, 15° terrain/uphill/downhill limits, climbing weight 2 and
slope weight 1. Padding is 200 m for this short integration test. It prints a
JSON report location containing the full route, costs, metrics and status. It
independently re-reads path heights from the DEM and checks distances, movement
grades, elevation gain/loss, and cost accounting. Terrain slope is checked against
the returned model's maximum; this does not independently certify sub-grid terrain.
Missing files, blocked endpoints, and no-route results fail the enabled test;
there is no synthetic fallback.

The default endpoints `(-89.9, 0)` to `(-89.899, 0)` are a short example, not a known
traversable route. If those points are blocked, inspect the report and choose two
known traversable nearby points rather than loosening the rover limits just to pass:

```bat
set "MOON_FLYERS_ROVER_START=[-89.9, 0]"
set "MOON_FLYERS_ROVER_GOAL=[-89.899, 0]"
```

Replace these example values with the chosen coordinates (latitude, longitude).
The JSON arrays work as quoted environment values on macOS/Linux as well.
A blocked result can be correct; the successful-route integration test specifically
requires a nontrivial route so it cannot pass without checking any actual path.
After a real-data pass, the backend team can wire the endpoint and deployment.

## References

- A* lower-bound heuristic and graph-search background: Carnegie Mellon,
  [Robotic Motion Planning — A* and D* Search](https://www.cs.cmu.edu/~motionplanning/lecture/AppH-astar-dstar_howie.pdf).
- Projection family, spherical support and radius convention:
  [PROJ: Azimuthal Equidistant](https://proj.org/en/stable/operations/projections/aeqd.html).
- Dataset conventions and sampling implementation: this repository's
  `backend/src/lunar_horizon_dem.py`.
