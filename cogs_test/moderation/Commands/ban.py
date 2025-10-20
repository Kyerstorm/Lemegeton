# ban.py
"""
Features:
 - /ban, /tempban, /unban, /softban
 - /setappealschannel, /setmodlog, /showconfig, /appeals, /export
 - Appeals modal + Appeal button -> posts to appeals channel with moderator decision UI
 - Uses aiosqlite for persistence: moderation.db with tables (guild_config, tempbans, appeals, softbans, mod_logs)
 - Robust Discord API wrappers with retries & fallbacks
 - Startup recovery to handle missed softban/unban actions
 - Permission checks, role-hierarchy checks, and helpful errors
 - /botperms to list missing bot permissions in a guild
"""

from __future__ import annotations
import asyncio
import aiosqlite
import json
import logging
import os
import re
import traceback
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any, Tuple, List

import discord
from discord import app_commands
from discord.ext import commands, tasks

# -------------------------
# CONFIG
# -------------------------
LOG = logging.getLogger("BanCog")
LOG.setLevel(logging.INFO)

DB_PATH = "data/moderation.db"
ensure_dir = lambda p: os.makedirs(os.path.dirname(p), exist_ok=True) if os.path.dirname(p) else None
ensure_dir(DB_PATH)

# visual theme (Royal Blue & Silver)
ROYAL_BLUE = discord.Color.from_rgb(65, 105, 225)  # 0x4169E1
SILVER = discord.Color.from_rgb(192, 192, 192)

# allowed delete days for ban API (0..7)
MAX_DELETE_DAYS = 7

# API retry settings
API_RETRY_ATTEMPTS = 3
API_RETRY_BACKOFF = 1.0  # seconds base

# temporary ban check interval
TEMPBAN_CHECK_SECONDS = 45

# moderate role requirement: either Administrator OR (kick && ban && moderate)
def is_staff_member(member: discord.Member) -> bool:
    perms = member.guild_permissions
    return perms.administrator or (perms.kick_members and perms.ban_members and perms.moderate_members)

# -------------------------
# UTIL HELPERS
# -------------------------
def utcnow() -> datetime:
    return datetime.utcnow().replace(tzinfo=timezone.utc)

def human_delta(delta: timedelta) -> str:
    s = int(delta.total_seconds())
    if s < 60:
        return f"{s}s"
    parts = []
    days, rem = divmod(s, 86400)
    hours, rem = divmod(rem, 3600)
    minutes, seconds = divmod(rem, 60)
    if days:
        parts.append(f"{days}d")
    if hours:
        parts.append(f"{hours}h")
    if minutes:
        parts.append(f"{minutes}m")
    if seconds and not parts:
        parts.append(f"{seconds}s")
    return " ".join(parts)

# parse duration like "1d2h30m" -> seconds
_DURATION_RE = re.compile(r"(\d+)([smhdw])", re.IGNORECASE)
def parse_duration_to_seconds(s: str) -> Optional[int]:
    if not s:
        return None
    s = s.strip().lower()
    total = 0
    matched = False
    for m in _DURATION_RE.finditer(s):
        matched = True
        num = int(m.group(1))
        unit = m.group(2)
        if unit == "s":
            total += num
        elif unit == "m":
            total += num * 60
        elif unit == "h":
            total += num * 3600
        elif unit == "d":
            total += num * 86400
        elif unit == "w":
            total += num * 604800
    if not matched:
        # maybe it's just a number (seconds)
        if s.isdigit():
            return int(s)
        return None
    return total if total > 0 else None

def embed_base(title: Optional[str] = None, description: Optional[str] = None, color: discord.Colour = ROYAL_BLUE) -> discord.Embed:
    e = discord.Embed(title=title, description=description, color=color, timestamp=utcnow())
    e.set_footer(text="Moderation • Royal Edition")
    return e

# -------------------------
# DATABASE (aiosqlite) helpers
# -------------------------
CREATE_TABLES_SQL = [
    # guild configuration table
    """
    CREATE TABLE IF NOT EXISTS guild_config (
        guild_id INTEGER PRIMARY KEY,
        appeals_channel_id INTEGER,
        mod_log_channel_id INTEGER,
        created_at TEXT
    );
    """,
    # tempbans: store unban time
    """
    CREATE TABLE IF NOT EXISTS tempbans (
        guild_id INTEGER,
        user_id INTEGER,
        unban_at TEXT,
        reason TEXT,
        moderator_id INTEGER,
        PRIMARY KEY (guild_id, user_id)
    );
    """,
    # appeals
    """
    CREATE TABLE IF NOT EXISTS appeals (
        id TEXT PRIMARY KEY,
        guild_id INTEGER,
        user_id INTEGER,
        appeal_text TEXT,
        extra TEXT,
        status TEXT,
        moderator_id INTEGER,
        moderator_reason TEXT,
        submitted_at TEXT,
        decided_at TEXT,
        appeals_channel_id INTEGER,
        appeals_message_id INTEGER
    );
    """,
    # softbans: audit records for softbans
    """
    CREATE TABLE IF NOT EXISTS softbans (
        id TEXT PRIMARY KEY,
        guild_id INTEGER,
        user_id INTEGER,
        moderator_id INTEGER,
        reason TEXT,
        delete_days INTEGER,
        performed_at TEXT,
        dm_sent INTEGER,
        dm_error TEXT
    );
    """,
    # moderation logs (generic)
    """
    CREATE TABLE IF NOT EXISTS mod_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        guild_id INTEGER,
        action TEXT,
        actor_id INTEGER,
        target_id INTEGER,
        reason TEXT,
        details TEXT,
        created_at TEXT
    );
    """
]

