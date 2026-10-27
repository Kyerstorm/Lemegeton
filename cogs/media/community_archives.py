"""Database-backed community media archives and panel-style events."""
from __future__ import annotations

import json
import logging
import secrets
from typing import Any
from urllib.parse import urlsplit

import discord
from discord import app_commands
from discord.ext import commands

from helpers.command_error_handler import FeedbackAwareModal, FeedbackAwareView, handle_application_command_error
import database
from helpers import media_storage
from cogs_test.general_commands.dashboard import command_meta

log = logging.getLogger("Lemegeton.CommunityArchives")
ACTIONS = [
    app_commands.Choice(name="Add submission", value="add"),
    app_commands.Choice(name="Browse approved entries", value="browse"),
    app_commands.Choice(name="Search entries", value="search"),
    app_commands.Choice(name="Random entry", value="random"),
]
ARCHIVE_TYPES = [
    app_commands.Choice(name="All archives", value="all"),
    app_commands.Choice(name="Quotes", value="quotes"),
    app_commands.Choice(name="Fanworks", value="fanworks"),
    app_commands.Choice(name="Moodboards", value="moodboards"),
    app_commands.Choice(name="Soundtracks", value="soundtracks"),
    app_commands.Choice(name="Scenes", value="scenes"),
    app_commands.Choice(name="Recommendations", value="recommendation-board"),
    app_commands.Choice(name="Theories", value="theories"),
]
MEDIA_TYPES = [
    app_commands.Choice(name="Anime", value="Anime"),
    app_commands.Choice(name="Manga / manhwa / manhua", value="Manga"),
    app_commands.Choice(name="Light novel", value="Light novel"),
    app_commands.Choice(name="Webnovel", value="Webnovel"),
    app_commands.Choice(name="Book", value="Book"),
    app_commands.Choice(name="Movie", value="Movie"),
    app_commands.Choice(name="TV series", value="TV"),
    app_commands.Choice(name="Other", value="Other"),
]
MAX_TAGS = 10
MAX_QUOTE_LENGTH = 280


def normalize_tags(value: str | None) -> list[str]:
    """Return a bounded, deduplicated tag set."""
    tags = []
    for raw in (value or "").split(","):
        tag = " ".join(raw.split()).casefold()
        if not tag:
            continue
        if len(tag) > 40:
            raise ValueError("Each tag must be 40 characters or fewer.")
        if tag not in tags:
            tags.append(tag)
    if len(tags) > MAX_TAGS:
        raise ValueError(f"Use no more than {MAX_TAGS} tags.")
    return tags


def split_candidates(value: str | None) -> list[str]:
    """Parse a bracket's pipe-separated candidates and reject duplicates."""
    candidates = [" ".join(item.split()) for item in (value or "").split("|")]
    candidates = [item[:150] for item in candidates if item]
    unique = []
    seen = set()
    for item in candidates:
        if item.casefold() not in seen:
            unique.append(item)
            seen.add(item.casefold())
    if not 2 <= len(unique) <= 16:
        raise ValueError("Provide between 2 and 16 distinct candidates, separated with |.")
    return unique


def spoiler_wrap(text: str, spoiler: bool) -> str:
    return f"||{text}||" if spoiler else text


def _safe(value: Any, limit: int = 500) -> str:
    return discord.utils.escape_markdown(" ".join(str(value or "").split()))[:limit]


def _https_url(value: str | None, required: bool = False) -> str | None:
    raw = (value or "").strip()
    if not raw:
        if required:
            raise ValueError("Provide a source URL.")
        return None
    parsed = urlsplit(raw)
    if parsed.scheme.lower() != "https" or not parsed.hostname or parsed.username or parsed.password or len(raw) > 1000:
        raise ValueError("Source links must be complete HTTPS URLs without embedded credentials.")
    return raw



ARCHIVE_UI_TYPES = [
    ("Quotes", "quotes"), ("Fanworks", "fanworks"), ("Moodboards", "moodboards"),
    ("Soundtracks", "soundtracks"), ("Scenes", "scenes"),
    ("Recommendations", "recommendation-board"), ("Theories", "theories"),
]
ARCHIVE_UI_ACTIONS = [
    ("Browse", "browse"), ("Search", "search"), ("Submit", "add"), ("Random entry", "random"),
    ("My submissions", "mine"), ("Report an entry", "report"),
    ("Review submissions", "review"), ("Review a submission", "review-entry"),
    ("View reports", "reports"), ("Review a report", "report-review"),
]


class ArchiveSubmissionModal(FeedbackAwareModal):
    def __init__(self, cog: "CommunityArchives", archive_type: str, media_type: str = "Other"):
        super().__init__(title=f"Submit {archive_type.replace('-', ' ').title()}", timeout=180)
        self.cog = cog
        self.archive_type = archive_type
        self.media_type = media_type
        self.entry_title = discord.ui.TextInput(label="Title", max_length=200, required=True)
        self.content = discord.ui.TextInput(
            label="Description / quote (max 280 for quotes)", style=discord.TextStyle.paragraph,
            max_length=3000, required=True,
        )
        self.source_title = discord.ui.TextInput(label="Related work / source title", max_length=200, required=False)
        self.creator = discord.ui.TextInput(label="Creator / speaker / composer", max_length=200, required=False)
        self.url = discord.ui.TextInput(label="Source URL (HTTPS)", max_length=1000, required=False)
        for field in (self.entry_title, self.content, self.source_title, self.creator, self.url):
            self.add_item(field)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        await self.cog._archive_action(
            interaction, self.archive_type, "add",
            self.entry_title.value, self.content.value, self.source_title.value or None,
            self.creator.value or None, self.url.value or None, self.media_type, None,
            self.archive_type == "theories", None,
        )


class ArchiveSearchModal(FeedbackAwareModal):
    def __init__(self, cog: "CommunityArchives", archive_type: str):
        super().__init__(title=f"Search {archive_type.replace('-', ' ').title()}", timeout=180)
        self.cog = cog
        self.archive_type = archive_type
        self.keyword = discord.ui.TextInput(label="Search terms", max_length=100, required=True)
        self.add_item(self.keyword)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        await self.cog._archive_action(
            interaction, self.archive_type, "search", None, None, None, None, None,
            "Other", None, self.archive_type == "theories", self.keyword.value,
        )


class ArchiveReportModal(FeedbackAwareModal):
    def __init__(self, cog: "CommunityArchives", archive_type: str):
        super().__init__(title="Report archive entry", timeout=180)
        self.cog = cog
        self.archive_type = archive_type
        self.entry_id = discord.ui.TextInput(label="Entry ID", max_length=20, required=True)
        self.reason = discord.ui.TextInput(
            label="Why should moderators review it?", style=discord.TextStyle.paragraph,
            min_length=10, max_length=1000, required=True,
        )
        self.add_item(self.entry_id)
        self.add_item(self.reason)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        try:
            entry_id = int(self.entry_id.value.strip())
        except ValueError:
            await interaction.response.send_message("Entry ID must be a number.", ephemeral=True)
            return
        await self.cog.archive_report(interaction, self.archive_type, entry_id, self.reason.value)


