"""Private management bridge used only by the Rust dashboard process.

This adapter runs inside the existing discord.py process so commands are changed
and synchronized through the live bot, rather than through a simulated API.
It binds to loopback and requires a separate shared secret on every request.
"""
from __future__ import annotations

import asyncio
import hmac
import json
import logging
import os
import sys
import time
from pathlib import Path
from typing import Any

from aiohttp import web

import config

logger = logging.getLogger("web.dashboard_bridge")
ROOT = Path(__file__).resolve().parent.parent
PROTECTED_NAMES = {"help", "feedback"}
LOG_FILES = {"bot.log", "dashboard.log"}


def _error(message: str, status: int) -> web.Response:
    return web.json_response({"error": message}, status=status)


def _valid_identifier(value: Any) -> bool:
    text = str(value) if isinstance(value, (str, int)) else ""
    return 0 < len(text) <= 20 and text.isascii() and text.isdigit() and int(text) > 0


def _connection_status(ready: bool, was_ready: bool, latency_ms: float | None) -> str:
    if not ready:
        return "offline" if was_ready else "connecting"
    return "degraded" if latency_ms is not None and latency_ms >= 500 else "online"


def _effective_enabled(fullname: str, meta: dict[str, Any], cfg: dict[str, Any]) -> bool:
    command_name = getattr(meta.get("command"), "name", fullname)
    if command_name in PROTECTED_NAMES:
        return True
    commands = cfg.get("commands", {})
    if fullname in commands:
        return commands[fullname] is True
    section = meta.get("section") or "Other"
    if section in cfg.get("sections", {}):
        return cfg["sections"][section] is True
    return False


def _iso(value: Any) -> str | None:
    if value is None:
        return None
    if hasattr(value, "isoformat"):
        try:
            return value.isoformat()
        except (TypeError, ValueError):
            return None
    return str(value)


