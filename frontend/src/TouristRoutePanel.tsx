import { useCallback, useEffect, useId, useMemo, useRef, useState } from 'react';
import type { ReactNode } from 'react';
import { project, MAP_CENTER, MAP_RADIUS, METRES_TO_SVG } from './map/projection';
import type { MapPoint } from './map/projection';
import { zoomAt, panBy } from './map/navigation';
import type { MapCamera } from './map/navigation';
import { ROUTE_LAYERS, visibleTiles } from './map/routeTiles';
import type { RouteLayer } from './map/routeTiles';
import { FitBadge } from './FitBadge';
import { formatUtc } from './time';
import type { FitStatus, Recommendation, RouteResponse } from './types';

const MAX_ZOOM = 600;
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

const FIT_COLOR: Record<FitStatus, string> = {
  both_met: '#00e676',
  power_short: '#f5a623',
  comms_short: '#4fc3f7',
  neither_met: '#8a8aa8',
};
const UNKNOWN_COLOR = '#ddddf8';
const LEGEND: [string, string][] = [
  [FIT_COLOR.both_met, 'Power + comms met'],
  [FIT_COLOR.power_short, 'Power short'],
  [FIT_COLOR.comms_short, 'Comms short'],
  [FIT_COLOR.neither_met, 'Neither met'],
];

function fitCamera(pts: MapPoint[]): MapCamera {
  if (!pts.length) return { x: MAP_CENTER, y: MAP_CENTER, zoom: 1 };
  const xs = pts.map(p => p.x), ys = pts.map(p => p.y);
  const halfSpan = Math.max(
    (Math.max(...xs) - Math.min(...xs)) / 2,
    (Math.max(...ys) - Math.min(...ys)) / 2,
    0.5,
  );
  return {
    x: (Math.min(...xs) + Math.max(...xs)) / 2,
    y: (Math.min(...ys) + Math.max(...ys)) / 2,
    zoom: Math.min(MAX_ZOOM, Math.max(1, MAP_CENTER / (halfSpan * 1.45))),
  };
}

function niceKm(km: number): number {
  const p = 10 ** Math.floor(Math.log10(km));
  return [5, 2, 1].map(m => m * p).find(v => v <= km) ?? p;
}

const km = (m: number) => `${(m / 1000).toFixed(1)} km`;

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
  siteName: string;
  landingUtc: string;
  route?: RouteResponse | null;
  metrics?: Map<string, Recommendation>;
  loading: boolean;
  error?: string;
  onRetry: () => void;
  onClose: () => void;
}

export function TouristRoutePanel({ siteName, landingUtc, route, metrics, loading, error, onRetry, onClose }: Props) {
  const slug = siteName.replace(/\s+/g, '_');
  let body: ReactNode;
  if (error) body = <div className="request-error" role="alert">Route request failed: {error} <button className="ct-btn" onClick={onRetry}>Retry</button></div>;
  else if (loading) body = <p className="request-status route-status" role="status">Planning route…</p>;
  else if (!route) body = <p className="request-status route-status" role="status">No recommended sites within 150 km of {siteName} to visit.</p>;
  else body = <RouteView route={route} metrics={metrics} />;

  return (
    <section className="route-wrap" aria-label="Tourist route" aria-busy={loading}>
      <div className="route-hdr">
        <div className="route-title">
          <span className="route-kicker">Tourist route</span>
          <strong>{siteName}</strong>
          <span className="route-sub">Landing {formatUtc(landingUtc)}</span>
        </div>
        <div className="route-stats">
          {route && <>
            <span className="route-stat">{km(route.total_distance_m)}</span>
            <span className="route-stat">{route.waypoints.length - 2} stop{route.waypoints.length !== 3 ? 's' : ''}</span>
          </>}
        </div>
        <div className="route-actions">
          {route && <>
            <button className="ct-btn" onClick={() => download(toKml(route, siteName), `${slug}_route.kml`, 'application/vnd.google-earth.kml+xml')}>KML</button>
            <button className="ct-btn" onClick={() => download(toCsv(route), `${slug}_route.csv`, 'text/csv')}>CSV</button>
          </>}
          <button className="ct-btn route-close" aria-label="Close tourist route" onClick={onClose}>✕</button>
        </div>
      </div>
      {route?.method === 'straight_line' && (
        <div className="route-mock-banner">
          Straight-line route: the planner doesn't consider terrain, slope or shadow yet.
        </div>
      )}
      {body}
    </section>
  );
}

