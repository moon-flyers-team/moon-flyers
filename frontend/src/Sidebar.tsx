import { useId, useRef, useState } from 'react';
import { Section } from './Section';
import { Field } from './Field';
import { DateField } from './DateField';
import { landingWindowError } from './time';
import type { Coordinates } from './map/projection';
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
  onSiteAdd: (coordinates: Coordinates, name: string) => void;
}

export function Sidebar({
  mission, power, comms, terrain, sites,
  onMissionChange, onPowerChange, onCommsChange, onTerrainChange, onSiteToggle, onSiteAdd,
}: Props) {
  const formId = useId();
  const dateErrorId = useId();
  const dateError = landingWindowError(mission.windowStart, mission.windowEnd);
  const addButtonRef = useRef<HTMLButtonElement>(null);
  const nameRef = useRef<HTMLInputElement>(null);
  const [adding, setAdding] = useState(false);
  const [siteName, setSiteName] = useState('');
  const [latitude, setLatitude] = useState('');
  const [longitude, setLongitude] = useState('');
  const [announcement, setAnnouncement] = useState('');
  const validCoordinates = latitude.trim() !== '' && longitude.trim() !== ''
    && Number.isFinite(Number(latitude)) && Number.isFinite(Number(longitude))
    && Number(latitude) >= -90 && Number(latitude) <= 90 && Number(longitude) >= -180 && Number(longitude) <= 180;
  function closeForm() {
    setAdding(false); setSiteName(''); setLatitude(''); setLongitude('');
    addButtonRef.current?.focus();
  }
  return (
    <aside className="sidebar">
      <Section title="Mission Planner">
        {dateError && <div id={dateErrorId} className="sb-mission-error" role="alert">
          <strong>Invalid landing window</strong><p>{dateError}</p>
        </div>}
        <DateField label="Landing window start (UTC)" value={mission.windowStart}
          errorId={dateError ? dateErrorId : undefined}
          onChange={windowStart => onMissionChange({ ...mission, windowStart })} />
        <DateField label="Landing window end (UTC)" value={mission.windowEnd}
          errorId={dateError ? dateErrorId : undefined}
          onChange={windowEnd => onMissionChange({ ...mission, windowEnd })} />
        <div className="sb-row">
          <Field label="Days on surface">
            <div className="sb-unit">
              <input
                type="number"
                className="sb-input"
                min={1}
                step={1}
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
                min={0}
                max={90}
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
                min={0}
                max={100}
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
                min={0}
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
                min={0}
                max={100}
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
                min={0}
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
              min={0}
              max={90}
              value={terrain.maxSlope}
              onChange={e => onTerrainChange({ ...terrain, maxSlope: +e.target.value })}
            />
            <span>°</span>
          </div>
        </Field>
      </Section>

      <Section title="Sites" action={<button ref={addButtonRef} type="button" className="ct-btn sb-add-site"
        aria-label="Add site manually" aria-expanded={adding} aria-controls={formId}
        onClick={() => { setAdding(true); setAnnouncement(''); nameRef.current?.focus(); }}>+ Add</button>}>
        {adding && <form id={formId} className="sb-site-form" aria-label="Add a site manually"
          onKeyDown={event => { if (event.key === 'Escape') { event.preventDefault(); closeForm(); } }}
          onSubmit={event => {
            event.preventDefault();
            if (!siteName.trim() || !validCoordinates) return;
            onSiteAdd({ latitude_deg: Number(latitude), longitude_deg: Number(longitude) }, siteName.trim());
            setAnnouncement(`Added ${siteName.trim()} to Sites.`);
            closeForm();
          }}>
          <label>Site name<input ref={nameRef} autoFocus className="sb-input" required maxLength={80}
            value={siteName} onChange={event => setSiteName(event.target.value)} /></label>
          <label>Latitude (decimal degrees)<input type="number" className="sb-input" required step="any" min={-90} max={90}
            value={latitude} onChange={event => setLatitude(event.target.value)} /></label>
          <label>Longitude (decimal degrees)<input type="number" className="sb-input" required step="any" min={-180} max={180}
            value={longitude} onChange={event => setLongitude(event.target.value)} /></label>
          <p>Latitude −90…90°, longitude −180…180°. East-positive longitude; use negative values for west.</p>
          <div className="sb-form-actions"><button type="submit" className="ct-btn" disabled={!siteName.trim() || !validCoordinates}>Add site</button>
            <button type="button" className="ct-btn" onClick={closeForm}>Cancel</button></div>
          <small>Custom sites are saved for this session.</small>
        </form>}
        {announcement && <p className="sb-site-announcement" role="status">{announcement}</p>}
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
                  <div className="sb-site-coords">{site.latitude_deg}°, {site.longitude_deg}°</div>
                </div>
              </label>
            </li>
          ))}
        </ul>
      </Section>
    </aside>
  );
}
