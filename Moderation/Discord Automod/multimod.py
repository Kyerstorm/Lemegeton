# cogs/moderation_cog.py
# Single, unified cog file implementing AutoMod + AI Moderation + related systems
# Designed to be dropped into a discord.py v2+ bot (commands.Bot / ext.commands)
#
# Sections:
# PART 0: Imports & constants
# PART 1: Async SQLite DB (per-guild config + infractions)
# PART 2: Embed helper (aesthetic per system prompt)
# PART 3: Utility helpers (permission checks, mute role management, language detection stub, nsfw stub)
# PART 4: The MultiModCog class (listeners + slash command groups)
# PART 5: setup function for discord.py extension loading
#
# WARNING: This file is intentionally large. Keep it in a cog folder and load normally.
# Also: Configure .env with DISCORD_TOKEN and optionally OPENAI_API_KEY.
# ------------------------------------------------------------------------------

# PART 0: Imports & constants
import discord
from discord.ext import commands, tasks
from discord import app_commands
import aiosqlite
import asyncio
import re
import json
from datetime import datetime, timedelta
import os
import traceback
from typing import Optional, Dict, Any, List, Tuple

# Optional OpenAI: only used if OPENAI_API_KEY env var present.
try:
    import openai
    OPENAI_AVAILABLE = True
except Exception:
    OPENAI_AVAILABLE = False

# Constants for embed colors / emojis per system prompt
EMOJI_SUCCESS = "✅"
EMOJI_WARNING = "⚠️"
EMOJI_ERROR = "❌"

COLORS = {
    "success": 0x2ecc71,  # green
    "warning": 0xf39c12,  # orange
    "error":   0xe74c3c,  # red
    "info":    0x3498db,  # blue
}

DEFAULT_GUILD_CONFIG = {
    "log_channel_id": None,
    "mod_role_ids": [],          # ints
    "trusted_role_ids": [],      # ints
    "banned_words": ["damn", "hell"],
    "automod_triggers": [],      # list of dict {trigger_type, pattern, action}
    "aimod_enabled": False,
    "spam_threshold": {"messages": 5, "seconds": 8},  # 5 messages in 8 seconds = spam
    "links_whitelist": [],       # domains allowed
    "links_blacklist": [],       # domains blocked
    "nsfw_enabled": False,
    "language_enforced_channels": {},  # {channel_id: "en"}
    "mute_role_id": None,
    "infractions": [],           # List of infractions (kept short); infractions saved in separate table too
    "temp_mutes": [],            # list of active temp mutes {user_id, unmute_at_iso, reason, moderator}
}

DB_PATH = "moderation_bot.db"  # will be created in working dir

# ------------------------------------------------------------------------------

