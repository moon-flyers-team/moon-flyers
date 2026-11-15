import { useMemo } from 'react';
import type { SiteAnalysis, TimeseriesPoint } from './types';
import { DAY_MS, LUNAR_DAY_EARTH_DAYS, formatUtc } from './time';

interface Props {
  siteName: string;
  analysis?: SiteAnalysis;
  landingUtc: string;
  loading: boolean;
  error?: string;
  onRetry: () => void;
}
const VW = 900, VH = 240, ML = 48, MR = 16, MT = 14, MB = 30;
const CW = VW - ML - MR, CH = VH - MT - MB;
const COMPASS = ['N (0°)', 'E (90°)', 'S (180°)', 'W (270°)', 'N (360°)'];
const azToX = (az: number) => ML + az / 360 * CW;

// Split path into visible (solid) and hidden (dashed) segments.
export function splitSkyPath(data: TimeseriesPoint[], body: 'sun' | 'earth', y: (el: number) => number) {
  let visD = '', hidD = '';
  let open: boolean | null = null;
  const pt = (p: TimeseriesPoint) => `${azToX(p[`${body}_azimuth_deg`]).toFixed(2)},${y(p[`${body}_elevation_deg`]).toFixed(2)}`;
  for (let i = 1; i < data.length; i++) {
    const a = data[i - 1], b = data[i];
    if (Math.abs(b[`${body}_azimuth_deg`] - a[`${body}_azimuth_deg`]) > 180) { open = null; continue; }
    // segment takes the state of its start point
    const vis = a[`${body}_visible`];
    const seg = (open === vis ? '' : ` M ${pt(a)}`) + ` L ${pt(b)}`;
    if (vis) visD += seg; else hidD += seg;
    open = vis;
  }
  return [visD.trim(), hidD.trim()] as const;
}

