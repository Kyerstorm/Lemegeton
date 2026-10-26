"""Tests for multi-title comparison formatting."""
import unittest

from cogs_test.general_commands.compare import comparison_embed


class ComparisonEmbedTests(unittest.TestCase):
    def test_comparison_accepts_two_or_more_provider_records(self):
        embed = comparison_embed(
            "WEBNOVEL",
            {"title": "Novel One", "author": "Author One", "status": "Completed", "url": "https://example.org/one"},
            {"title": "Novel Two", "author": "Author Two", "status": "Ongoing", "url": "https://example.org/two"},
            {"title": "Novel Three", "author": "Author Three", "status": "Ongoing", "url": "https://example.org/three"},
        )
        self.assertIn("3 titles", embed.title)
        self.assertEqual(sum(field.name in {"Novel One", "Novel Two", "Novel Three"} for field in embed.fields), 3)
        self.assertIn("Novel Updates", embed.footer.text)


if __name__ == "__main__":
    unittest.main()
