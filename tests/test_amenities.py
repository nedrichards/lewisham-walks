import unittest
from unittest import mock

from lewisham_walks.models import Coordinate
from lewisham_walks.providers.amenities import OverpassAmenityProvider


class FakeResponse:
    status_code = 200

    def __init__(self, payload):
        self._payload = payload

    def json(self):
        return self._payload

    def raise_for_status(self):
        return None


class FakeSession:
    def __init__(self, payload, get_payload=None):
        self.payload = payload
        self.get_payload = get_payload or []
        self.requests = []
        self.get_requests = []

    def post(self, endpoint, data, timeout, headers):
        self.requests.append((endpoint, data["data"], timeout, headers))
        return FakeResponse(self.payload)

    def get(self, endpoint, params, headers, timeout):
        self.get_requests.append((endpoint, params, headers, timeout))
        return FakeResponse(self.get_payload)


class OverpassAmenityProviderTests(unittest.TestCase):
    def setUp(self):
        patcher = mock.patch("lewisham_walks.providers.amenities.time.sleep")
        self.sleep = patcher.start()
        self.addCleanup(patcher.stop)

    def test_search_uses_global_overpass_with_application_identity(self):
        session = FakeSession({"elements": []})
        OverpassAmenityProvider(session).search(Coordinate(51.45, -0.02), "cafe")
        self.assertEqual("https://overpass-api.de/api/interpreter", session.requests[0][0])
        self.assertIn("LewishamWalks", session.requests[0][3]["User-Agent"])

    def test_zero_longitude_is_a_valid_node_coordinate(self):
        session = FakeSession({"elements": [{"id": 1, "lat": 51.45, "lon": 0, "tags": {}}]})
        result = OverpassAmenityProvider(session).search(Coordinate(51.45, 0), "cafe")
        self.assertEqual(Coordinate(51.45, 0), result[0].coordinate)
        self.assertEqual([], session.get_requests)

    def test_nominatim_requests_are_spaced_between_provider_instances(self):
        previous = OverpassAmenityProvider._last_request_started
        self.addCleanup(setattr, OverpassAmenityProvider, "_last_request_started", previous)
        OverpassAmenityProvider._last_request_started = 0
        payload = [{"osm_type": "node", "osm_id": 1, "lat": "51.45", "lon": "0", "type": "cafe"}]
        with mock.patch("lewisham_walks.providers.amenities.time.monotonic", side_effect=[100, 100, 100.25, 101]):
            for _ in range(2):
                OverpassAmenityProvider(FakeSession({}, payload)).search(Coordinate(51.45, 0), "cafe")
        self.sleep.assert_called_once_with(0.75)

    def test_query_includes_nodes_ways_and_relations(self):
        session = FakeSession(
            {
                "elements": [
                    {
                        "type": "node",
                        "id": 1,
                        "lat": 51.45,
                        "lon": -0.02,
                        "tags": {"name": "Test Cafe"},
                    }
                ]
            }
        )
        provider = OverpassAmenityProvider(session=session)

        provider.search(Coordinate(51.45, -0.02), "cafe", radius_m=1200)

        query = session.requests[0][1]
        self.assertIn('node["amenity"="cafe"]', query)
        self.assertIn('way["amenity"="cafe"]', query)
        self.assertIn('relation["amenity"="cafe"]', query)
        self.assertIn("out tags center 40", query)
        self.assertIn("around:1200", query)

    def test_query_is_coordinate_based_at_a_borough_border(self):
        session = FakeSession({"elements": []})
        provider = OverpassAmenityProvider(session=session)

        provider.search(Coordinate(51.4812, -0.0058), "pub", radius_m=900)

        query = session.requests[0][1]
        self.assertIn("around:900,51.4812,-0.0058", query)
        self.assertNotIn("Lewisham", query)

    def test_parses_way_centres_and_sorts_by_distance(self):
        session = FakeSession(
            {
                "elements": [
                    {
                        "type": "way",
                        "id": 10,
                        "center": {"lat": 51.47, "lon": -0.02},
                        "tags": {"name": "Far Cafe"},
                    },
                    {
                        "type": "node",
                        "id": 11,
                        "lat": 51.451,
                        "lon": -0.0201,
                        "tags": {"name": "Near Cafe"},
                    },
                ]
            }
        )
        provider = OverpassAmenityProvider(session=session)

        amenities = provider.search(Coordinate(51.45, -0.02), "cafe")

        self.assertEqual(["Near Cafe", "Far Cafe"], [amenity.name for amenity in amenities])
        self.assertEqual("way/10", amenities[1].id)

    def test_falls_back_to_bounded_nominatim_search(self):
        session = FakeSession(
            {"elements": []},
            get_payload=[
                {
                    "osm_type": "node",
                    "osm_id": 20,
                    "lat": "51.451",
                    "lon": "-0.0201",
                    "category": "amenity",
                    "type": "pub",
                    "display_name": "Nearby Pub, Test Road",
                }
            ],
        )
        provider = OverpassAmenityProvider(session=session)

        amenities = provider.search(Coordinate(51.45, -0.02), "pub")

        self.assertEqual(["Nearby Pub"], [amenity.name for amenity in amenities])
        self.assertEqual("nominatim/node/20", amenities[0].id)
        self.assertEqual(["pub"], [request[1]["q"] for request in session.get_requests])
        self.assertTrue(all(request[1]["bounded"] == 1 for request in session.get_requests))


if __name__ == "__main__":
    unittest.main()
