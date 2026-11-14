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
or a complete catalogue of every lunar feature. Areas without a named feature leave the feature readout blank.

Attribution is displayed in the map footer. The imagery's fixed illumination is not a
simulation of the selected mission dates; mission heatmaps are fetched separately.

## Topography / altitude contours

The Layers dropdown offers an independent LOLA topographic basemap. Its 36 locally bundled
color-shaded-relief tiles are in `topography/` and use **the same level-4 tile origin,
pixel size, rows, columns and Moon2000_sp projection** as the satellite basemap above.
Changing basemaps preserves camera position, waypoints, coordinate grid and heatmap settings.

Product: `LRO_LOLA_ClrShade_SPole45_100mp_v04` (LOLA Instrument Team / NASA Goddard).
It is the version-4, nominal 100 m/pixel south-polar elevation product based on LOLA
altimetry through September 2011. The display tiles are downsampled to 535.1220703125 m/pixel.
Elevations are in metres relative to a 1,737,400 m lunar reference radius, not sea level.
The official color legend spans −9,126 to +7,026 m across the source product; the displayed
80°S cap occupies a subset of that range. Light/dark shading indicates terrain relief,
not illumination for the user's mission date.

Metadata (projection, reference radius, acquisition dates, credit and unrestricted use):
https://trek.nasa.gov/moon/TrekWS/rest/cat/metadata/fgdc/html?label=LRO_LOLA_ClrShade_SPole45_100mp_v04

WMTS metadata:
https://trek.nasa.gov/tiles/Moon/SP/LRO_LOLA_ClrShade_SPole45_100mp_v04/1.0.0/WMTSCapabilities.xml

Tile URL pattern (same rows/columns 5–10):
https://trek.nasa.gov/tiles/Moon/SP/LRO_LOLA_ClrShade_SPole45_100mp_v04/1.0.0/default/default028mm/4/{row}/{column}.png

Official legend (`topography/legend.png`):
https://trek.nasa.gov/moon/TrekWS/rest/cat/legend/stream?label=LRO_LOLA_ClrShade_SPole45_100mp_v04

### Contour data and regeneration

`topography/contours.json` contains real elevation isolines at 500 m intervals. Index lines
at 1,000 m intervals are drawn slightly heavier. They are computed offline with contourpy
from the matching `LRO_LOLA_DEM_SPole45_100mp_v04` elevation service, **not from image colors
or invented terrain**. The 768×768 DEM crop covers the projected 80°S cap bounding square,
bilinearly resampled to ~791.68 m/pixel. They are regional display contours, not high-resolution
landing-safety measurements. Contour paths use the same SVG plane as the tile basemaps,
including half-pixel offsets for DEM sample centres. The 80°S circle clips the square.

DEM metadata:
https://trek.nasa.gov/moon/trekarcgis/rest/services/LRO_LOLA_DEM_SPole45_100mp_v04/ImageServer?f=pjson

To reproduce, download a Float32 GeoTIFF from that service's `/exportImage` endpoint with:

```text
bbox=-304005.6080198807,-304005.6080198807,304005.6080198807,304005.6080198807
size=768,768
format=tiff
pixelType=F32
interpolation=RSP_BilinearInterpolation
f=image
```

Then, from the repository root:

```sh
uv run --with pillow --with numpy --with contourpy frontend/scripts/generate-contours.py \
  /path/to/cropped-dem.tif frontend/public/maps/south-pole/topography/contours.json
```

The TIFF and Python processing dependencies are not part of the shipped application. The
script checks the floating-point raster and GeoTIFF extent before emitting contour paths.
At runtime the frontend fetches the local contour JSON only when topography is active, and
uses the existing debounced/abortable request lifecycle with a zero delay. An unavailable
contour file shows an error while retaining the elevation imagery. All basemap assets are
served by Vite or production static hosting; no backend or external map service is needed.

## Long-term sunlight and Earth-visibility reference overlays

`reference/sunlight.png` and `reference/earth-visibility.png` are real LOLA average-visibility
rasters, colorized for the app's amber and cyan legends. They are **long-term reference
averages**, not synthetic demo values or predictions for the selected mission window.
The publication describes hourly sampling over approximately 18.6 years. The products count
a sample as visible when **any fraction of the body disc** is visible. That differs from
our mission API's whole-disc-plus-clearance criterion. Dates, duration, thresholds and
horizon clearance in the sidebar do not recalculate these layers.

Source description, interpretation and requested scientific citation:
https://pgda.gsfc.nasa.gov/products/69

Citation: Mazarico, E., et al. (2011), *Illumination conditions of the lunar polar regions
using LOLA topography*, Icarus 211, 1066–1081. https://doi.org/10.1016/j.icarus.2010.10.030
The bundled data use the updated 2016 product release, version 1.05.

Original numeric rasters (82,432,800 bytes each; raw files are not committed):
https://imbrium.mit.edu/EXTRAS/ILLUMINATION/IMG/AVGVISIB_65S_240M_201608.IMG
https://imbrium.mit.edu/EXTRAS/ILLUMINATION/IMG/AVGVISIB_65S_240M_201608_EARTH.IMG

Official detached labels are bundled in `reference/` and available beside each IMG with
`.LBL` replacing `.IMG`. They specify 6420×6420 little-endian signed 16-bit samples,
240 m/pixel, south-polar spherical stereographic with central meridian 0°, radius
1,737,400 m, east-positive longitude, and line/sample projection offsets 3209.5.
The fractional visibility is `DN × 0.00004 + 0`; percentages multiply that by 100.
Zero is valid permanent shadow / no visibility and must not be treated as missing data.

Regeneration (download both IMG and LBL files into a temporary directory first):

```sh
uv run --with numpy --with pillow frontend/scripts/generate-reference-overlays.py \
  /path/to/download-directory frontend/public/maps/south-pole/reference
```

The generator crops the numeric data to the exact projected 80°S-cap bounding square,
resamples bilinearly to 1024×1024 (~593.76 m/pixel), and applies a fixed 0–100% color ramp.
It accounts for the source pixel centres and masks out-of-cap/no-data samples with alpha.
These regional display rasters can smooth or miss small illuminated terrain peaks; use
native-resolution data for quantitative site analysis. The display PNGs are colorized images,
not an invertible numerical dataset. `reference/metadata.json` records projection, extent,
scaling, input SHA-256 checksums and generated value ranges for reproducibility.

Both layers may be enabled together. Selecting any heatmap hides the underlying satellite
or topographic basemap, its contours and elevation legend, leaving a neutral surface. They are composited in sunlight,
then Earth-visibility order, using the toolbar opacity for each image. Their combined colors
are a visual blend, not a new physical metric; the top-left map legends describe each layer
separately. Clearing the final heatmap restores the remembered basemap and camera.
Mission-dependent backend overlays render above the reference layers. Disabling one reference
layer leaves the other visible. Neither requires a backend, and their checkbox changes do
not trigger backend heatmap requests. Other toolbar heatmaps retain the proposed API path.
