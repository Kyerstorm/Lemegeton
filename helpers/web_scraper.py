"""
Public-page scraping utilities for Lemegeton.

Engines:
- Scrapling AsyncFetcher: asynchronous HTTP fetching and extraction.
- Botasaurus: browser rendering for JavaScript-heavy pages.
- Scrapling Spider: asynchronous, bounded programmatic crawls with robots.txt support.
- Scrapy PublicPageSpider: standalone CLI crawling, retries, AutoThrottle and feed exports.

The framework only targets public HTTP(S) pages. It validates URLs, limits response
and crawl sizes, respects crawl scope/robots.txt, and treats rate limits, Cloudflare
challenges and CAPTCHAs as stop conditions. It does not solve challenges or evade
site access controls. Use a documented API or obtain permission if a site blocks access.

Examples:
    # Single page from an async Lemegeton task
    result = await fetch_public_page("https://example.com", engine="http")

    # Render a public JavaScript-heavy page with Botasaurus
    result = await fetch_public_page("https://example.com", engine="browser")

    # Bounded programmatic crawl (same host by default)
    pages = await crawl_public_site(["https://example.com"], max_pages=25)

    # Scrapy CLI crawl
    scrapy runspider helpers/web_scraper.py -a urls=https://example.com \
        -a max_pages=25 -O pages.jsonl
"""

import asyncio
import ipaddress
import json
import logging
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set
from urllib.parse import urljoin, urlsplit

import scrapy
from bs4 import BeautifulSoup
from botasaurus.browser import browser as botasaurus_browser, Driver
from scrapling.fetchers import AsyncFetcher

logger = logging.getLogger("WebScraper")

DEFAULT_MAX_TEXT_CHARS = 12_000
MAX_TEXT_CHARS = 40_000
MAX_SELECTOR_RESULTS = 50
MAX_LINK_RESULTS = 50
MAX_RESPONSE_BYTES = 5 * 1024 * 1024
MAX_CRAWL_PAGES = 500
DEFAULT_TIMEOUT_SECONDS = 20
DEFAULT_USER_AGENT = "Lemegeton/1.0 (public metadata scraper)"

# Challenge markers are intentionally used for detection, not solving or circumvention.
_CHALLENGE_MARKERS = (
    "cf-chl-",
    "challenge-platform",
    "just a moment...",
    "attention required! | cloudflare",
    "verify you are human",
    "g-recaptcha",
    "h-captcha",
    "hcaptcha",
    "cf-turnstile",
    "captcha-container",
    "captcha challenge",
)


class ScrapeError(RuntimeError):
    """Base exception for fetch/extraction errors."""


class ScrapeBlockedError(ScrapeError):
    """Raised when a site signals that automated access is blocked or challenged."""


class ScrapeRequestError(ScrapeError):
    """Raised when the target cannot be fetched as a public HTML page."""


def _validate_public_http_url(url: str) -> None:
    """Reject malformed URLs and obvious private/local targets before requesting them."""
    if not isinstance(url, str) or not url.strip():
        raise ValueError("A complete public HTTP(S) URL is required.")

    parsed = urlsplit(url.strip())
    if parsed.scheme.lower() not in ("http", "https") or not parsed.hostname:
        raise ValueError("A complete public HTTP(S) URL is required.")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError("Credentials embedded in URLs are not allowed.")

    hostname = parsed.hostname.lower().rstrip(".")
    if hostname == "localhost" or hostname.endswith(
        (".localhost", ".local", ".internal", ".test", ".invalid")
    ):
        raise ValueError("Local or internal hosts are not allowed by the public-page scraper.")

    try:
        port = parsed.port
    except ValueError as exc:
        raise ValueError("The URL contains an invalid port.") from exc
    if port is not None and port not in (80, 443):
        raise ValueError("Only standard public HTTP(S) ports are allowed.")

    # IP-literal URLs are checked directly. Hostnames are not resolved here, so
    # deployment environments should still enforce outbound-network restrictions.
    try:
        address = ipaddress.ip_address(hostname)
    except ValueError:
        address = None
    if address and not address.is_global:
        raise ValueError("Private or reserved IP addresses are not allowed.")


