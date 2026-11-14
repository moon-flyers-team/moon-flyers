"""Focused calculation checks; each case isolates a boundary or a known numeric result."""
import unittest
import sys
from pathlib import Path

# Add backend/app to Python's module search path
APP_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(APP_DIR))

from Functions.visibility import (
    calculate_visibility,
    calculate_visibility_margin
)
from Functions.windows import extract_visibility_windows
from Functions.metrics import calculate_metrics
from Functions.suitability import evaluate_fit

H_AZ = [0, 90, 180, 270]
H_EL = [0, 0, 0, 0]

class CoreTests(unittest.TestCase):
    def setUp(self):
        """Build a reusable history with known visible and blocked periods."""
        self.ts = [f"2027-08-01T0{i}:00:00Z" for i in range(4)]
        self.end = "2027-08-01T04:00:00Z"

    def test_disc_radius_clearance(self):
        """Check the whole disc clears the horizon: a visible centre alone is insufficient."""
        m = calculate_visibility_margin([10, 10], [.5, .6], H_AZ, H_EL, .25, .3)
        self.assertAlmostEqual(m[0], -.05)
        self.assertAlmostEqual(m[1], .05)
        self.assertEqual(calculate_visibility([10,10], [.5,.6], H_AZ,H_EL,.25,.3),[False,True])

    def test_wraparound(self):
        """Directions just before and after north must use the same continuous skyline."""
        self.assertEqual(calculate_visibility([359,1],[3,3],[350,10,90,180,270],[2,2,0,0,0],0,.3),[True,True])

    def test_duplicate_horizon_conflict(self):
        """Conflicting heights at 0°/360° must fail rather than choose an arbitrary one."""
        with self.assertRaises(ValueError):
            calculate_visibility([0], [1], [0, 360, 90], [0, 3, 0], 0)

    def test_windows_sample_hold(self):
        """Consecutive true flags merge; a false flag splits the visible intervals."""
        self.assertEqual(extract_visibility_windows(self.ts, [True,True,False,True], self.end),
            [{"start_utc":self.ts[0],"end_utc":self.ts[2]},
             {"start_utc":self.ts[3],"end_utc":self.end}])

    def test_crossing_interpolated(self):
        """Equal positive/negative margins place sunset halfway between the samples."""
        ts = self.ts[:2]
        w = extract_visibility_windows(ts, [True,False], "2027-08-01T02:00:00Z", [2,-2])
        self.assertEqual(w, [{"start_utc":ts[0],"end_utc":"2027-08-01T00:30:00Z"}])

    def test_crossing_gained(self):
        """Unequal margins place sunrise one quarter of the way into the interval."""
        ts = self.ts[:2]
        w = extract_visibility_windows(ts, [False,True], "2027-08-01T02:00:00Z", [-1,3])
        self.assertEqual(w, [{"start_utc":"2027-08-01T00:15:00Z", "end_utc":"2027-08-01T02:00:00Z"}])

    def test_exact_zero_touch_not_invented(self):
        """Touching the boundary adds no earlier duration; the final true state is held."""
        w = extract_visibility_windows(self.ts[:2], [False,True], "2027-08-01T02:00:00Z", [-2,0])
        self.assertEqual(w, [{"start_utc":self.ts[1], "end_utc":"2027-08-01T02:00:00Z"}])

    def test_metrics_hold(self):
        """Four hourly states give 50% Sun and 75% Earth coverage, with known outage lengths."""
        m=calculate_metrics(self.ts,[True,True,False,False],[False,True,True,True],self.end)
        self.assertEqual(m,{"sun_visible_pct":50,"longest_darkness_hours":2,
                            "earth_visible_pct":75,"longest_earth_blackout_hours":1,"slope_deg":None})
        self.assertEqual(evaluate_fit(m), {"status":"power_short","violations":["sun_visible_pct"]})

    def test_metrics_interpolated(self):
        """A crossing at 00:30 gives 25% Sun and 75% Earth over a two-hour mission."""
        m = calculate_metrics(self.ts[:2],[True,False],[False,True],"2027-08-01T02:00:00Z",
                              sun_clearance_margin_deg=[2,-2],earth_clearance_margin_deg=[-2,2])
        self.assertAlmostEqual(m["sun_visible_pct"],25)
        self.assertAlmostEqual(m["longest_darkness_hours"],1.5)
        self.assertAlmostEqual(m["earth_visible_pct"],75)
        self.assertAlmostEqual(m["longest_earth_blackout_hours"],.5)

    def test_missing_body(self):
        """A disabled body stays unknown; suitability must reject incomplete metrics."""
        m=calculate_metrics(self.ts,[True]*4,None,self.end)
        self.assertIsNone(m["earth_visible_pct"])
        with self.assertRaises(ValueError):
            evaluate_fit(m)

    def test_all_visible_none_visible(self):
        """Check the extremes: continuous coverage has no outage; no coverage has a mission-long outage."""
        m=calculate_metrics(self.ts,[True]*4,[False]*4,self.end)
        self.assertEqual((m["sun_visible_pct"],m["longest_darkness_hours"]),(100,0))
        self.assertEqual((m["earth_visible_pct"],m["longest_earth_blackout_hours"]),(0,4))

    def test_bad_order(self):
        """Reject timestamps that run backwards because their durations are invalid."""
        with self.assertRaises(ValueError):
            extract_visibility_windows([self.ts[1],self.ts[0]],[True,False],self.end)

    def test_fit_statuses(self):
        """Exercise all four statuses and confirm exact requirement boundaries pass."""
        m=calculate_metrics(self.ts,[True]*4,[True]*4,self.end)
        self.assertEqual(evaluate_fit(m)["status"],"both_met")
        self.assertEqual(evaluate_fit(m,{"min_earth_visible_pct":100,"max_earth_blackout_hours":0})["status"],"both_met")
        m["earth_visible_pct"]=40
        self.assertEqual(evaluate_fit(m)["status"],"comms_short")
        m["sun_visible_pct"]=30
        self.assertEqual(evaluate_fit(m)["status"],"neither_met")

if __name__ == "__main__": unittest.main()
