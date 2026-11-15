import type {
  SiteDefinition, SiteReference, SiteAnalysisResponse, ComparisonResult,
  LandingWindow, Constraints, LandingSite, MapHeatmapsParams, MapHeatmapsResponse,
  RouteParams, RouteResponse, RecommendedSitesParams, RecommendedSitesResponse,
} from './types';

const BASE = (import.meta.env.VITE_API_URL || '/api').replace(/\/$/, '');

async function response(path: string, init: RequestInit = {}): Promise<Response> {
  const res = await fetch(`${BASE}${path}`, init);
  if (!res.ok) {
    const body: unknown = await res.json().catch(() => null);
    const detail = body && typeof body === 'object' && 'detail' in body ? body.detail : null;
    throw new Error(`${res.status} ${typeof detail === 'string' ? detail : detail ? JSON.stringify(detail) : res.statusText}`);
  }
  return res;
}
async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  return (await response(path, init)).json() as Promise<T>;
}
function post<T>(path: string, body: unknown, signal?: AbortSignal) {
  return request<T>(path, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body), signal,
  });
}
export interface SiteAnalysisParams {
  site: SiteReference;
  window_start_utc: string;
  window_end_utc: string;
  constraints: Constraints;
  timestep_seconds?: number;
  sun_visibility?: boolean;
  earth_visibility?: boolean;
}
export interface CompareParams {
  sites: SiteReference[];
  window_start_utc: string;
  window_end_utc: string;
  constraints: Constraints;
  candidate_step_hours?: number;
  timestep_seconds?: number;
}
export interface LandingWindowsParams {
  site: SiteReference;
  window_start_utc: string;
  window_end_utc: string;
  constraints: Constraints;
  candidate_step_hours?: number;
  limit?: number;
}
// Local IDs identify custom sites in React only; the backend needs their coordinates.
export function siteReference(site: LandingSite): SiteReference {
  return site.custom ? { name: site.name, latitude_deg: site.latitude_deg, longitude_deg: site.longitude_deg }
    : { id: site.id };
}
export const api = {
  getMapHeatmaps: (params: MapHeatmapsParams, signal?: AbortSignal) =>
    post<MapHeatmapsResponse>('/map/heatmaps', params, signal),
  getCatalogue: async (signal?: AbortSignal) => {
    const res = await response('/sites', { signal });
    return {
      sites: await res.json() as SiteDefinition[],
      isMock: res.headers.get('X-Moon-Flyers-Data-Source') === 'mock',
    };
  },
  getSites: (signal?: AbortSignal) => request<SiteDefinition[]>('/sites', { signal }),
  getSiteAnalysis: (params: SiteAnalysisParams, signal?: AbortSignal) => {
    const query = new URLSearchParams();
    const site = 'id' in params.site ? { site_id: params.site.id } : params.site;
    const fields = {
      ...site, ...params.constraints,
      window_start_utc: params.window_start_utc, window_end_utc: params.window_end_utc,
      timestep_seconds: params.timestep_seconds ?? 3600,
      sun_visibility: params.sun_visibility ?? true,
      earth_visibility: params.earth_visibility ?? true,
    };
    Object.entries(fields).forEach(([key, value]) => query.set(key, String(value)));
    return request<SiteAnalysisResponse>(`/sites?${query}`, { signal });
  },
  compare: (params: CompareParams, signal?: AbortSignal) =>
    post<ComparisonResult[]>('/compare', { timestep_seconds: 3600, ...params }, signal),
  getLandingWindows: (params: LandingWindowsParams, signal?: AbortSignal) =>
    post<LandingWindow[]>('/landing-windows', { candidate_step_hours: 6, limit: 5, ...params }, signal),
  getRoute: (params: RouteParams, signal?: AbortSignal) =>
    post<RouteResponse>('/route', { step_m: 100, ...params }, signal),
  getRecommendedSites: (params: RecommendedSitesParams, signal?: AbortSignal) =>
    post<RecommendedSitesResponse>('/recommended-sites', { limit: 5, ...params }, signal),
  health: (signal?: AbortSignal) => request<{ status: string }>('/health', { signal }),
};
