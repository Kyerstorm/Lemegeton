# cogs/ban.py
"""
Ban/Tempban Cog with appeals flow and aesthetics.
Features:
- ban, tempban, unban commands (group: moderation)
- DM to banned user with "Appeal" button -> opens Modal in DM
- Appeals are posted to configured appeals channel in the guild with Accept/Reject buttons
- Moderators must supply a reason when Accepting/Rejecting; Accept -> unban + notify user
- Persistent JSON stores for tempbans and appeals
- Permission check: admin OR (kick_members and ban_members and moderate_members)
- Multi-guild support
- Configurable aesthetics and channel names/IDs
"""

import asyncio
import json
import logging
import os
from datetime import datetime, timedelta
from typing import Optional, Dict, Any

import discord
from discord.ext import commands, tasks

LOG = logging.getLogger(__name__)
DEFAULTS = {
    "mod_log_channel_id": None,          # id or None -> fallback to mod_log_channel_name
    "mod_log_channel_name": "mod-log",
    "appeals_channel_id": None,          # id or None -> fallback to appeals_channel_name
    "appeals_channel_name": "appeals",
    "appeals_store": "data/appeals.json",
    "tempban_store": "data/tempbans.json",
    "bot_avatar_url": None,
    "embed_color": 0x6A0DAD,             # default aesthetic color (purple)
    "banner_image_url": None,            # optional top-banner for embeds
    "footer_text": "Moderation • Powered by Bot",
}

def ensure_dir_for(path: str):
    os.makedirs(os.path.dirname(path), exist_ok=True)

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

class ModPermissionError(commands.CheckFailure):
    pass

def is_mod():
    async def predicate(ctx: commands.Context):
        perms = ctx.author.guild_permissions
        if perms.administrator:
            return True
        if perms.kick_members and perms.ban_members and perms.moderate_members:
            return True
        raise ModPermissionError("You must be an administrator or have Kick, Ban and Moderate permissions.")
    return commands.check(predicate)

# ---------------------------
# Helper: read/write JSON stores
# ---------------------------
def load_json(path: str) -> Dict[str, Any]:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def save_json(path: str, data: Dict[str, Any]):
    ensure_dir_for(path)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, default=str)