async def init_db():
    ensure_dir(DB_PATH)
    async with aiosqlite.connect(DB_PATH) as db:
        for s in CREATE_TABLES_SQL:
            await db.execute(s)
        await db.commit()

# helper to perform simple upserts / queries
class DB:
    def __init__(self, path=DB_PATH):
        self.path = path

    async def execute(self, sql: str, params: tuple = ()):
        async with aiosqlite.connect(self.path) as db:
            await db.execute(sql, params)
            await db.commit()

    async def fetchone(self, sql: str, params: tuple = ()):
        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute(sql, params)
            row = await cur.fetchone()
            await cur.close()
            return row

    async def fetchall(self, sql: str, params: tuple = ()):
        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute(sql, params)
            rows = await cur.fetchall()
            await cur.close()
            return rows

db = DB()

# -------------------------
# DISCORD API WRAPPERS (retries, best-effort)
# -------------------------
async def safe_api(coro_callable, *args, attempts=API_RETRY_ATTEMPTS, backoff=API_RETRY_BACKOFF, **kwargs):
    """
    Generic wrapper for API calls. coro_callable should be a coroutine function (callable), not yet awaited.
    Returns tuple (ok: bool, result_or_error: Any)
    """
    last_exc = None
    for i in range(attempts):
        try:
            res = await coro_callable(*args, **kwargs)
            return True, res
        except discord.HTTPException as e:
            last_exc = e
            # handle rate-limit (discord.py does automatic ratelimit handling usually)
            await asyncio.sleep(backoff * (i + 1))
        except discord.Forbidden as e:
            return False, e
        except Exception as e:
            last_exc = e
            await asyncio.sleep(backoff * (i + 1))
    return False, last_exc

# convenience wrappers
async def safe_ban(guild: discord.Guild, user: discord.abc.Snowflake, reason: Optional[str], delete_message_days: int = 0):
    return await safe_api(guild.ban, user, reason=reason, delete_message_days=delete_message_days)

async def safe_unban(guild: discord.Guild, user: discord.abc.Snowflake, reason: Optional[str]):
    return await safe_api(guild.unban, user, reason=reason)

async def safe_dm(user: discord.User, embed: Optional[discord.Embed] = None, view: Optional[discord.ui.View] = None):
    async def _send():
        ch = await user.create_dm()
        return await ch.send(embed=embed, view=view)
    return await safe_api(_send)

# -------------------------
# VIEWS & MODALS (appeals + moderator decision)
# -------------------------
class AppealModal(discord.ui.Modal, title="Submit an Appeal"):
    appeal_text = discord.ui.TextInput(label="Why should you be unbanned?", style=discord.TextStyle.long, required=True, max_length=2000)
    extra = discord.ui.TextInput(label="Anything else?", style=discord.TextStyle.paragraph, required=False, max_length=1000)

    def __init__(self, cog: "BanCog", guild_id: int, banned_user_id: int):
        super().__init__()
        self.cog = cog
        self.guild_id = guild_id
        self.banned_user_id = banned_user_id

    async def on_submit(self, interaction: discord.Interaction):
        # create appeal record
        aid = f"appeal-{self.guild_id}-{self.banned_user_id}-{int(datetime.utcnow().timestamp())}"
        rec = {
            "id": aid,
            "guild_id": self.guild_id,
            "user_id": self.banned_user_id,
            "appeal_text": str(self.appeal_text.value),
            "extra": str(self.extra.value) if self.extra.value else "",
            "status": "pending",
            "moderator_id": None,
            "moderator_reason": None,
            "submitted_at": utcnow().isoformat(),
            "decided_at": None,
            "appeals_channel_id": None,
            "appeals_message_id": None
        }
        # insert to DB
        try:
            await db.execute(
                "INSERT INTO appeals (id, guild_id, user_id, appeal_text, extra, status, submitted_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (rec["id"], rec["guild_id"], rec["user_id"], rec["appeal_text"], rec["extra"], rec["status"], rec["submitted_at"])
            )
        except Exception:
            LOG.exception("Failed to insert appeal")
        # post to appeals channel if configured
        guild = self.cog.bot.get_guild(self.guild_id)
        embed = embed_base(title="📝 New Ban Appeal", description=f"Appeal from <@{self.banned_user_id}>", color=ROYAL_BLUE)
        embed.add_field(name="Appeal", value=rec["appeal_text"], inline=False)
        if rec["extra"]:
            embed.add_field(name="Extra", value=rec["extra"], inline=False)
        embed.add_field(name="Submitted (UTC)", value=rec["submitted_at"], inline=False)
        try:
            ch = await self.cog._get_appeals_channel(guild)
            if ch:
                view = ModeratorDecisionView(self.cog, rec["id"])
                sent_ok, sent_res = await safe_api(ch.send, embed=embed, view=view)
                if sent_ok:
                    msg = sent_res
                    # update DB with channel and message id
                    await db.execute("UPDATE appeals SET appeals_channel_id = ?, appeals_message_id = ? WHERE id = ?", (ch.id, msg.id, rec["id"]))
                    await interaction.response.send_message("✅ Your appeal was submitted to the staff. They will review it.", ephemeral=True)
                    await self.cog._mod_log(guild, f"Appeal {rec['id']} submitted by <@{self.banned_user_id}>")
                    return
        except Exception:
            LOG.exception("Error posting appeal")
        await interaction.response.send_message("Your appeal was recorded, but I couldn't post to the server appeals channel. Staff will need to check manually.", ephemeral=True)

