"""Regression tests for the /browse book and webnovel provider paths."""

import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from cogs.media.browse import (
    BrowseCog,
    _search_novelfire_uncached,
    _search_novelphoenix_uncached,
    search_webnovels,
)


class _FakeResponse:
    def __init__(self, status=200, payload=None):
        self.status = status
        self.payload = payload or {}

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        return None

    async def json(self):
        return self.payload


class _FakeSession:
    def __init__(self, response):
        self.response = response
        self.url = None
        self.params = None

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        return None

    def get(self, url, *, params=None):
        self.url = url
        self.params = dict(params or {})
        return self.response


class BookProviderTests(unittest.IsolatedAsyncioTestCase):
    async def test_google_books_year_range_filters_published_dates(self):
        session = _FakeSession(_FakeResponse(payload={
            "items": [
                {"volumeInfo": {
                    "title": "The River Chronicle",
                    "categories": ["Fiction / Fantasy"],
                    "publishedDate": "2018-04-12",
                }},
                {"volumeInfo": {
                    "title": "An Older Chronicle",
                    "categories": ["Fiction"],
                    "publishedDate": "2004",
                }},
                {"volumeInfo": {
                    "title": "A Biography",
                    "categories": ["Non-fiction / Biography"],
                    "publishedDate": "2017-09",
                }},
                {"volumeInfo": {
                    "title": "An Undated Fiction Book",
                    "categories": ["Fiction"],
                }},
            ]
        }))
        with patch(
            "cogs.media.browse.aiohttp.ClientSession",
            return_value=session,
        ):
            results = await BrowseCog(None).fetch_book_results(
                "River Chronicle",
                "fiction",
                year_from=2010,
                year_to=2020,
            )

        self.assertEqual(
            [item["volumeInfo"]["title"] for item in results],
            ["The River Chronicle"],
        )
        self.assertNotIn("after:", session.params["q"].casefold())
        self.assertNotIn("before:", session.params["q"].casefold())

    async def test_nonfiction_results_are_not_classified_as_fiction(self):
        non_fiction = {"categories": ["Non-fiction"]}
        nonfiction_spaced = {"categories": ["Non Fiction / History"]}
        science_fiction = {"categories": ["Science Fiction"]}

        self.assertFalse(BrowseCog._is_fiction_book(non_fiction))
        self.assertFalse(BrowseCog._is_fiction_book(nonfiction_spaced))
        self.assertTrue(BrowseCog._is_nonfiction_book(nonfiction_spaced))
        self.assertTrue(BrowseCog._is_fiction_book(science_fiction))
        self.assertFalse(BrowseCog._is_nonfiction_book(science_fiction))

    async def test_publication_year_parser_accepts_google_books_date_formats(self):
        self.assertTrue(BrowseCog._book_matches_publication_year(
            {"publishedDate": "2012"}, 2010, 2015
        ))
        self.assertTrue(BrowseCog._book_matches_publication_year(
            {"publishedDate": "2012-07"}, 2010, 2015
        ))
        self.assertTrue(BrowseCog._book_matches_publication_year(
            {"publishedDate": "2012-07-30"}, 2010, 2015
        ))
        self.assertFalse(BrowseCog._book_matches_publication_year(
            {"publishedDate": "2009-12-31"}, 2010, 2015
        ))
        self.assertFalse(BrowseCog._book_matches_publication_year({}, 2010, 2015))

    async def test_constrained_google_books_failure_does_not_use_unfiltered_goodreads(self):
        session = _FakeSession(_FakeResponse(status=503))
        browse = BrowseCog(None)
        browse.fetch_goodreads_results = AsyncMock(return_value=[
            {"volumeInfo": {"title": "Unfiltered result"}}
        ])
        with patch("cogs.media.browse.aiohttp.ClientSession", return_value=session):
            results = await browse.fetch_book_results(
                "River Chronicle", "fiction", genre="Fantasy"
            )

        self.assertEqual(results, [])
        browse.fetch_goodreads_results.assert_not_awaited()

    async def test_browse_routes_general_novels_and_books_to_distinct_searches(self):
        for media_type, expected_type in (
            ("GENERAL_NOVEL", "fiction"),
            ("BOOKS", "nonfiction"),
        ):
            with self.subTest(media_type=media_type):
                browse = BrowseCog(None)
                browse.fetch_book_results = AsyncMock(return_value=[{
                    "volumeInfo": {
                        "title": "The River Chronicle",
                        "authors": ["A. Writer"],
                        "publishedDate": "2018",
                        "infoLink": "https://books.google.com/",
                    }
                }])
                interaction = SimpleNamespace(
                    response=SimpleNamespace(
                        defer=AsyncMock(),
                        send_message=AsyncMock(),
                    ),
                    followup=SimpleNamespace(send=AsyncMock()),
                    channel=SimpleNamespace(is_nsfw=lambda: False),
                )

                await BrowseCog.search.callback(
                    browse,
                    interaction,
                    SimpleNamespace(value=media_type),
                    title="The River Chronicle",
                )

                interaction.response.defer.assert_awaited_once()
                browse.fetch_book_results.assert_awaited_once_with(
                    "The River Chronicle",
                    expected_type,
                    genre=None,
                    year_from=None,
                    year_to=None,
                    author=None,
                    language=None,
                    publisher=None,
                )
                interaction.followup.send.assert_awaited_once()
                sent_embed = interaction.followup.send.await_args.kwargs["embed"]
                self.assertIn("The River Chronicle", sent_embed.title)


