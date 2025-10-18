# cogs/aimoderation.py
"""
AI Moderation Cog (aimoderation.py)
- Strictly AI moderation (text + image stubs) using Perspective API.
- Slash-only commands under /aimod
- Uses SQLite (moderation.db) for per-guild configuration and infractions.
- Fully automatic actions (delete, warn, temp_mute by role, kick, ban) based on category thresholds and action config.
- Dependencies: discord.py>=2.5.1, aiohttp, aiosqlite, python-dotenv
- Environment variables: DISCORD_TOKEN, PERSPECTIVE_API_KEY (optional), BOT_OWNER_ID (optional)
"""

import os
import json
import re
import asyncio
import traceback
from typing import Optional, Dict, Any, List, Tuple
from datetime import datetime, timedelta

import discord
from discord import app_commands
from discord.ext import commands

import aiosqlite
import aiohttp
from dotenv import load_dotenv

load_dotenv()

DB_PATH = "moderation.db"
PERSPECTIVE_API_KEY = os.getenv("PERSPECTIVE_API_KEY")
PERSPECTIVE_ENDPOINT = "https://commentanalyzer.googleapis.com/v1alpha1/comments:analyze"
EMOJI_SUCCESS = "✅"
EMOJI_WARNING = "⚠️"
EMOJI_ERROR = "❌"
COLORS = {"success": 0x2ecc71, "warning": 0xf39c12, "error": 0xe74c3c, "info": 0x3498db}

# Default guild AI config (stored under guild config -> "ai")
DEFAULT_AI_CONFIG = {
    "enabled": False,
    "text_moderation": True,
    "image_moderation": False,
    "log_channel_id": None,
    "whitelist": [],  # entity ids (users/roles/channels)
    "thresholds": {   # category -> threshold (0.0 - 1.0)
        "TOXICITY": 0.85,
        "SEVERE_TOXICITY": 0.6,
        "THREAT": 0.7,
        "IDENTITY_ATTACK": 0.7,
        "INSULT": 0.8,
        "SEXUALLY_EXPLICIT": 0.8,
    },
    "actions": {  # category -> action
        # possible actions: delete, warn, temp_mute, kick, ban, none
        # default fallback:
    },
    "categories_enabled": {},  # category -> bool
}


# ------------------------
# DB helper
# ------------------------
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
                cfg = {"ai": DEFAULT_AI_CONFIG.copy(), "automod": {}}  # automod placeholder
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
                    return {"ai": DEFAULT_AI_CONFIG.copy(), "automod": {}}
            else:
                cfg = {"ai": DEFAULT_AI_CONFIG.copy(), "automod": {}}
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
# Embeds helper
# ------------------------
class EmbedHelper:
    @staticmethod
    def embed(title: str, description: str, color: int = COLORS["info"], fields: Optional[List[Tuple[str, str, bool]]] = None):
        em = discord.Embed(title=title, description=description, color=color, timestamp=datetime.utcnow())
        if fields:
            for n, v, i in fields:
                em.add_field(name=n, value=v, inline=i)
        return em

    @staticmethod
    def success(title: str, description: str, **kwargs):
        return EmbedHelper.embed(f"{EMOJI_SUCCESS} {title}", description, color=COLORS["success"], **kwargs)

    @staticmethod
    def warning(title: str, description: str, **kwargs):
        return EmbedHelper.embed(f"{EMOJI_WARNING} {title}", description, color=COLORS["warning"], **kwargs)

    @staticmethod
    def error(title: str, description: str, **kwargs):
        return EmbedHelper.embed(f"{EMOJI_ERROR} {title}", description, color=COLORS["error"], **kwargs)


