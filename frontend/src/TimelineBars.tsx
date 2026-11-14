import type { TimeWindow } from './types';

interface Props {
  powerWindows?: TimeWindow[];
  commsWindows?: TimeWindow[];
  missionStart?: string;
  missionEnd?: string;
}

function normalise(windows: TimeWindow[], missionStart: string, missionEnd: string) {
  const start = new Date(missionStart).getTime();
  const range = new Date(missionEnd).getTime() - start;
  return windows.map(w => ({
    left: (new Date(w.start).getTime() - start) / range,
    width: (new Date(w.end).getTime() - new Date(w.start).getTime()) / range,
  }));
}

function Track({ windows }: { windows?: TimeWindow[]; missionStart?: string; missionEnd?: string; cls: string }) {
  return (
    <td>
      <div className="tl-track">
        {windows && windows.length > 0 ? null : (
          <div className="tl-empty" />
        )}
      </div>
    </td>
  );
}

export function TimelineBars({ powerWindows, commsWindows, missionStart, missionEnd }: Props) {
  const hasData = powerWindows && commsWindows && missionStart && missionEnd;

  if (!hasData) {
    return (
      <>
        <td><div className="tl-track tl-track--empty" /></td>
        <td><div className="tl-track tl-track--empty" /></td>
      </>
    );
  }

  const powerSegs = normalise(powerWindows, missionStart, missionEnd);
  const commsSegs = normalise(commsWindows, missionStart, missionEnd);

  return (
    <>
      <td>
        <div className="tl-track">
          {powerSegs.map((seg, i) => (
            <div
              key={i}
              className="tl-seg tl-seg--power"
              style={{ left: `${seg.left * 100}%`, width: `${seg.width * 100}%` }}
            />
          ))}
        </div>
      </td>
      <td>
        <div className="tl-track">
          {commsSegs.map((seg, i) => (
            <div
              key={i}
              className="tl-seg tl-seg--comms"
              style={{ left: `${seg.left * 100}%`, width: `${seg.width * 100}%` }}
            />
          ))}
        </div>
      </td>
    </>
  );
}

// suppress unused warning on Track until wired up
void Track;
