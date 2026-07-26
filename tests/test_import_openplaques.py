import importlib.util
import unittest
from pathlib import Path

SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "import_openplaques.py"
SPEC = importlib.util.spec_from_file_location("import_openplaques", SCRIPT_PATH)
import_openplaques = importlib.util.module_from_spec(SPEC)
if SPEC.loader is None:
    raise RuntimeError("Could not load the OpenPlaques importer")
SPEC.loader.exec_module(import_openplaques)


class ImportOpenPlaquesTests(unittest.TestCase):
    def test_filters_records_by_boundary(self):
        dump = {
            "features": [
                {
                    "type": "Feature",
                    "geometry": {"type": "Point", "coordinates": [0.5, 0.5], "is_accurate": True},
                    "properties": {"id": 1, "inscription": "Inside discovery lived here"},
                },
                {
                    "type": "Feature",
                    "geometry": {"type": "Point", "coordinates": [2.0, 2.0], "is_accurate": True},
                    "properties": {"id": 2, "inscription": "Outside discovery lived here"},
                },
            ]
        }
        boundary = {
            "type": "Feature",
            "geometry": {
                "type": "Polygon",
                "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]]],
            },
            "properties": {},
        }
        records = import_openplaques.records_from_dump(dump, boundary, {"exclude": [], "records": {}}, "Test Borough")
        self.assertEqual([record["external_id"] for record in records], ["1"])
        self.assertEqual(records[0]["kind"], "plaque")
        self.assertEqual(records[0]["source_name"], "Open Plaques")
        self.assertEqual(records[0]["borough"], "Test Borough")

    def test_applies_corrections_and_exclusions(self):
        dump = {
            "features": [
                {
                    "type": "Feature",
                    "geometry": {"type": "Point", "coordinates": [0.5, 0.5], "is_accurate": False},
                    "properties": {"id": 1, "inscription": "Original title and text"},
                },
                {
                    "type": "Feature",
                    "geometry": {"type": "Point", "coordinates": [0.6, 0.6], "is_accurate": False},
                    "properties": {"id": 2, "inscription": "Exclude me"},
                },
            ]
        }
        boundary = {
            "type": "Feature",
            "geometry": {
                "type": "Polygon",
                "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]]],
            },
            "properties": {},
        }
        corrections = {
            "exclude": ["2"],
            "records": {"1": {"title": "Corrected", "lat": 0.7, "lon": 0.7, "address": "Corrected address"}},
        }
        records = import_openplaques.records_from_dump(dump, boundary, corrections)
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["title"], "Corrected")
        self.assertEqual(records[0]["lat"], 0.7)
        self.assertEqual(records[0]["address"], "Corrected address")

    def test_merges_multiple_boundaries_without_duplicate_records(self):
        dump = {
            "features": [
                {
                    "type": "Feature",
                    "geometry": {"type": "Point", "coordinates": [0.5, 0.5], "is_accurate": True},
                    "properties": {"id": 1, "inscription": "Shared discovery"},
                },
                {
                    "type": "Feature",
                    "geometry": {"type": "Point", "coordinates": [2.5, 2.5], "is_accurate": True},
                    "properties": {"id": 2, "inscription": "Second discovery"},
                },
            ]
        }
        first = {
            "type": "Feature",
            "geometry": {"type": "Polygon", "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]]]},
            "properties": {},
        }
        second = {
            "type": "Feature",
            "geometry": {"type": "Polygon", "coordinates": [[[0, 0], [3, 0], [3, 3], [0, 3], [0, 0]]]},
            "properties": {},
        }
        records = import_openplaques.records_from_boundaries(
            dump,
            {"First": first, "Second": second},
            {"exclude": [], "records": {}},
        )
        self.assertEqual([record["external_id"] for record in records], ["1", "2"])


if __name__ == "__main__":
    unittest.main()