class ArchiveReviewModal(FeedbackAwareModal):
    def __init__(self, cog: "CommunityArchives", archive_type: str):
        super().__init__(title="Review archive submission", timeout=180)
        self.cog = cog
        self.archive_type = archive_type
        self.action = discord.ui.TextInput(
            label="Action: approve, reject, or remove", max_length=10, required=True,
        )
        self.entry_id = discord.ui.TextInput(label="Submission ID", max_length=20, required=True)
        self.add_item(self.action)
        self.add_item(self.entry_id)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        action = self.action.value.strip().casefold()
        if action not in {"approve", "reject", "remove"}:
            await interaction.response.send_message("Choose approve, reject, or remove.", ephemeral=True)
            return
        try:
            entry_id = int(self.entry_id.value.strip())
        except ValueError:
            await interaction.response.send_message("Submission ID must be a number.", ephemeral=True)
            return
        await self.cog._review_archive(interaction, action, entry_id)


class ArchiveReportReviewModal(FeedbackAwareModal):
    def __init__(self, cog: "CommunityArchives"):
        super().__init__(title="Review archive report", timeout=180)
        self.cog = cog
        self.decision = discord.ui.TextInput(
            label="Decision (list, resolved, dismissed, remove)", max_length=12, required=False,
            placeholder="list",
        )
        self.report_id = discord.ui.TextInput(label="Report ID (for a decision)", max_length=20, required=False)
        self.reason = discord.ui.TextInput(label="Moderator note (optional)", max_length=1000, required=False)
        for field in (self.decision, self.report_id, self.reason):
            self.add_item(field)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        decision = self.decision.value.strip().casefold() or "list"
        try:
            report_id = int(self.report_id.value.strip()) if self.report_id.value.strip() else None
        except ValueError:
            await interaction.response.send_message("Report ID must be a number.", ephemeral=True)
            return
        await self.cog.archive_report_review(interaction, decision, report_id, self.reason.value or "")


