import { before, after, test } from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { createServer } from 'vite';
import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';

let server, cacheDir, HorizonChart;
before(async () => {
  cacheDir = await mkdtemp(join(tmpdir(), 'moon-flyers-provenance-'));
  server = await createServer({ cacheDir, optimizeDeps: { noDiscovery: true, include: [] },
    server: { middlewareMode: true, watch: null, hmr: false, ws: false }, appType: 'custom' });
  ({ HorizonChart } = await server.ssrLoadModule('/src/HorizonChart.tsx'));
});
after(async () => { await server?.close(); if (cacheDir) await rm(cacheDir, { recursive: true, force: true }); });

test('flat and nonflat backend profiles do not claim verified or universally flat terrain', () => {
  for (const horizon_elevation_deg of [[0, 0, 0], [-1, 2, -1]]) for (const sunVisible of [true, false]) {
    const html = renderToStaticMarkup(React.createElement(HorizonChart, {
      siteName: 'Test site', landingUtc: '2027-08-01T00:00:00Z', loading: false, onRetry() {},
      analysis: {
        timeseries: [{ time_utc: '2027-08-01T00:00:00Z', sun_azimuth_deg: 20,
          sun_elevation_deg: 2, sun_visible: sunVisible, earth_azimuth_deg: 100,
          earth_elevation_deg: 3, earth_visible: !sunVisible }],
        horizon: { horizon_azimuth_deg: [0, 180, 360], horizon_elevation_deg },
        windows: { sun: [], earth: [], eclipse: [] },
        metrics: { sun_visible_pct: 100, longest_darkness_hours: 0, earth_visible_pct: 100,
          longest_earth_blackout_hours: 0, slope_deg: null },
        fit: { status: 'both_met', violations: [] },
      },
    }));
    assert.ok(html.includes(`Sun ${sunVisible ? 'visible' : 'not visible'} · 2.0°`));
    assert.ok(html.includes(`Earth ${sunVisible ? 'not visible' : 'visible'} · 3.0°`));
    assert.match(html, /Eclipse intervals/);
    assert.match(html, /Backend horizon/);
    assert.match(html, /terrain source not reported/);
    assert.match(html, /slope not assessed/);
    assert.doesNotMatch(html, /API v0: flat|verified terrain|NaN|Infinity/);
  }
});
