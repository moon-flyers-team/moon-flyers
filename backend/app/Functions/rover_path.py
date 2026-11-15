"""Bounded A* rover routing over elevation samples; no network or API dependencies.

These are terrain-feasible candidate routes at the supplied resolution, not
validated driving instructions. Limits must describe the intended rover.
"""
import heapq
import math
from numbers import Integral, Real

import numpy as np

SLOPE_REFERENCE_DEG = 15.0  # Preference scale, not a vehicle capability.
MOON_RADIUS_M = 1_737_400.0  # Same reference sphere as lunar_horizon_dem.py.
_NEIGHBOURS = [(r, c) for r in (-1, 0, 1) for c in (-1, 0, 1) if (r, c) != (0, 0)]


def _number(value, name, minimum=0, maximum=math.inf, *, positive=False):
    """Reject booleans and nonfinite values before allocating grids or searching."""
    if (isinstance(value, bool) or not isinstance(value, Real) or not math.isfinite(value)
            or value < minimum or value > maximum or (positive and value == 0)):
        raise ValueError(f'{name} must be finite and in the allowed range')
    return float(value)


def _limit(value, name):
    if isinstance(value, bool) or not isinstance(value, Integral) or value < 1:
        raise ValueError(f'{name} must be a positive integer')
    return int(value)


def _index(value, shape, name):
    if (not isinstance(value, (tuple, list)) or len(value) != 2
            or any(isinstance(v, bool) or not isinstance(v, Integral) for v in value)):
        raise ValueError(f'{name} must be an integer (row, column)')
    result = tuple(int(v) for v in value)
    if not all(0 <= i < size for i, size in zip(result, shape)):
        raise ValueError(f'{name} is outside the grid')
    return result


def _settings(max_slope_deg, uphill, downhill, weight, max_expansions, slope_weight):
    slope = _number(max_slope_deg, 'max_slope_deg', maximum=89)
    up = slope if uphill is None else _number(uphill, 'max_uphill_grade_deg', maximum=89)
    down = slope if downhill is None else _number(downhill, 'max_downhill_grade_deg', maximum=89)
    return (slope, up, down, _number(weight, 'climb_weight'),
            _limit(max_expansions, 'max_expansions'), _number(slope_weight, 'slope_weight'))


