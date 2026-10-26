"""Tests for robust title handling across franchise providers."""
import unittest

from cogs_test.general_commands.franchise import _ani_release_date, _has_full_release_date, _ani_release_sort, media_title


class FranchiseTitleTests(unittest.TestCase):
    def test_anilist_title_dictionary(self):
        self.assertEqual(media_title({"title": {"english": "English", "romaji": "Japanese"}}), "English")

    def test_tmdb_and_google_books_string_titles(self):
        self.assertEqual(media_title({"title": "Movie Title"}), "Movie Title")
        self.assertEqual(media_title({"title": "", "name": "TV Series"}), "TV Series")

    def test_release_order_requires_full_provider_dates(self):
        full = {"startDate": {"year": 2024, "month": 8, "day": 17}}
        partial = {"startDate": {"year": 2024}}
        self.assertEqual(_ani_release_date(full), "2024-08-17")
        self.assertEqual(_ani_release_date(partial), "2024")
        self.assertTrue(_has_full_release_date(full))
        self.assertFalse(_has_full_release_date(partial))
        self.assertLess(_ani_release_sort({"startDate": {"year": 2023, "month": 12, "day": 1}}), _ani_release_sort(full))

    def test_missing_title_has_safe_fallback(self):
        self.assertEqual(media_title({}), "Untitled")


if __name__ == "__main__":
    unittest.main()
