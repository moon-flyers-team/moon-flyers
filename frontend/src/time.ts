// Mean lunar solar day: https://svs.gsfc.nasa.gov/12739/
export const LUNAR_DAY_EARTH_DAYS = 29.5306;
export const DAY_MS = 86_400_000;
// Whole Earth days remain compatible with integer days_on_surface backends.
export const LUNAR_DAY_FETCH_DAYS = Math.ceil(LUNAR_DAY_EARTH_DAYS);
export const dateUtc = (date: string) => `${date}T00:00:00Z`;
export const formatUtc = (iso: string) => `${iso.slice(0, 10)} ${iso.slice(11, 16)} UTC`;
