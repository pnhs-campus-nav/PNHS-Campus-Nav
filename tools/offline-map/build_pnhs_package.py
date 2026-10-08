#!/usr/bin/env python3
"""Build a small PNHS/Passi offline map package from OpenStreetMap data.

The output ZIP can be bundled in app assets or served from a stable HTTPS URL.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import shutil
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path
from typing import Any


DEFAULT_BBOX = (11.1060, 122.6400, 11.1135, 122.6475)  # south, west, north, east
DEFAULT_OVERPASS_URLS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://z.overpass-api.de/api/interpreter",
    "https://overpass.private.coffee/api/interpreter",
]

# Overpass mirrors return 504/500 under load far more often than they fail for a
# real reason, so a single attempt per endpoint is not enough to conclude the
# build is impossible. These two constants govern the retry budget around the
# whole endpoint list. Observed in practice: two consecutive full passes over the
# list failing entirely, then the third succeeding.
OVERPASS_ATTEMPTS = 3
OVERPASS_RETRY_SLEEP_SECONDS = 45

# Every byte inside the ZIP is hashed by the app to decide whether a published
# package differs from the installed one, so the archive must be reproducible:
# two builds from the same OSM input have to produce identical bytes, on any
# machine, at any time. That rules out both a wall-clock timestamp in the
# metadata and ZIP entry timestamps inherited from the filesystem, so entries
# carry this fixed date instead. 1980-01-01 is the earliest value the ZIP format
# can represent.
FIXED_ZIP_DATE_TIME = (1980, 1, 1, 0, 0, 0)

# Decimal places kept for every coordinate written into the GeoJSON layers.
#
# Belt and braces, not the primary defence -- math.fsum() in centroid() is what
# actually removes the cross-version instability, and rounding alone is not
# sufficient: a centroid that happens to sit within summation error of a
# 0.00000005 boundary rounds to opposite sides on different interpreters.
#
# Seven decimals is about 1.1 cm, so this costs nothing a campus map can use,
# and it means any float arithmetic added to a layer later is bounded to a
# predictable, comparable precision. Applied to whole feature collections in
# round_floats() so new layers are covered without having to remember.
# Do not remove this in the name of precision -- nothing here needs nanometre
# accuracy.
COORDINATE_PRECISION = 7

ROAD_HIGHWAYS = {
    "service",
    "residential",
    "living_street",
    "unclassified",
    "tertiary",
    "secondary",
}
PATH_HIGHWAYS = {
    "footway",
    "path",
    "pedestrian",
    "steps",
    "track",
    "cycleway",
}
LANDUSE_VALUES = {
    "grass",
    "forest",
    "meadow",
    "recreation_ground",
    "residential",
    "commercial",
    "education",
    "school",
}
LEISURE_VALUES = {
    "park",
    "pitch",
    "sports_centre",
    "track",
    "garden",
}
NATURAL_LANDUSE_VALUES = {
    "wood",
    "grassland",
    "scrub",
}
NATURAL_WATER_VALUES = {
    "water",
    "bay",
}


def main() -> int:
    args = parse_args()
    bbox = tuple(args.bbox)
    output_zip = Path(args.output).resolve()
    work_dir = Path(args.work_dir).resolve()

    if work_dir.exists():
        shutil.rmtree(work_dir)
    (work_dir / "map").mkdir(parents=True, exist_ok=True)
    (work_dir / "routing").mkdir(parents=True, exist_ok=True)

    if args.input_osm_json:
        input_osm_json = Path(args.input_osm_json).resolve()
        print(f"Using cached OSM data from {input_osm_json}")
        overpass_json = input_osm_json.read_text(encoding="utf-8")
    else:
        print(f"Fetching OSM data for bbox south={bbox[0]}, west={bbox[1]}, north={bbox[2]}, east={bbox[3]}")
        overpass_json = fetch_overpass(args.overpass_url, build_query(bbox))
    (work_dir / "routing" / "osm-route-graph.json").write_text(overpass_json, encoding="utf-8")

    data = json.loads(overpass_json)
    layers = build_layers(data)
    for layer_name, feature_collection in layers.items():
        target = work_dir / "map" / f"{layer_name}.geojson"
        target.write_text(
            json.dumps(round_floats(feature_collection), ensure_ascii=False, separators=(",", ":")),
            encoding="utf-8",
        )

    metadata = {
        "packageType": "campusatlas-offline-map",
        "schemaVersion": 1,
        # Replaces the former wall-clock "generatedAt". The app hashes the whole
        # ZIP to detect updates, so a build timestamp here made every build
        # publish a different digest even when the map data was unchanged, which
        # left first-launch installs permanently reporting a phantom update. The
        # source digest identifies the data instead, and is stable across
        # machines and reruns. The snapshot's real fetch date lives in
        # tools/offline-map/data/README.md, outside the archive.
        "sourceDigest": "sha256:" + hashlib.sha256(overpass_json.encode("utf-8")).hexdigest(),
        "source": "OpenStreetMap via cached Overpass JSON" if args.input_osm_json else "OpenStreetMap via Overpass API",
        "license": "ODbL",
        "bbox": {
            "south": bbox[0],
            "west": bbox[1],
            "north": bbox[2],
            "east": bbox[3],
        },
        "layers": sorted(layers.keys()),
        "routingGraph": "routing/osm-route-graph.json",
    }
    (work_dir / "metadata.json").write_text(
        json.dumps(metadata, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    output_zip.parent.mkdir(parents=True, exist_ok=True)
    if output_zip.exists():
        output_zip.unlink()
    with zipfile.ZipFile(output_zip, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for file in sorted(work_dir.rglob("*")):
            if file.is_file():
                # archive.write() would stamp each entry with the file's mtime,
                # making the output depend on when the files happened to be
                # written. Explicit ZipInfo entries keep the bytes stable.
                info = zipfile.ZipInfo(file.relative_to(work_dir).as_posix(), date_time=FIXED_ZIP_DATE_TIME)
                info.compress_type = zipfile.ZIP_DEFLATED
                info.external_attr = 0o644 << 16
                archive.writestr(info, file.read_bytes())

    if not args.keep_work_dir:
        shutil.rmtree(work_dir)

    print(f"Created {output_zip}")
    print("The app can bundle this ZIP in assets or download it from offlineMapPackageUrl.")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build the CampusAtlas PNHS offline map package.")
    parser.add_argument(
        "--bbox",
        type=float,
        nargs=4,
        metavar=("SOUTH", "WEST", "NORTH", "EAST"),
        default=DEFAULT_BBOX,
        help="Bounding box to export. Defaults to PNHS and nearby roads.",
    )
    parser.add_argument(
        "--output",
        default="build/offline-map/pnhs-offline-map-package.zip",
        help="Output ZIP path.",
    )
    parser.add_argument(
        "--work-dir",
        default="build/offline-map/package",
        help="Temporary package directory.",
    )
    parser.add_argument(
        "--overpass-url",
        action="append",
        default=[],
        help="Overpass API interpreter URL.",
    )
    parser.add_argument(
        "--input-osm-json",
        default="",
        help="Use a cached Overpass JSON file instead of fetching from Overpass.",
    )
    parser.add_argument(
        "--keep-work-dir",
        action="store_true",
        help="Keep the generated unpacked package directory for inspection.",
    )
    return parser.parse_args()


def build_query(bbox: tuple[float, float, float, float]) -> str:
    south, west, north, east = bbox
    bbox_text = f"{south},{west},{north},{east}"
    return f"""
        [out:json][timeout:60];
        (
          way["building"]({bbox_text});
          way["highway"]({bbox_text});
          way["landuse"]({bbox_text});
          way["leisure"]({bbox_text});
          way["natural"]({bbox_text});
          way["amenity"]({bbox_text});
          node["amenity"]({bbox_text});
          node["name"]({bbox_text});
        );
        out body geom;
    """


def fetch_overpass(overpass_urls: list[str], query: str) -> str:
    urls = overpass_urls or DEFAULT_OVERPASS_URLS
    body = urllib.parse.urlencode({"data": query}).encode("utf-8")
    errors: list[str] = []
    for attempt in range(1, OVERPASS_ATTEMPTS + 1):
        if attempt > 1:
            print(f"All endpoints failed, retrying pass {attempt} of {OVERPASS_ATTEMPTS} "
                  f"in {OVERPASS_RETRY_SLEEP_SECONDS}s")
            time.sleep(OVERPASS_RETRY_SLEEP_SECONDS)
        for overpass_url in urls:
            request = urllib.request.Request(
                overpass_url,
                data=body,
                headers={
                    "Content-Type": "application/x-www-form-urlencoded",
                    "User-Agent": "CampusAtlasOfflineMapBuilder/1.0",
                },
                method="POST",
            )
            try:
                print(f"Trying {overpass_url}")
                with urllib.request.urlopen(request, timeout=90) as response:
                    return response.read().decode("utf-8")
            except urllib.error.HTTPError as error:
                body_text = read_http_error_body(error)
                errors.append(f"{overpass_url}: HTTP {error.code} {error.reason}. {body_text}")
            except Exception as error:  # noqa: BLE001 - print all endpoint failures for CLI users.
                errors.append(f"{overpass_url}: {error}")

    raise RuntimeError("All Overpass endpoints failed:\n" + "\n".join(errors))


def round_floats(value: Any, precision: int = COORDINATE_PRECISION) -> Any:
    """Recursively rounds every float so the output cannot depend on summation order.

    Applied to whole feature collections rather than to individual coordinate
    producers, so any arithmetic added to a layer later is covered without
    having to remember. Ints and bools pass through untouched.
    """
    if isinstance(value, float):
        return round(value, precision)
    if isinstance(value, list):
        return [round_floats(item, precision) for item in value]
    if isinstance(value, dict):
        return {key: round_floats(item, precision) for key, item in value.items()}
    return value


def read_http_error_body(error: urllib.error.HTTPError) -> str:
    try:
        return error.read().decode("utf-8", errors="replace")[:500].strip()
    except Exception:  # noqa: BLE001 - best-effort diagnostic only.
        return ""


def build_layers(data: dict[str, Any]) -> dict[str, dict[str, Any]]:
    layer_features: dict[str, list[dict[str, Any]]] = {
        "background": [build_background_feature(data)],
        "buildings": [],
        "landuse": [],
        "water": [],
        "roads": [],
        "paths": [],
        "poi-labels": [],
        "road-labels": [],
        "labels": [],
    }

    for element in data.get("elements", []):
        tags = element.get("tags") or {}
        element_type = element.get("type")
        if element_type == "node":
            add_node_label(layer_features["poi-labels"], element, tags)
            continue
        if element_type != "way":
            continue

        geometry = element.get("geometry") or []
        if len(geometry) < 2:
            continue

        layer_name = classify_way(tags)
        if layer_name is None:
            add_way_point_label(layer_features["poi-labels"], geometry, tags)
            continue

        properties = compact_properties(tags, element.get("id"))
        if layer_name in {"roads", "paths"}:
            layer_features[layer_name].append(
                feature("LineString", line_coordinates(geometry), properties)
            )
            add_way_line_label(layer_features["road-labels"], geometry, tags)
        else:
            polygon = polygon_coordinates(geometry)
            if polygon:
                layer_features[layer_name].append(feature("Polygon", polygon, properties))
            add_way_point_label(layer_features["poi-labels"], geometry, tags)

    layer_features["labels"] = layer_features["poi-labels"] + layer_features["road-labels"]

    return {
        layer: feature_collection(features)
        for layer, features in layer_features.items()
    }


def classify_way(tags: dict[str, Any]) -> str | None:
    highway = tags.get("highway")
    if highway in ROAD_HIGHWAYS:
        return "roads"
    if highway in PATH_HIGHWAYS:
        return "paths"
    if tags.get("building"):
        return "buildings"
    if tags.get("natural") in NATURAL_WATER_VALUES or tags.get("water"):
        return "water"
    if (
        tags.get("landuse") in LANDUSE_VALUES
        or tags.get("leisure") in LEISURE_VALUES
        or tags.get("natural") in NATURAL_LANDUSE_VALUES
        or tags.get("amenity") == "school"
    ):
        return "landuse"
    return None


def add_node_label(
    labels: list[dict[str, Any]],
    element: dict[str, Any],
    tags: dict[str, Any],
) -> None:
    name = tags.get("name")
    lat = element.get("lat")
    lon = element.get("lon")
    if not name or lat is None or lon is None:
        return
    labels.append(
        feature(
            "Point",
            [lon, lat],
            compact_properties(tags, element.get("id")),
        )
    )


def add_way_point_label(
    labels: list[dict[str, Any]],
    geometry: list[dict[str, Any]],
    tags: dict[str, Any],
) -> None:
    if not tags.get("name"):
        return
    center = centroid(geometry)
    if center is None:
        return
    labels.append(
        feature(
            "Point",
            [center[1], center[0]],
            compact_properties(tags, None),
        )
    )


def add_way_line_label(
    labels: list[dict[str, Any]],
    geometry: list[dict[str, Any]],
    tags: dict[str, Any],
) -> None:
    if not tags.get("name"):
        return
    coordinates = line_coordinates(geometry)
    if len(coordinates) < 2:
        return
    labels.append(
        feature(
            "LineString",
            coordinates,
            compact_properties(tags, None),
        )
    )


def build_background_feature(data: dict[str, Any]) -> dict[str, Any]:
    bounds = derive_bounds(data) or DEFAULT_BBOX
    south, west, north, east = pad_bounds(bounds, padding=0.00035)
    return feature(
        "Polygon",
        [[
            [west, south],
            [east, south],
            [east, north],
            [west, north],
            [west, south],
        ]],
        {"name": "Offline map background"},
    )


def derive_bounds(data: dict[str, Any]) -> tuple[float, float, float, float] | None:
    latitudes: list[float] = []
    longitudes: list[float] = []
    for element in data.get("elements", []):
        if "lat" in element and "lon" in element:
            latitudes.append(element["lat"])
            longitudes.append(element["lon"])
        for point in element.get("geometry") or []:
            if "lat" in point and "lon" in point:
                latitudes.append(point["lat"])
                longitudes.append(point["lon"])
    if not latitudes or not longitudes:
        return None
    return min(latitudes), min(longitudes), max(latitudes), max(longitudes)


def pad_bounds(
    bounds: tuple[float, float, float, float],
    padding: float,
) -> tuple[float, float, float, float]:
    south, west, north, east = bounds
    return south - padding, west - padding, north + padding, east + padding


def compact_properties(tags: dict[str, Any], osm_id: int | None) -> dict[str, Any]:
    keep_keys = [
        "name",
        "amenity",
        "building",
        "highway",
        "landuse",
        "leisure",
        "natural",
        "ref",
    ]
    properties = {key: tags[key] for key in keep_keys if key in tags}
    if osm_id is not None:
        properties["osm_id"] = osm_id
    return properties


def line_coordinates(geometry: list[dict[str, Any]]) -> list[list[float]]:
    return [[point["lon"], point["lat"]] for point in geometry if "lat" in point and "lon" in point]


def polygon_coordinates(geometry: list[dict[str, Any]]) -> list[list[list[float]]] | None:
    ring = line_coordinates(geometry)
    if len(ring) < 3:
        return None
    if ring[0] != ring[-1]:
        ring.append(ring[0])
    return [ring]


def centroid(geometry: list[dict[str, Any]]) -> tuple[float, float] | None:
    points = [(point["lat"], point["lon"]) for point in geometry if "lat" in point and "lon" in point]
    if not points:
        return None
    # math.fsum, not sum. sum() is only correct to within accumulated error, and
    # CPython 3.12 changed its algorithm (Neumaier compensated summation), so the
    # same geometry produced slightly different centroids depending on the
    # interpreter version. fsum computes the exactly-rounded sum and is stable
    # across versions, which is what makes the package digest reproducible.
    # Rounding in round_floats() is not a substitute: it cannot repair a value
    # that lands either side of a rounding boundary, which is precisely what
    # happened to a couple of centroids before this was fixed.
    return (
        math.fsum(point[0] for point in points) / len(points),
        math.fsum(point[1] for point in points) / len(points),
    )


def feature(geometry_type: str, coordinates: Any, properties: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": "Feature",
        "properties": properties,
        "geometry": {
            "type": geometry_type,
            "coordinates": coordinates,
        },
    }


def feature_collection(features: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "type": "FeatureCollection",
        "features": features,
    }


if __name__ == "__main__":
    sys.exit(main())