# ---------------------------
# UI: modal for appeals (user) and for moderator decision reasons
# ---------------------------
class AppealModal(discord.ui.Modal, title="Submit Appeal"):
    def __init__(self, cog, guild_id: int, banned_user_id: int, appeal_context: str = ""):
        super().__init__()
        self.cog = cog
        self.guild_id = guild_id
        self.banned_user_id = banned_user_id
        # fields
        self.appeal_reason = discord.ui.TextInput(label="Why should you be unbanned?", style=discord.TextStyle.long, placeholder="Explain your appeal...", required=True, max_length=2000)
        self.extra = discord.ui.TextInput(label="Anything else? (optional)", style=discord.TextStyle.paragraph, required=False, max_length=1000)
        # Append inputs to the modal
        self.add_item(self.appeal_reason)
        self.add_item(self.extra)

    async def on_submit(self, interaction: discord.Interaction):
        # Save appeal to store and post to guild appeals channel
        guild_id = str(self.guild_id)
        appeals = self.cog.appeals
        appeal_id = None
        # create appeal record
        now = datetime.utcnow().isoformat()
        record = {
            "guild_id": int(self.guild_id),
            "banned_user_id": int(self.banned_user_id),
            "submitted_at": now,
            "appeal_text": str(self.appeal_reason.value),
            "extra": str(self.extra.value) if self.extra.value else "",
            "status": "pending",
            "moderator_id": None,
            "moderator_reason": None,
            "appeal_message_id": None,
            "appeal_channel_id": None
        }
        # generate an appeal id (timestamp + user)
        appeal_id = f"{self.guild_id}-{self.banned_user_id}-{int(datetime.utcnow().timestamp())}"
        appeals[appeal_id] = record
        save_json(self.cog.appeals_store, appeals)

        # send to guild appeals channel
        guild = self.cog.bot.get_guild(self.guild_id)
        embed = self.cog._embed_base(color=discord.Colour(self.cog.config["embed_color"]))
        embed.title = "New Ban Appeal"
        user_mention = f"<@{self.banned_user_id}>"
        embed.description = f"Appeal from {user_mention} ({self.banned_user_id})"
        embed.add_field(name="Appeal Text", value=record["appeal_text"], inline=False)
        if record["extra"]:
            embed.add_field(name="Extra", value=record["extra"], inline=False)
        embed.add_field(name="Submitted (UTC)", value=now, inline=False)
        embed.set_footer(text=f"Appeal ID: {appeal_id}")

        if guild:
            # find appeals channel
            ch = await self.cog._get_appeals_channel(guild)
            if ch:
                view = self.cog.ModeratorDecisionView(cog=self.cog, appeal_id=appeal_id)
                try:
                    msg = await ch.send(embed=embed, view=view)
                    # persist message id and channel id
                    appeals[appeal_id]["appeal_message_id"] = msg.id
                    appeals[appeal_id]["appeal_channel_id"] = ch.id
                    save_json(self.cog.appeals_store, appeals)
                except Exception as exc:
                    LOG.exception("Failed to send appeal to channel: %s", exc)
                    # inform user
                    await interaction.response.send_message("Your appeal was recorded but I couldn't post it to the server (missing permissions). Try contacting staff manually.", ephemeral=True)
                    return
                # confirm to user
                await interaction.response.send_message("✅ Your appeal was submitted to the server staff. You will be notified if a decision is made.", ephemeral=True)
                # also notify mod-log
                if guild:
                    log_e = self.cog._embed_base(color=discord.Colour.orange())
                    log_e.title = "Appeal Submitted"
                    log_e.description = f"Appeal ID: `{appeal_id}`\nFrom: {user_mention} ({self.banned_user_id})"
                    await self.cog._send_mod_log(guild, log_e)
                return
        # fallback: not in guild or channel missing
        await interaction.response.send_message("Your appeal was recorded but server channel was not found.", ephemeral=True)

