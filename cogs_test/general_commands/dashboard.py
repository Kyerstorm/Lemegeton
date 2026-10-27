"""High-end, guild-aware command dashboard for Lemegeton.

The dashboard stores each guild's settings in PostgreSQL through database.py,
keeps command metadata compatible with the existing @command_meta decorator,
and uses ephemeral, interaction-driven UI rather than public control panels.
"""
from __future__ import annotations

import asyncio
import json
import logging
from copy import copy as shallow_copy
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
PROTECTED_CMD_NAMES = {"help", "feedback", "dashboard"}
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
        qualified_name = getattr(cmd_obj, "qualified_name", None)
        if qualified_name in self._commands:
            return qualified_name
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
        # Initialize before taking the mutation lock: open() uses that same lock.
        await self.open()
        async with self._lock:
            cfg = await self.get_guild_config(guild_id)
            cfg.setdefault("commands", {})[fullname] = bool(enabled)
            await self._set_guild_config(guild_id, cfg)

    async def set_section(self, guild_id: int, section: str, enabled: bool) -> None:
        await self.open()
        async with self._lock:
            cfg = await self.get_guild_config(guild_id)
            cfg.setdefault("sections", {})[section] = bool(enabled)
            for fullname, meta in COMMAND_REGISTRY.get_commands_in_section(section):
                if meta["command"].name not in PROTECTED_CMD_NAMES:
                    cfg.setdefault("commands", {})[fullname] = bool(enabled)
            await self._set_guild_config(guild_id, cfg)

    async def reset_guild(self, guild_id: int) -> None:
        await self.open()
        async with self._lock:
            await self._set_guild_config(guild_id, {"sections": {}, "commands": {}})

    async def replace_guild_config(self, guild_id: int, data: dict[str, Any]) -> None:
        """Atomically replace one guild's saved settings, used for failed-sync rollback."""
        await self.open()
        async with self._lock:
            await self._set_guild_config(guild_id, {
                "sections": dict(data.get("sections") or {}),
                "commands": dict(data.get("commands") or {}),
            })

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


def _infer_command_section(command: app_commands.Command) -> str:
    """Give every registered slash-command leaf a useful dashboard category."""
    module = str(getattr(getattr(command, "callback", None), "__module__", ""))
    leaf = module.rsplit(".", 1)[-1]
    if module.startswith("cogs.account."):
        return "Account"
    if module.startswith("cogs.admin."):
        return "Administration"
    if module.startswith("cogs.customization."):
        return "Customization"
    if module.startswith("cogs.gaming.") or leaf == "game":
        return "Gaming"
    if module.startswith("cogs.media."):
        return "Media"
    if module.startswith("cogs.server_management.") or leaf in {"server_check", "server_taste"}:
        return "Server Management"
    if module.startswith("cogs.social."):
        return "Social"
    if module.startswith("cogs.utilities.") or leaf in {"dashboard", "gpt"}:
        return "Utilities"
    if module.startswith("cogs_test.general_commands."):
        if leaf in {"community_archives", "media_night", "reading_club", "release_calendar"}:
            return "Community"
        if leaf in {"server_check", "server_taste"}:
            return "Server Management"
        return "Media Discovery"
    return "Other"


def _root_app_command(command: app_commands.Command | app_commands.Group):
    while getattr(command, "parent", None) is not None:
        command = command.parent
    return command


def _copy_app_command(
    command: app_commands.Command | app_commands.Group | app_commands.ContextMenu,
    parent: app_commands.Group | None = None,
):
    """Copy a command root without sharing mutable slash-group children."""
    cloned = shallow_copy(command)
    if isinstance(command, app_commands.Group):
        cloned.parent = parent
        cloned._children = {}
        for child in command.commands:
            child_copy = _copy_app_command(child, cloned)
            cloned._children[child_copy.name] = child_copy
    elif isinstance(command, app_commands.Command):
        cloned.parent = parent
        cloned._params = command._params.copy()
    # ContextMenu has neither a parent, child map, nor slash-command params.
    # A shallow copy preserves its callback and configuration without altering its shape.
    return cloned


def _filter_group_for_guild(group: app_commands.Group, cfg: dict[str, Any]) -> app_commands.Group | None:
    """Copy a command group and remove disabled managed leaves without flattening it."""
    cloned = _copy_app_command(group)

    def prune(parent: app_commands.Group) -> None:
        for child in list(parent.commands):
            if isinstance(child, app_commands.Group):
                prune(child)
                if not child.commands:
                    parent.remove_command(child.name)
                continue
            fullname = getattr(child, "qualified_name", child.name)
            meta = COMMAND_REGISTRY.get_meta(fullname)
            if meta is not None and not _is_enabled(fullname, meta, cfg):
                parent.remove_command(child.name)

    prune(cloned)
    return cloned if cloned.commands else None