// Legacy export kept for any external references.
export function skyPath(data: TimeseriesPoint[], body: 'sun' | 'earth', y: (el: number) => number) {
  return data.map((point, i) => {
    const az = point[`${body}_azimuth_deg`];
    const previous = data[i - 1]?.[`${body}_azimuth_deg`];
    const command = i === 0 || Math.abs(az - previous) > 180 ? 'M' : 'L';
    return `${command} ${azToX(az).toFixed(2)},${y(point[`${body}_elevation_deg`]).toFixed(2)}`;
  }).join(' ');
}
export function HorizonChart({ siteName, analysis, landingUtc, loading, error, onRetry }: Props) {
  const samples = useMemo(() => {
    const start = Date.parse(landingUtc);
    const end = start + LUNAR_DAY_EARTH_DAYS * DAY_MS;
    return (analysis?.timeseries ?? []).filter(point => {
      const time = Date.parse(point.time_utc);
      return time >= start && time <= end;
    }).sort((a, b) => Date.parse(a.time_utc) - Date.parse(b.time_utc));
  }, [analysis, landingUtc]);

  const trail = useMemo(() => {
    const start = Date.parse(landingUtc);
    return (analysis?.timeseries ?? [])
      .filter(p => Date.parse(p.time_utc) < start)
      .sort((a, b) => Date.parse(b.time_utc) - Date.parse(a.time_utc))
      .slice(0, 8);
  }, [analysis, landingUtc]);

  const current = samples[0];
  const terrain = analysis?.horizon;
  // Use the entire site's batch so scrubbing never changes the altitude scale.
  const { min, max } = useMemo(() => {
    let low = -5, high = 9;
    const include = (elevation: number) => {
      if (Number.isFinite(elevation)) {
        low = Math.min(low, elevation);
        high = Math.max(high, elevation);
      }
    };
    for (const point of analysis?.timeseries ?? []) {
      include(point.sun_elevation_deg);
      include(point.earth_elevation_deg);
    }
    for (const elevation of analysis?.horizon.horizon_elevation_deg ?? []) include(elevation);
    return { min: Math.floor(low - 1), max: Math.ceil(high + 1) };
  }, [analysis]);
  const y = (el: number) => MT + (max - el) / (max - min) * CH;
  const terrainPoints = terrain?.horizon_azimuth_deg.map((az, i) => `${azToX(az)},${y(terrain.horizon_elevation_deg[i])}`) ?? [];
  const status = loading ? 'Loading a lunar day of positions. This can take 10–30 seconds…'
    : !analysis ? 'Select a site to load its horizon.' : !samples.length ? 'No time samples returned for this lunar day.' : '';

  return <section className="hz-wrap" aria-label="Lunar day horizon" aria-busy={loading}>
    <div className="hz-hdr"><span className="hz-title">Horizon</span><span className="hz-site">{siteName}</span>
      {current && <div className="hz-legend">
        <span>{formatUtc(current.time_utc)}</span>
        <span><span className={`hz-dot ${current.sun_visible ? 'hz-dot--sun' : 'hz-dot--off'}`} />Sun {current.sun_visible ? 'visible' : 'not visible'} · {current.sun_elevation_deg.toFixed(1)}°</span>
        <span><span className={`hz-dot ${current.earth_visible ? 'hz-dot--earth-visible' : 'hz-dot--off'}`} />Earth {current.earth_visible ? 'visible' : 'not visible'} · {current.earth_elevation_deg.toFixed(1)}°</span>
        <span><span className="hz-dot hz-dot--eclipse" />Eclipse intervals</span>
      </div>}
    </div>
    {error ? <div className="request-error" role="alert">Horizon request failed: {error} <button className="ct-btn" onClick={onRetry}>Retry horizon</button></div>
      : status && <p className="request-status" role="status">{status}</p>}
    <svg viewBox={`0 0 ${VW} ${VH}`} className="hz-svg" role="img" aria-label={`Sun and Earth azimuth and elevation at ${siteName}${current ? `, ${formatUtc(current.time_utc)}` : ''}`}>
      <defs>
        <linearGradient id="fade-sun" x1={ML} y1="0" x2={ML + CW} y2="0" gradientUnits="userSpaceOnUse">
          <stop offset="0%"   stopColor="#f5a623" stopOpacity="0" />
          <stop offset="8%"   stopColor="#f5a623" stopOpacity="1" />
          <stop offset="92%"  stopColor="#f5a623" stopOpacity="1" />
          <stop offset="100%" stopColor="#f5a623" stopOpacity="0" />
        </linearGradient>
        <linearGradient id="fade-earth" x1={ML} y1="0" x2={ML + CW} y2="0" gradientUnits="userSpaceOnUse">
          <stop offset="0%"   stopColor="#4fc3f7" stopOpacity="0" />
          <stop offset="8%"   stopColor="#4fc3f7" stopOpacity="1" />
          <stop offset="92%"  stopColor="#4fc3f7" stopOpacity="1" />
          <stop offset="100%" stopColor="#4fc3f7" stopOpacity="0" />
        </linearGradient>
      </defs>
      <rect x={ML} y={MT} width={CW} height={CH} fill="#12121e" />
      {Array.from({ length: 6 }, (_, i) => min + i * (max - min) / 5).map(el => <g key={el}>
        <line x1={ML} y1={y(el)} x2={ML + CW} y2={y(el)} stroke="#262640" />
        <text x={ML - 5} y={y(el)} textAnchor="end" dominantBaseline="middle" fill="#8989af" fontSize={11}>{el.toFixed(1)}°</text>
      </g>)}
      <line x1={ML} y1={y(0)} x2={ML + CW} y2={y(0)} stroke="#62628a" strokeDasharray="4 3" />
      {COMPASS.map((label, i) => <text key={i} x={ML + i / 4 * CW} y={VH - 8}
        textAnchor={i === 0 ? 'start' : i === 4 ? 'end' : 'middle'} fill="#8989af" fontSize={11}>{label}</text>)}
      {terrainPoints.length > 0 && <path d={`M ${ML},${MT + CH} L ${terrainPoints.join(' L ')} L ${ML + CW},${MT + CH} Z`} fill="#303040" />}
      {(() => {
        const [sunVis, sunHid] = splitSkyPath(samples, 'sun', y);
        const [earthVis, earthHid] = splitSkyPath(samples, 'earth', y);
        return <>
          {sunVis   && <path d={sunVis}   fill="none" stroke="url(#fade-sun)"   strokeWidth={2} opacity={0.75} />}
          {sunHid   && <path d={sunHid}   fill="none" stroke="url(#fade-sun)"   strokeWidth={1.5} opacity={0.45} strokeDasharray="5 4" />}
          {earthVis && <path d={earthVis} fill="none" stroke="url(#fade-earth)" strokeWidth={2} opacity={0.75} />}
          {earthHid && <path d={earthHid} fill="none" stroke="url(#fade-earth)" strokeWidth={1.5} opacity={0.45} strokeDasharray="5 4" />}
        </>;
      })()}
      {trail.map((point, i) => (['sun', 'earth'] as const).map(body => (
        <circle key={`${body}-trail-${i}`}
          cx={azToX(point[`${body}_azimuth_deg`])} cy={y(point[`${body}_elevation_deg`])}
          r={Math.max(1.5, 4.5 - i * 0.43)}
          fill={body === 'sun' ? '#f5a623' : '#4fc3f7'}
          opacity={Math.max(0.03, 0.58 - i * 0.08)} />
      )))}
      {current && (['sun', 'earth'] as const).map(body => <circle key={body}
        cx={azToX(current[`${body}_azimuth_deg`])} cy={y(current[`${body}_elevation_deg`])} r={6}
        fill={current[`${body}_visible`] ? body === 'sun' ? '#f5a623' : '#4fc3f7' : '#12121e'}
        stroke={body === 'sun' ? '#f5a623' : '#4fc3f7'} strokeWidth={2}
        strokeDasharray={current[`${body}_visible`] ? undefined : '3.4 2.9'} />)}
    </svg>
    <div className="hz-footer">
      <span><span className="hz-line hz-line--sun" />Sun path</span><span><span className="hz-line hz-line--earth" />Earth path</span>
      <span>● visible · ◌ below horizon clearance</span><span>Backend horizon · terrain source not reported · slope not assessed</span>
      <span>1 lunar day ≈ 29.53 Earth days from landing</span>
    </div>
  </section>;
}
