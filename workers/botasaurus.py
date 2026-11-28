# DO NOT EDIT OR Configure This File.


from __future__ import annotations

import os as _os
import sys as _sys

_here = _os.path.dirname(_os.path.abspath(__file__))
if _sys.path and _os.path.normcase(_sys.path[0]) == _os.path.normcase(_here):
    _sys.path.pop(0)
    _sys.path.append(_here)

import csv
import hmac
import ipaddress
import io
import json
import logging
import os
import shutil
import signal
import socket
import subprocess
import threading
import time
import uuid
from concurrent.futures import Future, ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Optional

from openpyxl import Workbook
from urllib.parse import urljoin, urlsplit
from urllib.request import Request, urlopen

from botasaurus.cache import Cache
from botasaurus.task import task
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

try:
    from config import SETTINGS
except ImportError:
    from workers.config import SETTINGS


LOGGER = logging.getLogger("lemegeton.botasaurus")
DEFAULT_USER_AGENT = "Lemegeton/3.1 (media discovery scraper)"
MAX_REQUEST_BYTES = SETTINGS.max_response_bytes
MAX_TEXT_CHARS = SETTINGS.max_text_chars
MAX_SELECTORS = 12
MAX_LINKS = 50
MAX_STRUCTURED_RECORDS = 30
MAX_BODY_BYTES = 64 * 1024
MAX_BATCH_JOBS = 16
MAX_JOB_PAGE_SIZE = 100
MAX_EXPORT_BYTES = 10 * 1024 * 1024
CHALLENGE_MARKERS = (
    "cf-chl-widget",
    "cf-chl-body",
    "cdn-cgi/challenge-platform/h/",
    "just a moment...",
    "verify you are human",
    "captcha-container",
    "g-recaptcha",
    "h-captcha-container",
    "cf-turnstile-wrapper",
    "attention required | cloudflare",
)

CF_CHALLENGE_HOSTS = (
    "challenges.cloudflare.com",
    "cdn-cgi.challenge-platform",
)


class RequestRejected(Exception):
    pass


class ChallengeBlocked(RequestRejected):
    pass


class JobCancelled(Exception):
    pass


def _json_bytes(payload: Any) -> bytes:
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def _safe_host(host: str) -> str:
    return host.lower().rstrip(".").strip("[]")


_NON_PUBLIC_IPV6_NETWORKS = tuple(
    ipaddress.ip_network(value)
    for value in ("2001::/23", "2001:db8::/32", "2002::/16", "3fff::/20", "64:ff9b::/32")
)


