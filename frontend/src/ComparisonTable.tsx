import { FitBadge } from './FitBadge';
import { TimelineBars } from './TimelineBars';
import type { LandingSite, PowerParams, CommsParams, TerrainParams } from './types';

interface NumCellProps {
  value: number;
  threshold: number;
  hi: boolean;
  unit?: string;
}

function NumCell({ value, threshold, hi, unit = '' }: NumCellProps) {
  const warn = hi ? value > threshold : value < threshold;
  return (
    <td className={warn ? 'warn' : ''}>
      {warn && <span className="warn-icon">⚠ </span>}
      {value}{unit}
    </td>
  );
}

interface Props {
  sites: LandingSite[];
  power: PowerParams;
  comms: CommsParams;
  terrain: TerrainParams;
  selectedId: string | null;
  onSelect: (id: string) => void;
  landingTime: string;
  onTimeShift: (hours: number) => void;
  missionStart: string;
  missionEnd: string;
}

export function ComparisonTable({
  sites, power, comms, terrain,
  selectedId, onSelect,
  landingTime, onTimeShift,
  missionStart, missionEnd,
}: Props) {
  const visible = sites.filter(s => s.enabled);

  return (
    <div className="ct-wrap">
      <div className="ct-topbar">
        <span className="ct-tab">Comparison</span>
        <div className="ct-time">
          <span className="ct-time-label">Landing (UTC)</span>
          <button className="ct-btn" onClick={() => onTimeShift(-6)}>-6 h</button>
          <span className="ct-time-val">{landingTime}</span>
          <button className="ct-btn" onClick={() => onTimeShift(6)}>+6 h</button>
        </div>
      </div>

      <div className="ct-scroll">
        <table className="ct">
          <thead>
            <tr>
              <th rowSpan={2} className="ct-left">Site</th>
              <th rowSpan={2}>Fit</th>
              <th colSpan={2} className="ct-grp ct-grp--power">
                <span className="grp-dot grp-dot--power" /> Power (Sun)
              </th>
              <th colSpan={2} className="ct-grp ct-grp--comms">
                <span className="grp-dot grp-dot--comms" /> Comms (Earth)
              </th>
              <th rowSpan={2}>
                Terrain<br />
                <span className="th-sub">Slope max {terrain.maxSlope}°</span>
              </th>
              <th rowSpan={2}>Power met</th>
              <th rowSpan={2}>Comms met</th>
            </tr>
            <tr>
              <th>Sunlight<br /><span className="th-sub">min {power.minSunlight} %</span></th>
              <th>Longest night<br /><span className="th-sub">max {power.maxNight} h</span></th>
              <th>Earth contact<br /><span className="th-sub">min {comms.minEarthContact} %</span></th>
              <th>Longest gap<br /><span className="th-sub">max {comms.maxCommsGap} h</span></th>
            </tr>
          </thead>
          <tbody>
            {visible.length === 0 && (
              <tr>
                <td colSpan={9} className="ct-empty">No sites selected</td>
              </tr>
            )}
            {visible.map(site => (
              <tr
                key={site.id}
                className={selectedId === site.id ? 'row-sel' : ''}
                onClick={() => onSelect(site.id)}
              >
                <td className="ct-left ct-name">{site.name}</td>
                <td><FitBadge fit={site.fit} /></td>
                <NumCell value={site.sunlight} threshold={power.minSunlight} hi={false} />
                <NumCell value={site.longestNight} threshold={power.maxNight} hi />
                <td>{site.earthContact}</td>
                <td>{site.longestGap}</td>
                <NumCell value={site.slope} threshold={terrain.maxSlope} hi unit="°" />
                <TimelineBars
                  powerWindows={site.powerWindows}
                  commsWindows={site.commsWindows}
                  missionStart={missionStart}
                  missionEnd={missionEnd}
                />
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
