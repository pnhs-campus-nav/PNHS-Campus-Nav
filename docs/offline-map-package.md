# CampusAtlas Offline Map Package

This project uses a small OpenStreetMap-derived offline map package for the
locked PNHS/Passi map area. It is not scraped from `tile.openstreetmap.org`.

## Build

CI builds from the committed snapshot at `tools/offline-map/data/pnhs-overpass.json`
rather than fetching Overpass live, so a release run does not fail when the public
mirrors are overloaded:

```bash
python tools/offline-map/build_pnhs_package.py \
  --input-osm-json tools/offline-map/data/pnhs-overpass.json \
  --output build/offline-map/pnhs-offline-map-package.zip
```

From the project root on Windows:

```powershell
.\tools\offline-map\build-pnhs-package.ps1
```

To build against live OSM data instead (for example when refreshing the
snapshot), omit `--input-osm-json`. This depends on the public Overpass mirrors
and will fail if they are all unavailable; the builder retries the whole endpoint
list a few times before giving up, because 504/500 responses under load are
usually transient.

Refreshing the committed snapshot itself is documented in
`tools/offline-map/data/README.md`. Map data does not change on its own — OSM
edits reach the app only when that snapshot is deliberately re-fetched.

Output:

```text
build/offline-map/pnhs-offline-map-package.zip
```

## Reproducibility

The package ZIP is built to be byte-for-byte reproducible: building twice from
the same snapshot produces the same SHA-256 on any machine. This matters because
the app detects map updates by comparing the digest of the published package
against the digest of the package it is running.

Two sources of drift were removed to make that hold:

- `metadata.json` carries a `sourceDigest` (SHA-256 of the source snapshot)
  instead of the former wall-clock `generatedAt` timestamp
- ZIP entries are written with a fixed timestamp instead of inheriting the build
  machine's file modification times

A third one only shows up across machines. Label and POI centroids were averaged
with `sum()`, whose algorithm CPython changed in 3.12 to use compensated
summation, so the same geometry produced centroids differing in the last bit
depending on the interpreter — nanometres on the ground, but a different package
digest. The build now uses `math.fsum()` and rounds coordinates to seven decimal
places, which makes the output identical on any Python version. Rounding alone
was not enough: a centroid sitting within summation error of a rounding boundary
still landed on opposite sides.

This matters because CI pins Python 3.11 while a developer's machine may run
something newer. Without this, the copy bundled in the APK never matched the copy
CI published, and every fresh install saw a map update that did not exist.

Verify after any change to the builder:

```bash
python tools/offline-map/build_pnhs_package.py --input-osm-json tools/offline-map/data/pnhs-overpass.json --output /tmp/a.zip
python tools/offline-map/build_pnhs_package.py --input-osm-json tools/offline-map/data/pnhs-overpass.json --output /tmp/b.zip
sha256sum /tmp/a.zip /tmp/b.zip   # must match
```

The ZIP contains:

- `map/background.geojson`
- `map/buildings.geojson`
- `map/landuse.geojson`
- `map/water.geojson`
- `map/roads.geojson`
- `map/paths.geojson`
- `map/poi-labels.geojson`
- `map/road-labels.geojson`
- `map/labels.geojson`
- `routing/osm-route-graph.json`
- `metadata.json`

## Upload

The app bundles `app/src/main/assets/offline-map/pnhs-offline-map-package.zip`
as the built-in fallback package.

Keep that bundled copy identical to the one CI publishes. The app records the
digest of whichever package it is running and compares it to the published
digest, so if the bundled copy drifts, a first-launch install reports a map
update that does not exist and the user has to refresh once to clear it. Rebuild
it from the snapshot with the command above and commit the result alongside any
snapshot change.

The default hosted package is the latest GitHub Release asset:

```text
https://github.com/pnhs-campus-nav/PNHS-Campus-Nav/releases/latest/download/pnhs-offline-map-package.zip
```

To publish a new map package from GitHub:

1. Open the repository on GitHub.
2. Go to `Actions`.
3. Run `Build Offline Map Package`.
4. Keep the release asset name as `pnhs-offline-map-package.zip`.

The Android app's `Settings -> Refresh Map Data` action downloads that hosted ZIP
when no Firebase override URL is configured. If the download fails, the app keeps
the current installed package, or falls back to the bundled asset on a fresh
install.

Firebase Storage is optional if you want a different per-campus package URL.

Set one of these fields on the matching `campusCodes/{code}` Firestore document:

```text
offlineMapPackageUrl
```

Fallback field names also supported:

```text
mapPackageUrl
offlineMapZipUrl
```

## App Behavior

During setup/settings offline download, the app tries to download and unpack the
package into app storage.

When the package exists, the MapLibre renderer draws the local GeoJSON map layers
over the online raster source. The local `background.geojson` layer is opaque so
the online raster text does not bleed through inside the package area. Offline,
those local layers still render even when the online raster tiles are unavailable.

The package also includes `routing/osm-route-graph.json`, which the app copies
into its local route graph cache.

## Custom Bounds

The default bounds cover PNHS and nearby roads. To change the area:

```powershell
python .\tools\offline-map\build_pnhs_package.py --bbox SOUTH WEST NORTH EAST
```

Use a small area. This pipeline is intended for a locked campus/nearby-neighborhood
map, not full-region Visayas scale.
