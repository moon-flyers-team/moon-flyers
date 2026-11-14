// Mean lunar solar day: https://svs.gsfc.nasa.gov/12739/
export const LUNAR_DAY_EARTH_DAYS = 29.5306;
export const DAY_MS = 86_400_000;
// Whole Earth days remain compatible with integer days_on_surface backends.
export const LUNAR_DAY_FETCH_DAYS = Math.ceil(LUNAR_DAY_EARTH_DAYS);
export const dateUtc = (date: string) => `${date}T00:00:00Z`;
export function landingWindowError(startDate: string, endDate: string): string {
  const validDate = (value: string) => {
    if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) return false;
    const time = Date.parse(dateUtc(value));
    return Number.isFinite(time) && new Date(time).toISOString().slice(0, 10) === value;
  };
  return validDate(startDate) && validDate(endDate) && endDate > startDate ? ''
    : 'Choose valid dates. The end date must be later than the start date.';
}
export const formatUtc = (iso: string) => `${iso.slice(0, 10)} ${iso.slice(11, 16)} UTC`;
