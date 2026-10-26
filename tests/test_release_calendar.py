"""Unit tests for provider-backed release calendar normalization."""
import unittest
from datetime import datetime, timezone

from cogs_test.general_commands.release_calendar import _title, date_is_in_window, normalize_categories


class ReleaseCalendarTests(unittest.TestCase):
    def test_title_helper_accepts_anilist_title_objects(self):
        self.assertEqual(_title({"title": {"english": "English", "romaji": "Romaji"}}), "English")
        self.assertEqual(_title({"title": "Movie Title"}), "Movie Title")
        self.assertEqual(_title({"name": "TV Series"}, tv=True), "TV Series")

    def test_categories_are_normalized_and_deduplicated(self):
        self.assertEqual(normalize_categories(" Anime, movies,anime "), ["anime", "movies"])

    def test_categories_reject_unknown_values(self):
        with self.assertRaises(ValueError):
            normalize_categories("anime,books")

    def test_empty_categories_are_rejected(self):
        with self.assertRaises(ValueError):
            normalize_categories(" , ")

    def test_release_date_inclusive_window(self):
        start = datetime(2026, 10, 26, tzinfo=timezone.utc)
        end = datetime(2026, 11, 2, tzinfo=timezone.utc)
        self.assertTrue(date_is_in_window("2026-10-26", start, end))
        self.assertTrue(date_is_in_window("2026-11-02", start, end))
        self.assertFalse(date_is_in_window("2026-11-03", start, end))

    def test_missing_or_invalid_dates_are_not_included(self):
        start = datetime(2026, 10, 26, tzinfo=timezone.utc)
        end = datetime(2026, 11, 2, tzinfo=timezone.utc)
        self.assertFalse(date_is_in_window(None, start, end))
        self.assertFalse(date_is_in_window("TBA", start, end))


if __name__ == "__main__":
    unittest.main()
