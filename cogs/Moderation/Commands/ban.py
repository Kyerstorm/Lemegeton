# cogs/ban.py
"""
BanCog (slash-only). Features:
- /ban, /tempban, /unban (slash-only)
- DM to banned user with "Appeal" button -> opens Modal -> posts to configured appeals channel
- Staff Accept / Reject buttons (only staff: admin OR kick+ban+moderate)
- Moderator must provide reason on accept/reject; the same embed is edited with decision
- Auto-unban for tempbans; tempbans stored in tempbans.json
- Guild configuration stored in guildconfig.json (appeals channel id, mod-log channel id)
- Royal Blue & Silver aesthetic theme
"""

from __future__ import annotations
import os
import json
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Any

import discord
from discord import app_commands
from discord.ext import commands, tasks

LOG = logging.getLogger("BanCog")
LOG.setLevel(logging.INFO)

# -------------------------
# PART 1 - CONFIG & HELPERS
# -------------------------
# Aesthetic theme: Royal Blue & Silver
EMBED_COLOR = 0x4169E1  # Royal Blue
SILVER = 0xC0C0C0

# Storage files (two separate files as requested)
GUILDCONFIG_STORE = "data/guildconfig.json"   # stores: { guild_id: { "appeals_channel_id": int, "mod_log_channel_id": int } }
TEMPBANS_STORE = "data/tempbans.json"         # stores: { guild_id: { user_id: unban_iso } }
APPEALS_STORE = "data/appeals.json"           # optional: store appeals for persistence (keeps simple history)

TEMP_CHECK_INTERVAL = 60  # seconds

# ensure directories exist
def ensure_dir_for(path: str) -> None:
    directory = os.path.dirname(path)
    if directory and not os.path.exists(directory):
        os.makedirs(directory, exist_ok=True)

def atomic_write_json(path: str, data: Dict[str, Any]) -> None:
    ensure_dir_for(path)
    tmp = f"{path}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, default=str, ensure_ascii=False)
    os.replace(tmp, path)

def load_json(path: str) -> Dict[str, Any]:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return {}
    except Exception:
        LOG.exception("Failed to load JSON: %s", path)
        return {}

def parse_duration_to_seconds(s: str) -> Optional[int]:
    """Parse duration strings like '30m', '2h', '1d', '3d12h', '1w' -> seconds"""
    if not s:
        return None
    s = s.strip().lower()
    multipliers = {"w": 7 * 24 * 3600, "d": 24 * 3600, "h": 3600, "m": 60, "s": 1}
    total = 0
    num = ""
    i = 0
    while i < len(s):
        ch = s[i]
        if ch.isdigit():
            num += ch
            i += 1
            continue
        if ch in multipliers and num:
            total += int(num) * multipliers[ch]
            num = ""
            i += 1
            continue
        return None
    if num:
        total += int(num)
    return total if total > 0 else None

def human_readable_delta(delta: timedelta) -> str:
    total = int(delta.total_seconds())
    days, rem = divmod(total, 86400)
    hours, rem = divmod(rem, 3600)
    minutes, seconds = divmod(rem, 60)
    parts = []
    if days:
        parts.append(f"{days}d")
    if hours:
        parts.append(f"{hours}h")
    if minutes:
        parts.append(f"{minutes}m")
    if seconds and not parts:
        parts.append(f"{seconds}s")
    return " ".join(parts) if parts else "0s"

def embed_base(title: Optional[str] = None, color: int = EMBED_COLOR, footer: Optional[str] = None) -> discord.Embed:
    e = discord.Embed(color=color, timestamp=datetime.utcnow())
    if title:
        e.title = title
    footer_text = footer or "Moderation • Powered by Bot"
    e.set_footer(text=footer_text)
    return e

# -------------------------
# PART 2 - PERMISSIONS & UI CHECKS
# -------------------------
def is_staff(member: discord.Member) -> bool:
    """Admin OR (kick_members AND ban_members AND moderate_members)"""
    perms = member.guild_permissions
    if perms.administrator:
        return True
    if perms.kick_members and perms.ban_members and perms.moderate_members:
        return True
    return False

# app command check for staff
async def mod_interaction_check(interaction: discord.Interaction) -> bool:
    if not interaction.guild:
        raise app_commands.AppCommandError("This command can only be used in a server.")
    if is_staff(interaction.user):  # type: ignore
        return True
    raise app_commands.AppCommandError("You must be an administrator or have Kick, Ban and Moderate permissions.")

def mod_check_decorator():
    return app_commands.check(mod_interaction_check)

