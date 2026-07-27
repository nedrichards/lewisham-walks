#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
from contextlib import suppress
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

DEFAULT_BOUNDARIES = {
    "Lewisham": Path("data/boundaries/lewisham.geojson"),
    "Greenwich": Path("data/boundaries/greenwich.geojson"),
    "Southwark": Path("data/boundaries/southwark.geojson"),
}
DATASET_URL = "https://data.london.gov.uk/dataset/cultural-infrastructure-map-2023-23697"
CATEGORY_INFO = {
    "archives": ("Archive", "check-ahead", "2022"),
    "artists-workspaces": ("Artists' workspace", "check-ahead", "2022"),
    "arts-centres": ("Arts centre", "public-facing", "2022"),
    "cinemas": ("Cinema", "public-facing", "2022"),
    "commercial-galleries": ("Gallery", "public-facing", "2022"),
    "dance-performance": ("Dance venue", "public-facing", "2022"),
    "libraries": ("Library", "public-facing", "2022"),
    "makerspaces": ("Makerspace", "check-ahead", "2022"),
    "museums": ("Museum or public gallery", "public-facing", "2022"),
    "music-venues": ("Music venue", "public-facing", "2024"),
    "theatres": ("Theatre", "public-facing", "2022"),
}
CATEGORY_PRIORITY = (
    "arts-centres",
    "cinemas",
    "commercial-galleries",
    "dance-performance",
    "museums",
    "music-venues",
    "theatres",
    "artists-workspaces",
    "makerspaces",
    "archives",
    "libraries",
)


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


def clean_text(value: Any) -> str:
    text = str(value or "").replace("\xa0", " ").strip()
    if any(marker in text for marker in ("â€", "Ã", "Â")):
        with suppress(UnicodeEncodeError, UnicodeDecodeError):
            text = text.encode("latin-1").decode("utf-8")
    return re.sub(r"\s+", " ", text).strip()


def normalise_website(value: Any) -> str:
    website = clean_text(value)
    if website.casefold() in {"", "na", "n/a", "none"}:
        return ""
    website = website.split()[0].rstrip("/#")
    website = re.sub(r"^https:/([^/])", r"https://\1", website, flags=re.IGNORECASE)
    if not re.match(r"^https?://", website, flags=re.IGNORECASE):
        if "." not in website:
            return ""
        website = f"https://{website}"
    parsed = urlparse(website)
    return website if parsed.netloc and "." in parsed.netloc else ""


def clean_address(row: dict[str, str]) -> str:
    parts: list[str] = []
    for field in ("address1", "address2", "address3"):
        part = clean_text(row.get(field))
        if part.casefold() in {"", "na", "n/a", "none"}:
            continue
        if part.casefold() not in {existing.casefold() for existing in parts}:
            parts.append(part)
    return ", ".join(parts)


def record_key(category: str, name: str) -> str:
    return f"{category}|{clean_text(name)}".casefold()


def load_curation(path: Path | None) -> dict[str, Any]:
    if path is None:
        return {"include_only": {}, "exclude": set(), "aliases": {}, "records": {}}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return {
        "include_only": {
            category: {clean_text(name).casefold() for name in names}
            for category, names in payload.get("include_only", {}).items()
        },
        "exclude": {clean_text(key).casefold() for key in payload.get("exclude", [])},
        "aliases": {
            clean_text(key).casefold(): clean_text(value)
            for key, value in payload.get("aliases", {}).items()
        },
        "records": {
            clean_text(key).casefold(): value
            for key, value in payload.get("records", {}).items()
        },
    }


def included_by_curation(category: str, name: str, curation: dict[str, Any]) -> bool:
    key = record_key(category, name)
    if key in curation["exclude"]:
        return False
    include_only = curation["include_only"].get(category)
    return include_only is None or clean_text(name).casefold() in include_only


def source_record(
    category: str,
    row: dict[str, str],
    borough_shapes: dict[str, list[list[list[list[float]]]]],
    curation: dict[str, Any],
) -> dict[str, Any] | None:
    if category not in CATEGORY_INFO:
        raise ValueError(f"Unknown cultural category: {category}")
    name = clean_text(row.get("name"))
    if not name or not included_by_curation(category, name, curation):
        return None
    try:
        lat = float(row.get("latitude", ""))
        lon = float(row.get("longitude", ""))
    except (TypeError, ValueError):
        return None
    borough = next(
        (
            borough_name
            for borough_name, multipolygon in borough_shapes.items()
            if point_in_multipolygon(lon, lat, multipolygon)
        ),
        "",
    )
    if not borough:
        return None

    key = record_key(category, name)
    override = curation["records"].get(key, {})
    canonical_name = clean_text(
        override.get("title") or curation["aliases"].get(key) or name
    )
    return {
        "name": canonical_name,
        "lat": float(override.get("lat", lat)),
        "lon": float(override.get("lon", lon)),
        "address": clean_text(override.get("address")) or clean_address(row),
        "borough": clean_text(override.get("borough")) or borough,
        "website": normalise_website(override.get("website") or row.get("website")),
        "uprn": clean_text(row.get("os_addressbase_uprn")),
        "ward": clean_text(row.get("ward_2022_name")),
        "categories": [category],
        "is_accurate": bool(override.get("is_accurate", True)),
        "status_checked": clean_text(override.get("status_checked")),
    }


