import type { RouteResponse } from './types';

// While a result is stale the draft must stay authoritative for what is on the map and in the
// table: stops are added and removed by clicking, so freezing the old stop list makes the map feel
// dead until the user recalculates. Only the geometry (path, legs, totals) comes from the previous
// response, and the panel marks it as old.
export function displayRoute(staleRoute: RouteResponse | null, preview: RouteResponse): RouteResponse {
  if (!staleRoute) return preview;
  return { ...staleRoute, waypoints: preview.waypoints };
}
