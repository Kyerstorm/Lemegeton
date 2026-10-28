"""Bounded Novel Phoenix search for public, non-adult novel metadata."""
from __future__ import annotations

import asyncio
import logging
import re
from typing import Any
from urllib.parse import urljoin, urlsplit

import aiohttp
from bs4 import BeautifulSoup

log = logging.getLogger("Lemegeton.NovelPhoenix")
BASE_URL = "https://novelphoenix.com/"
SEARCH_PAGE = urljoin(BASE_URL, "search-adv")
REQUEST_TIMEOUT = 9
MAX_HTML_BYTES = 3 * 1024 * 1024
_BLOCKED_GENRE_WORDS = {
    "adult", "mature", "smut", "ecchi", "hentai", "erotica", "erotic",
    "explicit", "nsfw", "pornographic",
}


def _safe_novel_url(value: str, base_url: str = BASE_URL) -> str | None:
    """Accept only HTTPS Novel Phoenix novel pages."""
    target = urljoin(base_url, str(value or "").strip())
    parsed = urlsplit(target)
    host = (parsed.hostname or "").casefold().rstrip(".")
    if (
        parsed.scheme != "https"
        or host not in {"novelphoenix.com", "www.novelphoenix.com"}
        or parsed.username is not None
        or parsed.password is not None
        or not re.fullmatch(r"/novel/[^/]+/?", parsed.path, flags=re.IGNORECASE)
    ):
        return None
    return target.split("#", 1)[0]


def _card_for(anchor):
    """Find the nearest result wrapper likely to contain novel metadata."""
    node = anchor
    for _ in range(6):
        node = getattr(node, "parent", None)
        if node is None:
            break
        name = getattr(node, "name", None)
        classes = " ".join(node.get("class", [])) if hasattr(node, "get") else ""
        if name in {"article", "li"} or re.search(r"novel|book|result|card|item", classes, re.I):
            return node
    return anchor.parent or anchor


def _card_genres(card) -> list[str]:
    """Read visible genre/category labels without treating arbitrary links as genres."""
    genres: list[str] = []
    selectors = (
        "[class*='genre'] a",
        "[class*='tag'] a",
        ".badge",
        ".genre",
        ".tag",
        "a[href*='/genre-']",
        "a[href*='/genre/']",
    )
    for selector in selectors:
        try:
            nodes = card.select(selector)
        except Exception:
            nodes = []
        for node in nodes:
            value = " ".join(node.get_text(" ", strip=True).split())
            href = str(node.get("href") or "").casefold()
            if not value or (node.name == "a" and not ("/genre-" in href or "/genre/" in href or "genre" in " ".join(node.get("class", [])).casefold())):
                continue
            if value.casefold() not in {existing.casefold() for existing in genres}:
                genres.append(value[:80])
    return genres[:30]


def _has_blocked_genre(genres: list[str]) -> bool:
    pattern = re.compile(r"\b(?:" + "|".join(re.escape(word) for word in sorted(_BLOCKED_GENRE_WORDS)) + r")\b", re.I)
    return any(pattern.search(value) for value in genres)


def is_safe_novel_record(record: dict[str, Any], *, require_genres: bool = False) -> bool:
    """Exclude results visibly labelled for adult content; optionally require genre evidence."""
    labels = record.get("genres") or []
    labels += record.get("tags") or []
    labels += record.get("categories") or []
    clean_labels = [str(value) for value in labels if value]
    if require_genres and not clean_labels:
        return False
    return not _has_blocked_genre(clean_labels)


def parse_novelphoenix_html(html: str, *, base_url: str = BASE_URL, limit: int = 10) -> list[dict[str, Any]]:
    """Parse novel search cards and omit records with adult categories or no genre evidence."""
    if not html or len(html.encode("utf-8", errors="ignore")) > MAX_HTML_BYTES:
        return []
    soup = BeautifulSoup(html, "html.parser")
    results: list[dict[str, Any]] = []
    seen: set[str] = set()

    for anchor in soup.select("a[href*='/novel/']"):
        url = _safe_novel_url(anchor.get("href") or "", base_url)
        if not url or url.rstrip("/").casefold() in seen:
            continue
        title = " ".join(anchor.get_text(" ", strip=True).split())
        if not title:
            title = " ".join(str(anchor.get("title") or anchor.get("aria-label") or "").split())
        if not title:
            continue

        card = _card_for(anchor)
        genres = _card_genres(card)
        if not genres or _has_blocked_genre(genres):
            continue

        def first_text(*selectors: str) -> str | None:
            for selector in selectors:
                try:
                    node = card.select_one(selector)
                except Exception:
                    node = None
                if node:
                    value = " ".join(node.get_text(" ", strip=True).split())
                    if value:
                        return value[:1600]
            return None

        author = first_text("[class*='author']", ".author", ".writer")
        status = first_text("[class*='status']", ".status")
        rating = first_text("[class*='rating']", ".rating", ".score")
        description = first_text("[class*='summary']", "[class*='description']", ".summary", ".desc", "p")

        image_url = None
        try:
            image = card.select_one("img[data-src], img[data-lazy-src], img[src]")
        except Exception:
            image = None
        if image:
            candidate = str(image.get("data-src") or image.get("data-lazy-src") or image.get("src") or "").strip()
            parsed_image = urlsplit(urljoin(base_url, candidate)) if candidate else None
            if parsed_image and parsed_image.scheme == "https" and parsed_image.hostname and not parsed_image.username and not parsed_image.password:
                image_url = urljoin(base_url, candidate)

        card_text = " ".join(card.get_text(" ", strip=True).split())
        chapter_match = re.search(r"\b([\d,]+)\s+chapters?\b", card_text, re.I)
        item = {
            "title": title[:256],
            "url": url,
            "description": description,
            "image": image_url,
            "author": author,
            "status": status,
            "rating": rating,
            "genres": genres,
            "translated_chapters": chapter_match.group(1).replace(",", "") if chapter_match else None,
            "provider": "Novel Phoenix",
        }
        if not is_safe_novel_record(item, require_genres=True):
            continue
        results.append(item)
        seen.add(url.rstrip("/").casefold())
        if len(results) >= max(1, min(int(limit), 10)):
            break

    return results


