# cogs/automod.py
"""
Purpose:
    * Provide server (guild) specific AutoMod features: banned words, spam detection,
      link whitelist/blacklist, language enforcement, NSFW attachment scanning (stub),
      and helper commands to manage native Discord AutoMod rules where supported.
    * Persist all configuration and infractions in a SQLite database so settings survive restarts.
    * Provide aesthetic, informative embeds for user feedback and moderator logs.
    * Expose slash-only commands under the /automod command group.

Notes:
    * This cog uses "best-effort" integration with discord.py's AutoMod methods. Different
      discord.py versions expose different method names (create_auto_moderation_rule,
      create_automod_rule, automod_rules, fetch_auto_moderation_rules, etc.). The helpers
      in this cog try a few common names and gracefully fallback to storing triggers in the DB.
"""

import os
import re
import json
import asyncio
import traceback
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List, Tuple

import discord
from discord import app_commands
from discord.ext import commands

import aiosqlite
from dotenv import load_dotenv

load_dotenv()

# -------------------------
# Configuration constants
# -------------------------
DB_PATH = os.getenv("AUTOMOD_DB_PATH", "automod_bot.db")

EMOJI_SUCCESS = "✅"
EMOJI_WARNING = "⚠️"
EMOJI_ERROR = "❌"

COLORS = {
    "success": 0x2ecc71,   # green
    "warning": 0xf39c12,   # orange
    "error": 0xe74c3c,     # red
    "info": 0x3498db,      # blue
}

# Default per-guild Automod configuration — stored under guilds table.
DEFAULT_AUTOMOD_CFG = {
    "log_channel_id": None,
    "mod_role_ids": [],           # roles that may manage automod
    "trusted_role_ids": [],       # roles that are exempt from automod
    "banned_words": [],           # list of words/phrases (case-insensitive substring)
    "automod_triggers": [],       # DB fallback triggers (when native AutoMod unavailable)
    "spam_threshold": {"messages": 5, "seconds": 8},
    "links_whitelist": [],
    "links_blacklist": [],
    "nsfw_scan_enabled": False,   # simple stub scanner
    "language_enforced_channels": {},  # channel_id (str) -> language code
    "mute_role_id": None,
    "temp_mutes": [],             # list of {user_id, unmute_at_iso, reason, moderator_id}
    "custom_rules": [],           # custom rules shaped as dicts
}

# -------------------------
# Database layer (aiosqlite)
# -------------------------
class AutomodDB:
    """
    Simplified DB wrapper for guild configs and infractions.

    Tables:
        - guilds(guild_id INTEGER PRIMARY KEY, config TEXT)
        - infractions(id INTEGER PRIMARY KEY AUTOINCREMENT, guild_id, user_id, moderator_id, action, reason, created_at)
    """

    def __init__(self, path: str = DB_PATH):
        self.path = path
        self.conn: Optional[aiosqlite.Connection] = None
        self._lock = asyncio.Lock()

    async def connect(self):
        """Open DB connection and create tables if necessary."""
        self.conn = await aiosqlite.connect(self.path)
        await self.conn.execute("""
            CREATE TABLE IF NOT EXISTS guilds (
                guild_id INTEGER PRIMARY KEY,
                config TEXT NOT NULL
            );
        """)
        await self.conn.execute("""
            CREATE TABLE IF NOT EXISTS infractions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                moderator_id INTEGER,
                action TEXT NOT NULL,
                reason TEXT,
                created_at TEXT NOT NULL
            );
        """)
        await self.conn.commit()

    async def ensure_guild(self, guild_id: int):
        """Ensure a guild config exists in DB; insert default if missing."""
        async with self._lock:
            cur = await self.conn.execute("SELECT config FROM guilds WHERE guild_id = ?", (guild_id,))
            row = await cur.fetchone()
            await cur.close()
            if row is None:
                await self.set_guild_config(guild_id, DEFAULT_AUTOMOD_CFG.copy())

    async def get_guild_config(self, guild_id: int) -> Dict[str, Any]:
        """
        Returns parsed config dict for the guild.
        If absent, writes a default config and returns that.
        """
        async with self._lock:
            cur = await self.conn.execute("SELECT config FROM guilds WHERE guild_id = ?", (guild_id,))
            row = await cur.fetchone()
            await cur.close()
            if row:
                try:
                    return json.loads(row[0])
                except Exception:
                    # On parse failure, reset to default
                    return DEFAULT_AUTOMOD_CFG.copy()
            else:
                cfg = DEFAULT_AUTOMOD_CFG.copy()
                await self.set_guild_config(guild_id, cfg)
                return cfg

    async def set_guild_config(self, guild_id: int, config: Dict[str, Any]):
        """Write (insert/update) guild config JSON into DB."""
        cfg_json = json.dumps(config)
        async with self._lock:
            await self.conn.execute(
                "INSERT INTO guilds (guild_id, config) VALUES (?, ?) ON CONFLICT(guild_id) DO UPDATE SET config=excluded.config",
                (guild_id, cfg_json)
            )
            await self.conn.commit()

    async def add_infraction(self, guild_id: int, user_id: int, moderator_id: Optional[int], action: str, reason: Optional[str]):
        """Append an infraction record for auditing and escalation."""
        async with self._lock:
            ts = datetime.utcnow().isoformat()
            await self.conn.execute(
                "INSERT INTO infractions (guild_id, user_id, moderator_id, action, reason, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                (guild_id, user_id, moderator_id, action, reason, ts)
            )
            await self.conn.commit()

    async def get_recent_infractions(self, guild_id: int, limit: int = 20):
        """Return recent infractions rows for dashboard or escalation checks."""
        async with self._lock:
            cur = await self.conn.execute(
                "SELECT id, user_id, moderator_id, action, reason, created_at FROM infractions WHERE guild_id = ? ORDER BY id DESC LIMIT ?",
                (guild_id, limit)
            )
            rows = await cur.fetchall()
            await cur.close()
            return rows

