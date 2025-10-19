# cogs/dashboard.py
import asyncio
import sqlite3
import json
import logging
from typing import Optional, Dict, List, Any, Callable, Tuple, Set

import discord
from discord import ui, app_commands
from discord.ext import commands

# Configure logger for this module
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# -----------------------------------------------------------------------------
# AESTHETIC PALETTE (dark)
# -----------------------------------------------------------------------------
PALETTE = {
    "deep_black": discord.Color.from_rgb(20, 20, 20),
    "midnight_blue": discord.Color.from_rgb(25, 25, 112),
    "royal_gold": discord.Color.from_rgb(212, 175, 55),
    "velvet_purple": discord.Color.from_rgb(90, 50, 130),
    "accent": discord.Color.from_rgb(80, 60, 120),
}

# Extra aesthetic constants
BADGE_EMOJI = "⚙️"
ENABLED_EMOJI = "✅"
DISABLED_EMOJI = "❌"
SECTION_EMOJI = "🗂️"
BACK_ARROW = "◀️"
NEXT_ARROW = "▶️"
SAVED_EMOJI = "💾"
WARNING_EMOJI = "⚠️"

# -----------------------------------------------------------------------------
# DATABASE: sqlite helper for per-guild configs
# -----------------------------------------------------------------------------
class ConfigDB:
    """
    SQLite-backed simple config store.
    Schema:
      guild_configs: guild_id -> json blob with
        - sections: {section_name: enabled_bool}
        - commands: {command_full_name: enabled_bool}
    """

    def __init__(self, db_path: str = "guild_configs.db"):
        self.db_path = db_path
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._init_db()
        self._lock = asyncio.Lock()

    def _init_db(self):
        cur = self._conn.cursor()
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS guild_configs (
                guild_id INTEGER PRIMARY KEY,
                data TEXT NOT NULL
            )
            """
        )
        self._conn.commit()

    async def get_guild_config(self, guild_id: int) -> Dict[str, Any]:
        """
        Return dict with keys 'sections' and 'commands'.
        """
        async with self._lock:
            cur = self._conn.cursor()
            cur.execute("SELECT data FROM guild_configs WHERE guild_id = ?", (guild_id,))
            row = cur.fetchone()
            if row is None:
                default = {"sections": {}, "commands": {}}
                await self._set_guild_config(guild_id, default)
                return default
            else:
                return json.loads(row["data"])

    async def _set_guild_config(self, guild_id: int, data: Dict[str, Any]):
        async with self._lock:
            cur = self._conn.cursor()
            j = json.dumps(data)
            cur.execute(
                "INSERT INTO guild_configs(guild_id, data) VALUES(?, ?) ON CONFLICT(guild_id) DO UPDATE SET data = excluded.data",
                (guild_id, j),
            )
            self._conn.commit()

    async def set_section_state(self, guild_id: int, section_name: str, enabled: bool):
        cfg = await self.get_guild_config(guild_id)
        cfg.setdefault("sections", {})[section_name] = bool(enabled)
        await self._set_guild_config(guild_id, cfg)

    async def set_command_state(self, guild_id: int, command_name: str, enabled: bool):
        cfg = await self.get_guild_config(guild_id)
        cfg.setdefault("commands", {})[command_name] = bool(enabled)
        await self._set_guild_config(guild_id, cfg)

    async def reset_guild(self, guild_id: int):
        default = {"sections": {}, "commands": {}}
        await self._set_guild_config(guild_id, default)

    async def list_disabled_commands(self, guild_id: int) -> Set[str]:
        cfg = await self.get_guild_config(guild_id)
        commands = cfg.get("commands", {})
        disabled = {k for k, v in commands.items() if not v}
        sections = cfg.get("sections", {})
        # note: commands inside disabled sections should also be considered disabled
        return disabled, sections

# -----------------------------------------------------------------------------
# GLOBAL REGISTRY: keep a registry of commands and section metadata
# -----------------------------------------------------------------------------
class CommandRegistry:
    """
    Holds metadata for app commands (registered with @command_meta decorator).
    The Dashboard uses this to build the UI and to (re)register guild-specific commands.
    """

    def __init__(self):
        # full_command_name -> metadata
        # metadata: {
        #   "command": app_commands.Command,
        #   "callback": callable,
        #   "section": str,
        #   "name": str,
        #   "description": str,
        #   "registered_globally": bool,
        # }
        self._commands: Dict[str, Dict[str, Any]] = {}
        # Keep sections order
        self._sections: List[str] = []

    def register(self, full_name: str, command_obj: app_commands.Command, *, section: str, name: str):
        meta = {
            "command": command_obj,
            "section": section,
            "name": name,
            "description": getattr(command_obj, "description", ""),
        }
        self._commands[full_name] = meta
        if section not in self._sections:
            self._sections.append(section)

    def get_sections(self) -> List[str]:
        return list(self._sections)

    def get_commands_in_section(self, section: str) -> List[Tuple[str, Dict[str, Any]]]:
        out = []
        for fullname, meta in self._commands.items():
            if meta["section"] == section:
                out.append((fullname, meta))
        out.sort(key=lambda x: x[0])
        return out

    def get_all_commands(self) -> List[Tuple[str, Dict[str, Any]]]:
        return sorted(self._commands.items(), key=lambda x: x[0])

    def get_command_meta(self, fullname: str) -> Optional[Dict[str, Any]]:
        return self._commands.get(fullname)

    def get_fullname(self, command_obj: app_commands.Command) -> Optional[str]:
        # Try to find the fullname by matching object identity
        for fullname, meta in self._commands.items():
            if meta["command"] is command_obj:
                return fullname
        return None

# create a global registry instance
COMMAND_REGISTRY = CommandRegistry()

# -----------------------------------------------------------------------------
# DECORATOR: command_meta used by other cogs to register commands with metadata
# -----------------------------------------------------------------------------
def command_meta(section: str, name: Optional[str] = None):
    """
    Decorator for app_commands.Command-like functions to attach metadata.
    Usage:
        @app_commands.command(name="foo", description="...")
        @command_meta(section="Moderation", name="Ban")
        async def foo(interaction: discord.Interaction):
            ...
    The decorator will register the command object in COMMAND_REGISTRY at Cog setup time via
    the DashboardCog.on_ready hook (we try to discover existing commands).
    """
    def decorator(func_or_cmd):
        # If decorating an app_commands.Command object (when defined as @app_commands.command)
        # the obj is typically a function wrapped. We'll add attributes to the function so
        # that the DashboardCog can discover metadata.
        setattr(func_or_cmd, "__dashboard_section__", section)
        if name:
            setattr(func_or_cmd, "__dashboard_name__", name)
        else:
            setattr(func_or_cmd, "__dashboard_name__", getattr(func_or_cmd, "__name__", ""))
        return func_or_cmd
    return decorator

# -----------------------------------------------------------------------------
# HELPER: app command enabled check factory
# -----------------------------------------------------------------------------
def app_command_enabled_check():
    async def predicate(interaction: discord.Interaction) -> bool:
        bot = interaction.client
        db: ConfigDB = getattr(bot, "_dashboard_db", None)
        if db is None:
            # if no db present, allow by default
            return True
        guild = interaction.guild
        if guild is None:
            # bucket: DMs -> allow
            return True
        # Determine the command fullname in registry
        cmd = interaction.command
        fullname = None
        if cmd is not None:
            # Try to find registry fullname
            fullname = COMMAND_REGISTRY.get_fullname(cmd)
        # check the DB
        cfg = await db.get_guild_config(guild.id)
        # Section-level disabled?
        if fullname:
            meta = COMMAND_REGISTRY.get_command_meta(fullname)
            if meta:
                section = meta["section"]
                if not cfg.get("sections", {}).get(section, True):
                    # disabled by section
                    return False
        # Command-level disabled?
        if fullname:
            cmd_cfg = cfg.get("commands", {}).get(fullname, True)
            return bool(cmd_cfg)
        # default allow
        return True
    return app_commands.check(predicate)

# -----------------------------------------------------------------------------
# UI COMPONENTS
# -----------------------------------------------------------------------------
class ConfirmModal(ui.Modal, title="Confirm Action"):
    """
    Simple confirm modal with reason input (optional)
    """
    reason = ui.TextInput(label="Optional reason", required=False, style=discord.TextStyle.long, max_length=300)

    def __init__(self, *, placeholder: str = "Optional reason why..."):
        super().__init__()
        self.reason.placeholder = placeholder
        self.value = None

    async def on_submit(self, interaction: discord.Interaction):
        self.value = self.reason.value
        await interaction.response.defer(ephemeral=True)

# Main dashboard view (paginated sections)
class DashboardView(ui.View):
    def __init__(self, bot: commands.Bot, guild: discord.Guild, db: ConfigDB, *, timeout: int = 180):
        super().__init__(timeout=timeout)
        self.bot = bot
        self.guild = guild
        self.db = db
        self.current_section_index = 0
        self.sections = COMMAND_REGISTRY.get_sections()
        if not self.sections:
            self.sections = ["General"]
        # add persistent select for sections (updated in populate)
        self.section_select = ui.Select(placeholder="Choose section...", min_values=1, max_values=1, options=[])
        self.section_select.callback = self.section_select_callback
        self.add_item(self.section_select)
        # buttons
        self.back_button = ui.Button(emoji=BACK_ARROW, style=discord.ButtonStyle.blurple)
        self.back_button.callback = self.go_back
        self.add_item(self.back_button)
        self.next_button = ui.Button(emoji=NEXT_ARROW, style=discord.ButtonStyle.blurple)
        self.next_button.callback = self.go_next
        self.add_item(self.next_button)
        self.reset_button = ui.Button(label="Reset Guild Config", emoji=WARNING_EMOJI, style=discord.ButtonStyle.danger)
        self.reset_button.callback = self.reset_guild
        self.add_item(self.reset_button)
        # filler area for commands toggle container (we'll manage it in the message)
        # The commands list will be represented with ephemeral updates to the message embed and dynamic child buttons/selects.
        self.command_buttons: Dict[str, ui.Button] = {}  # command_fullname -> button
        # load initial options
        self.populate_section_options()

    def populate_section_options(self):
        options = []
        for idx, sec in enumerate(self.sections):
            options.append(discord.SelectOption(label=sec, description=f"Section {idx+1}", emoji=SECTION_EMOJI))
        self.section_select.options = options
        # set current index safe
        self.current_section_index = min(max(self.current_section_index, 0), len(self.sections)-1)
        self.section_select.default_values = [self.sections[self.current_section_index]]

    async def update_message(self, interaction: discord.Interaction):
        """
        Build embed and buttons for the current section, then edit the original message.
        """
        section = self.sections[self.current_section_index]
        cfg = await self.db.get_guild_config(self.guild.id)
        section_enabled = cfg.get("sections", {}).get(section, True)
        commands = COMMAND_REGISTRY.get_commands_in_section(section)

        # build embed
        embed = discord.Embed(
            title=f"{BADGE_EMOJI} Dashboard — {section}",
            description=f"Toggle **sections** and **individual commands** for this guild.",
            color=PALETTE["midnight_blue"],
        )
        embed.set_footer(text="Dark Dashboard • Use the toggles below • Changes sync per guild")
        embed.add_field(name="Section state", value=(ENABLED_EMOJI if section_enabled else DISABLED_EMOJI), inline=True)
        if not commands:
            embed.add_field(name="No commands", value="This section has no registered commands.", inline=False)
        else:
            # list commands with states
            lines = []
            for fullname, meta in commands:
                cmd_state = cfg.get("commands", {}).get(fullname, True)
                # If section is disabled, consider command disabled in display
                effective_state = cmd_state and section_enabled
                emoji = ENABLED_EMOJI if effective_state else DISABLED_EMOJI
                lines.append(f"{emoji} **{meta['name']}** — `{fullname}` — {meta.get('description','')}")
            embed.add_field(name="Commands", value="\n".join(lines[:20]), inline=False)
            if len(lines) > 20:
                embed.add_field(name="More...", value=f"{len(lines)-20} more commands hidden", inline=False)
        new_view = DashboardView._clone_static_controls(self, for_guild=self.guild)
        # Add per-command toggle buttons
        for fullname, meta in commands:
            cmd_state = cfg.get("commands", {}).get(fullname, True)
            effective_state = cmd_state and section_enabled
            label = f"{meta['name']}"
            style = discord.ButtonStyle.success if effective_state else discord.ButtonStyle.secondary
            emoji = ENABLED_EMOJI if effective_state else DISABLED_EMOJI
            btn = ui.Button(label=label, emoji=emoji, style=style, custom_id=f"toggle_cmd::{fullname}")
            # bind callback
            async def make_callback(f):
                async def callback(i: discord.Interaction):
                    # toggle the command
                    current_cfg = await self.db.get_guild_config(self.guild.id)
                    cur_val = current_cfg.get("commands", {}).get(f, True)
                    new_val = not cur_val
                    await self.db.set_command_state(self.guild.id, f, new_val)
                    # Attempt to sync guild commands to hide/show (best-effort)
                    await attempt_sync_for_guild(self.bot, self.guild)
                    await i.response.defer(ephemeral=True)
                    await self.update_message(i)
                return callback
            btn.callback = await make_callback(fullname)
            new_view.add_item(btn)

        # replace message
        try:
            await interaction.followup.edit_message(interaction.message.id, embed=embed, view=new_view)
        except Exception:
            # fallback to simple edit if followup fails (depends on how the message was created)
            try:
                await interaction.edit_original_response(embed=embed, view=new_view)
            except Exception:
                # last resort: send a fresh message
                await interaction.channel.send(embed=embed, view=new_view)

    @staticmethod
    def _clone_static_controls(old_view: "DashboardView", *, for_guild: discord.Guild) -> ui.View:
        """
        Make a copy of static controls (section select, next/back/reset) preserving callbacks.
        This avoids carrying old dynamic buttons.
        """
        new_view = ui.View(timeout=old_view.timeout)
        # section select
        section_select = ui.Select(placeholder="Choose section...", min_values=1, max_values=1, options=[])
        section_select.callback = old_view.section_select_callback
        new_view.add_item(section_select)
        # copy options
        section_select.options = old_view.section_select.options
        section_select.default_values = old_view.section_select.default_values
        # back button
        back_button = ui.Button(emoji=BACK_ARROW, style=discord.ButtonStyle.blurple)
        back_button.callback = old_view.go_back
        new_view.add_item(back_button)
        # next button
        next_button = ui.Button(emoji=NEXT_ARROW, style=discord.ButtonStyle.blurple)
        next_button.callback = old_view.go_next
        new_view.add_item(next_button)
        # reset button
        reset_button = ui.Button(label="Reset Guild Config", emoji=WARNING_EMOJI, style=discord.ButtonStyle.danger)
        reset_button.callback = old_view.reset_guild
        new_view.add_item(reset_button)
        return new_view

    async def section_select_callback(self, interaction: discord.Interaction):
        selected = self.section_select.values[0]
        if selected in self.sections:
            self.current_section_index = self.sections.index(selected)
        await interaction.response.defer(ephemeral=True)
        await self.update_message(interaction)

    async def go_back(self, interaction: discord.Interaction):
        self.current_section_index = (self.current_section_index - 1) % len(self.sections)
        self.section_select.default_values = [self.sections[self.current_section_index]]
        await interaction.response.defer(ephemeral=True)
        await self.update_message(interaction)

    async def go_next(self, interaction: discord.Interaction):
        self.current_section_index = (self.current_section_index + 1) % len(self.sections)
        self.section_select.default_values = [self.sections[self.current_section_index]]
        await interaction.response.defer(ephemeral=True)
        await self.update_message(interaction)

    async def reset_guild(self, interaction: discord.Interaction):
        # request confirmation
        modal = ConfirmModal(placeholder="Type a reason (optional)...")
        await interaction.response.send_modal(modal)
        await modal.wait()
        # If user submitted, perform reset
        await self.db.reset_guild(self.guild.id)
        # Attempt to sync guild commands after reset
        await attempt_sync_for_guild(self.bot, self.guild)
        # update UI
        await interaction.followup.send(content=f"{SAVED_EMOJI} Reset guild configuration.", ephemeral=True)
        await self.update_message(interaction)

# -----------------------------------------------------------------------------
# UTILITY: sync guild commands (best-effort)
# -----------------------------------------------------------------------------
async def attempt_sync_for_guild(bot: commands.Bot, guild: discord.Guild):
    """
    Best-effort attempt to make disabled commands hidden in the guild by re-syncing a
    custom subset of app commands to the specific guild. This function:
      - Builds a list of app_commands.Command objects that are enabled per the DB for the guild
      - Clears guild-specific commands and adds the enabled ones, then syncs.
    Note: Discord caches command registrations; propagation may take a few seconds.
    """
    db: ConfigDB = getattr(bot, "_dashboard_db", None)
    if db is None:
        return
    try:
        cfg = await db.get_guild_config(guild.id)
        enabled_commands = []
        # For each registered command in COMMAND_REGISTRY, include it only if
        # command-level true and section-level true.
        for fullname, meta in COMMAND_REGISTRY.get_all_commands():
            section = meta["section"]
            cmd_enabled = cfg.get("commands", {}).get(fullname, True)
            section_enabled = cfg.get("sections", {}).get(section, True)
            if cmd_enabled and section_enabled:
                # the stored meta['command'] is an app_commands.Command object
                cmd_obj = meta["command"]
                enabled_commands.append(cmd_obj)
        try:
            bot.tree.clear_commands(guild=guild)
        except Exception:
            logger.debug("clear_commands(guild) unsupported or failed - proceeding anyway")
        # Add commands
        for cmd in enabled_commands:
            try:
                # If command is a copying of a global command object, adding may raise. Handle gracefully.
                bot.tree.add_command(cmd, guild=guild)
            except Exception as e:
                logger.debug(f"Failed to add command {cmd} to guild {guild.id}: {e}")
        try:
            await bot.tree.sync(guild=guild)
            logger.debug(f"Synced {len(enabled_commands)} commands for guild {guild.id}")
        except Exception as e:
            logger.warning(f"Sync failed for guild {guild.id}: {e}")
    except Exception as exc:
        logger.exception("Error while attempting to sync guild commands: %s", exc)

# -----------------------------------------------------------------------------
# DASHBOARD COG
# -----------------------------------------------------------------------------
class DashboardCog(commands.Cog):
    """
    A large, featureful cog that provides:
      - /dashboard slash command to open an interactive dashboard (UI) for server admins
      - utilities to register command metadata
      - on_ready syncing and per-guild updates
      - global app command check enforcement via 'app_command_enabled_check'
    """
    def __init__(self, bot: commands.Bot, *, db_path: str = "guild_configs.db"):
        self.bot = bot
        self.db = ConfigDB(db_path)
        # expose db to bot for decorator-created checks
        setattr(bot, "_dashboard_db", self.db)
        # attach this cog's tree commands to a namespace
        self.tree = bot.tree  # convenience
        # internal caches
        self._ready = False
        self._sync_lock = asyncio.Lock()
        # styles
        self.palette = PALETTE
        # Register the /dashboard command as a guild/global app command
        self.bot.loop.create_task(self._register_dashboard_command())
        # schedule periodic resync (optional)
        self.bot.loop.create_task(self._periodic_resync())

    async def _register_dashboard_command(self):
        """
        Adds the /dashboard command to the global tree. The actual command handlers are in this class.
        """
        # Wait until bot is ready
        await self.bot.wait_until_ready()
        # Define the app command here (so the function has access to self)
        @app_commands.command(name="dashboard", description="Open the server dashboard to configure this bot")
        async def _dashboard(interaction: discord.Interaction):
            # only allow users with Manage Guild or Manage Roles (owner can also use)
            if not interaction.guild:
                await interaction.response.send_message("This command only works in servers.", ephemeral=True)
                return
            # permission check: manage_guild or manage_roles or administrator or owner
            me = self.bot
            perm = interaction.user.guild_permissions
            is_admin = perm.manage_guild or perm.administrator or perm.manage_roles
            if not is_admin and interaction.user.id != getattr(self.bot, "owner_id", None):
                await interaction.response.send_message("You need Manage Server (or similar) permissions to access the dashboard.", ephemeral=True)
                return
            await interaction.response.defer(ephemeral=False)
            view = DashboardView(self.bot, interaction.guild, self.db)
            # initial message with embed
            embed = discord.Embed(
                title=f"{BADGE_EMOJI} Server Dashboard",
                color=self.palette["velvet_purple"],
                description="Use the controls below to enable/disable sections and commands for this server."
            )
            embed.add_field(name="Guild", value=f"{interaction.guild.name} (`{interaction.guild.id}`)")
            embed.set_footer(text="Changes are stored per-guild and sync to the command list (best-effort).")
            # send followup or initial response
            try:
                await interaction.followup.send(embed=embed, view=view)
                # update initial message contents to the first section
                await view.update_message(interaction)
            except Exception:
                # fallback to responding with editable original response
                try:
                    await interaction.edit_original_response(embed=embed, view=view)
                    await view.update_message(interaction)
                except Exception:
                    await interaction.channel.send(embed=embed, view=view)

        # attach to tree if not present
        try:
            self.bot.tree.add_command(_dashboard)
            try:
                await self.bot.tree.sync()
            except Exception:
                # global sync failed, try just for guilds later
                logger.debug("Initial dashboard sync may have failed; it will be attempted later per guild.")
        except Exception:
            # Already present or failed. ignore
            pass

    # Cog lifecycle
    @commands.Cog.listener()
    async def on_ready(self):
        if self._ready:
            return
        # Discover app command metadata across loaded commands and cogs
        await self._discover_commands_meta()
        # initial per-guild sync
        for guild in list(self.bot.guilds):
            # schedule best-effort sync
            self.bot.loop.create_task(attempt_sync_for_guild(self.bot, guild))
        self._ready = True
        logger.info("DashboardCog ready. Registered %d command metas across %d sections.", len(COMMAND_REGISTRY.get_all_commands()), len(COMMAND_REGISTRY.get_sections()))

    @commands.Cog.listener()
    async def on_guild_join(self, guild: discord.Guild):
        # new guild joined; ensure the DB has a default record
        await self.db.get_guild_config(guild.id)
        await attempt_sync_for_guild(self.bot, guild)

    async def _discover_commands_meta(self):
        # scan bot.tree commands
        def try_register(cmd: app_commands.Command):
            # try to find a function with dashboard attributes
            target = None
            # command has callback property (Command.callback) -> a function or coroutine
            callback = getattr(cmd, "callback", None)
            if callback is not None:
                # check attributes on callback
                section = getattr(callback, "__dashboard_section__", None)
                name = getattr(callback, "__dashboard_name__", None)
                if section is not None:
                    # register with registry using command.qualified_name as unique key
                    fullname = f"{cmd.qualified_name}"
                    COMMAND_REGISTRY.register(fullname, cmd, section=section, name=(name or cmd.name))
                    return True
            # fallback: if there are subcommands in a group, iterate them
            return False

        for c in list(self.bot.tree.commands):
            # For groups and commands
            try:
                # for top-level commands
                try_register(c)
                # for groups
                if isinstance(c, app_commands.Group):
                    for sub in c.commands:
                        try_register(sub)
            except Exception:
                logger.debug("Error attempting to register command meta for command %s", getattr(c, "name", "<unknown>"), exc_info=True)

        # Also check cogs for functions decorated with @command_meta that might not be added to tree yet
        # We try to find global functions with the attribute as fallback.
        # NOTE: This is not exhaustive but catches many common patterns.

        # Nothing to return; registry mutated

    async def _periodic_resync(self):
        """
        Background task to periodically resync guild commands (best-effort). This helps in case
        a toggle changed but the sync wasn't processed by Discord the first time.
        """
        await self.bot.wait_until_ready()
        while True:
            try:
                # iterate guilds and attempt sync
                for guild in list(self.bot.guilds):
                    await attempt_sync_for_guild(self.bot, guild)
                await asyncio.sleep(300)  # every 5 minutes
            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("Periodic resync encountered an error.")
                await asyncio.sleep(60)

    # Example of a convenience command to mark a section default on/off (exposed to owner/admin)
    @app_commands.command(name="dashboard-section-toggle", description="Toggle a section on/off for this guild (admin only).")
    async def _section_toggle(self, interaction: discord.Interaction, section: str, enabled: bool):
        if not interaction.guild:
            await interaction.response.send_message("This command must be used in a guild.", ephemeral=True)
            return
        perm = interaction.user.guild_permissions
        if not (perm.manage_guild or perm.administrator or interaction.user.id == getattr(self.bot, "owner_id", None)):
            await interaction.response.send_message("You need Manage Server permissions to use this.", ephemeral=True)
            return
        # set section state
        await self.db.set_section_state(interaction.guild.id, section, enabled)
        # sync commands for the guild (best-effort)
        await attempt_sync_for_guild(self.bot, interaction.guild)
        await interaction.response.send_message(f"{SAVED_EMOJI} Section `{section}` set to {'enabled' if enabled else 'disabled'}.", ephemeral=True)

def register_command_for_dashboard(cmd: app_commands.Command, *, section: str, name: Optional[str] = None):
    """
    Use this function when you programmatically create app_commands.Command objects.
    It registers the command in the COMMAND_REGISTRY so the dashboard can show it.
    """
    fullname = getattr(cmd, "qualified_name", getattr(cmd, "name", None))
    if fullname is None:
        fullname = cmd.name
    COMMAND_REGISTRY.register(fullname, cmd, section=section, name=(name or cmd.name))

# -----------------------------------------------------------------------------
# EXAMPLE: put some sample commands into registry for demonstration.
# This is optional; remove or replace with your real commands.
# -----------------------------------------------------------------------------
# NOTE: The following example commands are created only to illustrate how
# the registry & check should be used. In a real bot, your cogs define
# the real commands and you decorate them with @command_meta + @app_commands.check.
async def _example_command_callback(interaction: discord.Interaction):
    await interaction.response.send_message("This is an example command.")

# Create a dummy command object for example (not strictly necessary)
example_cmd = app_commands.Command(
    name="example",
    description="Example command (demo)",
    callback=_example_command_callback,
)

# Register in registry under section "General"
COMMAND_REGISTRY.register("example", example_cmd, section="General", name="Example (demo)")

# -----------------------------------------------------------------------------
# Loader function for cogs
# -----------------------------------------------------------------------------
async def setup(bot: commands.Bot):
    """
    This is the standardized cog loader for discord.py; use `await bot.add_cog(DashboardCog(bot))` or allow
    the bot.load_extension mechanism to call setup for you.
    """
    cog = DashboardCog(bot)
    await bot.add_cog(cog)
    logger.info("DashboardCog loaded.")
                                         
# -----------------------------------------------------------------------------
# End of file
# -----------------------------------------------------------------------------
