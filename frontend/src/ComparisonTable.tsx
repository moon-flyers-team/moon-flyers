import { useState, useEffect, useMemo, useRef } from 'react';
import { FitBadge } from './FitBadge';
import { TimelineBars } from './TimelineBars';
import type { LandingSite, ComparisonResult, Constraints, Metrics, WindowMetricsEntry } from './types';

const THREE_MONTHS_MS = 91 * 86_400_000;
const STEP_MS = 6 * 3_600_000;

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
  onTimeSeek: (iso: string) => void;
  missionStart: string;
  sliderEnd: string;
  disabled?: boolean;
  loading: boolean;
  error?: string;
  onRetry: () => void;
}

export function ComparisonTable({ sites, results, constraints: c, selectedId, onSelect,
  landingTime, onTimeSeek,
  missionStart, sliderEnd, disabled,
  loading, error, onRetry }: Props) {

  const startMs = useMemo(() => {
    const value = Date.parse(missionStart);
    return Number.isFinite(value) ? value : 0;
  }, [missionStart]);
  const sliderEndMs = useMemo(() => {
    const value = Date.parse(sliderEnd);
    return Number.isFinite(value) ? Math.max(startMs, value) : startMs;
  }, [sliderEnd, startMs]);

  const [viewStartMs, setViewStartMs] = useState(() => startMs);

  useEffect(() => { setViewStartMs(startMs); }, [startMs]);

  useEffect(() => {
    const landingMs = Date.parse(landingTime);
    if (!Number.isFinite(landingMs)) return;
    setViewStartMs(prev => {
      const prevEnd = Math.min(prev + THREE_MONTHS_MS, sliderEndMs);
      if (landingMs >= prev && landingMs <= prevEnd) return prev;
      const offset = Math.max(0, Math.floor((landingMs - startMs) / THREE_MONTHS_MS));
      return startMs + offset * THREE_MONTHS_MS;
    });
  }, [landingTime, startMs, sliderEndMs]);

  const viewEndMs = Math.min(viewStartMs + THREE_MONTHS_MS, sliderEndMs);
  const viewStart = useMemo(() => new Date(viewStartMs).toISOString(), [viewStartMs]);
  const viewEnd   = useMemo(() => new Date(viewEndMs).toISOString(),   [viewEndMs]);

  const canGoPrev = viewStartMs > startMs;
  const canGoNext = viewEndMs  < sliderEndMs;

  function goPrev() { setViewStartMs(ms => Math.max(startMs, ms - THREE_MONTHS_MS)); }
  function goNext() { setViewStartMs(ms => Math.min(sliderEndMs - THREE_MONTHS_MS, ms + THREE_MONTHS_MS)); }

  // Custom inline slider
  const sliderRef      = useRef<HTMLDivElement>(null);
  const sliderDragging = useRef(false);

  const thumbPct = useMemo(() => {
    const start   = Date.parse(viewStart);
    const end     = Date.parse(viewEnd);
    const landing = Date.parse(landingTime);
    if (!Number.isFinite(start) || !Number.isFinite(end) || end <= start || !Number.isFinite(landing)) return null;
    return Math.max(0, Math.min(100, (landing - start) / (end - start) * 100));
  }, [viewStart, viewEnd, landingTime]);

  const ticks = useMemo(() => {
    const start = Date.parse(viewStart);
    const end   = Date.parse(viewEnd);
    const result: { pct: number; label: string }[] = [];
    const d = new Date(start);
    d.setUTCDate(1);
    d.setUTCMonth(d.getUTCMonth() + 1);
    while (d.getTime() < end) {
      result.push({
        pct: ((d.getTime() - start) / (end - start)) * 100,
        label: d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', timeZone: 'UTC' }),
      });
      d.setUTCMonth(d.getUTCMonth() + 1);
    }
    return result;
  }, [viewStart, viewEnd]);

  function seekSlider(clientX: number) {
    if (disabled || !sliderRef.current) return;
    const rect  = sliderRef.current.getBoundingClientRect();
    if (rect.width <= 0) return;
    const pct   = Math.max(0, Math.min(1, (clientX - rect.left) / rect.width));
    const start = Date.parse(viewStart);
    const end   = Date.parse(viewEnd);
    onTimeSeek(new Date(Math.round((start + pct * (end - start)) / STEP_MS) * STEP_MS).toISOString());
  }

  useEffect(() => {
    function onMove(e: MouseEvent) { if (sliderDragging.current) seekSlider(e.clientX); }
    function onUp()  { sliderDragging.current = false; }
    window.addEventListener('mousemove', onMove);
    window.addEventListener('mouseup', onUp);
    return () => { window.removeEventListener('mousemove', onMove); window.removeEventListener('mouseup', onUp); };
  }, [viewStart, viewEnd, onTimeSeek, disabled]);

  return <section className="ct-wrap" aria-label="Site comparison" aria-busy={loading}>
    <div className="ct-topbar">
      <span className="ct-tab">Comparison</span>
      <div className="ct-time">
        <span className="ct-time-label">Landing (UTC)</span>
        <span className="ct-time-val">{landingTime.slice(0, 10)} {landingTime.slice(11, 16)}</span>
      </div>
    </div>
    {loading && <p className="request-status" role="status">Comparing sites. This can take 10–30 seconds…</p>}
    {error && <div className="request-error" role="alert">Comparison failed: {error} <button className="ct-btn" onClick={onRetry}>Retry comparison</button></div>}
    <div className="ct-scroll"><table className="ct">
      <thead>
      <tr>
        <th className="ct-left">Site</th>
        <th>Result</th>
        <th>Sunlight<span className="th-sub">min {c.min_sun_visible_pct}%</span></th>
        <th>Longest night<span className="th-sub">max {c.max_darkness_hours} h</span></th>
        <th>Earth contact<span className="th-sub">min {c.min_earth_visible_pct}%</span></th>
        <th>Longest gap<span className="th-sub">max {c.max_earth_blackout_hours} h</span></th>
        <th>Terrain<span className="th-sub">Slope max {c.max_slope_deg}°</span></th>
        <th className="ct-slider-cell">
          <div className="ts-wrapper">
            <div className="ts-controls-row">
              <button className="ct-btn ts-nav-btn" disabled={disabled || !canGoPrev} onClick={goPrev}>◀</button>
              <div
                ref={sliderRef}
                className={`ts-custom-track${disabled ? ' ts-custom-track--disabled' : ''}`}
                aria-disabled={!!disabled}
                onMouseDown={e => { if (!disabled) { sliderDragging.current = true; seekSlider(e.clientX); } }}
              >
                {thumbPct !== null && <div className="ts-thumb" style={{ left: `${thumbPct}%` }} />}
              </div>
              <button className="ct-btn ts-nav-btn" disabled={disabled || !canGoNext} onClick={goNext}>▶</button>
            </div>
            <div className="ts-ticks-inset">
              {ticks.map(t => (
                <div key={t.label} className="ts-tick" style={{ left: `${t.pct}%` }}>
                  <div className="ts-tick-mark" />
                  <span className="ts-tick-label">{t.label}</span>
                </div>
              ))}
            </div>
          </div>
        </th>
      </tr>
      </thead>
      <tbody>
        {!sites.length && <tr><td colSpan={8} className="ct-empty">No sites selected</td></tr>}
        {sites.map((site, index) => {
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
              eclipseWindows={result?.timeline.eclipse}
              missionStart={viewStart} missionEnd={viewEnd} landingUtc={landingTime} onChange={disabled ? undefined : onTimeSeek} />
          </tr>;
        })}
      </tbody>
    </table></div>
  </section>;
}
