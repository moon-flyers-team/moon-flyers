import { useState, useEffect, useLayoutEffect, useMemo, useRef } from 'react';
import type { ReactNode } from 'react';
import { FitBadge } from './FitBadge';
import { SurfaceStayWindow, TimelineBars } from './TimelineBars';
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
  onLandingSelect?: (id: string) => void;
  landingSiteId?: string | null;
  landingTime: string;
  onTimeSeek: (iso: string) => void;
  missionStart: string;
  sliderEnd: string;
  disabled?: boolean;
  loading: boolean;
  error?: string;
  onRetry: () => void;
  children?: ReactNode;
}

export function ComparisonTable({ sites, results, constraints: c, selectedId, onSelect, onLandingSelect, landingSiteId,
  landingTime, onTimeSeek,
  missionStart, sliderEnd, disabled,
  loading, error, onRetry, children }: Props) {

  const startMs = useMemo(() => {
    const value = Date.parse(missionStart);
    return Number.isFinite(value) ? value : 0;
  }, [missionStart]);
  const sliderEndMs = useMemo(() => {
    const value = Date.parse(sliderEnd);
    return Number.isFinite(value) ? Math.max(startMs, value) : startMs;
  }, [sliderEnd, startMs]);

  const [viewStartMs, setViewStartMs] = useState(() => startMs);
  const selectedMs = Date.parse(landingTime);

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

  // Topbar slider tracks the timeline column so thumb and bar markers line up
  const topbarRef = useRef<HTMLDivElement>(null);
  const columnRef = useRef<HTMLTableCellElement>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const [sliderBox, setSliderBox] = useState<{ left: number; width: number } | null>(null);
  useLayoutEffect(() => {
    const bar = topbarRef.current, col = columnRef.current, scroller = scrollRef.current;
    if (!bar || !col || !scroller) return;
    const measure = () => {
      const b = bar.getBoundingClientRect(), c = col.getBoundingClientRect();
      const pad = 9;
      setSliderBox({ left: c.left - b.left + pad, width: Math.max(0, c.width - 2 * pad) });
    };
    measure();
    const ro = new ResizeObserver(measure);
    ro.observe(bar);
    ro.observe(col);
    scroller.addEventListener('scroll', measure, { passive: true });
    return () => { ro.disconnect(); scroller.removeEventListener('scroll', measure); };
  }, []);

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
    <div className="ct-topbar" ref={topbarRef}>
      <span className="ct-tab">Comparison{onLandingSelect && <span className="ct-info" tabIndex={0} role="img"
        aria-label="Double-click a site to choose landing · keyboard: Shift+Enter"
        data-tip="Double-click a site to choose landing · keyboard: Shift+Enter">i</span>}</span>
      <div className="ct-time">
        <span className="ct-time-label">Landing (UTC)</span>
        <input type="datetime-local" className="ct-time-val ct-time-input"
          aria-label="Landing time (UTC)" title="UTC arrival; 6-hour sampled candidates"
          value={Number.isFinite(selectedMs) ? new Date(selectedMs).toISOString().slice(0, 16) : ''}
          min={new Date(startMs).toISOString().slice(0, 16)}
          max={new Date(sliderEndMs).toISOString().slice(0, 16)} step={21600} disabled={!!disabled}
          onChange={event => {
            const value = Date.parse(`${event.currentTarget.value}Z`);
            if (!disabled && event.currentTarget.validity.valid && Number.isFinite(value)
              && value >= startMs && value <= sliderEndMs && (value - startMs) % STEP_MS === 0) {
              onTimeSeek(new Date(value).toISOString());
            }
          }} />
      </div>
      <div className="ts-wrapper ct-topbar-slider"
        style={sliderBox ? { left: sliderBox.left, width: sliderBox.width } : undefined}>
        <div className="ts-controls-row">
          <button className="ct-btn ts-nav-btn" disabled={disabled || !canGoPrev} onClick={goPrev}>◀</button>
          <div
            ref={sliderRef}
            className={`ts-custom-track${disabled ? ' ts-custom-track--disabled' : ''}`}
            aria-disabled={!!disabled}
            onMouseDown={e => { if (!disabled) { sliderDragging.current = true; seekSlider(e.clientX); } }}
          >
            {!disabled && <SurfaceStayWindow landingUtc={landingTime} daysOnSurface={c.days_on_surface}
              missionStart={viewStart} missionEnd={viewEnd} />}
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
    </div>
    <div className="ct-body">
      <div className="ct-card">
      {loading && <p className="request-status" role="status">Comparing sites. This can take 10–30 seconds…</p>}
      {error && <div className="request-error" role="alert">Comparison failed: {error} <button className="ct-btn" onClick={onRetry}>Retry comparison</button></div>}
      <div className="ct-scroll" ref={scrollRef}><table className="ct">
        <thead>
        <tr>
          <th className="ct-left">Site</th>
          <th>Result</th>
          <th>Sunlight<span className="th-sub">min {c.min_sun_visible_pct}%</span></th>
          <th>Longest night<span className="th-sub">max {c.max_darkness_hours} h</span></th>
          <th>Earth contact<span className="th-sub">min {c.min_earth_visible_pct}%</span></th>
          <th>Longest gap<span className="th-sub">max {c.max_earth_blackout_hours} h</span></th>
          <th>Terrain<span className="th-sub">Slope max {c.max_slope_deg}°</span></th>
          <th className="ct-slider-cell" ref={columnRef}>Timeline
            <span className="th-sub">
              <span className="tl-legend-dot tl-legend-dot--sun" />Sun
              <span className="tl-legend-dot tl-legend-dot--earth" />Earth
            </span>
            <span className="th-sub"><span className="surface-stay-key" />Shaded: {c.days_on_surface} {c.days_on_surface === 1 ? 'day' : 'days'} on surface</span>
          </th>
        </tr>
        </thead>
        <tbody>
          {!sites.length && <tr><td colSpan={8} className="ct-empty">No sites selected</td></tr>}
          {sites.map((site, index) => {
            const result = results?.[index];
            const entry: WindowMetricsEntry | undefined = result?.window_metrics.find(
              e => Date.parse(e.landing_utc) === selectedMs
            );
            const metrics = entry?.metrics;
            const warn = (metric: keyof Metrics) => entry?.fit.violations.includes(metric) ?? false;
            return <tr key={site.id} className={`${selectedId === site.id ? 'row-sel' : ''}${landingSiteId === site.id ? ' row-landing' : ''}`}  onClick={() => onSelect(site.id)} onDoubleClick={() => onLandingSelect?.(site.id)}>
              <td className="ct-left ct-name"><button className="site-select" onKeyDown={event => { if (event.key === 'Enter' && event.shiftKey) { event.preventDefault(); onLandingSelect?.(site.id); } }} aria-pressed={selectedId === site.id} onClick={() => onSelect(site.id)}>{site.name}</button>{landingSiteId === site.id && <span className="ct-landing-badge">Landing site</span>}</td>
              <td>{entry ? <FitBadge fit={entry.fit.status} /> : result ? 'Not sampled' : '—'}</td>
              <NumCell value={metrics?.sun_visible_pct} warn={warn('sun_visible_pct')} unit="%" />
              <NumCell value={metrics?.longest_darkness_hours} warn={warn('longest_darkness_hours')} unit=" h" />
              <NumCell value={metrics?.earth_visible_pct} warn={warn('earth_visible_pct')} unit="%" />
              <NumCell value={metrics?.longest_earth_blackout_hours} warn={warn('longest_earth_blackout_hours')} unit=" h" />
              <NumCell value={metrics?.slope_deg} warn={warn('slope_deg')} unit="°" />
              <TimelineBars powerWindows={result?.timeline.sun} commsWindows={result?.timeline.earth}
                missionStart={viewStart} missionEnd={viewEnd} landingUtc={landingTime}
                daysOnSurface={disabled ? undefined : c.days_on_surface} onChange={disabled ? undefined : onTimeSeek}
                allMet={entry?.fit.status === 'both_met'} />
            </tr>;
          })}
        </tbody>
      </table></div>
      </div>
      {children}
    </div>
  </section>;
}
