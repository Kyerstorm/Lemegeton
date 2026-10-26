"""Tests for media-night mood, title normalization, and suitability filters."""
import unittest

from cogs_test.general_commands.media_night import _family_friendly, _matches_mood, title_of


class MediaNightFilterTests(unittest.TestCase):
    def test_title_of_accepts_anilist_and_tmdb_shapes(self):
        self.assertEqual(title_of({"title": {"english": "English Name"}}), "English Name")
        self.assertEqual(title_of({"title": "Movie Name"}), "Movie Name")

    def test_mood_filter_uses_provider_genres_and_tags(self):
        item = {
            "genres": ["Comedy", "Slice of Life"],
            "tags": [{"name": "Found Family"}],
        }
        self.assertTrue(_matches_mood(item, "cozy"))
        self.assertFalse(_matches_mood(item, "dark"))
        self.assertTrue(_matches_mood(item, None))

    def test_family_friendly_excludes_adult_flags_and_explicit_markers(self):
        self.assertTrue(_family_friendly({"genres": ["Adventure"], "tags": []}))
        self.assertFalse(_family_friendly({"isAdult": True}))
        self.assertFalse(_family_friendly({"genres": [], "tags": [{"name": "Hentai"}]}))


if __name__ == "__main__":
    unittest.main()