def _search(height, x, y, start, goal, settings, blocked, unit_vectors=None):
    """Shared graph search. Optional sphere vectors give physical lunar distances."""
    slope_limit, uphill, downhill, weight, expansion_limit, slope_weight = settings
    if blocked is None:
        blocked = np.zeros(height.shape, dtype=bool)
    blocked = np.asarray(blocked)
    if blocked.shape != height.shape or blocked.dtype != bool:
        raise ValueError('blocked mask must be boolean and match the elevation grid')
    height = np.where(np.isfinite(height), height, np.nan)
    # Cross-slope matters too: do not accept a flat contour across a steep hillside.
    # Central differences inside; one-sided differences at the region boundary.
    # Missing neighbours propagate to unknown slope and therefore blocked cells.
    with np.errstate(invalid='ignore', divide='ignore'):
        dy, dx = np.gradient(height, y, x)
        slopes = np.degrees(np.arctan(np.hypot(dx, dy)))
    passable = np.isfinite(height) & np.isfinite(slopes) & (slopes <= slope_limit + 1e-10) & ~blocked

    def endpoint_check(point):
        """Explain terrain checks without guessing which cause blocked a cell."""
        r, c = point
        reasons = []
        if not np.isfinite(height[point]):
            reasons.append('missing_elevation')
        if not np.isfinite(slopes[point]):
            reasons.append('unknown_slope')
        elif slopes[point] > slope_limit + 1e-10:
            reasons.append('terrain_slope_exceeds_limit')
        if blocked[point]:
            reasons.append('excluded_by_mask')
        check = {
            'grid_cell': [r, c],
            'elevation_m': float(height[point]) if np.isfinite(height[point]) else None,
            'terrain_slope_deg': float(slopes[point]) if np.isfinite(slopes[point]) else None,
            'max_slope_deg': slope_limit, 'passable': bool(passable[point]),
            'blocked_reasons': reasons, 'nearby_terrain_candidates': [],
        }
        if reasons:
            # These suggestions pass node terrain checks only. They are NOT a
            # route or proof of connected access, and never replace the endpoints.
            cells = np.argwhere(passable)
            if len(cells):
                if unit_vectors is None:
                    distances = np.hypot(x[cells[:, 1]]-x[c], y[cells[:, 0]]-y[r])
                else:
                    chords = np.linalg.norm(unit_vectors[cells[:, 0], cells[:, 1]]-unit_vectors[point], axis=1)
                    distances = 2*MOON_RADIUS_M*np.arcsin(np.clip(chords/2, 0, 1))
                for i in np.argsort(distances, kind='stable')[:3]:
                    cell = tuple(int(v) for v in cells[i])
                    check['nearby_terrain_candidates'].append({
                        'grid_cell': list(cell), 'offset_m': float(distances[i]),
                        'elevation_m': float(height[cell]), 'terrain_slope_deg': float(slopes[cell]),
                    })
        return check

    checks = {'start': endpoint_check(start), 'goal': endpoint_check(goal)}
    result = {
        'endpoint_checks': checks,
        'search_boundary_reached': {'row_min': False, 'row_max': False, 'col_min': False, 'col_max': False},
        'status': None, 'reason': None, 'path_rc': [], 'expanded_nodes': 0,
        'distance_m': None, 'terrain_distance_m': None, 'elevation_gain_m': None,
        'elevation_loss_m': None, 'max_terrain_slope_deg': None,
        'max_uphill_grade_deg': None, 'max_downhill_grade_deg': None, 'cost': None,
        'slope_penalty_cost': None, 'climb_penalty_cost': None,
    }
    for name in ('start', 'goal'):
        check = checks[name]
        if not check['passable']:
            messages = {
                'missing_elevation': 'no finite elevation at the endpoint',
                'unknown_slope': 'terrain slope cannot be estimated from the sampled elevations',
                'terrain_slope_exceeds_limit':
                    f"terrain slope {check['terrain_slope_deg']:.3f}° exceeds {slope_limit:g}°"
                    if check['terrain_slope_deg'] is not None else '',
                'excluded_by_mask': 'endpoint is inside the supplied exclusion mask',
            }
            result.update(status=name+'_blocked',
                          reason=name.capitalize()+' blocked: '+
                          '; '.join(messages[cause] for cause in check['blocked_reasons']))
            return result

    def distance(a, b):
        if unit_vectors is None:
            return math.hypot(x[b[1]]-x[a[1]], y[b[0]]-y[a[0]])
        chord = float(np.linalg.norm(unit_vectors[b]-unit_vectors[a]))
        return 2*MOON_RADIUS_M*math.asin(min(1, chord/2))

    def heuristic(point):
        if unit_vectors is None:
            return distance(point, goal)
        # Chord <= great-circle distance <= any route's distance component.
        return MOON_RADIUS_M*float(np.linalg.norm(unit_vectors[point]-unit_vectors[goal]))

    def edge(a, b):
        if not passable[b]:
            return None
        length = distance(a, b)
        dz = float(height[b]-height[a])
        grade = math.degrees(math.atan2(dz, length))
        if grade > uphill + 1e-10 or -grade > downhill + 1e-10:
            return None
        return length, dz, grade

    def slope_penalty(a, b, length, grade):
        # Local gradient magnitude captures cross-slope even on a level contour.
        # Absolute movement grade also catches steep steps smoothed by gradients.
        # The max makes the penalty conservative and independent of direction.
        steepness = max(float(slopes[a]), float(slopes[b]), abs(grade))
        return slope_weight*length*(steepness/SLOPE_REFERENCE_DEG)**2

    costs = np.full(height.shape, np.inf)
    costs[start] = 0
    parents = {}
    queue = [(heuristic(start), 0.0, start)]
    while queue:
        _, cost, current = heapq.heappop(queue)
        if cost > costs[current]:
            continue  # A better arrival superseded this queued entry.
        if current == goal:
            path = [goal]
            while path[-1] != start:
                path.append(parents[path[-1]])
            path.reverse()
            lengths, changes, grades, slope_costs = [], [], [], []
            for a, b in zip(path, path[1:]):
                length, dz, grade = edge(a, b)
                lengths.append(length)
                changes.append(dz)
                grades.append(grade)
                slope_costs.append(slope_penalty(a, b, length, grade))
            result.update(
                status='route_found', path_rc=[list(p) for p in path], cost=float(cost),
                distance_m=sum(lengths),
                terrain_distance_m=sum(math.hypot(d, dz) for d, dz in zip(lengths, changes)),
                elevation_gain_m=sum(max(0, dz) for dz in changes),
                elevation_loss_m=sum(max(0, -dz) for dz in changes),
                max_terrain_slope_deg=max(float(slopes[p]) for p in path),
                max_uphill_grade_deg=max([0.0]+grades),
                max_downhill_grade_deg=max([0.0]+[-g for g in grades]),
                slope_penalty_cost=sum(slope_costs),
                climb_penalty_cost=weight*sum(max(0, dz) for dz in changes),
            )
            return result
        if result['expanded_nodes'] >= expansion_limit:
            result.update(status='search_limit_reached', reason='Expansion budget reached; route existence is unknown')
            return result
        result['expanded_nodes'] += 1
        r, c = current
        # This records only where the search actually expanded. Touching an edge
        # suggests a larger region may help; it does not establish a route beyond it.
        for name, touched in [('row_min', r == 0), ('row_max', r == height.shape[0]-1),
                              ('col_min', c == 0), ('col_max', c == height.shape[1]-1)]:
            if touched:
                result['search_boundary_reached'][name] = True
        for dr, dc in _NEIGHBOURS:
            target = (r+dr, c+dc)
            if not (0 <= target[0] < height.shape[0] and 0 <= target[1] < height.shape[1]):
                continue
            movement = edge(current, target)
            if movement is None:
                continue
            if dr and dc:
                # Both flanking cells AND their orthogonal approaches must be usable.
                # This prevents squeezing diagonally through blocked or steep corners.
                flank_a, flank_b = (r+dr, c), (r, c+dc)
                if any(edge(a, b) is None for a, b in [
                    (current, flank_a), (flank_a, target), (current, flank_b), (flank_b, target)
                ]):
                    continue
            length, dz, grade = movement
            new_cost = cost + length + weight*max(0, dz) + slope_penalty(current, target, length, grade)
            if new_cost < costs[target]:
                costs[target] = new_cost
                parents[target] = current
                heapq.heappush(queue, (new_cost+heuristic(target), new_cost, target))
    result.update(status='no_route', reason='No feasible route exists in the sampled search region under these limits')
    return result


