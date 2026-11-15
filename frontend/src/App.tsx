import { useState, useEffect, useId, useRef } from 'react';
import { useRequest } from './useRequest';
import { Sidebar } from './Sidebar';
import { MainPanel } from './MainPanel';
import { Section } from './Section';
import { Field } from './Field';
import { DateField } from './DateField';
import { api } from './api';
import { mockSites } from './mockData';
import { landingWindowError } from './time';
import type { LandingSite, MissionParams, PowerParams, CommsParams, TerrainParams } from './types';
import type { Coordinates } from './map/projection';

export default function App() {
  const [mission, setMission] = useState<MissionParams>({
    windowStart: '2027-08-01',
    windowEnd: '2027-10-31',
    daysOnSurface: 14,
    horizonClearance: 0.3,
  });
  const [power, setPower] = useState<PowerParams>({ minSunlight: 60, maxNight: 96 });
  const [comms, setComms] = useState<CommsParams>({ minEarthContact: 45, maxCommsGap: 240 });
  const [terrain, setTerrain] = useState<TerrainParams>({ maxSlope: 8 });
  const [sites, setSites] = useState<LandingSite[]>([]);
  const [usingMock, setUsingMock] = useState(false);
  const [backendMock, setBackendMock] = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [applied, setApplied] = useState({ mission, power, comms, terrain });

  const catalogue = useRequest(api.getCatalogue, 0);
  useEffect(() => {
    if (catalogue.data) {
      const catalogueSites = catalogue.data.sites;
      setSites(previous => [...catalogueSites.map(site => ({ ...site,
        enabled: previous.find(existing => existing.id === site.id)?.enabled ?? true })),
        ...previous.filter(site => site.custom)]);
      setUsingMock(false);
      setBackendMock(catalogue.data.isMock);
    } else if (catalogue.error) {
      setSites(previous => [...mockSites, ...previous.filter(site => site.custom)]);
      setBackendMock(false);
      setUsingMock(true);
    }
  }, [catalogue.data, catalogue.error]);

  function toggleSite(id: string) {
    setSites(prev => prev.map(s => s.id === id ? { ...s, enabled: !s.enabled } : s));
  }
  function addSite(coordinates: Coordinates, name: string) {
    setSites(previous => [...previous, { ...coordinates, id: `custom_${crypto.randomUUID()}`,
      name, group: 'Custom sites', custom: true, enabled: true }]);
  }
  function renameSite(id: string, name: string) {
    if (!name.trim()) return;
    setSites(previous => previous.map(site => site.id === id && site.custom ? { ...site, name: name.trim() } : site));
  }
  function deleteSite(id: string) {
    setSites(previous => previous.filter(site => site.id !== id || !site.custom));
  }

  return (
    <div className="app-shell">
      {catalogue.loading && <div className="api-banner" role="status">Loading site catalogue…</div>}
      {backendMock && !usingMock && (
        <div className="api-banner" role="status">Mock backend — synthetic demo data for interface testing</div>
      )}
      {usingMock && (
        <div className="mock-banner" role="alert">
          <span>API unavailable — showing example sites. Analysis requires the backend. {catalogue.error}</span>
          <button className="ct-btn" onClick={catalogue.retry} disabled={catalogue.loading}>Retry connection</button>
        </div>
      )}
      {settingsOpen && (
        <SettingsModal
          mission={mission} power={power} comms={comms} terrain={terrain}
          onMissionChange={setMission} onPowerChange={setPower}
          onCommsChange={setComms} onTerrainChange={setTerrain}
          onClose={() => setSettingsOpen(false)}
          onCompare={() => { setApplied({ mission, power, comms, terrain }); setSettingsOpen(false); }}
        />
      )}
      <div className="layout">
        <Sidebar
          sites={sites}
          onSiteToggle={toggleSite}
          onSiteAdd={addSite}
          onOpenSettings={() => setSettingsOpen(true)}
        />
        <MainPanel
          onSiteAdd={addSite}
          onSiteRename={renameSite}
          onSiteDelete={deleteSite}
          sites={sites}
          power={applied.power}
          comms={applied.comms}
          terrain={applied.terrain}
          mission={applied.mission}
        />
      </div>
    </div>
  );
}

