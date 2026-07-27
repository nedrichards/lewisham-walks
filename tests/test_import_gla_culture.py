import importlib.util
import unittest
from pathlib import Path

SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "import_gla_culture.py"
SPEC = importlib.util.spec_from_file_location("import_gla_culture", SCRIPT_PATH)
import_gla_culture = importlib.util.module_from_spec(SPEC)
if SPEC.loader is None:
    raise RuntimeError("Could not load the GLA cultural importer")
SPEC.loader.exec_module(import_gla_culture)


class ImportGlaCultureTests(unittest.TestCase):
    def setUp(self):
        self.boundary = {
            "type": "Feature",
            "geometry": {
                "type": "Polygon",
                "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]]],
            },
            "properties": {},
        }
        self.curation = {
            "include_only": {},
            "exclude": set(),
            "aliases": {},
            "records": {},
        }

    def test_filters_to_exact_boundaries_not_claimed_borough(self):
        sources = {
            "museums": [
                self._row("Inside museum", 0.5, 0.5, borough="Wrong Borough"),
                self._row("Outside museum", 2.0, 2.0, borough="Test Borough"),
            ]
        }

        records = import_gla_culture.records_from_sources(
            sources,
            {"Test Borough": self.boundary},
            self.curation,
        )

        self.assertEqual(["Inside museum"], [record["title"] for record in records])
        self.assertEqual("Test Borough", records[0]["borough"])
        self.assertEqual("cultural-venue", records[0]["kind"])

    def test_applies_allowlists_exclusions_and_aliases(self):
        curation = {
            "include_only": {"archives": {"keep archive"}},
            "exclude": {"cinemas|closed cinema"},
            "aliases": {"museums|old name": "Current Museum"},
            "records": {},
        }
        sources = {
            "archives": [self._row("Keep Archive", 0.2, 0.2), self._row("Office Archive", 0.3, 0.3)],
            "cinemas": [self._row("Closed Cinema", 0.4, 0.4)],
            "museums": [self._row("Old Name", 0.5, 0.5)],
        }

        records = import_gla_culture.records_from_sources(
            sources,
            {"Test Borough": self.boundary},
            curation,
        )

        self.assertEqual(["Keep Archive", "Current Museum"], [record["title"] for record in records])

    def test_merges_the_same_place_across_categories(self):
        curation = dict(self.curation)
        curation["aliases"] = {"arts-centres|venue arts": "One Venue"}
        sources = {
            "arts-centres": [self._row("Venue Arts", 0.5, 0.5, website="venue.example")],
            "theatres": [self._row("One Venue", 0.5001, 0.5001)],
        }

        records = import_gla_culture.records_from_sources(
            sources,
            {"Test Borough": self.boundary},
            curation,
        )

        self.assertEqual(1, len(records))
        self.assertEqual("Arts centre, Theatre", records[0]["attributes"]["categories"])
        self.assertEqual("https://venue.example", records[0]["source_url"])
        self.assertIn("check current opening hours", records[0]["description"])
        self.assertEqual("in_scope", records[0]["curation_status"])

    def test_curation_can_correct_a_stale_location_and_record_check(self):
        curation = dict(self.curation)
        curation["records"] = {
            "archives|old archive": {
                "title": "Current Archive",
                "address": "New address",
                "lat": 0.6,
                "lon": 0.7,
                "is_accurate": False,
                "status_checked": "Official page checked July 2026",
            }
        }

        records = import_gla_culture.records_from_sources(
            {"archives": [self._row("Old Archive", 0.2, 0.2)]},
            {"Test Borough": self.boundary},
            curation,
        )

        self.assertEqual("Current Archive", records[0]["title"])
        self.assertEqual("New address", records[0]["address"])
        self.assertEqual(0.6, records[0]["lat"])
        self.assertFalse(records[0]["is_accurate"])
        self.assertEqual(
            "Official page checked July 2026",
            records[0]["attributes"]["status_checked"],
        )

    @staticmethod
    def _row(name, lat, lon, borough="Test Borough", website=""):
        return {
            "name": name,
            "address1": "1 Test Street",
            "address2": "",
            "address3": "SE1 1AA",
            "borough_name": borough,
            "website": website,
            "os_addressbase_uprn": "1234",
            "ward_2022_name": "Test Ward",
            "latitude": str(lat),
            "longitude": str(lon),
        }


if __name__ == "__main__":
    unittest.main()
