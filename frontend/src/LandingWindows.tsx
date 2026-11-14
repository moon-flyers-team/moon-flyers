import { useMemo, useState } from 'react';
import { api } from './api';
import { useRequest } from './useRequest';
import { dateUtc, formatUtc } from './time';
import { FitBadge } from './FitBadge';
import type { Constraints } from './types';

interface Props {
  siteId: string; siteName: string; windowStart: string; windowEnd: string;
  constraints: Constraints; onSelect: (utc: string) => void;
}
export function LandingWindows({ siteId, siteName, windowStart, windowEnd, constraints, onSelect }: Props) {
  const [requested, setRequested] = useState(false);
  const request = useMemo(() => !requested ? null : (signal: AbortSignal) => api.getLandingWindows({
    site: { id: siteId }, window_start_utc: dateUtc(windowStart),
    window_end_utc: dateUtc(windowEnd), constraints,
  }, signal), [requested, siteId, windowStart, windowEnd, constraints]);
  const result = useRequest(request);
  return <section className="ct-wrap" aria-label="Best landing times">
    <div className="ct-topbar"><span className="ct-tab">Best landing times · {siteName}</span>
      <button className="ct-btn" disabled={result.loading} onClick={() => requested ? result.retry() : setRequested(true)}>
        {result.loading ? 'Finding landing times…' : 'Find best times'}
      </button>
    </div>
    {result.loading && <p className="request-status" role="status">Searching the landing window. This can take 10–30 seconds.</p>}
    {result.error && <p className="request-error" role="alert">Could not find landing times: {result.error}</p>}
    {result.data && <div className="ct-scroll"><table className="ct">
      <thead><tr><th>Rank</th><th className="ct-left">Landing (UTC)</th><th>Fit</th><th>Sunlight</th><th>Earth contact</th><th>Use time</th></tr></thead>
      <tbody>{result.data.map(window => <tr key={window.landing_utc}>
        <td>{window.rank}</td><td className="ct-left">{formatUtc(window.landing_utc)}</td>
        <td><FitBadge fit={window.fit.status} /></td><td>{window.metrics.sun_visible_pct}%</td><td>{window.metrics.earth_visible_pct}%</td>
        <td><button className="ct-btn" onClick={() => onSelect(window.landing_utc)}>Set landing</button></td>
      </tr>)}{!result.data.length && <tr><td colSpan={6} className="ct-empty">No landing times returned for this window.</td></tr>}</tbody>
    </table></div>}
  </section>;
}
