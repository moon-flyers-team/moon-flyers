import { useEffect, useId, useMemo, useRef, useState } from 'react';
import { api } from './api';
import { useRequest } from './useRequest';
import { dateUtc } from './time';
import type { Constraints, HeatmapCriterion, LandingSite, MapHeatmapsParams, MapHeatmapsResponse, MissionParams } from './types';
import { CAP_RADIUS_M, distanceMetres, MAP_CENTER, MAP_RADIUS, METRES_TO_SVG, NORTH_LIMIT, project, unproject } from './map/projection';
import type { Coordinates, MapPoint } from './map/projection';
import { HEATMAPS, rasterPixels, validateHeatmaps } from './map/heatmaps';
import features from './map/features.json';
import { INITIAL_CAMERA, MAX_ZOOM, panBy, wheelAction, zoomAt } from './map/navigation';
import { TopographicContours } from './map/TopographicContours';

interface Props {
  sites: LandingSite[];
  constraints: Constraints;
  mission: MissionParams;
  active: boolean;
  validation: string;
  showValidation?: boolean;
  onSiteAdd: (coordinates: Coordinates, name: string) => void;
  onSiteRename: (id: string, name: string) => void;
  onSiteDelete: (id: string) => void;
}
function featureAt(coordinates: Coordinates) {
  // Gazetteer diameters give approximate circular footprints, not surveyed boundaries.
  return features.filter(feature => distanceMetres(coordinates, feature) <= feature.diameter_km * 500)
    .sort((a, b) => a.diameter_km - b.diameter_km)[0];
}
const formatCoordinates = (coordinates: Coordinates | null) => coordinates
  ? `${coordinates.latitude_deg.toFixed(4)}°, ${coordinates.longitude_deg.toFixed(4)}°` : '—.—°, —.—°';
const TILES = Array.from({ length: 36 }, (_, index) => {
  const row = 5 + Math.floor(index / 6), column = 5 + index % 6;
  // NASA WMTS level 4: 535.1220703125 m/px, 256 px/tile, top-left (-1095930,1095930).
  const span = 136_991.25;
  return { row, column, x: MAP_CENTER + (-1_095_930 + column * span) * METRES_TO_SVG,
    y: MAP_CENTER - (1_095_930 - row * span) * METRES_TO_SVG, size: span * METRES_TO_SVG };
});
function HeatmapImages({ data, opacity }: { data?: MapHeatmapsResponse; opacity: number }) {
  const [rendered, setRendered] = useState<{ data: MapHeatmapsResponse; urls: string[] }>();
  useEffect(() => {
    if (!data) return;
    const urls = data.layers.map(layer => {
      const canvas = document.createElement('canvas');
      canvas.width = data.width;
      canvas.height = data.height;
      const context = canvas.getContext('2d');
      if (!context) return '';
      const image = context.createImageData(data.width, data.height);
      image.data.set(rasterPixels(layer));
      context.putImageData(image, 0, 0);
      return canvas.toDataURL();
    });
    setRendered({ data, urls });
  }, [data]);
  if (!data || rendered?.data !== data) return null;
  return <g opacity={opacity}>{rendered.urls.map((url, index) => url && <image key={data.layers[index].criterion}
    href={url} x={MAP_CENTER - MAP_RADIUS} y={MAP_CENTER - MAP_RADIUS}
    width={2 * MAP_RADIUS} height={2 * MAP_RADIUS} preserveAspectRatio="none" />)}</g>;
}

