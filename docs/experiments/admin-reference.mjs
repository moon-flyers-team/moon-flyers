// Administrator-only cross-check. Never expose this script or its output to a participant.
// Requires the explicitly synthetic standalone mock; does not query NASA or validate physics.
import { writeFile } from 'node:fs/promises';
const base = process.env.MOCK_REFERENCE_URL || 'http://127.0.0.1:8000';
const request = {
  sites: [{ id: 'connecting_ridge' }, { id: 'malapert_massif' },
    { name: 'Survey Ridge', latitude_deg: -89.2, longitude_deg: 45 }],
  window_start_utc: '2027-08-01T00:00:00Z', window_end_utc: '2027-08-10T00:00:00Z',
  constraints: { days_on_surface: 3, horizon_clearance_deg: 0.3,
    min_sun_visible_pct: 60, max_darkness_hours: 96, min_earth_visible_pct: 45,
    max_earth_blackout_hours: 240, max_slope_deg: 8 },
  candidate_step_hours: 6, timestep_seconds: 3600,
};
const response = await fetch(`${base}/compare`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(request) });
if (!response.ok || response.headers.get('X-Moon-Flyers-Data-Source') !== 'mock') throw new Error('An explicitly synthetic mock response is required');
const rows = await response.json();
const times = ['2027-08-07T06:00:00Z','2027-08-08T06:00:00Z'];
const reference = {
  status: 'Administrator synthetic cross-check only, not scientific ground truth', request,
  rows: rows.map(row => ({ site: row.site,
    candidates: times.map(time => {
      const candidate = row.window_metrics.find(item => Date.parse(item.landing_utc) === Date.parse(time));
      if (!candidate) throw new Error(`Missing candidate ${time}`);
      return candidate;
    }),
  })),
};
await writeFile(new URL('./admin-reference.json', import.meta.url), JSON.stringify(reference, null, 2) + '\n');
console.log('Wrote synthetic administrator reference for 7/8 August; never scientific ground truth.');
