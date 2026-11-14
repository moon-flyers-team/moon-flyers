"""Compatibility with the teammate's supplied terrain sample (message.txt).

Body positions below are controlled test inputs, not supplied ephemerides.
"""
import json
import math
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from Functions.visibility import calculate_visibility, calculate_visibility_margin


class ProvidedHorizonTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        """Load the supplied terrain once so every check uses the same sample."""
        cls.data = json.loads((Path(__file__).parent / 'fixtures/horizon_example.json').read_text())

    def test_supplied_arrays_cover_the_compass_without_gaps(self):
        """Check the teammate fixture has matching finite samples for every compass degree."""
        self.assertEqual(self.data['horizon_azimuth_deg'], list(range(360)))
        elevations = self.data['horizon_elevation_deg']
        self.assertEqual(len(elevations), 360)
        self.assertTrue(all(math.isfinite(e) for e in elevations))
        self.assertEqual(self.data['horizon_gap_fraction'], 0)

    def test_visibility_accepts_supplied_horizon_including_negative_elevations(self):
        """Use controlled body elevations around the real skyline to check clear/blocked decisions."""
        azimuths = [0, 135, 359]
        skyline = [self.data['horizon_elevation_deg'][i] for i in azimuths]
        # Required bottom-disc clearance is .3; radius is .2.
        # The first/last samples clear by .1, the middle is blocked by .1.
        elevations = [h + .5 + delta for h, delta in zip(skyline, [.1, -.1, .1])]
        args = (azimuths, elevations, self.data['horizon_azimuth_deg'],
                self.data['horizon_elevation_deg'], .2, .3)
        margins = calculate_visibility_margin(*args)
        for actual, expected in zip(margins, [.1, -.1, .1]):
            self.assertAlmostEqual(actual, expected)
        self.assertEqual(calculate_visibility(*args), [True, False, True])

    def test_interpolation_wraps_between_last_and_first_sample(self):
        """At 359.5° the skyline must be halfway between the 359° and 0° samples."""
        skyline = self.data['horizon_elevation_deg']
        expected = (skyline[359] + skyline[0]) / 2
        args = ([359.5, -.5], [0, 0], self.data['horizon_azimuth_deg'], skyline, .2, .3)
        for margin in calculate_visibility_margin(*args):
            self.assertAlmostEqual(margin, -expected - .5)
