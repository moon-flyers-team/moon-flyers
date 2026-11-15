import { useEffect, useId, useMemo, useRef, useState } from 'react';
import { project, MAP_CENTER, MAP_RADIUS, METRES_TO_SVG } from './map/projection';
import { zoomAt, panBy, wheelAction, MAX_ZOOM } from './map/navigation';
import type { MapCamera } from './map/navigation';
import type { TouristRoute, RouteWaypoint } from './types';

// Same tile grid as MapPanel (NASA WMTS level 4, south-polar cap)
const TILES = Array.from({ length: 36 }, (_, i) => {
  const row = 5 + Math.floor(i / 6), col = 5 + i % 6;
  const span = 136_991.25;
  return {
    row, col,
    x: MAP_CENTER + (-1_095_930 + col * span) * METRES_TO_SVG,
    y: MAP_CENTER - (1_095_930 - row * span) * METRES_TO_SVG,
    size: span * METRES_TO_SVG,
  };
});

function fitCamera(wps: RouteWaypoint[]): MapCamera {
  if (!wps.length) return { x: MAP_CENTER, y: MAP_CENTER, zoom: 1 };
  const pts = wps.map(w => project({ latitude_deg: w.lat, longitude_deg: w.lon }));
  const xs = pts.map(p => p.x), ys = pts.map(p => p.y);
  const cx = (Math.min(...xs) + Math.max(...xs)) / 2;
  const cy = (Math.min(...ys) + Math.max(...ys)) / 2;
  const halfSpan = Math.max(
    (Math.max(...xs) - Math.min(...xs)) / 2,
    (Math.max(...ys) - Math.min(...ys)) / 2,
    5
  );
  const zoom = Math.min(MAX_ZOOM, Math.max(1, MAP_CENTER / (halfSpan + 25)));
  return { x: cx, y: cy, zoom };
}

function segColor(wp: RouteWaypoint): string {
  if (wp.eclipse) return '#b388ff';
  if (wp.sun_visible && wp.earth_visible) return '#00e676';
  if (wp.sun_visible) return '#f5a623';
  if (wp.earth_visible) return '#4fc3f7';
  return '#484860';
}

function download(content: string, filename: string, mime: string) {
  const a = document.createElement('a');
  a.href = URL.createObjectURL(new Blob([content], { type: mime }));
  a.download = filename;
  a.click();
}

function toKml(r: TouristRoute) {
  const slug = r.site.name.replace(/\s+/g, '_');
  const track = r.waypoints.map(w => `${w.lon},${w.lat},0`).join(' ');
  const marks = r.waypoints.map(w => `
    <Placemark>
      <name>${w.index}: ${w.label}</name>
      <description><![CDATA[Type: ${w.type}<br/>Arrival: ${w.arrival_utc}<br/>Departure: ${w.departure_utc}<br/>Sun visible: ${w.sun_visible}<br/>Earth contact: ${w.earth_visible}<br/>Earth eclipse: ${w.eclipse}<br/>Slope: ${w.slope_deg ?? '—'}°<br/>Leg: ${w.leg_distance_km ?? '—'} km<br/>${w.notes}]]></description>
      <Point><coordinates>${w.lon},${w.lat},0</coordinates></Point>
    </Placemark>`).join('');
  return `<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2">
  <Document>
    <name>${slug} Tourist Route</name>
    <description>Site: ${r.site.name} | Landing: ${r.landing_utc} | ${r.days_on_surface} days | ${r.total_distance_km.toFixed(1)} km</description>
    <Style id="track"><LineStyle><color>ff76e600</color><width>3</width></LineStyle></Style>
    <Placemark>
      <name>Route Track</name><styleUrl>#track</styleUrl>
      <LineString><tessellate>1</tessellate><coordinates>${track}</coordinates></LineString>
    </Placemark>${marks}
  </Document>
</kml>`;
}

function toCsv(r: TouristRoute) {
  const hdr = 'index,label,type,arrival_utc,departure_utc,latitude_deg,longitude_deg,leg_distance_km,slope_deg,sun_visible,earth_visible,eclipse,notes';
  const rows = r.waypoints.map(w =>
    [w.index, `"${w.label}"`, w.type, w.arrival_utc, w.departure_utc,
     w.lat.toFixed(6), w.lon.toFixed(6),
     w.leg_distance_km ?? '', w.slope_deg ?? '',
     w.sun_visible, w.earth_visible, w.eclipse,
     `"${w.notes}"`].join(','));
  return [hdr, ...rows].join('\r\n');
}

