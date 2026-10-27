"""Offline regression tests for TMDB movie and TV discovery filters."""
import unittest

from cogs_test.general_commands.screen_discovery import build_discover_params


class ScreenDiscoveryParamsTests(unittest.TestCase):
    def test_movie_filters_use_movie_year_genre_and_guild_region(self):
        params = build_discover_params(
            "MOVIE", "newest", genre="science fiction", year=2024,
            minimum_rating=7.5, language="JA", region="IE",
        )
        self.assertEqual(params["sort_by"], "primary_release_date.desc")
        self.assertEqual(params["with_genres"], 878)
        self.assertEqual(params["primary_release_year"], 2024)
        self.assertEqual(params["vote_average.gte"], 7.5)
        self.assertEqual(params["with_original_language"], "ja")
        self.assertEqual(params["region"], "IE")
        self.assertNotIn("first_air_date_year", params)

    def test_tv_filters_use_tv_year_and_action_adventure_genre(self):
        params = build_discover_params(
            "TV", "rating", genre="Action & Adventure", year=2025, region="GB",
        )
        self.assertEqual(params["with_genres"], 10759)
        self.assertEqual(params["first_air_date_year"], 2025)
        self.assertEqual(params["sort_by"], "vote_average.desc")
        self.assertEqual(params["vote_count.gte"], 50)
        self.assertNotIn("region", params)
        self.assertNotIn("primary_release_year", params)

    def test_popularity_and_votes_have_distinct_sorts(self):
        self.assertEqual(build_discover_params("MOVIE")["sort_by"], "popularity.desc")
        self.assertEqual(build_discover_params("TV", "votes")["sort_by"], "vote_count.desc")

    def test_rejects_invalid_filters(self):
        cases = [
            (("ANIME",), {}),
            (("MOVIE",), {"sort_by": "random"}),
            (("MOVIE",), {"genre": "not a real genre"}),
            (("TV",), {"year": 1800}),
            (("MOVIE",), {"minimum_rating": 11}),
            (("MOVIE",), {"language": "english"}),
            (("MOVIE",), {"region": "IRE"}),
        ]
        for args, kwargs in cases:
            with self.subTest(args=args, kwargs=kwargs), self.assertRaises(ValueError):
                build_discover_params(*args, **kwargs)


if __name__ == "__main__":
    unittest.main()