def _find_search_form(html: str):
    soup = BeautifulSoup(html, "html.parser")
    candidates = []
    for form in soup.select("form"):
        for field in form.select("input[name]"):
            field_type = str(field.get("type") or "text").casefold()
            if field_type not in {"text", "search", ""}:
                continue
            name = " ".join(str(field.get(attr) or "") for attr in ("name", "id", "placeholder", "aria-label", "class")).casefold()
            if re.search(r"search|keyword|title|novel|query|term|^q$", name):
                candidates.append((form, field))
                break
    if not candidates:
        return None
    return candidates[0]


async def search_novelphoenix(query: str, *, timeout: int = REQUEST_TIMEOUT, limit: int = 10) -> list[dict[str, Any]] | None:
    """Search the site's own public search form; return None for provider failures."""
    query = " ".join((query or "").split())
    if len(query) < 2:
        return []
    timeout = max(1, min(int(timeout), 12))
    client_timeout = aiohttp.ClientTimeout(total=timeout)
    headers = {"User-Agent": "Lemegeton media discovery/1.0", "Accept": "text/html,application/xhtml+xml"}

    try:
        async with aiohttp.ClientSession(timeout=client_timeout, headers=headers) as session:
            html = ""
            page_url = BASE_URL
            form_data = None
            action_url = None
            method = "get"

            for page in (BASE_URL, SEARCH_PAGE):
                async with session.get(page, allow_redirects=True) as response:
                    if response.status in {403, 429}:
                        log.info("Novel Phoenix declined the search request (HTTP %s)", response.status)
                        return None
                    if response.status >= 500:
                        log.info("Novel Phoenix search page returned HTTP %s", response.status)
                        return None
                    if response.status >= 400:
                        continue
                    if response.content_length and response.content_length > MAX_HTML_BYTES:
                        log.warning("Novel Phoenix search page exceeded the response-size limit")
                        return None
                    html = await response.content.read(MAX_HTML_BYTES + 1)
                    if len(html) > MAX_HTML_BYTES:
                        return None
                    html = html.decode(response.charset or "utf-8", errors="replace")
                    page_url = str(response.url)
                    selected = _find_search_form(html)
                    if selected:
                        form, field = selected
                        form_data = {}
                        for hidden in form.select("input[type='hidden'][name]"):
                            form_data[str(hidden.get("name"))] = str(hidden.get("value") or "")
                        for control in form.select("input[name]:checked"):
                            form_data[str(control.get("name"))] = str(control.get("value") or "")
                        for select in form.select("select[name]"):
                            option = select.select_one("option[selected]") or select.select_one("option")
                            if option and option.get("value") is not None:
                                form_data[str(select.get("name"))] = str(option.get("value") or "")
                        form_data[str(field.get("name"))] = query
                        action_url = urljoin(page_url, str(form.get("action") or page_url))
                        method = str(form.get("method") or "get").casefold()
                        break

            if not form_data or not action_url:
                log.info("Novel Phoenix search form could not be identified")
                return None
            parsed_action = urlsplit(action_url)
            action_host = (parsed_action.hostname or "").casefold().rstrip(".")
            if parsed_action.scheme != "https" or action_host not in {"novelphoenix.com", "www.novelphoenix.com"}:
                return None

            if method == "post":
                response_context = session.post(action_url, data=form_data, allow_redirects=True)
            else:
                response_context = session.get(action_url, params=form_data, allow_redirects=True)
            async with response_context as response:
                if response.status in {403, 429} or response.status >= 500 or response.status >= 400:
                    log.info("Novel Phoenix search returned HTTP %s", response.status)
                    return None
                if response.content_length and response.content_length > MAX_HTML_BYTES:
                    return None
                body = await response.content.read(MAX_HTML_BYTES + 1)
                if len(body) > MAX_HTML_BYTES:
                    return None
                result_html = body.decode(response.charset or "utf-8", errors="replace")
                results = parse_novelphoenix_html(result_html, base_url=str(response.url), limit=limit)
                return [{**item, "provider": "Novel Phoenix"} for item in results]
    except (aiohttp.ClientError, asyncio.TimeoutError, UnicodeError, ValueError):
        log.info("Novel Phoenix lookup failed")
        return None
    except Exception:
        log.warning("Unexpected Novel Phoenix parser failure", exc_info=True)
        return None
