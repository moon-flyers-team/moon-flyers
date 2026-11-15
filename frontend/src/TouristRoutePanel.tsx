import { useCallback, useEffect, useId, useMemo, useRef, useState } from 'react';
import type { ReactNode } from 'react';
import { project, unproject, MAP_CENTER, MAP_RADIUS, METRES_TO_SVG } from './map/projection';
import type { Coordinates, MapPoint } from './map/projection';
import { zoomAt, panBy, wheelAction } from './map/navigation';
import type { MapCamera } from './map/navigation';
import { visibleTiles } from './map/routeTiles';
import { api, siteReference } from './api';
import { useRequest } from './useRequest';
import { elevationChange, loadElevations } from './map/elevations';
import type { ElevationGrid } from './map/elevations';
import { formatUtc } from './time';
import type { LandingSite, PoiCategory, PointOfInterest, RecommendedSitesResponse, RouteResponse } from './types';

const MAX_ZOOM = 600;
// FastAPI accepts 100 entries, including the repeated landing at start and end.
const MAX_WAYPOINTS = 100 - 2;
const reducedMotion = typeof matchMedia === 'function' && matchMedia('(prefers-reduced-motion: reduce)').matches;

// Bundled level-4 basemap, shown underneath while high-res tiles load or offline
const BASE_TILES = Array.from({ length: 36 }, (_, i) => {
  const row = 5 + Math.floor(i / 6), col = 5 + i % 6;
  const span = 136_991.25;
  return {
    row, col,
    x: MAP_CENTER + (-1_095_930 + col * span) * METRES_TO_SVG,
    y: MAP_CENTER - (1_095_930 - row * span) * METRES_TO_SVG,
    size: span * METRES_TO_SVG,
  };
});

const WAYPOINT_COLOR = '#ddddf8';
const LANDING_COLOR = '#00e676';
const POI_COLOR = '#ffb74d';
const LEGEND: [string, string][] = [[LANDING_COLOR, 'Landing site'], [WAYPOINT_COLOR, 'Waypoints'], [POI_COLOR, 'Recommended sites']];
const DRAG_TYPE = 'application/x-moon-waypoint';
const CATEGORY_LABEL: Record<PoiCategory, string> = {
  lander: 'Lander', rover: 'Rover', impact: 'Impact site', natural_feature: 'Natural feature',
};
const poiWaypointId = (poi: PointOfInterest) => `poi:${poi.id}`;

export function fitCamera(pts: MapPoint[], width = 600, height = 600): MapCamera {
  if (!pts.length) return { x: MAP_CENTER, y: MAP_CENTER, zoom: 1 };
  if (pts.length === 1) return { ...pts[0], zoom: 16 };
  let minX = Infinity, maxX = -Infinity, minY = Infinity, maxY = -Infinity;
  for (const p of pts) {
    minX = Math.min(minX, p.x); maxX = Math.max(maxX, p.x);
    minY = Math.min(minY, p.y); maxY = Math.max(maxY, p.y);
  }
  if (minX === maxX && minY === maxY) return { ...pts[0], zoom: 16 };
  // xMidYMid slice crops the square viewBox along the shorter viewport dimension.
  const halfSpan = Math.max(
    (maxX - minX) / 2 * Math.max(width, height) / width,
    (maxY - minY) / 2 * Math.max(width, height) / height,
    0.5,
  );
  return {
    x: (minX + maxX) / 2,
    y: (minY + maxY) / 2,
    zoom: Math.min(MAX_ZOOM, Math.max(1, MAP_CENTER / (halfSpan * 1.45))),
  };
}

function niceKm(km: number): number {
  const p = 10 ** Math.floor(Math.log10(km));
  return [5, 2, 1].map(m => m * p).find(v => v <= km) ?? p;
}

const km = (m: number | null) => m == null || !Number.isFinite(m) ? '—' : `${(m / 1000).toFixed(1)} km`;

function download(content: string, filename: string, mime: string) {
  const url = URL.createObjectURL(new Blob([content], { type: mime }));
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 0);
}

