import unittest
from physics.visibility import calculate_visibility, calculate_visibility_margin
from physics.windows import extract_visibility_windows
from physics.metrics import calculate_metrics
from physics.suitability import evaluate_fit

H_AZ = [0, 90, 180, 270]
H_EL = [0, 0, 0, 0]

class CoreTests(unittest.TestCase):
    def setUp(self):
        self.ts = [f"2027-08-01T0{i}:00:00Z" for i in range(4)]
        self.end = "2027-08-01T04:00:00Z"

    def test_disc_radius_clearance(self):
        m = calculate_visibility_margin([10, 10], [.5, .6], H_AZ, H_EL, .25, .3)
        self.assertAlmostEqual(m[0], -.05)
        self.assertAlmostEqual(m[1], .05)
        self.assertEqual(calculate_visibility([10,10], [.5,.6], H_AZ,H_EL,.25,.3),[False,True])

    def test_wraparound(self):
        self.assertEqual(calculate_visibility([359,1],[3,3],[350,10,90,180,270],[2,2,0,0,0],0,.3),[True,True])

    def test_duplicate_horizon_conflict(self):
        with self.assertRaises(ValueError):
            calculate_visibility([0], [1], [0, 360, 90], [0, 3, 0], 0)

    def test_windows_sample_hold(self):
        self.assertEqual(extract_visibility_windows(self.ts, [True,True,False,True], self.end),
            [{"start_utc":self.ts[0],"end_utc":self.ts[2]},
             {"start_utc":self.ts[3],"end_utc":self.end}])

    def test_crossing_interpolated(self):
        ts = self.ts[:2]
        w = extract_visibility_windows(ts, [True,False], "2027-08-01T02:00:00Z", [2,-2])
        self.assertEqual(w, [{"start_utc":ts[0],"end_utc":"2027-08-01T00:30:00Z"}])

    def test_crossing_gained(self):
        ts = self.ts[:2]
        w = extract_visibility_windows(ts, [False,True], "2027-08-01T02:00:00Z", [-1,3])
        self.assertEqual(w, [{"start_utc":"2027-08-01T00:15:00Z", "end_utc":"2027-08-01T02:00:00Z"}])

    def test_exact_zero_touch_not_invented(self):
        w = extract_visibility_windows(self.ts[:2], [False,True], "2027-08-01T02:00:00Z", [-2,0])
        self.assertEqual(w, [{"start_utc":self.ts[1], "end_utc":"2027-08-01T02:00:00Z"}])

    def test_metrics_hold(self):
        m=calculate_metrics(self.ts,[True,True,False,False],[False,True,True,True],self.end)
        self.assertEqual(m,{"sun_visible_pct":50,"longest_darkness_hours":2,
                            "earth_visible_pct":75,"longest_earth_blackout_hours":1,"slope_deg":None})
        self.assertEqual(evaluate_fit(m), {"status":"power_short","violations":["sun_visible_pct"]})

    def test_metrics_interpolated(self):
        m = calculate_metrics(self.ts[:2],[True,False],[False,True],"2027-08-01T02:00:00Z",
                              sun_clearance_margin_deg=[2,-2],earth_clearance_margin_deg=[-2,2])
        self.assertAlmostEqual(m["sun_visible_pct"],25)
        self.assertAlmostEqual(m["longest_darkness_hours"],1.5)
        self.assertAlmostEqual(m["earth_visible_pct"],75)
        self.assertAlmostEqual(m["longest_earth_blackout_hours"],.5)

    def test_missing_body(self):
        m=calculate_metrics(self.ts,[True]*4,None,self.end)
        self.assertIsNone(m["earth_visible_pct"])
        with self.assertRaises(ValueError):
            evaluate_fit(m)

    def test_all_visible_none_visible(self):
        m=calculate_metrics(self.ts,[True]*4,[False]*4,self.end)
        self.assertEqual((m["sun_visible_pct"],m["longest_darkness_hours"]),(100,0))
        self.assertEqual((m["earth_visible_pct"],m["longest_earth_blackout_hours"]),(0,4))

    def test_bad_order(self):
        with self.assertRaises(ValueError):
            extract_visibility_windows([self.ts[1],self.ts[0]],[True,False],self.end)

    def test_fit_statuses(self):
        m=calculate_metrics(self.ts,[True]*4,[True]*4,self.end)
        self.assertEqual(evaluate_fit(m)["status"],"both_met")
        self.assertEqual(evaluate_fit(m,{"min_earth_visible_pct":100,"max_earth_blackout_hours":0})["status"],"both_met")
        m["earth_visible_pct"]=40
        self.assertEqual(evaluate_fit(m)["status"],"comms_short")
        m["sun_visible_pct"]=30
        self.assertEqual(evaluate_fit(m)["status"],"neither_met")

if __name__ == "__main__": unittest.main()
