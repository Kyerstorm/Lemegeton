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



READING_ACTIONS = [
    ("Nominate a title", "nominate"), ("View nominations", "list"), ("Vote", "vote"),
    ("Select the next read", "select"), ("Schedule a discussion", "schedule"),
    ("Explore reading order", "order"),
]
READING_CATEGORIES = [
    ("Manga", "manga"), ("Manhwa", "manhwa"), ("Manhua", "manhua"), ("Webtoon", "webtoon"),
    ("Light novel", "light novel"), ("Webnovel", "webnovel"), ("General book", "book"),
    ("Anime", "anime"), ("Movie", "movie"), ("TV series", "tv"), ("Video game", "game"),
]
READING_ORDER_CATEGORIES = {
    "manga": "MANGA", "manhwa": "MANGA", "manhua": "MANGA", "webtoon": "MANGA",
    "light novel": "LIGHT_NOVEL", "webnovel": "WEBNOVEL", "book": "BOOK",
    "anime": "ANIME", "movie": "MOVIE", "tv": "TV", "game": "GAME",
}


class ReadingActionModal(discord.ui.Modal):
    def __init__(self, cog: "ReadingClub", action: str, category: str):
        labels = {
            "nominate": "Nominate a Read", "vote": "Vote for a Read", "select": "Select Next Read",
            "schedule": "Schedule Reading Discussion", "order": "Explore Reading Order",
        }
        super().__init__(title=labels.get(action, "Reading"), timeout=180)
        self.cog = cog
        self.action = action
        self.category = category
        self.title_input = None
        self.source_url = None
        self.nomination_id = None
        self.when = None
        if action in {"nominate", "order"}:
            self.title_input = discord.ui.TextInput(
                label="Title to nominate" if action == "nominate" else "Title to explore",
                max_length=200, required=True,
            )
            self.add_item(self.title_input)
        if action == "nominate":
            self.source_url = discord.ui.TextInput(label="Publisher or metadata URL (optional)", max_length=1000, required=False)
            self.add_item(self.source_url)
        elif action in {"vote", "select", "schedule"}:
            self.nomination_id = discord.ui.TextInput(
                label="Nomination ID" + (" (leave blank for vote winner)" if action == "select" else ""),
                max_length=100, required=action != "select",
            )
            self.add_item(self.nomination_id)
        if action == "schedule":
            self.when = discord.ui.TextInput(
                label="Future date and time with timezone", max_length=40, required=True,
                placeholder="2026-11-02T18:30+00:00",
            )
            self.add_item(self.when)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        if self.action == "nominate":
            category = self.category
            if category not in {"manga", "manhwa", "manhua", "webtoon", "light novel", "webnovel", "book"}:
                category = "book"
            await self.cog.nominate(
                interaction, self.title_input.value, category,
                self.source_url.value or None,
            )
        elif self.action == "vote":
            await self.cog.vote(interaction, self.nomination_id.value.strip())
        elif self.action == "select":
            await self.cog.select(interaction, self.nomination_id.value.strip() or None)
        elif self.action == "schedule":
            await self.cog.schedule(
                interaction, self.nomination_id.value.strip(), self.when.value.strip(),
            )
        elif self.action == "order":
            connected_media = self.cog.bot.get_cog("ConnectedMedia")
            if connected_media is None:
                await interaction.response.send_message("The media relationship resolver is unavailable right now.", ephemeral=True)
                return
            category = READING_ORDER_CATEGORIES.get(self.category, "LIGHT_NOVEL")
            await connected_media._show_franchise_picker(
                interaction, self.title_input.value, category, reading_order=True,
            )


