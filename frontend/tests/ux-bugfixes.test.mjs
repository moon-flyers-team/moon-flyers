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

const stopCheck = (index, extra = {}) => ({
  index, latitude_deg: -89, longitude_deg: 0, elevation_m: 100, terrain_slope_deg: 3,
  max_slope_deg: 20, passable: true, blocked_reasons: [], nearby_terrain_candidates: [], ...extra,
});
const steepCheck = (index, candidates) => stopCheck(index, {
  terrain_slope_deg: 21.4, passable: false, blocked_reasons: ['terrain_slope_exceeds_limit'],
  nearby_terrain_candidates: candidates,
});
const candidate = (offset_m, slope, lat = -89.01, lon = 0.02) => ({
  grid_cell: [0, 0], latitude_deg: lat, longitude_deg: lon, elevation_m: 120,
  terrain_slope_deg: slope, offset_m,
});

test('an impractical stop is described before a route is calculated', async () => {
  const { stopChipText, stopChipTitle, snapTarget } = await server.ssrLoadModule('/src/TouristRoutePanel.tsx');
  assert.equal(stopChipText(stopCheck(1)), 'Slope 3°');
  assert.equal(stopChipText(steepCheck(1, [candidate(120, 2)])), 'Not practical · 21°');
  assert.match(stopChipTitle(steepCheck(1, [])), /Not practical for a 20° rover: terrain is steeper/);
  assert.equal(snapTarget(stopCheck(1)), null);
  assert.equal(snapTarget(steepCheck(1, [candidate(400, 2), candidate(120, 3)])).offset_m, 120);
});

test('a map pick on steep terrain is snapped to the nearest workable cell', async () => {
  const { snapPickedStops } = await server.ssrLoadModule('/src/TouristRoutePanel.tsx');
  const picked = { id: 'picked', name: 'Waypoint 1', latitude_deg: -89, longitude_deg: 0, enabled: true };
  const published = { id: 'poi:iau-5450', name: 'Crater', latitude_deg: -89, longitude_deg: 0, enabled: true };
  const stops = [stopCheck(0), steepCheck(1, [candidate(120, 2)]), steepCheck(2, [candidate(90, 4)])];

  const pickedResult = snapPickedStops([picked, published], stops, new Set(['picked']));
  assert.equal(pickedResult.waypoints[0].latitude_deg, -89.01);
  assert.equal(pickedResult.waypoints[0].longitude_deg, 0.02);
  assert.deepEqual(pickedResult.moved, [{ id: 'picked', offset_m: 120, terrain_slope_deg: 2 }]);

  // A published stop keeps its coordinates; the user chooses to move it explicitly.
  const publishedResult = snapPickedStops([published], stops.slice(0, 2), new Set());
  assert.deepEqual(publishedResult.moved, []);
  assert.equal(publishedResult.waypoints[0].latitude_deg, -89);
});

