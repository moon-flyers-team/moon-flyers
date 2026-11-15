import { useState, useEffect, useMemo } from 'react';
import { ComparisonTable } from './ComparisonTable';
import { HorizonChart } from './HorizonChart';
import { MapPanel } from './MapPanel';
import { TouristRoutePanel } from './TouristRoutePanel';
import type { Coordinates } from './map/projection';
import { useSiteBatch } from './useSiteBatch';
import { dateUtc, landingWindowError } from './time';
import type { LandingSite, MissionParams, PowerParams, CommsParams, TerrainParams, Constraints } from './types';

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
  const [tab, setTab] = useState<'profiles' | 'map' | 'route'>('profiles');
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [landingUtc, setLandingUtc] = useState(`${mission.windowStart}T06:00:00Z`);
  const enabled = useMemo(() => sites.filter(site => site.enabled), [sites]);
  const selectedSite = enabled.find(site => site.id === selectedId) ?? enabled[0];
  const siteId = selectedSite?.id;
  const [landingSiteId, setLandingSiteId] = useState<string | null>(null);
  const landingSite = sites.find(site => site.id === landingSiteId);
  const tabs: ('profiles' | 'map' | 'route')[] = landingSite ? ['map', 'profiles', 'route'] : ['map', 'profiles'];
  const activeTab = tab === 'route' && !landingSite ? 'profiles' : tab;
  useEffect(() => {
    if (landingSiteId && !landingSite) { setLandingSiteId(null); setTab('profiles'); }
  }, [landingSiteId, landingSite]);
  function chooseLandingSite(id: string) {
    setSelectedId(id);
    setLandingSiteId(id);
    setTab('route');
  }

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

  const dateError = landingWindowError(mission.windowStart, mission.windowEnd);
  const validConstraints = Object.values(constraints).every(value => Number.isFinite(value) && value >= 0)
    && Number.isInteger(mission.daysOnSurface) && mission.daysOnSurface >= 1
    && power.minSunlight <= 100 && comms.minEarthContact <= 100
    && mission.horizonClearance <= 90 && terrain.maxSlope <= 90;
  const validation = dateError ? dateError
    : !validConstraints ? 'Use positive whole mission days, percentages from 0–100, angles from 0–90°, and nonnegative time limits.' : '';
  const compareQuery = useMemo(() => validation || !enabled.length ? null
    : ({ windowStart: dateUtc(mission.windowStart), windowEnd: dateUtc(mission.windowEnd), constraints }),
    [validation, enabled.length, mission.windowStart, mission.windowEnd, constraints]);
  const batch = useSiteBatch(enabled, compareQuery);

  const profilesLoading = batch.loading;

  return (
    <main className="main">
      <div className="main-hdr">
        <h1 className="main-title">Lunar landing site navigator</h1>
        <div className="main-score" role="status">
          {batch.loading ? 'Comparing sites…' : batch.results ? `Scored ${batch.loadedCount} sites` : `${enabled.length} sites selected`}
        </div>
      </div>
      <div className="workspace-tabs" role="tablist" aria-label="Workspace">
        {tabs.map(name => <button key={name} id={`tab-${name}`} role="tab"
          aria-selected={activeTab === name} aria-controls={`panel-${name}`} tabIndex={activeTab === name ? 0 : -1}
          onClick={() => setTab(name)} onKeyDown={event => {
            if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return;
            event.preventDefault();
            const index = tabs.indexOf(name);
            const next = event.key === 'Home' ? tabs[0] : event.key === 'End' ? tabs[tabs.length - 1]
              : tabs[(index + (event.key === 'ArrowRight' ? 1 : -1) + tabs.length) % tabs.length];
            setTab(next);
            document.getElementById(`tab-${next}`)?.focus();
          }}>{name === 'profiles' ? 'Site Comparison' : name === 'map' ? 'Map' : 'Route Planner'}</button>)}
      </div>
      <div className="main-body profiles-body" id="panel-profiles" role="tabpanel" aria-labelledby="tab-profiles" hidden={activeTab !== 'profiles'}>
        {activeTab === 'profiles' && profilesLoading && <div className="profiles-loading-overlay">
          <div className="profiles-loading-popup" role="status" aria-live="polite" aria-atomic="true">
            <span className="profiles-loading-spinner" aria-hidden="true" />
            <strong>Loading site profiles…</strong>
            <p>Fetching comparison and visibility data. This can take 10–30 seconds.</p>
          </div>
        </div>}
        {validation && !dateError && <div className="request-error" role="alert">{validation}</div>}
        <ComparisonTable sites={enabled} results={batch.results} constraints={constraints}
          selectedId={siteId ?? null} onSelect={setSelectedId} onLandingSelect={chooseLandingSite} landingSiteId={landingSiteId} landingTime={landingUtc}
          onTimeSeek={setLandingUtc}
          missionStart={dateUtc(mission.windowStart)}
          sliderEnd={dateUtc(mission.windowEnd)} disabled={!!validation}
          loading={batch.loading} error={batch.error} onRetry={batch.retry}>
          <div className="hz-grid">
            {enabled.map(site => <HorizonChart key={site.id} siteName={site.name}
              analysis={batch.analyses.get(site.id)?.analysis} landingUtc={landingUtc}
              selected={site.id === siteId} onSelect={() => setSelectedId(site.id)}
              loading={batch.loading} error={batch.error} onRetry={batch.retry} />)}
          </div>
        </ComparisonTable>
      </div>
      <div className="main-body map-body" id="panel-map" role="tabpanel" aria-labelledby="tab-map" hidden={tab !== 'map'}>
        <MapPanel sites={sites} landingSiteId={landingSiteId} constraints={constraints} mission={mission} active={tab === 'map'}
          validation={validation} showValidation={!dateError} onSiteAdd={onSiteAdd} onSiteRename={onSiteRename} onSiteDelete={onSiteDelete} />
      </div>
      {landingSite && <div className="main-body route-planner-body" id="panel-route" role="tabpanel"
        aria-labelledby="tab-route" hidden={activeTab !== 'route'}>
        <TouristRoutePanel key={`${landingSite.id}:${landingSite.latitude_deg}:${landingSite.longitude_deg}`}
          landingSite={landingSite} landingUtc={landingUtc} poiRadiusKm={mission.poiRadiusKm ?? 40} onClose={() => { setLandingSiteId(null); setTab('profiles'); }} />
      </div>}
    </main>
  );
}
