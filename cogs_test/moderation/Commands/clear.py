# clear.py
"""
Features:
 - Permission checks (invoker needs manage_messages or administrator)
 - Bot permission checks (manage_messages)
 - Confirmation for large deletes (interactive confirm)
 - Respect pinned messages (skip by default)
 - Handles messages older than 14 days by deleting individually (no bulk_delete)
 - Batching and small delays to respect rate limits
 - SQLite logging to bot_meta.db -> clear_logs table
 - Dark Luxury themed embeds & neutral footer
 - Preview (ephemeral) to show how many messages will be affected
 - Progress messages and final report with summary
"""

import discord
from discord.ext import commands
from discord import app_commands
from datetime import datetime, timezone, timedelta
import asyncio
import sqlite3
from typing import Optional, List, Tuple, Dict

# ---------------------------
# Palette & embed helper (Dark Luxury)
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
# DB utilities for logging
# ---------------------------
def init_db(path: str = DB_PATH):
    conn = sqlite3.connect(path)
    cur = conn.cursor()
    cur.execute("""
    CREATE TABLE IF NOT EXISTS clear_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        guild_id INTEGER,
        guild_name TEXT,
        channel_id INTEGER,
        channel_name TEXT,
        performed_by INTEGER,
        target_user_id INTEGER,
        amount_requested INTEGER,
        amount_deleted INTEGER,
        reason TEXT,
        outcome TEXT,
        details TEXT,
        invoked_at TEXT
    )
    """)
    conn.commit()
    conn.close()


def log_clear_action(
    guild: Optional[discord.Guild],
    channel: Optional[discord.TextChannel],
    performed_by: discord.User,
    target_user: Optional[discord.User],
    amount_requested: int,
    amount_deleted: int,
    reason: Optional[str],
    outcome: str,
    details: Optional[str] = None,
    path: str = DB_PATH
):
    try:
        conn = sqlite3.connect(path)
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO clear_logs (guild_id, guild_name, channel_id, channel_name, performed_by, target_user_id, amount_requested, amount_deleted, reason, outcome, details, invoked_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                guild.id if guild else None,
                guild.name if guild else None,
                channel.id if channel else None,
                getattr(channel, "name", None) if channel else None,
                performed_by.id if performed_by else None,
                target_user.id if target_user else None,
                amount_requested,
                amount_deleted,
                reason,
                outcome,
                details,
                datetime.utcnow().isoformat()
            )
        )
        conn.commit()
        conn.close()
    except Exception:
        # best-effort logging; don't raise
        pass


# ---------------------------
# Permission helpers
# ---------------------------
def invoker_can_clear(interaction: discord.Interaction) -> Tuple[bool, str]:
    """
    Returns (allowed: bool, reason_message: str).
    By default, requires Manage Messages OR Administrator.
    """
    if not isinstance(interaction.user, discord.Member):
        return False, "Command must be used in a server."
    perms = interaction.user.guild_permissions
    if perms.manage_messages or perms.administrator:
        return True, ""
    return False, "You need Manage Messages (or Administrator) permission to use this command."


def bot_can_clear(guild: discord.Guild, channel: discord.TextChannel) -> Tuple[bool, str]:
    """
    Check that bot has permission to manage messages in the channel.
    """
    bot_member = guild.get_member(guild.me.id) if guild.me else None
    try:
        perms = channel.permissions_for(bot_member or guild.get_member(guild.owner_id))
        if not perms.manage_messages:
            return False, "Bot requires Manage Messages permission in that channel."
        if not perms.read_message_history or not perms.read_messages:
            return False, "Bot needs Read Messages and Read Message History to delete messages."
        return True, ""
    except Exception:
        return False, "Failed to determine bot permissions."


