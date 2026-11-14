import type { HeatmapCriterion, MapHeatmapsResponse } from '../types';
import { HEATMAPS } from './heatmaps';
import { REFERENCE_OVERLAYS } from './referenceOverlays';
import type { ReferenceCriterion } from './referenceOverlays';

interface Props {
  references: ReferenceCriterion[];
  criteria: HeatmapCriterion[];
  data?: MapHeatmapsResponse;
  status: string;
}
export function HeatmapLegends({ references, criteria, data, status }: Props) {
  if (!references.length && !criteria.length) return null;
  return <aside className="map-heatmap-legends" aria-label="Heatmap legends">
    <strong>Heatmap legends</strong>
    {HEATMAPS.filter(option => references.includes(option.criterion as ReferenceCriterion) || criteria.includes(option.criterion)).map(option => {
      const reference = REFERENCE_OVERLAYS.find(layer => layer.criterion === option.criterion && references.includes(layer.criterion));
      const layer = data?.layers.find(layer => layer.criterion === option.criterion);
      const range = reference ? { min: 0, max: 100, unit: '%' } : layer;
      const unit = range?.unit === 'deg' ? '°' : range?.unit;
      const value = (number: number) => `${Number(number.toFixed(1))}${unit === '°' || unit === '%' ? '' : ' '}${unit}`;
      return <div className="map-heatmap-legend" key={option.criterion} data-criterion={option.criterion}>
        <span className="map-heatmap-legend-name">{reference?.name ?? option.label}</span>
        <div className="map-heatmap-legend-scale">
          {range && <span>{value(range.min)}</span>}
          <span className="map-gradient" style={{ background: `linear-gradient(90deg, rgb(25,27,42), rgb(${option.color.join(',')}))` }} />
          {range && <span>{value(range.max)}</span>}
        </div>
        <small>{reference ? 'Long-term reference average' : range ? data?.data_source === 'mock' ? 'Synthetic demo data' : 'Mission analysis' : status}</small>
        <small>{option.direction}{!reference && range ? ' · No data: transparent' : ''}</small>
      </div>;
    })}
  </aside>;
}
