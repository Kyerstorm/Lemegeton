"""Fetch an image from a link a member pasted, without letting the link reach private networks.

Rules (spec §6.5, tightened):
- https only, port 443 only, no username/password in the link, at most 2048 characters.
- The host is resolved first and EVERY address must be on the public internet: an allow-list
  (ipaddress `is_global`, and not multicast), not a block-list. IPv4 addresses hidden inside IPv6
  (IPv4-mapped, 6to4, NAT64, Teredo, IPv4-compatible) are unwrapped and must be public too.
- The connection is pinned to the addresses that were checked, so a second DNS answer can't
  switch it to a private address (DNS rebinding). TLS still checks the real host name.
- No redirects, no proxies from the environment, no cookies.
- Whole fetch (DNS included) limited to LINK_TIMEOUT seconds; the body is streamed and cut off past
  the size limit (checked against Content-Length first). Only image/png and image/jpeg answers.
The caller still checks the bytes themselves (images.inspect_source).
"""
from __future__ import annotations

import asyncio
import ipaddress
import socket
from typing import Awaitable, Callable, List, Optional, Tuple
from urllib.parse import urlsplit

import aiohttp
from aiohttp.abc import AbstractResolver, ResolveResult

import config
from helpers.lunar_roles.images import HEIC_MESSAGE, HEIF_CONTENT_TYPES

LINK_TIMEOUT = 10.0
MAX_URL_LENGTH = 2048
ALLOWED_TYPES = {"image/png": "PNG", "image/jpeg": "JPEG", "image/jpg": "JPEG"}


def user_agent() -> str:
    """Identifies the bot with a contact address (its picker page). Some sites, like Wikimedia,
    refuse requests whose User-Agent doesn't include one."""
    return f"LemegetonLunarRoles/1.0 (+{config.LUNAR_PUBLIC_URL}/lunar; role icon fetch)"
CHUNK = 64 * 1024

_NAT64 = (ipaddress.ip_network("64:ff9b::/96"), ipaddress.ip_network("64:ff9b:1::/48"))


class FetchError(Exception):
    """A user-facing reason a link can't be used."""

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


PRIVATE_MESSAGE = "That link points to a private or local network address, which isn't allowed."


def _embedded_ipv4(ip: ipaddress.IPv6Address) -> List[ipaddress.IPv4Address]:
    """IPv4 addresses carried inside an IPv6 address (each must be public too)."""
    found = []
    if ip.ipv4_mapped is not None:
        found.append(ip.ipv4_mapped)
    if ip.sixtofour is not None:
        found.append(ip.sixtofour)
    if ip.teredo is not None:
        found.extend(ip.teredo)  # (server, client)
    if any(ip in net for net in _NAT64):
        found.append(ipaddress.IPv4Address(int(ip) & 0xFFFFFFFF))
    if int(ip) >> 32 == 0 and int(ip) > 1:  # deprecated IPv4-compatible ::a.b.c.d
        found.append(ipaddress.IPv4Address(int(ip)))
    return found


def address_allowed(address: str) -> bool:
    """True only for public internet addresses (allow-list)."""
    try:
        ip = ipaddress.ip_address(address.split("%", 1)[0])
    except ValueError:
        return False
    if not ip.is_global or ip.is_multicast:
        return False
    if isinstance(ip, ipaddress.IPv6Address):
        return all(inner.is_global and not inner.is_multicast for inner in _embedded_ipv4(ip))
    return True


def check_url(url: object, allow_http: bool = False, allowed_port: int = 443) -> Tuple[str, str]:
    """Validate the link's shape. Returns (cleaned url, host)."""
    if not isinstance(url, str) or not url.strip():
        raise FetchError("Paste a link to a PNG or JPEG image.")
    url = url.strip()
    if len(url) > MAX_URL_LENGTH:
        raise FetchError("That link is too long.")
    if any(ch.isspace() or ord(ch) < 32 for ch in url):
        raise FetchError("That link has spaces or hidden characters in it.")
    try:
        parts = urlsplit(url)
        port = parts.port
    except ValueError:
        raise FetchError("That doesn't look like a valid link.")
    schemes = {"https", "http"} if allow_http else {"https"}
    if parts.scheme.lower() not in schemes:
        raise FetchError("Only https:// links work.")
    if parts.username is not None or parts.password is not None:
        raise FetchError("Links with a username or password aren't allowed.")
    host = (parts.hostname or "").rstrip(".").lower()
    if not host:
        raise FetchError("That doesn't look like a valid link.")
    if port is not None and port != allowed_port:
        raise FetchError("Only links on the normal https port (443) work.")
    if host == "localhost" or host.endswith(".localhost"):
        raise FetchError(PRIVATE_MESSAGE)
    return url, host