// --- placeholder mock ---
const MOCK_ROUTE: TouristRoute = {
  site: { id: 'shackleton', name: 'Shackleton Rim', latitude_deg: -89.54, longitude_deg: 0 },
  landing_utc:    '2027-08-15T06:00:00Z',
  departure_utc:  '2027-08-29T06:00:00Z',
  days_on_surface: 14,
  total_distance_km: 38.4,
  eclipse_windows: [{ start_utc: '2027-08-20T12:00:00Z', end_utc: '2027-08-20T15:30:00Z' }],
  waypoints: [
    { index: 0, lat: -89.54, lon: 0,    label: 'Base Camp',           arrival_utc: '2027-08-15T06:00:00Z', departure_utc: '2027-08-16T08:00:00Z', type: 'base',     sun_visible: true,  earth_visible: true,  eclipse: false, slope_deg: 3.2, leg_distance_km: null, notes: 'Landing + setup' },
    { index: 1, lat: -89.48, lon: 60,   label: 'Crater Rim Overlook', arrival_utc: '2027-08-16T16:00:00Z', departure_utc: '2027-08-17T10:00:00Z', type: 'poi',      sun_visible: true,  earth_visible: true,  eclipse: false, slope_deg: 5.1, leg_distance_km: 7.2, notes: 'Shackleton crater edge' },
    { index: 2, lat: -89.44, lon: 120,  label: 'Camp 1',              arrival_utc: '2027-08-17T20:00:00Z', departure_utc: '2027-08-19T08:00:00Z', type: 'camp',     sun_visible: false, earth_visible: true,  eclipse: false, slope_deg: 2.8, leg_distance_km: 6.1, notes: 'Overnight rest' },
    { index: 3, lat: -89.4,  lon: 180,  label: 'Ridge Traverse',      arrival_utc: '2027-08-19T18:00:00Z', departure_utc: '2027-08-20T09:00:00Z', type: 'waypoint', sun_visible: true,  earth_visible: false, eclipse: false, slope_deg: 7.4, leg_distance_km: 5.8, notes: '' },
    { index: 4, lat: -89.46, lon: -120, label: 'Eclipse Watch Point',  arrival_utc: '2027-08-20T11:00:00Z', departure_utc: '2027-08-21T10:00:00Z', type: 'poi',      sun_visible: true,  earth_visible: true,  eclipse: true,  slope_deg: 2.1, leg_distance_km: 6.4, notes: 'Earth eclipse 12:00–15:30 UTC' },
    { index: 5, lat: -89.5,  lon: -60,  label: 'Lava Tube Entrance',  arrival_utc: '2027-08-22T12:00:00Z', departure_utc: '2027-08-23T18:00:00Z', type: 'poi',      sun_visible: true,  earth_visible: true,  eclipse: false, slope_deg: 1.5, leg_distance_km: 8.9, notes: 'Exploration stop' },
    { index: 6, lat: -89.54, lon: 0,    label: 'Base Camp',           arrival_utc: '2027-08-29T06:00:00Z', departure_utc: '2027-08-29T06:00:00Z', type: 'base',     sun_visible: true,  earth_visible: true,  eclipse: false, slope_deg: 3.2, leg_distance_km: 4.0, notes: 'Return — ascent prep' },
  ],
};

const LEGEND: [string, string][] = [
  ['#00e676', 'Sun + Earth'],
  ['#f5a623', 'Sun only'],
  ['#4fc3f7', 'Earth only'],
  ['#484860', 'Neither'],
];

interface Props {
  route?: TouristRoute | null;
  loading?: boolean;
  error?: string;
}