# -------------------------
# PART 3 - UI: Modal / Views for appeals & moderator decisions
# -------------------------
class AppealModal(discord.ui.Modal, title="Submit an Appeal"):
    def __init__(self, cog: "BanCog", guild_id: int, banned_user_id: int):
        super().__init__()
        self.cog = cog
        self.guild_id = guild_id
        self.banned_user_id = banned_user_id

        self.appeal_text = discord.ui.TextInput(
            label="Why should you be unbanned?",
            style=discord.TextStyle.long,
            placeholder="Explain why you should be unbanned. Be honest and detailed.",
            required=True,
            max_length=2000
        )
        self.add_item(self.appeal_text)

        self.extra = discord.ui.TextInput(
            label="Anything else? (optional)",
            style=discord.TextStyle.paragraph,
            required=False,
            max_length=1000
        )
        self.add_item(self.extra)

    async def on_submit(self, interaction: discord.Interaction):
        # protect duplicates: one pending appeal per user per guild
        gid = str(self.guild_id)
        pending = [a for a in self.cog.appeals.values() if str(a.get("guild_id")) == gid and int(a.get("banned_user_id", 0)) == self.banned_user_id and a.get("status") == "pending"]
        if len(pending) >= 1:
            await interaction.response.send_message("You already have a pending appeal for this server. Please wait for staff to review it.", ephemeral=True)
            return

        appeal_id = f"{self.guild_id}-{self.banned_user_id}-{int(datetime.utcnow().timestamp())}"
        rec = {
            "id": appeal_id,
            "guild_id": int(self.guild_id),
            "banned_user_id": int(self.banned_user_id),
            "appeal_text": str(self.appeal_text.value),
            "extra": str(self.extra.value) if self.extra.value else "",
            "submitted_at": datetime.utcnow().isoformat(),
            "status": "pending",
            "moderator_id": None,
            "moderator_reason": None,
            "decision_at": None,
            "appeal_channel_id": None,
            "appeal_message_id": None,
        }

        # persist appeals history (optional)
        self.cog.appeals[appeal_id] = rec
        try:
            atomic_write_json(self.cog.appeals_store, self.cog.appeals)
        except Exception:
            LOG.exception("Failed to persist appeals")

        # post to configured appeals channel
        guild = self.cog.bot.get_guild(self.guild_id)
        embed = embed_base(title="📝 New Ban Appeal", color=EMBED_COLOR, footer=self.cog.footer_text)
        embed.description = f"Appeal from <@{self.banned_user_id}> (`{self.banned_user_id}`)"
        embed.add_field(name="Appeal", value=rec["appeal_text"], inline=False)
        if rec["extra"]:
            embed.add_field(name="Extra", value=rec["extra"], inline=False)
        embed.add_field(name="Submitted (UTC)", value=rec["submitted_at"], inline=False)
        embed.set_footer(text=f"Appeal ID: {appeal_id}")

        if guild:
            ch = await self.cog._get_appeals_channel(guild)
            if ch:
                view = ModeratorDecisionView(self.cog, appeal_id=appeal_id)
                try:
                    msg = await ch.send(embed=embed, view=view)
                    rec["appeal_channel_id"] = ch.id
                    rec["appeal_message_id"] = msg.id
                    atomic_write_json(self.cog.appeals_store, self.cog.appeals)
                    await interaction.response.send_message("✅ Your appeal was submitted to server staff. You will be notified of the decision.", ephemeral=True)
                    await self.cog._mod_log(guild, f"Appeal `{appeal_id}` submitted by <@{self.banned_user_id}>")
                    return
                except Exception:
                    LOG.exception("Failed to post appeal to appeals channel for guild %s", guild.id)
                    await interaction.response.send_message("Your appeal was recorded, but I couldn't post it to the server (missing permissions). Contact staff manually.", ephemeral=True)
                    return

        await interaction.response.send_message("Your appeal was recorded, but the server appeals channel was not found. Contact staff manually.", ephemeral=True)

