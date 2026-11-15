import { METRES_TO_SVG, project } from './projection';
import type { Coordinates } from './projection';
import type { StopCheck } from '../types';

// Hover previews round the point to a 30 m bucket, so moving inside one cell reuses the answer
// instead of asking again. The bucket is in projected metres, which stays meaningful near the pole.
const CACHE_CELL_M = 30;

export function probeKey(coordinates: Coordinates): string {
  const point = project(coordinates);
  return `${Math.round(point.x / METRES_TO_SVG / CACHE_CELL_M)},`
    + `${Math.round(point.y / METRES_TO_SVG / CACHE_CELL_M)}`;
}

export type HoverState = 'idle' | 'checking' | 'ok' | 'snapped' | 'blocked';
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
export function hoverFeedback(check: StopCheck | null, pending: boolean): HoverFeedback {
  if (pending) return { state: 'checking', label: 'Checking slope…' };
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
