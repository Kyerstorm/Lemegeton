"""Integration tests for the catalog-first Novel Updates search path."""
import asyncio
import csv
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from cogs.media import browse


class NovelUpdatesDatasetSearchIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        browse._NOVELUPDATES_SEARCH_CACHE.clear()
        browse._NOVELUPDATES_KEY_LOCKS.clear()
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.path = Path(self.temp_dir.name) / "novels.csv"
        with self.path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(
                handle,
                fieldnames=["Novel ID", "Name", "Associated Names", "Genres", "Completed (translation)"],
            )
            writer.writeheader()
            writer.writerow({
                "Novel ID": "10",
                "Name": "The Offline Chronicle",
                "Associated Names": "Chronicle Without Internet",
                "Genres": "Fantasy, Adventure",
                "Completed (translation)": "True",
            })

    async def test_dataset_hit_avoids_network_scraping(self):
        with patch.dict("os.environ", {"NOVELUPDATES_DATASET_PATH": str(self.path)}):
            with patch(
                "cogs.media.browse._search_novelupdates_uncached",
                new=AsyncMock(side_effect=AssertionError("live scraper should not be called on a catalog hit")),
            ) as live_search:
                results = await browse.search_novelupdates("Chronicle Without Internet")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["title"], "The Offline Chronicle")
        self.assertEqual(results[0]["metadata_source"], "novelupdates-catalog")
        live_search.assert_not_awaited()

    async def test_catalog_miss_falls_back_to_existing_live_scraper(self):
        live_result = [{
            "title": "Live Result",
            "url": "https://www.novelupdates.com/series/live-result/",
        }]
        with patch.dict("os.environ", {"NOVELUPDATES_DATASET_PATH": str(self.path)}):
            with patch(
                "cogs.media.browse._search_novelupdates_uncached",
                new=AsyncMock(return_value=live_result),
            ) as live_search:
                results = await browse.search_novelupdates("No Matching Dataset Title")
        self.assertEqual(results, live_result)
        live_search.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()