def _is_public_address(address: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    if not address.is_global:
        return False
    if isinstance(address, ipaddress.IPv6Address):
        if address.ipv4_mapped is not None:
            return _is_public_address(address.ipv4_mapped)
        if any(address in network for network in _NON_PUBLIC_IPV6_NETWORKS):
            return False
    return True


def validate_public_url(value: str) -> tuple[str, str, str]:
    if not isinstance(value, str) or len(value) > 4096:
        raise RequestRejected("A valid HTTP(S) URL is required.")
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError as error:
        raise RequestRejected("The URL is malformed.") from error
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise RequestRejected("Only complete HTTP(S) URLs are supported.")
    if parsed.username or parsed.password:
        raise RequestRejected("URLs containing embedded credentials are not supported.")
    if port not in (None, 80, 443):
        raise RequestRejected("Only standard HTTP(S) ports are supported.")

    host = _safe_host(parsed.hostname)
    if host in ("localhost",) or host.endswith((".localhost", ".local", ".internal")):
        raise RequestRejected("Local and internal hosts are not supported.")

    try:
        address = ipaddress.ip_address(host)
        addresses = [address]
    except ValueError:
        try:
            records = socket.getaddrinfo(host, port or (443 if parsed.scheme == "https" else 80), type=socket.SOCK_STREAM)
        except OSError as error:
            raise RequestRejected("The target hostname could not be resolved.") from error
        addresses = []
        for record in records:
            try:
                address = ipaddress.ip_address(record[4][0].split("%", 1)[0])
            except ValueError:
                continue
            if address not in addresses:
                addresses.append(address)

    if not addresses or any(not _is_public_address(address) for address in addresses):
        raise RequestRejected("The target hostname resolves to a private or reserved address.")

    ipv4 = next((str(address) for address in addresses if address.version == 4), None)
    if not ipv4:
        ipv4 = str(addresses[0])
    return value, host, ipv4


def _same_origin_host(url: str, expected_host: str) -> bool:
    try:
        parsed = urlsplit(url)
        port = parsed.port
        return (
            parsed.scheme in ("http", "https")
            and port in (None, 80, 443)
            and _safe_host(parsed.hostname or "") == expected_host
            and not parsed.username
            and not parsed.password
        )
    except ValueError:
        return False


def _challenge_reason(status: int, headers: dict[str, str], html: str) -> str | None:
    normalized = {str(key).lower(): str(value).lower() for key, value in headers.items()}
    if normalized.get("cf-mitigated") == "challenge":
        return "Cloudflare challenge"
    if status in (503, 522, 524) and "cloudflare" in normalized.get("server", ""):
        return "Cloudflare challenge or unavailable response"
    lower = html.lower()
    if any(marker in lower for marker in CHALLENGE_MARKERS):
        return "access challenge"
    if status in (401, 403, 429):
        return f"HTTP {status} access response"
    return None


def _bounded_options(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raw = {}
    selectors = raw.get("selectors", {})
    if not isinstance(selectors, dict):
        selectors = {}
    safe_selectors: dict[str, str] = {}
    for key, value in list(selectors.items())[:MAX_SELECTORS]:
        if isinstance(key, str) and isinstance(value, str):
            safe_selectors[key[:80]] = value[:300]

    timeout = raw.get("timeoutMs", SETTINGS.timeout_ms)
    if not isinstance(timeout, (int, float)):
        timeout = SETTINGS.timeout_ms
    timeout = max(1000, min(int(timeout), 60000))

    max_text = raw.get("maxTextChars", MAX_TEXT_CHARS)
    if not isinstance(max_text, (int, float)):
        max_text = MAX_TEXT_CHARS
    max_text = max(1, min(int(max_text), MAX_TEXT_CHARS))

    return {
            "selectors": safe_selectors,
            "includeText": raw.get("includeText") is not False,
            "maxTextChars": max_text,
            "includeStructuredData": raw.get("includeStructuredData") is True,
            "includeArticle": raw.get("includeArticle") is True,
            "includeLinks": raw.get("includeLinks") is True,
            "includeHtml": raw.get("includeHtml") is True,
            "timeoutMs": timeout,
            "cfBypass": raw.get("cfBypass") is True,
        }


@task(output=None, raise_exception=True, create_error_logs=False, max_retry=0)
def _extract_page_task(data: dict[str, Any]) -> dict[str, Any]:
    html = data["html"]
    url = data["url"]
    hostname = data["hostname"]
    options = data["options"]
    soup = BeautifulSoup(html, "html.parser")

    def meta(*selectors: str) -> str | None:
        for selector in selectors:
            node = soup.select_one(selector)
            if node:
                value = node.get("content") or node.get("href") or node.get_text(" ", strip=True)
                if value:
                    return str(value).strip()[:2000]
        return None

    title_node = soup.title or soup.select_one("h1")
    title = title_node.get_text(" ", strip=True)[:300] if title_node else ""
    description = meta('meta[name="description"]', 'meta[property="og:description"]') or ""
    canonical = urljoin(url, meta('link[rel="canonical"]') or url)
    if not _same_origin_host(canonical, hostname):
        canonical = url
    image = meta('meta[property="og:image"]', 'meta[name="twitter:image"]')
    if image:
        try:
            candidate = urljoin(url, image)
            image = candidate if _same_origin_host(candidate, hostname) else None
        except ValueError:
            image = None

    structured: list[dict[str, Any]] = []
    for node in soup.select('script[type="application/ld+json"]')[:MAX_STRUCTURED_RECORDS]:
        raw = node.string or node.get_text()
        if not raw or len(raw.encode("utf-8", errors="ignore")) > 256 * 1024:
            continue
        try:
            value = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            continue
        candidates = value if isinstance(value, list) else [value]
        for item in candidates:
            if isinstance(item, dict) and len(structured) < MAX_STRUCTURED_RECORDS:
                structured.append(item)
                graph = item.get("@graph")
                if isinstance(graph, list):
                    structured.extend(entry for entry in graph[:MAX_STRUCTURED_RECORDS - len(structured)] if isinstance(entry, dict))

    fields: dict[str, Any] = {}
    for name, selector in options["selectors"].items():
        try:
            values = [node.get_text(" ", strip=True)[:2000] for node in soup.select(selector)[:MAX_LINKS]]
            values = [value for value in values if value]
            if len(values) == 1:
                fields[name] = values[0]
            elif values:
                fields[name] = values
        except Exception:
            continue

    result: dict[str, Any] = {
        "url": url,
        "canonicalUrl": canonical,
        "title": title or "Untitled page",
        "description": description,
        "fields": fields,
        "statusCode": int(data["statusCode"]),
        "engine": data["engine"],
        "author": meta('meta[name="author"]', 'meta[property="article:author"]'),
        "publishedAt": meta('meta[property="article:published_time"]', 'meta[name="datePublished"]', 'meta[name="pubdate"]'),
        "siteName": meta('meta[property="og:site_name"]'),
        "image": image,
        "feeds": [],
    }

    for node in soup.select('link[rel="alternate"][href][type]'):
        if len(result["feeds"]) >= 12:
            break
        feed_type = str(node.get("type") or "").lower()
        if not any(term in feed_type for term in ("rss", "atom", "xml")):
            continue
        feed_url = urljoin(url, str(node.get("href") or ""))
        if _same_origin_host(feed_url, hostname):
            result["feeds"].append({
                "title": str(node.get("title") or "")[:160] or None,
                "type": feed_type[:100],
                "url": feed_url,
            })

    if options["includeStructuredData"]:
        result["structuredData"] = structured

    if options["includeText"]:
        content_soup = BeautifulSoup(html, "html.parser")
        for node in content_soup.select("script,style,noscript,svg,template,nav,footer,header"):
            node.decompose()
        article = content_soup.select_one("article") or content_soup.select_one("main") or content_soup.body
        text = article.get_text(" ", strip=True) if article else content_soup.get_text(" ", strip=True)
        result["text"] = " ".join(text.split())[:options["maxTextChars"]]

    if options["includeArticle"]:
        article_node = soup.select_one("article") or soup.select_one("main")
        if article_node:
            article_text = " ".join(article_node.get_text(" ", strip=True).split())[:options["maxTextChars"]]
            result["article"] = {
                "title": title or "Untitled article",
                "description": description or None,
                "image": image,
                "author": result["author"],
                "publishedAt": result["publishedAt"],
                "content": article_text,
                "readTimeSeconds": max(0, int(len(article_text.split()) / 4 * 60)),
            }

    if options["includeLinks"]:
        links: list[dict[str, str]] = []
        for node in soup.select("a[href]"):
            if len(links) >= MAX_LINKS:
                break
            target = urljoin(url, str(node.get("href") or ""))
            if not _same_origin_host(target, hostname):
                continue
            text = node.get_text(" ", strip=True) or str(node.get("title") or node.get("aria-label") or "")
            links.append({"text": text[:200], "url": target[:2048]})
        result["links"] = links

    if options["includeHtml"]:
        result["html"] = html[:MAX_REQUEST_BYTES]
    return result


def _find_obscura() -> str | None:
    configured = SETTINGS.obscura_binary
    candidate = shutil.which(configured)
    if candidate:
        return candidate
    path = Path(configured)
    return str(path) if path.is_file() and os.access(path, os.X_OK) else None


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


def _start_obscura(cf_bypass: bool = False) -> tuple[subprocess.Popen[bytes], str] | None:
    binary = _find_obscura()
    if not binary:
        return None
    port = _free_port()
    environment = os.environ.copy()
    environment["OBSCURA_ALLOW_PRIVATE_NETWORK"] = "0"
    if not cf_bypass:
        environment.pop("OBSCURA_STEALTH", None)
        environment.pop("OBSCURA_PROXY", None)
    else:
        environment["OBSCURA_STEALTH"] = "1"
        if SETTINGS.proxy_url:
            environment["OBSCURA_PROXY"] = SETTINGS.proxy_url
    command = [binary, "serve", "--host", "127.0.0.1", "--port", str(port)]
    if SETTINGS.proxy_url and not cf_bypass:
        command[1:1] = ["--proxy", SETTINGS.proxy_url]

    process = subprocess.Popen(
        command,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        env=environment,
        start_new_session=True,
    )
    endpoint = f"http://127.0.0.1:{port}"
    deadline = time.monotonic() + 12
    while time.monotonic() < deadline:
        if process.poll() is not None:
            return None
        try:
            with urlopen(endpoint + "/json/version", timeout=0.3) as response:
                if response.status == 200:
                    return process, endpoint
        except Exception:
            time.sleep(0.15)
    process.terminate()
    try:
        process.wait(timeout=2)
    except subprocess.TimeoutExpired:
        process.kill()
    return None


def _stop_process(process: subprocess.Popen[bytes] | None) -> None:
    if process is None or process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=3)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=2)


