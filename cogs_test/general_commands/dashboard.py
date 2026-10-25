"""High-end, guild-aware command dashboard for Lemegeton.

The dashboard stores each guild's settings in PostgreSQL through database.py,
keeps command metadata compatible with the existing @command_meta decorator,
and uses ephemeral, interaction-driven UI rather than public control panels.
"""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Any, Optional

import discord
from discord import app_commands, ui
from helpers.command_error_handler import FeedbackAwareView
from discord.ext import commands

import database

logger = logging.getLogger("dashboard_cog")
logger.setLevel(logging.INFO)

PALETTE = {
    "background": discord.Color.from_rgb(18, 22, 34),
    "panel": discord.Color.from_rgb(31, 39, 58),
    "accent": discord.Color.from_rgb(124, 92, 255),
    "success": discord.Color.from_rgb(46, 204, 113),
    "warning": discord.Color.from_rgb(241, 196, 15),
    "danger": discord.Color.from_rgb(231, 76, 60),
    "muted": discord.Color.from_rgb(130, 145, 170),
}
ENABLED_EMOJI = "🟢"
DISABLED_EMOJI = "⚪"
LOCK_EMOJI = "🔒"
GEAR = "⚙️"
PROTECTED_CMD_NAMES = {"help", "feedback"}
COMMANDS_PER_PAGE = 8
MAX_AUDIT_ENTRIES = 8


# ---------------------------------------------------------------------------
# Command metadata registry
# ---------------------------------------------------------------------------
class CommandRegistry:
    """Central index of slash commands exposed to the dashboard."""

    def __init__(self):
        self._commands: dict[str, dict[str, Any]] = {}

    def register(
        self,
        fullname: str,
        cmd_obj: app_commands.Command,
        section: str,
        display_name: Optional[str] = None,
    ) -> None:
        self._commands[fullname] = {
            "command": cmd_obj,
            "section": section,
            "display_name": display_name or getattr(cmd_obj, "name", fullname),
            "description": getattr(cmd_obj, "description", "") or "No description provided.",
        }

    def get_sections(self) -> list[str]:
        return sorted({meta["section"] for meta in self._commands.values()}, key=str.casefold)

    def get_commands_in_section(self, section: str) -> list[tuple[str, dict[str, Any]]]:
        return sorted(
            ((key, meta) for key, meta in self._commands.items() if meta["section"] == section),
            key=lambda item: item[1]["display_name"].casefold(),
        )

    def all_commands(self) -> list[tuple[str, dict[str, Any]]]:
        return sorted(self._commands.items(), key=lambda item: item[1]["display_name"].casefold())

    def get_meta(self, fullname: str) -> Optional[dict[str, Any]]:
        return self._commands.get(fullname)

    def find_fullname_by_cmd(self, cmd_obj: app_commands.Command) -> Optional[str]:
        return next(
            (fullname for fullname, meta in self._commands.items() if meta["command"] is cmd_obj),
            None,
        )


COMMAND_REGISTRY = CommandRegistry()


def command_meta(section: str, name: Optional[str] = None):
    """Annotate an application command for dashboard discovery."""
    def decorator(func_or_cmd):
        setattr(func_or_cmd, "__dashboard_section__", section)
        setattr(
            func_or_cmd,
            "__dashboard_name__",
            name or getattr(func_or_cmd, "__name__", getattr(func_or_cmd, "name", "")),
        )
        return func_or_cmd
    return decorator


