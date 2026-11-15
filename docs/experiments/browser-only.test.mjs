import { test } from 'node:test';
import assert from 'node:assert/strict';
import installGate from './browser-only.ts';

function gate() {
  const handlers = new Map();
  let active;
  installGate({ on: (name, handler) => handlers.set(name, handler), setActiveTools: names => { active = names; } });
  handlers.get('before_agent_start')();
  const call = (toolName, input) => handlers.get('tool_call')({ toolName, input });
  const result = content => handlers.get('tool_result')({ toolName: 'computer_open', content });
  return { active, call, result };
}
function open(g) {
  assert.equal(g.call('computer_open', { at: 'computer:machine/local', browser: 'msedge',
    url: process.env.BROWSER_AUDIT_URL || 'http://127.0.0.1:5175' }), undefined);
  g.result([{ type: 'text', text: 'Window: computer:local/w1test\nObservation: computer:local/o1test' }]);
}

test('participant loadout excludes code, shell, JavaScript and filesystem tools', () => {
  const g = gate();
  for (const name of ['read','bash','edit','write','computer_browser','computer_files']) {
    assert.ok(!g.active.includes(name));
    assert.equal(g.call(name, {}).block, true);
  }
});

test('only a single disposable browser and its observed addresses are accepted', () => {
  const g = gate();
  assert.equal(g.call('computer_open', { at: 'computer:machine/local', path: 'cmd.exe' }).block, true);
  open(g);
  assert.equal(g.call('computer_open', { at: 'computer:machine/local', browser: 'msedge', url: 'http://127.0.0.1:5175' }).block, true);
  assert.equal(g.call('computer_read', { path: 'computer:machine/local' }).block, true);
  const input = { path: 'computer:local/w1test', views: ['image'] };
  assert.equal(g.call('computer_read', input), undefined);
  assert.deepEqual(input.views, ['dom']);
  const filtered = g.result([{ type: 'text', text: 'ok' }, { type: 'image', data: 'not-retained', mimeType: 'image/png' }]);
  assert.deepEqual(filtered.content, [{ type: 'text', text: 'ok' }]);
});

test('input budget is enforced, waits are not inputs, browser-chrome keys are refused', () => {
  const g = gate(); open(g);
  assert.equal(g.call('computer_wait', { window: 'computer:local/w1test' }), undefined);
  assert.equal(g.call('computer_press', { window: 'computer:local/w1test', key: 'ctrl+l' }).block, true);
  // The refused key is still an attempted input, as declared by the protocol.
  for (let i = 0; i < 19; i++) assert.equal(g.call('computer_click', { window: 'computer:local/w1test', target: 'e1' }), undefined);
  assert.equal(g.call('computer_click', { window: 'computer:local/w1test', target: 'e1' }).terminate, true);
});
