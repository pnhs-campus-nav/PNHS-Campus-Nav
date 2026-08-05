# CampusAtlas Offline Map Package

This project uses a small OpenStreetMap-derived offline map package for the
locked PNHS/Passi map area. It is not scraped from `tile.openstreetmap.org`.

## Build

From the project root on Windows:

```powershell
.\tools\offline-map\build-pnhs-package.ps1
```

If Overpass is unavailable, rebuild from a cached Overpass JSON export:

```powershell
.\tools\offline-map\build-pnhs-package.ps1 -InputOsmJson build/offline-map/source-osm-route-graph.json
```

Output:

```text
build/offline-map/pnhs-offline-map-package.zip
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
