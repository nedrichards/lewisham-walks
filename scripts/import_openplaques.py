#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

DEFAULT_BOUNDARIES = {
    "Lewisham": Path("data/boundaries/lewisham.geojson"),
    "Greenwich": Path("data/boundaries/greenwich.geojson"),
    "Southwark": Path("data/boundaries/southwark.geojson"),
}


def point_in_ring(lon: float, lat: float, ring: list[list[float]]) -> bool:
    inside = False
    previous = len(ring) - 1
    for current, (current_lon, current_lat) in enumerate(ring):
        previous_lon, previous_lat = ring[previous]
        crosses_latitude = (current_lat > lat) != (previous_lat > lat)
        if crosses_latitude:
            intersection_lon = (previous_lon - current_lon) * (lat - current_lat) / (previous_lat - current_lat) + current_lon
            if lon < intersection_lon:
                inside = not inside
        previous = current
    return inside


def point_in_polygon(lon: float, lat: float, polygon: list[list[list[float]]]) -> bool:
    shell = polygon[0]
    holes = polygon[1:]
    return point_in_ring(lon, lat, shell) and not any(point_in_ring(lon, lat, hole) for hole in holes)


def point_in_multipolygon(lon: float, lat: float, multipolygon: list[list[list[list[float]]]]) -> bool:
    return any(point_in_polygon(lon, lat, polygon) for polygon in multipolygon)


def title_from_inscription(inscription: str) -> str:
    cleaned = normalise_text(inscription)
    if not cleaned:
        return "Untitled plaque"
    first_sentence = re.split(r"(?<=[.!?])\s+", cleaned, maxsplit=1)[0]
    if len(first_sentence) <= 72:
        return first_sentence
    words = first_sentence.split()
    title_words: list[str] = []
    for word in words:
        if sum(len(part) + 1 for part in [*title_words, word]) > 72:
            break
        title_words.append(word)
    return " ".join(title_words).rstrip(",;:") or cleaned[:72].rstrip()


def normalise_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def load_corrections(path: Path | None) -> dict[str, Any]:
    if path is None or not path.exists():
        return {"exclude": [], "records": {}}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return {
        "exclude": [str(item) for item in payload.get("exclude", [])],
        "records": {str(key): value for key, value in payload.get("records", {}).items()},
    }


def record_from_feature(feature: dict[str, Any], corrections: dict[str, Any], borough: str = "") -> dict[str, Any] | None:
    properties = feature.get("properties", {})
    plaque_id = str(properties.get("id", ""))
    if not plaque_id or plaque_id in corrections["exclude"]:
        return None

    geometry = feature.get("geometry", {})
    coordinates = geometry.get("coordinates", [])
    if geometry.get("type") != "Point" or len(coordinates) < 2:
        return None

    inscription = normalise_text(str(properties.get("inscription", "")))
    override = corrections["records"].get(plaque_id, {})
    lon = float(override.get("lon", coordinates[0]))
    lat = float(override.get("lat", coordinates[1]))
    description = normalise_text(str(override.get("description", inscription)))

    return {
        "id": f"openplaques-{plaque_id}",
        "kind": "plaque",
        "collection": override.get("collection", override.get("scheme", "openplaques")),
        "source_name": "Open Plaques",
        "external_id": plaque_id,
        "title": override.get("title") or title_from_inscription(description),
        "description": description,
        "lat": lat,
        "lon": lon,
        "address": override.get("address", ""),
        "attributes": {"colour": override.get("colour", "unknown")},
        "source_url": override.get("source_url", f"https://openplaques.org/plaques/{plaque_id}"),
        "borough": override.get("borough", borough),
        "is_accurate": bool(geometry.get("is_accurate", False)),
        "curation_status": override.get("curation_status", "candidate"),
        "curation_note": override.get("curation_note", "Needs brown-plaque scheme review."),
    }


def boundary_to_multipolygon(boundary: dict[str, Any]) -> list[list[list[list[float]]]]:
    geometry = boundary["geometry"]
    if geometry["type"] == "Polygon":
        return [geometry["coordinates"]]
    if geometry["type"] == "MultiPolygon":
        return geometry["coordinates"]
    raise ValueError("Boundary must be Polygon or MultiPolygon GeoJSON.")


def records_from_dump(
    dump: dict[str, Any],
    boundary: dict[str, Any],
    corrections: dict[str, Any],
    borough: str = "",
) -> list[dict[str, Any]]:
    multipolygon = boundary_to_multipolygon(boundary)
    records: list[dict[str, Any]] = []
    for feature in dump.get("features", []):
        record = record_from_feature(feature, corrections, borough)
        if record is None:
            continue
        if point_in_multipolygon(record["lon"], record["lat"], multipolygon):
            records.append(record)
    return sorted(records, key=lambda item: (item["title"].lower(), item["external_id"]))


def records_from_boundaries(
    dump: dict[str, Any],
    boundaries: dict[str, dict[str, Any]],
    corrections: dict[str, Any],
) -> list[dict[str, Any]]:
    records_by_id: dict[str, dict[str, Any]] = {}
    for borough, boundary in boundaries.items():
        for record in records_from_dump(dump, boundary, corrections, borough):
            records_by_id.setdefault(record["id"], record)
    return sorted(records_by_id.values(), key=lambda item: (item.get("borough", ""), item["title"].lower(), item["external_id"]))


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate bundled plaque fixture from Open Plaques GeoJSON.")
    parser.add_argument("dump", type=Path, help="Open Plaques thin GeoJSON dump")
    parser.add_argument(
        "--boundary",
        action="append",
        default=[],
        metavar="BOROUGH=PATH",
        help="Boundary GeoJSON to include. May be repeated. Defaults to Lewisham, Greenwich, and Southwark.",
    )
    parser.add_argument("--corrections", type=Path, default=Path("data/corrections/openplaques-lewisham.json"))
    parser.add_argument("--output", type=Path, default=Path("src/lewisham_walks/data/plaques.json"))
    args = parser.parse_args()

    dump = json.loads(args.dump.read_text(encoding="utf-8"))
    boundary_paths = parse_boundary_args(args.boundary) if args.boundary else DEFAULT_BOUNDARIES
    boundaries = {borough: json.loads(path.read_text(encoding="utf-8")) for borough, path in boundary_paths.items()}
    corrections = load_corrections(args.corrections)
    records = records_from_boundaries(dump, boundaries, corrections)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(records, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Wrote {len(records)} plaques to {args.output}")
    return 0


def parse_boundary_args(values: list[str]) -> dict[str, Path]:
    boundaries: dict[str, Path] = {}
    for value in values:
        if "=" not in value:
            raise ValueError("--boundary must be in BOROUGH=PATH form")
        borough, path = value.split("=", 1)
        boundaries[borough.strip()] = Path(path.strip())
    return boundaries


if __name__ == "__main__":
    raise SystemExit(main())
