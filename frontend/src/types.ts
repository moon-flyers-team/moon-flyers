export type FitStatus = 'both-met' | 'power-short' | 'comms-short' | 'neither';

export interface TimeWindow {
  start: string; // ISO datetime
  end: string;
}

export interface HorizonPoint {
  azimuth: number;    // 0–360°
  sunEl: number;      // sun elevation in degrees
  earthEl: number;    // earth elevation in degrees
  terrainEl: number;  // terrain horizon elevation in degrees
}

export interface LandingSite {
  id: string;
  name: string;
  lat: number;
  lon: number;
  enabled: boolean;
  sunlight: number;
  longestNight: number;
  earthContact: number;
  longestGap: number;
  slope: number;
  fit: FitStatus;
  powerWindows?: TimeWindow[];
  commsWindows?: TimeWindow[];
}

export interface MissionParams {
  windowStart: string;
  windowEnd: string;
  daysOnSurface: number;
  horizonClearance: number;
}

export interface PowerParams {
  minSunlight: number;
  maxNight: number;
}

export interface CommsParams {
  minEarthContact: number;
  maxCommsGap: number;
}

export interface TerrainParams {
  maxSlope: number;
}
