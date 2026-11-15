"""Connect the rover planner to the actual LOLA loader, using its tiny offline fixture."""
import json
import math
import os

import numpy as np
import pytest

from app.Functions.rover_path import MOON_RADIUS_M, plan_rover_route
from src.lunar_horizon_dem import DEM
from tools.lola_fixture import write_dataset


def test_rover_route_reads_lola_loader_without_horizon_or_mock_fallback(tmp_path):
    directory = write_dataset(tmp_path / 'lola_dem')
    dem = DEM(str(directory))
    start, goal = (-88.0, 45), (-88.0, 45.1)
    # This is a loader-compatibility test on synthetic raster heights, not a real
    # claim about traversability. Limits here are illustrative test inputs.
    result = plan_rover_route(dem, start, goal, cell_size_m=20, padding_m=40, max_slope_deg=45)
    assert result['status'] == 'route_found'
    assert result['path'][0]['latitude_deg'] == start[0]
    assert result['path'][0]['longitude_deg'] == start[1]
    assert result['path'][-1]['latitude_deg'] == goal[0]
    assert result['path'][-1]['longitude_deg'] == goal[1]
    lat = np.array([p['latitude_deg'] for p in result['path']])
    lon = np.array([p['longitude_deg'] for p in result['path']])
    assert [p['elevation_m'] for p in result['path']] == pytest.approx(dem.sample(lat, lon))
    assert result['distance_m'] > 0
    assert result['max_terrain_slope_deg'] <= 45
    _check_route_against_dem(result, dem, start, goal, 45)


def _check_route_against_dem(result, dem, start, goal, limit):
    """Independently re-read heights and calculate lengths/grades from the polyline."""
    assert result['status'] == 'route_found', (
        f"Real-data route not found: {result['status']}: {result['reason']}. "
        "Inspect the terrain/limits and select known traversable endpoints; "
        "a blocked/no-route result is not automatically an algorithm defect.")
    points = result['path']
    assert len(points) >= 2, 'Choose distinct endpoints for a meaningful route check'
    assert (points[0]['latitude_deg'], points[0]['longitude_deg']) == start
    assert (points[-1]['latitude_deg'], points[-1]['longitude_deg']) == goal
    lat = np.array([p['latitude_deg'] for p in points])
    lon = np.array([p['longitude_deg'] for p in points])
    heights = dem.sample(lat, lon)
    assert np.all(np.isfinite(heights))
    assert [p['elevation_m'] for p in points] == pytest.approx(heights)
    lengths, grades = [], []
    for i in range(len(points)-1):
        a, b = math.radians(lat[i]), math.radians(lat[i+1])
        dlon = math.radians(lon[i+1]-lon[i])
        hav = math.sin((b-a)/2)**2 + math.cos(a)*math.cos(b)*math.sin(dlon/2)**2
        distance = 2*MOON_RADIUS_M*math.asin(math.sqrt(min(1, max(0, hav))))
        assert distance > 0
        lengths.append(distance)
        grades.append(math.degrees(math.atan2(heights[i+1]-heights[i], distance)))
    assert max(abs(g) for g in grades) <= limit+1e-8
    assert result['max_terrain_slope_deg'] <= limit+1e-8
    assert result['distance_m'] == pytest.approx(sum(lengths), rel=1e-7)
    assert result['elevation_gain_m'] == pytest.approx(sum(max(0, d) for d in np.diff(heights)))
    assert result['elevation_loss_m'] == pytest.approx(sum(max(0, -d) for d in np.diff(heights)))
    assert result['max_uphill_grade_deg'] == pytest.approx(max([0]+grades), abs=1e-7)
    assert result['max_downhill_grade_deg'] == pytest.approx(max([0]+[-g for g in grades]), abs=1e-7)
    assert result['cost'] == pytest.approx(
        result['distance_m']+result['slope_penalty_cost']+result['climb_penalty_cost'])
    json.dumps(result, allow_nan=False)


@pytest.mark.skipif(os.getenv('MOON_FLYERS_REAL_ROVER') != '1',
                    reason='requires local LOLA rasters; set MOON_FLYERS_REAL_ROVER=1')
def test_rover_route_on_real_lola_dataset(tmp_path):
    """Real rasters only: no JPL, internet, synthetic terrain, or API involved.

    Default coordinates are the short real-data case the teammate reported passing.
    This is not an operational access route. Environment overrides remain available.
    Enabled runs fail on missing data, blocked endpoints, or no route; these are
    never silently turned into a passing synthetic test.
    """
    directory = os.environ.get('LOLA_DEM_DIR')
    assert directory, 'Set LOLA_DEM_DIR to the directory containing the calibrated IMG/LBL dataset'
    start = tuple(json.loads(os.getenv('MOON_FLYERS_ROVER_START', '[-89.90461690407035, 0.0]')))
    goal = tuple(json.loads(os.getenv('MOON_FLYERS_ROVER_GOAL', '[-89.90461462373575, -0.3961843417649203]')))
    dem = DEM(directory)
    result = plan_rover_route(dem, start, goal, cell_size_m=20, padding_m=200,
                              max_slope_deg=15, max_uphill_grade_deg=15,
                              max_downhill_grade_deg=15, climb_weight=2, slope_weight=1)
    report = tmp_path / 'real_rover_route.json'
    report.write_text(json.dumps(result, indent=2, allow_nan=False), encoding='utf-8')
    print(f"Real LOLA route report: {report}")
    print(f"Status: {result['status']}; distance: {result['distance_m']} m; "
          f"maximum modelled terrain slope: {result['max_terrain_slope_deg']} degrees")
    print('Endpoint checks and nearby terrain candidates (not verified routes):')
    print(json.dumps(result['endpoint_checks'], indent=2, allow_nan=False))
    _check_route_against_dem(result, dem, start, goal, 15)
