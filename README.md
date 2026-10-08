# PNHS Campus Nav

Public download and offline map package repository for PNHS Campus Nav.

## Downloads

Use GitHub Releases to download:

- PNHS Campus Nav APK
- pnhs-offline-map-package.zip

## Offline Map

The offline map package can be rebuilt from OpenStreetMap data using:

```bash
python tools/offline-map/build_pnhs_package.py
```

The Android app downloads the latest map package from GitHub Releases:

```text
https://github.com/pnhs-campus-nav/PNHS-Campus-Nav/releases/latest/download/pnhs-offline-map-package.zip
```

## Updating The Map

Open the Actions tab and run `Build Offline Map Package`. The workflow publishes `pnhs-offline-map-package.zip` to the latest GitHub Release.

The Android app source, Firebase config, APK signing key, and keystore files are intentionally not stored in this public repository.

## Why This Repository Must Stay Public

The Android app checks this repository's release metadata **unauthenticated** to decide whether a newer offline map package exists. It reads `GET /repos/pnhs-campus-nav/PNHS-Campus-Nav/releases/latest` and compares the release asset's `sha256` digest against the copy already installed on the device.

GitHub answers unauthenticated requests for a private repository with `404 Not Found`, not `403`. That is not a rate limit that eventually clears — it fails on every request, from every device, permanently. The app treats a failed check as "no update information available" and simply never shows the "new map version available" pill. Nothing breaks, but updates silently stop being advertised.

This repository therefore has to remain publicly readable for the in-app map update notification to work. Nothing sensitive is stored here: the contents are the offline map builder, its documentation, and the workflow that publishes the package. Real credentials (`keystore.properties`, keystore files, `google-services.json`) are excluded by `.gitignore` and must never be added.
