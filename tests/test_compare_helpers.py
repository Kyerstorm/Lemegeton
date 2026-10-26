"""Tests for multi-title comparison formatting."""
import unittest

from cogs_test.general_commands.compare import comparison_embed


class ComparisonEmbedTests(unittest.TestCase):
    def test_comparison_accepts_mixed_media_categories(self):
        embed = comparison_embed(
            ["WEBNOVEL", "MOVIE", "TV"],
            {"title": "Novel One", "author": "Writer", "url": "https://example.org/novel"},
            {"id": 2, "title": "Movie One", "release_date": "2024-01-02", "vote_average": 7.5},
            {"id": 3, "name": "Series One", "first_air_date": "2023-04-05", "number_of_seasons": 2},
        )
        self.assertIn("Cross-media Comparison", embed.title)
        names = [field.name for field in embed.fields]
        self.assertTrue(any(name.startswith("Webnovel · Novel One") for name in names))
        self.assertTrue(any(name.startswith("Movie · Movie One") for name in names))
        self.assertTrue(any(name.startswith("Tv · Series One") for name in names))

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
