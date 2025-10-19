# mute.py
"""
Features:
- /setmuterole role:<role>         -> set the role used to mute members (persisted per guild)
- /mute user:<user> duration:<opt> reason:<opt> channels:<opt multi-select>
    -> Mutes a member by assigning the mute role (preferred) or by applying channel overwrites when channels provided.
    -> Duration supports "10s", "15m", "1h", "2d" formats. If omitted, mute is permanent until manually unmuted.
- /unmute user:<user> reason:<opt> -> Unmute and cancel scheduled unmute.
- Multi-guild persistent configs stored in bot_meta.db (tables: mute_roles, mutes, mute_logs)
- Schedules unmute tasks that persist across restarts (on cog load reads DB)
- Permission checks and safe guards (can't mute admins/owners/bots in certain cases)
- Interactive confirms and progress UIs
- Logging of actions to DB
"""

import discord
from discord.ext import commands, tasks
from discord import app_commands
from datetime import datetime, timezone, timedelta
import asyncio
import sqlite3
import re
import traceback
from typing import Optional, List, Dict, Tuple

# ---------------------------
# Palette & embed helper (Dark Luxury)
# ---------------------------
PALETTE = {
    "deep_black": discord.Color.from_rgb(18, 18, 20),
    "midnight_blue": discord.Color.from_rgb(28, 30, 45),
    "royal_gold": discord.Color.from_rgb(212, 175, 55),
    "velvet_purple": discord.Color.from_rgb(85, 45, 110),
    "soft_accent": discord.Color.from_rgb(110, 80, 150)
}


def create_darlux_embed(title: Optional[str] = None, description: Optional[str] = None, accent: str = "royal_gold"):
    emb = discord.Embed(
        title=title,
        description=description,
        color=PALETTE.get(accent, PALETTE["royal_gold"]),
        timestamp=datetime.utcnow()
    )
    return emb


DB_PATH = "bot_meta.db"


