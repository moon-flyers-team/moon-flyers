"""Offline end-to-end checks for the optional visualization tool."""
import json
import math

import pytest

pytest.importorskip('matplotlib', reason='install requirements-visualization.txt to check plotting')
from tools.plot_rover_path import main  # noqa: E402


def test_demo_draws_real_computed_detour_and_records_provenance(tmp_path, capsys):
    output = tmp_path / 'demo.png'
    assert main(['--demo', '--output', str(output)]) == 0
    assert output.read_bytes().startswith(b'\x89PNG\r\n\x1a\n')
    report = json.loads(output.with_suffix('.json').read_text())
    assert 'synthetic' in report['source']
    result = report['result']
    assert result['status'] == 'route_found'
    # Demo endpoints share a meridian 0.02 degrees apart. Hill forces a longer route.
    direct = 1_737_400*math.radians(.02)
    assert result['distance_m'] > direct*1.1
    assert result['max_terrain_slope_deg'] <= 15
    assert result['path'][0]['latitude_deg'] == -89.9
    assert result['path'][-1]['latitude_deg'] == -89.88
    assert 'route_found' in capsys.readouterr().out


def test_blocked_demo_still_saves_diagnostics_without_a_fake_route(tmp_path, capsys):
    output = tmp_path / 'blocked.png'
    assert main(['--demo', '--max-slope-deg', '0', '--output', str(output)]) == 2
    assert output.read_bytes().startswith(b'\x89PNG\r\n\x1a\n')
    result = json.loads(output.with_suffix('.json').read_text())['result']
    assert result['status'] == 'start_blocked'
    assert result['path'] == []
    assert result['distance_m'] is None
    assert 'start_blocked' in capsys.readouterr().out


def test_larger_plotting_region_uses_explicit_budgets_without_relaxing_slopes(tmp_path):
    output = tmp_path / 'larger.png'
    args = ['--demo', '--padding-m', '400', '--output', str(output)]
    with pytest.raises(ValueError, match='max_cells'):
        main(args+['--max-cells', '2000'])
    assert main(args+['--max-cells', '4000', '--max-expansions', '4000']) == 0
    result = json.loads(output.with_suffix('.json').read_text())['result']
    search = result['search']
    assert search['max_cells'] == search['max_expansions'] == 4000
    assert search['grid_shape'][0]*search['grid_shape'][1] > 2000
    assert search['requested_cell_size_m'] == 20
    assert search['padding_m'] == 400
    assert search['max_slope_deg'] == search['max_uphill_grade_deg'] == search['max_downhill_grade_deg'] == 15
