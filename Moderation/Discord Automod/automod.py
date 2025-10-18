# cogs/automod.py
import discord
import os
import re
import aiosqlite
import aiohttp
import json
import asyncio
import traceback
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List, Tuple
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv

load_dotenv()

# ----------------------------
# Config constants & defaults
# ----------------------------
DB_PATH = "automod_bot.db"
PERSPECTIVE_API_KEY = os.getenv("PERSPECTIVE_API_KEY")  # set in .env; leave blank to disable AI features
PERSPECTIVE_ENDPOINT = "https://commentanalyzer.googleapis.com/v1alpha1/comments:analyze"

EMOJI_SUCCESS = "✅"
EMOJI_WARNING = "⚠️"
EMOJI_ERROR = "❌"

COLORS = {
    "success": 0x2ecc71,
    "warning": 0xf39c12,
    "error": 0xe74c3c,
    "info": 0x3498db,
}

DEFAULT_GUILD_CONFIG = {
    "log_channel_id": None,
    "mod_role_ids": [],
    "trusted_role_ids": [],
    "banned_words": ["damn", "hell"],
    "automod_triggers": [],   # fallback DB triggers: {trigger_type, pattern, action}
    "aimod_enabled": False,
    "spam_threshold": {"messages": 5, "seconds": 8},
    "links_whitelist": [],
    "links_blacklist": [],
    "nsfw_enabled": False,
    "language_enforced_channels": {},  # channel_id (str) -> language code
    "mute_role_id": None,
    "temp_mutes": [],  # list of {user_id, unmute_at_iso, reason, moderator}
    "infractions_preview": [],
    "custom_rules": [],  # custom DB-backed rules
    "auto_roles": {},    # behavior -> role_id
}

# ----------------------------
# DB layer (aiosqlite)
# ----------------------------
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
        async with self._lock:
            cur = await self.conn.execute("SELECT config FROM guilds WHERE guild_id = ?", (guild_id,))
            row = await cur.fetchone()
            await cur.close()
            if row is None:
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
                await self.set_guild_config(guild_id, DEFAULT_GUILD_CONFIG.copy())
                return DEFAULT_GUILD_CONFIG.copy()

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
            # update preview in guild config (short list)
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

# ----------------------------
# Embed / UI helpers
# ----------------------------
class Embeds:
    def moderation_embed(self, title: str, description: str, *, color_key: str = "info",
                         fields: Optional[List[Tuple[str, str, bool]]] = None, footer: Optional[str] = None) -> discord.Embed:
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

# ----------------------------
# Small utilities (language detect stub, nsfw stub)
# ----------------------------
def simple_language_detect(text: str) -> str:
    # super-naive detection — replace with fasttext/langdetect in production
    t = text.lower()
    if any(w in t for w in (" the ", " and ", " is ", " you ")): return "en"
    if any(w in t for w in (" el ", " la ", " y ", " que ")): return "es"
    if any(w in t for w in (" le ", " la ", " est ", " et ")): return "fr"
    return "unknown"

def extract_domains(text: str) -> List[str]:
    found = re.findall(r"https?://[^\s/$.?#].[^\s]*", text)
    domains = []
    for u in found:
        m = re.match(r"https?://([^/]+)", u)
        if m:
            domains.append(m.group(1).lower())
    return domains

def domain_matches(domain: str, patterns: List[str]) -> bool:
    for p in patterns:
        if p.lower() in domain.lower():
            return True
    return False

def nsfw_stub_check(url: str) -> Dict[str, Any]:
    # detect 'nsfw' substring as an obvious stub; replace with real classifier
    return {"nsfw": "nsfw" in url.lower(), "score": 0.95 if "nsfw" in url.lower() else 0.02}

# ----------------------------
# Perspective API helper (async)
# ----------------------------
class PerspectiveClient:
    def __init__(self, api_key: Optional[str]):
        self.api_key = api_key
        self.endpoint = PERSPECTIVE_ENDPOINT
        self.session: Optional[aiohttp.ClientSession] = None

    async def ensure_session(self):
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession()

    async def close(self):
        if self.session and not self.session.closed:
            await self.session.close()

    async def analyze_text(self, text: str, attributes: Optional[List[str]] = None) -> Dict[str, Any]:
        """
        Call Perspective API to analyze text for toxicity/severe_toxicity/insult/identity_attack, etc.
        Returns the raw JSON response, or raises on network error.
        """
        if not self.api_key:
            return {"error": "no_api_key"}
        await self.ensure_session()
        if attributes is None:
            attributes = ["TOXICITY", "SEVERE_TOXICITY", "INSULT", "IDENTITY_ATTACK", "THREAT", "SEXUALLY_EXPLICIT"]
        payload = {
            "comment": {"text": text},
            "languages": ["en"],
            "requestedAttributes": {attr: {} for attr in attributes},
            "doNotStore": True,
        }
        params = {"key": self.api_key}
        try:
            async with self.session.post(self.endpoint, params=params, json=payload, timeout=15) as resp:
                if resp.status != 200:
                    text_body = await resp.text()
                    return {"error": f"status_{resp.status}", "body": text_body}
                js = await resp.json()
                return js
        except Exception as e:
            return {"error": str(e)}

