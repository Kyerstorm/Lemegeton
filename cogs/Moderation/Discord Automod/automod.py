# cogs/automod.py
"""
AutoMod Cog (automod.py)
- Strictly Discord AutoMod + non-AI detectors:
    * banned words
    * spam detection
    * link whitelist/blacklist
    * language enforcement (stub)
    * native AutoMod rule management (best-effort)
- Slash only commands under /automod
- Uses SQLite (moderation.db) shared with aimoderation.py
- Dependencies: discord.py>=2.5.1, aiosqlite, python-dotenv
"""

import os
import re
import json
import asyncio
import traceback
from typing import Optional, Dict, Any, List, Tuple
from datetime import datetime, timedelta

import discord
from discord import app_commands
from discord.ext import commands

import aiosqlite
from dotenv import load_dotenv

load_dotenv()

DB_PATH = "moderation.db"
EMOJI_SUCCESS = "✅"
EMOJI_WARNING = "⚠️"
EMOJI_ERROR = "❌"
COLORS = {"success": 0x2ecc71, "warning": 0xf39c12, "error": 0xe74c3c, "info": 0x3498db}

DEFAULT_AUTOMOD_CONFIG = {
    "log_channel_id": None,
    "mod_role_ids": [],
    "trusted_role_ids": [],
    "banned_words": ["damn", "hell"],
    "spam_threshold": {"messages": 5, "seconds": 8},
    "links_whitelist": [],
    "links_blacklist": [],
    "language_enforced_channels": {},  # channel_id (str) -> language code
    "mute_role_id": None,
    "temp_mutes": [],
    "automod_triggers": [],  # db fallback triggers
    "custom_rules": [],
}

# ------------------------
# DB helper (shares same DB file)
# ------------------------
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
                cfg = {"automod": DEFAULT_AUTOMOD_CONFIG.copy(), "ai": {}}
                await self.set_guild_config(guild_id, cfg)

    async def get_guild_config(self, guild_id: int) -> Dict[str, Any]:
        async with self._lock:
            cur = await self.conn.execute("SELECT config FROM guilds WHERE guild_id = ?", (guild_id,))
            row = await cur.fetchone()
            await cur.close()
            if row:
                try:
                    return json.loads(row[0])
                except Exception:
                    return {"automod": DEFAULT_AUTOMOD_CONFIG.copy(), "ai": {}}
            else:
                cfg = {"automod": DEFAULT_AUTOMOD_CONFIG.copy(), "ai": {}}
                await self.set_guild_config(guild_id, cfg)
                return cfg

    async def set_guild_config(self, guild_id: int, config: Dict[str, Any]):
        cfg_json = json.dumps(config)
        async with self._lock:
            await self.conn.execute(
                "INSERT INTO guilds (guild_id, config) VALUES (?, ?) ON CONFLICT(guild_id) DO UPDATE SET config=excluded.config",
                (guild_id, cfg_json)
            )
            await self.conn.commit()

    async def add_infraction(self, guild_id: int, user_id: int, moderator_id: Optional[int], action: str, reason: Optional[str]):
        async with self._lock:
            ts = datetime.utcnow().isoformat()
            await self.conn.execute(
                "INSERT INTO infractions (guild_id, user_id, moderator_id, action, reason, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                (guild_id, user_id, moderator_id, action, reason, ts)
            )
            await self.conn.commit()

    async def get_recent_infractions(self, guild_id: int, limit: int = 20):
        async with self._lock:
            cur = await self.conn.execute(
                "SELECT id, user_id, moderator_id, action, reason, created_at FROM infractions WHERE guild_id = ? ORDER BY id DESC LIMIT ?",
                (guild_id, limit)
            )
            rows = await cur.fetchall()
            await cur.close()
            return rows


# ------------------------
# Small helpers
# ------------------------
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

def simple_language_detect(text: str) -> str:
    txt = text.lower()
    if any(x in txt for x in (" the ", " and ", " is ", " you ")): return "en"
    if any(x in txt for x in (" el ", " la ", " y ", " que ")): return "es"
    return "unknown"


