import { before, after, test } from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { createServer } from 'vite';
import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';

let server, cacheDir, ComparisonTable, TouristRoutePanel, MainPanel, terrain, projection;
before(async () => {
  cacheDir = await mkdtemp(join(tmpdir(), 'moon-flyers-arrival-'));
  server = await createServer({ cacheDir, optimizeDeps: { noDiscovery: true, include: [] },
    server: { middlewareMode: true, watch: null, hmr: false, ws: false }, appType: 'custom' });
  ({ ComparisonTable } = await server.ssrLoadModule('/src/ComparisonTable.tsx'));
  ({ TouristRoutePanel } = await server.ssrLoadModule('/src/TouristRoutePanel.tsx'));
  ({ MainPanel } = await server.ssrLoadModule('/src/MainPanel.tsx'));
  terrain = await server.ssrLoadModule('/src/map/elevations.ts');
  projection = await server.ssrLoadModule('/src/map/projection.ts');
});
after(async () => { await server?.close(); if (cacheDir) await rm(cacheDir, { recursive: true, force: true }); });
const site = { id: 'test', name: 'Test site', latitude_deg: -89, longitude_deg: 0, enabled: true };
const metrics = sun => ({ sun_visible_pct: sun, longest_darkness_hours: 0,
  earth_visible_pct: 100, longest_earth_blackout_hours: 0, slope_deg: null });
const props = {
  sites: [site], results: [{ site, window_metrics: [
    { landing_utc: '2027-08-01T00:00:00Z', metrics: metrics(10), fit: { status: 'power_short', violations: ['sun_visible_pct'] } },
    { landing_utc: '2027-08-07T06:00:00Z', metrics: metrics(90), fit: { status: 'both_met', violations: [] } },
  ], timeline: { sun: [], earth: [] } }],
  constraints: { days_on_surface: 3, horizon_clearance_deg: 0.3, min_sun_visible_pct: 60,
    max_darkness_hours: 96, min_earth_visible_pct: 45, max_earth_blackout_hours: 240, max_slope_deg: 8 },
  selectedId: site.id, onSelect() {}, onTimeSeek() {}, missionStart: '2027-08-01T00:00:00Z',
  sliderEnd: '2027-08-10T00:00:00Z', landingTime: '2027-08-07T06:00:00.000Z', loading: false, onRetry() {},
};
const render = overrides => renderToStaticMarkup(React.createElement(ComparisonTable, { ...props, ...overrides }));

test('route planning starts with one landing marker and no invented path or distances', () => {
  const html = renderToStaticMarkup(React.createElement(TouristRoutePanel, {
    landingSite: site, landingUtc: props.landingTime, onClose() {},
  }));
  assert.match(html, /aria-label="Tourist route"/);
  assert.equal((html.match(/class="route-marker(?: route-marker--landing)?"/g) ?? []).length, 1);
  assert.match(html, /Click the map to add up to 98 waypoints/);
  assert.match(html, /disabled="">Calculate round trip/);
  assert.doesNotMatch(html, /_route\.kml|Straight-line route:|class="route-stat"/);
});

test('Profiles contains no tourist route section and Route Planner is absent until landing selection', () => {
  const html = renderToStaticMarkup(React.createElement(MainPanel, {
    sites: [site], mission: { windowStart: '2027-08-01', windowEnd: '2027-08-10', daysOnSurface: 3, horizonClearance: 0.3 },
    power: { minSunlight: 60, maxNight: 96 }, comms: { minEarthContact: 45, maxCommsGap: 240 },
    terrain: { maxSlope: 8 }, onSiteAdd() {}, onSiteRename() {}, onSiteDelete() {},
  }));
  assert.match(html, /Double-click a site to choose landing/);
  assert.doesNotMatch(html, /id="tab-route"|aria-label="Tourist route"|Plan tourist route from this landing/);
});