def _route_policy(route: Any, expected_host: str, cf_bypass: bool = False) -> None:
    request_url = route.request.url
    if request_url.startswith(("data:", "blob:")):
        route.continue_()
        return
    if not _same_origin_host(request_url, expected_host):
        if cf_bypass:
            try:
                parsed = urlsplit(request_url)
                req_host = _safe_host(parsed.hostname or "")
                if any(req_host == cf_host or req_host.endswith("." + cf_host) for cf_host in CF_CHALLENGE_HOSTS):
                    route.continue_()
                    return
            except Exception:
                pass
        route.abort()
        return
    if route.request.resource_type in ("image", "font", "media"):
        route.abort()
        return
    route.continue_()


def _extract_turnstile_sitekey(page: Any) -> Optional[str]:
    try:
        sitekey = page.evaluate("""() => {
            const el = document.querySelector('[data-sitekey]')
                   || document.querySelector('.cf-turnstile')
                   || document.querySelector('[data-cf-turnstile-sitekey]');
            if (!el) return null;
            return el.getAttribute('data-sitekey')
                || el.getAttribute('data-cf-turnstile-sitekey');
        }""")
        if isinstance(sitekey, str) and sitekey.strip():
            return sitekey.strip()
    except Exception:
        pass
    return None


def _solve_turnstile_2captcha(sitekey: str, page_url: str, timeout_ms: int) -> Optional[str]:
    api_key = SETTINGS.captcha_solver_api_key
    if not api_key:
        return None
    try:
        import urllib.parse as _up
        payload = _up.urlencode({
            "key": api_key,
            "method": "turnstile",
            "sitekey": sitekey,
            "pageurl": page_url,
            "json": "1",
        }).encode()
        with urlopen("https://2captcha.com/in.php", data=payload, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8", errors="ignore"))
        if str(data.get("status")) != "1":
            return None
        task_id = data.get("request")
        if not task_id:
            return None
        deadline = time.monotonic() + (timeout_ms / 1000.0)
        time.sleep(10)
        while time.monotonic() < deadline:
            poll = f"https://2captcha.com/res.php?key={_up.quote(api_key)}&action=get&id={_up.quote(str(task_id))}&json=1"
            with urlopen(poll, timeout=15) as resp:
                poll_data = json.loads(resp.read().decode("utf-8", errors="ignore"))
            if str(poll_data.get("status")) == "1":
                token = poll_data.get("request")
                return token if isinstance(token, str) and token.strip() else None
            if "CAPCHA_NOT_READY" not in str(poll_data.get("request", "")):
                return None
            time.sleep(5)
    except Exception:
        return None
    return None


def _solve_turnstile_capsolver(sitekey: str, page_url: str, timeout_ms: int) -> Optional[str]:
    api_key = SETTINGS.captcha_solver_api_key
    if not api_key:
        return None
    try:
        create_payload = json.dumps({
            "clientKey": api_key,
            "task": {
                "type": "AntiTurnstileTaskProxyLess",
                "websiteURL": page_url,
                "websiteKey": sitekey,
            },
        }).encode()
        req = Request("https://api.capsolver.com/createTask", data=create_payload, headers={"Content-Type": "application/json"})
        with urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8", errors="ignore"))
        if data.get("errorId"):
            return None
        task_id = data.get("taskId")
        if not task_id:
            return None
        deadline = time.monotonic() + (timeout_ms / 1000.0)
        time.sleep(5)
        poll_payload = json.dumps({"clientKey": api_key, "taskId": task_id}).encode()
        while time.monotonic() < deadline:
            req = Request("https://api.capsolver.com/getTaskResult", data=poll_payload, headers={"Content-Type": "application/json"})
            with urlopen(req, timeout=15) as resp:
                poll_data = json.loads(resp.read().decode("utf-8", errors="ignore"))
            if poll_data.get("status") == "ready":
                token = (poll_data.get("solution") or {}).get("token")
                return token if isinstance(token, str) and token.strip() else None
            if poll_data.get("errorId"):
                return None
            time.sleep(3)
    except Exception:
        return None
    return None


def _solve_captcha(page: Any, page_url: str) -> Optional[str]:
    provider = SETTINGS.captcha_solver_provider
    if provider not in ("twocaptcha", "2captcha", "capsolver"):
        return None
    if not SETTINGS.captcha_solver_api_key:
        return None
    sitekey = _extract_turnstile_sitekey(page)
    if not sitekey:
        return None
    timeout = SETTINGS.captcha_solver_timeout_ms
    if provider in ("twocaptcha", "2captcha"):
        return _solve_turnstile_2captcha(sitekey, page_url, timeout)
    return _solve_turnstile_capsolver(sitekey, page_url, timeout)


def _inject_turnstile_token(page: Any, token: str) -> bool:
    try:
        return bool(page.evaluate(
            """(tok) => {
                try {
                    const inputs = document.querySelectorAll(
                        'input[name=\"cf-turnstile-response\"], input[name=\"g-recaptcha-response\"]'
                    );
                    inputs.forEach(i => { i.value = tok; });
                    if (window.turnstile && typeof window.turnstile.execute === 'function') {
                        try { window.turnstile.execute(); } catch (_) {}
                    }
                    const cb = window.___grecaptcha_cfg && window.___grecaptcha_cfg.clients;
                    return true;
                } catch (e) { return false; }
            }""",
            token,
        ))
    except Exception:
        return False


def _wait_for_cf_challenge(page: Any, host: str, cancel_event: threading.Event, timeout_ms: int, poll_ms: int) -> Optional[tuple[str, str, int, dict[str, str]]]:
    deadline = time.monotonic() + (timeout_ms / 1000.0)
    solver_tried = False
    while time.monotonic() < deadline:
        if cancel_event.is_set():
            raise JobCancelled()
        try:
            cookies = page.context.cookies()
            for cookie in cookies:
                if cookie.get("name") == "cf_clearance" and cookie.get("domain", "").endswith(host):
                    response = page.reload(wait_until="domcontentloaded", timeout=min(10000, max(1000, int(deadline - time.monotonic()) * 1000)))
                    if response:
                        headers = response.all_headers()
                        final_url = page.url
                        if not _same_origin_host(final_url, host):
                            raise ChallengeBlocked("Navigation left the validated host after challenge.")
                        html = page.content()
                        return final_url, html, response.status, headers
                    break
        except Exception:
            pass
        if not solver_tried and SETTINGS.captcha_solver_provider and SETTINGS.captcha_solver_api_key and (time.monotonic() - (deadline - timeout_ms / 1000.0)) > 5:
            solver_tried = True
            token = _solve_captcha(page, page.url)
            if token and _inject_turnstile_token(page, token):
                time.sleep(1.5)
        time.sleep(poll_ms / 1000.0)
    return None


def _navigate_with_obscura(
    url: str, host: str, timeout_ms: int, cancel_event: threading.Event,
    cf_bypass: bool = False,
) -> tuple[str, str, int, dict[str, str]]:
    started = _start_obscura(cf_bypass)
    if not started:
        raise RuntimeError("Obscura is unavailable or did not become ready.")
    process, endpoint = started
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.connect_over_cdp(endpoint, timeout=timeout_ms)
            if cf_bypass and browser.contexts:
                context = browser.contexts[0]
                context_owned = False
            else:
                context = browser.new_context(user_agent=DEFAULT_USER_AGENT, service_workers="block")
                context_owned = True
            page = None
            try:
                page = context.new_page()
                page.route("**/*", lambda route: _route_policy(route, host, cf_bypass))
                page.route_web_socket("**/*", lambda socket: socket.close())
                if cancel_event.is_set():
                    raise JobCancelled()
                response = page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
                if cancel_event.is_set():
                    raise JobCancelled()
                if response is None:
                    raise RuntimeError("Obscura did not receive a page response.")
                headers = response.all_headers()
                content_length = headers.get("content-length")
                if content_length and content_length.isdigit() and int(content_length) > MAX_REQUEST_BYTES:
                    raise RequestRejected("The page exceeded the configured response-size limit.")
                final_url = page.url
                if not _same_origin_host(final_url, host):
                    raise ChallengeBlocked("Navigation left the validated host and was stopped.")
                html = page.content()
                reason = _challenge_reason(response.status, headers, html)
                if reason and cf_bypass:
                    waited = _wait_for_cf_challenge(page, host, cancel_event, SETTINGS.cf_challenge_wait_ms, SETTINGS.cf_challenge_poll_ms)
                    if waited:
                        return waited
                    raise ChallengeBlocked(f"Cloudflare challenge did not clear within timeout.")
                if reason:
                    raise ChallengeBlocked(f"Scraping stopped after {reason}.")
                if response.status < 200 or response.status >= 300:
                    raise RuntimeError(f"Obscura navigation returned HTTP {response.status}.")
                return final_url, html, response.status, headers
            finally:
                if page is not None:
                    try:
                        page.close()
                    except Exception:
                        pass
                if context_owned:
                    context.close()
                try:
                    browser.close()
                except Exception:
                    pass
    finally:
        _stop_process(process)


def _navigate_with_chromium(
    url: str, host: str, pinned_ip: str, timeout_ms: int, cancel_event: threading.Event,
) -> tuple[str, str, int, dict[str, str]]:
    proxy = {"server": SETTINGS.proxy_url} if SETTINGS.proxy_url else None
    try:
        ipaddress.ip_address(host)
        resolver = "EXCLUDE localhost"
    except ValueError:
        resolver = f"MAP {host} {pinned_ip},MAP * ~NOTFOUND"
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            headless=True,
            proxy=proxy,
            args=["--no-sandbox", "--disable-dev-shm-usage", f"--host-resolver-rules={resolver}"],
        )
        context = browser.new_context(user_agent=DEFAULT_USER_AGENT, service_workers="block")
        try:
            page = context.new_page()
            page.route("**/*", lambda route: _route_policy(route, host))
            page.route_web_socket("**/*", lambda socket: socket.close())
            if cancel_event.is_set():
                raise JobCancelled()
            response = page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
            if cancel_event.is_set():
                raise JobCancelled()
            if response is None:
                raise RuntimeError("Chromium did not receive a page response.")
            headers = response.all_headers()
            content_length = headers.get("content-length")
            if content_length and content_length.isdigit() and int(content_length) > MAX_REQUEST_BYTES:
                raise RequestRejected("The page exceeded the configured response-size limit.")
            final_url = page.url
            if not _same_origin_host(final_url, host):
                raise ChallengeBlocked("Navigation left the validated host and was stopped.")
            html = page.content()
            reason = _challenge_reason(response.status, headers, html)
            if reason:
                raise ChallengeBlocked(f"Scraping stopped after {reason}.")
            if response.status < 200 or response.status >= 300:
                raise RuntimeError(f"Chromium navigation returned HTTP {response.status}.")
            return final_url, html, response.status, headers
        finally:
            context.close()
            browser.close()


