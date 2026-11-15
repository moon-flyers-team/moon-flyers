import type { FitStatus } from './types';

const MAP: Record<FitStatus, { cls: string; label: string }> = {
  'both_met':    { cls: 'badge--green',  label: '✓ All met' },
  'power_short': { cls: 'badge--yellow', label: '~ Power' },
  'comms_short': { cls: 'badge--yellow', label: '~ Comms' },
  'neither_met': { cls: 'badge--red',    label: '✗ None met' },
};

export function FitBadge({ fit }: { fit: FitStatus }) {
  const { cls, label } = MAP[fit];
  return <span className={`badge ${cls}`}>{label}</span>;
}
