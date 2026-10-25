"""Focused regression tests for manga panel metadata and tag selection."""
import unittest

from cogs.media import panel


class PanelChapterCaptionTests(unittest.TestCase):
    def test_numbered_chapter_with_caption(self):
        self.assertEqual(panel._parse_chapter_caption("Chapter 12 — The final battle"), ("12", "The final battle"))

    def test_numbered_chapter_can_omit_caption(self):
        self.assertEqual(panel._parse_chapter_caption("Chapter 12"), ("12", ""))
        self.assertEqual(panel._parse_chapter_caption("12"), ("12", ""))

    def test_unknown_chapter_uses_na_with_optional_caption(self):
        self.assertEqual(panel._parse_chapter_caption("N/A"), ("N/A", ""))
        self.assertEqual(panel._parse_chapter_caption("N/A — Favorite panel"), ("N/A", "Favorite panel"))
        self.assertEqual(panel._parse_chapter_caption("n/a"), ("N/A", ""))

    def test_rejects_missing_chapter_and_dangling_separator(self):
        for value in ("", "   ", "chapter twelve", "Chapter 12 —", "N/A —"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                panel._parse_chapter_caption(value)


class PanelTagCatalogueTests(unittest.TestCase):
    def test_bundled_tag_groups_stay_within_discord_option_limit(self):
        self.assertLessEqual(len(panel.PANEL_TAGS), 25)
        self.assertLessEqual(len(panel.PANEL_VISUAL_TAGS), 25)

    def test_all_bundled_options_have_short_descriptions(self):
        all_tags = (*panel.PANEL_TAGS, *panel.PANEL_VISUAL_TAGS, *panel.PANEL_MANGAUPDATES_TAGS)
        self.assertEqual(len(all_tags), len(set(all_tags)))
        for tag in all_tags:
            with self.subTest(tag=tag):
                self.assertTrue(panel.PANEL_TAG_DESCRIPTIONS.get(tag))
                self.assertLessEqual(len(panel.PANEL_TAG_DESCRIPTIONS[tag]), 100)

    def test_catalogue_includes_non_adult_anilist_and_mangaupdates_tags(self):
        catalogue = dict(panel._build_panel_tag_catalogue([
            {"name": "New AniList Tag", "description": "A test description.", "isAdult": False},
            {"name": "Filtered AniList Tag", "description": "Not selectable.", "isAdult": True},
        ]))
        self.assertIn("new anilist tag", catalogue)
        self.assertNotIn("filtered anilist tag", catalogue)
        self.assertIn("doujinshi", catalogue)
        self.assertIn("shoujo ai", catalogue)
        self.assertGreater(len(catalogue), 50)
        self.assertTrue(all(len(description) <= 100 for description in catalogue.values()))

    def test_tag_values_use_discord_limit_and_support_longer_names(self):
        long_tag = "x" * 100
        self.assertEqual(panel._normalise_tag_values([long_tag]), [long_tag])
        with self.assertRaisesRegex(ValueError, "100 characters or fewer"):
            panel._normalise_tag_values(["x" * 101])

    def test_tag_parser_accepts_twenty_distinct_tags_across_both_selects(self):
        selected = ",".join((*panel.PANEL_TAGS[:10], *panel.PANEL_VISUAL_TAGS[:10]))
        self.assertEqual(len(panel._tags(selected)), 20)

    def test_tag_parser_deduplicates_and_rejects_more_than_twenty(self):
        self.assertEqual(panel._tags("action, action, romance"), ["action", "romance"])
        selected = ",".join((*panel.PANEL_TAGS[:10], *panel.PANEL_VISUAL_TAGS[:11]))
        with self.assertRaisesRegex(ValueError, "20 unique tags"):
            panel._tags(selected)


    def test_chapter_is_shown_even_when_optional_caption_is_blank(self):
        embed = panel._embed(
            {
                "id": 10,
                "title": "Example manga",
                "is_nsfw": False,
                "created_at": None,
                "attachment_url": None,
                "tags": ["action"],
                "uploader_id": 123,
                "chapter_number": "12",
                "caption": "",
                "source_url": None,
            },
            page=1,
            total=1,
            guild_name="Example server",
        )
        self.assertIn("Chapter 12", embed.description)
        self.assertIn("No caption provided", embed.description)

    def test_mature_tag_is_available_for_age_restricted_panels(self):
        self.assertIn("mature", panel.PANEL_VISUAL_TAGS)
        self.assertIn("Age-restricted", panel.PANEL_TAG_DESCRIPTIONS["mature"])

