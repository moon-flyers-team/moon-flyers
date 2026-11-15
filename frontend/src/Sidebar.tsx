import { useEffect, useRef, useState } from 'react';
import { Section } from './Section';
import type { LandingSite } from './types';
import type { Coordinates } from './map/projection';

interface Props {
  sites: LandingSite[];
  onSiteToggle: (id: string) => void;
  onSiteAdd: (coordinates: Coordinates, name: string) => void;
  onOpenSettings: () => void;
}

const MIN_SIDEBAR_WIDTH = 220;
const MAX_SIDEBAR_WIDTH = 600;

export function Sidebar({ sites, onSiteToggle, onSiteAdd, onOpenSettings }: Props) {
  const asideRef = useRef<HTMLElement>(null);
  const addButtonRef = useRef<HTMLButtonElement>(null);
  const nameRef = useRef<HTMLInputElement>(null);
  const [adding, setAdding] = useState(false);
  const [siteName, setSiteName] = useState('');
  const [latitude, setLatitude] = useState('');
  const [longitude, setLongitude] = useState('');
  const [announcement, setAnnouncement] = useState('');
  const [width, setWidth] = useState(() => {
    const stored = Number(localStorage.getItem('sidebarWidth'));
    return Number.isFinite(stored) && stored >= MIN_SIDEBAR_WIDTH && stored <= MAX_SIDEBAR_WIDTH ? stored : 268;
  });
  const [resizing, setResizing] = useState(false);
  useEffect(() => { localStorage.setItem('sidebarWidth', String(width)); }, [width]);
  useEffect(() => {
    if (!resizing) return;
    const onMove = (e: PointerEvent) => {
      const left = asideRef.current?.getBoundingClientRect().left ?? 0;
      setWidth(Math.max(MIN_SIDEBAR_WIDTH, Math.min(MAX_SIDEBAR_WIDTH, e.clientX - left)));
    };
    const onUp = () => setResizing(false);
    window.addEventListener('pointermove', onMove);
    window.addEventListener('pointerup', onUp);
    return () => { window.removeEventListener('pointermove', onMove); window.removeEventListener('pointerup', onUp); };
  }, [resizing]);
  const validCoordinates = latitude.trim() !== '' && longitude.trim() !== ''
    && Number.isFinite(Number(latitude)) && Number.isFinite(Number(longitude))
    && Number(latitude) >= -90 && Number(latitude) <= 90 && Number(longitude) >= -180 && Number(longitude) <= 180;
  function closeForm() {
    setAdding(false); setSiteName(''); setLatitude(''); setLongitude('');
    addButtonRef.current?.focus();
  }
  return (
    <aside className="sidebar" ref={asideRef} style={{ width, minWidth: width, maxWidth: width }}>
      <div className="sb-top-bar">
        <button className="sb-settings-btn" onClick={onOpenSettings} aria-label="Open mission planner settings" title="Mission planner settings">
          ⚙
        </button>
        <span className="sb-top-title">Settings</span>
      </div>
      <Section title="Sites" action={<button ref={addButtonRef} type="button" className="ct-btn sb-add-site"
        aria-label="Add site manually" aria-expanded={adding}
        onClick={() => { setAdding(true); setAnnouncement(''); nameRef.current?.focus(); }}>+ Add</button>}>
        {adding && <form className="sb-site-form" aria-label="Add a site manually"
          onKeyDown={event => { if (event.key === 'Escape') { event.preventDefault(); closeForm(); } }}
          onSubmit={event => {
            event.preventDefault();
            if (!siteName.trim() || !validCoordinates) return;
            onSiteAdd({ latitude_deg: Number(latitude), longitude_deg: Number(longitude) }, siteName.trim());
            setAnnouncement(`Added ${siteName.trim()} to Sites.`);
            closeForm();
          }}>
          <label>Site name<input ref={nameRef} autoFocus className="sb-input" required maxLength={80}
            value={siteName} onChange={event => setSiteName(event.target.value)} /></label>
          <label>Latitude (decimal degrees)<input type="number" className="sb-input" required step="any" min={-90} max={90}
            value={latitude} onChange={event => setLatitude(event.target.value)} /></label>
          <label>Longitude (decimal degrees)<input type="number" className="sb-input" required step="any" min={-180} max={180}
            value={longitude} onChange={event => setLongitude(event.target.value)} /></label>
          <p>Latitude −90…90°, longitude −180…180°.</p>
          <div className="sb-form-actions">
            <button type="submit" className="ct-btn" disabled={!siteName.trim() || !validCoordinates}>Add site</button>
            <button type="button" className="ct-btn" onClick={closeForm}>Cancel</button>
          </div>
        </form>}
        {announcement && <p className="sb-site-announcement" role="status">{announcement}</p>}
        <span className="sb-count">{sites.filter(s => s.enabled).length} of {sites.length} compared</span>
        <ul className="sb-sites">
          {sites.map(site => (
            <li key={site.id}>
              <label className="sb-site">
                <input type="checkbox" checked={site.enabled} onChange={() => onSiteToggle(site.id)} />
                <div>
                  <div className="sb-site-name">{site.name}</div>
                  <div className="sb-site-coords">{site.latitude_deg}°, {site.longitude_deg}°</div>
                </div>
              </label>
            </li>
          ))}
        </ul>
      </Section>
      <div
        className={`sb-resizer${resizing ? ' sb-resizer--active' : ''}`}
        role="separator"
        aria-orientation="vertical"
        aria-label="Resize sidebar"
        onPointerDown={e => { e.preventDefault(); setResizing(true); }}
        onDoubleClick={() => setWidth(268)}
      />
    </aside>
  );
}
