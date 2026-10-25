"""Regression batch for books/webnovels discovery, recommendations, and helper edge cases."""
import unittest
from unittest.mock import AsyncMock, patch

from cogs.media import browse as browse_module
from cogs.media.browse import BrowseCog
from cogs.media.recommendations import get_format_category, normalize_score, truncate_description
from cogs.server_management.server_config import validate_config_channel
from helpers import crypto_random


class FakeResponse:
    def __init__(self, payload=None, status=200):
        self.payload = payload
        self.status = status

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        return False

    async def json(self, *args, **kwargs):
        return self.payload


class FakeSession:
    def __init__(self, response):
        self.response = response
        self.request = None

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        return False

    def get(self, *args, **kwargs):
        self.request = (args, kwargs)
        return self.response


class MediaDiscoveryVariationTests(unittest.TestCase):
    def test_title_normalization_handles_empty_unicode_whitespace_and_apostrophes(self):
        cases = (
            (None, ""),
            ("  A\u00a0Title \n ", "a title"),
            ("O’NEIL", "o'neil"),
            ("One\tTwo   Three", "one two three"),
        )
        for source, expected in cases:
            with self.subTest(source=source):
                self.assertEqual(BrowseCog.normalize_title_search(source), expected)

    def test_best_title_match_handles_empty_query_exact_prefix_substring_and_ties(self):
        results = [
            {"titles": ["The Example: Side Story"]},
            {"titles": ["Example"]},
            {"titles": ["Example"]},
        ]
        getter = lambda item: item["titles"]
        self.assertIsNone(BrowseCog.choose_best_title_match([], "x", getter))
        self.assertIs(BrowseCog.choose_best_title_match(results, "", getter), results[0])
        self.assertIs(BrowseCog.choose_best_title_match(results, "example", getter), results[1])
        self.assertIs(BrowseCog.choose_best_title_match(results, "the example", getter), results[0])
        self.assertIs(BrowseCog.choose_best_title_match(results, "ample", getter), results[1])

    def test_title_match_accepts_scalar_titles_and_preserves_provider_order(self):
        results = [{"title": "First"}, {"title": "First"}]
        selected = BrowseCog.choose_best_title_match(results, "first", lambda item: item["title"])
        self.assertIs(selected, results[0])

    def test_fiction_classifier_handles_categories_and_nonfiction_exceptions(self):
        self.assertTrue(BrowseCog._is_fiction_book({"categories": ["Literary Fiction"]}))
        self.assertTrue(BrowseCog._is_fiction_book({"categories": ["Young Adult"]}))
        self.assertTrue(BrowseCog._is_fiction_book({"categories": ["Graphic novels"]}))
        self.assertFalse(BrowseCog._is_fiction_book({"categories": ["History", "Science"]}))
        self.assertFalse(BrowseCog._is_fiction_book({"categories": ["Non-fiction: Mystery"]}))
        self.assertFalse(BrowseCog._is_fiction_book({"categories": []}))
        self.assertFalse(BrowseCog._is_fiction_book({}))

    def test_score_normalization_covers_every_provider_score_format(self):
        cases = (
            (100, "POINT_100", 10.0),
            (87, "POINT_100", 8.7),
            (8.5, "POINT_10_DECIMAL", 8.5),
            (4, "POINT_5", 8.0),
            (2, "POINT_3", 20.0 / 3.0),
            (7, "POINT_10", 7.0),
            (7, "UNRECOGNIZED", 7.0),
            (None, "POINT_100", 0.0),
            (0, "POINT_5", 0.0),
        )
        for score, score_format, expected in cases:
            with self.subTest(score=score, score_format=score_format):
                self.assertAlmostEqual(normalize_score(score, score_format), expected)

    def test_format_category_distinguishes_novel_origins_and_fallbacks(self):
        cases = (
            ("NOVEL", None, "light_novels"),
            ("MANGA", "JP", "manga"),
            ("MANGA", "KR", "manhwa"),
            ("MANGA", "CN", "manhua"),
            ("ONE_SHOT", None, "manga"),
            ("MANHWA", None, "manhwa"),
            ("MANHUA", None, "manhua"),
            ("UNKNOWN", None, "manga"),
        )
        for fmt, country, expected in cases:
            with self.subTest(fmt=fmt, country=country):
                self.assertEqual(get_format_category(fmt, country), expected)

    def test_description_truncation_handles_empty_html_exact_and_over_limit(self):
        self.assertEqual(truncate_description(None), "No description available.")
        self.assertEqual(truncate_description("<p>Short</p>", 10), "Short")
        result = truncate_description("<p>" + ("x" * 25) + "</p>", 12)
        self.assertEqual(len(result), 12)
        self.assertTrue(result.endswith("..."))