# ----------------------------
# The Cog itself
# ----------------------------
class AutoModCog(commands.Cog):
    """Single-file unified AutoMod + AI moderation Cog."""
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # attach DB to bot for reuse if not present
        if not hasattr(bot, "automod_db"):
            bot.automod_db = AutomodDB(DB_PATH)
        self.db: AutomodDB = bot.automod_db
        self.emb = Embeds()
        self._spam_cache: Dict[int, Dict[int, List[float]]] = {}  # guild_id -> user_id -> [timestamps]
        self.perspective = PerspectiveClient(PERSPECTIVE_API_KEY)
        self._unmute_task: Optional[asyncio.Task] = None

    # Cog lifecycle
    async def cog_load(self):
        await self.db.connect()
        await self.perspective.ensure_session()
        if self._unmute_task is None:
            self._unmute_task = asyncio.create_task(self._temp_mute_watcher())

    async def cog_unload(self):
        if self._unmute_task:
            self._unmute_task.cancel()
            self._unmute_task = None
        await self.perspective.close()
        await self.db.conn.close()

    # ----------------------------
    # Permission & helper utilities
    # ----------------------------
    async def _is_mod_member(self, member: discord.Member) -> bool:
        if not member.guild:
            return False
        cfg = await self.db.get_guild_config(member.guild.id)
        mod_roles = cfg.get("mod_role_ids", [])
        if member.guild.owner_id == member.id:
            return True
        if member.guild_permissions.administrator:
            return True
        for r in member.roles:
            if r.id in mod_roles:
                return True
        return False

    async def _is_trusted(self, member: discord.Member, cfg: Optional[Dict[str, Any]] = None) -> bool:
        if not member.guild:
            return False
        if cfg is None:
            cfg = await self.db.get_guild_config(member.guild.id)
        trusted = cfg.get("trusted_role_ids", [])
        if member.guild.owner_id == member.id:
            return True
        for r in member.roles:
            if r.id in trusted:
                return True
        if member.guild_permissions.administrator:
            return True
        return False

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

    # Moderation actions
    async def _warn_user(self, guild: discord.Guild, target: discord.Member, reason: str, moderator: Optional[discord.Member] = None):
        em = self.emb.warning("You were warned", f"You were warned in **{guild.name}**.\n**Reason:** {reason}")
        try:
            await target.send(embed=em)
        except Exception:
            pass
        await self.db.add_infraction(guild.id, target.id, getattr(moderator, "id", None), "warn", reason)
        await self._log(guild, self.emb.warning("User warned", f"{target.mention} was warned.", fields=[("Reason", reason, False)]))

    async def _delete_message(self, message: discord.Message, reason: str, moderator: Optional[discord.Member] = None):
        try:
            await message.delete()
        except Exception:
            pass
        await self.db.add_infraction(message.guild.id, message.author.id, getattr(moderator, "id", None), "delete", reason)
        await self._log(message.guild, self.emb.warning("Message deleted", f"Deleted message by {message.author.mention}", fields=[("Reason", reason, False), ("Content", message.content[:1000] or "[no content]", False), ("Channel", message.channel.mention, True)]))

    async def _apply_temp_mute(self, guild: discord.Guild, member: discord.Member, seconds: int, reason: str, moderator: Optional[discord.Member] = None):
        cfg = await self.db.get_guild_config(guild.id)
        muted_role = None
        if cfg.get("mute_role_id"):
            muted_role = guild.get_role(cfg.get("mute_role_id"))
        if muted_role is None:
            try:
                muted_role = await guild.create_role(name="Muted", reason="Auto-created Muted role")
            except Exception:
                muted_role = None
            if muted_role:
                # attempt to set send_messages=False for text channels
                for ch in guild.text_channels:
                    try:
                        await ch.set_permissions(muted_role, send_messages=False, add_reactions=False)
                    except Exception:
                        pass
                cfg["mute_role_id"] = muted_role.id
                await self.db.set_guild_config(guild.id, cfg)
        try:
            if muted_role:
                await member.add_roles(muted_role, reason=f"Temp mute: {reason}")
            else:
                # fallback to timeout on supported runtimes as a best-effort
                try:
                    await member.timeout_for(timedelta(seconds=seconds), reason=reason)
                except Exception:
                    pass
        except Exception:
            pass
        # record temp mute
        unmute_at = (datetime.utcnow() + timedelta(seconds=seconds)).isoformat()
        cfg = await self.db.get_guild_config(guild.id)
        tms = cfg.get("temp_mutes", [])
        tms.append({"user_id": member.id, "unmute_at": unmute_at, "reason": reason, "moderator": getattr(moderator, "id", None)})
        cfg["temp_mutes"] = tms
        await self.db.set_guild_config(guild.id, cfg)
        await self.db.add_infraction(guild.id, member.id, getattr(moderator, "id", None), "temp_mute", reason)
        await self._log(guild, self.emb.warning("Temp mute applied", f"{member.mention} muted for {seconds} seconds", fields=[("Reason", reason, False)]))
        try:
            await member.send(embed=self.emb.warning("You were temporarily muted", f"You were muted for {seconds} seconds in **{guild.name}**.\nReason: {reason}"))
        except Exception:
            pass

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
        new = [t for t in tms if t.get("user_id") != user_id]
        cfg["temp_mutes"] = new
        await self.db.set_guild_config(guild.id, cfg)
        await self._log(guild, self.emb.success("User unmuted", f"<@{user_id}> unmuted (auto)."))

    # Escalation policy (naive)
    async def _escalate_if_needed(self, guild: discord.Guild, member: discord.Member):
        rows = await self.db.get_recent_infractions(guild.id, limit=100)
        user_count = sum(1 for r in rows if r[1] == member.id)
        if user_count >= 6:
            await self._apply_temp_mute(guild, member, 86400, "Escalation: repeated infractions")
        elif user_count >= 3:
            await self._apply_temp_mute(guild, member, 600, "Escalation: repeated infractions")

    # ----------------------------
    # Background task: unmute watcher
    # ----------------------------
    async def _temp_mute_watcher(self):
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
                            # fallback parsing
                            try:
                                unmute_at = datetime.fromisoformat(tm["unmute_at"].replace("Z", "+00:00"))
                            except Exception:
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

    # ----------------------------
    # Native Discord AutoMod helpers (best-effort)
    # ----------------------------
    async def try_create_native_rule(self, guild: discord.Guild, name: str, trigger_type: str, trigger_data: Dict[str, Any], actions: List[Dict[str, Any]]):
        """
        Attempt to create a native AutoMod rule. discord.py runtimes vary; this is best-effort.
        If it fails or not supported, returns None.
        """
        try:
            # many implementations provide guild.create_auto_moderation_rule or create_automod_rule
            create_fn = getattr(guild, "create_auto_moderation_rule", None) or getattr(guild, "create_automod_rule", None)
            if create_fn:
                # Build parameters best-effort; real runtime might need discord.AutoModTriggerType enums
                rule = await create_fn(
                    name=name,
                    event_type=discord.AutoModEventType.message_send,
                    trigger_type=trigger_type,
                    trigger_metadata=trigger_data,
                    actions=actions,
                    enabled=True,
                )
                return rule
        except Exception:
            traceback.print_exc()
            return None
        return None

    async def try_list_native_rules(self, guild: discord.Guild):
        try:
            # some runtimes provide guild.automod_rules or fetch_auto_moderation_rules
            getter = getattr(guild, "automod_rules", None)
            if getter:
                if callable(getter):
                    return await getter()
                return getter
            # fallback: guild.fetch_auto_moderation_rules?
            fetcher = getattr(guild, "fetch_auto_moderation_rules", None)
            if fetcher:
                return await fetcher()
        except Exception:
            traceback.print_exc()
        return None

    async def try_delete_native_rule(self, guild: discord.Guild, rule_id: int) -> bool:
        try:
            delete_fn = getattr(guild, "delete_auto_moderation_rule", None) or getattr(guild, "delete_automod_rule", None)
            if delete_fn:
                await delete_fn(rule_id)
                return True
        except Exception:
            traceback.print_exc()
        return False

    # ----------------------------
    # Primary message handler: DB triggers -> AI moderation
    # ----------------------------
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return
        guild = message.guild
        await self.db.ensure_guild(guild.id)
        cfg = await self.db.get_guild_config(guild.id)
        content = message.content or ""

        # 1) Banned words
        for bad in cfg.get("banned_words", []):
            if bad.lower() in content.lower():
                await self._delete_message(message, f"banned_word:{bad}")
                await self._warn_user(guild, message.author, f"Use of banned word: {bad}")
                await self._escalate_if_needed(guild, message.author)
                return

        # 2) Custom DB rules
        for r in cfg.get("custom_rules", []):
            ttype = r.get("trigger_type")
            pattern = r.get("pattern")
            action = r.get("action", "warn")
            matched = False
            if ttype == "contains":
                if pattern.lower() in content.lower():
                    matched = True
            elif ttype == "regex":
                try:
                    if re.search(pattern, content, re.IGNORECASE):
                        matched = True
                except re.error:
                    matched = False
            elif ttype == "invite":
                if "discord.gg/" in content.lower() or "discord.com/invite/" in content.lower():
                    matched = True
            if matched:
                reason = f"custom_rule:{ttype}:{pattern}"
                if "delete" in action:
                    await self._delete_message(message, reason)
                if "warn" in action:
                    await self._warn_user(guild, message.author, reason)
                if action.startswith("temp_mute"):
                    parts = action.split(":")
                    sec = int(parts[1]) if len(parts) > 1 else 300
                    await self._apply_temp_mute(guild, message.author, sec, reason)
                if action == "kick":
                    try:
                        await message.author.kick(reason=reason)
                        await self.db.add_infraction(guild.id, message.author.id, None, "kick", reason)
                        await self._log(guild, self.emb.warning("User kicked", f"{message.author.mention} kicked for custom rule.", fields=[("Reason", reason, False)]))
                    except Exception:
                        pass
                if action == "ban":
                    try:
                        await message.author.ban(reason=reason)
                        await self.db.add_infraction(guild.id, message.author.id, None, "ban", reason)
                        await self._log(guild, self.emb.warning("User banned", f"{message.author.mention} banned for custom rule.", fields=[("Reason", reason, False)]))
                    except Exception:
                        pass
                return

        # 3) Spam detection (sliding)
        spam_cfg = cfg.get("spam_threshold", {"messages": 5, "seconds": 8})
        thr_msgs = int(spam_cfg.get("messages", 5))
        thr_secs = int(spam_cfg.get("seconds", 8))
        gcache = self._spam_cache.setdefault(guild.id, {})
        ucache = gcache.setdefault(message.author.id, [])
        now_ts = asyncio.get_event_loop().time()
        ucache.append(now_ts)
        window_start = now_ts - thr_secs
        ucache = [t for t in ucache if t >= window_start]
        gcache[message.author.id] = ucache
        if len(ucache) >= thr_msgs:
            await self._delete_message(message, f"spam:{len(ucache)} in {thr_secs}s")
            await self._warn_user(guild, message.author, "Spam detected (too many messages).")
            await self._apply_temp_mute(guild, message.author, 60, "Spam auto-mute")
            gcache[message.author.id] = []
            return

        # 4) Link protection
        if "http://" in content.lower() or "https://" in content.lower():
            domains = extract_domains(content)
            for d in domains:
                if domain_matches(d, cfg.get("links_blacklist", [])):
                    await self._delete_message(message, "link_blacklisted")
                    await self._warn_user(guild, message.author, "Posting blacklisted links is prohibited.")
                    await self._escalate_if_needed(guild, message.author)
                    return
            wl = cfg.get("links_whitelist", [])
            if wl:
                allowed_any = any(domain_matches(d, wl) for d in domains)
                if not allowed_any and domains:
                    await self._delete_message(message, "link_not_whitelisted")
                    await self._warn_user(guild, message.author, "Posting links outside the whitelist is not allowed.")
                    return

        # 5) NSFW attachments (stub)
        if cfg.get("nsfw_enabled", False) and message.attachments:
            for att in message.attachments:
                check = nsfw_stub_check(att.url)
                if check.get("nsfw"):
                    await self._delete_message(message, "nsfw_attachment")
                    await self._warn_user(guild, message.author, "Sharing NSFW content in non-NSFW channels is prohibited.")
                    await self._escalate_if_needed(guild, message.author)
                    return

        # 6) Language enforcement
        lec = cfg.get("language_enforced_channels", {})
        ch_lang = lec.get(str(message.channel.id))
        if ch_lang:
            detected = simple_language_detect(content)
            if detected != ch_lang and detected != "unknown":
                await self._delete_message(message, f"language_violation expected:{ch_lang} detected:{detected}")
                await self._warn_user(guild, message.author, f"Please use the configured language ({ch_lang}) in this channel.")
                return

        # 7) AI moderation via Perspective
        if cfg.get("aimod_enabled", False) and PERSPECTIVE_API_KEY:
            # skip mods/trusted
            if await self._is_trusted(message.author, cfg):
                return
            try:
                # call perspective async
                res = await self.perspective.analyze_text(content)
                if res.get("error"):
                    # skip if error
                    return
                # examine results: each attribute returns a score between 0 and 1 in res['attributeScores']
                attr_scores = {}
                if "attributeScores" in res:
                    for k, v in res["attributeScores"].items():
                        # some shapes have spanScores -> having summaryScore -> value
                        score = None
                        try:
                            score = v.get("summaryScore", {}).get("value")
                        except Exception:
                            score = None
                        if score is None:
                            # try other shapes
                            try:
                                score = list(v.get("spanScores", [{}])[0].get("score", {}).values())[0]
                            except Exception:
                                score = 0.0
                        attr_scores[k] = float(score or 0.0)
                # Decide flaggedness based on thresholds (customize thresholds as needed)
                # Example: if TOXICITY >= 0.85 or SEVERE_TOXICITY >= 0.6 -> flag
                flagged = False
                flagged_reasons = []
                if attr_scores.get("TOXICITY", 0) >= 0.85:
                    flagged = True
                    flagged_reasons.append("TOXICITY")
                if attr_scores.get("SEVERE_TOXICITY", 0) >= 0.60:
                    flagged = True
                    flagged_reasons.append("SEVERE_TOXICITY")
                if attr_scores.get("THREAT", 0) >= 0.7:
                    flagged = True
                    flagged_reasons.append("THREAT")
                if attr_scores.get("IDENTITY_ATTACK", 0) >= 0.7:
                    flagged = True
                    flagged_reasons.append("IDENTITY_ATTACK")
                if attr_scores.get("INSULT", 0) >= 0.8:
                    flagged = True
                    flagged_reasons.append("INSULT")
                # NSFW-like flags considered separately (SEXUALLY_EXPLICIT)
                if attr_scores.get("SEXUALLY_EXPLICIT", 0) >= 0.8:
                    flagged = True
                    flagged_reasons.append("SEXUALLY_EXPLICIT")

                if flagged:
                    # action: delete + warn, escalate if repeated
                    reason = f"perspective_flagged: {', '.join(flagged_reasons)}"
                    await self._delete_message(message, reason)
                    await self._warn_user(guild, message.author, "Your message was flagged by AI moderation.")
                    await self._escalate_if_needed(guild, message.author)
                    # log details to moderation log for staff review
                    details = "\n".join(f"{k}: {v:.3f}" for k, v in attr_scores.items())
                    await self._log(guild, self.emb.warning("AI Moderation Triggered", f"Message flagged by Perspective API: {', '.join(flagged_reasons)}", fields=[("Scores", details, False), ("Content", message.content[:1000], False)]))
                    return
            except Exception:
                traceback.print_exc()
                return

    # ----------------------------
    # Slash commands (combined groups) under /mod + unified /play
    # ----------------------------
    mod = app_commands.Group(name="mod", description="Moderation (AutoMod + AI) commands")

    # --- AutoMod native or fallback triggers ---
    @mod.group(name="automod", description="Manage AutoMod rules (native where supported) or fallback triggers")
    async def automod_root(self, interaction: discord.Interaction):
        await interaction.response.send_message(embed=self.emb.info("AutoMod", "Use subcommands: rule add/remove/list OR triggers (fallback)."), ephemeral=True)

    @automod_root.group(name="rule", description="Native AutoMod rule operations (best-effort)")
    async def automod_rule_group(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

    @automod_rule_group.command(name="add", description="Create native AutoMod rule (keyword/spam/mention/invite). If not supported, stored as fallback.")
    @app_commands.describe(name="Rule name", trigger_type="keyword|mentions_excessive|invite|spam", keywords="comma-separated keywords", action="action type e.g., block_message|send_alert_message|timeout", threshold="optional threshold")
    async def automod_rule_add(self, interaction: discord.Interaction, name: str, trigger_type: str, keywords: Optional[str], action: str, threshold: Optional[int] = None):
        await interaction.response.defer(ephemeral=True)
        if not await self._is_mod_member(interaction.user if isinstance(interaction.user, discord.Member) else interaction.user):
            await interaction.followup.send(embed=self.emb.error("Permission denied", "Only configured moderators can create AutoMod rules."), ephemeral=True)
            return
        guild = interaction.guild
        if not guild:
            await interaction.followup.send(embed=self.emb.error("Guild only", "This command must be used in a guild."), ephemeral=True)
            return
        trigger_type_lower = trigger_type.lower()
        trigger_data = {}
        if trigger_type_lower in ("keyword", "keywords"):
            words = [w.strip() for w in (keywords or "").split(",") if w.strip()]
            trigger_data = {"keywords": words}
        elif trigger_type_lower == "mentions_excessive":
            trigger_data = {"mention_total_limit": threshold or 5}
        elif trigger_type_lower == "invite":
            trigger_data = {"invites": True}
        elif trigger_type_lower == "spam":
            trigger_data = {"threshold_seconds": threshold or 8}
        else:
            trigger_data = {"keywords": [k.strip() for k in (keywords or "").split(",") if k.strip()]}

        actions = [{"type": action}]
        native = await self.try_create_native_rule(guild, name, trigger_type_lower, trigger_data, actions)
        if native:
            await interaction.followup.send(embed=self.emb.success("Native AutoMod rule created", f"Created rule {name} (ID: {getattr(native, 'id', '?')})"), ephemeral=True)
            return
        # fallback: store in DB triggers
        cfg = await self.db.get_guild_config(guild.id)
        trigs = cfg.get("automod_triggers", [])
        trigs.append({"trigger_type": trigger_type_lower, "pattern": keywords or "", "action": action})
        cfg["automod_triggers"] = trigs
        await self.db.set_guild_config(guild.id, cfg)
        await interaction.followup.send(embed=self.emb.warning("Fallback stored", "Could not create native AutoMod rule; stored as DB fallback trigger."), ephemeral=True)

    @automod_rule_group.command(name="list", description="List native AutoMod rules if available, otherwise DB triggers")
    async def automod_rule_list(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        guild = interaction.guild
        if not guild:
            await interaction.followup.send(embed=self.emb.error("Guild only", "This command must be used in a guild."), ephemeral=True)
            return
        native = await self.try_list_native_rules(guild)
        if native:
            lines = []
            for r in native:
                try:
                    lines.append(f"ID: {getattr(r, 'id', '?')} • {getattr(r, 'name', getattr(r, 'id', 'rule'))} • enabled={getattr(r, 'enabled', '?')}")
                except Exception:
                    lines.append(str(r))
            await interaction.followup.send(embed=self.emb.info("Native AutoMod Rules", "\n".join(lines)), ephemeral=True)
            return
        cfg = await self.db.get_guild_config(guild.id)
        trigs = cfg.get("automod_triggers", [])
        if not trigs:
            await interaction.followup.send(embed=self.emb.info("No rules", "No native rules and no fallback triggers found."), ephemeral=True)
            return
        desc = "\n".join(f"- `{t.get('trigger_type')}` `{t.get('pattern')}` -> `{t.get('action')}`" for t in trigs)
        await interaction.followup.send(embed=self.emb.info("DB fallback triggers", desc), ephemeral=True)

    @automod_rule_group.command(name="remove", description="Remove native rule by ID or fallback triggers by pattern")
    @app_commands.describe(rule_id="Native rule ID", pattern="Fallback pattern to remove")
    async def automod_rule_remove(self, interaction: discord.Interaction, rule_id: Optional[int] = None, pattern: Optional[str] = None):
        await interaction.response.defer(ephemeral=True)
        if not await self._is_mod_member(interaction.user if isinstance(interaction.user, discord.Member) else interaction.user):
            await interaction.followup.send(embed=self.emb.error("Permission denied", "Only moderators can remove rules."), ephemeral=True)
            return
        guild = interaction.guild
        if not guild:
            await interaction.followup.send(embed=self.emb.error("Guild only", "This command must be used in a guild."), ephemeral=True)
            return
        if rule_id:
            ok = await self.try_delete_native_rule(guild, rule_id)
            if ok:
                await interaction.followup.send(embed=self.emb.success("Native rule removed", f"Removed native rule {rule_id}"), ephemeral=True)
            else:
                await interaction.followup.send(embed=self.emb.error("Failed", "Could not remove native rule — unsupported or permission error."), ephemeral=True)
            return
        if pattern:
            cfg = await self.db.get_guild_config(guild.id)
            trigs = cfg.get("automod_triggers", [])
            new = [t for t in trigs if t.get("pattern") != pattern]
            cfg["automod_triggers"] = new
            await self.db.set_guild_config(guild.id, cfg)
            await interaction.followup.send(embed=self.emb.success("DB triggers updated", f"Removed triggers matching `{pattern}`."), ephemeral=True)
            return
        await interaction.followup.send(embed=self.emb.error("Missing args", "Provide rule_id or pattern to remove."), ephemeral=True)

    # --- AI moderation (Perspective) ---
    @mod.group(name="aimod", description="AI moderation: toggle/test (Perspective API)")
    async def aimod_root(self, interaction: discord.Interaction):
        await interaction.response.send_message(embed=self.emb.info("AI Moderation", "Use subcommands: toggle/test"), ephemeral=True)

    @aimod_root.command(name="toggle", description="Enable or disable AI moderation for this guild")
    async def aimod_toggle(self, interaction: discord.Interaction, enabled: bool):
        await interaction.response.defer(ephemeral=True)
        if not await self._is_mod_member(interaction.user if isinstance(interaction.user, discord.Member) else interaction.user):
            await interaction.followup.send(embed=self.emb.error("Permission denied", "Only moderators can toggle AI moderation."), ephemeral=True)
            return
        cfg = await self.db.get_guild_config(interaction.guild.id)
        cfg["aimod_enabled"] = bool(enabled)
        await self.db.set_guild_config(interaction.guild.id, cfg)
        await interaction.followup.send(embed=self.emb.success("AI moderation updated", f"AI moderation set to `{enabled}`."), ephemeral=True)

    @aimod_root.command(name="test", description="Test a message via Perspective API")
    async def aimod_test(self, interaction: discord.Interaction, message: str):
        await interaction.response.defer(ephemeral=True)
        if not PERSPECTIVE_API_KEY:
            await interaction.followup.send(embed=self.emb.error("Perspective API not configured", "Set PERSPECTIVE_API_KEY in your environment."), ephemeral=True)
            return
        try:
            res = await self.perspective.analyze_text(message)
            if res.get("error"):
                await interaction.followup.send(embed=self.emb.error("Perspective error", str(res.get("error"))), ephemeral=True)
                return
            attr_scores = {}
            if "attributeScores" in res:
                for k, v in res["attributeScores"].items():
                    try:
                        score = v.get("summaryScore", {}).get("value", 0)
                    except Exception:
                        score = 0
                    attr_scores[k] = float(score or 0.0)
            details = "\n".join(f"{k}: {v:.3f}" for k, v in attr_scores.items())
            flagged = any([
                attr_scores.get("TOXICITY", 0) >= 0.85,
                attr_scores.get("SEVERE_TOXICITY", 0) >= 0.6,
                attr_scores.get("THREAT", 0) >= 0.7
            ])
            await interaction.followup.send(embed=self.emb.warning("AI Test - Flagged", details) if flagged else self.emb.success("AI Test - Clean", details), ephemeral=True)
        except Exception as e:
            await interaction.followup.send(embed=self.emb.error("Error calling Perspective", str(e)), ephemeral=True)

    # --- Custom rules (DB) ---
    @mod.group(name="rules", description="Manage DB-backed custom rules")
    async def rules_root(self, interaction: discord.Interaction):
        await interaction.response.send_message(embed=self.emb.info("Custom Rules", "Use add/remove/list"), ephemeral=True)

    @rules_root.command(name="add", description="Add custom rule e.g., contains:badword action=delete/warn/temp_mute:3600")
    async def rule_add(self, interaction: discord.Interaction, trigger: str, action: str, dm_message: Optional[str] = None):
        await interaction.response.defer(ephemeral=True)
        if not await self._is_mod_member(interaction.user if isinstance(interaction.user, discord.Member) else interaction.user):
            await interaction.followup.send(embed=self.emb.error("Permission denied", "Only moderators can add rules."), ephemeral=True)
            return
        if ":" not in trigger:
            await interaction.followup.send(embed=self.emb.error("Invalid trigger", "Trigger must be type:pattern (e.g., contains:invite or regex:^bad$)."), ephemeral=True)
            return
        ttype, pattern = trigger.split(":", 1)
        cfg = await self.db.get_guild_config(interaction.guild.id)
        arr = cfg.get("custom_rules", [])
        arr.append({"trigger_type": ttype, "pattern": pattern, "action": action, "dm_message": dm_message})
        cfg["custom_rules"] = arr
        await self.db.set_guild_config(interaction.guild.id, cfg)
        await interaction.followup.send(embed=self.emb.success("Rule added", f"{ttype}:{pattern} -> {action}"), ephemeral=True)

    @rules_root.command(name="remove", description="Remove custom rules by exact pattern")
    async def rule_remove(self, interaction: discord.Interaction, pattern: str):
        await interaction.response.defer(ephemeral=True)
        if not await self._is_mod_member(interaction.user if isinstance(interaction.user, discord.Member) else interaction.user):
            await interaction.followup.send(embed=self.emb.error("Permission denied", "Only moderators can remove rules."), ephemeral=True)
            return
        cfg = await self.db.get_guild_config(interaction.guild.id)
        new = [r for r in cfg.get("custom_rules", []) if r.get("pattern") != pattern]
        cfg["custom_rules"] = new
        await self.db.set_guild_config(interaction.guild.id, cfg)
        await interaction.followup.send(embed=self.emb.success("Rule removed", f"Removed rules matching `{pattern}`."), ephemeral=True)

    @rules_root.command(name="list", description="List custom rules")
    async def rule_list(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        cfg = await self.db.get_guild_config(interaction.guild.id)
        rules = cfg.get("custom_rules", [])
        if not rules:
            await interaction.followup.send(embed=self.emb.info("No custom rules", "No custom rules configured."), ephemeral=True)
            return
        desc = "\n".join(f"`{i+1}.` {r.get('trigger_type')}:{r.get('pattern')} -> **{r.get('action')}** • msg: {r.get('dm_message') or 'none'}" for i, r in enumerate(rules))
        await interaction.followup.send(embed=self.emb.info("Custom rules", desc), ephemeral=True)

    # --- Spam config + links management (combined) ---
    @mod.command(name="spam", description="Set spam threshold: messages seconds OR view current")
    async def spam(self, interaction: discord.Interaction, messages: Optional[int] = None, seconds: Optional[int] = None):
        await interaction.response.defer(ephemeral=True)
        if not await self._is_mod_member(interaction.user if isinstance(interaction.user, discord.Member) else interaction.user):
            await interaction.followup.send(embed=self.emb.error("Permission denied", "Only moderators can change spam settings."), ephemeral=True)
            return
        cfg = await self.db.get_guild_config(interaction.guild.id)
        if messages is None or seconds is None:
            thr = cfg.get("spam_threshold", {})
            await interaction.followup.send(embed=self.emb.info("Spam threshold", f"{thr.get('messages')} messages in {thr.get('seconds')} seconds"), ephemeral=True)
            return
        cfg["spam_threshold"] = {"messages": max(1, messages), "seconds": max(1, seconds)}
        await self.db.set_guild_config(interaction.guild.id, cfg)
        await interaction.followup.send(embed=self.emb.success("Spam config updated", f"{messages} messages in {seconds} seconds"), ephemeral=True)

    @mod.command(name="links", description="Links: whitelist_add blacklist_add list")
    async def links(self, interaction: discord.Interaction, verb: str, domain: Optional[str] = None):
        await interaction.response.defer(ephemeral=True)
        if not await self._is_mod_member(interaction.user if isinstance(interaction.user, discord.Member) else interaction.user):
            await interaction.followup.send(embed=self.emb.error("Permission denied", "Only moderators can manage links."), ephemeral=True)
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
            await interaction.followup.send(embed=self.emb.success("Whitelisted", f"Added `{domain}` to whitelist"), ephemeral=True)
            return
        if verb == "blacklist_add" and domain:
            if domain.lower() not in [d.lower() for d in bl]:
                bl.append(domain)
            cfg["links_blacklist"] = bl
            await self.db.set_guild_config(interaction.guild.id, cfg)
            await interaction.followup.send(embed=self.emb.success("Blacklisted", f"Added `{domain}` to blacklist"), ephemeral=True)
            return
        if verb == "list":
            await interaction.followup.send(embed=self.emb.info("Links", f"Whitelist: {', '.join(wl) or 'None'}\nBlacklist: {', '.join(bl) or 'None'}"), ephemeral=True)
            return
        await interaction.followup.send(embed=self.emb.error("Invalid usage", "Use whitelist_add|blacklist_add|list"), ephemeral=True)

    # --- NSFW scanner toggle/test (stub) ---
    @mod.command(name="nsfw", description="nsfw enable|disable|test <image_url>")
    async def nsfw(self, interaction: discord.Interaction, action: str, image_url: Optional[str] = None):
        await interaction.response.defer(ephemeral=True)
        if not await self._is_mod_member(interaction.user if isinstance(interaction.user, discord.Member) else interaction.user):
            await interaction.followup.send(embed=self.emb.error("Permission denied", "Only moderators can manage NSFW scanning."), ephemeral=True)
            return
        action = action.lower()
        cfg = await self.db.get_guild_config(interaction.guild.id)
        if action in ("enable", "disable"):
            cfg["nsfw_enabled"] = (action == "enable")
            await self.db.set_guild_config(interaction.guild.id, cfg)
            await interaction.followup.send(embed=self.emb.success("NSFW scanner updated", f"NSFW scanning set to {cfg['nsfw_enabled']}"), ephemeral=True)
            return
        if action == "test":
            if not image_url:
                await interaction.followup.send(embed=self.emb.error("Missing url", "Provide an image url to test."), ephemeral=True)
                return
            res = nsfw_stub_check(image_url)
            await interaction.followup.send(embed=self.emb.warning("NSFW flagged", f"Score {res['score']}") if res["nsfw"] else self.emb.success("NSFW clean", "Stub result: clean"), ephemeral=True)
            return
        await interaction.followup.send(embed=self.emb.error("Invalid usage", "Use enable|disable|test <url>"), ephemeral=True)

    # --- Roles (manual + auto) ---
    @mod.command(name="roles", description="roles manual <member> <role> assign/remove OR roles auto <role> enable|disable")
    async def roles(self, interaction: discord.Interaction, mode: str, member: Optional[discord.Member] = None, role: Optional[discord.Role] = None, action: Optional[str] = None):
        await interaction.response.defer(ephemeral=True)
        if not await self._is_mod_member(interaction.user if isinstance(interaction.user, discord.Member) else interaction.user):
            await interaction.followup.send(embed=self.emb.error("Permission denied", "Only moderators can manage roles."), ephemeral=True)
            return
        mode = mode.lower()
        if mode == "manual":
            if not member or not role or not action:
                await interaction.followup.send(embed=self.emb.error("Invalid usage", "manual requires member, role, assign|remove"), ephemeral=True)
                return
            if action == "assign":
                await member.add_roles(role, reason=f"Manual assign by {interaction.user}")
                await interaction.followup.send(embed=self.emb.success("Role assigned", f"{role.mention} -> {member.mention}"), ephemeral=True)
                return
            if action == "remove":
                await member.remove_roles(role, reason=f"Manual remove by {interaction.user}")
                await interaction.followup.send(embed=self.emb.success("Role removed", f"{role.mention} removed from {member.mention}"), ephemeral=True)
                return
            await interaction.followup.send(embed=self.emb.error("Invalid action", "Action must be assign or remove"), ephemeral=True)
            return
        if mode == "auto":
            if not role or not action:
                await interaction.followup.send(embed=self.emb.error("Invalid usage", "auto requires role and enable|disable"), ephemeral=True)
                return
            cfg = await self.db.get_guild_config(interaction.guild.id)
            auto = cfg.get("auto_roles", {})
            auto[str(role.id)] = (action.lower() == "enable")
            cfg["auto_roles"] = auto
            await self.db.set_guild_config(interaction.guild.id, cfg)
            await interaction.followup.send(embed=self.emb.success("Auto roles updated", f"{role.name} auto set to {auto[str(role.id)]}"), ephemeral=True)
            return
        await interaction.followup.send(embed=self.emb.error("Invalid usage", "See /mod roles help"), ephemeral=True)

    # --- Language enforcement ---
    @mod.command(name="lang", description="lang set <channel> <lang>|lang list")
    async def lang(self, interaction: discord.Interaction, sub: str, channel: Optional[discord.TextChannel] = None, language: Optional[str] = None):
        await interaction.response.defer(ephemeral=True)
        if not await self._is_mod_member(interaction.user if isinstance(interaction.user, discord.Member) else interaction.user):
            await interaction.followup.send(embed=self.emb.error("Permission denied", "Only moderators can configure language enforcement."), ephemeral=True)
            return
        sub = sub.lower()
        cfg = await self.db.get_guild_config(interaction.guild.id)
        lec = cfg.get("language_enforced_channels", {})
        if sub == "set":
            if not channel or not language:
                await interaction.followup.send(embed=self.emb.error("Invalid usage", "set requires channel and language (or 'none' to disable)"), ephemeral=True)
                return
            if language.lower() == "none":
                lec.pop(str(channel.id), None)
                msg = f"Disabled language enforcement for {channel.mention}"
            else:
                lec[str(channel.id)] = language
                msg = f"Set language for {channel.mention} -> {language}"
            cfg["language_enforced_channels"] = lec
            await self.db.set_guild_config(interaction.guild.id, cfg)
            await interaction.followup.send(embed=self.emb.success("Language updated", msg), ephemeral=True)
            return
        if sub == "list":
            if not lec:
                await interaction.followup.send(embed=self.emb.info("Language enforcement", "No channels enforced."), ephemeral=True)
                return
            desc = "\n".join(f"<#{k}> -> `{v}`" for k, v in lec.items())
            await interaction.followup.send(embed=self.emb.info("Enforced channels", desc), ephemeral=True)
            return
        await interaction.followup.send(embed=self.emb.error("Invalid usage", "lang set <channel> <lang>|lang list"), ephemeral=True)

    # --- Setup helpers ---
    @mod.group(name="setup", description="Setup guild settings: log/modrole/trusted/bannedwords")
    async def setup_group(self, interaction: discord.Interaction):
        await interaction.response.send_message(embed=self.emb.info("Setup", "Use setup subcommands"), ephemeral=True)

    @setup_group.command(name="log", description="Set log channel")
    async def setup_log(self, interaction: discord.Interaction, channel: discord.TextChannel):
        await interaction.response.defer(ephemeral=True)
        if not (await self._is_mod_member(interaction.user if isinstance(interaction.user, discord.Member) else interaction.user)) and interaction.user.id != interaction.guild.owner_id:
            await interaction.followup.send(embed=self.emb.error("Permission denied", "Only moderators or guild owner can set log channel."), ephemeral=True)
            return
        cfg = await self.db.get_guild_config(interaction.guild.id)
        cfg["log_channel_id"] = channel.id
        await self.db.set_guild_config(interaction.guild.id, cfg)
        await interaction.followup.send(embed=self.emb.success("Log channel set", f"Log channel set to {channel.mention}"), ephemeral=True)

    @setup_group.command(name="modrole", description="Add a moderator role")
    async def setup_modrole(self, interaction: discord.Interaction, role: discord.Role):
        await interaction.response.defer(ephemeral=True)
        if not (await self._is_mod_member(interaction.user if isinstance(interaction.user, discord.Member) else interaction.user)) and interaction.user.id != interaction.guild.owner_id:
            await interaction.followup.send(embed=self.emb.error("Permission denied", "Only moderators or guild owner can set mod role."), ephemeral=True)
            return
        cfg = await self.db.get_guild_config(interaction.guild.id)
        mods = cfg.get("mod_role_ids", [])
        if role.id not in mods:
            mods.append(role.id)
        cfg["mod_role_ids"] = mods
        await self.db.set_guild_config(interaction.guild.id, cfg)
        await interaction.followup.send(embed=self.emb.success("Mod role updated", f"{role.mention} added to mod roles."), ephemeral=True)

    @setup_group.command(name="trusted", description="Add or remove trusted role")
    async def setup_trusted(self, interaction: discord.Interaction, role: discord.Role, enable: bool):
        await interaction.response.defer(ephemeral=True)
        if not (await self._is_mod_member(interaction.user if isinstance(interaction.user, discord.Member) else interaction.user)) and interaction.user.id != interaction.guild.owner_id:
            await interaction.followup.send(embed=self.emb.error("Permission denied", "Only moderators or guild owner can set trusted role."), ephemeral=True)
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
        await interaction.followup.send(embed=self.emb.success("Trusted roles updated", f"{role.mention} updated."), ephemeral=True)

    @setup_group.command(name="bannedwords", description="Set banned words comma-separated, or 'none' to clear")
    async def setup_bannedwords(self, interaction: discord.Interaction, words: str):
        await interaction.response.defer(ephemeral=True)
        if not (await self._is_mod_member(interaction.user if isinstance(interaction.user, discord.Member) else interaction.user)) and interaction.user.id != interaction.guild.owner_id:
            await interaction.followup.send(embed=self.emb.error("Permission denied", "Only moderators or guild owner can set banned words."), ephemeral=True)
            return
        cfg = await self.db.get_guild_config(interaction.guild.id)
        if words.lower() == "none":
            cfg["banned_words"] = []
        else:
            cfg["banned_words"] = [w.strip() for w in words.split(",") if w.strip()]
        await self.db.set_guild_config(interaction.guild.id, cfg)
        await interaction.followup.send(embed=self.emb.success("Banned words updated", "Banned words updated."), ephemeral=True)

    # --- Logs & dashboard ---
    @mod.command(name="logs", description="View recent infractions")
    async def logs(self, interaction: discord.Interaction, limit: int = 10):
        await interaction.response.defer(ephemeral=True)
        rows = await self.db.get_recent_infractions(interaction.guild.id, limit=max(1, min(50, limit)))
        if not rows:
            await interaction.followup.send(embed=self.emb.info("Logs", "No infractions found."), ephemeral=True)
            return
        lines = []
        for r in rows:
            _id, user_id, moderator_id, action, reason, created_at = r
            lines.append(f"**#{_id}** {action} • <@{user_id}> • by <@{moderator_id}> • {created_at} • {reason or ''}")
        await interaction.followup.send(embed=self.emb.info("Recent infractions", "\n".join(lines[:20])), ephemeral=True)

    @mod.command(name="dashboard", description="Basic moderation dashboard")
    async def dashboard(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        rows = await self.db.get_recent_infractions(interaction.guild.id, limit=200)
        if not rows:
            await interaction.followup.send(embed=self.emb.info("Dashboard", "No infractions yet."), ephemeral=True)
            return
        counts = {}
        for r in rows:
            _id, user_id, moderator_id, action, reason, created_at = r
            counts[user_id] = counts.get(user_id, 0) + 1
        top = sorted(counts.items(), key=lambda x: x[1], reverse=True)[:5]
        top_text = "\n".join(f"<@{uid}> — {c} infractions" for uid, c in top) or "None"
        embed = self.emb.info("Moderation Dashboard", f"Total infractions (recent): {len(rows)}", fields=[("Top offenders", top_text, False)])
        await interaction.followup.send(embed=embed, ephemeral=True)

    # --- Unified /play test command ---
    @app_commands.command(name="play", description="Unified test: profanity|spam|nsfw|ai|roles")
    async def play(self, interaction: discord.Interaction, kind: str, content: Optional[str] = None):
        await interaction.response.defer(ephemeral=True)
        kind = kind.lower()
        cfg = await self.db.get_guild_config(interaction.guild.id)
        if kind == "profanity":
            bads = cfg.get("banned_words", [])
            found = [b for b in bads if b.lower() in (content or "").lower()]
            if found:
                await interaction.followup.send(embed=self.emb.warning("Profanity test - would trigger", f"Detected: {', '.join(found)} — action delete & warn"), ephemeral=True)
            else:
                await interaction.followup.send(embed=self.emb.success("Profanity test - clean", "No banned words detected"), ephemeral=True)
            return
        if kind == "spam":
            thr = cfg.get("spam_threshold", {})
            await interaction.followup.send(embed=self.emb.info("Spam test", f"Threshold: {thr.get('messages')} messages in {thr.get('seconds')} seconds"), ephemeral=True)
            return
        if kind == "nsfw":
            if not content:
                await interaction.followup.send(embed=self.emb.error("Missing image url", "Provide an image URL to test NSFW."), ephemeral=True)
                return
            res = nsfw_stub_check(content)
            await interaction.followup.send(embed=self.emb.warning("NSFW flagged", f"Score {res['score']}") if res["nsfw"] else self.emb.success("NSFW clean", "Stub result: clean"), ephemeral=True)
            return
        if kind == "ai":
            if not content:
                await interaction.followup.send(embed=self.emb.error("Missing message", "Provide text to test AI moderation."), ephemeral=True)
                return
            if not PERSPECTIVE_API_KEY:
                await interaction.followup.send(embed=self.emb.error("AI not configured", "Set PERSPECTIVE_API_KEY in environment."), ephemeral=True)
                return
            res = await self.perspective.analyze_text(content)
            if res.get("error"):
                await interaction.followup.send(embed=self.emb.error("Perspective error", str(res.get("error"))), ephemeral=True)
                return
            attr_scores = {}
            for k, v in res.get("attributeScores", {}).items():
                try:
                    score = v.get("summaryScore", {}).get("value", 0)
                except Exception:
                    score = 0
                attr_scores[k] = float(score or 0.0)
            details = "\n".join(f"{k}: {v:.3f}" for k, v in attr_scores.items())
            flagged = any([
                attr_scores.get("TOXICITY", 0) >= 0.85,
                attr_scores.get("SEVERE_TOXICITY", 0) >= 0.6,
                attr_scores.get("THREAT", 0) >= 0.7,
            ])
            await interaction.followup.send(embed=self.emb.warning("AI Test - Flagged", details) if flagged else self.emb.success("AI Test - Clean", details), ephemeral=True)
            return
        if kind == "roles":
            await interaction.followup.send(embed=self.emb.info("Role test", "Use /mod roles manual to test role assignment."), ephemeral=True)
            return
        await interaction.followup.send(embed=self.emb.error("Unknown test kind", "Supported: profanity, spam, nsfw, ai, roles"), ephemeral=True)

# ----------------------------
# Setup entrypoint
# ----------------------------
async def setup(bot: commands.Bot):
    cog = AutoModCog(bot)
    await bot.add_cog(cog)
    # ensure DB connected (redundant if cog_load runs)
    if not hasattr(bot, "automod_db"):
        bot.automod_db = AutomodDB(DB_PATH)
    await bot.automod_db.connect()
