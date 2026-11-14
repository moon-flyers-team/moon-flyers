// Spherical south-polar stereographic, true scale at 90°S; east-positive longitude.
// Moon Trek's Moon2000_sp uses radius 1,737,400 m and central meridian 0°.
export const MOON_RADIUS_M = 1_737_400;
export const NORTH_LIMIT = -80;
export const CAP_RADIUS_M = 2 * MOON_RADIUS_M * Math.tan(5 * Math.PI / 180);
export const MAP_CENTER = 350;
export const MAP_RADIUS = 300;
export const METRES_TO_SVG = MAP_RADIUS / CAP_RADIUS_M;
export interface Coordinates { latitude_deg: number; longitude_deg: number }
export interface MapPoint { x: number; y: number }

export function project({ latitude_deg, longitude_deg }: Coordinates): MapPoint {
  const radius = 2 * MOON_RADIUS_M * Math.tan((90 + latitude_deg) * Math.PI / 360);
  const longitude = longitude_deg * Math.PI / 180;
  return { x: MAP_CENTER + radius * Math.sin(longitude) * METRES_TO_SVG,
    y: MAP_CENTER - radius * Math.cos(longitude) * METRES_TO_SVG };
}
export function unproject({ x, y }: MapPoint): Coordinates | null {
  const east = (x - MAP_CENTER) / METRES_TO_SVG;
  const north = (MAP_CENTER - y) / METRES_TO_SVG;
  const radius = Math.hypot(east, north);
  if (!Number.isFinite(radius) || radius > CAP_RADIUS_M + 1e-6) return null;
  const longitude = radius < 1e-6 ? 0 : Math.atan2(east, north) * 180 / Math.PI;
  return { latitude_deg: -90 + 2 * Math.atan(radius / (2 * MOON_RADIUS_M)) * 180 / Math.PI,
    longitude_deg: longitude === 180 ? -180 : longitude };
}
export function distanceMetres(a: Coordinates, b: Coordinates): number {
  const radians = Math.PI / 180;
  const dLat = (a.latitude_deg - b.latitude_deg) * radians;
  const dLon = (a.longitude_deg - b.longitude_deg) * radians;
  const h = Math.sin(dLat / 2) ** 2 + Math.cos(a.latitude_deg * radians)
    * Math.cos(b.latitude_deg * radians) * Math.sin(dLon / 2) ** 2;
  return 2 * MOON_RADIUS_M * Math.asin(Math.sqrt(Math.min(1, h)));
}
