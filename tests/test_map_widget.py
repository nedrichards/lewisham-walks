import unittest

from lewisham_walks.map_geometry import (
    coordinate_bounds,
    discoveries_for_viewport,
    find_discovery_at_position,
    project_coordinate,
    unproject_coordinate,
)
from lewisham_walks.models import Coordinate, Discovery


class MapProjectionTests(unittest.TestCase):
    def test_project_coordinate_places_bounds_correctly(self):
        bounds = coordinate_bounds([Coordinate(51.4, -0.08), Coordinate(51.5, 0.04)], padding_ratio=0)
        top_left = project_coordinate(Coordinate(51.5, -0.08), bounds, 200, 100, margin=10)
        bottom_right = project_coordinate(Coordinate(51.4, 0.04), bounds, 200, 100, margin=10)
        self.assertEqual(top_left, (10, 10))
        self.assertEqual(bottom_right, (190, 90))

    def test_empty_bounds_uses_lewisham_area(self):
        bounds = coordinate_bounds([])
        self.assertLessEqual(bounds.min_lat, 51.40)
        self.assertGreaterEqual(bounds.max_lat, 51.50)
        self.assertLessEqual(bounds.min_lon, -0.08)
        self.assertGreaterEqual(bounds.max_lon, 0.04)

    def test_unproject_coordinate_reverses_projection(self):
        bounds = coordinate_bounds([Coordinate(51.4, -0.08), Coordinate(51.5, 0.04)], padding_ratio=0)
        coordinate = Coordinate(51.46, -0.02)
        x, y = project_coordinate(coordinate, bounds, 200, 100, margin=10)
        result = unproject_coordinate(x, y, bounds, 200, 100, margin=10)

        self.assertAlmostEqual(result.lat, coordinate.lat)
        self.assertAlmostEqual(result.lon, coordinate.lon)

    def test_unproject_coordinate_clamps_to_bounds(self):
        bounds = coordinate_bounds([Coordinate(51.4, -0.08), Coordinate(51.5, 0.04)], padding_ratio=0)

        result = unproject_coordinate(-100, 500, bounds, 200, 100, margin=10)

        self.assertEqual(result, Coordinate(51.4, -0.08))

    def test_find_discovery_at_position_returns_nearest_hit(self):
        discoveries = [
            Discovery("a", "A", "", Coordinate(51.46, -0.02)),
            Discovery("b", "B", "", Coordinate(51.47, -0.01)),
        ]
        bounds = coordinate_bounds([discovery.coordinate for discovery in discoveries], padding_ratio=0)
        x, y = project_coordinate(discoveries[1].coordinate, bounds, 200, 100)

        result = find_discovery_at_position(x + 2, y + 1, bounds, 200, 100, discoveries)

        self.assertEqual(discoveries[1], result)

    def test_find_discovery_at_position_returns_none_outside_threshold(self):
        discoveries = [Discovery("a", "A", "", Coordinate(51.46, -0.02))]
        bounds = coordinate_bounds([discovery.coordinate for discovery in discoveries], padding_ratio=0)
        x, y = project_coordinate(discoveries[0].coordinate, bounds, 200, 100)

        result = find_discovery_at_position(x + 40, y + 40, bounds, 200, 100, discoveries)

        self.assertIsNone(result)

    def test_viewport_selection_changes_as_the_map_moves(self):
        west = [
            Discovery(f"west-{index}", f"West {index}", "Story", Coordinate(51.45 + index * 0.001, -0.06))
            for index in range(4)
        ]
        east = [
            Discovery(f"east-{index}", f"East {index}", "Story", Coordinate(51.45 + index * 0.001, 0.02))
            for index in range(4)
        ]

        west_visible = discoveries_for_viewport(
            [*west, *east],
            coordinate_bounds([Coordinate(51.44, -0.07), Coordinate(51.47, -0.04)], padding_ratio=0),
            Coordinate(51.455, -0.055),
        )
        east_visible = discoveries_for_viewport(
            [*west, *east],
            coordinate_bounds([Coordinate(51.44, 0.01), Coordinate(51.47, 0.03)], padding_ratio=0),
            Coordinate(51.455, 0.02),
        )

        self.assertTrue(all(item.id.startswith("west-") for item in west_visible))
        self.assertTrue(all(item.id.startswith("east-") for item in east_visible))

    def test_viewport_selection_spreads_a_fixed_marker_budget(self):
        discoveries = [
            Discovery(
                f"point-{column}-{row}",
                f"Point {column} {row}",
                "Story",
                Coordinate(51.40 + row * 0.01, -0.08 + column * 0.015),
                is_accurate=True,
            )
            for column in range(8)
            for row in range(6)
        ]
        bounds = coordinate_bounds([item.coordinate for item in discoveries], padding_ratio=0)

        selected = discoveries_for_viewport(discoveries, bounds, Coordinate(51.425, -0.025), limit=12)

        self.assertEqual(12, len(selected))
        self.assertGreaterEqual(len({round(item.coordinate.lon, 2) for item in selected}), 4)
        self.assertGreaterEqual(len({round(item.coordinate.lat, 2) for item in selected}), 3)


if __name__ == "__main__":
    unittest.main()
