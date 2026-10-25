"""Regression tests for the public scraper's scoped link extraction."""
import unittest

from helpers.web_scraper import _extract_page_data


class ScopedLinkExtractionTests(unittest.TestCase):
    def test_link_selector_ignores_unrelated_navigation_links(self):
        html = """
        <html><body>
          <nav><a href="/help">Help</a></nav>
          <div class="results">
            <a href="/series/example-novel/">Example Novel</a>
          </div>
        </body></html>
        """
        result = _extract_page_data(
            "https://www.novelupdates.com/series-finder/",
            html,
            {
                "include_links": True,
                "include_text": False,
                "link_selector": "a[href*='/series/']",
            },
            status_code=200,
            engine="test",
        )
        self.assertEqual(
            result["links"],
            [{
                "text": "Example Novel",
                "url": "https://www.novelupdates.com/series/example-novel/",
            }],
        )

    def test_invalid_link_selector_fails_safely(self):
        result = _extract_page_data(
            "https://example.com/",
            "<html><body><a href='/safe'>Safe</a></body></html>",
            {
                "include_links": True,
                "include_text": False,
                "link_selector": "[",
            },
            status_code=200,
            engine="test",
        )
        self.assertEqual(result["links"], [])


if __name__ == "__main__":
    unittest.main()
