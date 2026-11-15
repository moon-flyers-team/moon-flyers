export type FitStatus = 'both_met' | 'power_short' | 'comms_short' | 'neither_met';

export interface SiteDefinition {
  id: string;
  name: string;
  group?: string;
  latitude_deg: number;
  longitude_deg: number;
  notes?: string;
}
export type SiteReference = { id: string } | {
  name: string; latitude_deg: number; longitude_deg: number;
};
export interface LandingSite extends SiteDefinition { enabled: boolean; custom?: boolean }
export interface Constraints {
  days_on_surface: number;
  horizon_clearance_deg: number;
  min_sun_visible_pct: number;
  max_darkness_hours: number;
  min_earth_visible_pct: number;
  max_earth_blackout_hours: number;
  max_slope_deg: number;
}
export interface Metrics {
  sun_visible_pct: number;
  longest_darkness_hours: number;
  earth_visible_pct: number;
  longest_earth_blackout_hours: number;
  slope_deg: number | null;
}
export interface Fit { status: FitStatus; violations: (keyof Metrics)[] }
export interface TimeWindow { start_utc: string; end_utc: string }
// eclipse: Earth covering the Sun while Earth is visible from the site
export interface VisibilityWindows { sun: TimeWindow[]; earth: TimeWindow[]; eclipse?: TimeWindow[] }
export interface TimeseriesPoint {
  time_utc: string;
  sun_azimuth_deg: number;
  sun_elevation_deg: number;
  sun_visible: boolean;
  earth_azimuth_deg: number;
  earth_elevation_deg: number;
  earth_visible: boolean;
}
export interface HorizonProfile {
  horizon_azimuth_deg: number[];
  horizon_elevation_deg: number[];
}
export interface SiteAnalysis {
  timeseries: TimeseriesPoint[];
  horizon: HorizonProfile;
  windows: VisibilityWindows;
  metrics: Metrics;
  fit: Fit;
}
export interface SiteAnalysisResponse extends SiteDefinition { analysis: SiteAnalysis }
export interface WindowMetricsEntry { landing_utc: string; metrics: Metrics; fit: Fit }
export interface ComparisonResult {
  site: SiteDefinition; window_metrics: WindowMetricsEntry[]; timeline: VisibilityWindows;
}
export interface LandingWindow { rank: number; landing_utc: string; metrics: Metrics; fit: Fit }
export interface MissionParams {
  windowStart: string; windowEnd: string; daysOnSurface: number; horizonClearance: number;
}
export interface PowerParams { minSunlight: number; maxNight: number }
export interface CommsParams { minEarthContact: number; maxCommsGap: number }
export interface TerrainParams { maxSlope: number }

export type HeatmapCriterion = 'sun_visible_pct' | 'earth_visible_pct' | 'longest_darkness_hours'
  | 'longest_earth_blackout_hours' | 'slope_deg';
export interface MapHeatmapsParams {
  projection: 'lunar_south_polar_stereographic';
  bounds_m: [number, number, number, number];
  width: number;
  height: number;
  window_start_utc: string;
  window_end_utc: string;
  constraints: Constraints;
  criteria: HeatmapCriterion[];
}
export interface HeatmapLayer {
  criterion: HeatmapCriterion;
  unit: '%' | 'h' | 'deg';
  min: number;
  max: number;
  values: (number | null)[];
}
export interface RouteParams { waypoints: SiteReference[]; step_m?: number }
export interface RoutePoint {
  latitude_deg: number;
  longitude_deg: number;
  distance_m: number;
  waypoint_index: number | null;
}
export interface RouteLeg { from_index: number; to_index: number; distance_m: number }
export interface RouteResponse {
  method: 'straight_line';
  waypoints: (SiteDefinition & { id: string | null })[];
  legs: RouteLeg[];
  total_distance_m: number;
  path: RoutePoint[];
}
export interface RecommendedSitesParams {
  window_start_utc: string;
  window_end_utc: string;
  constraints: Constraints;
  limit?: number;
}
export interface Recommendation { rank: number; site: SiteDefinition; landing_utc: string; metrics: Metrics; fit: Fit }
export interface RecommendedSitesResponse { method: 'mock_heuristic'; recommendations: Recommendation[] }

export interface MapHeatmapsResponse {
  projection: MapHeatmapsParams['projection'];
  bounds_m: MapHeatmapsParams['bounds_m'];
  width: number;
  height: number;
  data_source: 'mock' | 'real';
  layers: HeatmapLayer[];
}