function toKml(r: RouteResponse, name: string) {
  const track = r.path.map(p => `${p.longitude_deg},${p.latitude_deg},0`).join(' ');
  const marks = r.waypoints.map((w, i) => `
    <Placemark><name>${i}: ${w.name}</name>
      <Point><coordinates>${w.longitude_deg},${w.latitude_deg},0</coordinates></Point>
    </Placemark>`).join('');
  return `<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2">
  <Document>
    <name>${name} tourist route</name>
    <description>Method: ${r.method} | ${km(r.total_distance_m)}</description>
    <Style id="track"><LineStyle><color>ff76e600</color><width>3</width></LineStyle></Style>
    <Placemark><name>Route track</name><styleUrl>#track</styleUrl>
      <LineString><tessellate>1</tessellate><coordinates>${track}</coordinates></LineString>
    </Placemark>${marks}
  </Document>
</kml>`;
}

function toCsv(r: RouteResponse) {
  const rows = r.path.map(p => [p.latitude_deg.toFixed(6), p.longitude_deg.toFixed(6),
    p.distance_m.toFixed(1), p.waypoint_index ?? ''].join(','));
  return ['latitude_deg,longitude_deg,distance_m,waypoint_index', ...rows].join('\r\n');
}

interface Props {
  landingSite: LandingSite;
  landingUtc: string;
  poiRadiusKm?: number;
  onClose: () => void;
}