_cache_lock = threading.Lock()


def _cache_key(url: str, options: dict[str, Any], scope: dict[str, str]) -> dict[str, Any]:
    return {
        "guild_id": scope["guild_id"],
        "user_id": scope["user_id"],
        "url": url,
        "options": options,
    }


def _scrape(payload: dict[str, Any], cancel_event: threading.Event) -> dict[str, Any]:
    url, host, pinned_ip = validate_public_url(payload["url"])
    options = _bounded_options(payload.get("options"))
    scope = payload["scope"]
    cache_key = _cache_key(url, options, scope)
    cache_name = "lemegeton_public_page"

    if SETTINGS.cache_ttl_seconds > 0:
        with _cache_lock:
            cached = Cache.get(cache_name, cache_key, raise_exception=False)
            if isinstance(cached, dict) and cached.get("expiresAt", 0) > time.time():
                result = cached.get("result")
                if isinstance(result, dict):
                    return result
            if isinstance(cached, dict):
                Cache.delete(cache_name, cache_key)

    timeout_ms = options["timeoutMs"]
    engine = "obscura"
    cf_bypass = options.get("cfBypass", False)
    try:
        page_url, html, status, headers = _navigate_with_obscura(url, host, timeout_ms, cancel_event, cf_bypass)
    except (RequestRejected, JobCancelled):
        raise
    except Exception as obscura_error:
        if not SETTINGS.chromium_fallback:
            raise RuntimeError(f"Obscura failed and Chromium fallback is disabled: {obscura_error}") from obscura_error
        LOGGER.warning("Obscura failed; using the Chromium fallback (%s).", type(obscura_error).__name__)
        engine = "chromium"
        page_url, html, status, headers = _navigate_with_chromium(url, host, pinned_ip, timeout_ms, cancel_event)

    if cancel_event.is_set():
        raise JobCancelled()
    reason = _challenge_reason(status, headers, html)
    if reason:
        raise ChallengeBlocked(f"Scraping stopped after {reason}.")

    if len(html.encode("utf-8", errors="ignore")) > MAX_REQUEST_BYTES:
        raise RequestRejected("The page exceeded the configured response-size limit.")
    result = _extract_page_task({
        "url": page_url,
        "hostname": host,
        "html": html,
        "statusCode": status,
        "engine": engine,
        "options": options,
    })
    if SETTINGS.cache_ttl_seconds > 0:
        with _cache_lock:
            Cache.put(cache_name, cache_key, {
                "expiresAt": time.time() + SETTINGS.cache_ttl_seconds,
                "result": result,
            })
    return result