def detect_access_challenge(
    status: Optional[int],
    html: str,
    headers: Optional[Dict[str, Any]] = None,
) -> Optional[str]:
    """Classify common denial/challenge responses; never attempts to work around them."""
    body = (html or "").lower()
    header_map = {str(key).lower(): str(value).lower() for key, value in (headers or {}).items()}
    server = header_map.get("server", "")

    if status == 429:
        return "http_429_rate_limited"
    if status in (401, 403):
        if "cloudflare" in server or "cloudflare" in body or "cf-chl-" in body:
            return "cloudflare_access_challenge"
        return f"http_{status}_access_denied"
    if "cf-chl-" in body or "challenge-platform" in body:
        return "cloudflare_challenge"
    if any(marker in body for marker in _CHALLENGE_MARKERS):
        return "captcha_or_human_verification_challenge"
    if status in (503, 522, 524) and "cloudflare" in server:
        return "cloudflare_unavailable_or_challenged"
    return None


def _parse_bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _parse_selectors(value: Any) -> Dict[str, str]:
    """Accept a selector mapping or JSON mapping from Scrapy command-line arguments."""
    if value is None or value == "":
        return {}
    if isinstance(value, str):
        if not value.strip():
            return {}
        try:
            value = json.loads(value)
        except json.JSONDecodeError as exc:
            raise ValueError("selectors must be a JSON object mapping field names to CSS selectors.") from exc

    if not isinstance(value, dict):
        raise ValueError("selectors must be a mapping of output field names to CSS selectors.")

    selectors: Dict[str, str] = {}
    for field_name, selector in value.items():
        if isinstance(field_name, str) and isinstance(selector, str) and selector.strip():
            selectors[field_name[:100]] = selector.strip()[:300]
    return selectors


