import type { HeatmapCriterion } from '../types';

export type ReferenceCriterion = 'sun_visible_pct' | 'earth_visible_pct';
export const REFERENCE_OVERLAYS: { criterion: ReferenceCriterion; name: string; file: string; color: string }[] = [
  { criterion: 'sun_visible_pct', name: 'Sunlight', file: 'sunlight.png', color: '#f5a623' },
  { criterion: 'earth_visible_pct', name: 'Earth visibility', file: 'earth-visibility.png', color: '#4fc3f7' },
];
export function isReferenceCriterion(criterion: HeatmapCriterion): criterion is ReferenceCriterion {
  return criterion === 'sun_visible_pct' || criterion === 'earth_visible_pct';
}