# ---------------------------
# Interaction helpers (confirm / progress)
# ---------------------------
class ConfirmView(discord.ui.View):
    def __init__(self, author: discord.User, timeout: int = 45):
        super().__init__(timeout=timeout)
        self.author = author
        self.value: Optional[bool] = None

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author.id:
            await interaction.response.send_message("This confirmation is only for the command user.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Confirm", style=discord.ButtonStyle.danger)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.value = True
        try:
            await interaction.response.edit_message(content="Confirmed — processing...", view=None)
        except Exception:
            try:
                await interaction.followup.send("Confirmed — processing...", ephemeral=True)
            except Exception:
                pass
        self.stop()

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.value = False
        try:
            await interaction.response.edit_message(content="Cancelled — no changes made.", view=None)
        except Exception:
            try:
                await interaction.followup.send("Cancelled — no changes made.", ephemeral=True)
            except Exception:
                pass
        self.stop()


class ProgressView(discord.ui.View):
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
# Core deletion utilities
# ---------------------------
async def fetch_messages_for_deletion(channel: discord.TextChannel, amount: int, user: Optional[discord.User], skip_pinned: bool = True) -> List[discord.Message]:
    """
    Return a list of messages to delete. Will fetch in batches until we have enough.
    This respects pinned messages and filters by user if provided.
    Note: This will fetch up to amount*3 messages to find the requested number from a user.
    """
    messages_to_delete: List[discord.Message] = []
    last_message = None
    attempts = 0
    max_attempts = 50  # safety guard

    while len(messages_to_delete) < amount and attempts < max_attempts:
        attempts += 1
        fetch_limit = min(100, (amount - len(messages_to_delete)) * 3 + 20)
        try:
            # Build history iterator; pass `before=last_message` only when last_message is set
            if last_message:
                history_iter = channel.history(limit=fetch_limit, before=last_message, oldest_first=False)
            else:
                history_iter = channel.history(limit=fetch_limit, oldest_first=False)
            batch = []
            async for m in history_iter:
                batch.append(m)
        except Exception:
            # if we can't fetch, break and return what we have
            break

        if not batch:
            break

        for msg in batch:
            if skip_pinned and getattr(msg, "pinned", False):
                continue
            if user and msg.author.id != user.id:
                continue
            messages_to_delete.append(msg)
            if len(messages_to_delete) >= amount:
                break

        # prepare for next batch - set last_message to the oldest message we fetched
        last_message = batch[-1] if batch else None
        # small delay to be polite with rate limits
        await asyncio.sleep(0.12)

    return messages_to_delete[:amount]


async def delete_messages_bulk(channel: discord.TextChannel, messages: List[discord.Message], batch_delay: float = 0.12) -> Tuple[int, List[Tuple[int, str]]]:
    """
    Attempt to delete messages in bulk where possible (messages younger than 14 days).
    For messages older than 14 days, delete individually.
    Returns (deleted_count, failures list[(message_id, error_message)])
    """
    deleted_count = 0
    failures: List[Tuple[int, str]] = []

    if not messages:
        return 0, []

    now = datetime.utcnow().replace(tzinfo=timezone.utc)
    bulk_group: List[discord.Message] = []
    older_group: List[discord.Message] = []

    for m in messages:
        created = m.created_at
        if created.tzinfo is None:
            created = created.replace(tzinfo=timezone.utc)
        age = now - created
        if age <= timedelta(days=14):
            bulk_group.append(m)
        else:
            older_group.append(m)

    # Bulk delete younger messages in chunks of up to 100
    if bulk_group:
        chunks = [bulk_group[i:i + 100] for i in range(0, len(bulk_group), 100)]
        for chunk in chunks:
            ids = [m.id for m in chunk]
            # Preferred method: delete_messages (bulk)
            try:
                if hasattr(channel, "delete_messages"):
                    await channel.delete_messages(chunk)  # library versions vary; many accept list of messages
                    deleted_count += len(chunk)
                else:
                    # fallback to purge if delete_messages not available
                    await channel.purge(limit=None, check=lambda m, ids=ids: m.id in ids)
                    deleted_count += len(chunk)
            except Exception:
                # fallback: try purge with check
                try:
                    await channel.purge(limit=None, check=lambda m, ids=ids: m.id in ids)
                    deleted_count += len(chunk)
                except Exception:
                    # final fallback: delete individually
                    for m in chunk:
                        try:
                            await m.delete()
                            deleted_count += 1
                            await asyncio.sleep(batch_delay)
                        except Exception as e:
                            failures.append((m.id, f"Individual delete failed: {e}"))
            await asyncio.sleep(batch_delay)

    # Delete older messages individually (can't bulk delete)
    for m in older_group:
        try:
            await m.delete()
            deleted_count += 1
            await asyncio.sleep(batch_delay)
        except Exception as e:
            failures.append((m.id, f"Old-message delete failed: {e}"))

    return deleted_count, failures