function RouteView({ route, metrics }: { route: RouteResponse; metrics?: Map<string, Recommendation> }) {
  const clipId = useId();
  const svgRef = useRef<SVGSVGElement>(null);
  const drag = useRef<{ pointerId: number; x: number; y: number } | null>(null);
  const [panning, setPanning] = useState(false);
  const [layer, setLayer] = useState<RouteLayer>('relief');
  const [active, setActive] = useState<number | null>(null);
  const [px, setPx] = useState(600);

  const stopInfo = (i: number) => {
    const id = route.waypoints[i].id;
    return id ? metrics?.get(id) : undefined;
  };
  const colorOf = (i: number) => {
    const fit = stopInfo(i)?.fit.status;
    return fit ? FIT_COLOR[fit] : UNKNOWN_COLOR;
  };

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

  const fit = useMemo(() => fitCamera(stops), [stops]);
  const [camera, setCamera] = useState<MapCamera>(fit);
  useEffect(() => setCamera(fit), [fit]);

  useEffect(() => {
    const svg = svgRef.current;
    if (!svg) return;
    const ro = new ResizeObserver(([entry]) => {
      const { width, height } = entry.contentRect;
      if (width && height) setPx(Math.max(width, height));
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
      setCamera(c => zoomAt(c, Math.exp(-e.deltaY * m * 0.002), anchor, MAX_ZOOM));
    };
    svg.addEventListener('wheel', onWheel, { passive: false });
    return () => svg.removeEventListener('wheel', onWheel);
  }, []);

  const stopPanning = useCallback(() => { drag.current = null; setPanning(false); }, []);

  const half = MAP_CENTER / camera.zoom;
  const k = (2 * half) / px; // svg units per screen pixel
  const tiles = useMemo(
    () => visibleTiles(layer, { x: camera.x, y: camera.y, half, pxPerSvg: 1 / k }),
    [layer, camera.x, camera.y, half, k],
  );
  const scaleKm = niceKm((px / 5) * k / METRES_TO_SVG / 1000);
  const scalePx = scaleKm * 1000 * METRES_TO_SVG / k;
  const cumulative = route.legs.reduce<number[]>((acc, l) => [...acc, acc[acc.length - 1] + l.distance_m], [0]);
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
          aria-label="Terrain map of the tourist route"
          onContextMenu={e => e.preventDefault()}
          onDoubleClick={e => {
            const inv = e.currentTarget.getScreenCTM()?.inverse();
            if (inv) setCamera(c => zoomAt(c, 2, new DOMPoint(e.clientX, e.clientY).matrixTransform(inv), MAX_ZOOM));
          }}
          onPointerDown={e => {
            if (e.button !== 0 && e.button !== 2) return;
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
              <image key={`${t.row}-${t.col}`} href={`/maps/south-pole/${t.row}-${t.col}.png`}
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
            <path key={i} d={d} fill="none" stroke={colorOf(route.legs[i].to_index)}
              strokeWidth={4.5 * k} strokeLinejoin="round" strokeLinecap="round" />
          ))}
          <path d={fullD} fill="none" stroke="#fff" strokeOpacity={0.85}
            strokeWidth={1.5 * k} strokeDasharray={`${2 * k} ${14 * k}`} strokeLinecap="round">
            {!reducedMotion && <animate attributeName="stroke-dashoffset" from="0" to={-16 * k} dur="0.9s" repeatCount="indefinite" />}
          </path>

          {stops.map((pt, i) => {
            if (isLoop && i === stops.length - 1) return null;
            const base = i === 0;
            const r = (base ? 11 : 9) * k;
            const on = active === i;
            const color = colorOf(i);
            return (
              <g key={i} className="route-marker" onMouseEnter={() => setActive(i)} onMouseLeave={() => setActive(null)}
                onClick={() => focus(i)}>
                {(base || on) && (
                  <circle cx={pt.x} cy={pt.y} r={r + 6 * k} fill="none" stroke={color}
                    strokeWidth={2 * k} opacity={on ? 0.9 : 0.5} />
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

        <div className="route-layers" role="radiogroup" aria-label="Terrain layer">
          {(Object.keys(ROUTE_LAYERS) as RouteLayer[]).map(id => (
            <button key={id} role="radio" aria-checked={layer === id}
              className={`route-layer${layer === id ? ' route-layer--on' : ''}`}
              onClick={() => setLayer(id)}>{ROUTE_LAYERS[id].label}</button>
          ))}
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
          <span className="route-credit">NASA Moon Trek · {ROUTE_LAYERS[layer].credit}</span>
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
              <th title="Sunlight over the stay">Sun</th>
              <th title="Earth contact over the stay">Earth</th>
              <th>Fit</th>
            </tr>
          </thead>
          <tbody>
            {route.waypoints.map((wp, i) => {
              const info = stopInfo(i);
              return (
                <tr key={i} className={active === i ? 'route-row--active' : ''} tabIndex={0}
                  data-wtype={i === 0 || (isLoop && i === route.waypoints.length - 1) ? 'base' : 'stop'}
                  onMouseEnter={() => setActive(i)} onMouseLeave={() => setActive(null)}
                  onClick={() => focus(i)}
                  onKeyDown={e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); focus(i); } }}>
                  <td className="route-idx">{i}</td>
                  <td className="route-name-cell">
                    <span className="route-dot" style={{ background: colorOf(i) }} />
                    <span>
                      {wp.name}
                      {wp.group && <span className="route-note">{wp.group}</span>}
                    </span>
                  </td>
                  <td className="route-num">{i ? km(route.legs[i - 1].distance_m) : '—'}</td>
                  <td className="route-num">{km(cumulative[i])}</td>
                  <td className="route-num">{info ? `${info.metrics.sun_visible_pct}%` : '—'}</td>
                  <td className="route-num">{info ? `${info.metrics.earth_visible_pct}%` : '—'}</td>
                  <td>{info ? <FitBadge fit={info.fit.status} /> : '—'}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
