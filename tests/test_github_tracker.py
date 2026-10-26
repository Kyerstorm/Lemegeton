"""Regression tests for commit statistics and GitHub tracker embed formatting."""
import unittest

from cogs.admin.github_tracker import GITHUB_ICON_URL, MAX_COMMIT_STATS_LOOKUPS, GitHubTracker


class GitHubCommitStatisticsTests(unittest.TestCase):
    def test_stats_render_file_count_and_coloured_diff_lines(self):
        rendered = GitHubTracker._format_commit_stats({
            "_tracker_stats": {"files_changed": 2, "additions": 37, "deletions": 12},
        })
        self.assertIn("-# 📄 2 files changed", rendered)
        self.assertIn("```diff", rendered)
        self.assertIn("+ 37 lines added", rendered)
        self.assertIn("- 12 lines deleted", rendered)

    def test_single_changed_file_uses_singular_label(self):
        rendered = GitHubTracker._format_commit_stats({
            "_tracker_stats": {"files_changed": 1, "additions": 0, "deletions": 0},
        })
        self.assertIn("1 file changed", rendered)
        self.assertNotIn("1 files changed", rendered)

    def test_missing_stats_are_reported_without_fabricated_numbers(self):
        self.assertEqual(GitHubTracker._format_commit_stats({}), "-# Change statistics unavailable")

    def test_embed_uses_github_icon_and_preserves_commit_statistics(self):
        tracker = GitHubTracker.__new__(GitHubTracker)
        tracker.repo = "owner/repo"
        tracker.branch = "multi_guild"
        commit = {
            "sha": "abcdef1234567",
            "html_url": "https://github.com/owner/repo/commit/abcdef1234567",
            "commit": {"message": "Add tracker stats", "author": {"name": "Tester", "date": "2026-01-01T00:00:00Z"}},
            "_tracker_stats": {"files_changed": 3, "additions": 21, "deletions": 4},
        }
        embed = tracker._build_commits_embed([commit])
        self.assertEqual(embed.author.icon_url, GITHUB_ICON_URL)
        self.assertIn("3 files changed", embed.description)
        self.assertIn("+ 21 lines added", embed.description)
        self.assertIn("- 4 lines deleted", embed.description)

    def test_stats_lookup_budget_is_bounded(self):
        self.assertGreater(MAX_COMMIT_STATS_LOOKUPS, 0)
        self.assertLessEqual(MAX_COMMIT_STATS_LOOKUPS, 100)

