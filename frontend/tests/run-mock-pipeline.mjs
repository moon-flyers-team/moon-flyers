// Own both test servers; never reuse, stop or reconfigure a developer's backend.
import { spawn } from 'node:child_process';
import { once } from 'node:events';
import { createServer as createNetServer } from 'node:net';
import { mkdtemp, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { setTimeout as sleep } from 'node:timers/promises';
import { createServer } from 'vite';

async function unusedPort() {
  const probe = createNetServer();
  probe.listen(0, '127.0.0.1');
  await once(probe, 'listening');
  const port = probe.address().port;
  await new Promise((resolve, reject) => probe.close(error => error ? reject(error) : resolve()));
  return port;
}
const mockPort = await unusedPort();
const frontendPort = await unusedPort();
const cacheDir = await mkdtemp(join(tmpdir(), 'moon-flyers-http-'));
let vite;
const mock = spawn(process.execPath, ['src/mock/server.mjs'], {
  env: { ...process.env, MOCK_API_PORT: String(mockPort), MOCK_API_DELAY_SECONDS: '0' },
  stdio: ['ignore', 'pipe', 'pipe'],
});
let mockLog = '';
mock.stdout.on('data', chunk => { mockLog += chunk; });
mock.stderr.on('data', chunk => { mockLog += chunk; });
let mockError;
mock.on('error', error => { mockError = error; });
try {
  const deadline = Date.now() + 15_000;
  while (true) {
    if (mockError) throw mockError;
    if (mock.exitCode !== null) throw new Error(`Mock exited: ${mockLog}`);
    try {
      const response = await fetch(`http://127.0.0.1:${mockPort}/health`, { signal: AbortSignal.timeout(1000) });
      if (response.ok && response.headers.get('X-Moon-Flyers-Data-Source') === 'mock') break;
    } catch { /* Bounded startup wait; errors become a failure below. */ }
    if (Date.now() >= deadline) throw new Error(`Mock startup timed out: ${mockLog}`);
    await sleep(100);
  }
  vite = await createServer({
    cacheDir, optimizeDeps: { noDiscovery: true, include: [] },
    server: { host: '127.0.0.1', port: frontendPort, strictPort: true, open: false,
      proxy: { '/api': { target: `http://127.0.0.1:${mockPort}`, changeOrigin: true,
        rewrite: path => path.replace(/^\/api/, '') } } },
  });
  await vite.listen();
  const frontendUrl = `http://127.0.0.1:${vite.httpServer.address().port}`;
  const check = spawn(process.execPath, ['tests/mock-pipeline.mjs'], {
    env: { ...process.env, FRONTEND_TEST_URL: frontendUrl }, stdio: 'inherit',
  });
  const [code] = await once(check, 'exit');
  if (code !== 0) throw new Error(`Mock pipeline exited with code ${code}`);
} catch (error) {
  console.error(mockLog);
  throw error;
} finally {
  await vite?.close();
  if (mock.exitCode === null) {
    const exited = once(mock, 'exit');
    mock.kill();
    await exited;
  }
  await rm(cacheDir, { recursive: true, force: true });
}
