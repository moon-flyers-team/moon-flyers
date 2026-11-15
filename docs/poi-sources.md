# South-polar points-of-interest catalogue

## Scope and interpretation

`POST /recommended-sites` searches a **published, bundled catalogue**, not generated
landing candidates or a suitability ranking. The initial snapshot contains **61 POIs**:
55 named natural features, four historical impact locations, and two landers. It covers
footprints intersecting **80°S–90°S**, matching the map. Seven natural-feature centres lie
north of 80°S but their approximate footprints intersect the cap.

This is a curated snapshot, **not an exhaustive inventory** of geological targets, mission
hardware, or accessible destinations. A crater is not a cave; a permanently shadowed region
is not evidence of a cave or an ice deposit. No synthetic records, inferred rover positions,
or future mission landing targets are included. The schema permits `rover` records and
geological `natural_feature` subtypes, but no separately verified in-cap rover or cave
location was added from the checked sources.

Research/retrieval date: **2026-11-15 UTC**. The exact retrieval timestamp, Moon Trek query
URL and response SHA-256, and LROC pit-survey statistics/checksum are recorded in
`backend/src/data/points_of_interest.json`. Each POI carries source URLs and, where
applicable, a source record ID.

## 1. NASA Moon Trek / IAU-USGS named features and impact sites

