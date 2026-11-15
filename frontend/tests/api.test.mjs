import { test, before, after, afterEach } from 'node:test';
import assert from 'node:assert/strict';
import { createServer } from 'vite';
import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';

let server, api, TimelineBars, normalise, HorizonChart, skyPath, ComparisonTable;
const originalFetch = globalThis.fetch;
const constraints = {
  days_on_surface: 14, horizon_clearance_deg: 0.3, min_sun_visible_pct: 60,
  max_darkness_hours: 96, min_earth_visible_pct: 45,
  max_earth_blackout_hours: 240, max_slope_deg: 8,
};
const landing = '2027-08-07T06:00:00Z';
const site = { id: 'malapert_massif', name: 'Malapert massif', latitude_deg: -86, longitude_deg: 0 };
const metrics = { sun_visible_pct: 89, longest_darkness_hours: 36, earth_visible_pct: 20, longest_earth_blackout_hours: 250, slope_deg: null };
const fit = { status: 'comms_short', violations: ['earth_visible_pct', 'longest_earth_blackout_hours'] };
const windows = { sun: [{ start_utc: landing, end_utc: '2027-08-08T06:00:00Z' }], earth: [] };
const point = (time, az = 5, elevation = 1, visible = false) => ({
  time_utc: time, sun_azimuth_deg: az, sun_elevation_deg: elevation, sun_visible: visible,
  earth_azimuth_deg: 358, earth_elevation_deg: 3.7, earth_visible: true,
});

before(async () => {
  server = await createServer({ optimizeDeps: { noDiscovery: true, include: [] },
    server: { middlewareMode: true, watch: null, hmr: false, ws: false }, appType: 'custom' });
  ({ api } = await server.ssrLoadModule('/src/api.ts'));
  ({ TimelineBars, normalise } = await server.ssrLoadModule('/src/TimelineBars.tsx'));
  ({ HorizonChart, skyPath } = await server.ssrLoadModule('/src/HorizonChart.tsx'));
  ({ ComparisonTable } = await server.ssrLoadModule('/src/ComparisonTable.tsx'));
});
afterEach(() => { globalThis.fetch = originalFetch; });
after(async () => { await server?.close(); });
function capture(response = {}) {
  const calls = [];
  globalThis.fetch = async (url, init = {}) => {
    calls.push({ url: new URL(url, 'http://frontend.test'), init });
    return new Response(JSON.stringify(response), { status: 200 });
  };
  return calls;
}

test('catalogue and health use parameter-free GET requests', async () => {
  const calls = capture([site]);
  assert.deepEqual(await api.getSites(), [site]);
  await api.health();
  assert.match(calls[0].url.pathname, /\/sites$/);
  assert.equal(calls[0].url.search, '');
  assert.match(calls[1].url.pathname, /\/health$/);
  assert.equal(calls[0].init.method, undefined);
});

test('catalogue metadata identifies a mock server without changing the site response format', async () => {
  globalThis.fetch = async () => new Response(JSON.stringify([site]), {
    headers: { 'X-Moon-Flyers-Data-Source': 'mock' },
  });
  assert.deepEqual(await api.getCatalogue(), { sites: [site], isMock: true });
  capture([site]);
  assert.deepEqual(await api.getCatalogue(), { sites: [site], isMock: false });
});

test('site analysis serializes every constraint and requests a whole lunar day in one batch', async () => {
  const calls = capture({ ...site, analysis: {} });
  const signal = new AbortController().signal;
  await api.getSiteAnalysis({ site: { id: site.id }, landing_utc: landing,
    constraints: { ...constraints, days_on_surface: 30 } }, signal);
  const { url, init } = calls[0];
  assert.match(url.pathname, /\/sites$/);
  assert.equal(url.searchParams.get('site_id'), site.id);
  assert.equal(url.searchParams.get('landing_utc'), landing);
  for (const [key, value] of Object.entries({ ...constraints, days_on_surface: 30 })) {
    assert.equal(url.searchParams.get(key), String(value));
  }
  assert.equal(url.searchParams.get('timestep_seconds'), '3600');
  assert.equal(url.searchParams.get('sun_visibility'), 'true');
  assert.equal(url.searchParams.get('earth_visibility'), 'true');
  assert.equal(url.searchParams.has('id'), false);
  assert.equal(url.searchParams.has('constraints'), false);
  assert.equal(init.signal, signal);
});