def plan_rover_grid(elevation_m, start_rc, goal_rc, *, cell_size_m, max_slope_deg,
                    max_uphill_grade_deg=None, max_downhill_grade_deg=None,
                    climb_weight=0.0, slope_weight=1.0, blocked=None, max_cells=250_000, max_expansions=250_000):
    """Plan over a regular metre-based grid; returns a JSON-compatible result.

    NaN/inf heights mean missing terrain. blocked is an optional boolean mask.
    max_slope_deg limits terrain gradient magnitude; uphill/downhill grade limits
    apply to individual directed moves and default to max_slope_deg. Climb weight
    adds equivalent distance cost per metre gained; it is not an energy model.
    slope_weight penalizes terrain and movement steepness in either direction:
    length * slope_weight * (steepness / 15 degrees)**2. Default 1 makes a 15-degree
    edge cost twice its distance before any climb charge; 0 disables this preference.
    Hard slope and grade limits still apply regardless of the weights.
    """
    step = _number(cell_size_m, 'cell_size_m', positive=True)
    settings = _settings(
        max_slope_deg, max_uphill_grade_deg, max_downhill_grade_deg, climb_weight, max_expansions, slope_weight)
    height = np.asarray(elevation_m, dtype=float)
    if height.ndim != 2 or min(height.shape) < 3:
        raise ValueError('elevation_m must be a 2D grid with at least 3 rows and columns')
    if height.size > _limit(max_cells, 'max_cells'):
        raise ValueError('Grid exceeds max_cells; reduce the region or increase cell_size_m')
    start = _index(start_rc, height.shape, 'start_rc')
    goal = _index(goal_rc, height.shape, 'goal_rc')
    x, y = np.arange(height.shape[1])*step, np.arange(height.shape[0])*step
    return _search(height, x, y, start, goal, settings, blocked)


