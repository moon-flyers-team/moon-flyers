"""Check calculation functions against current terrain code and recorded JPL positions.

Offline tests run the real horizon algorithm on a controlled spherical DEM.
An opt-in test runs the actual DEM and live JPL query for the same observer.
"""
import bisect
import json
import os

import numpy as np
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from app.Functions.evaluate_site import evaluate_site
from app.Functions.landing_windows import find_landing_windows
from app.Functions.windows import parse_utc, format_utc
from src.lunar_horizon_dem import horizon
from src.positions import positions
from src.schemas import Analysis
from src.services import visibility

FIXTURES = Path(__file__).resolve().parents[1] / 'app/Functions/Tests/fixtures'


@pytest.fixture
def recorded():
    return json.loads((FIXTURES / 'horizons_positions.json').read_text())


class ReferenceSphereDEM:
    """Controlled terrain for offline geometry checks; not real lunar DEM data."""

    last_counts = {}

    def sample(self, lat, lon):
        return np.zeros(np.broadcast(np.asarray(lat), np.asarray(lon)).shape)


@pytest.fixture
def terrain(recorded):
    request = recorded['request']
    # Zero terrain altitude and zero observer height match the recorded JPL query.
    return horizon(request['latitude_deg'], request['longitude_deg'],
                   height_above_terrain=0, dem=ReferenceSphereDEM())


def function_input(recorded):
    """Only rename/normalize provider fields; never manufacture missing time coverage.

    Horizons includes the stop sample. The functions require samples before the end.
    Provider timestamps are naive UTC; attach UTC explicitly. Radii are the backend's
    existing approximations, not angular sizes measured in this Horizons response.
    """
    raw = recorded['data']
    end = parse_utc(recorded['request']['window_end_utc'])
    times = [datetime.fromisoformat(t).replace(tzinfo=timezone.utc) for t in raw['time_utc']]
    indices = [i for i, t in enumerate(times) if t < end]
    result = {'timestamps_utc': [format_utc(times[i]) for i in indices]}
    for body, radius in [('sun', visibility.SUN_RADIUS_DEG), ('earth', visibility.EARTH_RADIUS_DEG)]:
        for angle in ('azimuth', 'elevation'):
            key = f'{body}_{angle}_deg'
            result[key] = [raw[key][i] for i in indices]
        result[f'{body}_angular_radius_deg'] = radius
    return result


def summarize(windows, start, end):
    """Independent duration oracle: clip intervals and count coverage plus every gap."""
    total = 0
    gap = 0
    cursor = start
    for window in windows:
        a = max(start, parse_utc(window['start_utc']))
        b = min(end, parse_utc(window['end_utc']))
        if b <= a:
            continue
        gap = max(gap, (a-cursor).total_seconds())
        total += (b-a).total_seconds()
        cursor = b
    gap = max(gap, (end-cursor).total_seconds())
    return total / (end-start).total_seconds()*100, gap/3600


def test_recorded_provider_grid_and_endpoint_conversion(recorded):
    raw = recorded['data']
    assert len(raw['time_utc']) == 721
    assert all(len(values) == 721 for values in raw.values())
    data = function_input(recorded)
    assert len(data['timestamps_utc']) == 720
    assert data['timestamps_utc'][0] == '2027-08-01T00:00:00Z'
    assert data['timestamps_utc'][-1] == '2027-08-30T23:00:00Z'


@pytest.mark.parametrize('horizon_kind', ['flat', 'generated_terrain'])
def test_actual_positions_through_complete_pipeline(recorded, terrain, horizon_kind):
    data = function_input(recorded)
    h = terrain if horizon_kind == 'generated_terrain' else {
        'horizon_azimuth_deg': [0, 90, 180, 270], 'horizon_elevation_deg': [0]*4}
    start = data['timestamps_utc'][0]
    result = evaluate_site(data, h, start, days_on_surface=30)
    # The complete both-body result can be serialized using the running API schema.
    Analysis(**result)
    azimuths = h['horizon_azimuth_deg']
    elevations = h['horizon_elevation_deg']
    for body in ('sun', 'earth'):
        flags = []
        margins = []
        for row in result['timeseries']:
            az = row[f'{body}_azimuth_deg'] % 360
            index = bisect.bisect_right(azimuths, az)-1
            nxt = (index+1) % len(azimuths)
            a, b = azimuths[index], azimuths[nxt]
            if nxt == 0:
                b += 360
            skyline = elevations[index] + (elevations[nxt]-elevations[index])*(az-a)/(b-a)
            margin = row[f'{body}_elevation_deg'] - data[f'{body}_angular_radius_deg'] - skyline - .3
            margins.append(margin)
            expected = margin >= 0
            assert row[f'{body}_visible'] == expected
            flags.append(expected)
        # A month of polar data exercises both blocked and clear states, not just a trivial pass.
        assert any(flags) and not all(flags)
        # Independently locate every sign-changing crossing in the hourly series.
        boundaries = {parse_utc(w[key]) for w in result['windows'][body]
                      for key in ('start_utc', 'end_utc')}
        for i in range(len(margins)-1):
            if flags[i] != flags[i+1]:
                t0 = parse_utc(data['timestamps_utc'][i])
                fraction = -margins[i]/(margins[i+1]-margins[i])
                assert t0 + timedelta(hours=fraction) in boundaries
        pct, gap = summarize(
            result['windows'][body], parse_utc(start), parse_utc(recorded['request']['window_end_utc']))
        assert result['metrics'][f'{body}_visible_pct'] == pytest.approx(pct)
        gap_key = 'longest_darkness_hours' if body == 'sun' else 'longest_earth_blackout_hours'
        assert result['metrics'][gap_key] == pytest.approx(gap)
    # Check default suitability without using the implementation's rule evaluator.
    m = result['metrics']
    expected_violations = [key for key, failed in [
        ('sun_visible_pct', m['sun_visible_pct'] < 60),
        ('longest_darkness_hours', m['longest_darkness_hours'] > 96),
        ('earth_visible_pct', m['earth_visible_pct'] < 45),
        ('longest_earth_blackout_hours', m['longest_earth_blackout_hours'] > 240)] if failed]
    assert result['fit']['violations'] == expected_violations


