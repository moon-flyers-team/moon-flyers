import { before, after, test } from 'node:test';
import assert from 'node:assert/strict';
import { createServer } from 'vite';
import { mkdtemp, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';

let server, landingWindowError, SettingsModal, MainPanel, cacheDir;
before(async () => {
  cacheDir = await mkdtemp(join(tmpdir(), 'moon-flyers-dates-'));
  server = await createServer({ cacheDir, optimizeDeps: { noDiscovery: true, include: [] },
    server: { middlewareMode: true, watch: null, hmr: false, ws: false }, appType: 'custom' });
  ({ landingWindowError } = await server.ssrLoadModule('/src/time.ts'));
  ({ SettingsModal } = await server.ssrLoadModule('/src/App.tsx'));
  ({ MainPanel } = await server.ssrLoadModule('/src/MainPanel.tsx'));
});
after(async () => { await server?.close(); if (cacheDir) await rm(cacheDir, { recursive: true, force: true }); });
const props = {
  mission: { windowStart: '2027-08-01', windowEnd: '2027-08-01', daysOnSurface: 14, horizonClearance: 0.3 },
  power: { minSunlight: 60, maxNight: 96 }, comms: { minEarthContact: 45, maxCommsGap: 240 },
  terrain: { maxSlope: 8 }, sites: [], onMissionChange() {}, onPowerChange() {}, onCommsChange() {},
  onTerrainChange() {}, onSiteToggle() {}, onSiteAdd() {}, onSiteRename() {}, onSiteDelete() {},
  onClose() {}, onCompare() {},
};

test('landing windows require real calendar dates and a strictly later end date', () => {
  assert.equal(landingWindowError('2027-08-01','2027-08-02'),'');
  assert.equal(landingWindowError('2028-02-29','2028-03-01'),'');
  const expected=landingWindowError('2027-08-01','2027-08-01');
  assert.match(expected,/end date must be later than the start date/);
  for (const [start,end] of [['2027-08-02','2027-08-01'],['','2027-08-02'],['2027-08-01',''],
    ['2027-02-29','2027-03-02'],['2027-04-31','2027-05-02'],['invalid','2027-08-02']]) {
    assert.equal(landingWindowError(start,end),expected);
  }
});

test('settings date error appears before mission inputs and native date controls have no duplicate calendar buttons', () => {
  const html=renderToStaticMarkup(React.createElement(SettingsModal,props));
  assert.match(html,/Invalid landing window/);
  assert.ok(html.indexOf('role="alert"')<html.indexOf('Landing window start (UTC)'));
  assert.equal((html.match(/type="date"/g)??[]).length,2);
  assert.equal((html.match(/aria-invalid="true"/g)??[]).length,2);
  assert.doesNotMatch(html,/sb-calendar-button|Choose landing window .* from calendar/);
  const valid=renderToStaticMarkup(React.createElement(SettingsModal,{...props,mission:{...props.mission,windowEnd:'2027-08-02'}}));
  assert.doesNotMatch(valid,/Invalid landing window|aria-invalid="true"/);
});

test('invalid-date alert is not duplicated in Profiles or Map and the time slider is disabled', () => {
  const html=renderToStaticMarkup(React.createElement(MainPanel,props));
  assert.doesNotMatch(html,/end date must be later than the start date/);
  assert.match(html,/ts-custom-track--disabled[^>]*aria-disabled="true"/);
  assert.doesNotMatch(html,/tl-tracks--interactive/);
  assert.equal((html.match(/class="ct-btn ts-nav-btn" disabled=""/g)??[]).length,2);
  for (const [windowStart, windowEnd] of [['', '2027-08-02'], ['invalid', ''], ['2027-08-02', '2027-08-01']]) {
    const invalid = renderToStaticMarkup(React.createElement(MainPanel, {...props,
      mission: {...props.mission, windowStart, windowEnd}}));
    assert.doesNotMatch(invalid,/NaN|Infinity/);
    assert.match(invalid,/aria-disabled="true"/);
  }
});
