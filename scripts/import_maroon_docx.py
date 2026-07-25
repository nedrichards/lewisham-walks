#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any
from xml.etree import ElementTree
from zipfile import ZipFile

OPENPLAQUES_MATCHES = {
    1: "10273",
    2: "4382",
    3: "4390",
    4: "4378",
    5: "4374",
    6: "4398",
    7: "9705",
    8: "4400",
    9: "4384",
    10: "4376",
    11: "4386",
    12: "4388",
    13: "4394",
    14: "4392",
    15: "10365",
    16: "55979",
    18: "4396",
    19: "4380",
    20: "8919",
    21: "4404",
    22: "11751",
    23: "50771",
    24: "55981",
    25: "55989",
    26: "43711",
    27: "59745",
    28: "55980",
}

FALLBACK_COORDINATES = {
    17: {"lat": 51.444622, "lon": -0.021058, "note": "Approximate coordinate from postcode SE6 9SE."},
    29: {"lat": 51.478106, "lon": -0.036775, "note": "Approximate coordinate from postcode SE14 6LU."},
}

WORD_NS = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
SOURCE_DOCUMENT_URL = "https://www.whatdotheyknow.com/request/maroon_plaque_locations"


def normalise_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def slugify(value: str) -> str:
    value = value.encode("ascii", "ignore").decode("ascii").lower()
    value = re.sub(r"[^a-z0-9]+", "-", value).strip("-")
    return value or "plaque"


def extract_docx_chunks(path: Path) -> list[str]:
    with ZipFile(path) as archive:
        root = ElementTree.fromstring(archive.read("word/document.xml"))

    chunks: list[str] = []
    for paragraph in root.findall(".//w:p", WORD_NS):
        parts: list[str] = []
        for node in paragraph.iter():
            tag = node.tag.rsplit("}", 1)[-1]
            if tag == "t":
                parts.append(node.text or "")
            elif tag in ("br", "cr"):
                parts.append("\n")
        text = "".join(parts).strip()
        if text and not text.startswith("Lewisham Maroon"):
            chunks.extend(chunk.strip() for chunk in re.split(r"\n\s*\n+", text) if chunk.strip())
    return chunks


def records_from_docx(path: Path, openplaques_dump: dict[str, Any]) -> list[dict[str, Any]]:
    features_by_id = {
        str(feature.get("properties", {}).get("id", "")): feature for feature in openplaques_dump.get("features", [])
    }
    records: list[dict[str, Any]] = []
    for index, chunk in enumerate(extract_docx_chunks(path), start=1):
        lines = [line.strip() for line in chunk.splitlines() if line.strip()]
        if len(lines) < 2:
            continue

        title = normalise_text(lines[0])
        address = normalise_text(lines[1])
        description = normalise_text(" ".join(lines[2:]))
        plaque_id = OPENPLAQUES_MATCHES.get(index, "")
        fallback = FALLBACK_COORDINATES.get(index, {})
        feature = features_by_id.get(plaque_id, {})
        coordinates = feature.get("geometry", {}).get("coordinates", [])

        if coordinates:
            lon = float(coordinates[0])
            lat = float(coordinates[1])
            is_accurate = bool(feature.get("geometry", {}).get("is_accurate", False))
            source_url = f"https://openplaques.org/plaques/{plaque_id}"
            note = "Imported from Lewisham Maroon Plaque Location and Text List 2025; matched to OpenPlaques point."
        elif fallback:
            lon = float(fallback["lon"])
            lat = float(fallback["lat"])
            is_accurate = False
            source_url = ""
            note = f"Imported from Lewisham Maroon Plaque Location and Text List 2025. {fallback['note']}"
        else:
            continue

        records.append(
            {
                "id": f"lewisham-maroon-{slugify(title)}",
                "kind": "plaque",
                "collection": "lewisham-maroon",
                "source_name": "Lewisham Council and Open Plaques" if plaque_id else "Lewisham Council",
                "external_id": plaque_id,
                "title": title,
                "description": description,
                "lat": lat,
                "lon": lon,
                "address": address,
                "attributes": {
                    "colour": "maroon",
                    "source_document": path.name,
                    "source_document_url": SOURCE_DOCUMENT_URL,
                },
                "borough": "Lewisham",
                "source_url": source_url,
                "is_accurate": is_accurate,
                "curation_status": "in_scope",
                "curation_note": note,
            }
        )
    return records


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate Lewisham maroon plaque records from the 2025 DOCX.")
    parser.add_argument("docx", type=Path)
    parser.add_argument("--openplaques-dump", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=Path("src/lewisham_walks/data/lewisham_maroon_plaques.json"))
    args = parser.parse_args()

    dump = json.loads(args.openplaques_dump.read_text(encoding="utf-8"))
    records = records_from_docx(args.docx, dump)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(records, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Wrote {len(records)} Lewisham maroon plaques to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
