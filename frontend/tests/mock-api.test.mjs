import { test } from 'node:test';
import assert from 'node:assert/strict';
import { handleMockRequest } from '../src/mock/api.mjs';

const LANDING = '2027-08-01T06:00:00Z';
const BOUNDS = { window_start_utc: '2027-08-01T00:00:00Z', window_end_utc: '2027-08-04T00:00:00Z' };
const get = (path, params = {}, origin) => handleMockRequest({ url: `${path}?${new URLSearchParams(params)}`, origin });
const post = (path, body) => handleMockRequest({ method: 'POST', url: path, body });
const analysis = (params = {}, site = 'malapert_massif') => get('/sites', { site_id: site, ...BOUNDS, ...params });

test('mock catalogue and health preserve the contract and identify synthetic data', () => {
  const response = get('/sites');
  assert.equal(response.status, 200);
  assert.equal(response.headers['X-Moon-Flyers-Data-Source'], 'mock');
  assert.equal(response.body.length, 4);
  assert.equal(new Set(response.body.map(site => site.id)).size, 4);
  assert.ok(response.body.every(site => site.notes.includes('Synthetic demo')));
  assert.deepEqual(get('/health').body, { status: 'ok' });
});

test('mock batch covers the window plus stay with independent body positions and a flat horizon', () => {
  const response = analysis({ days_on_surface: 30, timestep_seconds: 3600 }, 'connecting_ridge');
  assert.equal(response.status, 200);
  const { timeseries: points, horizon, metrics } = response.body.analysis;
  assert.equal(points.length, (3 + 30) * 24 + 1);
  assert.equal(points[0].time_utc, BOUNDS.window_start_utc);
  assert.equal(points.at(-1).time_utc, '2027-09-03T00:00:00Z');
  assert.equal(horizon.horizon_azimuth_deg.length, 361);
  assert.ok(horizon.horizon_elevation_deg.every(el => el === 0));
  assert.ok(points.some(point => point.sun_azimuth_deg !== point.earth_azimuth_deg));
  assert.equal(new Set(points.map(point => point.sun_visible)).size, 2);
  assert.equal(metrics.slope_deg, null);
});

test('mock metrics match visibility intervals and include the exact endpoint for uneven steps', () => {
  const result = analysis({ days_on_surface: 3, timestep_seconds: 5000 }).body.analysis;
  assert.equal(result.timeseries.at(-1).time_utc, '2027-08-07T00:00:00Z');
  const duration = Date.parse(result.timeseries.at(-1).time_utc) - Date.parse(result.timeseries[0].time_utc);
  assert.equal(duration, (3 + 3) * 86_400_000);
  for (const [body, metric] of [['sun', 'sun_visible_pct'], ['earth', 'earth_visible_pct']]) {
    const visible = result.windows[body].reduce((sum, window) => sum + Date.parse(window.end_utc) - Date.parse(window.start_utc), 0);
    assert.ok(Math.abs(result.metrics[metric] - 100 * visible / duration) <= 0.005);
  }
  assert.deepEqual(analysis({ days_on_surface: 3 }), analysis({ days_on_surface: 3 }));
});

test('mock comparison preserves site order and matches selected-site analysis metrics and fit', () => {
  const refs = [{ id: 'de_gerlache_rim' }, { id: 'malapert_massif' }];
  const response = post('/compare', { ...BOUNDS, sites: refs, constraints: { days_on_surface: 3 } });
  assert.equal(response.status, 200);
  assert.deepEqual(response.body.map(row => row.site.id), refs.map(site => site.id));
  for (const row of response.body) {
    assert.equal(row.window_metrics.length, 3 * 4 + 1);
    for (const candidate of row.window_metrics) {
      // GET metrics cover its full requested batch; make that batch exactly one stay.
      const expected = analysis({ window_start_utc: candidate.landing_utc,
        window_end_utc: candidate.landing_utc, days_on_surface: 3 }, row.site.id).body.analysis;
      assert.deepEqual(candidate.metrics, expected.metrics);
      assert.deepEqual(candidate.fit, expected.fit);
    }
    const fullBatch = analysis({ days_on_surface: 3 }, row.site.id).body.analysis;
    assert.deepEqual(row.timeline, fullBatch.windows);
    for (const windows of Object.values(row.timeline)) {
      for (const window of windows) {
        assert.ok(window.start_utc >= BOUNDS.window_start_utc);
        assert.ok(window.end_utc <= '2027-08-07T00:00:00Z');
        assert.ok(window.start_utc < window.end_utc);
      }
    }
  }
});

test('default frontend window returns four varied mock comparisons and visibility bars', () => {
  const refs = get('/sites').body.map(site => ({ id: site.id }));
  const response = post('/compare', { sites: refs,
    window_start_utc: '2027-08-01T00:00:00Z', window_end_utc: '2027-10-31T00:00:00Z' });
  assert.equal(response.status, 200);
  assert.equal(response.body.length, 4);
  assert.ok(new Set(response.body.map(row => row.window_metrics[0].fit.status)).size > 1);
  assert.ok(response.body.every(row => row.window_metrics.length === 91 * 4 + 1));
  assert.ok(response.body.every(row => row.timeline.sun.length && row.timeline.earth.length));
});

