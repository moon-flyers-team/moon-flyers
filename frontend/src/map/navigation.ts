import { MAP_CENTER, MAP_RADIUS } from './projection';
import type { MapPoint } from './projection';

export interface MapCamera extends MapPoint { zoom: number }
export const INITIAL_CAMERA: MapCamera = { x: MAP_CENTER, y: MAP_CENTER, zoom: 1 };
export const MAX_ZOOM = 16;

export function constrainCamera(camera: MapCamera): MapCamera {
  const zoom = Math.max(1, Math.min(MAX_ZOOM, camera.zoom));
  const limit = MAP_CENTER - MAP_CENTER / zoom;
  const dx = Math.max(-limit, Math.min(limit, camera.x - MAP_CENTER));
  const dy = Math.max(-limit, Math.min(limit, camera.y - MAP_CENTER));
  const scale = Math.min(1, MAP_RADIUS / (Math.hypot(dx, dy) || 1));
  return { zoom, x: MAP_CENTER + dx * scale, y: MAP_CENTER + dy * scale };
}
export function zoomAt(camera: MapCamera, factor: number, anchor: MapPoint): MapCamera {
  const zoom = Math.max(1, Math.min(MAX_ZOOM, camera.zoom * factor));
  const ratio = camera.zoom / zoom;
  return constrainCamera({ zoom, x: anchor.x + (camera.x - anchor.x) * ratio,
    y: anchor.y + (camera.y - anchor.y) * ratio });
}
export function panBy(camera: MapCamera, dx: number, dy: number): MapCamera {
  return constrainCamera({ ...camera, x: camera.x + dx, y: camera.y + dy });
}
export interface WheelInput {
  deltaX: number; deltaY: number; deltaMode: number; ctrlKey: boolean; metaKey: boolean; shiftKey: boolean;
}
export function wheelAction(event: WheelInput): 'pan' | 'zoom' {
  // Pinches arrive as Ctrl+wheel in Chromium/Firefox. Browsers expose no reliable
  // mouse-vs-trackpad identifier: smooth pixel deltas indicate two-finger scrolling;
  // line/page deltas or coarse vertical ticks indicate a mouse wheel. Shift forces pan.
  if (event.ctrlKey || event.metaKey) return 'zoom';
  if (event.shiftKey) return 'pan';
  if (event.deltaMode !== 0) return 'zoom';
  return event.deltaX !== 0 || Math.abs(event.deltaY) < 50 || !Number.isInteger(event.deltaY) ? 'pan' : 'zoom';
}
