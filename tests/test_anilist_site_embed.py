"""Regression tests for automatic AniList link handling."""

import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock

from cogs.social.anilist_site_embed import (
    AniListCog,
    _user_profile_embed_section,
)


class AniListUserEmbedRouteTests(unittest.IsolatedAsyncioTestCase):
    def test_list_routes_are_not_supported_auto_embed_sections(self):
        for route in (
            "animelist",
            "anime",
            "anime-list",
            "mangalist",
            "manga",
            "manga-list",
        ):
            with self.subTest(route=route):
                self.assertIsNone(_user_profile_embed_section(route))

    def test_profile_and_non_list_sections_remain_supported(self):
        self.assertEqual(_user_profile_embed_section(None), "overview")
        self.assertEqual(_user_profile_embed_section(""), "overview")
        self.assertEqual(_user_profile_embed_section("stats"), "statistics")
        self.assertEqual(_user_profile_embed_section("favorites"), "favorites")
        self.assertEqual(_user_profile_embed_section("activity"), "activity")

    async def test_listener_ignores_anime_and_manga_list_urls(self):
        cog = SimpleNamespace(fetch_user_profile=AsyncMock())
        channel = SimpleNamespace(send=AsyncMock())

        for route in ("animelist", "mangalist"):
            message = SimpleNamespace(
                author=SimpleNamespace(bot=False),
                content=f"https://anilist.co/user/example/{route}/",
                channel=channel,
                guild=None,
            )
            await AniListCog.on_message(cog, message)

        cog.fetch_user_profile.assert_not_awaited()
        channel.send.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