class ModeratorReasonModal(discord.ui.Modal):
    def __init__(self, cog: "BanCog", appeal_id: str, action: str):
        title = "Accept Appeal" if action == "accept" else "Reject Appeal"
        super().__init__(title=title)
        self.cog = cog
        self.appeal_id = appeal_id
        self.action = action
        self.reason = discord.ui.TextInput(
            label="Moderator Reason (required)",
            style=discord.TextStyle.long,
            placeholder="Explain why you accept or reject this appeal...",
            required=True,
            max_length=2000
        )
        self.add_item(self.reason)

    async def on_submit(self, interaction: discord.Interaction):
        rec = self.cog.appeals.get(self.appeal_id)
        if not rec:
            await interaction.response.send_message("Appeal not found or already processed.", ephemeral=True)
            return

        guild = self.cog.bot.get_guild(int(rec["guild_id"]))
        if not guild:
            await interaction.response.send_message("Guild not found.", ephemeral=True)
            return

        # permission check: only staff may decide
        member = guild.get_member(interaction.user.id)
        if not member or not is_staff(member):
            await interaction.response.send_message("You don't have permission to process appeals.", ephemeral=True)
            return

        # update record
        rec["status"] = "accepted" if self.action == "accept" else "rejected"
        rec["moderator_id"] = int(interaction.user.id)
        rec["moderator_reason"] = str(self.reason.value)
        rec["decision_at"] = datetime.utcnow().isoformat()
        try:
            atomic_write_json(self.cog.appeals_store, self.cog.appeals)
        except Exception:
            LOG.exception("Failed to persist appeal decision")

        # edit original embed in appeals channel (if present)
        msg_obj = None
        if rec.get("appeal_channel_id") and rec.get("appeal_message_id"):
            ch = guild.get_channel(int(rec["appeal_channel_id"]))
            if ch:
                try:
                    msg_obj = await ch.fetch_message(int(rec["appeal_message_id"]))
                except Exception:
                    msg_obj = None

        decision_color = EMBED_COLOR if rec["status"] == "accepted" else discord.Colour.red().value
        decision_embed = embed_base(title=f"🧾 Appeal {rec['status'].capitalize()}", color=decision_color, footer=self.cog.footer_text)
        decision_embed.description = (
            f"Appeal ID: `{self.appeal_id}`\n"
            f"User: <@{rec['banned_user_id']}> (`{rec['banned_user_id']}`)\n"
            f"Moderator: {interaction.user} (`{interaction.user.id}`)"
        )
        decision_embed.add_field(name="Moderator Reason", value=rec["moderator_reason"], inline=False)
        decision_embed.add_field(name="Original Appeal", value=rec["appeal_text"], inline=False)
        decision_embed.add_field(name="Submitted (UTC)", value=rec["submitted_at"], inline=False)
        decision_embed.set_footer(text=f"Decision at (UTC): {rec['decision_at']}")

        if msg_obj:
            try:
                await msg_obj.edit(embed=decision_embed, view=None)
            except Exception:
                LOG.exception("Failed to edit appeal message in channel %s", ch.id)

        # perform action
        if rec["status"] == "accepted":
            try:
                target = discord.Object(id=int(rec["banned_user_id"]))
                await guild.unban(target, reason=f"Appeal accepted by {interaction.user} — {rec['moderator_reason']}")
                # DM the user
                try:
                    usr = await self.cog.bot.fetch_user(int(rec["banned_user_id"]))
                    dm_embed = embed_base(title=f"✅ Appeal Accepted in {guild.name}", color=EMBED_COLOR, footer=self.cog.footer_text)
                    dm_embed.description = f"Your appeal was accepted by {interaction.user}.\nModerator reason: {rec['moderator_reason']}"
                    await usr.send(embed=dm_embed)
                except Exception:
                    LOG.exception("Failed to DM user after appeal accepted")
                await interaction.response.send_message(f"Appeal `{self.appeal_id}` accepted — user unbanned.", ephemeral=True)
                await self.cog._mod_log(guild, f"Appeal `{self.appeal_id}` accepted by {interaction.user} (`{interaction.user.id}`).")
            except Exception as exc:
                LOG.exception("Failed to unban on appeal accept: %s", exc)
                await interaction.response.send_message("Attempted to unban but failed (missing bot permission or role hierarchy). Check mod-log.", ephemeral=True)
                await self.cog._mod_log(guild, f"Appeal `{self.appeal_id}` accepted by {interaction.user} but unban failed: {exc}")
        else:
            # rejected -> DM the user
            try:
                usr = await self.cog.bot.fetch_user(int(rec["banned_user_id"]))
                dm_embed = embed_base(title=f"❌ Appeal Rejected in {guild.name}", color=discord.Colour.red().value, footer=self.cog.footer_text)
                dm_embed.description = f"Your appeal was rejected by {interaction.user}.\nModerator reason: {rec['moderator_reason']}"
                await usr.send(embed=dm_embed)
            except Exception:
                LOG.exception("Failed to DM user after appeal rejected")
            await interaction.response.send_message(f"Appeal `{self.appeal_id}` rejected.", ephemeral=True)
            await self.cog._mod_log(guild, f"Appeal `{self.appeal_id}` rejected by {interaction.user} (`{interaction.user.id}`).")