def _extract_page_data(
    url: str,
    html: str,
    data: Dict[str, Any],
    *,
    status_code: Optional[int] = None,
    engine: str = "unknown",
) -> Dict[str, Any]:
    """Normalize HTML into bounded metadata, selected text fields and optional links."""
    if len((html or "").encode("utf-8", errors="replace")) > MAX_RESPONSE_BYTES:
        raise ScrapeRequestError(f"Page response exceeded the {MAX_RESPONSE_BYTES}-byte limit.")

    soup = BeautifulSoup(html or "", "html.parser")

    def read_meta(*css_selectors: str) -> str:
        for selector in css_selectors:
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

    fields: Dict[str, Any] = {}
    for field_name, css_selector in _parse_selectors(data.get("selectors")).items():
        try:
            nodes = soup.select(css_selector)[:MAX_SELECTOR_RESULTS]
        except Exception as exc:
            logger.warning("Invalid CSS selector for field %r: %s", field_name, exc)
            continue

        values = [node.get_text(" ", strip=True) for node in nodes]
        values = [value[:MAX_TEXT_CHARS] for value in values if value]
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
        "engine": engine,
    }
    if status_code is not None:
        result["status_code"] = status_code

    if _parse_bool(data.get("include_text"), default=True):
        try:
            max_chars = int(data.get("max_text_chars", DEFAULT_MAX_TEXT_CHARS))
        except (TypeError, ValueError):
            max_chars = DEFAULT_MAX_TEXT_CHARS
        max_chars = max(1, min(max_chars, MAX_TEXT_CHARS))

        text_soup = BeautifulSoup(str(soup), "html.parser")
        for node in text_soup.select("script, style, noscript, svg, template"):
            node.decompose()
        body = text_soup.body or text_soup
        result["text"] = body.get_text(" ", strip=True)[:max_chars]

    if _parse_bool(data.get("include_links"), default=False):
        links = []
        for node in soup.select("a[href]"):
            if len(links) >= MAX_LINK_RESULTS:
                break
            href = (node.get("href") or "").strip()
            if not href:
                continue
            target = urljoin(url, href)
            try:
                _validate_public_http_url(target)
            except ValueError:
                continue
            links.append({"text": node.get_text(" ", strip=True)[:200], "url": target})
        result["links"] = links

    return result


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
    Render one public page using Botasaurus and extract metadata/CSS fields/links.

    Required data: {"url": "https://example.com/article"}
    Optional data: selectors, include_text, max_text_chars, include_links.

    This function is synchronous because Botasaurus owns the browser lifecycle.
    Async code should call it with asyncio.to_thread(scrape_public_page, data,
    output=None). Blocked/challenge pages are reported as ScrapeBlockedError.
    """
    url = str(data.get("url") or "").strip()
    _validate_public_http_url(url)
    driver.get(url)
    html = driver.page_html or ""
    reason = detect_access_challenge(None, html)
    if reason:
        raise ScrapeBlockedError(f"Public-page access stopped for {url}: {reason}.")
    return _extract_page_data(url, html, data, engine="botasaurus")


async def fetch_public_page(
    url: str,
    *,
    engine: str = "http",
    selectors: Optional[Dict[str, str]] = None,
    include_text: bool = True,
    max_text_chars: int = DEFAULT_MAX_TEXT_CHARS,
    include_links: bool = False,
    timeout: int = DEFAULT_TIMEOUT_SECONDS,
    retries: int = 2,
) -> Dict[str, Any]:
    """
    Fetch one public page asynchronously using Scrapling HTTP or Botasaurus browser mode.

    engine="http" is the fast, non-browser route. engine="browser" renders JavaScript.
    Redirects are followed manually so every destination is validated before requesting.
    Rate limits and access challenges raise ScrapeBlockedError instead of being bypassed.
    """
    url = url.strip()
    _validate_public_http_url(url)
    mode = engine.strip().lower()
    data = {
        "url": url,
        "selectors": selectors or {},
        "include_text": include_text,
        "max_text_chars": max_text_chars,
        "include_links": include_links,
    }

    if mode == "browser":
        try:
            return await asyncio.to_thread(scrape_public_page, data, output=None)
        except ScrapeBlockedError:
            raise
        except Exception as exc:
            logger.warning("Botasaurus fetch failed for %s: %s", url, exc)
            raise ScrapeRequestError(f"Browser fetch failed for {url}: {exc}") from exc
    if mode != "http":
        raise ValueError("engine must be either 'http' or 'browser'.")

    headers = {"User-Agent": DEFAULT_USER_AGENT, "Accept": "text/html,application/xhtml+xml"}
    current_url = url

    # Disable automatic redirects and validate each Location target to reduce SSRF risk.
    for redirect_count in range(6):
        try:
            page = await AsyncFetcher.get(
                current_url,
                timeout=max(1, min(int(timeout), 60)),
                retries=max(0, min(int(retries), 4)),
                retry_delay=1,
                follow_redirects=False,
                headers=headers,
            )
        except Exception as exc:
            logger.warning("Scrapling HTTP fetch failed for %s: %s", current_url, exc)
            raise ScrapeRequestError(f"HTTP fetch failed for {current_url}: {exc}") from exc

        status_code = int(getattr(page, "status", 0) or 0)
        response_headers = getattr(page, "headers", {}) or {}
        html = getattr(page, "html_content", "") or ""
        response_url = str(getattr(page, "url", current_url) or current_url)

        raw_body = getattr(page, "body", b"") or b""
        if isinstance(raw_body, bytes) and len(raw_body) > MAX_RESPONSE_BYTES:
            raise ScrapeRequestError(f"Page response exceeded the {MAX_RESPONSE_BYTES}-byte limit.")

        if status_code in (301, 302, 303, 307, 308):
            location = next(
                (str(value) for key, value in response_headers.items() if str(key).lower() == "location"),
                "",
            )
            if not location:
                raise ScrapeRequestError(f"Redirect from {current_url} did not include a Location header.")
            if redirect_count >= 5:
                raise ScrapeRequestError(f"Too many redirects while fetching {url}.")
            current_url = urljoin(current_url, location)
            _validate_public_http_url(current_url)
            continue

        reason = detect_access_challenge(status_code, html, response_headers)
        if reason:
            raise ScrapeBlockedError(f"Public-page access stopped for {current_url}: {reason}.")
        if status_code < 200 or status_code >= 300:
            raise ScrapeRequestError(f"HTTP {status_code or 'unknown'} returned for {current_url}.")

        content_type = next(
            (str(value).lower() for key, value in response_headers.items() if str(key).lower() == "content-type"),
            "",
        )
        if content_type and not any(kind in content_type for kind in ("text/html", "application/xhtml+xml")):
            raise ScrapeRequestError(f"Expected HTML from {current_url}, received {content_type}.")

        _validate_public_http_url(response_url)
        return _extract_page_data(
            response_url, html, data, status_code=status_code, engine="scrapling-http"
        )

    raise ScrapeRequestError(f"Redirect handling failed for {url}.")


async def fetch_many(
    urls: Sequence[str],
    *,
    concurrency: int = 4,
    **fetch_options: Any,
) -> List[Dict[str, Any]]:
    """Fetch multiple independent pages concurrently and return per-URL results/errors."""
    semaphore = asyncio.Semaphore(max(1, min(int(concurrency), 8)))

    async def run_one(url: str) -> Dict[str, Any]:
        async with semaphore:
            try:
                return await fetch_public_page(url, **fetch_options)
            except (ScrapeError, ValueError) as exc:
                return {
                    "url": url,
                    "error": str(exc),
                    "blocked": isinstance(exc, ScrapeBlockedError),
                }
            except Exception as exc:
                logger.exception("Unexpected scraper failure for %s", url)
                return {"url": url, "error": str(exc), "blocked": False}

    return await asyncio.gather(*(run_one(url) for url in urls))


def _normalize_domains(urls: Sequence[str], allowed_domains: Optional[Iterable[str]]) -> Set[str]:
    """Create the host allowlist used to keep recursive crawls in scope."""
    if allowed_domains:
        values = [allowed_domains] if isinstance(allowed_domains, str) else list(allowed_domains)
        domains = {str(value).strip().lower().lstrip(".").rstrip(".") for value in values if str(value).strip()}
    else:
        domains = set()
        for url in urls:
            hostname = (urlsplit(url).hostname or "").lower().rstrip(".")
            if hostname.startswith("www."):
                hostname = hostname[4:]
            if hostname:
                domains.add(hostname)
    if not domains:
        raise ValueError("At least one allowed domain is required.")
    return domains


def _domain_is_allowed(hostname: str, domains: Set[str]) -> bool:
    host = (hostname or "").lower().rstrip(".")
    return any(host == domain or host.endswith("." + domain) for domain in domains)


async def crawl_public_site(
    start_urls: Sequence[str],
    *,
    max_pages: int = 50,
    allowed_domains: Optional[Iterable[str]] = None,
    selectors: Optional[Dict[str, str]] = None,
    include_text: bool = True,
    max_text_chars: int = DEFAULT_MAX_TEXT_CHARS,
    include_links: bool = True,
    respect_robots: bool = True,
    concurrency: int = 2,
    delay: float = 1.0,
) -> List[Dict[str, Any]]:
    """
    Crawl a bounded set of public pages through Scrapling's asynchronous Spider engine.

    Crawling stays within allowed_domains (the seed hosts by default), obeys robots.txt
    by default, deduplicates URLs, limits pages/text/response size, and uses conservative
    concurrency/delay defaults. A blocked or challenged URL becomes a result record and
    is not retried through a different engine.
    """
    from scrapling.spiders import Request, Response, Spider

    seeds = []
    for url in start_urls:
        clean_url = str(url).strip()
        _validate_public_http_url(clean_url)
        if clean_url not in seeds:
            seeds.append(clean_url)
    if not seeds:
        raise ValueError("At least one start URL is required.")

    max_pages = max(1, min(int(max_pages), MAX_CRAWL_PAGES))
    seeds = seeds[:max_pages]
    domains = _normalize_domains(seeds, allowed_domains)
    for url in seeds:
        if not _domain_is_allowed(urlsplit(url).hostname or "", domains):
            raise ValueError(f"Start URL is outside allowed_domains: {url}")

    options = {
        "selectors": selectors or {},
        "include_text": include_text,
        "max_text_chars": max_text_chars,
        "include_links": include_links,
    }

    class _PublicSiteSpider(Spider):
        name = "lemegeton_public_site"

        async def parse(self, response: Response):
            url = str(response.url)
            html = getattr(response, "html_content", "") or ""
            status_code = int(getattr(response, "status", 0) or 0)
            reason = detect_access_challenge(status_code, html, getattr(response, "headers", {}) or {})
            if reason:
                logger.warning("Crawl stopped at %s: %s", url, reason)
                yield {"url": url, "blocked": True, "reason": reason, "engine": "scrapling-spider"}
                return

            if status_code < 200 or status_code >= 300:
                logger.warning("Crawl received HTTP %s for %s; skipping", status_code, url)
                return

            try:
                item = _extract_page_data(
                    url, html, options, status_code=status_code, engine="scrapling-spider"
                )
            except ScrapeError as exc:
                logger.warning("Skipping %s: %s", url, exc)
                return
            yield item

            if len(self._scheduled_urls) >= max_pages:
                return

            soup = BeautifulSoup(html, "html.parser")
            for anchor in soup.select("a[href]"):
                if len(self._scheduled_urls) >= max_pages:
                    break
                target = urljoin(url, (anchor.get("href") or "").strip())
                try:
                    _validate_public_http_url(target)
                except ValueError:
                    continue
                host = urlsplit(target).hostname or ""
                if not _domain_is_allowed(host, domains) or target in self._scheduled_urls:
                    continue
                self._scheduled_urls.add(target)
                yield Request(target)

    spider = _PublicSiteSpider()
    spider.start_urls = seeds
    spider.allowed_domains = domains
    spider.robots_txt_obey = bool(respect_robots)
    spider.concurrent_requests = max(1, min(int(concurrency), 8))
    spider.concurrent_requests_per_domain = 1
    spider.download_delay = max(0.5, min(float(delay), 30.0))
    spider.autothrottle_enabled = True
    spider.max_blocked_retries = 0
    spider._scheduled_urls = set(seeds)

    results: List[Dict[str, Any]] = []
    async for item in spider.stream():
        results.append(item)
    return results


class PublicPageSpider(scrapy.Spider):
    """
    Generic Scrapy spider for public-page crawling.

    Run with:
        scrapy runspider helpers/web_scraper.py -a urls=https://example.com \\
            -a max_pages=25 -O pages.jsonl

    Optional arguments:
        allowed_domains=example.com
        selectors={"headline":"h1","paragraphs":"article p"}
        include_text=true
        include_links=true
        follow_links=true

    Scrapy's feed exporter supports JSON, JSON Lines, CSV and XML; choose with -O.
    robots.txt, AutoThrottle, conservative per-domain concurrency and response-size
    limits are enabled. HTTP access challenges are logged and treated as stop conditions.
    """
    name = "lemegeton_public_page_spider"
    custom_settings = {
        "ROBOTSTXT_OBEY": True,
        "DOWNLOAD_DELAY": 1.0,
        "CONCURRENT_REQUESTS": 8,
        "CONCURRENT_REQUESTS_PER_DOMAIN": 2,
        "AUTOTHROTTLE_ENABLED": True,
        "AUTOTHROTTLE_START_DELAY": 1.0,
        "AUTOTHROTTLE_MAX_DELAY": 30.0,
        "AUTOTHROTTLE_TARGET_CONCURRENCY": 1.0,
        "DOWNLOAD_TIMEOUT": DEFAULT_TIMEOUT_SECONDS,
        "DOWNLOAD_MAXSIZE": MAX_RESPONSE_BYTES,
        "RETRY_ENABLED": True,
        "RETRY_TIMES": 1,
        "RETRY_HTTP_CODES": [500, 502, 503, 504, 522, 524],
        "TELNETCONSOLE_ENABLED": False,
        "LOG_LEVEL": "INFO",
    }

    def __init__(
        self,
        urls: str = "",
        max_pages: Any = 50,
        allowed_domains: str = "",
        selectors: str = "",
        include_text: Any = "true",
        include_links: Any = "true",
        follow_links: Any = "true",
        **kwargs: Any,
    ):
        super().__init__(**kwargs)
        candidate_urls = urls or getattr(self, "start_urls", [])
        if isinstance(candidate_urls, str):
            candidate_urls = [part.strip() for part in candidate_urls.replace("\n", ",").split(",") if part.strip()]

        self.start_urls = []
        for url in candidate_urls:
            _validate_public_http_url(url)
            if url not in self.start_urls:
                self.start_urls.append(url)
        if not self.start_urls:
            raise ValueError("Pass at least one start URL with -a urls=https://example.com.")

        self.max_pages = max(1, min(int(max_pages), MAX_CRAWL_PAGES))
        self.selectors = _parse_selectors(selectors)
        self.include_text = _parse_bool(include_text, True)
        self.include_links = _parse_bool(include_links, True)
        self.follow_links = _parse_bool(follow_links, True)
        self._scheduled_urls = set(self.start_urls[: self.max_pages])
        self.start_urls = self.start_urls[: self.max_pages]

        if allowed_domains:
            self.allowed_domains = [
                domain.strip().lower().lstrip(".").rstrip(".")
                for domain in allowed_domains.replace("\n", ",").split(",")
                if domain.strip()
            ]
        else:
            self.allowed_domains = sorted(_normalize_domains(self.start_urls, None))

    async def start(self):
        # Scrapy 2.13+ supports async start generators; keep requests in the same
        # callback/error-handling path as discovered links.
        for url in self.start_urls:
            yield scrapy.Request(url, callback=self.parse, errback=self.handle_request_failure)

    def handle_request_failure(self, failure):
        response = getattr(failure.value, "response", None)
        if response is not None:
            reason = detect_access_challenge(response.status, getattr(response, "text", ""), response.headers)
            logger.warning(
                "Scrapy request stopped for %s (HTTP %s, challenge=%s)",
                response.url,
                response.status,
                reason or "unclassified",
            )
        else:
            logger.warning("Scrapy request failed: %s", failure.getErrorMessage())

    def parse(self, response):
        html = response.text or ""
        reason = detect_access_challenge(response.status, html, response.headers)
        if reason:
            logger.warning("Scrapy stopped at %s: %s", response.url, reason)
            yield {"url": response.url, "blocked": True, "reason": reason, "engine": "scrapy"}
            return
        if response.status < 200 or response.status >= 300:
            logger.warning("Scrapy skipped HTTP %s for %s", response.status, response.url)
            return

        try:
            result = _extract_page_data(
                response.url,
                html,
                {
                    "selectors": self.selectors,
                    "include_text": self.include_text,
                    "include_links": self.include_links,
                },
                status_code=response.status,
                engine="scrapy",
            )
        except ScrapeError as exc:
            logger.warning("Scrapy skipped %s: %s", response.url, exc)
            return
        yield result

        if not self.follow_links or len(self._scheduled_urls) >= self.max_pages:
            return

        soup = BeautifulSoup(html, "html.parser")
        for anchor in soup.select("a[href]"):
            if len(self._scheduled_urls) >= self.max_pages:
                break
            target = urljoin(response.url, (anchor.get("href") or "").strip())
            try:
                _validate_public_http_url(target)
            except ValueError:
                continue
            host = urlsplit(target).hostname or ""
            if not _domain_is_allowed(host, set(self.allowed_domains)) or target in self._scheduled_urls:
                continue
            self._scheduled_urls.add(target)
            yield scrapy.Request(target, callback=self.parse, errback=self.handle_request_failure)