# -------------------------
# Embed / aesthetic helpers
# -------------------------
class EmbedMaker:
    """Utility to create consistent, aesthetic embeds for success/warning/error/info."""

    @staticmethod
    def _base(title: str, description: str, color: int):
        em = discord.Embed(title=title, description=description, color=color, timestamp=datetime.utcnow())
        return em

    @staticmethod
    def success(title: str, description: str, *, fields: Optional[List[Tuple[str, str, bool]]] = None, footer: Optional[str] = None):
        em = EmbedMaker._base(f"{EMOJI_SUCCESS} {title}", description, COLORS["success"])
        if fields:
            for name, value, inline in fields:
                em.add_field(name=name, value=value, inline=inline)
        if footer:
            em.set_footer(text=footer)
        return em

    @staticmethod
    def warning(title: str, description: str, *, fields: Optional[List[Tuple[str, str, bool]]] = None, footer: Optional[str] = None):
        em = EmbedMaker._base(f"{EMOJI_WARNING} {title}", description, COLORS["warning"])
        if fields:
            for name, value, inline in fields:
                em.add_field(name=name, value=value, inline=inline)
        if footer:
            em.set_footer(text=footer)
        return em

    @staticmethod
    def error(title: str, description: str, *, fields: Optional[List[Tuple[str, str, bool]]] = None, footer: Optional[str] = None):
        em = EmbedMaker._base(f"{EMOJI_ERROR} {title}", description, COLORS["error"])
        if fields:
            for name, value, inline in fields:
                em.add_field(name=name, value=value, inline=inline)
        if footer:
            em.set_footer(text=footer)
        return em

    @staticmethod
    def info(title: str, description: str, *, fields: Optional[List[Tuple[str, str, bool]]] = None, footer: Optional[str] = None):
        em = EmbedMaker._base(f"ℹ️ {title}", description, COLORS["info"])
        if fields:
            for name, value, inline in fields:
                em.add_field(name=name, value=value, inline=inline)
        if footer:
            em.set_footer(text=footer)
        return em

# -------------------------
# Small utility helpers
# -------------------------
def extract_domains_from_text(content: str) -> List[str]:
    """Return a list of hostnames found in the text (http(s) links)."""
    found = re.findall(r"https?://[^\s/$.?#].[^\s]*", content)
    domains = []
    for u in found:
        m = re.match(r"https?://([^/]+)", u)
        if m:
            domains.append(m.group(1).lower())
    return domains

def domain_in_patterns(domain: str, patterns: List[str]) -> bool:
    """Return True if domain matches any of the given patterns (simple substring match)."""
    for p in patterns:
        if p.strip().lower() in domain.lower():
            return True
    return False

def detect_language_stub(text: str) -> str:
    """Very naive language detector. Replace with fasttext/langdetect for production."""
    t = text.lower()
    if any(x in t for x in (" the ", " and ", " is ", " you ")): return "en"
    if any(x in t for x in (" el ", " la ", " y ", " que ")): return "es"
    if any(x in t for x in (" le ", " la ", " est ", " et ")): return "fr"
    return "unknown"

def nsfw_stub_analysis(url: str) -> Dict[str, Any]:
    """
    Very simple NSFW attachment stub. This should be replaced by an actual image moderation
    pipeline (Vision SafeSearch or HF model). For now, detect 'nsfw' or 'adult' in filename/url.
    """
    token = url.lower()
    is_nsfw = any(x in token for x in ("nsfw", "adult", "porn", "xxx"))
    return {"nsfw": is_nsfw, "score": 0.95 if is_nsfw else 0.02}