class ModeratorReasonModal(discord.ui.Modal):
    def __init__(self, cog, appeal_id: str, action: str):
        title = "Accept Appeal" if action == "accept" else "Reject Appeal"
        super().__init__(title=title)
        self.cog = cog
        self.appeal_id = appeal_id
        self.action = action
        self.reason = discord.ui.TextInput(label="Reason (required)", style=discord.TextStyle.long, placeholder="Explain why you accept or reject this appeal", required=True, max_length=2000)
        self.add_item(self.reason)

    async def on_submit(self, interaction: discord.Interaction):
        # Validate moderator permissions in the appeal's guild
        appeals = self.cog.appeals
        record = appeals.get(self.appeal_id)
        if not record:
            await interaction.response.send_message("Appeal not found or already processed.", ephemeral=True)
            return
        guild = self.cog.bot.get_guild(record["guild_id"])
        # Check permission for this moderator in this guild
        member = None
        if guild:
            member = guild.get_member(interaction.user.id)
        # If moderator isn't in guild or lacks perms: reject
        if not member:
            await interaction.response.send_message("You must be a member of the guild to process appeals.", ephemeral=True)
            return
        perms = member.guild_permissions
        if not (perms.administrator or (perms.kick_members and perms.ban_members and perms.moderate_members)):
            await interaction.response.send_message("You don't have permission to process appeals.", ephemeral=True)
            return

        # Update record
        record["status"] = "accepted" if self.action == "accept" else "rejected"
        record["moderator_id"] = interaction.user.id
        record["moderator_reason"] = str(self.reason.value)
        record["decision_at"] = datetime.utcnow().isoformat()
        save_json(self.cog.appeals_store, appeals)

        # Edit the appeal embed in guild channel (if present)
        channel = None
        if record.get("appeal_channel_id"):
            channel = guild.get_channel(record["appeal_channel_id"])
        if channel:
            try:
                msg = await channel.fetch_message(record["appeal_message_id"])
            except Exception:
                msg = None
        else:
            msg = None

        decision_embed = self.cog._embed_base(color=discord.Colour.green() if self.action == "accept" else discord.Colour.red())
        decision_embed.title = f"Appeal {record['status'].capitalize()}"
        decision_embed.description = f"Appeal ID: `{self.appeal_id}`\nUser: <@{record['banned_user_id']}> ({record['banned_user_id']})\nModerator: {interaction.user} ({interaction.user.id})"
        decision_embed.add_field(name="Moderator Reason", value=record["moderator_reason"], inline=False)
        decision_embed.add_field(name="Original Appeal", value=record["appeal_text"], inline=False)
        decision_embed.add_field(name="Submitted (UTC)", value=record["submitted_at"], inline=False)
        decision_embed.set_footer(text=f"Decision at (UTC): {record['decision_at']}")

        if msg:
            # disable buttons and replace embed
            try:
                await msg.edit(embed=decision_embed, view=None)
            except Exception:
                LOG.exception("Failed to edit appeal message embed.")

        # If accepted -> unban the user
        if self.action == "accept":
            try:
                target = discord.Object(id=record["banned_user_id"])
                await guild.unban(target, reason=f"Unbanned via appeal (accepted by {interaction.user}): {record['moderator_reason']}")
                # DM the user
                try:
                    user = await self.cog.bot.fetch_user(record["banned_user_id"])
                    dm_e = self.cog._embed_base(color=discord.Colour.green())
                    dm_e.title = f"Appeal accepted in {guild.name}"
                    dm_e.description = f"Your appeal was accepted by {interaction.user}.\nReason: {record['moderator_reason']}"
                    if self.cog.config.get("appeal_result_extra"):
                        dm_e.add_field(name="Note", value=self.cog.config.get("appeal_result_extra"))
                    await user.send(embed=dm_e)
                except Exception:
                    LOG.exception("Failed to DM user about accepted appeal.")
            except Exception as exc:
                LOG.exception("Failed to unban via appeal: %s", exc)
                # notify moderator
                await interaction.response.send_message("Attempted to unban but failed (missing permissions or role hierarchy). See logs.", ephemeral=True)
                return

        else:
            # Rejected -> DM the user the rejection
            try:
                user = await self.cog.bot.fetch_user(record["banned_user_id"])
                dm_e = self.cog._embed_base(color=discord.Colour.red())
                dm_e.title = f"Appeal rejected in {guild.name}"
                dm_e.description = f"Your appeal was rejected by {interaction.user}.\nReason: {record['moderator_reason']}"
                await user.send(embed=dm_e)
            except Exception:
                LOG.exception("Failed to DM user about rejection.")

        # Acknowledge to moderator
        await interaction.response.send_message(f"Appeal `{self.appeal_id}` marked as **{record['status']}** and processed.", ephemeral=True)
        # log to mod-log
        await self.cog._send_mod_log(guild, decision_embed)

# ---------------------------
# Views for buttons
# ---------------------------
class AppealButtonView(discord.ui.View):
    def __init__(self, cog, guild_id: int, banned_user_id: int, timeout: float = None):
        super().__init__(timeout=timeout)
        self.cog = cog
        self.guild_id = guild_id
        self.banned_user_id = banned_user_id

    @discord.ui.button(label="Appeal Ban", style=discord.ButtonStyle.primary, emoji="📝")
    async def appeal_button(self, button: discord.ui.Button, interaction: discord.Interaction):
        # open the AppealModal (works in DMs)
        modal = AppealModal(self.cog, guild_id=self.guild_id, banned_user_id=self.banned_user_id)
        await interaction.response.send_modal(modal)

class ModeratorDecisionView(discord.ui.View):
    def __init__(self, cog, appeal_id: str, timeout: float = None):
        super().__init__(timeout=timeout)
        self.cog = cog
        self.appeal_id = appeal_id

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        # ensure the user is a mod in the associated guild
        record = self.cog.appeals.get(self.appeal_id)
        if not record:
            await interaction.response.send_message("Appeal not found.", ephemeral=True)
            return False
        guild = self.cog.bot.get_guild(record["guild_id"])
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

    @discord.ui.button(label="Accept", style=discord.ButtonStyle.success, emoji="✅")
    async def accept(self, button: discord.ui.Button, interaction: discord.Interaction):
        # Open a modal asking for reason
        modal = ModeratorReasonModal(self.cog, appeal_id=self.appeal_id, action="accept")
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="Reject", style=discord.ButtonStyle.danger, emoji="❌")
    async def reject(self, button: discord.ui.Button, interaction: discord.Interaction):
        modal = ModeratorReasonModal(self.cog, appeal_id=self.appeal_id, action="reject")
        await interaction.response.send_modal(modal)

