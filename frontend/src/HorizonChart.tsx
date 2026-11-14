import type { HorizonPoint } from './types';

interface Props {
  siteName: string;
  data: HorizonPoint[];
  loading?: boolean;
}

const VW = 900;
const VH = 200;
const ML = 44;
const MT = 8;
const MB = 28;
const CW = VW - ML - 6;
const CH = VH - MT - MB;
const EL_MAX = 9;
const EL_MIN = -5;
const EL_RANGE = EL_MAX - EL_MIN;

function elToY(el: number) {
  return MT + ((EL_MAX - el) / EL_RANGE) * CH;
}
function azToX(az: number) {
  return ML + (az / 360) * CW;
}
function toPolyline(data: HorizonPoint[], key: keyof HorizonPoint) {
  return data.map(p => `${azToX(p.azimuth).toFixed(1)},${elToY(p[key] as number).toFixed(1)}`).join(' ');
}
function toTerrainPath(data: HorizonPoint[]) {
  if (data.length === 0) return '';
  const bottom = MT + CH;
  const coords = data.map(p => `L ${azToX(p.azimuth).toFixed(1)},${elToY(p.terrainEl).toFixed(1)}`);
  const first = `M ${azToX(data[0].azimuth).toFixed(1)},${elToY(data[0].terrainEl).toFixed(1)}`;
  const last = data[data.length - 1];
  return `${first} ${coords.slice(1).join(' ')} L ${azToX(last.azimuth).toFixed(1)},${bottom} L ${ML},${bottom} Z`;
}

const Y_LINES = [8, 6, 4, 2, 0, -2, -4];
const COMPASS = ['N', 'E', 'S', 'W', 'N'] as const;

export function HorizonChart({ siteName, data, loading = false }: Props) {
  const sunPt = data.length > 0
    ? data.reduce((a, b) => (a.sunEl > b.sunEl ? a : b))
    : null;
  const earthPt = data.length > 0
    ? data.reduce((a, b) => (a.earthEl > b.earthEl ? a : b))
    : null;

  return (
    <div className="hz-wrap">
      <div className="hz-hdr">
        <span className="hz-title">Horizon</span>
        <span className="hz-site">{siteName}</span>
        {sunPt && (
          <span className="hz-legend">
            <span className="hz-dot hz-dot--sun" />
            Sun visible {sunPt.sunEl.toFixed(1)}° elevation
            <span className="hz-dot hz-dot--earth" style={{ marginLeft: 10 }} />
            {earthPt && `Earth visible ${earthPt.earthEl.toFixed(1)}° elevation`}
          </span>
        )}
      </div>

      <svg viewBox={`0 0 ${VW} ${VH}`} className="hz-svg" preserveAspectRatio="xMidYMid meet">
        <rect x={ML} y={MT} width={CW} height={CH} fill="#12121e" />

        {Y_LINES.map(el => (
          <g key={el}>
            <line
              x1={ML} y1={elToY(el)} x2={ML + CW} y2={elToY(el)}
              stroke={el === 0 ? '#303060' : '#1e1e38'}
              strokeWidth={el === 0 ? 1.5 : 1}
              strokeDasharray={el === 0 ? '4 3' : undefined}
            />
            <text x={ML - 4} y={elToY(el)} textAnchor="end" dominantBaseline="middle" fill="#50507a" fontSize={11}>
              {el}°
            </text>
          </g>
        ))}

        {COMPASS.map((label, i) => (
          <text
            key={`${label}-${i}`}
            x={ML + (i / (COMPASS.length - 1)) * CW}
            y={VH - 6}
            textAnchor="middle"
            fill="#50507a"
            fontSize={11}
          >
            {label}
          </text>
        ))}

        {data.length > 0 && (
          <>
            <path d={toTerrainPath(data)} fill="#252535" />
            <polyline points={toPolyline(data, 'earthEl')} fill="none" stroke="#4fc3f7" strokeWidth={1.8} opacity={0.75} />
            <polyline points={toPolyline(data, 'sunEl')} fill="none" stroke="#f5a623" strokeWidth={2.2} />
            {sunPt && <circle cx={azToX(sunPt.azimuth)} cy={elToY(sunPt.sunEl)} r={6} fill="#f5a623" />}
            {earthPt && <circle cx={azToX(earthPt.azimuth)} cy={elToY(earthPt.earthEl)} r={6} fill="#4fc3f7" />}
          </>
        )}

        {data.length === 0 && !loading && (
          <text x={VW / 2} y={VH / 2} textAnchor="middle" dominantBaseline="middle" fill="#30305a" fontSize={13}>
            No horizon data — select a site
          </text>
        )}

        {loading && (
          <text x={VW / 2} y={VH / 2} textAnchor="middle" dominantBaseline="middle" fill="#30305a" fontSize={13}>
            Loading…
          </text>
        )}
      </svg>

      <div className="hz-footer">
        <span><span className="hz-line hz-line--sun" /> Sun path</span>
        <span><span className="hz-line hz-line--earth" /> Earth path</span>
        <span className="hz-muted">over 14 days from landing</span>
        <span><span className="hz-circ hz-circ--fill" /> visible</span>
        <span><span className="hz-circ hz-circ--empty" /> below the horizon</span>
      </div>
    </div>
  );
}
