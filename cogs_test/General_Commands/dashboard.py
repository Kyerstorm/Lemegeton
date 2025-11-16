# cogs/dashboard.py
import asyncio
import aiosqlite
import json
import logging
import datetime
import traceback
from typing import Any, Dict, List, Optional, Tuple

import discord
from discord import ui, app_commands
from discord.ext import commands

# ---------- Logging ----------
logger = logging.getLogger("dashboard_cog")
logger.setLevel(logging.INFO)
if not logger.handlers:
    fh = logging.FileHandler("logs/dashboard.log", encoding="utf-8")
    fh.setFormatter(logging.Formatter("[%(asctime)s] [%(levelname)s] %(message)s"))
    logger.addHandler(fh)

# ---------- Aesthetics ----------
PALETTE = {
    "deep_black": discord.Color.from_rgb(20, 20, 20),
    "midnight_blue": discord.Color.from_rgb(25, 25, 112),
    "royal_gold": discord.Color.from_rgb(212, 175, 55),
    "velvet_purple": discord.Color.from_rgb(90, 50, 130),
    "accent": discord.Color.from_rgb(80, 60, 120),
}
ENABLED_EMOJI = "✅"
DISABLED_EMOJI = "❌"
LOCK_EMOJI = "🔒"
GITHUB_ICON = "🐙"
GEAR = "⚙️"
WARN = "⚠️"

# ---------- Constants ----------
# protected commands that must always be enabled & cannot be toggled off.
PROTECTED_CMD_NAMES = {"help", "feedback"}
# how many command buttons to show per page (must keep total components <= 25)
COMMANDS_PER_PAGE = 10

# ---------- Command registry ----------
class CommandRegistry:
    def __init__(self):
        self._commands: Dict[str, Dict[str, Any]] = {}  # fullname -> meta
        self._sections: List[str] = []

    def register(self, fullname: str, cmd_obj: app_commands.Command, section: str, display_name: Optional[str] = None):
        display_name = display_name or getattr(cmd_obj, "name", fullname)
        if section not in self._sections:
            self._sections.append(section)
        self._commands[fullname] = {
            "command": cmd_obj,
            "section": section,
            "display_name": display_name,
            "description": getattr(cmd_obj, "description", "") or ""
        }

    def get_sections(self) -> List[str]:
        return list(self._sections)

    def get_commands_in_section(self, section: str) -> List[Tuple[str, Dict[str, Any]]]:
        return sorted([(k, v) for k, v in self._commands.items() if v["section"] == section],
                      key=lambda x: x[1]['display_name'].lower())

    def all_commands(self) -> List[Tuple[str, Dict[str, Any]]]:
        return sorted(self._commands.items(), key=lambda x: x[1]['display_name'].lower())

    def get_meta(self, fullname: str) -> Optional[Dict[str, Any]]:
        return self._commands.get(fullname)

    def find_fullname_by_cmd(self, cmd_obj: app_commands.Command) -> Optional[str]:
        for fullname, meta in self._commands.items():
            if meta["command"] is cmd_obj:
                return fullname
        return None

COMMAND_REGISTRY = CommandRegistry()

# ---------- Decorator (for other cogs) ----------
def command_meta(section: str, name: Optional[str] = None):
    def decorator(func_or_cmd):
        setattr(func_or_cmd, "__dashboard_section__", section)
        if name:
            setattr(func_or_cmd, "__dashboard_name__", name)
        else:
            setattr(func_or_cmd, "__dashboard_name__", getattr(func_or_cmd, "__name__", ""))
        return func_or_cmd
    return decorator