class AppealButtonView(discord.ui.View):
    def __init__(self, cog: "BanCog", guild_id: int, banned_user_id: int):
        super().__init__(timeout=None)
        self.cog = cog
        self.guild_id = guild_id
        self.banned_user_id = banned_user_id

    @discord.ui.button(label="📝 Appeal Ban", style=discord.ButtonStyle.primary, custom_id="appeal_button")
    async def appeal_button(self, button: discord.ui.Button, interaction: discord.Interaction):
        # open modal in DM
        modal = AppealModal(self.cog, guild_id=self.guild_id, banned_user_id=self.banned_user_id)
        await interaction.response.send_modal(modal)

class ModeratorDecisionView(discord.ui.View):
    def __init__(self, cog: "BanCog", appeal_id: str):
        super().__init__(timeout=None)
        self.cog = cog
        self.appeal_id = appeal_id

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        rec = self.cog.appeals.get(self.appeal_id)
        if not rec:
            await interaction.response.send_message("Appeal not found.", ephemeral=True)
            return False
        guild = self.cog.bot.get_guild(int(rec["guild_id"]))
        if not guild:
            await interaction.response.send_message("Guild not found.", ephemeral=True)
            return False
        member = guild.get_member(interaction.user.id)
        if not member or not is_staff(member):
            await interaction.response.send_message("You don't have permission to process appeals.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="✅ Accept", style=discord.ButtonStyle.success, custom_id="appeal_accept")
    async def accept(self, button: discord.ui.Button, interaction: discord.Interaction):
        modal = ModeratorReasonModal(self.cog, appeal_id=self.appeal_id, action="accept")
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="❌ Reject", style=discord.ButtonStyle.danger, custom_id="appeal_reject")
    async def reject(self, button: discord.ui.Button, interaction: discord.Interaction):
        modal = ModeratorReasonModal(self.cog, appeal_id=self.appeal_id, action="reject")
        await interaction.response.send_modal(modal)