# ---------------------------
# Clear Cog
# ---------------------------
class ClearCog(commands.Cog):
    """
    /clear command Cog
    """

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        init_db()
        # default safety settings (tweak here)
        self.skip_pinned = True
        self.large_confirm_threshold = 50  # ask for confirmation if deleting >= this many messages
        self.max_allowed = 5000  # hard upper limit to prevent accidental massive deletes (tweakable)
        self.batch_delay = 0.12  # seconds between deletes individually
        # small in-memory cache for rate-limiting by user (avoid spam)
        self._recent_invocations: Dict[int, float] = {}
        self._invocation_cooldown = 2.0  # seconds between uses per user to avoid accidental double-taps

    # -------------
    # helpers
    # -------------
    def _check_invocation_rate(self, user_id: int) -> Tuple[bool, Optional[str]]:
        import time
        last = self._recent_invocations.get(user_id)
        now = time.time()
        if last and (now - last) < self._invocation_cooldown:
            return False, f"Please wait {int(self._invocation_cooldown - (now - last))}s before invoking again."
        self._recent_invocations[user_id] = now
        return True, None

    # -------------
    # Slash command
    # -------------
    @app_commands.command(name="clear", description="Delete a number of messages from this channel (optional: filter by user).")
    @app_commands.describe(amount="Number of messages to delete (1 - max)", user="Optional: limit deletion to messages by this user", reason="Optional reason for audit logging")
    @app_commands.rename(amount="amount", user="user", reason="reason")
    async def app_clear(self, interaction: discord.Interaction, amount: int, user: Optional[discord.User] = None, reason: Optional[str] = None):
        """
        Slash command handler for /clear.
        - amount: int
        - user: optional discord.User
        - reason: optional string
        """
        # Defer quickly (thinking indicator). We will use followups for ephemeral messages.
        try:
            await interaction.response.defer(thinking=True)
        except Exception:
            # If response was already used, ignore - we'll use followup below
            pass

        # Basic validations and environment checks
        if not interaction.guild:
            await interaction.followup.send("This command can only be used in servers.", ephemeral=True)
            return

        # Validate amount range
        if amount <= 0:
            await interaction.followup.send("Amount must be greater than 0.", ephemeral=True)
            return
        if amount > self.max_allowed:
            await interaction.followup.send(f"Amount exceeds the hard limit of {self.max_allowed}. Please choose a smaller number.", ephemeral=True)
            return

        # Rate-limit invocations per user (tiny debounce)
        ok, msg = self._check_invocation_rate(interaction.user.id)
        if not ok:
            await interaction.followup.send(msg, ephemeral=True)
            return

        # Permission checks for invoker
        allowed, acl_msg = invoker_can_clear(interaction)
        if not allowed:
            await interaction.followup.send(acl_msg, ephemeral=True)
            return

        # Bot permission checks
        channel = interaction.channel
        if not isinstance(channel, discord.TextChannel):
            await interaction.followup.send("This command must be used in a text channel.", ephemeral=True)
            return
        ok, bot_msg = bot_can_clear(interaction.guild, channel)
        if not ok:
            await interaction.followup.send(f"I cannot delete messages here: {bot_msg}", ephemeral=True)
            return

        # Fetch candidate messages (preview)
        preview_list = await fetch_messages_for_deletion(channel, amount, user, skip_pinned=self.skip_pinned)
        preview_count = len(preview_list)

        # If preview_count is zero, nothing to delete
        if preview_count == 0:
            emb = create_darlux_embed(title="🖤 Clear — Nothing Found", description="No eligible messages found to delete (perhaps pinned messages or none from that user).", accent="velvet_purple")
            emb.set_footer(text=f"Requested by {interaction.user}", icon_url=interaction.user.display_avatar.url if interaction.user.display_avatar else None)
            await interaction.followup.send(embed=emb, ephemeral=True)
            # log zero-action
            log_clear_action(interaction.guild, channel, interaction.user, user, amount, 0, reason, "no_messages", details="No eligible messages found")
            return

        # If the requested amount is greater than what exists, warn the user in preview
        emb_preview = create_darlux_embed(title="🖤 Clear — Preview", description=f"Found **{preview_count}** messages matching your criteria that are eligible for deletion.", accent="midnight_blue")
        emb_preview.add_field(name="Channel", value=channel.mention, inline=True)
        emb_preview.add_field(name="Requested", value=str(amount), inline=True)
        emb_preview.add_field(name="To delete", value=str(preview_count), inline=True)
        emb_preview.add_field(name="Target User", value=f"{user}" if user else "Any", inline=True)
        emb_preview.add_field(name="Skip pinned", value=str(self.skip_pinned), inline=True)
        emb_preview.add_field(name="Reason", value=reason or "No reason provided", inline=False)
        emb_preview.set_footer(text=f"Requested by {interaction.user}", icon_url=interaction.user.display_avatar.url if interaction.user.display_avatar else None)

        # If above threshold, require confirmation
        if preview_count >= self.large_confirm_threshold:
            confirm_view = ConfirmView(interaction.user, timeout=45)
            try:
                await interaction.followup.send(embed=emb_preview, view=confirm_view, ephemeral=True)
            except Exception:
                # fallback
                await interaction.followup.send(embed=emb_preview, ephemeral=True)
            await confirm_view.wait()
            if confirm_view.value is not True:
                await interaction.followup.send("Clear cancelled.", ephemeral=True)
                return
            # If confirmed, proceed to deletion
            processing_emb = create_darlux_embed(title="🖤 Clear — In Progress", description=f"Deleting {preview_count} messages...", accent="velvet_purple")
            processing_emb.set_footer(text=f"Requested by {interaction.user}", icon_url=interaction.user.display_avatar.url if interaction.user.display_avatar else None)
            prog_view = ProgressView()
            prog_msg = await interaction.followup.send(embed=processing_emb, view=prog_view)
        else:
            # Small confirmations for small deletes - still show ephemeral info and then proceed
            try:
                await interaction.followup.send(embed=emb_preview, ephemeral=True)
            except Exception:
                pass
            processing_emb = create_darlux_embed(title="🖤 Clear — In Progress", description=f"Deleting {preview_count} messages...", accent="velvet_purple")
            processing_emb.set_footer(text=f"Requested by {interaction.user}", icon_url=interaction.user.display_avatar.url if interaction.user.display_avatar else None)
            prog_view = ProgressView()
            prog_msg = await interaction.followup.send(embed=processing_emb, view=prog_view)

        # Perform deletion
        try:
            deleted_count, failures = await delete_messages_bulk(channel, preview_list, batch_delay=self.batch_delay)
            # Build result embed
            final_emb = create_darlux_embed(title="🖤 Clear — Completed", description=f"Requested: {amount} • Deleted: {deleted_count}", accent="royal_gold")
            if failures:
                final_emb.add_field(name="Failures", value=str(len(failures)), inline=True)
            final_emb.add_field(name="Target User", value=f"{user}" if user else "Any", inline=True)
            final_emb.add_field(name="Channel", value=channel.mention, inline=True)
            final_emb.add_field(name="Reason", value=reason or "No reason provided", inline=False)

            # If there are failures, include a sample list (ephemeral)
            if failures:
                sample = "\n".join([f"{fid} — {msg}" for fid, msg in failures[:12]])
                details_emb = create_darlux_embed(title="🖤 Clear — Failures (sample)", description=sample or "No details", accent="velvet_purple")
                details_emb.set_footer(text=f"Requested by {interaction.user}", icon_url=interaction.user.display_avatar.url if interaction.user.display_avatar else None)
                await interaction.followup.send(embed=details_emb, ephemeral=True)

            try:
                await prog_msg.edit(embed=final_emb, view=None)
            except Exception:
                # fallback: send followup
                await interaction.followup.send(embed=final_emb, ephemeral=True)

            # Logging
            outcome = "partial_failures" if failures else "success"
            details_text = f"failures:{len(failures)}" if failures else None
            log_clear_action(interaction.guild, channel, interaction.user, user, amount, deleted_count, reason, outcome, details=details_text)
        except Exception as e:
            err_emb = create_darlux_embed(title="🖤 Clear — Failed", description=f"An error occurred: {e}", accent="velvet_purple")
            err_emb.set_footer(text=f"Requested by {interaction.user}", icon_url=interaction.user.display_avatar.url if interaction.user.display_avatar else None)
            try:
                await prog_msg.edit(embed=err_emb, view=None)
            except Exception:
                await interaction.followup.send(embed=err_emb, ephemeral=True)
            log_clear_action(interaction.guild, channel, interaction.user, user, amount, 0, reason, "failed", details=str(e))

    # ---------------------------
    # Optional helper command: clear_preview (ephemeral preview only)
    # ---------------------------
    @app_commands.command(name="clear_preview", description="Preview how many messages would be removed by /clear (ephemeral).")
    @app_commands.describe(amount="Number of messages to consider", user="Optional user filter")
    async def app_clear_preview(self, interaction: discord.Interaction, amount: int, user: Optional[discord.User] = None):
        try:
            await interaction.response.defer(thinking=True)
        except Exception:
            pass

        if not interaction.guild:
            await interaction.followup.send("Use this in a server.", ephemeral=True)
            return
        if amount <= 0:
            await interaction.followup.send("Amount must be greater than 0.", ephemeral=True)
            return
        if amount > self.max_allowed:
            await interaction.followup.send(f"Amount exceeds limit of {self.max_allowed}.", ephemeral=True)
            return
        # permission checks
        ok, msg = invoker_can_clear(interaction)
        if not ok:
            await interaction.followup.send(msg, ephemeral=True)
            return
        channel = interaction.channel
        if not isinstance(channel, discord.TextChannel):
            await interaction.followup.send("This must be used in a text channel.", ephemeral=True)
            return
        ok, botmsg = bot_can_clear(interaction.guild, channel)
        if not ok:
            await interaction.followup.send(f"I cannot operate here: {botmsg}", ephemeral=True)
            return

        preview_list = await fetch_messages_for_deletion(channel, amount, user, skip_pinned=self.skip_pinned)
        emb = create_darlux_embed(title="🖤 Clear — Preview", description=f"Found **{len(preview_list)}** messages matching your criteria.", accent="midnight_blue")
        emb.add_field(name="Channel", value=channel.mention, inline=True)
        emb.add_field(name="Requested", value=str(amount), inline=True)
        emb.add_field(name="To delete", value=str(len(preview_list)), inline=True)
        emb.add_field(name="Target User", value=f"{user}" if user else "Any", inline=True)
        emb.set_footer(text=f"Requested by {interaction.user}", icon_url=interaction.user.display_avatar.url if interaction.user.display_avatar else None)
        await interaction.followup.send(embed=emb, ephemeral=True)


# ---------------------------
# Setup
# ---------------------------
async def setup(bot: commands.Bot):
    await bot.add_cog(ClearCog(bot))
