import { useEffect, useRef } from 'react';
import type { Fit, TimeWindow } from './types';
import { DAY_MS, formatUtc } from './time';

const STEP_MS = 6 * 3_600_000;

interface Props {
  fit?: Fit;
  powerWindows?: TimeWindow[];
  commsWindows?: TimeWindow[];
  missionStart: string;
  missionEnd: string;
  landingUtc?: string;
  daysOnSurface?: number;
  onChange?: (iso: string) => void;
}
export function normalise(windows: TimeWindow[], missionStart: string, missionEnd: string) {
  const start = Date.parse(missionStart);
  const end = Date.parse(missionEnd);
  if (!Number.isFinite(start) || !Number.isFinite(end) || end <= start) return [];
  return windows.flatMap(window => {
    const left = Math.max(start, Date.parse(window.start_utc));
    const right = Math.min(end, Date.parse(window.end_utc));
    if (!Number.isFinite(left) || !Number.isFinite(right) || right <= left) return [];
    return [{ left: (left - start) / (end - start), width: (right - left) / (end - start), window }];
  });
}
// Shared by the slider and site rows so both show the same scoring interval.
export function SurfaceStayWindow({ landingUtc, daysOnSurface, missionStart, missionEnd }: {
  landingUtc?: string; daysOnSurface?: number; missionStart: string; missionEnd: string;
}) {
  const start = Date.parse(landingUtc ?? '');
  const end = start + (daysOnSurface ?? 0) * DAY_MS;
  if (!Number.isFinite(start) || !Number.isFinite(end) || end <= start || Math.abs(end) > 8.64e15) return null;
  const startUtc = new Date(start).toISOString(), endUtc = new Date(end).toISOString();
  const segment = normalise([{ start_utc: startUtc, end_utc: endUtc }], missionStart, missionEnd)[0];
  if (!segment) return null;
  const continues = end > Date.parse(missionEnd);
  const label = `Time on surface: ${daysOnSurface} ${daysOnSurface === 1 ? 'day' : 'days'} · ${formatUtc(startUtc)} – ${formatUtc(endUtc)}${continues ? ' (continues beyond view)' : ''}`;
  return <div className={`surface-stay-window${continues ? ' surface-stay-window--continues' : ''}`}
    role="img" aria-label={label} title={label}
    style={{ left: `${segment.left * 100}%`, width: `${segment.width * 100}%` }} />;
}

export function TimelineBars({ fit, powerWindows, commsWindows, missionStart, missionEnd, landingUtc, daysOnSurface, onChange }: Props) {
  const startMs = Date.parse(missionStart);
  const endMs   = Date.parse(missionEnd);
  const tracksRef = useRef<HTMLDivElement>(null);
  const dragging  = useRef(false);

  const markerPct = landingUtc && Number.isFinite(startMs) && Number.isFinite(endMs) && endMs > startMs
    ? Math.max(0, Math.min(100, (Date.parse(landingUtc) - startMs) / (endMs - startMs) * 100))
    : null;

  function seek(clientX: number) {
    if (!onChange || !tracksRef.current || !Number.isFinite(startMs) || !Number.isFinite(endMs)) return;
    const rect = tracksRef.current.getBoundingClientRect();
    const pct  = Math.max(0, Math.min(1, (clientX - rect.left) / rect.width));
    const raw  = startMs + pct * (endMs - startMs);
    onChange(new Date(Math.round(raw / STEP_MS) * STEP_MS).toISOString());
  }

  useEffect(() => {
    if (!onChange) return;
    function onMove(e: MouseEvent) { if (dragging.current) seek(e.clientX); }
    function onUp()  { dragging.current = false; }
    window.addEventListener('mousemove', onMove);
    window.addEventListener('mouseup', onUp);
    return () => { window.removeEventListener('mousemove', onMove); window.removeEventListener('mouseup', onUp); };
  }, [onChange, startMs, endMs]);

  const meetsConstraints = fit?.status === 'both_met' && fit.violations.length === 0;
  return (
    <td>
      <div className="tl-wrap">
        <div
          ref={tracksRef}
          className={`tl-tracks${onChange ? ' tl-tracks--interactive' : ''}`}
          onMouseDown={e => { dragging.current = true; seek(e.clientX); }}
        >
          <div className={`tl-track${powerWindows ? '' : ' tl-track--empty'}`}
            role="img" aria-label={`Sun: ${powerWindows ? `${powerWindows.length} visibility windows` : 'data unavailable'}`}>
            {normalise(powerWindows ?? [], missionStart, missionEnd).map((seg, i) => (
              <div key={i} className="tl-seg tl-seg--power"
                title={`${formatUtc(seg.window.start_utc)} – ${formatUtc(seg.window.end_utc)}`}
                style={{ left: `${seg.left * 100}%`, width: `${seg.width * 100}%` }} />
            ))}
          </div>
          <div className={`tl-track${commsWindows ? '' : ' tl-track--empty'}`}
            role="img" aria-label={`Earth: ${commsWindows ? `${commsWindows.length} visibility windows` : 'data unavailable'}`}>
            {normalise(commsWindows ?? [], missionStart, missionEnd).map((seg, i) => (
              <div key={i} className="tl-seg tl-seg--comms"
                title={`${formatUtc(seg.window.start_utc)} – ${formatUtc(seg.window.end_utc)}`}
                style={{ left: `${seg.left * 100}%`, width: `${seg.width * 100}%` }} />
            ))}
          </div>
          <SurfaceStayWindow landingUtc={landingUtc} daysOnSurface={daysOnSurface} missionStart={missionStart} missionEnd={missionEnd} />
          {markerPct !== null && <div className={`tl-marker${meetsConstraints ? ' tl-marker--both' : ''}`} style={{ left: `${markerPct}%` }} />}
        </div>
      </div>
    </td>
  );
}
