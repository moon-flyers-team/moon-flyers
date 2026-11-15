import { useEffect, useRef, useState } from 'react';
import { api, siteReference } from './api';
import type { ComparisonResult, Constraints, LandingSite, SiteAnalysisResponse } from './types';

export interface SiteBatchEntry {
  row: ComparisonResult;
  analysis: SiteAnalysisResponse;
}

export interface SiteBatchQuery {
  windowStart: string;
  windowEnd: string;
  constraints: Constraints;
}

interface Cache {
  key: string;
  entries: Record<string, SiteBatchEntry>;
  error?: string;
}

// Per-site cache for comparison rows and horizon analyses. Changing the mission window or
// constraints invalidates every site; enabling or disabling one only fetches that site.
export function useSiteBatch(sites: LandingSite[], query: SiteBatchQuery | null, delay = 350) {
  const [attempt, setAttempt] = useState(0);
  const [cache, setCache] = useState<Cache>({ key: '', entries: {} });
  const [pending, setPending] = useState(false);
  // Mirror of the cache for the fetch effect, which must not re-run when the cache changes.
  const cacheRef = useRef(cache);
  cacheRef.current = cache;

  const key = query
    ? JSON.stringify([query.windowStart, query.windowEnd, query.constraints])
    : '';
  const sitesKey = sites.map(site => site.id).join('|');
  // Stale entries from a previous mission stay hidden; a new site starts with no entry.
  const entries = query && cache.key === key ? cache.entries : {};
  const missing = sites.filter(site => !entries[site.id]);
  const error = query && cache.key === key ? cache.error : undefined;

  useEffect(() => {
    if (!query) return;
    const wanted = sites.filter(site =>
      !(cacheRef.current.key === key && cacheRef.current.entries[site.id]));
    if (!wanted.length) return;
    const controller = new AbortController();
    let active = true;
    const timer = window.setTimeout(() => {
      setPending(true);
      const bounds = { window_start_utc: query.windowStart, window_end_utc: query.windowEnd,
        constraints: query.constraints };
      // One comparison request for every missing site, plus one analysis each, in parallel.
      Promise.all([
        api.compare({ sites: wanted.map(siteReference), ...bounds, candidate_step_hours: 6 },
          controller.signal),
        Promise.all(wanted.map(site => api.getSiteAnalysis({ site: siteReference(site), ...bounds },
          controller.signal))),
      ]).then(([rows, analyses]) => {
        if (!active) return;
        setCache(previous => {
          const next = previous.key === key ? { ...previous.entries } : {};
          wanted.forEach((site, i) => { next[site.id] = { row: rows[i], analysis: analyses[i] }; });
          return { key, entries: next };
        });
      }).catch((reason: unknown) => {
        if (!active) return;
        setCache(previous => ({ key, error: reason instanceof Error ? reason.message : 'Request failed',
          entries: previous.key === key ? previous.entries : {} }));
      }).finally(() => { if (active) setPending(false); });
    }, delay);
    return () => { active = false; window.clearTimeout(timer); controller.abort(); setPending(false); };
  }, [key, sitesKey, attempt, delay]);

  return {
    // Aligned with `sites`; a site still loading has no entry and renders as pending.
    results: query ? sites.map(site => entries[site.id]?.row) : undefined,
    analyses: new Map(Object.entries(entries).map(([id, entry]) => [id, entry.analysis])),
    loadedCount: sites.filter(site => entries[site.id]).length,
    loading: !!query && (pending || missing.length > 0),
    error,
    retry: () => setAttempt(value => value + 1),
  };
}
