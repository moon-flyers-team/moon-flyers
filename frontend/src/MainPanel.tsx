import { useState, useEffect, useMemo } from 'react';
import { ComparisonTable } from './ComparisonTable';
import { HorizonChart } from './HorizonChart';
import { api, siteReference } from './api';
import { MapPanel } from './MapPanel';
import { TouristRoutePanel } from './TouristRoutePanel';
import { distanceMetres } from './map/projection';
import type { Coordinates } from './map/projection';
import { useRequest } from './useRequest';
import { DAY_MS, dateUtc, formatUtc, landingWindowError } from './time';
import type { LandingSite, MissionParams, PowerParams, CommsParams, TerrainParams, Constraints, SiteAnalysisResponse, Recommendation } from './types';

interface Props {
  sites: LandingSite[];
  power: PowerParams;
  comms: CommsParams;
  terrain: TerrainParams;
  mission: MissionParams;
  onSiteAdd: (coordinates: Coordinates, name: string) => void;
  onSiteRename: (id: string, name: string) => void;
  onSiteDelete: (id: string) => void;
  routeOpen: boolean;
  onRouteOpenChange: (open: boolean) => void;
}

export function MainPanel({ sites, power, comms, terrain, mission, onSiteAdd, onSiteRename, onSiteDelete, routeOpen, onRouteOpenChange: setRouteOpen }: Props) {
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

  const routeRequest = useMemo(() => !routeOpen || !selectedSite || validation ? null
    : async (signal: AbortSignal) => {
      const start = new Date(landingUtc);
      const { recommendations } = await api.getRecommendedSites({
        window_start_utc: start.toISOString(),
        window_end_utc: new Date(start.getTime() + mission.daysOnSurface * DAY_MS).toISOString(),
        constraints, limit: 100,
      }, signal);
      const stops = nearbyStops(selectedSite, recommendations);
      const route = stops.length ? await api.getRoute({
        waypoints: [siteReference(selectedSite), ...stops.map(r => ({ id: r.site.id })), siteReference(selectedSite)],
      }, signal) : null;
      return { route, metrics: new Map(recommendations.map(r => [r.site.id, r])) };
    }, [routeOpen, selectedSite, validation, landingUtc, mission.daysOnSurface, constraints]);
  const tour = useRequest(routeRequest);
  const profilesLoading = comparison.loading || horizons.loading;

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
      <div className="main-body profiles-body" id="panel-profiles" role="tabpanel" aria-labelledby="tab-profiles" hidden={tab !== 'profiles'}>
        {tab === 'profiles' && profilesLoading && <div className="profiles-loading-overlay">
          <div className="profiles-loading-popup" role="status" aria-live="polite" aria-atomic="true">
            <span className="profiles-loading-spinner" aria-hidden="true" />
            <strong>Loading site profiles…</strong>
            <p>Fetching comparison and visibility data. This can take 10–30 seconds.</p>
          </div>
        </div>}
        {validation && !dateError && <div className="request-error" role="alert">{validation}</div>}
        <ComparisonTable sites={enabled} results={comparison.data} constraints={constraints}
          selectedId={siteId ?? null} onSelect={setSelectedId} landingTime={landingUtc}
          onTimeSeek={setLandingUtc}
          missionStart={dateUtc(mission.windowStart)}
          sliderEnd={dateUtc(mission.windowEnd)} disabled={!!validation}
          loading={comparison.loading} error={comparison.error} onRetry={comparison.retry}>
          <div className="hz-grid">
            {enabled.map(site => <HorizonChart key={site.id} siteName={site.name}
              analysis={horizons.data?.get(site.id)?.analysis} landingUtc={landingUtc}
              selected={site.id === siteId} onSelect={() => setSelectedId(site.id)}
              loading={horizons.loading} error={horizons.error} onRetry={horizons.retry} />)}
          </div>
          {routeOpen && selectedSite ? <TouristRoutePanel siteName={selectedSite.name}
              landingUtc={landingUtc} route={tour.data?.route} metrics={tour.data?.metrics}
              loading={tour.loading} error={tour.error} onRetry={tour.retry} onClose={() => setRouteOpen(false)} />
            : <button className="route-cta" disabled={!selectedSite || !!validation} onClick={() => setRouteOpen(true)}>
              <span className="route-cta-main">Plan tourist route from this landing</span>
              <span className="route-cta-sub">{selectedSite ? `${selectedSite.name} · ${formatUtc(landingUtc)}` : 'Select a site first'}</span>
              <span className="route-cta-arrow" aria-hidden="true">→</span>
            </button>}
        </ComparisonTable>
      </div>
      <div className="main-body map-body" id="panel-map" role="tabpanel" aria-labelledby="tab-map" hidden={tab !== 'map'}>
        <MapPanel sites={sites} constraints={constraints} mission={mission} active={tab === 'map'}
          validation={validation} showValidation={!dateError} onSiteAdd={onSiteAdd} onSiteRename={onSiteRename} onSiteDelete={onSiteDelete} />
      </div>
    </main>
  );
}

const STOP_RADIUS_M = 150_000;
const MAX_STOPS = 4;

// Best-fit recommended sites near the landing point, ordered as a nearest-neighbour loop.
function nearbyStops(origin: LandingSite, recommendations: Recommendation[]): Recommendation[] {
  const candidates = recommendations
    .filter(r => r.site.id !== origin.id && distanceMetres(origin, r.site) <= STOP_RADIUS_M)
    .slice(0, MAX_STOPS);
  const ordered: Recommendation[] = [];
  let from: Coordinates = origin;
  while (candidates.length) {
    let best = 0;
    candidates.forEach((r, i) => { if (distanceMetres(from, r.site) < distanceMetres(from, candidates[best].site)) best = i; });
    const [next] = candidates.splice(best, 1);
    ordered.push(next);
    from = next.site;
  }
  return ordered;
}
