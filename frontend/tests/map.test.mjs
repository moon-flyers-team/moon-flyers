import { before, after, afterEach, test } from 'node:test';
import assert from 'node:assert/strict';
import { createServer } from 'vite';
import React from 'react';
import { readFile } from 'node:fs/promises';
import { renderToStaticMarkup } from 'react-dom/server';

let server, projection, validateHeatmaps, rasterPixels, api, siteReference, MapPanel, MainPanel, navigation;
const nativeFetch = globalThis.fetch;
const constraints = { days_on_surface: 14, horizon_clearance_deg: 0.3, min_sun_visible_pct: 60,
  max_darkness_hours: 96, min_earth_visible_pct: 45, max_earth_blackout_hours: 240, max_slope_deg: 8 };
const mission = { windowStart: '2027-08-01', windowEnd: '2027-10-31', daysOnSurface: 14, horizonClearance: 0.3 };
const custom = { id: 'custom_local', name: 'A map site', latitude_deg: -88, longitude_deg: 90, custom: true, enabled: true };
before(async () => {
  server = await createServer({ optimizeDeps: { noDiscovery: true, include: [] },
    server: { middlewareMode: true, watch: null, hmr: false, ws: false }, appType: 'custom' });
  projection = await server.ssrLoadModule('/src/map/projection.ts');
  navigation = await server.ssrLoadModule('/src/map/navigation.ts');
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
  const html=renderToStaticMarkup(React.createElement(MapPanel,{sites,constraints,mission,active:false,validation:'',onSiteAdd(){},onSiteRename(){},onSiteDelete(){}}));
  assert.equal((html.match(/href="\/maps\/south-pole\//g)??[]).length,36);
  assert.match(html,/map-grid/);
  assert.match(html,/aria-label="Map surface layer"/);
  assert.match(html,/Satellite imagery/);
  assert.match(html,/Topography \/ altitude contours/);
  assert.match(html,/Shackleton/);
  assert.match(html,/A map site/);
  assert.match(html,/map-waypoint--disabled/);
  assert.match(html,/1 sidebar site lies outside/);
  assert.match(html,/class="map-coordinates"/);
  assert.match(html,/map-waypoint--custom/);
  assert.match(html,/aria-label="Edit site A map site"/);
  assert.doesNotMatch(html,/No named feature/);
  assert.doesNotMatch(html,/NaN|Infinity/);
});

test('Profiles remains the initial tab and Map has its own accessible tab panel', () => {
  const html=renderToStaticMarkup(React.createElement(MainPanel,{sites:[custom],mission,
    power:{minSunlight:60,maxNight:96},comms:{minEarthContact:45,maxCommsGap:240},terrain:{maxSlope:8},onSiteAdd(){},onSiteRename(){},onSiteDelete(){}}));
  assert.match(html,/id="tab-profiles" role="tab" aria-selected="true"/);
  assert.match(html,/id="panel-map" role="tabpanel" aria-labelledby="tab-map" hidden/);
  assert.match(html,/id="panel-profiles" role="tabpanel" aria-labelledby="tab-profiles"/);
});


test('zoom preserves the point under the cursor and constrains the camera to the cap viewport', () => {
  const {INITIAL_CAMERA,zoomAt,panBy,constrainCamera}=navigation;
  const anchor={x:400,y:300};
  const zoomed=zoomAt(INITIAL_CAMERA,2,anchor);
  assert.equal(zoomed.zoom,2);
  assert.equal((anchor.x-zoomed.x)*zoomed.zoom,(anchor.x-INITIAL_CAMERA.x)*INITIAL_CAMERA.zoom);
  assert.equal((anchor.y-zoomed.y)*zoomed.zoom,(anchor.y-INITIAL_CAMERA.y)*INITIAL_CAMERA.zoom);
  assert.deepEqual(panBy(INITIAL_CAMERA,100,-100),INITIAL_CAMERA);
  assert.deepEqual(constrainCamera({zoom:2,x:-1000,y:1000}),{zoom:2,x:175,y:525});
  assert.equal(zoomAt(zoomed,100,anchor).zoom,16);
  const edge=constrainCamera({zoom:16,x:-10000,y:10000});
  assert.ok(projection.unproject(edge), 'panning cannot lose the lunar surface');
  assert.deepEqual(zoomAt(zoomed,0.01,anchor),INITIAL_CAMERA);
});

test('wheel gestures distinguish pinch, smooth pan, mouse ticks and explicit Shift-pan', () => {
  const {wheelAction}=navigation;
  const event={deltaX:0,deltaY:100,deltaMode:0,ctrlKey:false,metaKey:false,shiftKey:false};
  assert.equal(wheelAction(event),'zoom');
  assert.equal(wheelAction({...event,deltaY:12.5}),'pan');
  assert.equal(wheelAction({...event,deltaX:45}),'pan');
  assert.equal(wheelAction({...event,deltaY:2,deltaMode:1}),'zoom');
  assert.equal(wheelAction({...event,deltaY:-12,ctrlKey:true}),'zoom');
  assert.equal(wheelAction({...event,shiftKey:true}),'pan');
});


test('bundled topography assets contain all aligned tiles, the official legend and real 500 m contours', async () => {
  const root=new URL('../public/maps/south-pole/topography/',import.meta.url);
  for (let row=5;row<=10;row++) for (let column=5;column<=10;column++) {
    const png=await readFile(new URL(`${row}-${column}.png`,root));
    assert.equal(png.subarray(1,4).toString(),'PNG');
    assert.equal(png.readUInt32BE(16),256);
    assert.equal(png.readUInt32BE(20),256);
  }
  const legend=await readFile(new URL('legend.png',root));
  assert.equal(legend.readUInt32BE(16),50);
  assert.equal(legend.readUInt32BE(20),150);
  const contours=JSON.parse(await readFile(new URL('contours.json',root),'utf8'));
  assert.equal(contours.interval_m,500);
  assert.equal(contours.reference_radius_m,1737400);
  assert.deepEqual(contours.dem_size,[768,768]);
  assert.ok(contours.layers.length>20);
  for (const layer of contours.layers) {
    assert.equal(Math.abs(layer.elevation_m%500),0);
    assert.match(layer.path,/^M/);
    const coordinates=layer.path.match(/-?\d+\.\d+/g).map(Number);
    assert.ok(coordinates.every(value=>value>=45 && value<=655),'contours fit the georeferenced cap square');
  }
});
