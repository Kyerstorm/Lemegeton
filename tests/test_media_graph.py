"""Focused tests for the shared cross-system media relationship graph."""
import json
import unittest
from unittest.mock import AsyncMock, patch

from helpers.media_graph import (
    find_linked_resources,
    find_media_relationships,
    normalize_media_title,
    record_media_relationship,
    safe_media_url,
)


class MediaGraphNormalizationTests(unittest.TestCase):
    def test_title_normalization_is_punctuation_and_case_insensitive(self):
        self.assertEqual(
            normalize_media_title("The King's Avatar: 2"),
            normalize_media_title(" the king s avatar 2 "),
        )
        self.assertEqual(normalize_media_title(None), "")

    def test_source_urls_require_https_and_reject_credentials(self):
        self.assertEqual(safe_media_url("https://example.com/title"), "https://example.com/title")
        for value in (
            "http://example.com/title",
            "javascript:alert(1)",
            "https://user:password@example.com/title",
            "not a url",
            None,
        ):
            with self.subTest(value=value):
                self.assertIsNone(safe_media_url(value))


class MediaGraphPersistenceTests(unittest.IsolatedAsyncioTestCase):
    async def test_community_edges_require_a_guild_before_database_access(self):
        with (
            patch("helpers.media_graph.ensure_media_graph_schema", new_callable=AsyncMock) as ensure,
            patch("helpers.media_graph.database.execute_db_operation", new_callable=AsyncMock) as execute,
        ):
            stored = await record_media_relationship(
                "Source", "ANIME", "https://anilist.co/anime/1",
                "Target", "GAME", "https://www.igdb.com/games/target",
                "adaptation",
                source_kind="community",
                source_label="Moderator-approved suggestion",
            )
        self.assertFalse(stored)
        ensure.assert_not_awaited()
        execute.assert_not_awaited()

    async def test_provider_edges_are_global_and_categories_are_normalized(self):
        with (
            patch("helpers.media_graph.ensure_media_graph_schema", new_callable=AsyncMock),
            patch(
                "helpers.media_graph.database.execute_db_operation",
                new_callable=AsyncMock,
                return_value=(17,),
            ) as execute,
        ):
            stored = await record_media_relationship(
                " Source  Title ", "Anime", "http://invalid.example/source",
                "Target TV Series", "TV series", "https://example.com/tv/1",
                "SEQUEL",
                source_kind="provider",
                source_label="TMDB provider relationship",
                guild_id=12345,
            )
        self.assertTrue(stored)
        params = execute.await_args.args[2]
        self.assertEqual(params[0], "Source Title")
        self.assertEqual(params[2], "ANIME")
        self.assertIsNone(params[3])
        self.assertEqual(params[6], "TV")
        self.assertEqual(params[8], "sequel")
        self.assertIsNone(params[11])

    async def test_invalid_categories_are_rejected_without_database_writes(self):
        with (
            patch("helpers.media_graph.ensure_media_graph_schema", new_callable=AsyncMock) as ensure,
            patch("helpers.media_graph.database.execute_db_operation", new_callable=AsyncMock) as execute,
        ):
            stored = await record_media_relationship(
                "Source", "Anime", None,
                "Target", "Unrecognized media type", None,
                "related",
                source_kind="provider",
                source_label="Test",
            )
        self.assertFalse(stored)
        ensure.assert_not_awaited()
        execute.assert_not_awaited()

    async def test_linked_resources_include_same_guild_reading_club_and_media_night(self):
        captured = []

        async def db_result(operation, query, params=None, fetch_type=None):
            captured.append((query, params))
            if "reading_club_nominations" in query:
                return [
                    ("nomination-1", "A Shared Title", "manga", "https://anilist.co/manga/3", "open", None),
                    ("nomination-2", "Another Title", "book", None, "open", None),
                ]
            if "media_night_sessions" in query:
                candidates = json.dumps([{"title": {"english": "A Shared Title"}}])
                return [("session-1", 100, 200, "anime", candidates)]
            return []

        with patch(
            "helpers.media_graph.database.execute_db_operation",
            new_callable=AsyncMock,
            side_effect=db_result,
        ):
            resources = await find_linked_resources(
                "A Shared Title", "ANIME", 42, url="https://anilist.co/anime/1",
            )

        self.assertTrue(any(item["kind"] == "Reading Club" for item in resources))
        self.assertTrue(any(item["kind"] == "Media Night" for item in resources))
        media_night = next(item for item in resources if item["kind"] == "Media Night")
        self.assertEqual(media_night["url"], "https://discord.com/channels/42/100/200")
        guild_queries = [
            (query, params) for query, params in captured
            if "reading_club_nominations" in query or "media_night_sessions" in query
        ]
        self.assertEqual(len(guild_queries), 2)
        for query, params in guild_queries:
            self.assertIn("guild_id = ?", query)
            self.assertEqual(params[0], 42)

    async def test_relationship_queries_include_global_and_current_guild_edges(self):
        with (
            patch("helpers.media_graph.ensure_media_graph_schema", new_callable=AsyncMock),
            patch("helpers.media_graph.database.execute_db_operation", new_callable=AsyncMock, return_value=[]) as execute,
        ):
            results = await find_media_relationships(
                "Example Game", "GAME", "https://www.igdb.com/games/example-game", 42,
            )
        self.assertEqual(results, [])
        query = execute.await_args.args[1]
        params = execute.await_args.args[2]
        self.assertIn("guild_id IS NULL OR guild_id = ?", query)
        self.assertEqual(params[0], 42)
        self.assertIn("source_title_key", query)
        self.assertIn("target_title_key", query)


if __name__ == "__main__":
    unittest.main()
