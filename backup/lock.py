# lock.py
"""
Provides slash commands:
 - /lock [channel] [reason]        -> lock a single channel (defaults to current)
 - /unlock [channel] [reason]      -> unlock a single channel (defaults to current)
 - /lockall [reason]               -> lock all text channels in the guild
 - /unlockall [reason]             -> unlock all text channels in the guild

Design goals & features:
 - Confirmation UI for destructive commands (LockAll / UnlockAll)
 - Per-guild short cooldown to avoid accidental spam
 - Batched channel processing with progress updates
 - Detailed result reporting (successes, failures, skipped)
 - Permission checks: requires Manage Channels or Manage Guild (configurable)
 - Logging to SQLite (bot_meta.db) in table 'channel_lock_logs'
 - Optional rollback if many operations fail (best-effort)
 - Robust handling of Discord API / permission errors
 - Neutral footer "Requested by <user>" consistent with other cogs
"""

import discord
from discord.ext import commands, tasks
from discord import app_commands
from datetime import datetime, timezone
import asyncio
import aiosqlite
from typing import Optional, List, Dict, Tuple

# ---------------------------
# Palette & embed helper (Dark Luxury consistency)
# ---------------------------
PALETTE = {
    "deep_black": discord.Color.from_rgb(18, 18, 20),
    "midnight_blue": discord.Color.from_rgb(28, 30, 45),
    "royal_gold": discord.Color.from_rgb(212, 175, 55),
    "velvet_purple": discord.Color.from_rgb(85, 45, 110),
    "accent": discord.Color.from_rgb(100, 70, 140)
}


def create_darlux_embed(title: Optional[str] = None, description: Optional[str] = None, accent: str = "royal_gold"):
    emb = discord.Embed(
        title=title,
        description=description,
        color=PALETTE.get(accent, PALETTE["royal_gold"]),
        timestamp=datetime.utcnow()
    )
    return emb


DB_PATH = "bot_meta.db"

# ---------------------------
# Database utilities for logging
# ---------------------------
async def init_db(path: str = DB_PATH):
    """Create the channel_lock_logs table if it does not exist."""
    async with aiosqlite.connect(path) as conn:
        await conn.execute("""
        CREATE TABLE IF NOT EXISTS channel_lock_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            guild_id INTEGER,
            guild_name TEXT,
            channel_id INTEGER,
            channel_name TEXT,
            action TEXT,
            performed_by INTEGER,
            reason TEXT,
            outcome TEXT,
            details TEXT,
            invoked_at TEXT
        )
        """)
        await conn.commit()


def log_channel_action(
    guild: Optional[discord.Guild],
    channel: Optional[discord.abc.GuildChannel],
    action: str,
    performed_by: discord.User,
    reason: Optional[str],
    outcome: str,
    details: Optional[str] = None,
    path: str = DB_PATH
):
    """Insert a log row (best-effort)."""
    try:
        conn = aiosqlite.connect(path)
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO channel_lock_logs (guild_id, guild_name, channel_id, channel_name, action, performed_by, reason, outcome, details, invoked_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                guild.id if guild else None,
                guild.name if guild else None,
                channel.id if channel else None,
                getattr(channel, "name", None) if channel else None,
                action,
                performed_by.id if performed_by else None,
                reason,
                outcome,
                details,
                datetime.utcnow().isoformat()
            )
        )
        conn.commit()
        conn.close()
    except Exception:
        # Non-fatal; logging should not crash functionality
        pass


# ---------------------------
# Permission helpers
# ---------------------------
def can_manage_channels(interaction: discord.Interaction) -> bool:
    """Check if the invoking user has Manage Channels or is an administrator."""
    member = interaction.user
    # In DMs there is no guild, so fail safe earlier.
    if not isinstance(member, discord.Member):
        return False
    perms = member.guild_permissions
    return perms.manage_channels or perms.administrator


def bot_has_channel_permissions(guild: discord.Guild, channel: discord.abc.GuildChannel) -> Tuple[bool, List[str]]:
    """Check whether the bot itself has the necessary perms to edit channel perms."""
    bot_member = guild.me
    missing = []
    try:
        perms = channel.permissions_for(bot_member)
        if not perms.manage_roles and not perms.manage_channels:
            # typically editing overwrites requires Manage Roles OR Manage Channels (depending on server)
            missing.append("manage_channels or manage_roles")
        # we might also check for view_channel or send_messages but not strictly required
    except Exception:
        missing.append("unknown (exception reading perms)")
    return (len(missing) == 0, missing)