class BookProviderFallbackTests(unittest.IsolatedAsyncioTestCase):
    async def test_goodreads_fallback_normalizes_field_variations_and_relative_links(self):
        payload = {
            "results": [
                {
                    "title": "Book One",
                    "author": ["A. Author", "B. Author"],
                    "imageUrl": "https://img.example/one.jpg",
                    "url": "/book/show/1",
                    "average_rating": "4.2",
                    "num_pages": 321,
                    "publication_year": 2020,
                },
                {"name": "Book Two", "author_name": "Writer", "image": "https://img.example/two.jpg"},
                {"title": "   "},
                None,
            ]
        }
        session = FakeSession(FakeResponse(payload))
        with patch.object(browse_module.aiohttp, "ClientSession", return_value=session):
            results = await BrowseCog(None).fetch_goodreads_results("  test title ")
        self.assertEqual(len(results), 2)
        first = results[0]["volumeInfo"]
        self.assertEqual(first["title"], "Book One")
        self.assertEqual(first["authors"], ["A. Author", "B. Author"])
        self.assertEqual(first["infoLink"], "https://www.goodreads.com/book/show/1")
        self.assertEqual(first["imageLinks"]["thumbnail"], "https://img.example/one.jpg")
        self.assertEqual(first["pageCount"], 321)
        self.assertEqual(results[1]["volumeInfo"]["authors"], ["Writer"])

    async def test_goodreads_http_failure_returns_empty_list(self):
        session = FakeSession(FakeResponse({"results": []}, status=503))
        with patch.object(browse_module.aiohttp, "ClientSession", return_value=session):
            self.assertEqual(await BrowseCog(None).fetch_goodreads_results("example"), [])

    async def test_google_books_separates_fiction_and_nonfiction(self):
        items = [
            {"volumeInfo": {"title": "Fantasy", "categories": ["Fantasy"]}},
            {"volumeInfo": {"title": "History", "categories": ["History"]}},
            {"volumeInfo": {"title": "Nonfiction mystery", "categories": ["Non-fiction: Mystery"]}},
            {"volumeInfo": {"title": "No categories", "categories": []}},
        ]
        fiction_session = FakeSession(FakeResponse({"items": items}))
        with patch.object(browse_module.aiohttp, "ClientSession", return_value=fiction_session):
            fiction = await BrowseCog(None).fetch_book_results("fantasy", "fiction")
        self.assertEqual([item["volumeInfo"]["title"] for item in fiction], ["Fantasy"])

        nonfiction_session = FakeSession(FakeResponse({"items": items}))
        with patch.object(browse_module.aiohttp, "ClientSession", return_value=nonfiction_session):
            nonfiction = await BrowseCog(None).fetch_book_results("history", "nonfiction")
        self.assertEqual(
            [item["volumeInfo"]["title"] for item in nonfiction],
            ["History", "Nonfiction mystery"],
        )

    async def test_google_books_applies_subject_and_year_bounds(self):
        session = FakeSession(FakeResponse({"items": [{"volumeInfo": {"title": "Novel", "categories": ["Fantasy"]}}]}))
        with patch.object(browse_module.aiohttp, "ClientSession", return_value=session):
            await BrowseCog(None).fetch_book_results(
                "  some   title ", "fiction", genre="Fantasy", year_from=1990, year_to=None
            )
        params = session.request[1]["params"]
        self.assertEqual(params["q"], "subject:Fantasy some title")
        self.assertEqual(params["publishedDate"], "1990..2100")
        self.assertEqual(params["printType"], "books")

    async def test_unfiltered_empty_google_books_results_use_goodreads_fallback(self):
        session = FakeSession(FakeResponse({"items": []}))
        cog = BrowseCog(None)
        with (
            patch.object(browse_module.aiohttp, "ClientSession", return_value=session),
            patch.object(cog, "fetch_goodreads_results", new=AsyncMock(return_value=[{"volumeInfo": {"title": "Fallback"}}])) as fallback,
        ):
            result = await cog.fetch_book_results("title", "fiction")
        fallback.assert_awaited_once_with("title")
        self.assertEqual(result[0]["volumeInfo"]["title"], "Fallback")

    async def test_constrained_empty_google_books_results_do_not_use_unfiltered_fallback(self):
        session = FakeSession(FakeResponse({"items": []}))
        cog = BrowseCog(None)
        with (
            patch.object(browse_module.aiohttp, "ClientSession", return_value=session),
            patch.object(cog, "fetch_goodreads_results", new=AsyncMock(return_value=[])) as fallback,
        ):
            result = await cog.fetch_book_results("title", "fiction", genre="Fantasy")
        self.assertEqual(result, [])
        fallback.assert_not_awaited()

    async def test_anilist_search_rejects_blank_query_and_handles_response_variants(self):
        cog = BrowseCog(None)
        with patch.object(browse_module, "post_graphql", new=AsyncMock()) as post:
            self.assertEqual(await cog.fetch_media("   ", "ANIME"), [])
            post.assert_not_awaited()

        session = FakeSession(FakeResponse({}))
        with (
            patch.object(browse_module.aiohttp, "ClientSession", return_value=session),
            patch.object(browse_module, "post_graphql", new=AsyncMock(return_value={"Page": {"media": [{"id": 1}]}})),
        ):
            self.assertEqual(await cog.fetch_media("  title  with whitespace ", "MANGA"), [{"id": 1}])


