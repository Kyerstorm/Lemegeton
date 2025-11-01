# cogs/dashboard.py
import asyncio
import aiosqlite
import json
import logging
import datetime
import traceback
from typing import Any, Dict, List, Optional, Tuple, Set, Callable

import discord
from discord import ui, app_commands
from discord.ext import commands

logger = logging.getLogger("dashboard_cog")
logger.setLevel(logging.INFO)

# dark aesthetic palette provided by user
PALETTE = {
    "deep_black": discord.Color.from_rgb(20, 20, 20),
    "midnight_blue": discord.Color.from_rgb(25, 25, 112),
    "royal_gold": discord.Color.from_rgb(212, 175, 55),
    "velvet_purple": discord.Color.from_rgb(90, 50, 130),
    "accent": discord.Color.from_rgb(80, 60, 120),
}

ENABLED_EMOJI = "✅"
DISABLED_EMOJI = "❌"
GITHUB_ICON = "🐙"
GEAR = "⚙️"
WARN = "⚠️"

# global registry for commands metadata
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
            "description": getattr(cmd_obj, "description", "")
        }

    def get_sections(self) -> List[str]:
        return list(self._sections)

    def get_commands_in_section(self, section: str) -> List[Tuple[str, Dict[str, Any]]]:
        return sorted([(k, v) for k, v in self._commands.items() if v["section"] == section], key=lambda x: x[0])

    def all_commands(self) -> List[Tuple[str, Dict[str, Any]]]:
        return sorted(self._commands.items(), key=lambda x: x[0])

    def get_meta(self, fullname: str) -> Optional[Dict[str, Any]]:
        return self._commands.get(fullname)

    def find_fullname_by_cmd(self, cmd_obj: app_commands.Command) -> Optional[str]:
        for fullname, meta in self._commands.items():
            if meta["command"] is cmd_obj:
                return fullname
        return None

COMMAND_REGISTRY = CommandRegistry()

# decorator used by other cogs to annotate app command callbacks
def command_meta(section: str, name: Optional[str] = None):
    def decorator(func_or_cmd):
        setattr(func_or_cmd, "__dashboard_section__", section)
        if name:
            setattr(func_or_cmd, "__dashboard_name__", name)
        else:
            setattr(func_or_cmd, "__dashboard_name__", getattr(func_or_cmd, "__name__", ""))
        return func_or_cmd
    return decorator

# runtime check to enforce disabled commands
def app_command_enabled_check():
    async def predicate(interaction: discord.Interaction) -> bool:
        bot = interaction.client
        db: "ConfigDB" = getattr(bot, "_dashboard_db", None)
        if db is None:
            return True
        if interaction.guild is None:
            return True
        cmd = interaction.command
        fullname = None
        if cmd:
            fullname = COMMAND_REGISTRY.find_fullname_by_cmd(cmd)
        cfg = await db.get_guild_config(interaction.guild.id)
        # section-level
        if fullname:
            meta = COMMAND_REGISTRY.get_meta(fullname)
            if meta:
                sec = meta["section"]
                if not cfg["sections"].get(sec, True):
                    return False
        # command-level
        if fullname:
            return bool(cfg["commands"].get(fullname, True))
        return True
    return app_commands.check(predicate)

# async DB wrapper using aiosqlite
class ConfigDB:
    def __init__(self, path: str = "dashboard_guilds.db"):
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
            return json.loads(row[0])

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
        ts = datetime.datetime.utcnow().isoformat() + "Z"
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

# small helper to format GitHub-like commit messages
def format_commit_message(actor: discord.User, action: str, details: str = "") -> str:
    ts = datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
    commit = f"commit {datetime.datetime.utcnow().timestamp():.0f}\nAuthor: {actor} <{actor.id}>\nDate:   {ts}\n\n    {action}\n\n{details}"
    return commit

# UI: Confirm modal (reason)
class ConfirmModal(ui.Modal, title="Confirm"):
    reason = ui.TextInput(label="Reason (optional)", required=False, style=discord.TextStyle.short, max_length=200)
    def __init__(self):
        super().__init__()
        self.submitted_reason: Optional[str] = None

    async def on_submit(self, interaction: discord.Interaction):
        self.submitted_reason = self.reason.value
        await interaction.response.defer(ephemeral=True)