_jobs: dict[str, dict[str, Any]] = {}
_jobs_lock = threading.RLock()
_executor = ThreadPoolExecutor(max_workers=SETTINGS.max_workers, thread_name_prefix="botasaurus")
_capacity = threading.BoundedSemaphore(SETTINGS.max_workers + SETTINGS.max_queue)


def _cleanup_jobs() -> None:
    cutoff = time.time() - SETTINGS.job_ttl_seconds
    with _jobs_lock:
        expired = [
            job_id for job_id, job in _jobs.items()
            if job.get("updatedAt", job.get("createdAt", 0)) < cutoff
            and job.get("status") in ("succeeded", "failed", "cancelled")
        ]
        for job_id in expired:
            _jobs.pop(job_id, None)
        if len(_jobs) > 2000:
            terminal = sorted(
                ((job.get("updatedAt", 0), job_id) for job_id, job in _jobs.items()
                 if job.get("status") in ("succeeded", "failed", "cancelled"))
            )
            for _, job_id in terminal[:len(_jobs) - 2000]:
                _jobs.pop(job_id, None)


def _run_job(job_id: str, payload: dict[str, Any], cancel_event: threading.Event) -> None:
    with _jobs_lock:
        job = _jobs.get(job_id)
        if not job:
            _capacity.release()
            return
        if cancel_event.is_set():
            job.update(status="cancelled", updatedAt=time.time())
            _capacity.release()
            return
        job["status"] = "running"
        job["updatedAt"] = time.time()
    try:
        result = _scrape(payload, cancel_event)
        with _jobs_lock:
            job = _jobs.get(job_id)
            if job:
                job.update(status="cancelled" if cancel_event.is_set() else "succeeded",
                           result=None if cancel_event.is_set() else result,
                           updatedAt=time.time())
    except JobCancelled:
        with _jobs_lock:
            job = _jobs.get(job_id)
            if job:
                job.update(status="cancelled", updatedAt=time.time())
    except ChallengeBlocked as error:
        with _jobs_lock:
            job = _jobs.get(job_id)
            if job:
                job.update(status="failed", blocked=True, error=str(error), updatedAt=time.time())
    except RequestRejected as error:
        with _jobs_lock:
            job = _jobs.get(job_id)
            if job:
                job.update(status="failed", blocked=True, error=str(error), updatedAt=time.time())
    except Exception as error:
        LOGGER.error("Scrape job failed (%s).", type(error).__name__)
        with _jobs_lock:
            job = _jobs.get(job_id)
            if job:
                job.update(
                    status="failed",
                    blocked=False,
                    error=f"Browser scrape failed ({type(error).__name__}).",
                    updatedAt=time.time(),
                )
    finally:
        _capacity.release()


