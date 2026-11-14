import type { LandingSite } from './types';

// Catalogue-only fallback. Analysis is always obtained from the backend.
export const mockSites: LandingSite[] = [
  { id: 'shackleton_rim', name: 'Shackleton rim', latitude_deg: -89.667, longitude_deg: 129.783, enabled: true },
  { id: 'connecting_ridge', name: 'Connecting Ridge', latitude_deg: -89.458, longitude_deg: -140.2, enabled: true },
  { id: 'de_gerlache_rim', name: 'de Gerlache rim', latitude_deg: -88.67, longitude_deg: -68, enabled: true },
  { id: 'malapert_massif', name: 'Malapert massif', latitude_deg: -86, longitude_deg: 0, enabled: true },
];
