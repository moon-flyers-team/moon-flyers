import { FitBadge } from './FitBadge';
import { TimelineBars } from './TimelineBars';
import { formatUtc } from './time';
import type { LandingSite, ComparisonResult, Constraints, Metrics, WindowMetricsEntry } from './types';

function NumCell({ value, warn, unit = '' }: { value?: number | null; warn: boolean; unit?: string }) {
  return <td className={warn ? 'warn' : ''}>
    {warn && <span className="warn-icon" aria-label="Requirement not met">⚠ </span>}
    {value == null ? '—' : `${value}${unit}`}
  </td>;
}
interface Props {
  sites: LandingSite[];
  results?: ComparisonResult[];
  constraints: Constraints;
  selectedId: string | null;
  onSelect: (id: string) => void;
  landingTime: string;
  onTimeShift: (hours: number) => void;
  canShiftBack: boolean;
  canShiftForward: boolean;
  missionStart: string;
  missionEnd: string;
  loading: boolean;
  error?: string;
  onRetry: () => void;
}
export function ComparisonTable({ sites, results, constraints: c, selectedId, onSelect,
  landingTime, onTimeShift, canShiftBack, canShiftForward, missionStart, missionEnd,
  loading, error, onRetry }: Props) {
  return <section className="ct-wrap" aria-label="Site comparison" aria-busy={loading}>
    <div className="ct-topbar">
      <span className="ct-tab">Comparison · {c.days_on_surface} days on surface</span>
      <div className="ct-time"><span className="ct-time-label">Landing</span>
        <button className="ct-btn" disabled={!canShiftBack} onClick={() => onTimeShift(-6)}>−6 h</button>
        <span className="ct-time-val">{formatUtc(landingTime)}</span>
        <button className="ct-btn" disabled={!canShiftForward} onClick={() => onTimeShift(6)}>+6 h</button>
      </div>
    </div>
    {loading && <p className="request-status" role="status">Comparing sites. This can take 10–30 seconds…</p>}
    {error && <div className="request-error" role="alert">Comparison failed: {error} <button className="ct-btn" onClick={onRetry}>Retry comparison</button></div>}
    <div className="ct-scroll"><table className="ct">
      <thead><tr>
        <th rowSpan={2} className="ct-left">Site</th><th rowSpan={2}>Fit</th>
        <th colSpan={2} className="ct-grp ct-grp--power"><span className="grp-dot grp-dot--power" /> Power (Sun)</th>
        <th colSpan={2} className="ct-grp ct-grp--comms"><span className="grp-dot grp-dot--comms" /> Comms (Earth)</th>
        <th rowSpan={2}>Terrain<span className="th-sub">Slope max {c.max_slope_deg}°</span></th>
        <th rowSpan={2}>Windows</th>
      </tr><tr>
        <th>Sunlight<span className="th-sub">min {c.min_sun_visible_pct}%</span></th>
        <th>Longest night<span className="th-sub">max {c.max_darkness_hours} h</span></th>
        <th>Earth contact<span className="th-sub">min {c.min_earth_visible_pct}%</span></th>
        <th>Longest gap<span className="th-sub">max {c.max_earth_blackout_hours} h</span></th>
      </tr></thead>
      <tbody>{!sites.length && <tr><td colSpan={8} className="ct-empty">No sites selected</td></tr>}
        {sites.map((site, index) => {
          // The contract guarantees response order, including custom sites without IDs.
          const result = results?.[index];
          const entry: WindowMetricsEntry | undefined = result?.window_metrics.find(
            e => e.landing_utc === landingTime
          ) ?? result?.window_metrics[0];
          const metrics = entry?.metrics;
          const warn = (metric: keyof Metrics) => entry?.fit.violations.includes(metric) ?? false;
          return <tr key={site.id} className={selectedId === site.id ? 'row-sel' : ''} onClick={() => onSelect(site.id)}>
            <td className="ct-left ct-name"><button className="site-select" aria-pressed={selectedId === site.id} onClick={() => onSelect(site.id)}>{site.name}</button></td>
            <td>{entry ? <FitBadge fit={entry.fit.status} /> : '—'}</td>
            <NumCell value={metrics?.sun_visible_pct} warn={warn('sun_visible_pct')} unit="%" />
            <NumCell value={metrics?.longest_darkness_hours} warn={warn('longest_darkness_hours')} unit=" h" />
            <NumCell value={metrics?.earth_visible_pct} warn={warn('earth_visible_pct')} unit="%" />
            <NumCell value={metrics?.longest_earth_blackout_hours} warn={warn('longest_earth_blackout_hours')} unit=" h" />
            <NumCell value={metrics?.slope_deg} warn={warn('slope_deg')} unit="°" />
            <TimelineBars powerWindows={result?.timeline.sun} commsWindows={result?.timeline.earth}
              missionStart={missionStart} missionEnd={missionEnd} landingUtc={landingTime} />
          </tr>;
        })}
      </tbody>
    </table></div>
    {results && <p className="request-status">Visibility windows: {formatUtc(missionStart)} to {formatUtc(missionEnd)}. Terrain slope is unavailable in API v0.</p>}
  </section>;
}
