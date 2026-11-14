import { useMemo } from 'react';
import { formatUtc } from './time';

interface Props {
  missionStart: string; // ISO UTC e.g. '2027-08-01T00:00:00Z'
  missionEnd: string;
  value: string;        // ISO UTC e.g. '2027-08-07T06:00:00Z'
  onChange: (iso: string) => void;
  disabled?: boolean;
  showDate?: boolean;   // show the date/time label row; default true
}

export function TimeSlider({ missionStart, missionEnd, value, onChange, disabled, showDate = true }: Props) {
  const startMs = useMemo(() => Date.parse(missionStart), [missionStart]);
  const endMs   = useMemo(() => Date.parse(missionEnd),   [missionEnd]);
  const totalH  = (endMs - startMs) / 3_600_000;
  const valueH  = Number.isFinite(Date.parse(value))
    ? Math.round((Date.parse(value) - startMs) / 3_600_000)
    : 0;

  const ticks = useMemo(() => {
    const result: { pct: number; label: string }[] = [];
    const d = new Date(startMs);
    d.setUTCDate(1);
    d.setUTCMonth(d.getUTCMonth() + 1);
    while (d.getTime() < endMs) {
      result.push({
        pct: ((d.getTime() - startMs) / (endMs - startMs)) * 100,
        label: d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', timeZone: 'UTC' }),
      });
      d.setUTCMonth(d.getUTCMonth() + 1);
    }
    return result;
  }, [startMs, endMs]);

  function handleSlider(e: React.ChangeEvent<HTMLInputElement>) {
    onChange(new Date(startMs + +e.target.value * 3_600_000).toISOString());
  }

  return (
    <div className="ts-wrap">
      {showDate && (
        <div className="ts-date">
          <span className="ts-date-label">Landing (UTC)</span>
          <span className="ts-time">{value ? formatUtc(value) : '—'}</span>
        </div>
      )}

      <div className="ts-track-wrap">
        <input
          type="range"
          className="ts-range"
          min={0}
          max={totalH}
          step={6}
          value={valueH}
          onChange={handleSlider}
          disabled={disabled}
        />
      </div>

      <div className="ts-ticks">
        {ticks.map(t => (
          <div key={t.label} className="ts-tick" style={{ left: `${t.pct}%` }}>
            <div className="ts-tick-mark" />
            <span className="ts-tick-label">{t.label}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
