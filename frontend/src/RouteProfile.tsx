import type { RouteResponse } from './types';

// Signed elevation change at a stop, from the terrain the route actually sampled.
// Placeholder legs carry no elevation, so a crossing into or out of one shows a dash.
export function stopElevationChange(route: RouteResponse, index: number): number | null {
  if (index <= 0 || index >= route.waypoints.length) return null;
  const at = (waypointIndex: number) => route.path.find(p => p.waypoint_index === waypointIndex)?.elevation_m ?? null;
  const from = at(index - 1), to = at(index);
  return from == null || to == null ? null : to - from;
}

export interface ProfilePoint { distance_m: number; elevation_m: number | null }
export interface ProfileSeries { planned: ProfilePoint[]; placeholders: ProfilePoint[]; min: number; max: number; length_m: number }

// Split the returned path into planned and placeholder runs so the chart never draws a straight
// connector as if it were terrain.
export function profileSeries(route: RouteResponse): ProfileSeries | null {
  const points = route.path.filter(p => Number.isFinite(p.distance_m));
  if (points.length < 2) return null;
  const planned: ProfilePoint[] = [];
  const placeholders: ProfilePoint[] = [];
  for (const point of points) {
    const entry = { distance_m: point.distance_m, elevation_m: point.elevation_m ?? null };
    (point.placeholder ? placeholders : planned).push(entry);
  }
  const elevations = points.map(p => p.elevation_m).filter((value): value is number => value != null);
  if (elevations.length < 2) return null;
  return {
    planned, placeholders,
    min: Math.min(...elevations), max: Math.max(...elevations),
    length_m: points[points.length - 1].distance_m,
  };
}

function path(series: ProfilePoint[], x: (m: number) => number, y: (m: number) => number): string {
  const drawn = series.filter(p => p.elevation_m != null);
  return drawn.map((p, i) => `${i ? 'L' : 'M'}${x(p.distance_m).toFixed(2)},${y(p.elevation_m!).toFixed(2)}`).join(' ');
}

// Small profile of the planned route: distance along the route against sampled elevation.
export function RouteProfile({ route, height = 84 }: { route: RouteResponse; height?: number }) {
  const series = profileSeries(route);
  if (!series) return null;
  const width = 600;
  const pad = 6;
  const span = Math.max(1, series.max - series.min);
  const x = (m: number) => pad + (m / Math.max(1, series.length_m)) * (width - 2 * pad);
  const y = (m: number) => height - pad - ((m - series.min) / span) * (height - 2 * pad);
  const plannedCount = series.planned.filter(p => p.elevation_m != null).length;
  const placeholderCount = series.placeholders.length;
  return (
    <figure className="route-profile">
      <figcaption>
        Elevation profile · {Math.round(series.min)}–{Math.round(series.max)} m
        {placeholderCount > 0 && ` · ${placeholderCount} points on straight connectors`}
      </figcaption>
      <svg viewBox={`0 0 ${width} ${height}`} role="img" aria-label={
        `Elevation profile over ${(series.length_m / 1000).toFixed(1)} km, ${Math.round(series.min)} to `
        + `${Math.round(series.max)} m${placeholderCount > 0 ? ', with straight connectors that are not terrain' : ''}`}>
        <line x1={pad} x2={width - pad} y1={y(series.min)} y2={y(series.min)} className="route-profile-axis" />
        {placeholderCount > 0 && (
          <path d={path(series.placeholders, x, y)} className="route-profile-placeholder" />
        )}
        {plannedCount > 1 && <path d={path(series.planned, x, y)} className="route-profile-line" />}
        <text x={pad} y={y(series.max) + 10} className="route-profile-label">{Math.round(series.max)} m</text>
        <text x={pad} y={y(series.min) - 3} className="route-profile-label">{Math.round(series.min)} m</text>
      </svg>
    </figure>
  );
}