# ------------------------
# Embeds helper
# ------------------------
class Embeds:
    @staticmethod
    def build(title: str, description: str, color: int = COLORS["info"], fields: Optional[List[Tuple[str, str, bool]]] = None):
        em = discord.Embed(title=title, description=description, color=color, timestamp=datetime.utcnow())
        if fields:
            for n, v, i in fields:
                em.add_field(name=n, value=v, inline=i)
        return em

    @staticmethod
    def success(title: str, description: str, **kwargs):
        return Embeds.build(f"{EMOJI_SUCCESS} {title}", description, color=COLORS["success"], **kwargs)

    @staticmethod
    def warning(title: str, description: str, **kwargs):
        return Embeds.build(f"{EMOJI_WARNING} {title}", description, color=COLORS["warning"], **kwargs)

    @staticmethod
    def error(title: str, description: str, **kwargs):
        return Embeds.build(f"{EMOJI_ERROR} {title}", description, color=COLORS["error"], **kwargs)


# ------------------------
# The Cog
# ------------------------
class AutoModCog(commands.Cog, name="AutoMod"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.db = AutomodDB(DB_PATH)
        self.emb = Embeds()
        self._spam_cache: Dict[int, Dict[int, List[float]]] = {}  # guild -> user -> timestamps
        self._unmute_task: Optional[asyncio.Task] = None

    async def cog_load(self):
        await self.db.connect()
        if self._unmute_task is None:
            self._unmute_task = asyncio.create_task(self._temp_mute_watcher())

    async def cog_unload(self):
        if self._unmute_task:
            self._unmute_task.cancel()
            self._unmute_task = None
        await self.db.conn.close()

    # ------------------------
    # helpers: perms, logging, moderation actions
    # ------------------------
    async def _is_mod(self, member: discord.Member) -> bool:
        cfg = await self.db.get_guild_config(member.guild.id)
        mod_roles = cfg.get("automod", {}).get("mod_role_ids", [])
        if member.guild.owner_id == member.id:
            return True
        if member.guild_permissions.administrator:
            return True
        for r in member.roles:
            if r.id in mod_roles:
                return True
        return False

    async def _is_trusted(self, member: discord.Member) -> bool:
        cfg = await self.db.get_guild_config(member.guild.id)
        trusted = cfg.get("automod", {}).get("trusted_role_ids", [])
        for r in member.roles:
            if r.id in trusted:
                return True
        return False

    async def _log(self, guild: discord.Guild, embed: discord.Embed):
        cfg = await self.db.get_guild_config(guild.id)
        ch_id = cfg.get("automod", {}).get("log_channel_id")
        if ch_id:
            ch = guild.get_channel(ch_id)
            if ch:
                try:
                    await ch.send(embed=embed)
                except Exception:
                    pass

    async def _add_infraction(self, guild_id: int, user_id: int, mod_id: Optional[int], action: str, reason: str):
        await self.db.add_infraction(guild_id, user_id, mod_id, action, reason)

    async def _warn(self, guild: discord.Guild, member: discord.Member, reason: str):
        try:
            await member.send(embed=self.emb.warning("You were warned", f"You were warned in **{guild.name}**.\nReason: {reason}"))
        except Exception:
            pass
        await self._add_infraction(guild.id, member.id, None, "warn", reason)
        await self._log(guild, self.emb.warning("User warned", f"{member.mention} warned", fields=[("Reason", reason, False)]))

    async def _delete_and_log(self, message: discord.Message, reason: str):
        try:
            await message.delete()
        except Exception:
            pass
        await self._add_infraction(message.guild.id, message.author.id, None, "delete", reason)
        await self._log(message.guild, self.emb.warning("Message deleted", f"Deleted message by {message.author.mention}", fields=[("Reason", reason, False), ("Content", message.content[:1000] or "[no content]", False), ("Channel", message.channel.mention, True)]))

    async def _temp_mute(self, guild: discord.Guild, member: discord.Member, seconds: int, reason: str):
        cfg = await self.db.get_guild_config(guild.id)
        amod = cfg.get("automod", DEFAULT_AUTOMOD_CONFIG.copy())
        muted_role_id = amod.get("mute_role_id")
        muted_role = guild.get_role(muted_role_id) if muted_role_id else None
        if muted_role is None:
            try:
                muted_role = await guild.create_role(name="Muted", reason="AutoMod temp mute")
            except Exception:
                muted_role = None
            if muted_role:
                for ch in guild.text_channels:
                    try:
                        await ch.set_permissions(muted_role, send_messages=False, add_reactions=False)
                    except Exception:
                        pass
                amod["mute_role_id"] = muted_role.id
                cfg["automod"] = amod
                await self.db.set_guild_config(guild.id, cfg)
        try:
            if muted_role:
                await member.add_roles(muted_role, reason=reason)
            else:
                try:
                    await member.timeout_for(timedelta(seconds=seconds), reason=reason)
                except Exception:
                    pass
        except Exception:
            pass
        unmute_at = (datetime.utcnow() + timedelta(seconds=seconds)).isoformat()
        tms = amod.get("temp_mutes", [])
        tms.append({"user_id": member.id, "unmute_at": unmute_at, "reason": reason})
        amod["temp_mutes"] = tms
        cfg["automod"] = amod
        await self.db.set_guild_config(guild.id, cfg)
        await self._add_infraction(guild.id, member.id, None, "temp_mute", reason)
        await self._log(guild, self.emb.warning("Temp mute", f"{member.mention} muted for {seconds}s", fields=[("Reason", reason, False)]))
        try:
            await member.send(embed=self.emb.warning("You were muted", f"You were muted for {seconds} seconds in **{guild.name}**.\nReason: {reason}"))
        except Exception:
            pass

    async def _unmute_watcher(self):
        pass

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
                    amod = cfg.get("automod", {})
                    tms = amod.get("temp_mutes", [])
                    changed = False
                    for tm in list(tms):
                        try:
                            unmute_at = datetime.fromisoformat(tm["unmute_at"])
                        except Exception:
                            continue
                        if unmute_at <= now:
                            guild = self.bot.get_guild(guild_id)
                            if guild:
                                role_id = amod.get("mute_role_id")
                                if role_id:
                                    member = guild.get_member(tm["user_id"])
                                    if member:
                                        role = guild.get_role(role_id)
                                        if role:
                                            try:
                                                await member.remove_roles(role, reason="Auto unmute")
                                            except Exception:
                                                pass
                                        await self._log(guild, self.emb.success("Auto unmute", f"<@{tm['user_id']}> unmuted (auto)."))
                            tms.remove(tm)
                            changed = True
                    if changed:
                        amod["temp_mutes"] = tms
                        cfg["automod"] = amod
                        async with self.db._lock:
                            await self.db.conn.execute("INSERT INTO guilds (guild_id, config) VALUES (?, ?) ON CONFLICT(guild_id) DO UPDATE SET config=excluded.config", (guild_id, json.dumps(cfg)))
                            await self.db.conn.commit()
            except asyncio.CancelledError:
                return
            except Exception:
                traceback.print_exc()
            await asyncio.sleep(15)

    # ------------------------
    # Native AutoMod helpers (best-effort)
    # ------------------------
    async def try_create_native_rule(self, guild: discord.Guild, name: str, trigger_type: str, metadata: Dict[str, Any], actions: List[Dict[str, Any]]):
        try:
            create_fn = getattr(guild, "create_auto_moderation_rule", None) or getattr(guild, "create_automod_rule", None)
            if create_fn:
                rule = await create_fn(
                    name=name,
                    event_type=discord.AutoModEventType.message_send,
                    trigger_type=trigger_type,
                    trigger_metadata=metadata,
                    actions=actions,
                    enabled=True,
                )
                return rule
        except Exception:
            traceback.print_exc()
        return None

    async def try_list_native_rules(self, guild: discord.Guild):
        try:
            getter = getattr(guild, "automod_rules", None)
            if getter:
                if callable(getter):
                    return await getter()
                return getter
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

    # ------------------------
    # Message listener: banned words, custom rules, spam, links, language
    # ------------------------
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return
        await self.db.ensure_guild(message.guild.id)
        cfg = await self.db.get_guild_config(message.guild.id)
        amod = cfg.get("automod", DEFAULT_AUTOMOD_CONFIG.copy())
        content = message.content or ""

        # banned words
        for bad in amod.get("banned_words", []):
            if bad.lower() in content.lower():
                await self._delete_and_log(message, f"banned_word:{bad}")
                await self._warn(message.guild, message.author, f"Use of banned word: {bad}")
                return

        # custom rules
        for r in amod.get("custom_rules", []):
            ttype = r.get("trigger_type")
            pattern = r.get("pattern")
            action = r.get("action", "warn")
            matched = False
            if ttype == "contains":
                if pattern.lower() in content.lower():
                    matched = True
            elif ttype == "regex":
                try:
                    if re.search(pattern, content, re.IGNORECASE): matched = True
                except re.error:
                    matched = False
            elif ttype == "invite":
                if "discord.gg/" in content.lower() or "discord.com/invite/" in content.lower(): matched = True
            if matched:
                reason = f"custom_rule:{ttype}:{pattern}"
                if "delete" in action:
                    await self._delete_and_log(message, reason)
                if "warn" in action:
                    await self._warn(message.guild, message.author, reason)
                if action.startswith("temp_mute"):
                    parts = action.split(":")
                    sec = int(parts[1]) if len(parts) > 1 else 300
                    await self._temp_mute(message.guild, message.author, sec, reason)
                if action == "kick":
                    try:
                        await message.author.kick(reason=reason)
                        await self._add_infraction(message.guild.id, message.author.id, None, "kick", reason)
                        await self._log(message.guild, self.emb.warning("User kicked", f"{message.author.mention} kicked for custom rule", fields=[("Reason", reason, False)]))
                    except Exception:
                        pass
                if action == "ban":
                    try:
                        await message.author.ban(reason=reason)
                        await self._add_infraction(message.guild.id, message.author.id, None, "ban", reason)
                        await self._log(message.guild, self.emb.warning("User banned", f"{message.author.mention} banned for custom rule", fields=[("Reason", reason, False)]))
                    except Exception:
                        pass
                return

        # spam detection
        thr = amod.get("spam_threshold", {"messages": 5, "seconds": 8})
        thr_msgs = int(thr.get("messages", 5))
        thr_secs = int(thr.get("seconds", 8))
        gcache = self._spam_cache.setdefault(message.guild.id, {})
        ucache = gcache.setdefault(message.author.id, [])
        now_ts = asyncio.get_event_loop().time()
        ucache.append(now_ts)
        window_start = now_ts - thr_secs
        ucache = [t for t in ucache if t >= window_start]
        gcache[message.author.id] = ucache
        if len(ucache) >= thr_msgs:
            await self._delete_and_log(message, f"spam:{len(ucache)} in {thr_secs}s")
            await self._warn(message.guild, message.author, "Spam detected (too many messages).")
            await self._temp_mute(message.guild, message.author, 60, "Spam auto-mute")
            gcache[message.author.id] = []
            return

        # links
        if "http://" in content.lower() or "https://" in content.lower():
            domains = extract_domains(content)
            for d in domains:
                if domain_matches(d, amod.get("links_blacklist", [])):
                    await self._delete_and_log(message, "link_blacklisted")
                    await self._warn(message.guild, message.author, "Posting blacklisted links is prohibited.")
                    return
            wl = amod.get("links_whitelist", [])
            if wl:
                allowed_any = any(domain_matches(d, wl) for d in domains)
                if not allowed_any and domains:
                    await self._delete_and_log(message, "link_not_whitelisted")
                    await self._warn(message.guild, message.author, "Posting links outside whitelist is not allowed.")
                    return

        # language enforcement
        lec = amod.get("language_enforced_channels", {})
        ch_lang = lec.get(str(message.channel.id))
        if ch_lang:
            detected = simple_language_detect(content)
            if detected != ch_lang and detected != "unknown":
                await self._delete_and_log(message, f"language_violation expected:{ch_lang} detected:{detected}")
                await self._warn(message.guild, message.author, f"Please use the configured language ({ch_lang}) in this channel.")
                return

    # ------------------------
    # Slash commands
    # ------------------------
    automod = app_commands.Group(name="automod", description="AutoMod commands (non-AI)")

    @automod.command(name="status", description="Show automod configuration for this guild")
    async def cmd_status(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        await self.db.ensure_guild(interaction.guild.id)
        cfg = await self.db.get_guild_config(interaction.guild.id)
        amod = cfg.get("automod", DEFAULT_AUTOMOD_CONFIG.copy())
        desc = f"Log Channel: `{amod.get('log_channel_id')}`\nBanned words: `{', '.join(amod.get('banned_words', []))}`\nSpam threshold: `{amod.get('spam_threshold')}`"
        await interaction.followup.send(embed=self.emb.success("AutoMod status", desc), ephemeral=True)

    @automod.command(name="setlog", description="Set AutoMod log channel")
    async def cmd_setlog(self, interaction: discord.Interaction, channel: discord.TextChannel):
        await interaction.response.defer(ephemeral=True)
        if not await self._is_mod(interaction.user if isinstance(interaction.user, discord.Member) else interaction.user):
            await interaction.followup.send(embed=self.emb.error("Permission denied", "You must be a mod to do this."), ephemeral=True)
            return
        await self.db.ensure_guild(interaction.guild.id)
        cfg = await self.db.get_guild_config(interaction.guild.id)
        amod = cfg.get("automod", DEFAULT_AUTOMOD_CONFIG.copy())
        amod["log_channel_id"] = channel.id
        cfg["automod"] = amod
        await self.db.set_guild_config(interaction.guild.id, cfg)
        await interaction.followup.send(embed=self.emb.success("Log channel set", f"AutoMod logs will go to {channel.mention}"), ephemeral=True)

    @automod.command(name="bannedwords", description="Set banned words (comma-separated) or 'none' to clear")
    async def cmd_bannedwords(self, interaction: discord.Interaction, words: str):
        await interaction.response.defer(ephemeral=True)
        if not await self._is_mod(interaction.user if isinstance(interaction.user, discord.Member) else interaction.user):
            await interaction.followup.send(embed=self.emb.error("Permission denied", "You must be a mod to do this."), ephemeral=True)
            return
        await self.db.ensure_guild(interaction.guild.id)
        cfg = await self.db.get_guild_config(interaction.guild.id)
        amod = cfg.get("automod", DEFAULT_AUTOMOD_CONFIG.copy())
        if words.lower() == "none":
            amod["banned_words"] = []
        else:
            amod["banned_words"] = [w.strip() for w in words.split(",") if w.strip()]
        cfg["automod"] = amod
        await self.db.set_guild_config(interaction.guild.id, cfg)
        await interaction.followup.send(embed=self.emb.success("Banned words updated", "Updated banned words list."), ephemeral=True)

    @automod.command(name="spam_config", description="Set spam threshold: messages seconds")
    async def cmd_spam(self, interaction: discord.Interaction, messages: Optional[int] = None, seconds: Optional[int] = None):
        await interaction.response.defer(ephemeral=True)
        if not await self._is_mod(interaction.user if isinstance(interaction.user, discord.Member) else interaction.user):
            await interaction.followup.send(embed=self.emb.error("Permission denied", "You must be a mod to do this."), ephemeral=True)
            return
        await self.db.ensure_guild(interaction.guild.id)
        cfg = await self.db.get_guild_config(interaction.guild.id)
        amod = cfg.get("automod", DEFAULT_AUTOMOD_CONFIG.copy())
        if messages is None or seconds is None:
            await interaction.followup.send(embed=self.emb.info("Spam threshold", f"{amod.get('spam_threshold')}"), ephemeral=True)
            return
        amod["spam_threshold"] = {"messages": max(1, messages), "seconds": max(1, seconds)}
        cfg["automod"] = amod
        await self.db.set_guild_config(interaction.guild.id, cfg)
        await interaction.followup.send(embed=self.emb.success("Spam config updated", f"{messages} messages in {seconds} seconds"), ephemeral=True)

    @automod.command(name="links", description="Manage links: whitelist_add|blacklist_add|list")
    async def cmd_links(self, interaction: discord.Interaction, verb: str, domain: Optional[str] = None):
        await interaction.response.defer(ephemeral=True)
        if not await self._is_mod(interaction.user if isinstance(interaction.user, discord.Member) else interaction.user):
            await interaction.followup.send(embed=self.emb.error("Permission denied", "You must be a mod to do this."), ephemeral=True)
            return
        verb = verb.lower()
        await self.db.ensure_guild(interaction.guild.id)
        cfg = await self.db.get_guild_config(interaction.guild.id)
        amod = cfg.get("automod", DEFAULT_AUTOMOD_CONFIG.copy())
        wl = amod.get("links_whitelist", [])
        bl = amod.get("links_blacklist", [])
        if verb == "whitelist_add" and domain:
            if domain.lower() not in [d.lower() for d in wl]:
                wl.append(domain)
            amod["links_whitelist"] = wl
            cfg["automod"] = amod
            await self.db.set_guild_config(interaction.guild.id, cfg)
            await interaction.followup.send(embed=self.emb.success("Whitelisted", f"Added `{domain}` to whitelist"), ephemeral=True)
            return
        if verb == "blacklist_add" and domain:
            if domain.lower() not in [d.lower() for d in bl]:
                bl.append(domain)
            amod["links_blacklist"] = bl
            cfg["automod"] = amod
            await self.db.set_guild_config(interaction.guild.id, cfg)
            await interaction.followup.send(embed=self.emb.success("Blacklisted", f"Added `{domain}` to blacklist"), ephemeral=True)
            return
        if verb == "list":
            await interaction.followup.send(embed=self.emb.info("Links", f"Whitelist: {', '.join(wl) or 'None'}\nBlacklist: {', '.join(bl) or 'None'}"), ephemeral=True)
            return
        await interaction.followup.send(embed=self.emb.error("Invalid usage", "Use whitelist_add|blacklist_add|list"), ephemeral=True)

    @automod.command(name="native_add", description="Try to create a native Discord AutoMod rule (best-effort).")
    async def cmd_native_add(self, interaction: discord.Interaction, name: str, trigger_type: str, keywords: Optional[str], action: str, threshold: Optional[int] = None):
        await interaction.response.defer(ephemeral=True)
        if not await self._is_mod(interaction.user if isinstance(interaction.user, discord.Member) else interaction.user):
            await interaction.followup.send(embed=self.emb.error("Permission denied", "You must be a mod to do this."), ephemeral=True)
            return
        # build metadata
        t = trigger_type.lower()
        metadata = {}
        if t in ("keyword", "keywords"):
            metadata = {"keywords": [w.strip() for w in (keywords or "").split(",") if w.strip()]}
        elif t == "mentions_excessive":
            metadata = {"mention_total_limit": threshold or 5}
        elif t == "invite":
            metadata = {"invites": True}
        elif t == "spam":
            metadata = {"threshold_seconds": threshold or 8}
        else:
            metadata = {"keywords": [w.strip() for w in (keywords or "").split(",") if w.strip()]}
        actions = [{"type": action}]
        native = await self.try_create_native_rule(interaction.guild, name, t, metadata, actions)
        if native:
            await interaction.followup.send(embed=self.emb.success("Native rule created", f"{name} (ID: {getattr(native,'id', '?')})"), ephemeral=True)
            return
        # fallback: store in DB automod_triggers
        await self.db.ensure_guild(interaction.guild.id)
        cfg = await self.db.get_guild_config(interaction.guild.id)
        amod = cfg.get("automod", DEFAULT_AUTOMOD_CONFIG.copy())
        trigs = amod.get("automod_triggers", [])
        trigs.append({"trigger_type": t, "pattern": keywords or "", "action": action})
        amod["automod_triggers"] = trigs
        cfg["automod"] = amod
        await self.db.set_guild_config(interaction.guild.id, cfg)
        await interaction.followup.send(embed=self.emb.warning("Fallback stored", "Could not create native rule; stored in DB fallback triggers."), ephemeral=True)

    @automod.command(name="native_list", description="List native AutoMod rules or DB fallback triggers")
    async def cmd_native_list(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        native = await self.try_list_native_rules(interaction.guild)
        if native:
            lines = []
            for r in native:
                try:
                    lines.append(f"ID: {getattr(r,'id','?')} • {getattr(r,'name',str(r))} • enabled={getattr(r,'enabled','?')}")
                except Exception:
                    lines.append(str(r))
            await interaction.followup.send(embed=self.emb.info("Native AutoMod rules", "\n".join(lines)), ephemeral=True)
            return
        await self.db.ensure_guild(interaction.guild.id)
        cfg = await self.db.get_guild_config(interaction.guild.id)
        trigs = cfg.get("automod", DEFAULT_AUTOMOD_CONFIG.copy()).get("automod_triggers", [])
        if not trigs:
            await interaction.followup.send(embed=self.emb.info("No rules", "No native rules and no DB fallback triggers found."), ephemeral=True)
            return
        desc = "\n".join(f"- `{t.get('trigger_type')}` `{t.get('pattern')}` -> `{t.get('action')}`" for t in trigs)
        await interaction.followup.send(embed=self.emb.info("DB fallback triggers", desc), ephemeral=True)

    @automod.command(name="native_remove", description="Remove native AutoMod rule by ID or remove fallback by pattern")
    async def cmd_native_remove(self, interaction: discord.Interaction, rule_id: Optional[int] = None, pattern: Optional[str] = None):
        await interaction.response.defer(ephemeral=True)
        if not await self._is_mod(interaction.user if isinstance(interaction.user, discord.Member) else interaction.user):
            await interaction.followup.send(embed=self.emb.error("Permission denied", "You must be a mod to do this."), ephemeral=True)
            return
        if rule_id:
            ok = await self.try_delete_native_rule(interaction.guild, rule_id)
            if ok:
                await interaction.followup.send(embed=self.emb.success("Native rule removed", f"Removed rule {rule_id}"), ephemeral=True)
            else:
                await interaction.followup.send(embed=self.emb.error("Failed", "Could not remove native rule."), ephemeral=True)
            return
        if pattern:
            await self.db.ensure_guild(interaction.guild.id)
            cfg = await self.db.get_guild_config(interaction.guild.id)
            amod = cfg.get("automod", DEFAULT_AUTOMOD_CONFIG.copy())
            trigs = amod.get("automod_triggers", [])
            new = [t for t in trigs if t.get("pattern") != pattern]
            amod["automod_triggers"] = new
            cfg["automod"] = amod
            await self.db.set_guild_config(interaction.guild.id, cfg)
            await interaction.followup.send(embed=self.emb.success("Removed", f"Removed fallback triggers matching `{pattern}`"), ephemeral=True)
            return
        await interaction.followup.send(embed=self.emb.error("Missing args", "Provide rule_id or pattern"), ephemeral=True)

# Setup
async def setup(bot: commands.Bot):
    cog = AutoModCog(bot)
    await bot.add_cog(cog)
    # ensure DB attached
    if not hasattr(bot, "automod_db"):
        bot.automod_db = AutomodDB(DB_PATH)
    await bot.automod_db.connect()
