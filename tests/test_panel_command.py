"""Focused regression tests for manga panel metadata and tag selection."""
import unittest
from unittest import mock

from cogs.media import panel


class PanelModalComponentTests(unittest.TestCase):
    def test_modal_labels_and_descriptions_fit_discord_limits(self):
        modal = panel.PanelForm(None, mode="add", user_id=1, guild_id=1)
        for item in modal.children:
            with self.subTest(label=item.text):
                self.assertLessEqual(len(item.text), 45)
                if item.description:
                    self.assertLessEqual(len(item.description), 100)


class PanelArchiveActionTests(unittest.IsolatedAsyncioTestCase):
    async def test_browse_routes_through_the_existing_panel_browser(self):
        cog = panel.PanelCog(mock.MagicMock())
        interaction = mock.MagicMock()
        with mock.patch.object(cog, "_safe_home_action", new_callable=mock.AsyncMock) as action:
            await cog.handle_archive_action(interaction, "browse")
        action.assert_awaited_once_with(interaction, "browse")

    async def test_search_opens_the_existing_panel_search_modal(self):
        cog = panel.PanelCog(mock.MagicMock())
        interaction = mock.MagicMock()
        interaction.response.send_modal = mock.AsyncMock()
        await cog.handle_archive_action(interaction, "search")
        interaction.response.send_modal.assert_awaited_once()
        self.assertIsInstance(
            interaction.response.send_modal.await_args.args[0],
            panel.PanelSearchModal,
        )


class PanelArchiveConfigurationTests(unittest.TestCase):
    def test_configure_modal_exposes_the_global_or_server_archive_select(self):
        modal = panel.PanelConfigureModal(None, owner_id=10, guild_id=20, archive_scope="server")
        visibility = next(item for item in modal.children if item.text == "Community archive visibility")
        self.assertEqual([option.value for option in visibility.component.options], ["global", "server"])
        self.assertFalse(visibility.component.options[0].default)
        self.assertTrue(visibility.component.options[1].default)


    def test_archive_storage_channel_is_optional_when_s3_is_configured(self):
        modal = panel.PanelConfigureModal(None, owner_id=1, guild_id=2)
        storage = next(item for item in modal.children if item.text.startswith("Media storage channel"))
        self.assertFalse(storage.component.required)


class SharedPanelArchiveSettingsTests(unittest.IsolatedAsyncioTestCase):
    async def test_missing_archive_settings_keep_legacy_panel_uploads_enabled(self):
        with mock.patch.object(
            panel.database, "execute_db_operation", new_callable=mock.AsyncMock, return_value=None,
        ):
            self.assertEqual(await panel._shared_panel_archive_availability(10), (True, True))

    async def test_server_can_disable_panels_or_panel_image_uploads(self):
        with mock.patch.object(
            panel.database, "execute_db_operation", new_callable=mock.AsyncMock,
            return_value=('["quotes"]', '["audio"]'),
        ):
            self.assertEqual(await panel._shared_panel_archive_availability(10), (False, False))

    async def test_enabled_panels_can_keep_image_uploads_without_audio(self):
        with mock.patch.object(
            panel.database, "execute_db_operation", new_callable=mock.AsyncMock,
            return_value=('["panels", "quotes"]', '["image"]'),
        ):
            self.assertEqual(await panel._shared_panel_archive_availability(10), (True, True))


class PrivatePanelStorageChannelTests(unittest.TestCase):
    def test_rejects_storage_channels_visible_to_everyone(self):
        class FakeChannel:
            def __init__(self, public_access):
                self.guild = mock.MagicMock()
                self.guild.me = object()
                self.guild.default_role = object()
                self.public_role = self.guild.default_role
                self.public_access = public_access

            def permissions_for(self, role):
                if role is self.public_role:
                    return mock.Mock(view_channel=self.public_access)
                return mock.Mock(view_channel=True, send_messages=True, attach_files=True)

        self.assertTrue(panel._is_private_storage_channel(FakeChannel(False)))
        self.assertFalse(panel._is_private_storage_channel(FakeChannel(True)))


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

    def test_tag_search_matches_names_case_insensitively(self):
        catalogue = (
            ("fantasy", "Magic or mythical worlds."),
            ("kingdom building", "A story about establishing a realm."),
            ("time travel", "Temporal travel and changing timelines."),
        )
        self.assertEqual(
            panel._search_panel_tag_catalogue(catalogue, " KINGDOM "),
            (("kingdom building", "A story about establishing a realm."),),
        )

    def test_tag_search_matches_descriptions_and_empty_query(self):
        catalogue = (
            ("fantasy", "Magic or mythical worlds."),
            ("kingdom building", "A story about establishing a realm."),
        )
        self.assertEqual(
            panel._search_panel_tag_catalogue(catalogue, "MYTHICAL"),
            (("fantasy", "Magic or mythical worlds."),),
        )
        self.assertEqual(panel._search_panel_tag_catalogue(catalogue, "  "), catalogue)
        self.assertEqual(panel._search_panel_tag_catalogue(catalogue, "not-a-tag"), ())

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


class _FakeConn:
    def __init__(self, n: int):
        self.n = n
        self.calls: list[tuple] = []

    async def fetchrow(self, sql, *args):
        self.calls.append((sql, args))
        return {"n": self.n}


class _FakeAcquire:
    def __init__(self, conn):
        self.conn = conn

    async def __aenter__(self):
        return self.conn

    async def __aexit__(self, *exc):
        return False


class _FakePool:
    def __init__(self, conn):
        self.conn = conn

    def acquire(self):
        return _FakeAcquire(self.conn)


class PanelArchiveAgeGateTests(unittest.IsolatedAsyncioTestCase):
    """Panel queries continue to apply the channel age gate."""

    async def test_guild_count_query_applies_the_age_gate(self):
        conn = _FakeConn(n=3)
        with mock.patch.object(panel, "_pool", mock.AsyncMock(return_value=_FakePool(conn))):
            total = await panel._count_from_guild(20, False)
        self.assertEqual(total, 3)
        sql, args = conn.calls[0]
        self.assertIn("is_nsfw=FALSE", sql)
        self.assertEqual(args, (20, False))


class PanelCogLoadTests(unittest.IsolatedAsyncioTestCase):
    async def test_schema_failure_still_registers_the_context_menu(self):
        bot = mock.MagicMock()
        cog = panel.PanelCog(bot)
        with mock.patch.object(panel, "_schema", mock.AsyncMock(side_effect=RuntimeError("db down"))):
            await cog.cog_load()
        bot.tree.add_command.assert_called_once_with(cog.save_menu, override=True)

