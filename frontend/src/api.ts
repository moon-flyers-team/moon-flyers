import type { LandingSite, HorizonPoint, MissionParams, PowerParams, CommsParams, TerrainParams } from './types';

const BASE = import.meta.env.VITE_API_URL;

async function get<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`);
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.json() as Promise<T>;
}

export interface AnalyzeParams {
  mission: MissionParams;
  power: PowerParams;
  comms: CommsParams;
  terrain: TerrainParams;
  siteIds: string[];
}

export const api = {
  getSites: (): Promise<LandingSite[]> =>
    get('/sites'),

  getHorizon: (siteId: string, landingTime: string): Promise<HorizonPoint[]> =>
    get(`/sites/${encodeURIComponent(siteId)}/horizon?t=${encodeURIComponent(landingTime)}`),

  analyze: (params: AnalyzeParams): Promise<LandingSite[]> =>
    get(`/analyze?${new URLSearchParams({
      window_start: params.mission.windowStart,
      window_end: params.mission.windowEnd,
      days: String(params.mission.daysOnSurface),
      horizon_clearance: String(params.mission.horizonClearance),
      min_sunlight: String(params.power.minSunlight),
      max_night: String(params.power.maxNight),
      min_earth_contact: String(params.comms.minEarthContact),
      max_comms_gap: String(params.comms.maxCommsGap),
      max_slope: String(params.terrain.maxSlope),
      site_ids: params.siteIds.join(','),
    })}`),
};
