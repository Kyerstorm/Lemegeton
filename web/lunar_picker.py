"""Lunar Roles color picker: page, static files and JSON API under /lunar.

Works without the dashboard's OAuth settings. Every API call needs the link token in
an `Authorization: Bearer` header; the token is never accepted in a URL. Each call
re-checks that the member is still in the server, still eligible and still has a role.
Role logic stays in helpers/lunar_roles/service.py.
"""
from __future__ import annotations

import logging
import time
from collections import deque
from pathlib import Path
from typing import Deque, Dict, Optional
from urllib.parse import urlsplit

from aiohttp import web

import config
from helpers.lunar_roles import COMMAND_GROUP, service, tokens

logger = logging.getLogger("web.lunar_picker")
STATIC_DIR = Path(__file__).resolve().parent / "static" / "lunar"
BASE = "/lunar"
STATIC_FILES = {
    "picker.css": "text/css",
    "picker.js": "application/javascript",
    "lunar-theme.css": "text/css",
}
TOKEN_QUERY_KEYS = {"token", "t", "access_token", "auth", "key"}

# Requests with an unknown or expired token, per client address.
FAILED_LIMIT = 30
FAILED_WINDOW = 600.0

EXPIRED_MESSAGE = f"This link expired. Run `/{COMMAND_GROUP} color-picker` again for a new one."

CSP = (
    "default-src 'none'; script-src 'self'; style-src 'self'; "
    "img-src 'self' data: https://cdn.discordapp.com https://media.discordapp.net; "
    "connect-src 'self'; font-src 'self'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'"
)


def is_picker_path(path: str) -> bool:
    return path == BASE or path.startswith(BASE + "/")


def client_ip(request: web.Request, trust_proxy: Optional[bool] = None) -> str:
    """The caller's address, for rate limiting.

    trust_proxy=False (the default): X-Forwarded-For is ignored completely.
    trust_proxy=True: use the rightmost X-Forwarded-For entry, the one the trusted proxy
    appended. Everything left of it came from the client and can be made up.
    """
    if trust_proxy is None:
        trust_proxy = config.LUNAR_TRUST_PROXY
    if trust_proxy:
        hops = [hop.strip() for value in request.headers.getall("X-Forwarded-For", [])
                for hop in value.split(",") if hop.strip()]
        if hops:
            return hops[-1]
    return request.remote or "unknown"


def _origin(url: str) -> str:
    parts = urlsplit(url)
    return f"{parts.scheme}://{parts.netloc}".lower()


class LunarPicker:
    """Registers the /lunar routes on the bot's aiohttp app."""

    def __init__(self, bot):
        self.bot = bot
        self._failed: Dict[str, Deque[float]] = {}

    def register(self, app: web.Application) -> None:
        app.middlewares.append(self._middleware)
        app.router.add_get(BASE, self._page)
        app.router.add_get(BASE + "/", self._page)
        app.router.add_get(BASE + "/static/{filename}", self._static)
        app.router.add_get(BASE + "/api/state", self._api_state)

    # ------------------------------------------------------------------ security

    @web.middleware
    async def _middleware(self, request: web.Request, handler):
        if not is_picker_path(request.path):
            return await handler(request)
        if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
            origin = request.headers.get("Origin")
            allowed = {_origin(config.LUNAR_PUBLIC_URL), f"{request.scheme}://{request.host}".lower()}
            if origin and origin.rstrip("/").lower() not in allowed:
                return self._headers(self._error(403, "cross_origin", "Requests from other sites aren't allowed."))
        try:
            response = await handler(request)
        except web.HTTPException as exc:
            if exc.status == 404:
                response = self._error(404, "not_found", "Not found.")
            else:
                raise
        return self._headers(response)

    @staticmethod
    def _headers(response: web.StreamResponse) -> web.StreamResponse:
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        response.headers["Content-Security-Policy"] = CSP
        return response

    @staticmethod
    def _error(status: int, code: str, message: str) -> web.Response:
        return web.json_response({"ok": False, "error": code, "message": message}, status=status)

    def _failed_allowed(self, ip: str) -> bool:
        now = time.monotonic()
        bucket = self._failed.setdefault(ip, deque())
        while bucket and bucket[0] <= now - FAILED_WINDOW:
            bucket.popleft()
        return len(bucket) < FAILED_LIMIT

    def _note_failed(self, ip: str) -> None:
        self._failed.setdefault(ip, deque()).append(time.monotonic())

    async def _member_for(self, request: web.Request, write: bool = False):
        """Resolve the bearer token to a live member, or return an error response."""
        if TOKEN_QUERY_KEYS & {key.lower() for key in request.query}:
            return None, None, self._error(
                400, "token_in_url", "The link token must be sent in the Authorization header, not in the address.")
        header = request.headers.get("Authorization", "")
        token = header[7:].strip() if header[:7].lower() == "bearer " else ""
        link = tokens.lookup(token)
        if link is None:
            # Only bad tokens are limited per address. A valid link always gets through, so
            # visitors sharing one address (e.g. behind a proxy) can't lock each other out.
            ip = client_ip(request)
            if not self._failed_allowed(ip):
                return None, None, self._error(429, "too_many_attempts", "Too many invalid links. Try again in a few minutes.")
            self._note_failed(ip)
            return None, None, self._error(401, "expired", EXPIRED_MESSAGE)
        if not tokens.allow(link, write=write):
            return None, None, self._error(429, "rate_limited", "Slow down a little - try again in a minute.")
        guild = self.bot.get_guild(link.guild_id)
        if guild is None or guild.unavailable:
            return None, None, self._error(503, "guild_unavailable", "The server isn't available right now. Try again soon.")
        member = guild.get_member(link.user_id)
        if member is None:
            return None, None, self._error(403, "not_member", "You're no longer in this server.")
        return link, member, None

    # ------------------------------------------------------------------ routes

    async def _page(self, request: web.Request) -> web.Response:
        return web.Response(text=(STATIC_DIR / "picker.html").read_text(encoding="utf-8"), content_type="text/html")

    async def _static(self, request: web.Request) -> web.Response:
        name = request.match_info.get("filename", "")
        content_type = STATIC_FILES.get(name)
        path = STATIC_DIR / name
        if content_type is None or not path.is_file():
            raise web.HTTPNotFound()
        return web.Response(text=path.read_text(encoding="utf-8"), content_type=content_type)

    async def _api_state(self, request: web.Request) -> web.Response:
        link, member, error = await self._member_for(request)
        if error is not None:
            return error
        result = await service.picker_state(member)
        if not result.ok:
            return self._error(403, "not_allowed", result.message)
        return web.json_response({"ok": True, "expires_at": int(link.expires_at), "state": result.data})