class ArchiveResultsView(FeedbackAwareView):
    """Panel-style, one-entry-at-a-time browsing for community archives."""
    def __init__(
        self, cog: "CommunityArchives", owner_id: int, archive_type: str,
        rows: list[Any], media_type: str = "Other",
    ):
        super().__init__(timeout=240)
        self.cog = cog
        self.owner_id = owner_id
        self.archive_type = archive_type
        self.rows = [dict(row) for row in rows]
        self.media_type = media_type
        self.index = 0
        previous = discord.ui.Button(label="Previous", style=discord.ButtonStyle.secondary, row=0)
        following = discord.ui.Button(label="Next", style=discord.ButtonStyle.secondary, row=0)
        search = discord.ui.Button(label="Search", style=discord.ButtonStyle.primary, row=1)
        submit = discord.ui.Button(label="Contribute", style=discord.ButtonStyle.success, row=1)
        close = discord.ui.Button(label="Close", style=discord.ButtonStyle.secondary, row=1)
        previous.callback = self._previous
        following.callback = self._next
        search.callback = self._search
        submit.callback = self._submit
        close.callback = self._close
        self.add_item(previous)
        self.add_item(following)
        self.add_item(search)
        self.add_item(submit)
        self.add_item(close)
        self._sync_buttons()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message("Only the person who opened this archive view can control it.", ephemeral=True)
            return False
        return True

    def _sync_buttons(self) -> None:
        self.children[0].disabled = self.index <= 0
        self.children[1].disabled = self.index >= len(self.rows) - 1

    def build_embed(self) -> discord.Embed:
        embed = self.cog._entry_embed(self.archive_type, self.rows[self.index])
        embed.set_footer(text=f"Community archive · Entry {self.index + 1} of {len(self.rows)} · Use the buttons to browse or contribute")
        return embed

    async def _move(self, interaction: discord.Interaction, delta: int) -> None:
        self.index = max(0, min(len(self.rows) - 1, self.index + delta))
        self._sync_buttons()
        await interaction.response.edit_message(embed=self.build_embed(), view=self)

    async def _previous(self, interaction: discord.Interaction) -> None:
        await self._move(interaction, -1)

    async def _next(self, interaction: discord.Interaction) -> None:
        await self._move(interaction, 1)

    async def _search(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_modal(ArchiveSearchModal(self.cog, self.archive_type))

    async def _submit(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_modal(ArchiveSubmissionModal(self.cog, self.archive_type, self.media_type))

    async def _close(self, interaction: discord.Interaction) -> None:
        await interaction.response.edit_message(content="Archive view closed.", embed=None, view=None)


class ArchiveHomeView(FeedbackAwareView):
    """Unified archive launcher for browse, submissions, and guild-local moderation."""
    def __init__(self, cog: "CommunityArchives", owner_id: int):
        super().__init__(timeout=240)
        self.cog = cog
        self.owner_id = owner_id
        self.archive_type = "quotes"
        self.media_type = "Other"
        self.action = "browse"

        archive_select = discord.ui.Select(
            placeholder="Choose an archive", min_values=1, max_values=1, row=0,
            options=[discord.SelectOption(label=label, value=value, default=value == self.archive_type) for label, value in ARCHIVE_UI_TYPES],
        )
        media_select = discord.ui.Select(
            placeholder="Related media type", min_values=1, max_values=1, row=1,
            options=[discord.SelectOption(label=choice.name, value=choice.value, default=choice.value == self.media_type) for choice in MEDIA_TYPES],
        )
        action_select = discord.ui.Select(
            placeholder="Choose an action", min_values=1, max_values=1, row=2,
            options=[discord.SelectOption(label=label, value=value, default=value == self.action) for label, value in ARCHIVE_UI_ACTIONS],
        )
        archive_select.callback = self._set_archive
        media_select.callback = self._set_media
        action_select.callback = self._set_action
        self.add_item(archive_select)
        self.add_item(media_select)
        self.add_item(action_select)
        open_button = discord.ui.Button(label="Continue", style=discord.ButtonStyle.primary, emoji="↗️", row=3)
        close_button = discord.ui.Button(label="Close", style=discord.ButtonStyle.secondary, row=3)
        open_button.callback = self._open
        close_button.callback = self._close
        self.add_item(open_button)
        self.add_item(close_button)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message("Only the person who opened this archive menu can control it.", ephemeral=True)
            return False
        return True

    async def _set_archive(self, interaction: discord.Interaction) -> None:
        self.archive_type = self.children[0].values[0]
        await interaction.response.edit_message(view=self)

    async def _set_media(self, interaction: discord.Interaction) -> None:
        self.media_type = self.children[1].values[0]
        await interaction.response.edit_message(view=self)

    async def _set_action(self, interaction: discord.Interaction) -> None:
        self.action = self.children[2].values[0]
        await interaction.response.edit_message(view=self)

    async def _open(self, interaction: discord.Interaction) -> None:
        if self.action in {"browse", "random"}:
            await self.cog._archive_action(
                interaction, self.archive_type, self.action, None, None, None, None, None,
                self.media_type, None, self.archive_type == "theories", None,
            )
        elif self.action == "search":
            await interaction.response.send_modal(ArchiveSearchModal(self.cog, self.archive_type))
        elif self.action == "add":
            await interaction.response.send_modal(ArchiveSubmissionModal(self.cog, self.archive_type, self.media_type))
        elif self.action == "mine":
            await self.cog.archive_mine(interaction, self.archive_type)
        elif self.action == "report":
            await interaction.response.send_modal(ArchiveReportModal(self.cog, self.archive_type))
        elif self.action == "review":
            await self.cog._review_archive(interaction, "list", None)
        elif self.action == "review-entry":
            await interaction.response.send_modal(ArchiveReviewModal(self.cog, self.archive_type))
        elif self.action == "reports":
            await self.cog.archive_report_review(interaction, "list", None, "")
        elif self.action == "report-review":
            await interaction.response.send_modal(ArchiveReportReviewModal(self.cog))
        else:
            await interaction.response.send_message("That archive action is not available.", ephemeral=True)

    async def _close(self, interaction: discord.Interaction) -> None:
        await interaction.response.edit_message(content="Community archive closed.", embed=None, view=None)


class CommunityArchives(commands.Cog):
    """Global public entries, guild-local moderation, and guild-local polls."""
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def cog_load(self) -> None:
        statements = [
            ("create community archive entries", """CREATE TABLE IF NOT EXISTS community_archive_entries (
                id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
                archive_type VARCHAR(32) NOT NULL,
                title VARCHAR(200) NOT NULL,
                content TEXT NOT NULL DEFAULT '',
                source_title VARCHAR(200),
                creator VARCHAR(200),
                media_type VARCHAR(32) NOT NULL DEFAULT 'Other',
                source_url TEXT,
                tags TEXT NOT NULL DEFAULT '[]',
                spoiler BOOLEAN NOT NULL DEFAULT FALSE,
                status VARCHAR(16) NOT NULL DEFAULT 'pending',
                created_by BIGINT NOT NULL,
                created_guild_id BIGINT NOT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )"""),
            ("index community archive browsing", "CREATE INDEX IF NOT EXISTS community_archive_browse_idx ON community_archive_entries (archive_type, status, created_at DESC)"),
            ("index archive origin guild", "CREATE INDEX IF NOT EXISTS community_archive_guild_idx ON community_archive_entries (created_guild_id, status, created_at DESC)"),
            ("create community archive reports", """CREATE TABLE IF NOT EXISTS community_archive_reports (
                id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
                archive_type VARCHAR(32) NOT NULL,
                entry_id BIGINT NOT NULL,
                guild_id BIGINT NOT NULL,
                reporter_id BIGINT NOT NULL,
                reason TEXT NOT NULL,
                status VARCHAR(16) NOT NULL DEFAULT 'pending',
                reviewed_by BIGINT,
                review_reason TEXT,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                reviewed_at TIMESTAMPTZ,
                UNIQUE (guild_id, archive_type, entry_id, reporter_id)
            )"""),
            ("index community archive reports", "CREATE INDEX IF NOT EXISTS community_archive_reports_guild_status_idx ON community_archive_reports (guild_id, status, created_at DESC)"),
            ("create panel of the day history", """CREATE TABLE IF NOT EXISTS community_panel_daily_log (
                guild_id BIGINT NOT NULL,
                feature_date DATE NOT NULL DEFAULT CURRENT_DATE,
                panel_id BIGINT NOT NULL,
                featured_by BIGINT NOT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                PRIMARY KEY (guild_id, feature_date)
            )"""),
            ("create community brackets", """CREATE TABLE IF NOT EXISTS community_media_brackets (
                bracket_id VARCHAR(16) PRIMARY KEY, guild_id BIGINT NOT NULL, creator_id BIGINT NOT NULL,
                title VARCHAR(200) NOT NULL, media_type VARCHAR(32) NOT NULL, candidates TEXT NOT NULL,
                status VARCHAR(16) NOT NULL DEFAULT 'open', created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )"""),
            ("create bracket votes", """CREATE TABLE IF NOT EXISTS community_media_bracket_votes (
                guild_id BIGINT NOT NULL, bracket_id VARCHAR(16) NOT NULL, user_id BIGINT NOT NULL,
                candidate TEXT NOT NULL, updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                PRIMARY KEY (guild_id, bracket_id, user_id)
            )"""),
            ("create adaptation polls", """CREATE TABLE IF NOT EXISTS community_adaptation_polls (
                poll_id VARCHAR(16) PRIMARY KEY, guild_id BIGINT NOT NULL, creator_id BIGINT NOT NULL,
                title VARCHAR(200) NOT NULL, media_type VARCHAR(32) NOT NULL, option_a VARCHAR(200) NOT NULL,
                option_b VARCHAR(200) NOT NULL, source_url TEXT, created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )"""),
            ("create adaptation poll votes", """CREATE TABLE IF NOT EXISTS community_adaptation_votes (
                guild_id BIGINT NOT NULL, poll_id VARCHAR(16) NOT NULL, user_id BIGINT NOT NULL,
                choice VARCHAR(1) NOT NULL, updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                PRIMARY KEY (guild_id, poll_id, user_id)
            )"""),
            ("create media quiz questions", """CREATE TABLE IF NOT EXISTS community_media_quiz_questions (
                id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY, guild_id BIGINT NOT NULL,
                creator_id BIGINT NOT NULL, question TEXT NOT NULL, answer TEXT NOT NULL, source_url TEXT,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )"""),
            ("create media quiz sessions", """CREATE TABLE IF NOT EXISTS community_media_quiz_sessions (
                guild_id BIGINT NOT NULL, channel_id BIGINT NOT NULL, user_id BIGINT NOT NULL,
                question_id BIGINT NOT NULL, created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                PRIMARY KEY (guild_id, user_id)
            )"""),
        ]
        for name, sql in statements:
            await database.execute_db_operation(name, sql)

    async def _archive_action(
        self, interaction: discord.Interaction, archive_type: str, action: str,
        title: str | None, content: str | None, source_title: str | None,
        creator: str | None, url: str | None, media_type: str,
        tags_raw: str | None, spoiler: bool, keyword: str | None,
    ) -> None:
        if action == "add":
            if not interaction.guild_id:
                await interaction.response.send_message("Submissions must be made in a server.", ephemeral=True)
                return
            clean_title = " ".join((title or "").split())
            clean_content = (content or "").strip()
            clean_source = " ".join((source_title or "").split()) or None
            clean_creator = " ".join((creator or "").split()) or None
            if not clean_title or not clean_content:
                await interaction.response.send_message("Provide both a title and content/description.", ephemeral=True)
                return
            if len(clean_title) > 200 or len(clean_content) > 3000:
                await interaction.response.send_message("Titles are limited to 200 characters and content to 3,000.", ephemeral=True)
                return
            if archive_type == "quotes":
                if len(clean_content) > MAX_QUOTE_LENGTH:
                    await interaction.response.send_message(f"Quotes are limited to {MAX_QUOTE_LENGTH} characters. Do not submit lyrics, chapters or long copyrighted passages.", ephemeral=True)
                    return
                if not clean_source:
                    await interaction.response.send_message("Add the source work's title for attribution.", ephemeral=True)
                    return
            if archive_type == "fanworks" and not clean_creator:
                await interaction.response.send_message("Provide the original creator's name or handle.", ephemeral=True)
                return
            if archive_type == "soundtracks" and not url:
                await interaction.response.send_message("Provide a legitimate music/video platform link. Lemegeton does not host audio.", ephemeral=True)
                return
            try:
                clean_url = _https_url(url, required=archive_type in {"fanworks", "soundtracks"})
                tags = normalize_tags(tags_raw)
            except ValueError as exc:
                await interaction.response.send_message(str(exc), ephemeral=True)
                return
            row = await database.execute_db_operation(
                "save community archive submission",
                """INSERT INTO community_archive_entries
                   (archive_type, title, content, source_title, creator, media_type, source_url, tags,
                    spoiler, status, created_by, created_guild_id)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?) RETURNING id""",
                (archive_type, clean_title, clean_content, clean_source, clean_creator, media_type, clean_url,
                 json.dumps(tags), bool(spoiler), interaction.user.id, interaction.guild_id),
                fetch_type="one",
            )
            entry_id = row[0] if row else "unknown"
            await interaction.response.send_message(
                f"Submission **#{entry_id}** is saved and awaits moderator review in this server. Approved entries enter the shared archive.",
                ephemeral=True,
            )
            return

        clean_keyword = " ".join((keyword or title or "").split())
        query = """SELECT id, title, content, source_title, creator, media_type, source_url, tags, spoiler, created_at
                   FROM community_archive_entries WHERE archive_type = ? AND status = 'approved'"""
        params: list[Any] = [archive_type]
        if action == "search":
            if not clean_keyword:
                await interaction.response.send_message("Provide a search keyword.", ephemeral=True)
                return
            query += " AND (title ILIKE ? OR content ILIKE ? OR COALESCE(source_title, '') ILIKE ? OR COALESCE(creator, '') ILIKE ?)"
            pattern = f"%{clean_keyword[:100]}%"
            params.extend([pattern, pattern, pattern, pattern])
        if action == "random":
            query += " ORDER BY RANDOM() LIMIT 1"
        else:
            query += " ORDER BY created_at DESC LIMIT 30"
        rows = await database.execute_db_operation("browse community archive", query, tuple(params), fetch_type="all") or []
        if not rows:
            text = "No approved entries matched that search." if action == "search" else "No approved entries yet. Submit one with action Add; moderators review contributions."
            await interaction.response.send_message(text, ephemeral=True)
            return
        view = ArchiveResultsView(self, interaction.user.id, archive_type, rows, media_type)
        await interaction.response.send_message(
            embed=view.build_embed(), view=view, ephemeral=True,
            allowed_mentions=discord.AllowedMentions.none(),
        )

    @staticmethod
    def _entry_embed(archive_type: str, row: Any) -> discord.Embed:
        item = dict(row)
        content = str(item.get("content") or "")
        if item.get("spoiler"):
            content = spoiler_wrap(content, True)
        embed = discord.Embed(title=_safe(item.get("title"), 256), description=content[:3500], color=discord.Color.blurple())
        for key, label in (("source_title", "Work / source"), ("media_type", "Media type"), ("creator", "Creator / contributor")):
            value = item.get(key)
            if value:
                embed.add_field(name=label, value=_safe(value, 900), inline=True)
        if item.get("source_url"):
            embed.add_field(name="Source", value=f"[Open source]({item['source_url']})", inline=False)
        try:
            tags = json.loads(item.get("tags") or "[]")
            if tags:
                embed.add_field(name="Tags", value=", ".join(_safe(tag, 40) for tag in tags[:10])[:1000], inline=False)
        except (TypeError, ValueError):
            pass
        embed.set_footer(text=f"{archive_type.replace('-', ' ').title()} archive · Community-submitted metadata")
        return embed

    async def _review_archive(self, interaction: discord.Interaction, action: str, entry_id: int | None) -> None:
        if not interaction.guild_id:
            await interaction.response.send_message("Archive moderation is server-scoped.", ephemeral=True)
            return
        perms = getattr(interaction.user, "guild_permissions", None)
        if not (getattr(perms, "manage_guild", False) or getattr(perms, "manage_messages", False)):
            await interaction.response.send_message("Manage Server or Manage Messages permission is required.", ephemeral=True)
            return
        if action == "list":
            rows = await database.execute_db_operation(
                "list pending archive entries in guild",
                """SELECT id, archive_type, title, created_by FROM community_archive_entries
                   WHERE created_guild_id = ? AND status = 'pending' ORDER BY created_at ASC LIMIT 20""",
                (interaction.guild_id,), fetch_type="all",
            ) or []
            lines = [f"• **#{r[0]}** · {r[1]} · {_safe(r[2], 150)} · submitter <@{r[3]}>" for r in rows]
            await interaction.response.send_message("\n".join(lines)[:3900] or "No pending submissions for this server.", ephemeral=True, allowed_mentions=discord.AllowedMentions.none())
            return
        if entry_id is None:
            await interaction.response.send_message("Provide an entry ID.", ephemeral=True)
            return
        new_status = {"approve": "approved", "reject": "rejected", "remove": "removed"}.get(action)
        if not new_status:
            await interaction.response.send_message("Unsupported review action.", ephemeral=True)
            return
        row = await database.execute_db_operation(
            "find archive entry for guild review",
            "SELECT id FROM community_archive_entries WHERE id = ? AND created_guild_id = ? AND status IN ('pending', 'approved')",
            (entry_id, interaction.guild_id), fetch_type="one",
        )
        if not row:
            await interaction.response.send_message("That entry is not pending or active in this server.", ephemeral=True)
            return
        await database.execute_db_operation(
            "update archive entry review status",
            "UPDATE community_archive_entries SET status = ? WHERE id = ? AND created_guild_id = ?",
            (new_status, entry_id, interaction.guild_id),
        )
        await interaction.response.send_message(f"Archive entry **#{entry_id}** is now **{new_status}**.", ephemeral=True)


    @app_commands.command(name="archive", description="Open the unified community media archive")
    @app_commands.guild_only()
    @command_meta(section="Community Archives", name="Community Archive")
    async def archive(self, interaction: discord.Interaction) -> None:
        embed = discord.Embed(
            title="Community Archive",
            description=(
                "Browse a shared collection of fanworks, moodboards, scenes, soundtracks, quotes, "
                "recommendations, and theories. Contributions enter moderator review in this server; "
                "approved entries become discoverable across the community.\n\n"
                "Choose an archive and action below. Search, submission, and moderation forms open in modals."
            ),
            color=discord.Color.blurple(),
        )
        embed.add_field(name="Browse", value="Explore approved entries one card at a time, with source attribution and spoiler marking.", inline=False)
        embed.add_field(name="Contribute", value="Submit credited work and source links. Archive content is metadata and links; Lemegeton does not host fan media or music.", inline=False)
        embed.set_footer(text="Review queues are server-scoped · Public entries retain their creator attribution")
        await interaction.response.send_message(embed=embed, view=ArchiveHomeView(self, interaction.user.id), ephemeral=True)

    async def quotes(self, interaction: discord.Interaction, action: str, title: str | None = None, content: str | None = None, source_title: str | None = None, creator: str | None = None, url: str | None = None, media_type: str = "Other", tags: str | None = None, spoiler: bool = False, keyword: str | None = None) -> None:
        await self._archive_action(interaction, "quotes", action, title, content, source_title, creator, url, media_type, tags, spoiler, keyword)

    async def fanworks(self, interaction: discord.Interaction, action: str, title: str | None = None, content: str | None = None, source_title: str | None = None, creator: str | None = None, url: str | None = None, media_type: str = "Other", tags: str | None = None, spoiler: bool = False, keyword: str | None = None) -> None:
        await self._archive_action(interaction, "fanworks", action, title, content, source_title, creator, url, media_type, tags, spoiler, keyword)

    async def moodboards(self, interaction: discord.Interaction, action: str, title: str | None = None, content: str | None = None, source_title: str | None = None, creator: str | None = None, url: str | None = None, media_type: str = "Other", tags: str | None = None, spoiler: bool = False, keyword: str | None = None) -> None:
        await self._archive_action(interaction, "moodboards", action, title, content, source_title, creator, url, media_type, tags, spoiler, keyword)

    async def soundtracks(self, interaction: discord.Interaction, action: str, title: str | None = None, content: str | None = None, source_title: str | None = None, creator: str | None = None, url: str | None = None, media_type: str = "Other", tags: str | None = None, spoiler: bool = False, keyword: str | None = None) -> None:
        await self._archive_action(interaction, "soundtracks", action, title, content, source_title, creator, url, media_type, tags, spoiler, keyword)

    async def scenes(self, interaction: discord.Interaction, action: str, title: str | None = None, content: str | None = None, source_title: str | None = None, creator: str | None = None, url: str | None = None, media_type: str = "Other", tags: str | None = None, spoiler: bool = False, keyword: str | None = None) -> None:
        await self._archive_action(interaction, "scenes", action, title, content, source_title, creator, url, media_type, tags, spoiler, keyword)

    async def recommendation_board(self, interaction: discord.Interaction, action: str, title: str | None = None, content: str | None = None, source_title: str | None = None, creator: str | None = None, url: str | None = None, media_type: str = "Other", tags: str | None = None, spoiler: bool = False, keyword: str | None = None) -> None:
        await self._archive_action(interaction, "recommendation-board", action, title, content, source_title, creator, url, media_type, tags, spoiler, keyword)

    async def theories(self, interaction: discord.Interaction, action: str, title: str | None = None, content: str | None = None, source_title: str | None = None, creator: str | None = None, url: str | None = None, media_type: str = "Other", tags: str | None = None, spoiler: bool = True, keyword: str | None = None) -> None:
        await self._archive_action(interaction, "theories", action, title, content, source_title, creator, url, media_type, tags, spoiler, keyword)

    async def archive_mine(self, interaction: discord.Interaction, archive_type: str = "all") -> None:
        if not interaction.guild_id:
            await interaction.response.send_message("Submissions are scoped to the server where you made them.", ephemeral=True)
            return
        query = """SELECT id, archive_type, title, status, created_at
                   FROM community_archive_entries
                   WHERE created_by = ? AND created_guild_id = ?"""
        params: list[Any] = [interaction.user.id, interaction.guild_id]
        if archive_type != "all":
            query += " AND archive_type = ?"
            params.append(archive_type)
        query += " ORDER BY created_at DESC LIMIT 20"
        rows = await database.execute_db_operation("list member archive submissions", query, tuple(params), fetch_type="all") or []
        lines = [f"• **#{row[0]}** · {_safe(row[2], 150)} · {row[1]} · **{row[3]}**" for row in rows]
        embed = discord.Embed(
            title="Your community archive submissions",
            description="\n".join(lines)[:3900] or "You have not submitted anything to this archive in this server.",
            color=discord.Color.blurple(),
        )
        embed.set_footer(text="Pending entries need moderator review in the server where they were submitted.")
        await interaction.response.send_message(embed=embed, ephemeral=True, allowed_mentions=discord.AllowedMentions.none())

    async def archive_report(self, interaction: discord.Interaction, archive_type: str, entry_id: int, reason: str) -> None:
        if not interaction.guild_id:
            await interaction.response.send_message("Reports are server-scoped.", ephemeral=True)
            return
        reason = " ".join((reason or "").split())
        if len(reason) < 10 or len(reason) > 1000:
            await interaction.response.send_message("Explain the issue in 10–1,000 characters.", ephemeral=True)
            return
        target = await database.execute_db_operation(
            "find approved community archive entry for report",
            "SELECT id FROM community_archive_entries WHERE id = ? AND archive_type = ? AND status = 'approved'",
            (entry_id, archive_type), fetch_type="one",
        )
        if not target:
            await interaction.response.send_message("That approved entry was not found in the selected archive.", ephemeral=True)
            return
        saved = await database.execute_db_operation(
            "save community archive report",
            """INSERT INTO community_archive_reports (archive_type, entry_id, guild_id, reporter_id, reason)
               VALUES (?, ?, ?, ?, ?) ON CONFLICT (guild_id, archive_type, entry_id, reporter_id) DO NOTHING
               RETURNING id""",
            (archive_type, entry_id, interaction.guild_id, interaction.user.id, reason),
            fetch_type="one",
        )
        if saved:
            message = f"Report **#{saved[0]}** was sent to this server's moderators for review."
        else:
            message = "You have already reported this entry in this server. The existing report remains in the moderator queue."
        await interaction.response.send_message(message, ephemeral=True)

    async def archive_report_review(self, interaction: discord.Interaction, decision: str = "list", report_id: int | None = None, reason: str = "") -> None:
        if not interaction.guild_id:
            await interaction.response.send_message("Reports are server-scoped.", ephemeral=True)
            return
        perms = getattr(interaction.user, "guild_permissions", None)
        if not (getattr(perms, "manage_guild", False) or getattr(perms, "manage_messages", False)):
            await interaction.response.send_message("Manage Server or Manage Messages permission is required.", ephemeral=True)
            return
        if decision == "list":
            rows = await database.execute_db_operation(
                "list pending community archive reports",
                """SELECT r.id, r.archive_type, r.entry_id, e.title, r.reason
                   FROM community_archive_reports r
                   JOIN community_archive_entries e ON e.id = r.entry_id AND e.archive_type = r.archive_type
                   WHERE r.guild_id = ? AND r.status = 'pending'
                   ORDER BY r.created_at ASC LIMIT 20""",
                (interaction.guild_id,), fetch_type="all",
            ) or []
            lines = [f"**#{r[0]}** · {r[1]} entry **#{r[2]}** · {_safe(r[3], 120)}\nReason: {_safe(r[4], 180)}" for r in rows]
            embed = discord.Embed(title="Pending archive reports", description="\n\n".join(lines)[:3900] or "No pending archive reports.", color=discord.Color.blurple())
            embed.set_footer(text="A report is a review request, not a finding that the entry is invalid.")
            await interaction.response.send_message(embed=embed, ephemeral=True, allowed_mentions=discord.AllowedMentions.none())
            return
        if report_id is None:
            await interaction.response.send_message("Provide a report ID. Use decision List to see pending reports.", ephemeral=True)
            return
        row = await database.execute_db_operation(
            "find archive report in current guild",
            """SELECT r.id, r.entry_id, r.archive_type, e.created_guild_id
               FROM community_archive_reports r
               JOIN community_archive_entries e ON e.id = r.entry_id AND e.archive_type = r.archive_type
               WHERE r.id = ? AND r.guild_id = ? AND r.status = 'pending'""",
            (report_id, interaction.guild_id), fetch_type="one",
        )
        if not row:
            await interaction.response.send_message("No pending report with that ID exists in this server.", ephemeral=True)
            return
        if decision == "remove":
            if int(row[3]) != int(interaction.guild_id):
                await interaction.response.send_message(
                    "Only moderators in the server that approved the original submission can remove it. You can mark this report reviewed or dismissed.",
                    ephemeral=True,
                )
                return
            await database.execute_db_operation(
                "remove reported archive entry in its originating guild",
                "UPDATE community_archive_entries SET status = 'removed' WHERE id = ? AND created_guild_id = ?",
                (row[1], interaction.guild_id),
            )
            new_status = "resolved"
        elif decision in {"resolved", "dismissed"}:
            new_status = decision
        else:
            await interaction.response.send_message("Choose List, Mark reviewed, Dismiss or Remove entry.", ephemeral=True)
            return
        await database.execute_db_operation(
            "update community archive report review",
            """UPDATE community_archive_reports SET status = ?, reviewed_by = ?, review_reason = ?, reviewed_at = NOW()
               WHERE id = ? AND guild_id = ? AND status = 'pending'""",
            (new_status, interaction.user.id, (reason or "")[:1000], report_id, interaction.guild_id),
        )
        await interaction.response.send_message(f"Report **#{report_id}** marked **{new_status}**.", ephemeral=True)

    async def archive_review(self, interaction: discord.Interaction, action: str, entry_id: int | None = None) -> None:
        await self._review_archive(interaction, action, entry_id)

    @app_commands.command(name="media-bracket", description="Run a database-backed community elimination poll")
    @app_commands.guild_only()
    @app_commands.choices(action=[
        app_commands.Choice(name="Start bracket", value="start"),
        app_commands.Choice(name="Vote", value="vote"),
        app_commands.Choice(name="Results", value="results"),
    ], media_type=MEDIA_TYPES)
    @app_commands.describe(action="Start, vote, or results", title="Bracket title", candidates="2–16 names separated with |", bracket_id="ID returned on creation", choice="Exact candidate name", media_type="Media category")
    @command_meta(section="Community Events", name="Media Bracket")
    async def media_bracket(self, interaction: discord.Interaction, action: str, title: str | None = None, candidates: str | None = None, bracket_id: str | None = None, choice: str | None = None, media_type: str = "Other") -> None:
        if not interaction.guild_id:
            await interaction.response.send_message("Brackets are server-specific.", ephemeral=True)
            return
        if action == "start":
            if not (title or "").strip():
                await interaction.response.send_message("Provide a bracket title.", ephemeral=True)
                return
            try:
                choices = split_candidates(candidates)
            except ValueError as exc:
                await interaction.response.send_message(str(exc), ephemeral=True)
                return
            key = secrets.token_hex(4)
            await database.execute_db_operation(
                "create community media bracket",
                "INSERT INTO community_media_brackets (bracket_id, guild_id, creator_id, title, media_type, candidates) VALUES (?, ?, ?, ?, ?, ?)",
                (key, interaction.guild_id, interaction.user.id, " ".join(title.split())[:200], media_type, json.dumps(choices)),
            )
            await interaction.response.send_message(f"Bracket **{_safe(title, 180)}** created with ID **{key}**. Voting is limited to this server.", ephemeral=False, allowed_mentions=discord.AllowedMentions.none())
            return
        if not bracket_id:
            await interaction.response.send_message("Provide a bracket ID.", ephemeral=True)
            return
        row = await database.execute_db_operation(
            "find media bracket in guild",
            "SELECT title, media_type, candidates, status FROM community_media_brackets WHERE bracket_id = ? AND guild_id = ?",
            (bracket_id.strip(), interaction.guild_id), fetch_type="one",
        )
        if not row:
            await interaction.response.send_message("No bracket with that ID exists in this server.", ephemeral=True)
            return
        bracket_title, category, raw_candidates, status = row
        choices = json.loads(raw_candidates or "[]")
        if action == "vote":
            selected = next((c for c in choices if c.casefold() == (choice or "").strip().casefold()), None)
            if not selected:
                await interaction.response.send_message("Choice must match one of the listed candidate names.", ephemeral=True)
                return
            if status != "open":
                await interaction.response.send_message("This bracket is closed.", ephemeral=True)
                return
            await database.execute_db_operation(
                "save community bracket vote",
                """INSERT INTO community_media_bracket_votes (guild_id, bracket_id, user_id, candidate) VALUES (?, ?, ?, ?)
                   ON CONFLICT (guild_id, bracket_id, user_id) DO UPDATE SET candidate = EXCLUDED.candidate, updated_at = NOW()""",
                (interaction.guild_id, bracket_id.strip(), interaction.user.id, selected),
            )
            await interaction.response.send_message(f"Vote recorded for **{selected}**. You can change it while the bracket is open.", ephemeral=True)
            return
        rows = await database.execute_db_operation(
            "count community bracket votes",
            "SELECT candidate, COUNT(*) FROM community_media_bracket_votes WHERE guild_id = ? AND bracket_id = ? GROUP BY candidate ORDER BY COUNT(*) DESC",
            (interaction.guild_id, bracket_id.strip()), fetch_type="all",
        ) or []
        totals = {str(r[0]): int(r[1]) for r in rows}
        lines = [f"• **{_safe(candidate, 150)}** — {totals.get(candidate, 0)} vote(s)" for candidate in choices]
        embed = discord.Embed(title=f"Bracket · {_safe(bracket_title, 200)}", description="\n".join(lines)[:3800], color=discord.Color.blurple())
        embed.set_footer(text=f"{category} · ID {bracket_id} · {sum(totals.values())} total vote(s)")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="adaptation-vote", description="Vote between two adaptations or versions of a work")
    @app_commands.guild_only()
    @app_commands.choices(action=[
        app_commands.Choice(name="Create poll", value="create"),
        app_commands.Choice(name="Vote", value="vote"),
        app_commands.Choice(name="Results", value="results"),
    ], media_type=MEDIA_TYPES)
    @app_commands.describe(action="Create, vote, or results", title="Poll question", option_a="First work/adaptation", option_b="Second work/adaptation", poll_id="ID returned on creation", choice="A or B", media_type="Media category", source_url="Optional HTTPS metadata link")
    @command_meta(section="Community Events", name="Adaptation Vote")
    async def adaptation_vote(self, interaction: discord.Interaction, action: str, title: str | None = None, option_a: str | None = None, option_b: str | None = None, poll_id: str | None = None, choice: str | None = None, media_type: str = "Other", source_url: str | None = None) -> None:
        if not interaction.guild_id:
            await interaction.response.send_message("Adaptation polls are server-specific.", ephemeral=True)
            return
        if action == "create":
            question, first, second = ((" ".join(v.split())) for v in (title or "", option_a or "", option_b or ""))
            if not question or not first or not second or first.casefold() == second.casefold():
                await interaction.response.send_message("Provide a poll title and two distinct options.", ephemeral=True)
                return
            try:
                url = _https_url(source_url)
            except ValueError as exc:
                await interaction.response.send_message(str(exc), ephemeral=True)
                return
            key = secrets.token_hex(4)
            await database.execute_db_operation(
                "create adaptation poll",
                "INSERT INTO community_adaptation_polls (poll_id, guild_id, creator_id, title, media_type, option_a, option_b, source_url) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (key, interaction.guild_id, interaction.user.id, question[:200], media_type, first[:200], second[:200], url),
            )
            await interaction.response.send_message(f"Poll **{_safe(question, 180)}** created. ID: **{key}** · Vote with A or B.", ephemeral=False, allowed_mentions=discord.AllowedMentions.none())
            return
        if not poll_id:
            await interaction.response.send_message("Provide a poll ID.", ephemeral=True)
            return
        row = await database.execute_db_operation(
            "find adaptation poll in guild",
            "SELECT title, media_type, option_a, option_b, source_url FROM community_adaptation_polls WHERE poll_id = ? AND guild_id = ?",
            (poll_id.strip(), interaction.guild_id), fetch_type="one",
        )
        if not row:
            await interaction.response.send_message("No poll with that ID exists in this server.", ephemeral=True)
            return
        question, category, first, second, source = row
        if action == "vote":
            selected = (choice or "").strip().upper()
            if selected not in {"A", "B"}:
                await interaction.response.send_message("Vote with A or B.", ephemeral=True)
                return
            await database.execute_db_operation(
                "save adaptation vote",
                """INSERT INTO community_adaptation_votes (guild_id, poll_id, user_id, choice) VALUES (?, ?, ?, ?)
                   ON CONFLICT (guild_id, poll_id, user_id) DO UPDATE SET choice = EXCLUDED.choice, updated_at = NOW()""",
                (interaction.guild_id, poll_id.strip(), interaction.user.id, selected),
            )
            await interaction.response.send_message(f"Vote recorded for option {selected}.", ephemeral=True)
            return
        rows = await database.execute_db_operation(
            "count adaptation votes",
            "SELECT choice, COUNT(*) FROM community_adaptation_votes WHERE guild_id = ? AND poll_id = ? GROUP BY choice",
            (interaction.guild_id, poll_id.strip()), fetch_type="all",
        ) or []
        counts = {str(r[0]): int(r[1]) for r in rows}
        embed = discord.Embed(title=f"Adaptation vote · {_safe(question, 200)}", color=discord.Color.blurple())
        embed.add_field(name="A", value=f"{_safe(first, 900)}\nVotes: {counts.get('A', 0)}", inline=True)
        embed.add_field(name="B", value=f"{_safe(second, 900)}\nVotes: {counts.get('B', 0)}", inline=True)
        if source:
            embed.add_field(name="Source", value=f"[Open metadata]({source})", inline=False)
        embed.set_footer(text=f"{category} · Community preference, not an objective score · Poll {poll_id}")
        await interaction.response.send_message(embed=embed, ephemeral=True, allowed_mentions=discord.AllowedMentions.none())

    @app_commands.command(name="media-quiz", description="Create or play source-linked community media trivia")
    @app_commands.guild_only()
    @app_commands.choices(action=[
        app_commands.Choice(name="Add question", value="add"),
        app_commands.Choice(name="Play random question", value="play"),
        app_commands.Choice(name="Submit answer", value="answer"),
    ])
    @app_commands.describe(action="Add, play or answer", question="Question text when adding", answer="Correct answer when adding / your answer when answering", source_url="Optional HTTPS source link")
    @command_meta(section="Community Events", name="Media Quiz")
    async def media_quiz(self, interaction: discord.Interaction, action: str, question: str | None = None, answer: str | None = None, source_url: str | None = None) -> None:
        if not interaction.guild_id:
            await interaction.response.send_message("Media Quiz is server-specific.", ephemeral=True)
            return
        if action == "add":
            prompt, solution = " ".join((question or "").split()), " ".join((answer or "").split())
            if not 10 <= len(prompt) <= 1000 or not solution or len(solution) > 300:
                await interaction.response.send_message("Provide a question (10–1,000 characters) and answer (1–300 characters).", ephemeral=True)
                return
            try:
                url = _https_url(source_url)
            except ValueError as exc:
                await interaction.response.send_message(str(exc), ephemeral=True)
                return
            await database.execute_db_operation(
                "add media quiz question",
                "INSERT INTO community_media_quiz_questions (guild_id, creator_id, question, answer, source_url) VALUES (?, ?, ?, ?, ?)",
                (interaction.guild_id, interaction.user.id, prompt, solution, url),
            )
            await interaction.response.send_message("Question saved to this server's quiz pool.", ephemeral=True)
            return
        if action == "play":
            row = await database.execute_db_operation(
                "choose random media quiz question",
                "SELECT id, question, source_url FROM community_media_quiz_questions WHERE guild_id = ? ORDER BY RANDOM() LIMIT 1",
                (interaction.guild_id,), fetch_type="one",
            )
            if not row:
                await interaction.response.send_message("No quiz questions have been submitted in this server.", ephemeral=True)
                return
            await database.execute_db_operation(
                "save current quiz session",
                """INSERT INTO community_media_quiz_sessions (guild_id, channel_id, user_id, question_id) VALUES (?, ?, ?, ?)
                   ON CONFLICT (guild_id, user_id) DO UPDATE SET channel_id = EXCLUDED.channel_id, question_id = EXCLUDED.question_id, created_at = NOW()""",
                (interaction.guild_id, interaction.channel_id or 0, interaction.user.id, row[0]),
            )
            embed = discord.Embed(title="Media Quiz", description=str(row[1])[:1500], color=discord.Color.blurple())
            if row[2]:
                embed.add_field(name="Source", value=f"[Check the source]({row[2]})", inline=False)
            embed.set_footer(text="Answer privately with /media-quiz action:answer")
            await interaction.response.send_message(embed=embed, ephemeral=True, allowed_mentions=discord.AllowedMentions.none())
            return
        if not answer or not answer.strip():
            await interaction.response.send_message("Provide your answer with action Answer.", ephemeral=True)
            return
        row = await database.execute_db_operation(
            "load current user's quiz session",
            """SELECT q.answer, q.source_url, s.channel_id FROM community_media_quiz_sessions s
               JOIN community_media_quiz_questions q ON q.id = s.question_id AND q.guild_id = s.guild_id
               WHERE s.guild_id = ? AND s.user_id = ?""",
            (interaction.guild_id, interaction.user.id), fetch_type="one",
        )
        if not row or int(row[2]) != int(interaction.channel_id or 0):
            await interaction.response.send_message("Start a quiz in this channel first with action Play.", ephemeral=True)
            return
        await database.execute_db_operation("clear current quiz session", "DELETE FROM community_media_quiz_sessions WHERE guild_id = ? AND user_id = ?", (interaction.guild_id, interaction.user.id))
        is_correct = " ".join(str(row[0]).casefold().split()) == " ".join(answer.casefold().split())
        message = "Correct!" if is_correct else f"Not quite. The correct answer was: **{_safe(row[0], 300)}**"
        if row[1]:
            message += f"\nSource: {row[1]}"
        await interaction.response.send_message(message, ephemeral=True, allowed_mentions=discord.AllowedMentions.none())

    @app_commands.command(name="panel-of-the-day", description="View this server's selected safe panel for today")
    @app_commands.guild_only()
    @command_meta(section="Community Archives", name="Panel of the Day")
    async def panel_of_the_day(self, interaction: discord.Interaction) -> None:
        if not interaction.guild_id:
            await interaction.response.send_message("This feature is server-specific.", ephemeral=True)
            return
        try:
            logged = await database.execute_db_operation(
                "find today's panel for guild",
                """SELECT panel_id FROM community_panel_daily_log WHERE guild_id = ? AND feature_date = CURRENT_DATE""",
                (interaction.guild_id,), fetch_type="one",
            )
            if logged:
                row = await database.execute_db_operation(
                    "load today's previously selected panel",
                    """SELECT id, title, attachment_url, caption, chapter_number, source_url, media_asset_id
                       FROM panels WHERE id = ? AND is_nsfw = FALSE AND (attachment_url IS NOT NULL OR media_asset_id IS NOT NULL)""",
                    (logged[0],), fetch_type="one",
                )
            else:
                row = await database.execute_db_operation(
                    "choose panel of the day",
                    """SELECT id, title, attachment_url, caption, chapter_number, source_url, media_asset_id
                       FROM panels p
                       WHERE is_nsfw = FALSE AND (attachment_url IS NOT NULL OR media_asset_id IS NOT NULL)
                         AND NOT EXISTS (
                           SELECT 1 FROM community_panel_daily_log d
                           WHERE d.guild_id = ? AND d.feature_date = CURRENT_DATE AND d.panel_id = p.id
                         )
                       ORDER BY RANDOM() LIMIT 1""",
                    (interaction.guild_id,), fetch_type="one",
                )
                if row:
                    inserted = await database.execute_db_operation(
                        "save today's panel selection",
                        """INSERT INTO community_panel_daily_log (guild_id, feature_date, panel_id, featured_by)
                           VALUES (?, CURRENT_DATE, ?, ?) ON CONFLICT (guild_id, feature_date) DO NOTHING
                           RETURNING panel_id""",
                        (interaction.guild_id, row[0], interaction.user.id), fetch_type="one",
                    )
                    if not inserted:
                        logged = await database.execute_db_operation(
                            "resolve concurrent panel of the day selection",
                            "SELECT panel_id FROM community_panel_daily_log WHERE guild_id = ? AND feature_date = CURRENT_DATE",
                            (interaction.guild_id,), fetch_type="one",
                        )
                        if logged:
                            row = await database.execute_db_operation(
                                "load concurrent panel of the day selection",
                                """SELECT id, title, attachment_url, caption, chapter_number, source_url, media_asset_id
                                   FROM panels WHERE id = ? AND is_nsfw = FALSE AND (attachment_url IS NOT NULL OR media_asset_id IS NOT NULL)""",
                                (logged[0],), fetch_type="one",
                            )
        except Exception:
            log.warning("Panel of the Day could not query the existing Panels archive", exc_info=True)
            await interaction.response.send_message("The existing Panels archive is unavailable right now.", ephemeral=True)
            return
        if not row:
            await interaction.response.send_message("No public-safe panels are available to feature today.", ephemeral=True)
            return
        image_url = row[2]
        if not image_url and row[6]:
            try:
                image_url = await media_storage.asset_url(int(row[6]))
            except Exception:
                log.warning("Could not sign Panel of the Day image asset %s", row[6], exc_info=True)
        embed = discord.Embed(
            title=f"Panel of the Day · {_safe(row[1], 220)}",
            description=_safe(row[3] or "No caption provided.", 1500),
            url=row[5], color=discord.Color.blurple(),
        )
        embed.add_field(name="Panel", value=f"#{row[0]}" + (f" · Chapter {row[4]}" if row[4] else ""), inline=False)
        if image_url:
            embed.set_image(url=image_url)
        else:
            embed.description = (embed.description or "") + "\n\n**Image unavailable right now.**"
        embed.set_footer(text="Today's selection is saved per server · Existing Panels archive · NSFW entries excluded")
        await interaction.response.send_message(embed=embed, allowed_mentions=discord.AllowedMentions.none())



    async def cog_app_command_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError) -> None:
        """Route unexpected database and archive failures through the shared private reporter."""
        await handle_application_command_error(interaction, error)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(CommunityArchives(bot))