test('custom site analysis sends coordinates and explicit visibility flags', async () => {
  const calls = capture();
  await api.getSiteAnalysis({ site: { name: 'My site & ridge', latitude_deg: -89.2, longitude_deg: 45 },
    landing_utc: landing, constraints, timestep_seconds: 1800, sun_visibility: false, earth_visibility: false });
  const q = calls[0].url.searchParams;
  assert.equal(q.has('site_id'), false);
  assert.equal(q.get('name'), 'My site & ridge');
  assert.equal(q.get('latitude_deg'), '-89.2');
  assert.equal(q.get('longitude_deg'), '45');
  assert.equal(q.get('sun_visibility'), 'false');
  assert.equal(q.get('earth_visibility'), 'false');
  assert.equal(q.get('timestep_seconds'), '1800');
});

test('comparison POST preserves mission duration and UTC boundaries', async () => {
  const calls = capture([{ site, metrics, fit, timeline: windows }]);
  const params = { sites: [{ id: site.id }, { name: 'Custom', latitude_deg: -89, longitude_deg: 45 }],
    landing_utc: landing, window_start_utc: '2027-08-01T00:00:00Z',
    window_end_utc: '2027-10-31T00:00:00Z', constraints };
  const result = await api.compare(params);
  assert.equal(calls[0].init.method, 'POST');
  assert.match(calls[0].url.pathname, /\/compare$/);
  assert.equal(calls[0].init.headers['Content-Type'], 'application/json');
  assert.deepEqual(JSON.parse(calls[0].init.body), { timestep_seconds: 3600, ...params });
  assert.equal(result[0].metrics.slope_deg, null);
});

test('landing-window POST uses one site, six-hour candidates and a five-result limit', async () => {
  const calls = capture([]);
  const params = { site: { id: site.id }, window_start_utc: '2027-08-01T00:00:00Z',
    window_end_utc: '2027-10-31T00:00:00Z', constraints };
  await api.getLandingWindows(params);
  assert.match(calls[0].url.pathname, /\/landing-windows$/);
  assert.equal(calls[0].init.method, 'POST');
  assert.deepEqual(JSON.parse(calls[0].init.body), { candidate_step_hours: 6, limit: 5, ...params });
});

test('FastAPI validation details and non-JSON failures reach the UI', async () => {
  globalThis.fetch = async () => new Response(JSON.stringify({ detail: [{ loc: ['body', 'sites'], msg: 'Required' }] }), { status: 422 });
  await assert.rejects(api.getSites(), /422.*Required/);
  globalThis.fetch = async () => new Response('Bad Gateway', { status: 502, statusText: 'Bad Gateway' });
  await assert.rejects(api.getSites(), /502 Bad Gateway/);
});

test('requests propagate aborts for obsolete analyses', async () => {
  globalThis.fetch = async (_url, { signal }) => {
    signal.throwIfAborted();
    return new Response('{}');
  };
  const controller = new AbortController();
  controller.abort();
  await assert.rejects(api.getSiteAnalysis({ site: { id: site.id }, landing_utc: landing, constraints }, controller.signal), { name: 'AbortError' });
});

test('timeline intervals clip to the displayed window, ignoring invalid or reversed ranges', () => {
  const range = [
    { start_utc: '2027-07-31T00:00:00Z', end_utc: '2027-08-02T00:00:00Z' },
    { start_utc: '2027-08-03T00:00:00Z', end_utc: '2027-08-10T00:00:00Z' },
    { start_utc: '2027-08-05T00:00:00Z', end_utc: '2027-08-06T00:00:00Z' },
    { start_utc: 'bad', end_utc: landing },
    { start_utc: landing, end_utc: '2027-08-01T00:00:00Z' },
  ];
  const result = normalise(range, '2027-08-01T00:00:00Z', '2027-08-05T00:00:00Z');
  assert.deepEqual(result.map(({ left, width }) => ({ left, width })), [{ left: 0, width: 0.25 }, { left: 0.5, width: 0.5 }]);
  assert.deepEqual(normalise(range, landing, landing), []);
  const html = renderToStaticMarkup(React.createElement(TimelineBars, { powerWindows: [], commsWindows: [], missionStart: landing, missionEnd: landing }));
  assert.doesNotMatch(html, /NaN|Infinity/);
});

