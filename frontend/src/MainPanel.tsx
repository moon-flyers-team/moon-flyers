import { useState, useEffect } from 'react';
import { ComparisonTable } from './ComparisonTable';
import { HorizonChart } from './HorizonChart';
import { api } from './api';
import type { LandingSite, HorizonPoint, PowerParams, CommsParams, TerrainParams } from './types';

interface Props {
  sites: LandingSite[];
  power: PowerParams;
  comms: CommsParams;
  terrain: TerrainParams;
  missionStart: string;
  missionEnd: string;
}

export function MainPanel({ sites, power, comms, terrain, missionStart, missionEnd }: Props) {
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [landingTime, setLandingTime] = useState('');
  const [horizonData, setHorizonData] = useState<HorizonPoint[]>([]);
  const [horizonLoading, setHorizonLoading] = useState(false);

  const selectedSite = sites.find(s => s.id === selectedId);

  function shiftTime(hours: number) {
    const [datePart, timePart] = landingTime.split(' ');
    const d = new Date(`${datePart}T${timePart}:00Z`);
    d.setUTCHours(d.getUTCHours() + hours);
    const iso = d.toISOString();
    setLandingTime(`${iso.slice(0, 10)} ${iso.slice(11, 16)}`);
  }

  useEffect(() => {
    if (!missionStart) return;
    setLandingTime(`${missionStart} 06:00`);
  }, [missionStart]);

  useEffect(() => {
    if (!selectedId || !landingTime) {
      setHorizonData([]);
      return;
    }
    setHorizonLoading(true);
    api.getHorizon(selectedId, landingTime)
      .then(setHorizonData)
      .catch(() => setHorizonData([]))
      .finally(() => setHorizonLoading(false));
  }, [selectedId, landingTime]);

  return (
    <main className="main">
      <div className="main-hdr">
        <h1 className="main-title">Lunar landing site navigator</h1>
        <div className="main-score">
          <span className="score-dot" />
          Scored {sites.filter(s => s.enabled).length} sites
          {landingTime && ` at ${landingTime.split(' ')[1]} UTC`}
        </div>
      </div>

      <div className="main-body">
        <ComparisonTable
          sites={sites}
          power={power}
          comms={comms}
          terrain={terrain}
          selectedId={selectedId}
          onSelect={setSelectedId}
          landingTime={landingTime}
          onTimeShift={shiftTime}
          missionStart={missionStart}
          missionEnd={missionEnd}
        />

        <div className="bottom-row">
          <HorizonChart
            siteName={selectedSite?.name ?? '—'}
            data={horizonData}
            loading={horizonLoading}
          />
        </div>
      </div>
    </main>
  );
}
