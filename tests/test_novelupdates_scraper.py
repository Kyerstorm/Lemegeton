"""Regression tests for Novel Updates' alternative search-page layouts."""
import unittest

from cogs.media.browse import (
    _novelupdates_parse_html,
    _novelupdates_results_from_helper,
    _novelupdates_search_urls,
)


BASE_URL = "https://www.novelupdates.com/series-finder/?sf=1&sh=test"


class NovelUpdatesParserTests(unittest.TestCase):
    def test_parses_standard_series_cards_and_metadata(self):
        html = """
        <div class="search_main_box_nu">
          <div class="search_title"><a href="/series/the-test-novel/">The Test Novel</a></div>
          <div class="search_body">A long description of the story.</div>
          <div class="search_ratings">4.7</div>
          <img data-src="/images/test-cover.jpg">
          <div class="search_genre"><a href="/genre/fantasy/">Fantasy</a></div>
        </div>
        """
        results = _novelupdates_parse_html(html, BASE_URL)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["title"], "The Test Novel")
        self.assertEqual(results[0]["url"], "https://www.novelupdates.com/series/the-test-novel/")
        self.assertEqual(results[0]["description"], "A long description of the story.")
        self.assertEqual(results[0]["rating"], "4.7")
        self.assertEqual(results[0]["image"], "https://www.novelupdates.com/images/test-cover.jpg")
        self.assertEqual(results[0]["genres"], ["Fantasy"])

    def test_recovers_series_links_when_card_classes_change(self):
        html = """
        <main>
          <article class="entry">
            <h2><a href="/series/another-novel/">Another Novel</a></h2>
            <p class="desc">Fallback description.</p>
          </article>
        </main>
        """
        results = _novelupdates_parse_html(html, BASE_URL)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["title"], "Another Novel")
        self.assertEqual(results[0]["description"], "Fallback description.")

    def test_rejects_non_novelupdates_and_non_series_links(self):
        html = """
        <div class="search_main_box_nu">
          <div class="search_title"><a href="https://example.com/series/fake/">Fake</a></div>
        </div>
        <a href="/genre/fantasy/">Fantasy</a>
        """
        self.assertEqual(_novelupdates_parse_html(html, BASE_URL), [])

    def test_deduplicates_series_urls_and_limits_results(self):
        html = """
        <div class="search_main_box_nu">
          <div class="search_title"><a href="/series/same-novel/">Same Novel</a></div>
        </div>
        <div class="search_main_box">
          <div class="search_title"><a href="/series/same-novel/">Same Novel</a></div>
        </div>
        """
        results = _novelupdates_parse_html(html, BASE_URL)
        self.assertEqual(len(results), 1)

    def test_http_helper_results_are_normalized(self):
        payload = {
            "url": BASE_URL,
            "links": [
                {"text": "Helper Result", "url": "https://www.novelupdates.com/series/helper-result/"},
                {"text": "Not a series", "url": "https://www.novelupdates.com/genre/fantasy/"},
            ],
            "fields": {
                "descriptions": ["Helper description."],
                "ratings": ["4.2"],
            },
        }
        results = _novelupdates_results_from_helper(payload)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["title"], "Helper Result")
        self.assertEqual(results[0]["description"], "Helper description.")
        self.assertEqual(results[0]["rating"], "4.2")

    def test_search_urls_include_encoded_fallback_routes(self):
        urls = _novelupdates_search_urls("A Novel & More")
        self.assertEqual(len(urls), 3)
        self.assertIn("sh=A+Novel+%26+More", urls[0])
        self.assertIn("post_type=series", urls[1])
        self.assertIn("sort=abc", urls[2])

    def test_empty_query_does_not_request_site(self):
        self.assertEqual(_novelupdates_search_urls("   "), [])


if __name__ == "__main__":
    unittest.main()