test('mock constraints and landing dates change generated metrics and violations', () => {
  const baseline = analysis().body.analysis;
  const strict = analysis({ min_sun_visible_pct: 100, max_darkness_hours: 0,
    min_earth_visible_pct: 100, max_earth_blackout_hours: 0, horizon_clearance_deg: 90 }).body.analysis;
  assert.equal(strict.fit.status, 'neither_met');
  assert.equal(strict.fit.violations.length, 4);
  assert.equal(strict.metrics.sun_visible_pct, 0);
  assert.equal(strict.metrics.longest_darkness_hours, (3 + 14) * 24);
  const shifted = analysis({ window_start_utc: '2027-08-08T00:00:00Z', window_end_utc: '2027-08-11T00:00:00Z' }).body.analysis;
  assert.notDeepEqual(baseline.timeseries[0], shifted.timeseries[0]);
  assert.notDeepEqual(baseline.metrics, shifted.metrics);
});

test('mock visibility flags disable the respective time-series flags and windows', () => {
  const result = analysis({ sun_visibility: false, earth_visibility: false }).body.analysis;
  assert.deepEqual(result.windows, { sun: [], earth: [], eclipse: [] });
  assert.ok(result.timeseries.every(point => !point.sun_visible && !point.earth_visible));
  assert.equal(result.metrics.earth_visible_pct, 0);
});

test('mock custom sites work across endpoints and are never stored in the catalogue', () => {
  const custom = { name: 'Test ridge', latitude_deg: -89.2, longitude_deg: 45 };
  const response = get('/sites', { ...custom, ...BOUNDS });
  assert.equal(response.status, 200);
  assert.ok(response.body.id.startsWith('custom_'));
  const comparison = post('/compare', { ...BOUNDS, sites: [custom] });
  assert.equal(comparison.status, 200);
  assert.equal(comparison.body[0].site.id, response.body.id);
  assert.deepEqual(comparison.body[0].timeline, response.body.analysis.windows);
  const candidate = comparison.body[0].window_metrics[0];
  const stay = get('/sites', { ...custom, window_start_utc: candidate.landing_utc,
    window_end_utc: candidate.landing_utc }).body.analysis;
  assert.deepEqual(candidate.metrics, stay.metrics);
  assert.equal(get('/sites').body.length, 4);
});

test('mock landing windows are ranked, limited, reproducible, and consistent with analysis', () => {
  const body = { ...BOUNDS, site: { id: 'de_gerlache_rim' }, limit: 5 };
  const response = post('/landing-windows', body);
  assert.equal(response.status, 200);
  const rows = response.body;
  assert.deepEqual(rows.map(row => row.rank), [1, 2, 3, 4, 5]);
  for (let i = 0; i < rows.length; i++) {
    const row = rows[i];
    assert.ok(row.landing_utc >= BOUNDS.window_start_utc && row.landing_utc <= BOUNDS.window_end_utc);
    assert.deepEqual(analysis({ window_start_utc: row.landing_utc, window_end_utc: row.landing_utc }, 'de_gerlache_rim').body.analysis.metrics, row.metrics);
    const previous = rows[i - 1];
    if (previous) {
      assert.ok(previous.fit.violations.length < row.fit.violations.length
        || (previous.fit.violations.length === row.fit.violations.length
          && (previous.metrics.sun_visible_pct > row.metrics.sun_visible_pct
            || (previous.metrics.sun_visible_pct === row.metrics.sun_visible_pct
              && previous.metrics.earth_visible_pct >= row.metrics.earth_visible_pct))));
    }
  }
  assert.deepEqual(rows, post('/landing-windows', body).body);
});

test('invalid mock requests return contract-shaped 404/422 errors', () => {
  assert.equal(analysis({}, 'unknown').status, 404);
  for (const params of [{ days_on_surface: 0 }, { timestep_seconds: 0 }, { min_sun_visible_pct: 101 },
    { horizon_clearance_deg: -1 }, { sun_visibility: 'invalid' }, { days_on_surface: 30, timestep_seconds: 1 }]) {
    const response = analysis(params);
    assert.equal(response.status, 422);
    assert.ok(response.body.detail);
  }
  for (const params of [{ site_id: 'malapert_massif' }, { ...BOUNDS, name: 'incomplete' },
    { ...BOUNDS, site_id: 'malapert_massif', window_start_utc: '2027-08-01T06:00:00' }]) {
    assert.equal(get('/sites', params).status, 422);
  }
  assert.equal(post('/landing-windows', { ...BOUNDS, window_end_utc: '2027-07-01T00:00:00Z', site: { id: 'malapert_massif' } }).status, 422);
  assert.equal(post('/compare', { ...BOUNDS, sites: [] }).status, 422);
  assert.equal(post('/compare', { ...BOUNDS, sites: [{ id: 'malapert_massif' }], constraints: { unexpected_field: 1 } }).status, 422);
});

test('mock normalizes UTC offsets and exposes its source header through CORS', () => {
  const response = get('/sites', { ...BOUNDS, site_id: 'malapert_massif', window_start_utc: '2027-08-01T08:00:00+02:00' }, 'http://localhost:5173');
  assert.equal(response.body.analysis.timeseries[0].time_utc, LANDING);
  assert.equal(response.headers['Access-Control-Allow-Origin'], 'http://localhost:5173');
  assert.ok(response.headers['Access-Control-Expose-Headers'].includes('X-Moon-Flyers-Data-Source'));
  const preflight = handleMockRequest({ method: 'OPTIONS', url: '/compare', origin: 'http://127.0.0.1:5173' });
  assert.equal(preflight.status, 200);
  assert.equal(preflight.headers['Access-Control-Allow-Origin'], 'http://127.0.0.1:5173');
});
