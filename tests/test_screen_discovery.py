"""Offline tests for TMDB discovery integrated into /browse."""
import unittest

from helpers.tmdb_discovery import build_tmdb_discover_params


class BrowseTMDBDiscoveryTests(unittest.TestCase):
    def test_movie_filters_include_genre_year_rating_language_sort_and_region(self):
        params = build_tmdb_discover_params(
            "MOVIE",
            genre="science fiction",
            language="JA",
            year_from=2020,
            year_to=2024,
            minimum_rating=7.5,
            sort_by="newest",
            region="IE",
            keyword_id=803,
            director_id=525,
            cast_id=6193,
            runtime_min=90,
            runtime_max=180,
        )
        self.assertEqual(params["with_genres"], 878)
        self.assertEqual(params["primary_release_date.gte"], "2020-01-01")
        self.assertEqual(params["primary_release_date.lte"], "2024-12-31")
        self.assertEqual(params["vote_average.gte"], 7.5)
        self.assertEqual(params["with_original_language"], "ja")
        self.assertEqual(params["sort_by"], "primary_release_date.desc")
        self.assertEqual(params["region"], "IE")
        self.assertEqual(params["with_keywords"], 803)
        self.assertEqual(params["with_crew"], 525)
        self.assertEqual(params["with_cast"], 6193)
        self.assertEqual(params["with_runtime.gte"], 90)
        self.assertEqual(params["with_runtime.lte"], 180)
        self.assertEqual(params["include_adult"], "false")

    def test_tv_filters_use_tv_specific_genres_dates_and_status(self):
        params = build_tmdb_discover_params(
            "TV", genre="Action & Adventure", status="returning series",
            year_from=2021, year_to=2025, minimum_rating=8,
            sort_by="rating", region="GB",
        )
        self.assertEqual(params["with_genres"], 10759)
        self.assertEqual(params["first_air_date.gte"], "2021-01-01")
        self.assertEqual(params["first_air_date.lte"], "2025-12-31")
        self.assertEqual(params["with_status"], 0)
        self.assertEqual(params["vote_count.gte"], 50)
        self.assertEqual(params["sort_by"], "vote_average.desc")
        self.assertNotIn("region", params)
        self.assertNotIn("primary_release_date.gte", params)

    def test_default_sort_and_region_are_safe(self):
        params = build_tmdb_discover_params("MOVIE")
        self.assertEqual(params["sort_by"], "popularity.desc")
        self.assertEqual(params["region"], "IE")
        self.assertEqual(params["include_adult"], "false")
        self.assertEqual(build_tmdb_discover_params("TV", sort_by="votes")["sort_by"], "vote_count.desc")

    def test_invalid_filters_fail_explicitly(self):
        cases = [
            (("ANIME",), {}),
            (("MOVIE",), {"sort_by": "random"}),
            (("MOVIE",), {"genre": "not a real genre"}),
            (("TV",), {"year_from": 2025, "year_to": 2020}),
            (("MOVIE",), {"minimum_rating": 11}),
            (("MOVIE",), {"language": "english"}),
            (("MOVIE",), {"region": "IRE"}),
            (("MOVIE",), {"status": "released"}),
            (("TV",), {"status": "mystery"}),
        ]
        for args, kwargs in cases:
            with self.subTest(args=args, kwargs=kwargs), self.assertRaises(ValueError):
                build_tmdb_discover_params(*args, **kwargs)


if __name__ == "__main__":
    unittest.main()