class CoreUtilityEdgeCases(unittest.TestCase):
    def test_secure_random_bounds_reject_invalid_values_and_handle_one(self):
        for bound in (0, -1, True, 1.5, "4", 1 << 512):
            with self.subTest(bound=bound), self.assertRaises(ValueError):
                crypto_random.secure_randbelow(bound)
        self.assertEqual(crypto_random.secure_randbelow(1), 0)

    def test_secure_randbelow_rejects_out_of_range_digest_without_modulo_bias(self):
        rejected = bytes([255]) + bytes(63)
        accepted = bytes([2]) + bytes(63)
        with (
            patch("helpers.crypto_random.secrets.token_bytes", return_value=bytes(64)),
            patch("helpers.crypto_random.hashlib.sha512") as sha512,
        ):
            sha512.return_value.digest.side_effect = [rejected, accepted]
            self.assertEqual(crypto_random.secure_randbelow(3), 2)
            self.assertEqual(sha512.call_count, 2)

    def test_secure_choice_empty_single_and_selected_indices(self):
        with self.assertRaises(IndexError):
            crypto_random.secure_choice([])
        with patch("helpers.crypto_random.secure_randbelow", return_value=0):
            self.assertEqual(crypto_random.secure_choice(["only"]), "only")
        with patch("helpers.crypto_random.secure_randbelow", return_value=2) as choose:
            self.assertEqual(crypto_random.secure_choice(["a", "b", "c"]), "c")
            choose.assert_called_once_with(3)

    def test_channel_validation_reports_each_missing_permission(self):
        permissions = {
            "view_channel": True,
            "send_messages": True,
            "embed_links": True,
        }
        channel = type(
            "TextChannel",
            (),
            {
                "guild": type("Guild", (), {"id": 123})(),
                "mention": "<#456>",
                "permissions_for": lambda _self, _member: type("Permissions", (), permissions)(),
            },
        )()
        bot_member = object()
        self.assertIsNone(validate_config_channel(channel, 123, bot_member, True))
        for missing in permissions:
            with self.subTest(permission=missing):
                changed = dict(permissions)
                changed[missing] = False
                channel.permissions_for = lambda _member, changed=changed: type("Permissions", (), changed)()
                message = validate_config_channel(channel, 123, bot_member, True)
                self.assertIsNotNone(message)
                self.assertIn(missing.replace("_", " ").title().split()[0], message)


if __name__ == "__main__":
    unittest.main()
