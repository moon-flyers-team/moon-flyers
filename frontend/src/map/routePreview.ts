import { METRES_TO_SVG, project, unproject } from './projection';
import type { Coordinates } from './projection';
import { sampleElevation } from './elevations';
import type { ElevationGrid } from './elevations';
import type { StopCheck } from '../types';

// Hover previews round the point to a 30 m bucket, so moving inside one cell reuses the answer
// instead of asking again. The bucket is in projected metres, which stays meaningful near the pole.
const CACHE_CELL_M = 30;

export function probeKey(coordinates: Coordinates): string {
  const point = project(coordinates);
  return `${Math.round(point.x / METRES_TO_SVG / CACHE_CELL_M)},`
    + `${Math.round(point.y / METRES_TO_SVG / CACHE_CELL_M)}`;
}

export type HoverState = 'idle' | 'checking' | 'hint' | 'ok' | 'snapped' | 'blocked';
export interface HoverFeedback { state: HoverState; label: string }

const candidate = (check: StopCheck | null | undefined) => {
  if (!check || check.passable || !check.nearby_terrain_candidates.length) return null;
  return [...check.nearby_terrain_candidates].sort((a, b) => a.offset_m - b.offset_m)[0];
};

// Where a click would place the stop: the cursor itself, or the nearest passable cell.
export function previewCoordinates(coordinates: Coordinates, check: StopCheck | null,
  pending: boolean): Coordinates {
  if (pending || !check || check.passable) return coordinates;
  const target = candidate(check);
  return target ? { latitude_deg: target.latitude_deg, longitude_deg: target.longitude_deg } : coordinates;
}

// Cursor label, in the spirit of a tool that refuses a bad connection and says why.
export function hoverFeedback(check: StopCheck | null, pending: boolean,
  hintDeg: number | null = null): HoverFeedback {
  if (pending) {
    // The coarse grid hedges the label while the authoritative probe is in flight.
    if (hintDeg == null) return { state: 'checking', label: 'Checking slope…' };
    return { state: 'hint', label: `~${Math.round(hintDeg)}° · checking…` };
  }
  if (!check) return { state: 'idle', label: '' };
  const slope = check.terrain_slope_deg == null ? null : Math.round(check.terrain_slope_deg);
  const limit = Math.round(check.max_slope_deg);
  if (check.passable) return { state: 'ok', label: slope == null ? 'Slope unknown' : `Slope ${slope}°` };
  const target = candidate(check);
  if (slope == null) {
    return { state: target ? 'snapped' : 'blocked',
      label: target ? `Not practical · moves ${Math.round(target.offset_m)} m` : 'Not practical terrain' };
  }
  return {
    state: target ? 'snapped' : 'blocked',
    label: target
      ? `Steep ${slope}° (limit ${limit}°) · moves ${Math.round(target.offset_m)} m`
      : `Steep ${slope}° (limit ${limit}°) · no workable cell nearby`,
  };
}

// Continuous hover hint from the bundled ~792 m LOLA grid: one central-difference gradient.
// Coarse compared with the planner's 60 m cells, so it only hedges the label until the probe
// answers; it never decides a snap or a passability verdict.
export function localSlopeDeg(grid: ElevationGrid | undefined, coordinates: Coordinates): number | null {
  if (!grid) return null;
  const centre = sampleElevation(grid, coordinates);
  if (centre == null) return null;
  const point = project(coordinates);
  const step = grid.resolution_m * METRES_TO_SVG;
  const east = unproject({ x: point.x + step, y: point.y });
  const north = unproject({ x: point.x, y: point.y - step });
  if (!east || !north) return null;
  const eastElevation = sampleElevation(grid, east);
  const northElevation = sampleElevation(grid, north);
  if (eastElevation == null || northElevation == null) return null;
  const gradient = Math.hypot((eastElevation - centre) / grid.resolution_m,
    (northElevation - centre) / grid.resolution_m);
  return Math.atan(gradient) * 180 / Math.PI;
}