def squared_distance_rough_m(first: dict[str, Any], second: dict[str, Any]) -> float:
    lat_scale = 111_320
    lon_scale = 69_200
    return ((first["lat"] - second["lat"]) * lat_scale) ** 2 + (
        (first["lon"] - second["lon"]) * lon_scale
    ) ** 2


def merge_source_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = []
    for record in records:
        existing = next(
            (
                item
                for item in merged
                if item["name"].casefold() == record["name"].casefold()
                and squared_distance_rough_m(item, record) <= 100**2
            ),
            None,
        )
        if existing is None:
            merged.append(record)
            continue
        existing["categories"] = sorted(
            {*existing["categories"], *record["categories"]},
            key=CATEGORY_PRIORITY.index,
        )
        if not existing["website"]:
            existing["website"] = record["website"]
        if not existing["address"]:
            existing["address"] = record["address"]
        if not existing["uprn"]:
            existing["uprn"] = record["uprn"]
        existing["is_accurate"] = existing["is_accurate"] and record["is_accurate"]
        if not existing["status_checked"]:
            existing["status_checked"] = record["status_checked"]
    return merged


def neutral_record(record: dict[str, Any]) -> dict[str, Any]:
    categories = record["categories"]
    labels = [CATEGORY_INFO[category][0] for category in categories]
    audit_years = sorted({CATEGORY_INFO[category][2] for category in categories})
    digest = hashlib.sha256(
        f"{record['name'].casefold()}|{record['lat']:.5f}|{record['lon']:.5f}".encode()
    ).hexdigest()[:12]
    description = f"GLA Cultural Infrastructure Map categories: {'; '.join(labels)}."
    description += (
        " This is an audit snapshot, not live opening information; check current opening hours"
        " and public access before visiting."
    )
    external_id = record["uprn"]
    if not external_id or "e+" in external_id.casefold():
        external_id = digest
    attributes = {
        "category": labels[0],
        "categories": ", ".join(labels),
        "access": CATEGORY_INFO[categories[0]][1],
        "audit_year": ", ".join(audit_years),
        "ward": record["ward"],
        "venue_website": record["website"],
    }
    if record["status_checked"]:
        attributes["status_checked"] = record["status_checked"]
    return {
        "id": f"gla-culture-{digest}",
        "kind": "cultural-venue",
        "collection": "gla-cultural-infrastructure",
        "source_name": "GLA Cultural Infrastructure Map",
        "external_id": external_id,
        "title": record["name"],
        "description": description,
        "lat": record["lat"],
        "lon": record["lon"],
        "address": record["address"],
        "attributes": attributes,
        "source_url": record["website"] or DATASET_URL,
        "borough": record["borough"],
        "is_accurate": record["is_accurate"],
        "curation_status": "in_scope",
        "curation_note": "Curated for destination value; confirm that the venue still operates and welcomes visitors.",
    }


def records_from_sources(
    sources: dict[str, list[dict[str, str]]],
    boundaries: dict[str, dict[str, Any]],
    curation: dict[str, Any],
) -> list[dict[str, Any]]:
    borough_shapes = {
        borough: boundary_to_multipolygon(boundary)
        for borough, boundary in boundaries.items()
    }
    source_records = [
        record
        for category in CATEGORY_PRIORITY
        for row in sources.get(category, [])
        if (record := source_record(category, row, borough_shapes, curation)) is not None
    ]
    records = [neutral_record(record) for record in merge_source_records(source_records)]
    return sorted(
        records,
        key=lambda item: (
            item["borough"] != "Lewisham",
            item["borough"],
            item["attributes"]["category"],
            item["title"].casefold(),
        ),
    )


def parse_sources(values: list[str]) -> dict[str, Path]:
    sources: dict[str, Path] = {}
    for value in values:
        if "=" not in value:
            raise ValueError("Each source must be in CATEGORY=PATH form")
        category, path = value.split("=", 1)
        if category not in CATEGORY_INFO:
            raise ValueError(f"Unknown cultural category: {category}")
        sources[category] = Path(path)
    return sources


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate curated cultural discoveries from GLA Cultural Infrastructure CSV files."
    )
    parser.add_argument("source", nargs="+", help="GLA CSV in CATEGORY=PATH form")
    parser.add_argument(
        "--curation",
        type=Path,
        default=Path("data/corrections/gla-cultural-infrastructure.json"),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("src/lewisham_walks/data/cultural_venues.json"),
    )
    args = parser.parse_args()

    source_paths = parse_sources(args.source)
    sources: dict[str, list[dict[str, str]]] = {}
    for category, path in source_paths.items():
        with path.open(encoding="utf-8-sig", newline="") as source:
            sources[category] = list(csv.DictReader(source))
    boundaries = {
        borough: json.loads(path.read_text(encoding="utf-8"))
        for borough, path in DEFAULT_BOUNDARIES.items()
    }
    records = records_from_sources(sources, boundaries, load_curation(args.curation))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(records, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    counts = ", ".join(
        f"{borough}: {sum(record['borough'] == borough for record in records)}"
        for borough in DEFAULT_BOUNDARIES
    )
    print(f"Wrote {len(records)} cultural venues to {args.output} ({counts})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
