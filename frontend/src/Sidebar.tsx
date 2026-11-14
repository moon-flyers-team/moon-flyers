import { Section } from './Section';
import { Field } from './Field';
import type { LandingSite, MissionParams, PowerParams, CommsParams, TerrainParams } from './types';

interface Props {
  mission: MissionParams;
  power: PowerParams;
  comms: CommsParams;
  terrain: TerrainParams;
  sites: LandingSite[];
  onMissionChange: (m: MissionParams) => void;
  onPowerChange: (p: PowerParams) => void;
  onCommsChange: (c: CommsParams) => void;
  onTerrainChange: (t: TerrainParams) => void;
  onSiteToggle: (id: string) => void;
}

export function Sidebar({
  mission, power, comms, terrain, sites,
  onMissionChange, onPowerChange, onCommsChange, onTerrainChange, onSiteToggle,
}: Props) {
  return (
    <aside className="sidebar">
      <Section title="Mission Planner">
        <Field label="Landing window start (UTC)">
          <input
            type="date"
            className="sb-input"
            value={mission.windowStart}
            onChange={e => onMissionChange({ ...mission, windowStart: e.target.value })}
          />
        </Field>
        <Field label="Landing window end (UTC)">
          <input
            type="date"
            className="sb-input"
            value={mission.windowEnd}
            onChange={e => onMissionChange({ ...mission, windowEnd: e.target.value })}
          />
        </Field>
        <div className="sb-row">
          <Field label="Days on surface">
            <div className="sb-unit">
              <input
                type="number"
                className="sb-input"
                value={mission.daysOnSurface}
                onChange={e => onMissionChange({ ...mission, daysOnSurface: +e.target.value })}
              />
              <span>d</span>
            </div>
          </Field>
          <Field label="Horizon clearance">
            <div className="sb-unit">
              <input
                type="number"
                className="sb-input"
                step="0.1"
                value={mission.horizonClearance}
                onChange={e => onMissionChange({ ...mission, horizonClearance: +e.target.value })}
              />
              <span>°</span>
            </div>
          </Field>
        </div>
      </Section>

      <Section title="Power (Sun)" dot="#f5a623">
        <div className="sb-row">
          <Field label="Min sunlight">
            <div className="sb-unit">
              <input
                type="number"
                className="sb-input"
                value={power.minSunlight}
                onChange={e => onPowerChange({ ...power, minSunlight: +e.target.value })}
              />
              <span>%</span>
            </div>
          </Field>
          <Field label="Max night">
            <div className="sb-unit">
              <input
                type="number"
                className="sb-input"
                value={power.maxNight}
                onChange={e => onPowerChange({ ...power, maxNight: +e.target.value })}
              />
              <span>h</span>
            </div>
          </Field>
        </div>
      </Section>

      <Section title="Comms (Earth)" dot="#4fc3f7">
        <div className="sb-row">
          <Field label="Min Earth contact">
            <div className="sb-unit">
              <input
                type="number"
                className="sb-input"
                value={comms.minEarthContact}
                onChange={e => onCommsChange({ ...comms, minEarthContact: +e.target.value })}
              />
              <span>%</span>
            </div>
          </Field>
          <Field label="Max comms gap">
            <div className="sb-unit">
              <input
                type="number"
                className="sb-input"
                value={comms.maxCommsGap}
                onChange={e => onCommsChange({ ...comms, maxCommsGap: +e.target.value })}
              />
              <span>h</span>
            </div>
          </Field>
        </div>
      </Section>

      <Section title="Terrain">
        <Field label="Max slope">
          <div className="sb-unit">
            <input
              type="number"
              className="sb-input"
              value={terrain.maxSlope}
              onChange={e => onTerrainChange({ ...terrain, maxSlope: +e.target.value })}
            />
            <span>°</span>
          </div>
        </Field>
      </Section>

      <Section title="Sites">
        <span className="sb-count">
          {sites.filter(s => s.enabled).length} of {sites.length} compared
        </span>
        <ul className="sb-sites">
          {sites.map(site => (
            <li key={site.id}>
              <label className="sb-site">
                <input
                  type="checkbox"
                  checked={site.enabled}
                  onChange={() => onSiteToggle(site.id)}
                />
                <div>
                  <div className="sb-site-name">{site.name}</div>
                  <div className="sb-site-coords">{site.lat}°, {site.lon}°</div>
                </div>
              </label>
            </li>
          ))}
        </ul>
      </Section>
    </aside>
  );
}
