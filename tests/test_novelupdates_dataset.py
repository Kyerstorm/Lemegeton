"""Tests for the optional local Novel Updates dataset integration."""
import csv
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from helpers import novelupdates_dataset as dataset


class NovelUpdatesDatasetTests(unittest.TestCase):
    def setUp(self):
        dataset._CACHE.clear()
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.root = Path(self.temp_dir.name)

    def write_csv(self, rows):
        path = self.root / "novels.csv"
        columns = list(rows[0])
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=columns)
            writer.writeheader()
            writer.writerows(rows)
        return path

    def test_csv_search_normalizes_dataset_fields_and_links_to_source_search(self):
        path = self.write_csv([{
            "Novel ID": "101",
            "Name": "The Glass Archive",
            "Novel Type": "Web Novel",
            "Associated Names": "Glass Archive|The Archive of Glass",
            "Original Langauge": "Chinese",
            "Author / Authors": "A. Writer",
            "Genres": "Fantasy, Mystery",
            "Tags": "Magic, Investigation",
            "Start Year": "2020",
            "Licensed": "False",
            "Number of Chapters (original language)": "900",
            "Completed (original language)": "True",
            "Number of Chapters (translation)": "415",
            "Completed (translation)": "False",
            "Release Frequency": "Daily",
            "Activity All-time Rank": "12",
            "On Number of Reading Lists": "2200",
            "Rating": "4.6",
            "Rating Votes": "350",
        }])

        results = dataset.search_novelupdates_dataset("archive of glass", path=str(path))
        self.assertEqual(len(results), 1)
        novel = results[0]
        self.assertEqual(novel["title"], "The Glass Archive")
        self.assertEqual(novel["url"], "https://www.novelupdates.com/series-finder/?sf=1&sh=The+Glass+Archive")
        self.assertEqual(novel["genres"], ["Fantasy", "Mystery"])
        self.assertEqual(novel["tags"], ["Magic", "Investigation"])
        self.assertEqual(novel["original_language"], "Chinese")
        self.assertEqual(novel["original_chapters"], "900")
        self.assertEqual(novel["translated_chapters"], "415")
        self.assertEqual(novel["translation_completed"], False)
        self.assertEqual(novel["original_completed"], True)
        self.assertEqual(novel["reading_lists"], "2200")
        self.assertEqual(novel["metadata_source"], "novelupdates-catalog")

    def test_json_relations_resolve_ids_without_guessing_series_urls(self):
        path = self.root / "novels.json"
        path.write_text(json.dumps({
            "novels": [
                {
                    "novel_id": 12,
                    "name": "The First Chronicle",
                    "Recommended Series IDs": "[13]",
                    "Related Series IDs": "13",
                    "Genres": ["Fantasy"],
                },
                {
                    "novel_id": 13,
                    "name": "The Second Chronicle",
                    "Genres": ["Fantasy", "Adventure"],
                    "Cover Image URL": "https://example.org/cover.jpg",
                },
            ]
        }), encoding="utf-8")

        results = dataset.search_novelupdates_dataset("The First Chronicle", path=str(path))
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["recommended_series"], [{
            "title": "The Second Chronicle",
            "url": "https://www.novelupdates.com/series-finder/?sf=1&sh=The+Second+Chronicle",
            "dataset_id": "13",
        }])
        self.assertEqual(results[0]["related_series"][0]["title"], "The Second Chronicle")
        self.assertEqual(results[0]["image"], "https://example.org/cover.jpg")

    def test_dataset_filters_genreless_rows_and_rejects_unmatched_queries(self):
        path = self.write_csv([
            {"Novel ID": "1", "Name": "A Title With Genres", "Genres": "Fantasy"},
            {"Novel ID": "2", "Name": "A Title Without Genres", "Genres": ""},
        ])
        results = dataset.search_novelupdates_dataset("A Title", path=str(path), require_genres=True)
        self.assertEqual([item["title"] for item in results], ["A Title With Genres"])
        self.assertEqual(dataset.search_novelupdates_dataset("completely unrelated", path=str(path)), [])

    def test_missing_or_unsupported_dataset_returns_empty_results(self):
        self.assertEqual(dataset.search_novelupdates_dataset("Example", path=str(self.root / "missing.json")), [])
        unsupported = self.root / "novels.txt"
        unsupported.write_text("not data", encoding="utf-8")
        self.assertEqual(dataset.search_novelupdates_dataset("Example", path=str(unsupported)), [])

    def test_invalid_cover_and_non_novelupdates_permalink_are_not_trusted(self):
        path = self.write_csv([{
            "Novel ID": "7",
            "Name": "Safe Title",
            "Cover Image URL": "javascript:alert(1)",
            "URL": "https://example.com/series/fake/",
        }])
        novel = dataset.search_novelupdates_dataset("Safe Title", path=str(path))[0]
        self.assertIsNone(novel["image"])
        self.assertEqual(novel["url"], "https://www.novelupdates.com/series-finder/?sf=1&sh=Safe+Title")

    def test_conventional_path_is_used_only_when_file_exists(self):
        custom = self.root / "custom.csv"
        custom.write_text("Name\nAn Example\n", encoding="utf-8")
        with patch.dict("os.environ", {"NOVELUPDATES_DATASET_PATH": str(custom)}):
            self.assertEqual(dataset.get_novelupdates_dataset_path(), str(custom))
            self.assertTrue(dataset.novelupdates_dataset_enabled())


if __name__ == "__main__":
    unittest.main()
