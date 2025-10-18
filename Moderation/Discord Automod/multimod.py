# cogs/automod_ai.py
"""
Single-file cog: Discord AutoMod (native where possible) + AI moderation (OpenAI).
Designed for discord.py v2.5+ but includes fallbacks for older runtimes.
Features:
- Per-guild configuration persisted in SQLite (aiosqlite)
- Integration with Discord AutoMod (create/list/remove rules) when supported
- AI moderation using OpenAI Moderation endpoint (if OPENAI_API_KEY set)
- Unified management commands grouped under /mod
    - /mod automod rule add/remove/list (this will create native AutoMod rules if available)
    - /mod aimod toggle/test
    - /mod rules custom add/remove/list (DB-backed custom rules)
    - /mod spam config
    - /mod links whitelist/blacklist/list
    - /mod nsfw toggle/test (stub detection with optional external classifier)
    - /mod roles auto/manual
    - /mod lang set/list
    - /mod setup log/modrole/trusted/bannedwords
    - /mod logs view
    - /play <kind> combined test command
- Listeners:
    - on_message: runs DB automod -> AI moderation (if enabled)
    - on_automod_action_execution: attempts to receive automod events (if runtime supports event)
- Infractions stored and simple dashboard & escalation implemented
- Temp-mute via Muted role + background watcher persisted across restarts

Prereqs:
- python-dotenv, discord.py >= 2.5.1, aiosqlite, openai (optional)
- .env file: DISCORD_TOKEN, optionally OPENAI_API_KEY, BOT_OWNER_ID
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
from discord.ext import commands, tasks

import aiosqlite

# Attempt to import OpenAI; if missing, AI features will be disabled
try:
    import openai
    OPENAI_AVAILABLE = True
except Exception:
    OPENAI_AVAILABLE = False

# -----------------------
# Configuration constants
# -----------------------
DB_PATH = "automod_ai.db"
EMOJI_SUCCESS = "✅"
EMOJI_WARNING = "⚠️"
EMOJI_ERROR = "❌"
COLORS = {
    "success": 0x2ecc71,
    "warning": 0xf39c12,
    "error": 0xe74c3c,
    "info": 0x3498db,
}
DEFAULT_GUILD_CFG = {
    "log_channel_id": None,
    "mod_role_ids": [],
    "trusted_role_ids": [],
    "banned_words": ["damn", "hell"],
    "automod_triggers": [],   # fallback triggers for DB if native AutoMod not used
    "aimod_enabled": False,
    "spam_threshold": {"messages": 5, "seconds": 8},
    "links_whitelist": [],
    "links_blacklist": [],
    "nsfw_enabled": False,
    "language_enforced_channels": {},  # channel_id -> lang code
    "mute_role_id": None,
    "temp_mutes": [],   # list of {user_id, unmute_at_iso, reason, moderator}
    "infractions_preview": [],  # short list stored for quick display
    "custom_rules": [],  # custom DB-backed rules
}

# -----------------------
# Utility / DB Layer
# -----------------------
class AutomodDB:
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
            )
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
            )
        """)
        await self.conn.commit()

    async def ensure_guild(self, guild_id: int):
        async with self._lock:
            cur = await self.conn.execute("SELECT config FROM guilds WHERE guild_id = ?", (guild_id,))
            row = await cur.fetchone()
            await cur.close()
            if row is None:
                await self.set_guild_config(guild_id, DEFAULT_GUILD_CFG.copy())

    async def get_guild_config(self, guild_id: int) -> Dict[str, Any]:
        async with self._lock:
            cur = await self.conn.execute("SELECT config FROM guilds WHERE guild_id = ?", (guild_id,))
            row = await cur.fetchone()
            await cur.close()
            if row:
                try:
                    return json.loads(row[0])
                except Exception:
                    return DEFAULT_GUILD_CFG.copy()
            else:
                await self.set_guild_config(guild_id, DEFAULT_GUILD_CFG.copy())
                return DEFAULT_GUILD_CFG.copy()

    async def set_guild_config(self, guild_id: int, config: Dict[str, Any]):
        cfg_json = json.dumps(config)
        async with self._lock:
            await self.conn.execute(
                "INSERT INTO guilds (guild_id, config) VALUES (?, ?) ON CONFLICT(guild_id) DO UPDATE SET config=excluded.config",
                (guild_id, cfg_json)
            )
            await self.conn.commit()

    async def update_guild_config(self, guild_id: int, patch: Dict[str, Any]):
        cfg = await self.get_guild_config(guild_id)
        cfg.update(patch)
        await self.set_guild_config(guild_id, cfg)

    async def add_infraction(self, guild_id: int, user_id: int, moderator_id: Optional[int], action: str, reason: Optional[str]):
        async with self._lock:
            ts = datetime.utcnow().isoformat()
            await self.conn.execute(
                "INSERT INTO infractions (guild_id, user_id, moderator_id, action, reason, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                (guild_id, user_id, moderator_id, action, reason, ts)
            )
            await self.conn.commit()
            # maintain preview list in guild config
            cfg = await self.get_guild_config(guild_id)
            preview = cfg.get("infractions_preview", [])
            preview.append({"user_id": user_id, "action": action, "reason": reason, "created_at": ts})
            cfg["infractions_preview"] = preview[-200:]
            await self.set_guild_config(guild_id, cfg)

    async def get_recent_infractions(self, guild_id: int, limit: int = 20):
        async with self._lock:
            cur = await self.conn.execute(
                "SELECT id, user_id, moderator_id, action, reason, created_at FROM infractions WHERE guild_id = ? ORDER BY id DESC LIMIT ?",
                (guild_id, limit)
            )
            rows = await cur.fetchall()
            await cur.close()
            return rows

# -----------------------
# Embed helper
# -----------------------
class EmbedHelper:
    def moderation_embed(self, title: str, description: str, *, color_key: str = "info", fields: Optional[List[Tuple[str, str, bool]]] = None, footer: Optional[str] = None) -> discord.Embed:
        color = COLORS.get(color_key, COLORS["info"])
        em = discord.Embed(title=title, description=description, color=color, timestamp=datetime.utcnow())
        if fields:
            for name, value, inline in fields:
                em.add_field(name=name, value=value, inline=inline)
        if footer:
            em.set_footer(text=footer)
        return em

    def success(self, title: str, description: str, **kwargs):
        return self.moderation_embed(f"{EMOJI_SUCCESS} {title}", description, color_key="success", **kwargs)

    def warning(self, title: str, description: str, **kwargs):
        return self.moderation_embed(f"{EMOJI_WARNING} {title}", description, color_key="warning", **kwargs)

    def error(self, title: str, description: str, **kwargs):
        return self.moderation_embed(f"{EMOJI_ERROR} {title}", description, color_key="error", **kwargs)

    def info(self, title: str, description: str, **kwargs):
        return self.moderation_embed(title, description, color_key="info", **kwargs)