# ---------------------------
# Database initialization & helpers
# ---------------------------
def init_db(path: str = DB_PATH):
    conn = sqlite3.connect(path)
    cur = conn.cursor()
    # table to store per-guild mute role
    cur.execute("""
    CREATE TABLE IF NOT EXISTS mute_roles (
        guild_id INTEGER PRIMARY KEY,
        role_id INTEGER,
        set_by INTEGER,
        set_at TEXT
    )
    """)
    # table to store scheduled mutes/unmutes (active mutes)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS mutes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        guild_id INTEGER,
        user_id INTEGER,
        role_id INTEGER,
        muted_by INTEGER,
        reason TEXT,
        muted_at TEXT,
        unmute_at TEXT,  -- nullable; ISO timestamp for scheduled unmute
        channels TEXT     -- optional JSON-like string of channel ids overwrote (for channel-specific mutes)
    )
    """)
    # logs
    cur.execute("""
    CREATE TABLE IF NOT EXISTS mute_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        guild_id INTEGER,
        guild_name TEXT,
        user_id INTEGER,
        user_name TEXT,
        action TEXT,
        performed_by INTEGER,
        reason TEXT,
        details TEXT,
        invoked_at TEXT
    )
    """)
    conn.commit()
    conn.close()


def set_mute_role_db(guild_id: int, role_id: int, setter_id: int, path: str = DB_PATH):
    try:
        conn = sqlite3.connect(path)
        cur = conn.cursor()
        cur.execute("REPLACE INTO mute_roles (guild_id, role_id, set_by, set_at) VALUES (?, ?, ?, ?)",
                    (guild_id, role_id, setter_id, datetime.utcnow().isoformat()))
        conn.commit()
        conn.close()
    except Exception:
        pass


def get_mute_role_db(guild_id: int, path: str = DB_PATH) -> Optional[int]:
    try:
        conn = sqlite3.connect(path)
        cur = conn.cursor()
        cur.execute("SELECT role_id FROM mute_roles WHERE guild_id = ?", (guild_id,))
        row = cur.fetchone()
        conn.close()
        if row:
            return row[0]
    except Exception:
        pass
    return None


def add_mute_db(guild_id: int, user_id: int, role_id: int, muted_by: int, reason: Optional[str], muted_at: datetime, unmute_at: Optional[datetime], channels_serialized: Optional[str] = None, path: str = DB_PATH):
    try:
        conn = sqlite3.connect(path)
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO mutes (guild_id, user_id, role_id, muted_by, reason, muted_at, unmute_at, channels) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (guild_id, user_id, role_id, muted_by, reason, muted_at.isoformat(), unmute_at.isoformat() if unmute_at else None, channels_serialized)
        )
        conn.commit()
        conn.close()
    except Exception:
        pass


def remove_mute_db(guild_id: int, user_id: int, path: str = DB_PATH):
    try:
        conn = sqlite3.connect(path)
        cur = conn.cursor()
        cur.execute("DELETE FROM mutes WHERE guild_id = ? AND user_id = ?", (guild_id, user_id))
        conn.commit()
        conn.close()
    except Exception:
        pass


def fetch_all_pending_mutes(path: str = DB_PATH) -> List[Tuple]:
    try:
        conn = sqlite3.connect(path)
        cur = conn.cursor()
        cur.execute("SELECT id, guild_id, user_id, role_id, muted_by, reason, muted_at, unmute_at, channels FROM mutes WHERE unmute_at IS NOT NULL")
        rows = cur.fetchall()
        conn.close()
        return rows
    except Exception:
        return []


def fetch_active_mute(guild_id: int, user_id: int, path: str = DB_PATH) -> Optional[Tuple]:
    try:
        conn = sqlite3.connect(path)
        cur = conn.cursor()
        cur.execute("SELECT id, role_id, muted_at, unmute_at, channels FROM mutes WHERE guild_id = ? AND user_id = ?", (guild_id, user_id))
        row = cur.fetchone()
        conn.close()
        return row
    except Exception:
        return None


def log_mute_action(guild: Optional[discord.Guild], user: discord.User, action: str, performed_by: discord.User, reason: Optional[str], details: Optional[str] = None, path: str = DB_PATH):
    try:
        conn = sqlite3.connect(path)
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO mute_logs (guild_id, guild_name, user_id, user_name, action, performed_by, reason, details, invoked_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (guild.id if guild else None, guild.name if guild else None, user.id if user else None, str(user) if user else None, action, performed_by.id if performed_by else None, reason, details, datetime.utcnow().isoformat())
        )
        conn.commit()
        conn.close()
    except Exception:
        pass


# ---------------------------
# Utilities: parse duration strings like "10m", "1h", "2d"
# ---------------------------
_DURATION_RE = re.compile(r"^\s*(\d+)\s*([smhdw]?)\s*$", re.IGNORECASE)


def parse_duration(duration_str: str) -> Optional[timedelta]:
    """
    Parse simple duration strings:
      - "30s" seconds
      - "10m" minutes
      - "2h" hours
      - "3d" days
      - "1w" weeks
      - "15" (defaults to seconds)
    Returns timedelta or None if invalid.
    """
    if not duration_str:
        return None
    m = _DURATION_RE.match(duration_str)
    if not m:
        return None
    qty = int(m.group(1))
    unit = m.group(2).lower() if m.group(2) else "s"
    if unit == "s":
        return timedelta(seconds=qty)
    if unit == "m":
        return timedelta(minutes=qty)
    if unit == "h":
        return timedelta(hours=qty)
    if unit == "d":
        return timedelta(days=qty)
    if unit == "w":
        return timedelta(weeks=qty)
    return None


def pretty_timedelta(td: timedelta) -> str:
    """Return a human-friendly string for a timedelta."""
    total_seconds = int(td.total_seconds())
    if total_seconds < 60:
        return f"{total_seconds}s"
    parts = []
    weeks, rem = divmod(total_seconds, 604800)
    days, rem = divmod(rem, 86400)
    hours, rem = divmod(rem, 3600)
    minutes, seconds = divmod(rem, 60)
    if weeks:
        parts.append(f"{weeks}w")
    if days:
        parts.append(f"{days}d")
    if hours:
        parts.append(f"{hours}h")
    if minutes:
        parts.append(f"{minutes}m")
    if seconds and not parts:
        parts.append(f"{seconds}s")
    return " ".join(parts)


# ---------------------------
# Permission checks
# ---------------------------
def invoker_can_mute(interaction: discord.Interaction) -> Tuple[bool, str]:
    """
    Basic guard: require Moderate Members (timeout), Manage Roles, or Administrator.
    We accept Manage Roles as well because assigning role is used for mutes.
    """
    if not isinstance(interaction.user, discord.Member):
        return False, "This command must be used in a server."
    perms = interaction.user.guild_permissions
    if perms.moderate_members or perms.manage_roles or perms.administrator:
        return True, ""
    return False, "You need Moderate Members, Manage Roles, or Administrator permission to perform mutes."


def bot_can_manage_roles(guild: discord.Guild) -> Tuple[bool, str]:
    """
    Check if the bot has Manage Roles permission in the guild.
    """
    bot_member = guild.me
    if not bot_member:
        return False, "Bot member not found in guild."
    perms = bot_member.guild_permissions
    if not perms.manage_roles:
        return False, "Bot requires Manage Roles permission to assign/unassign mute role."
    return True, ""


def role_is_managed_or_higher_than_bot(guild: discord.Guild, role: discord.Role) -> Tuple[bool, str]:
    """
    Ensure the bot's top role is higher than the target mute role.
    """
    bot_member = guild.me
    if not bot_member:
        return False, "Bot is not available in guild."
    try:
        if bot_member.top_role <= role:
            return False, "Bot's top role must be above the mute role to manage it."
    except Exception:
        return False, "Could not compare role hierarchy."
    return True, ""


def safe_to_mute(invoker: discord.Member, target: discord.Member, bot_member: discord.Member) -> Tuple[bool, str]:
    """
    Prevent muting server owner, administrators, or members with higher roles than the bot or invoker.
    """
    # Prevent muting the owner
    try:
        if target == target.guild.owner:
            return False, "Cannot mute the server owner."
    except Exception:
        pass
    # Prevent muting administrators
    if target.guild_permissions.administrator:
        return False, "Cannot mute a server administrator."
    # role hierarchy: invoker must be higher than target unless invoker is guild owner
    if invoker != invoker.guild.owner:
        try:
            if invoker.top_role <= target.top_role and invoker != target.guild.owner:
                return False, "You cannot mute a member with an equal or higher role."
        except Exception:
            pass
    # bot must be able to affect the target
    try:
        if bot_member.top_role <= target.top_role:
            return False, "I cannot mute this user because their top role is equal or higher than mine."
    except Exception:
        pass
    # don't mute bots (optional: allow bots to be muted)
    if target.bot:
        return False, "This command cannot mute bot accounts."
    return True, ""


# ---------------------------
# Views: Confirm & Progress
# ---------------------------
class ConfirmView(discord.ui.View):
    def __init__(self, author: discord.User, timeout: int = 45):
        super().__init__(timeout=timeout)
        self.author = author
        self.value: Optional[bool] = None

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author.id:
            await interaction.response.send_message("This confirmation is only for the command user.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Confirm", style=discord.ButtonStyle.danger)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.value = True
        await interaction.response.edit_message(content="Confirmed — proceeding...", view=None)
        self.stop()

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.value = False
        await interaction.response.edit_message(content="Cancelled — aborting.", view=None)
        self.stop()


class ProgressView(discord.ui.View):
    def __init__(self, timeout: int = 300):
        super().__init__(timeout=timeout)

    @discord.ui.button(label="❌ Close", style=discord.ButtonStyle.danger)
    async def close(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            await interaction.message.delete()
        except Exception:
            pass
        self.stop()


# ---------------------------
# The Cog
# ---------------------------
class MuteCog(commands.Cog):
    """Mute management cog (Dark Luxury edition)."""
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        init_db()
        # in-memory scheduled unmute tasks: (guild_id, user_id) -> asyncio.Task
        self._scheduled_unmutes: Dict[Tuple[int, int], asyncio.Task] = {}
        # internal batch delay for channel overwrites
        self._batch_delay = 0.12

    # ---------------------------
    # Startup: schedule pending unmutes found in DB
    # ---------------------------
    async def _load_and_schedule_pending_unmutes(self):
        # wait until bot ready
        await self.bot.wait_until_ready()
        rows = fetch_all_pending_mutes()
        for row in rows:
            try:
                mid, guild_id, user_id, role_id, muted_by, reason, muted_at_iso, unmute_at_iso, channels_ser = row
                if not unmute_at_iso:
                    continue
                unmute_at = datetime.fromisoformat(unmute_at_iso)
                # if unmute_at in the past, attempt immediate unmute
                if unmute_at <= datetime.utcnow().replace(tzinfo=timezone.utc):
                    # schedule immediate task to run shortly
                    asyncio.create_task(self._perform_scheduled_unmute(guild_id, user_id, reason="Scheduled unmute (missed)"))
                else:
                    # schedule for future
                    delay = (unmute_at - datetime.utcnow().replace(tzinfo=timezone.utc)).total_seconds()
                    task = asyncio.create_task(self._delayed_unmute(guild_id, user_id, delay))
                    self._scheduled_unmutes[(guild_id, user_id)] = task
            except Exception:
                # don't let a single bad row break startup scheduling
                traceback.print_exc()

    async def _delayed_unmute(self, guild_id: int, user_id: int, delay: float):
        try:
            await asyncio.sleep(delay)
            await self._perform_scheduled_unmute(guild_id, user_id, reason="Scheduled unmute")
        except asyncio.CancelledError:
            return
        except Exception:
            traceback.print_exc()

    async def _perform_scheduled_unmute(self, guild_id: int, user_id: int, reason: Optional[str] = None):
        guild = self.bot.get_guild(guild_id)
        if not guild:
            # cannot unmute if guild is unavailable
            remove_mute_db(guild_id, user_id)
            return
        member = guild.get_member(user_id) or await self._fetch_member_safe(guild, user_id)
        if not member:
            # if user not present, just remove DB record
            remove_mute_db(guild_id, user_id)
            return
        # try to retrieve stored mute record to know role/channels
        row = fetch_active_mute(guild_id, user_id)
        if row:
            _, role_id, muted_at_iso, unmute_at_iso, channels_ser = row
            # attempt unmute
            try:
                await self._unmute_member(member, performed_by=None, reason=reason or "Scheduled unmute", suppress_feedback=True, stored_role_id=role_id, stored_channels_serialized=channels_ser)
            except Exception:
                pass
        else:
            # nothing to do
            pass
        # cleanup in-memory scheduled map
        self._scheduled_unmutes.pop((guild_id, user_id), None)
        # ensure DB record removed
        remove_mute_db(guild_id, user_id)

    # ---------------------------
    # Safe fetch helpers
    # ---------------------------
    async def _fetch_member_safe(self, guild: discord.Guild, user_id: int) -> Optional[discord.Member]:
        try:
            return await guild.fetch_member(user_id)
        except Exception:
            return None

    async def _fetch_user_safe(self, user_id: int) -> Optional[discord.User]:
        try:
            return await self.bot.fetch_user(user_id)
        except Exception:
            return None

    # ---------------------------
    # Core role assignment & overwrite helpers
    # ---------------------------
    async def _assign_mute_role(self, guild: discord.Guild, member: discord.Member, mute_role: discord.Role) -> Tuple[bool, Optional[str]]:
        # Add role with reason
        try:
            await member.add_roles(mute_role, reason="Muted via bot action")
            return True, None
        except discord.Forbidden:
            return False, "Bot lacks permission to add roles to this member."
        except Exception as e:
            return False, f"Failed to add role: {e}"

    async def _remove_mute_role(self, guild: discord.Guild, member: discord.Member, mute_role: discord.Role) -> Tuple[bool, Optional[str]]:
        try:
            await member.remove_roles(mute_role, reason="Unmuted via bot action")
            return True, None
        except discord.Forbidden:
            return False, "Bot lacks permission to remove roles from this member."
        except Exception as e:
            return False, f"Failed to remove role: {e}"

    async def _apply_channel_overwrites(self, guild: discord.Guild, member: discord.Member, channels: 'List[discord.TextChannel]', lock: bool = True, reason: Optional[str] = None) -> Dict[int, Tuple[bool, str]]:
        """
        Apply overwrites to channels for @member (if lock=True, remove speak/send; if lock=False, remove overwrite).
        Returns dict mapping channel.id -> (success, message).
        """
        results = {}
        for ch in channels:
            try:
                if not isinstance(ch, (discord.TextChannel, discord.VoiceChannel, discord.Thread)):
                    results[ch.id] = (False, "Unsupported channel type")
                    continue
                # build member-specific overwrite: deny send_messages and add_reactions if locking
                if lock:
                    ow = discord.PermissionOverwrite(send_messages=False, add_reactions=False)
                else:
                    ow = discord.PermissionOverwrite(send_messages=None, add_reactions=None)
                await ch.set_permissions(member, overwrite=ow, reason=reason or "Mute/Unmute action")
                results[ch.id] = (True, "OK")
            except discord.Forbidden:
                results[ch.id] = (False, "Bot lacks permission to edit channel overwrites")
            except Exception as e:
                results[ch.id] = (False, f"Exception: {e}")
            await asyncio.sleep(self._batch_delay)
        return results

    # ---------------------------
    # High-level unmute helper (used for manual/unmute and scheduled)
    # ---------------------------
    async def _unmute_member(self, member: discord.Member, performed_by: Optional[discord.User], reason: Optional[str], suppress_feedback: bool = False, stored_role_id: Optional[int] = None, stored_channels_serialized: Optional[str] = None) -> Tuple[bool, str]:
        guild = member.guild
        # prefer to remove role if configured
        role_id = stored_role_id or get_mute_role_db(guild.id)
        mute_role = None
        if role_id:
            mute_role = guild.get_role(role_id)
        results = []
        details = []

        if mute_role and mute_role in member.roles:
            ok, msg = await self._remove_mute_role(guild, member, mute_role)
            results.append(ok)
            details.append(f"role:{msg or 'removed'}")
        # also try to remove member-specific overwrites if stored
        if stored_channels_serialized:
            try:
                channel_ids = [int(x) for x in stored_channels_serialized.split(",") if x]
                channels = [guild.get_channel(cid) for cid in channel_ids if guild.get_channel(cid)]
                overw_res = await self._apply_channel_overwrites(guild, member, channels, lock=False, reason=reason)
                for cid, (ok2, msg2) in overw_res.items():
                    details.append(f"ch{cid}:{'ok' if ok2 else msg2}")
            except Exception:
                pass

        # If neither role nor overwrites detected (or operation failed), we still consider the unmute attempted
        # remove DB record regardless
        remove_mute_db(guild.id, member.id)
        # log action
        try:
            performed_by_user = performed_by or self.bot.user
            log_mute_action(guild, member, "unmute", performed_by_user, reason, details=";".join(details) or None)
        except Exception:
            pass

        return True, ";".join(details)

    # ---------------------------
    # Slash: /setmuterole
    # ---------------------------
    @app_commands.command(name="setmuterole", description="Assign the role the bot uses to mute members in this guild.")
    @app_commands.describe(role="Role to assign as the mute role")
    async def app_setmuterole(self, interaction: discord.Interaction, role: discord.Role):
        await interaction.response.defer(thinking=True)
        # permission checks
        allow, msg = invoker_can_mute(interaction)
        if not allow:
            await interaction.followup.send(msg, ephemeral=True)
            return
        # bot permission
        ok, bmsg = bot_can_manage_roles(interaction.guild)
        if not ok:
            await interaction.followup.send(bmsg, ephemeral=True)
            return
        # role hierarchy check
        ok2, rmsg = role_is_managed_or_higher_than_bot(interaction.guild, role)
        if not ok2:
            await interaction.followup.send(rmsg, ephemeral=True)
            return
        # set role in DB
        set_mute_role_db(interaction.guild.id, role.id, interaction.user.id)
        emb = create_darlux_embed(title="🖤 Mute Role Set", description=f"{role.mention} has been set as the mute role for this guild.", accent="royal_gold")
        emb.set_footer(text=f"Requested by {interaction.user}", icon_url=interaction.user.display_avatar.url)
        await interaction.followup.send(embed=emb, ephemeral=False)
        log_mute_action(interaction.guild, interaction.user, "setmuterole", interaction.user, reason=f"Set to role {role.id}", details=None)

    # ---------------------------
    # Slash: /mute
    # ---------------------------
    @app_commands.command(name="mute", description="Mute a user. Optionally set a duration (e.g., 10m, 1h).")
    @app_commands.describe(user="User to mute", duration="Optional duration like 10m/1h/2d", reason="Optional reason", channels="Optional list of channels to apply channel-overwrites instead of role-based mute")
    async def app_mute(self, interaction: discord.Interaction, user: discord.User, duration: Optional[str] = None, reason: Optional[str] = None, channels: Optional[str] = None):
        """
        Mute a user. Two modes:
         - Role-based mute (recommended): assign the configured mute role.
         - Channel-specific mute: if `channels` provided, the bot will set member-specific overwrites in those channels.
        """
        await interaction.response.defer(thinking=True)
        if not interaction.guild:
            await interaction.followup.send("This command must be used in a server.", ephemeral=True)
            return
        # basic permission check
        allow, msg = invoker_can_mute(interaction)
        if not allow:
            await interaction.followup.send(msg, ephemeral=True)
            return
        guild = interaction.guild
        invoker = interaction.user
        # fetch member object
        member = guild.get_member(user.id) or await self._fetch_member_safe(guild, user.id)
        if not member:
            await interaction.followup.send("User not found in this guild.", ephemeral=True)
            return
        # don't allow muting self
        if member.id == invoker.id:
            await interaction.followup.send("You cannot mute yourself.", ephemeral=True)
            return
        # safety checks
        bot_member = guild.me
        safe, safe_msg = safe_to_mute(invoker, member, bot_member)
        if not safe:
            await interaction.followup.send(safe_msg, ephemeral=True)
            return
        # parse duration
        unmute_at = None
        if duration:
            td = parse_duration(duration)
            if not td:
                await interaction.followup.send("Invalid duration format. Use e.g., 10m, 1h, 2d, 30s.", ephemeral=True)
                return
            unmute_at = datetime.utcnow().replace(tzinfo=timezone.utc) + td

        # Determine mode: role-based if mute role configured and no channels provided
            configured_role_id = get_mute_role_db(guild.id)
            mute_role = guild.get_role(int(configured_role_id)) if configured_role_id else None
        channels_list = None
        if channels:
            # Accept a comma-separated string of channel mentions or IDs, then resolve
            parts = re.split(r"\s*,\s*", str(channels).strip())
            resolved = []
            for p in parts:
                m = re.search(r"(\d{17,19})", p)
                if m:
                    cid = int(m.group(1))
                    ch = guild.get_channel(cid)
                    if ch:
                        resolved.append(ch)
            channels_list = resolved if resolved else None
        else:
            # no role configured and no channels provided -> cannot proceed
            await interaction.followup.send("No mute role configured for this guild. Use /setmuterole or provide channels to mute.", ephemeral=True)
            return

        # Confirm final action (show summary)
        summary_lines = []
        if mute_role:
            summary_lines.append(f"Role-based mute: will add {mute_role.mention}")
        if channels:
            summary_lines.append(f"Channel-specific mutes on: {', '.join([c.mention for c in channels])}")
        if unmute_at:
            summary_lines.append(f"Duration: {pretty_timedelta(unmute_at - datetime.utcnow().replace(tzinfo=timezone.utc))}")
        else:
            summary_lines.append("Duration: Permanent (until manually unmuted)")
        summary = "\n".join(summary_lines)
        emb = create_darlux_embed(title="🖤 Confirm Mute", description=f"About to mute {member.mention}\n\n{summary}\n\nReason: {reason or 'No reason provided.'}", accent="midnight_blue")
        emb.set_footer(text=f"Requested by {interaction.user}", icon_url=interaction.user.display_avatar.url)
        confirm = ConfirmView(interaction.user, timeout=30)
        await interaction.followup.send(embed=emb, view=confirm, ephemeral=True)
        await confirm.wait()
        if confirm.value is not True:
            await interaction.followup.send("Mute cancelled.", ephemeral=True)
            return

        # Apply action: either role-based or channel-specific
        errors = []
        details = []
        channels_serialized = None
        if mute_role:
            ok, err = await self._assign_mute_role(guild, member, mute_role)
            if not ok:
                await interaction.followup.send(f"Failed to add mute role: {err}", ephemeral=True)
                log_mute_action(guild, member, "mute_failed", interaction.user, reason, details=err)
                return
            details.append(f"role:{mute_role.id}")
        if channels:
            # apply member-specific overwrites
            overw_res = await self._apply_channel_overwrites(guild, member, channels, lock=True, reason=reason)
            # serialize channel ids for DB
            channels_serialized = ",".join(str(c.id) for c in channels)
            for cid, (ok2, msg2) in overw_res.items():
                if not ok2:
                    errors.append(f"{cid}:{msg2}")
                else:
                    details.append(f"ch:{cid}")

        # schedule unmute if needed
        if unmute_at:
            # store in DB and schedule task
            add_mute_db(guild.id, member.id, mute_role.id if mute_role else (configured_role_id or None), interaction.user.id, reason, datetime.utcnow().replace(tzinfo=timezone.utc), unmute_at.replace(tzinfo=timezone.utc), channels_serialized)
            delay = (unmute_at - datetime.utcnow().replace(tzinfo=timezone.utc)).total_seconds()
            task = self.bot.loop.create_task(self._delayed_unmute(guild.id, member.id, delay))
            self._scheduled_unmutes[(guild.id, member.id)] = task
        else:
            # record as active mute with no scheduled unmute
            add_mute_db(guild.id, member.id, mute_role.id if mute_role else (configured_role_id or None), interaction.user.id, reason, datetime.utcnow().replace(tzinfo=timezone.utc), None, channels_serialized)

        # send feedback
        emb_ok = create_darlux_embed(title="🖤 Muted", description=f"{member.mention} has been muted.", accent="royal_gold")
        emb_ok.add_field(name="Reason", value=reason or "No reason provided", inline=True)
        if unmute_at:
            emb_ok.add_field(name="Unmute At (UTC)", value=unmute_at.isoformat(), inline=True)
            emb_ok.add_field(name="Time Remaining", value=pretty_timedelta(unmute_at - datetime.utcnow().replace(tzinfo=timezone.utc)), inline=True)
        emb_ok.set_footer(text=f"Requested by {interaction.user}", icon_url=interaction.user.display_avatar.url)
        await interaction.followup.send(embed=emb_ok, ephemeral=False)
        # log
        log_mute_action(guild, member, "mute", interaction.user, reason, details=";".join(details) if details else None)

    # ---------------------------
    # Slash: /unmute
    # ---------------------------
    @app_commands.command(name="unmute", description="Unmute a previously muted user.")
    @app_commands.describe(user="User to unmute", reason="Optional reason for audit log")
    async def app_unmute(self, interaction: discord.Interaction, user: discord.User, reason: Optional[str] = None):
        await interaction.response.defer(thinking=True)
        if not interaction.guild:
            await interaction.followup.send("This command must be used in a server.", ephemeral=True)
            return
        allow, msg = invoker_can_mute(interaction)
        if not allow:
            await interaction.followup.send(msg, ephemeral=True)
            return
        guild = interaction.guild
        member = guild.get_member(user.id) or await self._fetch_member_safe(guild, user.id)
        if not member:
            await interaction.followup.send("User not found in this guild.", ephemeral=True)
            # still remove DB entry if exists
            remove_mute_db(guild.id, user.id)
            return

        # confirm unmute
        emb = create_darlux_embed(title="🖤 Confirm Unmute", description=f"Are you sure you want to unmute {member.mention}?\n\nReason: {reason or 'No reason provided.'}", accent="velvet_purple")
        emb.set_footer(text=f"Requested by {interaction.user}", icon_url=interaction.user.display_avatar.url)
        confirm = ConfirmView(interaction.user, timeout=30)
        await interaction.followup.send(embed=emb, view=confirm, ephemeral=True)
        await confirm.wait()
        if confirm.value is not True:
            await interaction.followup.send("Unmute cancelled.", ephemeral=True)
            return

        # attempt to fetch stored mute to know what to remove
        row = fetch_active_mute(guild.id, member.id)
        stored_role_id = None
        stored_channels_ser = None
        if row:
            _, stored_role_id, muted_at_iso, unmute_at_iso, stored_channels_ser = row

        # perform unmute
        ok, details = await self._unmute_member(member, interaction.user, reason, suppress_feedback=False, stored_role_id=stored_role_id, stored_channels_serialized=stored_channels_ser)

        emb_fin = create_darlux_embed(title="🖤 Unmuted", description=f"{member.mention} has been unmuted.", accent="royal_gold")
        emb_fin.add_field(name="Reason", value=reason or "No reason provided", inline=False)
        emb_fin.set_footer(text=f"Requested by {interaction.user}", icon_url=interaction.user.display_avatar.url)
        await interaction.followup.send(embed=emb_fin, ephemeral=False)

    # ---------------------------
    # Utility: view active mutes (optional internal command for admins)
    # ---------------------------
    @app_commands.command(name="listmutes", description="(Admin) List active mutes in this server.")
    async def app_list_mutes(self, interaction: discord.Interaction):
        await interaction.response.defer(thinking=True, ephemeral=True)
        if not interaction.guild:
            await interaction.followup.send("This must be used in a server.", ephemeral=True)
            return
        if not (isinstance(interaction.user, discord.Member) and interaction.user.guild_permissions.administrator):
            await interaction.followup.send("Administrator permission required to use this command.", ephemeral=True)
            return
        # fetch DB rows for this guild
        try:
            conn = sqlite3.connect(DB_PATH)
            cur = conn.cursor()
            cur.execute("SELECT user_id, reason, muted_at, unmute_at FROM mutes WHERE guild_id = ?", (interaction.guild.id,))
            rows = cur.fetchall()
            conn.close()
        except Exception:
            rows = []
        if not rows:
            emb = create_darlux_embed(title="🖤 Active Mutes", description="No active mutes found.", accent="velvet_purple")
            await interaction.followup.send(embed=emb, ephemeral=True)
            return
        lines = []
        for r in rows[:40]:
            uid, reason, mut_at, un_at = r
            try:
                user = await self._fetch_user_safe(uid)
                uname = str(user) if user else str(uid)
            except Exception:
                uname = str(uid)
            lines.append(f"{uname} • Reason: {reason or 'N/A'} • Muted at: {mut_at} • Unmute: {un_at or 'Manual'}")
        text = "\n".join(lines)
        if len(text) > 1900:
            fp = discord.File(fp=bytes(text, "utf-8"), filename="active_mutes.txt")
            await interaction.followup.send("Active mutes:", file=fp, ephemeral=True)
        else:
            emb = create_darlux_embed(title="🖤 Active Mutes", description=text, accent="midnight_blue")
            await interaction.followup.send(embed=emb, ephemeral=True)

    # ---------------------------
    # On cog unload cleanup
    # ---------------------------
    def cog_unload(self):
        # cancel scheduled tasks
        for k, t in list(self._scheduled_unmutes.items()):
            try:
                t.cancel()
            except Exception:
                pass

    @commands.Cog.listener()
    async def on_ready(self):
        await self._load_and_schedule_pending_unmutes()


# ---------------------------
# Setup
# ---------------------------
async def setup(bot: commands.Bot):
    cog = MuteCog(bot)
    await bot.add_cog(cog)