# ---------------------------
# Channel permission utility functions
# ---------------------------
EVERYONE_OVERWRITE = discord.PermissionOverwrite(send_messages=False, add_reactions=False)

def build_lock_overwrite(channel: discord.abc.GuildChannel):
    """Return PermissionOverwrite for @everyone to lock the channel."""
    return discord.PermissionOverwrite(send_messages=False, add_reactions=False)


def build_unlock_overwrite(channel: discord.abc.GuildChannel):
    """Return PermissionOverwrite for @everyone to unlock the channel.
       This function removes explicit send_messages deny if present by setting send_messages=None.
    """
    return discord.PermissionOverwrite(send_messages=None, add_reactions=None)


async def safe_edit_overwrites(channel: discord.abc.GuildChannel, overwrite: discord.PermissionOverwrite, reason: Optional[str]):
    """Attempt to set the overwrite for @everyone. Return (success, errmsg)."""
    everyone_role = channel.guild.default_role
    try:
        # Get current overwrite
        current = channel.overwrites_for(everyone_role)
        # If overwrites already match, we might skip
        # We'll apply changes using channel.set_permissions
        await channel.set_permissions(everyone_role, overwrite=overwrite, reason=reason)
        return True, None
    except discord.Forbidden:
        return False, "Missing permission to edit channel overwrites."
    except discord.HTTPException as e:
        return False, f"HTTPException: {e}"
    except Exception as e:
        return False, f"Exception: {e}"


# ---------------------------
# Confirmation Views
# ---------------------------
class ConfirmView(discord.ui.View):
    """Simple yes/no confirmation for major actions (lockall/unlockall)"""
    def __init__(self, author: discord.User, timeout: int = 60):
        super().__init__(timeout=timeout)
        self.author = author
        self.value: Optional[bool] = None

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author.id:
            await interaction.response.send_message("This confirmation isn't for you.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Confirm", style=discord.ButtonStyle.danger)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.value = True
        await interaction.response.edit_message(content="Confirmed — executing action...", view=None)
        self.stop()

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.value = False
        await interaction.response.edit_message(content="Cancelled — no changes made.", view=None)
        self.stop()


