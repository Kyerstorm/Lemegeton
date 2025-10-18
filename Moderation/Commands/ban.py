# cogs/ban.py
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

# -------------------------------
# PART 1 — CONFIG, DEFAULTS, HELPERS
# -------------------------------
DEFAULTS: Dict[str, Any] = {
    "tempban_store": "data/tempbans.json",
    "appeals_store": "data/appeals.json",
    "guild_settings_store": "data/guild_settings.json",
    "embed_color": 0x6A0DAD,
    "banner_image_url": None,
    "bot_avatar_url": None,
    "footer_text": "Moderation • Powered by Bot",
    "mod_log_channel_name": "mod-log",
    "appeals_channel_name": "appeals",
    "tempban_check_interval": 60,
    "max_pending_appeals_per_user_per_guild": 1,
}

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
        LOG.exception("Failed to load JSON %s", path)
        return {}

def parse_duration_to_seconds(s: str) -> Optional[int]:
    """30m 2h 1d 3d12h 1w"""
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

# -------------------------------
# PART 2 — PERMISSION CHECKS & UI HELPERS
# -------------------------------
class ModPermissionError(app_commands.AppCommandError):
    pass

async def mod_interaction_check(interaction: discord.Interaction) -> bool:
    """App command check: Administrator OR (kick+ban+moderate)."""
    if not interaction.guild:
        raise app_commands.AppCommandError("This command can only be used in a server.")
    perms = interaction.user.guild_permissions
    if perms.administrator:
        return True
    if perms.kick_members and perms.ban_members and perms.moderate_members:
        return True
    raise app_commands.AppCommandError("You must be an administrator or have Kick, Ban and Moderate permissions.")

def mod_check_decorator():
    return app_commands.check(mod_interaction_check)

# Small embed factory
def embed_base(config: Dict[str, Any], color: Optional[discord.Colour] = None) -> discord.Embed:
    clr = color or discord.Colour(config.get("embed_color", DEFAULTS["embed_color"]))
    e = discord.Embed(color=clr, timestamp=datetime.utcnow())
    banner = config.get("banner_image_url")
    if banner:
        e.set_image(url=banner)
    footer = config.get("footer_text", DEFAULTS["footer_text"])
    e.set_footer(text=footer)
    avatar = config.get("bot_avatar_url")
    if avatar:
        try:
            e.set_thumbnail(url=avatar)
        except Exception:
            pass
    return e