# UI: Dashboard view (main)
class DashboardView(ui.View):
    def __init__(self, bot: commands.Bot, guild: discord.Guild, db: ConfigDB, timeout: int = 180):
        super().__init__(timeout=timeout)
        self.bot = bot
        self.guild = guild
        self.db = db
        self.sections = COMMAND_REGISTRY.get_sections() or ["General"]
        self.current_index = 0
        self.section_select = ui.Select(placeholder="Select section...", min_values=1, max_values=1, options=[])
        self.section_select.callback = self.on_section_select
        self.add_item(self.section_select)
        self.prev_btn = ui.Button(emoji="◀️", style=discord.ButtonStyle.blurple)
        self.prev_btn.callback = self.on_prev
        self.add_item(self.prev_btn)
        self.next_btn = ui.Button(emoji="▶️", style=discord.ButtonStyle.blurple)
        self.next_btn.callback = self.on_next
        self.add_item(self.next_btn)
        self.reset_btn = ui.Button(label="Reset Config", emoji=WARN, style=discord.ButtonStyle.danger)
        self.reset_btn.callback = self.on_reset
        self.add_item(self.reset_btn)
        self.audit_btn = ui.Button(label="View Audit", emoji=GITHUB_ICON, style=discord.ButtonStyle.gray)
        self.audit_btn.callback = self.on_audit
        self.add_item(self.audit_btn)
        self.populate_select()

    def populate_select(self):
        options = []
        for s in self.sections:
            options.append(discord.SelectOption(label=s, description=f"Section: {s}", emoji=GEAR))
        self.section_select.options = options
        if self.sections:
            self.section_select.default_values = [self.sections[self.current_index]]

    async def send_initial(self, interaction: discord.Interaction):
        embed = self.build_embed_for_section(self.sections[self.current_index], interaction.user)
        await interaction.response.send_message(embed=embed, view=self, ephemeral=False)
        await self.update_section_message(interaction)

    def build_embed_for_section(self, section: str, actor: discord.User) -> discord.Embed:
        color = PALETTE["midnight_blue"]
        embed = discord.Embed(title=f"{GITHUB_ICON} /dashboard — {section}", color=color)
        embed.add_field(name="Guild", value=f"{self.guild.name} (`{self.guild.id}`)", inline=True)
        embed.set_footer(text=f"Dark Dashboard • git-style audit available • {actor}")
        return embed

    async def update_section_message(self, interaction: discord.Interaction):
        # build state and update message with dynamic command toggles
        section = self.sections[self.current_index]
        cfg = await self.db.get_guild_config(self.guild.id)
        section_enabled = cfg["sections"].get(section, True)
        commands = COMMAND_REGISTRY.get_commands_in_section(section)
        embed = discord.Embed(title=f"{GITHUB_ICON} {section} — Dashboard", color=PALETTE["velvet_purple"])
        embed.add_field(name="Section enabled", value=(ENABLED_EMOJI if section_enabled else DISABLED_EMOJI), inline=True)
        if not commands:
            embed.add_field(name="Commands", value="(no registered commands in this section)", inline=False)
        else:
            lines = []
            for fullname, meta in commands:
                cmd_enabled = cfg["commands"].get(fullname, True)
                effective = cmd_enabled and section_enabled
                emoji = ENABLED_EMOJI if effective else DISABLED_EMOJI
                lines.append(f"{emoji} **{meta['display_name']}** — `{fullname}`")
            embed.add_field(name="Commands", value="\n".join(lines[:25]) or "none", inline=False)
        # build a fresh view clone to include command buttons
        new_view = DashboardView._clone_static(self, for_guild=self.guild)
        # add per-command toggle buttons
        for fullname, meta in commands:
            cmd_enabled = cfg["commands"].get(fullname, True)
            effective = cmd_enabled and section_enabled
            label = meta["display_name"]
            style = discord.ButtonStyle.success if effective else discord.ButtonStyle.secondary
            emoji = ENABLED_EMOJI if effective else DISABLED_EMOJI
            btn = ui.Button(label=label, emoji=emoji, style=style, custom_id=f"toggle::{fullname}")
            async def make_cb(f):
                async def cb(i: discord.Interaction):
                    cur_cfg = await self.db.get_guild_config(self.guild.id)
                    cur_val = cur_cfg["commands"].get(f, True)
                    new_val = not cur_val
                    await self.db.set_command(self.guild.id, f, new_val)
                    # log as git-like commit
                    commit = format_commit_message(i.user, f"Toggled command `{f}` to {'enabled' if new_val else 'disabled'}", details="")
                    await self.db.log_action(self.guild.id, i.user.id, f"toggle_command {f} -> {new_val}", commit)
                    # best-effort sync
                    await attempt_sync_for_guild(self.bot, self.guild)
                    await i.response.defer(ephemeral=True)
                    await self.update_section_message(i)
                return cb
            btn.callback = await make_cb(fullname)
            new_view.add_item(btn)
        # add section toggle
        sec_label = f"{'Disable' if section_enabled else 'Enable'} Section"
        sec_style = discord.ButtonStyle.danger if section_enabled else discord.ButtonStyle.success
        sec_btn = ui.Button(label=sec_label, style=sec_style)
        async def sec_cb(i: discord.Interaction):
            await i.response.defer(ephemeral=True)
            new_state = not section_enabled
            await self.db.set_section(self.guild.id, section, new_state)
            commit = format_commit_message(i.user, f"Section `{section}` set to {'enabled' if new_state else 'disabled'}", "")
            await self.db.log_action(self.guild.id, i.user.id, f"toggle_section {section} -> {new_state}", commit)
            await attempt_sync_for_guild(self.bot, self.guild)
            await self.update_section_message(i)
        sec_btn.callback = sec_cb
        new_view.add_item(sec_btn)
        # send edit
        try:
            await interaction.edit_original_response(embed=embed, view=new_view)
        except Exception:
            try:
                await interaction.followup.edit_message(interaction.message.id, embed=embed, view=new_view)
            except Exception:
                # fallback to sending new message
                await interaction.channel.send(embed=embed, view=new_view)

    @staticmethod
    def _clone_static(old: "DashboardView", *, for_guild: discord.Guild) -> ui.View:
        v = ui.View(timeout=old.timeout)
        sel = ui.Select(placeholder="Select section...", min_values=1, max_values=1, options=[])
        sel.callback = old.on_section_select
        sel.options = old.section_select.options
        sel.default_values = old.section_select.default_values
        v.add_item(sel)
        prev = ui.Button(emoji="◀️", style=discord.ButtonStyle.blurple)
        prev.callback = old.on_prev
        v.add_item(prev)
        nxt = ui.Button(emoji="▶️", style=discord.ButtonStyle.blurple)
        nxt.callback = old.on_next
        v.add_item(nxt)
        reset = ui.Button(label="Reset Config", emoji=WARN, style=discord.ButtonStyle.danger)
        reset.callback = old.on_reset
        v.add_item(reset)
        audit = ui.Button(label="View Audit", emoji=GITHUB_ICON, style=discord.ButtonStyle.gray)
        audit.callback = old.on_audit
        v.add_item(audit)
        return v

    async def on_section_select(self, interaction: discord.Interaction):
        val = self.section_select.values[0]
        if val in self.sections:
            self.current_index = self.sections.index(val)
        await interaction.response.defer(ephemeral=True)
        await self.update_section_message(interaction)

    async def on_prev(self, interaction: discord.Interaction):
        self.current_index = (self.current_index - 1) % len(self.sections)
        self.section_select.default_values = [self.sections[self.current_index]]
        await interaction.response.defer(ephemeral=True)
        await self.update_section_message(interaction)

    async def on_next(self, interaction: discord.Interaction):
        self.current_index = (self.current_index + 1) % len(self.sections)
        self.section_select.default_values = [self.sections[self.current_index]]
        await interaction.response.defer(ephemeral=True)
        await self.update_section_message(interaction)

    async def on_reset(self, interaction: discord.Interaction):
        modal = ConfirmModal()
        await interaction.response.send_modal(modal)
        await modal.wait()
        reason = modal.submitted_reason or ""
        await self.db.reset_guild(self.guild.id)
        commit = format_commit_message(interaction.user, f"Reset config for guild {self.guild.id}", reason)
        await self.db.log_action(self.guild.id, interaction.user.id, "reset_guild", commit)
        await attempt_sync_for_guild(self.bot, self.guild)
        await interaction.followup.send(content=f"{ENABLED_EMOJI} Guild configuration reset.", ephemeral=True)
        await self.update_section_message(interaction)

    async def on_audit(self, interaction: discord.Interaction):
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

