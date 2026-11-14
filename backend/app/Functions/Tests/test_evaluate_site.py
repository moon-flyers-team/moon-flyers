import unittest
from physics.evaluate_site import evaluate_site

TS = ['2027-08-01T00:00:00Z','2027-08-01T06:00:00Z',
      '2027-08-01T12:00:00Z','2027-08-01T18:00:00Z']
H = {'horizon_azimuth_deg':[0,90,180,270], 'horizon_elevation_deg':[0,0,0,0]}
E = {'timestamps_utc': TS,
     'sun_azimuth_deg':[45]*4, 'sun_elevation_deg':[2,2,-2,-2],
     'sun_angular_radius_deg':0.25,
     'earth_azimuth_deg':[80]*4, 'earth_elevation_deg':[3]*4,
     'earth_angular_radius_deg':1.0}

class EvalSiteTests(unittest.TestCase):
    def test_evaluation(self):
        result = evaluate_site(E,H,TS[0],1,{'horizon_clearance_deg':0.3})
        self.assertEqual(len(result['timeseries']),4)
        self.assertAlmostEqual(result['metrics']['sun_visible_pct'],34.0625)
        self.assertAlmostEqual(result['metrics']['longest_darkness_hours'],15.825)
        self.assertEqual(result['metrics']['earth_visible_pct'],100)
        self.assertEqual(result['metrics']['initial_sunlight_hours'],8.175)
        self.assertEqual(result['metrics']['initial_earth_visibility_hours'],24)
        self.assertEqual(result['fit']['status'],'power_short')
        self.assertEqual(len(result['windows']['sun']),1)
    def test_disabled_body(self):
        e={k:v for k,v in E.items() if not k.startswith('earth_')}
        result=evaluate_site(e,H,TS[0],1,sun_visibility=True,earth_visibility=False)
        self.assertIsNone(result['fit'])
        self.assertIsNone(result['metrics']['earth_visible_pct'])
        self.assertNotIn('earth_visible',result['timeseries'][0])
    def test_rejects_coverage_error(self):
        with self.assertRaises(ValueError):
            evaluate_site(E,H,'2027-07-31T00:00:00Z',1)
        with self.assertRaises(ValueError):
            evaluate_site(E,H,TS[0],0.5)
    def test_initial_constraint(self):
        r=evaluate_site(E,H,TS[0],1, {'min_initial_sunlight_hours':10})
        self.assertIn('initial_sunlight_hours',r['fit']['violations'])

if __name__=='__main__':
    unittest.main()
