// Requires the mock API on :8000 and the frontend dev server on :5173.
// These are real HTTP requests through Vite, with no fetch stubs.
import assert from 'node:assert/strict';
import { createServer } from 'vite';
import { mkdtemp, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';

const nativeFetch = globalThis.fetch;
const frontendUrl = process.env.FRONTEND_TEST_URL || 'http://localhost:5173';
const cacheDir = await mkdtemp(join(tmpdir(), 'moon-flyers-pipeline-'));
const server = await createServer({
  cacheDir, optimizeDeps: { noDiscovery: true, include: [] },
  define: { 'import.meta.env.VITE_API_URL': JSON.stringify('/api') },
  server: { middlewareMode: true, watch: null, hmr: false, ws: false },
  appType: 'custom',
});
globalThis.fetch = (url, init) => nativeFetch(new URL(url, frontendUrl), init);
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
  const rows = await api.compare({ ...bounds, sites: refs, constraints, candidate_step_hours: 6 });
  assert.ok(rows.every(row => row.window_metrics.length === 91 * 4 + 1));
  assert.deepEqual(rows.map(row => row.site.id), refs.map(site => site.id));
  const table = renderToStaticMarkup(React.createElement(ComparisonTable, {
    sites: catalogue.sites.map(site => ({ ...site, enabled: true })), results: rows, constraints,
    selectedId: refs[0].id, onSelect() {}, landingTime: landing, onTimeSeek() {},
    missionStart: bounds.window_start_utc, sliderEnd: bounds.window_end_utc,
    loading: false, onRetry() {},
  }));
  for (const site of catalogue.sites) assert.ok(table.includes(site.name));
  assert.match(table, /tl-seg--power/);
  assert.match(table, /tl-seg--comms/);
  console.log('PASS: real comparison response renders four sites, fit badges, and visibility bars');

  const response = await api.getSiteAnalysis({ site: refs[0], ...bounds, constraints });
  assert.equal(response.analysis.timeseries.length, (91 + constraints.days_on_surface) * 24 + 1);
  assert.equal(response.analysis.timeseries[0].time_utc, bounds.window_start_utc);
  assert.equal(response.analysis.timeseries.at(-1).time_utc, '2027-11-14T00:00:00Z');
  const chart = renderToStaticMarkup(React.createElement(HorizonChart, {
    siteName: response.name, analysis: response.analysis, landingUtc: landing, loading: false, onRetry() {},
  }));
  assert.match(chart, /<svg/);
  assert.match(chart, /2027-08-01 06:00 UTC/);
  assert.doesNotMatch(chart, /NaN|Infinity/);
  console.log('PASS: full window-plus-stay batch renders the selected lunar-day horizon');

  const best = await api.getLandingWindows({ ...bounds, site: refs[0], constraints });
  assert.equal(best.length, 5);
  assert.deepEqual(best.map(row => row.rank), [1, 2, 3, 4, 5]);
  const selected = rows[0].window_metrics.find(row => Date.parse(row.landing_utc) === Date.parse(best[0].landing_utc));
  assert.ok(selected, 'ranked candidate must be present in the comparison grid');
  assert.deepEqual(selected.metrics, best[0].metrics);
  assert.deepEqual(selected.fit, best[0].fit);

  const custom = { name: 'Pipeline custom ridge', latitude_deg: -89.2, longitude_deg: 45 };
  const customRows = await api.compare({ ...bounds, sites: [custom], constraints });
  const customDetail = await api.getSiteAnalysis({ ...bounds, site: custom, constraints });
  assert.equal(customRows[0].site.id, customDetail.id);
  assert.deepEqual(customRows[0].timeline, customDetail.analysis.windows);
  assert.equal((await api.getSites()).length, 4, 'custom sites must not persist in the catalogue');
  console.log('PASS: custom coordinates produce consistent comparison/detail without persistence');
  console.log('PASS: best-time search and applying its landing time produce matching comparison results');
  console.log(`Live mock pipeline passed through ${frontendUrl}.`);
} finally {
  globalThis.fetch = nativeFetch;
  await server.close();
  await rm(cacheDir, { recursive: true, force: true });
}
