import unittest
from dataclasses import FrozenInstanceError, asdict, replace

from lewisham_walks.map_geometry import MapBounds
from lewisham_walks.models import (
    AmenityStop,
    Coordinate,
    Discovery,
    DiscoveryKind,
    RouteMode,
    RouteRequest,
    RouteTheme,
    StopPreference,
)


class ModelTests(unittest.TestCase):
    def test_slotted_models_preserve_value_semantics_and_serialization(self):
        coordinate = Coordinate(51.46, -0.01)
        discovery = Discovery("story", "Story", "Description", coordinate, attributes={"key": "value"})
        for value in (coordinate, discovery, RouteRequest(coordinate, 60), MapBounds(51.4, 51.5, -0.1, 0.1)):
            with self.subTest(model=type(value).__name__):
                self.assertNotHasAttr(value, "__dict__")
                self.assertEqual(replace(value), value)
        self.assertEqual(asdict(discovery)["coordinate"], {"lat": 51.46, "lon": -0.01})
        self.assertEqual(replace(discovery, title="Changed").title, "Changed")
        self.assertEqual(discovery.title, "Story")
        with self.assertRaises(FrozenInstanceError):
            coordinate.lat = 0

    def test_metadata_defaults_remain_independent(self):
        coordinate = Coordinate(51.46, -0.01)
        first = Discovery("one", "One", "", coordinate)
        second = Discovery("two", "Two", "", coordinate)
        first.attributes["source"] = "example"
        self.assertEqual(second.attributes, {})
        cafe = AmenityStop("cafe", "Cafe", "cafe", coordinate)
        pub = AmenityStop("pub", "Pub", "pub", coordinate)
        cafe.tags["name"] = "Cafe"
        self.assertEqual(pub.tags, {})

    def test_string_enums_preserve_persisted_values(self):
        for enum_type in (DiscoveryKind, StopPreference, RouteMode, RouteTheme):
            for member in enum_type:
                with self.subTest(member=member):
                    self.assertEqual(str(member), member.value)
                    self.assertEqual(f"{member}", member.value)
                    self.assertIs(enum_type(member.value), member)
                    self.assertEqual(member, member.value)


if __name__ == "__main__":
    unittest.main()
