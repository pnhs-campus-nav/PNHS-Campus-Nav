# OSM Data Snapshots

`pnhs-overpass.json` is the OpenStreetMap extract the offline map package is built
from. It is committed to the repository so that the package build never depends
on a public Overpass API instance being reachable.

## Why this exists

The Android app decides whether a published map package is newer than the
installed one by comparing the SHA-256 of the package ZIP against the SHA-256 of
the ZIP shipped in the app. That comparison is only meaningful if the same
source data always produces the same bytes. Two things used to prevent that:

- a `generatedAt` wall-clock timestamp written into `metadata.json`
- ZIP entry timestamps inherited from the build machine's filesystem

Both are now removed, so building twice from the same snapshot yields identical
digests. See `docs/offline-map-package.md`.

The practical effect is that CI no longer fails when Overpass is overloaded.
Before this change a release run died with `All Overpass endpoints failed` when
the public mirrors returned 504/500, which happened on two of three consecutive
attempts while preparing this snapshot.

## Current snapshot

| Field | Value |
| --- | --- |
| File | `pnhs-overpass.json` |
| Fetched (UTC) | 2026-10-08T12:45:04Z |
| Endpoint | `https://overpass-api.de/api/interpreter` |
| Bounding box | `11.1060, 122.6400, 11.1135, 122.6475` |
| SHA-256 | `037d0afc6dff6ace9dc591cc31f73c6620ff844dde150177bf64d608c664b3c7` |
| Elements | 1488 (1358 ways, 130 nodes) |

This file's digest is also recorded as `sourceDigest` inside the built package's
`metadata.json`, so a package can always be traced back to the exact snapshot it
came from.

The fetch date is recorded here rather than inside the package on purpose: any
timestamp written into the ZIP changes its digest.

## Refreshing the snapshot

Map data is frozen until this is run deliberately. The workflow does not fetch
live data, so OSM edits will not appear in the app until you refresh and commit.

1. Fetch fresh data, retrying: the public mirrors return 504/500 under load far
   more often than they fail for a real reason.

   ```bash
   python3 tools/offline-map/build_pnhs_package.py --keep-work-dir \
     --output /tmp/probe.zip
   ```

   That fetches and builds in one step. To capture the raw response without
   building, post `build_query(DEFAULT_BBOX)` to any endpoint in
   `DEFAULT_OVERPASS_URLS` and save the body.

2. Save it over `pnhs-overpass.json` and update the table above.

3. Verify reproducibility before committing:

   ```bash
   python3 tools/offline-map/build_pnhs_package.py \
     --input-osm-json tools/offline-map/data/pnhs-overpass.json \
     --output /tmp/a.zip
   python3 tools/offline-map/build_pnhs_package.py \
     --input-osm-json tools/offline-map/data/pnhs-overpass.json \
     --output /tmp/b.zip
   sha256sum /tmp/a.zip /tmp/b.zip   # digests must match
   ```

4. Rebuild the bundled asset in the Android repository (see
   `docs/offline-map-package.md`) so the copy shipped inside the app matches the
   copy published by CI. If these two ever diverge, first-launch installs report
   a phantom map update.

5. Commit the snapshot and dispatch `offline-map-package.yml`.

Do not use `https://overpass.osm.ch` for this bbox. It answers `HTTP 200` but
serves a regional database, so it returns an empty `elements` array for the
Philippines rather than an error.
