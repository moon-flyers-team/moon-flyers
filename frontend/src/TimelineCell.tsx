import { useMemo, useEffect, useRef } from 'react';
import type { TimeWindow } from './types';
import { normalise } from './TimelineBars';
import { formatUtc } from './time';

const STEP_MS = 6 * 3_600_000;

interface Props {
  windows?: TimeWindow[];
  type: 'power' | 'comms';
  missionStart: string;
  missionEnd: string;
  landingUtc?: string;
  onChange?: (iso: string) => void;
}

export function TimelineCell({ windows, type, missionStart, missionEnd, landingUtc, onChange }: Props) {
  const startMs = Date.parse(missionStart);
  const endMs   = Date.parse(missionEnd);
  const trackRef = useRef<HTMLDivElement>(null);
  const dragging = useRef(false);

  const markerPct = landingUtc && Number.isFinite(startMs) && Number.isFinite(endMs) && endMs > startMs
    ? Math.max(0, Math.min(100, (Date.parse(landingUtc) - startMs) / (endMs - startMs) * 100))
    : null;

  function seek(clientX: number) {
    if (!onChange || !trackRef.current || !Number.isFinite(startMs) || !Number.isFinite(endMs)) return;
    const rect = trackRef.current.getBoundingClientRect();
    const pct  = Math.max(0, Math.min(1, (clientX - rect.left) / rect.width));
    onChange(new Date(Math.round((startMs + pct * (endMs - startMs)) / STEP_MS) * STEP_MS).toISOString());
  }

  useEffect(() => {
    if (!onChange) return;
    function onMove(e: MouseEvent) { if (dragging.current) seek(e.clientX); }
    function onUp()  { dragging.current = false; }
    window.addEventListener('mousemove', onMove);
    window.addEventListener('mouseup',  onUp);
    return () => { window.removeEventListener('mousemove', onMove); window.removeEventListener('mouseup', onUp); };
  }, [onChange, startMs, endMs]);

  const segs = useMemo(() => normalise(windows ?? [], missionStart, missionEnd), [windows, missionStart, missionEnd]);
  const segClass = type === 'power' ? 'tl-seg--power' : 'tl-seg--comms';

  return (
    <td className="tl-cell">
      <div
        ref={trackRef}
        className={`tl-track${windows ? '' : ' tl-track--empty'}${onChange ? ' tl-tracks--interactive' : ''}`}
        onMouseDown={e => { dragging.current = true; seek(e.clientX); }}
        role="img"
        aria-label={`${type === 'power' ? 'Sun' : 'Earth'}: ${windows ? `${windows.length} visibility windows` : 'unavailable'}`}
      >
        {segs.map((seg, i) => (
          <div key={i} className={`tl-seg ${segClass}`}
            title={`${formatUtc(seg.window.start_utc)} – ${formatUtc(seg.window.end_utc)}`}
            style={{ left: `${seg.left * 100}%`, width: `${seg.width * 100}%` }}
          />
        ))}
        {markerPct !== null && <div className="tl-marker" style={{ left: `${markerPct}%` }} />}
      </div>
    </td>
  );
}
