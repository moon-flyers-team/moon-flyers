import { useId } from 'react';

interface Props { label: string; value: string; onChange: (date: string) => void; errorId?: string }

export function DateField({ label, value, onChange, errorId }: Props) {
  const id = useId();
  return <div className="sb-field sb-date-field">
    <label htmlFor={id}>{label}</label>
    <input id={id} type="date" required className="sb-input" value={value}
      aria-invalid={errorId ? true : undefined} aria-describedby={errorId}
      onChange={event => onChange(event.target.value)} />
  </div>;
}
