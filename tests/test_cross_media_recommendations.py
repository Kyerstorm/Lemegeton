"""Tests for transparent cross-media recommendation ranking."""
import unittest

from cogs_test.general_commands.cross_media_recommendations import CrossMediaRecommendations, genre_tokens, local_match_reason


class CrossMediaRecommendationTests(unittest.TestCase):
    def test_genre_tokens_normalize_provider_labels(self):
        self.assertEqual(
            genre_tokens(["Fiction / Fantasy / Epic", "Science Fiction", "Romance"]),
            {"fantasy", "sci-fi", "romance"},
        )

    def test_local_reason_only_uses_shared_genres(self):
        count, shared = local_match_reason({"fantasy", "romance"}, {"fantasy", "drama"})
        self.assertEqual(count, 1)
        self.assertEqual(shared, ["fantasy"])

    def test_webnovel_seed_keeps_novel_updates_source_and_genres(self):
        title, url, genres, tags, extra = CrossMediaRecommendations.seed_metadata(
            {"title": "Novel Title", "url": "https://www.novelupdates.com/series/example/", "genres": ["Fantasy"]},
            "WEBNOVEL",
        )
        self.assertEqual(title, "Novel Title")
        self.assertEqual(url, "https://www.novelupdates.com/series/example/")
        self.assertEqual(genres, ["Fantasy"])
        self.assertEqual(tags, [])
        self.assertEqual(extra, [])

    def test_no_shared_genres_does_not_create_a_match(self):
        self.assertEqual(local_match_reason({"horror"}, {"romance"}), (0, []))


if __name__ == "__main__":
    unittest.main()
