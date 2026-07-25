#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

import import_maroon_docx
import import_openplaques


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the bundled plaque fixture.")
    parser.add_argument("openplaques_dump", type=Path)
    parser.add_argument(
        "--maroon-docx",
        type=Path,
        default=Path("Maroon Plaque Location and Text List 2025.docx"),
    )
    parser.add_argument("--output", type=Path, default=Path("src/lewisham_walks/data/plaques.json"))
    args = parser.parse_args()

    dump = json.loads(args.openplaques_dump.read_text(encoding="utf-8"))
    boundaries = {
        borough: json.loads(path.read_text(encoding="utf-8"))
        for borough, path in import_openplaques.DEFAULT_BOUNDARIES.items()
    }
    corrections = import_openplaques.load_corrections(Path("data/corrections/openplaques-lewisham.json"))
    openplaques_records = import_openplaques.records_from_boundaries(dump, boundaries, corrections)
    maroon_records = import_maroon_docx.records_from_docx(args.maroon_docx, dump)

    maroon_openplaques_ids = {record["external_id"] for record in maroon_records if record.get("external_id")}
    records = [
        record
        for record in openplaques_records
        if record.get("external_id") not in maroon_openplaques_ids
    ]
    records.extend(maroon_records)
    records.sort(key=lambda item: (item.get("borough", ""), item.get("collection", ""), item["title"].lower()))

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(records, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(
        f"Wrote {len(records)} plaques to {args.output} "
        f"({len(openplaques_records)} OpenPlaques candidates, {len(maroon_records)} Lewisham maroon)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
