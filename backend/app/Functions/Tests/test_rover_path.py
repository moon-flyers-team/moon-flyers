"""A* checks with hand-computable terrain and an independent shortest-path oracle."""
import heapq
import json
import math
import sys
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from Functions.rover_path import MOON_RADIUS_M, plan_rover_grid, plan_rover_route


class FlatDEM:
    """Deterministic controlled input, not lunar observations."""
    def __init__(self):
        self.calls = 0

    def sample(self, lat, lon):
        self.calls += 1
        return np.zeros(np.asarray(lat).shape)


def dijkstra_flat(blocked, start, goal, step, heights=None, weight=0, slope_weight=0):
    """Independent zero-heuristic oracle; optional heights add uphill costs."""
    def slope(r, c):
        if heights is None:
            return 0
        lo_r, hi_r = max(0, r-1), min(heights.shape[0]-1, r+1)
        lo_c, hi_c = max(0, c-1), min(heights.shape[1]-1, c+1)
        dy = (heights[hi_r, c]-heights[lo_r, c])/((hi_r-lo_r)*step)
        dx = (heights[r, hi_c]-heights[r, lo_c])/((hi_c-lo_c)*step)
        return math.degrees(math.atan(math.hypot(dx, dy)))

    queue = [(0.0, start)]
    best = {start: 0.0}
    while queue:
        cost, (r, c) = heapq.heappop(queue)
        if cost > best[(r, c)]:
            continue
        if (r, c) == goal:
            return cost
        for dr in (-1, 0, 1):
            for dc in (-1, 0, 1):
                nr, nc = r+dr, c+dc
                if (dr, dc) == (0, 0) or not (0 <= nr < blocked.shape[0] and 0 <= nc < blocked.shape[1]):
                    continue
                if blocked[nr, nc] or (dr and dc and (blocked[r, nc] or blocked[nr, c])):
                    continue
                rise = 0 if heights is None else max(0, heights[nr, nc]-heights[r, c])
                distance = math.hypot(dr, dc)*step
                grade = 0 if heights is None else math.degrees(math.atan2(heights[nr, nc]-heights[r, c], distance))
                steepness = max(slope(r, c), slope(nr, nc), abs(grade))
                new = cost+distance+weight*rise+slope_weight*distance*(steepness/15)**2
                if new < best.get((nr, nc), math.inf):
                    best[(nr, nc)] = new
                    heapq.heappush(queue, (new, (nr, nc)))
    return math.inf