class WebnovelProviderTests(unittest.IsolatedAsyncioTestCase):
    async def test_one_slow_provider_does_not_discard_another_providers_results(self):
        async def slow_provider(*args, **kwargs):
            await asyncio.sleep(0.05)
            return []

        phoenix_result = [{
            "title": "The River Chronicle",
            "url": "https://novelphoenix.com/novel/the-river-chronicle/",
            "genres": ["Fantasy"],
            "source": "Novel Phoenix",
            "provider": "novelphoenix",
        }]
        with (
            patch("cogs.media.browse._WEBNOVEL_PROVIDER_TIMEOUT", 0.005),
            patch("cogs.media.browse.search_novelupdates", new=AsyncMock(side_effect=slow_provider)),
            patch("cogs.media.browse.search_novelphoenix", new=AsyncMock(return_value=phoenix_result)) as phoenix,
            patch("cogs.media.browse.search_novelfire", new=AsyncMock(return_value=[])) as fire,
            patch("cogs.media.browse.search_novelist", new=AsyncMock(return_value=[])) as novelist,
        ):
            results = await search_webnovels(
                "The River Chronicle",
                browser_fallback=False,
                max_http_urls=2,
            )

        self.assertEqual([item["title"] for item in results], ["The River Chronicle"])
        self.assertEqual(phoenix.await_args.kwargs["max_urls"], 2)
        self.assertEqual(fire.await_args.kwargs["max_urls"], 2)
        self.assertEqual(novelist.await_args.kwargs["max_urls"], 2)

    async def test_novelphoenix_browser_fallback_tries_the_second_search_route(self):
        empty = {"fields": {"cards": []}, "links": []}
        valid = {
            "url": "https://novelphoenix.com/search-adv?keyword=river",
            "fields": {"cards": ["The River Chronicle Fantasy Adventure 42 Chapters Ongoing"]},
            "links": [{
                "text": "The River Chronicle",
                "url": "https://novelphoenix.com/novel/the-river-chronicle/",
            }],
        }
        fetch = AsyncMock(side_effect=[
            dict(empty, url="https://novelphoenix.com/search?keyword=river"),
            dict(empty, url="https://novelphoenix.com/search-adv?keyword=river"),
            dict(empty, url="https://novelphoenix.com/search?keyword=river"),
            valid,
        ])
        with (
            patch("cogs.media.browse.fetch_public_page", new=fetch),
            patch(
                "cogs.media.browse._enrich_aggregator_results",
                new=AsyncMock(side_effect=lambda results, provider: results),
            ),
        ):
            results = await _search_novelphoenix_uncached(
                "The River Chronicle", max_urls=2, browser_fallback=True
            )

        self.assertEqual([item["title"] for item in results], ["The River Chronicle"])
        self.assertEqual(fetch.await_count, 4)
        self.assertEqual(
            [call.kwargs["engine"] for call in fetch.await_args_list],
            ["http", "http", "browser", "browser"],
        )

    async def test_novelfire_browser_fallback_tries_the_second_search_route(self):
        empty = {"fields": {"cards": []}, "links": []}
        valid = {
            "url": "https://novelfire.net/search?q=river",
            "fields": {"cards": ["The River Chronicle Fantasy Adventure 42 Chapters Ongoing"]},
            "links": [{
                "text": "The River Chronicle",
                "url": "https://novelfire.net/book/the-river-chronicle",
            }],
        }
        fetch = AsyncMock(side_effect=[
            dict(empty, url="https://novelfire.net/search?keyword=river"),
            dict(empty, url="https://novelfire.net/search?q=river"),
            dict(empty, url="https://novelfire.net/search?keyword=river"),
            valid,
        ])
        with (
            patch("cogs.media.browse.fetch_public_page", new=fetch),
            patch(
                "cogs.media.browse._enrich_aggregator_results",
                new=AsyncMock(side_effect=lambda results, provider: results),
            ),
        ):
            results = await _search_novelfire_uncached(
                "The River Chronicle", max_urls=2, browser_fallback=True
            )

        self.assertEqual([item["title"] for item in results], ["The River Chronicle"])
        self.assertEqual(fetch.await_count, 4)
        self.assertEqual(
            [call.kwargs["engine"] for call in fetch.await_args_list],
            ["http", "http", "browser", "browser"],
        )


if __name__ == "__main__":
    unittest.main()
