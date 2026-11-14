"""Landing-search checks using one reusable history and hand-calculated mission stays."""
import unittest
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from datetime import datetime, timedelta, timezone
from Functions.landing_windows import find_landing_windows, rank_landing_windows
from Functions.metrics import initial_visibility_hours
from Functions.suitability import evaluate_fit


class LandingWindowsTests(unittest.TestCase):
    def setUp(self):
        """Build a reusable history with known visible and blocked periods."""
        start = datetime(2027, 8, 1, tzinfo=timezone.utc)
        self.times = [(start + timedelta(hours=i)).isoformat().replace('+00:00','Z') for i in range(12)]
        self.end = (start + timedelta(hours=12)).isoformat().replace('+00:00','Z')
        # Sun: visible 00–06, blocked 06–09, visible 09–12. Earth: visible throughout.
        # Candidates land at 00, 02, or 04 and each stay for four hours.
        self.base = dict(
            timestamps_utc=self.times,
            sun_visible=[True]*6 + [False]*3 + [True]*3,
            earth_visible=[True]*12,
            data_end_utc=self.end,
            window_start_utc=self.times[0],
            window_end_utc=self.times[4],
            days_on_surface=4/24,
            candidate_step_hours=2,
        )

    def test_search_crops_partial_missions(self):
        """Each touchdown must score its own four-hour stay, not the whole shared history."""
        rows = find_landing_windows(**self.base)
        self.assertEqual(len(rows), 3)
        # 00-04 all sunshine; 04-08 half; 02-06 all sunshine
        by_time = {r['landing_utc']: r for r in rows}
        self.assertEqual(by_time[self.times[0]]['metrics']['sun_visible_pct'], 100)
        self.assertEqual(by_time[self.times[2]]['metrics']['sun_visible_pct'], 100)
        self.assertEqual(by_time[self.times[4]]['metrics']['sun_visible_pct'], 50)
        self.assertEqual(by_time[self.times[4]]['metrics']['longest_darkness_hours'], 2)

    def test_rank_fit_first_then_percentages(self):
        """A candidate meeting the requirements must rank above the candidate short of sunlight."""
        rows = find_landing_windows(**self.base,
            constraints={'min_sun_visible_pct': 80, 'max_darkness_hours': 2,
                         'min_earth_visible_pct': 0, 'max_earth_blackout_hours': 10})
        self.assertEqual(rows[-1]['fit']['status'], 'power_short')
        self.assertEqual(rows[0]['rank'], 1)

    def test_initial_sunlight_and_earth(self):
        """Initial coverage counts only the uninterrupted period starting at touchdown."""
        rows = find_landing_windows(**self.base,
            constraints={'min_sun_visible_pct': 0, 'max_darkness_hours': 10,
                         'min_earth_visible_pct': 0, 'max_earth_blackout_hours': 10,
                         'min_initial_sunlight_hours': 3,
                         'min_initial_earth_visibility_hours': 4})
        by_time = {r['landing_utc']: r for r in rows}
        self.assertEqual(by_time[self.times[4]]['metrics']['initial_sunlight_hours'], 2)
        self.assertEqual(by_time[self.times[4]]['fit']['violations'], ['initial_sunlight_hours'])
        self.assertEqual(by_time[self.times[4]]['metrics']['initial_earth_visibility_hours'], 4)

    def test_initial_zero_if_not_visible_at_touchdown(self):
        """Coverage starting later cannot satisfy an immediate touchdown requirement."""
        self.assertEqual(initial_visibility_hours([
            {'start_utc':self.times[2], 'end_utc':self.times[4]}], self.times[0]), 0)

    def test_missing_data_rejected(self):
        """Reject a history that ends too early or omits a required body."""
        with self.assertRaises(ValueError):
            find_landing_windows(**{**self.base, 'data_end_utc':self.times[5]})
        with self.assertRaises(ValueError):
            find_landing_windows(**{**self.base, 'earth_visible':None})

    def test_non_step_aligned_candidate_with_interpolated_crossing(self):
        # 0h: +1, 2h: -1 => setting at 1h, candidate 0.5h, duration 1h
        """A 00:30 landing must not snap to a sample; sunset at 01:00 gives half an hour of Sun."""
        times = [self.times[0], self.times[2], self.times[4], self.times[6]]
        rows = find_landing_windows(
            timestamps_utc=times, sun_visible=[True,False,False,False],
            earth_visible=[True]*4, data_end_utc=self.times[8],
            window_start_utc='2027-08-01T00:30:00Z',
            window_end_utc='2027-08-01T00:30:00Z',
            days_on_surface=1/24, candidate_step_hours=6,
            sun_clearance_margin_deg=[1,-1,-1,-1],
            constraints={'min_sun_visible_pct':0,'max_darkness_hours':5,
                         'min_earth_visible_pct':0,'max_earth_blackout_hours':5})
        self.assertAlmostEqual(rows[0]['metrics']['sun_visible_pct'], 50)

    def test_rank_deterministic(self):
        """Equal scores use earlier touchdown as the tie breaker, regardless of input order."""
        c=[{'landing_utc':self.times[i], 'fit':{'status':'both_met'}, 'metrics':{'sun_visible_pct':50,'earth_visible_pct':50}} for i in [2,0,1]]
        self.assertEqual([x['landing_utc'] for x in rank_landing_windows(c)], self.times[:3])

    def test_optional_constraint_with_missing_metric_fails_loudly(self):
        """An explicitly requested initial-coverage rule requires its corresponding metric."""
        m={'sun_visible_pct':100,'longest_darkness_hours':0,'earth_visible_pct':100,'longest_earth_blackout_hours':0}
        with self.assertRaises(ValueError):
            evaluate_fit(m, {'min_initial_sunlight_hours':1})

if __name__ == '__main__':
    unittest.main()