test('the panel preflights stops and sends the routing slope limit', async () => {
  const { readFile } = await import('node:fs/promises');
  const source = await readFile(new URL('../src/TouristRoutePanel.tsx', import.meta.url), 'utf8');
  assert.match(source, /api\.getRouteStops\(/);
  assert.match(source, /snapPickedStops\(/);
  const client = await readFile(new URL('../src/api.ts', import.meta.url), 'utf8');
  assert.match(client, /max_slope_deg: 20/);
  assert.match(client, /\/route\/stops/);
});

test('hover preview explains a snap and shows where the click will land', async () => {
  const { hoverFeedback, previewCoordinates, probeKey } = await server.ssrLoadModule('/src/map/routePreview.ts');
  const at = { latitude_deg: -89, longitude_deg: 0 };

  assert.deepEqual(hoverFeedback(null, true), { state: 'checking', label: 'Checking slope…' });
  assert.equal(hoverFeedback(stopCheck(0, { terrain_slope_deg: 3.4 }), false).label, 'Slope 3°');

  const steep = steepCheck(0, [candidate(120, 2)]);
  const snapped = hoverFeedback(steep, false);
  assert.equal(snapped.state, 'snapped');
  assert.match(snapped.label, /Steep 21° \(limit 20°\) · moves 120 m/);
  assert.deepEqual(previewCoordinates(at, steep, false), { latitude_deg: -89.01, longitude_deg: 0.02 });

  const stuck = hoverFeedback(steepCheck(0, []), false);
  assert.equal(stuck.state, 'blocked');
  assert.match(stuck.label, /no workable cell nearby/);
  assert.deepEqual(previewCoordinates(at, steepCheck(0, []), false), at);

  // A passable or still-checking point previews at the cursor itself.
  assert.deepEqual(previewCoordinates(at, stopCheck(0), false), at);
  assert.deepEqual(previewCoordinates(at, steep, true), at);

  // The 30 m probe bucket reuses answers for nearby positions and separates distant ones.
  assert.equal(probeKey(at), probeKey({ latitude_deg: -89.000004, longitude_deg: 0.000004 }));
  assert.notEqual(probeKey(at), probeKey({ latitude_deg: -89.2, longitude_deg: 0 }));
});

test('the route map previews the snap on hover and probes the cursor position', async () => {
  const { readFile } = await import('node:fs/promises');
  const panel = await readFile(new URL('../src/TouristRoutePanel.tsx', import.meta.url), 'utf8');
  assert.match(panel, /useHoverCheck\(/);
  assert.match(panel, /onMapPick\(hoverPreview \?\? coordinates\)/);
  assert.match(panel, /route-hover-tip/);
  const hook = await readFile(new URL('../src/useHoverCheck.ts', import.meta.url), 'utf8');
  assert.match(hook, /api\.getRouteStops/);
  assert.match(hook, /DEBOUNCE_MS = 120/);
});

const routedPoint = (waypoint_index, distance_m, elevation_m, placeholder = false) => ({
  latitude_deg: -89, longitude_deg: 0, distance_m, elevation_m, waypoint_index, placeholder,
});
const routedResponse = {
  method: 'astar_terrain', status: 'no_route', failed_legs: [1], total_distance_m: 300,
  waypoints: [
    { id: null, name: 'A', group: 'Custom', latitude_deg: -89, longitude_deg: 0 },
    { id: null, name: 'B', group: 'Custom', latitude_deg: -89, longitude_deg: 0.01 },
    { id: null, name: 'C', group: 'Custom', latitude_deg: -89, longitude_deg: 0.02 },
  ],
  legs: [
    { from_index: 0, to_index: 1, distance_m: 300, status: 'route_found', padding_m: 5000 },
    { from_index: 1, to_index: 2, distance_m: null, status: 'no_route', padding_m: 1000,
      reason: 'No feasible route exists in the sampled search region under these limits' },
  ],
  path: [routedPoint(0, 0, 100), routedPoint(1, 300, 140), routedPoint(2, 500, null, true)],
};

test('elevation change comes from the route path, not the bundled grid', async () => {
  const { stopElevationChange, profileSeries } = await server.ssrLoadModule('/src/RouteProfile.tsx');
  assert.equal(stopElevationChange(routedResponse, 1), 40);
  // A connector has no sampled elevation, so a dash is correct rather than a made-up delta.
  assert.equal(stopElevationChange(routedResponse, 2), null);
  assert.equal(stopElevationChange(routedResponse, 0), null);

  const series = profileSeries(routedResponse);
  assert.equal(series.planned.length, 2);
  assert.equal(series.placeholders.length, 1);
  assert.equal(series.min, 100);
  assert.equal(series.max, 140);
  assert.equal(profileSeries({ ...routedResponse, path: [] }), null);
});

test('exports keep planned legs and straight connectors apart', async () => {
  const { readFile } = await import('node:fs/promises');
  const source = await readFile(new URL('../src/TouristRoutePanel.tsx', import.meta.url), 'utf8');
  // CSV carries a kind column and KML gets a separate style for connectors.
  assert.match(source, /waypoint_index,kind/);
  assert.match(source, /'Straight connector \(not a driving route\)'/);
  assert.match(source, /<Style id="connector">/);
  assert.match(source, /p\.placeholder \? 'connector' : 'planned'/);
});

test('the panel exposes routing limits, stale state and recovery actions', async () => {
  const { readFile } = await import('node:fs/promises');
  const source = await readFile(new URL('../src/TouristRoutePanel.tsx', import.meta.url), 'utf8');
  assert.match(source, /data-testid="route-max-slope"/);
  assert.match(source, /data-testid="route-cell-size"/);
  assert.match(source, /data-testid="route-corridor"/);
  assert.match(source, /Recalculate automatically/);
  assert.match(source, /route below is from the previous calculation/);
  assert.match(source, /Widen corridor/);
  assert.match(source, /Allow \{Math\.min\(25/);
  assert.match(source, /Still planning/);
  const nginx = await readFile(new URL('../nginx.conf', import.meta.url), 'utf8');
  assert.match(nginx, /proxy_read_timeout 300s;/);
});

test('hover feedback hedges with the coarse grid while the probe is in flight', async () => {
  const { hoverFeedback } = await server.ssrLoadModule('/src/map/routePreview.ts');
  assert.deepEqual(hoverFeedback(null, true, 21.4), { state: 'hint', label: '~21° · checking…' });
  assert.deepEqual(hoverFeedback(null, true, null), { state: 'checking', label: 'Checking slope…' });
  // The authoritative verdict wins once it arrives.
  assert.equal(hoverFeedback(stopCheck(0, { terrain_slope_deg: 2.2, passable: true }), false, 21.4).label, 'Slope 2°');
});

test('route panel renders its routing limits and calculation controls', () => {
  const html = renderToStaticMarkup(React.createElement(TouristRoutePanel, {
    landingSite: site, landingUtc: '2027-08-01T00:00:00Z', poiRadiusKm: 12.5, onClose() {},
  }));
  assert.match(html, /Slope limit/);
  assert.match(html, /Corridor/);
  assert.match(html, /Smoother \(prefer gentle grades\)/);
  assert.match(html, /Recalculate automatically/);
  assert.match(html, /Calculate route/);
  assert.match(html, /value="20"/);
  assert.match(html, /value="60"/);
});

test('a stale route keeps the draft stops on the map, not the old stop list', async () => {
  const { displayRoute } = await server.ssrLoadModule('/src/routeDisplay.ts');
  const draft = {
    method: 'straight_line', waypoints: [
      { id: null, name: 'Landing', group: 'Custom', latitude_deg: -89, longitude_deg: 0 },
      { id: null, name: 'New stop', group: 'Custom', latitude_deg: -89.01, longitude_deg: 0.02 },
      { id: null, name: 'Landing', group: 'Custom', latitude_deg: -89, longitude_deg: 0 },
    ],
    path: [], legs: [], total_distance_m: 0,
  };
  const stale = {
    ...routedResponse,
    waypoints: [
      { id: null, name: 'Landing', group: 'Custom', latitude_deg: -89, longitude_deg: 0 },
      { id: null, name: 'Old stop', group: 'Custom', latitude_deg: -89.02, longitude_deg: 0.03 },
      { id: null, name: 'Landing', group: 'Custom', latitude_deg: -89, longitude_deg: 0 },
    ],
  };

  const merged = displayRoute(stale, draft);
  // Geometry comes from the previous response, so the path is still visible while editing.
  assert.equal(merged.path.length, stale.path.length);
  assert.equal(merged.total_distance_m, stale.total_distance_m);
  // Stops come from the draft, so a newly clicked waypoint appears immediately.
  assert.deepEqual(merged.waypoints.map(w => w.name), ['Landing', 'New stop', 'Landing']);
  assert.equal(displayRoute(null, draft).waypoints, draft.waypoints);
});