- [Layer metadata](https://trek.nasa.gov/moon/trekarcgis/rest/services/CombinedNomenclatureS/MapServer/0?f=pjson)
- [Full attribute query](https://trek.nasa.gov/moon/trekarcgis/rest/services/CombinedNomenclatureS/MapServer/0/query?where=1%3D1&outFields=%2A&returnGeometry=false&f=json)
- Layer title at retrieval: `combinedNomenclatureS_y2024m02d27`.
- Query returned **496 records**, without `exceededTransferLimit`. The builder queries the
  entire layer, rather than filtering by centre latitude, to retain boundary-crossing features.

Imported types: `Crater, craters`, `Satellite Feature`, `Mons, montes`, and `Impact`.
Names follow the service's `LABEL`, coordinates its `center_lat`/`center_lon`, diameters
its `diameter` in kilometres. Longitudes are normalized to −180…180°, east-positive.
Satellite features here are lettered geological features, **not orbiting spacecraft**.
The named-feature entries link to their IAU/USGS Gazetteer records where supplied; Mons
Mouton links to NASA's naming article. The numbers are a snapshot of this NASA layer, not
an assertion that they match the latest Gazetteer revision. For example,
[Shackleton's Gazetteer page](https://planetarynames.wr.usgs.gov/Feature/5450) now includes
revised coordinates and multiple historical coordinate sets.

The four imported `Impact` records are:

| Moon Trek FID | Object | Latitude | East-positive longitude |
| --- | --- | ---: | ---: |
| 0 | Lunar Prospector | −87.7° | 42° |
| 1 | Chandrayaan-1 Moon Impact Probe (service label: Chandraya'an 1 MIP) | −89° | −30° |
| 3 | LCROSS Centaur | −84.6796° | −48.7093° |
| 4 | LCROSS spacecraft | −84.719° | −49.61° |

**Known source discrepancy:** the same layer also contains unofficial LCROSS labels at
(−84.6971°, −48.717°) and (−84.7183°, −49.6197°), FIDs 489/490. These are not independent
objects. We import the explicit `Impact` records and exclude unofficial duplicates; we do
not claim these are the most precise reconstructed impact solutions. In particular, the
Moon Impact Probe location is coarse. These records support regional discovery, not
metre-scale navigation or recovery of hardware. Their uncertainty is **unquantified**.

## 2. IM-1 Odysseus lander — NASA/LRO

[NASA: LRO Images Intuitive Machine's Odysseus Lander](https://www.nasa.gov/missions/lro/nasas-lro-images-intuitive-machines-odysseus-lander/)
(2024-02-26).

The article reports the observed location as **80.13°S, 1.44°E**, with LROC NAC frame
`M1463440322L`. We use those published coordinates, not a planned landing target or the
centre of Malapert A. The Trek robotic-lander entry is excluded to avoid duplication.
No uncertainty radius or separate payload/rover position is invented from the image.

## 3. IM-2 Athena lander — NASA/GSFC/ASU LROC

[LROC: IM-2 Athena Seen Obliquely](https://www.lroc.asu.edu/images/1408)
(Mark Robinson, 2025-03-10).

The image article reports **84.7906°S, 29.1957°E**, observed in NAC frame `M1495922531LR`.
It describes the lander resting on its side in a 20 m crater. That crater diameter is **not**
used as the hardware footprint or positional uncertainty. Separate rover/hopper/payload
locations are not inferred from the lander location.

## 4. Caves and collapse pits — researched, none included in this cap

- [NASA/GSFC/ASU LROC Pits Atlas](https://www.lroc.asu.edu/atlases/pits)
- [Published coordinate/dimension table](https://www.lroc.asu.edu/atlases/pits/list)
- [NASA: LRO Finds Lunar Pits Harbor Comfortable Temperatures](https://www.nasa.gov/solar-system/nasas-lro-finds-lunar-pits-harbor-comfortable-temperatures/)
  (background on why pits are exploration targets; not used to invent coordinates).

We parsed **all 278 table records**. The southernmost is **Schomberger A 1**,
**78.0579°S, 25.3441°E**, with maximum funnel diameter 13 m. None of the published
centres or approximate funnel footprints intersect 80°S–90°S. Consequently, **this
catalogue has no cave or collapse-pit POIs**. This is a limitation of the checked catalogue
and cap, not proof that south-polar caves do not exist. A pit alone does not establish an
accessible subsurface cave or lava tube.

The refresh tool repeats this survey. If a future source contains an in-cap pit candidate,
it stops for explicit source/geometry review rather than silently calling it a cave.
An actual pit could be added as `category: natural_feature`, `feature_type: collapse_pit`,
with sourced dimensions and evidence notes. No such record is currently shipped.

## Geometry, accuracy, and travel interpretation

- Lunar reference sphere: **1,737.4 km**, matching Moon Trek and the existing map.
- Natural features use an **approximate spherical circular area** with radius half their
  published diameter. This is an explicit approximation, not a traced rim, surveyed
  boundary, or assertion of circular geology. No polygon accuracy is claimed.
- Hardware/impact locations use published points with zero footprint radius. If a future
  feature has no usable dimensions, a published point can be used with point semantics.
- Distance is shortest great-circle distance to the point or approximate area:
  `max(0, centre_distance_km − feature_radius_km)`. Inside an area it is zero, not the
  distance to the far side, centre, or crater rim. The whole footprint is retained when it
  intersects the cap; an outside-cap centre remains valid metadata.
- `location_uncertainty_km: null` means **unknown/not quantified**, never zero uncertainty.
  Decimal precision is not an accuracy estimate. Circle approximation error is also not
  quantified. No uncertainty buffer is silently added to the search radius.
- The default **40 km radius** is a user-selected scenario: 10 km/h × 8 total driving
  hours ÷ 2 for an out-and-back trip. These are **not NASA-certified rover capabilities**.
  Stops, scientific work, detours, slopes, obstacles, shadow, energy, communications,
  reserve, heritage protection, and trafficability are not evaluated.

## Refresh and review procedure

From the repository root, with Python 3.12 (stdlib only):

```sh
backend/.venv/Scripts/python.exe backend/tools/build_poi_catalogue.py
```

The script downloads the full Moon Trek layer and LROC pit table, rejects truncated/empty
responses, normalizes fields, filters approximate footprints by cap intersection, and
adds the two explicitly sourced lander records. It writes the bundled JSON only after
both source checks succeed. Source failures do not produce substitute records.

Before committing a refresh:
1. Inspect source changes, object identities and duplicates. Trek FIDs are source-layer
   identifiers, not guaranteed stable across layer replacements; preserve public POI IDs
   deliberately if that source changes. Review updated authoritative coordinates rather
   than assuming a historical layer is current.
2. Recheck the NASA/LROC lander articles and any proposed hardware/pit additions. These two
   manually transcribed supplemental records are in the builder and are not automatically
   re-scraped. Require published coordinates; do not use mission target coordinates.
3. Review circles near the cap boundary and any better mapped outlines; never silently
   present approximate extents as exact. Gazetteer WKT may be generalized, not a surveyed rim.
4. Update this document, snapshot expectations in tests, and the version if necessary.
5. Run backend pytest and ruff. Deploy the reviewed JSON with the application.

Runtime requests use **only** the committed catalogue; no external lookup or synthetic
fallback runs. Missing, empty, duplicate-ID, invalid, or out-of-coverage catalogue data
fails loading rather than returning plausible-looking replacement POIs.