class DashboardBotBridge:
    """Serve narrowly scoped bot operations on a loopback-only HTTP listener."""

    def __init__(self, bot: Any):
        self.bot = bot
        self.runner: web.AppRunner | None = None
        self.site: web.TCPSite | None = None
        self.started_at = time.monotonic()
        self._was_ready = False
        self._guild_locks: dict[int, asyncio.Lock] = {}
        self.secret = getattr(config, "DASHBOARD_BRIDGE_SECRET", "") or os.getenv("DASHBOARD_BRIDGE_SECRET", "")
        self.host = getattr(config, "DASHBOARD_BRIDGE_HOST", "127.0.0.1")
        self.port = getattr(config, "DASHBOARD_BRIDGE_PORT", 8091)

    async def start(self) -> None:
        if not self.secret:
            logger.warning("Dashboard bot bridge is disabled: set DASHBOARD_BRIDGE_SECRET.")
            return
        if self.runner:
            return
        app = web.Application(client_max_size=64 * 1024, middlewares=[self._authenticate])
        app.router.add_get("/health", self._health)
        app.router.add_get("/guilds", self._guilds)
        app.router.add_get("/guilds/{guild_id}/overview", self._overview)
        app.router.add_get("/guilds/{guild_id}/commands", self._commands)
        app.router.add_put("/guilds/{guild_id}/commands/{fullname:.*}", self._set_command)
        app.router.add_post("/guilds/{guild_id}/sync", self._sync)
        app.router.add_post("/guilds/{guild_id}/reset", self._reset)
        app.router.add_get("/guilds/{guild_id}/audit", self._audit)
        app.router.add_get("/guilds/{guild_id}/database", self._database)
        app.router.add_get("/logs", self._logs)
        app.router.add_get("/integrations", self._integrations)
        self.runner = web.AppRunner(app, access_log=logger)
        await self.runner.setup()
        self.site = web.TCPSite(self.runner, self.host, self.port)
        try:
            await self.site.start()
        except Exception:
            await self.runner.cleanup()
            self.runner = None
            self.site = None
            raise
        logger.info("Private dashboard bridge listening on %s:%s", self.host, self.port)

    async def stop(self) -> None:
        if self.runner:
            await self.runner.cleanup()
            self.runner = None
            self.site = None

    @web.middleware
    async def _authenticate(self, request: web.Request, handler):
        supplied = request.headers.get("Authorization", "")
        expected = f"Bearer {self.secret}"
        if not self.secret or not hmac.compare_digest(supplied, expected):
            return _error("Unauthorized internal dashboard request.", 401)
        try:
            return await handler(request)
        except web.HTTPException as exc:
            return _error(exc.reason or "Request rejected.", exc.status)
        except Exception:
            logger.exception("Unexpected dashboard bridge error for %s %s", request.method, request.path)
            return _error("The bot could not complete this request.", 500)

    def _guild(self, request: web.Request):
        guild_id = request.match_info.get("guild_id", "")
        if not guild_id.isdigit():
            raise web.HTTPBadRequest(text="Invalid guild identifier.")
        guild = self.bot.get_guild(int(guild_id))
        if guild is None:
            raise web.HTTPNotFound(text="The bot is no longer in this server.")
        return guild

    def _cog(self):
        cog = self.bot.get_cog("DashboardCog")
        if cog is None or getattr(self.bot, "_dashboard_db", None) is None:
            raise web.HTTPServiceUnavailable(text="The command registry is not ready.")
        return cog

    async def _json_body(self, request: web.Request) -> dict[str, Any]:
        if request.content_type != "application/json":
            raise web.HTTPUnsupportedMediaType(text="Expected application/json.")
        try:
            value = await request.json()
        except (json.JSONDecodeError, ValueError):
            raise web.HTTPBadRequest(text="Invalid JSON body.")
        if not isinstance(value, dict):
            raise web.HTTPBadRequest(text="Expected a JSON object.")
        return value

    def _command_rows(self, cfg: dict[str, Any]) -> list[dict[str, Any]]:
        from cogs_test.general_commands.dashboard import COMMAND_REGISTRY

        rows = []
        for fullname, meta in COMMAND_REGISTRY.all_commands():
            command = meta["command"]
            name = getattr(command, "name", fullname)
            default_permissions = getattr(command, "default_permissions", None)
            permissions = str(default_permissions) if default_permissions is not None else None
            description = meta.get("description") or getattr(command, "description", "") or "No description provided."
            rows.append({
                "fullname": fullname,
                "name": name,
                "description": description,
                "section": meta.get("section") or "Other",
                "type": "slash",
                "scope": "guild",
                "aliases": [],
                "required_permissions": permissions,
                "protected": name in PROTECTED_NAMES,
                "enabled": _effective_enabled(fullname, meta, cfg),
            })
        return rows

    async def _health(self, request: web.Request) -> web.Response:
        ready = bool(self.bot.is_ready())
        latency = float(self.bot.latency * 1000) if ready else None
        if ready:
            self._was_ready = True
        status = _connection_status(ready, self._was_ready, latency)
        return web.json_response({
            "status": status,
            "ready": ready,
            "latency_ms": latency,
            "guild_count": len(self.bot.guilds),
            "extension_count": len(self.bot.extensions),
            "extensions": sorted(self.bot.extensions.keys()),
            "uptime_seconds": max(0, int(time.monotonic() - self.started_at)),
            "python_version": sys.version.split()[0],
            "checked_at": int(time.time()),
        })

    async def _guilds(self, request: web.Request) -> web.Response:
        result = []
        for guild in self.bot.guilds:
            icon = getattr(guild, "icon", None)
            result.append({
                "id": str(guild.id),
                "name": guild.name,
                "icon": icon.url if icon else None,
                "member_count": getattr(guild, "member_count", None),
            })
        result.sort(key=lambda item: item["name"].casefold())
        return web.json_response(result)

    async def _overview(self, request: web.Request) -> web.Response:
        guild = self._guild(request)
        cog = self._cog()
        cfg = await cog.db.get_guild_config(guild.id)
        rows = self._command_rows(cfg)
        ready = bool(self.bot.is_ready())
        latency = float(self.bot.latency * 1000) if ready else None
        if ready:
            self._was_ready = True
        status = _connection_status(ready, self._was_ready, latency)
        return web.json_response({
            "guild": {"id": str(guild.id), "name": guild.name},
            "bot": {
                "ready": ready,
                "status": status,
                "latency_ms": latency,
                "guild_count": len(self.bot.guilds),
                "member_count": getattr(guild, "member_count", None),
                "extension_count": len(self.bot.extensions),
                "extensions": sorted(self.bot.extensions.keys()),
            },
            "commands": {
                "total": len(rows),
                "enabled": sum(1 for row in rows if row["enabled"]),
                "disabled": sum(1 for row in rows if not row["enabled"]),
            },
        })

    async def _commands(self, request: web.Request) -> web.Response:
        guild = self._guild(request)
        cog = self._cog()
        cfg = await cog.db.get_guild_config(guild.id)
        return web.json_response({"commands": self._command_rows(cfg)})

    def _guild_lock(self, guild_id: int) -> asyncio.Lock:
        return self._guild_locks.setdefault(guild_id, asyncio.Lock())

    async def _set_command(self, request: web.Request) -> web.Response:
        guild = self._guild(request)
        async with self._guild_lock(guild.id):
            return await self._set_command_locked(request, guild)

    async def _set_command_locked(self, request: web.Request, guild: Any) -> web.Response:
        data = await self._json_body(request)
        if type(data.get("enabled")) is not bool:
            return _error("enabled must be a boolean.", 400)
        actor_id = data.get("actor_id")
        if not _valid_identifier(actor_id):
            return _error("Invalid dashboard actor.", 400)
        fullname = request.match_info.get("fullname", "")
        if not fullname or len(fullname) > 100:
            return _error("Invalid command name.", 400)

        from cogs_test.general_commands.dashboard import COMMAND_REGISTRY, PROTECTED_CMD_NAMES, attempt_sync_for_guild
        meta = COMMAND_REGISTRY.get_meta(fullname)
        if not meta:
            return _error("Command is not registered for dashboard management.", 404)
        if getattr(meta["command"], "name", "") in PROTECTED_CMD_NAMES:
            return _error("This system command is protected.", 403)

        cog = self._cog()
        before = await cog.db.get_guild_config(guild.id)
        old_value = _effective_enabled(fullname, meta, before)
        try:
            await cog.db.set_command(guild.id, fullname, data["enabled"])
            if not await attempt_sync_for_guild(self.bot, guild):
                await cog.db._set_guild_config(guild.id, before)
                await attempt_sync_for_guild(self.bot, guild)
                return _error("Discord did not confirm command synchronization. The previous configuration was restored.", 502)
            await cog.db.log_action(guild.id, int(actor_id), "toggle_command",
                f"{fullname} -> {'enabled' if data['enabled'] else 'disabled'}")
        except Exception:
            logger.exception("Command update failed for guild %s command %s", guild.id, fullname)
            try:
                await cog.db._set_guild_config(guild.id, before)
                await attempt_sync_for_guild(self.bot, guild)
            except Exception:
                logger.exception("Could not restore the previous command configuration for guild %s", guild.id)
            return _error("The command change failed. The previous configuration was restored where possible.", 503)
        logger.info("Dashboard user %s set %s in guild %s to %s (previous=%s)",
            actor_id, fullname, guild.id, data["enabled"], old_value)
        return web.json_response({"fullname": fullname, "enabled": data["enabled"], "synced": True})

    async def _sync(self, request: web.Request) -> web.Response:
        guild = self._guild(request)
        data = await self._json_body(request)
        actor_id = data.get("actor_id")
        if not _valid_identifier(actor_id):
            return _error("Invalid dashboard actor.", 400)
        from cogs_test.general_commands.dashboard import attempt_sync_for_guild
        if not await attempt_sync_for_guild(self.bot, guild):
            return _error("Discord did not confirm command synchronization.", 502)
        cog = self._cog()
        rows = self._command_rows(await cog.db.get_guild_config(guild.id))
        await cog.db.log_action(guild.id, int(actor_id), "sync_commands", "Published dashboard-managed slash commands.")
        return web.json_response({"synced": sum(1 for row in rows if row["enabled"]), "ok": True})

    async def _reset(self, request: web.Request) -> web.Response:
        guild = self._guild(request)
        async with self._guild_lock(guild.id):
            return await self._reset_locked(request, guild)

    async def _reset_locked(self, request: web.Request, guild: Any) -> web.Response:
        data = await self._json_body(request)
        actor_id = data.get("actor_id")
        if not _valid_identifier(actor_id):
            return _error("Invalid dashboard actor.", 400)
        from cogs_test.general_commands.dashboard import attempt_sync_for_guild
        cog = self._cog()
        before = await cog.db.get_guild_config(guild.id)
        try:
            await cog.db.reset_guild(guild.id)
            if not await attempt_sync_for_guild(self.bot, guild):
                await cog.db._set_guild_config(guild.id, before)
                await attempt_sync_for_guild(self.bot, guild)
                return _error("Discord did not confirm synchronization. The previous configuration was restored.", 502)
            await cog.db.log_action(guild.id, int(actor_id), "reset_dashboard", "Reset per-server command settings from the web dashboard.")
        except Exception:
            logger.exception("Dashboard reset failed for guild %s", guild.id)
            try:
                await cog.db._set_guild_config(guild.id, before)
                await attempt_sync_for_guild(self.bot, guild)
            except Exception:
                logger.exception("Could not restore the previous guild configuration for %s", guild.id)
            return _error("Reset failed. The previous configuration was restored where possible.", 503)
        return web.json_response({"ok": True, "reset": True})

    async def _audit(self, request: web.Request) -> web.Response:
        guild = self._guild(request)
        entries = await self._cog().db.last_audit_entries(guild.id, limit=25)
        result = [{"id": row.get("id"), "ts": _iso(row.get("ts")), "actor_id": str(row.get("actor_id", "")),
            "action": row.get("action", "Administrative action"), "details": row.get("details", "")} for row in entries]
        return web.json_response({"entries": result})

    async def _database(self, request: web.Request) -> web.Response:
        guild = self._guild(request)
        cfg = await self._cog().db.get_guild_config(guild.id)
        return web.json_response({"resources": [
            {"name": "Guild command configuration", "purpose": "Persisted per-server command enablement",
             "state": "Available", "detail": f"{len(cfg.get('commands', {}))} command overrides"},
            {"name": "Guild category configuration", "purpose": "Persisted section defaults",
             "state": "Available", "detail": f"{len(cfg.get('sections', {}))} category settings"},
            {"name": "Audit trail", "purpose": "Management change history", "state": "Available",
             "detail": "Audit events are stored in the shared PostgreSQL database"},
        ]})

    async def _logs(self, request: web.Request) -> web.Response:
        filename = request.query.get("file", "bot.log")
        if filename not in LOG_FILES:
            return _error("That log file is not available.", 400)
        path = ROOT / "logs" / filename
        if not path.is_file():
            return web.json_response({"name": filename, "content": "This log file does not exist yet."})
        try:
            content = path.read_text(encoding="utf-8", errors="replace")[-30_000:]
        except OSError:
            return _error("Could not read this log file.", 503)
        return web.json_response({"name": filename, "content": content})

    async def _integrations(self, request: web.Request) -> web.Response:
        return web.json_response({"integrations": [
            {"name": "AniList", "configured": bool(getattr(config, "ANILIST_API_URL", None)), "detail": "Media metadata provider"},
            {"name": "Steam", "configured": bool(getattr(config, "STEAM_API_KEY", None)), "detail": "Game and player metadata"},
            {"name": "GitHub tracker", "configured": bool(getattr(config, "GITHUB_REPO", None) and getattr(config, "GITHUB_BRANCH", None)), "detail": "Commit notifications"},
            {"name": "IGDB", "configured": bool(getattr(config, "IGDB_CLIENT_ID", None) and getattr(config, "IGDB_CLIENT_SECRET", None)), "detail": "Game cover metadata"},
            {"name": "TMDB", "configured": bool(getattr(config, "TMDB_BEARER_TOKEN", None)), "detail": "Film and television metadata"},
        ]})
