import { useState } from 'react';

interface Props {
  title: string;
  dot?: string;
  children: React.ReactNode;
}

export function Section({ title, dot, children }: Props) {
  const [open, setOpen] = useState(true);
  return (
    <div className="sb-section">
      <button className="sb-hdr" onClick={() => setOpen(o => !o)}>
        <span className={`sb-arrow${open ? ' open' : ''}`}>▶</span>
        {dot && <span className="sb-dot" style={{ background: dot }} />}
        {title}
      </button>
      {open && <div className="sb-body">{children}</div>}
    </div>
  );
}
