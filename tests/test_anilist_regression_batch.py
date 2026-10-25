"""Offline regression coverage for AniList URL, text, progress, and profile variations."""
import unittest

from cogs.social import anilist_site_embed as anilist


class AniListURLVariationTests(unittest.TestCase):
    def test_entity_urls_accept_www_slug_trailing_slash_and_case_variants(self):
        cases = (
            (anilist.ACTIVITY_URL_RE, "https://www.anilist.co/activity/12345", "12345"),
            (anilist.ACTIVITY_URL_RE, "HTTP://ANILIST.CO/activity/678/", "678"),
            (anilist.ANIME_URL_RE, "https://www.anilist.co/anime/1/example-title/", "1"),
            (anilist.MANGA_URL_RE, "https://anilist.co/manga/42/slug", "42"),
            (anilist.REVIEW_URL_RE, "https://www.anilist.co/review/98765", "98765"),
            (anilist.CHARACTER_URL_RE, "https://anilist.co/character/17/example", "17"),
            (anilist.STAFF_URL_RE, "https://www.anilist.co/staff/18/example/", "18"),
            (anilist.STUDIO_URL_RE, "https://anilist.co/studio/2/example", "2"),
        )
        for pattern, url, expected_id in cases:
            with self.subTest(url=url):
                match = pattern.match(url)
                self.assertIsNotNone(match)
                self.assertEqual(match.group(1), expected_id)

    def test_user_routes_preserve_username_and_section_variants(self):
        cases = (
            ("https://anilist.co/user/Vireon/", "Vireon", ""),
            ("https://www.anilist.co/user/Vireon/animelist", "Vireon", "animelist"),
            ("https://anilist.co/user/Vireon/mangalist?sort=SCORE_DESC", "Vireon", "mangalist"),
            ("https://www.anilist.co/user/test_user/statistics", "test_user", "statistics"),
            ("https://anilist.co/user/name-123/favourites#top", "name-123", "favourites"),
        )
        for url, username, route in cases:
            with self.subTest(url=url):
                match = anilist.USER_URL_RE.match(url)
                self.assertIsNotNone(match)
                self.assertEqual(match.group(1), username)
                self.assertEqual((match.group(2) or "").rstrip("/"), route)

    def test_invalid_hosts_and_non_numeric_entity_ids_are_rejected(self):
        cases = (
            (anilist.ANIME_URL_RE, "https://notanilist.co/anime/12"),
            (anilist.ANIME_URL_RE, "https://anilist.com/anime/12"),
            (anilist.ANIME_URL_RE, "https://anilist.co/anime/not-a-number"),
            (anilist.CHARACTER_URL_RE, "https://anilist.co/character/abc"),
        )
        for pattern, url in cases:
            with self.subTest(url=url):
                self.assertIsNone(pattern.match(url))


class AniListTextRegressionTests(unittest.TestCase):
    def setUp(self):
        # Avoid opening an aiohttp session just to exercise synchronous helpers.
        self.cog = object.__new__(anilist.AniListCog)

    def test_clean_text_handles_empty_html_markdown_entities_and_code(self):
        self.assertEqual(self.cog.clean_text(None), "")
        self.assertEqual(self.cog.clean_text(""), "")
        source = (
            "<p><strong>Bold</strong> and <em>italic</em></p>"
            "<a href='https://example.com/a?a=1&amp;b=2'>read &amp; learn</a>"
            "<blockquote>quoted</blockquote><code>x &lt; y</code>"
        )
        result = self.cog.clean_text(source)
        self.assertIn("**Bold**", result)
        self.assertIn("*italic*", result)
        self.assertIn("[read & learn](https://example.com/a?a=1&b=2)", result)
        self.assertIn("> quoted", result)
        self.assertIn(chr(96) + "x < y" + chr(96), result)

    def test_clean_text_converts_spoilers_headings_and_numbered_media_tokens(self):
        result = self.cog.clean_text(
            "# Heading\n## Subheading\n~!spoiler!~\n"
            "img1(https://cdn.example/one.png) img12(https://cdn.example/two.png) "
            "imgx(https://cdn.example/three.png) vid(https://cdn.example/clip.mp4)"
        )
        self.assertIn("__**Heading**__", result)
        self.assertIn("**Subheading**", result)
        self.assertIn("||spoiler||", result)
        self.assertIn("https://cdn.example/one.png", result)
        self.assertIn("https://cdn.example/two.png", result)
        self.assertIn("https://cdn.example/three.png", result)
        self.assertIn("https://cdn.example/clip.mp4", result)

    def test_extract_media_supports_each_token_style_and_deduplicates_urls(self):
        urls = (
            "https://cdn.example/plain.png",
            "https://cdn.example/img.png",
            "https://cdn.example/img1.jpg",
            "https://cdn.example/img12.webp",
            "https://cdn.example/imgx.gif",
            "https://cdn.example/clip.mp4",
            "https://cdn.example/markdown.png",
            "https://cdn.example/html.webp",
        )
        source = (
            f"img({urls[1]}) img1({urls[2]}) img12({urls[3]}) imgx({urls[4]}) "
            f"vid({urls[5]}) ![alt]({urls[6]}) <img src='{urls[7]}'> "
            f"{urls[0]} img({urls[1]})"
        )
        extracted, cleaned = self.cog.extract_media(source)
        self.assertEqual(set(extracted), set(urls))
        self.assertEqual(len(extracted), len(urls))
        self.assertNotIn(urls[0], cleaned)
        self.assertNotIn("img12(", cleaned)

    def test_anilist_errors_and_warnings_point_to_feedback_with_reporting_steps(self):
        for embed in (
            anilist._anilist_error("Example failure"),
            anilist._anilist_warning("Example warning"),
        ):
            with self.subTest(title=embed.title):
                self.assertIn("/feedback", embed.description)
                self.assertIn("Bugs", embed.description)
                self.assertIn("AniList URL", embed.description)
                self.assertIn("screenshot", embed.description)