# attempt to sync enabled commands to guild so disabled commands are hidden (best-effort)
async def attempt_sync_for_guild(bot: commands.Bot, guild: discord.Guild):
    db: ConfigDB = getattr(bot, "_dashboard_db", None)
    if db is None:
        return
    try:
        cfg = await db.get_guild_config(guild.id)
        enabled_cmds = []
        for fullname, meta in COMMAND_REGISTRY.all_commands():
            sec = meta["section"]
            cmd_enabled = cfg["commands"].get(fullname, True)
            sec_enabled = cfg["sections"].get(sec, True)
            if cmd_enabled and sec_enabled:
                enabled_cmds.append(meta["command"])
        # clear guild commands then add enabled
        try:
            bot.tree.clear_commands(guild=guild)
        except Exception:
            pass
        for cmd in enabled_cmds:
            try:
                bot.tree.add_command(cmd, guild=guild)
            except Exception:
                # some command objects cannot be re-added; ignore
                logger.debug("Could not add command %s to guild %s", getattr(cmd, "name", "<unknown>"), guild.id)
        try:
            await bot.tree.sync(guild=guild)
            logger.debug("Synced %d commands for guild %s", len(enabled_cmds), guild.id)
        except Exception as e:
            logger.warning("Sync failed for guild %s: %s", guild.id, e)
    except Exception:
        logger.exception("Error in attempt_sync_for_guild")

