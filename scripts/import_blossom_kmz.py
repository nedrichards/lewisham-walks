from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from xml.etree import ElementTree
from zipfile import ZipFile

KML_NS = {"kml": "http://www.opengis.net/kml/2.2"}
SOURCE_URL = "https://www.telegraphhillfestival.org.uk/events/a-guided-stroll-along-freddys-blossom-walk/"

STYLE_META = {
    "#icon-1886-1A237E": ("freddys-blossom-walk", "blue route tree"),
    "#icon-1886-097138": ("freddys-blossom-outlying", "green outlying tree"),
    "#icon-1729-FFEA00": ("freddys-blossom-walk", "yellow bench or landmark"),
}


def import_blossom_kmz(path: Path) -> list[dict]:
    with ZipFile(path) as archive:
        root = ElementTree.fromstring(archive.read("doc.kml"))

    records: list[dict] = []
    for route_order, placemark in enumerate(root.findall(".//kml:Placemark", KML_NS), start=1):
        coordinate = _placemark_coordinate(placemark)
        if coordinate is None:
            continue
        lon, lat = coordinate
        style_url = (placemark.findtext("kml:styleUrl", default="", namespaces=KML_NS) or "").strip()
        scheme, style_label = STYLE_META.get(style_url, ("freddys-blossom", "unknown style"))
        extended = _extended_data(placemark)
        title = _clean_text(placemark.findtext("kml:name", default="", namespaces=KML_NS) or "")
        species = extended.get("Species", "")
        location = extended.get("Location description", "")
        address = _address_from_extended(extended)
        description_parts = [part for part in (species, location) if part]
        records.append(
            {
                "id": f"freddys-blossom-{route_order:03d}",
                "kind": "blossom",
                "collection": scheme,
                "source_name": "Freddy's Blossom Walk",
                "external_id": "",
                "title": title or f"Freddy's Blossom Walk point {route_order}",
                "description": ". ".join(description_parts),
                "lat": lat,
                "lon": lon,
                "address": address,
                "attributes": {
                    "colour": "blue" if "blue" in style_label else "green" if "green" in style_label else "yellow",
                    "style": style_label,
                },
                "source_url": SOURCE_URL,
                "image_url": "",
                "borough": "Lewisham",
                "is_accurate": True,
                "curation_status": "in_scope" if scheme == "freddys-blossom-walk" else "outlying",
                "curation_note": f"Imported from Freddy's Blossom Walk KMZ; {style_label}.",
                "route_order": route_order,
            }
        )
    return records


def _placemark_coordinate(placemark) -> tuple[float, float] | None:
    text = placemark.findtext(".//kml:Point/kml:coordinates", default="", namespaces=KML_NS)
    text = " ".join((text or "").split())
    if not text:
        return None
    first = text.split()[0]
    parts = first.split(",")
    if len(parts) < 2:
        return None
    return float(parts[0]), float(parts[1])


def _extended_data(placemark) -> dict[str, str]:
    values: dict[str, str] = {}
    for data in placemark.findall(".//kml:ExtendedData/kml:Data", KML_NS):
        name = data.attrib.get("name", "")
        value = data.findtext("kml:value", default="", namespaces=KML_NS) or ""
        if name:
            values[name] = _clean_text(value)
    return values


def _address_from_extended(extended: dict[str, str]) -> str:
    number = extended.get("Number", "")
    postcode = extended.get("Postcode", "")
    return ", ".join(part for part in (number, postcode) if part)


def _clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate Freddy's Blossom Walk fixture from a KMZ export.")
    parser.add_argument("kmz", type=Path)
    parser.add_argument("--output", type=Path, default=Path("src/lewisham_walks/data/freddys_blossom_walk.json"))
    args = parser.parse_args()

    records = import_blossom_kmz(args.kmz)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(records, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    walk_points = sum(1 for record in records if record["collection"] == "freddys-blossom-walk")
    outlying = len(records) - walk_points
    print(f"Wrote {len(records)} Freddy's Blossom Walk points to {args.output} ({walk_points} route, {outlying} outlying)")


if __name__ == "__main__":
    main()