def _is_enabled(fullname: str, meta: dict[str, Any], cfg: dict[str, Any]) -> bool:
    if _is_protected(meta["command"]):
        return True
    section = meta["section"]
    command_overrides = cfg.get("commands", {})
    if fullname in command_overrides:
        return command_overrides[fullname] is True
    if section in cfg.get("sections", {}):
        return cfg["sections"][section] is True
    # No saved override means the command keeps its existing normal availability.
    return True


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
            title="🎛️  LEMEGETON / SERVER CONTROL CENTER",
            description=(
                f"### {GEAR} {discord.utils.escape_markdown(self.current_section)}\n"
                f"Configure this category for **{discord.utils.escape_markdown(self.guild.name)}**. "
                "Changes are isolated to this server."
            ),
            color=PALETTE["accent"],
            timestamp=discord.utils.utcnow(),
        )
        embed.set_thumbnail(url=self.bot.user.display_avatar.url if self.bot.user else discord.Embed.Empty)
        embed.add_field(name="⚙️ CATEGORY STATUS", value="🟢 Enabled" if section_enabled else "🔴 Disabled", inline=True)
        embed.add_field(name="🟢 ACTIVE COMMANDS", value=f"**{enabled_count}** / {total}", inline=True)
        embed.add_field(name="🔒 LOCKED", value=f"**{protected_count}**", inline=True)

        if page_items:
            embed.add_field(
                name=f"📚 COMMANDS · PAGE {self.current_page + 1}/{pages}",
                value=f"Showing {len(page_items)} of {total} registered commands in this category.",
                inline=False,
            )
            for fullname, meta in page_items:
                command = meta["command"]
                protected = _is_protected(command)
                enabled = _is_enabled(fullname, meta, cfg)
                icon = LOCK_EMOJI if protected else (ENABLED_EMOJI if enabled else DISABLED_EMOJI)
                status = "Always on" if protected else ("Enabled" if enabled else "Disabled")
                display_name = discord.utils.escape_markdown(str(meta["display_name"]))[:150]
                description = discord.utils.escape_markdown(str(meta["description"] or "").strip())[:400]
                embed.add_field(
                    name=f"{icon} {display_name} · /{fullname}"[:256],
                    value=f"{description or 'No description provided.'}\n\n**Status:** {status}",
                    inline=False,
                )
        else:
            embed.add_field(
                name="📭 COMMANDS",
                value="No dashboard-managed commands were found in this category.",
                inline=False,
            )

        all_commands = COMMAND_REGISTRY.all_commands()
        all_enabled = sum(_is_enabled(name, meta, cfg) for name, meta in all_commands)
        embed.add_field(
            name="🌐 SERVER OVERVIEW",
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
            before: dict[str, Any] | None = None
            try:
                await interaction.response.defer()
                before = await self.db.get_guild_config(self.guild.id)
                meta = COMMAND_REGISTRY.get_meta(fullname)
                if meta is None or _is_protected(meta["command"]):
                    await interaction.edit_original_response(content="This command is protected or is no longer registered.")
                    return
                new_value = not _is_enabled(fullname, meta, before)
                await self.db.set_command(self.guild.id, fullname, new_value)
                if not await attempt_sync_for_guild(self.bot, self.guild):
                    await _restore_dashboard_config(self.db, self.bot, self.guild, before, f"toggle command {fullname}")
                    embed = await self.render(interaction.user)
                    await interaction.edit_original_response(
                        content="Discord did not confirm the command change. The previous settings were restored where possible.",
                        embed=embed,
                        view=self,
                    )
                    return
                await self.db.log_action(
                    self.guild.id,
                    interaction.user.id,
                    "command_toggle",
                    format_commit_message(interaction.user, f"{fullname} → {'enabled' if new_value else 'disabled'}"),
                )
                embed = await self.render(interaction.user)
                await interaction.edit_original_response(
                    content=None,
                    embed=embed,
                    view=self,
                )
            except Exception:
                logger.exception("Failed toggling dashboard command %s for guild %s", fullname, self.guild.id)
                if before is not None:
                    await _restore_dashboard_config(self.db, self.bot, self.guild, before, f"failed toggle {fullname}")
                try:
                    embed = await self.render(interaction.user)
                    await interaction.edit_original_response(
                        content="Couldn't apply that command change. The previous settings were restored where possible; check the bot logs if the issue continues.",
                        embed=embed,
                        view=self,
                    )
                except Exception:
                    logger.exception("Could not refresh dashboard message after failed toggle")
                    try:
                        await interaction.followup.send("The command change failed. Check the bot logs and try again.", ephemeral=True)
                    except discord.HTTPException:
                        pass
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
        await interaction.response.defer()
        embed = await self.render(interaction.user)
        await interaction.edit_original_response(embed=embed, view=self)

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
        if self._busy:
            await interaction.response.send_message("A dashboard update is already in progress. Try again in a moment.", ephemeral=True)
            return
        self._busy = True
        before: dict[str, Any] | None = None
        try:
            await interaction.response.defer()
            before = await self.db.get_guild_config(self.guild.id)
            currently_enabled = before.get("sections", {}).get(self.current_section, True)
            new_value = not currently_enabled
            await self.db.set_section(self.guild.id, self.current_section, new_value)
            if not await attempt_sync_for_guild(self.bot, self.guild):
                await _restore_dashboard_config(self.db, self.bot, self.guild, before, f"toggle section {self.current_section}")
                embed = await self.render(interaction.user)
                await interaction.edit_original_response(
                    content="Discord did not confirm this category change. The previous settings were restored where possible.",
                    embed=embed,
                    view=self,
                )
                return
            await self.db.log_action(
                self.guild.id,
                interaction.user.id,
                "section_toggle",
                format_commit_message(interaction.user, f"{self.current_section} → {'enabled' if new_value else 'disabled'}"),
            )
            embed = await self.render(interaction.user)
            await interaction.edit_original_response(content=None, embed=embed, view=self)
        except Exception:
            logger.exception("Failed changing dashboard section %s for guild %s", self.current_section, self.guild.id)
            if before is not None:
                await _restore_dashboard_config(self.db, self.bot, self.guild, before, f"failed section toggle {self.current_section}")
            try:
                embed = await self.render(interaction.user)
                await interaction.edit_original_response(
                    content="Couldn't apply the category change. The previous settings were restored where possible.",
                    embed=embed,
                    view=self,
                )
            except Exception:
                logger.exception("Could not refresh dashboard message after failed section toggle")
                try:
                    await interaction.followup.send("The category change failed. Check the bot logs and try again.", ephemeral=True)
                except discord.HTTPException:
                    pass
        finally:
            self._busy = False

    async def _on_audit(self, interaction: discord.Interaction):
        if not await self._authorize_component(interaction):
            return
        try:
            await interaction.response.defer(ephemeral=True, thinking=True)
            entries = await self.db.last_audit_entries(self.guild.id)
            embed = discord.Embed(
                title="🧾  DASHBOARD / AUDIT TRAIL",
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
                        name=f"#{entry['id']} · {str(entry['action'])[:180]}",
                        value=f"Actor: <@{entry['actor_id']}>\n{str(timestamp)}\n{str(entry['details'])[:350] or '—'}",
                        inline=False,
                    )
            embed.set_footer(text=f"🔒 {self.guild.name} • Private administrator view")
            await interaction.followup.send(embed=embed, ephemeral=True)
        except Exception:
            logger.exception("Failed loading dashboard audit log")
            if interaction.response.is_done():
                await interaction.followup.send("The audit log couldn't be loaded. Please retry.", ephemeral=True)
            else:
                await interaction.response.send_message("The audit log couldn't be loaded. Please retry.", ephemeral=True)

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
        before: dict[str, Any] | None = None
        try:
            await interaction.response.defer()
            before = await dashboard.db.get_guild_config(dashboard.guild.id)
            await dashboard.db.reset_guild(dashboard.guild.id)
            if not await attempt_sync_for_guild(dashboard.bot, dashboard.guild):
                await _restore_dashboard_config(
                    dashboard.db, dashboard.bot, dashboard.guild, before, "confirm reset"
                )
                embed = await dashboard.render(interaction.user)
                await interaction.edit_original_response(
                    content="Discord did not confirm the reset. Previous settings were restored where possible.",
                    embed=embed,
                    view=dashboard,
                )
                return
            await dashboard.db.log_action(
                dashboard.guild.id,
                interaction.user.id,
                "reset_guild",
                format_commit_message(interaction.user, "Reset command configuration"),
            )
            embed = await dashboard.render(interaction.user)
            await interaction.edit_original_response(
                content="✅ Server command settings reset and synchronized.",
                embed=embed,
                view=dashboard,
            )
        except Exception:
            logger.exception("Failed resetting dashboard config for guild %s", dashboard.guild.id)
            if before is not None:
                await _restore_dashboard_config(
                    dashboard.db, dashboard.bot, dashboard.guild, before, "failed reset"
                )
            try:
                embed = await dashboard.render(interaction.user)
                await interaction.edit_original_response(
                    content="Reset failed. Previous settings were restored where possible; check the bot logs if the issue continues.",
                    embed=embed,
                    view=dashboard,
                )
            except Exception:
                logger.exception("Could not refresh dashboard message after failed reset")
                try:
                    await interaction.followup.send("Reset failed. Please retry after checking the bot logs.", ephemeral=True)
                except discord.HTTPException:
                    pass

    @ui.button(label="Cancel", emoji="✕", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: ui.Button):
        if not await self.dashboard._authorize_component(interaction):
            return
        await interaction.response.edit_message(content="Reset cancelled.", view=None)


# ---------------------------------------------------------------------------
# Command synchronization
# ---------------------------------------------------------------------------
_GUILD_SYNC_LOCKS: dict[int, asyncio.Lock] = {}


async def attempt_sync_for_guild(bot: commands.Bot, guild: discord.Guild):
    """Serialize per-guild command publications and retain grouped command structure."""
    lock = _GUILD_SYNC_LOCKS.setdefault(guild.id, asyncio.Lock())
    async with lock:
        return await _sync_guild_commands(bot, guild)


async def _sync_guild_commands(bot: commands.Bot, guild: discord.Guild) -> bool:
    db: ConfigDB | None = getattr(bot, "_dashboard_db", None)
    if db is None:
        return False
    previous_commands = None
    try:
        cfg = await db.get_guild_config(guild.id)
        previous_commands = list(bot.tree.get_commands(guild=guild))
        roots: dict[str, app_commands.Command | app_commands.Group] = {}
        for _, meta in COMMAND_REGISTRY.all_commands():
            root = _root_app_command(meta["command"])
            roots[root.name] = root

        global_roots = {command.name: command for command in bot.tree.get_commands()}
        current_roots = {command.name: command for command in previous_commands}
        managed_roots = {
            name: global_roots.get(name) or current_roots.get(name) or root
            for name, root in roots.items()
        }
        desired_commands = [
            _copy_app_command(command)
            for command in previous_commands
            if command.name not in managed_roots
        ]
        for root in managed_roots.values():
            if isinstance(root, app_commands.Group):
                filtered = _filter_group_for_guild(root, cfg)
                if filtered is not None:
                    desired_commands.append(filtered)
                continue
            fullname = getattr(root, "qualified_name", root.name)
            meta = COMMAND_REGISTRY.get_meta(fullname)
            if meta is None or _is_enabled(fullname, meta, cfg):
                desired_commands.append(_copy_app_command(root))

        bot.tree.clear_commands(guild=guild)
        for command in desired_commands:
            bot.tree.add_command(command, guild=guild)
        await bot.tree.sync(guild=guild)
        logger.info("Synced %s dashboard-managed command roots for guild %s", len(managed_roots), guild.id)
        return True
    except Exception:
        logger.exception("Dashboard command sync failed for guild %s", guild.id)
        if previous_commands is not None:
            try:
                bot.tree.clear_commands(guild=guild)
                for command in previous_commands:
                    bot.tree.add_command(_copy_app_command(command), guild=guild)
                await bot.tree.sync(guild=guild)
            except Exception:
                logger.exception("Could not restore the previous command tree for guild %s", guild.id)
        return False


async def _restore_dashboard_config(
    db: ConfigDB,
    bot: commands.Bot,
    guild: discord.Guild,
    snapshot: dict[str, Any],
    operation: str,
) -> None:
    """Restore the pre-change guild settings and try to republish them after a failed sync."""
    try:
        await db.replace_guild_config(guild.id, snapshot)
        if not await attempt_sync_for_guild(bot, guild):
            logger.error(
                "Rollback settings were saved but Discord did not confirm command restoration "
                "for guild %s after %s",
                guild.id,
                operation,
            )
    except Exception:
        logger.exception(
            "Could not restore dashboard settings for guild %s after %s",
            guild.id,
            operation,
        )



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
        """Initialize persistence and the live command registry; leave retry enabled on failure."""
        try:
            await self.db.open()
            self._refresh_command_registry()
            self._ready = True
        except Exception:
            self._ready = False
            logger.exception("Dashboard startup initialization failed; the next ready event will retry")

    @staticmethod
    def _register_if_annotated(command: app_commands.Command) -> None:
        callback = getattr(command, "callback", None)
        if callback is None:
            return
        fullname = getattr(command, "qualified_name", command.name)
        section = getattr(callback, "__dashboard_section__", None) or _infer_command_section(command)
        name = getattr(callback, "__dashboard_name__", None) or fullname.replace("-", " ").replace("_", " ").title()
        COMMAND_REGISTRY.register(fullname, command, section, name)

    def _refresh_command_registry(self) -> None:
        """Index every eligible slash-command leaf and install its execution guard."""
        COMMAND_REGISTRY._commands.clear()
        for command in list(self.bot.tree.walk_commands()):
            if isinstance(command, app_commands.Group):
                continue
            if not isinstance(command, app_commands.Command):
                continue
            self._register_if_annotated(command)
            fullname = getattr(command, "qualified_name", getattr(command, "name", ""))
            meta = COMMAND_REGISTRY.get_meta(fullname)
            checks = getattr(command, "checks", None)
            add_check = getattr(command, "add_check", None)
            if meta and checks is not None and callable(add_check) and self._dashboard_execution_guard not in checks:
                add_check(self._dashboard_execution_guard)
        logger.info(
            "Dashboard registry refreshed: %s commands across %s categories",
            len(COMMAND_REGISTRY.all_commands()),
            len(COMMAND_REGISTRY.get_sections()),
        )

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
            if fullname not in cfg.get("commands", {}) and meta["section"] not in cfg.get("sections", {}):
                return True
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
            await interaction.response.defer(ephemeral=True, thinking=True)
            await self.db.open()
            self._refresh_command_registry()
            view = DashboardView(self.bot, interaction.guild, self.db)
            embed = await view.render(interaction.user)
            await interaction.followup.send(embed=embed, view=view, ephemeral=True)
        except Exception:
            logger.exception("Failed to open dashboard for guild %s", interaction.guild.id)
            if interaction.response.is_done():
                await interaction.followup.send(
                    "The dashboard couldn't load. Please retry shortly; the failure was logged.",
                    ephemeral=True,
                )
            else:
                await interaction.response.send_message(
                    "The dashboard couldn't load. Please retry shortly; the failure was logged.",
                    ephemeral=True,
                )

    @app_commands.command(name="dashboard-section-toggle", description="Admin: enable or disable a dashboard category")
    @app_commands.describe(section="Exact dashboard category name", enabled="Whether this category should be enabled")
    async def section_toggle(self, interaction: discord.Interaction, section: str, enabled: bool):
        if interaction.guild is None:
            await interaction.response.send_message("This command is only available in a server.", ephemeral=True)
            return
        if not _has_dashboard_access(interaction, self.bot):
            await interaction.response.send_message("You don't have permission to change dashboard settings.", ephemeral=True)
            return
        before: dict[str, Any] | None = None
        try:
            await interaction.response.defer(ephemeral=True, thinking=True)
            await self.db.open()
            self._refresh_command_registry()
            sections = COMMAND_REGISTRY.get_sections()
            if section not in sections:
                await interaction.followup.send(
                    f"Unknown category. Available categories: {', '.join(sections) or 'none'}",
                    ephemeral=True,
                )
                return
            before = await self.db.get_guild_config(interaction.guild.id)
            await self.db.set_section(interaction.guild.id, section, enabled)
            if not await attempt_sync_for_guild(self.bot, interaction.guild):
                await _restore_dashboard_config(self.db, self.bot, interaction.guild, before, f"section command {section}")
                await interaction.followup.send(
                    "Discord did not confirm that category change. Previous settings were restored where possible.",
                    ephemeral=True,
                )
                return
            await self.db.log_action(
                interaction.guild.id,
                interaction.user.id,
                "section_toggle",
                format_commit_message(interaction.user, f"{section} → {'enabled' if enabled else 'disabled'}"),
            )
            await interaction.followup.send(
                f"{'🟢' if enabled else '⚪'} **{section}** is now {'enabled' if enabled else 'disabled'}.",
                ephemeral=True,
            )
        except Exception:
            logger.exception("Failed setting dashboard section for guild %s", interaction.guild.id)
            if before is not None:
                await _restore_dashboard_config(self.db, self.bot, interaction.guild, before, f"failed section command {section}")
            if interaction.response.is_done():
                await interaction.followup.send("Couldn't update that category. Previous settings were restored where possible; check the bot logs.", ephemeral=True)
            else:
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
        if not self._ready:
            return
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
