import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from helpers.crypto_random import secure_choice, secure_randbelow
from cogs_test.general_commands.airing import filter_schedule, format_utc_airing_time
from cogs.media.browse import BrowseCog
from cogs.media.recommendations import RecommendationsCog, get_format_category
from cogs.server_management.server_config import validate_config_channel


class ServerConfigChannelValidationTests(unittest.TestCase):
    def setUp(self):
        self.permissions = SimpleNamespace(
            view_channel=True, send_messages=True, embed_links=True,
        )
        self.bot_member = object()
        self.channel = SimpleNamespace(
            guild=SimpleNamespace(id=123),
            mention="<#456>",
            permissions_for=lambda _member: self.permissions,
        )

    def test_rejects_channel_from_another_guild(self):
        message = validate_config_channel(self.channel, 789, self.bot_member, True)
        self.assertIn("belonging to this server", message)

    def test_rejects_non_text_channel(self):
        message = validate_config_channel(self.channel, 123, self.bot_member, False)
        self.assertIn("text or announcement channel", message)

    def test_reports_missing_required_bot_permissions(self):
        self.permissions.send_messages = False
        message = validate_config_channel(self.channel, 123, self.bot_member, True)
        self.assertIn("Send Messages", message)

    def test_accepts_a_valid_channel_and_permission_set(self):
        self.assertIsNone(validate_config_channel(self.channel, 123, self.bot_member, True))

    def test_missing_channel_is_not_silently_reset(self):
        message = validate_config_channel(None, 123, self.bot_member, True)
        self.assertIn("text or announcement channel", message)


class MediaDiscoveryHelperTests(unittest.TestCase):
    def test_title_normalization_collapses_whitespace_and_case(self):
        self.assertEqual(
            BrowseCog.normalize_title_search("  A\u00a0Title  "),
            "a title",
        )
        self.assertEqual(
            BrowseCog.normalize_title_search("O’NEIL"),
            "o'neil",
        )

    def test_best_title_match_prefers_exact_title(self):
        results = [{"title": "A Title: Side Story"}, {"title": "A Title"}]
        selected = BrowseCog.choose_best_title_match(
            results, "a title", lambda item: item["title"]
        )
        self.assertIs(selected, results[1])

    def test_book_category_helpers_distinguish_fiction_and_nonfiction(self):
        self.assertTrue(BrowseCog._is_fiction_book({"categories": ["Fiction / Fantasy"]}))
        self.assertTrue(BrowseCog._is_nonfiction_book({"categories": ["History"]}))
        self.assertFalse(BrowseCog._is_nonfiction_book({"categories": ["Fiction / Fantasy"]}))

    def test_uncategorized_books_remain_eligible_for_fallback_results(self):
        book = {"title": "An Unclassified Title"}
        self.assertFalse(BrowseCog._is_fiction_book(book))
        self.assertFalse(BrowseCog._is_nonfiction_book(book))

    def test_novel_format_is_categorized_as_light_novel(self):
        self.assertEqual(get_format_category("NOVEL", "JP"), "light_novels")

    def test_recommendations_exclude_titles_already_in_the_list(self):
        cog = RecommendationsCog(None)
        duplicate = {
            "id": 1, "status": "FINISHED", "format": "MANGA",
            "countryOfOrigin": "JP", "title": {"english": "Already Owned"},
        }
        candidate = {
            "id": 2, "status": "FINISHED", "format": "MANGA",
            "countryOfOrigin": "JP", "title": {"english": "New Title"},
            "averageScore": 80, "coverImage": {"large": None},
            "genres": ["Fantasy"], "description": "Test",
            "startDate": {"year": 2020}, "chapters": 12, "volumes": 2,
        }
        nodes = [
            {"rating": 5, "mediaRecommendation": duplicate},
            {"rating": 4, "mediaRecommendation": candidate},
            {"rating": 7, "mediaRecommendation": {"status": "FINISHED"}},
        ]
        source_list = [
            {"media": {"recommendations": {"nodes": nodes}}},
            {"media": {"recommendations": {"nodes": nodes}}},
            {"media": {"recommendations": {"nodes": nodes}}},
        ]
        grouped = cog.extract_recommendations(source_list, {1}, "MANGA")
        self.assertNotIn(1, grouped["manga"])
        self.assertIn(2, grouped["manga"])
        self.assertEqual(grouped["manga"][2]["occurrences"], 3)

    def test_secure_random_selection_respects_bounds(self):
        for bound in (1, 2, 7, 128, 10000):
            selected = secure_randbelow(bound)
            self.assertGreaterEqual(selected, 0)
            self.assertLess(selected, bound)

    def test_secure_choice_rejects_empty_candidates(self):
        with self.assertRaises(IndexError):
            secure_choice([])

    def test_airing_filter_ignores_missing_and_past_timestamps(self):
        now = datetime.now(timezone.utc)
        entries = [
            {"airingAt": int((now + timedelta(hours=1)).timestamp()), "episode": 2, "media": {}},
            {"airingAt": int((now - timedelta(hours=1)).timestamp()), "episode": 1, "media": {}},
            {"episode": 3, "media": {}},
            {"airingAt": "soon", "episode": 4, "media": {}},
        ]
        filtered = filter_schedule(entries, days=1)
        self.assertEqual([item["episode"] for item in filtered], [2])

    def test_airing_window_and_weekday_use_utc_timestamps(self):
        now = datetime.now(timezone.utc)
        first = int((now + timedelta(hours=1)).timestamp())
        late = int((now + timedelta(days=8)).timestamp())
        entries = [
            {"airingAt": late, "media": {"season": "WINTER", "seasonYear": 2027}},
            {"airingAt": first, "media": {"season": "WINTER", "seasonYear": 2027}},
        ]
        filtered = filter_schedule(entries, season="WINTER", year=2027, days=7)
        self.assertEqual(len(filtered), 1)
        self.assertEqual(filtered[0]["airingAt"], first)

    def test_airing_time_is_explicitly_formatted_as_utc(self):
        timestamp = int(datetime(2030, 1, 2, 3, 4, tzinfo=timezone.utc).timestamp())
        self.assertEqual(format_utc_airing_time(timestamp), "Wed, 02 Jan 2030 03:04 UTC")


if __name__ == "__main__":
    unittest.main()
