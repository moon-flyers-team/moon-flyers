// Standalone local mock API. All mock source lives under frontend/src/mock/.
import { createServer } from 'node:http';
import { setTimeout as sleep } from 'node:timers/promises';
import { handleMockRequest } from './api.mjs';

const delay = Number(process.env.MOCK_API_DELAY_SECONDS ?? 0.4);
const port = Number(process.env.MOCK_API_PORT ?? 8000);
if (!Number.isFinite(delay) || delay < 0) throw new Error('MOCK_API_DELAY_SECONDS must be nonnegative');
const server = createServer(async (request, response) => {
  try {
    const chunks = [];
    let size = 0;
    for await (const chunk of request) {
      size += chunk.length;
      if (size > 1_048_576) {
        response.writeHead(413, { 'Content-Type': 'application/json' });
        response.end(JSON.stringify({ detail: 'Demo request body exceeds 1 MB' }));
        return;
      }
      chunks.push(chunk);
    }
    let body;
    try { body = chunks.length ? JSON.parse(Buffer.concat(chunks).toString()) : undefined; }
    catch {
      response.writeHead(400, { 'Content-Type': 'application/json' });
      response.end(JSON.stringify({ detail: 'Invalid JSON body' }));
      return;
    }
    const pathname = new URL(request.url, 'http://localhost').pathname;
    if (delay && !['/', '/health'].includes(pathname) && request.method !== 'OPTIONS') await sleep(delay * 1000);
    const result = handleMockRequest({ method: request.method, url: request.url, body, origin: request.headers.origin });
    response.writeHead(result.status, result.headers);
    response.end(JSON.stringify(result.body));
    console.log(`${request.method} ${pathname} ${result.status}`);
  } catch (error) {
    console.error(error);
    if (!response.headersSent) response.writeHead(500, { 'Content-Type': 'application/json' });
    response.end(JSON.stringify({ detail: 'Mock server error' }));
  }
});
server.on('error', error => { console.error(error.message); process.exitCode = 1; });
server.listen(port, '127.0.0.1', () => console.log(`Mock API at http://127.0.0.1:${port} — synthetic demo data`));
for (const signal of ['SIGINT', 'SIGTERM']) process.once(signal, () => server.close());