test('comparison renders API fit and communication violations, with null slope as a dash', () => {
  const html = renderToStaticMarkup(React.createElement(ComparisonTable, {
    sites: [{ ...site, enabled: true }], results: [{ site, metrics, fit, timeline: windows }], constraints,
    selectedId: site.id, onSelect() {}, landingTime: landing, onTimeShift() {},
    canShiftBack: true, canShiftForward: true, missionStart: landing, missionEnd: '2027-11-14T00:00:00Z', loading: false, onRetry() {},
  }));
  assert.match(html, /Comms short/);
  assert.match(html, /class="warn"[^>]*>.*20%/);
  assert.match(html, /class="warn"[^>]*>.*250 h/);
  assert.match(html, /<td class="">—<\/td>/);
});

test('horizon shows the first lunar-day sample rather than maxima without slider controls', () => {
  const timeseries = [point('2027-08-08T06:00:00Z', 15, 8, true), point(landing),
    point('2027-09-06T06:00:00Z', 300, 9, true), point('2027-08-06T06:00:00Z')];
  const props = { siteName: site.name, landingUtc: landing, loading: false, onRetry() {},
    analysis: { timeseries, horizon: { horizon_azimuth_deg: [0, 180, 360], horizon_elevation_deg: [0, 0, 0] }, metrics, fit, windows } };
  const calls = capture();
  const html = renderToStaticMarkup(React.createElement(HorizonChart, props));
  assert.match(html, /Sun visible · 1.0°/);
  assert.match(html, /Earth visible · 3.7°/);
  assert.doesNotMatch(html, /type="range"/);
  assert.match(html, /2027-08-07 06:00 UTC/);
  assert.equal(calls.length, 0, 'visualization consumes data without fetching');
});

test('horizon altitude scale stays fixed across the full site batch when scrubbing', () => {
  const timeseries = [point('2027-08-06T06:00:00Z', 0, -30), point(landing),
    point('2027-09-06T06:00:00Z', 300, 1), point('2027-10-07T06:00:00Z', 200, 45)];
  const props = { siteName: site.name, landingUtc: landing, loading: false, onRetry() {},
    analysis: { timeseries, horizon: { horizon_azimuth_deg: [0, 180, 360],
      horizon_elevation_deg: [0, 50, 0] }, metrics, fit, windows } };
  const render = landingUtc => renderToStaticMarkup(React.createElement(HorizonChart, { ...props, landingUtc }));
  const early = render(landing), late = render('2027-09-06T06:00:00Z');
  const ticks = html => html.match(/<text[^>]*>-?\d+\.\d°<\/text>/g);
  assert.equal(ticks(early)?.length, 6);
  assert.deepEqual(ticks(early), ticks(late));
  assert.match(early, />-31.0°<\/text>/);
  assert.match(early, />51.0°<\/text>/, 'terrain outside the body range also fits the scale');
  const terrainPath = html => html.match(/<path[^>]*fill="#303040"[^>]*>/)?.[0];
  assert.ok(terrainPath(early));
  assert.equal(terrainPath(early), terrainPath(late));
});

test('horizon distinguishes loading, empty samples and backend failures', () => {
  const props = { siteName: site.name, landingUtc: landing, loading: true, onRetry() {} };
  assert.match(renderToStaticMarkup(React.createElement(HorizonChart, props)), /Loading a lunar day/);
  assert.match(renderToStaticMarkup(React.createElement(HorizonChart, { ...props, loading: false, error: '404 Not Found' })), /Retry horizon/);
  const empty = { timeseries: [], horizon: { horizon_azimuth_deg: [], horizon_elevation_deg: [] }, metrics, fit, windows };
  const html = renderToStaticMarkup(React.createElement(HorizonChart, { ...props, loading: false, analysis: empty }));
  assert.match(html, /No time samples returned/);
  assert.doesNotMatch(html, /NaN|Infinity/);
});

test('sky paths break at north independently for Sun and Earth', () => {
  const data = [point(landing, 359), point('2027-08-07T07:00:00Z', 1)];
  assert.equal((skyPath(data, 'sun', el => el).match(/M /g) ?? []).length, 2);
  assert.equal((skyPath(data, 'earth', el => el).match(/M /g) ?? []).length, 1);
});