# -------------------------------
# PART 3 — UI: Modals & Views (Appeal flow)
# -------------------------------
class AppealModal(discord.ui.Modal, title="Submit an Appeal"):
    def __init__(self, cog: "BanCog", guild_id: int, banned_user_id: int):
        super().__init__()
        self.cog = cog
        self.guild_id = guild_id
        self.banned_user_id = banned_user_id

        self.appeal_text = discord.ui.TextInput(
            label="Why should you be unbanned?",
            style=discord.TextStyle.long,
            placeholder="Explain your appeal in as much detail as you want...",
            required=True,
            max_length=2000
        )
        self.extra = discord.ui.TextInput(
            label="Anything else? (optional)",
            style=discord.TextStyle.paragraph,
            required=False,
            max_length=1000
        )
        self.add_item(self.appeal_text)
        self.add_item(self.extra)

    async def on_submit(self, interaction: discord.Interaction):
        # Protect from duplicates (limit per-guild)
        gid_str = str(self.guild_id)
        pending = [r for r in self.cog.appeals.values() if int(r["guild_id"]) == self.guild_id and r["banned_user_id"] == self.banned_user_id and r["status"] == "pending"]
        if len(pending) >= self.cog.config["max_pending_appeals_per_user_per_guild"]:
            await interaction.response.send_message("You already have a pending appeal for this server. Wait for staff to review it.", ephemeral=True)
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
            "appeal_message_id": None,
            "appeal_channel_id": None,
        }
        # persist
        self.cog.appeals[appeal_id] = rec
        try:
            atomic_write_json(self.cog.appeals_store, self.cog.appeals)
        except Exception:
            LOG.exception("Failed to save appeal %s", appeal_id)

        # prepare embed for staff
        guild = self.cog.bot.get_guild(self.guild_id)
        embed = embed_base(self.cog.config)
        embed.title = "📝 New Ban Appeal"
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
                    rec["appeal_message_id"] = msg.id
                    rec["appeal_channel_id"] = ch.id
                    atomic_write_json(self.cog.appeals_store, self.cog.appeals)
                    await interaction.response.send_message("✅ Your appeal was submitted to server staff. They will review it soon.", ephemeral=True)
                    await self.cog._send_mod_log_by_guild(guild, title="Appeal Submitted", description=f"Appeal `{appeal_id}` submitted by <@{self.banned_user_id}>")
                    return
                except Exception:
                    LOG.exception("Failed to post appeal to appeals channel for guild %s", guild.id)
                    await interaction.response.send_message("Your appeal was recorded but I couldn't post it to the server (missing permissions). Contact staff manually.", ephemeral=True)
                    return

        await interaction.response.send_message("Your appeal was recorded, but the server appeals channel was not found.", ephemeral=True)

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

        # permission enforcement (only staff)
        member = guild.get_member(interaction.user.id)
        if not member:
            await interaction.response.send_message("You must be a member of the guild to process appeals.", ephemeral=True)
            return
        perms = member.guild_permissions
        if not (perms.administrator or (perms.kick_members and perms.ban_members and perms.moderate_members)):
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
            LOG.exception("Failed to persist appeal decision %s", self.appeal_id)

        # edit the same embed in appeals channel (if available)
        msg_obj = None
        if rec.get("appeal_channel_id") and rec.get("appeal_message_id"):
            ch = guild.get_channel(int(rec["appeal_channel_id"]))
            if ch:
                try:
                    msg_obj = await ch.fetch_message(int(rec["appeal_message_id"]))
                except Exception:
                    msg_obj = None

        decision_embed = embed_base(self.cog.config, color=discord.Colour.green() if rec["status"] == "accepted" else discord.Colour.red())
        decision_embed.title = f"🧾 Appeal {rec['status'].capitalize()}"
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
                LOG.exception("Failed to edit appeal message in guild %s", guild.id)

        # action: accept -> unban; reject -> DM user
        if rec["status"] == "accepted":
            try:
                target = discord.Object(id=int(rec["banned_user_id"]))
                await guild.unban(target, reason=f"Appeal accepted by {interaction.user} — {rec['moderator_reason']}")
                # DM user
                try:
                    user = await self.cog.bot.fetch_user(int(rec["banned_user_id"]))
                    dm = embed_base(self.cog.config, color=discord.Colour.green())
                    dm.title = f"✅ Appeal Accepted in {guild.name}"
                    dm.description = f"Your appeal has been accepted by {interaction.user}.\nModerator reason: {rec['moderator_reason']}"
                    await user.send(embed=dm)
                except Exception:
                    LOG.exception("Failed to DM user after appeal accept")
                await interaction.response.send_message(f"Appeal `{self.appeal_id}` accepted — user unbanned.", ephemeral=True)
                await self.cog._send_mod_log_by_guild(guild, title="Appeal Accepted", description=f"Appeal `{self.appeal_id}` accepted by {interaction.user} (`{interaction.user.id}`).")
            except Exception as exc:
                LOG.exception("Unban via appeal failed: %s", exc)
                await interaction.response.send_message("Tried to unban but failed (missing bot permission or role hierarchy). Check mod-log.", ephemeral=True)
                await self.cog._send_mod_log_by_guild(guild, title="Appeal Accepted (Unban Failed)", description=f"Appeal `{self.appeal_id}` accepted by {interaction.user} but unban failed: {exc}", color=discord.Colour.orange())
        else:
            # rejected
            try:
                user = await self.cog.bot.fetch_user(int(rec["banned_user_id"]))
                dm = embed_base(self.cog.config, color=discord.Colour.red())
                dm.title = f"❌ Appeal Rejected in {guild.name}"
                dm.description = f"Your appeal was rejected by {interaction.user}.\nModerator reason: {rec['moderator_reason']}"
                await user.send(embed=dm)
            except Exception:
                LOG.exception("Failed to DM user after appeal rejection")
            await interaction.response.send_message(f"Appeal `{self.appeal_id}` rejected.", ephemeral=True)
            await self.cog._send_mod_log_by_guild(guild, title="Appeal Rejected", description=f"Appeal `{self.appeal_id}` rejected by {interaction.user} (`{interaction.user.id}`).", color=discord.Colour.red())

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
        if not member:
            await interaction.response.send_message("You must be a guild member to process appeals.", ephemeral=True)
            return False
        perms = member.guild_permissions
        if not (perms.administrator or (perms.kick_members and perms.ban_members and perms.moderate_members)):
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