interface SettingsModalProps {
  mission: MissionParams;
  power: PowerParams;
  comms: CommsParams;
  terrain: TerrainParams;
  onMissionChange: (m: MissionParams) => void;
  onPowerChange: (p: PowerParams) => void;
  onCommsChange: (c: CommsParams) => void;
  onTerrainChange: (t: TerrainParams) => void;
  onClose: () => void;
  onCompare: () => void;
}

function SettingsModal({ mission, power, comms, terrain, onMissionChange, onPowerChange, onCommsChange, onTerrainChange, onClose, onCompare }: SettingsModalProps) {
  const dateErrorId = useId();
  const dateError = landingWindowError(mission.windowStart, mission.windowEnd);
  const overlayRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function onKey(e: KeyboardEvent) { if (e.key === 'Escape') onClose(); }
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);

  return (
    <div className="settings-overlay" ref={overlayRef} role="dialog" aria-modal="true" aria-label="Mission planner settings"
      onClick={e => { if (e.target === overlayRef.current) onClose(); }}>
      <div className="settings-modal">
        <div className="settings-modal-hdr">
          <span className="settings-modal-title">Mission Planner</span>
          <button className="settings-close-btn" onClick={onClose} aria-label="Close settings">✕</button>
        </div>
        <div className="settings-modal-body">
          <Section title="Mission">
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
                  <input type="number" className="sb-input" min={1} step={1} value={mission.daysOnSurface}
                    onChange={e => onMissionChange({ ...mission, daysOnSurface: +e.target.value })} />
                  <span>d</span>
                </div>
              </Field>
              <Field label="Horizon clearance">
                <div className="sb-unit">
                  <input type="number" className="sb-input" step="0.1" min={0} max={90} value={mission.horizonClearance}
                    onChange={e => onMissionChange({ ...mission, horizonClearance: +e.target.value })} />
                  <span>°</span>
                </div>
              </Field>
            </div>
          </Section>

          <Section title="Power (Sun)" dot="#f5a623">
            <div className="sb-row">
              <Field label="Min sunlight">
                <div className="sb-unit">
                  <input type="number" className="sb-input" min={0} max={100} value={power.minSunlight}
                    onChange={e => onPowerChange({ ...power, minSunlight: +e.target.value })} />
                  <span>%</span>
                </div>
              </Field>
              <Field label="Max night">
                <div className="sb-unit">
                  <input type="number" className="sb-input" min={0} value={power.maxNight}
                    onChange={e => onPowerChange({ ...power, maxNight: +e.target.value })} />
                  <span>h</span>
                </div>
              </Field>
            </div>
          </Section>

          <Section title="Comms (Earth)" dot="#4fc3f7">
            <div className="sb-row">
              <Field label="Min Earth contact">
                <div className="sb-unit">
                  <input type="number" className="sb-input" min={0} max={100} value={comms.minEarthContact}
                    onChange={e => onCommsChange({ ...comms, minEarthContact: +e.target.value })} />
                  <span>%</span>
                </div>
              </Field>
              <Field label="Max comms gap">
                <div className="sb-unit">
                  <input type="number" className="sb-input" min={0} value={comms.maxCommsGap}
                    onChange={e => onCommsChange({ ...comms, maxCommsGap: +e.target.value })} />
                  <span>h</span>
                </div>
              </Field>
            </div>
          </Section>

          <Section title="Terrain">
            <Field label="Max slope">
              <div className="sb-unit">
                <input type="number" className="sb-input" min={0} max={90} value={terrain.maxSlope}
                  onChange={e => onTerrainChange({ ...terrain, maxSlope: +e.target.value })} />
                <span>°</span>
              </div>
            </Field>
          </Section>
        </div>
        <div className="settings-modal-footer">
          <button type="button" className="settings-compare-btn" onClick={onCompare} disabled={!!dateError}>
            SET MISSION
          </button>
        </div>
      </div>
    </div>
  );
}
