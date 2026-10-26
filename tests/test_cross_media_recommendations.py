"""Tests for transparent cross-media recommendation ranking."""
import unittest

from cogs_test.general_commands.cross_media_recommendations import genre_tokens, local_match_reason


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

    def test_no_shared_genres_does_not_create_a_match(self):
        self.assertEqual(local_match_reason({"horror"}, {"romance"}), (0, []))


if __name__ == "__main__":
    unittest.main()
