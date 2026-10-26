# Local vector maps

The main map uses MapLibre GL JS and MVT in a locally served PMTiles archive.
Flask and GeoPandas still perform exact queries against the existing local
analysis datasets. The Leaflet watershed dialog, startup downloads, and original
CSV/GeoJSON/GeoPackage exports remain available. This release does not reduce
installation downloads or publish artifacts externally.

## Generate artifacts

Let the existing startup workflow finish downloading/processing the matched
`TotalFire_data.parquet` and `TotalFire_display50m.parquet` files. Then run this
explicit maintenance command from the repository root:

```sh
# macOS; Linux users can build https://github.com/felt/tippecanoe
brew install tippecanoe
venv/bin/python scripts/build_tiles.py
```

Tippecanoe 2.17 or later supports direct PMTiles output. The validated build used
2.82.0. The command accepts `--source`, `--display`, `--output`, and
`--tippecanoe /path/to/tippecanoe`. Allow several GB of scratch space in addition
to the Parquet datasets and the completed archive. Tile generation is a
maintenance operation and can take substantial time; ordinary server startup
never generates or downloads tiles.

The builder reads original geometry one Parquet row group at a time and writes a
temporary GeoJSON sequence. Numeric feature IDs equal physical original row
positions. Tiles carry `province`, `fire_year`, `fire_size`, `data_source`, and
`data_aquisition` (the existing field spelling). Zooms 0–14 use Tippecanoe's
zoom-dependent simplification, detail 10 below maximum zoom and detail 12 at
maximum zoom. `--drop-rate=1`, `--no-feature-limit`, `--no-tile-size-limit`, and
`--no-tiny-polygon-reduction` disable rate dropping, size-driven dropping, and
combining small records. No adaptive dropping, clustering, or coalescing is used.
Quantization and simplification can make subpixel polygons invisible at low
zooms. Counts always come from the backend.

The generated directory contains:

```text
data/tiles/manifest.json
           <dataset_version>/fires.pmtiles
           <dataset_version>/manifest.json
```

The version is the SHA-256 of canonical original/display source fingerprints
(each includes SHA-256 and byte size). The manifest records fingerprints, version,
record count, longitude/latitude bounds, layer name, zoom range, archive size and
checksum, Tippecanoe version, and build options. Staging happens on the target
filesystem. The complete version directory is renamed into place before the
current manifest is atomically replaced. Interrupted/failed builds leave the
previous manifest intact. Existing version URLs are immutable: a rebuild that
would change the bytes at an existing version is rejected. Keep old version
directories while old browser sessions need them. If intentionally changing the
tile recipe for the same dataset, use a separate output root and retire the old
root/cache as a coordinated replacement; never overwrite a cached version URL.
Generated archives, sequences, and all `data/` contents are ignored by Git.

