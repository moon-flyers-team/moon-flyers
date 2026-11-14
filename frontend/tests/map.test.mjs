import { before, after, afterEach, test } from 'node:test';
import assert from 'node:assert/strict';
import { createServer } from 'vite';
import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';

let server, projection, validateHeatmaps, rasterPixels, api, siteReference, MapPanel, MainPanel;
const nativeFetch = globalThis.fetch;
const constraints = { days_on_surface: 14, horizon_clearance_deg: 0.3, min_sun_visible_pct: 60,
  max_darkness_hours: 96, min_earth_visible_pct: 45, max_earth_blackout_hours: 240, max_slope_deg: 8 };
const mission = { windowStart: '2027-08-01', windowEnd: '2027-10-31', daysOnSurface: 14, horizonClearance: 0.3 };
const custom = { id: 'custom_local', name: 'A map site', latitude_deg: -88, longitude_deg: 90, custom: true, enabled: true };
before(async () => {
  server = await createServer({ optimizeDeps: { noDiscovery: true, include: [] },
    server: { middlewareMode: true, watch: null, hmr: false, ws: false }, appType: 'custom' });
  projection = await server.ssrLoadModule('/src/map/projection.ts');
  ({ validateHeatmaps, rasterPixels } = await server.ssrLoadModule('/src/map/heatmaps.ts'));
  ({ api, siteReference } = await server.ssrLoadModule('/src/api.ts'));
  ({ MapPanel } = await server.ssrLoadModule('/src/MapPanel.tsx'));
  ({ MainPanel } = await server.ssrLoadModule('/src/MainPanel.tsx'));
});
afterEach(() => { globalThis.fetch = nativeFetch; });
after(async () => { await server?.close(); });

function params() {
  const radius = projection.CAP_RADIUS_M;
  return { projection: 'lunar_south_polar_stereographic', bounds_m: [-radius, -radius, radius, radius],
    width: 2, height: 2, window_start_utc: '2027-08-01T00:00:00Z', window_end_utc: '2027-10-31T00:00:00Z',
    constraints, criteria: ['sun_visible_pct'] };
}
function response() {
  const { projection, bounds_m, width, height } = params();
  return { projection, bounds_m, width, height, data_source: 'mock',
    layers: [{ criterion: 'sun_visible_pct', unit: '%', min: 0, max: 100, values: [null, 0, 50, 100] }] };
}

test('south-polar projection round-trips coordinates with the correct longitude orientation', () => {
  const { project, unproject, MAP_CENTER, MAP_RADIUS } = projection;
  assert.deepEqual(project({latitude_deg:-90,longitude_deg:0}), {x:MAP_CENTER,y:MAP_CENTER});
  for (const latitude_deg of [-90, -89.667, -86, -80]) {
    for (const longitude_deg of [-180, -90, 0, 90, 179.999]) {
      const result=unproject(project({latitude_deg,longitude_deg}));
      assert.ok(Math.abs(result.latitude_deg-latitude_deg)<1e-8);
      if (latitude_deg!==-90) assert.ok(Math.abs(result.longitude_deg-longitude_deg)<1e-8);
    }
  }
  assert.ok(Math.abs(project({latitude_deg:-80,longitude_deg:0}).y-(MAP_CENTER-MAP_RADIUS))<1e-8);
  assert.ok(Math.abs(project({latitude_deg:-80,longitude_deg:90}).x-(MAP_CENTER+MAP_RADIUS))<1e-8);
  assert.equal(unproject({x:MAP_CENTER+MAP_RADIUS+1,y:MAP_CENTER}),null);
  assert.equal(unproject({x:NaN,y:0}),null);
});

