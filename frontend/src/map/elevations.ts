import { CAP_RADIUS_M, MAP_CENTER, METRES_TO_SVG, project } from './projection';
import type { Coordinates } from './projection';

export interface ElevationGrid {
  width: number; height: number; bounds_m: number[]; reference_radius_m: number;
  resolution_m: number; values: (number | null)[];
}
export function validateElevationGrid(data: ElevationGrid): ElevationGrid {
  if (!data || !Number.isInteger(data.width) || !Number.isInteger(data.height)
    || data.width < 2 || data.height < 2 || data.width > 2048 || data.height > 2048
    || data.reference_radius_m !== 1737400 || !Number.isFinite(data.resolution_m) || data.resolution_m <= 0
    || !Array.isArray(data.bounds_m) || data.bounds_m.length !== 4
    || data.bounds_m.some((v, i) => !Number.isFinite(v) || Math.abs(v - (i < 2 ? -CAP_RADIUS_M : CAP_RADIUS_M)) > 0.01)
    || !Array.isArray(data.values) || data.values.length !== data.width * data.height
    || data.values.some(v => v !== null && (!Number.isFinite(v) || Math.abs(v) > 20000))) {
    throw new Error('Invalid LOLA elevation grid');
  }
  return data;
}
export async function loadElevations(signal: AbortSignal): Promise<ElevationGrid> {
  const response = await fetch('/maps/south-pole/topography/elevations.json', { signal });
  if (!response.ok) throw new Error(`Elevation data unavailable (${response.status})`);
  return validateElevationGrid(await response.json());
}
// Raster samples are at cell centres, rows north to south. Do not extrapolate.
export function sampleElevation(grid: ElevationGrid, coordinates: Coordinates): number | null {
  if (!Number.isFinite(coordinates.latitude_deg) || !Number.isFinite(coordinates.longitude_deg)
    || coordinates.latitude_deg < -90 || coordinates.latitude_deg > -80) return null;
  const point = project(coordinates);
  const east = (point.x - MAP_CENTER) / METRES_TO_SVG;
  const north = (MAP_CENTER - point.y) / METRES_TO_SVG;
  const [xmin, ymin, xmax, ymax] = grid.bounds_m;
  const x = (east - xmin) / (xmax - xmin) * grid.width - 0.5;
  const y = (ymax - north) / (ymax - ymin) * grid.height - 0.5;
  if (x < 0 || y < 0 || x > grid.width - 1 || y > grid.height - 1) return null;
  const col = Math.min(Math.floor(x), grid.width - 2), row = Math.min(Math.floor(y), grid.height - 2);
  const dx = x - col, dy = y - row;
  const samples = [grid.values[row * grid.width + col], grid.values[row * grid.width + col + 1],
    grid.values[(row + 1) * grid.width + col], grid.values[(row + 1) * grid.width + col + 1]];
  if (samples.some(value => value === null)) return null;
  return samples[0]! * (1 - dx) * (1 - dy) + samples[1]! * dx * (1 - dy)
    + samples[2]! * (1 - dx) * dy + samples[3]! * dx * dy;
}
export function elevationChange(grid: ElevationGrid | undefined, from: Coordinates, to: Coordinates): number | null {
  if (!grid) return null;
  const start = sampleElevation(grid, from), end = sampleElevation(grid, to);
  return start === null || end === null ? null : end - start;
}
