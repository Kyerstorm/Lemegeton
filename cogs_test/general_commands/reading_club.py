"""Multi-guild reading club nominations, voting, and scheduled spoiler-aware discussions."""
from __future__ import annotations

import logging
import secrets
from datetime import datetime, timezone
from urllib.parse import urlsplit

import discord
from discord import app_commands
from discord.ext import commands, tasks

from database import execute_db_operation
from cogs_test.general_commands.dashboard import command_meta

log = logging.getLogger(__name__)

def validate_source_url(value: str | None) -> str | None:
    """Allow optional HTTPS metadata links; reject malformed and credential-bearing URLs."""
    value = (value or "").strip()
    if not value:
        return None
    parsed = urlsplit(value)
    if parsed.scheme.lower() != "https" or not parsed.hostname or parsed.username is not None or parsed.password is not None:
        raise ValueError("Source links must be complete HTTPS URLs without embedded credentials.")
    return value


def parse_schedule_time(value: str, now: datetime | None = None) -> datetime:
    """Parse an ISO-8601 timestamp that explicitly includes a timezone."""
    text = (value or "").strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as exc:
        raise ValueError("Use ISO-8601 with a timezone, for example 2026-11-02T18:30+00:00.") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("The scheduled time must include a timezone offset, such as +00:00.")
    parsed = parsed.astimezone(timezone.utc)
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    if parsed <= current.astimezone(timezone.utc):
        raise ValueError("Choose a discussion time in the future.")
    return parsed