test('custom map sites send coordinates through all analysis endpoints, never their local ID', async () => {
  const calls=[];
  globalThis.fetch=async (url,init={}) => { calls.push({url:new URL(url,'http://test'),init}); return Response.json([]); };
  const reference=siteReference(custom);
  assert.deepEqual(reference,{name:custom.name,latitude_deg:-88,longitude_deg:90});
  assert.deepEqual(siteReference({...custom,custom:false}),{id:custom.id});
  const bounds={window_start_utc:'2027-08-01T00:00:00Z',window_end_utc:'2027-10-31T00:00:00Z'};
  await api.getSiteAnalysis({site:reference,...bounds,constraints});
  await api.compare({sites:[reference],...bounds,constraints});
  await api.getLandingWindows({site:reference,...bounds,constraints});
  assert.equal(calls[0].url.searchParams.get('latitude_deg'),'-88');
  assert.equal(calls[0].url.searchParams.has('site_id'),false);
  assert.deepEqual(JSON.parse(calls[1].init.body).sites,[reference]);
  assert.deepEqual(JSON.parse(calls[2].init.body).site,reference);
});

test('heatmap request sends all mission settings, raster extent, enabled criteria and abort signal', async () => {
  let call;
  const expected=response(), body=params(), signal=new AbortController().signal;
  globalThis.fetch=async (url,init) => {call={url,init};return Response.json(expected);};
  assert.deepEqual(await api.getMapHeatmaps(body,signal),expected);
  assert.match(call.url,/\/map\/heatmaps$/);
  assert.equal(call.init.method,'POST');
  assert.equal(call.init.signal,signal);
  assert.deepEqual(JSON.parse(call.init.body),body);
  globalThis.fetch=async () => Response.json({detail:'Not Found'},{status:404});
  await assert.rejects(api.getMapHeatmaps(body),/404/);
});

test('heatmap validation rejects misaligned, incomplete, or malformed rasters', () => {
  const expected=response();
  assert.deepEqual(validateHeatmaps(expected,params()),expected);
  for (const patch of [{projection:'earth'}, {bounds_m:[0,0,1,1]}, {width:3}, {data_source:'unknown'}, {layers:[]}]) {
    assert.throws(()=>validateHeatmaps({...expected,...patch},params()),/incompatible/);
  }
  for (const patch of [{values:[0]}, {values:[0,0,NaN,1]}, {unit:'m'}, {min:100,max:0}]) {
    assert.throws(()=>validateHeatmaps({...expected,layers:[{...expected.layers[0],...patch}]},params()),/incompatible/);
  }
});

test('heatmap colors preserve no-data transparency and handle a constant-valued layer', () => {
  const pixels=rasterPixels(response().layers[0]);
  assert.equal(pixels[3],0);
  assert.equal(pixels[7],255);
  assert.deepEqual([...pixels.slice(12,16)],[245,166,35,255]);
  const constant=rasterPixels({...response().layers[0],min:50,max:50,values:[50]});
  assert.deepEqual([...constant],[135,96,38,255]);
});

test('map renders the polar grid, real local basemap tiles, disabled and custom waypoints, and fixed cursor output', () => {
  const sites=[custom,{...custom,id:'disabled',name:'Disabled site',enabled:false},
    {...custom,id:'outside',name:'Outside cap',latitude_deg:-60}];
  const html=renderToStaticMarkup(React.createElement(MapPanel,{sites,constraints,mission,active:false,validation:'',onSiteAdd(){}}));
  assert.equal((html.match(/href="\/maps\/south-pole\//g)??[]).length,36);
  assert.match(html,/map-grid/);
  assert.match(html,/Shackleton/);
  assert.match(html,/A map site/);
  assert.match(html,/map-waypoint--disabled/);
  assert.match(html,/1 sidebar site lies outside/);
  assert.match(html,/class="map-coordinates"/);
  assert.doesNotMatch(html,/NaN|Infinity/);
});

test('Profiles remains the initial tab and Map has its own accessible tab panel', () => {
  const html=renderToStaticMarkup(React.createElement(MainPanel,{sites:[custom],mission,
    power:{minSunlight:60,maxNight:96},comms:{minEarthContact:45,maxCommsGap:240},terrain:{maxSlope:8},onSiteAdd(){}}));
  assert.match(html,/id="tab-profiles" role="tab" aria-selected="true"/);
  assert.match(html,/id="panel-map" role="tabpanel" aria-labelledby="tab-map" hidden/);
  assert.match(html,/id="panel-profiles" role="tabpanel" aria-labelledby="tab-profiles"/);
});