class ModeratorDecisionModal(discord.ui.Modal):
    reason_input = discord.ui.TextInput(label="Moderator Reason", style=discord.TextStyle.long, required=True, max_length=2000)

    def __init__(self, cog: "BanCog", appeal_id: str, action: str):
        super().__init__(title="Decision")
        self.cog = cog
        self.appeal_id = appeal_id
        self.action = action  # "accept" or "reject"

    async def on_submit(self, interaction: discord.Interaction):
        # permission check
        guild_id = None
        try:
            row = await db.fetchone("SELECT guild_id, user_id FROM appeals WHERE id = ?", (self.appeal_id,))
            if not row:
                await interaction.response.send_message("Appeal not found.", ephemeral=True)
                return
            guild_id = int(row["guild_id"])
            guild = self.cog.bot.get_guild(guild_id)
            if not guild:
                await interaction.response.send_message("Guild not available.", ephemeral=True)
                return
            member = guild.get_member(interaction.user.id)
            if not member or not is_staff_member(member):
                await interaction.response.send_message("You don't have permission to make this decision.", ephemeral=True)
                return
            # update DB
            await db.execute("UPDATE appeals SET status = ?, moderator_id = ?, moderator_reason = ?, decided_at = ? WHERE id = ?",
                             (self.action, interaction.user.id, str(self.reason_input.value), utcnow().isoformat(), self.appeal_id))
            # edit original message if possible
            row2 = await db.fetchone("SELECT appeals_channel_id, appeals_message_id FROM appeals WHERE id = ?", (self.appeal_id,))
            if row2 and row2["appeals_channel_id"] and row2["appeals_message_id"]:
                ch = guild.get_channel(int(row2["appeals_channel_id"]))
                if ch:
                    try:
                        msg = await ch.fetch_message(int(row2["appeals_message_id"]))
                        decision_color = ROYAL_BLUE if self.action == "accept" else discord.Color.red()
                        embed = embed_base(title=f"Appeal {self.action.title()}", color=decision_color)
                        embed.add_field(name="Moderator", value=f"{interaction.user} (`{interaction.user.id}`)", inline=False)
                        embed.add_field(name="Moderator Reason", value=str(self.reason_input.value), inline=False)
                        await msg.edit(embed=embed, view=None)
                    except Exception:
                        LOG.exception("Failed to edit appeal message")
            # do accept/unban if appropriate
            if self.action == "accept":
                # unban user if banned
                target_id = int(row["user_id"])
                try:
                    obj = discord.Object(id=target_id)
                    ok, res = await safe_unban(guild, obj, reason=f"Appeal accepted by {interaction.user}")
                    if ok:
                        # DM user
                        try:
                            user = await self.cog.bot.fetch_user(target_id)
                            dm_embed = embed_base(title=f"✅ Appeal Accepted in {guild.name}", description=f"Your appeal was accepted. Moderator reason: {self.reason_input.value}", color=ROYAL_BLUE)
                            await safe_dm(user, embed=dm_embed)
                        except Exception:
                            LOG.debug("Failed to DM user after appeal accept")
                        await interaction.response.send_message("Appeal accepted and user unbanned (if banned).", ephemeral=True)
                        await self.cog._mod_log(guild, f"Appeal {self.appeal_id} accepted by {interaction.user}.")
                        return
                    else:
                        await interaction.response.send_message(f"Appeal accepted, but unban failed: {res}", ephemeral=True)
                        await self.cog._mod_log(guild, f"Appeal {self.appeal_id} accepted by {interaction.user} but unban failed: {res}")
                        return
                except Exception:
                    LOG.exception("Unban during appeal acceptance failed")
                    await interaction.response.send_message("Attempted to unban but failed. Check bot permissions.", ephemeral=True)
                    return
            else:
                # rejected -> DM user
                target_id = int(row["user_id"])
                try:
                    user = await self.cog.bot.fetch_user(target_id)
                    dm_embed = embed_base(title=f"❌ Appeal Rejected in {guild.name}", description=f"Your appeal was rejected. Moderator reason: {self.reason_input.value}", color=discord.Color.red())
                    await safe_dm(user, embed=dm_embed)
                except Exception:
                    LOG.debug("Failed to DM user after appeal reject")
                await interaction.response.send_message("Appeal rejected.", ephemeral=True)
                await self.cog._mod_log(guild, f"Appeal {self.appeal_id} rejected by {interaction.user}.")
        except Exception:
            LOG.exception("Error handling moderator decision modal")
            await interaction.response.send_message("An error occurred while processing the appeal.", ephemeral=True)

class AppealButtonView(discord.ui.View):
    def __init__(self, cog: "BanCog", guild_id: int, banned_user_id: int):
        super().__init__(timeout=None)
        self.cog = cog
        self.guild_id = guild_id
        self.banned_user_id = banned_user_id

    @discord.ui.button(label="📝 Appeal Ban", style=discord.ButtonStyle.primary, custom_id="appeal_button")
    async def appeal(self, button: discord.ui.Button, interaction: discord.Interaction):
        modal = AppealModal(self.cog, self.guild_id, self.banned_user_id)
        await interaction.response.send_modal(modal)

