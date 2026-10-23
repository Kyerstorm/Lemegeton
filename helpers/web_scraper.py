"""
Reusable browser-backed extraction for public pages that permit automated access.

Botasaurus renders JavaScript-heavy pages; BeautifulSoup performs predictable HTML
extraction after rendering. This helper does not solve CAPTCHAs, evade access controls,
rotate proxies to defeat blocks, or bypass login/paywall requirements. If a site refuses
automated access, treat that as a stop condition and use an authorized API instead.
"""

import ipaddress
import logging
from typing import Any, Dict
from urllib.parse import urljoin, urlsplit

from bs4 import BeautifulSoup
from botasaurus.browser import browser as botasaurus_browser, Driver

logger = logging.getLogger("WebScraper")

# Keep returned content bounded so callers cannot accidentally retain a whole site in memory.
DEFAULT_MAX_TEXT_CHARS = 12_000
MAX_TEXT_CHARS = 40_000
MAX_SELECTOR_RESULTS = 50
MAX_LINK_RESULTS = 50


def _validate_public_http_url(url: str) -> None:
    """Reject malformed URLs and obvious local/private destinations."""
    parsed = urlsplit(url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise ValueError("A complete public HTTP(S) URL is required.")

    hostname = parsed.hostname.lower().rstrip(".")
    if hostname == "localhost" or hostname.endswith((".localhost", ".local", ".internal")):
        raise ValueError("Local or internal hosts are not allowed by the public-page scraper.")

    # If the URL uses an IP literal, block non-public ranges. Domain names are not resolved here.
    try:
        address = ipaddress.ip_address(hostname)
    except ValueError:
        address = None
    if address and (
        address.is_private
        or address.is_loopback
        or address.is_link_local
        or address.is_multicast
        or address.is_reserved
        or address.is_unspecified
    ):
        raise ValueError("Private or reserved IP addresses are not allowed.")


@botasaurus_browser(
    headless=True,
    max_retry=2,
    retry_wait=2,
    create_error_logs=False,
    raise_exception=True,
    close_on_crash=True,
)
def scrape_public_page(driver: Driver, data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Render one public page and extract common metadata, selected CSS fields and optional links.

    Required input:
        {"url": "https://example.com/article"}

    Optional input:
        "selectors": {"headline": "h1", "paragraphs": "article p"}
            Maps output field names to CSS selectors. A single match becomes a string;
            multiple matches become a list of non-empty strings (up to 50).
        "include_text": True
            Includes bounded, visible-page text in the "text" result field.
        "max_text_chars": 12000
            Text limit, clamped to 1..40000 characters.
        "include_links": False
            Includes up to 50 links as {"text": ..., "url": ...} dictionaries.

    The function is synchronous because Botasaurus owns the browser lifecycle. Async callers
    should invoke it with asyncio.to_thread(..., output=None). Retries cover transient browser
    failures; they are not a mechanism for bypassing a site's denial of access.
    """
    url = str(data.get("url") or "").strip()
    _validate_public_http_url(url)

    # Load the page through a real browser so scripts can populate the DOM before extraction.
    driver.get(url)
    html = driver.page_html or ""
    soup = BeautifulSoup(html, "html.parser")

    def read_meta(*selectors: str) -> str:
        """Return the first populated meta content value from the provided selectors."""
        for selector in selectors:
            node = soup.select_one(selector)
            if node:
                value = (node.get("content") or "").strip()
                if value:
                    return value
        return ""

    title_node = soup.select_one("title")
    title = title_node.get_text(" ", strip=True) if title_node else ""
    title = title or read_meta('meta[property="og:title"]')

    description = read_meta(
        'meta[name="description"]',
        'meta[property="og:description"]',
        'meta[name="twitter:description"]',
    )

    canonical_node = soup.select_one('link[rel="canonical"][href]')
    canonical_url = (
        urljoin(url, canonical_node.get("href", "").strip())
        if canonical_node and canonical_node.get("href")
        else url
    )

    # User-provided CSS selectors are extracted as text only; raw page HTML is never returned.
    fields: Dict[str, Any] = {}
    selectors = data.get("selectors") or {}
    if isinstance(selectors, dict):
        for field_name, css_selector in selectors.items():
            if not isinstance(field_name, str) or not isinstance(css_selector, str) or not css_selector.strip():
                continue
            try:
                nodes = soup.select(css_selector)[:MAX_SELECTOR_RESULTS]
            except Exception as exc:
                logger.warning("Invalid CSS selector for field %r: %s", field_name, exc)
                continue
            values = [node.get_text(" ", strip=True) for node in nodes]
            values = [value for value in values if value]
            if len(values) == 1:
                fields[field_name] = values[0]
            elif values:
                fields[field_name] = values

    result: Dict[str, Any] = {
        "url": url,
        "canonical_url": canonical_url,
        "title": title,
        "description": description,
        "fields": fields,
    }

    if data.get("include_text", True):
        try:
            max_chars = int(data.get("max_text_chars", DEFAULT_MAX_TEXT_CHARS))
        except (TypeError, ValueError):
            max_chars = DEFAULT_MAX_TEXT_CHARS
        max_chars = max(1, min(max_chars, MAX_TEXT_CHARS))
        body = soup.body or soup
        result["text"] = body.get_text(" ", strip=True)[:max_chars]

    if data.get("include_links", False):
        links = []
        for node in soup.select("a[href]")[:MAX_LINK_RESULTS]:
            href = (node.get("href") or "").strip()
            if not href:
                continue
            links.append({
                "text": node.get_text(" ", strip=True)[:200],
                "url": urljoin(url, href),
            })
        result["links"] = links

    return result