# ---------- Config DB ----------
class ConfigDB:
    def __init__(self, path: str = "data/dashboard_guilds.db"):
        self.path = path
        self._conn: Optional[aiosqlite.Connection] = None
        self._lock = asyncio.Lock()

    async def open(self):
        if self._conn is None:
            self._conn = await aiosqlite.connect(self.path)
            await self._conn.execute(
                "CREATE TABLE IF NOT EXISTS guild_configs (guild_id INTEGER PRIMARY KEY, data TEXT NOT NULL)"
            )
            await self._conn.execute(
                "CREATE TABLE IF NOT EXISTS audit_log (id INTEGER PRIMARY KEY AUTOINCREMENT, guild_id INTEGER, ts TEXT, actor_id INTEGER, action TEXT, details TEXT)"
            )
            await self._conn.commit()

    async def close(self):
        if self._conn:
            await self._conn.close()
            self._conn = None

    async def get_guild_config(self, guild_id: int) -> Dict[str, Any]:
        await self.open()
        async with self._lock:
            cur = await self._conn.execute("SELECT data FROM guild_configs WHERE guild_id = ?", (guild_id,))
            row = await cur.fetchone()
            if row is None:
                default = {"sections": {}, "commands": {}}
                await self._set_guild_config(guild_id, default)
                return default
            try:
                return json.loads(row[0])
            except Exception:
                # fallback: reset config if corrupted
                default = {"sections": {}, "commands": {}}
                await self._set_guild_config(guild_id, default)
                return default

    async def _set_guild_config(self, guild_id: int, data: Dict[str, Any]):
        await self.open()
        async with self._lock:
            j = json.dumps(data)
            await self._conn.execute(
                "INSERT INTO guild_configs (guild_id, data) VALUES (?, ?) ON CONFLICT(guild_id) DO UPDATE SET data = excluded.data",
                (guild_id, j)
            )
            await self._conn.commit()

    async def set_section(self, guild_id: int, section: str, enabled: bool):
        cfg = await self.get_guild_config(guild_id)
        cfg.setdefault("sections", {})[section] = bool(enabled)
        await self._set_guild_config(guild_id, cfg)

    async def set_command(self, guild_id: int, fullname: str, enabled: bool):
        cfg = await self.get_guild_config(guild_id)
        cfg.setdefault("commands", {})[fullname] = bool(enabled)
        await self._set_guild_config(guild_id, cfg)

    async def reset_guild(self, guild_id: int):
        default = {"sections": {}, "commands": {}}
        await self._set_guild_config(guild_id, default)

    async def log_action(self, guild_id: int, actor_id: int, action: str, details: str = ""):
        await self.open()
        ts = datetime.datetime.datetime.utcnow().isoformat() + "Z"
        async with self._lock:
            await self._conn.execute(
                "INSERT INTO audit_log (guild_id, ts, actor_id, action, details) VALUES (?, ?, ?, ?, ?)",
                (guild_id, ts, actor_id, action, details)
            )
            await self._conn.commit()

    async def last_audit_entries(self, guild_id: int, limit: int = 10) -> List[Dict[str, Any]]:
        await self.open()
        async with self._lock:
            cur = await self._conn.execute(
                "SELECT id, ts, actor_id, action, details FROM audit_log WHERE guild_id = ? ORDER BY id DESC LIMIT ?",
                (guild_id, limit)
            )
            rows = await cur.fetchall()
            out = []
            for r in rows:
                out.append({"id": r[0], "ts": r[1], "actor_id": r[2], "action": r[3], "details": r[4]})
            return out

# ---------- Utilities ----------
def format_commit_message(actor: discord.User, action: str, details: str = "") -> str:
    ts = datetime.datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
    commit = f"commit {datetime.datetime.datetime.utcnow().timestamp():.0f}\nAuthor: {actor} <{actor.id}>\nDate:   {ts}\n\n    {action}\n\n{details}"
    return commit

# ---------- Confirm modal ----------
class ConfirmModal(ui.Modal, title="Confirm"):
    reason = ui.TextInput(label="Reason (optional)", required=False, style=discord.TextStyle.short, max_length=200)
    def __init__(self):
        super().__init__()
        self.submitted_reason: Optional[str] = None
    async def on_submit(self, interaction: discord.Interaction):
        self.submitted_reason = self.reason.value
        await interaction.response.defer(ephemeral=True)

