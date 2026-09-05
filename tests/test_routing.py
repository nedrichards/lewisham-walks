import unittest
from unittest import mock

import requests

from lewisham_walks.models import AmenityStop, Coordinate, RouteRequest, StopPreference
from lewisham_walks.planner import RoutePlanner
from lewisham_walks.providers.routing import LocalFallbackRoutingProvider, OpenStreetMapRoutingProvider, RoutingError


class FakeResponse:
    def raise_for_status(self):
        return None

    def json(self):
        return {
            "code": "Ok",
            "routes": [{
                "distance": 820.4,
                "duration": 610.0,
                "geometry": {"coordinates": [[-0.01, 51.46], [-0.02, 51.47]]},
                "legs": [
                    {"steps": [{
                        "distance": 120,
                        "duration": 90,
                        "name": "Lewisham Way",
                        "maneuver": {"type": "turn", "modifier": "left"},
                    }]},
                    {"steps": [{
                        "distance": 80,
                        "duration": 60,
                        "name": "Ladywell Road",
                        "maneuver": {"type": "continue", "modifier": "straight"},
                    }]},
                ],
            }],
        }


class FakeSession:
    def __init__(self):
        self.request = None

    def get(self, endpoint, params, headers, timeout):
        self.request = endpoint, params, headers, timeout
        return FakeResponse()


class OpenStreetMapRoutingTests(unittest.TestCase):
    def test_connection_failure_uses_local_itinerary_without_repeating_amenities(self):
        session = mock.Mock()
        session.get.side_effect = requests.ConnectionError("offline")
        routing = LocalFallbackRoutingProvider(OpenStreetMapRoutingProvider(session))
        start = Coordinate(51.46, -0.01)
        cafe = AmenityStop("cafe", "Cafe", "cafe", Coordinate(51.461, -0.01))
        amenities = mock.Mock()
        amenities.search.return_value = [cafe]
        with mock.patch("lewisham_walks.providers.routing.time.sleep"):
            plan = RoutePlanner([], routing, amenities).plan(
                RouteRequest(start, 60, stop_preference=StopPreference.CAFE_END)
            )
        self.assertTrue(routing.used_fallback)
        self.assertEqual([start, cafe.coordinate], plan.geometry)
        self.assertEqual([cafe], plan.amenities)
        amenities.search.assert_called_once()
        session.get.assert_called_once()

    def test_malformed_success_responses_raise_routing_error(self):
        payloads = [None, [], {"code": "Ok", "routes": [{}]}]
        for coordinates in ([], [[0, float("nan")], [0, 51]], [[0, 91], [0, 51]]):
            payload = FakeResponse().json()
            payload["routes"][0]["geometry"]["coordinates"] = coordinates
            payloads.append(payload)
        invalid_step = FakeResponse().json()
        invalid_step["routes"][0]["legs"][0]["steps"][0]["duration"] = float("nan")
        payloads.append(invalid_step)
        for payload in payloads:
            with self.subTest(payload=payload), mock.patch("lewisham_walks.providers.routing.time.sleep"):
                session = mock.Mock()
                session.get.return_value.json.return_value = payload
                with self.assertRaises(RoutingError):
                    OpenStreetMapRoutingProvider(session).route(
                        [Coordinate(51, 0), Coordinate(52, 0)], RouteRequest(Coordinate(51, 0), 60)
                    )

    def test_returns_walking_geometry_and_directions(self):
        session = FakeSession()
        provider = OpenStreetMapRoutingProvider(session)
        start = Coordinate(51.46, -0.01)
        end = Coordinate(51.47, -0.02)

        geometry, steps, distance, duration = provider.route([start, end], RouteRequest(start, 60))

        self.assertEqual([start, end], geometry)
        self.assertEqual("Turn left onto Lewisham Way", steps[0].instruction)
        self.assertEqual([0, 1], [step.leg_index for step in steps])
        self.assertEqual(820.4, distance)
        self.assertEqual(610.0, duration)
        self.assertIn("routed-foot", session.request[0])
        self.assertIn("User-Agent", session.request[2])

    def test_rate_limit_is_shared_between_provider_instances(self):
        start = Coordinate(51.46, -0.01)
        end = Coordinate(51.47, -0.02)
        request = RouteRequest(start, 60)
        previous_request_started = OpenStreetMapRoutingProvider._last_request_started
        OpenStreetMapRoutingProvider._last_request_started = 0.0
        self.addCleanup(setattr, OpenStreetMapRoutingProvider, "_last_request_started", previous_request_started)

        with (
            mock.patch(
                "lewisham_walks.providers.routing.time.monotonic",
                side_effect=[100.0, 100.0, 100.25, 101.0],
            ),
            mock.patch("lewisham_walks.providers.routing.time.sleep") as sleep,
        ):
            OpenStreetMapRoutingProvider(FakeSession()).route([start, end], request)
            OpenStreetMapRoutingProvider(FakeSession()).route([start, end], request)

        sleep.assert_called_once_with(0.75)


if __name__ == "__main__":
    unittest.main()