def _new_job(payload: dict[str, Any]) -> str:
    _cleanup_jobs()
    if not _capacity.acquire(blocking=False):
        raise RuntimeError("The browser worker queue is full.")
    job_id = str(uuid.uuid4())
    cancel_event = threading.Event()
    job = {
        "status": "queued",
        "createdAt": time.time(),
        "updatedAt": time.time(),
        "scope": payload["scope"],
        "cancelEvent": cancel_event,
        "future": None,
        "result": None,
    }
    with _jobs_lock:
        _jobs[job_id] = job
    try:
        future = _executor.submit(_run_job, job_id, payload, cancel_event)
        with _jobs_lock:
            if job_id in _jobs:
                _jobs[job_id]["future"] = future
    except Exception:
        with _jobs_lock:
            _jobs.pop(job_id, None)
        _capacity.release()
        raise
    return job_id


def _job_summary(job_id: str, job: dict[str, Any]) -> dict[str, Any]:
    return {
        "jobId": job_id,
        "status": job["status"],
        "createdAt": job["createdAt"],
        "updatedAt": job["updatedAt"],
        "error": job.get("error"),
        "blocked": bool(job.get("blocked", False)),
    }


def _job_snapshot(job_id: str, scope: dict[str, str]) -> dict[str, Any] | None:
    with _jobs_lock:
        job = _jobs.get(job_id)
        if not job or job.get("scope") != scope:
            return None
        return {
            **_job_summary(job_id, job),
            "result": job.get("result"),
        }


def _list_jobs(
    scope: dict[str, str], status: str | None, limit: int, offset: int,
) -> dict[str, Any]:
    with _jobs_lock:
        matching = [
            (job_id, job) for job_id, job in _jobs.items()
            if job.get("scope") == scope and (status is None or job.get("status") == status)
        ]
        matching.sort(key=lambda item: (item[1].get("createdAt", 0), item[0]), reverse=True)
        return {
            "items": [_job_summary(job_id, job) for job_id, job in matching[offset:offset + limit]],
            "total": len(matching),
            "limit": limit,
            "offset": offset,
        }


def _job_stats(scope: dict[str, str]) -> dict[str, Any]:
    counts = {"queued": 0, "running": 0, "succeeded": 0, "failed": 0, "cancelled": 0}
    with _jobs_lock:
        for job in _jobs.values():
            if job.get("scope") == scope and job.get("status") in counts:
                counts[job["status"]] += 1
    return {
        "counts": counts,
        "total": sum(counts.values()),
        "maxWorkers": SETTINGS.max_workers,
        "maxQueue": SETTINGS.max_queue,
    }


def _delete_job(job_id: str, scope: dict[str, str]) -> bool:
    with _jobs_lock:
        job = _jobs.get(job_id)
        if not job or job.get("scope") != scope or job.get("status") not in ("succeeded", "failed", "cancelled"):
            return False
        _jobs.pop(job_id, None)
        return True


def _cancel_job(job_id: str, scope: dict[str, str]) -> bool:
    with _jobs_lock:
        job = _jobs.get(job_id)
        if not job or job.get("scope") != scope:
            return False
        if job["status"] in ("succeeded", "failed", "cancelled"):
            return True
        job["cancelEvent"].set()
        future: Future[Any] | None = job.get("future")
        if future and future.cancel():
            job.update(status="cancelled", updatedAt=time.time())
            _capacity.release()
        return True


def _validated_scope(raw_scope: Any) -> dict[str, str]:
    if not isinstance(raw_scope, dict):
        raise RequestRejected("A valid job scope is required.")
    guild_id = str(raw_scope.get("guild_id", "global"))
    user_id = str(raw_scope.get("user_id", "system"))
    if len(guild_id) > 64 or len(user_id) > 64 or not guild_id or not user_id:
        raise RequestRejected("A valid job scope is required.")
    return {"guild_id": guild_id, "user_id": user_id}


def _scope_from_request(handler: BaseHTTPRequestHandler) -> dict[str, str]:
    from urllib.parse import parse_qs, urlsplit
    query = parse_qs(urlsplit(handler.path).query)
    return _validated_scope({
        "guild_id": (query.get("guild_id") or ["global"])[0],
        "user_id": (query.get("user_id") or ["system"])[0],
    })


def _job_payload(raw_job: Any, scope: dict[str, str]) -> dict[str, Any]:
    if not isinstance(raw_job, dict):
        raise RequestRejected("Each scrape job must be a JSON object.")
    url, _, _ = validate_public_url(raw_job.get("url", ""))
    return {
        "url": url,
        "options": _bounded_options(raw_job.get("options")),
        "scope": scope,
    }


