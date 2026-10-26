"""Tests for robust title handling across franchise providers."""
import unittest

from cogs_test.general_commands.franchise import media_title


class FranchiseTitleTests(unittest.TestCase):
    def test_anilist_title_dictionary(self):
        self.assertEqual(media_title({"title": {"english": "English", "romaji": "Japanese"}}), "English")

    def test_tmdb_and_google_books_string_titles(self):
        self.assertEqual(media_title({"title": "Movie Title"}), "Movie Title")
        self.assertEqual(media_title({"title": "", "name": "TV Series"}), "TV Series")

    def test_missing_title_has_safe_fallback(self):
        self.assertEqual(media_title({}), "Untitled")


if __name__ == "__main__":
    unittest.main()
