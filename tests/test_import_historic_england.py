import importlib.util
import unittest
from pathlib import Path

SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "import_historic_england.py"
SPEC = importlib.util.spec_from_file_location("import_historic_england", SCRIPT_PATH)
import_historic_england = importlib.util.module_from_spec(SPEC)
if SPEC.loader is None:
    raise RuntimeError("Could not load the Historic England importer")
SPEC.loader.exec_module(import_historic_england)


class ImportHistoricEnglandTests(unittest.TestCase):
    def setUp(self):
        self.boundary = {
            "type": "Feature",
            "geometry": {
                "type": "Polygon",
                "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]]],
            },
            "properties": {},
        }

    def test_keeps_only_high_grade_records_inside_the_boundary(self):
        dump = {
            "features": [
                self._feature(100, "Exceptional church", "I", [0.5, 0.5]),
                self._feature(200, "Important hall", "II*", [0.6, 0.6]),
                self._feature(300, "Grade two house", "II", [0.7, 0.7]),
                self._feature(400, "Outside church", "I", [2.0, 2.0]),
            ]
        }

        records = import_historic_england.records_from_boundaries(
            dump,
            {"Test Borough": self.boundary},
        )

        self.assertEqual(["100", "200"], [record["external_id"] for record in records])
        self.assertTrue(all(record["kind"] == "listed-building" for record in records))
        self.assertTrue(all(record["borough"] == "Test Borough" for record in records))

    def test_maps_official_provenance_dates_and_grade_to_neutral_fields(self):
        feature = self._feature(1234567, "  CHURCH  OF ST TEST  ", "II*", [0.5, 0.5])
        feature["properties"].update(
            {
                "ListDate": 0,
                "AmendDate": 86_400_000,
                "NGR": "TQ 123 456",
                "hyperlink": "https://historicengland.org.uk/listing/the-list/list-entry/1234567",
            }
        )

        record = import_historic_england.record_from_feature(feature, "Lewisham")

        self.assertEqual("CHURCH OF ST TEST", record["title"])
        self.assertEqual("1970-01-01", record["attributes"]["listed_on"])
        self.assertEqual("1970-01-02", record["attributes"]["amended_on"])
        self.assertEqual("II*", record["attributes"]["grade"])
        self.assertIn("First listed 1 January 1970", record["description"])
        self.assertEqual("Historic England", record["source_name"])
        self.assertTrue(record["is_accurate"])

    @staticmethod
    def _feature(list_entry, name, grade, coordinates):
        return {
            "type": "Feature",
            "geometry": {"type": "MultiPoint", "coordinates": [coordinates]},
            "properties": {
                "ListEntry": list_entry,
                "Name": name,
                "Grade": grade,
                "ListDate": None,
                "AmendDate": None,
                "NGR": "",
                "hyperlink": "",
            },
        }


if __name__ == "__main__":
    unittest.main()
