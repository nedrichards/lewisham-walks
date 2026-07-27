import unittest

from lewisham_walks.discovery import discoveries_for_theme, display_title, featured_discoveries, source_label
from lewisham_walks.models import Coordinate, Discovery, DiscoveryKind, RouteTheme


class DiscoveryTests(unittest.TestCase):
    def setUp(self):
        self.local = Discovery(
            "local", "A locally curated story", "An artist lived here", Coordinate(51.46, -0.01),
            collection="lewisham-maroon", borough="Lewisham", curation_status="in_scope",
        )
        self.place = Discovery(
            "place", "The old station building which stood on this site and served the neighbourhood",
            "The station was built here", Coordinate(51.47, -0.02), is_accurate=True,
        )
        self.listed = Discovery(
            "listed", "A listed hall", "Grade II* listed building", Coordinate(51.45, -0.03),
            kind=DiscoveryKind.LISTED_BUILDING, collection="historic-england-listed-buildings",
            source_name="Historic England", borough="Lewisham", attributes={"grade": "II*"},
        )
        self.culture = Discovery(
            "culture", "A cultural venue", "A public gallery", Coordinate(51.48, -0.03),
            kind=DiscoveryKind.CULTURAL_VENUE, collection="gla-cultural-infrastructure",
            source_name="GLA Cultural Infrastructure Map", borough="Lewisham",
            attributes={"category": "Gallery"},
        )

    def test_theme_filters_are_understandable_and_deterministic(self):
        self.assertEqual([self.local], discoveries_for_theme([self.local, self.place], RouteTheme.PEOPLE))
        self.assertEqual([self.place], discoveries_for_theme([self.local, self.place], RouteTheme.PLACES))
        self.assertEqual([self.local], discoveries_for_theme([self.local, self.place], RouteTheme.LEWISHAM))
        self.assertEqual(
            [self.listed],
            discoveries_for_theme([self.local, self.place, self.listed], RouteTheme.LISTED_BUILDINGS),
        )
        self.assertEqual(
            [self.culture],
            discoveries_for_theme([self.local, self.culture, self.listed], RouteTheme.CULTURE),
        )

    def test_listed_building_source_label_includes_grade_and_borough(self):
        self.assertEqual("Historic England · Grade II* · Lewisham", source_label(self.listed))

    def test_cultural_venue_source_label_includes_category_and_borough(self):
        self.assertEqual(
            "GLA Cultural Infrastructure Map · Gallery · Lewisham",
            source_label(self.culture),
        )

    def test_featured_stories_prefer_curated_records(self):
        self.assertEqual(self.local, featured_discoveries([self.place, self.local], limit=1)[0])

    def test_featured_stories_deduplicate_the_same_location(self):
        duplicate = Discovery(
            "duplicate", "Raw imported duplicate title", "The same artist lived here",
            Coordinate(51.46001, -0.01001), curation_status="candidate",
        )

        self.assertEqual([self.local], featured_discoveries([duplicate, self.local], limit=2))

    def test_long_imported_titles_are_shortened(self):
        self.assertLessEqual(len(display_title(self.place)), 62)

    def test_featured_preview_reserves_nearby_border_context(self):
        discoveries = [
            Discovery(f"local-{index}", f"Local {index}", "", Coordinate(51.46, -0.01), borough="Lewisham")
            for index in range(20)
        ]
        discoveries.extend(
            [
                Discovery("greenwich", "Greenwich border", "", Coordinate(51.47, -0.005), borough="Greenwich", is_accurate=True),
                Discovery("southwark", "Southwark border", "", Coordinate(51.47, -0.025), borough="Southwark", is_accurate=True),
            ]
        )

        featured = featured_discoveries(discoveries, limit=8)

        self.assertEqual(DiscoveryKind.PLAQUE, featured[-1].kind)
        self.assertEqual(
            {"Greenwich", "Southwark"},
            {item.borough for item in featured if item.borough != "Lewisham"},
        )


if __name__ == "__main__":
    unittest.main()
