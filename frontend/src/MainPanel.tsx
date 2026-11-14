import { useState, useEffect, useMemo } from 'react';
import { ComparisonTable } from './ComparisonTable';
import { HorizonChart } from './HorizonChart';
import { api, siteReference } from './api';
import { MapPanel } from './MapPanel';
import type { Coordinates } from './map/projection';
import { useRequest } from './useRequest';
import { dateUtc, landingWindowError } from './time';
import type { LandingSite, MissionParams, PowerParams, CommsParams, TerrainParams, Constraints, SiteAnalysisResponse } from './types';

interface Props {
  sites: LandingSite[];
  power: PowerParams;
  comms: CommsParams;
  terrain: TerrainParams;
  mission: MissionParams;
  onSiteAdd: (coordinates: Coordinates, name: string) => void;
  onSiteRename: (id: string, name: string) => void;
  onSiteDelete: (id: string) => void;
}

export function MainPanel({ sites, power, comms, terrain, mission, onSiteAdd, onSiteRename, onSiteDelete }: Props) {
  const [tab, setTab] = useState<'profiles' | 'map'>('profiles');
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [landingUtc, setLandingUtc] = useState(`${mission.windowStart}T06:00:00Z`);
  const enabled = useMemo(() => sites.filter(site => site.enabled), [sites]);
  const selectedSite = enabled.find(site => site.id === selectedId) ?? enabled[0];
  const siteId = selectedSite?.id;

  useEffect(() => {
    if (mission.windowStart) setLandingUtc(`${mission.windowStart}T06:00:00Z`);
  }, [mission.windowStart, mission.windowEnd]);

  const constraints = useMemo<Constraints>(() => ({
    days_on_surface: mission.daysOnSurface,
    horizon_clearance_deg: mission.horizonClearance,
    min_sun_visible_pct: power.minSunlight,
    max_darkness_hours: power.maxNight,
    min_earth_visible_pct: comms.minEarthContact,
    max_earth_blackout_hours: comms.maxCommsGap,
    max_slope_deg: terrain.maxSlope,
  }), [mission.daysOnSurface, mission.horizonClearance, power, comms, terrain]);

  const start = Date.parse(dateUtc(mission.windowStart));
  const end = Date.parse(dateUtc(mission.windowEnd));
  const dateError = landingWindowError(mission.windowStart, mission.windowEnd);
  const validConstraints = Object.values(constraints).every(value => Number.isFinite(value) && value >= 0)
    && Number.isInteger(mission.daysOnSurface) && mission.daysOnSurface >= 1
    && power.minSunlight <= 100 && comms.minEarthContact <= 100
    && mission.horizonClearance <= 90 && terrain.maxSlope <= 90;
  const validation = dateError ? dateError
    : !validConstraints ? 'Use positive whole mission days, percentages from 0–100, angles from 0–90°, and nonnegative time limits.' : '';
  const compareRequest = useMemo(() => validation || !enabled.length ? null
    : (signal: AbortSignal) => api.compare({
      sites: enabled.map(siteReference),
      window_start_utc: dateUtc(mission.windowStart), window_end_utc: dateUtc(mission.windowEnd),
      constraints, candidate_step_hours: 6,
    }, signal), [validation, enabled, mission.windowStart, mission.windowEnd, constraints]);
  const comparison = useRequest(compareRequest);

  const horizonsRequest = useMemo(() => validation || !enabled.length ? null
    : (signal: AbortSignal) => Promise.all(
        enabled.map(site => api.getSiteAnalysis({
          site: siteReference(site),
          window_start_utc: dateUtc(mission.windowStart), window_end_utc: dateUtc(mission.windowEnd),
          constraints,
        }, signal))
      ).then(results => new Map<string, SiteAnalysisResponse>(
        enabled.map((site, i) => [site.id, results[i]])
      )),
    [validation, enabled, mission.windowStart, mission.windowEnd, constraints]);
  const horizons = useRequest(horizonsRequest);
  function canShift(hours: number) {
    const next = Date.parse(landingUtc) + hours * 3_600_000;
    return !validation && next >= start && next <= end;
  }
  function shiftTime(hours: number) {
    if (canShift(hours)) setLandingUtc(new Date(Date.parse(landingUtc) + hours * 3_600_000).toISOString());
  }

  return (
    <main className="main">
      <div className="main-hdr">
        <h1 className="main-title">Lunar landing site navigator</h1>
        <div className="main-score" role="status">
          {comparison.loading ? 'Comparing sites…' : comparison.data ? `Scored ${comparison.data.length} sites` : `${enabled.length} sites selected`}
        </div>
      </div>
      <div className="workspace-tabs" role="tablist" aria-label="Workspace">
        {(['profiles', 'map'] as const).map(name => <button key={name} id={`tab-${name}`} role="tab"
          aria-selected={tab === name} aria-controls={`panel-${name}`} tabIndex={tab === name ? 0 : -1}
          onClick={() => setTab(name)} onKeyDown={event => {
            if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return;
            event.preventDefault();
            const next = event.key === 'Home' ? 'profiles' : event.key === 'End' ? 'map' : name === 'map' ? 'profiles' : 'map';
            setTab(next);
            document.getElementById(`tab-${next}`)?.focus();
          }}>{name === 'profiles' ? 'Profiles' : 'Map'}</button>)}
      </div>
      <div className="main-body" id="panel-profiles" role="tabpanel" aria-labelledby="tab-profiles" hidden={tab !== 'profiles'}>
        {validation && <div className="request-error" role="alert">{validation}</div>}
        <ComparisonTable sites={enabled} results={comparison.data} constraints={constraints}
          selectedId={siteId ?? null} onSelect={setSelectedId} landingTime={landingUtc}
          onTimeShift={shiftTime} onTimeSeek={setLandingUtc} canShiftBack={canShift(-6)} canShiftForward={canShift(6)}
          missionStart={dateUtc(mission.windowStart)}
          sliderEnd={dateUtc(mission.windowEnd)} disabled={!!validation}
          loading={comparison.loading} error={comparison.error} onRetry={comparison.retry} />
        <div className="bottom-row">
          <HorizonChart siteName={selectedSite?.name ?? '—'}
            analysis={siteId ? horizons.data?.get(siteId)?.analysis : undefined} landingUtc={landingUtc}
            loading={horizons.loading} error={horizons.error} onRetry={horizons.retry} />
        </div>
      </div>
      <div className="main-body map-body" id="panel-map" role="tabpanel" aria-labelledby="tab-map" hidden={tab !== 'map'}>
        <MapPanel sites={sites} constraints={constraints} mission={mission} active={tab === 'map'}
          validation={validation} showValidation={!dateError} onSiteAdd={onSiteAdd} onSiteRename={onSiteRename} onSiteDelete={onSiteDelete} />
      </div>
    </main>
  );
}
