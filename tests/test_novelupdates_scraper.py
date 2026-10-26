"""Regression tests for Novel Updates' alternative search-page layouts."""
import asyncio
import unittest
from unittest.mock import AsyncMock, patch

from cogs.media.browse import (
    _NOVELUPDATES_SEARCH_CACHE,
    _novelupdates_parse_html,
    _novelupdates_results_from_helper,
    _novelupdates_search_urls,
    search_novelupdates,
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
          <div class="search_author">A. Writer</div>
          <div class="search_status">Ongoing</div>
          <div class="search_original">Royal Road</div>
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
        self.assertEqual(results[0]["author"], "A. Writer")
        self.assertEqual(results[0]["status"], "Ongoing")
        self.assertEqual(results[0]["platform"], "Royal Road")

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
                "authors": ["B. Author"],
                "statuses": ["Completed"],
                "platforms": ["Novel Updates"],
                "genres": ["Fantasy, Adventure"],
            },
        }
        results = _novelupdates_results_from_helper(payload)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["title"], "Helper Result")
        self.assertEqual(results[0]["description"], "Helper description.")
        self.assertEqual(results[0]["rating"], "4.2")
        self.assertEqual(results[0]["author"], "B. Author")
        self.assertEqual(results[0]["status"], "Completed")
        self.assertEqual(results[0]["platform"], "Novel Updates")
        self.assertEqual(results[0]["genres"], ["Fantasy", "Adventure"])

    def test_search_urls_include_encoded_fallback_routes(self):
        urls = _novelupdates_search_urls("A Novel & More")
        self.assertEqual(len(urls), 3)
        self.assertIn("sh=A+Novel+%26+More", urls[0])
        self.assertIn("post_type=series", urls[1])
        self.assertIn("sort=abc", urls[2])

    def test_empty_query_does_not_request_site(self):
        self.assertEqual(_novelupdates_search_urls("   "), [])


class NovelUpdatesSearchCacheTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        _NOVELUPDATES_SEARCH_CACHE.clear()

    async def test_successful_results_are_cached(self):
        result = [{"title": "Cached novel", "url": "https://www.novelupdates.com/series/cached-novel/"}]
        with patch("cogs.media.browse._search_novelupdates_uncached", new=AsyncMock(return_value=result)) as search:
            first = await search_novelupdates("Cache me")
            second = await search_novelupdates("  Cache me  ")
        self.assertEqual(first, result)
        self.assertEqual(second, result)
        search.assert_awaited_once()

    async def test_empty_results_are_not_cached(self):
        with patch("cogs.media.browse._search_novelupdates_uncached", new=AsyncMock(return_value=[])) as search:
            await search_novelupdates("Nothing here")
            await search_novelupdates("Nothing here")
        self.assertEqual(search.await_count, 2)

    async def test_concurrent_identical_searches_are_coalesced(self):
        result = [{"title": "One shared lookup", "url": "https://www.novelupdates.com/series/shared/"}]

        async def delayed_search(*args, **kwargs):
            await asyncio.sleep(0.01)
            return result

        with patch("cogs.media.browse._search_novelupdates_uncached", new=AsyncMock(side_effect=delayed_search)) as search:
            first, second = await asyncio.gather(
                search_novelupdates("same title"),
                search_novelupdates("same title"),
            )
        self.assertEqual(first, result)
        self.assertEqual(second, result)
        search.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()