# ---------------------------------------------------------------------------
# PostgreSQL-backed configuration and audit log
# ---------------------------------------------------------------------------
class ConfigDB:
    """Persist per-guild settings via the project's shared PostgreSQL layer."""

    def __init__(self):
        self._lock = asyncio.Lock()
        self._initialized = False

    async def open(self) -> None:
        if self._initialized:
            return
        async with self._lock:
            if self._initialized:
                return
            await database.execute_db_operation(
                "create dashboard guild configs",
                """
                CREATE TABLE IF NOT EXISTS dashboard_guild_configs (
                    guild_id BIGINT PRIMARY KEY,
                    data TEXT NOT NULL,
                    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """,
            )
            # Tables created before updated_at existed don't get it from CREATE TABLE IF NOT EXISTS.
            await database.execute_db_operation(
                "add dashboard guild configs updated_at",
                "ALTER TABLE dashboard_guild_configs "
                "ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP",
            )
            await database.execute_db_operation(
                "create dashboard audit log",
                """
                CREATE TABLE IF NOT EXISTS dashboard_audit_log (
                    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
                    guild_id BIGINT NOT NULL,
                    ts TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    actor_id BIGINT NOT NULL,
                    action TEXT NOT NULL,
                    details TEXT NOT NULL DEFAULT ''
                )
                """,
            )
            await database.execute_db_operation(
                "create dashboard audit lookup index",
                "CREATE INDEX IF NOT EXISTS dashboard_audit_guild_ts_idx ON dashboard_audit_log (guild_id, ts DESC)",
            )
            self._initialized = True

    async def close(self) -> None:
        # Connections are managed by database.py's shared pool.
        return None

    async def get_guild_config(self, guild_id: int) -> dict[str, Any]:
        await self.open()
        rows = await database.execute_db_operation(
            "load dashboard guild config",
            "SELECT data FROM dashboard_guild_configs WHERE guild_id = ?",
            (guild_id,),
            fetch_type="one",
        )
        if rows:
            try:
                data = json.loads(rows[0])
                if isinstance(data, dict):
                    data.setdefault("sections", {})
                    data.setdefault("commands", {})
                    return data
            except (TypeError, ValueError, json.JSONDecodeError):
                logger.exception("Corrupt dashboard config for guild %s; resetting defaults", guild_id)

        default = {"sections": {}, "commands": {}}
        await self._set_guild_config(guild_id, default)
        return default

    async def _set_guild_config(self, guild_id: int, data: dict[str, Any]) -> None:
        await self.open()
        serialized = json.dumps(data, separators=(",", ":"), sort_keys=True)
        await database.execute_db_operation(
            "save dashboard guild config",
            """
            INSERT INTO dashboard_guild_configs (guild_id, data, updated_at)
            VALUES (?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT (guild_id) DO UPDATE
            SET data = EXCLUDED.data, updated_at = CURRENT_TIMESTAMP
            """,
            (guild_id, serialized),
        )

    async def set_command(self, guild_id: int, fullname: str, enabled: bool) -> None:
        async with self._lock:
            cfg = await self.get_guild_config(guild_id)
            cfg.setdefault("commands", {})[fullname] = bool(enabled)
            await self._set_guild_config(guild_id, cfg)

    async def set_section(self, guild_id: int, section: str, enabled: bool) -> None:
        async with self._lock:
            cfg = await self.get_guild_config(guild_id)
            cfg.setdefault("sections", {})[section] = bool(enabled)
            for fullname, meta in COMMAND_REGISTRY.get_commands_in_section(section):
                if meta["command"].name not in PROTECTED_CMD_NAMES:
                    cfg.setdefault("commands", {})[fullname] = bool(enabled)
            await self._set_guild_config(guild_id, cfg)

    async def reset_guild(self, guild_id: int) -> None:
        async with self._lock:
            await self._set_guild_config(guild_id, {"sections": {}, "commands": {}})

    async def log_action(self, guild_id: int, actor_id: int, action: str, details: str = "") -> None:
        await self.open()
        await database.execute_db_operation(
            "write dashboard audit event",
            """
            INSERT INTO dashboard_audit_log (guild_id, actor_id, action, details)
            VALUES (?, ?, ?, ?)
            """,
            (guild_id, actor_id, action, details),
        )

    async def last_audit_entries(self, guild_id: int, limit: int = MAX_AUDIT_ENTRIES) -> list[dict[str, Any]]:
        await self.open()
        rows = await database.execute_db_operation(
            "load dashboard audit events",
            """
            SELECT id, ts, actor_id, action, details
            FROM dashboard_audit_log
            WHERE guild_id = ?
            ORDER BY ts DESC, id DESC
            LIMIT ?
            """,
            (guild_id, max(1, min(int(limit), 25))),
            fetch_type="all",
        ) or []
        return [
            {"id": row[0], "ts": row[1], "actor_id": row[2], "action": row[3], "details": row[4]}
            for row in rows
        ]


def format_commit_message(actor: discord.abc.User, action: str, details: str = "") -> str:
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    return f"Actor: {actor} ({actor.id})\nTime: {timestamp}\nAction: {action}\nDetails: {details or '—'}"


