// Deterministic interface fixtures, not lunar ephemerides or terrain calculations.
import { createHash } from 'node:crypto';

export const DAY_MS = 86_400_000;
export const HOUR_MS = 3_600_000;
const PERIOD_MS = 29.5306 * DAY_MS;
const EPOCH = Date.parse('2027-08-01T00:00:00Z');
const NOTE = 'Synthetic demo data; not NASA ephemerides or terrain calculations.';
export const sites = [
  { id: 'shackleton_rim', name: 'Shackleton rim', latitude_deg: -89.9297, longitude_deg: -139.407 },
  { id: 'connecting_ridge', name: 'Connecting Ridge', latitude_deg: -89.458, longitude_deg: -140.2 },
  { id: 'de_gerlache_rim', name: 'de Gerlache rim', latitude_deg: -88.67, longitude_deg: -68 },
  { id: 'malapert_massif', name: 'Malapert massif', latitude_deg: -86, longitude_deg: 0 },
].map(site => ({ ...site, group: 'Demo south-pole sites', notes: NOTE }));
const profiles = {
  shackleton_rim: [-1.2, 2, 0], connecting_ridge: [3.4, 0.3, 0.8],
  de_gerlache_rim: [1.8, -0.5, 1.6], malapert_massif: [4.4, 3.6, 2.4],
};
export const utc = time => new Date(time).toISOString().replace('.000Z', 'Z');
const round = (value, places = 2) => Number(value.toFixed(places));
const modulo = value => ((value % 360) + 360) % 360;

