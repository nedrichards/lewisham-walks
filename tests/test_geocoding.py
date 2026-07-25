import unittest

from lewisham_walks.providers.geocoding import normalise_postcode


class PostcodeTests(unittest.TestCase):
    def test_normalises_valid_postcode(self):
        self.assertEqual(normalise_postcode("se135af"), "SE13 5AF")

    def test_rejects_invalid_postcode(self):
        with self.assertRaises(ValueError):
            normalise_postcode("not a postcode")


if __name__ == "__main__":
    unittest.main()