class ReadingHomeView(FeedbackAwareView):
    """Single entry point for nomination, voting, scheduling, and reading order."""
    def __init__(self, cog: "ReadingClub", owner_id: int):
        super().__init__(timeout=240)
        self.cog = cog
        self.owner_id = owner_id
        self.action = "nominate"
        self.category = "light novel"
        action_select = discord.ui.Select(
            placeholder="Choose a reading action", min_values=1, max_values=1, row=0,
            options=[discord.SelectOption(label=label, value=value, default=value == self.action) for label, value in READING_ACTIONS],
        )
        category_select = discord.ui.Select(
            placeholder="Choose a media category", min_values=1, max_values=1, row=1,
            options=[discord.SelectOption(label=label, value=value, default=value == self.category) for label, value in READING_CATEGORIES],
        )
        action_select.callback = self._set_action
        category_select.callback = self._set_category
        self.add_item(action_select)
        self.add_item(category_select)
        continue_button = discord.ui.Button(label="Continue", style=discord.ButtonStyle.primary, emoji="📚", row=2)
        close_button = discord.ui.Button(label="Close", style=discord.ButtonStyle.secondary, row=2)
        continue_button.callback = self._continue
        close_button.callback = self._close
        self.add_item(continue_button)
        self.add_item(close_button)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message("Only the person who opened this reading menu can control it.", ephemeral=True)
            return False
        return True

    async def _set_action(self, interaction: discord.Interaction) -> None:
        self.action = self.children[0].values[0]
        await interaction.response.edit_message(view=self)

    async def _set_category(self, interaction: discord.Interaction) -> None:
        self.category = self.children[1].values[0]
        await interaction.response.edit_message(view=self)

    async def _continue(self, interaction: discord.Interaction) -> None:
        if self.action == "list":
            await self.cog.list_nominations(interaction)
            return
        await interaction.response.send_modal(ReadingActionModal(self.cog, self.action, self.category))

    async def _close(self, interaction: discord.Interaction) -> None:
        await interaction.response.edit_message(content="Reading menu closed.", embed=None, view=None)


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
            f"📚 **Nomination submitted:** {title[:200]} ({category})\nNomination ID: **{nomination_id}**{link}\nUse /reading (View nominations) to see nominations and /reading (Vote) to vote.",
            allowed_mentions=discord.AllowedMentions.none(),
        )

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
            await interaction.response.send_message("There are no open nominations yet. Use /reading (Nominate a title) to suggest a title.", ephemeral=True)
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

    async def select(self, interaction: discord.Interaction, nomination_id: str | None = None) -> None:
        if interaction.guild is None:
            await interaction.response.send_message("This command is server-specific.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True, thinking=True)
        if nomination_id and nomination_id.strip():
            selected = await execute_db_operation(
                "find selected reading-club nomination",
                "SELECT * FROM reading_club_nominations WHERE guild_id = ? AND nomination_id = ? AND status = 'open'",
                (interaction.guild.id, nomination_id.strip()), fetch_type="one",
            )
            if not selected:
                await interaction.followup.send("That open nomination was not found in this server.", ephemeral=True)
                return
        else:
            nominations = await execute_db_operation(
                "list nominations for reading-club vote winner",
                "SELECT * FROM reading_club_nominations WHERE guild_id = ? AND status = 'open' ORDER BY created_at ASC",
                (interaction.guild.id,), fetch_type="all",
            )
            if not nominations:
                await interaction.followup.send("There are no open nominations to select.", ephemeral=True)
                return
            winner = None
            winner_votes = -1
            for nomination in nominations:
                candidate = dict(nomination)
                vote_row = await execute_db_operation(
                    "count votes for reading-club winner",
                    "SELECT COUNT(*) AS vote_count FROM reading_club_votes WHERE guild_id = ? AND nomination_id = ?",
                    (interaction.guild.id, candidate["nomination_id"]), fetch_type="one",
                )
                votes = int(dict(vote_row).get("vote_count", 0)) if vote_row else 0
                # Stable tie-break: the earliest nomination wins a tie.
                if votes > winner_votes:
                    winner = candidate
                    winner_votes = votes
            selected = winner
            if not selected:
                await interaction.followup.send("No nomination could be selected.", ephemeral=True)
                return
        item = dict(selected)
        await execute_db_operation(
            "select and close reading-club nominations",
            "UPDATE reading_club_nominations SET status = CASE WHEN nomination_id = ? THEN 'selected' ELSE 'closed' END WHERE guild_id = ? AND status = 'open'",
            (item["nomination_id"], interaction.guild.id),
        )
        source = f"\nSource: {item['source_url']}" if item.get("source_url") else ""
        try:
            await interaction.channel.send(
                f"🏆 **Community read selected:** {item.get('title', 'Untitled')} ({item.get('category', 'book')}){source}\nA moderator can schedule discussion with /reading (Schedule a discussion).",
                allowed_mentions=discord.AllowedMentions.none(),
            )
        except (discord.Forbidden, discord.HTTPException, AttributeError):
            log.exception("Could not announce reading-club selection in guild %s", interaction.guild.id)
            await interaction.followup.send("The selection was recorded, but I couldn't announce it in this channel. Check the bot's Send Messages permission.", ephemeral=True)
            return
        await interaction.followup.send(f"The selection is recorded ({winner_votes if not nomination_id else 'manual override'} votes). Other open nominations are closed.", ephemeral=True)

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
            await interaction.followup.send("Select a nomination first with /reading (Select the next read).", ephemeral=True)
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
        try:
            rows = await execute_db_operation(
                "find due reading-club discussions",
                "SELECT * FROM reading_club_nominations WHERE status = 'selected' AND scheduled_at IS NOT NULL AND reminder_sent = 0 AND scheduled_at <= CURRENT_TIMESTAMP",
                fetch_type="all",
            )
        except Exception:
            log.exception("Could not query due reading-club discussions")
            return
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
                try:
                    await execute_db_operation(
                        "mark reading-club reminder sent",
                        "UPDATE reading_club_nominations SET reminder_sent = 1 WHERE guild_id = ? AND nomination_id = ?",
                        (item["guild_id"], item["nomination_id"]),
                    )
                except Exception:
                    log.exception("Could not mark reading-club reminder sent for nomination %s", item.get("nomination_id"))

    @dispatch_scheduled_discussions.before_loop
    async def before_dispatch_scheduled_discussions(self) -> None:
        await self.bot.wait_until_ready()


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(ReadingClub(bot))