# -------------------------
# PART 4 - COG CORE (commands & stores)
# -------------------------
class BanCog(commands.Cog):
    def __init__(self, bot: commands.Bot, *, config: Optional[Dict[str, Any]] = None):
        super().__init__()
        self.bot = bot
        cfg = config or {}
        self.footer_text = cfg.get("footer_text", "Moderation • Powered by Bot")
        self.config_store = load_json(GUILDCONFIG_STORE)  # { guild_id: {...} }
        self.tempbans = load_json(TEMPBANS_STORE)         # { guild_id: { user_id: iso } }
        self.appeals = load_json(APPEALS_STORE)           # { appeal_id: rec }
        self.appeals_store = APPEALS_STORE
        self.guildconfig_store = GUILDCONFIG_STORE
        self.tempban_store = TEMPBANS_STORE

        # start unban checker
        self.unban_task.start()

        # register the app commands under a command group for neatness
        # but per your request, commands are /ban, /tempban, /unban, /setappealschannel
        bot.tree.add_command(self._build_ban_command())
        bot.tree.add_command(self._build_tempban_command())
        bot.tree.add_command(self._build_unban_command())
        bot.tree.add_command(self._build_appeals_command())
        bot.tree.add_command(self._build_setappeals_command())
        bot.tree.add_command(self._build_setmodlog_command())
        bot.tree.add_command(self._build_showconfig_command())
        bot.tree.add_command(self._build_export_command())

    # -------------------------
    # Low-level helpers
    # -------------------------
    async def _get_guildconfig(self, guild: discord.Guild) -> Dict[str, Any]:
        return self.config_store.get(str(guild.id), {})

    async def _set_guildconfig(self, guild: discord.Guild, key: str, value: Any) -> None:
        self.config_store.setdefault(str(guild.id), {})
        self.config_store[str(guild.id)][key] = value
        try:
            atomic_write_json(self.guildconfig_store, self.config_store)
        except Exception:
            LOG.exception("Failed to persist guild config")

    async def _get_appeals_channel(self, guild: discord.Guild) -> Optional[discord.TextChannel]:
        cfg = self.config_store.get(str(guild.id), {})
        cid = cfg.get("appeals_channel_id")
        if cid:
            ch = guild.get_channel(int(cid))
            if ch:
                return ch
        # fallback: find by configured name
        name = cfg.get("appeals_channel_name", "appeals")
        for c in guild.text_channels:
            if c.name == name:
                return c
        return None

    async def _get_mod_log_channel(self, guild: discord.Guild) -> Optional[discord.TextChannel]:
        cfg = self.config_store.get(str(guild.id), {})
        cid = cfg.get("mod_log_channel_id")
        if cid:
            ch = guild.get_channel(int(cid))
            if ch:
                return ch
        name = cfg.get("mod_log_channel_name", "mod-log")
        for c in guild.text_channels:
            if c.name == name:
                return c
        return None

    async def _mod_log(self, guild: discord.Guild, message: str):
        ch = await self._get_mod_log_channel(guild)
        embed = embed_base(color=SILVER, footer=self.footer_text)
        embed.title = "📜 Moderation Log"
        embed.description = message
        embed.timestamp = datetime.utcnow()
        try:
            if ch:
                await ch.send(embed=embed)
            else:
                LOG.info("No mod-log channel for guild %s — message: %s", guild.id, message)
        except Exception:
            LOG.exception("Failed to send mod-log for guild %s", guild.id)

    # -------------------------
    # Auto-unban loop
    # -------------------------
    @tasks.loop(seconds=TEMP_CHECK_INTERVAL)
    async def unban_task(self):
        now = datetime.utcnow()
        changed = False
        for gid, mapping in list(self.tempbans.items()):
            guild = self.bot.get_guild(int(gid))
            if not guild:
                continue
            for uid, iso in list(mapping.items()):
                try:
                    unban_at = datetime.fromisoformat(iso)
                except Exception:
                    continue
                if now >= unban_at:
                    try:
                        obj = discord.Object(id=int(uid))
                        await guild.unban(obj, reason="Temporary ban expired (automated).")
                        await self._mod_log(guild, f"User <@{uid}> (`{uid}`) auto-unbanned (tempban expired).")
                    except Exception:
                        LOG.exception("Auto-unban failed for %s in guild %s", uid, gid)
                    try:
                        del self.tempbans[gid][uid]
                        changed = True
                    except Exception:
                        pass
            if gid in self.tempbans and not self.tempbans[gid]:
                del self.tempbans[gid]
                changed = True
        if changed:
            try:
                atomic_write_json(self.tempban_store, self.tempbans)
            except Exception:
                LOG.exception("Failed to persist tempbans after unban run")

    @unban_task.before_loop
    async def before_unban_task(self):
        await self.bot.wait_until_ready()

    # -------------------------
    # Command builders (slash-only)
    # -------------------------
    def _build_ban_command(self) -> app_commands.Command:
        @app_commands.command(name="ban", description="🔨 Permanently ban a member (staff only). Provide a reason.")
        @app_commands.check(mod_interaction_check)
        async def ban_cmd(interaction: discord.Interaction, member: discord.Member, reason: Optional[str] = None):
            reason_text = reason or "No reason provided"
            if not interaction.guild:
                return await interaction.response.send_message("This command must be used in a server.", ephemeral=True)
            if member == interaction.user:
                return await interaction.response.send_message("You cannot ban yourself.", ephemeral=True)
            if member == interaction.guild.me:
                return await interaction.response.send_message("I cannot ban myself.", ephemeral=True)
            if interaction.user != interaction.guild.owner and interaction.user.top_role <= member.top_role:
                return await interaction.response.send_message("You cannot ban someone with an equal or higher top role.", ephemeral=True)

            # confirmation ephemeral
            view = ConfirmView(interaction.user)
            e = embed_base(title="⚠️ Confirm Permanent Ban", color=EMBED_COLOR, footer=self.footer_text)
            e.description = f"Ban **{member}** permanently?\n**Reason:** {reason_text}"
            e.add_field(name="Invoker", value=f"{interaction.user} (`{interaction.user.id}`)", inline=True)
            e.add_field(name="Target", value=f"{member} (`{member.id}`)", inline=True)
            await interaction.response.send_message(embed=e, view=view, ephemeral=True)
            await view.wait()
            if view.value is not True:
                return

            # DM attempt with Appeal button
            dm_embed = embed_base(title=f"You were banned from {interaction.guild.name}", color=discord.Colour.red().value, footer=self.footer_text)
            dm_embed.description = f"You were permanently banned.\n**Reason:** {reason_text}\nIf you'd like to appeal, click the button below."
            appeal_view = AppealButtonView(self, guild_id=interaction.guild.id, banned_user_id=member.id)
            dm_sent = True
            try:
                await member.send(embed=dm_embed, view=appeal_view)
            except Exception:
                dm_sent = False

            # perform ban
            try:
                await interaction.guild.ban(member, reason=f"{reason_text} — banned by {interaction.user}", delete_message_days=0)
            except Exception as exc:
                LOG.exception("Ban failed: %s", exc)
                return await interaction.followup.send("Failed to ban (missing permission or bot role position).", ephemeral=True)

            # respond to moderator (ephemeral)
            res = embed_base(title="✅ Member Banned", color=discord.Colour.red().value, footer=self.footer_text)
            res.description = f"{member.mention} has been permanently banned."
            res.add_field(name="Reason", value=reason_text, inline=False)
            res.add_field(name="DM", value="Sent ✅" if dm_sent else "Failed ❌", inline=True)
            await interaction.followup.send(embed=res, ephemeral=True)

            await self._mod_log(interaction.guild, f"{member} (`{member.id}`) permanently banned by {interaction.user} (`{interaction.user.id}`). Reason: {reason_text}")

        return app_commands.Command(ban_cmd.callback, name=ban_cmd.name, description=ban_cmd.description)

    def _build_tempban_command(self) -> app_commands.Command:
        @app_commands.command(name="tempban", description="⏳ Temporarily ban a member. Duration examples: 30m, 2h, 1d, 1w")
        @app_commands.check(mod_interaction_check)
        async def tempban_cmd(interaction: discord.Interaction, member: discord.Member, duration: str, reason: Optional[str] = None):
            reason_text = reason or "No reason provided"
            if not interaction.guild:
                return await interaction.response.send_message("This command must be used in a server.", ephemeral=True)
            if member == interaction.user:
                return await interaction.response.send_message("You cannot ban yourself.", ephemeral=True)
            if member == interaction.guild.me:
                return await interaction.response.send_message("I cannot ban myself.", ephemeral=True)
            if interaction.user != interaction.guild.owner and interaction.user.top_role <= member.top_role:
                return await interaction.response.send_message("You cannot ban someone with an equal or higher top role.", ephemeral=True)

            secs = parse_duration_to_seconds(duration)
            if secs is None or secs <= 0:
                return await interaction.response.send_message("Invalid duration format. Examples: `30m`, `2h`, `1d`, `1w`.", ephemeral=True)
            unban_time = datetime.utcnow() + timedelta(seconds=secs)

            view = ConfirmView(interaction.user)
            e = embed_base(title="⚠️ Confirm Temporary Ban", color=EMBED_COLOR, footer=self.footer_text)
            e.description = f"Ban **{member}** for **{human_readable_delta(timedelta(seconds=secs))}**?\n**Reason:** {reason_text}"
            await interaction.response.send_message(embed=e, view=view, ephemeral=True)
            await view.wait()
            if view.value is not True:
                return

            # DM attempt with appeal button
            dm_embed = embed_base(title=f"You were temporarily banned from {interaction.guild.name}", color=discord.Colour.red().value, footer=self.footer_text)
            dm_embed.description = f"Ban length: **{human_readable_delta(timedelta(seconds=secs))}**\n**Reason:** {reason_text}\nAppeal using the button below."
            appeal_view = AppealButtonView(self, guild_id=interaction.guild.id, banned_user_id=member.id)
            dm_sent = True
            try:
                await member.send(embed=dm_embed, view=appeal_view)
            except Exception:
                dm_sent = False

            # perform ban
            try:
                await interaction.guild.ban(member, reason=f"{reason_text} — tempbanned by {interaction.user} until {unban_time.isoformat()}", delete_message_days=0)
            except Exception as exc:
                LOG.exception("Tempban failed: %s", exc)
                return await interaction.followup.send("Failed to tempban (missing permission or bot role position).", ephemeral=True)

            # persist tempban
            gid = str(interaction.guild.id)
            self.tempbans.setdefault(gid, {})
            self.tempbans[gid][str(member.id)] = unban_time.isoformat()
            try:
                atomic_write_json(self.tempban_store, self.tempbans)
            except Exception:
                LOG.exception("Failed to persist tempban")

            res = embed_base(title="✅ Member Temporarily Banned", color=discord.Colour.red().value, footer=self.footer_text)
            res.description = f"{member.mention} has been banned for **{human_readable_delta(timedelta(seconds=secs))}**."
            res.add_field(name="Reason", value=reason_text, inline=False)
            res.add_field(name="DM", value="Sent ✅" if dm_sent else "Failed ❌", inline=True)
            res.add_field(name="Scheduled Unban (UTC)", value=unban_time.isoformat(), inline=False)
            await interaction.followup.send(embed=res, ephemeral=True)

            await self._mod_log(interaction.guild, f"{member} (`{member.id}`) temporarily banned by {interaction.user} (`{interaction.user.id}`) until {unban_time.isoformat()}. Reason: {reason_text}")

        return app_commands.Command(tempban_cmd.callback, name=tempban_cmd.name, description=tempban_cmd.description)

    def _build_unban_command(self) -> app_commands.Command:
        @app_commands.command(name="unban", description="⚖️ Unban a user by ID (staff only).")
        @app_commands.check(mod_interaction_check)
        async def unban_cmd(interaction: discord.Interaction, user_id: str, reason: Optional[str] = None):
            reason_text = reason or "No reason provided"
            if not interaction.guild:
                return await interaction.response.send_message("This command must be used in a server.", ephemeral=True)
            try:
                uid = int(user_id.strip("<@!> "))
            except Exception:
                return await interaction.response.send_message("Invalid user ID.", ephemeral=True)
            try:
                target = await self.bot.fetch_user(uid)
                await interaction.guild.unban(target, reason=f"{reason_text} — unbanned by {interaction.user}")
            except Exception as exc:
                LOG.exception("Unban failed: %s", exc)
                return await interaction.response.send_message("Failed to unban (maybe not banned or missing perms).", ephemeral=True)

            # remove scheduled tempban if present
            gid = str(interaction.guild.id)
            removed = False
            if gid in self.tempbans and str(uid) in self.tempbans[gid]:
                try:
                    del self.tempbans[gid][str(uid)]
                    if not self.tempbans[gid]:
                        del self.tempbans[gid]
                    atomic_write_json(self.tempban_store, self.tempbans)
                    removed = True
                except Exception:
                    LOG.exception("Failed to remove scheduled tempban")

            e = embed_base(title="✅ User Unbanned", color=discord.Colour.green().value, footer=self.footer_text)
            e.description = f"<@{uid}> (`{uid}`) has been unbanned."
            e.add_field(name="Moderator", value=f"{interaction.user} (`{interaction.user.id}`)", inline=False)
            e.add_field(name="Reason", value=reason_text, inline=False)
            if removed:
                e.add_field(name="Note", value="Scheduled tempban removed.", inline=False)
            await interaction.response.send_message(embed=e, ephemeral=True)
            await self._mod_log(interaction.guild, f"<@{uid}> (`{uid}`) unbanned by {interaction.user} (`{interaction.user.id}`). Reason: {reason_text}")

        return app_commands.Command(unban_cmd.callback, name=unban_cmd.name, description=unban_cmd.description)

    def _build_appeals_command(self) -> app_commands.Command:
        @app_commands.command(name="appeals", description="🧾 List pending appeals for this server (staff only).")
        @app_commands.check(mod_interaction_check)
        async def appeals_cmd(interaction: discord.Interaction):
            if not interaction.guild:
                return await interaction.response.send_message("This command must be used in a server.", ephemeral=True)
            gid = str(interaction.guild.id)
            pending = [(aid, a) for aid, a in self.appeals.items() if str(a.get("guild_id")) == gid and a.get("status") == "pending"]
            if not pending:
                e = embed_base(title="Appeals", color=discord.Colour.green().value, footer=self.footer_text)
                e.description = "No pending appeals."
                return await interaction.response.send_message(embed=e, ephemeral=True)
            e = embed_base(title=f"Pending Appeals ({len(pending)})", color=EMBED_COLOR, footer=self.footer_text)
            for aid, rec in pending[:10]:
                snippet = rec.get("appeal_text", "")
                if len(snippet) > 200:
                    snippet = snippet[:197] + "..."
                e.add_field(name=f"ID: {aid}", value=f"{snippet}\nFrom: <@{rec.get('banned_user_id')}>", inline=False)
            await interaction.response.send_message(embed=e, ephemeral=True)
        return app_commands.Command(appeals_cmd.callback, name=appeals_cmd.name, description=appeals_cmd.description)

    def _build_setappeals_command(self) -> app_commands.Command:
        @app_commands.command(name="setappealschannel", description="🛠️ Set the appeals channel for this server (staff only).")
        @app_commands.check(mod_interaction_check)
        async def setappeals_cmd(interaction: discord.Interaction, channel: discord.TextChannel):
            if not interaction.guild:
                return await interaction.response.send_message("This command must be used in a server.", ephemeral=True)
            await self._set_guildconfig(interaction.guild, "appeals_channel_id", int(channel.id))
            e = embed_base(title="Appeals Channel Configured", color=discord.Colour.green().value, footer=self.footer_text)
            e.description = f"Appeals channel set to {channel.mention} (`{channel.id}`)."
            await interaction.response.send_message(embed=e, ephemeral=True)
        return app_commands.Command(setappeals_cmd.callback, name=setappeals_cmd.name, description=setappeals_cmd.description)

    def _build_setmodlog_command(self) -> app_commands.Command:
        @app_commands.command(name="setmodlog", description="🛡️ Set the mod-log channel for this server (staff only).")
        @app_commands.check(mod_interaction_check)
        async def setmodlog_cmd(interaction: discord.Interaction, channel: discord.TextChannel):
            if not interaction.guild:
                return await interaction.response.send_message("This command must be used in a server.", ephemeral=True)
            await self._set_guildconfig(interaction.guild, "mod_log_channel_id", int(channel.id))
            e = embed_base(title="Mod-log Channel Configured", color=discord.Colour.green().value, footer=self.footer_text)
            e.description = f"Mod-log channel set to {channel.mention} (`{channel.id}`)."
            await interaction.response.send_message(embed=e, ephemeral=True)
        return app_commands.Command(setmodlog_cmd.callback, name=setmodlog_cmd.name, description=setmodlog_cmd.description)

    def _build_showconfig_command(self) -> app_commands.Command:
        @app_commands.command(name="showconfig", description="🔍 Show moderation configuration for this server (staff only).")
        @app_commands.check(mod_interaction_check)
        async def showconfig_cmd(interaction: discord.Interaction):
            if not interaction.guild:
                return await interaction.response.send_message("This command must be used in a server.", ephemeral=True)
            cfg = self.config_store.get(str(interaction.guild.id), {})
            e = embed_base(title=f"Moderation Config — {interaction.guild.name}", color=EMBED_COLOR, footer=self.footer_text)
            e.add_field(name="Appeals channel ID", value=str(cfg.get("appeals_channel_id") or "Not set"), inline=False)
            e.add_field(name="Mod-log channel ID", value=str(cfg.get("mod_log_channel_id") or "Not set"), inline=False)
            await interaction.response.send_message(embed=e, ephemeral=True)
        return app_commands.Command(showconfig_cmd.callback, name=showconfig_cmd.name, description=showconfig_cmd.description)

    def _build_export_command(self) -> app_commands.Command:
        @app_commands.command(name="export", description="📤 Export moderation data files to your DMs (staff only).")
        @app_commands.check(mod_interaction_check)
        async def export_cmd(interaction: discord.Interaction):
            files = []
            for path in (self.tempban_store, self.appeals_store, self.guildconfig_store):
                if os.path.exists(path):
                    files.append(path)
            if not files:
                return await interaction.response.send_message("No data files to export.", ephemeral=True)
            try:
                dm = await interaction.user.create_dm()
                sent = 0
                for p in files:
                    try:
                        await dm.send(file=discord.File(p, filename=os.path.basename(p)))
                        sent += 1
                    except Exception:
                        LOG.exception("Failed to send file %s to %s", p, interaction.user)
                await interaction.response.send_message(f"Exported {sent} file(s) to your DMs.", ephemeral=True)
            except Exception:
                LOG.exception("Export failed")
                await interaction.response.send_message("Failed to send files via DM.", ephemeral=True)
        return app_commands.Command(export_cmd.callback, name=export_cmd.name, description=export_cmd.description)

    # -------------------------
    # App command error handling
    # -------------------------
    @commands.Cog.listener()
    async def on_app_command_error(self, interaction: discord.Interaction, error: Exception):
        if isinstance(error, app_commands.AppCommandError):
            try:
                await interaction.response.send_message(str(error), ephemeral=True)
            except Exception:
                LOG.exception("Failed to send AppCommandError response")
        else:
            LOG.exception("Unhandled app command error: %s", error)
            try:
                await interaction.response.send_message("An unexpected error occurred. Check logs.", ephemeral=True)
            except Exception:
                pass

