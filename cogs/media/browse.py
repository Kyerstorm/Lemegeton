from helpers.color_palette import PALETTE
import discord
from helpers.command_error_handler import application_error_message, FeedbackAwareView
from discord.ext import commands
from discord import app_commands
import aiohttp
import asyncio
from bs4 import BeautifulSoup
import logging
import os
import time
from typing import List, Dict, Optional, Tuple
from urllib.parse import quote_plus, urljoin, urlsplit
from botasaurus.browser import browser as botasaurus_browser, Driver, Wait
from helpers.web_scraper import (
    fetch_public_page, ScrapeBlockedError, ScrapeRequestError, detect_access_challenge,
)
from discord.ui import Button
from database import get_all_users_guild_aware
from helpers.embed_helper import build_error_embed, build_info_embed
from helpers.anilist_helper import post_graphql
from cogs_test.general_commands.dashboard import command_meta

logger = logging.getLogger("BrowseCog")
GOOGLE_BOOKS_URL = "https://www.googleapis.com/books/v1/volumes"
GOODREADS_AUTOCOMPLETE_URL = "https://www.goodreads.com/book/auto_complete"
TMDB_API_BASE_URL = "https://api.themoviedb.org/3"
TMDB_IMAGE_BASE_URL = "https://image.tmdb.org/t/p"
MDBLIST_API_BASE_URL = "https://api.mdblist.com"
_NOVELUPDATES_CACHE_TTL = 300
_NOVELUPDATES_SEARCH_CACHE: Dict[tuple, tuple[float, List[Dict]]] = {}
_NOVELUPDATES_CACHE_LOCK = asyncio.Lock()


def _novelupdates_search_urls(query: str) -> List[str]:
    """Known public Novel Updates search routes, ordered from most to least targeted."""
    query = " ".join((query or "").split())
    if not query:
        return []
    term = quote_plus(query)
    return [
        f"https://www.novelupdates.com/series-finder/?sf=1&sh={term}&sort=sdate&order=desc",
        f"https://www.novelupdates.com/?s={term}&post_type=series",
        f"https://www.novelupdates.com/series-finder/?sf=1&sh={term}&sort=abc&order=asc",
    ]


def _novelupdates_is_series_url(url: str, base_url: str) -> bool:
    """Accept only Novel Updates series URLs, not genre links or site navigation."""
    target = urljoin(base_url, url or "")
    parts = urlsplit(target)
    host = (parts.hostname or "").lower().rstrip(".")
    return (
        parts.scheme in ("http", "https")
        and (host == "novelupdates.com" or host.endswith(".novelupdates.com"))
        and "/series/" in parts.path.lower()
    )


def _novelupdates_title_anchor(card):
    """Find a title anchor across the known and fallback Novel Updates layouts."""
    selectors = (
        ".search_title a[href]",
        ".series_title a[href]",
        ".search_result_title a[href]",
        "a.search_title[href]",
        "a[href*='/series/']",
    )
    for selector in selectors:
        try:
            anchor = card.select_one(selector)
        except Exception:
            anchor = None
        if anchor and anchor.get("href"):
            return anchor
    if getattr(card, "name", None) == "a" and card.get("href"):
        return card
    return None


def _novelupdates_parse_html(html: str, base_url: str) -> List[Dict]:
    """Parse series metadata from normal cards, alternate cards, or bare series links."""
    if not html:
        return []
    soup = BeautifulSoup(html, "html.parser")
    card_selectors = (
        ".search_main_box_nu",
        ".search_main_box",
        ".search_result",
        ".series_result",
        "article",
    )
    cards = []
    for selector in card_selectors:
        try:
            candidates = soup.select(selector)
        except Exception:
            candidates = []
        if any(_novelupdates_title_anchor(card) for card in candidates):
            cards = candidates
            break

    # If the wrapper classes changed, recover directly from series links and climb
    # to a nearby card for any available description/rating/image metadata.
    if not cards:
        recovered = []
        seen_links = set()
        for anchor in soup.select("a[href*='/series/']"):
            href = anchor.get("href") or ""
            if not _novelupdates_is_series_url(href, base_url):
                continue
            target = urljoin(base_url, href).rstrip("/")
            if target in seen_links:
                continue
            seen_links.add(target)
            card = (
                anchor.find_parent("div", class_="search_main_box_nu")
                or anchor.find_parent("div", class_="search_main_box")
                or anchor.find_parent("article")
                or anchor.parent
                or anchor
            )
            recovered.append((card, anchor))
        entries = recovered
    else:
        entries = [(card, _novelupdates_title_anchor(card)) for card in cards]

    novels = []
    seen_urls = set()
    for card, title_link in entries:
        if not title_link:
            continue
        href = (title_link.get("href") or "").strip()
        if not _novelupdates_is_series_url(href, base_url):
            continue
        url = urljoin(base_url, href).split("#", 1)[0]
        dedupe_url = url.rstrip("/").casefold()
        if dedupe_url in seen_urls:
            continue

        title = " ".join(title_link.get_text(" ", strip=True).split())
        if not title:
            title = " ".join(str(
                title_link.get("title") or title_link.get("aria-label") or ""
            ).split())
        if not title:
            slug = urlsplit(url).path.rstrip("/").split("/")[-1]
            title = slug.replace("-", " ").replace("_", " ").strip()
        if not title:
            continue

        def first_text(*selectors: str) -> Optional[str]:
            for selector in selectors:
                try:
                    node = card.select_one(selector)
                except Exception:
                    node = None
                if node:
                    value = " ".join(node.get_text(" ", strip=True).split())
                    if value:
                        return value[:4000]
            return None

        description = first_text(
            ".search_body", ".search_body_nu", ".search_desc",
            ".series_synopsis", ".desc", "[class*='description']",
        )
        rating = first_text(".search_ratings", ".search_rating", ".rating")
        author = first_text(".search_author", ".series_author", "[class*='author']")
        status = first_text(".search_status", ".series_status", "[class*='status']")
        image_url = None
        image_node = None
        try:
            image_node = card.select_one("img[src], img[data-src], img[data-lazy-src], img[srcset]")
        except Exception:
            pass
        if image_node:
            image_value = (
                image_node.get("data-src")
                or image_node.get("data-lazy-src")
                or image_node.get("src")
                or image_node.get("srcset")
                or ""
            ).strip()
            if image_value:
                image_url = urljoin(base_url, image_value.split(",", 1)[0].split(" ", 1)[0])

        genres = []
        try:
            genre_nodes = card.select(
                ".search_genre a, .search_genres a, a[href*='/genre/']"
            )
        except Exception:
            genre_nodes = []
        for node in genre_nodes:
            genre = " ".join(node.get_text(" ", strip=True).split())
            if genre and genre.casefold() not in {item.casefold() for item in genres}:
                genres.append(genre)

        novels.append({
            "title": title[:256],
            "url": url,
            "description": description,
            "image": image_url,
            "rating": rating,
            "author": author,
            "status": status,
            "genres": genres,
        })
        seen_urls.add(dedupe_url)
        if len(novels) >= 10:
            break

    return novels


def _novelupdates_results_from_helper(payload: Dict) -> List[Dict]:
    """Normalize the web-scraper helper's scoped links and parallel text fields."""
    fields = payload.get("fields") or {}

    def field_at(name: str, index: int) -> Optional[str]:
        value = fields.get(name)
        if isinstance(value, str):
            return value if index == 0 else None
        if isinstance(value, list) and index < len(value):
            text_value = " ".join(str(value[index]).split())
            return text_value or None
        return None

    results = []
    seen_urls = set()
    for link in payload.get("links") or []:
        href = str(link.get("url") or "").strip()
        if not _novelupdates_is_series_url(href, payload.get("url") or "https://www.novelupdates.com/"):
            continue
        url = urljoin(payload.get("url") or "https://www.novelupdates.com/", href).split("#", 1)[0]
        normalized_url = url.rstrip("/").casefold()
        if normalized_url in seen_urls:
            continue
        title = " ".join(str(link.get("text") or "").split())
        index = len(results)
        if not title:
            title = field_at("titles", index) or ""
        if not title:
            slug = urlsplit(url).path.rstrip("/").split("/")[-1]
            title = slug.replace("-", " ").replace("_", " ").strip()
        if not title:
            continue
        results.append({
            "title": title[:256],
            "url": url,
            "description": field_at("descriptions", index),
            "image": field_at("images", index),
            "rating": field_at("ratings", index),
            "author": field_at("authors", index),
            "status": field_at("statuses", index),
            "genres": [part.strip() for part in (field_at("genres", index) or "").split(",") if part.strip()],
        })
        seen_urls.add(normalized_url)
        if len(results) >= 10:
            break
    return results


