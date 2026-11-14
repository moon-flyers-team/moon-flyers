// Requires the mock API on :8000 and the frontend dev server on :5173.
// These are real HTTP requests through Vite, with no fetch stubs.
import assert from 'node:assert/strict';
import { createServer } from 'vite';
import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';

const nativeFetch = globalThis.fetch;
const server = await createServer({
  define: { 'import.meta.env.VITE_API_URL': JSON.stringify('/api') },
  server: { middlewareMode: true, watch: null, hmr: false, ws: false },
  appType: 'custom',
});
globalThis.fetch = (url, init) => nativeFetch(new URL(url, 'http://localhost:5173'), init);
try {
  const { api } = await server.ssrLoadModule('/src/api.ts');
  const { HorizonChart } = await server.ssrLoadModule('/src/HorizonChart.tsx');
  const { ComparisonTable } = await server.ssrLoadModule('/src/ComparisonTable.tsx');
  const catalogue = await api.getCatalogue();
  assert.equal(catalogue.isMock, true, 'Run pnpm mock:api before this check');
  assert.equal(catalogue.sites.length, 4);
  console.log('PASS: Vite proxy → mock catalogue → frontend client; mock header recognized');

  const constraints = { days_on_surface: 14, horizon_clearance_deg: 0.3,
    min_sun_visible_pct: 60, max_darkness_hours: 96, min_earth_visible_pct: 45,
    max_earth_blackout_hours: 240, max_slope_deg: 8 };
  const landing = '2027-08-01T06:00:00Z';
  const bounds = { window_start_utc: '2027-08-01T00:00:00Z', window_end_utc: '2027-10-31T00:00:00Z' };
  const refs = catalogue.sites.map(site => ({ id: site.id }));
  const rows = await api.compare({ ...bounds, sites: refs, landing_utc: landing, constraints });
  assert.deepEqual(rows.map(row => row.site.id), refs.map(site => site.id));
  const table = renderToStaticMarkup(React.createElement(ComparisonTable, {
    sites: catalogue.sites.map(site => ({ ...site, enabled: true })), results: rows, constraints,
    selectedId: refs[0].id, onSelect() {}, landingTime: landing, onTimeShift() {},
    canShiftBack: true, canShiftForward: true, missionStart: bounds.window_start_utc,
    missionEnd: '2027-11-14T00:00:00Z', loading: false, onRetry() {},
  }));
  for (const site of catalogue.sites) assert.ok(table.includes(site.name));
  assert.match(table, /tl-seg--power/);
  assert.match(table, /tl-seg--comms/);
  console.log('PASS: real comparison response renders four sites, fit badges, and visibility bars');

  const response = await api.getSiteAnalysis({ site: refs[0], landing_utc: landing,
    constraints: { ...constraints, days_on_surface: 30 } });
  assert.equal(response.analysis.timeseries.length, 721);
  const chart = renderToStaticMarkup(React.createElement(HorizonChart, {
    siteName: response.name, analysis: response.analysis, landingUtc: landing, loading: false, onRetry() {},
  }));
  assert.match(chart, /<svg/);
  assert.match(chart, /2027-08-01 06:00 UTC/);
  assert.doesNotMatch(chart, /NaN|Infinity/);
  console.log('PASS: 721 hourly samples from the mock render the lunar-day horizon');

  const best = await api.getLandingWindows({ ...bounds, site: refs[0], constraints });
  assert.equal(best.length, 5);
  assert.deepEqual(best.map(row => row.rank), [1, 2, 3, 4, 5]);
  const selected = await api.compare({ ...bounds, sites: [refs[0]], landing_utc: best[0].landing_utc, constraints });
  assert.deepEqual(selected[0].metrics, best[0].metrics);
  assert.deepEqual(selected[0].fit, best[0].fit);
  console.log('PASS: best-time search and applying its landing time produce matching comparison results');
  console.log('Live mock pipeline passed. Refresh http://localhost:5173 to explore the UI.');
} finally {
  globalThis.fetch = nativeFetch;
  await server.close();
}