def _is_protected(command: app_commands.Command) -> bool:
    return command.name in PROTECTED_CMD_NAMES


def _is_enabled(fullname: str, meta: dict[str, Any], cfg: dict[str, Any]) -> bool:
    if _is_protected(meta["command"]):
        return True
    section = meta["section"]
    command_overrides = cfg.get("commands", {})
    if fullname in command_overrides:
        return command_overrides[fullname] is True
    if section in cfg.get("sections", {}):
        return cfg["sections"][section] is True
    return False


def _has_dashboard_access(interaction: discord.Interaction, bot: commands.Bot) -> bool:
    if interaction.guild is None:
        return False
    member = interaction.user
    perms = getattr(member, "guild_permissions", None)
    return bool(
        getattr(perms, "administrator", False)
        or getattr(perms, "manage_guild", False)
        or getattr(perms, "manage_roles", False)
        or interaction.user.id == getattr(bot, "owner_id", None)
    )


# ---------------------------------------------------------------------------
# Polished interactive dashboard
# ---------------------------------------------------------------------------
class DashboardView(FeedbackAwareView):
    def __init__(self, bot: commands.Bot, guild: discord.Guild, db: ConfigDB):
        super().__init__(timeout=300)
        self.bot = bot
        self.guild = guild
        self.db = db
        self.sections = COMMAND_REGISTRY.get_sections() or ["General"]
        self.current_section = self.sections[0]
        self.current_page = 0
        self._busy = False
        self._build_controls()

    def _build_controls(self) -> None:
        self.clear_items()

        section_options = [
            discord.SelectOption(
                label=section[:100],
                description=f"{len(COMMAND_REGISTRY.get_commands_in_section(section))} commands",
                value=section,
                emoji=GEAR,
                default=section == self.current_section,
            )
            for section in self.sections[:25]
        ]
        section_select = ui.Select(
            placeholder="Choose a command category",
            min_values=1,
            max_values=1,
            options=section_options,
            row=0,
        )
        section_select.callback = self._on_section_select
        self.add_item(section_select)

        previous = ui.Button(label="Previous", emoji="◀️", style=discord.ButtonStyle.secondary, row=1)
        previous.callback = self._on_previous
        self.add_item(previous)

        next_page = ui.Button(label="Next", emoji="▶️", style=discord.ButtonStyle.secondary, row=1)
        next_page.callback = self._on_next
        self.add_item(next_page)

        section_toggle = ui.Button(label="Toggle category", emoji="⚡", style=discord.ButtonStyle.primary, row=1)
        section_toggle.callback = self._on_toggle_section
        self.add_item(section_toggle)

        audit = ui.Button(label="Audit log", emoji="📋", style=discord.ButtonStyle.secondary, row=1)
        audit.callback = self._on_audit
        self.add_item(audit)

        reset = ui.Button(label="Reset settings", emoji="↺", style=discord.ButtonStyle.danger, row=1)
        reset.callback = self._on_reset
        self.add_item(reset)

    async def render(self, actor: discord.abc.User) -> discord.Embed:
        cfg = await self.db.get_guild_config(self.guild.id)
        commands_in_section = COMMAND_REGISTRY.get_commands_in_section(self.current_section)
        total = len(commands_in_section)
        pages = max(1, (total + COMMANDS_PER_PAGE - 1) // COMMANDS_PER_PAGE)
        self.current_page = max(0, min(self.current_page, pages - 1))
        start = self.current_page * COMMANDS_PER_PAGE
        page_items = commands_in_section[start:start + COMMANDS_PER_PAGE]

        enabled_count = sum(_is_enabled(name, meta, cfg) for name, meta in commands_in_section)
        protected_count = sum(_is_protected(meta["command"]) for _, meta in commands_in_section)
        section_enabled = cfg.get("sections", {}).get(self.current_section, True)

        embed = discord.Embed(
            title="LEMEGETON  /  CONTROL CENTER",
            description=(
                f"### {GEAR} {discord.utils.escape_markdown(self.current_section)}\n"
                f"Configure this category for **{discord.utils.escape_markdown(self.guild.name)}**. "
                "Changes are isolated to this server."
            ),
            color=PALETTE["accent"],
            timestamp=discord.utils.utcnow(),
        )
        embed.set_thumbnail(url=self.bot.user.display_avatar.url if self.bot.user else discord.Embed.Empty)
        embed.add_field(name="CATEGORY STATUS", value="🟢 Enabled" if section_enabled else "🔴 Disabled", inline=True)
        embed.add_field(name="ACTIVE COMMANDS", value=f"**{enabled_count}** / {total}", inline=True)
        embed.add_field(name="LOCKED", value=f"**{protected_count}**", inline=True)

        if page_items:
            lines = []
            for fullname, meta in page_items:
                command = meta["command"]
                protected = _is_protected(command)
                enabled = _is_enabled(fullname, meta, cfg)
                icon = LOCK_EMOJI if protected else (ENABLED_EMOJI if enabled else DISABLED_EMOJI)
                status = "Always on" if protected else ("Enabled" if enabled else "Disabled")
                description = discord.utils.escape_markdown(meta["description"].strip())[:110]
                lines.append(f"{icon} **{discord.utils.escape_markdown(meta['display_name'])}**  ·  `/{fullname}`\n{description or 'No description provided.'}\n*{status}*")
            embed.add_field(
                name=f"COMMANDS  ·  PAGE {self.current_page + 1}/{pages}",
                value="\n\n".join(lines)[:1024],
                inline=False,
            )
        else:
            embed.add_field(name="COMMANDS", value="No dashboard-managed commands were found in this category.", inline=False)

        all_commands = COMMAND_REGISTRY.all_commands()
        all_enabled = sum(_is_enabled(name, meta, cfg) for name, meta in all_commands)
        embed.add_field(
            name="SERVER OVERVIEW",
            value=f"**{all_enabled} / {len(all_commands)}** commands enabled across **{len(self.sections)}** categories",
            inline=False,
        )
        embed.set_footer(text=f"Lemegeton • {self.guild.name} • Requested by {actor}", icon_url=self.bot.user.display_avatar.url if self.bot.user else None)

        # Rebuild after rendering so controls accurately reflect current pagination.
        self._build_controls()
        for item in self.children:
            if isinstance(item, ui.Button):
                if item.label == "Previous":
                    item.disabled = self.current_page <= 0
                elif item.label == "Next":
                    item.disabled = self.current_page >= pages - 1
                elif item.label == "Toggle category":
                    item.label = "Disable category" if section_enabled else "Enable category"
                    item.emoji = "⏸️" if section_enabled else "▶️"
        # Add compact command toggles after fixed controls.
        for fullname, meta in page_items:
            command = meta["command"]
            protected = _is_protected(command)
            enabled = _is_enabled(fullname, meta, cfg)
            button = ui.Button(
                label=(meta["display_name"][:68] or command.name),
                emoji=LOCK_EMOJI if protected else (ENABLED_EMOJI if enabled else DISABLED_EMOJI),
                style=discord.ButtonStyle.success if enabled else discord.ButtonStyle.secondary,
                disabled=protected,
                row=2 + (len([child for child in self.children if isinstance(child, ui.Button) and child.row == 2]) // 4),
            )
            button.callback = self._make_toggle_callback(fullname)
            self.add_item(button)
        return embed

    def _make_toggle_callback(self, fullname: str):
        async def callback(interaction: discord.Interaction):
            if not await self._authorize_component(interaction):
                return
            if self._busy:
                await interaction.response.send_message("A dashboard update is already in progress. Try again in a moment.", ephemeral=True)
                return
            self._busy = True
            try:
                meta = COMMAND_REGISTRY.get_meta(fullname)
                if meta is None or _is_protected(meta["command"]):
                    await interaction.response.send_message("This command is protected and cannot be disabled.", ephemeral=True)
                    return
                cfg = await self.db.get_guild_config(self.guild.id)
                new_value = not _is_enabled(fullname, meta, cfg)
                await self.db.set_command(self.guild.id, fullname, new_value)
                await self.db.log_action(
                    self.guild.id,
                    interaction.user.id,
                    "command_toggle",
                    format_commit_message(interaction.user, f"{fullname} → {'enabled' if new_value else 'disabled'}"),
                )
                await attempt_sync_for_guild(self.bot, self.guild)
                embed = await self.render(interaction.user)
                await interaction.response.edit_message(embed=embed, view=self)
            except Exception:
                logger.exception("Failed toggling dashboard command %s for guild %s", fullname, self.guild.id)
                if not interaction.response.is_done():
                    await interaction.response.send_message("Couldn't update that command. Check the bot logs and try again.", ephemeral=True)
            finally:
                self._busy = False
        return callback

    async def _authorize_component(self, interaction: discord.Interaction) -> bool:
        if interaction.guild_id != self.guild.id or not _has_dashboard_access(interaction, self.bot):
            try:
                await interaction.response.send_message("You don't have permission to control this dashboard.", ephemeral=True)
            except discord.HTTPException:
                pass
            return False
        return True

    async def _refresh(self, interaction: discord.Interaction) -> None:
        embed = await self.render(interaction.user)
        await interaction.response.edit_message(embed=embed, view=self)

    async def _on_section_select(self, interaction: discord.Interaction):
        if not await self._authorize_component(interaction):
            return
        selected = interaction.data.get("values", []) if interaction.data else []
        if selected and selected[0] in self.sections:
            self.current_section = selected[0]
            self.current_page = 0
        await self._refresh(interaction)

    async def _on_previous(self, interaction: discord.Interaction):
        if not await self._authorize_component(interaction):
            return
        self.current_page = max(0, self.current_page - 1)
        await self._refresh(interaction)

    async def _on_next(self, interaction: discord.Interaction):
        if not await self._authorize_component(interaction):
            return
        total = len(COMMAND_REGISTRY.get_commands_in_section(self.current_section))
        pages = max(1, (total + COMMANDS_PER_PAGE - 1) // COMMANDS_PER_PAGE)
        self.current_page = min(pages - 1, self.current_page + 1)
        await self._refresh(interaction)

    async def _on_toggle_section(self, interaction: discord.Interaction):
        if not await self._authorize_component(interaction):
            return
        cfg = await self.db.get_guild_config(self.guild.id)
        currently_enabled = cfg.get("sections", {}).get(self.current_section, True)
        new_value = not currently_enabled
        await self.db.set_section(self.guild.id, self.current_section, new_value)
        await self.db.log_action(
            self.guild.id,
            interaction.user.id,
            "section_toggle",
            format_commit_message(interaction.user, f"{self.current_section} → {'enabled' if new_value else 'disabled'}"),
        )
        await attempt_sync_for_guild(self.bot, self.guild)
        await self._refresh(interaction)

    async def _on_audit(self, interaction: discord.Interaction):
        if not await self._authorize_component(interaction):
            return
        try:
            entries = await self.db.last_audit_entries(self.guild.id)
            embed = discord.Embed(
                title="DASHBOARD  /  AUDIT TRAIL",
                description="Recent configuration changes for this server.",
                color=PALETTE["panel"],
            )
            if not entries:
                embed.description = "No dashboard changes have been recorded yet."
            else:
                for entry in entries:
                    timestamp = entry["ts"]
                    if hasattr(timestamp, "strftime"):
                        timestamp = timestamp.strftime("%Y-%m-%d %H:%M UTC")
                    embed.add_field(
                        name=f"#{entry['id']} · {entry['action'][:200]}",
                        value=f"Actor: <@{entry['actor_id']}>\n{str(timestamp)}\n{entry['details'][:400] or '—'}",
                        inline=False,
                    )
            embed.set_footer(text=f"{self.guild.name} • Private administrator view")
            await interaction.response.send_message(embed=embed, ephemeral=True)
        except Exception:
            logger.exception("Failed loading dashboard audit log")
            await interaction.response.send_message("The audit log couldn't be loaded.", ephemeral=True)

    async def _on_reset(self, interaction: discord.Interaction):
        if not await self._authorize_component(interaction):
            return
        await interaction.response.send_message(
            "Reset all command settings for this server? Protected commands remain enabled.",
            view=ResetConfirmView(self),
            ephemeral=True,
        )


class ResetConfirmView(FeedbackAwareView):
    def __init__(self, dashboard: DashboardView):
        super().__init__(timeout=45)
        self.dashboard = dashboard

    @ui.button(label="Confirm reset", emoji="↺", style=discord.ButtonStyle.danger)
    async def confirm(self, interaction: discord.Interaction, button: ui.Button):
        dashboard = self.dashboard
        if not await dashboard._authorize_component(interaction):
            return
        try:
            await dashboard.db.reset_guild(dashboard.guild.id)
            await dashboard.db.log_action(
                dashboard.guild.id,
                interaction.user.id,
                "reset_guild",
                format_commit_message(interaction.user, "Reset command configuration"),
            )
            await attempt_sync_for_guild(dashboard.bot, dashboard.guild)
            embed = await dashboard.render(interaction.user)
            await interaction.response.edit_message(content="Settings reset successfully.", embed=embed, view=dashboard)
        except Exception:
            logger.exception("Failed resetting dashboard config for guild %s", dashboard.guild.id)
            await interaction.response.send_message("Reset failed. Check the bot logs and try again.", ephemeral=True)

    @ui.button(label="Cancel", emoji="✕", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: ui.Button):
        if not await self.dashboard._authorize_component(interaction):
            return
        await interaction.response.edit_message(content="Reset cancelled.", view=None)


# ---------------------------------------------------------------------------
# Command synchronization
# ---------------------------------------------------------------------------
async def attempt_sync_for_guild(bot: commands.Bot, guild: discord.Guild):
    """Sync dashboard-managed commands without deleting unrelated guild commands."""
    db: ConfigDB | None = getattr(bot, "_dashboard_db", None)
    if db is None:
        return False
    try:
        cfg = await db.get_guild_config(guild.id)
        managed_names = {meta["command"].name for _, meta in COMMAND_REGISTRY.all_commands()}
        current_guild_commands = bot.tree.get_commands(guild=guild)
        preserved_commands = [cmd for cmd in current_guild_commands if cmd.name not in managed_names]
        enabled_commands = [
            meta["command"]
            for fullname, meta in COMMAND_REGISTRY.all_commands()
            if _is_enabled(fullname, meta, cfg)
        ]

        bot.tree.clear_commands(guild=guild)
        for command in preserved_commands:
            bot.tree.add_command(command, guild=guild)
        for command in enabled_commands:
            try:
                bot.tree.add_command(command, guild=guild)
            except (app_commands.CommandAlreadyRegistered, ValueError):
                logger.warning("Skipping already registered command %s for guild %s", command.name, guild.id)
        await bot.tree.sync(guild=guild)
        logger.info("Synced %s dashboard-managed commands for guild %s", len(enabled_commands), guild.id)
        return True
    except Exception:
        logger.exception("Dashboard command sync failed for guild %s", guild.id)
        return False


# ---------------------------------------------------------------------------
# Cog
# ---------------------------------------------------------------------------
class DashboardCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.db = ConfigDB()
        self._ready = False
        setattr(self.bot, "_dashboard_db", self.db)

    async def _startup_tasks(self):
        try:
            await self.db.open()
            COMMAND_REGISTRY._commands.clear()
            # walk_commands recurses into nested groups (e.g. /group subgroup command).
            for command in list(self.bot.tree.walk_commands()):
                self._register_if_annotated(command)
                fullname = getattr(command, "qualified_name", getattr(command, "name", ""))
                meta = COMMAND_REGISTRY.get_meta(fullname)
                checks = getattr(command, "checks", None)
                add_check = getattr(command, "add_check", None)
                if meta and checks is not None and callable(add_check) and self._dashboard_execution_guard not in checks:
                    add_check(self._dashboard_execution_guard)
            logger.info(
                "Dashboard registry initialized: %s commands across %s categories",
                len(COMMAND_REGISTRY.all_commands()),
                len(COMMAND_REGISTRY.get_sections()),
            )
        except Exception:
            logger.exception("Dashboard startup initialization failed")
        finally:
            self._ready = True

    @staticmethod
    def _register_if_annotated(command: app_commands.Command | app_commands.Group) -> None:
        callback = getattr(command, "callback", None)
        if callback is None:
            return
        section = getattr(callback, "__dashboard_section__", None)
        if not section:
            return
        name = getattr(callback, "__dashboard_name__", None) or command.name
        fullname = getattr(command, "qualified_name", command.name)
        COMMAND_REGISTRY.register(fullname, command, section, name)

    async def _dashboard_execution_guard(self, interaction: discord.Interaction) -> bool:
        """Enforce persisted guild command state before executing managed slash commands.

        Discord command visibility/synchronization is not a security boundary: a global
        command can still be visible after a guild override. This check blocks execution
        through the actual application-command dispatch path.
        """
        if interaction.guild is None:
            return True
        command = getattr(interaction, "command", None)
        fullname = COMMAND_REGISTRY.find_fullname_by_cmd(command) if command is not None else None
        meta = COMMAND_REGISTRY.get_meta(fullname) if fullname else None
        if not meta or _is_protected(meta["command"]):
            return True
        try:
            cfg = await self.db.get_guild_config(interaction.guild.id)
            return _is_enabled(fullname, meta, cfg)
        except Exception:
            logger.exception(
                "Could not verify dashboard command access for guild %s command %s",
                interaction.guild.id, fullname,
            )
            # Fail closed: a database failure must not bypass a saved disablement.
            return False

    @app_commands.command(name="dashboard", description="Open Lemegeton's server command control center")
    async def dashboard(self, interaction: discord.Interaction):
        if interaction.guild is None:
            await interaction.response.send_message("The dashboard is available inside a server only.", ephemeral=True)
            return
        if not _has_dashboard_access(interaction, self.bot):
            await interaction.response.send_message(
                "You need **Manage Server**, **Manage Roles**, or **Administrator** permission to open this dashboard.",
                ephemeral=True,
            )
            return
        try:
            await self.db.open()
            view = DashboardView(self.bot, interaction.guild, self.db)
            embed = await view.render(interaction.user)
            await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
        except Exception:
            logger.exception("Failed to open dashboard for guild %s", interaction.guild.id)
            if not interaction.response.is_done():
                await interaction.response.send_message("The dashboard couldn't load. Please try again shortly.", ephemeral=True)

    @app_commands.command(name="dashboard-section-toggle", description="Admin: enable or disable a dashboard category")
    @app_commands.describe(section="Exact dashboard category name", enabled="Whether this category should be enabled")
    async def section_toggle(self, interaction: discord.Interaction, section: str, enabled: bool):
        if interaction.guild is None:
            await interaction.response.send_message("This command is only available in a server.", ephemeral=True)
            return
        if not _has_dashboard_access(interaction, self.bot):
            await interaction.response.send_message("You don't have permission to change dashboard settings.", ephemeral=True)
            return
        if section not in COMMAND_REGISTRY.get_sections():
            await interaction.response.send_message(
                f"Unknown category. Available categories: {', '.join(COMMAND_REGISTRY.get_sections()) or 'none'}",
                ephemeral=True,
            )
            return
        try:
            await self.db.set_section(interaction.guild.id, section, enabled)
            await self.db.log_action(
                interaction.guild.id,
                interaction.user.id,
                "section_toggle",
                format_commit_message(interaction.user, f"{section} → {'enabled' if enabled else 'disabled'}"),
            )
            await attempt_sync_for_guild(self.bot, interaction.guild)
            await interaction.response.send_message(
                f"{'🟢' if enabled else '⚪'} **{section}** is now {'enabled' if enabled else 'disabled'}.",
                ephemeral=True,
            )
        except Exception:
            logger.exception("Failed setting dashboard section for guild %s", interaction.guild.id)
            await interaction.response.send_message("Couldn't update that category. Check the bot logs.", ephemeral=True)

    @commands.Cog.listener()
    async def on_guild_join(self, guild: discord.Guild):
        try:
            await self.db.get_guild_config(guild.id)
            await attempt_sync_for_guild(self.bot, guild)
        except Exception:
            logger.exception("Failed initializing dashboard for new guild %s", guild.id)

    @commands.Cog.listener()
    async def on_ready(self):
        if self._ready:
            return
        await self._startup_tasks()
        for guild in self.bot.guilds:
            try:
                await attempt_sync_for_guild(self.bot, guild)
            except Exception:
                logger.exception("Dashboard initial sync failed for guild %s", guild.id)

    async def cog_unload(self):
        # The database pool is shared application state and is closed by bot.py.
        self._ready = False


async def setup(bot: commands.Bot):
    await bot.add_cog(DashboardCog(bot))