async def resolve_public(host: str) -> List[str]:
    """Every address the host resolves to; refuses if any of them isn't public."""
    try:
        literal = ipaddress.ip_address(host.strip("[]"))
    except ValueError:
        literal = None
    if literal is not None:
        if not address_allowed(str(literal)):
            raise FetchError(PRIVATE_MESSAGE)
        return [str(literal)]
    try:
        lookup_host = host.encode("idna").decode("ascii")
    except UnicodeError:
        raise FetchError("That link's address isn't valid.")
    try:
        infos = await asyncio.get_running_loop().getaddrinfo(lookup_host, 443, type=socket.SOCK_STREAM)
    except (socket.gaierror, UnicodeError, OSError):
        raise FetchError("I couldn't find that website. Check the link.")
    addresses = sorted({info[4][0] for info in infos})
    if not addresses:
        raise FetchError("I couldn't find that website. Check the link.")
    if not all(address_allowed(a) for a in addresses):
        raise FetchError(PRIVATE_MESSAGE)
    return addresses


class PinnedResolver(AbstractResolver):
    """Hands aiohttp only the addresses that were already checked, for the one expected host."""

    def __init__(self, host: str, addresses: List[str]):
        self.host = host
        self.addresses = addresses

    async def resolve(self, host: str, port: int = 0, family: socket.AddressFamily = socket.AF_INET) -> List[ResolveResult]:
        if host.rstrip(".").lower() != self.host:
            raise OSError(f"unexpected host {host!r}")
        results: List[ResolveResult] = []
        for address in self.addresses:
            fam = socket.AF_INET6 if ":" in address else socket.AF_INET
            if family not in (0, socket.AF_UNSPEC) and fam != family:
                continue
            results.append(ResolveResult(hostname=host, host=address, port=port, family=fam,
                                         proto=0, flags=socket.AI_NUMERICHOST))
        if not results:
            raise OSError("no checked address for this family")
        return results

    async def close(self) -> None:
        pass


Resolver = Callable[[str], Awaitable[List[str]]]


async def fetch_image(url: object, max_bytes: int, timeout: float = LINK_TIMEOUT, *,
                      resolve: Resolver = resolve_public, allow_http: bool = False,
                      allowed_port: int = 443) -> Tuple[bytes, str, str]:
    """Download an image link safely. Returns (bytes, "PNG"|"JPEG", host).

    resolve / allow_http / allowed_port exist only so tests can use a local test server.
    """
    url, host = check_url(url, allow_http=allow_http, allowed_port=allowed_port)
    try:
        return await asyncio.wait_for(_fetch(url, host, max_bytes, timeout, resolve), timeout)
    except asyncio.TimeoutError:
        raise FetchError(f"That website took too long (over {timeout:.0f} seconds).")


async def _fetch(url: str, host: str, max_bytes: int, timeout: float, resolve: Resolver) -> Tuple[bytes, str, str]:
    addresses = await resolve(host)
    connector = aiohttp.TCPConnector(resolver=PinnedResolver(host, addresses), use_dns_cache=False,
                                     limit=2, force_close=True)
    session = aiohttp.ClientSession(
        connector=connector,
        timeout=aiohttp.ClientTimeout(total=timeout),
        trust_env=False,
        cookie_jar=aiohttp.DummyCookieJar(),
        headers={"User-Agent": user_agent(), "Accept": "image/png, image/jpeg"},
    )
    try:
        async with session.get(url, allow_redirects=False) as response:
            if 300 <= response.status < 400:
                raise FetchError("That link redirects somewhere else. Use the image's own address "
                                 "(right-click the image → Copy image address).")
            if response.status != 200:
                raise FetchError(f"The website answered with an error ({response.status}).")
            kind = ALLOWED_TYPES.get(response.content_type.lower())
            if response.content_type.lower() in HEIF_CONTENT_TYPES:
                raise FetchError(HEIC_MESSAGE)
            if kind is None:
                raise FetchError("That link isn't a PNG or JPEG image.")
            too_big = FetchError(f"That image is larger than {max_bytes // (1024 * 1024) or 1} MB.")
            if response.content_length is not None and response.content_length > max_bytes:
                raise too_big
            data = bytearray()
            async for chunk in response.content.iter_chunked(CHUNK):
                data.extend(chunk)
                if len(data) > max_bytes:
                    raise too_big
            return bytes(data), kind, host
    except FetchError:
        raise
    except asyncio.TimeoutError:  # aiohttp's own timeouts are also ClientErrors, so this comes first
        raise FetchError(f"That website took too long (over {timeout:.0f} seconds).")
    except aiohttp.ClientConnectorCertificateError:
        raise FetchError("That website's security certificate isn't valid.")
    except (aiohttp.ClientError, OSError):
        raise FetchError("I couldn't download that image. Check the link and try again.")
    finally:
        await session.close()