# -------------------------
# PART 5 - Confirm View
# -------------------------
class ConfirmView(discord.ui.View):
    def __init__(self, author: discord.User, timeout: float = 30.0):
        super().__init__(timeout=timeout)
        self.author = author
        self.value: Optional[bool] = None

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author.id:
            await interaction.response.send_message("This confirmation isn't for you.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Confirm", style=discord.ButtonStyle.danger, emoji="🔨", custom_id="confirm_ban")
    async def confirm(self, button: discord.ui.Button, interaction: discord.Interaction):
        self.value = True
        await interaction.response.edit_message(content="✅ Confirmed.", view=None)

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary, emoji="✖️", custom_id="cancel_ban")
    async def cancel(self, button: discord.ui.Button, interaction: discord.Interaction):
        self.value = False
        await interaction.response.edit_message(content="❎ Cancelled.", view=None)

# -------------------------
# Setup entrypoint
# -------------------------
async def setup(bot: commands.Bot, *, config: Optional[Dict[str, Any]] = None):
    """
    Load this cog:
        await bot.load_extension("cogs.ban")
    Optionally pass a small config dict for footer text:
        await bot.load_extension("cogs.ban")
        # setup() receives config via loader if your loader supports it.
    """
    cog = BanCog(bot, config=(config or {}))
    await bot.add_cog(cog)
