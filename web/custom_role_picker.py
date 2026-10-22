"""Custom Roles color picker: page, static files and JSON API under /custom-roles.

Works without the dashboard's OAuth settings. Every API call needs the link token in
an `Authorization: Bearer` header; the token is never accepted in a URL. Each call
re-checks that the member is still in the server, still eligible and still has a role.
Role logic stays in helpers/custom_roles/service.py.
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from collections import deque
from pathlib import Path
from typing import Deque, Dict, Optional
from urllib.parse import urlsplit

from aiohttp import web

import config
from helpers.custom_roles import COMMAND_GROUP, images, safe_fetch, service, tokens, validation

logger = logging.getLogger("web.custom_role_picker")
STATIC_DIR = Path(__file__).resolve().parent / "static" / "custom_roles"
BASE = "/custom-roles"
STATIC_FILES = {
    "picker.css": "text/css",
    "picker.js": "application/javascript",
    "theme.css": "text/css",
    "favicon.svg": "image/svg+xml",
}
MAX_BODY = 2048  # bytes; write requests are tiny JSON objects
MULTIPART_OVERHEAD = 64 * 1024  # room for the multipart headers and the crop field
FETCH_LIMIT = 6          # image links one member may fetch per FETCH_WINDOW
FETCH_WINDOW = 60.0
FETCH_CONCURRENCY = 3    # image links fetched at the same time, for everyone together
MODES = (service.MODE_SOLID, service.MODE_GRADIENT, service.MODE_HOLOGRAPHIC)
TOKEN_QUERY_KEYS = {"token", "t", "access_token", "auth", "key"}

# Requests with an unknown or expired token, per client address.
FAILED_LIMIT = 30
FAILED_WINDOW = 600.0

EXPIRED_MESSAGE = f"This link expired. Run `/{COMMAND_GROUP}` and press **Color picker** for a new one."

CSP = (
    "default-src 'none'; script-src 'self'; style-src 'self'; "
    "img-src 'self' data: blob:; "
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
        trust_proxy = config.CUSTOM_ROLES_TRUST_PROXY
    if trust_proxy:
        hops = [hop.strip() for value in request.headers.getall("X-Forwarded-For", [])
                for hop in value.split(",") if hop.strip()]
        if hops:
            return hops[-1]
    return request.remote or "unknown"


def _relative(unix_time: int) -> str:
    left = max(0, unix_time - int(time.time()))
    return f"in {service.format_duration(left)}" if left else "now"


def web_text(text: str) -> str:
    """Turn a Discord-formatted service message into plain text for the page.

    The page inserts it with textContent, so this is about readability, not safety.
    """
    text = re.sub(r"<t:(\d+)(?::[tTdDfFR])?>", lambda m: _relative(int(m.group(1))), text or "")
    text = re.sub(r"<@&\d+>", "a role", text)
    text = re.sub(r"<@!?\d+>", "a member", text)
    text = re.sub(r"<#\d+>", "a channel", text)
    return text.replace("**", "").replace("`", "")


def _expiry(link: tokens.PickerLink) -> dict:
    return {"expires_at": int(link.expires_at), "max_expires_at": int(link.max_expires_at)}


def _origin(url: str) -> str:
    parts = urlsplit(url)
    return f"{parts.scheme}://{parts.netloc}".lower()


class CustomRolePicker:
    """Registers the /custom-roles routes on the bot's aiohttp app."""

    def __init__(self, bot):
        self.bot = bot
        self._failed: Dict[str, Deque[float]] = {}
        self._fetches: Dict[tuple, Deque[float]] = {}
        self._fetch_slots = asyncio.Semaphore(FETCH_CONCURRENCY)
        self.fetch_options: dict = {}  # tests only: lets the link fetcher reach a local test server

    def register(self, app: web.Application) -> None:
        app.middlewares.append(self._middleware)
        app.router.add_get(BASE, self._page)
        app.router.add_get(BASE + "/", self._page)
        app.router.add_get(BASE + "/static/{filename}", self._static)
        app.router.add_get(BASE + "/api/state", self._api_state)
        app.router.add_get(BASE + "/api/palette", self._api_palette)
        app.router.add_post(BASE + "/api/color", self._api_color)
        app.router.add_post(BASE + "/api/name", self._api_name)
        app.router.add_post(BASE + "/api/icon", self._api_icon)
        app.router.add_delete(BASE + "/api/icon", self._api_icon_remove)
        app.router.add_post(BASE + "/api/icon/emoji", self._api_icon_emoji)
        app.router.add_post(BASE + "/api/icon/fetch", self._api_icon_fetch)
        app.router.add_get(BASE + "/api/icon/source", self._api_icon_source)

    # ------------------------------------------------------------------ security

    @web.middleware
    async def _middleware(self, request: web.Request, handler):
        if not is_picker_path(request.path):
            return await handler(request)
        if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
            origin = request.headers.get("Origin")
            allowed = {_origin(config.CUSTOM_ROLES_PUBLIC_URL), f"{request.scheme}://{request.host}".lower()}
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
        return web.json_response({"ok": False, "error": code, "message": web_text(message)}, status=status)

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
        return web.Response(text=path.read_text(encoding="utf-8"), content_type=content_type, charset="utf-8")

    async def _api_state(self, request: web.Request) -> web.Response:
        link, member, error = await self._member_for(request)
        if error is not None:
            return error
        result = await service.picker_state(member)
        if not result.ok:
            return self._error(403, "not_allowed", result.message)
        tokens.touch(link)
        return web.json_response({"ok": True, **_expiry(link), "state": result.data})

    async def _api_palette(self, request: web.Request) -> web.Response:
        link, member, error = await self._member_for(request)
        if error is not None:
            return error
        check = await service.precheck(member)
        if check is not None:
            return self._error(403, "not_allowed", web_text(check.message))
        result = await service.get_palette(member)
        tokens.touch(link)
        if not result.ok:
            return web.json_response({"ok": False, "message": web_text(result.message), "colors": [], **_expiry(link)})
        return web.json_response({"ok": True, "colors": [validation.format_hex(c) for c in result.data], **_expiry(link)})

    # ------------------------------------------------------------------ writes

    async def _read_json(self, request: web.Request):
        """(body dict, None) or (None, error response)."""
        if request.content_length is not None and request.content_length > MAX_BODY:
            return None, self._error(413, "too_big", "That request is too big.")
        raw = await request.content.read(MAX_BODY + 1)
        if len(raw) > MAX_BODY:
            return None, self._error(413, "too_big", "That request is too big.")
        try:
            body = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, ValueError):
            return None, self._error(400, "bad_json", "That request couldn't be read.")
        if not isinstance(body, dict):
            return None, self._error(400, "bad_json", "That request couldn't be read.")
        return body, None

    async def _write(self, request: web.Request, action, body: str = "json") -> web.Response:
        """Shared checks for write calls, then run action(member, data) -> Result.

        body: "json" (data = the parsed object), "multipart" (data = the request, read by the
        action) or "none" (data = {}).
        """
        link, member, error = await self._member_for(request, write=True)
        if error is not None:
            return error
        if body == "json" and request.content_type != "application/json":
            return self._error(415, "json_only", "Send JSON (Content-Type: application/json).")
        if body == "multipart" and request.content_type != "multipart/form-data":
            return self._error(415, "multipart_only", "Send the image as multipart/form-data.")
        check = await service.precheck(member)
        if check is not None:
            return self._error(403, "not_allowed", web_text(check.message))
        data = {}
        if body == "json":
            data, error = await self._read_json(request)
            if error is not None:
                return error
        elif body == "multipart":
            data = request

        result = await action(member, data)
        if isinstance(result, web.Response):
            return result  # a bad request found by the action
        state = await service.picker_state(member)
        tokens.touch(link)
        payload = {
            **_expiry(link),
            "ok": result.ok,
            "message": web_text(result.message),
            "notes": [web_text(n) for n in result.notes],
            "state": state.data if state.ok else None,
        }
        if isinstance(result.data, dict) and "retry_at" in result.data:
            payload["retry_at"] = result.data["retry_at"]
        return web.json_response(payload)

    async def _api_color(self, request: web.Request) -> web.Response:
        async def action(member, body):
            mode = body.get("mode")
            if mode not in MODES:
                return self._error(400, "bad_mode", "Pick Solid, Gradient or Holographic.")
            if mode == service.MODE_HOLOGRAPHIC:
                return await service.set_colors(member, mode)
            colors = []
            for key, label in (("primary", "Primary"), ("secondary", "Secondary")):
                if key == "secondary" and mode == service.MODE_SOLID:
                    break
                raw = body.get(key)
                value = validation.parse_hex(raw) if isinstance(raw, str) and len(raw) <= 16 else None
                if value is None:
                    return self._error(400, "bad_color", f"{label} isn't a hex color. Try #FF66AA.")
                colors.append(value)
            return await service.set_colors(member, mode, *colors)
        return await self._write(request, action)

    async def _api_name(self, request: web.Request) -> web.Response:
        async def action(member, body):
            name = body.get("name")
            if not isinstance(name, str) or len(name) > validation.NAME_MAX * 4:
                return self._error(400, "bad_name", f"Role names can be at most {validation.NAME_MAX} characters.")
            return await service.rename(member, name)
        return await self._write(request, action)

    # ------------------------------------------------------------------ role icon

    async def _api_icon(self, request: web.Request) -> web.Response:
        """Multipart: "image" = the original PNG/JPEG exactly as chosen, "crop" = {"x", "y", "size"}."""
        async def action(member, req):
            limit = images.source_max_bytes()
            too_big = self._error(413, "too_big", f"Images can be at most {images.format_size(limit)}.")
            if req.content_length is not None and req.content_length > limit + MULTIPART_OVERHEAD:
                return too_big
            image, crop = None, None
            try:
                reader = await req.multipart()
                while True:
                    part = await reader.next()
                    if part is None:
                        break
                    if part.name == "image" and image is None:
                        data = bytearray()
                        while True:
                            chunk = await part.read_chunk(64 * 1024)
                            if not chunk:
                                break
                            data.extend(chunk)
                            if len(data) > limit:
                                return too_big
                        image = bytes(data)
                    elif part.name == "crop" and crop is None:
                        raw = await part.read_chunk(256)
                        if await part.read_chunk(1):
                            return self._error(400, "bad_crop", "That crop isn't valid. Try cropping again.")
                        crop = raw
                    else:
                        return self._error(400, "bad_upload", "That upload couldn't be read.")
            except (ValueError, AssertionError, RuntimeError):
                return self._error(400, "bad_upload", "That upload couldn't be read.")
            if not image:
                return self._error(400, "no_image", "Choose an image first.")
            box = None
            if crop is not None:
                try:
                    value = json.loads(crop.decode("utf-8"))
                    box = tuple(value[k] for k in ("x", "y", "size"))
                    if not all(isinstance(v, int) and not isinstance(v, bool) for v in box):
                        raise ValueError
                except (UnicodeDecodeError, ValueError, TypeError, KeyError):
                    return self._error(400, "bad_crop", "That crop isn't valid. Try cropping again.")
            return await service.set_icon(member, image=image, crop=box)
        return await self._write(request, action, body="multipart")

    async def _api_icon_emoji(self, request: web.Request) -> web.Response:
        async def action(member, body):
            emoji = body.get("emoji")
            if not isinstance(emoji, str) or not emoji.strip() or len(emoji) > 64:
                return self._error(400, "bad_emoji", "Type or paste one emoji.")
            return await service.set_icon(member, emoji=emoji.strip())
        return await self._write(request, action)

    async def _api_icon_remove(self, request: web.Request) -> web.Response:
        async def action(member, _):
            return await service.remove_icon(member)
        return await self._write(request, action, body="none")

    def _fetch_allowed(self, key: tuple) -> bool:
        now = time.monotonic()
        bucket = self._fetches.setdefault(key, deque())
        while bucket and bucket[0] <= now - FETCH_WINDOW:
            bucket.popleft()
        if len(bucket) >= FETCH_LIMIT:
            return False
        bucket.append(now)
        return True

    @staticmethod
    def _image_response(link, data: bytes, kind: str) -> web.Response:
        expiry = _expiry(link)
        return web.Response(body=data, content_type="image/png" if kind == "PNG" else "image/jpeg", headers={
            "X-Picker-Expires-At": str(expiry["expires_at"]),
            "X-Picker-Max-Expires-At": str(expiry["max_expires_at"]),
            "Content-Disposition": "attachment",
        })

    async def _api_icon_fetch(self, request: web.Request) -> web.Response:
        """{url} -> the image's bytes for the crop editor (nothing is applied)."""
        link, member, error = await self._member_for(request, write=True)
        if error is not None:
            return error
        if request.content_type != "application/json":
            return self._error(415, "json_only", "Send JSON (Content-Type: application/json).")
        check = await service.precheck(member)
        if check is not None:
            return self._error(403, "not_allowed", web_text(check.message))
        body, error = await self._read_json(request)
        if error is not None:
            return error
        if not service.icons_usable(member.guild):
            return self._error(403, "no_icons", service.NO_ICONS_MESSAGE)
        if not self._fetch_allowed((member.guild.id, member.id)):
            return self._error(429, "too_many_fetches", "That's a lot of links in a row. Wait a minute and try again.")
        if self._fetch_slots.locked():
            return self._error(503, "busy", "I'm fetching a lot of images right now. Try again in a few seconds.")
        async with self._fetch_slots:
            host = "?"
            try:
                data, kind, host = await safe_fetch.fetch_image(
                    body.get("url"), images.source_max_bytes(), **self.fetch_options)
                await asyncio.to_thread(images.inspect_source, data)
            except safe_fetch.FetchError as exc:
                service.logger.info("Icon link from %s in guild %s refused (%s): %s", member.id, member.guild.id, host, exc.message)
                return self._error(422, "fetch_refused", exc.message)
            except images.ImageError as exc:
                service.logger.info("Icon link from %s in guild %s: bad image from %s: %s", member.id, member.guild.id, host, exc.message)
                return self._error(422, "bad_image", exc.message)
        service.logger.info("Icon link from %s in guild %s fetched from %s (%s bytes)", member.id, member.guild.id, host, len(data))
        tokens.touch(link)
        return self._image_response(link, data, kind)

    async def _api_icon_source(self, request: web.Request) -> web.Response:
        """The original image of the current icon, for "Edit current crop"."""
        link, member, error = await self._member_for(request)
        if error is not None:
            return error
        check = await service.precheck(member)
        if check is not None:
            return self._error(403, "not_allowed", web_text(check.message))
        data = await service.icon_source(member)
        kind = images.sniff_type(data) if data else None
        if kind is None:
            return self._error(404, "no_icon", "Your role doesn't have an image icon to edit.")
        tokens.touch(link)
        return self._image_response(link, data, kind)