# -------------------------------
# PART 4 — COG: Commands & Core Moderation
# -------------------------------
class BanCog(commands.Cog):
    def __init__(self, bot: commands.Bot, config: Optional[Dict[str, Any]] = None):
        super().__init__()
        self.bot = bot
        self.config = {**DEFAULTS, **(config or {})}

        # stores
        self.tempban_store = self.config["tempban_store"]
        self.appeals_store = self.config["appeals_store"]
        self.guild_settings_store = self.config["guild_settings_store"]

        ensure_dir_for(self.tempban_store)
        ensure_dir_for(self.appeals_store)
        ensure_dir_for(self.guild_settings_store)

        self.tempbans: Dict[str, Dict[str, str]] = load_json(self.tempban_store)  # {guild_id: {user_id: iso}}
        self.appeals: Dict[str, Dict[str, Any]] = load_json(self.appeals_store)    # {appeal_id: rec}
        self.guild_settings: Dict[str, Dict[str, Any]] = load_json(self.guild_settings_store)

        self.ModeratorDecisionView = ModeratorDecisionView

        # start background task
        self.unban_task.start()

    # --- helper embed maker bound to instance (per-guild could be extended) ---
    def _embed_base(self, color: Optional[discord.Colour] = None) -> discord.Embed:
        return embed_base(self.config, color=color)

    async def _get_mod_log_channel(self, guild: discord.Guild) -> Optional[discord.TextChannel]:
        settings = self.guild_settings.get(str(guild.id), {})
        cid = settings.get("mod_log_channel_id") or self.config.get("mod_log_channel_id")
        if cid:
            try:
                ch = guild.get_channel(int(cid))
                if ch:
                    return ch
            except Exception:
                pass
        # fallback to name
        name = settings.get("mod_log_channel_name") or self.config.get("mod_log_channel_name")
        for c in guild.text_channels:
            if c.name == name:
                return c
        return None

    async def _get_appeals_channel(self, guild: discord.Guild) -> Optional[discord.TextChannel]:
        settings = self.guild_settings.get(str(guild.id), {})
        cid = settings.get("appeals_channel_id") or self.config.get("appeals_channel_id")
        if cid:
            try:
                ch = guild.get_channel(int(cid))
                if ch:
                    return ch
            except Exception:
                pass
        name = settings.get("appeals_channel_name") or self.config.get("appeals_channel_name")
        for c in guild.text_channels:
            if c.name == name:
                return c
        return None

    async def _send_mod_log_by_guild(self, guild: discord.Guild, title: str, description: str, color: Optional[discord.Colour] = None):
        ch = await self._get_mod_log_channel(guild)
        e = self._embed_base(color=color)
        e.title = title
        e.description = description
        try:
            if ch:
                await ch.send(embed=e)
            else:
                LOG.info("No mod-log channel set for guild %s", guild.id)
        except Exception:
            LOG.exception("Failed sending mod log for %s", guild.id)

    async def _dm_user(self, user: discord.User, embed: discord.Embed, view: Optional[discord.ui.View] = None) -> bool:
        try:
            await user.send(embed=embed, view=view)
            return True
        except Exception:
            return False

    # -------------------------
    # Background auto-unban task
    # -------------------------
    @tasks.loop(seconds=DEFAULTS["tempban_check_interval"])
    async def unban_task(self):
        now = datetime.utcnow()
        changed = False
        for gid, entries in list(self.tempbans.items()):
            guild = self.bot.get_guild(int(gid))
            if not guild:
                continue
            for uid, iso_ts in list(entries.items()):
                try:
                    unban_at = datetime.fromisoformat(iso_ts)
                except Exception:
                    continue
                if now >= unban_at:
                    try:
                        target = discord.Object(id=int(uid))
                        await guild.unban(target, reason="Temporary ban expired (automated).")
                        await self._send_mod_log_by_guild(guild, title="Temporary Ban Expired", description=f"User <@{uid}> (`{uid}`) auto-unbanned.", color=discord.Colour.green())
                    except Exception:
                        LOG.exception("Auto-unban failed for %s in guild %s", uid, gid)
                    try:
                        del self.tempbans[gid][uid]
                        changed = True
                    except KeyError:
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
        seconds = int(self.config.get("tempban_check_interval", DEFAULTS["tempban_check_interval"]))
        if seconds != self.unban_task.seconds:
            self.unban_task.change_interval(seconds=seconds)

    # -------------------------
    # Slash commands (app_commands) — top-level, slash-only
    # -------------------------
    @app_commands.command(name="ban", description="Permanently ban a member (staff only).")
    @app_commands.check(mod_interaction_check)
    async def ban(self, interaction: discord.Interaction, member: discord.Member, reason: Optional[str] = None):
        reason = reason or "No reason provided"
        if not interaction.guild:
            return await interaction.response.send_message("This command must be used in a server.", ephemeral=True)

        # basic checks
        if member == interaction.user:
            return await interaction.response.send_message("You cannot ban yourself.", ephemeral=True)
        if member == interaction.guild.me:
            return await interaction.response.send_message("I cannot ban myself.", ephemeral=True)
        if interaction.user != interaction.guild.owner and interaction.user.top_role <= member.top_role:
            return await interaction.response.send_message("You cannot ban someone with an equal or higher top role.", ephemeral=True)

        # confirm via ephemeral followup (UI confirm)
        view = ConfirmView(interaction.user)
        e = self._embed_base(color=discord.Colour.orange())
        e.title = "⚠️ Confirm Permanent Ban"
        e.description = f"Ban **{member}** permanently?\n**Reason:** {reason}"
        e.add_field(name="Invoker", value=f"{interaction.user} (`{interaction.user.id}`)", inline=True)
        e.add_field(name="Target", value=f"{member} (`{member.id}`)", inline=True)
        await interaction.response.send_message(embed=e, view=view, ephemeral=True)
        # wait for the confirm (view sets response)
        await view.wait()
        if view.value is not True:
            return  # cancelled

        # DM the user with Appeal button
        dm = self._embed_base(color=discord.Colour.dark_red())
        dm.title = f"You were banned from {interaction.guild.name}"
        dm.description = f"You were permanently banned.\n**Reason:** {reason}\nIf you'd like to appeal, click the button below."
        appeal_view = AppealButtonView(self, guild_id=interaction.guild.id, banned_user_id=member.id)
        dm_sent = await self._dm_user(member, dm, view=appeal_view)

        # perform ban
        try:
            await interaction.guild.ban(member, reason=f"{reason} — banned by {interaction.user}", delete_message_days=0)
        except Exception as exc:
            LOG.exception("Ban failed: %s", exc)
            return await interaction.followup.send("Failed to ban (missing permission or role hierarchy).", ephemeral=True)

        # public confirmation to invoker
        res = self._embed_base(color=discord.Colour.red())
        res.title = "✅ Member Banned"
        res.description = f"{member.mention} has been permanently banned."
        res.add_field(name="Reason", value=reason, inline=False)
        res.add_field(name="DM", value="Sent ✅" if dm_sent else "Failed ❌", inline=True)
        await interaction.followup.send(embed=res, ephemeral=True)

        await self._send_mod_log_by_guild(interaction.guild, title="Permanent Ban", description=f"{member} (`{member.id}`) was permanently banned by {interaction.user} (`{interaction.user.id}`). Reason: {reason}", color=discord.Colour.red())

    @app_commands.command(name="tempban", description="Temporarily ban a member (staff only). Duration examples: 30m, 2h, 1d, 1w).")
    @app_commands.check(mod_interaction_check)
    async def tempban(self, interaction: discord.Interaction, member: discord.Member, duration: str, reason: Optional[str] = None):
        reason = reason or "No reason provided"
        if not interaction.guild:
            return await interaction.response.send_message("This command must be used in a server.", ephemeral=True)

        if member == interaction.user:
            return await interaction.response.send_message("You cannot ban yourself.", ephemeral=True)
        if member == interaction.guild.me:
            return await interaction.response.send_message("I cannot ban myself.", ephemeral=True)
        if interaction.user != interaction.guild.owner and interaction.user.top_role <= member.top_role:
            return await interaction.response.send_message("You cannot ban someone with an equal or higher top role.", ephemeral=True)

        total_seconds = parse_duration_to_seconds(duration)
        if total_seconds is None or total_seconds <= 0:
            return await interaction.response.send_message("Invalid duration format. Examples: `30m`, `2h`, `1d`, `1w`.", ephemeral=True)

        unban_time = datetime.utcnow() + timedelta(seconds=total_seconds)

        view = ConfirmView(interaction.user)
        e = self._embed_base(color=discord.Colour.orange())
        e.title = "⚠️ Confirm Temporary Ban"
        e.description = f"Ban **{member}** for **{human_readable_delta(timedelta(seconds=total_seconds))}**?\n**Reason:** {reason}"
        await interaction.response.send_message(embed=e, view=view, ephemeral=True)
        await view.wait()
        if view.value is not True:
            return

        # DM user with appeal button
        dm = self._embed_base(color=discord.Colour.dark_red())
        dm.title = f"You were temporarily banned from {interaction.guild.name}"
        dm.description = f"Ban length: **{human_readable_delta(timedelta(seconds=total_seconds))}**\n**Reason:** {reason}\nAppeal using the button below."
        appeal_view = AppealButtonView(self, guild_id=interaction.guild.id, banned_user_id=member.id)
        dm_sent = await self._dm_user(member, dm, view=appeal_view)

        # perform ban
        try:
            await interaction.guild.ban(member, reason=f"{reason} — tempbanned by {interaction.user} until {unban_time.isoformat()}", delete_message_days=0)
        except Exception as exc:
            LOG.exception("Tempban failed: %s", exc)
            return await interaction.followup.send("Failed to tempban (missing permission or role hierarchy).", ephemeral=True)

        # persist tempban
        gid = str(interaction.guild.id)
        self.tempbans.setdefault(gid, {})
        self.tempbans[gid][str(member.id)] = unban_time.isoformat()
        try:
            atomic_write_json(self.tempban_store, self.tempbans)
        except Exception:
            LOG.exception("Failed to persist tempban")

        res = self._embed_base(color=discord.Colour.red())
        res.title = "✅ Member Temporarily Banned"
        res.description = f"{member.mention} has been banned for **{human_readable_delta(timedelta(seconds=total_seconds))}**."
        res.add_field(name="Reason", value=reason, inline=False)
        res.add_field(name="DM", value="Sent ✅" if dm_sent else "Failed ❌", inline=True)
        res.add_field(name="Scheduled Unban (UTC)", value=unban_time.isoformat(), inline=False)
        await interaction.followup.send(embed=res, ephemeral=True)
        await self._send_mod_log_by_guild(interaction.guild, title="Temporary Ban", description=f"{member} (`{member.id}`) was temporarily banned by {interaction.user} (`{interaction.user.id}`) until {unban_time.isoformat()}. Reason: {reason}", color=discord.Colour.red())

    @app_commands.command(name="unban", description="Unban a user by ID (staff only).")
    @app_commands.check(mod_interaction_check)
    async def unban(self, interaction: discord.Interaction, user_id: str, reason: Optional[str] = None):
        reason = reason or "No reason provided"
        if not interaction.guild:
            return await interaction.response.send_message("This command must be used in a server.", ephemeral=True)

        # parse user id
        try:
            uid = int(user_id.strip("<@!> "))
        except Exception:
            return await interaction.response.send_message("Invalid user ID.", ephemeral=True)

        try:
            target = await self.bot.fetch_user(uid)
            await interaction.guild.unban(target, reason=f"{reason} — unbanned by {interaction.user}")
        except Exception as exc:
            LOG.exception("Unban failed: %s", exc)
            return await interaction.response.send_message("Failed to unban (maybe not banned, or missing perms).", ephemeral=True)

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

        e = self._embed_base(color=discord.Colour.green())
        e.title = "✅ User Unbanned"
        e.description = f"<@{uid}> (`{uid}`) has been unbanned."
        e.add_field(name="Moderator", value=f"{interaction.user} (`{interaction.user.id}`)", inline=False)
        e.add_field(name="Reason", value=reason, inline=False)
        if removed:
            e.add_field(name="Note", value="Scheduled tempban removed.", inline=False)
        await interaction.response.send_message(embed=e, ephemeral=True)
        await self._send_mod_log_by_guild(interaction.guild, title="Manual Unban", description=f"<@{uid}> (`{uid}`) unbanned by {interaction.user} (`{interaction.user.id}`). Reason: {reason}", color=discord.Colour.green())

    # --- appeals listing for staff ---
    @app_commands.command(name="appeals", description="List pending appeals for this server (staff only).")
    @app_commands.check(mod_interaction_check)
    async def appeals(self, interaction: discord.Interaction):
        if not interaction.guild:
            return await interaction.response.send_message("This command must be used in a server.", ephemeral=True)
        gid = int(interaction.guild.id)
        pending = [(aid, r) for aid, r in self.appeals.items() if int(r["guild_id"]) == gid and r["status"] == "pending"]
        if not pending:
            e = self._embed_base(color=discord.Colour.green())
            e.title = "Appeals"
            e.description = "No pending appeals."
            return await interaction.response.send_message(embed=e, ephemeral=True)
        e = self._embed_base(color=discord.Colour.blurple())
        e.title = f"Pending Appeals ({len(pending)})"
        for aid, rec in pending[:10]:
            snippet = rec["appeal_text"]
            if len(snippet) > 200:
                snippet = snippet[:197] + "..."
            e.add_field(name=f"ID: {aid}", value=f"{snippet}\nFrom: <@{rec['banned_user_id']}>", inline=False)
        await interaction.response.send_message(embed=e, ephemeral=True)

    # --- configuration commands for guild ---
    @app_commands.command(name="setmodlog", description="Set the mod-log channel for this server (staff only).")
    @app_commands.check(mod_interaction_check)
    async def setmodlog(self, interaction: discord.Interaction, channel: discord.TextChannel):
        if not interaction.guild:
            return await interaction.response.send_message("This command must be used in a server.", ephemeral=True)
        gid = str(interaction.guild.id)
        self.guild_settings.setdefault(gid, {})
        self.guild_settings[gid]["mod_log_channel_id"] = int(channel.id)
        try:
            atomic_write_json(self.guild_settings_store, self.guild_settings)
        except Exception:
            LOG.exception("Failed to persist guild settings")
        e = self._embed_base(color=discord.Colour.green())
        e.title = "Mod-log Channel Configured"
        e.description = f"Mod-log set to {channel.mention} (`{channel.id}`)."
        await interaction.response.send_message(embed=e, ephemeral=True)

    @app_commands.command(name="setappeals", description="Set the appeals channel for this server (staff only).")
    @app_commands.check(mod_interaction_check)
    async def setappeals(self, interaction: discord.Interaction, channel: discord.TextChannel):
        if not interaction.guild:
            return await interaction.response.send_message("This command must be used in a server.", ephemeral=True)
        gid = str(interaction.guild.id)
        self.guild_settings.setdefault(gid, {})
        self.guild_settings[gid]["appeals_channel_id"] = int(channel.id)
        try:
            atomic_write_json(self.guild_settings_store, self.guild_settings)
        except Exception:
            LOG.exception("Failed to persist guild settings")
        e = self._embed_base(color=discord.Colour.green())
        e.title = "Appeals Channel Configured"
        e.description = f"Appeals set to {channel.mention} (`{channel.id}`)."
        await interaction.response.send_message(embed=e, ephemeral=True)

    @app_commands.command(name="showconfig", description="Show moderation configuration for this server (staff only).")
    @app_commands.check(mod_interaction_check)
    async def showconfig(self, interaction: discord.Interaction):
        if not interaction.guild:
            return await interaction.response.send_message("This command must be used in a server.", ephemeral=True)
        gid = str(interaction.guild.id)
        settings = self.guild_settings.get(gid, {})
        e = self._embed_base(color=discord.Colour.blurple())
        e.title = f"Moderation Config for {interaction.guild.name}"
        e.add_field(name="Mod-log channel ID", value=str(settings.get("mod_log_channel_id") or "Not set"), inline=False)
        e.add_field(name="Appeals channel ID", value=str(settings.get("appeals_channel_id") or "Not set"), inline=False)
        e.add_field(name="Embed color", value=hex(self.config.get("embed_color")), inline=True)
        await interaction.response.send_message(embed=e, ephemeral=True)

    @app_commands.command(name="export", description="Export moderation data files (sends files to your DMs).")
    @app_commands.check(mod_interaction_check)
    async def export(self, interaction: discord.Interaction):
        user = interaction.user
        files = []
        for p in (self.tempban_store, self.appeals_store, self.guild_settings_store):
            if os.path.exists(p):
                files.append(p)
        if not files:
            return await interaction.response.send_message("No data files to export.", ephemeral=True)
        try:
            dm = await user.create_dm()
            for p in files:
                try:
                    await dm.send(file=discord.File(p, filename=os.path.basename(p)))
                except Exception:
                    LOG.exception("Failed to send file %s to %s", p, user)
            await interaction.response.send_message("Exported files to your DMs.", ephemeral=True)
        except Exception:
            LOG.exception("Export failed")
            await interaction.response.send_message("Failed to send files via DM.", ephemeral=True)

    # -------------------------
    # Cog error handling
    # -------------------------
    @commands.Cog.listener()
    async def on_app_command_error(self, interaction: discord.Interaction, error: Exception):
        # user-friendly messages for app command errors
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

# -------------------------------
# PART 5 — SMALL HELPERS & CONFIRM VIEW (used for ban confirmations)
# -------------------------------
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

# -------------------------------
# COG SETUP ENTRYPOINT
# -------------------------------


async def setup(bot):
    """Setup function for the cog"""
    await bot.add_cog(ban(bot))
    logger.info("Ban cog loaded successfully")