export function TouristRoutePanel({ landingSite, landingUtc, poiRadiusKm = 40, onClose }: Props) {
  const [searchRadius, setSearchRadius] = useState<number | null>(null);
  // A changed applied radius invalidates previous catalogue results without an automatic search.
  useEffect(() => setSearchRadius(null), [poiRadiusKm]);
  const poiRequest = useMemo(() => searchRadius !== poiRadiusKm || !Number.isFinite(poiRadiusKm) || poiRadiusKm <= 0
    ? null : (signal: AbortSignal) => api.getRecommendedSites({
      site: siteReference(landingSite), radius_km: poiRadiusKm,
    }, signal), [searchRadius, poiRadiusKm, landingSite]);
  const nearby = useRequest(poiRequest, 0);
  const elevations = useRequest(loadElevations, 0);
  const siteName = landingSite.name;
  const slug = siteName.replace(/\s+/g, '_');
  const [waypoints, setWaypoints] = useState<LandingSite[]>([]);
  const [submitted, setSubmitted] = useState<LandingSite[] | null>(null);
  const [announcement, setAnnouncement] = useState('');
  const request = useMemo(() => submitted !== waypoints ? null
    : (signal: AbortSignal) => api.getRoute({
      waypoints: [siteReference(landingSite), ...waypoints.map(siteReference), siteReference(landingSite)],
    }, signal), [submitted, waypoints, landingSite]);
  const result = useRequest(request, 0);
  const route = result.data;
  const loading = result.loading;
  // Draft markers are preview-only: no path or distances are invented before the response.
  const preview = useMemo<RouteResponse>(() => ({ method: 'straight_line',
    waypoints: waypoints.length ? [landingSite, ...waypoints, landingSite] : [landingSite], path: [], legs: [], total_distance_m: 0,
  }), [landingSite, waypoints]);
  const addedPoiIds = useMemo(() => new Set(waypoints.map(w => w.id)), [waypoints]);
  function pushWaypoint(next: LandingSite): boolean {
    if (waypoints.length >= MAX_WAYPOINTS) {
      setAnnouncement(`Maximum of ${MAX_WAYPOINTS} waypoints reached. Remove a stop to add another.`);
      return false;
    }
    setWaypoints(previous => previous.length < MAX_WAYPOINTS ? [...previous, next] : previous);
    return true;
  }
  function addWaypoint(coordinates: Coordinates) {
    if (pushWaypoint({ ...coordinates, id: crypto.randomUUID(), custom: true, enabled: true,
      name: `Waypoint ${waypoints.length + 1}` })) setAnnouncement('');
  }
  // Recommended sites become ordinary custom waypoints, so routing and reordering are unchanged.
  function togglePoi(poi: PointOfInterest) {
    const id = poiWaypointId(poi);
    if (addedPoiIds.has(id)) {
      setWaypoints(previous => previous.filter(w => w.id !== id));
      setAnnouncement(`Removed ${poi.name}. Recalculate to update the route.`);
      return;
    }
    if (pushWaypoint({ id, custom: true, enabled: true, name: poi.name,
      latitude_deg: poi.latitude_deg, longitude_deg: poi.longitude_deg,
      group: `${CATEGORY_LABEL[poi.category]} · ${poi.feature_type}` })) {
      setAnnouncement(`Added ${poi.name} as stop ${waypoints.length + 1}.`);
    }
  }
  function moveWaypoint(from: number, to: number) {
    if (!Number.isInteger(from) || !Number.isInteger(to) || from === to
      || from < 0 || to < 0 || from >= waypoints.length || to >= waypoints.length) return;
    setWaypoints(previous => {
      const reordered = [...previous];
      const [moved] = reordered.splice(from, 1);
      reordered.splice(to, 0, moved);
      return reordered;
    });
    setAnnouncement(`Waypoint moved to position ${to + 1}. Recalculate to update the route.`);
  }
  return (
    <section className="route-wrap" aria-label="Tourist route" aria-busy={loading}>
      <div className="route-hdr">
        <div className="route-title">
          <span className="route-kicker">Tourist route</span>
          <strong>{siteName}</strong>
          <span className="ct-info map-info-tip" tabIndex={0} role="img"
            aria-label={`Elevation change: approximate endpoint difference from LOLA (~792 m grid), not cumulative ascent. Click the map to add up to ${MAX_WAYPOINTS} waypoints, or add recommended sites from the list or the amber map markers. Drag stops to reorder, or use up/down arrows. Right-drag to pan; wheel to zoom.`}
            data-tip={`Elevation change: approximate endpoint difference from LOLA (~792 m grid), not cumulative ascent.\nClick the map to add up to ${MAX_WAYPOINTS} waypoints, or add recommended sites (amber markers).\nDrag stops to reorder, or use ↑/↓. Right-drag to pan; wheel to zoom.`}>i</span>
          <span className="route-sub">Landing {formatUtc(landingUtc)}</span>
        </div>
        <div className="route-stats">
          {route && <>
            <span className="route-stat">{km(route.total_distance_m)}</span>
            <span className="route-stat">{route.waypoints.length - 2} stop{route.waypoints.length !== 3 ? 's' : ''}</span>
          </>}
        </div>
        <div className="route-actions">
          <button className="ct-btn route-primary-btn route-calc-btn" disabled={!waypoints.length || loading}
            onClick={() => { setAnnouncement(''); if (submitted === waypoints) result.retry(); else setSubmitted(waypoints); }}>Calculate route</button>
          <button className="ct-btn route-primary-btn" disabled={!waypoints.length} onClick={() => setWaypoints([])}>Clear waypoints</button>
          {route && <>
            <button className="ct-btn" onClick={() => download(toKml(route, siteName), `${slug}_route.kml`, 'application/vnd.google-earth.kml+xml')}>KML</button>
            <button className="ct-btn" onClick={() => download(toCsv(route), `${slug}_route.csv`, 'text/csv')}>CSV</button>
          </>}
          <button className="ct-btn route-close" aria-label="Close tourist route" onClick={onClose}>✕</button>
        </div>
      </div>

      {(elevations.loading || elevations.error) && (
        <div className="route-editor">
          {elevations.loading && <p>Loading elevations…</p>}
          {elevations.error && <p>Elevation data unavailable. <button className="ct-btn" onClick={elevations.retry}>Retry elevations</button></p>}
        </div>
      )}
      <div className="route-editor">
        <button className="ct-btn" disabled={nearby.loading || !Number.isFinite(poiRadiusKm) || poiRadiusKm <= 0}
          onClick={() => { if (searchRadius === poiRadiusKm) nearby.retry(); else setSearchRadius(poiRadiusKm); }}>
          Find nearby POIs ({poiRadiusKm} km)
        </button>
        {nearby.loading && <span role="status">Searching catalogue…</span>}
        {nearby.error && <span className="request-error" role="alert">POI search failed: {nearby.error}</span>}
        {nearby.data && <span>{nearby.data.recommendations.length} nearby POIs: add them from the list or the amber map markers.</span>}
      </div>
      {loading && <p className="request-status" role="status">Calculating route…</p>}
      {route?.failed_legs?.length ? <div className="request-error" role="status">
        No terrain route for {route.failed_legs.length} of {route.legs.length} leg{route.legs.length !== 1 ? 's' : ''} (dashed
        straight lines only connect the stops). {route.reason}</div> : null}
      {result.error && <div className="request-error" role="alert">Route request failed: {result.error}
        {' '}<button className="ct-btn" onClick={result.retry}>Retry</button></div>}
      <span className="map-announcement" role="status">{announcement}</span>
      <RouteView onWaypointRemove={index => {
        setWaypoints(previous => previous.filter((_, i) => i !== index));
        setAnnouncement(`Removed waypoint ${index + 1}. Recalculate to update the route.`);
      }} elevations={elevations.data} onWaypointMove={moveWaypoint} route={route ?? preview} onMapPick={addWaypoint} calculated={!!route}
        pois={(nearby.data?.recommendations ?? []).map(r => r.poi).filter(p => !addedPoiIds.has(poiWaypointId(p)))}
        onPoiPick={togglePoi}
        sidePanel={<RecommendedStops data={nearby.data} radiusKm={poiRadiusKm}
          isAdded={poi => addedPoiIds.has(poiWaypointId(poi))} onToggle={togglePoi} />} />
    </section>
  );
}

