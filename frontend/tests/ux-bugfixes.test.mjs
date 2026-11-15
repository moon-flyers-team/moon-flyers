import { before, after, test } from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { createServer } from 'vite';
import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';

let server, cacheDir, fitCamera, ComparisonTable, SettingsModal, TouristRoutePanel, api, siteReference;
before(async () => {
  cacheDir = await mkdtemp(join(tmpdir(), 'moon-ux-'));
  server = await createServer({ cacheDir, optimizeDeps: { noDiscovery: true, include: [] },
    server: { middlewareMode: true, watch: null, hmr: false, ws: false }, appType: 'custom' });
  ({ fitCamera, TouristRoutePanel } = await server.ssrLoadModule('/src/TouristRoutePanel.tsx'));
  ({ ComparisonTable } = await server.ssrLoadModule('/src/ComparisonTable.tsx'));
  ({ SettingsModal } = await server.ssrLoadModule('/src/App.tsx'));
  ({ api, siteReference } = await server.ssrLoadModule('/src/api.ts'));
});
after(async () => { await server?.close(); if (cacheDir) await rm(cacheDir, { recursive: true, force: true }); });

const site = { id: 'landing', name: 'Landing', latitude_deg: -89, longitude_deg: 0, enabled: true };
const mission = { windowStart: '2027-08-01', windowEnd: '2027-08-10', daysOnSurface: 3, horizonClearance: 0.3, poiRadiusKm: 12.5 };
const power = { minSunlight: 60, maxNight: 96 }, comms = { minEarthContact: 45, maxCommsGap: 240 }, terrain = { maxSlope: 8 };

test('route Fit preserves padding inside the cropped viewport in wide and tall layouts', () => {
  const pts = [{ x: 450, y: 450 }, { x: 550, y: 550 }, { x: 475, y: 420 }];
  for (const [width, height] of [[1000, 380], [320, 620], [600, 600]]) {
    const c = fitCamera(pts, width, height);
    const half = 350 / c.zoom;
    for (const p of pts) {
      assert.ok(Math.abs(p.x - c.x) * 1.4 <= half * width / Math.max(width, height));
      assert.ok(Math.abs(p.y - c.y) * 1.4 <= half * height / Math.max(width, height));
    }
  }
  assert.equal(fitCamera([pts[0], pts[0]]).zoom, 16);
});

test('timeline green marker follows each sampled mission fit, not instantaneous visibility', () => {
  const landingTime = '2027-08-01T00:00:00Z';
  const metrics = { sun_visible_pct: 20, earth_visible_pct: 20, longest_darkness_hours: 100, longest_earth_blackout_hours: 300, slope_deg: null };
  const window = { start_utc: landingTime, end_utc: '2027-08-10T00:00:00Z' };
  const props = { sites: [site], selectedId: site.id, onSelect() {}, onTimeSeek() {}, onRetry() {},
    missionStart: landingTime, sliderEnd: window.end_utc, landingTime, loading: false,
    constraints: { days_on_surface: 3 },
  };
  const render = (fit, timeline, sampled = true) => renderToStaticMarkup(React.createElement(ComparisonTable, {
    ...props, results: [{ site, window_metrics: sampled ? [{ landing_utc: '2027-08-01T00:00:00.000Z', metrics, fit }] : [], timeline }],
  }));
  const failed = { status: 'neither_met', violations: ['sun_visible_pct'] };
  assert.doesNotMatch(render(failed, { sun: [window], earth: [window] }), /tl-marker--both/);
  assert.match(render({ status: 'both_met', violations: [] }, { sun: [], earth: [] }), /tl-marker--both/);
  assert.doesNotMatch(render(failed, { sun: [window], earth: [window] }, false), /tl-marker--both/);
});

test('mission radius is editable, validated, and shown on the explicit POI search action', () => {
  const render = poiRadiusKm => renderToStaticMarkup(React.createElement(SettingsModal, {
    mission: { ...mission, poiRadiusKm }, power, comms, terrain,
    onMissionChange() {}, onPowerChange() {}, onCommsChange() {}, onTerrainChange() {}, onClose() {}, onCompare() {},
  }));
  assert.match(render(12.5), /Search radius/);
  assert.match(render(12.5), /value="12.5"/);
  for (const invalid of [0, -1, Infinity]) {
    assert.match(render(invalid), /Search radius must be greater than zero/);
    assert.match(render(invalid), /disabled=""[^>]*>SET MISSION/);
  }
  const html = renderToStaticMarkup(React.createElement(TouristRoutePanel, {
    landingSite: site, landingUtc: '2027-08-01T00:00:00Z', poiRadiusKm: 12.5, onClose() {},
  }));
  assert.match(html, /Find nearby POIs \(12.5 km\)/);
});

test('POI client sends only landing reference and optional radius, preserving abort signal', async () => {
  const original = globalThis.fetch;
  const calls = [];
  globalThis.fetch = async (url, init) => { calls.push({ url, init }); return new Response('{}'); };
  try {
    const signal = new AbortController().signal;
    await api.getRecommendedSites({ site: siteReference({ ...site, custom: true }), radius_km: 12.5 }, signal);
    assert.match(calls[0].url, /\/recommended-sites$/);
    assert.deepEqual(JSON.parse(calls[0].init.body), { site: { name: site.name, latitude_deg: -89, longitude_deg: 0 }, radius_km: 12.5 });
    assert.equal(calls[0].init.signal, signal);
    await api.getRecommendedSites({ site: { id: site.id } });
    assert.deepEqual(JSON.parse(calls[1].init.body), { site: { id: site.id } });
  } finally { globalThis.fetch = original; }
});
