import { useEffect, useRef } from 'react';
import type { TimeWindow } from './types';
import { formatUtc } from './time';

const STEP_MS = 6 * 3_600_000;

interface Props {
  powerWindows?: TimeWindow[];
  commsWindows?: TimeWindow[];
  missionStart: string;
  missionEnd: string;
  landingUtc?: string;
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
export function TimelineBars({ powerWindows, commsWindows, missionStart, missionEnd, landingUtc, onChange }: Props) {
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
          {markerPct !== null && <div className="tl-marker" style={{ left: `${markerPct}%` }} />}
        </div>
      </div>
    </td>
  );
}