class RoverGridTests(unittest.TestCase):
    def route(self, heights=None, start=(1, 1), goal=(5, 5), **kwargs):
        settings = dict(cell_size_m=10, max_slope_deg=20, slope_weight=0)
        settings.update(kwargs)
        return plan_rover_grid(np.zeros((7, 7)) if heights is None else heights, start, goal, **settings)

    def test_flat_diagonal_has_known_optimal_distance(self):
        result = self.route()
        self.assertEqual(result['status'], 'route_found')
        self.assertEqual(result['path_rc'][0], [1, 1])
        self.assertEqual(result['path_rc'][-1], [5, 5])
        self.assertAlmostEqual(result['distance_m'], 40*math.sqrt(2))
        self.assertAlmostEqual(result['cost'], result['distance_m'])
        self.assertEqual(result['elevation_gain_m'], 0)
        json.dumps(result, allow_nan=False)

    def test_wall_requires_detour_and_matches_dijkstra(self):
        blocked = np.zeros((7, 7), dtype=bool)
        blocked[:5, 3] = True
        result = self.route(start=(2, 1), goal=(2, 5), blocked=blocked)
        self.assertEqual(result['status'], 'route_found')
        self.assertGreater(result['distance_m'], 40)
        self.assertAlmostEqual(result['cost'], dijkstra_flat(blocked, (2, 1), (2, 5), 10))
        self.assertTrue(all(not blocked[r, c] for r, c in result['path_rc']))

    def test_corner_cutting_is_forbidden(self):
        blocked = np.ones((7, 7), dtype=bool)
        blocked[1, 1] = blocked[2, 2] = False
        result = self.route(goal=(2, 2), blocked=blocked)
        self.assertEqual(result['status'], 'no_route')
        self.assertEqual(result['path_rc'], [])
        self.assertIsNone(result['distance_m'])

    def test_incomplete_terrain_does_not_turn_into_flat_ground(self):
        height = np.zeros((7, 7))
        height[:, 3] = np.nan
        result = self.route(height)
        self.assertEqual(result['status'], 'no_route')
        height[1, 1] = math.inf
        self.assertEqual(self.route(height)['status'], 'start_blocked')

    def test_terrain_slope_blocks_even_travel_along_a_contour(self):
        # Each row rises 10 m over 10 m: 45° hillside. The requested route is
        # horizontal with zero edge grade, but the rover would face 45° cross-slope.
        height = np.repeat((np.arange(7)*10.0)[:, None], 7, axis=1)
        result = self.route(height, start=(3, 1), goal=(3, 5))
        self.assertEqual(result['status'], 'start_blocked')

    def test_directional_uphill_and_downhill_limits_are_distinct(self):
        height = np.repeat((np.arange(7)*2.0)[None, :], 7, axis=0)
        # Eastwards every move ascends; north/south detours cannot bypass that grade.
        result = self.route(height, start=(3, 1), goal=(3, 5), max_uphill_grade_deg=5)
        self.assertEqual(result['status'], 'no_route')
        downhill = self.route(height, start=(3, 5), goal=(3, 1), max_uphill_grade_deg=5)
        self.assertEqual(downhill['status'], 'route_found')
        self.assertAlmostEqual(downhill['elevation_loss_m'], 8)
        self.assertAlmostEqual(downhill['max_downhill_grade_deg'], math.degrees(math.atan(.2)))
        self.assertEqual(self.route(height, start=(3, 5), goal=(3, 1),
                                    max_downhill_grade_deg=5)['status'], 'no_route')

    def test_threshold_equality_passes_and_statistics_use_metres(self):
        height = np.repeat((np.arange(7)*2.0)[None, :], 7, axis=0)
        slope = math.degrees(math.atan(.2))
        result = self.route(height, start=(3, 1), goal=(3, 5), max_slope_deg=slope, climb_weight=3)
        self.assertEqual(result['status'], 'route_found')
        self.assertAlmostEqual(result['distance_m'], 40)
        self.assertAlmostEqual(result['elevation_gain_m'], 8)
        self.assertAlmostEqual(result['cost'], 40+3*8)
        self.assertAlmostEqual(result['terrain_distance_m'], 4*math.hypot(10, 2))
        self.assertAlmostEqual(result['max_terrain_slope_deg'], slope)

    def test_climbing_penalty_can_favour_a_longer_lower_route(self):
        height = np.zeros((7, 7))
        height[2:5, 3] = 2
        direct = self.route(height, start=(3, 1), goal=(3, 5), max_slope_deg=60)
        careful = self.route(height, start=(3, 1), goal=(3, 5), max_slope_deg=60, climb_weight=100)
        self.assertEqual(careful['status'], 'route_found')
        self.assertGreater(careful['distance_m'], direct['distance_m'])
        self.assertLess(careful['elevation_gain_m'], direct['elevation_gain_m'])

    def test_blocked_endpoints_same_point_and_budget_have_explicit_statuses(self):
        blocked = np.zeros((7, 7), dtype=bool)
        blocked[5, 5] = True
        self.assertEqual(self.route(blocked=blocked)['status'], 'goal_blocked')
        blocked[1, 1] = True
        self.assertEqual(self.route(blocked=blocked)['status'], 'start_blocked')
        self.assertEqual(self.route(max_expansions=1)['status'], 'search_limit_reached')
        point = self.route(goal=(1, 1))
        self.assertEqual(point['status'], 'route_found')
        self.assertEqual(point['distance_m'], 0)
        self.assertEqual(point['path_rc'], [[1, 1]])

    def test_astar_matches_dijkstra_on_several_reproducible_maps(self):
        rng = np.random.default_rng(42)
        for _ in range(12):
            blocked = rng.random((7, 7)) < .2
            blocked[1, 1] = blocked[5, 5] = False
            expected = dijkstra_flat(blocked, (1, 1), (5, 5), 10)
            result = self.route(blocked=blocked)
            if math.isinf(expected):
                self.assertEqual(result['status'], 'no_route')
            else:
                self.assertEqual(result['status'], 'route_found')
                self.assertAlmostEqual(result['cost'], expected)

    def test_weighted_astar_also_matches_independent_dijkstra(self):
        rng = np.random.default_rng(17)
        for _ in range(6):
            heights = rng.random((7, 7))*2
            blocked = rng.random((7, 7)) < .15
            blocked[1, 1] = blocked[5, 5] = False
            expected = dijkstra_flat(blocked, (1, 1), (5, 5), 10, heights, weight=30, slope_weight=1)
            result = self.route(heights, max_slope_deg=89, blocked=blocked, climb_weight=30, slope_weight=1)
            if math.isinf(expected):
                self.assertEqual(result['status'], 'no_route')
            else:
                self.assertEqual(result['status'], 'route_found')
                self.assertAlmostEqual(result['cost'], expected)

    def test_diagonal_cannot_bypass_steep_orthogonal_approaches(self):
        # Central slopes cancel in this alternating pattern. Diagonal grade is
        # 35.3°, but both side approaches are 45° and exceed the 40° limit.
        height = np.tile([0, 10, 0, 10, 0, 10, 0], (7, 1)).astype(float)
        result = self.route(height, start=(2, 2), goal=(3, 3), max_slope_deg=60,
                            max_uphill_grade_deg=40, max_downhill_grade_deg=40)
        self.assertEqual(result['status'], 'no_route')

    def test_slope_preference_penalizes_downhill_and_uphill_equally(self):
        # No ascent charge: the new term alone must penalize descending too.
        height = np.repeat((np.arange(7)*2.0)[None, :], 7, axis=0)
        up = self.route(height, start=(3, 1), goal=(3, 5), slope_weight=1)
        down = self.route(height, start=(3, 5), goal=(3, 1), slope_weight=1)
        expected_penalty = 40*(math.degrees(math.atan(.2))/15)**2
        self.assertAlmostEqual(up['slope_penalty_cost'], expected_penalty)
        self.assertAlmostEqual(up['cost'], 40+expected_penalty)
        self.assertAlmostEqual(up['cost'], down['cost'])
        self.assertEqual(down['climb_penalty_cost'], 0)

    def test_sideways_travel_is_penalized_despite_no_elevation_change(self):
        height = np.repeat((np.arange(7)*2.0)[:, None], 7, axis=1)
        result = self.route(height, start=(3, 1), goal=(3, 5), slope_weight=1, climb_weight=2)
        self.assertEqual(result['status'], 'route_found')
        self.assertEqual(result['elevation_gain_m'], 0)
        self.assertEqual(result['elevation_loss_m'], 0)
        self.assertEqual(result['max_uphill_grade_deg'], 0)
        self.assertGreater(result['slope_penalty_cost'], 0)
        self.assertAlmostEqual(result['cost'], 40+40*(math.degrees(math.atan(.2))/15)**2)

    def test_stronger_slope_preference_can_select_a_gentler_detour(self):
        height = np.zeros((7, 7))
        height[2:5, 3] = 2
        direct = self.route(height, start=(3, 1), goal=(3, 5))
        gentle = self.route(height, start=(3, 1), goal=(3, 5), slope_weight=25)
        self.assertGreater(gentle['distance_m'], direct['distance_m'])
        self.assertLess(gentle['max_terrain_slope_deg'], direct['max_terrain_slope_deg'])

    def test_combined_weights_preserve_cost_accounting_and_hard_limits(self):
        height = np.repeat((np.arange(7)*2.0)[None, :], 7, axis=0)
        result = self.route(height, start=(3, 1), goal=(3, 5), slope_weight=2, climb_weight=3)
        self.assertAlmostEqual(result['cost'], result['distance_m'] +
                               result['slope_penalty_cost'] + result['climb_penalty_cost'])
        self.assertAlmostEqual(result['climb_penalty_cost'], 24)
        blocked = self.route(height, max_slope_deg=5, slope_weight=0)
        self.assertEqual(blocked['status'], 'start_blocked')

    def test_invalid_input_is_rejected_before_search(self):
        cases = [dict(cell_size_m=0), dict(max_slope_deg=-1), dict(max_slope_deg=90),
                 dict(climb_weight=-1), dict(climb_weight=math.nan), dict(slope_weight=-1),
                 dict(slope_weight=math.inf), dict(slope_weight=True), dict(max_expansions=True),
                 dict(max_cells=10), dict(blocked=np.zeros((7, 7))), dict(blocked=np.zeros((2, 2), dtype=bool))]
        for case in cases:
            with self.subTest(case=case), self.assertRaises(ValueError):
                self.route(**case)
        for start in [(8, 0), (1.1, 1), (True, 1), '11']:
            with self.subTest(start=start), self.assertRaises(ValueError):
                self.route(start=start)
        with self.assertRaises(ValueError):
            self.route(np.zeros((2, 2)))


