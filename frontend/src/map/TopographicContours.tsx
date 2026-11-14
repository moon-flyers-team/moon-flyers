import { useEffect, useMemo } from 'react';
import { useRequest } from '../useRequest';

interface Contours {
  interval_m: number;
  reference_radius_m: number;
  layers: { elevation_m: number; path: string }[];
}
export function TopographicContours({ enabled, onError }: { enabled: boolean; onError: (error: string) => void }) {
  const request = useMemo(() => !enabled ? null : async (signal: AbortSignal) => {
    const response = await fetch('/maps/south-pole/topography/contours.json', { signal });
    if (!response.ok) throw new Error('Elevation contours could not load.');
    const contours = await response.json() as Contours;
    if (contours.interval_m !== 500 || contours.reference_radius_m !== 1737400 || !Array.isArray(contours.layers)
      || contours.layers.some(layer => !Number.isFinite(layer.elevation_m) || typeof layer.path !== 'string')) {
      throw new Error('Elevation contours have an incompatible format.');
    }
    return contours;
  }, [enabled]);
  const result = useRequest(request, 0);
  useEffect(() => { if (result.error) onError(result.error); }, [result.error, onError]);
  if (!enabled || !result.data) return null;
  return <g className="map-contours" aria-label="LOLA elevation contours, 500 metre interval">
    {result.data.layers.map(layer => <path key={layer.elevation_m} d={layer.path}
      className={layer.elevation_m % 1000 === 0 ? 'map-contour-major' : 'map-contour-minor'}
      vectorEffect="non-scaling-stroke"><title>{`${layer.elevation_m} m elevation`}</title></path>)}
  </g>;
}
