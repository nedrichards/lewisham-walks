import unittest

from lewisham_walks.models import Coordinate, RouteRequest
from lewisham_walks.providers.routing import OpenStreetMapRoutingProvider


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
                "legs": [{"steps": [{
                    "distance": 120,
                    "duration": 90,
                    "name": "Lewisham Way",
                    "maneuver": {"type": "turn", "modifier": "left"},
                }]}],
            }],
        }


class FakeSession:
    def __init__(self):
        self.request = None

    def get(self, endpoint, params, headers, timeout):
        self.request = endpoint, params, headers, timeout
        return FakeResponse()


class OpenStreetMapRoutingTests(unittest.TestCase):
    def test_returns_walking_geometry_and_directions(self):
        session = FakeSession()
        provider = OpenStreetMapRoutingProvider(session)
        start = Coordinate(51.46, -0.01)
        end = Coordinate(51.47, -0.02)

        geometry, steps, distance, duration = provider.route([start, end], RouteRequest(start, 60))

        self.assertEqual([start, end], geometry)
        self.assertEqual("Turn left onto Lewisham Way", steps[0].instruction)
        self.assertEqual(820.4, distance)
        self.assertEqual(610.0, duration)
        self.assertIn("routed-foot", session.request[0])
        self.assertIn("User-Agent", session.request[2])


if __name__ == "__main__":
    unittest.main()
