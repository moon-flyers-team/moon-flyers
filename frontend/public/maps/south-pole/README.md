# Lunar south-pole basemap

These 36 PNG tiles are a locally bundled subset of NASA Moon Trek's
**LRO_WAC_Mosaic_SPole60_100mp** basemap (LRO / LROC WAC).
Retrieved 2026-11-14. They are observational imagery, independent of the mock analysis API.

Source and exact tile matrix metadata:
https://trek.nasa.gov/tiles/Moon/SP/LRO_WAC_Mosaic_SPole60_100mp/1.0.0/WMTSCapabilities.xml

Tile URL pattern:
https://trek.nasa.gov/tiles/Moon/SP/LRO_WAC_Mosaic_SPole60_100mp/1.0.0/default/default028mm/4/{row}/{column}.png

Bundled rows and columns: 5 through 10 inclusive, level 4. Each tile is 256×256 pixels,
535.1220703125 metres per pixel (136,991.25 m per tile). Tile-matrix top-left:
(-1,095,930 m, +1,095,930 m). Display coordinates retain this origin and scale exactly;
the circular 80°S boundary clips the imagery. Imagery is not rotated or stretched onto
an unrelated projection.

Projection: spherical lunar south-polar stereographic, central meridian 0°, true scale
at 90°S, Moon radius 1,737,400 m. Coordinates follow Moon Trek's `Moon2000_sp` WKT:
https://trek.nasa.gov/moon/jpl/config/config.json

The small feature catalogue at `frontend/src/map/features.json` comes from:
https://trek.nasa.gov/moon/trekarcgis/rest/services/CombinedNomenclatureS/MapServer/0/query?where=center_lat%20%3C%3D%20-80&outFields=*&returnGeometry=false&f=json

It includes named craters and mountains in this service with centres south of 80°S
(28 records in the retrieved response). Names use the service's LABEL field. Coordinates
and diameters come from the IAU/USGS nomenclature catalogue exposed by Moon Trek.
Longitude is normalised to −180°…180°. Cursor hit detection uses centre-to-cursor
spherical distance and half the catalogue diameter, selecting the smallest overlapping
feature. Those circular areas approximate feature extents; they are not precise boundaries
or a complete catalogue of every lunar feature. Blank areas show “No named feature”.

Attribution is displayed in the map footer. The imagery's fixed illumination is not a
simulation of the selected mission dates; mission heatmaps are fetched separately.