class ModeratorDecisionView(discord.ui.View):
    def __init__(self, cog: "BanCog", appeal_id: str):
        super().__init__(timeout=None)
        self.cog = cog
        self.appeal_id = appeal_id

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        # ensure staff
        guild_row = await db.fetchone("SELECT guild_id FROM appeals WHERE id = ?", (self.appeal_id,))
        if not guild_row:
            await interaction.response.send_message("Appeal not found.", ephemeral=True)
            return False
        guild = self.cog.bot.get_guild(int(guild_row["guild_id"]))
        if not guild:
            await interaction.response.send_message("Guild not found.", ephemeral=True)
            return False
        member = guild.get_member(interaction.user.id)
        if not member or not is_staff_member(member):
            await interaction.response.send_message("You don't have permission to process appeals.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="✅ Accept", style=discord.ButtonStyle.success, custom_id="mod_accept")
    async def accept(self, button: discord.ui.Button, interaction: discord.Interaction):
        modal = ModeratorDecisionModal(self.cog, self.appeal_id, "accept")
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="❌ Reject", style=discord.ButtonStyle.danger, custom_id="mod_reject")
    async def reject(self, button: discord.ui.Button, interaction: discord.Interaction):
        modal = ModeratorDecisionModal(self.cog, self.appeal_id, "reject")
        await interaction.response.send_modal(modal)

# -------------------------
# Confirm & Progress views
# -------------------------
class ConfirmView(discord.ui.View):
    def __init__(self, author: discord.User, timeout: float = 30.0):
        super().__init__(timeout=timeout)
        self.author = author
        self.value: Optional[bool] = None

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author.id:
            await interaction.response.send_message("This confirmation is for the command user only.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Confirm", style=discord.ButtonStyle.danger)
    async def confirm(self, button: discord.ui.Button, interaction: discord.Interaction):
        self.value = True
        await interaction.response.edit_message(content="Confirmed.", view=None)

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def cancel(self, button: discord.ui.Button, interaction: discord.Interaction):
        self.value = False
        await interaction.response.edit_message(content="Cancelled.", view=None)

class ProgressView(discord.ui.View):
    def __init__(self, timeout: float = 300.0):
        super().__init__(timeout=timeout)

    @discord.ui.button(label="Close", style=discord.ButtonStyle.danger)
    async def close(self, button: discord.ui.Button, interaction: discord.Interaction):
        try:
            await interaction.message.delete()
        except Exception:
            pass
        self.stop()