export function resolveSite(reference) {
  if ('id' in reference) return sites.find(site => site.id === reference.id);
  const identity = `${reference.name}:${reference.latitude_deg}:${reference.longitude_deg}`;
  return { ...reference, id: `custom_${createHash('sha256').update(identity).digest('hex').slice(0, 12)}`,
    group: 'Custom demo site', notes: NOTE };
}
function sample(site, time, constraints, sun, earth) {
  const [sunBias, earthBias, phase] = profiles[site.id] ?? [
    2 + Math.abs(site.latitude_deg) / 90, 1 + site.longitude_deg / 180, site.longitude_deg * Math.PI / 180,
  ];
  const angle = 2 * Math.PI * (time - EPOCH) / PERIOD_MS + phase;
  const sunEl = sunBias + 4.2 * Math.sin(angle) + 0.4 * Math.sin(3 * angle);
  const earthEl = earthBias + 2.8 * Math.sin(angle * 0.93 + 1.1);
  return { time_utc: utc(time), sun_azimuth_deg: round(modulo(angle * 180 / Math.PI), 4),
    sun_elevation_deg: round(sunEl, 4),
    sun_visible: sun && sunEl - 0.27 >= constraints.horizon_clearance_deg,
    earth_azimuth_deg: round(modulo(180 + 16 * Math.sin(angle)), 4),
    earth_elevation_deg: round(earthEl, 4),
    earth_visible: earth && earthEl - 0.95 >= constraints.horizon_clearance_deg };
}
export function timeseries(site, start, end, constraints, timestep = 3600, sun = true, earth = true) {
  const points = [];
  for (let time = start; time < end; time += timestep * 1000) {
    points.push(sample(site, time, constraints, sun, earth));
  }
  points.push(sample(site, end, constraints, sun, earth));
  return points;
}
export function visibilityWindows(points, body) {
  const windows = [];
  let active = null;
  for (const point of points) {
    if (point[`${body}_visible`] && active === null) active = point.time_utc;
    else if (!point[`${body}_visible`] && active !== null) {
      if (active !== point.time_utc) windows.push({ start_utc: active, end_utc: point.time_utc });
      active = null;
    }
  }
  const end = points.at(-1).time_utc;
  if (active !== null && active !== end) windows.push({ start_utc: active, end_utc: end });
  return windows;
}
// Synthetic: ±2 h around approximate 2027 lunar eclipse peaks, only while Earth is visible.
const ECLIPSE_PEAKS = ['2027-02-20T23:13:00Z', '2027-07-18T16:03:00Z', '2027-08-17T07:13:00Z'].map(Date.parse);
export function eclipseWindows(points) {
  return visibilityWindows(points.map(point => ({ time_utc: point.time_utc,
    eclipse_visible: point.earth_visible
      && ECLIPSE_PEAKS.some(peak => Math.abs(Date.parse(point.time_utc) - peak) <= 2 * 3_600_000) })), 'eclipse');
}
function windowMetrics(windows, start, end) {
  let visible = 0, longestGap = 0, cursor = start;
  for (const window of windows) {
    const left = Date.parse(window.start_utc), right = Date.parse(window.end_utc);
    visible += right - left;
    longestGap = Math.max(longestGap, left - cursor);
    cursor = right;
  }
  longestGap = Math.max(longestGap, end - cursor);
  return [round(100 * visible / (end - start)), round(longestGap / 3_600_000)];
}
// Flag-based twin of windowMetrics over a slice of one precomputed hourly series. Numerically
// identical to windowMetrics(visibilityWindows(slicePoints, body), ...) so /compare can slice
// one series per site instead of rebuilding every candidate's stay from scratch.
function windowMetricsFromFlags(flags, start, end, step) {
  let visible = 0, longestGap = 0, cursor = start;
  let i = 0;
  while (i < flags.length) {
    if (!flags[i]) { i += 1; continue; }
    let j = i + 1;
    while (j < flags.length && flags[j]) j += 1;
    const left = start + i * step;
    const right = j < flags.length ? start + j * step : end;
    visible += right - left;
    longestGap = Math.max(longestGap, left - cursor);
    cursor = right;
    i = j;
  }
  longestGap = Math.max(longestGap, end - cursor);
  return [round(100 * visible / (end - start)), round(longestGap / 3_600_000)];
}
// Metrics and fit for a stay starting at `landing` from one hourly site series, identical to
// analyze(site, landing, c) when the landing sits on the series' hourly grid; null otherwise.
export function candidateMetrics(sunFlags, earthFlags, seriesStart, landing, constraints) {
  const offset = landing - seriesStart;
  if (!Number.isInteger(offset / HOUR_MS)) return null;
  const i0 = offset / HOUR_MS;
  const staySamples = constraints.days_on_surface * (DAY_MS / HOUR_MS);
  const end = landing + constraints.days_on_surface * DAY_MS;
  const sun = windowMetricsFromFlags(sunFlags.slice(i0, i0 + staySamples + 1), landing, end, HOUR_MS);
  const earth = windowMetricsFromFlags(earthFlags.slice(i0, i0 + staySamples + 1), landing, end, HOUR_MS);
  const metrics = { sun_visible_pct: sun[0], longest_darkness_hours: sun[1],
    earth_visible_pct: earth[0], longest_earth_blackout_hours: earth[1], slope_deg: null };
  return { metrics, fit: fitFor(metrics, constraints) };
}
function fitFor(metrics, constraints) {
  const checks = [
    ['sun_visible_pct', metrics.sun_visible_pct < constraints.min_sun_visible_pct],
    ['longest_darkness_hours', metrics.longest_darkness_hours > constraints.max_darkness_hours],
    ['earth_visible_pct', metrics.earth_visible_pct < constraints.min_earth_visible_pct],
    ['longest_earth_blackout_hours', metrics.longest_earth_blackout_hours > constraints.max_earth_blackout_hours],
  ];
  const power = checks.slice(0, 2).some(([, failed]) => failed);
  const comms = checks.slice(2).some(([, failed]) => failed);
  return { status: power && comms ? 'neither_met' : power ? 'power_short' : comms ? 'comms_short' : 'both_met',
    violations: checks.filter(([, failed]) => failed).map(([name]) => name) };
}
export function analyze(site, start, constraints, timestep = 3600, sun = true, earth = true, end = undefined) {
  end = end ?? (start + constraints.days_on_surface * DAY_MS);
  const points = timeseries(site, start, end, constraints, timestep, sun, earth);
  const windows = Object.fromEntries(['sun', 'earth'].map(body => [body, visibilityWindows(points, body)]));
  windows.eclipse = eclipseWindows(points);
  const [sunlight, darkness] = windowMetrics(windows.sun, start, end);
  const [contact, blackout] = windowMetrics(windows.earth, start, end);
  const metrics = { sun_visible_pct: sunlight, longest_darkness_hours: darkness,
    earth_visible_pct: contact, longest_earth_blackout_hours: blackout, slope_deg: null };
  return { timeseries: points, horizon: { horizon_azimuth_deg: Array.from({ length: 361 }, (_, i) => i),
    horizon_elevation_deg: Array(361).fill(0) }, windows, metrics, fit: fitFor(metrics, constraints) };
}