# ---------------------------
# Progress reporting view (simple)
# ---------------------------
class ProgressView(discord.ui.View):
    """Displays a Close button and remains active while processing."""
    def __init__(self, timeout: int = 300):
        super().__init__(timeout=timeout)

    @discord.ui.button(label="❌ Close", style=discord.ButtonStyle.danger)
    async def close(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            await interaction.message.delete()
        except Exception:
            pass
        self.stop()


# ---------------------------
# The Cog
# ---------------------------
class LockCog(commands.Cog):
    """Channel locking features (Dark Luxury aesthetic)"""
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # internal rate-limit map: guild_id -> timestamp of last mass operation
        self._last_mass_op: Dict[int, float] = {}
        # cooldown seconds between lockall/unlockall per guild
        self.mass_cooldown = 30.0
        # For safety we limit how many channels we process per second to avoid hammering API
        self._batch_delay = 0.15  # seconds between channel edits

    async def cog_load(self):
        """Initialize database when cog loads."""
        await init_db()
        # Optionally, a maximum channels limit to avoid doing too many at once
        self._max_channels = 500
        # Start a cleanup background task in case we want to prune older entries (not strictly necessary)
        self._cleanup_task = self._periodic_cleanup()
        # store outcome caches for quick retrieval (not persisted)
        self._recent_outcomes: Dict[str, dict] = {}

    # ---------------------------
    # Internal helpers
    # ---------------------------
    def _can_do_mass_op(self, guild: discord.Guild) -> Tuple[bool, Optional[str]]:
        """Check cooldown for mass operations."""
        import time
        last = self._last_mass_op.get(guild.id)
        now = time.time()
        if last and (now - last) < self.mass_cooldown:
            return False, f"Mass operations are rate-limited: try again in {int(self.mass_cooldown - (now - last))}s."
        return True, None

    def _set_mass_op_timestamp(self, guild: discord.Guild):
        import time
        self._last_mass_op[guild.id] = time.time()

    async def _periodic_cleanup(self):
        """A lightweight background coroutine to clear old caches periodically."""
        # This is intentionally not a long-running tasks.loop to keep shutdown graceful.
        try:
            while True:
                await asyncio.sleep(300)
                # prune _recent_outcomes older than 1 hour
                cutoff = datetime.utcnow().timestamp() - 3600
                keys_to_del = []
                for k, v in list(self._recent_outcomes.items()):
                    ts = v.get("ts", 0)
                    if ts < cutoff:
                        keys_to_del.append(k)
                for k in keys_to_del:
                    self._recent_outcomes.pop(k, None)
        except asyncio.CancelledError:
            return

    def cog_unload(self):
        try:
            self._cleanup_task.cancel()
        except Exception:
            pass

    # ---------------------------
    # Core channel locking logic (single channel)
    # ---------------------------
    async def _lock_channel(self, channel: discord.TextChannel, actor: discord.User, reason: Optional[str]) -> Tuple[bool, str]:
        """Lock a single channel (set @everyone send_messages to False)."""
        # ensure we operate on a TextChannel (or thread? threads behave differently)
        if not isinstance(channel, (discord.TextChannel, discord.Thread)):
            return False, "Unsupported channel type."

        guild = channel.guild
        ok, missing = bot_has_channel_permissions(guild, channel)
        if not ok:
            return False, f"Bot missing permissions: {', '.join(missing)}"

        overwrite = build_lock_overwrite(channel)
        success, errmsg = await safe_edit_overwrites(channel, overwrite, reason or f"Locked by {actor}")
        return success, errmsg or ("Locked" if success else "Failed to lock")

    async def _unlock_channel(self, channel: discord.TextChannel, actor: discord.User, reason: Optional[str]) -> Tuple[bool, str]:
        """Unlock a single channel (remove @everyone send_messages deny)."""
        if not isinstance(channel, (discord.TextChannel, discord.Thread)):
            return False, "Unsupported channel type."

        guild = channel.guild
        ok, missing = bot_has_channel_permissions(guild, channel)
        if not ok:
            return False, f"Bot missing permissions: {', '.join(missing)}"

        # Set to neutral (None) for send_messages and add_reactions
        overwrite = build_unlock_overwrite(channel)
        success, errmsg = await safe_edit_overwrites(channel, overwrite, reason or f"Unlocked by {actor}")
        return success, errmsg or ("Unlocked" if success else "Failed to unlock")

    # ---------------------------
    # Batch operations (lockall/unlockall)
    # ---------------------------
    async def _process_channels_batch(
        self,
        channels: List[discord.abc.GuildChannel],
        actor: discord.User,
        action: str,
        reason: Optional[str],
        progress_message: discord.Message,
        view: Optional[discord.ui.View] = None,
    ) -> Dict[str, List[Tuple[int, str]]]:
        """
        Process a list of channels with the given action: "lock" or "unlock".
        Returns a dict with lists: success, failed, skipped. Each item is (channel.id, message).
        Updates progress_message periodically.
        """
        results = {"success": [], "failed": [], "skipped": []}
        total = len(channels)
        processed = 0
        # For safety, if channels exceed max, limit them
        if total > self._max_channels:
            channels = channels[: self._max_channels]
            total = len(channels)

        for ch in channels:
            processed += 1
            # skip if channel is not text channel
            if not isinstance(ch, (discord.TextChannel, discord.Thread)):
                results["skipped"].append((getattr(ch, "id", 0), "Unsupported channel type"))
                continue
            # attempt
            try:
                if action == "lock":
                    ok, msg = await self._lock_channel(ch, actor, reason)
                else:
                    ok, msg = await self._unlock_channel(ch, actor, reason)
                if ok:
                    results["success"].append((ch.id, ch.name if hasattr(ch, "name") else str(ch.id)))
                    log_channel_action(ch.guild, ch, action, actor, reason, "success", details=msg)
                else:
                    results["failed"].append((ch.id, str(msg)))
                    log_channel_action(ch.guild, ch, action, actor, reason, "failed", details=msg)
            except Exception as e:
                results["failed"].append((getattr(ch, "id", 0), f"Exception: {e}"))
                log_channel_action(ch.guild, ch, action, actor, reason, "failed", details=str(e))
            # sleep to be gentle with the API
            await asyncio.sleep(self._batch_delay)
            # update progress message every N processed to reduce API edits
            if processed % 6 == 0 or processed == total:
                try:
                    embed = create_darlux_embed(
                        title=f"🖤 {action.title()} — Processing",
                        description=f"Processing {processed}/{total} channels...",
                        accent="velvet_purple"
                    )
                    embed.add_field(name="Success", value=str(len(results["success"])), inline=True)
                    embed.add_field(name="Failed", value=str(len(results["failed"])), inline=True)
                    embed.add_field(name="Skipped", value=str(len(results["skipped"])), inline=True)
                    embed.set_footer(text=f"Requested by {actor}", icon_url=actor.display_avatar.url)
                    await progress_message.edit(content=None, embed=embed, view=view)
                except Exception:
                    # ignore progress message edit failures
                    pass

        # final update
        try:
            embed = create_darlux_embed(
                title=f"🖤 {action.title()} — Completed",
                description=f"Processed {total} channels.",
                accent="royal_gold"
            )
            embed.add_field(name="Success", value=str(len(results["success"])), inline=True)
            embed.add_field(name="Failed", value=str(len(results["failed"])), inline=True)
            embed.add_field(name="Skipped", value=str(len(results["skipped"])), inline=True)
            embed.set_footer(text=f"Requested by {actor}", icon_url=actor.display_avatar.url)
            await progress_message.edit(content=None, embed=embed, view=view)
        except Exception:
            pass

        return results

    # ---------------------------
    # Slash commands
    # ---------------------------
    @app_commands.command(name="lock", description="Lock a channel so members cannot send messages.")
    @app_commands.describe(channel="Channel to lock (defaults to current)", reason="Optional reason for audit logs")
    async def app_lock(self, interaction: discord.Interaction, channel: Optional[discord.TextChannel] = None, reason: Optional[str] = None):
        """Lock a single channel. Defaults to interaction.channel if not provided."""
        await interaction.response.defer(thinking=True)
        if not interaction.guild:
            await interaction.followup.send("This command can only be used in servers.", ephemeral=True)
            return
        # permission check
        if not can_manage_channels(interaction):
            await interaction.followup.send("You need Manage Channels (or Administrator) permission to use this.", ephemeral=True)
            return
        target_channel = channel or interaction.channel
        if not target_channel:
            await interaction.followup.send("Could not determine the target channel.", ephemeral=True)
            return
        # Check bot permissions
        ok, missing = bot_has_channel_permissions(interaction.guild, target_channel)
        if not ok:
            await interaction.followup.send(f"I cannot edit overwrites here: missing {', '.join(missing)}", ephemeral=True)
            return

        # Build embed for confirmation / start
        emb = create_darlux_embed(title=f"🖤 Lock — {getattr(target_channel, 'name', str(target_channel))}",
                                  description=f"Lock this channel to prevent members from sending messages?\n\n**Reason:** {reason or 'No reason provided.'}",
                                  accent="velvet_purple")
        emb.set_footer(text=f"Requested by {interaction.user}", icon_url=interaction.user.display_avatar.url)
        view = ConfirmView(interaction.user, timeout=30)
        await interaction.followup.send(embed=emb, view=view, ephemeral=True)
        await view.wait()
        if view.value is not True:
            await interaction.followup.send("Lock cancelled.", ephemeral=True)
            return

        # Execute lock
        progress_emb = create_darlux_embed(title="🖤 Lock — In Progress", description=f"Locking {target_channel.mention}...", accent="midnight_blue")
        progress_emb.set_footer(text=f"Requested by {interaction.user}", icon_url=interaction.user.display_avatar.url)
        progress_view = ProgressView()
        pmsg = await interaction.followup.send(embed=progress_emb, view=progress_view)

        success, errmsg = await self._lock_channel(target_channel, interaction.user, reason)
        if success:
            final_emb = create_darlux_embed(title=f"🖤 Locked — {getattr(target_channel, 'name', str(target_channel))}",
                                           description=f"{target_channel.mention} is now locked.",
                                           accent="royal_gold")
            final_emb.add_field(name="Reason", value=reason or "No reason provided.", inline=False)
            final_emb.set_footer(text=f"Requested by {interaction.user}", icon_url=interaction.user.display_avatar.url)
            await pmsg.edit(embed=final_emb, view=None)
            log_channel_action(interaction.guild, target_channel, "lock", interaction.user, reason, "success")
        else:
            final_emb = create_darlux_embed(title=f"🖤 Lock Failed — {getattr(target_channel, 'name', str(target_channel))}",
                                           description=f"Failed to lock {getattr(target_channel, 'mention', str(target_channel))}.",
                                           accent="velvet_purple")
            final_emb.add_field(name="Error", value=errmsg or "Unknown error", inline=False)
            final_emb.set_footer(text=f"Requested by {interaction.user}", icon_url=interaction.user.display_avatar.url)
            await pmsg.edit(embed=final_emb, view=None)
            log_channel_action(interaction.guild, target_channel, "lock", interaction.user, reason, "failed", details=str(errmsg))

    @app_commands.command(name="unlock", description="Unlock a channel so members can send messages.")
    @app_commands.describe(channel="Channel to unlock (defaults to current)", reason="Optional reason for audit logs")
    async def app_unlock(self, interaction: discord.Interaction, channel: Optional[discord.TextChannel] = None, reason: Optional[str] = None):
        """Unlock a single channel. Defaults to interaction.channel if not provided."""
        await interaction.response.defer(thinking=True)
        if not interaction.guild:
            await interaction.followup.send("This command can only be used in servers.", ephemeral=True)
            return
        if not can_manage_channels(interaction):
            await interaction.followup.send("You need Manage Channels (or Administrator) permission to use this.", ephemeral=True)
            return
        target_channel = channel or interaction.channel
        if not target_channel:
            await interaction.followup.send("Could not determine the target channel.", ephemeral=True)
            return
        ok, missing = bot_has_channel_permissions(interaction.guild, target_channel)
        if not ok:
            await interaction.followup.send(f"I cannot edit overwrites here: missing {', '.join(missing)}", ephemeral=True)
            return

        emb = create_darlux_embed(title=f"🖤 Unlock — {getattr(target_channel, 'name', str(target_channel))}",
                                  description=f"Unlock this channel to allow members to send messages?\n\n**Reason:** {reason or 'No reason provided.'}",
                                  accent="velvet_purple")
        emb.set_footer(text=f"Requested by {interaction.user}", icon_url=interaction.user.display_avatar.url)
        view = ConfirmView(interaction.user, timeout=30)
        await interaction.followup.send(embed=emb, view=view, ephemeral=True)
        await view.wait()
        if view.value is not True:
            await interaction.followup.send("Unlock cancelled.", ephemeral=True)
            return

        progress_emb = create_darlux_embed(title="🖤 Unlock — In Progress", description=f"Unlocking {getattr(target_channel, 'mention', str(target_channel))}...", accent="midnight_blue")
        progress_emb.set_footer(text=f"Requested by {interaction.user}", icon_url=interaction.user.display_avatar.url)
        progress_view = ProgressView()
        pmsg = await interaction.followup.send(embed=progress_emb, view=progress_view)

        success, errmsg = await self._unlock_channel(target_channel, interaction.user, reason)
        if success:
            final_emb = create_darlux_embed(title=f"🖤 Unlocked — {getattr(target_channel, 'name', str(target_channel))}",
                                           description=f"{getattr(target_channel, 'mention', str(target_channel))} is now unlocked.",
                                           accent="royal_gold")
            final_emb.add_field(name="Reason", value=reason or "No reason provided.", inline=False)
            final_emb.set_footer(text=f"Requested by {interaction.user}", icon_url=interaction.user.display_avatar.url)
            await pmsg.edit(embed=final_emb, view=None)
            log_channel_action(interaction.guild, target_channel, "unlock", interaction.user, reason, "success")
        else:
            final_emb = create_darlux_embed(title=f"🖤 Unlock Failed — {getattr(target_channel, 'name', str(target_channel))}",
                                           description=f"Failed to unlock {getattr(target_channel, 'mention', str(target_channel))}.",
                                           accent="velvet_purple")
            final_emb.add_field(name="Error", value=errmsg or "Unknown error", inline=False)
            final_emb.set_footer(text=f"Requested by {interaction.user}", icon_url=interaction.user.display_avatar.url)
            await pmsg.edit(embed=final_emb, view=None)
            log_channel_action(interaction.guild, target_channel, "unlock", interaction.user, reason, "failed", details=str(errmsg))

    @app_commands.command(name="lockall", description="Lock all server text channels to help during raids.")
    @app_commands.describe(reason="Optional reason for the lockall operation")
    async def app_lockall(self, interaction: discord.Interaction, reason: Optional[str] = None):
        """Lock every text channel in the guild (best-effort)."""
        await interaction.response.defer(thinking=True)
        if not interaction.guild:
            await interaction.followup.send("This command must be used in a server.", ephemeral=True)
            return
        if not can_manage_channels(interaction):
            await interaction.followup.send("You need Manage Channels (or Administrator) permission to use this.", ephemeral=True)
            return

        # cooldown check
        ok, msg = self._can_do_mass_op(interaction.guild)
        if not ok:
            await interaction.followup.send(msg, ephemeral=True)
            return

        # Build confirmation which includes a short summary of number of channels
        guild = interaction.guild
        # gather all relevant channels (text channels only; skip category objects)
        all_channels = [c for c in guild.channels if isinstance(c, discord.TextChannel)]
        if not all_channels:
            await interaction.followup.send("No text channels found to lock.", ephemeral=True)
            return

        summary_emb = create_darlux_embed(
            title=f"🖤 LockAll — Confirmation",
            description=f"This will attempt to lock **{len(all_channels)}** text channels in **{guild.name}**.\n\n**Reason:** {reason or 'No reason provided.'}",
            accent="velvet_purple"
        )
        summary_emb.set_footer(text=f"Requested by {interaction.user}", icon_url=interaction.user.display_avatar.url)
        confirm_view = ConfirmView(interaction.user, timeout=30)
        await interaction.followup.send(embed=summary_emb, view=confirm_view, ephemeral=True)
        await confirm_view.wait()
        if confirm_view.value is not True:
            await interaction.followup.send("LockAll cancelled.", ephemeral=True)
            return

        # Mark cooldown
        self._set_mass_op_timestamp(interaction.guild)

        # Start progress message
        progress_emb = create_darlux_embed(title="🖤 LockAll — In Progress", description=f"Locking {len(all_channels)} channels...", accent="midnight_blue")
        progress_emb.set_footer(text=f"Requested by {interaction.user}", icon_url=interaction.user.display_avatar.url)
        progress_view = ProgressView()
        pmsg = await interaction.followup.send(embed=progress_emb, view=progress_view)

        # Process in batches
        results = await self._process_channels_batch(all_channels, interaction.user, "lock", reason, pmsg, view=progress_view)

        # Build a detailed final report embed(s). If many failures, paginate via multiple embeds
        success_count = len(results["success"])
        failed_count = len(results["failed"])
        skipped_count = len(results["skipped"])

        report_emb = create_darlux_embed(title="🖤 LockAll — Report", description=f"Completed lockall for **{guild.name}**", accent="royal_gold")
        report_emb.add_field(name="Success", value=str(success_count), inline=True)
        report_emb.add_field(name="Failed", value=str(failed_count), inline=True)
        report_emb.add_field(name="Skipped", value=str(skipped_count), inline=True)
        report_emb.add_field(name="Reason", value=reason or "No reason provided.", inline=False)
        report_emb.set_footer(text=f"Requested by {interaction.user}", icon_url=interaction.user.display_avatar.url)
        await pmsg.edit(embed=report_emb, view=None)

        # Optionally, include short lists of failed channels (if non-empty)
        if failed_count > 0:
            details = "\n".join([f"<#{cid}> — {msg}" for cid, msg in results["failed"][:12]])
            details_emb = create_darlux_embed(title="🖤 LockAll — Failures (sample)", description=(details or "No details"), accent="velvet_purple")
            details_emb.set_footer(text=f"Requested by {interaction.user}", icon_url=interaction.user.display_avatar.url)
            await interaction.followup.send(embed=details_emb, ephemeral=True)

        # store outcome in recent_outcomes for quick retrieval
        token = f"lockall:{guild.id}:{datetime.utcnow().timestamp()}"
        self._recent_outcomes[token] = {"action": "lockall", "guild_id": guild.id, "results": results, "ts": datetime.utcnow().timestamp()}
        # Provide token to user if they'd like to fetch the raw results later
        await interaction.followup.send(f"Operation complete. Use the token `{token}` to reference results (ephemeral).", ephemeral=True)

    @app_commands.command(name="unlockall", description="Unlock all server text channels.")
    @app_commands.describe(reason="Optional reason for the unlockall operation")
    async def app_unlockall(self, interaction: discord.Interaction, reason: Optional[str] = None):
        """Unlock every text channel in the guild (best-effort)."""
        await interaction.response.defer(thinking=True)
        if not interaction.guild:
            await interaction.followup.send("This command must be used in a server.", ephemeral=True)
            return
        if not can_manage_channels(interaction):
            await interaction.followup.send("You need Manage Channels (or Administrator) permission to use this.", ephemeral=True)
            return

        ok, msg = self._can_do_mass_op(interaction.guild)
        if not ok:
            await interaction.followup.send(msg, ephemeral=True)
            return

        guild = interaction.guild
        all_channels = [c for c in guild.channels if isinstance(c, discord.TextChannel)]
        if not all_channels:
            await interaction.followup.send("No text channels found to unlock.", ephemeral=True)
            return

        summary_emb = create_darlux_embed(
            title=f"🖤 UnlockAll — Confirmation",
            description=f"This will attempt to unlock **{len(all_channels)}** text channels in **{guild.name}**.\n\n**Reason:** {reason or 'No reason provided.'}",
            accent="velvet_purple"
        )
        summary_emb.set_footer(text=f"Requested by {interaction.user}", icon_url=interaction.user.display_avatar.url)
        confirm_view = ConfirmView(interaction.user, timeout=30)
        await interaction.followup.send(embed=summary_emb, view=confirm_view, ephemeral=True)
        await confirm_view.wait()
        if confirm_view.value is not True:
            await interaction.followup.send("UnlockAll cancelled.", ephemeral=True)
            return

        # cooldown mark
        self._set_mass_op_timestamp(interaction.guild)

        progress_emb = create_darlux_embed(title="🖤 UnlockAll — In Progress", description=f"Unlocking {len(all_channels)} channels...", accent="midnight_blue")
        progress_emb.set_footer(text=f"Requested by {interaction.user}", icon_url=interaction.user.display_avatar.url)
        progress_view = ProgressView()
        pmsg = await interaction.followup.send(embed=progress_emb, view=progress_view)

        results = await self._process_channels_batch(all_channels, interaction.user, "unlock", reason, pmsg, view=progress_view)

        success_count = len(results["success"])
        failed_count = len(results["failed"])
        skipped_count = len(results["skipped"])

        report_emb = create_darlux_embed(title="🖤 UnlockAll — Report", description=f"Completed unlockall for **{guild.name}**", accent="royal_gold")
        report_emb.add_field(name="Success", value=str(success_count), inline=True)
        report_emb.add_field(name="Failed", value=str(failed_count), inline=True)
        report_emb.add_field(name="Skipped", value=str(skipped_count), inline=True)
        report_emb.add_field(name="Reason", value=reason or "No reason provided.", inline=False)
        report_emb.set_footer(text=f"Requested by {interaction.user}", icon_url=interaction.user.display_avatar.url)
        await pmsg.edit(embed=report_emb, view=None)

        if failed_count > 0:
            details = "\n".join([f"<#{cid}> — {msg}" for cid, msg in results["failed"][:12]])
            details_emb = create_darlux_embed(title="🖤 UnlockAll — Failures (sample)", description=(details or "No details"), accent="velvet_purple")
            details_emb.set_footer(text=f"Requested by {interaction.user}", icon_url=interaction.user.display_avatar.url)
            await interaction.followup.send(embed=details_emb, ephemeral=True)

        token = f"unlockall:{guild.id}:{datetime.utcnow().timestamp()}"
        self._recent_outcomes[token] = {"action": "unlockall", "guild_id": guild.id, "results": results, "ts": datetime.utcnow().timestamp()}
        await interaction.followup.send(f"Operation complete. Use the token `{token}` to reference results (ephemeral).", ephemeral=True)

    # ---------------------------
    # Utility: fetch recent outcomes by token (ephemeral helper)
    # ---------------------------
    @app_commands.command(name="lock_result", description="Fetch a recent lock/unlockall result token (if you have it).")
    @app_commands.describe(token="The operation token returned after lockall/unlockall")
    async def app_lock_result(self, interaction: discord.Interaction, token: str):
        """Return a short summary of the stored recent outcome for a token."""
        await interaction.response.defer(thinking=True, ephemeral=True)
        data = self._recent_outcomes.get(token)
        if not data:
            await interaction.followup.send("No result found for that token (it may have expired).", ephemeral=True)
            return
        results = data.get("results", {})
        success_count = len(results.get("success", []))
        failed_count = len(results.get("failed", []))
        skipped_count = len(results.get("skipped", []))
        emb = create_darlux_embed(title="🖤 Recent Operation — Result", accent="royal_gold")
        emb.add_field(name="Action", value=data.get("action"), inline=True)
        emb.add_field(name="Guild ID", value=str(data.get("guild_id")), inline=True)
        emb.add_field(name="Success", value=str(success_count), inline=True)
        emb.add_field(name="Failed", value=str(failed_count), inline=True)
        emb.add_field(name="Skipped", value=str(skipped_count), inline=True)
        emb.set_footer(text=f"Requested by {interaction.user}", icon_url=interaction.user.display_avatar.url)
        await interaction.followup.send(embed=emb, ephemeral=True)

    # ---------------------------
    # Developer helper: raw DB export (ephemeral; requires Administrator)
    # ---------------------------
    @app_commands.command(name="lock_logs", description="(Admin) Export recent channel lock logs (ephemeral).")
    async def app_lock_logs(self, interaction: discord.Interaction):
        """Return recent logs from DB. Restricted to administrators for privacy."""
        await interaction.response.defer(thinking=True, ephemeral=True)
        if not interaction.guild:
            await interaction.followup.send("This command must be used in a server.", ephemeral=True)
            return
        member = interaction.user
        if not isinstance(member, discord.Member) or not member.guild_permissions.administrator:
            await interaction.followup.send("Administrator permission required.", ephemeral=True)
            return
        # fetch recent rows (limit)
        try:
            conn = aiosqlite.connect(DB_PATH)
            cur = conn.cursor()
            cur.execute("SELECT guild_name, channel_name, action, performed_by, reason, outcome, details, invoked_at FROM channel_lock_logs ORDER BY id DESC LIMIT 120")
            rows = cur.fetchall()
            conn.close()
            if not rows:
                await interaction.followup.send("No logs found.", ephemeral=True)
                return
            # Build a textual summary safely sized
            lines = []
            for r in rows[:50]:
                gname, cname, action, perf, reason, outcome, details, invoked_at = r
                lines.append(f"[{invoked_at}] {action.upper()} {gname or 'N/A'}/{cname or 'N/A'} by {perf} -> {outcome}")
            text = "\n".join(lines)
            # If text is long, put it in a file
            if len(text) > 1900:
                fp = discord.File(fp=bytes(text, "utf-8"), filename="lock_logs.txt")
                await interaction.followup.send("Recent lock logs:", file=fp, ephemeral=True)
            else:
                emb = create_darlux_embed(title="🖤 Recent Lock Logs (sample)", description=f"Showing up to 50 recent entries", accent="velvet_purple")
                emb.add_field(name="Entries", value=f"```{text}```", inline=False)
                emb.set_footer(text=f"Requested by {interaction.user}", icon_url=interaction.user.display_avatar.url)
                await interaction.followup.send(embed=emb, ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"Failed to read logs: {e}", ephemeral=True)

# ---------------------------
# Setup
# ---------------------------
async def setup(bot: commands.Bot):
    await bot.add_cog(LockCog(bot))
