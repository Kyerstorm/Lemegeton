"""Focused tests for Novel Phoenix result parsing and safe metadata filtering."""
import unittest

from helpers.novelphoenix import is_safe_novel_record, parse_novelphoenix_html


class NovelPhoenixParsingTests(unittest.TestCase):
    def test_parses_safe_novel_metadata_and_chapter_count(self):
        html = """
        <article class="novel-card">
          <a class="novel-title" href="/novel/the-glass-archive">The Glass Archive</a>
          <img src="https://novelphoenix.com/covers/glass.jpg">
          <div class="genres">
            <a href="/genre-fantasy">Fantasy</a>
            <a href="/genre-mystery">Mystery</a>
          </div>
          <div class="author">A. Writer</div>
          <div class="status">Ongoing</div>
          <div class="rating">4.6</div>
          <p class="summary">An archive of unusual discoveries.</p>
          <span>415 Chapters</span>
        </article>
        """
        results = parse_novelphoenix_html(html)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["title"], "The Glass Archive")
        self.assertEqual(results[0]["url"], "https://novelphoenix.com/novel/the-glass-archive")
        self.assertEqual(results[0]["author"], "A. Writer")
        self.assertEqual(results[0]["genres"], ["Fantasy", "Mystery"])
        self.assertEqual(results[0]["translated_chapters"], "415")
        self.assertEqual(results[0]["provider"], "Novel Phoenix")

    def test_filters_adult_labelled_records(self):
        html = """
        <article class="novel-card">
          <a href="/novel/flagged-title">Flagged Title</a>
          <div class="genres">
            <a href="/genre-fantasy">Fantasy</a>
            <a href="/genre-adult">Adult</a>
          </div>
        </article>
        """
        self.assertEqual(parse_novelphoenix_html(html), [])

    def test_skips_records_without_visible_genre_evidence(self):
        html = """
        <article class="novel-card">
          <a href="/novel/no-categories">No Categories</a>
          <p>Some summary text</p>
        </article>
        """
        self.assertEqual(parse_novelphoenix_html(html), [])

    def test_rejects_external_novel_links(self):
        html = """
        <article class="novel-card">
          <a href="https://example.com/novel/external">External Title</a>
          <div class="genres"><a href="/genre-fantasy">Fantasy</a></div>
        </article>
        """
        self.assertEqual(parse_novelphoenix_html(html), [])

    def test_generic_safety_filter_reads_tags_and_categories(self):
        self.assertFalse(is_safe_novel_record({"genres": ["Fantasy"], "tags": ["Smut"]}))
        self.assertFalse(is_safe_novel_record({"categories": ["Mature"]}))
        self.assertFalse(is_safe_novel_record({"genres": ["Fantasy"]}, require_genres=True))
        self.assertTrue(is_safe_novel_record({"genres": ["Fantasy", "Mystery"]}, require_genres=True))


if __name__ == "__main__":
    unittest.main()
