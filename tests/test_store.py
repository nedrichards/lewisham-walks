import json
import unittest
from importlib import resources

from lewisham_walks.models import DiscoveryKind
from lewisham_walks.store import (
    discoveries_from_openplaques_geojson,
    load_seed_blossom_discoveries,
    load_seed_discoveries,
    load_seed_listed_buildings,
)


class StoreTests(unittest.TestCase):
    def test_bundled_files_use_the_neutral_schema(self):
        for filename in ("plaques.json", "freddys_blossom_walk.json", "listed_buildings.json"):
            path = resources.files("lewisham_walks") / "data" / filename
            records = json.loads(path.read_text(encoding="utf-8"))
            self.assertTrue(records)
            self.assertTrue(all({"kind", "collection", "source_name", "external_id", "attributes"} <= record.keys() for record in records))
            self.assertTrue(all("scheme" not in record and "openplaques_id" not in record for record in records))

    def test_bundled_fixture_contains_real_openplaques_records(self):
        discoveries = load_seed_discoveries()
        self.assertGreaterEqual(len(discoveries), 300)
        self.assertTrue(any(discovery.id.startswith("openplaques-") for discovery in discoveries))
        self.assertTrue(any(discovery.source_url.startswith("https://openplaques.org/plaques/") for discovery in discoveries))
        self.assertTrue(any(discovery.external_id for discovery in discoveries))
        self.assertTrue(all(discovery.kind is DiscoveryKind.PLAQUE for discovery in discoveries))
        self.assertTrue(all(discovery.curation_status for discovery in discoveries))

    def test_fixture_includes_curated_statuses(self):
        discoveries = load_seed_discoveries()
        statuses = {discovery.curation_status for discovery in discoveries}
        collections = {discovery.collection for discovery in discoveries}
        boroughs = {discovery.borough for discovery in discoveries}
        self.assertIn("candidate", statuses)
        self.assertIn("in_scope", statuses)
        self.assertIn("openplaques", collections)
        self.assertIn("lewisham-maroon", collections)
        self.assertEqual({"Greenwich", "Lewisham", "Southwark"}, boroughs)
        self.assertEqual(29, sum(1 for discovery in discoveries if discovery.collection == "lewisham-maroon"))

    def test_bundled_blossom_fixture_keeps_route_order_and_outlying_points(self):
        points = load_seed_blossom_discoveries()
        collections = {point.collection for point in points}

        self.assertEqual(156, len(points))
        self.assertIn("freddys-blossom-walk", collections)
        self.assertIn("freddys-blossom-outlying", collections)
        self.assertTrue(all(point.kind is DiscoveryKind.BLOSSOM for point in points))
        self.assertEqual(1, points[0].route_order)
        self.assertTrue(points[0].title.startswith("Fred's Bench"))
        self.assertEqual(12, sum(1 for point in points if point.collection == "freddys-blossom-outlying"))

    def test_bundled_listed_buildings_are_high_grade_and_in_the_supported_boroughs(self):
        buildings = load_seed_listed_buildings()

        self.assertEqual(139, len(buildings))
        self.assertEqual({"I", "II*"}, {building.attributes["grade"] for building in buildings})
        self.assertEqual({"Greenwich", "Lewisham", "Southwark"}, {building.borough for building in buildings})
        self.assertTrue(all(building.kind is DiscoveryKind.LISTED_BUILDING for building in buildings))
        self.assertTrue(all(building.source_name == "Historic England" for building in buildings))
        self.assertTrue(all(building.source_url.startswith("https://historicengland.org.uk/listing/") for building in buildings))

    def test_imports_lewisham_brown_geojson_feature(self):
        payload = {
            "features": [
                {
                    "geometry": {"coordinates": [-0.01, 51.46]},
                    "properties": {
                        "id": 42,
                        "title": "Test Discovery",
                        "inscription": "Lewisham brown plaque",
                        "colour": "Brown",
                        "address": "Lewisham",
                    },
                }
            ]
        }
        discoveries = discoveries_from_openplaques_geojson(payload)
        self.assertEqual(len(discoveries), 1)
        self.assertEqual(discoveries[0].coordinate.lat, 51.46)


if __name__ == "__main__":
    unittest.main()