# -----------------------
# Small helpers
# -----------------------
def simple_detect_language(text: str) -> str:
    t = text.lower()
    if any(w in t for w in [" the ", " and ", " is ", " you "]): return "en"
    if any(w in t for w in [" el ", " la ", " y ", " que "]): return "es"
    return "unknown"

def extract_domains_from_content(content: str) -> List[str]:
    found = re.findall(r"https?://[^\s/$.?#].[^\s]*", content)
    domains = []
    for u in found:
        m = re.match(r"https?://([^/]+)", u)
        if m:
            domains.append(m.group(1).lower())
    return domains

def domain_in_list(url: str, domain_list: List[str]) -> bool:
    try:
        m = re.match(r"https?://([^/]+)", url)
        if not m: return False
        host = m.group(1).lower()
        for d in domain_list:
            if d.lower() in host:
                return True
    except Exception:
        return False
    return False

# -----------------------
# The Cog
# -----------------------
class AutoModAICog(commands.Cog, name="AutoMod+AI Moderation"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # DB attached to bot for reusability
        if not hasattr(bot, "automod_db"):
            bot.automod_db = AutomodDB(DB_PATH)
        self.db: AutomodDB = bot.automod_db
        self.embed = EmbedHelper()
        self._spam_cache: Dict[int, Dict[int, List[float]]] = {}  # guild_id -> user_id -> [timestamps]
        # background unmute task
        self._unmute_task: Optional[asyncio.Task] = None
        # OpenAI init if available
        if OPENAI_AVAILABLE and os.getenv("OPENAI_API_KEY"):
            openai.api_key = os.getenv("OPENAI_API_KEY")

    # lifecycle
    async def cog_load(self):
        await self.db.connect()
        if self._unmute_task is None:
            self._unmute_task = asyncio.create_task(self._temp_mute_watcher())

    async def cog_unload(self):
        if self._unmute_task:
            self._unmute_task.cancel()
            self._unmute_task = None
        await self.db.conn.close()

    # -----------------------
    # Permissions helper
    # -----------------------
    async def _is_moderator(self, member: discord.Member) -> bool:
        if member.guild is None:
            return False
        cfg = await self.db.get_guild_config(member.guild.id)
        mod_ids = cfg.get("mod_role_ids", [])
        if member.guild.owner_id == member.id:
            return True
        if member.guild_permissions.administrator:
            return True
        for r in member.roles:
            if r.id in mod_ids:
                return True
        return False

    async def _is_trusted(self, member: discord.Member, cfg: Dict[str, Any]) -> bool:
        if member.guild is None:
            return False
        trusted = cfg.get("trusted_role_ids", [])
        if member.guild.owner_id == member.id:
            return True
        for r in member.roles:
            if r.id in trusted:
                return True
        if member.guild_permissions.administrator:
            return True
        return False

    # -----------------------
    # Logging helper
    # -----------------------
    async def _log(self, guild: discord.Guild, embed: discord.Embed):
        cfg = await self.db.get_guild_config(guild.id)
        log_id = cfg.get("log_channel_id")
        if log_id:
            ch = guild.get_channel(log_id)
            if ch and isinstance(ch, (discord.TextChannel, discord.Thread)):
                try:
                    await ch.send(embed=embed)
                except Exception:
                    pass

    # -----------------------
    # Moderation actions
    # -----------------------
    async def _warn(self, guild: discord.Guild, member: discord.Member, reason: str, moderator: Optional[discord.Member] = None):
        em = self.embed.warning("You were warned", f"You received a warning in **{guild.name}**.\n\n**Reason:** {reason}")
        try:
            await member.send(embed=em)
        except Exception:
            pass
        await self.db.add_infraction(guild.id, member.id, getattr(moderator, "id", None), "warn", reason)
        await self._log(guild, self.embed.warning("User warned", f"{member.mention} was warned.", fields=[("Reason", reason, False)]))

    async def _delete_and_log(self, message: discord.Message, reason: str, moderator: Optional[discord.Member] = None):
        try:
            await message.delete()
        except Exception:
            pass
        await self.db.add_infraction(message.guild.id, message.author.id, getattr(moderator, "id", None), "delete", reason)
        await self._log(message.guild, self.embed.warning("Message deleted", f"Message by {message.author.mention} deleted.", fields=[("Reason", reason, False), ("Content", message.content[:1000] or "[no content]", False), ("Channel", message.channel.mention, True)]))

    async def _temp_mute(self, guild: discord.Guild, member: discord.Member, seconds: int, reason: str, moderator: Optional[discord.Member] = None):
        cfg = await self.db.get_guild_config(guild.id)
        # ensure muted role
        muted_role = None
        if cfg.get("mute_role_id"):
            muted_role = guild.get_role(cfg.get("mute_role_id"))
        if muted_role is None:
            # create Muted role and apply channel overwrites where possible
            try:
                muted_role = await guild.create_role(name="Muted", reason="AutoMod temp mute role")
            except Exception:
                muted_role = None
            if muted_role:
                # attempt to set send_messages=False in channels
                for ch in guild.text_channels:
                    try:
                        await ch.set_permissions(muted_role, send_messages=False, add_reactions=False)
                    except Exception:
                        pass
                cfg["mute_role_id"] = muted_role.id
                await self.db.set_guild_config(guild.id, cfg)
        # apply role if possible
        try:
            if muted_role:
                await member.add_roles(muted_role, reason=f"Temp mute: {reason}")
            else:
                # fallback: member.timeout_for if supported
                try:
                    await member.timeout_for(timedelta(seconds=seconds), reason=reason)
                except Exception:
                    pass
        except Exception:
            pass

        # store unmute time
        unmute_at = (datetime.utcnow() + timedelta(seconds=seconds)).isoformat()
        cfg = await self.db.get_guild_config(guild.id)
        tms = cfg.get("temp_mutes", [])
        tms.append({"user_id": member.id, "unmute_at": unmute_at, "reason": reason, "moderator": getattr(moderator, "id", None)})
        cfg["temp_mutes"] = tms
        await self.db.set_guild_config(guild.id, cfg)
        await self.db.add_infraction(guild.id, member.id, getattr(moderator, "id", None), "temp_mute", reason)
        await self._log(guild, self.embed.warning("Temp mute applied", f"{member.mention} was temp-muted.", fields=[("Duration sec", str(seconds), True), ("Reason", reason, False)]))
        try:
            await member.send(embed=self.embed.warning("You were muted", f"You have been muted for {seconds} seconds in **{guild.name}**.\n\nReason: {reason}"))
        except Exception:
            pass

    async def _unmute(self, guild: discord.Guild, user_id: int):
        cfg = await self.db.get_guild_config(guild.id)
        muted_role = guild.get_role(cfg.get("mute_role_id")) if cfg.get("mute_role_id") else None
        member = guild.get_member(user_id)
        if member and muted_role:
            try:
                await member.remove_roles(muted_role, reason="Auto unmute")
            except Exception:
                pass
        # remove from cfg
        tms = cfg.get("temp_mutes", [])
        new = [t for t in tms if t.get("user_id") != user_id]
        cfg["temp_mutes"] = new
        await self.db.set_guild_config(guild.id, cfg)
        await self._log(guild, self.embed.success("User unmuted", f"<@{user_id}> unmuted (auto)."))

    async def _escalation_check_and_act(self, guild: discord.Guild, member: discord.Member):
        # simplistic escalation: if infractions in recent 50 >= 3 -> temp mute 10 min, >=6 -> 1 day mute
        rows = await self.db.get_recent_infractions(guild.id, limit=100)
        count = sum(1 for r in rows if r[1] == member.id)
        if count >= 6:
            await self._temp_mute(guild, member, 86400, "Escalation: repeated infractions")
        elif count >= 3:
            await self._temp_mute(guild, member, 600, "Escalation: repeated infractions")

    # -----------------------
    # Background temp-mute watcher
    # -----------------------
    async def _temp_mute_watcher(self):
        await self.bot.wait_until_ready()
        while True:
            try:
                # iterate guild configs
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
                    if not tms:
                        continue
                    changed = False
                    now = datetime.utcnow()
                    for tm in list(tms):
                        try:
                            unmute_at = datetime.fromisoformat(tm["unmute_at"])
                        except Exception:
                            # try fallback parsing
                            unmute_at = datetime.fromisoformat(tm["unmute_at"][:-1]) if tm["unmute_at"].endswith("Z") else now
                        if unmute_at <= now:
                            guild = self.bot.get_guild(guild_id)
                            if guild:
                                await self._unmute(guild, tm["user_id"])
                            tms.remove(tm)
                            changed = True
                    if changed:
                        cfg["temp_mutes"] = tms
                        await self.db.set_guild_config(guild_id, cfg)
            except asyncio.CancelledError:
                return
            except Exception:
                traceback.print_exc()
            await asyncio.sleep(15)

    # -----------------------
    # OpenAI moderation wrapper
    # -----------------------
    def _call_openai_moderation(self, text: str) -> Dict[str, Any]:
        # Note: OpenAI SDK shape can vary. This code uses legacy / current moderation call pattern.
        # If your installed SDK differs, update this call accordingly.
        if not OPENAI_AVAILABLE or not os.getenv("OPENAI_API_KEY"):
            return {"flagged": False, "categories": {}}
        try:
            resp = openai.Moderation.create(input=text)
            if "results" in resp and len(resp["results"]) > 0:
                r = resp["results"][0]
                return {"flagged": r.get("flagged", False), "categories": r.get("categories", {}), "raw": r}
            # fallback
            return {"flagged": False, "categories": {}}
        except Exception:
            traceback.print_exc()
            return {"flagged": False, "categories": {}}

    # -----------------------
    # Native Discord AutoMod helpers (create/list/remove) - best-effort
    # -----------------------
    async def try_create_native_automod_rule(self, guild: discord.Guild, name: str, event_type: str, trigger_metadata: Dict[str, Any], actions: List[Dict[str, Any]]) -> Optional[discord.AutoModRule]:
        """
        Attempt to create a native Discord AutoMod rule using guild.create_auto_moderation_rule or similar.
        If your discord.py supports AutoMod, this will create a rule (requires MANAGE_GUILD).
        event_type e.g. "message_send", triggers use AutoModTriggerType - but here we pass data via trigger_metadata.
        This function uses try/except because different discord.py versions have different method names/signatures.
        """
        try:
            # modern discord.py might expose create_automod_rule or create_auto_moderation_rule
            create_fn = getattr(guild, "create_automod_rule", None) or getattr(guild, "create_auto_moderation_rule", None)
            if create_fn:
                # Many runtimes expect specific enumerations; do best-effort shape
                rule = await create_fn(
                    name=name,
                    event_type=discord.AutoModEventType.message_send,  # using enum if available
                    trigger_type=trigger_metadata.get("trigger_type"),
                    trigger_metadata=trigger_metadata.get("metadata", {}),
                    actions=actions,
                    enabled=True,
                    exempt_roles=trigger_metadata.get("exempt_roles", []),
                    exempt_channels=trigger_metadata.get("exempt_channels", [])
                )
                return rule
        except Exception:
            # if anything fails, just print and return None
            traceback.print_exc()
            return None
        return None

    async def try_list_native_automod_rules(self, guild: discord.Guild) -> Optional[List[Any]]:
        try:
            # some runtimes provide guild.automod_rules property or method
            if hasattr(guild, "automod_rules"):
                r = getattr(guild, "automod_rules")
                if callable(r):
                    return await r()
                else:
                    return r
        except Exception:
            traceback.print_exc()
        return None

    async def try_delete_native_automod_rule(self, guild: discord.Guild, rule_id: int) -> bool:
        try:
            # try guild.delete_automod_rule or delete_auto_moderation_rule
            fn = getattr(guild, "delete_automod_rule", None) or getattr(guild, "delete_auto_moderation_rule", None)
            if fn:
                await fn(rule_id)
                return True
        except Exception:
            traceback.print_exc()
        return False

    # -----------------------
    # Listener: AutoMod events (if runtime supports specific events)
    # -----------------------
    # NOTE: discord.py may expose events like on_automod_rule_create or on_automod_action_execution.
    # We'll add a generic handler for 'on_automod_action_execution' name commonly used; if your runtime uses another
    # event name, you can implement it similarly.
    @commands.Cog.listener()
    async def on_automod_action_execution(self, execution):
        """
        Best-effort listener for native AutoMod action events.
        execution typically contains fields: guild_id, rule_id, action, matched_content, user_id, channel_id
        This is runtime-dependent; if not available, this listener may not be called.
        """
        try:
            # Try to parse common fields; this is necessarily flexible due to API differences.
            guild = self.bot.get_guild(execution.guild_id)
            if not guild:
                return
            # Build a log embed
            fields = []
            try:
                fields.append(("Rule ID", str(execution.rule_id), True))
            except Exception:
                pass
            try:
                fields.append(("Action Type", str(execution.action.type), True))
            except Exception:
                pass
            try:
                fields.append(("Matched Content", str(getattr(execution, "matched_content", "[unknown]")), False))
            except Exception:
                pass
            await self._log(guild, self.embed.warning("Discord AutoMod: action executed", f"AutoMod rule executed in {guild.name}.", fields=fields))
        except Exception:
            traceback.print_exc()

    # -----------------------
    # Primary message listener: DB automod triggers -> AI moderation integration
    # -----------------------
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return
        guild = message.guild
        await self.db.ensure_guild(guild.id)
        cfg = await self.db.get_guild_config(guild.id)

        # 1) Banned words check (DB)
        content_lower = message.content.lower()
        for bad in cfg.get("banned_words", []):
            if bad.lower() in content_lower:
                await self._delete_and_log(message, f"banned_word: {bad}")
                await self._warn(guild, message.author, f"Use of banned word: {bad}")
                await self._escalation_check_and_act(guild, message.author)
                return

        # 2) Custom DB rules
        for r in cfg.get("custom_rules", []):
            ttype = r.get("trigger_type")
            pattern = r.get("pattern")
            action = r.get("action", "warn")
            matched = False
            if ttype == "contains":
                if pattern.lower() in content_lower: matched = True
            elif ttype == "regex":
                try:
                    if re.search(pattern, message.content, re.IGNORECASE): matched = True
                except Exception:
                    matched = False
            elif ttype == "invite":
                if "discord.gg/" in content_lower or "discord.com/invite/" in content_lower: matched = True
            if matched:
                # execute action
                reason = f"custom_rule: {ttype}:{pattern}"
                if "delete" in action:
                    await self._delete_and_log(message, reason)
                if "warn" in action:
                    await self._warn(guild, message.author, reason)
                if action.startswith("temp_mute"):
                    parts = action.split(":")
                    sec = int(parts[1]) if len(parts) > 1 else 300
                    await self._temp_mute(guild, message.author, sec, reason)
                if action == "kick":
                    try:
                        await message.author.kick(reason=reason)
                        await self.db.add_infraction(guild.id, message.author.id, None, "kick", reason)
                        await self._log(guild, self.embed.warning("User kicked", f"{message.author.mention} kicked for custom rule.", fields=[("Reason", reason, False)]))
                    except Exception:
                        pass
                if action == "ban":
                    try:
                        await message.author.ban(reason=reason)
                        await self.db.add_infraction(guild.id, message.author.id, None, "ban", reason)
                        await self._log(guild, self.embed.warning("User banned", f"{message.author.mention} banned for custom rule.", fields=[("Reason", reason, False)]))
                    except Exception:
                        pass
                return

        # 3) Spam detection (sliding window)
        spam_cfg = cfg.get("spam_threshold", {"messages": 5, "seconds": 8})
        thr_msgs = int(spam_cfg.get("messages", 5))
        thr_secs = int(spam_cfg.get("seconds", 8))
        gcache = self._spam_cache.setdefault(guild.id, {})
        u_times = gcache.setdefault(message.author.id, [])
        now_ts = asyncio.get_event_loop().time()
        u_times.append(now_ts)
        window_start = now_ts - thr_secs
        u_times = [t for t in u_times if t >= window_start]
        gcache[message.author.id] = u_times
        if len(u_times) >= thr_msgs:
            await self._delete_and_log(message, f"spam: {len(u_times)} msgs in {thr_secs}s")
            await self._warn(guild, message.author, "Spam detected (too many messages).")
            await self._temp_mute(guild, message.author, 60, "Spam auto-temp-mute")
            gcache[message.author.id] = []
            return

        # 4) Link protection
        if "http://" in content_lower or "https://" in content_lower:
            domains = extract_domains_from_content(message.content)
            for d in domains:
                if domain_in_list(f"https://{d}", cfg.get("links_blacklist", [])):
                    await self._delete_and_log(message, "link_blacklisted")
                    await self._warn(guild, message.author, "Posting blacklisted links is prohibited.")
                    await self._escalation_check_and_act(guild, message.author)
                    return
                wl = cfg.get("links_whitelist", [])
                if wl and not any(w.lower() in d for w in wl):
                    await self._delete_and_log(message, "link_not_whitelisted")
                    await self._warn(guild, message.author, "Posting links outside the whitelist is not allowed.")
                    return

        # 5) NSFW attachments if enabled (stub)
        if cfg.get("nsfw_enabled", False) and message.attachments:
            for att in message.attachments:
                if "nsfw" in att.filename.lower() or "nsfw" in att.url.lower():
                    await self._delete_and_log(message, "nsfw_attachment")
                    await self._warn(guild, message.author, "Sharing NSFW content in this channel is prohibited.")
                    await self._escalation_check_and_act(guild, message.author)
                    return

        # 6) Language enforcement
        lec = cfg.get("language_enforced_channels", {})
        allowed = lec.get(str(message.channel.id))
        if allowed:
            detected = simple_detect_language(message.content)
            if detected != allowed and detected != "unknown":
                await self._delete_and_log(message, f"language_violation expected:{allowed} detected:{detected}")
                await self._warn(guild, message.author, f"Please use the configured language ({allowed}) in this channel.")
                return

        # 7) AI moderation integration (OpenAI)
        if cfg.get("aimod_enabled", False) and OPENAI_AVAILABLE and os.getenv("OPENAI_API_KEY"):
            # skip moderators and trusted roles
            if await self._is_trusted(message.author, cfg):
                return
            try:
                loop = asyncio.get_event_loop()
                result = await loop.run_in_executor(None, self._call_openai_moderation, message.content)
                flagged = result.get("flagged", False)
                categories = result.get("categories", {})
                if flagged:
                    # default action: delete + warn; escalate if repeated
                    await self._delete_and_log(message, "ai_moderation_flagged")
                    await self._warn(guild, message.author, "Your message was flagged by AI moderation.")
                    await self._escalation_check_and_act(guild, message.author)
                    return
            except Exception:
                traceback.print_exc()
                # if AI fails, do nothing
                pass

    # -----------------------
    # Slash commands group (combined)
    # -----------------------
    mod = app_commands.Group(name="mod", description="Moderation commands (AutoMod + AI)")

    # Automod native management (best-effort)
    @mod.group(name="automod", description="Manage Discord AutoMod rules (native where supported) and fallback DB triggers")
    async def automod_root(self, interaction: discord.Interaction):
        await interaction.response.send_message(embed=self.embed.info("AutoMod", "Use subcommands: rule add/remove/list OR fallback triggers."), ephemeral=True)

    @automod_root.group(name="rule", description="Create/list/delete native AutoMod rules where supported")
    async def automod_rule_group(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

    @automod_rule_group.command(name="add", description="Create a native AutoMod rule (best-effort). You must have Manage Guild permission for the bot and caller must be mod.")
    @app_commands.describe(name="Name for the rule", trigger_type="Trigger type e.g. keyword, spam, mentions_excessive, invite", keywords="Comma-separated keywords (for keyword triggers)", action_type="Action: block_message|send_alert_message|timeout|block_message_and_alert", threshold="Optional threshold for mentions_excessive or spam")
    async def automod_rule_add(self, interaction: discord.Interaction, name: str, trigger_type: str, keywords: Optional[str], action_type: str, threshold: Optional[int] = None):
        await interaction.response.defer(ephemeral=True)
        # permission check
        if not await self._is_moderator(interaction.user if isinstance(interaction.user, discord.Member) else interaction.user):
            await interaction.followup.send(embed=self.embed.error("Permission denied", "You must be a moderator to create AutoMod rules."), ephemeral=True)
            return
        guild = interaction.guild
        if guild is None:
            await interaction.followup.send(embed=self.embed.error("Error", "Command must be invoked in a guild."), ephemeral=True)
            return

        # Build trigger metadata best-effort
        trigger_type_lower = trigger_type.lower()
        trigger_meta = {}
        try:
            if trigger_type_lower in ("keyword", "keywords", "keyword_phrase"):
                words = [w.strip() for w in (keywords or "").split(",") if w.strip()]
                trigger_meta = {"allow_list": False, "keywords": words}
            elif trigger_type_lower == "mentions_excessive":
                trigger_meta = {"mention_total_limit": threshold or 5}
            elif trigger_type_lower == "invite":
                trigger_meta = {"invites": True}
            elif trigger_type_lower == "spam":
                trigger_meta = {"threshold_seconds": threshold or 8}
            else:
                # fallback to keyword list if provided
                words = [w.strip() for w in (keywords or "").split(",") if w.strip()]
                trigger_meta = {"keywords": words}
        except Exception:
            trigger_meta = {}

        # Build actions (Discord AutoMod actions objects differ by runtime; we pass dicts)
        actions = [{"type": action_type}]
        # Try native creation; if fails, fallback to DB trigger
        native_rule = await self.try_create_native_automod_rule(guild, name, "message_send", {"trigger_type": trigger_type_lower, "metadata": trigger_meta}, actions)
        if native_rule:
            await interaction.followup.send(embed=self.embed.success("AutoMod rule created", f"Created native AutoMod rule `{name}` (ID: {getattr(native_rule, 'id', '?')})."), ephemeral=True)
            return
        else:
            # fallback: store as DB fallback trigger
            cfg = await self.db.get_guild_config(guild.id)
            trigs = cfg.get("automod_triggers", [])
            trigs.append({"trigger_type": trigger_type_lower, "pattern": keywords or "", "action": action_type})
            cfg["automod_triggers"] = trigs
            await self.db.set_guild_config(guild.id, cfg)
            await interaction.followup.send(embed=self.embed.warning("Fallback stored", "Native AutoMod creation failed — stored trigger in DB fallback."), ephemeral=True)
            return

    @automod_rule_group.command(name="list", description="List native AutoMod rules if available; otherwise show DB fallback triggers")
    async def automod_rule_list(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        guild = interaction.guild
        if guild is None:
            await interaction.followup.send(embed=self.embed.error("Error", "This command must be used in a guild."), ephemeral=True)
            return
        native = await self.try_list_native_automod_rules(guild)
        if native:
            lines = []
            for r in native:
                try:
                    lines.append(f"**{getattr(r, 'id', '?')}** • {getattr(r, 'name', str(r))} • enabled={getattr(r, 'enabled', '?')}")
                except Exception:
                    lines.append(str(r))
            await interaction.followup.send(embed=self.embed.info("Native AutoMod rules", "\n".join(lines)), ephemeral=True)
            return
        cfg = await self.db.get_guild_config(guild.id)
        trigs = cfg.get("automod_triggers", [])
        if not trigs:
            await interaction.followup.send(embed=self.embed.info("Rules", "No native rules and no DB fallback triggers exist."), ephemeral=True)
            return
        desc = "\n".join(f"- `{t.get('trigger_type')}` `{t.get('pattern')}` -> `{t.get('action')}`" for t in trigs)
        await interaction.followup.send(embed=self.embed.info("DB fallback AutoMod triggers", desc), ephemeral=True)
        return

    @automod_rule_group.command(name="remove", description="Remove native AutoMod rule by ID, or remove DB fallback triggers by pattern")
    @app_commands.describe(native_rule_id="Native rule ID (optional)", pattern="DB pattern (optional)")
    async def automod_rule_remove(self, interaction: discord.Interaction, native_rule_id: Optional[int] = None, pattern: Optional[str] = None):
        await interaction.response.defer(ephemeral=True)
        guild = interaction.guild
        if not await self._is_moderator(interaction.user if isinstance(interaction.user, discord.Member) else interaction.user):
            await interaction.followup.send(embed=self.embed.error("Permission denied", "You must be a moderator to remove rules."), ephemeral=True)
            return
        if guild is None:
            await interaction.followup.send(embed=self.embed.error("Error", "Command must be used in a guild."), ephemeral=True)
            return
        if native_rule_id:
            ok = await self.try_delete_native_automod_rule(guild, native_rule_id)
            if ok:
                await interaction.followup.send(embed=self.embed.success("Native rule removed", f"Deleted rule {native_rule_id}"), ephemeral=True)
            else:
                await interaction.followup.send(embed=self.embed.error("Failed", "Could not delete native rule — runtime may not support it or permissions missing."), ephemeral=True)
            return
        if pattern:
            cfg = await self.db.get_guild_config(guild.id)
            trigs = cfg.get("automod_triggers", [])
            new = [t for t in trigs if t.get("pattern") != pattern]
            cfg["automod_triggers"] = new
            await self.db.set_guild_config(guild.id, cfg)
            await interaction.followup.send(embed=self.embed.success("DB triggers updated", f"Removed triggers matching `{pattern}`."), ephemeral=True)
            return
        await interaction.followup.send(embed=self.embed.error("Missing arguments", "Provide native_rule_id or pattern to remove."), ephemeral=True)
        return

    # AIMOD (toggle/test)
    @mod.group(name="aimod", description="AI moderation: toggle and test (OpenAI)")
    async def aimod_root(self, interaction: discord.Interaction):
        await interaction.response.send_message(embed=self.embed.info("AI Moderation", "Use /mod aimod toggle or /mod aimod test."), ephemeral=True)

    @aimod_root.command(name="toggle", description="Enable or disable AI moderation for this guild")
    async def aimod_toggle(self, interaction: discord.Interaction, enabled: bool):
        await interaction.response.defer(ephemeral=True)
        if not await self._is_moderator(interaction.user if isinstance(interaction.user, discord.Member) else interaction.user):
            await interaction.followup.send(embed=self.embed.error("Permission denied", "You must be a moderator to configure AI moderation."), ephemeral=True)
            return
        cfg = await self.db.get_guild_config(interaction.guild.id)
        cfg["aimod_enabled"] = bool(enabled)
        await self.db.set_guild_config(interaction.guild.id, cfg)
        await interaction.followup.send(embed=self.embed.success("AI moderation updated", f"AI moderation set to `{enabled}`."), ephemeral=True)

    @aimod_root.command(name="test", description="Test a message string with AI moderation (OpenAI).")
    async def aimod_test(self, interaction: discord.Interaction, message: str):
        await interaction.response.defer(ephemeral=True)
        if not OPENAI_AVAILABLE or not os.getenv("OPENAI_API_KEY"):
            await interaction.followup.send(embed=self.embed.error("OpenAI not configured", "OPENAI_API_KEY missing on host."), ephemeral=True)
            return
        loop = asyncio.get_event_loop()
        try:
            result = await loop.run_in_executor(None, self._call_openai_moderation, message)
            flagged = result.get("flagged", False)
            cats = result.get("categories", {})
            fields = [("Flagged", str(flagged), True), ("Categories", ", ".join([k for k, v in cats.items() if v]) or "None", False)]
            await interaction.followup.send(embed=self.embed.warning("AI Test - Flagged" if flagged else "AI Test - Clean", f"Flagged: {flagged}", fields=fields), ephemeral=True)
        except Exception as e:
            await interaction.followup.send(embed=self.embed.error("OpenAI error", str(e)), ephemeral=True)

    # Custom rules (DB backed)
    @mod.group(name="rules", description="Manage DB-backed custom rules (add/remove/list)")
    async def rules_root(self, interaction: discord.Interaction):
        await interaction.response.send_message(embed=self.embed.info("Custom Rules", "Use subcommands: add/remove/list"), ephemeral=True)

    @rules_root.command(name="add", description="Add custom rule (format type:pattern). action examples: warn, delete, temp_mute:seconds, kick, ban")
    async def rules_add(self, interaction: discord.Interaction, trigger: str, action: str, dm_message: Optional[str] = None):
        await interaction.response.defer(ephemeral=True)
        if not await self._is_moderator(interaction.user if isinstance(interaction.user, discord.Member) else interaction.user):
            await interaction.followup.send(embed=self.embed.error("Permission denied", "You must be a moderator to add rules."), ephemeral=True)
            return
        if ":" not in trigger:
            await interaction.followup.send(embed=self.embed.error("Invalid trigger", "Trigger must be 'type:pattern' (e.g., contains:badword)."), ephemeral=True)
            return
        ttype, pattern = trigger.split(":", 1)
        cfg = await self.db.get_guild_config(interaction.guild.id)
        arr = cfg.get("custom_rules", [])
        arr.append({"trigger_type": ttype, "pattern": pattern, "action": action, "dm_message": dm_message})
        cfg["custom_rules"] = arr
        await self.db.set_guild_config(interaction.guild.id, cfg)
        await interaction.followup.send(embed=self.embed.success("Rule added", f"{ttype}:{pattern} -> {action}"), ephemeral=True)

    @rules_root.command(name="remove", description="Remove custom rule by exact pattern")
    async def rules_remove(self, interaction: discord.Interaction, pattern: str):
        await interaction.response.defer(ephemeral=True)
        if not await self._is_moderator(interaction.user if isinstance(interaction.user, discord.Member) else interaction.user):
            await interaction.followup.send(embed=self.embed.error("Permission denied", "You must be a moderator to remove rules."), ephemeral=True)
            return
        cfg = await self.db.get_guild_config(interaction.guild.id)
        new = [r for r in cfg.get("custom_rules", []) if r.get("pattern") != pattern]
        cfg["custom_rules"] = new
        await self.db.set_guild_config(interaction.guild.id, cfg)
        await interaction.followup.send(embed=self.embed.success("Rule removed", f"Removed rules matching `{pattern}`."), ephemeral=True)

    @rules_root.command(name="list", description="List custom rules")
    async def rules_list(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        cfg = await self.db.get_guild_config(interaction.guild.id)
        rules = cfg.get("custom_rules", [])
        if not rules:
            await interaction.followup.send(embed=self.embed.info("No rules", "No custom rules configured."), ephemeral=True)
            return
        desc = "\n".join(f"`{i+1}.` {r.get('trigger_type')}:`{r.get('pattern')}` -> **{r.get('action')}** • msg: {r.get('dm_message') or 'none'}" for i, r in enumerate(rules))
        await interaction.followup.send(embed=self.embed.info("Rules", desc), ephemeral=True)

    # Spam / links / nsfw / roles / language / setup / logs condensed (similar to prior implementation)
    # For brevity, these commands are combined and very similar to earlier examples - but still present and functional.

    @mod.command(name="spam_config", description="Set spam threshold: messages in seconds")
    async def spam_config(self, interaction: discord.Interaction, messages: int, seconds: int):
        await interaction.response.defer(ephemeral=True)
        if not await self._is_moderator(interaction.user if isinstance(interaction.user, discord.Member) else interaction.user):
            await interaction.followup.send(embed=self.embed.error("Permission denied", "You must be a moderator."), ephemeral=True)
            return
        cfg = await self.db.get_guild_config(interaction.guild.id)
        cfg["spam_threshold"] = {"messages": max(1, messages), "seconds": max(1, seconds)}
        await self.db.set_guild_config(interaction.guild.id, cfg)
        await interaction.followup.send(embed=self.embed.success("Spam config updated", f"{messages} messages in {seconds} seconds."), ephemeral=True)

    @mod.command(name="links", description="Manage link whitelist/blacklist actions")
    async def links(self, interaction: discord.Interaction, verb: str, domain: Optional[str] = None):
        await interaction.response.defer(ephemeral=True)
        if not await self._is_moderator(interaction.user if isinstance(interaction.user, discord.Member) else interaction.user):
            await interaction.followup.send(embed=self.embed.error("Permission denied", "You must be a moderator."), ephemeral=True)
            return
        cfg = await self.db.get_guild_config(interaction.guild.id)
        wl = cfg.get("links_whitelist", [])
        bl = cfg.get("links_blacklist", [])
        verb = verb.lower()
        if verb == "whitelist_add" and domain:
            if domain.lower() not in [d.lower() for d in wl]:
                wl.append(domain)
            cfg["links_whitelist"] = wl
            await self.db.set_guild_config(interaction.guild.id, cfg)
            await interaction.followup.send(embed=self.embed.success("Whitelisted", f"Added `{domain}`"), ephemeral=True)
            return
        if verb == "blacklist_add" and domain:
            if domain.lower() not in [d.lower() for d in bl]:
                bl.append(domain)
            cfg["links_blacklist"] = bl
            await self.db.set_guild_config(interaction.guild.id, cfg)
            await interaction.followup.send(embed=self.embed.success("Blacklisted", f"Added `{domain}`"), ephemeral=True)
            return
        if verb == "list":
            await interaction.followup.send(embed=self.embed.info("Links", f"Whitelist: {', '.join(wl) or 'None'}\nBlacklist: {', '.join(bl) or 'None'}"), ephemeral=True)
            return
        await interaction.followup.send(embed=self.embed.error("Invalid usage", "Use whitelist_add|blacklist_add|list"), ephemeral=True)

    @mod.command(name="nsfw", description="Enable/disable or test NSFW detection (stub)")
    async def nsfw(self, interaction: discord.Interaction, action: str, image_url: Optional[str] = None):
        await interaction.response.defer(ephemeral=True)
        if not await self._is_moderator(interaction.user if isinstance(interaction.user, discord.Member) else interaction.user):
            await interaction.followup.send(embed=self.embed.error("Permission denied", "You must be a moderator."), ephemeral=True)
            return
        cfg = await self.db.get_guild_config(interaction.guild.id)
        action = action.lower()
        if action in ("enable", "disable"):
            cfg["nsfw_enabled"] = (action == "enable")
            await self.db.set_guild_config(interaction.guild.id, cfg)
            await interaction.followup.send(embed=self.embed.success("NSFW updated", f"NSFW scanning set to {cfg['nsfw_enabled']}"), ephemeral=True)
            return
        if action == "test" and image_url:
            # simple stub: look for 'nsfw' substring
            flagged = "nsfw" in image_url.lower()
            await interaction.followup.send(embed=self.embed.warning("NSFW detected", "Image flagged (stub).") if flagged else self.embed.success("NSFW test", "Image clean (stub)."), ephemeral=True)
            return
        await interaction.followup.send(embed=self.embed.error("Invalid usage", "Use enable|disable|test <image_url>"), ephemeral=True)

    @mod.command(name="roles", description="Roles: manual assign/remove or toggle auto behavior (stub)")
    async def roles(self, interaction: discord.Interaction, sub: str, target: Optional[discord.Member] = None, role: Optional[discord.Role] = None, action: Optional[str] = None):
        await interaction.response.defer(ephemeral=True)
        if not await self._is_moderator(interaction.user if isinstance(interaction.user, discord.Member) else interaction.user):
            await interaction.followup.send(embed=self.embed.error("Permission denied", "You must be a moderator."), ephemeral=True)
            return
        sub = sub.lower()
        if sub == "manual" and target and role and action:
            if action == "assign":
                await target.add_roles(role, reason=f"Manual assign by {interaction.user}")
                await interaction.followup.send(embed=self.embed.success("Role assigned", f"{role.mention} -> {target.mention}"), ephemeral=True)
                return
            if action == "remove":
                await target.remove_roles(role, reason=f"Manual removal by {interaction.user}")
                await interaction.followup.send(embed=self.embed.success("Role removed", f"{role.mention} removed from {target.mention}"), ephemeral=True)
                return
        if sub == "auto" and role and action:
            # stub to set auto behavior; store in config
            cfg = await self.db.get_guild_config(interaction.guild.id)
            auto = cfg.get("auto_roles", {})
            auto[role.id] = (action == "enable")
            cfg["auto_roles"] = auto
            await self.db.set_guild_config(interaction.guild.id, cfg)
            await interaction.followup.send(embed=self.embed.success("Auto roles updated", f"{role.name} auto set to {auto[role.id]}"), ephemeral=True)
            return
        await interaction.followup.send(embed=self.embed.error("Invalid usage", "roles manual <user> <role> assign|remove OR roles auto <role> enable|disable"), ephemeral=True)

    @mod.command(name="lang", description="Language enforcement per channel: set/list")
    async def lang(self, interaction: discord.Interaction, sub: str, channel: Optional[discord.TextChannel] = None, language: Optional[str] = None):
        await interaction.response.defer(ephemeral=True)
        if not await self._is_moderator(interaction.user if isinstance(interaction.user, discord.Member) else interaction.user):
            await interaction.followup.send(embed=self.embed.error("Permission denied", "You must be a moderator."), ephemeral=True)
            return
        sub = sub.lower()
        cfg = await self.db.get_guild_config(interaction.guild.id)
        lec = cfg.get("language_enforced_channels", {})
        if sub == "set" and channel and language:
            if language.lower() == "none":
                lec.pop(str(channel.id), None)
                msg = f"Disabled language enforcement for {channel.mention}"
            else:
                lec[str(channel.id)] = language
                msg = f"Set language for {channel.mention} -> {language}"
            cfg["language_enforced_channels"] = lec
            await self.db.set_guild_config(interaction.guild.id, cfg)
            await interaction.followup.send(embed=self.embed.success("Language updated", msg), ephemeral=True)
            return
        if sub == "list":
            if not lec:
                await interaction.followup.send(embed=self.embed.info("Language enforcement", "No channels enforced."), ephemeral=True)
                return
            desc = "\n".join(f"<#{k}> -> `{v}`" for k, v in lec.items())
            await interaction.followup.send(embed=self.embed.info("Enforced channels", desc), ephemeral=True)
            return
        await interaction.followup.send(embed=self.embed.error("Invalid usage", "lang set <channel> <lang>|lang list"), ephemeral=True)

    # Setup subcommands to configure log channel, mod role, trusted role, banned words
    @mod.group(name="setup", description="Setup helpers: log/modrole/trusted/bannedwords")
    async def setup_root(self, interaction: discord.Interaction):
        await interaction.response.send_message(embed=self.embed.info("Setup", "Use subcommands to configure guild settings."), ephemeral=True)

    @setup_root.command(name="log", description="Set moderation log channel")
    async def setup_log(self, interaction: discord.Interaction, channel: discord.TextChannel):
        await interaction.response.defer(ephemeral=True)
        if not await self._is_moderator(interaction.user if isinstance(interaction.user, discord.Member) else interaction.user) and interaction.user.id != interaction.guild.owner_id:
            await interaction.followup.send(embed=self.embed.error("Permission denied", "Only moderators or guild owner can set config."), ephemeral=True)
            return
        cfg = await self.db.get_guild_config(interaction.guild.id)
        cfg["log_channel_id"] = channel.id
        await self.db.set_guild_config(interaction.guild.id, cfg)
        await interaction.followup.send(embed=self.embed.success("Log channel set", f"Log channel set to {channel.mention}"), ephemeral=True)

    @setup_root.command(name="modrole", description="Add a moderator role (this role can manage mod config)")
    async def setup_modrole(self, interaction: discord.Interaction, role: discord.Role):
        await interaction.response.defer(ephemeral=True)
        if not await self._is_moderator(interaction.user if isinstance(interaction.user, discord.Member) else interaction.user) and interaction.user.id != interaction.guild.owner_id:
            await interaction.followup.send(embed=self.embed.error("Permission denied", "Only moderators or guild owner can set config."), ephemeral=True)
            return
        cfg = await self.db.get_guild_config(interaction.guild.id)
        mods = cfg.get("mod_role_ids", [])
        if role.id not in mods:
            mods.append(role.id)
        cfg["mod_role_ids"] = mods
        await self.db.set_guild_config(interaction.guild.id, cfg)
        await interaction.followup.send(embed=self.embed.success("Mod role updated", f"{role.mention} added to mod roles."), ephemeral=True)

    @setup_root.command(name="trusted", description="Add/remove a trusted role")
    async def setup_trusted(self, interaction: discord.Interaction, role: discord.Role, enable: bool):
        await interaction.response.defer(ephemeral=True)
        if not await self._is_moderator(interaction.user if isinstance(interaction.user, discord.Member) else interaction.user) and interaction.user.id != interaction.guild.owner_id:
            await interaction.followup.send(embed=self.embed.error("Permission denied", "Only moderators or guild owner can set config."), ephemeral=True)
            return
        cfg = await self.db.get_guild_config(interaction.guild.id)
        trusted = cfg.get("trusted_role_ids", [])
        if enable:
            if role.id not in trusted: trusted.append(role.id)
        else:
            trusted = [r for r in trusted if r != role.id]
        cfg["trusted_role_ids"] = trusted
        await self.db.set_guild_config(interaction.guild.id, cfg)
        await interaction.followup.send(embed=self.embed.success("Trusted roles updated", f"{role.mention} updated."), ephemeral=True)

    @setup_root.command(name="bannedwords", description="Set banned words list (comma-separated). 'none' clears it.")
    async def setup_bannedwords(self, interaction: discord.Interaction, words: str):
        await interaction.response.defer(ephemeral=True)
        if not await self._is_moderator(interaction.user if isinstance(interaction.user, discord.Member) else interaction.user) and interaction.user.id != interaction.guild.owner_id:
            await interaction.followup.send(embed=self.embed.error("Permission denied", "Only moderators or guild owner can set config."), ephemeral=True)
            return
        cfg = await self.db.get_guild_config(interaction.guild.id)
        if words.lower() == "none":
            cfg["banned_words"] = []
        else:
            cfg["banned_words"] = [w.strip() for w in words.split(",") if w.strip()]
        await self.db.set_guild_config(interaction.guild.id, cfg)
        await interaction.followup.send(embed=self.embed.success("Banned words updated", "Banned words updated."), ephemeral=True)

    # Logs and dashboard
    @mod.command(name="logs", description="View recent infractions")
    async def logs(self, interaction: discord.Interaction, limit: int = 10):
        await interaction.response.defer(ephemeral=True)
        rows = await self.db.get_recent_infractions(interaction.guild.id, limit=max(1, min(50, limit)))
        if not rows:
            await interaction.followup.send(embed=self.embed.info("Logs", "No infractions found."), ephemeral=True)
            return
        lines = []
        for r in rows:
            _id, user_id, moderator_id, action, reason, created_at = r
            lines.append(f"**#{_id}** {action} • <@{user_id}> • by <@{moderator_id}> • {created_at} • {reason or ''}")
        await interaction.followup.send(embed=self.embed.info("Recent infractions", "\n".join(lines[:20])), ephemeral=True)

    @mod.command(name="dashboard", description="Basic moderation dashboard")
    async def dashboard(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        rows = await self.db.get_recent_infractions(interaction.guild.id, limit=200)
        if not rows:
            await interaction.followup.send(embed=self.embed.info("Dashboard", "No infractions yet."), ephemeral=True)
            return
        counts = {}
        for r in rows:
            _id, user_id, moderator_id, action, reason, created_at = r
            counts[user_id] = counts.get(user_id, 0) + 1
        top = sorted(counts.items(), key=lambda x: x[1], reverse=True)[:5]
        top_text = "\n".join(f"<@{uid}> — {c} infractions" for uid, c in top) or "None"
        embed = self.embed.info("Moderation Dashboard", f"Total infractions (recent): {len(rows)}", fields=[("Top offenders", top_text, False)])
        await interaction.followup.send(embed=embed, ephemeral=True)

    # -----------------------
    # Unified /play test command
    # -----------------------
    @app_commands.command(name="play", description="Unified test: profanity|spam|nsfw|ai|roles")
    async def play(self, interaction: discord.Interaction, kind: str, content: Optional[str] = None):
        await interaction.response.defer(ephemeral=True)
        kind = kind.lower()
        cfg = await self.db.get_guild_config(interaction.guild.id)
        if kind == "profanity":
            bads = cfg.get("banned_words", [])
            ts = [b for b in bads if b.lower() in (content or "").lower()]
            if ts:
                await interaction.followup.send(embed=self.embed.warning("Profanity test: would trigger", f"Found: {', '.join(ts)}\nAction: delete & warn"), ephemeral=True)
            else:
                await interaction.followup.send(embed=self.embed.success("Profanity test: clean", "No banned words detected"), ephemeral=True)
            return
        if kind == "spam":
            thr = cfg.get("spam_threshold", {})
            await interaction.followup.send(embed=self.embed.info("Spam test", f"Threshold: {thr.get('messages')} messages in {thr.get('seconds')} sec"), ephemeral=True)
            return
        if kind == "nsfw":
            if not content:
                await interaction.followup.send(embed=self.embed.error("Missing URL", "Provide an image URL for NSFW test."), ephemeral=True)
                return
            flagged = "nsfw" in content.lower()
            await interaction.followup.send(embed=self.embed.warning("NSFW test flagged", f"Score stub: 0.98") if flagged else self.embed.success("NSFW test clean", "Stub result: clean"), ephemeral=True)
            return
        if kind == "ai":
            if not content:
                await interaction.followup.send(embed=self.embed.error("Missing message", "Provide text to test."), ephemeral=True)
                return
            if not OPENAI_AVAILABLE or not os.getenv("OPENAI_API_KEY"):
                await interaction.followup.send(embed=self.embed.error("AI not configured", "OPENAI_API_KEY missing."), ephemeral=True)
                return
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(None, self._call_openai_moderation, content)
            flagged = result.get("flagged", False)
            cats = result.get("categories", {})
            await interaction.followup.send(embed=self.embed.warning("AI test flagged", f"Categories: {', '.join([k for k, v in cats.items() if v])}") if flagged else self.embed.success("AI test clean", "No issues detected"), ephemeral=True)
            return
        if kind == "roles":
            await interaction.followup.send(embed=self.embed.info("Role test", "Use /mod roles manual to test role assignment."), ephemeral=True)
            return
        await interaction.followup.send(embed=self.embed.error("Unknown kind", "Supported: profanity, spam, nsfw, ai, roles"), ephemeral=True)

# -----------------------
# Cog setup
# -----------------------
async def setup(bot: commands.Bot):
    cog = Multimod(bot)
    await bot.add_cog(cog)
    # ensure DB connected
    await bot.automod_db.connect()
