import type { FitStatus } from './types';

const MAP: Record<FitStatus, { cls: string; label: string }> = {
  'both-met':    { cls: 'badge--green',  label: '✓ Both met' },
  'power-short': { cls: 'badge--red',    label: '✗ Power short' },
  'comms-short': { cls: 'badge--orange', label: '⚠ Comms short' },
  'neither':     { cls: 'badge--red',    label: '✗ Neither' },
};

export function FitBadge({ fit }: { fit: FitStatus }) {
  const { cls, label } = MAP[fit];
  return <span className={`badge ${cls}`}>{label}</span>;
}
