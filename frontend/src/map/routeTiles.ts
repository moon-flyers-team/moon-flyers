import { MAP_CENTER, METRES_TO_SVG } from './projection';

// Moon Trek Moon2000_sp tile grid: level L has 2^L tiles across this square.
const GRID_M = 2_191_860;
const ORIGIN_M = GRID_M / 2;
const TILE_PX = 256;
const TREK = 'https://trek.nasa.gov/tiles/Moon/SP';

export type RouteLayer = 'relief' | 'elevation' | 'imagery';

interface TileSource {
  product: string;
  maxLevel: number;
  extentM: number; // half-width of the product's square coverage
}

export const ROUTE_LAYERS: Record<RouteLayer, { label: string; credit: string; sources: TileSource[] }> = {
  relief: {
    label: 'Relief',
    credit: 'LRO LOLA hillshade, 30 m and 5 m/px',
    sources: [
      { product: 'LRO_LOLA_Shade_SPole75_30mp_v04', maxLevel: 6, extentM: 457_440 },
      { product: 'LRO_LOLA_Shade_SPole875_5mp_v04', maxLevel: 9, extentM: 75_840 },
    ],
  },
  elevation: {
    label: 'Elevation',
    credit: 'LRO LOLA colour-shaded relief, 30 m and 5 m/px',
    sources: [
      { product: 'LRO_LOLA_ClrShade_SPole75_30mp_v04', maxLevel: 6, extentM: 457_440 },
      { product: 'LRO_LOLA_ClrShade_SPole875_5mp_v04', maxLevel: 9, extentM: 75_840 },
    ],
  },
  imagery: {
    label: 'Imagery',
    credit: 'LROC NAC average mosaic, 1 m/px (south of 85.5°S)',
    sources: [
      { product: 'LRO_LOLA_Shade_SPole75_30mp_v04', maxLevel: 6, extentM: 457_440 },
      { product: 'LRO_NAC_AvgMosaic_SPole855_1mp', maxLevel: 11, extentM: 136_525 },
    ],
  },
};

export interface RouteTile { key: string; href: string; x: number; y: number; size: number }

interface View { x: number; y: number; half: number; pxPerSvg: number }

export function visibleTiles(layer: RouteLayer, view: View): RouteTile[] {
  const metresPerPx = 1 / METRES_TO_SVG / view.pxPerSvg;
  const dpr = Math.min(2, globalThis.devicePixelRatio || 1);
  const wanted = Math.ceil(Math.log2(GRID_M / TILE_PX / (metresPerPx / dpr)));
  const toM = (svg: number) => (svg - MAP_CENTER) / METRES_TO_SVG;
  const east0 = toM(view.x - view.half), east1 = toM(view.x + view.half);
  const north1 = -toM(view.y - view.half), north0 = -toM(view.y + view.half);

  const tiles: RouteTile[] = [];
  for (const src of ROUTE_LAYERS[layer].sources) {
    const e0 = Math.max(east0, -src.extentM), e1 = Math.min(east1, src.extentM);
    const n0 = Math.max(north0, -src.extentM), n1 = Math.min(north1, src.extentM);
    if (e0 >= e1 || n0 >= n1) continue;
    const level = Math.max(4, Math.min(src.maxLevel, wanted));
    const span = GRID_M / 2 ** level;
    const c0 = Math.floor((e0 + ORIGIN_M) / span), c1 = Math.floor((e1 + ORIGIN_M) / span);
    const r0 = Math.floor((ORIGIN_M - n1) / span), r1 = Math.floor((ORIGIN_M - n0) / span);
    const size = span * METRES_TO_SVG;
    for (let row = r0; row <= r1; row++) for (let col = c0; col <= c1; col++) {
      tiles.push({
        key: `${src.product}/${level}/${row}/${col}`,
        href: `${TREK}/${src.product}/1.0.0/default/default028mm/${level}/${row}/${col}.png`,
        x: MAP_CENTER + (col * span - ORIGIN_M) * METRES_TO_SVG,
        y: MAP_CENTER - (ORIGIN_M - row * span) * METRES_TO_SVG,
        size,
      });
    }
  }
  return tiles;
}
