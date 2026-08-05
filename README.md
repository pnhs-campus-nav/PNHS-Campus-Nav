# PNHS Campus Nav APK

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