# ---------- Dashboard View ----------
class DashboardView(ui.View):
    def __init__(self, bot: commands.Bot, guild: discord.Guild, db: ConfigDB, timeout: int = 180):
        super().__init__(timeout=timeout)
        self.bot = bot
        self.guild = guild
        self.db = db

        # multiple sections preserved
        self.sections = COMMAND_REGISTRY.get_sections() or ["General"]
        # map section -> list of (fullname, meta)
        self.section_commands = {s: COMMAND_REGISTRY.get_commands_in_section(s) for s in self.sections}

        # UI state
        self.current_section_index = 0
        self.current_page = 0  # page within chosen section (commands pagination)

        # Build static controls: section select, prev/indicator/next (for sections)
        self.section_select = ui.Select(placeholder="Section...", min_values=1, max_values=1, options=[])
        self.section_select.callback = self.on_section_select
        self.add_item(self.section_select)

        self.prev_section_btn = ui.Button(emoji="◀️", style=discord.ButtonStyle.blurple)
        self.prev_section_btn.callback = self.on_prev_section
        self.add_item(self.prev_section_btn)

        self.section_page_indicator = ui.Button(label="1 / 1", style=discord.ButtonStyle.secondary, disabled=True)
        self.add_item(self.section_page_indicator)

        self.next_section_btn = ui.Button(emoji="▶️", style=discord.ButtonStyle.blurple)
        self.next_section_btn.callback = self.on_next_section
        self.add_item(self.next_section_btn)

        # Command-list pagination controls (Prev/Next commands page)
        self.prev_cmds_btn = ui.Button(label="Prev cmds", style=discord.ButtonStyle.gray)
        self.prev_cmds_btn.callback = self.on_prev_cmds
        self.add_item(self.prev_cmds_btn)

        self.cmds_page_indicator = ui.Button(label="1 / 1", style=discord.ButtonStyle.secondary, disabled=True)
        self.add_item(self.cmds_page_indicator)

        self.next_cmds_btn = ui.Button(label="Next cmds", style=discord.ButtonStyle.gray)
        self.next_cmds_btn.callback = self.on_next_cmds
        self.add_item(self.next_cmds_btn)

        # Audit / Reset
        self.reset_btn = ui.Button(label="Reset Config", emoji=WARN, style=discord.ButtonStyle.danger)
        self.reset_btn.callback = self.on_reset
        self.add_item(self.reset_btn)

        self.audit_btn = ui.Button(label="View Audit", emoji=GITHUB_ICON, style=discord.ButtonStyle.gray)
        self.audit_btn.callback = self.on_audit
        self.add_item(self.audit_btn)

        # populate select options now
        self.populate_section_select()
        self._update_section_nav_state()

    def populate_section_select(self):
        opts = []
        for s in self.sections:
            opts.append(discord.SelectOption(label=s, description=f"{len(self.section_commands.get(s, []))} cmds", emoji=GEAR))
        self.section_select.options = opts
        if self.sections:
            self.section_select.default_values = [self.sections[self.current_section_index]]

    def _update_section_nav_state(self):
        total = max(1, len(self.sections))
        idx = self.current_section_index + 1
        self.section_page_indicator.label = f"{idx} / {total}"
        if len(self.sections) <= 1:
            self.prev_section_btn.disabled = True
            self.next_section_btn.disabled = True
            self.section_select.disabled = True
        else:
            self.prev_section_btn.disabled = False
            self.next_section_btn.disabled = False
            self.section_select.disabled = False

    def _update_cmds_nav_state(self, section: str):
        cmds = self.section_commands.get(section, [])
        total_pages = max(1, (len(cmds) + COMMANDS_PER_PAGE - 1) // COMMANDS_PER_PAGE)
        self.cmds_page_indicator.label = f"{self.current_page + 1} / {total_pages}"
        self.prev_cmds_btn.disabled = (self.current_page <= 0)
        self.next_cmds_btn.disabled = (self.current_page >= total_pages - 1)

    async def send_initial(self, interaction: discord.Interaction):
        embed = self._build_embed_for_current_state(interaction.user)
        # initially respond as a followup (we expect the command deferred)
        await interaction.followup.send(embed=embed, view=self, ephemeral=False)
        # and update the message to show command buttons
        await self.update_command_list_message(interaction)

    def _build_embed_for_current_state(self, actor: discord.User) -> discord.Embed:
        section = self.sections[self.current_section_index]
        total_cmds = len(self.section_commands.get(section, []))
        embed = discord.Embed(
            title=f"{GITHUB_ICON} Server Dashboard — {section}",
            color=PALETTE["velvet_purple"],
            description=f"Manage commands for **{self.guild.name}** (`{self.guild.id}`)\n\nUse the buttons to toggle commands. Locked commands are always enabled."
        )
        embed.set_footer(text=f"UX: compact • Page size {COMMANDS_PER_PAGE} • Actor: {actor}")
        embed.add_field(name="Commands in section", value=f"{total_cmds} total", inline=True)
        return embed

    async def update_command_list_message(self, interaction: discord.Interaction):
        """
        Build buttons for the current section & page, then edit the original followup message to update.
        """
        try:
            section = self.sections[self.current_section_index]
            cmds = self.section_commands.get(section, [])
            cfg = await self.db.get_guild_config(self.guild.id)

            # ensure default behavior: protected commands are True, others default False when missing
            changed = False
            for fullname, meta in cmds:
                name = meta["command"].name if meta.get("command") else fullname
                if fullname not in cfg.get("commands", {}):
                    # default protected True, others False
                    default_val = (name in PROTECTED_CMD_NAMES)
                    cfg.setdefault("commands", {})[fullname] = bool(default_val)
                    changed = True
            if changed:
                await self.db._set_guild_config(self.guild.id, cfg)

            # pagination
            start = self.current_page * COMMANDS_PER_PAGE
            page_items = cmds[start:start + COMMANDS_PER_PAGE]

            # build embed
            embed = self._build_embed_for_current_state(interaction.user)
            lines = []

            # locked/protected split for clarity
            locked_lines = []
            normal_lines = []
            for fullname, meta in page_items:
                cmd_name = meta["display_name"]
                cmd_obj = meta["command"]
                simple_name = getattr(cmd_obj, "name", fullname)
                is_protected = simple_name in PROTECTED_CMD_NAMES
                enabled_in_cfg = cfg.get("commands", {}).get(fullname, False)
                # effective = protected always True, else enabled_in_cfg
                effective = True if is_protected else bool(enabled_in_cfg)
                emoji = LOCK_EMOJI if is_protected else (ENABLED_EMOJI if effective else DISABLED_EMOJI)
                desc = meta.get("description", "")[:80]
                line = f"{emoji} **{cmd_name}** — `{simple_name}`\n{desc}"
                if is_protected:
                    locked_lines.append(line)
                else:
                    normal_lines.append(line)

            if locked_lines:
                embed.add_field(name="Locked system commands", value="\n\n".join(locked_lines), inline=False)
            if normal_lines:
                embed.add_field(name=f"Commands (page {self.current_page + 1})", value="\n\n".join(normal_lines), inline=False)
            if not locked_lines and not normal_lines:
                embed.add_field(name="No commands on this page", value="There are no commands for this page.", inline=False)

            # build a fresh view clone so we can add dynamic per-command buttons (buttons must be attached to the message)
            new_view = DashboardView._clone_static_for_message(self, for_guild=self.guild)

            # add per-command toggle buttons for current page (protected commands get disabled locked buttons)
            for fullname, meta in page_items:
                cmd_obj = meta["command"]
                simple_name = getattr(cmd_obj, "name", fullname)
                is_protected = simple_name in PROTECTED_CMD_NAMES
                enabled_in_cfg = cfg.get("commands", {}).get(fullname, False)
                effective = True if is_protected else bool(enabled_in_cfg)

                label = (meta["display_name"][:80]) or simple_name
                emoji = LOCK_EMOJI if is_protected else (ENABLED_EMOJI if effective else DISABLED_EMOJI)
                style = discord.ButtonStyle.success if effective else discord.ButtonStyle.secondary
                btn = ui.Button(label=label, emoji=emoji, style=style)

                # disable click for protected commands
                if is_protected:
                    btn.disabled = True
                else:
                    # assign callback capturing fullname
                    async def make_cb(f):
                        async def cb(i: discord.Interaction):
                            # prevent race conditions & spam
                            try:
                                btn.disabled = True
                                await i.response.defer(ephemeral=True)
                                # toggle value
                                cur_cfg = await self.db.get_guild_config(self.guild.id)
                                cur_val = cur_cfg.get("commands", {}).get(f, False)
                                new_val = not bool(cur_val)
                                await self.db.set_command(self.guild.id, f, new_val)
                                commit = format_commit_message(i.user, f"Toggled command `{f}` -> {'enabled' if new_val else 'disabled'}", "")
                                await self.db.log_action(self.guild.id, i.user.id, f"toggle_command {f} -> {new_val}", commit)
                                # attempt to sync (removes or adds guild commands)
                                await attempt_sync_for_guild(self.bot, self.guild)
                                # update the message view
                                await self.update_command_list_message(i)
                            except Exception:
                                logger.exception("Error toggling command")
                            finally:
                                try:
                                    btn.disabled = False
                                except Exception:
                                    pass
                        return cb
                    btn.callback = await make_cb(fullname)

                new_view.add_item(btn)

            # update pagination controls state
            self._update_cmds_nav_state(section)
            # we keep nav controls in the cloned view (their callbacks already assigned)
            # edit original message - try interaction.edit_original_response first
            try:
                await interaction.edit_original_response(embed=embed, view=new_view)
            except Exception:
                # fallback: followup edit or channel send
                try:
                    if interaction.followup:
                        await interaction.followup.edit_message(interaction.message.id, embed=embed, view=new_view)
                except Exception:
                    await interaction.channel.send(embed=embed, view=new_view)
        except Exception:
            logger.exception("Failed to update command list message")

    @staticmethod
    def _clone_static_for_message(old: "DashboardView", *, for_guild: discord.Guild) -> ui.View:
        """
        Create a fresh view with static nav callbacks referencing the original's methods.
        Dynamic command buttons are added later by caller.
        """
        v = ui.View(timeout=old.timeout)
        # section select
        sel = ui.Select(placeholder="Section...", min_values=1, max_values=1, options=old.section_select.options)
        sel.callback = old.on_section_select
        sel.default_values = old.section_select.default_values
        v.add_item(sel)
        # prev / section indicator / next
        prev = ui.Button(emoji="◀️", style=discord.ButtonStyle.blurple)
        prev.callback = old.on_prev_section
        v.add_item(prev)
        page = ui.Button(label=old.section_page_indicator.label, style=discord.ButtonStyle.secondary, disabled=True)
        v.add_item(page)
        nxt = ui.Button(emoji="▶️", style=discord.ButtonStyle.blurple)
        nxt.callback = old.on_next_section
        v.add_item(nxt)
        # commands page nav
        prevc = ui.Button(label="Prev cmds", style=discord.ButtonStyle.gray)
        prevc.callback = old.on_prev_cmds
        v.add_item(prevc)
        pagec = ui.Button(label=old.cmds_page_indicator.label, style=discord.ButtonStyle.secondary, disabled=True)
        v.add_item(pagec)
        nxtc = ui.Button(label="Next cmds", style=discord.ButtonStyle.gray)
        nxtc.callback = old.on_next_cmds
        v.add_item(nxtc)
        # reset & audit
        reset = ui.Button(label="Reset Config", emoji=WARN, style=discord.ButtonStyle.danger)
        reset.callback = old.on_reset
        v.add_item(reset)
        audit = ui.Button(label="View Audit", emoji=GITHUB_ICON, style=discord.ButtonStyle.gray)
        audit.callback = old.on_audit
        v.add_item(audit)
        return v

    # ---------- interactions ----------
    async def on_section_select(self, interaction: discord.Interaction):
        try:
            val = interaction.data.get("values", [None])[0] if interaction.data else None
            if not val:
                # fallback to component value
                val = self.section_select.values[0] if self.section_select.values else None
            if val in self.sections:
                self.current_section_index = self.sections.index(val)
                self.current_page = 0
            await interaction.response.defer(ephemeral=True)
            self._update_section_nav_state()
            await self.update_command_list_message(interaction)
        except Exception:
            logger.exception("Error in on_section_select")

    async def on_prev_section(self, interaction: discord.Interaction):
        try:
            if len(self.sections) <= 1:
                await interaction.response.send_message("No other sections.", ephemeral=True)
                return
            self.current_section_index = (self.current_section_index - 1) % len(self.sections)
            self.section_select.default_values = [self.sections[self.current_section_index]]
            self.current_page = 0
            await interaction.response.defer(ephemeral=True)
            self._update_section_nav_state()
            await self.update_command_list_message(interaction)
        except Exception:
            logger.exception("Error in on_prev_section")

    async def on_next_section(self, interaction: discord.Interaction):
        try:
            if len(self.sections) <= 1:
                await interaction.response.send_message("No other sections.", ephemeral=True)
                return
            self.current_section_index = (self.current_section_index + 1) % len(self.sections)
            self.section_select.default_values = [self.sections[self.current_section_index]]
            self.current_page = 0
            await interaction.response.defer(ephemeral=True)
            self._update_section_nav_state()
            await self.update_command_list_message(interaction)
        except Exception:
            logger.exception("Error in on_next_section")

    async def on_prev_cmds(self, interaction: discord.Interaction):
        try:
            if self.current_page <= 0:
                await interaction.response.send_message("No previous page.", ephemeral=True)
                return
            self.current_page -= 1
            await interaction.response.defer(ephemeral=True)
            await self.update_command_list_message(interaction)
        except Exception:
            logger.exception("Error in on_prev_cmds")

    async def on_next_cmds(self, interaction: discord.Interaction):
        try:
            section = self.sections[self.current_section_index]
            cmds = self.section_commands.get(section, [])
            max_page = max(0, (len(cmds) - 1) // COMMANDS_PER_PAGE)
            if self.current_page >= max_page:
                await interaction.response.send_message("No next page.", ephemeral=True)
                return
            self.current_page += 1
            await interaction.response.defer(ephemeral=True)
            await self.update_command_list_message(interaction)
        except Exception:
            logger.exception("Error in on_next_cmds")

    async def on_reset(self, interaction: discord.Interaction):
        try:
            modal = ConfirmModal()
            await interaction.response.send_modal(modal)
            await modal.wait()
            reason = modal.submitted_reason or ""
            await self.db.reset_guild(self.guild.id)
            commit = format_commit_message(interaction.user, f"Reset config for guild {self.guild.id}", reason)
            await self.db.log_action(self.guild.id, interaction.user.id, "reset_guild", commit)
            await attempt_sync_for_guild(self.bot, self.guild)
            await interaction.followup.send(content=f"{ENABLED_EMOJI} Guild configuration reset.", ephemeral=True)
            await self.update_command_list_message(interaction)
        except Exception:
            logger.exception("Error in on_reset")

    async def on_audit(self, interaction: discord.Interaction):
        try:
            entries = await self.db.last_audit_entries(self.guild.id, limit=12)
            if not entries:
                await interaction.response.send_message("No audit entries found.", ephemeral=True)
                return
            lines = []
            for e in entries:
                ts = e["ts"]
                actor = e["actor_id"]
                action = e["action"]
                lines.append(f"`{e['id']}` {ts} <{actor}> — {action}")
            await interaction.response.send_message("Recent audit entries:\n" + "\n".join(lines), ephemeral=True)
        except Exception:
            logger.exception("Error in on_audit")

# ---------- Sync helper ----------
async def attempt_sync_for_guild(bot: commands.Bot, guild: discord.Guild):
    """
    Sync enabled commands to the guild. Defaults: protected commands True; others default False.
    """
    db: ConfigDB = getattr(bot, "_dashboard_db", None)
    if db is None:
        return
    try:
        cfg = await db.get_guild_config(guild.id)
        enabled_cmds = []
        for fullname, meta in COMMAND_REGISTRY.all_commands():
            cmd_obj: app_commands.Command = meta["command"]
            simple_name = getattr(cmd_obj, "name", fullname)
            # protection: if command name in protected, always include
            if simple_name in PROTECTED_CMD_NAMES:
                enabled_cmds.append(cmd_obj)
                # ensure persisted True
                if cfg.get("commands", {}).get(fullname) is not True:
                    cfg.setdefault("commands", {})[fullname] = True
            else:
                # default behavior: if not present assume disabled; only add if explicitly True
                if cfg.get("commands", {}).get(fullname, False):
                    enabled_cmds.append(cmd_obj)
        # persist any default changes (e.g., protected commands added)
        await db._set_guild_config(guild.id, cfg)

        # Attempt to sync: clear then add enabled guild-scoped commands
        try:
            # NOTE: clearing guild commands may be destructive for non-dashboard commands; we only sync dashboard-managed commands
            # We'll remove previously added commands by name if possible, but simplest is to re-sync enabled commands for this guild
            # Remove all commands previously added by us: attempt to clear guild commands, but be conservative: only add enabled_cmds
            # Clear and re-add:
            try:
                bot.tree.clear_commands(guild=guild)
            except Exception:
                # in case clear_commands is not supported for guild param in this runtime, ignore
                pass

            for cmd in enabled_cmds:
                try:
                    bot.tree.add_command(cmd, guild=guild)
                except Exception:
                    logger.debug("Couldn't add command %s to guild %s", getattr(cmd, "name", "<unknown>"), guild.id)
            try:
                await bot.tree.sync(guild=guild)
                logger.info("Synced dashboard-enabled commands to guild %s", guild.id)
            except Exception:
                logger.exception("Error syncing commands to guild %s", guild.id)
        except Exception:
            logger.exception("Error while re-registering commands for guild %s", guild.id)
    except Exception:
        logger.exception("Error in attempt_sync_for_guild")

# ---------- Cog ----------
class DashboardCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.db = ConfigDB()
        self._ready = False

    async def _startup_tasks(self):
        try:
            setattr(self.bot, "_dashboard_db", self.db)
            await self.db.open()

            # discover app_commands from bot.tree (auto mode)
            for cmd in list(self.bot.tree.commands):
                # top-level commands and groups
                tried = []
                def register_if_meta(c):
                    cb = getattr(c, "callback", None)
                    if cb:
                        sec = getattr(cb, "__dashboard_section__", None)
                        name = getattr(cb, "__dashboard_name__", None)
                        if sec is not None:
                            fullname = getattr(c, "qualified_name", getattr(c, "name", None))
                            COMMAND_REGISTRY.register(fullname, c, section=sec, display_name=name or c.name)
                            tried.append(fullname)
                register_if_meta(cmd)
                # groups -> subcommands
                if isinstance(cmd, app_commands.Group):
                    for sub in cmd.commands:
                        register_if_meta(sub)

        except Exception:
            logger.exception("Error during dashboard startup tasks")
        finally:
            self._ready = True

    # Dashboard command
    @app_commands.command(name="dashboard", description="Open the server dashboard to configure the bot")
    async def dashboard(self, interaction: discord.Interaction):
        if interaction.guild is None:
            await interaction.response.send_message("This command is available only in servers.", ephemeral=True)
            return
        perms = interaction.user.guild_permissions
        if not (perms.manage_guild or perms.administrator or perms.manage_roles or interaction.user.id == getattr(self.bot, "owner_id", None)):
            await interaction.response.send_message("You need Manage Server (or similar) to access the dashboard.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=False)
        view = DashboardView(self.bot, interaction.guild, self.db)
        await view.send_initial(interaction)

    @app_commands.command(name="dashboard-section-toggle", description="(Admin) Toggle a section on/off")
    async def section_toggle(self, interaction: discord.Interaction, section: str, enabled: bool):
        if interaction.guild is None:
            await interaction.response.send_message("Only for servers.", ephemeral=True)
            return
        perms = interaction.user.guild_permissions
        if not (perms.manage_guild or perms.administrator or interaction.user.id == getattr(self.bot, "owner_id", None)):
            await interaction.response.send_message("You need Manage Server permissions.", ephemeral=True)
            return
        await self.db.set_section(interaction.guild.id, section, enabled)
        commit = format_commit_message(interaction.user, f"Section {section} -> {'enabled' if enabled else 'disabled'}", "")
        await self.db.log_action(interaction.guild.id, interaction.user.id, f"section_toggle {section} -> {enabled}", commit)
        await attempt_sync_for_guild(self.bot, interaction.guild)
        await interaction.response.send_message(f"{ENABLED_EMOJI} Section `{section}` set to {'enabled' if enabled else 'disabled'}.", ephemeral=True)

    @commands.Cog.listener()
    async def on_guild_join(self, guild: discord.Guild):
        # ensure default config exists and attempt initial sync (will persist protected commands true)
        await self.db.get_guild_config(guild.id)
        await attempt_sync_for_guild(self.bot, guild)

    @commands.Cog.listener()
    async def on_ready(self):
        if self._ready:
            return
        await self._startup_tasks()
        # attempt to ensure each guild has protected commands enabled by default
        for g in self.bot.guilds:
            try:
                await attempt_sync_for_guild(self.bot, g)
            except Exception:
                logger.exception("Error initial syncing for guild %s", g.id)
# ---------- Cog loader ----------
async def setup(bot: commands.Bot):
    await bot.add_cog(DashboardCog(bot))