class AniListProfileAndProgressTests(unittest.TestCase):
    def setUp(self):
        self.cog = object.__new__(anilist.AniListCog)

    def test_safe_stat_handles_numeric_empty_and_invalid_values(self):
        self.assertEqual(self.cog._safe_stat(87), "87.0/100")
        self.assertEqual(self.cog._safe_stat(87.456), "87.5/100")
        for value in (None, "unknown", object()):
            with self.subTest(value=value):
                self.assertEqual(self.cog._safe_stat(value), "—")

    def test_profile_overview_survives_missing_optional_metadata_and_html_about(self):
        embed = self.cog.build_user_profile_embed({
            "id": 55,
            "name": "Reader",
            "about": "<p>Hello <strong>world</strong></p>",
            "statistics": {"anime": {"count": 12}, "manga": None},
        })
        self.assertIn("Reader", embed.title)
        self.assertIn("Hello **world**", embed.description)
        self.assertEqual(len(embed.fields), 2)
        self.assertIn("12", embed.fields[0].value)
        self.assertIn("User ID 55", embed.footer.text)

    def test_profile_overview_truncates_extremely_long_about(self):
        embed = self.cog.build_user_profile_embed({"id": 1, "name": "Reader", "about": "x" * 5000})
        self.assertLessEqual(len(embed.description), 900)
        self.assertTrue(embed.description.endswith("..."))

    def test_statistics_and_favourites_build_empty_and_populated_sections(self):
        stats = self.cog.build_user_stats_embed({"id": 5, "name": "Reader", "statistics": {}})
        self.assertEqual(len(stats.fields), 2)
        self.assertIn("Mean score", stats.fields[0].value)

        favourites = self.cog.build_user_favorites_embed({
            "id": 5,
            "name": "Reader",
            "favourites": {
                "anime": {"nodes": [{"id": 1, "title": {"english": "One"}}]},
                "manga": {"nodes": []},
                "characters": {"nodes": [{"id": 2, "name": {"full": "Character"}}]},
                "staff": {"nodes": []},
                "studios": {"nodes": [{"id": 3, "name": "Studio"}]},
            },
        })
        self.assertEqual(len(favourites.fields), 5)
        self.assertIn("One", favourites.fields[0].value)
        self.assertIn("None listed", favourites.fields[1].value)
        self.assertIn("Character", favourites.fields[2].value)
        self.assertIn("Studio", favourites.fields[4].value)

    def test_media_list_handles_provider_failure_empty_page_and_populated_page(self):
        unavailable = self.cog.build_user_media_list_embed({"id": 9, "name": "Reader"}, "ANIME", None)
        self.assertIn("/feedback", unavailable.description)
        empty = self.cog.build_user_media_list_embed(
            {"id": 9, "name": "Reader"}, "MANGA", {"mediaList": []}
        )
        self.assertIn("No public manga", empty.description)
        populated = self.cog.build_user_media_list_embed(
            {"id": 9, "name": "Reader", "scoreFormat": "POINT_100"},
            "ANIME",
            {"mediaList": [{
                "score": 87, "progress": 12, "status": "CURRENT",
                "media": {"id": 4, "title": {"english": "Title"}, "siteUrl": "https://anilist.co/anime/4"},
            }]},
        )
        self.assertIn("Title", str(populated.to_dict()))

    def test_progress_filter_variants(self):
        active = {
            "progress": 5, "score": 9, "status": "CURRENT",
            "is_recent": True, "score_format": "POINT_10",
        }
        expectations = {
            anilist.ProgressFilter.ALL: True,
            anilist.ProgressFilter.ACTIVE_ONLY: True,
            anilist.ProgressFilter.COMPLETED_ONLY: False,
            anilist.ProgressFilter.HIGH_SCORERS: True,
            anilist.ProgressFilter.RECENT_ACTIVITY: True,
            anilist.ProgressFilter.WATCHING_NOW: True,
            anilist.ProgressFilter.DROPPED: False,
        }
        for filter_type, expected in expectations.items():
            with self.subTest(filter_type=filter_type):
                self.assertEqual(
                    self.cog._apply_progress_filter(active, filter_type, {"episodes": 12}),
                    expected,
                )
        dropped = {**active, "status": "DROPPED", "progress": 0, "is_recent": False}
        self.assertTrue(self.cog._apply_progress_filter(dropped, anilist.ProgressFilter.DROPPED, {}))
        completed = {**active, "status": "CURRENT", "progress": 12}
        self.assertTrue(self.cog._apply_progress_filter(completed, anilist.ProgressFilter.COMPLETED_ONLY, {"chapters": 12}))

    def test_total_count_prefers_episodes_then_chapters_then_infinity(self):
        self.assertEqual(self.cog._get_total_episodes_chapters({"episodes": 12, "chapters": 44}), 12)
        self.assertEqual(self.cog._get_total_episodes_chapters({"chapters": 44}), 44)
        self.assertEqual(self.cog._get_total_episodes_chapters({}), float("inf"))


if __name__ == "__main__":
    unittest.main()