The integration follows the official [PMTiles MapLibre protocol](https://docs.protomaps.com/pmtiles/maplibre)
and [Tippecanoe preparation guide](https://docs.protomaps.com/pmtiles/create).
Pinned MapLibre 5.20.0 and PMTiles 4.4.0 browser bundles and upstream licenses live
in `static/vendor/`; no runtime CDN is needed for those libraries. Raster basemaps
continue to use their existing external providers.

## Run and refresh

```sh
./FIRECAN.sh
# Or, with dependencies already installed:
venv/bin/gunicorn firecan_main:app
```

The default renderer is `tiles`, enabled after the checks below passed. The
rollback switch is temporary:

```sh
FIRECAN_MAP_RENDERER=legacy venv/bin/gunicorn firecan_main:app
# Also works with FIRECAN.sh or python app/firecan_main.py.
```

`FIRECAN_TILE_ROOT=/absolute/path/to/tiles` selects another artifact directory.
The map waits for `/data_status` to report ready, validates `/map_manifest`, and
automatically displays all fires. Missing or stale tiles produce an explanatory
error while the existing data download process remains unchanged. After building
missing artifacts, reload the page. Exports still use `/fx_main`.

Each worker pins the identities of the original/display files when loading.
Source hashes are cached by device/inode/size/mtime/ctime, checked against the
manifest, and recomputed when files change. Replacing the datasets beneath a
worker invalidates tiled queries until restart. This deliberately prevents IDs
from being applied to different records. The first manifest request in each
worker hashes the datasets, so startup I/O can add latency before caches warm.
Queries have no selection token or per-worker session state.

For a dataset refresh: prepare matched original/display files, build the
corresponding tiles, stop serving during the final dataset/artifact replacement,
replace all matched files, restart **every** worker, and reload maps. Do not mix
Parquet files from different builds. Retain old tile directories only for old
clients' byte-range reads; new selections must match the current manifest.

On macOS, Gunicorn now imports the app in each worker (`preload_app=False`),
because preloading the Arrow/GEOS environment before fork caused native worker
crashes during validation. Linux retains preloading. On a fresh macOS install,
run the normal single-process setup once to prepare watershed files before
starting multiple workers; existing fire-download locking remains unchanged.

## API

`GET /map_manifest` returns the manifest plus `archive_url`, with `Cache-Control:
no-store`. Missing, incomplete, mismatched, or not-ready artifacts return 503.

`POST /map_query` requires `dataset_version` from that manifest and accepts the
existing province, year, size, radius, watershed, and `polygon_geojson` filters:

```json
{"dataset_version":"<version>","provinces":["QC"],"min_year":2016,"max_year":2025}
```

Responses contain `dataset_version`, exact `count`, `selection: {mode, ids}`, and
`user_point`, `user_buffer`, and `watershed_polygon` overlays. `mode` is `all`,
`include`, or `exclude`. The shorter of matching and complementary IDs is sent;
ties use inclusion. Empty results explicitly include an empty list; unrestricted
results use `all`. No fire geometry is sent. Wrong versions return 409, invalid
requests 400, oversized uploads 413, and unavailable artifacts/data 503.

The same existing filter implementation reads original geometry for spatial
checks. Radius and uploaded boundaries use intersection; watershed searches use
containment. IDs are used only for display and are not added as export columns.
`GET/POST /fx_main`, `polygon_tol`, validation, original geometry exports, and
100 MiB legacy display/geometry export limits remain supported. CSV behavior is
unchanged. The tiled path bypasses the large display GeoJSON response.

`GET/HEAD /map_tiles/<version>/fires.pmtiles` serves conditional byte ranges,
including 206, 304, and 416 responses, with an ETag and immutable caching. There
is no whole-archive content compression. Any future proxy must honor Range,
Content-Range, and the `no-transform` cache directive and preserve byte offsets.

The UI applies one membership expression against MVT feature IDs. The layer
filter also governs tiles loaded after panning. Popups deduplicate fragments by
ID and render text with DOM `textContent`. Boundary/point/buffer/watershed
geometry uses separate small GeoJSON sources. Failed queries retain the last
successful map/count; AbortController and request generations ignore old replies.
Reset clears uploads/filters/overlays and restores the national selection/view.

## Checks and reproduction

```sh
venv/bin/python -m pip install -r requirements-dev.txt
venv/bin/python -m unittest discover -s tests -v
TIPPECANOE=$(command -v tippecanoe) venv/bin/python -m unittest discover -s tests -v

# Against a ready tiled server:
venv/bin/python scripts/check_browser.py --url http://127.0.0.1:5050
venv/bin/python scripts/check_real_tiles.py
venv/bin/python scripts/benchmark_map.py --url http://127.0.0.1:5050 --repeats 3
# Optional visible browser: add --headed.
```

The ordinary suite uses tiny synthetic datasets without downloads; the actual
MVT test is skipped unless `TIPPECANOE` is set. The validated run passed all 17
tests, including original filtering/export tests. Coverage includes exact IDs
and counts for every filter family and combinations, empty/all/complement
selections, unchanged geometry exports, invalid requests, version/source
mismatches, missing artifacts, atomic-build failure, byte ranges, stable
fragments across zooms, rare-year and small-fire retention. Browser checks cover
auto loading, safe popup text, failure/stale-reply handling, boundary preview and
replacement, Reset, basemap changes, the Leaflet watershed dialog, and missing
manifest/tile/WebGL states. Twelve concurrent queries on two real Gunicorn
workers returned identical 25,267-record recent Quebec results. The real archive
check found the rare 1969 fire and five tiny fires (~0.001 ha) at zoom 14,
including repeated fragments retaining the same ID. See raw files under
`docs/benchmarks/`.

The benchmark fixes the viewport at 1280 × 800, uses a new browser context per
case, replaces external rasters with a local 1-pixel image to exclude basemap
latency, and waits for fire layers to finish loading. OS disk caches and server
data are warm. New contexts have cold browser/PMTiles caches; repeated selection
applications within a context are warm. Playwright request routing disables the
ordinary HTTP cache. This is a localhost overlay test, not an external network
or basemap benchmark. Startup downloads and tile preparation are outside the
time-to-display measurement. Each case first loads the automatic national
selection, then applies its filters at the same overview; the broad boundary is
sent through the same `polygon_geojson` API as a validated upload. The separate
browser regression exercises the actual file chooser and preview.

Selection latency is split into server query/transfer and application through
MapLibre idle plus two animation frames. Pan/zoom uses a 2.2-second camera
animation and samples animation-frame intervals and MapLibre render events over
2.5 seconds, including newly loaded tiles. It also verifies no rendered feature
ID violates the selection after the pan. These event rates are responsiveness
proxies; they do not measure physical display presentation. Memory reports both
main-page JS heap and summed Chrome browser/GPU/renderer/utility process RSS,
which can double-count shared pages and is not peak private memory.

## Recorded before/after results

Validated on Apple M4 (10 cores), 16 GiB RAM, macOS 26.6.2, installed Chrome
155.0.8059.85 in headless mode, two Gunicorn workers. Dataset version:
`1f2037da5cbe74a9531aaa90dee8e0836c4e016bd9620cf674f7a16d0ea5690d`.
The completed archive is **799.76 MiB on disk**; it is read in ranges.

The “before” GeoJSON figures below are the corrected measurements supplied in
the request, excluding internal bounding-box fields. They are response sizes
before the legacy 100 MiB check, not claimed successful browser transfers.
Legacy browser latency, memory, and FPS were not measured in this run.

| Selection | Exact count | Before: display GeoJSON | After: fire tiles at overview | After: selection JSON | First apply / warm apply | Query time |
|---|---:|---:|---:|---:|---:|---:|
| Canada | 157,093 | 312.25 MiB (413) | 0.82 MiB | 0.2 KiB | 0.34 / 0.58 s | 0.01 s |
| Quebec | 113,027 | 126.13 MiB (413) | 0.82 MiB | 248.8 KiB | 1.15 / 0.27 s | 0.29 s |
| Canada 2016–2025 | 36,977 | 86.21 MiB | 0.82 MiB | 225.8 KiB | 1.61 / 0.29 s | 0.02 s |
| Quebec 2016–2025 | 25,267 | 23.26 MiB | 0.82 MiB | 159.5 KiB | 0.83 / 0.28 s | 0.02 s |
| Broad boundary | 128,127 | Not measured | 0.82 MiB | 162.6 KiB | 1.16 / 0.34 s | 8.65 s |

The overview tile transfer is the automatically loaded national overlay in each
fresh context. Applying a selection at that same camera reuses those tiles; the
additional selection JSON is listed separately. Quebec sends 44,066 excluded
IDs; the broad boundary sends 28,966 excluded IDs for 128,127 matching records.

| Acceptance target | Recorded result |
|---|---|
| National display without the 100 MiB error | Passed: 157,093 exact records |
| Cold national fire data ≤10 MiB | Passed: 0.82 MiB tiles plus a small selection/manifest response |
| National display ≤5 s once datasets/tiles ready | Passed: 2.35 s in the final run; other fresh contexts 0.46–0.67 s |
| Apply returned selection ≤2 s | Passed: all five first applications 0.34–1.61 s |
| Ordinary pan/zoom ≥30 FPS | Passed in this run: 59.4–60.3 render events/s, p95 frame interval 16.7–16.8 ms |

Main-page JS heap was approximately 10.7–14.6 MiB before the pan. Summed Chrome
process RSS sampled after pan was approximately 0.47–1.27 GiB. This is substantial
browser memory despite the smaller network payload. No memory target was
specified. The headless measurements do not establish mobile, Safari/Firefox,
physical-display, slow-disk, or production network performance.

The broad uploaded-boundary query still takes roughly **8–11 seconds** in these
runs because it reads original geometry for exact intersection checks across a
large part of the dataset. Its returned ID filter applies in about 1.16 seconds
in the final run, but end-to-end filtering is about 9.8 seconds. The two-second
target applies to applying a returned selection; the full spatial query is a
remaining performance limitation. No geometry fidelity or records were traded
away to reduce this query time.

Other limits: the archive and scratch space add local storage; all analysis
downloads remain required; detailed zooms can fetch larger tiles; subpixel
polygons can be invisible at overview scale; modern WebGL2 is required; and
raster provider availability is outside these measurements. Rare/small-fire
retention was sampled and tested with fixtures, not exhaustively audited for
all 157,093 records at every zoom. The build flags forbid size-driven dropping
and combining records. Deployment, external hosting, lighter downloads, and a
full watershed-renderer migration remain outside this release.