# -------------------------
# The Cog
# -------------------------
class AutoMod(commands.Cog, name="AutoMod"):
    """
    AutoMod Cog - handles non-AI moderation and integrates with Discord AutoMod when possible.

    Key responsibilities:
        - Monitor messages in guilds and apply per-guild automod rules (banned words, spam, links).
        - Provide commands to administer native AutoMod (create/list/delete) with graceful fallback to DB triggers.
        - Provide test utilities for moderators and users.
        - Log all moderation actions to a guild-specific log channel.
    """

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # attach a DB instance to bot if not already present so other cogs can share the DB file
        if not hasattr(bot, "automod_db"):
            bot.automod_db = AutomodDB(DB_PATH)
        self.db: AutomodDB = bot.automod_db
        self.embed = EmbedMaker()
        self._spam_cache: Dict[int, Dict[int, List[float]]] = {}  # guild_id -> user_id -> [timestamps]
        self._unmute_task: Optional[asyncio.Task] = None

    async def cog_load(self):
        """Initialize DB and start background tasks on cog load."""
        await self.db.connect()
        if self._unmute_task is None:
            self._unmute_task = asyncio.create_task(self._temp_mute_watcher())

    async def cog_unload(self):
        """Cleanup background tasks and close DB (when cog unloads)."""
        if self._unmute_task:
            self._unmute_task.cancel()
            self._unmute_task = None
        if self.db.conn:
            await self.db.conn.close()

    # -------------------------
    # Permission helpers
    # -------------------------
    async def _is_moderator(self, user: discord.abc.Snowflake) -> bool:
        """
        Determine whether a user is considered a moderator in the guild.
        Criteria:
            - guild owner
            - administrators
            - any role present in the guild's config.mod_role_ids
        """
        if not isinstance(user, discord.Member):
            # try to fetch member (sometimes Interaction.user is Member)
            return False
        if user.guild is None:
            return False
        cfg = await self.db.get_guild_config(user.guild.id)
        mod_roles = cfg.get("mod_role_ids", [])
        if user.guild.owner_id == user.id:
            return True
        if user.guild_permissions.administrator:
            return True
        for r in user.roles:
            if r.id in mod_roles:
                return True
        return False

    async def _is_trusted(self, member: discord.Member, cfg: Optional[Dict[str, Any]] = None) -> bool:
        """
        Determine whether a member is 'trusted' (exempt from automod).
        Trusted roles are stored in config.trusted_role_ids.
        """
        if member.guild is None:
            return False
        if cfg is None:
            cfg = await self.db.get_guild_config(member.guild.id)
        trusted = cfg.get("trusted_role_ids", [])
        if member.guild.owner_id == member.id:
            return True
        if member.guild_permissions.administrator:
            return True
        for r in member.roles:
            if r.id in trusted:
                return True
        return False

    # -------------------------
    # Logging helper
    # -------------------------
    async def _log(self, guild: discord.Guild, embed: discord.Embed):
        """
        Send embed to the guild's configured log channel (if set).
        This method swallows exceptions so logging won't break moderation flow.
        """
        cfg = await self.db.get_guild_config(guild.id)
        log_ch_id = cfg.get("log_channel_id")
        if not log_ch_id:
            return
        ch = guild.get_channel(log_ch_id)
        if not ch or not isinstance(ch, (discord.TextChannel, discord.Thread)):
            return
        try:
            await ch.send(embed=embed)
        except Exception:
            # intentionally ignore log failures (permissions might be missing)
            pass

    # -------------------------
    # Moderation actions
    # -------------------------
    async def _warn_user(self, guild: discord.Guild, member: discord.Member, reason: str, moderator: Optional[discord.Member] = None):
        """
        Send a DM warning to the user and log the infraction.
        """
        dm = self.embed.warning("You received a warning", f"You were warned in **{guild.name}**.\n\n**Reason:** {reason}")
        try:
            await member.send(embed=dm)
        except Exception:
            pass
        await self.db.add_infraction(guild.id, member.id, getattr(moderator, "id", None), "warn", reason)
        await self._log(guild, self.embed.warning("User warned", f"{member.mention} was warned.", fields=[("Reason", reason, False)]))

    async def _delete_and_log(self, message: discord.Message, reason: str, moderator: Optional[discord.Member] = None):
        """
        Delete a message (best-effort), create an infraction, and log action.
        """
        try:
            await message.delete()
        except Exception:
            pass
        await self.db.add_infraction(message.guild.id, message.author.id, getattr(moderator, "id", None), "delete", reason)
        fields = [
            ("Moderator", getattr(moderator, "mention", "AutoMod"), True),
            ("Channel", message.channel.mention, True),
            ("Reason", reason, False),
            ("Content", message.content[:1000] or "[no content]", False),
        ]
        await self._log(message.guild, self.embed.warning("Message Deleted", f"Message by {message.author.mention} deleted.", fields=fields))

    async def _apply_temp_mute(self, guild: discord.Guild, member: discord.Member, seconds: int, reason: str, moderator: Optional[discord.Member] = None):
        """
        Apply a temporary mute to 'member' for 'seconds'.
        Strategy:
            - If a mute role is configured, add it and set channel overwrites (on role creation).
            - Otherwise attempt to use Member.timeout_for (if available in runtime).
        The unmute time is stored in the DB and a background task will unmute after expiry.
        """
        cfg = await self.db.get_guild_config(guild.id)
        mute_role_id = cfg.get("mute_role_id")
        mute_role = guild.get_role(mute_role_id) if mute_role_id else None

        # Create a Muted role if missing
        if mute_role is None:
            try:
                mute_role = await guild.create_role(name="Muted", reason="AutoMod - create Muted role")
            except Exception:
                mute_role = None
            if mute_role:
                # attempt to set send_messages=False for all text channels (best-effort)
                for ch in guild.text_channels:
                    try:
                        await ch.set_permissions(mute_role, send_messages=False, add_reactions=False)
                    except Exception:
                        pass
                cfg["mute_role_id"] = mute_role.id
                await self.db.set_guild_config(guild.id, cfg)

        try:
            if mute_role:
                await member.add_roles(mute_role, reason=f"Temp mute: {reason}")
            else:
                # try server timeout if supported
                try:
                    await member.timeout_for(timedelta(seconds=seconds), reason=reason)
                except Exception:
                    pass
        except Exception:
            pass

        # persist temp mute
        unmute_at = (datetime.utcnow() + timedelta(seconds=seconds)).isoformat()
        tms = cfg.get("temp_mutes", [])
        tms.append({"user_id": member.id, "unmute_at": unmute_at, "reason": reason, "moderator_id": getattr(moderator, "id", None)})
        cfg["temp_mutes"] = tms
        await self.db.set_guild_config(guild.id, cfg)

        await self.db.add_infraction(guild.id, member.id, getattr(moderator, "id", None), "temp_mute", reason)
        await self._log(guild, self.embed.warning("Temp mute applied", f"{member.mention} was muted for {seconds} seconds.", fields=[("Reason", reason, False)]))
        try:
            await member.send(embed=self.embed.warning("You were muted", f"You were muted for {seconds} seconds in **{guild.name}**.\n\nReason: {reason}"))
        except Exception:
            pass

    async def _unmute_member(self, guild: discord.Guild, user_id: int):
        """
        Remove mute role from member and clear pending temp_mute entry.
        """
        cfg = await self.db.get_guild_config(guild.id)
        mute_role_id = cfg.get("mute_role_id")
        member = guild.get_member(user_id)
        if member and mute_role_id:
            role = guild.get_role(mute_role_id)
            if role:
                try:
                    await member.remove_roles(role, reason="Auto unmute (temp mute expired)")
                except Exception:
                    pass
        # remove from config temp_mutes list
        tms = cfg.get("temp_mutes", [])
        new = [t for t in tms if t.get("user_id") != user_id]
        cfg["temp_mutes"] = new
        await self.db.set_guild_config(guild.id, cfg)
        await self._log(guild, self.embed.success("User unmuted", f"<@{user_id}> unmuted (auto)."))

    # -------------------------
    # Background: unmute watcher
    # -------------------------
    async def _temp_mute_watcher(self):
        """
        Periodically check DB for expired temp mutes and unmute the users.
        Runs as a background task created in cog_load.
        """
        await self.bot.wait_until_ready()
        while True:
            try:
                async with self.db._lock:
                    cur = await self.db.conn.execute("SELECT guild_id, config FROM guilds")
                    rows = await cur.fetchall()
                    await cur.close()
                now = datetime.utcnow()
                for guild_id, cfg_json in rows:
                    try:
                        cfg = json.loads(cfg_json)
                    except Exception:
                        continue
                    tms = cfg.get("temp_mutes", [])
                    changed = False
                    for tm in list(tms):
                        try:
                            unmute_at = datetime.fromisoformat(tm["unmute_at"])
                        except Exception:
                            # ignore invalid entries
                            continue
                        if unmute_at <= now:
                            guild = self.bot.get_guild(guild_id)
                            if guild:
                                await self._unmute_member(guild, tm["user_id"])
                            tms.remove(tm)
                            changed = True
                    if changed:
                        cfg["temp_mutes"] = tms
                        async with self.db._lock:
                            await self.db.conn.execute("INSERT INTO guilds (guild_id, config) VALUES (?, ?) ON CONFLICT(guild_id) DO UPDATE SET config=excluded.config", (guild_id, json.dumps(cfg)))
                            await self.db.conn.commit()
            except asyncio.CancelledError:
                return
            except Exception:
                traceback.print_exc()
            await asyncio.sleep(15)

    # -------------------------
    # Native AutoMod helpers (best-effort)
    # -------------------------
    async def try_create_native_automod_rule(self, guild: discord.Guild, name: str, trigger_type: str, trigger_metadata: Dict[str, Any], actions: List[Dict[str, Any]]):
        """
        Attempt to create a native Discord AutoMod rule.
        This is best-effort: discord.py exposes different names across versions.
        If creation fails, return None and the caller should store a DB fallback trigger.
        """
        try:
            create_fn = getattr(guild, "create_auto_moderation_rule", None) or getattr(guild, "create_automod_rule", None)
            if create_fn:
                # Build some safe parameters; runtimes may require discord.AutoModTriggerType enums.
                rule = await create_fn(
                    name=name,
                    event_type=getattr(discord, "AutoModEventType", getattr(discord, "AutoModerationEventType", None)).message_send \
                        if hasattr(discord, "AutoModEventType") or hasattr(discord, "AutoModerationEventType") else None,
                    trigger_type=trigger_type,
                    trigger_metadata=trigger_metadata,
                    actions=actions,
                    enabled=True
                )
                return rule
        except Exception:
            traceback.print_exc()
            return None
        return None

    async def try_list_native_automod_rules(self, guild: discord.Guild):
        """Try to enumerate native AutoMod rules; return None on failure."""
        try:
            getter = getattr(guild, "automod_rules", None)
            if getter:
                return await getter() if callable(getter) else getter
            fetcher = getattr(guild, "fetch_auto_moderation_rules", None)
            if fetcher:
                return await fetcher()
        except Exception:
            traceback.print_exc()
        return None

    async def try_delete_native_automod_rule(self, guild: discord.Guild, rule_id: int) -> bool:
        """Try to delete a native AutoMod rule by ID; return True if successful."""
        try:
            delete_fn = getattr(guild, "delete_auto_moderation_rule", None) or getattr(guild, "delete_automod_rule", None)
            if delete_fn:
                await delete_fn(rule_id)
                return True
        except Exception:
            traceback.print_exc()
        return False

    # -------------------------
    # Main message listener pipeline (non-AI)
    # -------------------------
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """
        Core pipeline:
            1) Ignore bots and DMs
            2) Ensure guild config exists
            3) Check banned words -> delete, warn, escalate
            4) Check custom DB rules -> take configured action
            5) Spam detection -> delete/warn/temp-mute
            6) Link protection -> whitelist/blacklist
            7) NSFW attachments (stub)
            8) Language enforcement
        Note: This listener only handles Non-AI moderation. AI moderation lives in aimoderation.py.
        """
        if message.author.bot or not message.guild:
            return

        guild = message.guild
        await self.db.ensure_guild(guild.id)
        cfg = await self.db.get_guild_config(guild.id)
        # note: stored config in DB might be just the default object or more complex. We'll expect the stored object is the automod config itself.
        # For compatibility: if the stored config is a mapping with nested keys, try to detect.
        # (This code expects the DB to store the per-guild config directly.)
        automod_cfg = cfg if isinstance(cfg, dict) else DEFAULT_AUTOMOD_CFG.copy()

        content = message.content or ""

        # 1) Banned words
        for bad in automod_cfg.get("banned_words", []):
            if bad and bad.lower() in content.lower():
                reason = f"banned_word:{bad}"
                await self._delete_and_log(message, reason)
                await self._warn_user(guild, message.author, f"Use of banned word: {bad}")
                # escalate if repeated infractions (simplistic)
                await self._maybe_escalate(guild, message.author)
                return

        # 2) Custom DB rules
        for rule in automod_cfg.get("custom_rules", []):
            ttype = rule.get("trigger_type")
            pattern = rule.get("pattern", "")
            action = rule.get("action", "warn")
            matched = False
            try:
                if ttype == "contains":
                    if pattern.lower() in content.lower():
                        matched = True
                elif ttype == "regex":
                    if re.search(pattern, content, re.IGNORECASE):
                        matched = True
                elif ttype == "invite":
                    if "discord.gg/" in content.lower() or "discord.com/invite/" in content.lower():
                        matched = True
            except re.error:
                matched = False
            if matched:
                reason = f"custom_rule:{ttype}:{pattern}"
                await self._execute_rule_action(message, action, reason)
                return

        # 3) Spam detection (sliding window)
        spam_cfg = automod_cfg.get("spam_threshold", {"messages": 5, "seconds": 8})
        thr_msgs = int(spam_cfg.get("messages", 5))
        thr_secs = int(spam_cfg.get("seconds", 8))
        guild_cache = self._spam_cache.setdefault(guild.id, {})
        user_times = guild_cache.setdefault(message.author.id, [])
        now_ts = asyncio.get_event_loop().time()
        user_times.append(now_ts)
        window_start = now_ts - thr_secs
        user_times = [t for t in user_times if t >= window_start]
        guild_cache[message.author.id] = user_times
        if len(user_times) >= thr_msgs:
            reason = f"spam:{len(user_times)} in {thr_secs}s"
            await self._delete_and_log(message, reason)
            await self._warn_user(guild, message.author, "Spam detected: too many messages in a short timeframe.")
            await self._apply_temp_mute(guild, message.author, 60, "Spam auto-mute")
            guild_cache[message.author.id] = []
            return

        # 4) Link protection
        if "http://" in content.lower() or "https://" in content.lower():
            domains = extract_domains_from_text(content)
            for d in domains:
                if domain_in_patterns(d, automod_cfg.get("links_blacklist", [])):
                    reason = "link_blacklisted"
                    await self._delete_and_log(message, reason)
                    await self._warn_user(guild, message.author, "Posting blacklisted links is prohibited.")
                    await self._maybe_escalate(guild, message.author)
                    return
            wl = automod_cfg.get("links_whitelist", [])
            if wl:
                allowed = any(domain_in_patterns(d, wl) for d in domains)
                if not allowed and domains:
                    reason = "link_not_whitelisted"
                    await self._delete_and_log(message, reason)
                    await self._warn_user(guild, message.author, "Posting links outside the whitelist is not allowed.")
                    return

        # 5) NSFW attachments (stub)
        if automod_cfg.get("nsfw_scan_enabled", False) and message.attachments:
            for att in message.attachments:
                res = nsfw_stub_analysis(att.url)
                if res.get("nsfw"):
                    reason = "nsfw_attachment_detected"
                    await self._delete_and_log(message, reason)
                    await self._warn_user(guild, message.author, "Sharing NSFW content in this channel is prohibited.")
                    await self._maybe_escalate(guild, message.author)
                    return

        # 6) Language enforcement
        lec = automod_cfg.get("language_enforced_channels", {})
        ch_lang = lec.get(str(message.channel.id))
        if ch_lang:
            detected = detect_language_stub(content)
            if detected != ch_lang and detected != "unknown":
                reason = f"language_violation expected:{ch_lang} detected:{detected}"
                await self._delete_and_log(message, reason)
                await self._warn_user(guild, message.author, f"Please use the configured language ({ch_lang}) in this channel.")
                return

        # 7) DB fallback AutoMod triggers (pattern matching)
        for trig in automod_cfg.get("automod_triggers", []):
            ttype = trig.get("trigger_type", "")
            pattern = trig.get("pattern", "")
            action = trig.get("action", "warn")
            matched = False
            try:
                if ttype == "keyword" or ttype == "contains":
                    if pattern.lower() in content.lower():
                        matched = True
                elif ttype == "regex":
                    if re.search(pattern, content, re.IGNORECASE):
                        matched = True
                elif ttype == "invite":
                    if "discord.gg/" in content.lower() or "discord.com/invite/" in content.lower():
                        matched = True
            except re.error:
                matched = False
            if matched:
                reason = f"db_trigger:{ttype}:{pattern}"
                await self._execute_rule_action(message, action, reason)
                return

    async def _execute_rule_action(self, message: discord.Message, action: str, reason: str):
        """
        Execute an automod action string against a message.
        Supported action formats (examples):
            - "delete"
            - "warn"
            - "temp_mute:300"  (seconds)
            - "kick"
            - "ban"
            - combinations like "delete+warn"
        """
        guild = message.guild
        author = message.author
        moderator = None  # automated action
        parts = action.split("+")
        for act in parts:
            act = act.strip()
            if act.startswith("temp_mute"):
                # parse optional seconds
                sec = 300
                if ":" in act:
                    try:
                        sec = int(act.split(":", 1)[1])
                    except Exception:
                        sec = 300
                await self._delete_and_log(message, reason, moderator)
                await self._apply_temp_mute(guild, author, sec, reason, moderator)
            elif act == "delete":
                await self._delete_and_log(message, reason, moderator)
            elif act == "warn":
                await self._warn_user(guild, author, reason, moderator)
            elif act == "kick":
                try:
                    await author.kick(reason=reason)
                    await self.db.add_infraction(guild.id, author.id, None, "kick", reason)
                    await self._log(guild, self.embed.warning("User kicked", f"{author.mention} kicked by AutoMod", fields=[("Reason", reason, False)]))
                except Exception:
                    pass
            elif act == "ban":
                try:
                    await author.ban(reason=reason)
                    await self.db.add_infraction(guild.id, author.id, None, "ban", reason)
                    await self._log(guild, self.embed.warning("User banned", f"{author.mention} banned by AutoMod", fields=[("Reason", reason, False)]))
                except Exception:
                    pass
            # else: unknown action -> ignore

    async def _maybe_escalate(self, guild: discord.Guild, member: discord.Member):
        """
        Basic escalation policy:
          - >=3 infractions -> temp_mute 10 minutes
          - >=6 infractions -> temp_mute 1 day
        This is intentionally simple; you can expand logic to consider time windows, action types, etc.
        """
        rows = await self.db.get_recent_infractions(guild.id, limit=200)
        count = sum(1 for r in rows if r[1] == member.id)
        if count >= 6:
            await self._apply_temp_mute(guild, member, 86400, "Escalation: repeated infractions")
        elif count >= 3:
            await self._apply_temp_mute(guild, member, 600, "Escalation: repeated infractions")

    # -------------------------
    # Slash commands (slash-only)
    # -------------------------
    automod = app_commands.Group(name="automod", description="AutoMod management and test commands (non-AI)")

    @automod.command(name="add_trigger", description="Add an AutoMod trigger. Tries native Discord AutoMod first, then falls back to DB-stored triggers.")
    @app_commands.describe(name="Rule name (human readable)", trigger_type="Type: keyword|mentions_excessive|invite|spam|regex", pattern="Keywords (comma-separated) or regex pattern", action="Action: delete|warn|temp_mute:seconds|kick|ban or combinations using +", threshold="Optional threshold for mention/spam")
    async def cmd_add_trigger(self, interaction: discord.Interaction, name: str, trigger_type: str, pattern: Optional[str], action: str, threshold: Optional[int] = None):
        """
        Create a moderation trigger.
        Permissions: caller must be a configured moderator (mod_role_ids) or guild admin/owner.
        Behavior:
            - Attempts to create a native Discord AutoMod rule if the runtime and permissions allow.
            - If native creation fails (no support or permission), stores a fallback trigger in the DB.
        Notes:
            - 'pattern' is interpreted depending on trigger_type: for 'keyword' it's comma-separated keywords;
              for 'regex' it's a regex string; for invite/mentions_excessive pattern may be ignored.
        """
        await interaction.response.defer(ephemeral=True)
        member = interaction.user if isinstance(interaction.user, discord.Member) else None
        if not member or not await self._is_moderator(member):
            await interaction.followup.send(embed=self.embed.error("Permission denied", "You must be a configured moderator or guild admin/owner to add triggers."), ephemeral=True)
            return

        guild = interaction.guild
        if guild is None:
            await interaction.followup.send(embed=self.embed.error("Guild required", "This command must be used inside a guild."), ephemeral=True)
            return

        trigger_type_lower = trigger_type.lower()
        metadata = {}
        if trigger_type_lower in ("keyword", "keywords"):
            keywords = [k.strip() for k in (pattern or "").split(",") if k.strip()]
            metadata = {"keywords": keywords}
        elif trigger_type_lower == "mentions_excessive":
            metadata = {"mention_total_limit": threshold or 5}
        elif trigger_type_lower == "invite":
            metadata = {"invites": True}
        elif trigger_type_lower == "spam":
            metadata = {"threshold_seconds": threshold or 8}
        elif trigger_type_lower == "regex":
            metadata = {"pattern": pattern}
        else:
            # fallback to keywords
            keywords = [k.strip() for k in (pattern or "").split(",") if k.strip()]
            metadata = {"keywords": keywords}

        actions = [{"type": action}]  # runtime may require different shapes; this is best-effort

        # Try to create native rule
        native_rule = await self.try_create_native_automod_rule(guild, name, trigger_type_lower, metadata, actions)
        if native_rule:
            # Attempt to extract ID/name for response (many runtimes will provide .id/.name)
            rid = getattr(native_rule, "id", None) or str(native_rule)
            await interaction.followup.send(embed=self.embed.success("Native AutoMod rule created", f"Created native rule **{name}** (ID: `{rid}`)."), ephemeral=True)
            # log to guild log
            await self._log(guild, self.embed.info("Native AutoMod rule created", f"Rule **{name}** created by {interaction.user.mention}", fields=[("Rule ID", str(rid), True), ("Type", trigger_type_lower, True), ("Metadata", json.dumps(metadata), False), ("Action", action, True)]))
            return

        # Fallback: store in DB triggers
        await self.db.ensure_guild(guild.id)
        cfg = await self.db.get_guild_config(guild.id)
        trigs = cfg.get("automod_triggers", [])
        trigs.append({"name": name, "trigger_type": trigger_type_lower, "pattern": pattern or "", "action": action, "metadata": metadata})
        cfg["automod_triggers"] = trigs
        await self.db.set_guild_config(guild.id, cfg)
        await interaction.followup.send(embed=self.embed.warning("Fallback trigger stored", "Could not create native AutoMod rule — stored trigger as DB fallback."), ephemeral=True)
        await self._log(guild, self.embed.warning("Fallback AutoMod trigger stored", f"Trigger '{name}' stored in DB fallback.", fields=[("Type", trigger_type_lower, True), ("Pattern", str(pattern or ""), True), ("Action", action, True)]))

    @automod.command(name="remove_trigger", description="Remove a native AutoMod rule by ID, or remove a DB fallback trigger by pattern or name.")
    @app_commands.describe(rule_id="Native rule ID (optional)", pattern_or_name="DB fallback trigger pattern or name (optional)")
    async def cmd_remove_trigger(self, interaction: discord.Interaction, rule_id: Optional[str] = None, pattern_or_name: Optional[str] = None):
        """
        Remove an AutoMod trigger.
        If rule_id is supplied, attempts to delete a native rule.
        If pattern_or_name is supplied, removes DB fallback triggers matching the pattern or name.
        """
        await interaction.response.defer(ephemeral=True)
        member = interaction.user if isinstance(interaction.user, discord.Member) else None
        if not member or not await self._is_moderator(member):
            await interaction.followup.send(embed=self.embed.error("Permission denied", "You must be a configured moderator or admin to remove triggers."), ephemeral=True)
            return
        guild = interaction.guild
        if guild is None:
            await interaction.followup.send(embed=self.embed.error("Guild required", "This command must be used inside a guild."), ephemeral=True)
            return

        if rule_id:
            # try to delete native rule (rule_id may be numeric or string)
            try:
                rid_int = int(rule_id)
            except Exception:
                rid_int = None
            ok = False
            if rid_int is not None:
                ok = await self.try_delete_native_automod_rule(guild, rid_int)
            if ok:
                await interaction.followup.send(embed=self.embed.success("Native rule removed", f"Removed native rule `{rule_id}`."), ephemeral=True)
                await self._log(guild, self.embed.info("Native AutoMod rule removed", f"Native rule `{rule_id}` removed by {interaction.user.mention}"))
            else:
                await interaction.followup.send(embed=self.embed.error("Failed to remove native rule", "Could not delete the native rule — runtime may not support it or bot lacks permissions."), ephemeral=True)
            return

        if pattern_or_name:
            await self.db.ensure_guild(guild.id)
            cfg = await self.db.get_guild_config(guild.id)
            trigs = cfg.get("automod_triggers", [])
            new_trigs = [t for t in trigs if not (pattern_or_name.lower() in (t.get("pattern", "") or "").lower() or pattern_or_name.lower() in (t.get("name", "") or "").lower())]
            removed_count = len(trigs) - len(new_trigs)
            cfg["automod_triggers"] = new_trigs
            await self.db.set_guild_config(guild.id, cfg)
            await interaction.followup.send(embed=self.embed.success("Fallback triggers updated", f"Removed {removed_count} fallback trigger(s) matching `{pattern_or_name}`."), ephemeral=True)
            await self._log(guild, self.embed.info("Fallback triggers removed", f"{removed_count} fallback trigger(s) removed by {interaction.user.mention}"))
            return

        await interaction.followup.send(embed=self.embed.error("Missing arguments", "Provide either rule_id (native) or pattern_or_name (fallback) to remove."), ephemeral=True)

    @automod.command(name="list_triggers", description="List native AutoMod rules (if supported) or DB-stored fallback triggers.")
    async def cmd_list_triggers(self, interaction: discord.Interaction):
        """
        List automod triggers.
        If the runtime supports native AutoMod enumeration, those rules will be listed.
        Otherwise DB fallback triggers will be shown.
        """
        await interaction.response.defer(ephemeral=True)
        guild = interaction.guild
        if guild is None:
            await interaction.followup.send(embed=self.embed.error("Guild required", "This command must be used in a guild."), ephemeral=True)
            return

        native = await self.try_list_native_automod_rules(guild)
        if native:
            lines = []
            for r in native:
                try:
                    rid = getattr(r, "id", "?")
                    name = getattr(r, "name", str(r))
                    enabled = getattr(r, "enabled", "?")
                    lines.append(f"ID: `{rid}` • **{name}** • enabled={enabled}")
                except Exception:
                    lines.append(str(r))
            page_text = "\n".join(lines) or "No native AutoMod rules found."
            await interaction.followup.send(embed=self.embed.info("Native AutoMod rules", page_text), ephemeral=True)
            return

        # fallback: DB triggers
        await self.db.ensure_guild(guild.id)
        cfg = await self.db.get_guild_config(guild.id)
        trigs = cfg.get("automod_triggers", [])
        if not trigs:
            await interaction.followup.send(embed=self.embed.info("Triggers", "No native rules and no DB fallback triggers found."), ephemeral=True)
            return
        text = "\n".join(f"- **{t.get('name','(no name)')}** • `{t.get('trigger_type')}` • `{t.get('pattern')}` -> `{t.get('action')}`" for t in trigs)
        await interaction.followup.send(embed=self.embed.info("DB fallback triggers", text), ephemeral=True)

    @automod.command(name="config", description="View or update automod configuration for this guild.")
    @app_commands.describe(subcommand="show | set_log | add_mod_role | remove_mod_role | add_trusted | remove_trusted | set_banned_words")
    async def cmd_config(self, interaction: discord.Interaction, subcommand: str, value: Optional[str] = None):
        """
        Multi-purpose config command for convenience. Subcommands:
            - show: display current automod config
            - set_log <#channel>: set log channel (use channel mention to pass)
            - add_mod_role <role_id or @role>
            - remove_mod_role <role_id or @role>
            - add_trusted <role_id or @role>
            - remove_trusted <role_id or @role>
            - set_banned_words <comma-separated list | 'none'>
        Note: For 'set_log' you must use the channel chooser in the UI (type is TextChannel) — but for flexibility we accept a string mention or id here too.
        """
        await interaction.response.defer(ephemeral=True)
        member = interaction.user if isinstance(interaction.user, discord.Member) else None
        if not member or not await self._is_moderator(member):
            await interaction.followup.send(embed=self.embed.error("Permission denied", "You must be a configured moderator or guild admin to manage the automod config."), ephemeral=True)
            return

        await self.db.ensure_guild(interaction.guild.id)
        cfg = await self.db.get_guild_config(interaction.guild.id)

        sub = subcommand.lower()
        if sub == "show":
            am = cfg
            fields = [
                ("Log Channel", str(am.get("log_channel_id")), True),
                ("Mod Roles", ", ".join(str(x) for x in am.get("mod_role_ids", [])) or "None", True),
                ("Trusted Roles", ", ".join(str(x) for x in am.get("trusted_role_ids", [])) or "None", True),
                ("Banned words", ", ".join(am.get("banned_words", [])[:20]) or "None", False),
                ("Spam threshold", str(am.get("spam_threshold", {})), True),
                ("Links whitelist", ", ".join(am.get("links_whitelist", [])[:10]) or "None", False),
                ("Links blacklist", ", ".join(am.get("links_blacklist", [])[:10]) or "None", False)
            ]
            await interaction.followup.send(embed=self.embed.info("AutoMod Configuration", "Current configuration snapshot", fields=fields), ephemeral=True)
            return

        # set_log expects value like '<#channelid>' or channel mention or id
        if sub == "set_log":
            if not value:
                await interaction.followup.send(embed=self.embed.error("Missing value", "Provide a channel mention or channel ID."), ephemeral=True)
                return
            # attempt to parse channel id
            ch_id = None
            m = re.search(r"<#(\d+)>", value)
            if m:
                ch_id = int(m.group(1))
            else:
                try:
                    ch_id = int(value)
                except Exception:
                    ch_id = None
            if ch_id is None:
                await interaction.followup.send(embed=self.embed.error("Invalid channel", "Could not parse channel id."), ephemeral=True)
                return
            cfg["log_channel_id"] = ch_id
            await self.db.set_guild_config(interaction.guild.id, cfg)
            await interaction.followup.send(embed=self.embed.success("Log channel set", f"AutoMod logs will be sent to <#{ch_id}> (if bot has access)."), ephemeral=True)
            return

        if sub in ("add_mod_role", "remove_mod_role"):
            if not value:
                await interaction.followup.send(embed=self.embed.error("Missing value", "Provide a role mention or role ID."), ephemeral=True)
                return
            role_id = None
            m = re.search(r"<@&(\d+)>", value)
            if m:
                role_id = int(m.group(1))
            else:
                try:
                    role_id = int(value)
                except Exception:
                    role_id = None
            if role_id is None:
                await interaction.followup.send(embed=self.embed.error("Invalid role", "Could not parse role id."), ephemeral=True)
                return
            mod_roles = cfg.get("mod_role_ids", [])
            if sub == "add_mod_role":
                if role_id not in mod_roles:
                    mod_roles.append(role_id)
                    cfg["mod_role_ids"] = mod_roles
                    await self.db.set_guild_config(interaction.guild.id, cfg)
                await interaction.followup.send(embed=self.embed.success("Mod role updated", f"Role <@&{role_id}> added to mod roles."), ephemeral=True)
            else:
                new = [r for r in mod_roles if r != role_id]
                cfg["mod_role_ids"] = new
                await self.db.set_guild_config(interaction.guild.id, cfg)
                await interaction.followup.send(embed=self.embed.success("Mod role removed", f"Role <@&{role_id}> removed from mod roles."), ephemeral=True)
            return

        if sub in ("add_trusted", "remove_trusted"):
            if not value:
                await interaction.followup.send(embed=self.embed.error("Missing value", "Provide a role mention or role ID."), ephemeral=True)
                return
            role_id = None
            m = re.search(r"<@&(\d+)>", value)
            if m:
                role_id = int(m.group(1))
            else:
                try:
                    role_id = int(value)
                except Exception:
                    role_id = None
            if role_id is None:
                await interaction.followup.send(embed=self.embed.error("Invalid role", "Could not parse role id."), ephemeral=True)
                return
            trusted = cfg.get("trusted_role_ids", [])
            if sub == "add_trusted":
                if role_id not in trusted:
                    trusted.append(role_id)
                    cfg["trusted_role_ids"] = trusted
                    await self.db.set_guild_config(interaction.guild.id, cfg)
                await interaction.followup.send(embed=self.embed.success("Trusted role updated", f"Role <@&{role_id}> added to trusted roles."), ephemeral=True)
            else:
                trusted = [r for r in trusted if r != role_id]
                cfg["trusted_role_ids"] = trusted
                await self.db.set_guild_config(interaction.guild.id, cfg)
                await interaction.followup.send(embed=self.embed.success("Trusted role removed", f"Role <@&{role_id}> removed from trusted roles."), ephemeral=True)
            return

        if sub == "set_banned_words":
            if value is None:
                await interaction.followup.send(embed=self.embed.error("Missing value", "Provide a comma-separated list or 'none'."), ephemeral=True)
                return
            if value.strip().lower() == "none":
                cfg["banned_words"] = []
            else:
                cfg["banned_words"] = [w.strip() for w in value.split(",") if w.strip()]
            await self.db.set_guild_config(interaction.guild.id, cfg)
            await interaction.followup.send(embed=self.embed.success("Banned words updated", f"New banned words: {', '.join(cfg['banned_words']) or 'None'}"), ephemeral=True)
            return

        await interaction.followup.send(embed=self.embed.error("Unknown subcommand", "Supported: show, set_log, add_mod_role, remove_mod_role, add_trusted, remove_trusted, set_banned_words"), ephemeral=True)

    @automod.command(name="test", description="Simulate automod checks: profanity|spam|link|nsfw|language")
    @app_commands.describe(kind="profanity|spam|link|nsfw|language", sample="Text or URL to test with")
    async def cmd_test(self, interaction: discord.Interaction, kind: str, sample: Optional[str] = None):
        """
        Simulate how AutoMod would handle a message. Useful for moderators and regular users.
        - profanity: checks for banned words in sample text
        - spam: returns current spam threshold settings
        - link: checks domain against whitelist/blacklist
        - nsfw: performs a stub nsfw test on a provided URL
        - language: tests language detection stub
        """
        await interaction.response.defer(ephemeral=True)
        kind = (kind or "").lower()
        await self.db.ensure_guild(interaction.guild.id)
        cfg = await self.db.get_guild_config(interaction.guild.id)

        if kind == "profanity":
            if not sample:
                await interaction.followup.send(embed=self.embed.error("Missing sample", "Provide sample text to test profanity."), ephemeral=True)
                return
            found = [w for w in cfg.get("banned_words", []) if w.lower() in sample.lower()]
            if found:
                await interaction.followup.send(embed=self.embed.warning("Profanity test — would trigger", f"Found banned words: {', '.join(found)}\nAction: delete & warn"), ephemeral=True)
            else:
                await interaction.followup.send(embed=self.embed.success("Profanity test — clean", "No banned words detected"), ephemeral=True)
            return

        if kind == "spam":
            thr = cfg.get("spam_threshold", {})
            await interaction.followup.send(embed=self.embed.info("Spam threshold", f"{thr.get('messages')} messages in {thr.get('seconds')} seconds"), ephemeral=True)
            return

        if kind == "link":
            if not sample:
                await interaction.followup.send(embed=self.embed.error("Missing sample", "Provide a sample URL to test."), ephemeral=True)
                return
            domains = extract_domains_from_text(sample)
            bl = cfg.get("links_blacklist", [])
            wl = cfg.get("links_whitelist", [])
            reasons = []
            for d in domains:
                if domain_in_patterns(d, bl):
                    reasons.append(f"{d} — blacklisted")
                elif wl and not domain_in_patterns(d, wl):
                    reasons.append(f"{d} — not whitelisted")
                else:
                    reasons.append(f"{d} — allowed")
            await interaction.followup.send(embed=self.embed.info("Link test", "\n".join(reasons) or "No links detected"), ephemeral=True)
            return

        if kind == "nsfw":
            if not sample:
                await interaction.followup.send(embed=self.embed.error("Missing URL", "Provide an image URL to test."), ephemeral=True)
                return
            res = nsfw_stub_analysis(sample)
            if res.get("nsfw"):
                await interaction.followup.send(embed=self.embed.warning("NSFW test flagged (stub)", f"Score: {res.get('score')} — would delete & warn"), ephemeral=True)
            else:
                await interaction.followup.send(embed=self.embed.success("NSFW test clean (stub)", "No obvious indicators found."), ephemeral=True)
            return

        if kind == "language":
            if not sample:
                await interaction.followup.send(embed=self.embed.error("Missing sample", "Provide sample text to test language detection."), ephemeral=True)
                return
            detected = detect_language_stub(sample)
            await interaction.followup.send(embed=self.embed.info("Language test", f"Detected language: `{detected}`"), ephemeral=True)
            return

        await interaction.followup.send(embed=self.embed.error("Unknown test kind", "Supported: profanity, spam, link, nsfw, language"), ephemeral=True)

# -------------------------
# Cog setup entrypoint
# -------------------------
async def setup(bot: commands.Bot):
    """
    Cog setup: create cog instance and attach to bot.
    Ensures DB initialization is done so other cogs (like aimoderation.py) can share the DB file.
    """
    cog = AutoMod(bot)
    await bot.add_cog(cog)
    # attach DB to bot if not present
    if not hasattr(bot, "automod_db"):
        bot.automod_db = AutomodDB(DB_PATH)
    await bot.automod_db.connect()