// Lists the latest "Find nearby POIs" results; the radius is the mission setting.
function RecommendedStops({ data, radiusKm, isAdded, onToggle }: {
  data?: RecommendedSitesResponse; radiusKm: number;
  isAdded: (poi: PointOfInterest) => boolean; onToggle: (poi: PointOfInterest) => void;
}) {
  return (
    <section className="route-recs" aria-label="Recommended sites">
      <div className="route-recs-hdr">
        <span className="route-recs-title">Recommended sites</span>
        <span className="route-recs-radius">within {radiusKm} km</span>
      </div>
      {!data && <p className="route-recs-empty">Use “Find nearby POIs” to list published sites you can add as stops.</p>}
      {data && !data.recommendations.length && (
        <p className="route-recs-empty">No published sites within {data.radius_km} km. Increase the search radius in Settings.</p>
      )}
      {data && data.recommendations.length > 0 && (
        <ul className="route-recs-list">
          {data.recommendations.map(({ poi, distance_km }) => {
            const added = isAdded(poi);
            return (
              <li key={poi.id} className={`route-rec${added ? ' route-rec--added' : ''}`}>
                <span className="route-dot" style={{ background: POI_COLOR }} />
                <span className="route-rec-text" title={poi.notes || undefined}>
                  {poi.name}
                  <span className="route-note">
                    {CATEGORY_LABEL[poi.category]} · {poi.feature_type} · {distance_km === 0 ? 'landing is inside' : `${distance_km.toFixed(1)} km`}
                  </span>
                </span>
                <button className="ct-btn route-rec-btn" aria-pressed={added}
                  aria-label={`${added ? 'Remove' : 'Add'} ${poi.name} ${added ? 'from' : 'to'} the route`}
                  onClick={() => onToggle(poi)}>{added ? 'Remove' : 'Add'}</button>
              </li>
            );
          })}
        </ul>
      )}
      {data && <p className="route-recs-foot">Published catalogue {data.catalogue_version}. Distances are to approximate footprints, not driving routes.</p>}
    </section>
  );
}