def test_real_data_search_scores_exact_non_sample_aligned_stays(recorded, terrain):
    data = function_input(recorded)
    full = evaluate_site(data, terrain, data['timestamps_utc'][0], days_on_surface=30)
    start = parse_utc(data['timestamps_utc'][0]) + timedelta(minutes=30)
    stop = start + timedelta(hours=12)
    # Use the complete computed margins to retain the same interpolated crossings.
    from app.Functions.visibility import calculate_visibility_margin
    kwargs = {}
    for body in ('sun', 'earth'):
        kwargs[f'{body}_visible'] = [r[f'{body}_visible'] for r in full['timeseries']]
        kwargs[f'{body}_clearance_margin_deg'] = calculate_visibility_margin(
            data[f'{body}_azimuth_deg'], data[f'{body}_elevation_deg'],
            terrain['horizon_azimuth_deg'], terrain['horizon_elevation_deg'], data[f'{body}_angular_radius_deg'])
    rows = find_landing_windows(data['timestamps_utc'], data_end_utc=recorded['request']['window_end_utc'],
        window_start_utc=format_utc(start), window_end_utc=format_utc(stop),
        days_on_surface=1.25, candidate_step_hours=6, limit=3, **kwargs)
    assert len(rows) == 3
    for row in rows:
        landing = parse_utc(row['landing_utc'])
        assert landing.minute == 30
        for body, gap_key in [('sun', 'longest_darkness_hours'), ('earth', 'longest_earth_blackout_hours')]:
            pct, gap = summarize(full['windows'][body], landing, landing+timedelta(days=1.25))
            assert row['metrics'][f'{body}_visible_pct'] == pytest.approx(pct)
            assert row['metrics'][gap_key] == pytest.approx(gap)


def test_inclusive_provider_stop_sample_is_rejected_until_sliced(recorded, terrain):
    data = function_input(recorded)
    # Appending the stop sample is a common integration mistake; fail explicitly.
    data['timestamps_utc'].append(recorded['request']['window_end_utc'])
    with pytest.raises(ValueError, match='precede mission end'):
        evaluate_site(data, terrain, data['timestamps_utc'][0], days_on_surface=30)


def test_current_horizon_function_preserves_observer_location(recorded, terrain):
    request = recorded['request']
    assert terrain['latitude_deg'] == request['latitude_deg']
    assert terrain['longitude_deg'] == request['longitude_deg']
    assert terrain['altitude_m'] == request['altitude_m'] == 0
    assert terrain['horizon_gap_fraction'] == 0
    assert len(terrain['horizon_azimuth_deg']) == len(terrain['horizon_elevation_deg']) == 360
    assert terrain['slope_deg'] == pytest.approx(0, abs=1e-6)


@pytest.mark.skipif(os.getenv('MOON_FLYERS_LIVE_TERRAIN') != '1',
                    reason='requires local LOLA rasters and live JPL; set MOON_FLYERS_LIVE_TERRAIN=1')
def test_live_terrain_and_jpl_for_same_observer():
    """Use current terrain output to request positions for exactly the same observer.

    Missing DEM files or failed JPL queries fail when explicitly enabled; this test
    never silently substitutes reference-sphere terrain or synthetic positions.
    """
    lat, lon, height = -89.667, 129.783, 2.0
    terrain = horizon(lat, lon, height_above_terrain=height)
    assert terrain['latitude_deg'] == lat and terrain['longitude_deg'] == lon
    assert terrain['horizon_gap_fraction'] == 0
    start, end = '2027-08-01T00:00:00Z', '2027-08-01T03:00:00Z'
    # Terrain altitude excludes observer height; Horizons needs their sum.
    raw = positions(terrain['latitude_deg'], terrain['longitude_deg'],
                    start.removesuffix('Z'), end.removesuffix('Z'), 3600,
                    altitude_m=terrain['altitude_m'] + height)
    data = function_input({'data': raw, 'request': {'window_end_utc': end}})
    result = evaluate_site(data, terrain, start, days_on_surface=3/24,
                           slope_deg=terrain['slope_deg'])
    Analysis(**result)
    assert len(result['timeseries']) == 3
    assert result['metrics']['slope_deg'] == terrain['slope_deg']
    for body in ('sun', 'earth'):
        pct, gap = summarize(result['windows'][body], parse_utc(start), parse_utc(end))
        assert result['metrics'][f'{body}_visible_pct'] == pytest.approx(pct)
        gap_key = 'longest_darkness_hours' if body == 'sun' else 'longest_earth_blackout_hours'
        assert result['metrics'][gap_key] == pytest.approx(gap)
