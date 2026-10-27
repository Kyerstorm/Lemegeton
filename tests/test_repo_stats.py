import tempfile
import unittest
from pathlib import Path

from helpers.repo_stats import collect_repository_stats, update_readme


class RepositoryStatsTests(unittest.TestCase):
    def test_counts_text_and_source_metrics_and_skips_generated_folders(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            (root / "main.py").write_text('print("ok")\n\n', encoding="utf-8")
            (root / "README.md").write_text("# Test\n\nLine two\n", encoding="utf-8")
            (root / "icon.png").write_bytes(b"\x89PNG\r\n\x00")
            (root / "node_modules").mkdir()
            (root / "node_modules" / "bundle.js").write_text("ignored()\n", encoding="utf-8")
            (root / ".venv").mkdir()
            (root / ".venv" / "ignored.py").write_text("ignored()\n", encoding="utf-8")

            stats = collect_repository_stats(root)

        self.assertEqual(stats["tracked_files"], 3)
        self.assertEqual(stats["text_files"], 2)
        self.assertEqual(stats["source_files"], 1)
        self.assertEqual(stats["source_lines"], 2)
        self.assertEqual(stats["nonblank_source_lines"], 1)
        self.assertEqual(stats["text_lines"], 5)
        self.assertEqual(stats["text_characters"], 25)
        self.assertEqual(stats["language_lines"], {"Python": 2})

    def test_readme_update_replaces_only_the_marked_block(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            (root / "main.py").write_text("print('ok')\n", encoding="utf-8")
            readme = root / "README.md"
            readme.write_text(
                "# Test README\n\n"
                "<!-- REPO-STATS:START -->\n"
                "old placeholder\n"
                "<!-- REPO-STATS:END -->\n\n"
                "Keep this note.\n",
                encoding="utf-8",
            )

            changed = update_readme(root)
            updated = readme.read_text(encoding="utf-8")

        self.assertTrue(changed)
        self.assertIn("| Tracked files | 2 |", updated)
        self.assertIn("| Source code files | 1 |", updated)
        self.assertIn("Last refreshed (UTC)", updated)
        self.assertIn("Keep this note.", updated)
        self.assertNotIn("old placeholder", updated)


if __name__ == "__main__":
    unittest.main()
