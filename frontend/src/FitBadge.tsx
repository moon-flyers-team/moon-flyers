import type { FitStatus } from './types';

const MAP: Record<FitStatus, { cls: string; label: string }> = {
  'both_met':    { cls: 'badge--green',  label: '✓ Both met' },
  'power_short': { cls: 'badge--red',    label: '✗ Power short' },
  'comms_short': { cls: 'badge--orange', label: '⚠ Comms short' },
  'neither_met':     { cls: 'badge--red',    label: '✗ Neither' },
};

export function FitBadge({ fit }: { fit: FitStatus }) {
  const { cls, label } = MAP[fit];
  return <span className={`badge ${cls}`}>{label}</span>;
}
