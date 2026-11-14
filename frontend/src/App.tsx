import { useState, useEffect } from 'react';
import { Sidebar } from './Sidebar';
import { MainPanel } from './MainPanel';
import { api } from './api';
import { mockSites } from './mockData';
import type { LandingSite, MissionParams, PowerParams, CommsParams, TerrainParams } from './types';

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

  useEffect(() => {
    api.getSites()
      .then(setSites)
      .catch(() => {
        setSites(mockSites);
        setUsingMock(true);
      });
  }, []);

  function toggleSite(id: string) {
    setSites(prev => prev.map(s => s.id === id ? { ...s, enabled: !s.enabled } : s));
  }

  return (
    <div className="layout">
      {usingMock && (
        <div className="mock-banner">Mock data — API offline</div>
      )}
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
        sites={sites}
        power={power}
        comms={comms}
        terrain={terrain}
        missionStart={mission.windowStart}
        missionEnd={mission.windowEnd}
      />
    </div>
  );
}