# ---------------------------
# The Cog
# ---------------------------
class BanCog(commands.Cog):
    def __init__(self, bot: commands.Bot, config: dict | None = None):
        self.bot = bot
        self.config = {**DEFAULTS, **(config or {})}
        # ensure stores
        self.tempban_store = self.config["tempban_store"]
        self.appeals_store = self.config["appeals_store"]
        ensure_dir_for(self.tempban_store)
        ensure_dir_for(self.appeals_store)
        # load
        self.tempbans = load_json(self.tempban_store)  # { guild_id: { user_id: iso_unban_time } }
        self.appeals = load_json(self.appeals_store)    # { appeal_id: record }
        # Views accessible to modal classes
        self.ModeratorDecisionView = ModeratorDecisionView
        # start background task for unbans
        self.unban_task.start()

    def cog_unload(self):
        self.unban_task.cancel()

    # ---------------------------
    # Embed aesthetics factory
    # ---------------------------
    def _embed_base(self, color: discord.Colour = None):
        color = color or discord.Colour(self.config.get("embed_color", 0x6A0DAD))
        e = discord.Embed(color=color, timestamp=datetime.utcnow())
        if self.config.get("banner_image_url"):
            # a small banner at top of embed (via image)
            e.set_image(url=self.config.get("banner_image_url"))
        footer_text = self.config.get("footer_text", "Moderation")
        e.set_footer(text=footer_text)
        avatar = self.config.get("bot_avatar_url")
        if avatar:
            e.set_thumbnail(url=avatar)
        return e

    async def _send_mod_log(self, guild: discord.Guild, embed: discord.Embed):
        # send into configured mod log channel (by id or name)
        ch = None
        cid = self.config.get("mod_log_channel_id")
        if cid:
            ch = guild.get_channel(cid)
        if not ch:
            # fallback to name
            name = self.config.get("mod_log_channel_name", "mod-log")
            for c in guild.text_channels:
                if c.name == name:
                    ch = c
                    break
        if ch:
            try:
                await ch.send(embed=embed)
            except Exception:
                LOG.exception("Failed to send to mod-log.")
        else:
            LOG.info("No mod-log channel found for guild %s", guild.id)

    async def _get_appeals_channel(self, guild: discord.Guild) -> Optional[discord.TextChannel]:
        cid = self.config.get("appeals_channel_id")
        if cid:
            ch = guild.get_channel(cid)
            if ch:
                return ch
        # fallback to name
        name = self.config.get("appeals_channel_name", "appeals")
        for c in guild.text_channels:
            if c.name == name:
                return c
        return None

    async def _dm_user(self, user: discord.User, embed: discord.Embed, view: discord.ui.View | None = None):
        try:
            await user.send(embed=embed, view=view)
            return True
        except Exception:
            return False

    # ---------------------------
    # Background scheduler for temp unbans
    # ---------------------------
    @tasks.loop(seconds=60.0)
    async def unban_task(self):
        now = datetime.utcnow()
        changed = False
        for guild_id, entries in list(self.tempbans.items()):
            guild = self.bot.get_guild(int(guild_id))
            if not guild:
                continue
            for user_id, iso_ts in list(entries.items()):
                try:
                    unban_time = datetime.fromisoformat(iso_ts)
                except Exception:
                    continue
                if now >= unban_time:
                    try:
                        user_obj = discord.Object(id=int(user_id))
                        await guild.unban(user_obj, reason="Temporary ban expired (automated).")
                        # log
                        eb = self._embed_base(color=discord.Colour.green())
                        eb.title = "Temporary Ban Expired (Auto-Unban)"
                        eb.description = f"User: <@{user_id}> ({user_id})\nGuild: {guild.name} ({guild.id})"
                        await self._send_mod_log(guild, eb)
                    except Exception:
                        LOG.exception("Auto-unban failed for %s in %s", user_id, guild_id)
                    # remove
                    del self.tempbans[guild_id][user_id]
                    changed = True
            if guild_id in self.tempbans and not self.tempbans[guild_id]:
                del self.tempbans[guild_id]
                changed = True
        if changed:
            save_json(self.tempban_store, self.tempbans)

    @unban_task.before_loop
    async def before_unban_task(self):
        await self.bot.wait_until_ready()

    # ---------------------------
    # Commands
    # ---------------------------
    @commands.hybrid_group(name="moderation", invoke_without_command=True)
    @is_mod()
    async def moderation(self, ctx: commands.Context):
        await ctx.send("Moderation commands: `ban`, `tempban`, `unban`, `appeal`.")

    @moderation.command(name="ban")
    @is_mod()
    @commands.guild_only()
    async def ban(self, ctx: commands.Context, member: discord.Member, *, reason: Optional[str] = "No reason provided"):
        """Permanently ban a member with DM and appeal button."""
        if member == ctx.author:
            return await ctx.send(embed=discord.Embed(description="You cannot ban yourself.", color=discord.Colour.red()))
        if member == ctx.guild.me:
            return await ctx.send(embed=discord.Embed(description="I cannot ban myself.", color=discord.Colour.red()))

        # role hierarchy
        if ctx.author != ctx.guild.owner and ctx.author.top_role <= member.top_role:
            return await ctx.send(embed=discord.Embed(description="You cannot ban someone with an equal or higher top role.", color=discord.Colour.red()))

        # Confirm via buttons
        confirm_view = ConfirmModalView(ctx.author)
        e = self._embed_base(color=discord.Colour.orange())
        e.title = "Confirm Permanent Ban"
        e.description = f"Are you sure you want to permanently ban {member.mention}?\n**Reason:** {reason}"
        e.add_field(name="Invoker", value=f"{ctx.author} ({ctx.author.id})")
        e.add_field(name="Target", value=f"{member} ({member.id})")
        msg = await ctx.send(embed=e, view=confirm_view)
        await confirm_view.wait()
        if not confirm_view.value:
            return  # cancelled

        # DM the user with appeal button
        dm_e = self._embed_base(color=discord.Colour.dark_red())
        dm_e.title = f"You were banned from {ctx.guild.name}"
        dm_e.description = f"You were permanently banned.\n**Reason:** {reason}"
        appeal_view = AppealButtonView(cog=self, guild_id=ctx.guild.id, banned_user_id=member.id)
        dm_sent = await self._dm_user(member, dm_e, view=appeal_view)

        # Ban the member
        try:
            await ctx.guild.ban(member, reason=f"{reason} — banned by {ctx.author}", delete_message_days=0)
        except Exception as exc:
            LOG.exception("Failed to ban user")
            return await ctx.send(embed=discord.Embed(description=f"Failed to ban: {exc}", color=discord.Colour.red()))

        # send confirmation to moderator
        ok = self._embed_base(color=discord.Colour.red())
        ok.title = "Member Banned"
        ok.description = f"{member.mention} has been permanently banned."
        ok.add_field(name="Reason", value=reason, inline=False)
        ok.add_field(name="DM", value="Sent ✅" if dm_sent else "Failed to DM (maybe DMs closed) ❌", inline=True)
        ok.set_footer(text=f"Member ID: {member.id} • Moderator: {ctx.author}")
        await ctx.send(embed=ok)

        # mod log
        log_e = self._embed_base(color=discord.Colour.red())
        log_e.title = "Permanent Ban"
        log_e.add_field(name="User", value=f"{member} ({member.id})", inline=False)
        log_e.add_field(name="Moderator", value=f"{ctx.author} ({ctx.author.id})", inline=False)
        log_e.add_field(name="Reason", value=reason, inline=False)
        await self._send_mod_log(ctx.guild, log_e)

    @moderation.command(name="tempban")
    @is_mod()
    @commands.guild_only()
    async def tempban(self, ctx: commands.Context, member: discord.Member, duration: str, *, reason: Optional[str] = "No reason provided"):
        """Tempban a member. Duration examples: 30m, 2h, 3d, 1w"""
        if member == ctx.author:
            return await ctx.send(embed=discord.Embed(description="You cannot ban yourself.", color=discord.Colour.red()))
        if member == ctx.guild.me:
            return await ctx.send(embed=discord.Embed(description="I cannot ban myself.", color=discord.Colour.red()))

        total_seconds = parse_duration_to_seconds(duration)
        if total_seconds is None or total_seconds <= 0:
            return await ctx.send(embed=discord.Embed(description="Invalid duration. Use examples like `30m`, `2h`, `1d`, `1w`.", color=discord.Colour.red()))
        unban_time = datetime.utcnow() + timedelta(seconds=total_seconds)

        # confirm
        confirm_view = ConfirmModalView(ctx.author)
        e = self._embed_base(color=discord.Colour.orange())
        e.title = "Confirm Temporary Ban"
        e.description = f"Ban {member.mention} for **{human_readable_delta(timedelta(seconds=total_seconds))}**?\n**Reason:** {reason}"
        msg = await ctx.send(embed=e, view=confirm_view)
        await confirm_view.wait()
        if not confirm_view.value:
            return

        # DM user with appeal button
        dm_e = self._embed_base(color=discord.Colour.dark_red())
        dm_e.title = f"You were temporarily banned from {ctx.guild.name}"
        dm_e.description = f"Ban length: **{human_readable_delta(timedelta(seconds=total_seconds))}**\nReason: {reason}"
        appeal_view = AppealButtonView(cog=self, guild_id=ctx.guild.id, banned_user_id=member.id)
        dm_sent = await self._dm_user(member, dm_e, view=appeal_view)

        # Perform ban
        try:
            await ctx.guild.ban(member, reason=f"{reason} — tempbanned by {ctx.author} until {unban_time.isoformat()}", delete_message_days=0)
        except Exception as exc:
            LOG.exception("Failed to tempban user")
            return await ctx.send(embed=discord.Embed(description=f"Failed to tempban: {exc}", color=discord.Colour.red()))

        # store scheduled unban
        gid = str(ctx.guild.id)
        if gid not in self.tempbans:
            self.tempbans[gid] = {}
        self.tempbans[gid][str(member.id)] = unban_time.isoformat()
        save_json(self.tempban_store, self.tempbans)

        ok = self._embed_base(color=discord.Colour.red())
        ok.title = "Member Temporarily Banned"
        ok.description = f"{member.mention} has been banned for **{human_readable_delta(timedelta(seconds=total_seconds))}**."
        ok.add_field(name="Reason", value=reason, inline=False)
        ok.add_field(name="DM", value="Sent ✅" if dm_sent else "Failed ❌", inline=True)
        ok.add_field(name="Unban (UTC)", value=unban_time.isoformat(), inline=False)
        await ctx.send(embed=ok)

        log_e = self._embed_base(color=discord.Colour.red())
        log_e.title = "Temporary Ban"
        log_e.add_field(name="User", value=f"{member} ({member.id})", inline=False)
        log_e.add_field(name="Moderator", value=f"{ctx.author} ({ctx.author.id})", inline=False)
        log_e.add_field(name="Reason", value=reason, inline=False)
        log_e.add_field(name="Unban (UTC)", value=unban_time.isoformat(), inline=False)
        await self._send_mod_log(ctx.guild, log_e)

    @moderation.command(name="unban")
    @is_mod()
    @commands.guild_only()
    async def unban(self, ctx: commands.Context, user: discord.User, *, reason: Optional[str] = "No reason provided"):
        """Unban a user or user ID."""
        try:
            await ctx.guild.unban(user, reason=f"{reason} — unbanned by {ctx.author}")
        except Exception as exc:
            LOG.exception("Failed to unban")
            return await ctx.send(embed=discord.Embed(description=f"Failed to unban: {exc}", color=discord.Colour.red()))

        # remove scheduled tempban if present
        gid = str(ctx.guild.id)
        uid = str(user.id)
        removed = False
        if gid in self.tempbans and uid in self.tempbans[gid]:
            del self.tempbans[gid][uid]
            if not self.tempbans[gid]:
                del self.tempbans[gid]
            save_json(self.tempban_store, self.tempbans)
            removed = True

        e = self._embed_base(color=discord.Colour.green())
        e.title = "User Unbanned"
        e.description = f"{user} ({user.id}) has been unbanned."
        e.add_field(name="Moderator", value=f"{ctx.author} ({ctx.author.id})")
        e.add_field(name="Reason", value=reason)
        if removed:
            e.add_field(name="Note", value="Scheduled tempban removed.")
        await ctx.send(embed=e)

        log_e = self._embed_base(color=discord.Colour.green())
        log_e.title = "Unban"
        log_e.add_field(name="User", value=f"{user} ({user.id})")
        log_e.add_field(name="Moderator", value=f"{ctx.author} ({ctx.author.id})")
        log_e.add_field(name="Reason", value=reason)
        await self._send_mod_log(ctx.guild, log_e)

    # manual appeal info (staff)
    @moderation.command(name="appeals")
    @is_mod()
    @commands.guild_only()
    async def appeals_command(self, ctx: commands.Context):
        """Show open appeals summary for this guild."""
        guild_id = ctx.guild.id
        open_appeals = []
        for aid, rec in self.appeals.items():
            if rec.get("guild_id") == guild_id and rec.get("status") == "pending":
                open_appeals.append((aid, rec))
        if not open_appeals:
            return await ctx.send(embed=self._embed_base(color=discord.Colour.green()).add_field(name="Appeals", value="No pending appeals."))

        e = self._embed_base(color=discord.Colour.blurple())
        e.title = f"Pending Appeals ({len(open_appeals)})"
        for aid, rec in open_appeals[:10]:
            snippet = rec["appeal_text"]
            if len(snippet) > 200:
                snippet = snippet[:197] + "..."
            e.add_field(name=f"ID: {aid}", value=f"{snippet}\nFrom: <@{rec['banned_user_id']}>", inline=False)
        await ctx.send(embed=e)

    # Cog-level error handling
    @commands.Cog.listener()
    async def on_command_error(self, ctx: commands.Context, error: Exception):
        if isinstance(error, ModPermissionError):
            await ctx.send(embed=discord.Embed(description=str(error), color=discord.Colour.red()))
        elif isinstance(error, commands.MissingRequiredArgument):
            await ctx.send(embed=discord.Embed(description="Missing argument.", color=discord.Colour.red()))
        elif isinstance(error, commands.BadArgument):
            await ctx.send(embed=discord.Embed(description="Bad argument.", color=discord.Colour.red()))
        else:
            LOG.exception("Unhandled command error: %s", error)

