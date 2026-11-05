import unittest

from cogs.media.community_archives import (
    ARCHIVE_UI_TYPES,
    DEFAULT_ARCHIVE_UPLOAD_TYPES,
    MAX_QUOTE_LENGTH,
    ArchiveAttachmentModal,
    ArchiveSelectionModal,
    ArchiveSettingsModal,
    CommunityArchives,
    allowed_archive_upload_types,
    archive_scope_filter,
    archive_upload_kind,
    normalize_archive_categories,
    normalize_tags,
    normalize_upload_types,
    split_candidates,
    spoiler_wrap,
)


class CommunityArchiveHelperTests(unittest.TestCase):
    def test_tags_are_normalized_and_deduplicated(self):
        self.assertEqual(normalize_tags("  Fantasy, fantasy, Psychological "), ["fantasy", "psychological"])
        self.assertEqual(normalize_tags(None), [])

    def test_tags_enforce_size_limits(self):
        with self.assertRaises(ValueError):
            normalize_tags(",".join(f"tag{i}" for i in range(11)))
        with self.assertRaises(ValueError):
            normalize_tags("x" * 41)

    def test_bracket_candidates_are_distinct_and_bounded(self):
        self.assertEqual(split_candidates("A | B | a"), ["A", "B"])
        with self.assertRaises(ValueError):
            split_candidates("Only one")
        with self.assertRaises(ValueError):
            split_candidates(" | ".join(f"Candidate {i}" for i in range(17)))

    def test_quote_size_and_spoiler_wrapper(self):
        self.assertEqual(MAX_QUOTE_LENGTH, 280)
        self.assertEqual(spoiler_wrap("ending revealed", True), "||ending revealed||")
        self.assertEqual(spoiler_wrap("safe caption", False), "safe caption")

    def test_archive_scope_filter_is_server_local_only_when_selected(self):
        self.assertEqual(archive_scope_filter("server", 123), (" AND created_guild_id = ?", (123,)))
        self.assertEqual(archive_scope_filter("global", 123), ("", ()))
        self.assertEqual(archive_scope_filter("server", None), ("", ()))

    def test_category_configuration_is_deduplicated_and_validated(self):
        self.assertEqual(
            normalize_archive_categories(["quotes", "quotes", "soundtracks"]),
            ["quotes", "soundtracks"],
        )
        with self.assertRaises(ValueError):
            normalize_archive_categories([])
        with self.assertRaises(ValueError):
            normalize_archive_categories(["quotes", "not-a-category"])
        self.assertEqual(len(ARCHIVE_UI_TYPES), 8)

    def test_upload_configuration_defaults_to_images_and_rejects_unknown_types(self):
        self.assertEqual(DEFAULT_ARCHIVE_UPLOAD_TYPES, ("image",))
        self.assertEqual(normalize_upload_types([]), [])
        self.assertEqual(normalize_upload_types(["audio", "video", "audio"]), ["audio", "video"])
        with self.assertRaises(ValueError):
            normalize_upload_types(["executable"])

    def test_uploads_are_restricted_by_archive_type(self):
        self.assertEqual(
            allowed_archive_upload_types("soundtracks", ["image", "audio", "video"]),
            ["audio", "video"],
        )
        self.assertEqual(
            allowed_archive_upload_types("moodboards", ["image", "audio", "video"]),
            ["image"],
        )
        self.assertEqual(allowed_archive_upload_types("recommendation-board", ["image"]), [])

    def test_upload_formats_are_classified_and_mime_checked(self):
        self.assertEqual(archive_upload_kind("theme.mp3", "audio/mpeg"), ("audio", "audio/mpeg"))
        self.assertEqual(archive_upload_kind("scene.mp4", "application/octet-stream"), ("video", "video/mp4"))
        self.assertEqual(archive_upload_kind("cover.PNG", "image/png"), ("image", "image/png"))
        with self.assertRaises(ValueError):
            archive_upload_kind("theme.exe", "application/octet-stream")
        with self.assertRaises(ValueError):
            archive_upload_kind("theme.mp3", "image/png")

    def test_archive_modal_filters_disabled_categories_but_keeps_three_select_layout(self):
        modal = ArchiveSelectionModal(None, enabled_categories=["quotes"], allow_configure=True)
        self.assertEqual(len(modal.children), 3)
        fields = {item.text: item.component for item in modal.children}
        self.assertEqual(set(fields), {"🗂️ Archive", "🎞️ Related media", "⚡ Action"})
        self.assertEqual({option.value for option in fields["🗂️ Archive"].options}, {"quotes"})
        actions = {option.value for option in fields["⚡ Action"].options}
        self.assertIn("configure", actions)

    def test_non_admin_archive_modal_hides_configuration_action(self):
        modal = ArchiveSelectionModal(None, enabled_categories=["quotes"], allow_configure=False)
        actions = {option.value for option in modal.children[2].component.options}
        self.assertNotIn("configure", actions)

    def test_archive_settings_modal_uses_two_multi_selects(self):
        settings = {"enabled_categories": ["quotes"], "upload_types": ["image", "audio"]}
        modal = ArchiveSettingsModal(None, owner_id=1, guild_id=2, settings=settings)
        self.assertEqual(len(modal.children), 2)
        self.assertEqual(modal.children[0].component.max_values, len(ARCHIVE_UI_TYPES))
        self.assertEqual(modal.children[1].component.min_values, 0)
        self.assertEqual(
            {option.value for option in modal.children[1].component.options if option.default},
            {"image", "audio"},
        )

    def test_attachment_modal_uses_one_file_upload(self):
        modal = ArchiveAttachmentModal(None, 1, 2, "soundtracks", 3, ["audio"])
        self.assertEqual(len(modal.children), 2)
        self.assertEqual(modal.children[0].component.max_values, 1)
        self.assertIn("Sharing rights", modal.children[1].text)

    def test_archive_is_the_registered_slash_command(self):
        self.assertEqual(CommunityArchives.archive.name, "archive")


if __name__ == "__main__":
    unittest.main()
