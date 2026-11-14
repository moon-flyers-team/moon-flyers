import type { TimeWindow } from './types';
import { formatUtc } from './time';

interface Props {
  powerWindows?: TimeWindow[];
  commsWindows?: TimeWindow[];
  missionStart: string;
  missionEnd: string;
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
export function TimelineBars({ powerWindows, commsWindows, missionStart, missionEnd }: Props) {
  return <>{(['power', 'comms'] as const).map(kind => {
    const windows = kind === 'power' ? powerWindows : commsWindows;
    const label = kind === 'power' ? 'Sun' : 'Earth';
    return <td key={kind}><div className={`tl-track${windows ? '' : ' tl-track--empty'}`}
      role="img" aria-label={`${label}: ${windows ? `${windows.length} visibility windows` : 'data unavailable'}`}>
      {normalise(windows ?? [], missionStart, missionEnd).map((seg, index) => <div key={index}
        className={`tl-seg tl-seg--${kind}`} title={`${formatUtc(seg.window.start_utc)} – ${formatUtc(seg.window.end_utc)}`}
        style={{ left: `${seg.left * 100}%`, width: `${seg.width * 100}%` }} />)}
    </div></td>;
  })}</>;
}
