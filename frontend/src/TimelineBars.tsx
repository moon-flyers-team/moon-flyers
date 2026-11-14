import { useMemo } from 'react';
import type { TimeWindow } from './types';
import { formatUtc } from './time';

interface Props {
  powerWindows?: TimeWindow[];
  commsWindows?: TimeWindow[];
  missionStart: string;
  missionEnd: string;
  landingUtc?: string;
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
export function TimelineBars({ powerWindows, commsWindows, missionStart, missionEnd, landingUtc }: Props) {
  const startMs = Date.parse(missionStart);
  const endMs   = Date.parse(missionEnd);

  const ticks = useMemo(() => {
    if (!Number.isFinite(startMs) || !Number.isFinite(endMs) || endMs <= startMs) return [];
    const result: { pct: number; label: string }[] = [];
    const d = new Date(startMs);
    d.setUTCDate(1);
    d.setUTCMonth(d.getUTCMonth() + 1);
    while (d.getTime() < endMs) {
      result.push({
        pct: (d.getTime() - startMs) / (endMs - startMs) * 100,
        label: d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', timeZone: 'UTC' }),
      });
      d.setUTCMonth(d.getUTCMonth() + 1);
    }
    return result;
  }, [startMs, endMs]);

  const markerPct = landingUtc && Number.isFinite(startMs) && Number.isFinite(endMs) && endMs > startMs
    ? Math.max(0, Math.min(100, (Date.parse(landingUtc) - startMs) / (endMs - startMs) * 100))
    : null;

  return (
    <td>
      <div className="tl-wrap">
        <div className="tl-ticks">
          {ticks.map(t => (
            <span key={t.label} className="tl-tick-label" style={{ left: `${t.pct}%` }}>{t.label}</span>
          ))}
        </div>
        <div className="tl-tracks">
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