export function TouristRoutePanel({ route: routeProp, loading, error }: Props) {
  const isMock = !routeProp;
  const route  = routeProp ?? MOCK_ROUTE;
  const clipId = useId();
  const svgRef = useRef<SVGSVGElement>(null);
  const drag   = useRef<{ pointerId: number; x: number; y: number } | null>(null);
  const [panning, setPanning] = useState(false);

  const initCamera = useMemo(() => fitCamera(route.waypoints), [route]);
  const [camera, setCamera] = useState<MapCamera>(initCamera);
  useEffect(() => { setCamera(fitCamera(route.waypoints)); }, [route]);

  const { zoom } = camera;
  const halfView = MAP_CENTER / zoom;

  const pts = useMemo(
    () => route.waypoints.map(w => project({ latitude_deg: w.lat, longitude_deg: w.lon })),
    [route]
  );

  // Non-passive wheel listener
  useEffect(() => {
    const svg = svgRef.current;
    if (!svg) return;
    const onWheel = (e: WheelEvent) => {
      e.preventDefault();
      const matrix = svg.getScreenCTM();
      if (!matrix) return;
      const inv = matrix.inverse();
      const anchor = new DOMPoint(e.clientX, e.clientY).matrixTransform(inv);
      const px = Math.hypot(inv.a, inv.b);
      const m  = e.deltaMode === 1 ? 16 : e.deltaMode === 2 ? svg.clientHeight : 1;
      if (wheelAction(e) === 'pan') {
        setCamera(c => panBy(c, e.deltaX * m * px, e.deltaY * m * px));
      } else {
        setCamera(c => zoomAt(c, Math.exp(-e.deltaY * m * 0.002), anchor));
      }
    };
    svg.addEventListener('wheel', onWheel, { passive: false });
    return () => svg.removeEventListener('wheel', onWheel);
  }, []);

  function stopPanning() { drag.current = null; setPanning(false); }

  const slug = route.site.name.replace(/\s+/g, '_');

  if (loading) return <div className="route-empty"><span>Generating route…</span></div>;
  if (error)   return <div className="route-empty route-empty--err"><span>{error}</span></div>;

  return (
    <div className="route-wrap">
      {isMock && (
        <div className="route-mock-banner">
          Sample route — connect the route API to show real data
        </div>
      )}

      <div className="route-hdr">
        <div className="route-stats">
          <span className="route-stat route-stat--name">{route.site.name}</span>
          <span className="route-stat">{route.days_on_surface} days on surface</span>
          <span className="route-stat">{route.total_distance_km.toFixed(1)} km total</span>
          <span className="route-stat">{route.waypoints.length} waypoints</span>
          {route.eclipse_windows.length > 0 && (
            <span className="route-stat route-stat--eclipse">
              {route.eclipse_windows.length} Earth eclipse{route.eclipse_windows.length !== 1 ? 's' : ''}
            </span>
          )}
        </div>
        <div className="route-actions">
          <button className="ct-btn" onClick={() => download(toKml(route), `${slug}_route.kml`, 'application/vnd.google-earth.kml+xml')}>Download KML</button>
          <button className="ct-btn" onClick={() => download(toCsv(route), `${slug}_route.csv`, 'text/csv')}>Download CSV</button>
        </div>
      </div>

      <div className="route-body">

        {/* Map */}
        <div className="route-map-wrap">
          <div className="route-map-controls">
            <button className="ct-btn" aria-label="Zoom in"  disabled={zoom >= MAX_ZOOM} onClick={() => setCamera(c => zoomAt(c, 2, c))}>+</button>
            <button className="ct-btn" aria-label="Zoom out" disabled={zoom <= 1}       onClick={() => setCamera(c => zoomAt(c, 0.5, c))}>−</button>
            <button className="ct-btn" onClick={() => setCamera(initCamera)}>Fit</button>
          </div>

          <svg
            ref={svgRef}
            className={`route-svg${panning ? ' route-svg--panning' : ''}`}
            viewBox={`${camera.x - halfView} ${camera.y - halfView} ${2*halfView} ${2*halfView}`}
            onContextMenu={e => e.preventDefault()}
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
              const to   = new DOMPoint(e.clientX, e.clientY).matrixTransform(inv);
              setCamera(c => panBy(c, from.x - to.x, from.y - to.y));
              drag.current = { ...prev, x: e.clientX, y: e.clientY };
            }}
            onPointerUp={e => { if (drag.current?.pointerId === e.pointerId) { e.currentTarget.releasePointerCapture(e.pointerId); stopPanning(); } }}
            onPointerCancel={stopPanning}
            onLostPointerCapture={stopPanning}
          >
            <defs>
              <clipPath id={clipId}>
                <circle cx={MAP_CENTER} cy={MAP_CENTER} r={MAP_RADIUS} />
              </clipPath>
            </defs>
            <circle cx={MAP_CENTER} cy={MAP_CENTER} r={MAP_RADIUS} fill="#191d29" />
            <g clipPath={`url(#${clipId})`}>
              {/* Real Moon surface tiles (same as MapPanel) */}
              {TILES.map(t => (
                <image key={`${t.row}-${t.col}`}
                  href={`/maps/south-pole/${t.row}-${t.col}.png`}
                  x={t.x} y={t.y} width={t.size + 0.02} height={t.size + 0.02} />
              ))}
              {/* Route path segments */}
              {pts.slice(1).map((pt, i) => (
                <line key={i}
                  x1={pts[i].x} y1={pts[i].y} x2={pt.x} y2={pt.y}
                  stroke={segColor(route.waypoints[i + 1])}
                  strokeWidth={2 / zoom}
                  strokeLinecap="round"
                  strokeDasharray={route.waypoints[i + 1].eclipse ? `${6/zoom} ${3/zoom}` : undefined} />
              ))}
              {/* Waypoint markers */}
              {pts.map((pt, i) => {
                const wp  = route.waypoints[i];
                const col = segColor(wp);
                const r   = (wp.type === 'base' ? 5 : wp.type === 'camp' ? 4 : 3) / zoom;
                return (
                  <g key={i}>
                    {wp.type === 'base' && (
                      <circle cx={pt.x} cy={pt.y} r={r + 4/zoom} fill="none" stroke={col} strokeWidth={1/zoom} opacity={0.4} />
                    )}
                    <circle cx={pt.x} cy={pt.y} r={r} fill={wp.type === 'base' ? '#ddddf8' : col} />
                    <text x={pt.x + (r + 2/zoom)} y={pt.y + 3/zoom}
                      fontSize={8/zoom} fill="white"
                      stroke="#191d29" strokeWidth={2.5/zoom} paintOrder="stroke">{wp.label}</text>
                  </g>
                );
              })}
            </g>
          </svg>

          <div className="route-legend">
            {LEGEND.map(([color, label]) => (
              <span key={label} className="route-legend-item">
                <span className="route-legend-dot" style={{ background: color }} />
                {label}
              </span>
            ))}
          </div>
        </div>

        {/* Waypoint table */}
        <div className="route-table-wrap">
          <table className="route-table">
            <thead>
              <tr>
                <th>#</th>
                <th className="route-th-wide">Waypoint</th>
                <th>Arrival UTC</th>
                <th>Leg</th>
                <th title="Sun visible">Sun</th>
                <th title="Earth visible">Earth</th>
                <th>Slope</th>
              </tr>
            </thead>
            <tbody>
              {route.waypoints.map((wp, i) => (
                <tr key={i} data-wtype={wp.type} className={wp.eclipse ? 'route-row--eclipse' : ''}>
                  <td className="route-idx">{i}</td>
                  <td className="route-name-cell">
                    <span className="route-dot" style={{ background: segColor(wp) }} />
                    <span>
                      {wp.label}
                      {wp.notes && <span className="route-note">{wp.notes}</span>}
                    </span>
                  </td>
                  <td className="route-time">{wp.arrival_utc.slice(5, 16).replace('T', ' ')}</td>
                  <td className="route-num">{wp.leg_distance_km != null ? `${wp.leg_distance_km.toFixed(1)} km` : '—'}</td>
                  <td className={wp.sun_visible ? 'vis-on' : 'vis-off'}>{wp.sun_visible ? '●' : '○'}</td>
                  <td className={wp.eclipse ? 'vis-eclipse' : wp.earth_visible ? 'vis-on' : 'vis-off'}>{wp.earth_visible || wp.eclipse ? '●' : '○'}</td>
                  <td className="route-num">{wp.slope_deg != null ? `${wp.slope_deg}°` : '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

      </div>
    </div>
  );
}
