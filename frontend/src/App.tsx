import { useState, useEffect } from 'react';
import { useRequest } from './useRequest';
import { Sidebar } from './Sidebar';
import { MainPanel } from './MainPanel';
import { api } from './api';
import { mockSites } from './mockData';
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
      name, group: 'Custom map sites', custom: true, enabled: true }]);
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
      <div className="layout">
        <Sidebar
          mission={mission}
          power={power}
          comms={comms}
          terrain={terrain}
          sites={sites}
          onMissionChange={setMission}
          onPowerChange={setPower}
          onCommsChange={setComms}
          onTerrainChange={setTerrain}
          onSiteToggle={toggleSite}
        />
        <MainPanel
          onSiteAdd={addSite}
          sites={sites}
          power={power}
          comms={comms}
          terrain={terrain}
          mission={mission}
        />
      </div>
    </div>
  );
}