# ------------------------
# Perspective client
# ------------------------
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

    async def analyze(self, text: str, attributes: Optional[List[str]] = None) -> Dict[str, Any]:
        if not self.api_key:
            return {"error": "no_api_key"}
        await self.ensure_session()
        if attributes is None:
            attributes = ["TOXICITY", "SEVERE_TOXICITY", "INSULT", "IDENTITY_ATTACK", "THREAT", "SEXUALLY_EXPLICIT"]
        payload = {
            "comment": {"text": text},
            "languages": ["en"],
            "requestedAttributes": {a: {} for a in attributes},
            "doNotStore": True,
        }
        params = {"key": self.api_key}
        try:
            async with self.session.post(self.endpoint, params=params, json=payload, timeout=15) as resp:
                if resp.status != 200:
                    return {"error": f"status_{resp.status}", "body": await resp.text()}
                return await resp.json()
        except Exception as e:
            return {"error": str(e)}


# ------------------------
# The Cog
# ------------------------
class AIModerationCog(commands.Cog, name="AI Moderation"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.db = ModerationDB(DB_PATH)
        self.emb = EmbedHelper()
        self.persp = PerspectiveClient(PERSPECTIVE_API_KEY)
        self._unmute_task: Optional[asyncio.Task] = None

    async def cog_load(self):
        await self.db.connect()
        await self.persp.ensure_session()
        if self._unmute_task is None:
            self._unmute_task = asyncio.create_task(self._temp_mute_watcher())

    async def cog_unload(self):
        if self._unmute_task:
            self._unmute_task.cancel()
        await self.persp.close()
        await self.db.conn.close()

    # ------------------------
    # Helpers: permissions, logging, actions
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

    async def _log(self, guild: discord.Guild, embed: discord.Embed, file: Optional[discord.File] = None):
        cfg = await self.db.get_guild_config(guild.id)
        ai_cfg = cfg.get("ai", {})
        ch_id = ai_cfg.get("log_channel_id")
        if ch_id:
            ch = guild.get_channel(ch_id)
            if ch:
                try:
                    await ch.send(embed=embed, file=file)
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
        await self._log(guild, self.emb.warning("User warned", f"{member.mention} was warned.", fields=[("Reason", reason, False)]))

    async def _delete_and_log(self, message: discord.Message, reason: str):
        try:
            await message.delete()
        except Exception:
            pass
        await self._add_infraction(message.guild.id, message.author.id, None, "delete", reason)
        await self._log(message.guild, self.emb.warning("Message deleted", f"Deleted message by {message.author.mention}", fields=[("Reason", reason, False), ("Content", message.content[:1000] or "[no content]", False), ("Channel", message.channel.mention, True)]))

    async def _temp_mute(self, guild: discord.Guild, member: discord.Member, seconds: int, reason: str):
        cfg = await self.db.get_guild_config(guild.id)
        muted_role_id = cfg.get("automod", {}).get("mute_role_id") or cfg.get("automod", {}).get("mute_role")
        muted_role = guild.get_role(muted_role_id) if muted_role_id else None
        if muted_role is None:
            try:
                muted_role = await guild.create_role(name="Muted", reason="AI Moderation temp mute")
            except Exception:
                muted_role = None
            if muted_role:
                for ch in guild.text_channels:
                    try:
                        await ch.set_permissions(muted_role, send_messages=False, add_reactions=False)
                    except Exception:
                        pass
                # persist
                cfg["automod"] = cfg.get("automod", {})
                cfg["automod"]["mute_role_id"] = muted_role.id
                await self.db.set_guild_config(guild.id, cfg)
        try:
            if muted_role:
                await member.add_roles(muted_role, reason=reason)
            else:
                # try member.timeout_for as fallback
                try:
                    await member.timeout_for(timedelta(seconds=seconds), reason=reason)
                except Exception:
                    pass
        except Exception:
            pass
        # store unmute info
        unmute_at = (datetime.utcnow() + timedelta(seconds=seconds)).isoformat()
        cfg["automod"] = cfg.get("automod", {})
        tms = cfg["automod"].get("temp_mutes", [])
        tms.append({"user_id": member.id, "unmute_at": unmute_at, "reason": reason})
        cfg["automod"]["temp_mutes"] = tms
        await self.db.set_guild_config(guild.id, cfg)
        await self._add_infraction(guild.id, member.id, None, "temp_mute", reason)
        await self._log(guild, self.emb.warning("Temp mute", f"{member.mention} muted for {seconds}s", fields=[("Reason", reason, False)]))
        try:
            await member.send(embed=self.emb.warning("You were muted", f"You were muted for {seconds} seconds in **{guild.name}**.\nReason: {reason}"))
        except Exception:
            pass

    async def _kick(self, guild: discord.Guild, member: discord.Member, reason: str):
        try:
            await member.kick(reason=reason)
            await self._add_infraction(guild.id, member.id, None, "kick", reason)
            await self._log(guild, self.emb.warning("User kicked", f"{member.mention} kicked", fields=[("Reason", reason, False)]))
        except Exception:
            pass

    async def _ban(self, guild: discord.Guild, member: discord.Member, reason: str):
        try:
            await member.ban(reason=reason)
            await self._add_infraction(guild.id, member.id, None, "ban", reason)
            await self._log(guild, self.emb.warning("User banned", f"{member.mention} banned", fields=[("Reason", reason, False)]))
        except Exception:
            pass

    async def _unmute_watcher(self):
        # invoked by background task
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
                    automod_cfg = cfg.get("automod", {})
                    tms = automod_cfg.get("temp_mutes", [])
                    changed = False
                    for tm in list(tms):
                        try:
                            unmute_at = datetime.fromisoformat(tm["unmute_at"])
                        except Exception:
                            continue
                        if unmute_at <= now:
                            guild = self.bot.get_guild(guild_id)
                            if guild:
                                # unmute by removing role
                                role_id = automod_cfg.get("mute_role_id")
                                if role_id:
                                    member = guild.get_member(tm["user_id"])
                                    if member:
                                        role = guild.get_role(role_id)
                                        if role:
                                            try:
                                                await member.remove_roles(role, reason="Auto unmute")
                                            except Exception:
                                                pass
                                        # log
                                        await self._log(guild, self.emb.success("Auto unmute", f"<@{tm['user_id']}> unmuted (auto)."))
                            tms.remove(tm)
                            changed = True
                    if changed:
                        automod_cfg["temp_mutes"] = tms
                        cfg["automod"] = automod_cfg
                        async with self.db._lock:
                            await self.db.conn.execute("INSERT INTO guilds (guild_id, config) VALUES (?, ?) ON CONFLICT(guild_id) DO UPDATE SET config=excluded.config", (guild_id, json.dumps(cfg)))
                            await self.db.conn.commit()
            except asyncio.CancelledError:
                return
            except Exception:
                traceback.print_exc()
            await asyncio.sleep(15)

    # ------------------------
    # AI processing pipeline
    # ------------------------
    async def _process_text(self, message: discord.Message, ai_cfg: Dict[str, Any]):
        # call perspective
        try:
            resp = await self.persp.analyze(message.content)
            if resp.get("error"):
                # logging only (do not act on API errors)
                return
            attr_scores = {}
            if "attributeScores" in resp:
                for k, v in resp["attributeScores"].items():
                    # try to extract summaryScore.value
                    try:
                        val = v.get("summaryScore", {}).get("value", 0.0)
                    except Exception:
                        val = 0.0
                    attr_scores[k] = float(val or 0.0)
            # check thresholds
            thresholds = ai_cfg.get("thresholds", {})
            flagged = []
            for cat, score in attr_scores.items():
                th = thresholds.get(cat, DEFAULT_AI_CONFIG["thresholds"].get(cat, 0.8))
                if score >= th:
                    flagged.append((cat, score, th))
            if not flagged:
                return
            # decide action
            # determine active categories (enabled)
            enabled_cats = ai_cfg.get("categories_enabled", {})
            active = [c for c, s, t in flagged if enabled_cats.get(c, True)]
            if not active:
                return
            # compute action order: if any category maps to severe action pick top
            actions_map = ai_cfg.get("actions", {})
            selected_action = None
            for c, s, th in flagged:
                act = actions_map.get(c)
                if act:
                    # pick the most severe if multiple categories map; severity order: ban>kick>temp_mute>delete>warn>none
                    if selected_action is None:
                        selected_action = act
                    else:
                        order = ["none", "warn", "delete", "temp_mute", "kick", "ban"]
                        if order.index(act) > order.index(selected_action):
                            selected_action = act
            if selected_action is None:
                # default mapping
                selected_action = "delete"
            # build reason and take actions
            cats = ", ".join(f"{c} ({attr_scores.get(c):.2f})" for c, _, _ in flagged)
            reason = f"AI moderation triggered: {cats}"
            # log to guild log channel
            log_embed = self.emb.warning("AI Moderation Triggered", f"{message.author.mention} — {reason}", fields=[("Channel", message.channel.mention, True), ("Message", message.content[:1000], False)])
            await self._log(message.guild, log_embed)
            # execute chosen action
            if selected_action == "none":
                return
            if selected_action == "warn":
                await self._warn(message.guild, message.author, reason)
                try:
                    await message.channel.send(f"{message.author.mention}, your message violated rules and was warned.", delete_after=8)
                except Exception:
                    pass
                return
            if selected_action == "delete":
                await self._delete_and_log(message, reason)
                try:
                    await message.channel.send(f"{message.author.mention}, your message was removed for policy violation.", delete_after=8)
                except Exception:
                    pass
                return
            if selected_action.startswith("temp_mute"):
                # format temp_mute:seconds or just temp_mute -> default 300s
                parts = selected_action.split(":")
                sec = int(parts[1]) if len(parts) > 1 else 300
                await self._delete_and_log(message, reason)
                await self._temp_mute(message.guild, message.author, sec, reason)
                return
            if selected_action == "kick":
                await self._delete_and_log(message, reason)
                await self._kick(message.guild, message.author, reason)
                return
            if selected_action == "ban":
                await self._delete_and_log(message, reason)
                await self._ban(message.guild, message.author, reason)
                return
        except Exception:
            traceback.print_exc()

    async def _process_image(self, message: discord.Message, ai_cfg: Dict[str, Any]):
        # if image moderation enabled, this is a stub: remove or warn on attachments flagged by naive rule
        for att in message.attachments:
            # naive stub: filename contains 'nsfw' or 'adult'
            if any(x in att.filename.lower() for x in ("nsfw", "adult")):
                reason = "AI image moderation flagged (stub)"
                await self._delete_and_log(message, reason)
                await self._warn(message.guild, message.author, reason)
                return

    # ------------------------
    # Event listener
    # ------------------------
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if not message.guild or message.author.bot:
            return
        await self.db.ensure_guild(message.guild.id)
        cfg = await self.db.get_guild_config(message.guild.id)
        ai_cfg = cfg.get("ai", DEFAULT_AI_CONFIG.copy())
        if not ai_cfg.get("enabled", False):
            return
        # whitelisting: user, channel, roles
        whitelist = ai_cfg.get("whitelist", [])
        if message.author.id in whitelist:
            return
        if message.channel.id in whitelist:
            return
        if any(r.id in whitelist for r in getattr(message.author, "roles", [])):
            return
        # text moderation
        if ai_cfg.get("text_moderation", True) and message.content:
            await self._process_text(message, ai_cfg)
        # image moderation
        if ai_cfg.get("image_moderation", False) and message.attachments:
            await self._process_image(message, ai_cfg)

    # ------------------------
    # Slash commands (slash-only)
    # ------------------------
    aimod = app_commands.Group(name="aimod", description="AI moderation commands (Perspective API)")

    @aimod.command(name="status", description="Show AI moderation status for this guild")
    async def cmd_status(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        await self.db.ensure_guild(interaction.guild.id)
        cfg = await self.db.get_guild_config(interaction.guild.id)
        ai_cfg = cfg.get("ai", DEFAULT_AI_CONFIG.copy())
        desc = f"Enabled: `{ai_cfg.get('enabled', False)}`\nText: `{ai_cfg.get('text_moderation', True)}`\nImage: `{ai_cfg.get('image_moderation', False)}`\nLog Channel: `{ai_cfg.get('log_channel_id')}`"
        await interaction.followup.send(embed=self.emb.info("AI Moderation Status", desc), ephemeral=True)

    @aimod.command(name="enable", description="Enable AI moderation in this guild")
    async def cmd_enable(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        if not PERSPECTIVE_API_KEY:
            await interaction.followup.send(embed=self.emb.error("Perspective API missing", "Set PERSPECTIVE_API_KEY in environment."), ephemeral=True)
            return
        if not await self._is_mod(interaction.user if isinstance(interaction.user, discord.Member) else interaction.user):
            await interaction.followup.send(embed=self.emb.error("Permission denied", "You must be a configured moderator to do this."), ephemeral=True)
            return
        await self.db.ensure_guild(interaction.guild.id)
        cfg = await self.db.get_guild_config(interaction.guild.id)
        ai_cfg = cfg.get("ai", DEFAULT_AI_CONFIG.copy())
        ai_cfg["enabled"] = True
        cfg["ai"] = ai_cfg
        await self.db.set_guild_config(interaction.guild.id, cfg)
        await interaction.followup.send(embed=self.emb.success("AI moderation enabled", "AI moderation is now enabled in this guild."), ephemeral=True)

    @aimod.command(name="disable", description="Disable AI moderation in this guild")
    async def cmd_disable(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        if not await self._is_mod(interaction.user if isinstance(interaction.user, discord.Member) else interaction.user):
            await interaction.followup.send(embed=self.emb.error("Permission denied", "You must be a configured moderator to do this."), ephemeral=True)
            return
        await self.db.ensure_guild(interaction.guild.id)
        cfg = await self.db.get_guild_config(interaction.guild.id)
        ai_cfg = cfg.get("ai", DEFAULT_AI_CONFIG.copy())
        ai_cfg["enabled"] = False
        cfg["ai"] = ai_cfg
        await self.db.set_guild_config(interaction.guild.id, cfg)
        await interaction.followup.send(embed=self.emb.success("AI moderation disabled", "AI moderation is now disabled in this guild."), ephemeral=True)

    @aimod.command(name="setlog", description="Set the AI moderation log channel")
    async def cmd_setlog(self, interaction: discord.Interaction, channel: discord.TextChannel):
        await interaction.response.defer(ephemeral=True)
        if not await self._is_mod(interaction.user if isinstance(interaction.user, discord.Member) else interaction.user):
            await interaction.followup.send(embed=self.emb.error("Permission denied", "You must be a configured moderator to do this."), ephemeral=True)
            return
        await self.db.ensure_guild(interaction.guild.id)
        cfg = await self.db.get_guild_config(interaction.guild.id)
        ai_cfg = cfg.get("ai", DEFAULT_AI_CONFIG.copy())
        ai_cfg["log_channel_id"] = channel.id
        cfg["ai"] = ai_cfg
        await self.db.set_guild_config(interaction.guild.id, cfg)
        await interaction.followup.send(embed=self.emb.success("Log channel set", f"AI moderation logs will be sent to {channel.mention}."), ephemeral=True)

    @aimod.command(name="whitelist_add", description="Add user/role/channel to AI whitelist (no moderation applied)")
    async def cmd_whitelist_add(self, interaction: discord.Interaction, entity: discord.abc.Snowflake):
        await interaction.response.defer(ephemeral=True)
        if not await self._is_mod(interaction.user if isinstance(interaction.user, discord.Member) else interaction.user):
            await interaction.followup.send(embed=self.emb.error("Permission denied", "You must be a configured moderator to do this."), ephemeral=True)
            return
        await self.db.ensure_guild(interaction.guild.id)
        cfg = await self.db.get_guild_config(interaction.guild.id)
        ai_cfg = cfg.get("ai", DEFAULT_AI_CONFIG.copy())
        wl = ai_cfg.get("whitelist", [])
        if entity.id in wl:
            await interaction.followup.send(embed=self.emb.warning("Already whitelisted", f"{getattr(entity, 'mention', str(entity.id))} is already whitelisted."), ephemeral=True)
            return
        wl.append(entity.id)
        ai_cfg["whitelist"] = wl
        cfg["ai"] = ai_cfg
        await self.db.set_guild_config(interaction.guild.id, cfg)
        await interaction.followup.send(embed=self.emb.success("Whitelisted", f"{getattr(entity, 'mention', str(entity.id))} will be exempt from AI moderation."), ephemeral=True)

    @aimod.command(name="whitelist_remove", description="Remove an entity from AI whitelist")
    async def cmd_whitelist_remove(self, interaction: discord.Interaction, entity: discord.abc.Snowflake):
        await interaction.response.defer(ephemeral=True)
        if not await self._is_mod(interaction.user if isinstance(interaction.user, discord.Member) else interaction.user):
            await interaction.followup.send(embed=self.emb.error("Permission denied", "You must be a configured moderator to do this."), ephemeral=True)
            return
        await self.db.ensure_guild(interaction.guild.id)
        cfg = await self.db.get_guild_config(interaction.guild.id)
        ai_cfg = cfg.get("ai", DEFAULT_AI_CONFIG.copy())
        wl = ai_cfg.get("whitelist", [])
        if entity.id not in wl:
            await interaction.followup.send(embed=self.emb.warning("Not found", f"{getattr(entity, 'mention', str(entity.id))} was not whitelisted."), ephemeral=True)
            return
        wl = [x for x in wl if x != entity.id]
        ai_cfg["whitelist"] = wl
        cfg["ai"] = ai_cfg
        await self.db.set_guild_config(interaction.guild.id, cfg)
        await interaction.followup.send(embed=self.emb.success("Removed", f"{getattr(entity, 'mention', str(entity.id))} removed from whitelist."), ephemeral=True)

    @aimod.command(name="test", description="Test AI moderation on a text snippet (Perspective API)")
    async def cmd_test(self, interaction: discord.Interaction, *, text: str):
        await interaction.response.defer(ephemeral=True)
        if not PERSPECTIVE_API_KEY:
            await interaction.followup.send(embed=self.emb.error("Perspective API missing", "Set PERSPECTIVE_API_KEY in environment."), ephemeral=True)
            return
        try:
            resp = await self.persp.analyze(text)
            if resp.get("error"):
                await interaction.followup.send(embed=self.emb.error("API error", str(resp.get("error"))), ephemeral=True)
                return
            attr_scores = {}
            if "attributeScores" in resp:
                for k, v in resp["attributeScores"].items():
                    try:
                        val = v.get("summaryScore", {}).get("value", 0.0)
                    except Exception:
                        val = 0.0
                    attr_scores[k] = float(val or 0.0)
            details = "\n".join(f"{k}: {v:.3f}" for k, v in attr_scores.items())
            flagged = any(attr_scores.get(k, 0) >= DEFAULT_AI_CONFIG["thresholds"].get(k, 0.8) for k in attr_scores)
            await interaction.followup.send(embed=self.emb.warning("AI Test - Flagged", details) if flagged else self.emb.success("AI Test - Clean", details), ephemeral=True)
        except Exception as e:
            await interaction.followup.send(embed=self.emb.error("Test failed", str(e)), ephemeral=True)

    @aimod.command(name="set_threshold", description="Set threshold for a category (0.0 - 1.0). Example: /aimod set_threshold TOXICITY 0.85")
    async def cmd_set_threshold(self, interaction: discord.Interaction, category: str, threshold: float):
        await interaction.response.defer(ephemeral=True)
        if not await self._is_mod(interaction.user if isinstance(interaction.user, discord.Member) else interaction.user):
            await interaction.followup.send(embed=self.emb.error("Permission denied", "You must be a configured moderator."), ephemeral=True)
            return
        if not (0.0 <= threshold <= 1.0):
            await interaction.followup.send(embed=self.emb.error("Invalid threshold", "Provide a value between 0.0 and 1.0."), ephemeral=True)
            return
        await self.db.ensure_guild(interaction.guild.id)
        cfg = await self.db.get_guild_config(interaction.guild.id)
        ai_cfg = cfg.get("ai", DEFAULT_AI_CONFIG.copy())
        ths = ai_cfg.get("thresholds", {})
        ths[category.upper()] = float(threshold)
        ai_cfg["thresholds"] = ths
        cfg["ai"] = ai_cfg
        await self.db.set_guild_config(interaction.guild.id, cfg)
        await interaction.followup.send(embed=self.emb.success("Threshold updated", f"{category.upper()} -> {threshold}"), ephemeral=True)

    @aimod.command(name="set_action", description="Set moderation action for a category (delete|warn|temp_mute:sec|kick|ban|none)")
    async def cmd_set_action(self, interaction: discord.Interaction, category: str, action: str):
        await interaction.response.defer(ephemeral=True)
        if not await self._is_mod(interaction.user if isinstance(interaction.user, discord.Member) else interaction.user):
            await interaction.followup.send(embed=self.emb.error("Permission denied", "You must be a configured moderator."), ephemeral=True)
            return
        await self.db.ensure_guild(interaction.guild.id)
        cfg = await self.db.get_guild_config(interaction.guild.id)
        ai_cfg = cfg.get("ai", DEFAULT_AI_CONFIG.copy())
        acts = ai_cfg.get("actions", {})
        acts[category.upper()] = action
        ai_cfg["actions"] = acts
        cfg["ai"] = ai_cfg
        await self.db.set_guild_config(interaction.guild.id, cfg)
        await interaction.followup.send(embed=self.emb.success("Action set", f"{category.upper()} -> {action}"), ephemeral=True)

    @aimod.command(name="set_category_enabled", description="Enable or disable a category")
    async def cmd_set_category_enabled(self, interaction: discord.Interaction, category: str, enabled: bool):
        await interaction.response.defer(ephemeral=True)
        if not await self._is_mod(interaction.user if isinstance(interaction.user, discord.Member) else interaction.user):
            await interaction.followup.send(embed=self.emb.error("Permission denied", "You must be a configured moderator."), ephemeral=True)
            return
        await self.db.ensure_guild(interaction.guild.id)
        cfg = await self.db.get_guild_config(interaction.guild.id)
        ai_cfg = cfg.get("ai", DEFAULT_AI_CONFIG.copy())
        cats = ai_cfg.get("categories_enabled", {})
        cats[category.upper()] = bool(enabled)
        ai_cfg["categories_enabled"] = cats
        cfg["ai"] = ai_cfg
        await self.db.set_guild_config(interaction.guild.id, cfg)
        await interaction.followup.send(embed=self.emb.success("Category updated", f"{category.upper()} enabled={enabled}"), ephemeral=True)


# Setup
async def setup(bot: commands.Bot):
    cog = AIModerationCog(bot)
    await bot.add_cog(cog)
    # ensure DB connected
    if not hasattr(bot, "moderation_db"):
        bot.moderation_db = ModerationDB(DB_PATH)
    await bot.moderation_db.connect()
 
