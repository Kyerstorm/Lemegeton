"""Pure formatting tests for the TMDB season guide."""
import unittest

from cogs_test.general_commands.tv_guide import episode_line, season_embed


class TVGuideTests(unittest.TestCase):
    def test_episode_line_includes_only_provider_supplied_fields(self):
        line = episode_line({
            "episode_number": 2,
            "name": "A New Beginning",
            "air_date": "2026-11-01",
            "runtime": 42,
            "overview": "A short synopsis.",
        })
        self.assertIn("E2: A New Beginning", line)
        self.assertIn("2026-11-01", line)
        self.assertIn("42 min", line)
        self.assertIn("||A short synopsis.||", line)

    def test_missing_episode_data_uses_explicit_fallbacks(self):
        line = episode_line({})
        self.assertIn("E?: Untitled episode", line)
        self.assertIn("Date not announced", line)
        self.assertIn("||Synopsis unavailable.||", line)

    def test_season_embed_reports_pagination_and_source(self):
        episodes = [{"episode_number": index, "name": f"Episode {index}"} for index in range(1, 9)]
        embed = season_embed({"id": 4, "name": "Example Show"}, {"season_number": 1, "name": "Season 1", "episodes": episodes}, page=1)
        self.assertIn("Page 2/2", embed.footer.text)
        self.assertIn("TMDB", embed.footer.text)
        self.assertIn("Episode 7", embed.description)


if __name__ == "__main__":
    unittest.main()
