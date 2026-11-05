import unittest

from cogs.media.community_archives import (
    MAX_QUOTE_LENGTH,
    ArchiveSelectionModal,
    CommunityArchives,
    archive_scope_filter,
    normalize_tags,
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
        self.assertEqual(
            archive_scope_filter("server", 123),
            (" AND created_guild_id = ?", (123,)),
        )
        self.assertEqual(archive_scope_filter("global", 123), ("", ()))
        self.assertEqual(archive_scope_filter("server", None), ("", ()))

    def test_archive_modal_keeps_all_choices_in_one_string_select_modal(self):
        modal = ArchiveSelectionModal(None)
        self.assertEqual(len(modal.children), 3)
        fields = {item.text: item.component for item in modal.children}
        self.assertEqual(set(fields), {"🗂️ Archive", "🎞️ Related media", "⚡ Action"})
        self.assertIn("panels", {option.value for option in fields["🗂️ Archive"].options})
        self.assertIn("Anime", {option.value for option in fields["🎞️ Related media"].options})
        actions = {option.value for option in fields["⚡ Action"].options}
        self.assertTrue({"browse", "add", "search", "configure", "modlog", "review"}.issubset(actions))

    def test_archive_is_the_registered_slash_command(self):
        self.assertEqual(CommunityArchives.archive.name, "archive")


if __name__ == "__main__":
    unittest.main()
