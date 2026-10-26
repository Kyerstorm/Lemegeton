import unittest

from cogs.media.community_archives import MAX_QUOTE_LENGTH, normalize_tags, split_candidates, spoiler_wrap


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


if __name__ == "__main__":
    unittest.main()