class WorkerHandler(BaseHTTPRequestHandler):
    server_version = "LemegetonBotasaurus/1.0"
    sys_version = ""

    def log_message(self, fmt: str, *args: Any) -> None:
        LOGGER.info("worker-http %s", fmt % args)

    def _send(self, status: int, payload: Any) -> None:
        body = _json_bytes(payload)
        self._send_bytes(status, body, "application/json; charset=utf-8")

    def _send_bytes(self, status: int, body: bytes, content_type: str, filename: str | None = None) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        if filename:
            self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
        self.end_headers()
        self.wfile.write(body)

    def _authorized(self) -> bool:
        authorization = self.headers.get("Authorization", "")
        supplied = authorization[7:] if authorization.startswith("Bearer ") else ""
        return bool(SETTINGS.worker_token) and hmac.compare_digest(supplied, SETTINGS.worker_token)

    def _read_json(self) -> dict[str, Any]:
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError as error:
            raise RequestRejected("Invalid request length.") from error
        if length < 2 or length > MAX_BODY_BYTES:
            raise RequestRejected("Request body must be between 2 bytes and 64 KiB.")
        try:
            payload = json.loads(self.rfile.read(length))
        except (json.JSONDecodeError, UnicodeDecodeError) as error:
            raise RequestRejected("Request body must contain valid JSON.") from error
        if not isinstance(payload, dict):
            raise RequestRejected("Request body must be a JSON object.")
        return payload

    def do_GET(self) -> None:
        from urllib.parse import parse_qs, urlsplit

        parsed = urlsplit(self.path)
        route = parsed.path.rstrip("/") or "/"
        if route == "/health":
            self._send(200, {
                "ok": True,
                "service": "lemegeton-botasaurus-worker",
                "engines": {
                    "obscura": _find_obscura() is not None,
                    "chromiumFallback": SETTINGS.chromium_fallback,
                },
                "features": ["task-api", "batch-jobs", "job-export", "cache", "structured-data", "same-host-links"],
                "capacity": {
                    "workers": SETTINGS.max_workers,
                    "queue": SETTINGS.max_queue,
                },
            })
            return
        if not self._authorized():
            self._send(401, {"error": "Unauthorized."})
            return
        try:
            scope = _scope_from_request(self)
        except RequestRejected as error:
            self._send(400, {"error": str(error)})
            return

        parts = route.strip("/").split("/") if route != "/" else []
        query = parse_qs(parsed.query)
        if parts == ["v1", "jobs"]:
            status = (query.get("status") or [None])[0]
            if status not in (None, "queued", "running", "succeeded", "failed", "cancelled"):
                self._send(400, {"error": "Unsupported job status filter."})
                return
            try:
                limit = int((query.get("limit") or ["50"])[0])
                offset = int((query.get("offset") or ["0"])[0])
            except ValueError:
                self._send(400, {"error": "Job pagination values must be integers."})
                return
            if not 1 <= limit <= MAX_JOB_PAGE_SIZE or not 0 <= offset <= 100000:
                self._send(400, {"error": "Job pagination is outside the supported bounds."})
                return
            self._send(200, _list_jobs(scope, status, limit, offset))
            return
        if parts == ["v1", "jobs", "stats"]:
            self._send(200, _job_stats(scope))
            return
        if len(parts) == 3 and parts[:2] == ["v1", "jobs"]:
            snapshot = _job_snapshot(parts[2], scope)
            self._send(200, snapshot) if snapshot else self._send(404, {"error": "Job not found."})
            return
        if len(parts) == 4 and parts[:2] == ["v1", "jobs"] and parts[3] in ("result", "export"):
            snapshot = _job_snapshot(parts[2], scope)
            if snapshot is None:
                self._send(404, {"error": "Job not found."})
                return
            if snapshot["status"] != "succeeded":
                self._send(409, {"error": "The job has no completed result.", "status": snapshot["status"]})
                return
            result = snapshot.get("result")
            if parts[3] == "result":
                body = _json_bytes(result)
                if len(body) > MAX_EXPORT_BYTES:
                    self._send(413, {"error": "The result exceeds the API response limit."})
                else:
                    self._send_bytes(200, body, "application/json; charset=utf-8")
                return
            export_format = (query.get("format") or ["json"])[0].lower()
            if export_format == "json":
                body = _json_bytes(result)
                content_type = "application/json; charset=utf-8"
                extension = "json"
            elif export_format in ("csv", "excel", "xlsx"):
                columns = ("url", "canonicalUrl", "title", "description", "statusCode", "engine",
                           "author", "publishedAt", "siteName", "image", "text", "fields",
                           "structuredData", "links", "feeds")
                values = [
                    json.dumps(result.get(key), ensure_ascii=False) if isinstance(result.get(key), (dict, list)) else result.get(key)
                    for key in columns
                ]
                if export_format == "csv":
                    output = io.StringIO(newline="")
                    writer = csv.writer(output)
                    writer.writerow(columns)
                    writer.writerow(values)
                    body = output.getvalue().encode("utf-8")
                    content_type = "text/csv; charset=utf-8"
                    extension = "csv"
                else:
                    workbook = Workbook(write_only=True)
                    sheet = workbook.create_sheet("Scrape Results")
                    sheet.append(list(columns))
                    sheet.append([
                        str(value)[:32767] if value is not None else None
                        for value in values
                    ])
                    output = io.BytesIO()
                    workbook.save(output)
                    body = output.getvalue()
                    content_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                    extension = "xlsx"
            else:
                self._send(400, {"error": "Export format must be json, csv, or excel."})
                return
            if len(body) > MAX_EXPORT_BYTES:
                self._send(413, {"error": "The export exceeds the configured size limit."})
                return
            self._send_bytes(200, body, content_type, f"botasaurus-{parts[2]}.{extension}")
            return
        self._send(404, {"error": "Not found."})

    def do_POST(self) -> None:
        if not self._authorized():
            self._send(401, {"error": "Unauthorized."})
            return
        route = self.path.split("?", 1)[0].rstrip("/")
        try:
            payload = self._read_json()
            if route in ("/v1/jobs", "/v1/jobs/batch"):
                scope = _validated_scope(payload.get("scope", {}))
                if route == "/v1/jobs":
                    body = _job_payload(payload, scope)
                    job_id = _new_job(body)
                    self._send(202, {"jobId": job_id, "status": "queued"})
                    return
                raw_jobs = payload.get("jobs")
                if not isinstance(raw_jobs, list) or not 1 <= len(raw_jobs) <= MAX_BATCH_JOBS:
                    raise RequestRejected(f"Batch jobs must contain between 1 and {MAX_BATCH_JOBS} items.")
                accepted: list[dict[str, Any]] = []
                rejected: list[dict[str, Any]] = []
                for index, raw_job in enumerate(raw_jobs):
                    try:
                        body = _job_payload(raw_job, scope)
                        job_id = _new_job(body)
                        accepted.append({
                            "index": index,
                            "jobId": job_id,
                            "url": body["url"],
                            "status": "queued",
                        })
                    except RequestRejected as error:
                        rejected.append({"index": index, "error": str(error)})
                    except RuntimeError as error:
                        rejected.append({"index": index, "error": str(error)})
                        rejected.extend(
                            {"index": next_index, "error": "The browser worker queue is full."}
                            for next_index in range(index + 1, len(raw_jobs))
                        )
                        break
                self._send(202, {"accepted": accepted, "rejected": rejected})
                return

            if route in ("/v1/jobs/cancel", "/v1/jobs/delete"):
                scope = _validated_scope(payload.get("scope", {}))
                ids = payload.get("jobIds")
                if not isinstance(ids, list) or not 1 <= len(ids) <= 100 or any(not isinstance(item, str) for item in ids):
                    raise RequestRejected("jobIds must contain between 1 and 100 job identifiers.")
                unique_ids = list(dict.fromkeys(ids))
                if route.endswith("/cancel"):
                    succeeded = [job_id for job_id in unique_ids if _cancel_job(job_id, scope)]
                    missing = [job_id for job_id in unique_ids if job_id not in succeeded]
                    self._send(200, {"cancelled": succeeded, "notFound": missing})
                else:
                    deleted = [job_id for job_id in unique_ids if _delete_job(job_id, scope)]
                    skipped = [job_id for job_id in unique_ids if job_id not in deleted]
                    self._send(200, {"deleted": deleted, "skipped": skipped})
                return

            parts = route.strip("/").split("/")
            if len(parts) == 4 and parts[:2] == ["v1", "jobs"] and parts[3] == "cancel":
                scope = _scope_from_request(self)
                if _cancel_job(parts[2], scope):
                    self._send(200, {"cancelled": True})
                else:
                    self._send(404, {"error": "Job not found."})
                return
            self._send(404, {"error": "Not found."})
        except RequestRejected as error:
            self._send(400, {"error": str(error)})
        except RuntimeError as error:
            self._send(429, {"error": str(error)})
        except Exception:
            LOGGER.exception("Could not process Botasaurus API request")
            self._send(500, {"error": "The worker could not process this API request."})

    def do_DELETE(self) -> None:
        if not self._authorized():
            self._send(401, {"error": "Unauthorized."})
            return
        parts = self.path.split("?", 1)[0].strip("/").split("/")
        try:
            scope = _scope_from_request(self)
        except RequestRejected as error:
            self._send(400, {"error": str(error)})
            return
        if len(parts) == 3 and parts[:2] == ["v1", "jobs"]:
            if _cancel_job(parts[2], scope):
                self._send(200, {"cancelled": True})
            else:
                self._send(404, {"error": "Job not found."})
            return
        if len(parts) == 4 and parts[:2] == ["v1", "jobs"] and parts[3] == "record":
            if _delete_job(parts[2], scope):
                self._send(200, {"deleted": True})
            else:
                self._send(409, {"error": "Only completed or cancelled jobs can be deleted."})
            return
        self._send(404, {"error": "Not found."})


class WorkerServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True


def serve() -> None:
    if len(SETTINGS.worker_token) < 32:
        raise SystemExit("BOTASAURUS_WORKER_TOKEN must contain at least 32 characters.")
    os.umask(0o077)
    Cache.set_cache_directory(str(SETTINGS.cache_dir))
    Path(SETTINGS.cache_dir).mkdir(parents=True, exist_ok=True)
    os.chmod(SETTINGS.cache_dir, 0o700)
    logging.basicConfig(
        level=getattr(logging, SETTINGS.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    server = WorkerServer((SETTINGS.host, SETTINGS.port), WorkerHandler)
    LOGGER.info("Botasaurus worker listening on %s:%s", SETTINGS.host, server.server_port)
    def request_shutdown(_signal: int, _frame: Any) -> None:
        threading.Thread(target=server.shutdown, daemon=True).start()

    signal.signal(signal.SIGTERM, request_shutdown)
    signal.signal(signal.SIGINT, request_shutdown)
    try:
        server.serve_forever(poll_interval=0.5)
    finally:
        server.server_close()
        _executor.shutdown(wait=True, cancel_futures=True)


def main() -> None:
    import argparse
    parser = argparse.ArgumentParser(description="Lemegeton Botasaurus browser worker")
    parser.add_argument("command", nargs="?", choices=("serve",), default="serve")
    args = parser.parse_args()
    if args.command == "serve":
        serve()


if __name__ == "__main__":
    main()
