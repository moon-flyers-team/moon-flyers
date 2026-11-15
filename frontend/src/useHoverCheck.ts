import { useEffect, useRef, useState } from 'react';
import { api } from './api';
import { probeKey } from './map/routePreview';
import type { Coordinates } from './map/projection';
import type { StopCheck } from './types';

const DEBOUNCE_MS = 120;
const CACHE_LIMIT = 600;

interface Probe {
  key: string;
  check: StopCheck | null;
}

// Terrain verdict for the point under the cursor, so a hover can preview where a click would land.
// Results are cached per 30 m bucket and superseded requests are aborted. A failed probe is
// advisory only: the click still adds the stop and the normal preflight handles it.
export function useHoverCheck(coordinates: Coordinates | null) {
  const cache = useRef(new Map<string, StopCheck>());
  const [probe, setProbe] = useState<Probe | null>(null);
  const [pending, setPending] = useState(false);
  const key = coordinates ? probeKey(coordinates) : null;

  useEffect(() => {
    if (!coordinates || !key) {
      setPending(false);
      return;
    }
    const cached = cache.current.get(key);
    if (cached) {
      setProbe({ key, check: cached });
      setPending(false);
      return;
    }
    const controller = new AbortController();
    setPending(true);
    const timer = window.setTimeout(() => {
      api.getRouteStops({
        waypoints: [{ name: 'Cursor',
          latitude_deg: coordinates.latitude_deg, longitude_deg: coordinates.longitude_deg }],
      }, controller.signal).then(response => {
        if (controller.signal.aborted) return;
        const check = response.stops[0] ?? null;
        if (check) {
          if (cache.current.size >= CACHE_LIMIT) cache.current.delete(cache.current.keys().next().value as string);
          cache.current.set(key, check);
        }
        setProbe({ key, check });
        setPending(false);
      }).catch(() => {
        if (!controller.signal.aborted) {
          setProbe({ key, check: null });
          setPending(false);
        }
      });
    }, DEBOUNCE_MS);
    return () => { window.clearTimeout(timer); controller.abort(); };
  }, [key, coordinates?.latitude_deg, coordinates?.longitude_deg]);

  return { check: probe && probe.key === key ? probe.check : null, pending: !!key && pending };
}
