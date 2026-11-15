import type { HeatmapCriterion, HeatmapLayer, MapHeatmapsParams, MapHeatmapsResponse } from '../types';

export const HEATMAPS: { criterion: HeatmapCriterion; label: string; unit: HeatmapLayer['unit'];
  color: [number, number, number]; direction: string }[] = [
  { criterion: 'sun_visible_pct', label: 'Sunlight', unit: '%', color: [245, 166, 35], direction: 'Higher is better' },
  { criterion: 'earth_visible_pct', label: 'Earth contact', unit: '%', color: [79, 195, 247], direction: 'Higher is better' },
];

// Fail visibly instead of placing an incompatible raster over the wrong coordinates.
export function validateHeatmaps(input: unknown, params: MapHeatmapsParams): MapHeatmapsResponse {
  const data = input as MapHeatmapsResponse;
  const invalid = () => { throw new Error('The backend returned an incompatible map heatmap. Check the proposed API contract.'); };
  if (!data || data.projection !== params.projection || !['mock', 'real'].includes(data.data_source)
    || data.width !== params.width || data.height !== params.height
    || !Array.isArray(data.bounds_m) || data.bounds_m.length !== 4
    || data.bounds_m.some((value, i) => !Number.isFinite(value) || Math.abs(value - params.bounds_m[i]) > 0.01)
    || !Array.isArray(data.layers) || data.layers.length !== params.criteria.length) return invalid();
  for (const criterion of params.criteria) {
    const layers = data.layers.filter(layer => layer?.criterion === criterion);
    const layer = layers[0];
    if (layers.length !== 1 || layer.unit !== HEATMAPS.find(option => option.criterion === criterion)?.unit
      || !Number.isFinite(layer.min) || !Number.isFinite(layer.max) || layer.max < layer.min
      || !Array.isArray(layer.values) || layer.values.length !== data.width * data.height
      || layer.values.some(value => value !== null && (typeof value !== 'number' || !Number.isFinite(value)))) return invalid();
  }
  return data;
}

export function rasterPixels(layer: HeatmapLayer): Uint8ClampedArray {
  const color = HEATMAPS.find(option => option.criterion === layer.criterion)!.color;
  const pixels = new Uint8ClampedArray(layer.values.length * 4);
  layer.values.forEach((value, index) => {
    if (value === null) return;
    const fraction = layer.max === layer.min ? 0.5 : Math.max(0, Math.min(1, (value - layer.min) / (layer.max - layer.min)));
    [25, 27, 42].forEach((low, channel) => { pixels[index * 4 + channel] = low + (color[channel] - low) * fraction; });
    pixels[index * 4 + 3] = 255;
  });
  return pixels;
}
