import { before, after, test } from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { createServer } from 'vite';
import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';

let server, cacheDir, SettingsModal;
before(async () => {
  cacheDir = await mkdtemp(join(tmpdir(), 'moon-flyers-labels-'));
  server = await createServer({ cacheDir, optimizeDeps: { noDiscovery: true, include: [] },
    server: { middlewareMode: true, watch: null, hmr: false, ws: false }, appType: 'custom' });
  ({ SettingsModal } = await server.ssrLoadModule('/src/App.tsx'));
});
after(async () => { await server?.close(); if (cacheDir) await rm(cacheDir, { recursive: true, force: true }); });

test('every numeric mission setting has an explicit associated visible label and a unique input ID', () => {
  const html = renderToStaticMarkup(React.createElement(SettingsModal, {
    mission: { windowStart: '2027-08-01', windowEnd: '2027-08-10', daysOnSurface: 3, horizonClearance: 0.3 },
    power: { minSunlight: 60, maxNight: 96 }, comms: { minEarthContact: 45, maxCommsGap: 240 }, terrain: { maxSlope: 8 },
    onMissionChange() {}, onPowerChange() {}, onCommsChange() {}, onTerrainChange() {}, onClose() {}, onCompare() {},
  }));
  const expected = ['Days on surface', 'Horizon clearance', 'Min sunlight', 'Max night', 'Min Earth contact', 'Max comms gap', 'Max slope'];
  const labels = [...html.matchAll(/<label for="([^"]+)">([^<]+)<\/label>/g)].filter(([, , text]) => expected.includes(text));
  assert.deepEqual(labels.map(([, , text]) => text), expected);
  assert.equal(new Set(labels.map(([, id]) => id)).size, expected.length);
  for (const [, id] of labels) {
    const inputs = [...html.matchAll(/<input\b[^>]*>/g)].map(([input]) => input);
    assert.equal(inputs.filter(input => input.includes(`id="${id}"`) && input.includes('type="number"')).length, 1);
  }
});
