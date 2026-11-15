// Validated mock implementation of API.md. No Python or backend/ files required.
import { DAY_MS, sites, resolveSite, analyze, timeseries, visibilityWindows, eclipseWindows, utc } from './data.mjs';

class ApiError extends Error {
  constructor(status, message) { super(message); this.status = status; }
}
const fail = message => { throw new ApiError(422, message); };
const DEFAULTS = { days_on_surface: 14, horizon_clearance_deg: 0.3, min_sun_visible_pct: 60,
  max_darkness_hours: 96, min_earth_visible_pct: 45, max_earth_blackout_hours: 240, max_slope_deg: 8 };
function object(value, label) {
  if (!value || typeof value !== 'object' || Array.isArray(value)) fail(`${label} must be an object`);
  return value;
}
function number(value, fallback, name, min = 0, max = Infinity, integer = false) {
  if (value === undefined) return fallback;
  if (typeof value === 'boolean' || value === null || value === '') fail(`Invalid ${name}`);
  const parsed = Number(value);
  if (!Number.isFinite(parsed) || parsed < min || parsed > max || (integer && !Number.isInteger(parsed))) fail(`Invalid ${name}`);
  return parsed;
}
function constraints(input = {}, strict = true) {
  object(input, 'constraints');
  if (strict && Object.keys(input).some(key => !(key in DEFAULTS))) fail('Unknown constraint field');
  const limits = { days_on_surface: [1, Infinity, true], horizon_clearance_deg: [0, 90],
    min_sun_visible_pct: [0, 100], min_earth_visible_pct: [0, 100], max_slope_deg: [0, 90] };
  return Object.fromEntries(Object.entries(DEFAULTS).map(([key, fallback]) => [
    key, number(input[key], fallback, key, ...(limits[key] ?? [0])),
  ]));
}
function timestamp(value, label) {
  if (typeof value !== 'string' || !/(?:Z|[+-]\d{2}:\d{2})$/i.test(value)) fail(`${label} requires an ISO 8601 timestamp with timezone`);
  const parsed = Date.parse(value);
  if (!Number.isFinite(parsed)) fail(`Invalid ${label}`);
  return parsed;
}
function siteFrom(reference) {
  object(reference, 'site');
  let ref;
  if ('id' in reference) {
    if (typeof reference.id !== 'string' || !reference.id || Object.keys(reference).length !== 1) fail('Provide id or custom coordinates, not both');
    ref = { id: reference.id };
  } else {
    if (typeof reference.name !== 'string' || !reference.name.trim()) fail('Custom site requires a name');
    if (reference.latitude_deg === undefined || reference.longitude_deg === undefined) fail('Custom site requires latitude_deg and longitude_deg');
    if (Object.keys(reference).some(key => !['name', 'latitude_deg', 'longitude_deg'].includes(key))) fail('Unknown site field');
    ref = { name: reference.name,
      latitude_deg: number(reference.latitude_deg, undefined, 'latitude_deg', -90, 90),
      longitude_deg: number(reference.longitude_deg, undefined, 'longitude_deg', -180, 180) };
  }
  const site = resolveSite(ref);
  if (!site) throw new ApiError(404, `Unknown site: ${ref.id}`);
  return site;
}
function seriesLimit(start, end, step) {
  if (!Number.isFinite(end) || Math.abs(end) > 8.64e15 || (end - start) / (step * 1000) > 100_000) {
    fail('Demo request exceeds 100,000 samples; shorten the range or increase the timestep.');
  }
}
function windowBody(body, extra) {
  object(body, 'request');
  const allowed = ['window_start_utc', 'window_end_utc', 'constraints', ...extra];
  if (Object.keys(body).some(key => !allowed.includes(key))) fail('Unknown request field');
  const start = timestamp(body.window_start_utc, 'window_start_utc');
  const end = timestamp(body.window_end_utc, 'window_end_utc');
  if (end < start) fail('window_end_utc must be on or after window_start_utc');
  return { start, end, c: constraints(body.constraints) };
}
function boolean(value, fallback, name) {
  if (value === undefined) return fallback;
  if (['true', '1'].includes(value)) return true;
  if (['false', '0'].includes(value)) return false;
  fail(`Invalid ${name}`);
}
function route(method, url, body) {
  const query = Object.fromEntries(url.searchParams);
  if (method === 'GET' && url.pathname === '/') return { message: 'Moon Flyers Mock API — synthetic demo data' };
  if (method === 'GET' && url.pathname === '/health') return { status: 'ok' };
  if (method === 'GET' && url.pathname === '/sites') {
    const c = constraints(query, false);
    const step = number(query.timestep_seconds, 3600, 'timestep_seconds', 1, Infinity, true);
    const sun = boolean(query.sun_visibility, true, 'sun_visibility');
    const earth = boolean(query.earth_visibility, true, 'earth_visibility');
    if (!['site_id', 'name', 'latitude_deg', 'longitude_deg', 'window_start_utc'].some(key => key in query)) return sites;
    const wStart = timestamp(query.window_start_utc, 'window_start_utc');
    const wEnd = timestamp(query.window_end_utc, 'window_end_utc');
    if (wEnd < wStart) fail('window_end_utc must be on or after window_start_utc');
    const hasCustom = ['name', 'latitude_deg', 'longitude_deg'].some(key => key in query);
    if ('site_id' in query && hasCustom) fail('Choose site_id or custom coordinates, not both');
    const site = siteFrom('site_id' in query ? { id: query.site_id } : {
      name: query.name, latitude_deg: query.latitude_deg, longitude_deg: query.longitude_deg,
    });
    const totalEnd = wEnd + c.days_on_surface * DAY_MS;
    seriesLimit(wStart, totalEnd, step);
    return { ...site, analysis: analyze(site, wStart, c, step, sun, earth, totalEnd) };
  }
  if (method === 'POST' && url.pathname === '/compare') {
    const { start, end, c } = windowBody(body, ['sites', 'candidate_step_hours', 'timestep_seconds']);
    const candidateStep = number(body.candidate_step_hours, 6, 'candidate_step_hours', Number.MIN_VALUE);
    const step = number(body.timestep_seconds, 3600, 'timestep_seconds', 1, Infinity, true);
    if (!Array.isArray(body.sites) || !body.sites.length) fail('sites must contain at least one site');
    const timelineEnd = end + c.days_on_surface * DAY_MS;
    const count = Math.floor((end - start) / (candidateStep * 3_600_000)) + 1;
    if (count > 2000 || count * (c.days_on_surface * 24 + 1) > 1_000_000) fail('Demo request too large; shorten the window or increase candidate_step_hours.');
    seriesLimit(start, timelineEnd, step);
    return body.sites.map(reference => {
      const site = siteFrom(reference);
      const window_metrics = Array.from({ length: count }, (_, i) => {
        const landing = start + i * candidateStep * 3_600_000;
        const a = analyze(site, landing, c);
        return { landing_utc: utc(landing), metrics: a.metrics, fit: a.fit };
      });
      const points = timeseries(site, start, timelineEnd, c, step);
      return { site, window_metrics,
        timeline: { ...Object.fromEntries(['sun', 'earth'].map(name => [name, visibilityWindows(points, name)])),
          eclipse: eclipseWindows(points) } };
    });
  }
  if (method === 'POST' && url.pathname === '/landing-windows') {
    const { start, end, c } = windowBody(body, ['site', 'candidate_step_hours', 'limit']);
    const site = siteFrom(body.site);
    const step = number(body.candidate_step_hours, 6, 'candidate_step_hours', Number.MIN_VALUE);
    const limit = number(body.limit, 5, 'limit', 1, Infinity, true);
    const count = Math.floor((end - start) / (step * 3_600_000)) + 1;
    if (count > 2000 || count * (c.days_on_surface * 24 + 1) > 1_000_000) fail('Demo search is too large; shorten the range or increase candidate_step_hours.');
    seriesLimit(start, end + c.days_on_surface * DAY_MS, 3600);
    const candidates = Array.from({ length: count }, (_, i) => {
      const time = start + i * step * 3_600_000;
      const analysis = analyze(site, time, c);
      return { landing_utc: utc(time), metrics: analysis.metrics, fit: analysis.fit };
    });
    candidates.sort((a, b) => a.fit.violations.length - b.fit.violations.length
      || b.metrics.sun_visible_pct - a.metrics.sun_visible_pct
      || b.metrics.earth_visible_pct - a.metrics.earth_visible_pct
      || a.landing_utc.localeCompare(b.landing_utc));
    return candidates.slice(0, limit).map((row, i) => ({ rank: i + 1, ...row }));
  }
  if (['/sites', '/compare', '/landing-windows', '/health'].includes(url.pathname)) throw new ApiError(405, 'Method not allowed');
  throw new ApiError(404, 'Not found');
}

export function handleMockRequest({ method = 'GET', url = '/', body, origin } = {}) {
  const headers = { 'Content-Type': 'application/json', 'X-Moon-Flyers-Data-Source': 'mock' };
  if (['http://localhost:5173', 'http://127.0.0.1:5173'].includes(origin)) {
    Object.assign(headers, { 'Access-Control-Allow-Origin': origin, 'Access-Control-Allow-Credentials': 'true',
      'Access-Control-Expose-Headers': 'X-Moon-Flyers-Data-Source', Vary: 'Origin',
      'Access-Control-Allow-Methods': 'GET, POST, OPTIONS', 'Access-Control-Allow-Headers': 'Content-Type' });
  }
  if (method === 'OPTIONS') return { status: 200, headers, body: {} };
  try {
    return { status: 200, headers, body: route(method, new URL(url, 'http://localhost'), body) };
  } catch (error) {
    if (!(error instanceof ApiError)) throw error;
    return { status: error.status, headers, body: { detail: error.message } };
  }
}