@botasaurus_browser(
    headless=True,
    max_retry=1,
    retry_wait=1,
    create_error_logs=False,
    raise_exception=True,
    close_on_crash=True,
)
def scrape_novelupdates(driver: Driver, data: Dict) -> List[Dict]:
    """Browser fallback for public Novel Updates search pages using multiple layouts."""
    query = " ".join(str(data.get("query") or "").split())
    urls = data.get("urls") or _novelupdates_search_urls(query)
    successful_page_loads = 0
    route_errors = []
    for route_index, url in enumerate(urls):
        try:
            driver.get(url)
        except Exception as exc:
            html = driver.page_html or ""
            challenge = detect_access_challenge(None, html)
            if challenge:
                raise ScrapeBlockedError(
                    f"Novel Updates stopped the browser search ({challenge})."
                ) from exc
            route_errors.append(f"{url}: {exc}")
            logger.warning("Novel Updates browser route failed for %s: %s", url, exc)
            continue
        successful_page_loads += 1
        html = driver.page_html or ""
        challenge = detect_access_challenge(None, html)
        if challenge:
            raise ScrapeBlockedError(
                f"Novel Updates stopped the browser search ({challenge})."
            )
        if route_index == 0:
            # Give the preferred route time to render its usual result container;
            # other routes stay non-blocking and are parsed through generic anchors.
            try:
                driver.select_all(".search_main_box_nu", wait=Wait.LONG)
            except Exception:
                pass
            html = driver.page_html or html
            challenge = detect_access_challenge(None, html)
            if challenge:
                raise ScrapeBlockedError(
                    f"Novel Updates stopped the browser search ({challenge})."
                )
        results = _novelupdates_parse_html(html, url)
        if results:
            logger.info(
                "Novel Updates browser search returned %s results for %r at %s",
                len(results), query, url,
            )
            return results
        page_text = BeautifulSoup(html, "html.parser").get_text(" ", strip=True)
        logger.debug(
            "Novel Updates layout produced no series links for %r at %s; page text: %s",
            query, url, page_text[:250],
        )
    if successful_page_loads == 0:
        raise ScrapeRequestError(
            "Botasaurus could not load any Novel Updates search route. "
            + "; ".join(route_errors[:3])
        )
    logger.info("Novel Updates returned no series links for query %r after %s routes", query, len(urls))
    return []


async def _search_novelupdates_uncached(
    query: str,
    *,
    browser_fallback: bool = True,
    http_timeout: int = 7,
    max_http_urls: int = 2,
    require_genres: bool = False,
) -> List[Dict]:
    """Use the shared HTTP scraper first, then Botasaurus for browser-rendered markup."""
    query = " ".join((query or "").split())
    urls = _novelupdates_search_urls(query)
    if not urls:
        return []

    selectors = {
        "titles": ".search_main_box_nu .search_title a, .search_main_box .search_title a, "
                  ".search_title a, a[href*='/series/']",
        "descriptions": ".search_body, .search_body_nu, .search_desc, .series_synopsis",
        "ratings": ".search_ratings, .search_rating, .rating",
        "authors": ".search_author, .series_author, [class*='author']",
        "statuses": ".search_status, .series_status, [class*='status']",
        "genres": ".search_genre a, .search_genres a, a[href*='/genre/']",
        "images": ".search_main_box_nu img, .search_main_box img, article img",
    }
    for url in urls[:max(1, min(max_http_urls, len(urls)))]:
        try:
            payload = await fetch_public_page(
                url,
                engine="http",
                selectors=selectors,
                include_text=False,
                include_links=True,
                link_selector="a[href*='/series/']",
                timeout=max(1, min(int(http_timeout), 10)),
                retries=0,
            )
        except ScrapeBlockedError:
            # A challenge/rate limit is a hard stop; do not retry the page through
            # another engine or attempt to evade the site's access controls.
            raise
        except (ScrapeRequestError, ValueError) as exc:
            logger.debug("Novel Updates HTTP route failed for %s: %s", url, exc)
            continue
        except Exception:
            logger.exception("Unexpected Novel Updates HTTP scraper failure for %s", url)
            continue
        results = _novelupdates_results_from_helper(payload)
        if results and (not require_genres or any(item.get("genres") for item in results)):
            logger.info(
                "Novel Updates HTTP search returned %s results for %r at %s",
                len(results), query, url,
            )
            return results

    if not browser_fallback:
        return []
    return await asyncio.to_thread(
        scrape_novelupdates, {"query": query, "urls": urls}, output=None
    )


async def search_novelupdates(
    query: str,
    *,
    browser_fallback: bool = True,
    http_timeout: int = 7,
    max_http_urls: int = 2,
    require_genres: bool = False,
) -> List[Dict]:
    """Cache successful Novel Updates searches briefly; never cache provider failures."""
    normalized = " ".join((query or "").split())
    if not normalized:
        return []
    key = (normalized.casefold(), bool(browser_fallback), max(1, min(int(max_http_urls), 3)), bool(require_genres))
    now = time.monotonic()
    cached = _NOVELUPDATES_SEARCH_CACHE.get(key)
    if cached and cached[0] > now:
        return [dict(item) for item in cached[1]]
    results = await _search_novelupdates_uncached(
        normalized,
        browser_fallback=browser_fallback,
        http_timeout=http_timeout,
        max_http_urls=max_http_urls,
        require_genres=require_genres,
    )
    if results:
        async with _NOVELUPDATES_CACHE_LOCK:
            now = time.monotonic()
            expired = [cache_key for cache_key, value in _NOVELUPDATES_SEARCH_CACHE.items() if value[0] <= now]
            for cache_key in expired:
                _NOVELUPDATES_SEARCH_CACHE.pop(cache_key, None)
            _NOVELUPDATES_SEARCH_CACHE[key] = (now + _NOVELUPDATES_CACHE_TTL, [dict(item) for item in results])
    return results


# Status order priority
STATUS_ORDER = {
    "REPEATING": 0,
    "COMPLETED": 1,
    "READING": 2,
    "PAUSED": 3,
    "DROPPED": 4,
    "PLANNING": 5,
    None: 6
}


class BrowseCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @staticmethod
    def normalize_title_search(value: Optional[str]) -> str:
        """Normalize whitespace and Unicode apostrophes for provider title matching."""
        return " ".join(str(value or "").replace("’", "'").casefold().split())

    @classmethod
    def choose_best_title_match(cls, results: List[Dict], query: str, title_getter):
        """Prefer exact/close title matches while preserving provider order for ties."""
        if not results:
            return None
        wanted = cls.normalize_title_search(query)
        if not wanted:
            return results[0]
        ranked = []
        for index, item in enumerate(results):
            titles = title_getter(item)
            if not isinstance(titles, (tuple, list, set)):
                titles = [titles]
            normalized = [cls.normalize_title_search(title) for title in titles if title]
            rank = 3
            if wanted in normalized:
                rank = 0
            elif any(title.startswith(wanted) for title in normalized):
                rank = 1
            elif any(wanted in title for title in normalized):
                rank = 2
            ranked.append((rank, index, item))
        return min(ranked, key=lambda result: (result[0], result[1]))[2]

    @staticmethod
    def _is_fiction_book(book: Dict) -> bool:
        """Recognize common fiction labels and genres in Google Books metadata."""
        fiction_markers = (
            "fiction", "mystery", "detective", "suspense", "thriller",
            "romance", "fantasy", "horror", "short stories", "adventure stories",
            "young adult", "graphic novels", "fairy tales",
        )
        for category in book.get("categories", []) or []:
            normalized = str(category).lower().replace("non-fiction", "nonfiction")
            if "nonfiction" in normalized:
                continue
            if any(marker in normalized for marker in fiction_markers):
                return True
        return False

    @staticmethod
    def _is_nonfiction_book(book: Dict) -> bool:
        """Recognize explicit non-fiction subjects without rejecting unclassified books."""
        nonfiction_markers = (
            "biography", "autobiography", "memoir", "history", "science",
            "business", "economics", "cooking", "education", "health",
            "fitness", "religion", "travel", "political science", "social science",
            "reference", "philosophy", "technology", "engineering", "law",
            "computer", "sports", "nature", "mathematics", "medical",
            "psychology", "self-help", "family", "relationships", "true crime",
            "finance", "management", "agriculture", "architecture", "parenting",
            "environment", "government", "statistics",
        )
        for category in book.get("categories", []) or []:
            normalized = str(category).lower().replace("non-fiction", "nonfiction")
            if "nonfiction" in normalized or any(marker in normalized for marker in nonfiction_markers):
                return True
        return False

    async def fetch_goodreads_results(self, query: str) -> List[Dict]:
        """Use Goodreads' public autocomplete endpoint as a best-effort book fallback."""
        params = {"format": "json", "q": query}
        headers = {"User-Agent": "Lemegeton Discord bot (book metadata lookup)"}
        try:
            timeout = aiohttp.ClientTimeout(total=8)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(
                    GOODREADS_AUTOCOMPLETE_URL, params=params, headers=headers
                ) as response:
                    if response.status != 200:
                        logger.warning("Goodreads fallback returned HTTP %s for %r", response.status, query)
                        return []
                    data = await response.json(content_type=None)
        except (aiohttp.ClientError, asyncio.TimeoutError, ValueError) as exc:
            logger.warning("Goodreads fallback failed for %r: %s", query, exc)
            return []

        if isinstance(data, dict):
            data = data.get("results") or data.get("books") or []

        normalized_results = []
        for result in data if isinstance(data, list) else []:
            if not isinstance(result, dict):
                continue
            title = (result.get("title") or result.get("name") or "").strip()
            if not title:
                continue
            author = result.get("author") or result.get("author_name") or ""
            authors = author if isinstance(author, list) else ([author] if author else [])
            image = (
                result.get("imageUrl") or result.get("image_url")
                or result.get("image") or result.get("smallImageUrl")
            )
            link = result.get("url") or result.get("book_url") or result.get("bookUrl") or ""
            if link:
                link = urljoin("https://www.goodreads.com", link)

            info = {
                "title": title,
                "authors": authors,
                "description": result.get("description") or "",
                "infoLink": link or "https://www.goodreads.com",
                "averageRating": result.get("averageRating") or result.get("average_rating"),
                "pageCount": result.get("num_pages") or result.get("pageCount"),
                "publishedDate": result.get("publication_year") or result.get("publishedDate"),
                "source": "Goodreads",
            }
            if image:
                info["imageLinks"] = {"thumbnail": image}
            normalized_results.append({"volumeInfo": info})
        return normalized_results[:10]

    async def fetch_book_results(
        self, query: str, book_type: str, genre: Optional[str] = None,
        year_from: Optional[int] = None, year_to: Optional[int] = None,
    ) -> List[Dict]:
        """Search Google Books first, using supported subject and publication-year constraints."""
        query_parts = [" ".join((query or "").split())]
        if genre:
            query_parts.insert(0, f"subject:{genre}")
        params = {
            "q": " ".join(part for part in query_parts if part),
            "printType": "books",
            "maxResults": 40,
            "orderBy": "relevance",
        }
        if year_from is not None or year_to is not None:
            params["publishedDate"] = f"{year_from or 1000}..{year_to or 2100}"
        all_items = []
        filtered_items = []
        try:
            timeout = aiohttp.ClientTimeout(total=8)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(GOOGLE_BOOKS_URL, params=params) as response:
                    if response.status == 200:
                        data = await response.json()
                        for item in data.get("items", []) or []:
                            if not isinstance(item, dict):
                                continue
                            book = item.get("volumeInfo") or {}
                            if not isinstance(book, dict) or not book.get("title"):
                                continue
                            all_items.append(item)
                            is_fiction = self._is_fiction_book(book)
                            is_nonfiction = self._is_nonfiction_book(book)
                            if book_type == "fiction" and is_fiction:
                                filtered_items.append(item)
                            elif book_type == "nonfiction" and is_nonfiction:
                                filtered_items.append(item)
                    else:
                        logger.warning(
                            "Google Books returned HTTP %s for %s query %r",
                            response.status, book_type, query,
                        )
        except (aiohttp.ClientError, asyncio.TimeoutError, ValueError) as exc:
            logger.warning("Google Books %s search failed for %r: %s", book_type, query, exc)

        if filtered_items:
            return filtered_items[:10]
        if genre or year_from is not None or year_to is not None:
            # Goodreads autocomplete does not reliably expose subject/year constraints.
            return []

        # Google Books often omits categories or labels them too broadly to classify
        # a result. Keep likely matches instead of dropping every title and needlessly
        # waiting on Goodreads. Exclude only results explicitly classified as the
        # opposite media type.
        fallback_items = [
            item for item in all_items
            if not (
                self._is_nonfiction_book(item.get("volumeInfo") or {})
                if book_type == "fiction"
                else self._is_fiction_book(item.get("volumeInfo") or {})
            )
        ]
        if fallback_items:
            logger.info(
                "Using unclassified Google Books results for %s query %r",
                book_type, query,
            )
            return fallback_items[:10]

        logger.info("No suitable Google Books result for %r; trying Goodreads", query)
        return await self.fetch_goodreads_results(query)

    async def search_tmdb_titles(self, query: str, media_type: str) -> List[Dict]:
        """Search TMDB for movies or TV shows using the configured read-access token."""
        query = " ".join((query or "").split())
        if not query:
            return []
        token = os.getenv("TMDB_BEARER_TOKEN", "").strip()
        if not token:
            return []
        endpoint = "movie" if media_type == "MOVIE" else "tv"
        headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
        params = {"query": query, "include_adult": "false", "language": "en-US", "page": 1}
        try:
            timeout = aiohttp.ClientTimeout(total=10)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(
                    f"{TMDB_API_BASE_URL}/search/{endpoint}", params=params, headers=headers
                ) as response:
                    if response.status != 200:
                        logger.warning("TMDB %s search returned HTTP %s", endpoint, response.status)
                        return []
                    data = await response.json()
                    return data.get("results", [])[:10]
        except (aiohttp.ClientError, asyncio.TimeoutError, ValueError) as exc:
            logger.warning("TMDB %s search failed for %r: %s", endpoint, query, exc)
            return []

    async def fetch_tmdb_media(self, query: str, media_type: str) -> Optional[Dict]:
        """Fetch a matching TMDB title and detailed metadata."""
        token = os.getenv("TMDB_BEARER_TOKEN", "").strip()
        if not token:
            return None
        endpoint = "movie" if media_type == "MOVIE" else "tv"
        results = await self.search_tmdb_titles(query, media_type)
        if not results:
            return None
        best_match = self.choose_best_title_match(
            results,
            query,
            lambda item: (
                item.get("title"), item.get("original_title"),
                item.get("name"), item.get("original_name"),
            ),
        )
        if best_match is not None:
            results = [best_match]
        append_fields = (
            "credits,videos,keywords,release_dates,external_ids,images,recommendations"
            if media_type == "MOVIE"
            else "aggregate_credits,videos,keywords,content_ratings,external_ids,images,recommendations"
        )
        headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
        params = {"append_to_response": append_fields, "language": "en-US"}
        try:
            timeout = aiohttp.ClientTimeout(total=12)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(
                    f"{TMDB_API_BASE_URL}/{endpoint}/{results[0]['id']}",
                    params=params, headers=headers,
                ) as response:
                    if response.status != 200:
                        logger.warning("TMDB %s details returned HTTP %s", endpoint, response.status)
                        return None
                    details = await response.json()
                    details["_media_type"] = media_type
                    return details
        except (aiohttp.ClientError, asyncio.TimeoutError, ValueError, KeyError) as exc:
            logger.warning("TMDB %s details failed for %r: %s", endpoint, query, exc)
            return None


    async def fetch_mdblist_ratings(self, tmdb_id: int, media_type: str) -> Dict[str, Dict]:
        """Fetch Metacritic critic and user scores from MDBList using a TMDB ID.

        Metacritic does not offer an unrestricted public developer endpoint, so this
        uses MDBList's documented API instead of querying Metacritic pages directly.
        MDBList supplies rating-source records through its documented API:
        "metacritic" is critic Metascore (0-100); "metacriticuser" is User Score (0-10).

        MDBList is optional. If MDBLIST_API_KEY is unset, the caller keeps the TMDB-only
        rating display. Missing scores are omitted, never estimated.
        """
        api_key = os.getenv("MDBLIST_API_KEY", "").strip()
        if not api_key or not tmdb_id:
            return {}

        # MDBList calls movies "movie" and TV series "show" in its TMDB-ID endpoints.
        endpoint_type = "movie" if media_type == "MOVIE" else "show"
        url = f"{MDBLIST_API_BASE_URL}/tmdb/{endpoint_type}/{tmdb_id}"
        params = {"apikey": api_key}

        try:
            timeout = aiohttp.ClientTimeout(total=10)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(url, params=params) as response:
                    if response.status != 200:
                        logger.warning(
                            "MDBList %s ratings returned HTTP %s for TMDB ID %s",
                            endpoint_type, response.status, tmdb_id,
                        )
                        return {}
                    payload = await response.json(content_type=None)
        except (aiohttp.ClientError, asyncio.TimeoutError, ValueError) as exc:
            logger.warning("MDBList ratings lookup failed for TMDB ID %s: %s", tmdb_id, exc)
            return {}

        # Current MDBList responses provide ratings as an array; accept a nested response
        # too so a response wrapper does not break optional score enrichment.
        ratings = payload.get("ratings") if isinstance(payload, dict) else None
        if not isinstance(ratings, list) and isinstance(payload, dict):
            nested = payload.get("data")
            ratings = nested.get("ratings") if isinstance(nested, dict) else []
        if not isinstance(ratings, list):
            return {}

        wanted = {"metacritic": 100.0, "metacriticuser": 10.0}
        normalized: Dict[str, Dict] = {}
        for rating in ratings:
            if not isinstance(rating, dict):
                continue
            source = str(rating.get("source") or "").strip().lower()
            if source not in wanted:
                continue

            # "value" uses the rating source's own scale; "score" is only a fallback.
            raw_value = rating.get("value")
            if raw_value in (None, "", "N/A"):
                raw_value = rating.get("score")
            try:
                value = float(str(raw_value).strip().split("/", 1)[0])
            except (TypeError, ValueError):
                continue
            if not 0 <= value <= wanted[source]:
                logger.debug("Ignoring out-of-range %s score %r", source, raw_value)
                continue

            item = {"value": value}
            try:
                votes = int(rating.get("votes"))
                if votes >= 0:
                    item["votes"] = votes
            except (TypeError, ValueError):
                pass

            rating_url = rating.get("url")
            # Some providers return non-URL IDs here; only expose a real Metacritic URL.
            if isinstance(rating_url, str) and rating_url.startswith("https://www.metacritic.com/"):
                item["url"] = rating_url
            normalized[source] = item

        return normalized

    # --------------------------------------------------
    # Fetch Media Info (Anime, Manga, LN)
    # --------------------------------------------------
    async def fetch_media(self, query: str, media_type: str) -> List[Dict]:
        query_str = """
        query ($search: String, $type: MediaType) {
            Page(perPage: 10) {
                media(search: $search, type: $type) {
                    id
                    title { romaji english native }
                    description(asHtml: false)
                    averageScore
                    siteUrl
                    status
                    episodes
                    chapters
                    volumes
                    startDate { year month day }
                    endDate { year month day }
                    genres
                    coverImage { large medium }
                    bannerImage
                    externalLinks { site url }
                    format
                }
            }
        }
        """
        query = " ".join((query or "").split())
        if not query:
            return []
        variables = {"search": query, "type": media_type}

        try:
            async with aiohttp.ClientSession() as session:
                data = await post_graphql(session, query_str, variables)
                if data is None:
                    logger.warning(f"Failed AniList request for query='{query}', type={media_type}")
                    return []
                return data.get("Page", {}).get("media", [])
        except Exception as e:
            logger.error(f"Failed AniList request: {e}", exc_info=True)
            return []

    # --------------------------------------------------
    # Fetch AniList Progress & Rating for a User
    # --------------------------------------------------
    async def fetch_user_anilist_progress(self, anilist_username: str, media_id: int, media_type: str) -> Optional[Dict]:
        if not anilist_username or not media_id:
            return None

        query = """
        query($userName: String, $mediaId: Int, $type: MediaType) {
            User(name: $userName) {
                mediaListOptions {
                    scoreFormat
                }
            }
            MediaList(userName: $userName, mediaId: $mediaId, type: $type) {
                progress
                score
                status
            }
        }
        """
        variables = {"userName": anilist_username, "mediaId": media_id, "type": media_type}

        try:
            async with aiohttp.ClientSession() as session:
                payload = await post_graphql(session, query, variables)
                if payload is None:
                    logger.warning(f"AniList fetch failed for {anilist_username=} {media_id=}")
                    return None
        except Exception as e:
            logger.exception("Error requesting AniList user progress: %s", e, exc_info=True)
            return None

        user_opts = payload.get("User", {}).get("mediaListOptions", {})
        score_format = user_opts.get("scoreFormat", "POINT_100")

        entry = payload.get("MediaList")
        if not entry:
            return None

        progress = entry.get("progress")
        score = entry.get("score")
        status = entry.get("status")

        # 📊 Normalize based on score format
        rating10: Optional[float] = None
        if score is not None:
            try:
                if score_format == "POINT_100":
                    rating10 = round(score / 10.0, 1)
                elif score_format in ("POINT_10", "POINT_10_DECIMAL"):
                    rating10 = float(score)
                elif score_format == "POINT_5":
                    rating10 = round((score / 5) * 10, 1)
                elif score_format == "POINT_3":
                    # 1=Bad, 2=Average, 3=Good → map roughly to 3, 6, 9 out of 10
                    mapping = {1: 3.0, 2: 6.0, 3: 9.0}
                    rating10 = mapping.get(score, None)
            except Exception:
                rating10 = None

        return {"progress": progress, "rating10": rating10, "status": status}

    # --------------------------------------------------
    # Fetch Page Users with Delays (Rate Limit Protection)
    # --------------------------------------------------
    async def fetch_page_users_with_delay(
        self, 
        usernames: List[str], 
        media_id: int, 
        media_type: str,
        delay: float = 0.67
    ) -> List[Dict]:
        """
        Fetch progress for multiple users sequentially with delays between requests.
        Returns list of user progress data (skips users without progress).
        """
        user_progress_list = []
        
        for username in usernames:
            if not username:
                continue
            
            # Fetch progress for this user
            anilist_progress = await self.fetch_user_anilist_progress(
                username, media_id, media_type
            )
            
            # Skip users without this media (404 or rate limit)
            if anilist_progress:
                user_progress_list.append({
                    "anilist_username": username,
                    "progress": anilist_progress.get("progress"),
                    "rating10": anilist_progress.get("rating10"),
                    "status": anilist_progress.get("status")
                })
            
            # Add delay between requests (except after the last one)
            if username != usernames[-1]:
                await asyncio.sleep(delay)
        
        return user_progress_list

    # --------------------------------------------------
    # Build Sorted User List with Progress (for pagination)
    # --------------------------------------------------
    async def build_sorted_user_progress_list(
        self, 
        users: List[Tuple], 
        media_id: int, 
        real_type: str
    ) -> List[Dict]:
        """
        Fetch progress for all users and return a sorted list.
        Sorted alphabetically by AniList username
        """
        user_progress_list = []
        processed_anilist_users = set()
        processed_discord_ids = set()

        for user in users:
            # Expected structure: (id, discord_id, guild_id, username, anilist_username, anilist_id, ...)
            if len(user) >= 5:
                discord_id = user[1]
                discord_name = user[3]
                anilist_username = user[4]
            else:
                logger.warning(f"Unexpected user row structure: {len(user)} columns")
                continue

            # Skip if no AniList username
            if not anilist_username:
                continue

            # Skip duplicates
            if anilist_username in processed_anilist_users or discord_id in processed_discord_ids:
                logger.debug(f"Skipping duplicate user: {anilist_username} (Discord ID: {discord_id})")
                continue

            anilist_progress = await self.fetch_user_anilist_progress(
                anilist_username, media_id, real_type
            )

            # Skip users without this media (404 or rate limit)
            if not anilist_progress:
                continue

            # Mark as processed
            processed_anilist_users.add(anilist_username)
            processed_discord_ids.add(discord_id)

            user_progress_list.append({
                "anilist_username": anilist_username,
                "progress": anilist_progress.get("progress"),
                "rating10": anilist_progress.get("rating10"),
                "status": anilist_progress.get("status")
            })

        # Sort alphabetically by AniList username
        user_progress_list.sort(key=lambda u: u["anilist_username"].lower())

        return user_progress_list

    # --------------------------------------------------
    # /Browse Command
    # --------------------------------------------------
    @app_commands.command(
        name="browse",
        description="Search Anime, Manga, Light Novels, General Novels, Books, Movies, TV Shows and Webnovels"
    )
    @command_meta(section="Media", name="Browse")
    @app_commands.describe(
        media_type="Choose a media type",
        title="Choose the title"
    )
    @app_commands.choices(media_type=[
        app_commands.Choice(name="Anime", value="ANIME"),
        app_commands.Choice(name="Manga", value="MANGA"),
        app_commands.Choice(name="Light Novel", value="MANGA_NOVEL"),
        app_commands.Choice(name="General Novels", value="GENERAL_NOVEL"),
        app_commands.Choice(name="Books", value="BOOKS"),
        app_commands.Choice(name="Movies", value="MOVIE"),
        app_commands.Choice(name="TV Shows", value="TV"),
        app_commands.Choice(name="Webnovels", value="WEBNOVEL"),
    ])
    async def search(self, interaction: discord.Interaction, media_type: app_commands.Choice[str], title: str):
        title = " ".join((title or "").split())
        if not title:
            await interaction.response.send_message(
                embed=build_error_embed("Search Required", "Enter a title to search for."),
                ephemeral=True,
            )
            return
        await interaction.response.defer()

        chosen_type = media_type.value
        real_type = "MANGA" if chosen_type == "MANGA_NOVEL" else chosen_type

        if chosen_type in ("MOVIE", "TV"):
            if not os.getenv("TMDB_BEARER_TOKEN", "").strip():
                embed = build_error_embed(
                    "TMDB Setup Required",
                    "Movies and TV metadata require a TMDB API read-access token. Set TMDB_BEARER_TOKEN in your bot environment.",
                )
                await interaction.followup.send(embed=embed, ephemeral=True)
                return

            media = await self.fetch_tmdb_media(title, chosen_type)
            if not media:
                label = "movie" if chosen_type == "MOVIE" else "TV show"
                embed = build_error_embed("No Results Found", f"No {label} found matching {title!r}.")
                await interaction.followup.send(embed=embed, ephemeral=True)
                return

            # Enrich TMDB metadata with optional Metacritic scores from MDBList.
            # This request is skipped when MDBLIST_API_KEY is not configured.
            rating_data = await self.fetch_mdblist_ratings(media.get("id"), chosen_type)

            is_movie = chosen_type == "MOVIE"
            name = media.get("title") if is_movie else media.get("name")
            year_source = media.get("release_date") if is_movie else media.get("first_air_date")
            year = year_source[:4] if year_source else "Year unknown"
            overview = media.get("overview") or "No overview is available."
            if len(overview) > 900:
                overview = overview[:897].rstrip() + "..."

            tmdb_url = f"https://www.themoviedb.org/{'movie' if is_movie else 'tv'}/{media['id']}"
            embed = discord.Embed(
                title=f"{'🎬' if is_movie else '📺'} {name or 'Unknown title'} ({year})"[:256],
                url=tmdb_url, description=overview, color=PALETTE.PRIMARY,
            )
            if media.get("poster_path"):
                embed.set_thumbnail(url=f"{TMDB_IMAGE_BASE_URL}/w500{media['poster_path']}")
            if media.get("backdrop_path"):
                embed.set_image(url=f"{TMDB_IMAGE_BASE_URL}/w780{media['backdrop_path']}")

            def add_tmdb_field(label: str, value: Optional[str], inline: bool = True) -> None:
                if value:
                    embed.add_field(name=label, value=str(value)[:200], inline=inline)

            genres = ", ".join(g.get("name", "") for g in media.get("genres", []) if g.get("name"))
            add_tmdb_field("🎭 Genres", genres)
            if media.get("vote_average") is not None:
                add_tmdb_field("⭐ TMDB Rating", f"{media['vote_average']:.1f}/10 · {media.get('vote_count', 0):,} votes")

            # Keep critic and audience scores distinct: Metascore is /100, User Score is /10.
            for source, label, scale in (
                ("metacritic", "🎞️ Metacritic Metascore", 100),
                ("metacriticuser", "👥 Metacritic User Score", 10),
            ):
                score_record = rating_data.get(source)
                if not score_record:
                    continue
                score_value = f"{score_record['value']:g}/{scale}"
                if isinstance(score_record.get("votes"), int):
                    score_value += f" · {score_record['votes']:,} votes"
                if score_record.get("url"):
                    score_value += f" · [Metacritic]({score_record['url']})"
                add_tmdb_field(label, score_value)

            add_tmdb_field("📌 Status", media.get("status"))
            add_tmdb_field("🌐 Original Language", media.get("original_language"))

            if is_movie:
                add_tmdb_field("📅 Release Date", media.get("release_date"))
                runtime = media.get("runtime")
                add_tmdb_field("⏱️ Runtime", f"{runtime} min" if runtime else None)
                add_tmdb_field("💬 Tagline", media.get("tagline"), inline=False)
                credits = media.get("credits") or {}
                crew = credits.get("crew") or []
                directors = ", ".join(p.get("name", "") for p in crew if p.get("job") == "Director")
                writers = ", ".join(p.get("name", "") for p in crew if p.get("job") in ("Writer", "Screenplay"))
                add_tmdb_field("🎥 Director", directors)
                add_tmdb_field("✍️ Writer(s)", writers)
                production = ", ".join(c.get("name", "") for c in media.get("production_companies", []) if c.get("name"))
                add_tmdb_field("🏢 Production", production)
                countries = ", ".join(c.get("name", "") for c in media.get("production_countries", []) if c.get("name"))
                add_tmdb_field("🌍 Countries", countries)
                if media.get("budget"):
                    add_tmdb_field("💰 Budget", f"USD {media['budget']:,}")
                if media.get("revenue"):
                    add_tmdb_field("🎟️ Revenue", f"USD {media['revenue']:,}")
                keyword_data = (media.get("keywords") or {}).get("keywords") or []
                release_dates = (media.get("release_dates") or {}).get("results") or []
                certification = next(
                    (r.get("certification") for c in release_dates if c.get("iso_3166_1") == "US"
                     for r in c.get("release_dates", []) if r.get("certification")), None
                )
                add_tmdb_field("🔞 US Certification", certification)
            else:
                add_tmdb_field("📅 First Air Date", media.get("first_air_date"))
                add_tmdb_field("📅 Last Air Date", media.get("last_air_date"))
                add_tmdb_field("📺 Seasons / Episodes", f"{media.get('number_of_seasons', '?')} / {media.get('number_of_episodes', '?')}")
                runtimes = media.get("episode_run_time") or []
                runtime_text = f"{min(runtimes)}–{max(runtimes)} min" if len(runtimes) > 1 else (f"{runtimes[0]} min" if runtimes else None)
                add_tmdb_field("⏱️ Episode Runtime", runtime_text)
                creators = ", ".join(p.get("name", "") for p in media.get("created_by", []) if p.get("name"))
                add_tmdb_field("✍️ Created By", creators)
                networks = ", ".join(n.get("name", "") for n in media.get("networks", []) if n.get("name"))
                add_tmdb_field("📡 Networks", networks)
                credits = media.get("aggregate_credits") or media.get("credits") or {}
                keyword_data = (media.get("keywords") or {}).get("results") or []
                ratings = (media.get("content_ratings") or {}).get("results") or []
                certification = next((r.get("rating") for r in ratings if r.get("iso_3166_1") == "US" and r.get("rating")), None)
                add_tmdb_field("🔞 US Content Rating", certification)

            cast = credits.get("cast") or []
            cast_names = []
            for person in cast[:6]:
                character = person.get("character") or ", ".join(
                    role.get("character", "") for role in person.get("roles", []) if role.get("character")
                )
                cast_names.append(f"{person.get('name', 'Unknown')}{f' as {character}' if character else ''}")
            add_tmdb_field("🎭 Cast", ", ".join(cast_names), inline=False)

            keywords = ", ".join(k.get("name", "") for k in keyword_data if k.get("name"))
            add_tmdb_field("🔎 Keywords", keywords, inline=False)
            imdb_id = (media.get("external_ids") or {}).get("imdb_id")
            add_tmdb_field("🔗 IMDb", f"https://www.imdb.com/title/{imdb_id}/" if imdb_id else None, inline=False)

            videos = (media.get("videos") or {}).get("results") or []
            trailer = next((v for v in videos if v.get("site") == "YouTube" and v.get("type") == "Trailer"), None)
            if trailer and trailer.get("key"):
                add_tmdb_field("▶️ Trailer", f"https://www.youtube.com/watch?v={trailer['key']}", inline=False)

            recommendations = (media.get("recommendations") or {}).get("results") or []
            similar = [item.get("title") or item.get("name") for item in recommendations[:5] if item.get("title") or item.get("name")]
            add_tmdb_field("✨ Similar", ", ".join(similar), inline=False)
            source_footer = "Metadata from TMDB"
            if rating_data:
                source_footer += " • Metacritic ratings via MDBList"
            embed.set_footer(text=f"{source_footer} • {'Movie' if is_movie else 'TV series'}")
            await interaction.followup.send(embed=embed)
            return

        if chosen_type == "WEBNOVEL":
            try:
                # Browser automation can hang on provider challenges; bound the wait so
                # the deferred Discord interaction always receives a response.
                results = await asyncio.wait_for(
                    search_novelupdates(title),
                    timeout=45,
                )
            except ScrapeBlockedError as exc:
                logger.warning("Novel Updates blocked the search for %r: %s", title, exc)
                embed = build_error_embed(
                    "Novel Updates Temporarily Unavailable",
                    "Novel Updates blocked or rate-limited automated access. Please try again later.",
                )
                await interaction.followup.send(embed=embed, ephemeral=True)
                return
            except asyncio.TimeoutError:
                logger.warning("Novel Updates search timed out for %r", title)
                embed = build_error_embed(
                    "Novel Updates Search Timed Out",
                    "Novel Updates took too long to respond. Please try again in a moment.",
                )
                await interaction.followup.send(embed=embed, ephemeral=True)
                return
            except Exception as e:
                logger.warning("Novel Updates search failed for %r: %s", title, e, exc_info=True)
                embed = build_error_embed(
                    "Novel Updates Search Failed",
                    "The search service failed while reading Novel Updates. Please try again later.",
                )
                await interaction.followup.send(embed=embed, ephemeral=True)
                return

            if not results:
                embed = build_error_embed(
                    "No Results Found",
                    f"No webnovel results found on Novel Updates for {title!r}.",
                )
                await interaction.followup.send(embed=embed, ephemeral=True)
                return

            novel = results[0]
            description = novel.get("description") or "No description available."
            description = description[:400] + "..." if len(description) > 400 else description
            embed = discord.Embed(
                title=f"📚 {novel['title']}",
                url=novel.get("url"),
                description=description,
                color=PALETTE.PRIMARY,
            )
            if novel.get("image"):
                embed.set_thumbnail(url=novel["image"])
            if novel.get("rating"):
                embed.add_field(name="⭐ Rating", value=novel["rating"], inline=True)
            if novel.get("genres"):
                genres = ", ".join(novel["genres"])
                embed.add_field(name="🎭 Genres", value=genres[:1024], inline=False)
            embed.set_footer(text="Fetched from Novel Updates")
            await interaction.followup.send(embed=embed)
            return

        if chosen_type in ("GENERAL_NOVEL", "BOOKS"):
            book_type = "fiction" if chosen_type == "GENERAL_NOVEL" else "nonfiction"
            try:
                # Keep provider delays/errors from leaving Discord's deferred response
                # spinning indefinitely.
                results = await asyncio.wait_for(
                    self.fetch_book_results(title, book_type),
                    timeout=18,
                )
            except asyncio.TimeoutError:
                logger.warning("Book search timed out for %r (%s)", title, book_type)
                results = []
            except Exception as exc:
                logger.exception("Book search failed for %r (%s)", title, book_type)
                await interaction.followup.send(
                    embed=build_error_embed("Book Search Failed", application_error_message(exc)),
                    ephemeral=True,
                )
                return
            if not results:
                category_name = "general novels" if book_type == "fiction" else "non-fiction books"
                embed = build_error_embed(
                    "No Results Found",
                    f"No {category_name} found matching {title!r}.",
                )
                await interaction.followup.send(embed=embed, ephemeral=True)
                return

            selected_book = self.choose_best_title_match(
                results,
                title,
                lambda item: (item.get("volumeInfo") or {}).get("title"),
            )
            book = (selected_book or results[0]).get("volumeInfo", {})
            title_text = book.get("title") or "Unknown title"
            raw_description = BeautifulSoup(
                book.get("description") or "", "html.parser"
            ).get_text(" ", strip=True)
            description = raw_description or "No description is available for this book."
            if len(description) > 900:
                description = description[:897].rstrip() + "..."

            embed = discord.Embed(
                title=f"{'📖' if book_type == 'fiction' else '📚'} {title_text}"[:256],
                url=book.get("infoLink") or book.get("previewLink"),
                description=description,
                color=PALETTE.PRIMARY,
            )

            image_links = book.get("imageLinks") or {}
            thumbnail = image_links.get("thumbnail") or image_links.get("smallThumbnail")
            if thumbnail:
                embed.set_thumbnail(url=thumbnail.replace("http://", "https://", 1))

            authors = ", ".join(book.get("authors") or []) or "Unknown"
            embed.add_field(name="✍️ Author(s)", value=authors[:1024], inline=True)
            embed.add_field(
                name="📅 Published",
                value=str(book.get("publishedDate") or "Unknown")[:1024],
                inline=True,
            )
            if book.get("publisher"):
                embed.add_field(name="🏢 Publisher", value=str(book["publisher"])[:1024], inline=True)
            if book.get("pageCount"):
                embed.add_field(name="📄 Pages", value=str(book["pageCount"]), inline=True)
            if book.get("averageRating") is not None:
                rating_source = "Goodreads" if book.get("source") == "Goodreads" else "Google Books"
                embed.add_field(name=f"⭐ {rating_source} Rating", value=f"{book['averageRating']}/5", inline=True)
            if book.get("language"):
                embed.add_field(name="🌐 Language", value=str(book["language"])[:1024], inline=True)
            identifiers = book.get("industryIdentifiers") or []
            isbns = [
                f"{entry.get('type')}: {entry.get('identifier')}"
                for entry in identifiers
                if entry.get("type") and entry.get("identifier")
            ]
            if isbns:
                embed.add_field(name="🔖 ISBN", value="\n".join(isbns)[:1024], inline=False)
            if book.get("subtitle"):
                embed.add_field(name="📘 Subtitle", value=str(book["subtitle"])[:1024], inline=False)

            categories = book.get("categories") or []
            if categories:
                embed.add_field(
                    name="🏷️ Categories",
                    value=", ".join(categories)[:1024],
                    inline=False,
                )

            source_name = book.get("source") or "Google Books"
            embed.set_footer(
                text=f"{source_name} • General fiction" if book_type == "fiction"
                else f"{source_name} • Non-fiction search"
            )
            await interaction.followup.send(embed=embed)
            return

        # ✅ AniList Fetch
        results = await self.fetch_media(title, real_type)
        if not results:
            embed = build_error_embed(
                "No Results Found",
                "No results found."
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
            return

        # Filter subtypes before ranking so manga cannot hide a light novel.
        if chosen_type == "MANGA_NOVEL":
            results = [item for item in results if item.get("format") == "NOVEL"]
        elif chosen_type == "MANGA":
            results = [item for item in results if item.get("format") != "NOVEL"]
        if not results:
            label = "Light Novel" if chosen_type == "MANGA_NOVEL" else "Manga"
            await interaction.followup.send(
                embed=build_error_embed("No Results Found", f"No {label} results found matching {title!r}."),
                ephemeral=True,
            )
            return
        media = self.choose_best_title_match(
            results,
            title,
            lambda item: (
                (item.get("title") or {}).get("english"),
                (item.get("title") or {}).get("romaji"),
                (item.get("title") or {}).get("native"),
            ),
        )

        # Filter by format to ensure correct media type
        if chosen_type == "MANGA_NOVEL" and media.get("format") != "NOVEL":
            embed = build_error_embed(
                "No Light Novel Results",
                "No Light Novel results found."
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
            return
        elif chosen_type == "MANGA" and media.get("format") == "NOVEL":
            embed = build_error_embed(
                "No Manga Results",
                "No Manga results found (try Light Novel instead)."
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
            return

        # Format dates
        start_date = media.get("startDate", {})
        end_date = media.get("endDate", {})
        start_str = f"{start_date.get('year','?')}-{start_date.get('month','?')}-{start_date.get('day','?')}"
        end_str = (
            f"{end_date.get('year','?')}-{end_date.get('month','?')}-{end_date.get('day','?')}"
            if end_date else "Ongoing"
        )

        # Description
        raw_description = media.get("description") or "No description available."
        description = raw_description[:400] + "..." if len(raw_description) > 400 else raw_description
        genres = ", ".join(media.get("genres", [])) or "Unknown"

        # --------------------------------------------------
        # AniList Embed
        # --------------------------------------------------
        embed = discord.Embed(
            title=f"{'🎬' if real_type=='ANIME' else '📖'} {media['title']['english'] or media['title']['romaji']}",
            url=media["siteUrl"],
            description=description,
            color=PALETTE.PRIMARY
        )

        cover_url = media.get("coverImage", {}).get("medium") or media.get("coverImage", {}).get("large")
        if cover_url:
            embed.set_thumbnail(url=cover_url)

        banner_url = media.get("bannerImage")
        if banner_url:
            embed.set_image(url=banner_url)

        if media.get("averageScore") is not None:
            embed.add_field(name="⭐ AniList Score", value=f"{media['averageScore']}/100", inline=True)
        embed.add_field(
            name="📌 Status",
            value=(media.get("status") or "Unknown").replace("_", " ").title(),
            inline=True,
        )
        format_value = (media.get("format") or "").replace("_", " ").title()
        if format_value:
            embed.add_field(name="📋 Format", value=format_value, inline=True)
        title_data = media.get("title") or {}
        native_title = title_data.get("native")
        primary_title = title_data.get("english") or title_data.get("romaji") or native_title
        if native_title and native_title != primary_title:
            embed.add_field(name="🈯 Native Title", value=str(native_title)[:1024], inline=False)

        if real_type == "ANIME":
            embed.add_field(name="📺 Episodes", value=media.get("episodes", '?'), inline=True)
        else:
            embed.add_field(name="📖 Chapters", value=media.get("chapters", '?'), inline=True)
            embed.add_field(name="📚 Volumes", value=media.get("volumes", '?'), inline=True)

        embed.add_field(name="🎭 Genres", value=genres, inline=False)
        embed.add_field(name="📅 Published", value=f"**Start:** {start_str}\n**End:** {end_str}", inline=False)

        mal_link = None
        for link in media.get("externalLinks", []):
            if link.get("site") == "MyAnimeList":
                mal_link = link.get("url")
                break
        if mal_link:
            embed.add_field(name="🔗 MyAnimeList", value=f"[View on MAL]({mal_link})", inline=False)

        embed.set_footer(text="Fetched from AniList")

        # --------------------------------------------------
        # PageView with Lazy-Loading
        # --------------------------------------------------
        class PageView(FeedbackAwareView):
            def __init__(self, embed1, media_data, real_type_val, guild_id, bot):
                super().__init__(timeout=300)
                self.embed1 = embed1
                self.media_data = media_data
                self.real_type = real_type_val
                self.guild_id = guild_id
                self.bot = bot
                self.current = "info"
                
                # Progress data (continuous loading)
                self.all_users: Optional[List[Tuple]] = None  # All users from database (sorted)
                self.loaded_user_progress: List[Dict] = []  # Continuous list of all loaded users with progress
                self.processed_usernames: set = set()  # Track all usernames we've attempted to fetch
                self.current_batch_start = 0  # Current position in all_users
                self.batch_size = 10  # Load 10 users at a time
                self.is_loading = False  # Track if currently loading
                
                self.rebuild_buttons()

            async def load_user_list(self):
                """Load all users from database, sorted alphabetically"""
                if self.all_users is None:
                    self.all_users = await get_all_users_guild_aware(self.guild_id)
                    # Sort users alphabetically by anilist_username
                    self.all_users.sort(key=lambda u: (u[4] or "").lower() if len(u) >= 5 else "")
                return self.all_users

            def get_next_batch_usernames(self) -> List[str]:
                """Get list of AniList usernames for the next batch to load"""
                if self.all_users is None:
                    return []
                
                usernames = []
                
                # Start from current_batch_start and get next batch_size users we haven't processed
                idx = self.current_batch_start
                
                while idx < len(self.all_users) and len(usernames) < self.batch_size:
                    user = self.all_users[idx]
                    # Expected structure: (id, discord_id, guild_id, username, anilist_username, anilist_id, ...)
                    if len(user) >= 5:
                        anilist_username = user[4]
                        if anilist_username and anilist_username not in self.processed_usernames:
                            usernames.append(anilist_username)
                    idx += 1
                
                return usernames

            def has_more_users(self) -> bool:
                """Check if there are more users to load"""
                if self.all_users is None:
                    return False
                return self.current_batch_start < len(self.all_users)

            async def load_next_batch(self) -> bool:
                """Load next batch of users and append to loaded_user_progress. Returns True if data was loaded."""
                if self.is_loading or not self.has_more_users():
                    return False
                
                self.is_loading = True
                
                try:
                    # Get usernames for next batch
                    usernames = self.get_next_batch_usernames()
                    
                    if not usernames:
                        # No more users to process
                        return False
                    
                    # Fetch progress with delays (0.67s)
                    browse_cog = self.bot.get_cog("BrowseCog")
                    user_progress = await browse_cog.fetch_page_users_with_delay(
                        usernames,
                        self.media_data.get("id", 0),
                        self.real_type,
                        delay=0.67
                    )
                    
                    # Mark all usernames as processed (even if they didn't have progress)
                    self.processed_usernames.update(usernames)
                    
                    # Append to continuous list
                    self.loaded_user_progress.extend(user_progress)
                    
                    # Update current_batch_start: advance past all users we just processed
                    # Find the next user that hasn't been processed yet
                    while self.current_batch_start < len(self.all_users):
                        user = self.all_users[self.current_batch_start]
                        if len(user) >= 5:
                            anilist_username = user[4]
                            if anilist_username:
                                if anilist_username in self.processed_usernames:
                                    self.current_batch_start += 1
                                    continue
                                else:
                                    # Found next unprocessed user
                                    break
                        self.current_batch_start += 1
                    
                    return len(user_progress) > 0
                finally:
                    self.is_loading = False

            def build_progress_embed(self) -> discord.Embed:
                """Build embed showing all loaded users"""
                col_name = "Episodes" if self.real_type == "ANIME" else "Chapters"
                
                progress_lines = [f"`{'User':<20} {col_name:<10} {'Rating':<7} {'Status':<12}`"]
                progress_lines.append("`{:-<20} {:-<10} {:-<7} {:-<12}`".format("", "", "", ""))
                
                if not self.loaded_user_progress:
                    progress_lines.append("`No users with progress found.`")
                else:
                    for user_data in self.loaded_user_progress:
                        total = self.media_data.get("episodes") if self.real_type == "ANIME" else self.media_data.get("chapters")
                        progress_text = f"{user_data['progress']}/{total or '?'}" if user_data.get("progress") is not None else "—"
                        rating_text = f"{user_data['rating10']}/10" if user_data.get("rating10") is not None else "—"
                        status_text = user_data.get("status", "—")
                        
                        progress_lines.append(f"`{user_data['anilist_username']:<20} {progress_text:<10} {rating_text:<7} {status_text:<12}`")
                
                # Check if description is too long (Discord limit is 4096 chars)
                description_text = "\n".join(progress_lines)
                if len(description_text) > 4096:
                    # Truncate but keep header
                    header = "\n".join(progress_lines[:2])
                    truncated = "\n".join(progress_lines[2:])
                    # Keep as many users as fit
                    max_chars = 4096 - len(header) - 50  # 50 chars buffer
                    lines = truncated.split("\n")
                    truncated_lines = []
                    for line in lines:
                        if len("\n".join(truncated_lines) + "\n" + line) > max_chars:
                            break
                        truncated_lines.append(line)
                    description_text = header + "\n" + "\n".join(truncated_lines) + "\n`... (truncated, use Load More to see more)`"
                
                progress_embed = discord.Embed(
                    title="👥 Registered Users' Progress",
                    description=description_text,
                    color=PALETTE.PRIMARY
                )
                media_title = self.media_data['title']['english'] or self.media_data['title']['romaji']
                emoji = '🎬' if self.real_type == 'ANIME' else '📖'
                checked_count = len(self.processed_usernames)
                total_users = len(self.all_users) if self.all_users else 0
                footer_text = f"{emoji} {media_title} • {len(self.loaded_user_progress)} users loaded • {checked_count}/{total_users} database users checked"
                if self.has_more_users():
                    footer_text += " • Fetched from AniList"
                else:
                    footer_text += " • All users loaded • Fetched from AniList"
                progress_embed.set_footer(text=footer_text)
                
                return progress_embed

            def rebuild_buttons(self):
                self.clear_items()

                if self.current == "info":
                    btn = Button(
                        label="👥 User Progress",
                        style=discord.ButtonStyle.green
                    )

                    async def user_progress_callback(interaction: discord.Interaction):
                        await interaction.response.defer()
                        
                        # Load user list first
                        await self.load_user_list()
                        
                        if not self.all_users or len(self.all_users) == 0:
                            try:
                                embed = build_info_embed(
                                    "No Users Found",
                                    "No registered users found."
                                )
                                await interaction.followup.send(embed=embed, ephemeral=True)
                            except Exception:
                                pass
                            return

                        # Switch to progress view
                        self.current = "progress"
                        
                        # Show loading message
                        loading_embed = discord.Embed(
                            title="👥 Registered Users' Progress",
                            description="Loading user progress... This may take ~7 seconds.",
                            color=PALETTE.PRIMARY
                        )
                        try:
                            await interaction.edit_original_response(embed=loading_embed, view=self)
                        except Exception:
                            pass
                        
                        # Load first batch
                        await self.load_next_batch()
                        embed = self.build_progress_embed()
                        
                        self.rebuild_buttons()
                        try:
                            await interaction.edit_original_response(embed=embed, view=self)
                        except Exception:
                            pass

                    btn.callback = user_progress_callback
                    self.add_item(btn)

                elif self.current == "progress":
                    # Back button
                    back_btn = Button(
                        label="📖 Media Info",
                        style=discord.ButtonStyle.blurple
                    )

                    async def media_info_callback(interaction: discord.Interaction):
                        self.current = "info"
                        self.rebuild_buttons()
                        await interaction.response.edit_message(embed=self.embed1, view=self)

                    back_btn.callback = media_info_callback
                    self.add_item(back_btn)

                    # Load More button
                    load_more_btn = Button(
                        label="Load More ➕",
                        style=discord.ButtonStyle.green,
                        disabled=(not self.has_more_users() or self.is_loading)
                    )

                    async def load_more_callback(interaction: discord.Interaction):
                        if not self.has_more_users() or self.is_loading:
                            embed = build_info_embed(
                                "Cannot Load More",
                                "No more users to load or already loading."
                            )
                            await interaction.response.send_message(embed=embed, ephemeral=True)
                            return
                        
                        # Show loading message
                        await interaction.response.defer()
                        loading_embed = discord.Embed(
                            title="👥 Registered Users' Progress",
                            description="Loading more users... This may take ~7 seconds.",
                            color=PALETTE.PRIMARY
                        )
                        try:
                            await interaction.edit_original_response(embed=loading_embed, view=self)
                        except Exception:
                            pass
                        
                        # Load next batch
                        loaded = await self.load_next_batch()
                        
                        if loaded:
                            embed = self.build_progress_embed()
                            self.rebuild_buttons()
                            try:
                                await interaction.edit_original_response(embed=embed, view=self)
                            except Exception:
                                pass
                        else:
                            # No more users loaded
                            embed = self.build_progress_embed()
                            self.rebuild_buttons()
                            try:
                                await interaction.edit_original_response(embed=embed, view=self)
                            except Exception:
                                pass

                    load_more_btn.callback = load_more_callback
                    self.add_item(load_more_btn)

            async def on_timeout(self):
                self.clear_items()

        # Start with media info; always include the view so buttons are visible
        view = PageView(embed, media, real_type, interaction.guild_id, self.bot)
        await interaction.followup.send(embed=embed, view=view)


    # --------------------------------------------------
    # Autocomplete
    # --------------------------------------------------
    @search.autocomplete("title")
    async def autocomplete_search(self, interaction: discord.Interaction, current: str):
        if len(current) < 2:
            return []

        media_type = getattr(interaction.namespace, "media_type", None)
        choices = []

        if media_type == "WEBNOVEL":
            try:
                # Autocomplete gets a short HTTP-only probe; full searches can use
                # the slower Botasaurus fallback after Discord's response is deferred.
                results = await asyncio.wait_for(
                    search_novelupdates(
                        current, browser_fallback=False, http_timeout=2, max_http_urls=1
                    ),
                    timeout=2.25,
                )
            except Exception as e:
                logger.debug("Novel Updates autocomplete failed: %s", e)
                return []
            for novel in results[:10]:
                title = (novel.get("title") or "").strip()
                if title:
                    choices.append(app_commands.Choice(name=title[:100], value=title[:100]))
        elif media_type in ("MOVIE", "TV"):
            results = await self.search_tmdb_titles(current, media_type)
            for item in results[:10]:
                title = (item.get("title") if media_type == "MOVIE" else item.get("name")) or ""
                title = title.strip()
                if title:
                    year_source = item.get("release_date") if media_type == "MOVIE" else item.get("first_air_date")
                    year = f" ({year_source[:4]})" if year_source else ""
                    choices.append(app_commands.Choice(name=f"{title}{year}"[:100], value=title[:100]))
        elif media_type in ("GENERAL_NOVEL", "BOOKS"):
            book_type = "fiction" if media_type == "GENERAL_NOVEL" else "nonfiction"
            try:
                # Discord autocomplete interactions have a short response deadline.
                results = await asyncio.wait_for(
                    self.fetch_book_results(current, book_type),
                    timeout=2.25,
                )
            except asyncio.TimeoutError:
                logger.debug("Book autocomplete timed out for %r (%s)", current, book_type)
                return []
            except Exception:
                logger.exception("Book autocomplete failed for %r (%s)", current, book_type)
                return []
            for item in results[:10]:
                info = item.get("volumeInfo", {})
                title = (info.get("title") or "").strip()
                if not title:
                    continue
                authors = ", ".join(info.get("authors") or [])
                label = f"{title} — {authors}" if authors else title
                choices.append(app_commands.Choice(name=label[:100], value=title[:100]))
        else:
            search_type = "MANGA" if media_type in ("MANGA", "MANGA_NOVEL") else "ANIME"
            results = await self.fetch_media(current, search_type)
            for media in results[:10]:
                title = media["title"].get("romaji") or media["title"].get("english") or "Unknown"
                title = title[:100]
                choices.append(app_commands.Choice(name=title, value=title))

        return choices


async def setup(bot: commands.Bot):
    await bot.add_cog(BrowseCog(bot))