# ---------------------------
# small Confirm view for moderator confirmation used above
# ---------------------------
class ConfirmModalView(discord.ui.View):
    def __init__(self, author: discord.Member, timeout: float = 30.0):
        super().__init__(timeout=timeout)
        self.author = author
        self.value: bool = False

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author.id:
            await interaction.response.send_message("This confirmation isn't for you.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Confirm", style=discord.ButtonStyle.danger, emoji="🔥")
    async def confirm(self, button: discord.ui.Button, interaction: discord.Interaction):
        self.value = True
        await interaction.response.edit_message(content="✅ Confirmed.", view=None)

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary, emoji="✖️")
    async def cancel(self, button: discord.ui.Button, interaction: discord.Interaction):
        self.value = False
        await interaction.response.edit_message(content="❎ Cancelled.", view=None)

# ---------------------------
# Duration parser (same as earlier)
# ---------------------------
def parse_duration_to_seconds(s: str) -> Optional[int]:
    s = s.strip().lower()
    if not s:
        return None
    total = 0
    num = ""
    multipliers = {"w": 7 * 24 * 3600, "d": 24 * 3600, "h": 3600, "m": 60, "s": 1}
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

# ---------------------------
# Cog setup
# ---------------------------
async def setup(bot: commands.Bot, *, config: dict | None = None):
    cog = BanCog(bot, config=config or {})
    await bot.ban(cog)