# main cog
class DashboardCog(commands.Cog):
    def __init__(self, bot: commands.Bot, *, db_path: str = "dashboard_guilds.db"):
        self.bot = bot
        self.db = ConfigDB(db_path)
        setattr(bot, "_dashboard_db", self.db)
        self._ready = False

    async def cog_load(self):
        """Initialize the dashboard cog."""
        # schedule setup tasks after ready
        asyncio.create_task(self._startup_tasks())

    async def _startup_tasks(self):
        await self.bot.wait_until_ready()
        await self.db.open()
        await self._discover_meta_commands()
        # initial per-guild sync
        for g in list(self.bot.guilds):
            asyncio.create_task(attempt_sync_for_guild(self.bot, g))
        logger.info("DashboardCog initialized: %d sections", len(COMMAND_REGISTRY.get_sections()))
        self._ready = True

    async def _discover_meta_commands(self):
        # scan bot.tree commands for attributes set by @command_meta
        for cmd in list(self.bot.tree.get_commands()):
            try:
                cb = getattr(cmd, "callback", None)
                if cb is not None:
                    sec = getattr(cb, "__dashboard_section__", None)
                    name = getattr(cb, "__dashboard_name__", None)
                    if sec is not None:
                        fullname = cmd.qualified_name
                        COMMAND_REGISTRY.register(fullname, cmd, section=sec, display_name=name or cmd.name)
                # handle groups
                if isinstance(cmd, app_commands.Group):
                    for sub in cmd.commands:
                        cb2 = getattr(sub, "callback", None)
                        if cb2:
                            sec = getattr(cb2, "__dashboard_section__", None)
                            name = getattr(cb2, "__dashboard_name__", None)
                            if sec is not None:
                                fullname = sub.qualified_name
                                COMMAND_REGISTRY.register(fullname, sub, section=sec, display_name=name or sub.name)
            except Exception:
                logger.debug("Error registering command meta: %s", traceback.format_exc())

    # /dashboard command
    @app_commands.command(name="dashboard", description="Open the server dashboard to configure the bot")
    async def dashboard(self, interaction: discord.Interaction):
        # only in guilds
        if interaction.guild is None:
            await interaction.response.send_message("This command is only available in servers.", ephemeral=True)
            return
        # permission check
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

    # helper to register manually-created app_commands to dashboard registry
    def register_command_for_dashboard(self, cmd: app_commands.Command, section: str, display_name: Optional[str] = None):
        fullname = getattr(cmd, "qualified_name", getattr(cmd, "name", None))
        if fullname is None:
            fullname = cmd.name
        COMMAND_REGISTRY.register(fullname, cmd, section=section, display_name=display_name)

    @commands.Cog.listener()
    async def on_guild_join(self, guild: discord.Guild):
        await self.db.get_guild_config(guild.id)
        await attempt_sync_for_guild(self.bot, guild)

    @commands.Cog.listener()
    async def on_ready(self):
        if self._ready:
            return
        await self._startup_tasks()

# Example: register a demo command in the registry so dashboard is not empty
async def _demo_callback(interaction: discord.Interaction):
    await interaction.response.send_message("Demo command executed.", ephemeral=True)

demo_cmd = app_commands.Command(name="demo", description="Demo command", callback=_demo_callback)
COMMAND_REGISTRY.register("demo", demo_cmd, section="General", display_name="Demo Command")

# ---------------------------
# Placeholders for sections
# ---------------------------
# You asked for placeholders where you can add your sections.
#
# Below are commented placeholders demonstrating how to define sections and how to annotate
# your app commands so they appear in the dashboard.
#
# Example usage:
#
# @app_commands.command(name="kick", description="Kick a member")
# @command_meta(section="Moderation", name="Kick")
# @app_commands.check(app_command_enabled_check())
# async def kick(interaction: discord.Interaction, member: discord.Member, reason: Optional[str] = None):
#     # your moderation logic
#     await interaction.response.send_message(f"Kicked {member}.", ephemeral=True)
#
# COMMAND_REGISTRY.register("kick", <the_command_obj>, section="Moderation", display_name="Kick")
#
# Placeholders:
# - Moderation
# - Utility
# - Fun
# - Economy
# - Info
#
# Add them by decorating and registering commands as shown above.

# loader for extension
async def setup(bot: commands.Bot):
    cog = DashboardCog(bot)
    await bot.add_cog(cog)
    logger.info("Loaded DashboardCog")

# end of file