class ReadingClub(commands.Cog):
    """Persist nomination and voting state with guild-scoped queries."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def cog_load(self) -> None:
        await execute_db_operation(
            "create reading-club nominations",
            """CREATE TABLE IF NOT EXISTS reading_club_nominations (
                nomination_id TEXT PRIMARY KEY,
                guild_id BIGINT NOT NULL,
                channel_id BIGINT NOT NULL,
                proposer_id BIGINT NOT NULL,
                title TEXT NOT NULL,
                category TEXT NOT NULL,
                source_url TEXT,
                status TEXT NOT NULL DEFAULT 'open',
                scheduled_at TIMESTAMP,
                thread_id BIGINT,
                reminder_sent INTEGER NOT NULL DEFAULT 0,
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            )""",
        )
        await execute_db_operation(
            "create reading-club votes",
            """CREATE TABLE IF NOT EXISTS reading_club_votes (
                guild_id BIGINT NOT NULL,
                user_id BIGINT NOT NULL,
                nomination_id TEXT NOT NULL,
                updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (guild_id, user_id)
            )""",
        )
        if not self.dispatch_scheduled_discussions.is_running():
            self.dispatch_scheduled_discussions.start()

    async def cog_unload(self) -> None:
        self.dispatch_scheduled_discussions.cancel()

    club = app_commands.Group(name="reading-club", description="Nominate, vote for, and discuss community reads")

    @club.command(name="nominate", description="Nominate a manga, webtoon, novel, or book")
    @app_commands.guild_only()
    @app_commands.choices(category=[
        app_commands.Choice(name="Manga", value="manga"),
        app_commands.Choice(name="Manhwa", value="manhwa"),
        app_commands.Choice(name="Manhua", value="manhua"),
        app_commands.Choice(name="Webtoon", value="webtoon"),
        app_commands.Choice(name="Light novel", value="light novel"),
        app_commands.Choice(name="Webnovel", value="webnovel"),
        app_commands.Choice(name="General book", value="book"),
    ])
    @app_commands.describe(title="Title to nominate", category="Media category", source_url="Optional metadata or publisher link")
    @command_meta(section="Community", name="Reading Club Nominate")
    async def nominate(self, interaction: discord.Interaction, title: str, category: str, source_url: str | None = None) -> None:
        if interaction.guild is None or interaction.channel is None:
            await interaction.response.send_message("Reading Club is available in server channels.", ephemeral=True)
            return
        title = " ".join((title or "").split())
        if not title:
            await interaction.response.send_message("Enter the title you want to nominate.", ephemeral=True)
            return
        try:
            url = validate_source_url(source_url)
        except ValueError as exc:
            await interaction.response.send_message(str(exc), ephemeral=True)
            return
        nomination_id = secrets.token_hex(4)
        try:
            await execute_db_operation(
                "insert guild reading-club nomination",
                """INSERT INTO reading_club_nominations
                (nomination_id, guild_id, channel_id, proposer_id, title, category, source_url, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, 'open')""",
                (nomination_id, interaction.guild.id, interaction.channel.id, interaction.user.id, title[:200], category, url),
            )
        except Exception:
            log.exception("Failed to save reading-club nomination for guild %s", interaction.guild.id)
            await interaction.response.send_message("The nomination could not be saved. Please try again later.", ephemeral=True)
            return
        link = f"\nSource: {url}" if url else ""
        await interaction.response.send_message(
            f"📚 **Nomination submitted:** {title[:200]} ({category})\nNomination ID: **{nomination_id}**{link}\nUse /reading-club list to see nominations and /reading-club vote to vote.",
            allowed_mentions=discord.AllowedMentions.none(),
        )

    @club.command(name="list", description="List open nominations and vote totals")
    @app_commands.guild_only()
    @command_meta(section="Community", name="Reading Club List")
    async def list_nominations(self, interaction: discord.Interaction) -> None:
        if interaction.guild is None:
            await interaction.response.send_message("This command is server-specific.", ephemeral=True)
            return
        rows = await execute_db_operation(
            "list open reading-club nominations for guild",
            "SELECT * FROM reading_club_nominations WHERE guild_id = ? AND status = 'open' ORDER BY created_at DESC",
            (interaction.guild.id,), fetch_type="all",
        )
        if not rows:
            await interaction.response.send_message("There are no open nominations yet. Use /reading-club nominate to suggest a title.", ephemeral=True)
            return
        lines = []
        for row in (rows or [])[:15]:
            item = dict(row)
            count_row = await execute_db_operation(
                "count votes for reading-club nomination",
                "SELECT COUNT(*) AS vote_count FROM reading_club_votes WHERE guild_id = ? AND nomination_id = ?",
                (interaction.guild.id, item["nomination_id"]), fetch_type="one",
            )
            count = int(dict(count_row).get("vote_count", 0)) if count_row else 0
            title = str(item.get("title") or "Untitled")
            if item.get("source_url"):
                title = f"[{title}]({item['source_url']})"
            lines.append(f"**{title}** · {item.get('category', 'book')} · **{count}** vote(s) · ID: **{item['nomination_id']}**")
        embed = discord.Embed(title="📚 Reading Club · Open nominations", description="\n".join(lines)[:4000], color=discord.Color.blurple())
        embed.set_footer(text="One active vote per person in this server · Votes can be changed")
        await interaction.response.send_message(embed=embed, ephemeral=True, allowed_mentions=discord.AllowedMentions.none())

    @club.command(name="vote", description="Vote for the next community reading selection")
    @app_commands.guild_only()
    @app_commands.describe(nomination_id="ID shown in /reading-club list")
    @command_meta(section="Community", name="Reading Club Vote")
    async def vote(self, interaction: discord.Interaction, nomination_id: str) -> None:
        if interaction.guild is None:
            await interaction.response.send_message("This command is server-specific.", ephemeral=True)
            return
        nomination_id = nomination_id.strip()
        nomination = await execute_db_operation(
            "verify open reading-club nomination",
            "SELECT nomination_id, title FROM reading_club_nominations WHERE guild_id = ? AND nomination_id = ? AND status = 'open'",
            (interaction.guild.id, nomination_id), fetch_type="one",
        )
        if not nomination:
            await interaction.response.send_message("That open nomination was not found in this server.", ephemeral=True)
            return
        existing = await execute_db_operation(
            "find existing guild reading-club vote",
            "SELECT nomination_id FROM reading_club_votes WHERE guild_id = ? AND user_id = ?",
            (interaction.guild.id, interaction.user.id), fetch_type="one",
        )
        if existing:
            await execute_db_operation(
                "change guild reading-club vote",
                "UPDATE reading_club_votes SET nomination_id = ?, updated_at = CURRENT_TIMESTAMP WHERE guild_id = ? AND user_id = ?",
                (nomination_id, interaction.guild.id, interaction.user.id),
            )
        else:
            await execute_db_operation(
                "save guild reading-club vote",
                "INSERT INTO reading_club_votes (guild_id, user_id, nomination_id) VALUES (?, ?, ?)",
                (interaction.guild.id, interaction.user.id, nomination_id),
            )
        await interaction.response.send_message(f"✅ Your vote for **{dict(nomination)['title']}** has been recorded for this server.", ephemeral=True)

    @club.command(name="select", description="Close nominations and select the community's next read")
    @app_commands.guild_only()
    @app_commands.checks.has_permissions(manage_guild=True)
    @app_commands.describe(nomination_id="Nomination ID to select")
    @command_meta(section="Community", name="Reading Club Select")
    async def select(self, interaction: discord.Interaction, nomination_id: str) -> None:
        if interaction.guild is None:
            await interaction.response.send_message("This command is server-specific.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True, thinking=True)
        selected = await execute_db_operation(
            "find selected reading-club nomination",
            "SELECT * FROM reading_club_nominations WHERE guild_id = ? AND nomination_id = ? AND status = 'open'",
            (interaction.guild.id, nomination_id.strip()), fetch_type="one",
        )
        if not selected:
            await interaction.followup.send("That open nomination was not found in this server.", ephemeral=True)
            return
        item = dict(selected)
        await execute_db_operation(
            "select and close reading-club nominations",
            "UPDATE reading_club_nominations SET status = CASE WHEN nomination_id = ? THEN 'selected' ELSE 'closed' END WHERE guild_id = ? AND status = 'open'",
            (item["nomination_id"], interaction.guild.id),
        )
        source = f"\nSource: {item['source_url']}" if item.get("source_url") else ""
        await interaction.channel.send(
            f"🏆 **Community read selected:** {item.get('title', 'Untitled')} ({item.get('category', 'book')}){source}\nA moderator can schedule discussion with /reading-club schedule.",
            allowed_mentions=discord.AllowedMentions.none(),
        )
        await interaction.followup.send("The selection is recorded and the other open nominations are closed.", ephemeral=True)

    @club.command(name="schedule", description="Schedule a spoiler-aware discussion for the selected read")
    @app_commands.guild_only()
    @app_commands.checks.has_permissions(manage_guild=True)
    @app_commands.describe(nomination_id="Selected title's ID", when="ISO-8601 time with timezone, e.g. 2026-11-02T18:30+00:00")
    @command_meta(section="Community", name="Reading Club Schedule")
    async def schedule(self, interaction: discord.Interaction, nomination_id: str, when: str) -> None:
        if interaction.guild is None or not isinstance(interaction.channel, discord.TextChannel):
            await interaction.response.send_message("Schedule discussions from a server text channel that supports public threads.", ephemeral=True)
            return
        try:
            scheduled_at = parse_schedule_time(when)
        except ValueError as exc:
            await interaction.response.send_message(str(exc), ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True, thinking=True)
        row = await execute_db_operation(
            "find selected reading-club nomination to schedule",
            "SELECT * FROM reading_club_nominations WHERE guild_id = ? AND nomination_id = ? AND status = 'selected'",
            (interaction.guild.id, nomination_id.strip()), fetch_type="one",
        )
        if not row:
            await interaction.followup.send("Select a nomination first with /reading-club select.", ephemeral=True)
            return
        item = dict(row)
        thread_name = f"📚 {str(item.get('title') or 'Reading Club')} discussion"[:100]
        try:
            thread = await interaction.channel.create_thread(
                name=thread_name, type=discord.ChannelType.public_thread,
                auto_archive_duration=10080, reason="Scheduled Reading Club discussion",
            )
            source = f"\nSource: {item['source_url']}" if item.get("source_url") else ""
            await thread.send(
                f"**Reading Club discussion**\nSelected work: **{item.get('title', 'Untitled')}** ({item.get('category', 'book')}){source}\n\n**Spoiler rules:** mark plot spoilers with Discord spoiler tags (||like this||), keep unmarked messages spoiler-free, and be considerate of readers at different points.",
                allowed_mentions=discord.AllowedMentions.none(),
            )
        except (discord.Forbidden, discord.HTTPException, AttributeError):
            log.exception("Could not create reading-club discussion thread")
            await interaction.followup.send("I couldn't create the discussion thread. Check Create Public Threads, Send Messages in Threads, and View Channel permissions.", ephemeral=True)
            return
        await execute_db_operation(
            "store scheduled reading-club discussion",
            "UPDATE reading_club_nominations SET scheduled_at = ?, thread_id = ?, reminder_sent = 0, channel_id = ? WHERE guild_id = ? AND nomination_id = ? AND status = 'selected'",
            (scheduled_at.replace(tzinfo=None), thread.id, interaction.channel.id, interaction.guild.id, item["nomination_id"]),
        )
        await interaction.followup.send(
            f"📅 Discussion thread created: <#{thread.id}>. Scheduled for <t:{int(scheduled_at.timestamp())}:F>.",
            ephemeral=True,
        )

    @tasks.loop(seconds=60)
    async def dispatch_scheduled_discussions(self) -> None:
        rows = await execute_db_operation(
            "find due reading-club discussions",
            "SELECT * FROM reading_club_nominations WHERE status = 'selected' AND scheduled_at IS NOT NULL AND reminder_sent = 0 AND scheduled_at <= CURRENT_TIMESTAMP",
            fetch_type="all",
        )
        for row in rows or []:
            item = dict(row)
            guild = self.bot.get_guild(int(item["guild_id"]))
            thread = guild.get_thread(int(item["thread_id"])) if guild and item.get("thread_id") else None
            if thread is None and item.get("thread_id"):
                try:
                    thread = await self.bot.fetch_channel(int(item["thread_id"]))
                except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                    thread = None
            try:
                if thread is not None:
                    await thread.send(
                        f"🔔 **The Reading Club session is starting now:** {item.get('title', 'Selected work')}.\nPlease keep spoilers marked with ||spoiler tags||.",
                        allowed_mentions=discord.AllowedMentions.none(),
                    )
                else:
                    log.warning("Scheduled reading-club thread %s is unavailable", item.get("thread_id"))
            except (discord.Forbidden, discord.HTTPException):
                log.warning("Could not post scheduled reading-club reminder for nomination %s", item.get("nomination_id"), exc_info=True)
            finally:
                await execute_db_operation(
                    "mark reading-club reminder sent",
                    "UPDATE reading_club_nominations SET reminder_sent = 1 WHERE guild_id = ? AND nomination_id = ?",
                    (item["guild_id"], item["nomination_id"]),
                )

    @dispatch_scheduled_discussions.before_loop
    async def before_dispatch_scheduled_discussions(self) -> None:
        await self.bot.wait_until_ready()


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(ReadingClub(bot))