# PART 1: Async DB layer (aiosqlite)
class ModerationDB:
    def __init__(self, path: str = DB_PATH):
        self.path = path
        self.conn: Optional[aiosqlite.Connection] = None
        self._lock = asyncio.Lock()

    async def connect(self):
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
            timestamp TEXT NOT NULL
        );
        """)
        await self.conn.commit()

    async def close(self):
        if self.conn:
            await self.conn.close()
            self.conn = None

    # Guild config helpers
    async def ensure_guild(self, guild_id: int):
        async with self._lock:
            cur = await self.conn.execute("SELECT config FROM guilds WHERE guild_id = ?", (guild_id,))
            row = await cur.fetchone()
            await cur.close()
            if row is None:
                # insert default copy
                await self.set_guild_config(guild_id, DEFAULT_GUILD_CONFIG.copy())

    async def get_guild_config(self, guild_id: int) -> Dict[str, Any]:
        async with self._lock:
            cur = await self.conn.execute("SELECT config FROM guilds WHERE guild_id = ?", (guild_id,))
            row = await cur.fetchone()
            await cur.close()
            if row:
                try:
                    return json.loads(row[0])
                except Exception:
                    return DEFAULT_GUILD_CONFIG.copy()
            else:
                # ensure and return default
                await self.set_guild_config(guild_id, DEFAULT_GUILD_CONFIG.copy())
                return DEFAULT_GUILD_CONFIG.copy()

    async def set_guild_config(self, guild_id: int, config: Dict[str, Any]):
        async with self._lock:
            cfg_json = json.dumps(config)
            await self.conn.execute(
                "INSERT INTO guilds (guild_id, config) VALUES (?, ?) ON CONFLICT(guild_id) DO UPDATE SET config = excluded.config",
                (guild_id, cfg_json)
            )
            await self.conn.commit()

    async def update_guild_config(self, guild_id: int, patch: Dict[str, Any]):
        cfg = await self.get_guild_config(guild_id)
        cfg.update(patch)
        await self.set_guild_config(guild_id, cfg)

    # Infractions helpers
    async def add_infraction(self, guild_id: int, user_id: int, moderator_id: Optional[int], action: str, reason: str):
        async with self._lock:
            ts = datetime.utcnow().isoformat()
            await self.conn.execute(
                "INSERT INTO infractions (guild_id, user_id, moderator_id, action, reason, timestamp) VALUES (?, ?, ?, ?, ?, ?)",
                (guild_id, user_id, moderator_id, action, reason, ts)
            )
            await self.conn.commit()
            # also append to guild config infractions short list
            cfg = await self.get_guild_config(guild_id)
            infra = cfg.get("infractions", [])
            infra.append({"user_id": user_id, "action": action, "reason": reason, "timestamp": ts})
            # keep only last 200 entries to avoid blowup
            cfg["infractions"] = infra[-200:]
            await self.set_guild_config(guild_id, cfg)

    async def get_recent_infractions(self, guild_id: int, limit: int = 20):
        async with self._lock:
            cur = await self.conn.execute(
                "SELECT id, user_id, moderator_id, action, reason, timestamp FROM infractions WHERE guild_id = ? ORDER BY id DESC LIMIT ?",
                (guild_id, limit)
            )
            rows = await cur.fetchall()
            await cur.close()
            return rows

# ------------------------------------------------------------------------------

# PART 2: Embed helper (aesthetic)
class EmbedHelper:
    def moderation_embed(self, title: str, description: str, color: str = "info", fields: Optional[List[Tuple[str, str, bool]]] = None, footer: Optional[str] = None) -> discord.Embed:
        c = COLORS.get(color, COLORS["info"])
        em = discord.Embed(title=title, description=description, color=c, timestamp=datetime.utcnow())
        if fields:
            for name, value, inline in fields:
                em.add_field(name=name, value=value, inline=inline)
        if footer:
            em.set_footer(text=footer)
        return em

    def success(self, title: str, description: str, **kwargs):
        return self.moderation_embed(f"{EMOJI_SUCCESS} {title}", description, color="success", **kwargs)

    def warning(self, title: str, description: str, **kwargs):
        return self.moderation_embed(f"{EMOJI_WARNING} {title}", description, color="warning", **kwargs)

    def error(self, title: str, description: str, **kwargs):
        return self.moderation_embed(f"{EMOJI_ERROR} {title}", description, color="error", **kwargs)

# ------------------------------------------------------------------------------

# PART 3: Utility helpers
async def create_or_get_muted_role(guild: discord.Guild, db_cfg: Dict[str, Any]) -> discord.Role:
    """
    Ensure a Muted role exists with appropriate permissions; return role.
    Stores id in db_cfg if created.
    """
    role_id = db_cfg.get("mute_role_id")
    if role_id:
        role = guild.get_role(role_id)
        if role:
            return role
    # find role named "Muted"
    role = discord.utils.get(guild.roles, name="Muted")
    if role is None:
        # create muted role
        perms = discord.Permissions(send_messages=False, speak=False, add_reactions=False)
        role = await guild.create_role(name="Muted", permissions=perms, reason="Auto-created Muted role for moderation cog")
    # apply channel overrides to remove send messages where possible
    for ch in guild.channels:
        try:
            # skip overwriting if channel already denies send_messages for that role
            if ch.overwrites_for(role).send_messages is True:
                continue
            await ch.set_permissions(role, send_messages=False, add_reactions=False, speak=False)
        except Exception:
            # ignore channels where we can't set permissions
            continue
    # save role id
    db_cfg["mute_role_id"] = role.id
    return role

def is_domain_in_list(url: str, domain_list: List[str]) -> bool:
    # simple extraction
    try:
        m = re.search(r"https?://([^/]+)", url)
        if not m:
            return False
        hostname = m.group(1).lower()
        for d in domain_list:
            if d.lower() in hostname:
                return True
    except Exception:
        return False
    return False

# Simple language detection stub (for demonstration): uses character frequency heuristics
def detect_language_simple(text: str) -> str:
    # very naive: presence of common words
    t = text.lower()
    if any(w in t for w in [" the ", " and ", " is ", " you ", " have "]):  # english
        return "en"
    if any(w in t for w in [" el ", " la ", " y ", " es ", " que "]):  # spanish-ish
        return "es"
    if any(w in t for w in [" le ", " la ", " est ", " et ", " à "]):  # french-ish
        return "fr"
    return "unknown"

# NSFW detection stub: placeholder (in production use Vision API or openai images/moderation endpoint)
def nsfw_check_stub(image_url: str) -> Dict[str, Any]:
    # This stub randomly returns not-safe or safe only for structure demonstration
    # Production: call a real classifier. Here we will just flag images with "nsfw" substring for demo.
    if "nsfw" in image_url.lower():
        return {"nsfw": True, "score": 0.98}
    return {"nsfw": False, "score": 0.02}

# ------------------------------------------------------------------------------

# PART 4: The MultiModCog (everything in one cog file)
class MultiModCog(commands.Cog):
    """Unified moderation cog with AutoMod + AI moderation + related features"""
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # attach helpers to bot for convenience elsewhere
        if not hasattr(bot, "mod_db"):
            bot.mod_db = ModerationDB(DB_PATH)
            # connect will be awaited in cog_load
        self.db: ModerationDB = bot.mod_db
        self.embed = EmbedHelper()
        self._spam_cache: Dict[int, Dict[int, List[float]]] = {}  # guild_id -> {user_id: [timestamps]}
        # background task to unmute users at correct times
        self._unmute_task = None
        # If OpenAI configured, set key
        openai_key = os.getenv("OPENAI_API_KEY")
        if OPENAI_AVAILABLE and openai_key:
            openai.api_key = openai_key

    # Life-cycle hooks to ensure DB connected & background task started
    async def cog_load(self):
        await self.db.connect()
        if self._unmute_task is None:
            self._unmute_task = asyncio.create_task(self._temp_mute_watcher())

    async def cog_unload(self):
        if self._unmute_task:
            self._unmute_task.cancel()
            self._unmute_task = None
        await self.db.close()

    # ---------------------------
    # Helper: permission checking
    # ---------------------------
    async def _is_moderator(self, interaction_or_member) -> bool:
        """
        Accepts Interaction or Member (or Context).
        Checks per-guild mod_role_ids list.
        """
        member = None
        guild = None
        if isinstance(interaction_or_member, discord.Interaction):
            member = interaction_or_member.user
            guild = interaction_or_member.guild
            # Ensure Member object to inspect roles
            if isinstance(member, discord.User) and guild:
                member = guild.get_member(member.id)
        elif isinstance(interaction_or_member, discord.Member):
            member = interaction_or_member
            guild = member.guild
        elif hasattr(interaction_or_member, "author"):  # context
            member = interaction_or_member.author
            guild = interaction_or_member.guild
        else:
            return False
        if member is None or guild is None:
            return False
        cfg = await self.db.get_guild_config(guild.id)
        mod_roles = cfg.get("mod_role_ids", [])
        # owner bypass
        if guild.owner_id == member.id:
            return True
        # check roles
        for r in member.roles:
            if r.id in mod_roles:
                return True
        # also allow administrators as fallback
        try:
            if member.guild_permissions.administrator:
                return True
        except Exception:
            pass
        return False

    # ---------------------------
    # Logging helper
    # ---------------------------
    async def _log_to_channel(self, guild: discord.Guild, embed: discord.Embed):
        cfg = await self.db.get_guild_config(guild.id)
        log_id = cfg.get("log_channel_id")
        if log_id:
            ch = guild.get_channel(log_id)
            if ch and isinstance(ch, (discord.TextChannel, discord.Thread)):
                try:
                    await ch.send(embed=embed)
                except Exception:
                    pass

    # ---------------------------
    # Moderation helper actions
    # ---------------------------
    async def _warn_user(self, guild: discord.Guild, target: discord.Member, reason: str, moderator: Optional[discord.Member] = None):
        em = self.embed.warning("You were warned", f"You received a warning in **{guild.name}**.\n\n**Reason:** {reason}")
        try:
            await target.send(embed=em)
        except Exception:
            pass
        await self.db.add_infraction(guild.id, target.id, getattr(moderator, "id", None), "warn", reason)
        log = self.embed.warning("User Warned", f"{target.mention} was warned.", fields=[("Reason", reason, False)])
        await self._log_to_channel(guild, log)

    async def _delete_message_and_log(self, message: discord.Message, reason: str, moderator: Optional[discord.Member] = None):
        try:
            await message.delete()
        except Exception:
            pass
        await self.db.add_infraction(message.guild.id, message.author.id, getattr(moderator, "id", None), "delete", reason)
        log = self.embed.warning("Message Deleted", f"Message by {message.author.mention} deleted.", fields=[
            ("Reason", reason, False),
            ("Content", message.content[:1000] or "[no content]", False),
            ("Channel", message.channel.mention, True),
        ])
        await self._log_to_channel(message.guild, log)

    async def _temp_mute_member(self, guild: discord.Guild, member: discord.Member, duration_seconds: int, reason: str, moderator: Optional[discord.Member] = None):
        cfg = await self.db.get_guild_config(guild.id)
        # ensure muted role exists or create
        muted_role = None
        try:
            muted_role = guild.get_role(cfg.get("mute_role_id")) if cfg.get("mute_role_id") else None
            if muted_role is None:
                muted_role = await create_or_get_muted_role(guild, cfg)
                # save role id inside config
                await self.db.update_guild_config(guild.id, {"mute_role_id": muted_role.id})
        except Exception:
            pass

        # apply role
        try:
            await member.add_roles(muted_role, reason=f"Temp mute: {reason}")
        except Exception:
            # fallback: try to set communication disabled via timeout if available
            try:
                # uses timeout feature (requires Manage Roles / moderate members perms)
                await member.timeout_for(timedelta(seconds=duration_seconds), reason=reason)
            except Exception:
                pass

        # record in DB temp_mutes
        unmute_at = datetime.utcnow() + timedelta(seconds=duration_seconds)
        cfg = await self.db.get_guild_config(guild.id)
        tms = cfg.get("temp_mutes", [])
        tms.append({"user_id": member.id, "unmute_at": unmute_at.isoformat(), "reason": reason, "moderator": getattr(moderator, "id", None)})
        cfg["temp_mutes"] = tms
        await self.db.set_guild_config(guild.id, cfg)
        await self.db.add_infraction(guild.id, member.id, getattr(moderator, "id", None), "temp_mute", reason)

        # DM user and log
        em = self.embed.warning("You were temporarily muted", f"You were muted for **{duration_seconds} seconds** in **{guild.name}**.\n\n**Reason:** {reason}")
        try:
            await member.send(embed=em)
        except Exception:
            pass
        log = self.embed.warning("Temp Mute Applied", f"{member.mention} was temp-muted.", fields=[("Duration (s)", str(duration_seconds), True), ("Reason", reason, False)])
        await self._log_to_channel(guild, log)

    async def _unmute_member(self, guild: discord.Guild, user_id: int):
        cfg = await self.db.get_guild_config(guild.id)
        muted_role_id = cfg.get("mute_role_id")
        member = guild.get_member(user_id)
        if muted_role_id and member:
            role = guild.get_role(muted_role_id)
            if role:
                try:
                    await member.remove_roles(role, reason="Auto unmute")
                except Exception:
                    pass
        # remove from temp_mutes list
        tms = cfg.get("temp_mutes", [])
        new_tms = [t for t in tms if t.get("user_id") != user_id]
        cfg["temp_mutes"] = new_tms
        await self.db.set_guild_config(guild.id, cfg)
        # log
        log = self.embed.success("User Unmuted", f"<@{user_id}> has been unmuted (auto).")
        await self._log_to_channel(guild, log)

    # Background watcher to auto-unmute at appropriate time
    async def _temp_mute_watcher(self):
        await self.bot.wait_until_ready()
        while True:
            try:
                # iterate guilds in DB
                # For simplicity, we fetch guild configs by reading guild entries from sqlite
                async with self.db._lock:
                    cur = await self.db.conn.execute("SELECT guild_id, config FROM guilds")
                    rows = await cur.fetchall()
                    await cur.close()
                for guild_id, cfg_json in rows:
                    try:
                        cfg = json.loads(cfg_json)
                    except Exception:
                        continue
                    tms = cfg.get("temp_mutes", [])
                    now = datetime.utcnow()
                    changed = False
                    for tm in list(tms):
                        unmute_at = datetime.fromisoformat(tm["unmute_at"])
                        if unmute_at <= now:
                            guild = self.bot.get_guild(guild_id)
                            if guild:
                                await self._unmute_member(guild, tm["user_id"])
                            tms.remove(tm)
                            changed = True
                    if changed:
                        cfg["temp_mutes"] = tms
                        await self.db.set_guild_config(guild_id, cfg)
            except asyncio.CancelledError:
                return
            except Exception:
                # log exception to console and continue
                traceback.print_exc()
            # run every 15 seconds
            await asyncio.sleep(15)

    # ---------------------------
    # LISTENER: main on_message handler
    # ---------------------------
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        # ignore bots & DMs
        if message.author.bot or not message.guild:
            return

        guild = message.guild
        await self.db.ensure_guild(guild.id)
        cfg = await self.db.get_guild_config(guild.id)

        # 1) Per-guild banned words (basic contains check)
        content_lower = message.content.lower()
        for bad in cfg.get("banned_words", []):
            if bad.lower() in content_lower:
                # default action: delete + warn
                await self._delete_message_and_log(message, f"banned_word: {bad}")
                await self._warn_user(guild, message.author, f"Use of banned word: {bad}")
                return  # stop further checks

        # 2) AutoMod triggers configured
        for trig in cfg.get("automod_triggers", []):
            ttype = trig.get("trigger_type")
            pattern = trig.get("pattern")
            action = trig.get("action", "warn")
            try:
                matched = False
                if ttype == "contains":
                    if pattern.lower() in content_lower:
                        matched = True
                elif ttype == "starts_with":
                    if content_lower.startswith(pattern.lower()):
                        matched = True
                elif ttype == "ends_with":
                    if content_lower.endswith(pattern.lower()):
                        matched = True
                elif ttype == "regex":
                    if re.search(pattern, message.content, re.IGNORECASE):
                        matched = True
                elif ttype == "mentions_excessive":
                    # pattern is an int threshold
                    try:
                        thr = int(pattern)
                        if len(message.mentions) >= thr:
                            matched = True
                    except Exception:
                        matched = False
                elif ttype == "invite":
                    # block invites by simple substring detection
                    if "discord.gg/" in content_lower or "discord.com/invite/" in content_lower:
                        matched = True
                # you can extend more trigger types here
                if matched:
                    # execute the configured action (delete/warn/temp_mute/kick/ban)
                    reason = f"AutoMod trigger matched ({ttype}:{pattern})"
                    if action in ("delete", "warn", "delete_warn"):
                        await self._delete_message_and_log(message, reason)
                        if action in ("warn", "delete_warn"):
                            await self._warn_user(guild, message.author, reason)
                    if action.startswith("temp_mute"):
                        # action format: temp_mute:seconds (e.g., temp_mute:3600)
                        parts = action.split(":")
                        seconds = int(parts[1]) if len(parts) > 1 else 300
                        await self._temp_mute_member(guild, message.author, seconds, reason)
                    if action == "kick":
                        try:
                            await message.author.kick(reason=reason)
                            await self.db.add_infraction(guild.id, message.author.id, None, "kick", reason)
                            await self._log_to_channel(guild, self.embed.warning("User Kicked", f"{message.author.mention} was kicked for automod trigger.", fields=[("Reason", reason, False)]))
                        except Exception:
                            pass
                    if action == "ban":
                        try:
                            await message.author.ban(reason=reason)
                            await self.db.add_infraction(guild.id, message.author.id, None, "ban", reason)
                            await self._log_to_channel(guild, self.embed.warning("User Banned", f"{message.author.mention} was banned for automod trigger.", fields=[("Reason", reason, False)]))
                        except Exception:
                            pass
                    return  # after action, stop processing
            except Exception:
                # ignore faulty trigger definitions
                continue

        # 3) Spam detection (sliding window) => configurable per guild
        spam_cfg = cfg.get("spam_threshold", {"messages": 5, "seconds": 8})
        thr_msgs = int(spam_cfg.get("messages", 5))
        thr_secs = int(spam_cfg.get("seconds", 8))
        gcache = self._spam_cache.setdefault(guild.id, {})
        u_times = gcache.setdefault(message.author.id, [])
        now_ts = asyncio.get_event_loop().time()
        u_times.append(now_ts)
        # remove old timestamps
        window_start = now_ts - thr_secs
        u_times = [t for t in u_times if t >= window_start]
        gcache[message.author.id] = u_times
        if len(u_times) >= thr_msgs:
            # spam detected => default action: warn + delete
            await self._delete_message_and_log(message, f"spam: {len(u_times)} msgs in {thr_secs}s")
            await self._warn_user(guild, message.author, "Spam detected (too many messages).")
            # optional escalation: temp mute for 60 seconds
            await self._temp_mute_member(guild, message.author, 60, "Spam auto-temp-mute")
            # clear spam cache for user
            gcache[message.author.id] = []
            return

        # 4) Link protection: whitelist/blacklist
        if "http://" in content_lower or "https://" in content_lower:
            # check against whitelist and blacklist
            for url in re.findall(r"https?://\S+", message.content):
                if is_domain_in_list(url, cfg.get("links_blacklist", [])):
                    await self._delete_message_and_log(message, "link_blacklisted")
                    await self._warn_user(guild, message.author, "Posting blacklisted links is prohibited.")
                    return
                # if whitelist non-empty and domain not in whitelist -> action if configured:
                whitelist = cfg.get("links_whitelist", [])
                if whitelist and not is_domain_in_list(url, whitelist):
                    # treat as blocked link
                    await self._delete_message_and_log(message, "link_not_whitelisted")
                    await self._warn_user(guild, message.author, "Posting links outside the whitelist is not allowed.")
                    return

        # 5) NSFW attachments detection (if enabled)
        if cfg.get("nsfw_enabled", False) and message.attachments:
            for att in message.attachments:
                # simple stub check
                res = nsfw_check_stub(att.url)
                if res.get("nsfw"):
                    await self._delete_message_and_log(message, "nsfw_attachment")
                    await self._warn_user(guild, message.author, "Sharing NSFW content in this channel is prohibited.")
                    return

        # 6) Language enforcement
        enforced = cfg.get("language_enforced_channels", {})
        ch_allowed = enforced.get(str(message.channel.id))
        if ch_allowed:
            detected = detect_language_simple(message.content)
            if detected != ch_allowed and detected != "unknown":
                await self._delete_message_and_log(message, f"language_violation expected:{ch_allowed} detected:{detected}")
                await self._warn_user(guild, message.author, f"Please use the configured language ({ch_allowed}) in this channel.")
                return

        # 7) AI moderation integration (if enabled)
        if cfg.get("aimod_enabled", False) and OPENAI_AVAILABLE and os.getenv("OPENAI_API_KEY"):
            # skip mods & trusted
            if not await self._is_member_trusted_or_mod(message.author, cfg):
                try:
                    # Use OpenAI moderation endpoint synchronously in executor
                    loop = asyncio.get_event_loop()
                    result = await loop.run_in_executor(None, self._call_openai_moderation, message.content)
                    flagged = result.get("flagged", False)
                    categories = result.get("categories", {})
                    if flagged:
                        # escalate: delete + warn; if repeated infractions, temp mute or ban (simple heuristic: count infractions in DB)
                        await self._delete_message_and_log(message, "ai_moderation_flagged")
                        await self._warn_user(guild, message.author, "Your message was flagged by AI moderation.")
                        # check recent infractions count to escalate
                        rows = await self.db.get_recent_infractions(guild.id, limit=50)
                        user_infractions = sum(1 for r in rows if r[2] == message.author.id or r[1] == message.author.id or r[2] == message.author.id)
                        # naive escalation rules:
                        if user_infractions >= 3:
                            # temp mute for 10 minutes
                            await self._temp_mute_member(guild, message.author, 600, "Repeated AI-moderation infractions")
                        return
                except Exception:
                    # if OpenAI fails, do nothing
                    pass

    # small helper to check trusted or mod
    async def _is_member_trusted_or_mod(self, member: discord.Member, cfg: Dict[str, Any]) -> bool:
        if member.guild.owner_id == member.id:
            return True
        mod_ids = cfg.get("mod_role_ids", [])
        trusted_ids = cfg.get("trusted_role_ids", [])
        for r in member.roles:
            if r.id in mod_ids or r.id in trusted_ids:
                return True
        if member.guild_permissions.administrator:
            return True
        return False

    # Simple OpenAI moderation call (synchronous helper executed in threadpool)
    def _call_openai_moderation(self, text: str) -> Dict[str, Any]:
        if not OPENAI_AVAILABLE or not os.getenv("OPENAI_API_KEY"):
            return {"flagged": False, "categories": {}}
        try:
            # NOTE: OpenAI Python SDK shapes change; this code uses legacy Moderation API call shape
            resp = openai.Moderation.create(input=text)
            if "results" in resp and len(resp["results"]) > 0:
                r = resp["results"][0]
                return {"flagged": r.get("flagged", False), "categories": r.get("categories", {})}
            return {"flagged": False, "categories": {}}
        except Exception:
            traceback.print_exc()
            return {"flagged": False, "categories": {}}

    # ---------------------------
    # Slash Command Groups (combined similar commands) - uses app_commands
    # ---------------------------

    # Root group for moderation config and actions
    mod_group = app_commands.Group(name="mod", description="Moderation commands (AutoMod, AI, rules, spam, links, nsfw, roles, language, logs, dashboard, play tests)")

    # ----- AutoMod: triggers management (combined add/remove/list as subcommands) -----
    @mod_group.group(name="automod", description="Manage AutoMod triggers and settings", invoke_without_command=True)
    async def automod_root(self, interaction: discord.Interaction):
        await interaction.response.send_message(embed=self.embed.info("AutoMod", "Use subcommands: `trigger`, `config`."), ephemeral=True)

    @automod_root.group(name="trigger", description="Manage AutoMod triggers (add/remove/list)")
    async def automod_trigger_group(self, interaction: discord.Interaction):
        # placeholder, real subcommands below
        await interaction.response.defer(ephemeral=True)

    @automod_trigger_group.command(name="add", description="Add an AutoMod trigger")
    @app_commands.describe(trigger_type="Type: contains|starts_with|ends_with|regex|mentions_excessive|invite", pattern="Pattern or value", action="Action: delete|warn|delete_warn|temp_mute:<seconds>|kick|ban")
    async def automod_trigger_add(self, interaction: discord.Interaction, trigger_type: str, pattern: str, action: str):
        await interaction.response.defer(ephemeral=True)
        await self.db.ensure_guild(interaction.guild.id)
        if not await self._is_moderator(interaction):
            await interaction.followup.send(embed=self.embed.error("Permission denied", "You must be a moderator to manage AutoMod."), ephemeral=True)
            return
        cfg = await self.db.get_guild_config(interaction.guild.id)
        trigs = cfg.get("automod_triggers", [])
        trigs.append({"trigger_type": trigger_type, "pattern": pattern, "action": action})
        cfg["automod_triggers"] = trigs
        await self.db.set_guild_config(interaction.guild.id, cfg)
        await interaction.followup.send(embed=self.embed.success("Trigger added", f"Added automod trigger `{trigger_type}` -> `{pattern}` -> `{action}`"), ephemeral=True)

    @automod_trigger_group.command(name="remove", description="Remove AutoMod triggers that exactly match a pattern")
    @app_commands.describe(pattern="Exact pattern to remove")
    async def automod_trigger_remove(self, interaction: discord.Interaction, pattern: str):
        await interaction.response.defer(ephemeral=True)
        if not await self._is_moderator(interaction):
            await interaction.followup.send(embed=self.embed.error("Permission denied", "You must be a moderator to manage AutoMod."), ephemeral=True)
            return
        cfg = await self.db.get_guild_config(interaction.guild.id)
        trigs = cfg.get("automod_triggers", [])
        new_trigs = [t for t in trigs if t.get("pattern") != pattern]
        cfg["automod_triggers"] = new_trigs
        await self.db.set_guild_config(interaction.guild.id, cfg)
        await interaction.followup.send(embed=self.embed.success("Trigger(s) removed", f"Removed triggers matching `{pattern}`."), ephemeral=True)

    @automod_trigger_group.command(name="list", description="List AutoMod triggers for this guild")
    async def automod_trigger_list(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        cfg = await self.db.get_guild_config(interaction.guild.id)
        trigs = cfg.get("automod_triggers", [])
        if not trigs:
            await interaction.followup.send(embed=self.embed.info("Triggers", "No AutoMod triggers configured."), ephemeral=True)
            return
        desc = "\n".join(f"`{i+1}.` {t.get('trigger_type')} - `{t.get('pattern')}` → **{t.get('action')}**" for i, t in enumerate(trigs))
        await interaction.followup.send(embed=self.embed.info("AutoMod Triggers", desc), ephemeral=True)

    # ----- AI Moderation: enable/disable/test (combined) -----
    @mod_group.group(name="aimod", description="AI Moderation enable/disable/test")
    async def aimod_root(self, interaction: discord.Interaction):
        await interaction.response.send_message(embed=self.embed.info("AI Mod", "Use subcommands: `toggle`, `test`."), ephemeral=True)

    @aimod_root.command(name="toggle", description="Enable or disable AI moderation for this guild")
    @app_commands.describe(enabled="true to enable, false to disable")
    async def aimod_toggle(self, interaction: discord.Interaction, enabled: bool):
        await interaction.response.defer(ephemeral=True)
        if not await self._is_moderator(interaction):
            await interaction.followup.send(embed=self.embed.error("Permission denied", "You must be a moderator to manage AI moderation."), ephemeral=True)
            return
        cfg = await self.db.get_guild_config(interaction.guild.id)
        cfg["aimod_enabled"] = bool(enabled)
        await self.db.set_guild_config(interaction.guild.id, cfg)
        await interaction.followup.send(embed=self.embed.success("AI Moderation Updated", f"AI moderation set to `{enabled}`."), ephemeral=True)

    @aimod_root.command(name="test", description="Run a test message through AI moderation")
    @app_commands.describe(message="Message to analyze")
    async def aimod_test(self, interaction: discord.Interaction, message: str):
        await interaction.response.defer(ephemeral=True)
        if not OPENAI_AVAILABLE or not os.getenv("OPENAI_API_KEY"):
            await interaction.followup.send(embed=self.embed.error("OpenAI not configured", "OpenAI API key not found on host."), ephemeral=True)
            return
        # run sync call in executor
        loop = asyncio.get_event_loop()
        try:
            result = await loop.run_in_executor(None, self._call_openai_moderation, message)
        except Exception as e:
            await interaction.followup.send(embed=self.embed.error("OpenAI Error", str(e)), ephemeral=True)
            return
        flagged = result.get("flagged", False)
        categories = result.get("categories", {})
        fields = [("Flagged", str(flagged), True), ("Categories", ", ".join([k for k, v in categories.items() if v]) or "None", False)]
        msg = "Message flagged by AI moderation." if flagged else "Message appears clean."
        embed = self.embed.warning("AI Moderation Test" if flagged else "AI Moderation Test (Clean)", msg, fields=fields)
        await interaction.followup.send(embed=embed, ephemeral=True)

    # ----- Custom Rules: combined add/remove/list -----
    @mod_group.group(name="rule", description="Add, remove, list custom guild rules")
    async def rule_root(self, interaction: discord.Interaction):
        await interaction.response.send_message(embed=self.embed.info("Rules", "Use subcommands: `add`, `remove`, `list`."), ephemeral=True)

    @rule_root.command(name="add", description="Add a custom rule (trigger->action->message)")
    @app_commands.describe(trigger="Trigger type and pattern (format: type:pattern, e.g., contains:invite or regex:^badword$)", action="Action: warn/delete/temp_mute:<seconds>/kick/ban", message="Optional DM message to the user")
    async def rule_add(self, interaction: discord.Interaction, trigger: str, action: str, message: Optional[str] = None):
        await interaction.response.defer(ephemeral=True)
        if not await self._is_moderator(interaction):
            await interaction.followup.send(embed=self.embed.error("Permission denied", "You must be a moderator to manage rules."), ephemeral=True)
            return
        # parse trigger into type and pattern
        if ":" not in trigger:
            await interaction.followup.send(embed=self.embed.error("Invalid trigger", "Trigger must be in format type:pattern"), ephemeral=True)
            return
        ttype, pattern = trigger.split(":", 1)
        cfg = await self.db.get_guild_config(interaction.guild.id)
        rules = cfg.get("custom_rules", [])
        rules.append({"trigger_type": ttype, "pattern": pattern, "action": action, "message": message})
        cfg["custom_rules"] = rules
        await self.db.set_guild_config(interaction.guild.id, cfg)
        await interaction.followup.send(embed=self.embed.success("Rule added", f"Added custom rule `{trigger}` -> `{action}`."), ephemeral=True)

    @rule_root.command(name="remove", description="Remove a custom rule by pattern (exact)")
    @app_commands.describe(pattern="Exact pattern to remove (pattern only, not type:pattern)")
    async def rule_remove(self, interaction: discord.Interaction, pattern: str):
        await interaction.response.defer(ephemeral=True)
        if not await self._is_moderator(interaction):
            await interaction.followup.send(embed=self.embed.error("Permission denied", "You must be a moderator to manage rules."), ephemeral=True)
            return
        cfg = await self.db.get_guild_config(interaction.guild.id)
        rules = cfg.get("custom_rules", [])
        new = [r for r in rules if r.get("pattern") != pattern]
        cfg["custom_rules"] = new
        await self.db.set_guild_config(interaction.guild.id, cfg)
        await interaction.followup.send(embed=self.embed.success("Rule removed", f"Removed rules matching `{pattern}`."), ephemeral=True)

    @rule_root.command(name="list", description="List custom rules")
    async def rule_list(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        cfg = await self.db.get_guild_config(interaction.guild.id)
        rules = cfg.get("custom_rules", [])
        if not rules:
            await interaction.followup.send(embed=self.embed.info("Rules", "No custom rules configured."), ephemeral=True)
            return
        desc = "\n".join(f"`{i+1}.` {r.get('trigger_type')} - `{r.get('pattern')}` → **{r.get('action')}** • msg: {r.get('message') or 'none'}" for i, r in enumerate(rules))
        await interaction.followup.send(embed=self.embed.info("Custom Rules", desc), ephemeral=True)

    # ----- Spam & Links: combined spam config + links whitelist/blacklist -----
    @mod_group.group(name="spam", description="Spam protection settings")
    async def spam_root(self, interaction: discord.Interaction):
        await interaction.response.send_message(embed=self.embed.info("Spam Config", "Use subcommands: `config` and `test` (via /play)."), ephemeral=True)

    @spam_root.command(name="config", description="Set spam threshold: messages in seconds")
    @app_commands.describe(messages="Number of messages", seconds="Number of seconds window")
    async def spam_config(self, interaction: discord.Interaction, messages: int, seconds: int):
        await interaction.response.defer(ephemeral=True)
        if not await self._is_moderator(interaction):
            await interaction.followup.send(embed=self.embed.error("Permission denied", "You must be a moderator to change spam config."), ephemeral=True)
            return
        cfg = await self.db.get_guild_config(interaction.guild.id)
        cfg["spam_threshold"] = {"messages": max(1, messages), "seconds": max(1, seconds)}
        await self.db.set_guild_config(interaction.guild.id, cfg)
        await interaction.followup.send(embed=self.embed.success("Spam config updated", f"{messages} messages in {seconds} seconds."), ephemeral=True)

    @mod_group.group(name="links", description="Manage link whitelist / blacklist")
    async def links_root(self, interaction: discord.Interaction):
        await interaction.response.send_message(embed=self.embed.info("Links", "Use subcommands: `whitelist add/remove/list`, `blacklist add/remove/list`."), ephemeral=True)

    @links_root.command(name="whitelist_add", description="Whitelist a domain for links")
    @app_commands.describe(domain="Domain to allow (example: example.com)")
    async def links_whitelist_add(self, interaction: discord.Interaction, domain: str):
        await interaction.response.defer(ephemeral=True)
        if not await self._is_moderator(interaction):
            await interaction.followup.send(embed=self.embed.error("Permission denied", "You must be a moderator to modify link whitelist."), ephemeral=True)
            return
        cfg = await self.db.get_guild_config(interaction.guild.id)
        wl = cfg.get("links_whitelist", [])
        if domain.lower() not in [d.lower() for d in wl]:
            wl.append(domain)
        cfg["links_whitelist"] = wl
        await self.db.set_guild_config(interaction.guild.id, cfg)
        await interaction.followup.send(embed=self.embed.success("Whitelisted", f"Added `{domain}` to links whitelist."), ephemeral=True)

    @links_root.command(name="blacklist_add", description="Blacklist a domain for links")
    @app_commands.describe(domain="Domain to block (example: bad.com)")
    async def links_blacklist_add(self, interaction: discord.Interaction, domain: str):
        await interaction.response.defer(ephemeral=True)
        if not await self._is_moderator(interaction):
            await interaction.followup.send(embed=self.embed.error("Permission denied", "You must be a moderator to modify link blacklist."), ephemeral=True)
            return
        cfg = await self.db.get_guild_config(interaction.guild.id)
        bl = cfg.get("links_blacklist", [])
        if domain.lower() not in [d.lower() for d in bl]:
            bl.append(domain)
        cfg["links_blacklist"] = bl
        await self.db.set_guild_config(interaction.guild.id, cfg)
        await interaction.followup.send(embed=self.embed.success("Blacklisted", f"Added `{domain}` to links blacklist."), ephemeral=True)

    @links_root.command(name="list", description="List whitelist & blacklist domains")
    async def links_list(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        cfg = await self.db.get_guild_config(interaction.guild.id)
        wl = cfg.get("links_whitelist", [])
        bl = cfg.get("links_blacklist", [])
        fields = [("Whitelist", ", ".join(wl) or "None", False), ("Blacklist", ", ".join(bl) or "None", False)]
        await interaction.followup.send(embed=self.embed.info("Link Lists", "Current link whitelist/blacklist:" , fields=fields), ephemeral=True)

    # ----- NSFW scanner: enable/disable/test (stub) -----
    @mod_group.group(name="nsfw", description="NSFW scanner and config")
    async def nsfw_root(self, interaction: discord.Interaction):
        await interaction.response.send_message(embed=self.embed.info("NSFW", "Use subcommands: `toggle`, `test`."), ephemeral=True)

    @nsfw_root.command(name="toggle", description="Enable or disable NSFW scanner")
    async def nsfw_toggle(self, interaction: discord.Interaction, enabled: bool):
        await interaction.response.defer(ephemeral=True)
        if not await self._is_moderator(interaction):
            await interaction.followup.send(embed=self.embed.error("Permission denied", "Only moderators can change NSFW scanner setting."), ephemeral=True)
            return
        cfg = await self.db.get_guild_config(interaction.guild.id)
        cfg["nsfw_enabled"] = bool(enabled)
        await self.db.set_guild_config(interaction.guild.id, cfg)
        await interaction.followup.send(embed=self.embed.success("NSFW scanner updated", f"NSFW scanner set to `{enabled}`."), ephemeral=True)

    @nsfw_root.command(name="test", description="Test NSFW detection on an image URL (stub)")
    async def nsfw_test(self, interaction: discord.Interaction, image_url: str):
        await interaction.response.defer(ephemeral=True)
        res = nsfw_check_stub(image_url)
        if res.get("nsfw"):
            await interaction.followup.send(embed=self.embed.warning("NSFW Detected", f"Image flagged as NSFW (score {res.get('score')})"), ephemeral=True)
        else:
            await interaction.followup.send(embed=self.embed.success("NSFW Check", "Image appears clean (stub)."), ephemeral=True)

    # ----- Roles (behavior-based): combined auto/manual -----
    @mod_group.group(name="roles", description="Role assignment automation and manual assignment")
    async def roles_root(self, interaction: discord.Interaction):
        await interaction.response.send_message(embed=self.embed.info("Roles", "Use subcommands: `auto`, `manual`."), ephemeral=True)

    @roles_root.command(name="manual", description="Moderator manually assigns/removes a role")
    @app_commands.describe(target="Target user", role="Role to assign/remove", action="assign or remove")
    async def roles_manual(self, interaction: discord.Interaction, target: discord.Member, role: discord.Role, action: str):
        await interaction.response.defer(ephemeral=True)
        if not await self._is_moderator(interaction):
            await interaction.followup.send(embed=self.embed.error("Permission denied", "You must be a moderator to manually assign roles."), ephemeral=True)
            return
        try:
            if action == "assign":
                await target.add_roles(role, reason=f"Manual role assign by {interaction.user}")
                await interaction.followup.send(embed=self.embed.success("Role assigned", f"{role.mention} assigned to {target.mention}"), ephemeral=True)
            elif action == "remove":
                await target.remove_roles(role, reason=f"Manual role remove by {interaction.user}")
                await interaction.followup.send(embed=self.embed.success("Role removed", f"{role.mention} removed from {target.mention}"), ephemeral=True)
            else:
                await interaction.followup.send(embed=self.embed.error("Invalid action", "Action must be `assign` or `remove`."), ephemeral=True)
        except Exception as e:
            await interaction.followup.send(embed=self.embed.error("Error", str(e)), ephemeral=True)

    @roles_root.command(name="auto", description="Enable or disable automatic role assignment for behavior (stub)")
    @app_commands.describe(behavior="Behavior trigger e.g.: 'trusted' for good behavior or 'muted' for infractions", enabled="true to enable, false to disable")
    async def roles_auto(self, interaction: discord.Interaction, behavior: str, enabled: bool):
        await interaction.response.defer(ephemeral=True)
        if not await self._is_moderator(interaction):
            await interaction.followup.send(embed=self.embed.error("Permission denied", "Only moderators can configure auto-roles."), ephemeral=True)
            return
        # This is a stub: save config for future automation hooks
        cfg = await self.db.get_guild_config(interaction.guild.id)
        auto_roles = cfg.get("auto_roles", {})
        auto_roles[behavior] = bool(enabled)
        cfg["auto_roles"] = auto_roles
        await self.db.set_guild_config(interaction.guild.id, cfg)
        await interaction.followup.send(embed=self.embed.success("Auto-roles updated", f"Auto-role `{behavior}` set to `{enabled}`."), ephemeral=True)

    # ----- Language enforcement -----
    @mod_group.group(name="lang", description="Language enforcement per channel")
    async def lang_root(self, interaction: discord.Interaction):
        await interaction.response.send_message(embed=self.embed.info("Language enforcement", "Use subcommands: `set`, `list`."), ephemeral=True)

    @lang_root.command(name="set", description="Set allowed language for a channel (use 'none' to disable)")
    @app_commands.describe(channel="Channel to enforce", language="Language code (e.g., en, es) or 'none' to disable")
    async def lang_set(self, interaction: discord.Interaction, channel: discord.TextChannel, language: str):
        await interaction.response.defer(ephemeral=True)
        if not await self._is_moderator(interaction):
            await interaction.followup.send(embed=self.embed.error("Permission denied", "Only moderators can set language enforcement."), ephemeral=True)
            return
        cfg = await self.db.get_guild_config(interaction.guild.id)
        lec = cfg.get("language_enforced_channels", {})
        if language.lower() == "none":
            lec.pop(str(channel.id), None)
            msg = f"Disabled language enforcement for {channel.mention}."
        else:
            lec[str(channel.id)] = language
            msg = f"Set allowed language for {channel.mention} to `{language}`."
        cfg["language_enforced_channels"] = lec
        await self.db.set_guild_config(interaction.guild.id, cfg)
        await interaction.followup.send(embed=self.embed.success("Language updated", msg), ephemeral=True)

    @lang_root.command(name="list", description="List enforced channels & languages")
    async def lang_list(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        cfg = await self.db.get_guild_config(interaction.guild.id)
        lec = cfg.get("language_enforced_channels", {})
        if not lec:
            await interaction.followup.send(embed=self.embed.info("Language enforcement", "No channels are enforced."), ephemeral=True)
            return
        desc = "\n".join(f"<#{k}> → `{v}`" for k, v in lec.items())
        await interaction.followup.send(embed=self.embed.info("Enforced channels", desc), ephemeral=True)

    # ----- Logging & Dashboard (simple) -----
    @mod_group.group(name="logs", description="View recent moderation logs / infractions")
    async def logs_root(self, interaction: discord.Interaction):
        await interaction.response.send_message(embed=self.embed.info("Logs", "Use `view` to list recent infractions."), ephemeral=True)

    @logs_root.command(name="view", description="View recent infractions")
    @app_commands.describe(limit="Number of infractions to show (max 50)")
    async def logs_view(self, interaction: discord.Interaction, limit: int = 10):
        await interaction.response.defer(ephemeral=True)
        limit = max(1, min(50, limit))
        rows = await self.db.get_recent_infractions(interaction.guild.id, limit=limit)
        if not rows:
            await interaction.followup.send(embed=self.embed.info("Logs", "No infractions found."), ephemeral=True)
            return
        lines = []
        for r in rows:
            _id, user_id, moderator_id, action, reason, timestamp = r
            lines.append(f"**#{_id}** {action} • <@{user_id}> • by <@{moderator_id}> • {timestamp} • {reason or ''}")
        await interaction.followup.send(embed=self.embed.info("Recent infractions", "\n".join(lines[:10])), ephemeral=True)

    @mod_group.command(name="dashboard", description="Show basic moderation dashboard (top offenders, infractions count)")
    async def dashboard(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        rows = await self.db.get_recent_infractions(interaction.guild.id, limit=200)
        if not rows:
            await interaction.followup.send(embed=self.embed.info("Dashboard", "No infractions yet."), ephemeral=True)
            return
        # Count top offenders
        counts = {}
        for r in rows:
            _id, user_id, moderator_id, action, reason, timestamp = r
            counts[user_id] = counts.get(user_id, 0) + 1
        top = sorted(counts.items(), key=lambda x: x[1], reverse=True)[:5]
        top_text = "\n".join(f"<@{uid}> — {c} infractions" for uid, c in top) or "None"
        total = len(rows)
        embed = self.embed.info("Moderation Dashboard", f"Total infractions (recent window): {total}", fields=[("Top offenders", top_text, False)])
        await interaction.followup.send(embed=embed, ephemeral=True)

    # ----- Setup helpers: configure log channel, mod role, trusted role, banned words -----
    @mod_group.group(name="setup", description="Guild setup for log channel, mod role, trusted role, banned words")
    async def setup_root(self, interaction: discord.Interaction):
        await interaction.response.send_message(embed=self.embed.info("Setup", "Use subcommands: `log`, `modrole`, `trusted`, `bannedwords`."), ephemeral=True)

    @setup_root.command(name="log", description="Set moderation log channel")
    async def setup_log(self, interaction: discord.Interaction, channel: discord.TextChannel):
        await interaction.response.defer(ephemeral=True)
        if not (await self._is_moderator(interaction)) and interaction.user.id != interaction.guild.owner_id:
            await interaction.followup.send(embed=self.embed.error("Permission denied", "Only moderators or guild owner can set config."), ephemeral=True)
            return
        cfg = await self.db.get_guild_config(interaction.guild.id)
        cfg["log_channel_id"] = channel.id
        await self.db.set_guild_config(interaction.guild.id, cfg)
        await interaction.followup.send(embed=self.embed.success("Log channel set", f"Log channel set to {channel.mention}"), ephemeral=True)

    @setup_root.command(name="modrole", description="Set moderator role")
    async def setup_modrole(self, interaction: discord.Interaction, role: discord.Role):
        await interaction.response.defer(ephemeral=True)
        if not (await self._is_moderator(interaction)) and interaction.user.id != interaction.guild.owner_id:
            await interaction.followup.send(embed=self.embed.error("Permission denied", "Only moderators or guild owner can set config."), ephemeral=True)
            return
        cfg = await self.db.get_guild_config(interaction.guild.id)
        mods = cfg.get("mod_role_ids", [])
        if role.id not in mods:
            mods.append(role.id)
        cfg["mod_role_ids"] = mods
        await self.db.set_guild_config(interaction.guild.id, cfg)
        await interaction.followup.send(embed=self.embed.success("Moderator role updated", f"Role {role.mention} added to mod roles."), ephemeral=True)

    @setup_root.command(name="trusted", description="Add or remove a trusted role")
    @app_commands.describe(role="Role", enable="true to add, false to remove")
    async def setup_trusted(self, interaction: discord.Interaction, role: discord.Role, enable: bool):
        await interaction.response.defer(ephemeral=True)
        if not (await self._is_moderator(interaction)) and interaction.user.id != interaction.guild.owner_id:
            await interaction.followup.send(embed=self.embed.error("Permission denied", "Only moderators or guild owner can set config."), ephemeral=True)
            return
        cfg = await self.db.get_guild_config(interaction.guild.id)
        trusted = cfg.get("trusted_role_ids", [])
        if enable:
            if role.id not in trusted:
                trusted.append(role.id)
        else:
            trusted = [r for r in trusted if r != role.id]
        cfg["trusted_role_ids"] = trusted
        await self.db.set_guild_config(interaction.guild.id, cfg)
        await interaction.followup.send(embed=self.embed.success("Trusted roles updated", f"Role {role.mention} updated."), ephemeral=True)

    @setup_root.command(name="bannedwords", description="Set banned words list (comma-separated). Use 'none' to clear.")
    async def setup_bannedwords(self, interaction: discord.Interaction, words: str):
        await interaction.response.defer(ephemeral=True)
        if not (await self._is_moderator(interaction)) and interaction.user.id != interaction.guild.owner_id:
            await interaction.followup.send(embed=self.embed.error("Permission denied", "Only moderators or guild owner can set config."), ephemeral=True)
            return
        cfg = await self.db.get_guild_config(interaction.guild.id)
        if words.lower() == "none":
            cfg["banned_words"] = []
        else:
            cfg["banned_words"] = [w.strip() for w in words.split(",") if w.strip()]
        await self.db.set_guild_config(interaction.guild.id, cfg)
        await interaction.followup.send(embed=self.embed.success("Banned words updated", f"New banned words list set."), ephemeral=True)

    # ----- Single unified /play test command (covers profanity, spam, nsfw, ai, roles) -----
    @app_commands.command(name="play", description="Unified test/play command to simulate detections: profanity|spam|nsfw|ai|roles")
    @app_commands.describe(kind="profanity|spam|nsfw|ai|roles", content="Message text or image_url or user mention (for roles)")
    async def play(self, interaction: discord.Interaction, kind: str, content: Optional[str] = None):
        """Unified test command (usable by regular users). Combined similar test commands into one entrypoint."""
        await interaction.response.defer(ephemeral=True)
        kind = kind.lower()
        if kind == "profanity":
            # simulate profanity detection
            cfg = await self.db.get_guild_config(interaction.guild.id)
            bads = cfg.get("banned_words", [])
            content_l = (content or "").lower()
            triggered = [b for b in bads if b.lower() in content_l]
            if triggered:
                em = self.embed.warning("Simulated Profanity Trigger", f"Would trigger for: {', '.join(triggered)}", fields=[("Action (default)", "delete & warn", False)])
            else:
                em = self.embed.success("Simulated Profanity", "No banned words found in the test content.")
            await interaction.followup.send(embed=em, ephemeral=True)
            return

        if kind == "spam":
            cfg = await self.db.get_guild_config(interaction.guild.id)
            thr = cfg.get("spam_threshold", {})
            em = self.embed.info("Simulated Spam Test", f"Spam threshold: {thr.get('messages')} messages in {thr.get('seconds')} seconds.\nTo test real spam, send multiple messages quickly in a test channel.")
            await interaction.followup.send(embed=em, ephemeral=True)
            return

        if kind == "nsfw":
            if not content:
                await interaction.followup.send(embed=self.embed.error("No image", "Provide an image URL to test."), ephemeral=True)
                return
            res = nsfw_check_stub(content)
            if res.get("nsfw"):
                await interaction.followup.send(embed=self.embed.warning("NSFW Simulated", f"Image would be flagged (score {res.get('score')})."), ephemeral=True)
            else:
                await interaction.followup.send(embed=self.embed.success("NSFW Simulated", "Image would be allowed (stub)."), ephemeral=True)
            return

        if kind == "ai":
            if not content:
                await interaction.followup.send(embed=self.embed.error("No message", "Provide a message to analyze."), ephemeral=True)
                return
            if not OPENAI_AVAILABLE or not os.getenv("OPENAI_API_KEY"):
                await interaction.followup.send(embed=self.embed.error("No OpenAI", "OpenAI API not configured (AI testing unavailable)."), ephemeral=True)
                return
            loop = asyncio.get_event_loop()
            try:
                result = await loop.run_in_executor(None, self._call_openai_moderation, content)
                flagged = result.get("flagged", False)
                cats = result.get("categories", {})
                em = self.embed.warning("AI Test - Flagged" if flagged else "AI Test - Clean", f"Flagged: {flagged}", fields=[("Categories", ", ".join([k for k, v in cats.items() if v]) or "None", False)])
            except Exception as e:
                em = self.embed.error("OpenAI error", str(e))
            await interaction.followup.send(embed=em, ephemeral=True)
            return

        if kind == "roles":
            await interaction.followup.send(embed=self.embed.info("Role Test", "To test roles, use `roles manual` command with a target user and role."), ephemeral=True)
            return

        await interaction.followup.send(embed=self.embed.error("Unknown test kind", "Supported: profanity, spam, nsfw, ai, roles."), ephemeral=True)

# End of MultiModCog

# PART 5: standard setup entrypoint for extension
async def setup(bot: commands.Bot):
    cog = MultiModCog(bot)
    await bot.add_cog(cog)
    # ensure db connected
    await bot.mod_db.connect()