def _coordinate(point, name):
    if not isinstance(point, (tuple, list)) or len(point) != 2:
        raise ValueError(f'{name} must be (latitude_deg, longitude_deg)')
    lat = _number(point[0], name+' latitude', minimum=-90, maximum=90)
    lon = _number(point[1], name+' longitude', minimum=-180, maximum=180)
    return lat, lon


def _unit(lat, lon):
    lat, lon = math.radians(lat), math.radians(lon)
    return np.array([math.cos(lat)*math.cos(lon), math.cos(lat)*math.sin(lon), math.sin(lat)])


def plan_rover_route(dem, start, goal, *, max_slope_deg, cell_size_m=20.0, padding_m=1000.0,
                     max_uphill_grade_deg=None, max_downhill_grade_deg=None, climb_weight=0.0, slope_weight=1.0,
                     exclusion_mask=None, max_region_radius_m=25_000.0,
                     max_cells=250_000, max_expansions=250_000):
    """Sample DEM.sample(lat_array, lon_array) and route between exact coordinates.

    start/goal: (latitude_deg, east-positive longitude_deg), in degrees. The DEM
    must return heights in metres over the same lunar sphere used by the loader.
    A local spherical azimuthal-equidistant grid handles poles and longitude wrap.
    Its x-axis points toward goal; endpoints are grid nodes, never silently snapped.

    exclusion_mask, if supplied, is callable(lat_array, lon_array) -> bool grid
    (True means blocked). It can encode catalogue keep-out zones or other hazards.
    slope_weight applies the same direction-independent preference as plan_rover_grid.
    padding_m permits detours on every side, rounded up to whole cells. The region
    is not automatically expanded on failure. Limits are checked before DEM access.
    Missing data is blocked; there is no mock/flat terrain fallback.
    """
    start, goal = _coordinate(start, 'start'), _coordinate(goal, 'goal')
    step = _number(cell_size_m, 'cell_size_m', positive=True)
    padding = _number(padding_m, 'padding_m', positive=True)
    radius_limit = _number(max_region_radius_m, 'max_region_radius_m', maximum=50_000, positive=True)
    cell_limit = _limit(max_cells, 'max_cells')
    settings = _settings(
        max_slope_deg, max_uphill_grade_deg, max_downhill_grade_deg, climb_weight, max_expansions, slope_weight)
    origin, destination = _unit(*start), _unit(*goal)
    # atan2 retains precision for nearby points, including near a geographic pole.
    angle = math.atan2(float(np.linalg.norm(np.cross(origin, destination))), float(np.dot(origin, destination)))
    distance = MOON_RADIUS_M*angle
    if distance > radius_limit:
        raise ValueError('Destination exceeds max_region_radius_m; only local routes are supported')
    tangent = destination - np.dot(origin, destination)*origin
    tangent_norm = float(np.linalg.norm(tangent))
    # At the same physical point, use local east for a well-defined grid orientation.
    along = tangent/tangent_norm if tangent_norm > 1e-14 else np.array([
        -math.sin(math.radians(start[1])), math.cos(math.radians(start[1])), 0.0])
    across = np.cross(origin, along)
    same_point = distance < 1e-8
    # Check ratios before ceil/array allocation, even for extremely tiny spacings.
    if padding/step > cell_limit or distance/step > cell_limit:
        raise ValueError('Search region exceeds max_cells; increase cell_size_m')
    segments = 0 if same_point else max(1, math.ceil(distance/step))
    pad = max(1, math.ceil(padding/step))
    rows, cols = 2*pad+1, segments+2*pad+1
    if rows*cols > cell_limit:
        raise ValueError('Search region exceeds max_cells; reduce padding/extent or increase cell_size_m')
    padded_distance = 0.0 if same_point else distance
    if math.hypot(padded_distance+pad*step, pad*step) > radius_limit:
        raise ValueError('Padded search region exceeds max_region_radius_m')
    # Interior intervals are <= requested cell size; padding retains that cell size.
    # Including both endpoints exactly avoids unchecked endpoint-to-grid connectors.
    middle = np.linspace(0, padded_distance, segments+1)
    x = np.concatenate((-np.arange(pad, 0, -1)*step, middle,
                        padded_distance+np.arange(1, pad+1)*step))
    y = np.arange(-pad, pad+1)*step
    xx, yy = np.meshgrid(x, y)
    rho = np.hypot(xx, yy)
    directions = (xx[..., None]*along+yy[..., None]*across)/np.where(rho == 0, 1, rho)[..., None]
    units = np.cos(rho/MOON_RADIUS_M)[..., None]*origin + np.sin(rho/MOON_RADIUS_M)[..., None]*directions
    lat = np.degrees(np.arctan2(units[..., 2], np.hypot(units[..., 0], units[..., 1])))
    lon = np.degrees(np.arctan2(units[..., 1], units[..., 0]))
    start_rc, goal_rc = (pad, pad), (pad, pad+segments)
    # Preserve the caller's exact coordinate spellings at the endpoints as well.
    lat[start_rc], lon[start_rc] = start
    lat[goal_rc], lon[goal_rc] = goal
    heights = np.asarray(dem.sample(lat, lon), dtype=float)
    if heights.shape != lat.shape:
        raise ValueError('DEM.sample must return one elevation per supplied coordinate')
    blocked = exclusion_mask(lat, lon) if exclusion_mask is not None else None
    result = _search(heights, x, y, start_rc, goal_rc, settings, blocked, units)
    # Attach coordinates to the diagnostic cells only after geographic sampling.
    for check in result['endpoint_checks'].values():
        for cell in [check] + check['nearby_terrain_candidates']:
            r, c = cell['grid_cell']
            cell['latitude_deg'] = float(lat[r, c])
            cell['longitude_deg'] = float(lon[r, c])
    result['path'] = [
        {'latitude_deg': float(lat[r, c]), 'longitude_deg': float(lon[r, c]),
         'elevation_m': float(heights[r, c])} for r, c in result['path_rc']
    ]
    result['search'] = {
        'grid_shape': [rows, cols], 'requested_cell_size_m': step, 'padding_m': pad*step,
        'projection': 'local spherical azimuthal equidistant, x toward destination',
        'moon_radius_m': MOON_RADIUS_M, 'max_slope_deg': settings[0],
        'max_uphill_grade_deg': settings[1], 'max_downhill_grade_deg': settings[2],
        'climb_weight': settings[3], 'slope_weight': settings[5],
        'slope_reference_deg': SLOPE_REFERENCE_DEG, 'max_region_radius_m': radius_limit,
        'max_cells': cell_limit, 'max_expansions': settings[4],
        'start': {'latitude_deg': start[0], 'longitude_deg': start[1]},
        'goal': {'latitude_deg': goal[0], 'longitude_deg': goal[1]},
    }
    return result
