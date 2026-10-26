"""Regression tests for provider-backed /browse filters."""
import unittest

from cogs.media.browse import BrowseCog


class BrowseFilterTests(unittest.TestCase):
    def setUp(self):
        self.anilist_item = {
            "genres": ["Fantasy", "Adventure"],
            "tags": [{"name": "Found Family", "isMediaSpoiler": False}],
            "status": "RELEASING",
            "startDate": {"year": 2024},
            "isAdult": False,
            "staff": {
                "edges": [
                    {"role": "Story & Art", "node": {"name": {"full": "A. Creator"}}},
                    {"role": "Art", "node": {"name": {"full": "B. Illustrator"}}},
                ]
            },
        }

    def test_anilist_filters_genre_theme_author_artist_status_and_year(self):
        matched = BrowseCog._filter_anilist_results(
            [self.anilist_item],
            genre="fant",
            theme="found family",
            author="Creator",
            artist="Illustrator",
            status="releasing",
            year_from=2020,
            year_to=2025,
        )
        self.assertEqual(matched, [self.anilist_item])

    def test_anilist_rejects_adult_items_by_default(self):
        item = dict(self.anilist_item, isAdult=True)
        self.assertEqual(BrowseCog._filter_anilist_results([item]), [])
        self.assertEqual(BrowseCog._filter_anilist_results([item], include_adult=True), [item])

    def test_anilist_year_and_status_filters_require_matching_metadata(self):
        self.assertEqual(BrowseCog._filter_anilist_results([self.anilist_item], year_from=2025), [])
        self.assertEqual(BrowseCog._filter_anilist_results([self.anilist_item], status="COMPLETED"), [])

    def test_tmdb_filters_release_runtime_language_genre_keyword_and_credits(self):
        movie = {
            "release_date": "2023-10-12",
            "genres": [{"name": "Fantasy"}, {"name": "Adventure"}],
            "keywords": {"keywords": [{"name": "found family"}]},
            "original_language": "en",
            "status": "Released",
            "runtime": 120,
            "credits": {
                "crew": [{"job": "Director", "name": "Example Director"}],
                "cast": [{"name": "Example Actor"}],
            },
            "adult": False,
        }
        self.assertTrue(BrowseCog._tmdb_matches(
            movie, "MOVIE", genre="fant", theme="found family", language="en",
            status="released", year_from=2020, year_to=2024,
            runtime_min=100, runtime_max=130,
            director="Example Director", cast="Example Actor",
        ))

    def test_tmdb_filter_fails_when_required_metadata_does_not_match(self):
        movie = {
            "release_date": "2023-10-12", "genres": [{"name": "Drama"}],
            "original_language": "fr", "runtime": 90, "status": "Released",
            "credits": {"crew": [], "cast": []}, "keywords": {"keywords": []},
        }
        self.assertFalse(BrowseCog._tmdb_matches(movie, "MOVIE", genre="fantasy"))
        self.assertFalse(BrowseCog._tmdb_matches(movie, "MOVIE", language="en"))
        self.assertFalse(BrowseCog._tmdb_matches(movie, "MOVIE", runtime_min=120))


if __name__ == "__main__":
    unittest.main()
