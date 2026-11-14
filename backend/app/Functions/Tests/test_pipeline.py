"""Function integration using small inputs with independently known answers.

No web server, synthetic ephemeris generator, or frontend is involved.
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from Functions.visibility import calculate_visibility_margin, calculate_visibility
from Functions.windows import extract_visibility_windows
from Functions.metrics import calculate_metrics
from Functions.suitability import evaluate_fit


class CalculationPipelineTests(unittest.TestCase):
    def test_disc_clearance_to_windows_metrics_and_fit(self):
        stamps = ['2027-08-01T00:00:00Z', '2027-08-01T01:00:00Z']
        end = '2027-08-01T02:00:00Z'
        # Radius .2 + required clearance .3 = .5 degrees.
        # Sun margin falls from +1 to -1; Earth rises from -1 to +1.
        # Both cross at 00:30; final flags are held from 01:00 to 02:00.
        common = dict(body_azimuth_deg=[0, 90], horizon_azimuth_deg=[0, 90, 180, 270],
                      horizon_elevation_deg=[0, 0, 0, 0], body_angular_radius_deg=.2,
                      horizon_clearance_deg=.3)
        margins, flags = {}, {}
        for body, elevation in [('sun', [1.5, -.5]), ('earth', [-.5, 1.5])]:
            inputs = dict(common, body_elevation_deg=elevation)
            margins[body] = calculate_visibility_margin(**inputs)
            flags[body] = calculate_visibility(**inputs)
        self.assertEqual(margins, {'sun': [1, -1], 'earth': [-1, 1]})
        self.assertEqual(flags, {'sun': [True, False], 'earth': [False, True]})
        self.assertEqual(extract_visibility_windows(stamps, flags['sun'], end, margins['sun']),
                         [{'start_utc': stamps[0], 'end_utc': '2027-08-01T00:30:00Z'}])
        self.assertEqual(extract_visibility_windows(stamps, flags['earth'], end, margins['earth']),
                         [{'start_utc': '2027-08-01T00:30:00Z', 'end_utc': end}])
        metrics = calculate_metrics(stamps, flags['sun'], flags['earth'], end,
                                   sun_clearance_margin_deg=margins['sun'],
                                   earth_clearance_margin_deg=margins['earth'])
        self.assertEqual(metrics, dict(sun_visible_pct=25, longest_darkness_hours=1.5,
                         earth_visible_pct=75, longest_earth_blackout_hours=.5, slope_deg=None))
        self.assertEqual(evaluate_fit(metrics), {'status': 'power_short', 'violations': ['sun_visible_pct']})
        # Inclusive boundaries: meeting each threshold exactly passes.
        self.assertEqual(evaluate_fit(metrics, dict(min_sun_visible_pct=25, max_darkness_hours=1.5,
                         min_earth_visible_pct=75, max_earth_blackout_hours=.5)),
                         {'status': 'both_met', 'violations': []})