function RouteView({ route, elevations, onWaypointRemove, onWaypointMove, onMapPick, calculated, pois, onPoiPick, sidePanel }: {
  onWaypointRemove: (index: number) => void;
  route: RouteResponse; elevations?: ElevationGrid; onWaypointMove: (from: number, to: number) => void;
  onMapPick: (coordinates: Coordinates) => void; calculated: boolean;
  pois: PointOfInterest[]; onPoiPick: (poi: PointOfInterest) => void; sidePanel: ReactNode;
}) {
  const clipId = useId();
  const svgRef = useRef<SVGSVGElement>(null);
  const drag = useRef<{ pointerId: number; x: number; y: number } | null>(null);
  const [panning, setPanning] = useState(false);
  const [active, setActive] = useState<number | null>(null);
  const [viewport, setViewport] = useState({ width: 600, height: 600 });
  const px = Math.max(viewport.width, viewport.height);

  const colorOf = (i: number) => i === 0 ? LANDING_COLOR : WAYPOINT_COLOR;

  const pathPts = useMemo(() => route.path.map(p => project(p)), [route]);
  const stops = useMemo(() => route.waypoints.map(w => project(w)), [route]);
  // Split the path at waypoint markers: leg n ends at waypoint n + 1
  const legPaths = useMemo(() => {
    const legs: string[] = [];
    let d = '';
    pathPts.forEach((p, i) => {
      d += `${d ? 'L' : 'M'}${p.x},${p.y}`;
      const w = route.path[i].waypoint_index;
      if (i > 0 && w != null) { legs.push(d); d = `M${p.x},${p.y}`; }
    });
    return legs;
  }, [route, pathPts]);
  const fullD = useMemo(() => pathPts.map((p, i) => `${i ? 'L' : 'M'}${p.x},${p.y}`).join(' '), [pathPts]);

  const fit = useMemo(() => fitCamera([...stops, ...pathPts], viewport.width, viewport.height),
    [stops, pathPts, viewport]);
  const [camera, setCamera] = useState<MapCamera>(fit);
  useEffect(() => { if (calculated) setCamera(fit); }, [fit, calculated]);

  useEffect(() => {
    const svg = svgRef.current;
    if (!svg) return;
    const ro = new ResizeObserver(([entry]) => {
      const { width, height } = entry.contentRect;
      if (width && height) setViewport(previous => previous.width === width && previous.height === height
        ? previous : { width, height });
    });
    ro.observe(svg);
    return () => ro.disconnect();
  }, []);

  useEffect(() => {
    const svg = svgRef.current;
    if (!svg) return;
    const onWheel = (e: WheelEvent) => {
      e.preventDefault();
      const inv = svg.getScreenCTM()?.inverse();
      if (!inv) return;
      const anchor = new DOMPoint(e.clientX, e.clientY).matrixTransform(inv);
      const m = e.deltaMode === 1 ? 16 : e.deltaMode === 2 ? svg.clientHeight : 1;
      if (wheelAction(e) === 'zoom') {
        setCamera(c => zoomAt(c, Math.exp(-e.deltaY * m * (e.ctrlKey ? 0.01 : 0.002)), anchor, MAX_ZOOM));
      } else {
        const to = new DOMPoint(e.clientX + e.deltaX * m, e.clientY + e.deltaY * m).matrixTransform(inv);
        setCamera(c => panBy(c, to.x - anchor.x, to.y - anchor.y, MAX_ZOOM));
      }
    };
    svg.addEventListener('wheel', onWheel, { passive: false });
    return () => svg.removeEventListener('wheel', onWheel);
  }, []);

  const stopPanning = useCallback(() => { drag.current = null; setPanning(false); }, []);

  const half = MAP_CENTER / camera.zoom;
  const k = (2 * half) / px; // svg units per screen pixel
  const tiles = useMemo(
    () => visibleTiles('relief', { x: camera.x, y: camera.y, half, pxPerSvg: 1 / k }),
    [camera.x, camera.y, half, k],
  );
  const scaleKm = niceKm((px / 5) * k / METRES_TO_SVG / 1000);
  const scalePx = scaleKm * 1000 * METRES_TO_SVG / k;
  const cumulative = route.legs.reduce<(number | null)[]>((acc, l) => {
    const previous = acc[acc.length - 1];
    return [...acc, previous == null || l.distance_m == null ? null : previous + l.distance_m];
  }, [0]);
  const isLoop = route.waypoints.length > 2
    && route.waypoints[0].latitude_deg === route.waypoints[route.waypoints.length - 1].latitude_deg
    && route.waypoints[0].longitude_deg === route.waypoints[route.waypoints.length - 1].longitude_deg;

  function focus(i: number) {
    setActive(i);
    setCamera(c => panBy({ ...c, x: stops[i].x, y: stops[i].y }, 0, 0, MAX_ZOOM));
  }

  return (
    <div className="route-body">
      <div className="route-map-wrap">
        <svg
          ref={svgRef}
          className={`route-svg${panning ? ' route-svg--panning' : ''}`}
          viewBox={`${camera.x - half} ${camera.y - half} ${2 * half} ${2 * half}`}
          preserveAspectRatio="xMidYMid slice"
          role="img"
          aria-label="Terrain map of the tourist route. Arrow keys pan; Enter adds a waypoint at the map center."
          tabIndex={0}
          onKeyDown={event => {
            if (event.key === 'Enter' || event.key === ' ') {
              event.preventDefault(); const coordinates = unproject(camera); if (coordinates) onMapPick(coordinates);
            }
            const delta = { ArrowLeft: [-1, 0], ArrowRight: [1, 0], ArrowUp: [0, -1], ArrowDown: [0, 1] }[event.key];
            if (delta) { event.preventDefault(); setCamera(c => panBy(c, delta[0] * half / 5, delta[1] * half / 5, MAX_ZOOM)); }
          }}
          onClick={event => {
            if (event.button !== 0) return;
            const inverse = event.currentTarget.getScreenCTM()?.inverse();
            const coordinates = inverse ? unproject(new DOMPoint(event.clientX, event.clientY).matrixTransform(inverse)) : null;
            if (coordinates) onMapPick(coordinates);
          }}
          onContextMenu={e => e.preventDefault()}
          onPointerDown={e => {
            if (e.button !== 1 && e.button !== 2) return;
            e.currentTarget.setPointerCapture(e.pointerId);
            drag.current = { pointerId: e.pointerId, x: e.clientX, y: e.clientY };
            setPanning(true);
          }}
          onPointerMove={e => {
            const prev = drag.current;
            if (!prev || prev.pointerId !== e.pointerId) return;
            const inv = e.currentTarget.getScreenCTM()?.inverse();
            if (!inv) return;
            const from = new DOMPoint(prev.x, prev.y).matrixTransform(inv);
            const to = new DOMPoint(e.clientX, e.clientY).matrixTransform(inv);
            setCamera(c => panBy(c, from.x - to.x, from.y - to.y, MAX_ZOOM));
            drag.current = { ...prev, x: e.clientX, y: e.clientY };
          }}
          onPointerUp={e => {
            if (drag.current?.pointerId !== e.pointerId) return;
            e.currentTarget.releasePointerCapture(e.pointerId);
            stopPanning();
          }}
          onPointerCancel={stopPanning}
          onLostPointerCapture={stopPanning}
        >
          <defs>
            <clipPath id={`${clipId}-cap`}>
              <circle cx={MAP_CENTER} cy={MAP_CENTER} r={MAP_RADIUS} />
            </clipPath>
          </defs>
          <rect x={camera.x - half * 2} y={camera.y - half * 2} width={half * 4} height={half * 4} fill="#0b0b14" />
          <g clipPath={`url(#${clipId}-cap)`}>
            {BASE_TILES.map(t => (
              <image key={`${t.row}-${t.col}`} href={`/maps/south-pole/topography/${t.row}-${t.col}.png`}
                x={t.x} y={t.y} width={t.size} height={t.size} preserveAspectRatio="none" />
            ))}
            {tiles.map(t => (
              <image key={t.key} href={t.href} x={t.x} y={t.y}
                width={t.size + k * 0.5} height={t.size + k * 0.5} preserveAspectRatio="none" />
            ))}
          </g>

          <path d={fullD} fill="none" stroke="#05050c" strokeOpacity={0.75}
            strokeWidth={9 * k} strokeLinejoin="round" strokeLinecap="round" />
          {legPaths.map((d, i) => (
            <path key={i} d={d} fill="none" stroke={colorOf(route.legs[i]?.to_index ?? i + 1)}
              strokeWidth={4.5 * k} strokeLinejoin="round" strokeLinecap="round"
              {...(route.failed_legs?.includes(i) ? { strokeDasharray: `${10 * k} ${8 * k}`, strokeOpacity: 0.6 } : {})} />
          ))}
          <path d={fullD} fill="none" stroke="#fff" strokeOpacity={0.85}
            strokeWidth={1.5 * k} strokeDasharray={`${2 * k} ${14 * k}`} strokeLinecap="round">
            {!reducedMotion && <animate attributeName="stroke-dashoffset" from="0" to={-16 * k} dur="0.9s" repeatCount="indefinite" />}
          </path>

          {pois.map(poi => {
            const pt = project(poi);
            const s = 7 * k;
            return (
              <g key={poi.id} className="route-poi" role="button" tabIndex={-1}
                onClick={event => { event.stopPropagation(); onPoiPick(poi); }}>
                <title>{`${poi.name} — click to add as a stop`}</title>
                <path d={`M${pt.x},${pt.y - s}L${pt.x + s},${pt.y}L${pt.x},${pt.y + s}L${pt.x - s},${pt.y}Z`}
                  fill="#11111d" stroke={POI_COLOR} strokeWidth={2 * k} />
                <text x={pt.x + s + 5 * k} y={pt.y} dominantBaseline="central" fontSize={11 * k} fill={POI_COLOR}
                  stroke="#05050c" strokeWidth={3 * k} paintOrder="stroke">{poi.name}</text>
              </g>
            );
          })}

          {stops.map((pt, i) => {
            if (isLoop && i === stops.length - 1) return null;
            const base = i === 0;
            const r = (base ? 11 : 9) * k;
            const on = active === i;
            const color = colorOf(i);
            return (
              <g key={i} className={`route-marker${base ? ' route-marker--landing' : ''}`}  onMouseEnter={() => setActive(i)} onMouseLeave={() => setActive(null)}
                onClick={event => { event.stopPropagation(); focus(i); }}>
                {(base || on) && (
                  <circle cx={pt.x} cy={pt.y} r={r + 6 * k} fill="none" stroke={color}
                    strokeWidth={2 * k} opacity={base ? 1 : on ? 0.9 : 0.5} />
                )}
                <circle cx={pt.x} cy={pt.y} r={r} fill={base ? '#f2f2ff' : '#11111d'}
                  stroke={color} strokeWidth={2.5 * k} />
                <text x={pt.x} y={pt.y} textAnchor="middle" dominantBaseline="central"
                  fontSize={(base ? 11 : 10) * k} fontWeight={700} fill={base ? '#11111d' : '#fff'}>
                  {base ? '⌂' : i}
                </text>
                <text x={pt.x + r + 6 * k} y={pt.y} dominantBaseline="central"
                  fontSize={(on ? 13 : 12) * k} fontWeight={on ? 700 : 500} fill="#fff"
                  stroke="#05050c" strokeWidth={3.5 * k} paintOrder="stroke">{route.waypoints[i].name}</text>
              </g>
            );
          })}
        </svg>

        <div className="route-map-controls">
          <button className="ct-btn" aria-label="Zoom in" disabled={camera.zoom >= MAX_ZOOM}
            onClick={() => setCamera(c => zoomAt(c, 2, c, MAX_ZOOM))}>+</button>
          <button className="ct-btn" aria-label="Zoom out" disabled={camera.zoom <= 1}
            onClick={() => setCamera(c => zoomAt(c, 0.5, c, MAX_ZOOM))}>−</button>
          <button className="ct-btn" onClick={() => setCamera(fit)}>Fit</button>
        </div>

        <div className="route-scale" aria-hidden="true">
          <span className="route-scale-bar" style={{ width: scalePx }} />
          <span>{scaleKm >= 1 ? `${scaleKm} km` : `${scaleKm * 1000} m`}</span>
        </div>

        <div className="route-map-foot">
          <div className="route-legend">
            {LEGEND.map(([color, label]) => (
              <span key={label} className="route-legend-item">
                <span className="route-legend-dot" style={{ background: color }} />
                {label}
              </span>
            ))}
          </div>
          <span className="route-credit">NASA Moon Trek · LRO/LOLA relief, 5 m/px</span>
        </div>
      </div>

      <div className="route-table-wrap">
        <table className="route-table">
          <thead>
            <tr>
              <th>#</th>
              <th className="route-th-wide">Stop</th>
              <th>Leg</th>
              <th>Total</th>
              <th title="Elevation at this stop minus elevation at the previous stop; positive uphill, negative downhill">Elevation change</th>
              <th>Order</th>
            </tr>
          </thead>
          <tbody>
            {route.waypoints.map((wp, i) => {
              const editable = i > 0 && !(isLoop && i === route.waypoints.length - 1);
              const change = i > 0 ? elevationChange(elevations, route.waypoints[i - 1], wp) : null;
              return (
                <tr key={i} className={active === i ? 'route-row--active' : ''} tabIndex={0}
                  data-wtype={editable ? 'stop' : 'base'} draggable={editable}
                  onDragStart={event => { if (!editable) return; event.dataTransfer.setData(DRAG_TYPE, String(i - 1)); event.dataTransfer.effectAllowed = 'move'; }}
                  onDragOver={event => { if (editable && event.dataTransfer.types.includes(DRAG_TYPE)) { event.preventDefault(); event.dataTransfer.dropEffect = 'move'; } }}
                  onDrop={event => { event.preventDefault(); const from = event.dataTransfer.getData(DRAG_TYPE); if (editable && from !== '') onWaypointMove(Number(from), i - 1); }}
                  onMouseEnter={() => setActive(i)} onMouseLeave={() => setActive(null)}
                  onClick={() => focus(i)}
                  onKeyDown={e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); focus(i); } }}>
                  <td className="route-idx">{i}</td>
                  <td className="route-name-cell">
                    <span className="route-dot" style={{ background: colorOf(i) }} />
                    <span>
                      {wp.name}
                      <span className="route-location-details">
                        <span className="route-coordinates">{wp.latitude_deg.toFixed(4)}°, {wp.longitude_deg.toFixed(4)}°</span>
                        {editable && <button className="ct-btn" aria-label={`Remove waypoint ${i}`}
                          onClick={event => { event.stopPropagation(); onWaypointRemove(i - 1); }}
                          onKeyDown={event => event.stopPropagation()}>Remove</button>}
                      </span>
                      {wp.group && <span className="route-note">{wp.group}</span>}
                    </span>
                  </td>
                  <td className="route-num" title={i && route.failed_legs?.includes(i - 1) ? route.legs[i - 1]?.reason ?? undefined : undefined}>
                    {i && calculated ? (route.failed_legs?.includes(i - 1) ? 'no route'
                      : route.legs[i - 1]?.distance_m != null ? km(route.legs[i - 1].distance_m) : '—') : '—'}</td>
                  <td className="route-num">{calculated && cumulative[i] != null ? km(cumulative[i]!) : '—'}</td>
                  <td className="route-num">{change === null ? '—' : `${change > 0 ? '+' : ''}${Math.round(change)} m`}</td>
                  <td>{editable ? <div className="route-order-controls" onClick={event => event.stopPropagation()} onKeyDown={event => event.stopPropagation()}>
                    <span className="route-drag-handle" aria-hidden="true">⠿</span>
                    <button className="ct-btn" aria-label={`Move stop ${i} up`} disabled={i === 1} onClick={() => onWaypointMove(i - 1, i - 2)}>↑</button>
                    <button className="ct-btn" aria-label={`Move stop ${i} down`} disabled={i === route.waypoints.length - 2} onClick={() => onWaypointMove(i - 1, i)}>↓</button>
                  </div> : i === 0 ? 'Start' : 'Return'}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
        {sidePanel}
      </div>
    </div>
  );
}
