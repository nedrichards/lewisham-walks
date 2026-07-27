#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

DEFAULT_BOUNDARIES = {
    "Lewisham": Path("data/boundaries/lewisham.geojson"),
    "Greenwich": Path("data/boundaries/greenwich.geojson"),
    "Southwark": Path("data/boundaries/southwark.geojson"),
}
ALLOWED_GRADES = frozenset({"I", "II*"})


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
    return point_in_ring(lon, lat, polygon[0]) and not any(
        point_in_ring(lon, lat, hole) for hole in polygon[1:]
    )


def boundary_to_multipolygon(boundary: dict[str, Any]) -> list[list[list[list[float]]]]:
    geometry = boundary["geometry"]
    if geometry["type"] == "Polygon":
        return [geometry["coordinates"]]
    if geometry["type"] == "MultiPolygon":
        return geometry["coordinates"]
    raise ValueError("Boundary must be Polygon or MultiPolygon GeoJSON.")


def point_in_multipolygon(lon: float, lat: float, multipolygon: list[list[list[list[float]]]]) -> bool:
    return any(point_in_polygon(lon, lat, polygon) for polygon in multipolygon)


def normalise_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def iso_date_from_epoch_ms(value: Any) -> str:
    if value is None or value == "":
        return ""
    return datetime.fromtimestamp(float(value) / 1000, tz=UTC).date().isoformat()


def readable_date(iso_date: str) -> str:
    parsed = date.fromisoformat(iso_date)
    return f"{parsed.day} {parsed.strftime('%B %Y')}"


def coordinates_from_feature(feature: dict[str, Any]) -> tuple[float, float] | None:
    geometry = feature.get("geometry", {})
    coordinates = geometry.get("coordinates", [])
    if geometry.get("type") == "Point" and len(coordinates) >= 2:
        return float(coordinates[0]), float(coordinates[1])
    if geometry.get("type") == "MultiPoint" and coordinates and len(coordinates[0]) >= 2:
        return float(coordinates[0][0]), float(coordinates[0][1])
    return None


def record_from_feature(feature: dict[str, Any], borough: str) -> dict[str, Any] | None:
    properties = feature.get("properties", {})
    grade = normalise_text(properties.get("Grade"))
    list_entry = normalise_text(properties.get("ListEntry"))
    coordinates = coordinates_from_feature(feature)
    if grade not in ALLOWED_GRADES or not list_entry or coordinates is None:
        return None

    lon, lat = coordinates
    listed_on = iso_date_from_epoch_ms(properties.get("ListDate"))
    amended_on = iso_date_from_epoch_ms(properties.get("AmendDate"))
    significance = (
        "recognised as being of exceptional interest"
        if grade == "I"
        else "recognised as being particularly important"
    )
    description = f"Grade {grade} listed building or structure, {significance}."
    if listed_on:
        description += f" First listed {readable_date(listed_on)}."
    if amended_on:
        description += f" Listing last amended {readable_date(amended_on)}."

    return {
        "id": f"historic-england-{list_entry}",
        "kind": "listed-building",
        "collection": "historic-england-listed-buildings",
        "source_name": "Historic England",
        "external_id": list_entry,
        "title": normalise_text(properties.get("Name")) or f"Listed building {list_entry}",
        "description": description,
        "lat": lat,
        "lon": lon,
        "address": "",
        "attributes": {
            "grade": grade,
            "listed_on": listed_on,
            "amended_on": amended_on,
            "ngr": normalise_text(properties.get("NGR")),
        },
        "source_url": normalise_text(properties.get("hyperlink"))
        or f"https://historicengland.org.uk/listing/the-list/list-entry/{list_entry}",
        "borough": borough,
        "is_accurate": True,
        "curation_status": "in_scope",
        "curation_note": "Official point location; this does not represent the building footprint.",
    }


def records_from_boundaries(
    dump: dict[str, Any],
    boundaries: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    boundary_shapes = {
        borough: boundary_to_multipolygon(boundary)
        for borough, boundary in boundaries.items()
    }
    records_by_id: dict[str, dict[str, Any]] = {}
    for feature in dump.get("features", []):
        coordinates = coordinates_from_feature(feature)
        if coordinates is None:
            continue
        lon, lat = coordinates
        for borough, multipolygon in boundary_shapes.items():
            if not point_in_multipolygon(lon, lat, multipolygon):
                continue
            record = record_from_feature(feature, borough)
            if record is not None:
                records_by_id.setdefault(record["id"], record)
            break
    grade_order = {"I": 0, "II*": 1}
    return sorted(
        records_by_id.values(),
        key=lambda item: (
            item["borough"],
            grade_order[item["attributes"]["grade"]],
            item["title"].casefold(),
            item["external_id"],
        ),
    )


def parse_boundary_args(values: list[str]) -> dict[str, Path]:
    boundaries: dict[str, Path] = {}
    for value in values:
        if "=" not in value:
            raise ValueError("--boundary must be in BOROUGH=PATH form")
        borough, path = value.split("=", 1)
        boundaries[borough.strip()] = Path(path.strip())
    return boundaries


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate bundled Grade I and II* listed-building points from Historic England GeoJSON."
    )
    parser.add_argument("dump", type=Path, help="Historic England listed-building point GeoJSON")
    parser.add_argument(
        "--boundary",
        action="append",
        default=[],
        metavar="BOROUGH=PATH",
        help="Boundary GeoJSON to include. May be repeated; defaults to the three supported boroughs.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("src/lewisham_walks/data/listed_buildings.json"),
    )
    args = parser.parse_args()

    dump = json.loads(args.dump.read_text(encoding="utf-8"))
    boundary_paths = parse_boundary_args(args.boundary) if args.boundary else DEFAULT_BOUNDARIES
    boundaries = {
        borough: json.loads(path.read_text(encoding="utf-8"))
        for borough, path in boundary_paths.items()
    }
    records = records_from_boundaries(dump, boundaries)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(records, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    borough_counts = ", ".join(
        f"{borough}: {sum(record['borough'] == borough for record in records)}"
        for borough in boundary_paths
    )
    print(f"Wrote {len(records)} listed buildings to {args.output} ({borough_counts})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