class GeographicRoverTests(unittest.TestCase):
    def route(self, start=(0, 0), goal=(0, .01), **kwargs):
        settings = dict(max_slope_deg=20, cell_size_m=20, padding_m=40)
        settings.update(kwargs)
        return plan_rover_route(FlatDEM(), start, goal, **settings)

    def test_exact_endpoints_and_known_equatorial_arc(self):
        result = self.route()
        self.assertEqual(result['status'], 'route_found')
        self.assertEqual(result['path'][0]['latitude_deg'], 0)
        self.assertEqual(result['path'][0]['longitude_deg'], 0)
        self.assertEqual(result['path'][-1]['longitude_deg'], .01)
        self.assertAlmostEqual(result['distance_m'], MOON_RADIUS_M*math.radians(.01), places=6)
        self.assertEqual(result['search']['moon_radius_m'], MOON_RADIUS_M)
        self.assertEqual(result['search']['slope_weight'], 1)
        self.assertEqual(result['slope_penalty_cost'], 0)
        json.dumps(result, allow_nan=False)

    def test_north_south_and_dateline_routes_do_not_use_earth_distances(self):
        meridian = self.route(start=(0, 20), goal=(.01, 20))
        self.assertAlmostEqual(meridian['distance_m'], MOON_RADIUS_M*math.radians(.01), places=6)
        dateline = self.route(start=(0, 179.995), goal=(0, -179.995))
        self.assertEqual(dateline['status'], 'route_found')
        self.assertAlmostEqual(dateline['distance_m'], meridian['distance_m'], places=5)
        self.assertTrue(all(-180 <= p['longitude_deg'] <= 180 for p in dateline['path']))

    def test_south_pole_route_and_very_nearby_endpoints(self):
        polar = self.route(start=(-90, 0), goal=(-89.99, 100))
        self.assertEqual(polar['status'], 'route_found')
        self.assertAlmostEqual(polar['distance_m'], MOON_RADIUS_M*math.radians(.01), places=5)
        near = self.route(goal=(0, .000001))
        self.assertEqual(near['status'], 'route_found')
        self.assertAlmostEqual(near['distance_m'], MOON_RADIUS_M*math.radians(.000001))
        self.assertEqual(self.route(goal=(0, 0))['distance_m'], 0)

    def test_exclusions_and_unknown_coverage_fail_without_fallback(self):
        result = self.route(exclusion_mask=lambda lat, lon: np.ones(lat.shape, dtype=bool))
        self.assertEqual(result['status'], 'start_blocked')
        self.assertEqual(result['path'], [])

        class MissingDEM:
            def sample(self, lat, lon):
                return np.full(lat.shape, np.nan)
        result = plan_rover_route(MissingDEM(), (0, 0), (0, .01), max_slope_deg=20)
        self.assertEqual(result['status'], 'start_blocked')

    def test_resource_limits_are_checked_before_dem_access(self):
        for settings in [dict(max_cells=10), dict(max_region_radius_m=50), dict(max_expansions=0),
                         dict(padding_m=-1), dict(max_region_radius_m=60_000), dict(cell_size_m=1e-320)]:
            dem = FlatDEM()
            with self.subTest(settings=settings), self.assertRaises(ValueError):
                plan_rover_route(dem, (0, 0), (0, .01), max_slope_deg=20, **settings)
            self.assertEqual(dem.calls, 0)
        for point in [(91, 0), (0, 181), (math.nan, 0)]:
            with self.assertRaises(ValueError):
                self.route(start=point)

    def test_bad_dem_shapes_and_bad_exclusion_masks_are_rejected(self):
        class WrongDEM:
            def sample(self, lat, lon):
                return np.zeros(3)
        with self.assertRaises(ValueError):
            plan_rover_route(WrongDEM(), (0, 0), (0, .01), max_slope_deg=20)
        with self.assertRaises(ValueError):
            self.route(exclusion_mask=lambda lat, lon: np.zeros(lat.shape))
