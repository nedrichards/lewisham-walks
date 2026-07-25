import unittest

from lewisham_walks.export import plan_to_gpx
from lewisham_walks.models import (
    AmenityStop,
    Coordinate,
    Discovery,
    DiscoveryKind,
    RouteMode,
    RouteRequest,
    StopPreference,
)
from lewisham_walks.planner import MAX_BLOSSOM_ROUTE_POINTS, RoutePlanner


class FakeAmenityProvider:
    def search(self, centre, kind, radius_m=900):
        return [AmenityStop("osm/1", f"Test {kind.title()}", kind, Coordinate(centre.lat + 0.001, centre.lon))]


class BrokenAmenityProvider:
    def search(self, centre, kind, radius_m=900):
        raise RuntimeError("Overpass returned 504")


class RecordingRoutingProvider:
    def __init__(self):
        self.last_waypoints = None

    def route(self, waypoints, request):
        self.last_waypoints = list(waypoints)
        return waypoints, [], 0.0, 0.0


class PlannerTests(unittest.TestCase):
    def setUp(self):
        self.discoveries = [
            Discovery("a", "A", "", Coordinate(51.46, -0.01)),
            Discovery("b", "B", "", Coordinate(51.461, -0.012)),
            Discovery("c", "C", "", Coordinate(51.462, -0.014)),
        ]

    def test_builds_circular_walk_with_discoveries(self):
        planner = RoutePlanner(self.discoveries)
        plan = planner.plan(RouteRequest(Coordinate(51.459, -0.011), 60))
        self.assertGreaterEqual(len(plan.discoveries), 1)
        self.assertEqual(plan.waypoints[0], plan.waypoints[-1])
        self.assertEqual(plan.visits[-1].kind, "end")
        self.assertEqual([visit.title for visit in plan.visits[:-1]], [discovery.title for discovery in plan.discoveries])
        self.assertGreater(plan.distance_m, 0)

    def test_new_walks_prefer_unseen_stories(self):
        planner = RoutePlanner(self.discoveries)
        plan = planner.plan(RouteRequest(Coordinate(51.459, -0.011), 60, max_discoveries=2, seen_story_ids=("a", "b")))

        self.assertEqual(["c"], [discovery.id for discovery in plan.discoveries])

    def test_walk_does_not_repeat_colocated_records(self):
        duplicate = Discovery("a-copy", "A copy", "", Coordinate(51.46001, -0.01001))
        planner = RoutePlanner([self.discoveries[0], duplicate])

        plan = planner.plan(RouteRequest(Coordinate(51.459, -0.011), 60, max_discoveries=2))

        self.assertEqual(1, len(plan.discoveries))

    def test_adds_end_amenity(self):
        planner = RoutePlanner(self.discoveries, amenity_provider=FakeAmenityProvider())
        plan = planner.plan(RouteRequest(Coordinate(51.459, -0.011), 60, StopPreference.PUB_END))
        self.assertEqual(plan.amenities[0].kind, "pub")
        self.assertEqual(plan.waypoints[-1], plan.amenities[0].coordinate)
        self.assertEqual(plan.visits[-1].kind, "pub")

    def test_uses_explicit_end_point(self):
        end = Coordinate(51.455, -0.005)
        planner = RoutePlanner(self.discoveries)
        plan = planner.plan(RouteRequest(Coordinate(51.459, -0.011), 60, end=end))
        self.assertEqual(plan.waypoints[-1], end)
        self.assertEqual(plan.visits[-1].title, "End point")

    def test_places_along_amenity_in_itinerary(self):
        planner = RoutePlanner(self.discoveries, amenity_provider=FakeAmenityProvider())
        plan = planner.plan(RouteRequest(Coordinate(51.459, -0.011), 60, StopPreference.CAFE_ALONG))
        self.assertIn("cafe", [visit.kind for visit in plan.visits])
        self.assertEqual(plan.visits[-1].kind, "end")

    def test_amenity_lookup_failure_keeps_route(self):
        planner = RoutePlanner(self.discoveries, amenity_provider=BrokenAmenityProvider())
        plan = planner.plan(RouteRequest(Coordinate(51.459, -0.011), 60, StopPreference.CAFE_ALONG))
        self.assertEqual(plan.amenities, [])
        self.assertGreaterEqual(len(plan.discoveries), 1)
        self.assertTrue(any("Could not find a nearby cafe" in warning for warning in plan.warnings))

    def test_blossom_walk_starts_at_closest_ordered_point_and_continues(self):
        points = [
            Discovery("tree-1", "Tree 1", "", Coordinate(51.450, -0.010), kind=DiscoveryKind.BLOSSOM, collection="freddys-blossom-walk", route_order=1),
            Discovery("tree-2", "Tree 2", "", Coordinate(51.451, -0.011), kind=DiscoveryKind.BLOSSOM, collection="freddys-blossom-walk", route_order=2),
            Discovery("tree-3", "Tree 3", "", Coordinate(51.452, -0.012), kind=DiscoveryKind.BLOSSOM, collection="freddys-blossom-walk", route_order=3),
        ]
        planner = RoutePlanner(points)

        plan = planner.plan(
            RouteRequest(
                Coordinate(51.4511, -0.011),
                60,
                max_discoveries=3,
                discovery_dwell_minutes=3,
                route_mode=RouteMode.BLOSSOM_WALK,
            )
        )

        self.assertEqual(["Tree 2", "Tree 3", "Tree 1"], [point.title for point in plan.discoveries])
        self.assertEqual(0, plan.dwell_seconds)
        self.assertEqual(plan.walking_seconds, plan.total_seconds)
        self.assertEqual("blossom", plan.visits[0].kind)
        self.assertEqual("Continue from Freddy's Blossom Walk", plan.visits[-1].title)
        self.assertNotEqual(plan.waypoints[0], plan.waypoints[-1])

    def test_mixed_walk_does_not_add_dwell_for_blossom_points(self):
        points = [
            Discovery("discovery-1", "Discovery 1", "", Coordinate(51.450, -0.010)),
            Discovery("tree-1", "Tree 1", "", Coordinate(51.451, -0.011), kind=DiscoveryKind.BLOSSOM, collection="freddys-blossom-walk", route_order=1),
        ]
        planner = RoutePlanner(points)

        plan = planner.plan(RouteRequest(Coordinate(51.449, -0.010), 60, max_discoveries=2, route_mode=RouteMode.MIXED))

        self.assertEqual(180, plan.dwell_seconds)

    def test_blossom_walk_caps_waypoints_for_routing_with_end_stop(self):
        points = [
            Discovery(
                f"tree-{index}",
                f"Tree {index}",
                "",
                Coordinate(51.45 + index * 0.0001, -0.01 - index * 0.0001),
                kind=DiscoveryKind.BLOSSOM,
                collection="freddys-blossom-walk",
                route_order=index,
            )
            for index in range(1, 80)
        ]
        routing = RecordingRoutingProvider()
        planner = RoutePlanner(points, routing_provider=routing, amenity_provider=FakeAmenityProvider())

        plan = planner.plan(
            RouteRequest(
                Coordinate(51.4511, -0.011),
                120,
                stop_preference=StopPreference.CAFE_END,
                max_discoveries=80,
                route_mode=RouteMode.BLOSSOM_WALK,
            )
        )

        self.assertEqual(MAX_BLOSSOM_ROUTE_POINTS, len(plan.discoveries))
        self.assertEqual(MAX_BLOSSOM_ROUTE_POINTS + 2, len(routing.last_waypoints))

    def test_exports_gpx(self):
        planner = RoutePlanner(self.discoveries)
        plan = planner.plan(RouteRequest(Coordinate(51.459, -0.011), 60))
        gpx = plan_to_gpx(plan)
        self.assertIn("<gpx", gpx)
        self.assertIn("<trkpt", gpx)

    def test_a_nearby_border_discovery_can_beat_a_farther_lewisham_one(self):
        start = Coordinate(51.4900, -0.0350)
        greenwich = Discovery(
            "greenwich", "Across the borough line", "A nearby story", Coordinate(51.4901, -0.0350),
            borough="Greenwich", is_accurate=True,
        )
        lewisham = Discovery(
            "lewisham", "Further into Lewisham", "A local story", Coordinate(51.4800, -0.0250),
            borough="Lewisham", is_accurate=True, curation_status="in_scope",
        )

        plan = RoutePlanner([lewisham, greenwich]).plan(RouteRequest(start, 30, max_discoveries=1))

        self.assertEqual(["greenwich"], [item.id for item in plan.discoveries])


if __name__ == "__main__":
    unittest.main()