export function MapPanel({ sites, constraints, mission, active, validation, showValidation = true, onSiteAdd, onSiteRename, onSiteDelete }: Props) {
  const clipId = useId();
  const svgRef = useRef<SVGSVGElement>(null);
  const viewportRef = useRef<HTMLDivElement>(null);
  const nameRef = useRef<HTMLInputElement>(null);
  const [criteria, setCriteria] = useState<HeatmapCriterion[]>([]);
  const [opacity, setOpacity] = useState(0.65);
  const [camera, setCamera] = useState(INITIAL_CAMERA);
  const { zoom } = camera;
  const drag = useRef<{ pointerId: number; x: number; y: number } | null>(null);
  const [panning, setPanning] = useState(false);
  const [hover, setHover] = useState<Coordinates | null>(null);
  const [selection, setSelection] = useState<{ coordinates: Coordinates; left: number; top: number; siteId?: string } | null>(null);
  const editingSite = selection?.siteId ? sites.find(site => site.id === selection.siteId && site.custom) : undefined;
  const [name, setName] = useState('');
  const [announcement, setAnnouncement] = useState('');
  const [imageError, setImageError] = useState(false);
  const [basemap, setBasemap] = useState<'satellite' | 'topography'>('satellite');
  const [contourError, setContourError] = useState('');
  const [keyboardPoint, setKeyboardPoint] = useState<MapPoint>({ x: MAP_CENTER, y: MAP_CENTER });
  const [keyboardFocus, setKeyboardFocus] = useState(false);
  const hoverFeature = hover ? featureAt(hover) : undefined;
  const params = useMemo<MapHeatmapsParams>(() => ({
    projection: 'lunar_south_polar_stereographic', bounds_m: [-CAP_RADIUS_M, -CAP_RADIUS_M, CAP_RADIUS_M, CAP_RADIUS_M],
    width: 128, height: 128, window_start_utc: dateUtc(mission.windowStart), window_end_utc: dateUtc(mission.windowEnd),
    constraints, criteria,
  }), [mission.windowStart, mission.windowEnd, constraints, criteria]);
  const request = useMemo(() => !active || validation || !criteria.length ? null : async (signal: AbortSignal) =>
    validateHeatmaps(await api.getMapHeatmaps(params, signal), params), [active, validation, criteria.length, params]);
  const heatmaps = useRequest(request);
  const outside = sites.filter(site => site.latitude_deg > NORTH_LIMIT || site.latitude_deg < -90);
  const halfView = 350 / zoom;

  useEffect(() => { if (selection) nameRef.current?.focus(); }, [selection]);
  useEffect(() => { if (!active) { setSelection(null); setHover(null); } }, [active]);
  useEffect(() => {
    const svg = svgRef.current;
    if (!svg || !active) return;
    let lastPan = -Infinity;
    const wheel = (event: WheelEvent) => {
      event.preventDefault();
      const matrix = svg.getScreenCTM();
      if (!matrix) return;
      const inverse = matrix.inverse();
      const anchor = new DOMPoint(event.clientX, event.clientY).matrixTransform(inverse);
      const pixelScale = Math.hypot(inverse.a, inverse.b);
      const multiplier = event.deltaMode === 1 ? 16 : event.deltaMode === 2 ? svg.clientHeight : 1;
      const dx = event.deltaX * multiplier, dy = event.deltaY * multiplier;
      const forceZoom = event.ctrlKey || event.metaKey;
      const action = !forceZoom && event.timeStamp - lastPan < 180 ? 'pan' : wheelAction(event);
      if (action === 'pan') {
        lastPan = event.timeStamp;
        setCamera(previous => panBy(previous, dx * pixelScale, dy * pixelScale));
      } else {
        setCamera(previous => zoomAt(previous, Math.exp(-dy * (forceZoom ? 0.01 : 0.002)), anchor));
      }
      setSelection(null);
      setHover(null);
    };
    // Native, non-passive listener prevents page scrolling/browser zoom over the map.
    svg.addEventListener('wheel', wheel, { passive: false });
    // Safari exposes trackpad pinch through GestureEvents rather than Ctrl+wheel.
    let gestureScale = 1;
    const gestureStart = (event: Event) => { event.preventDefault(); gestureScale = 1; };
    const gestureChange = (event: Event) => {
      event.preventDefault();
      const gesture = event as Event & { scale: number; clientX: number; clientY: number };
      const matrix = svg.getScreenCTM();
      if (!matrix || !Number.isFinite(gesture.scale) || gesture.scale <= 0) return;
      const anchor = new DOMPoint(gesture.clientX, gesture.clientY).matrixTransform(matrix.inverse());
      const factor = gesture.scale / gestureScale;
      gestureScale = gesture.scale;
      setCamera(previous => zoomAt(previous, factor, anchor));
      setSelection(null);
      setHover(null);
    };
    svg.addEventListener('gesturestart', gestureStart, { passive: false });
    svg.addEventListener('gesturechange', gestureChange, { passive: false });
    return () => {
      svg.removeEventListener('wheel', wheel);
      svg.removeEventListener('gesturestart', gestureStart);
      svg.removeEventListener('gesturechange', gestureChange);
    };
  }, [active]);

  function choose(coordinates: Coordinates, clientX?: number, clientY?: number, site?: LandingSite) {
    const rect = viewportRef.current?.getBoundingClientRect();
    setSelection({ coordinates, left: rect && clientX !== undefined ? 100 * (clientX - rect.left) / rect.width : 50,
      top: rect && clientY !== undefined ? 100 * (clientY - rect.top) / rect.height : 40, siteId: site?.id });
    setName(site?.name ?? featureAt(coordinates)?.name ?? 'Custom landing site');
    setAnnouncement('');
  }
  function pointerCoordinates(clientX: number, clientY: number) {
    const matrix = svgRef.current?.getScreenCTM();
    if (!matrix) return null;
    const point = new DOMPoint(clientX, clientY).matrixTransform(matrix.inverse());
    return unproject(point);
  }
  function closeSelection() { setSelection(null); svgRef.current?.focus(); }
  function stopPanning() { drag.current = null; setPanning(false); }

  return <section className="map-panel" aria-label="Lunar south pole map">
    <div className="map-toolbar" role="group" aria-label="Map layers and heatmap overlays">
      <label className="map-basemap-select"><span className="map-toolbar-title">Layers</span>
        <select aria-label="Map surface layer" value={basemap} onChange={event => {
          setBasemap(event.target.value as 'satellite' | 'topography');
          setImageError(false);
          setContourError('');
        }}>
          <option value="satellite">Satellite imagery</option>
          <option value="topography">Topography / altitude contours</option>
        </select>
      </label>
      <span className="map-toolbar-title">Heatmaps</span>
      {HEATMAPS.map(option => <label className="map-layer-toggle" key={option.criterion}>
        <input type="checkbox" checked={criteria.includes(option.criterion)} onChange={event => {
          const enabled = event.target.checked;
          setCriteria(previous => HEATMAPS.map(layer => layer.criterion).filter(criterion =>
            criterion === option.criterion ? enabled : previous.includes(criterion)));
        }} />
        <span style={{ color: `rgb(${option.color.join(',')})` }}>{option.label}</span>
      </label>)}
      <label className="map-opacity">Opacity <input type="range" aria-label="Heatmap opacity" min="0" max="1" step="0.05"
        value={opacity} onChange={event => setOpacity(Number(event.target.value))} /></label>
    </div>
    <div className="map-heading"><div><h2>South polar cap</h2><p>80°S–90°S · Polar stereographic · East-positive longitude</p></div>
      <div className="map-zoom" role="group" aria-label="Map zoom">
        <button className="ct-btn" aria-label="Zoom out" disabled={zoom <= 1} onClick={() => { setCamera(previous => zoomAt(previous, 0.5, previous)); setSelection(null); }}>−</button>
        <span>{Number(zoom.toFixed(1))}×</span>
        <button className="ct-btn" aria-label="Zoom in" disabled={zoom >= MAX_ZOOM} onClick={() => { setCamera(previous => zoomAt(previous, 2, previous)); setSelection(null); }}>+</button>
        <button className="ct-btn" onClick={() => { setCamera(INITIAL_CAMERA); setSelection(null); }}>Reset view</button>
      </div>
    </div>
    {showValidation && validation && <p className="request-error" role="alert">{validation}</p>}
    {heatmaps.loading && <p className="request-status" role="status">Calculating overlays for the current mission settings…</p>}
    {heatmaps.error && <p className="request-error" role="alert">
      {/^(404|405|501)\b/.test(heatmaps.error) ? 'Heatmaps unavailable: the backend does not yet implement POST /map/heatmaps.' : `Heatmap request failed: ${heatmaps.error}`}
      {' '}<button className="ct-btn" onClick={heatmaps.retry}>Retry overlays</button>
    </p>}
    {!criteria.length && <p className="map-hint">Click the surface to add a site. Enable a heatmap to request mission-dependent data.</p>}
    <p className="map-hint">Trackpad: pinch to zoom · two-finger scroll to pan. Mouse: wheel to zoom · right-drag to pan. Shift+scroll always pans.</p>
    <div className="map-site-legend"><span className="map-site-key map-site-key--default">Default sites</span><span className="map-site-key map-site-key--custom">Your sites · click to edit</span></div>
    {basemap === 'topography' && <p className="map-hint">LOLA elevation, relative to the 1,737.4 km lunar reference radius · 500 m contour interval. Shading shows terrain relief.</p>}
    {imageError && <p className="request-error" role="alert">Some local basemap tiles could not load. Coordinates and grid remain available.</p>}
    {basemap === 'topography' && contourError && <p className="request-error" role="alert">{contourError} The elevation basemap remains available.</p>}
    <div className="map-viewport" ref={viewportRef}>
      <svg ref={svgRef} className={`polar-map${panning ? ' polar-map--panning' : ''}`} viewBox={`${camera.x - halfView} ${camera.y - halfView} ${2 * halfView} ${2 * halfView}`}
        tabIndex={0} role="img" aria-label="Lunar south-pole surface map. Arrow keys move the cursor; Enter opens Add site; Escape closes it."
        onFocus={event => { if (event.target === event.currentTarget) { setKeyboardFocus(true); setKeyboardPoint({x: camera.x, y: camera.y}); setHover(unproject(camera)); } }} onBlur={() => setKeyboardFocus(false)}
        onContextMenu={event => event.preventDefault()}
        onPointerDown={event => {
          if (event.button !== 2 && event.button !== 1) return;
          event.preventDefault();
          event.currentTarget.setPointerCapture(event.pointerId);
          drag.current = { pointerId: event.pointerId, x: event.clientX, y: event.clientY };
          setPanning(true);
          setSelection(null);
        }}
        onPointerMove={event => {
          const previous = drag.current;
          if (previous && previous.pointerId === event.pointerId) {
            const inverse = event.currentTarget.getScreenCTM()?.inverse();
            if (!inverse) return;
            const from = new DOMPoint(previous.x, previous.y).matrixTransform(inverse);
            const to = new DOMPoint(event.clientX, event.clientY).matrixTransform(inverse);
            setCamera(value => panBy(value, from.x - to.x, from.y - to.y));
            drag.current = { pointerId: event.pointerId, x: event.clientX, y: event.clientY };
            setHover(null);
          } else setHover(pointerCoordinates(event.clientX, event.clientY));
        }}
        onPointerUp={event => { if (drag.current?.pointerId === event.pointerId) { event.currentTarget.releasePointerCapture(event.pointerId); stopPanning(); } }}
        onPointerCancel={stopPanning} onLostPointerCapture={stopPanning}
        onPointerLeave={() => setHover(null)}
        onClick={event => { if (event.button !== 0) return; const coordinates = pointerCoordinates(event.clientX, event.clientY); if (coordinates) choose(coordinates, event.clientX, event.clientY); }}
        onKeyDown={event => {
          if (event.key === 'Escape') { setSelection(null); return; }
          if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); const coordinates = unproject(keyboardPoint); if (coordinates) choose(coordinates); return; }
          const delta = { ArrowLeft: [-1, 0], ArrowRight: [1, 0], ArrowUp: [0, -1], ArrowDown: [0, 1] }[event.key];
          if (!delta) return;
          event.preventDefault();
          const next = { x: keyboardPoint.x + delta[0] * 5 / zoom, y: keyboardPoint.y + delta[1] * 5 / zoom };
          const coordinates = unproject(next);
          if (coordinates) { setKeyboardPoint(next); setHover(coordinates); }
        }}>
        <defs><clipPath id={clipId}><circle cx={MAP_CENTER} cy={MAP_CENTER} r={MAP_RADIUS} /></clipPath></defs>
        <circle cx={MAP_CENTER} cy={MAP_CENTER} r={MAP_RADIUS} fill="#252630" />
        <g clipPath={`url(#${clipId})`}>
          {TILES.map(tile => <image key={`${basemap}-${tile.row}-${tile.column}`} href={`/maps/south-pole/${basemap === 'topography' ? 'topography/' : ''}${tile.row}-${tile.column}.png`}
            x={tile.x} y={tile.y} width={tile.size + 0.02} height={tile.size + 0.02} onError={() => setImageError(true)} />)}
          <HeatmapImages data={heatmaps.data} opacity={opacity} />
          <TopographicContours enabled={active && basemap === 'topography'} onError={setContourError} />
          <g className="map-grid">
            {[-88, -86, -84, -82, -80].map(latitude => <circle key={latitude} cx={MAP_CENTER} cy={MAP_CENTER}
              r={MAP_CENTER - project({ latitude_deg: latitude, longitude_deg: 0 }).y} />)}
            {Array.from({ length: 12 }, (_, index) => index * 30).map(longitude => {
              const point = project({ latitude_deg: NORTH_LIMIT, longitude_deg: longitude });
              return <line key={longitude} x1={MAP_CENTER} y1={MAP_CENTER} x2={point.x} y2={point.y} />;
            })}
          </g>
          <g className="map-grid-labels">{[-88, -86, -84, -82, -80].map(latitude => {
            const point = project({ latitude_deg: latitude, longitude_deg: 0 });
            return <text key={latitude} x={point.x + 4 / zoom} y={point.y + 12 / zoom} fontSize={10 / zoom}>{Math.abs(latitude)}°S</text>;
          })}</g>
          {features.filter(feature => feature.diameter_km > 20).map(feature => {
            const point = project(feature);
            return <text className="map-feature-label" key={feature.name} x={point.x} y={point.y} fontSize={9 / zoom} textAnchor="middle">{feature.name}</text>;
          })}
          {sites.filter(site => !outside.includes(site)).map(site => {
            const point = project(site);
            return <g key={site.id} className={`map-waypoint ${site.custom ? 'map-waypoint--custom' : 'map-waypoint--default'} ${site.enabled ? '' : 'map-waypoint--disabled'}`}
              role={site.custom ? 'button' : undefined} tabIndex={site.custom ? 0 : undefined}
              aria-label={site.custom ? `Edit site ${site.name}` : undefined}
              onClick={site.custom ? event => { if (event.button !== 0) return; event.stopPropagation(); choose(site, event.clientX, event.clientY, site); } : undefined}
              onKeyDown={site.custom ? event => { if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); event.stopPropagation(); choose(site, undefined, undefined, site); } } : undefined}>
              <title>{`${site.name}: ${formatCoordinates(site)}${site.enabled ? '' : ' (disabled)'}`}</title>
              {site.custom && <circle className="map-waypoint-hit" cx={point.x} cy={point.y} r={11 / zoom} />}
              <circle cx={point.x} cy={point.y} r={5 / zoom} />
              <text x={point.x + 8 / zoom} y={point.y - 8 / zoom} fontSize={10 / zoom}>{site.name}</text>
            </g>;
          })}
          {selection && (() => { const p = project(selection.coordinates); return <circle className="map-pick" cx={p.x} cy={p.y} r={8 / zoom} />; })()}
          {keyboardFocus && <path d={`M ${keyboardPoint.x - 7 / zoom} ${keyboardPoint.y} h ${14 / zoom} M ${keyboardPoint.x} ${keyboardPoint.y - 7 / zoom} v ${14 / zoom}`} stroke="white" vectorEffect="non-scaling-stroke" />}
        </g>
        {['0°E', '90°E', '180°', '90°W'].map((label, i) => <text key={label}
          x={MAP_CENTER + Math.sin(i * Math.PI / 2) * 322} y={MAP_CENTER - Math.cos(i * Math.PI / 2) * 322}
          textAnchor="middle" dominantBaseline="middle" className="map-compass">{label}</text>)}
      </svg>
      {basemap === 'topography' && <figure className="map-topography-legend" aria-label="LOLA elevation scale">
        <img src="/maps/south-pole/topography/legend.png" width="50" height="150" alt="Elevation in metres: −9126 to 7026, purple lowlands through green and yellow to red highlands" />
        <figcaption>500 m contours</figcaption>
      </figure>}
      {selection && <form className="map-tooltip" role="dialog" aria-modal="false" aria-label={editingSite ? 'Edit custom site' : 'Add map location to sites'}
        style={{ left: `clamp(12px, ${selection.left}%, calc(100% - 272px))`, top: `clamp(12px, ${selection.top}%, calc(100% - ${editingSite ? 255 : 215}px))` }}
        onKeyDown={event => { if (event.key === 'Escape') { event.preventDefault(); closeSelection(); } }}
        onSubmit={event => {
          event.preventDefault();
          if (!name.trim()) return;
          const coordinates = { latitude_deg: Number(selection.coordinates.latitude_deg.toFixed(4)),
            longitude_deg: Number(selection.coordinates.longitude_deg.toFixed(4)) };
          if (editingSite) onSiteRename(editingSite.id, name.trim());
          else onSiteAdd(coordinates, name.trim());
          setAnnouncement(`${editingSite ? 'Renamed site to' : 'Added'} ${name.trim()}. Custom sites are kept for this session.`);
          closeSelection();
        }}>
        <strong>{editingSite ? 'Edit landing site' : 'Add landing site'}</strong>
        <p>{formatCoordinates(selection.coordinates)}</p>
        <label>Site name<input ref={nameRef} className="sb-input" value={name} maxLength={80} required onChange={event => setName(event.target.value)} /></label>
        <div><button className="ct-btn map-add-button" type="submit" disabled={!name.trim()}>{editingSite ? 'Save name' : 'Add to sites'}</button>
          <button className="ct-btn" type="button" onClick={closeSelection}>Cancel</button></div>
        {editingSite && <button className="ct-btn map-delete-button" type="button" onClick={() => {
          onSiteDelete(editingSite.id); setAnnouncement(`Deleted ${editingSite.name} from Sites.`); closeSelection();
        }}>Delete site</button>}
        <small>Saved for this session</small>
      </form>}
    </div>
    <div className="map-coordinate-bar"><span className="map-coordinate-label">Cursor</span>
      <output className="map-coordinates" aria-label="Cursor latitude and longitude">{formatCoordinates(hover)}</output>
      <span className="map-hover-feature">{hoverFeature?.name ?? ''}</span>
    </div>
    <p className="map-announcement" role="status">{announcement}</p>
    {outside.length > 0 && <p className="map-hint">{outside.length} sidebar {outside.length === 1 ? 'site lies' : 'sites lie'} outside 80°S–90°S and {outside.length === 1 ? 'is' : 'are'} not plotted.</p>}
    {heatmaps.data && <div className="map-legends" aria-label="Heatmap legends">
      <strong>{heatmaps.data.data_source === 'mock' ? 'Synthetic demo overlays' : 'Backend analysis overlays'}</strong>
      {heatmaps.data.layers.map(layer => { const option = HEATMAPS.find(item => item.criterion === layer.criterion)!;
        return <div className="map-legend" key={layer.criterion}><span>{option.label}</span>
          <span>{layer.min.toFixed(1)} {layer.unit}</span><span className="map-gradient" style={{ background: `linear-gradient(90deg, rgb(25,27,42), rgb(${option.color.join(',')}))` }} />
          <span>{layer.max.toFixed(1)} {layer.unit}</span><small>{option.direction} · No data: transparent</small></div>;
      })}
    </div>}
    <footer className="map-attribution">Basemap: <a href="https://trek.nasa.gov/moon/" target="_blank" rel="noreferrer">NASA Moon Trek · {basemap === 'topography' ? 'LRO/LOLA elevation' : 'LRO/LROC WAC'}</a>.
      {' '}Names: IAU/USGS via Moon Trek. Feature hover areas approximate catalogue diameters.
      {criteria.length > 1 && ' Overlays blend in toolbar order; enable one for an unambiguous color scale.'}
    </footer>
  </section>;
}