test('elevation changes interpolate cell centres, preserve signed deltas and reject missing coverage', () => {
  const { CAP_RADIUS_M: radius, MAP_CENTER: center, MAP_RADIUS: r, unproject } = projection;
  const grid = terrain.validateElevationGrid({ width: 2, height: 2,
    bounds_m: [-radius, -radius, radius, radius], reference_radius_m: 1737400,
    resolution_m: radius, values: [100, 200, 300, 400] });
  const pole = { latitude_deg: -90, longitude_deg: 0 };
  const north = unproject({ x: center, y: center - r / 2 });
  assert.equal(terrain.sampleElevation(grid, pole), 250);
  assert.ok(Math.abs(terrain.elevationChange(grid, pole, north) + 100) < 1e-8);
  assert.ok(Math.abs(terrain.elevationChange(grid, north, pole) - 100) < 1e-8);
  assert.equal(terrain.elevationChange(grid, pole, pole), 0);
  assert.equal(terrain.elevationChange(undefined, pole, north), null);
  assert.equal(terrain.elevationChange(grid, pole, { latitude_deg: -70, longitude_deg: 0 }), null);
  assert.equal(terrain.sampleElevation({ ...grid, values: [100, null, 300, 400] }, pole), null);
  assert.throws(() => terrain.validateElevationGrid({ ...grid, values: [0] }), /Invalid LOLA/);
});

test('landing outline follows the committed landing rather than ordinary profile selection', () => {
  const other = { ...site, id: 'other', name: 'Other site' };
  const html = render({ sites: [site, other], selectedId: other.id, landingSiteId: site.id });
  assert.equal((html.match(/row-landing/g) ?? []).length, 1);
  assert.match(html, /row-landing[^>]*>[\s\S]*?Test site<\/button><span class="ct-landing-badge">Landing site/);
});

test('selected comparison candidate matches the UTC instant, not timestamp spelling', () => {
  for (const landingTime of ['2027-08-07T06:00:00.000Z', '2027-08-07T08:00:00+02:00']) {
    const html = render({ landingTime });
    assert.match(html, /90%/);
    assert.doesNotMatch(html, />10%|~ Power/);
  }
});

test('an unsampled selected arrival never displays the first candidate as evidence', () => {
  const html = render({ landingTime: '2027-08-07T07:00:00Z' });
  assert.match(html, /Not sampled/);
  assert.doesNotMatch(html, />10%|90%|~ Power/);
});

test('arrival has a labeled native UTC control, 6-hour steps, range bounds and disabled state', () => {
  const html = render({});
  assert.match(html, /type="datetime-local"/);
  assert.match(html, /aria-label="Landing time \(UTC\)"/);
  assert.match(html, /step="21600"/);
  assert.match(html, /min="2027-08-01T00:00"/);
  assert.match(html, /max="2027-08-10T00:00"/);
  assert.match(render({ disabled: true }), /type="datetime-local"[^>]*disabled=""/);
});

test('surface stay follows arrival and applied duration on both slider and site timeline', () => {
  const windows = overrides => [...render(overrides).matchAll(/class="surface-stay-window[^"]*"[^>]*style="([^"]+)"/g)].map(m => m[1]);
  // Nine-day view: a one-day stay starts one day in, then moves two days in.
  const constraints = { ...props.constraints, days_on_surface: 1 };
  const first = windows({ constraints, landingTime: '2027-08-02T00:00:00Z' });
  const moved = windows({ constraints, landingTime: '2027-08-03T00:00:00Z' });
  assert.equal(first.length, 2);
  assert.deepEqual(first, ['left:11.11111111111111%;width:11.11111111111111%', 'left:11.11111111111111%;width:11.11111111111111%']);
  assert.ok(moved.every(style => style.startsWith('left:22.22222222222222%')));
  assert.match(render({ constraints }), /Time on surface: 1 day/);
  const extended = render({ landingTime: '2027-08-09T00:00:00Z' });
  assert.match(extended, /surface-stay-window--continues/);
  assert.match(extended, /continues beyond view/);
  assert.ok(windows({ landingTime: '2027-08-09T00:00:00Z' }).every(style => style.endsWith('width:11.11111111111111%')));
  assert.equal(windows({ disabled: true }).length, 0);
  assert.equal(windows({ sliderEnd: props.missionStart }).length, 0);
  assert.equal(windows({ landingTime: 'invalid' }).length, 0);
});
