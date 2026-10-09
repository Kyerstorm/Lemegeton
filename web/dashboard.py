"""Authenticated, guild-scoped web dashboard for Lemegeton.

The web UI is deliberately a thin client: permissions, command state, and audit
records are always resolved by the bot process and its existing dashboard DB.
"""
from __future__ import annotations

import asyncio
import json
import logging
import secrets
import sys
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

import aiohttp
from aiohttp import web

import config

logger = logging.getLogger("web.dashboard")
ROOT = Path(__file__).resolve().parent.parent
STATIC_DIR = ROOT / "web" / "static"
DISCORD_API = "https://discord.com/api/v10"
MANAGE_GUILD = 1 << 5
ADMINISTRATOR = 1 << 3
PROTECTED_COMMANDS = {"help", "feedback"}
ALLOWED_LOGS = {"bot.log", "dashboard.log"}


class DashboardWebServer:
    """Owns the OAuth2 flow and JSON API served alongside the Discord bot."""

    def __init__(self, bot):
        self.bot = bot
        self.runner: web.AppRunner | None = None
        self.site: web.TCPSite | None = None
        self.sessions: dict[str, dict[str, Any]] = {}
        self.oauth_states: dict[str, float] = {}
        self._http: aiohttp.ClientSession | None = None
        self._lock = asyncio.Lock()

    @property
    def configured(self) -> bool:
        return bool(
            config.DASHBOARD_CLIENT_ID
            and config.DASHBOARD_CLIENT_SECRET
            and config.DASHBOARD_SECRET_KEY
        )

    async def start(self) -> None:
        if not self.configured:
            logger.warning(
                "Web dashboard disabled: set DASHBOARD_CLIENT_ID, "
                "DASHBOARD_CLIENT_SECRET, and DASHBOARD_SECRET_KEY."
            )
            return
        if self.runner:
            return

        self._http = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=15, connect=5),
            headers={"User-Agent": "Lemegeton-Dashboard/1.0"},
        )
        app = web.Application(middlewares=[self._security_headers])
        app.router.add_get("/", self._home)
        app.router.add_get("/login", self._login)
        app.router.add_get("/oauth/callback", self._oauth_callback)
        app.router.add_get("/logout", self._logout)
        app.router.add_get("/api/bootstrap", self._api_bootstrap)
        app.router.add_get("/api/system", self._api_system)
        app.router.add_get("/api/guilds/{guild_id}/overview", self._api_overview)
        app.router.add_get("/api/guilds/{guild_id}/commands", self._api_commands)
        app.router.add_put("/api/guilds/{guild_id}/commands/{fullname:.*}", self._api_set_command)
        app.router.add_post("/api/guilds/{guild_id}/sync", self._api_sync)
        app.router.add_post("/api/guilds/{guild_id}/reset", self._api_reset)
        app.router.add_get("/api/guilds/{guild_id}/audit", self._api_audit)
        app.router.add_get("/api/logs", self._api_logs)
        app.router.add_get("/static/{filename}", self._static_file)
        self.runner = web.AppRunner(app, access_log=logger)
        await self.runner.setup()
        self.site = web.TCPSite(self.runner, config.DASHBOARD_HOST, config.DASHBOARD_PORT)
        try:
            await self.site.start()
        except Exception:
            await self.runner.cleanup()
            self.runner = None
            self.site = None
            await self._http.close()
            self._http = None
            raise
        logger.info("Web dashboard listening on %s:%s", config.DASHBOARD_HOST, config.DASHBOARD_PORT)

    async def stop(self) -> None:
        if self.runner:
            await self.runner.cleanup()
            self.runner = None
            self.site = None
        if self._http and not self._http.closed:
            await self._http.close()
        self._http = None
        self.sessions.clear()
        self.oauth_states.clear()

    @web.middleware
    async def _security_headers(self, request: web.Request, handler):
        if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
            origin = request.headers.get("Origin")
            if origin:
                expected = f"{request.scheme}://{request.host}"
                if origin.rstrip("/") != expected.rstrip("/"):
                    raise web.HTTPForbidden(text="Cross-origin requests are not allowed.")
        response = await handler(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; img-src 'self' https://cdn.discordapp.com data:; "
            "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
            "font-src 'self' https://fonts.gstatic.com; script-src 'self'; "
            "connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
        )
        return response

    def _cleanup_expired(self) -> None:
        now = time.time()
        ttl = max(300, config.DASHBOARD_SESSION_TTL)
        self.sessions = {
            key: value for key, value in self.sessions.items()
            if value.get("expires_at", 0) > now
        }
        self.oauth_states = {key: expiry for key, expiry in self.oauth_states.items() if expiry > now}
        # Bound memory usage even if an OAuth flow is abandoned.
        if len(self.sessions) > 5000:
            self.sessions = dict(list(self.sessions.items())[-2500:])

    def _session(self, request: web.Request) -> dict[str, Any] | None:
        self._cleanup_expired()
        session_id = request.cookies.get("lemegeton_session")
        if not session_id:
            return None
        session = self.sessions.get(session_id)
        if not session:
            return None
        session["expires_at"] = time.time() + max(300, config.DASHBOARD_SESSION_TTL)
        return session

    def _cookie(self, response: web.StreamResponse, session_id: str) -> None:
        response.set_cookie(
            "lemegeton_session", session_id,
            httponly=True, secure=config.DASHBOARD_COOKIE_SECURE,
            samesite="Lax", path="/",
            max_age=max(300, config.DASHBOARD_SESSION_TTL),
        )

    async def _require_session(self, request: web.Request) -> dict[str, Any]:
        session = self._session(request)
        if not session:
            raise web.HTTPUnauthorized(
                text=json.dumps({"error": "Please sign in with Discord again."}),
                content_type="application/json",
            )
        return session

    async def _json_body(self, request: web.Request) -> dict[str, Any]:
        if request.content_type != "application/json":
            raise web.HTTPUnsupportedMediaType(text="Expected application/json.")
        try:
            data = await request.json()
        except (json.JSONDecodeError, ValueError):
            raise web.HTTPBadRequest(text="Invalid JSON body.")
        if not isinstance(data, dict):
            raise web.HTTPBadRequest(text="Expected a JSON object.")
        return data

    async def _discord_request(self, method: str, path: str, **kwargs):
        if not self._http:
            raise web.HTTPServiceUnavailable(text="Discord OAuth client is unavailable.")
        async with self._http.request(method, f"{DISCORD_API}{path}", **kwargs) as response:
            try:
                data = await response.json()
            except Exception:
                data = {}
            if response.status >= 400:
                logger.warning("Discord API returned %s for %s", response.status, path)
                raise web.HTTPBadGateway(text="Discord authentication request failed.")
            return data

    async def _home(self, request: web.Request) -> web.StreamResponse:
        if not self._session(request):
            raise web.HTTPFound("/login")
        return await self._static_file(request, "dashboard.html")

    async def _login(self, request: web.Request) -> web.StreamResponse:
        if self._session(request):
            raise web.HTTPFound("/")
        state = secrets.token_urlsafe(32)
        self.oauth_states[state] = time.time() + 600
        params = {
            "client_id": str(config.DASHBOARD_CLIENT_ID),
            "redirect_uri": config.DASHBOARD_REDIRECT_URI,
            "response_type": "code",
            "scope": "identify guilds",
            "state": state,
        }
        raise web.HTTPFound("https://discord.com/oauth2/authorize?" + urlencode(params))

    async def _oauth_callback(self, request: web.Request) -> web.StreamResponse:
        error = request.query.get("error")
        if error:
            raise web.HTTPFound("/login?error=cancelled")
        code = request.query.get("code")
        state = request.query.get("state")
        if not code or not state or self.oauth_states.pop(state, 0) < time.time():
            raise web.HTTPBadRequest(text="OAuth state expired or invalid. Please sign in again.")

        payload = {
            "client_id": str(config.DASHBOARD_CLIENT_ID),
            "client_secret": config.DASHBOARD_CLIENT_SECRET,
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": config.DASHBOARD_REDIRECT_URI,
        }
        if not self._http:
            raise web.HTTPServiceUnavailable(text="OAuth client is unavailable.")
        async with self._http.post(
            f"{DISCORD_API}/oauth2/token",
            data=payload,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        ) as response:
            tokens = await response.json()
            if response.status >= 400 or not tokens.get("access_token"):
                logger.warning("Discord OAuth token exchange failed (%s)", response.status)
                raise web.HTTPUnauthorized(text="Discord sign-in failed. Please try again.")

        access_token = tokens["access_token"]
        headers = {"Authorization": f"Bearer {access_token}"}
        user = await self._discord_request("GET", "/users/@me", headers=headers)
        guilds = await self._discord_request("GET", "/users/@me/guilds", headers=headers)
        manageable = self._manageable_guilds(guilds if isinstance(guilds, list) else [])
        if not manageable:
            raise web.HTTPForbidden(
                text="No shared servers found. The bot must be in a server where your account has Manage Server or Administrator permission."
            )

        session_id = secrets.token_urlsafe(36)
        self.sessions[session_id] = {
            "user": {
                "id": str(user.get("id", "")),
                "username": user.get("username", "Discord user"),
                "global_name": user.get("global_name"),
                "avatar": user.get("avatar"),
            },
            "access_token": access_token,
            "refresh_token": tokens.get("refresh_token"),
            "access_expires_at": time.time() + max(60, int(tokens.get("expires_in", 3600)) - 60),
            "guilds": [str(g["id"]) for g in manageable],
            "expires_at": time.time() + max(300, config.DASHBOARD_SESSION_TTL),
        }
        response = web.HTTPFound("/")
        self._cookie(response, session_id)
        raise response

    async def _refresh_access_token(self, session: dict[str, Any]) -> str | None:
        token = session.get("access_token")
        if not token:
            return None
        if session.get("access_expires_at", 0) > time.time():
            return token
        refresh_token = session.get("refresh_token")
        if not refresh_token or not self._http:
            return None
        payload = {
            "client_id": str(config.DASHBOARD_CLIENT_ID),
            "client_secret": config.DASHBOARD_CLIENT_SECRET,
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
        }
        async with self._http.post(
            f"{DISCORD_API}/oauth2/token",
            data=payload,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        ) as response:
            refreshed = await response.json()
            if response.status >= 400 or not refreshed.get("access_token"):
                logger.info("Discord OAuth refresh expired; user must sign in again.")
                session["access_token"] = None
                return None
        session["access_token"] = refreshed["access_token"]
        session["refresh_token"] = refreshed.get("refresh_token", refresh_token)
        session["access_expires_at"] = time.time() + max(60, int(refreshed.get("expires_in", 3600)) - 60)
        return session["access_token"]

    def _manageable_guilds(self, oauth_guilds: list[dict[str, Any]]) -> list[dict[str, Any]]:
        bot_guilds = {str(g.id): g for g in self.bot.guilds}
        result = []
        for guild in oauth_guilds:
            guild_id = str(guild.get("id", ""))
            try:
                permissions = int(guild.get("permissions", 0))
            except (TypeError, ValueError):
                permissions = 0
            administrator = bool(permissions & ADMINISTRATOR)
            can_manage = bool(permissions & MANAGE_GUILD) or administrator
            if guild_id not in bot_guilds or not can_manage:
                continue
            live_guild = bot_guilds[guild_id]
            result.append({
                "id": guild_id,
                "name": live_guild.name,
                "icon": live_guild.icon.url if live_guild.icon else None,
                "administrator": administrator,
                "member_count": live_guild.member_count,
            })
        return sorted(result, key=lambda item: item["name"].casefold())

    async def _authorized_guild(self, request: web.Request) -> tuple[dict[str, Any], Any]:
        session = await self._require_session(request)
        guild_id = request.match_info.get("guild_id", "")
        if guild_id not in session.get("guilds", []):
            raise web.HTTPForbidden(
                text=json.dumps({"error": "You do not have Manage Server access to this guild."}),
                content_type="application/json",
            )
        guild = self.bot.get_guild(int(guild_id)) if guild_id.isdigit() else None
        if guild is None:
            raise web.HTTPNotFound(
                text=json.dumps({"error": "The bot is no longer in this server."}),
                content_type="application/json",
            )
        return session, guild

    def _dashboard_cog(self):
        cog = self.bot.get_cog("DashboardCog")
        if cog is None or getattr(self.bot, "_dashboard_db", None) is None:
            raise web.HTTPServiceUnavailable(
                text=json.dumps({"error": "The dashboard command registry is not ready yet."}),
                content_type="application/json",
            )
        return cog

    async def _static_file(self, request: web.Request, filename: str | None = None) -> web.Response:
        name = filename or request.match_info.get("filename", "")
        if name not in {"dashboard.html", "dashboard.css", "dashboard.js"}:
            raise web.HTTPNotFound()
        path = STATIC_DIR / name
        if not path.is_file():
            raise web.HTTPNotFound()
        content_type = {
            ".html": "text/html; charset=utf-8",
            ".css": "text/css; charset=utf-8",
            ".js": "application/javascript; charset=utf-8",
        }.get(path.suffix, "application/octet-stream")
        return web.Response(text=path.read_text(encoding="utf-8"), content_type=content_type)

    async def _api_bootstrap(self, request: web.Request) -> web.Response:
        session = await self._require_session(request)
        token = await self._refresh_access_token(session)
        if not token:
            raise web.HTTPUnauthorized()
        oauth_guilds = await self._discord_request(
            "GET", "/users/@me/guilds", headers={"Authorization": f"Bearer {token}"}
        )
        guilds = self._manageable_guilds(oauth_guilds if isinstance(oauth_guilds, list) else [])
        allowed = {str(g["id"]) for g in guilds}
        session["guilds"] = list(allowed)
        return web.json_response({
            "user": session["user"],
            "guilds": guilds,
            "selected_guild_id": guilds[0]["id"] if guilds else None,
        })

    async def _api_overview(self, request: web.Request) -> web.Response:
        session, guild = await self._authorized_guild(request)
        cog = self._dashboard_cog()
        config_data = await cog.db.get_guild_config(guild.id)
        commands = self._command_rows(config_data)
        return web.json_response({
            "guild": {"id": str(guild.id), "name": guild.name},
            "bot": {
                "ready": self.bot.is_ready(),
                "latency_ms": self.bot.latency * 1000 if self.bot.is_ready() else None,
                "guild_count": len(self.bot.guilds),
                "member_count": guild.member_count,
                "extension_count": len(self.bot.extensions),
            },
            "commands": {"total": len(commands), "enabled": sum(1 for c in commands if c["enabled"])},
        })

    def _command_rows(self, config_data: dict[str, Any]) -> list[dict[str, Any]]:
        from cogs_test.General_Commands.dashboard import COMMAND_REGISTRY
        commands = []
        command_state = config_data.get("commands", {})
        for fullname, meta in COMMAND_REGISTRY.all_commands():
            command = meta["command"]
            name = getattr(command, "name", fullname)
            protected = name in PROTECTED_COMMANDS
            commands.append({
                "fullname": fullname,
                "name": meta["display_name"],
                "description": meta.get("description", ""),
                "section": meta.get("section") or "Other",
                "protected": protected,
                "enabled": True if protected else bool(command_state.get(fullname, False)),
            })
        return commands

    async def _api_commands(self, request: web.Request) -> web.Response:
        session, guild = await self._authorized_guild(request)
        cog = self._dashboard_cog()
        config_data = await cog.db.get_guild_config(guild.id)
        return web.json_response({"commands": self._command_rows(config_data)})

    async def _api_set_command(self, request: web.Request) -> web.Response:
        session, guild = await self._authorized_guild(request)
        fullname = request.match_info.get("fullname", "")
        data = await self._json_body(request)
        if not isinstance(data.get("enabled"), bool):
            raise web.HTTPBadRequest(text=json.dumps({"error": "enabled must be a boolean."}), content_type="application/json")
        cog = self._dashboard_cog()
        from cogs_test.General_Commands.dashboard import COMMAND_REGISTRY, PROTECTED_CMD_NAMES
        meta = COMMAND_REGISTRY.get_meta(fullname)
        if not meta:
            raise web.HTTPNotFound(text=json.dumps({"error": "Command not found."}), content_type="application/json")
        if meta["command"].name in PROTECTED_CMD_NAMES:
            raise web.HTTPForbidden(text=json.dumps({"error": "This system command is protected."}), content_type="application/json")
        await cog.db.set_command(guild.id, fullname, data["enabled"])
        await cog.db.log_action(guild.id, int(session["user"]["id"]), "toggle_command", f"{fullname} -> {'enabled' if data['enabled'] else 'disabled'}")
        return web.json_response({"fullname": fullname, "enabled": data["enabled"]})

    async def _api_sync(self, request: web.Request) -> web.Response:
        session, guild = await self._authorized_guild(request)
        await self._json_body(request)
        self._dashboard_cog()
        from cogs_test.General_Commands.dashboard import attempt_sync_for_guild
        await attempt_sync_for_guild(self.bot, guild)
        return web.json_response({"synced": len(guild.app_commands) if hasattr(guild, "app_commands") else "enabled"})

    async def _api_reset(self, request: web.Request) -> web.Response:
        session, guild = await self._authorized_guild(request)
        await self._json_body(request)
        cog = self._dashboard_cog()
        await cog.db.reset_guild(guild.id)
        await cog.db.log_action(guild.id, int(session["user"]["id"]), "reset_dashboard", "Reset from web dashboard")
        from cogs_test.General_Commands.dashboard import attempt_sync_for_guild
        await attempt_sync_for_guild(self.bot, guild)
        return web.json_response({"ok": True})

    async def _api_audit(self, request: web.Request) -> web.Response:
        session, guild = await self._authorized_guild(request)
        cog = self._dashboard_cog()
        entries = await cog.db.last_audit_entries(guild.id, limit=75)
        return web.json_response({"entries": entries})

    async def _api_system(self, request: web.Request) -> web.Response:
        await self._require_session(request)
        started = getattr(self.bot, "dashboard_started_at", time.time())
        uptime = max(0, int(time.time() - started))
        hours, remainder = divmod(uptime, 3600)
        minutes, seconds = divmod(remainder, 60)
        return web.json_response({
            "ready": self.bot.is_ready(),
            "latency_ms": self.bot.latency * 1000 if self.bot.is_ready() else None,
            "guild_count": len(self.bot.guilds),
            "extension_count": len(self.bot.extensions),
            "extensions": sorted(self.bot.extensions.keys()),
            "python_version": sys.version.split()[0],
            "uptime": f"{hours}h {minutes}m {seconds}s",
        })

    async def _api_logs(self, request: web.Request) -> web.Response:
        await self._require_session(request)
        filename = request.query.get("file", "bot.log")
        if filename not in ALLOWED_LOGS:
            raise web.HTTPBadRequest(text=json.dumps({"error": "That log file is not available."}), content_type="application/json")
        path = ROOT / "logs" / filename
        if not path.is_file():
            return web.json_response({"name": filename, "content": "The requested log file does not exist yet."})
        try:
            content = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            raise web.HTTPServiceUnavailable(text=json.dumps({"error": "Could not read this log file."}), content_type="application/json")
        return web.json_response({"name": filename, "content": content[-30000:]})

    async def _logout(self, request: web.Request) -> web.Response:
        session_id = request.cookies.get("lemegeton_session")
        if session_id:
            self.sessions.pop(session_id, None)
        response = web.HTTPFound("/login")
        response.del_cookie("lemegeton_session", path="/")
        raise response
