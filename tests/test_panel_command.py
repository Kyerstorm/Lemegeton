"""Focused regression tests for manga panel metadata and tag selection."""
import unittest

from cogs.media import panel


class PanelModalComponentTests(unittest.TestCase):
    def test_modal_labels_and_descriptions_fit_discord_limits(self):
        modal = panel.PanelForm(None, mode="add", user_id=1, guild_id=1)
        for item in modal.children:
            with self.subTest(label=item.text):
                self.assertLessEqual(len(item.text), 45)
                if item.description:
                    self.assertLessEqual(len(item.description), 100)


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

    def test_catalogue_is_hand_curated_static_and_extensive(self):
        catalogue = dict(panel._build_panel_tag_catalogue())
        self.assertGreaterEqual(len(catalogue), 350)
        self.assertIn("4-koma", catalogue)
        self.assertIn("achromatic", catalogue)
        self.assertIn("kingdom building", catalogue)
        self.assertIn("doujinshi", catalogue)
        self.assertIn("shoujo ai", catalogue)
        self.assertTrue(all(len(description) <= 100 for description in catalogue.values()))
        self.assertEqual(len(catalogue), len(set(catalogue)))

    def test_catalogue_does_not_use_the_anilist_api(self):
        self.assertFalse(hasattr(panel, "ANILIST_TAG_QUERY"))
        self.assertFalse(hasattr(panel, "_panel_tag_catalogue"))

    def test_tag_values_use_discord_limit_and_support_longer_names(self):
        long_tag = "x" * 100
        self.assertEqual(panel._normalise_tag_values([long_tag]), [long_tag])
        with self.assertRaisesRegex(ValueError, "100 characters or fewer"):
            panel._normalise_tag_values(["x" * 101])

    def test_nsfw_and_mature_tags_are_age_restricted(self):
        catalogue = dict(panel._build_panel_tag_catalogue())
        self.assertIn("nsfw", catalogue)
        self.assertIn("mature", catalogue)
        self.assertIn("NSFW channels", catalogue["nsfw"])
        self.assertTrue(panel._tags_require_nsfw(["nsfw"]))
        self.assertTrue(panel._tags_require_nsfw(["mature"]))
        self.assertTrue(panel._tags_require_nsfw(["NSFW"]))
        self.assertFalse(panel._tags_require_nsfw(["action", "romance"]))

    def test_tag_parser_accepts_twenty_five_distinct_tags_across_pages(self):
        selected = ",".join((*panel.PANEL_TAGS[:15], *panel.PANEL_VISUAL_TAGS[:10]))
        self.assertEqual(len(panel._tags(selected)), 25)

    def test_tag_parser_deduplicates_and_rejects_more_than_twenty_five(self):
        self.assertEqual(panel._tags("action, action, romance"), ["action", "romance"])
        selected = ",".join((*panel.PANEL_TAGS[:16], *panel.PANEL_VISUAL_TAGS[:10]))
        with self.assertRaisesRegex(ValueError, "25 unique tags"):
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

