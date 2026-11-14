import { useState } from 'react';

interface Props {
  title: string;
  dot?: string;
  action?: React.ReactNode;
  children: React.ReactNode;
}

export function Section({ title, dot, action, children }: Props) {
  const [open, setOpen] = useState(true);
  return (
    <div className="sb-section">
      <div className="sb-section-heading">
      <button type="button" className="sb-hdr" aria-expanded={open} onClick={() => setOpen(o => !o)}>
        <span aria-hidden="true" className={`sb-arrow${open ? ' open' : ''}`}>▶</span>
        {dot && <span className="sb-dot" style={{ background: dot }} />}
        {title}
      </button>
      {action && <div className="sb-section-action" onClick={() => setOpen(true)}>{action}</div>}
      </div>
      {open && <div className="sb-body">{children}</div>}
    </div>
  );
}
