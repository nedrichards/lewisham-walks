import unittest

from lewisham_walks.models import Coordinate
from lewisham_walks.providers.geocoding import GeocodingError, PostcodesIoGeocoder, normalise_postcode


class FakeResponse:
    status_code = 200

    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


class FakeSession:
    def __init__(self, payload):
        self.payload = payload
        self.request = None

    def get(self, endpoint, **kwargs):
        self.request = endpoint, kwargs
        return FakeResponse(self.payload)


class PostcodeTests(unittest.TestCase):
    def test_normalises_valid_postcode(self):
        self.assertEqual(normalise_postcode("se135af"), "SE13 5AF")

    def test_rejects_invalid_postcode(self):
        with self.assertRaises(ValueError):
            normalise_postcode("not a postcode")

    def test_reverse_lookup_returns_nearest_normalised_uk_postcode(self):
        session = FakeSession({"result": [{"postcode": "se13 5af", "distance": 24.0}]})

        postcode = PostcodesIoGeocoder(session).reverse_lookup_postcode(Coordinate(51.46, -0.01))

        self.assertEqual(postcode, "SE13 5AF")
        self.assertEqual("https://api.postcodes.io/postcodes", session.request[0])
        self.assertEqual(
            {"lon": -0.01, "lat": 51.46, "limit": 1, "radius": 2000},
            session.request[1]["params"],
        )
        self.assertEqual(10, session.request[1]["timeout"])

    def test_reverse_lookup_rejects_locations_without_a_uk_postcode(self):
        session = FakeSession({"result": []})

        with self.assertRaisesRegex(GeocodingError, "No nearby UK postcode"):
            PostcodesIoGeocoder(session).reverse_lookup_postcode(Coordinate(40.71, -74.0))


if __name__ == "__main__":
    unittest.main()