# -------------------------
# THE COG
# -------------------------
class BanCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # ensure DB is ready
        self._ready_task = bot.loop.create_task(init_db())
        # start background task for tempbans/unban checks
        self._tempban_loop.start()
        # start recovery for softbans (no-op unless entries)
        self._recover_task = bot.loop.create_task(self._recover_softbans_on_startup())
        LOG.info("BanCog initialized")

    def cog_unload(self):
        try:
            self._tempban_loop.cancel()
        except Exception:
            pass
        try:
            self._recover_task.cancel()
        except Exception:
            pass

    # -------------------------
    # Background: tempban unban loop
    # -------------------------
    @tasks.loop(seconds=TEMPBAN_CHECK_SECONDS)
    async def _tempban_loop(self):
        try:
            rows = await db.fetchall("SELECT guild_id, user_id, unban_at FROM tempbans")
            now_iso = utcnow().isoformat()
            for r in rows:
                guild_id = int(r["guild_id"])
                user_id = int(r["user_id"])
                unban_at = r["unban_at"]
                if not unban_at:
                    continue
                try:
                    unban_dt = datetime.fromisoformat(unban_at)
                except Exception:
                    continue
                if utcnow() >= unban_dt:
                    guild = self.bot.get_guild(guild_id)
                    if not guild:
                        # remove the record (can't unban if guild not available)
                        await db.execute("DELETE FROM tempbans WHERE guild_id = ? AND user_id = ?", (guild_id, user_id))
                        continue
                    try:
                        obj = discord.Object(id=user_id)
                        ok, res = await safe_unban(guild, obj, reason="Temporary ban expired (automated).")
                        if ok:
                            await self._mod_log(guild, f"Auto-unbanned {user_id} (tempban expired).")
                        else:
                            LOG.warning("Auto-unban failed for %s in %s: %s", user_id, guild_id, res)
                        # delete record
                        await db.execute("DELETE FROM tempbans WHERE guild_id = ? AND user_id = ?", (guild_id, user_id))
                    except Exception:
                        LOG.exception("Exception during auto-unban")
        except Exception:
            LOG.exception("Error in tempban loop")

    @_tempban_loop.before_loop
    async def before_tempban_loop(self):
        await self.bot.wait_until_ready()
        await self._ready_task

    # -------------------------
    # Recovery: scan softbans table and attempt to finish any incomplete actions
    # -------------------------
    async def _recover_softbans_on_startup(self):
        await self.bot.wait_until_ready()
        await self._ready_task
        # softbans table is an audit log—no recovery needed, but we ensure no inconsistent state
        # If desired: find records missing performed_at (shouldn't happen). Here we log and continue.
        try:
            rows = await db.fetchall("SELECT id, guild_id, user_id FROM softbans WHERE performed_at IS NULL")
            for r in rows:
                LOG.warning("Found incomplete softban record: %s", r["id"])
                # we could attempt to fix but safest to leave as audit record for manual review
        except Exception:
            LOG.exception("Error during softban recovery")

    # -------------------------
    # Low-level helpers: config + channels + mod-log
    # -------------------------
    async def _get_guild_config(self, guild: discord.Guild) -> Dict[str, Any]:
        row = await db.fetchone("SELECT appeals_channel_id, mod_log_channel_id FROM guild_config WHERE guild_id = ?", (guild.id,))
        if not row:
            return {}
        return {"appeals_channel_id": row["appeals_channel_id"], "mod_log_channel_id": row["mod_log_channel_id"]}

    async def _set_guild_config(self, guild: discord.Guild, key: str, value: Any):
        row = await db.fetchone("SELECT guild_id FROM guild_config WHERE guild_id = ?", (guild.id,))
        if row:
            if key == "appeals_channel_id":
                await db.execute("UPDATE guild_config SET appeals_channel_id = ? WHERE guild_id = ?", (int(value), guild.id))
            elif key == "mod_log_channel_id":
                await db.execute("UPDATE guild_config SET mod_log_channel_id = ? WHERE guild_id = ?", (int(value), guild.id))
        else:
            # insert new row
            appeals = None
            modlog = None
            if key == "appeals_channel_id":
                appeals = int(value)
            if key == "mod_log_channel_id":
                modlog = int(value)
            await db.execute("INSERT OR REPLACE INTO guild_config (guild_id, appeals_channel_id, mod_log_channel_id, created_at) VALUES (?, ?, ?, ?)",
                             (guild.id, appeals, modlog, utcnow().isoformat()))

    async def _get_appeals_channel(self, guild: discord.Guild) -> Optional[discord.TextChannel]:
        cfg = await self._get_guild_config(guild)
        cid = cfg.get("appeals_channel_id")
        if cid:
            ch = guild.get_channel(int(cid))
            if ch and isinstance(ch, discord.TextChannel):
                return ch
        # try name fallback
        for c in guild.text_channels:
            if c.name == "appeals" or c.name == "appeals-logs":
                return c
        return None

    async def _get_mod_log_channel(self, guild: discord.Guild) -> Optional[discord.TextChannel]:
        cfg = await self._get_guild_config(guild)
        cid = cfg.get("mod_log_channel_id")
        if cid:
            ch = guild.get_channel(int(cid))
            if ch and isinstance(ch, discord.TextChannel):
                return ch
        # fallback
        for c in guild.text_channels:
            if c.name in ("mod-log", "modlog", "moderation"):
                return c
        return None

    async def _mod_log(self, guild: discord.Guild, message: str):
        try:
            ch = await self._get_mod_log_channel(guild)
            embed = embed_base(title="📜 Moderation Log", description=message, color=SILVER)
            await safe_api(ch.send, embed=embed) if ch else LOG.info("Mod log not configured for guild %s: %s", guild.id, message)
            # also persist generic mod log table
            await db.execute("INSERT INTO mod_logs (guild_id, action, actor_id, target_id, reason, details, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                             (guild.id, "log", None, None, None, message, utcnow().isoformat()))
        except Exception:
            LOG.exception("Failed to write mod_log")

    # -------------------------
    # PERMISSION CHECKS
    # -------------------------
    def _user_can_act_on(self, invoker: discord.Member, target: discord.Member) -> Tuple[bool, str]:
        if invoker == target:
            return False, "You cannot act on yourself."
        if target == invoker.guild.owner:
            return False, "You cannot act on the server owner."
        if invoker != invoker.guild.owner and invoker.top_role <= target.top_role:
            return False, "You cannot act on someone with an equal or higher top role."
        return True, ""

    def _bot_can_act_on(self, guild: discord.Guild, target: discord.Member) -> Tuple[bool, str]:
        me = guild.me
        if me is None:
            return False, "Bot is not present in this guild."
        if me.top_role <= target.top_role:
            return False, "I cannot act on this user due to role hierarchy."
        perms = guild.me.guild_permissions
        if not perms.ban_members:
            return False, "I require the Ban Members permission."
        return True, ""

    # -------------------------
    # APP COMMANDS
    # -------------------------
    @app_commands.command(name="ban", description="Permanently ban a member (staff only).")
    @app_commands.check(lambda i: is_staff_member(i.user if isinstance(i.user, discord.Member) else discord.Object(id=0)))
    async def ban(self, interaction: discord.Interaction, member: discord.Member, reason: Optional[str] = None, delete_days: Optional[int] = 0):
        await interaction.response.defer(ephemeral=True, thinking=True)
        if not interaction.guild:
            return await interaction.followup.send("This command can only be used in a server.", ephemeral=True)
        if delete_days is None:
            delete_days = 0
        delete_days = max(0, min(MAX_DELETE_DAYS, int(delete_days)))
        allowed, msg = self._user_can_act_on(interaction.user, member)
        if not allowed:
            return await interaction.followup.send(msg, ephemeral=True)
        ok_bot, bot_msg = self._bot_can_act_on(interaction.guild, member)
        if not ok_bot:
            return await interaction.followup.send(bot_msg, ephemeral=True)

        # confirm
        view = ConfirmView(interaction.user)
        emb = embed_base(title="⚠️ Confirm Ban", description=f"Ban {member}?\nReason: {reason or 'No reason provided'}\nDelete messages (days): {delete_days}")
        await interaction.followup.send(embed=emb, view=view, ephemeral=True)
        await view.wait()
        if view.value is not True:
            return await interaction.followup.send("Ban cancelled.", ephemeral=True)

        # DM attempt with appeal
        dm_embed = embed_base(title=f"You were banned from {interaction.guild.name}", description=f"Reason: {reason or 'No reason provided'}", color=discord.Color.red())
        dm_view = AppealButtonView(self, guild_id=interaction.guild.id, banned_user_id=member.id)
        dm_ok, dm_res = await safe_dm(member, embed=dm_embed, view=dm_view)
        dm_sent = bool(dm_ok)

        # ban
        ban_reason = f"{reason or 'No reason provided'} — banned by {interaction.user}"
        ok, res = await safe_ban(interaction.guild, member, reason=ban_reason, delete_message_days=delete_days)
        if not ok:
            await interaction.followup.send(f"Failed to ban: {res}", ephemeral=True)
            await self._mod_log(interaction.guild, f"Failed ban attempt: {member} by {interaction.user}. Error: {res}")
            return
        # success
        out = embed_base(title="✅ Member Banned", description=f"{member.mention} has been banned.", color=discord.Color.red())
        out.add_field(name="Reason", value=reason or "No reason provided", inline=False)
        out.add_field(name="DM Sent", value="✅" if dm_sent else "❌", inline=True)
        await interaction.followup.send(embed=out, ephemeral=True)
        await self._mod_log(interaction.guild, f"{member} banned by {interaction.user}. Reason: {reason or 'No reason provided'}")

    @app_commands.command(name="tempban", description="Temporarily ban a member. Duration example: 30m, 2h, 1d")
    @app_commands.check(lambda i: is_staff_member(i.user if isinstance(i.user, discord.Member) else discord.Object(id=0)))
    async def tempban(self, interaction: discord.Interaction, member: discord.Member, duration: str, reason: Optional[str] = None, delete_days: Optional[int] = 0):
        await interaction.response.defer(ephemeral=True, thinking=True)
        if not interaction.guild:
            return await interaction.followup.send("Must be used in a server.", ephemeral=True)
        secs = parse_duration_to_seconds(duration)
        if secs is None or secs <= 0:
            return await interaction.followup.send("Invalid duration. Examples: 30m, 2h, 1d", ephemeral=True)
        unban_at = utcnow() + timedelta(seconds=secs)
        delete_days = max(0, min(MAX_DELETE_DAYS, int(delete_days or 0)))

        allowed, msg = self._user_can_act_on(interaction.user, member)
        if not allowed:
            return await interaction.followup.send(msg, ephemeral=True)
        ok_bot, bot_msg = self._bot_can_act_on(interaction.guild, member)
        if not ok_bot:
            return await interaction.followup.send(bot_msg, ephemeral=True)

        view = ConfirmView(interaction.user)
        emb = embed_base(title="⚠️ Confirm Tempban", description=f"Ban {member} for {human_delta(timedelta(seconds=secs))}?\nReason: {reason or 'No reason provided'}")
        await interaction.followup.send(embed=emb, view=view, ephemeral=True)
        await view.wait()
        if view.value is not True:
            return await interaction.followup.send("Tempban cancelled.", ephemeral=True)

        # DM attempt
        dm_embed = embed_base(title=f"You were temporarily banned from {interaction.guild.name}", description=f"Duration: {human_delta(timedelta(seconds=secs))}\nReason: {reason or 'No reason provided'}", color=discord.Color.red())
        dm_view = AppealButtonView(self, guild_id=interaction.guild.id, banned_user_id=member.id)
        dm_ok, dm_res = await safe_dm(member, embed=dm_embed, view=dm_view)

        # ban
        ban_reason = f"{reason or 'No reason provided'} — tempbanned by {interaction.user} until {unban_at.isoformat()}"
        ok, res = await safe_ban(interaction.guild, member, reason=ban_reason, delete_message_days=delete_days)
        if not ok:
            await interaction.followup.send(f"Failed to tempban: {res}", ephemeral=True)
            await self._mod_log(interaction.guild, f"Failed tempban attempt: {member} by {interaction.user}. Error: {res}")
            return

        # persist tempban
        try:
            await db.execute("INSERT OR REPLACE INTO tempbans (guild_id, user_id, unban_at, reason, moderator_id) VALUES (?, ?, ?, ?, ?)",
                             (interaction.guild.id, member.id, unban_at.isoformat(), reason or "", interaction.user.id))
        except Exception:
            LOG.exception("Failed to persist tempban")

        out = embed_base(title="✅ Member Temporarily Banned", description=f"{member.mention} banned for {human_delta(timedelta(seconds=secs))}", color=discord.Color.orange())
        out.add_field(name="Reason", value=reason or "No reason provided", inline=False)
        out.add_field(name="DM Sent", value="✅" if dm_ok else "❌", inline=True)
        out.add_field(name="Scheduled Unban (UTC)", value=unban_at.isoformat(), inline=False)
        await interaction.followup.send(embed=out, ephemeral=True)
        await self._mod_log(interaction.guild, f"{member} tempbanned by {interaction.user} until {unban_at.isoformat()}. Reason: {reason or 'No reason provided'}")

    @app_commands.command(name="unban", description="Unban a user by ID (staff only).")
    @app_commands.check(lambda i: is_staff_member(i.user if isinstance(i.user, discord.Member) else discord.Object(id=0)))
    async def unban(self, interaction: discord.Interaction, user_id: str, reason: Optional[str] = None):
        await interaction.response.defer(ephemeral=True, thinking=True)
        if not interaction.guild:
            return await interaction.followup.send("Must be used in a server.", ephemeral=True)
        try:
            uid = int(re.sub(r"[<@!>]", "", user_id))
        except Exception:
            return await interaction.followup.send("Invalid user ID.", ephemeral=True)
        obj = discord.Object(id=uid)
        ok, res = await safe_unban(interaction.guild, obj, reason=f"{reason or 'No reason provided'} — unbanned by {interaction.user}")
        if not ok:
            return await interaction.followup.send(f"Failed to unban: {res}", ephemeral=True)
        # remove tempban row if present
        try:
            await db.execute("DELETE FROM tempbans WHERE guild_id = ? AND user_id = ?", (interaction.guild.id, uid))
        except Exception:
            LOG.exception("Failed to remove tempban record after unban")
        out = embed_base(title="✅ User Unbanned", description=f"<@{uid}> has been unbanned.", color=discord.Color.green())
        out.add_field(name="Moderator", value=str(interaction.user), inline=True)
        out.add_field(name="Reason", value=reason or "No reason provided", inline=False)
        await interaction.followup.send(embed=out, ephemeral=True)
        await self._mod_log(interaction.guild, f"User {uid} unbanned by {interaction.user}. Reason: {reason or 'No reason provided'}")

    # -------------------------
    # Softban: ban then unban
    # -------------------------
    @app_commands.command(name="softban", description="Softban (ban then unban) a user to purge recent messages.")
    @app_commands.check(lambda i: is_staff_member(i.user if isinstance(i.user, discord.Member) else discord.Object(id=0)))
    async def softban(self, interaction: discord.Interaction, member: discord.Member, delete_days: Optional[int] = 1, reason: Optional[str] = None, preview: Optional[bool] = False):
        """
        Softban behavior:
         - preview=True: don't perform action, only show what would happen
         - otherwise: attempts DM, bans (delete_days), then unbans immediately. Retries unban if first attempt fails.
         - logs an audit record in softbans table.
        """
        await interaction.response.defer(ephemeral=True, thinking=True)
        if not interaction.guild:
            return await interaction.followup.send("Must be used in a server.", ephemeral=True)
        delete_days = int(delete_days or 1)
        delete_days = max(0, min(MAX_DELETE_DAYS, delete_days))
        allowed, msg = self._user_can_act_on(interaction.user, member)
        if not allowed:
            return await interaction.followup.send(msg, ephemeral=True)
        ok_bot, bot_msg = self._bot_can_act_on(interaction.guild, member)
        if not ok_bot:
            return await interaction.followup.send(bot_msg, ephemeral=True)

        # preview mode
        if preview:
            emb = embed_base(title="🧐 Softban Preview", description=f"This will ban then unban {member.mention} and purge up to {delete_days} day(s) of messages.", color=discord.Color.gold())
            emb.add_field(name="Reason", value=reason or "No reason provided", inline=False)
            return await interaction.followup.send(embed=emb, ephemeral=True)

        # confirm
        view = ConfirmView(interaction.user)
        embc = embed_base(title="⚠️ Confirm Softban", description=f"Softban {member}? This will ban then unban and purge up to {delete_days} day(s) of messages.\nReason: {reason or 'No reason provided'}", color=discord.Color.orange())
        await interaction.followup.send(embed=embc, view=view, ephemeral=True)
        await view.wait()
        if view.value is not True:
            return await interaction.followup.send("Softban cancelled.", ephemeral=True)

        # Attempt to DM before action
        dm_embed = embed_base(title=f"You were softbanned from {interaction.guild.name}", description=f"Reason: {reason or 'No reason provided'}\nMessages deleted: up to {delete_days} day(s).", color=discord.Color.red())
        dm_view = AppealButtonView(self, guild_id=interaction.guild.id, banned_user_id=member.id)
        dm_ok, dm_res = await safe_dm(member, embed=dm_embed, view=dm_view)
        dm_sent = bool(dm_ok)

        # Execute ban
        ban_reason = f"{reason or 'No reason provided'} — softbanned by {interaction.user}"
        ok_ban, ban_res = await safe_ban(interaction.guild, member, reason=ban_reason, delete_message_days=delete_days)
        if not ok_ban:
            await interaction.followup.send(embed=embed_base(title="❌ Softban Failed", description=f"Failed to ban: {ban_res}", color=discord.Color.red()), ephemeral=True)
            await self._mod_log(interaction.guild, f"Softban failed (ban) for {member} by {interaction.user}: {ban_res}")
            return
        # attempt unban (retry a couple times)
        unban_err = None
        for attempt in range(3):
            await asyncio.sleep(0.6 * (attempt + 1))  # slight backoff
            obj = discord.Object(id=member.id)
            ok_unban, unban_res = await safe_unban(interaction.guild, obj, reason=f"Softban automatic unban — requested by {interaction.user}")
            if ok_unban:
                unban_err = None
                break
            else:
                unban_err = unban_res
                LOG.warning("Softban unban attempt %s failed: %s", attempt + 1, unban_res)
        # record softban audit
        sb_id = f"softban-{interaction.guild.id}-{member.id}-{int(datetime.utcnow().timestamp())}"
        try:
            await db.execute("INSERT INTO softbans (id, guild_id, user_id, moderator_id, reason, delete_days, performed_at, dm_sent, dm_error) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                             (sb_id, interaction.guild.id, member.id, interaction.user.id, reason or "", delete_days, utcnow().isoformat(), 1 if dm_sent else 0, None if dm_sent else str(dm_res)))
        except Exception:
            LOG.exception("Failed to persist softban audit")

        # result embed
        out = embed_base(title="✅ Softban Completed", description=f"{member.mention} was softbanned. Messages up to {delete_days} day(s) removed.", color=discord.Color.orange())
        out.add_field(name="Reason", value=reason or "No reason provided", inline=False)
        out.add_field(name="DM Sent", value="✅" if dm_sent else f"❌ ({str(dm_res)})", inline=True)
        if unban_err:
            out.add_field(name="Unban", value=f"⚠️ Unban failed: {unban_err}. User may remain banned — please check manually.", inline=False)
        await interaction.followup.send(embed=out, ephemeral=True)
        await self._mod_log(interaction.guild, f"Softban by {interaction.user} on {member}. Reason: {reason or 'No reason provided'}. Deleted {delete_days} day(s) messages.")

    # -------------------------
    # Appeals & Config commands
    # -------------------------
    @app_commands.command(name="setappealschannel", description="Set the appeals channel for this server (staff only).")
    @app_commands.check(lambda i: is_staff_member(i.user if isinstance(i.user, discord.Member) else discord.Object(id=0)))
    async def setappealschannel(self, interaction: discord.Interaction, channel: discord.TextChannel):
        await interaction.response.defer(ephemeral=True, thinking=True)
        await self._set_guild_config(interaction.guild, "appeals_channel_id", channel.id)
        await interaction.followup.send(embed=embed_base(title="✅ Appeals Channel Set", description=f"Appeals channel set to {channel.mention}"), ephemeral=True)

    @app_commands.command(name="setmodlog", description="Set the mod-log channel for this server (staff only).")
    @app_commands.check(lambda i: is_staff_member(i.user if isinstance(i.user, discord.Member) else discord.Object(id=0)))
    async def setmodlog(self, interaction: discord.Interaction, channel: discord.TextChannel):
        await interaction.response.defer(ephemeral=True, thinking=True)
        await self._set_guild_config(interaction.guild, "mod_log_channel_id", channel.id)
        await interaction.followup.send(embed=embed_base(title="✅ Mod-Log Channel Set", description=f"Mod-log set to {channel.mention}"), ephemeral=True)

    @app_commands.command(name="showconfig", description="Show moderation config for this server.")
    @app_commands.check(lambda i: is_staff_member(i.user if isinstance(i.user, discord.Member) else discord.Object(id=0)))
    async def showconfig(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True, thinking=True)
        cfg = await self._get_guild_config(interaction.guild)
        emb = embed_base(title=f"Moderation Config — {interaction.guild.name}", color=ROYAL_BLUE)
        emb.add_field(name="Appeals Channel ID", value=str(cfg.get("appeals_channel_id") or "Not set"), inline=False)
        emb.add_field(name="Mod-Log Channel ID", value=str(cfg.get("mod_log_channel_id") or "Not set"), inline=False)
        await interaction.followup.send(embed=emb, ephemeral=True)

    @app_commands.command(name="appeals", description="List recent appeals (staff only).")
    @app_commands.check(lambda i: is_staff_member(i.user if isinstance(i.user, discord.Member) else discord.Object(id=0)))
    async def appeals(self, interaction: discord.Interaction, limit: Optional[int] = 10):
        await interaction.response.defer(ephemeral=True, thinking=True)
        rows = await db.fetchall("SELECT id, user_id, appeal_text, status, submitted_at FROM appeals WHERE guild_id = ? ORDER BY submitted_at DESC LIMIT ?",
                                 (interaction.guild.id, limit))
        if not rows:
            return await interaction.followup.send(embed=embed_base(title="Appeals", description="No appeals found."), ephemeral=True)
        emb = embed_base(title=f"Recent Appeals ({len(rows)})", color=ROYAL_BLUE)
        for r in rows:
            txt = r["appeal_text"]
            if len(txt) > 200:
                txt = txt[:197] + "..."
            emb.add_field(name=f"ID: {r['id']}", value=f"{txt}\nFrom: <@{r['user_id']}> • Status: {r['status']}", inline=False)
        await interaction.followup.send(embed=emb, ephemeral=True)

    @app_commands.command(name="export", description="Export moderation DB tables as a file to your DM (staff only).")
    @app_commands.check(lambda i: is_staff_member(i.user if isinstance(i.user, discord.Member) else discord.Object(id=0)))
    async def export(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True, thinking=True)
        # dump the sqlite file itself
        try:
            if not os.path.exists(DB_PATH):
                return await interaction.followup.send("No database file to export.", ephemeral=True)
            await interaction.followup.send("Exporting DB...", ephemeral=True)
            dm = await interaction.user.create_dm()
            await dm.send(file=discord.File(DB_PATH, filename=os.path.basename(DB_PATH)))
            await interaction.followup.send("Database sent to your DMs.", ephemeral=True)
        except Exception:
            LOG.exception("Export failed")
            await interaction.followup.send("Failed to send DB via DM.", ephemeral=True)

    @app_commands.command(name="botperms", description="Show missing bot permissions in this guild/channel.")
    @app_commands.describe(channel="Optional channel to check (defaults to current channel)")
    async def botperms(self, interaction: discord.Interaction, channel: Optional[discord.TextChannel] = None):
        await interaction.response.defer(ephemeral=True, thinking=True)
        if not interaction.guild:
            return await interaction.followup.send("Use in a server.", ephemeral=True)
        ch = channel or interaction.channel
        me = interaction.guild.me
        if not me:
            return await interaction.followup.send("Bot not fully available in this guild.", ephemeral=True)
        perms = ch.permissions_for(me)
        missing = [p for p, v in perms if not v] if isinstance(perms, dict) else []
        # discord.Permissions object isn't a dict; we'll inspect important perms
        needed = ["ban_members", "kick_members", "manage_roles", "manage_channels", "send_messages", "read_messages", "read_message_history", "manage_messages"]
        missing_list = []
        for n in needed:
            if not getattr(perms, n, False):
                missing_list.append(n)
        emb = embed_base(title="🔎 Bot Permission Check", color=ROYAL_BLUE)
        if missing_list:
            emb.description = f"Missing permissions in {ch.mention}:"
            emb.add_field(name="Missing", value=", ".join(missing_list), inline=False)
        else:
            emb.description = f"Bot has required permissions in {ch.mention}."
        await interaction.followup.send(embed=emb, ephemeral=True)

    # -------------------------
    # Error handling
    # -------------------------
    @commands.Cog.listener()
    async def on_app_command_error(self, interaction: discord.Interaction, error: Exception):
        if isinstance(error, app_commands.AppCommandError):
            try:
                await interaction.response.send_message(str(error), ephemeral=True)
            except Exception:
                LOG.exception("Failed to send app command error message")
        else:
            LOG.exception("Unhandled app command error: %s", error)
            try:
                await interaction.response.send_message("An unexpected error occurred. Check logs.", ephemeral=True)
            except Exception:
                pass

# -------------------------
# Cog setup
# -------------------------
async def setup(bot: commands.Bot):
    cog = BanCog(bot)
    await bot.add_cog(cog)
