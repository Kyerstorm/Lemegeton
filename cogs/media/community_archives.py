"""Database-backed community media archives and panel-style events."""
from __future__ import annotations

import io
import json
import logging
import re
import secrets
from typing import Any
from urllib.parse import urlsplit

import discord
from discord import app_commands
from discord.ext import commands

from helpers.command_error_handler import FeedbackAwareModal, FeedbackAwareView, handle_application_command_error
import database
from helpers import media_storage
from cogs.admin.dashboard import command_meta

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


def archive_scope_filter(scope: str, guild_id: int | None) -> tuple[str, tuple[Any, ...]]:
    """Return the SQL predicate for the configured archive visibility."""
    if scope == "server" and guild_id is not None:
        return " AND created_guild_id = ?", (guild_id,)
    return "", ()


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
    ("Manga Panels", "panels", "📚"),
    ("Quotes", "quotes", "💬"),
    ("Fanworks", "fanworks", "🎨"),
    ("Moodboards", "moodboards", "🖼️"),
    ("Soundtracks", "soundtracks", "🎵"),
    ("Scenes", "scenes", "🎬"),
    ("Recommendations", "recommendation-board", "⭐"),
    ("Theories", "theories", "💡"),
]

ARCHIVE_UPLOAD_OPTIONS = [
    ("Images", "image", "🖼️", "PNG, JPEG, GIF, WebP, AVIF"),
    ("Audio", "audio", "🎵", "MP3, M4A, OGG, OPUS, WAV, FLAC, AAC"),
    ("Video", "video", "🎬", "MP4, WebM, MOV, M4V"),
]
ARCHIVE_UPLOAD_MIME_TYPES = {
    "image": {".png":"image/png", ".jpg":"image/jpeg", ".jpeg":"image/jpeg", ".gif":"image/gif", ".webp":"image/webp", ".avif":"image/avif"},
    "audio": {".mp3":"audio/mpeg", ".m4a":"audio/mp4", ".ogg":"audio/ogg", ".opus":"audio/ogg", ".wav":"audio/wav", ".flac":"audio/flac", ".aac":"audio/aac"},
    "video": {".mp4":"video/mp4", ".webm":"video/webm", ".mov":"video/quicktime", ".m4v":"video/x-m4v"},
}
ARCHIVE_CATEGORY_UPLOAD_TYPES = {
    "panels":{"image"}, "quotes":{"image"}, "fanworks":{"image","audio","video"},
    "moodboards":{"image"}, "soundtracks":{"audio","video"}, "scenes":{"image","video"},
    "recommendation-board":set(), "theories":{"image","video"},
}
ARCHIVE_MAX_UPLOAD_BYTES = 20 * 1024 * 1024
DEFAULT_ARCHIVE_CATEGORIES = tuple(value for _, value, _ in ARCHIVE_UI_TYPES)
DEFAULT_ARCHIVE_UPLOAD_TYPES: tuple[str, ...] = ("image",)


def normalize_archive_categories(values: list[str] | tuple[str, ...]) -> list[str]:
    allowed = {value for _, value, _ in ARCHIVE_UI_TYPES}
    raw = [str(value) for value in values]
    if any(value not in allowed for value in raw):
        raise ValueError("One or more archive categories are invalid.")
    selected = list(dict.fromkeys(raw))
    if not selected:
        raise ValueError("Keep at least one archive category enabled.")
    return selected


def normalize_upload_types(values: list[str] | tuple[str, ...]) -> list[str]:
    allowed = {value for _, value, _, _ in ARCHIVE_UPLOAD_OPTIONS}
    raw = [str(value) for value in values]
    if any(value not in allowed for value in raw):
        raise ValueError("One or more upload types are invalid.")
    return list(dict.fromkeys(raw))


def allowed_archive_upload_types(archive_type: str, enabled_types: list[str]) -> list[str]:
    supported = ARCHIVE_CATEGORY_UPLOAD_TYPES.get(archive_type, set())
    return [kind for kind in enabled_types if kind in supported]


def archive_upload_kind(filename: str, content_type: str | None) -> tuple[str, str]:
    extension = "." + str(filename or "").rsplit(".", 1)[-1].casefold() if "." in str(filename or "") else ""
    match = next(
        ((kind, mime) for kind, extensions in ARCHIVE_UPLOAD_MIME_TYPES.items()
         for ext, mime in extensions.items() if ext == extension),
        None,
    )
    if match is None:
        raise ValueError("That file format is not supported.")
    kind, expected_mime = match
    reported = str(content_type or "").split(";", 1)[0].strip().casefold()
    if reported not in {"", "application/octet-stream", "application/x-octet-stream", expected_mime}:
        raise ValueError("The file type does not match its filename.")
    return kind, expected_mime


async def get_archive_settings(guild_id: int | None) -> dict[str, list[str]]:
    defaults = {"enabled_categories": list(DEFAULT_ARCHIVE_CATEGORIES), "upload_types": list(DEFAULT_ARCHIVE_UPLOAD_TYPES)}
    if guild_id is None:
        return defaults
    try:
        row = await database.execute_db_operation(
            "load guild archive settings",
            "SELECT enabled_categories, upload_types FROM guild_archive_settings WHERE guild_id = ?",
            (guild_id,), fetch_type="one",
        )
        if not row:
            return defaults
        return {
            "enabled_categories": normalize_archive_categories(json.loads(row[0] or "[]")),
            "upload_types": normalize_upload_types(json.loads(row[1] or "[]")),
        }
    except (TypeError, ValueError, json.JSONDecodeError):
        log.warning("Invalid archive settings for guild %s; failing closed", guild_id, exc_info=True)
        return {"enabled_categories": [], "upload_types": []}
    except Exception:
        log.exception("Could not load archive settings for guild %s; failing closed", guild_id)
        return {"enabled_categories": [], "upload_types": []}


async def _archive_storage_channel(bot: commands.Bot, guild: discord.Guild):
    row = await database.execute_db_operation(
        "load archive fallback storage channel",
        "SELECT panel_storage_channel_id FROM guild_settings WHERE guild_id = ?",
        (guild.id,), fetch_type="one",
    )
    if not row or not row[0]:
        return None
    channel = guild.get_channel(int(row[0]))
    if channel is None:
        try:
            channel = await bot.fetch_channel(int(row[0]))
        except discord.HTTPException:
            return None
    if not isinstance(channel, discord.TextChannel):
        return None
    permissions = channel.permissions_for(guild.me) if guild.me else None
    if not permissions or not (permissions.view_channel and permissions.send_messages and permissions.attach_files):
        return None
    return channel


ARCHIVE_UI_ACTIONS = [
    ("Browse", "browse", "📖", "Open approved entries or panels."),
    ("Search", "search", "🔎", "Find a specific entry or panel."),
    ("Submit / Upload", "add", "➕", "Add a community entry or panel."),
    ("Random", "random", "🎲", "Open a random entry or panel."),
    ("My submissions / panels", "mine", "🗂️", "View your own entries."),
    ("Report entry", "report", "🚩", "Community archives only."),
    ("Review submissions", "review", "🛡️", "Community moderators only."),
    ("Review submission", "review-entry", "📝", "Community moderators only."),
    ("View reports", "reports", "📬", "Community moderators only."),
    ("Review report", "report-review", "🔍", "Community moderators only."),
    ("Configure archive", "configure", "⚙️", "Server admins: categories, uploads and storage."),
    ("Panel moderation log", "modlog", "📋", "Manga Panels only."),
]
MEDIA_TYPE_EMOJIS = {
    "Anime": "📺", "Manga": "📚", "Light novel": "📖", "Webnovel": "🌐",
    "Book": "📕", "Movie": "🎬", "TV": "📺", "Other": "✨",
}
PANEL_ARCHIVE_ACTIONS = {"browse", "search", "add", "random", "mine", "configure", "modlog"}
COMMUNITY_ARCHIVE_ACTIONS = {
    "browse", "search", "add", "random", "mine", "report", "review",
    "review-entry", "reports", "report-review",
}


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

    async def build_embed(self) -> discord.Embed:
        row = self.rows[self.index]
        embed = self.cog._entry_embed(self.archive_type, row)
        media_url = await self.cog._archive_media_url(row)
        if media_url:
            content_type = str(row.get("attachment_content_type") or "").casefold()
            filename = _safe(row.get("attachment_filename") or "Open attachment", 100)
            if content_type.startswith("image/"):
                embed.set_image(url=media_url)
            else:
                label = "Audio" if content_type.startswith("audio/") else "Video"
                embed.add_field(name=label, value=f"[{filename}]({media_url})", inline=False)
        embed.set_footer(text=f"Community archive · Entry {self.index + 1} of {len(self.rows)}")
        return embed

    async def _move(self, interaction: discord.Interaction, delta: int) -> None:
        self.index = max(0, min(len(self.rows) - 1, self.index + delta))
        self._sync_buttons()
        await interaction.response.edit_message(embed=await self.build_embed(), view=self)

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


class ArchiveActionLauncherView(FeedbackAwareView):
    """One-click handoff for actions that need a second form."""
    def __init__(
        self, cog: "CommunityArchives", owner_id: int, archive_type: str,
        media_type: str, action: str,
    ):
        super().__init__(timeout=180)
        self.cog = cog
        self.owner_id = owner_id
        self.archive_type = archive_type
        self.media_type = media_type
        self.action = action
        button = discord.ui.Button(
            label="Continue", emoji="➡️", style=discord.ButtonStyle.primary,
        )
        button.callback = self._continue
        self.add_item(button)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message(
                "Only the person who opened this archive can continue.", ephemeral=True,
            )
            return False
        return True

    async def _continue(self, interaction: discord.Interaction) -> None:
        if self.archive_type == "panels":
            panel_cog = self.cog.bot.get_cog("PanelCog")
            if panel_cog is None:
                await interaction.response.send_message(
                    "Manga Panels are temporarily unavailable.", ephemeral=True,
                )
                return
            await panel_cog.handle_archive_action(interaction, self.action)
            return

        if self.action == "search":
            await interaction.response.send_modal(ArchiveSearchModal(self.cog, self.archive_type))
        elif self.action == "add":
            await interaction.response.send_modal(
                ArchiveSubmissionModal(self.cog, self.archive_type, self.media_type),
            )
        elif self.action == "report":
            await interaction.response.send_modal(ArchiveReportModal(self.cog, self.archive_type))
        elif self.action == "review-entry":
            await interaction.response.send_modal(ArchiveReviewModal(self.cog, self.archive_type))
        elif self.action == "report-review":
            await interaction.response.send_modal(ArchiveReportReviewModal(self.cog))
        else:
            await interaction.response.send_message(
                "That archive action is no longer available.", ephemeral=True,
            )


class ArchiveSettingsModal(FeedbackAwareModal):
    def __init__(self, cog: "CommunityArchives", owner_id: int, guild_id: int, settings: dict[str, list[str]]):
        super().__init__(title="Archive Categories & Uploads", timeout=180)
        self.cog, self.owner_id, self.guild_id = cog, owner_id, guild_id
        self.categories = discord.ui.Label(
            text="🗂️ Visible categories",
            component=discord.ui.Select(
                placeholder="Choose categories members can use",
                min_values=1, max_values=len(ARCHIVE_UI_TYPES),
                options=[
                    discord.SelectOption(label=label, value=value, emoji=emoji,
                                         default=value in settings["enabled_categories"])
                    for label, value, emoji in ARCHIVE_UI_TYPES
                ],
            ),
        )
        self.uploads = discord.ui.Label(
            text="📎 Accepted uploads",
            description="Optional · 20 MiB per file · Storage must be configured",
            component=discord.ui.Select(
                placeholder="Choose accepted file types",
                min_values=0, max_values=len(ARCHIVE_UPLOAD_OPTIONS), required=False,
                options=[
                    discord.SelectOption(label=label, value=value, emoji=emoji,
                                         description=description, default=value in settings["upload_types"])
                    for label, value, emoji, description in ARCHIVE_UPLOAD_OPTIONS
                ],
            ),
        )
        self.add_item(self.categories)
        self.add_item(self.uploads)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        if (interaction.guild_id != self.guild_id or interaction.user.id != self.owner_id
                or not interaction.permissions.manage_guild):
            await interaction.response.send_message("Manage Server permission is required.", ephemeral=True)
            return
        try:
            categories = normalize_archive_categories(self.categories.component.values)
            uploads = normalize_upload_types(self.uploads.component.values)
            if uploads and not media_storage.is_configured(private=True):
                if interaction.guild is None or await _archive_storage_channel(self.cog.bot, interaction.guild) is None:
                    raise ValueError(
                        "Configure private S3 storage or a private storage channel before enabling uploads."
                    )
            await database.execute_db_operation(
                "save guild archive settings",
                """INSERT INTO guild_archive_settings(guild_id, enabled_categories, upload_types, updated_by)
                   VALUES (?, ?, ?, ?)
                   ON CONFLICT (guild_id) DO UPDATE SET
                   enabled_categories=EXCLUDED.enabled_categories,
                   upload_types=EXCLUDED.upload_types,
                   updated_by=EXCLUDED.updated_by, updated_at=NOW()""",
                (self.guild_id, json.dumps(categories), json.dumps(uploads), interaction.user.id),
            )
            summary = ", ".join(kind.title() for kind in uploads) if uploads else "uploads off"
            await interaction.response.send_message(
                f"Saved · {len(categories)} categories · {summary}.", ephemeral=True,
            )
        except ValueError as exc:
            await interaction.response.send_message(str(exc), ephemeral=True)
        except Exception:
            log.exception("Could not save archive settings for guild %s", self.guild_id)
            await interaction.response.send_message("Archive settings could not be saved. Try again later.", ephemeral=True)


class ArchiveSettingsView(FeedbackAwareView):
    def __init__(self, cog: "CommunityArchives", owner_id: int, guild_id: int):
        super().__init__(timeout=180)
        self.cog, self.owner_id, self.guild_id = cog, owner_id, guild_id
        categories = discord.ui.Button(label="Categories & uploads", emoji="🗂️", style=discord.ButtonStyle.primary)
        storage = discord.ui.Button(label="Storage & moderation", emoji="🛠️", style=discord.ButtonStyle.secondary)
        categories.callback = self._categories
        storage.callback = self._storage
        self.add_item(categories)
        self.add_item(storage)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message("Only the person who opened these settings can use them.", ephemeral=True)
            return False
        if interaction.guild_id != self.guild_id or not interaction.permissions.manage_guild:
            await interaction.response.send_message("Manage Server permission is required.", ephemeral=True)
            return False
        return True

    async def _categories(self, interaction: discord.Interaction) -> None:
        settings = await get_archive_settings(self.guild_id)
        await interaction.response.send_modal(ArchiveSettingsModal(self.cog, self.owner_id, self.guild_id, settings))

    async def _storage(self, interaction: discord.Interaction) -> None:
        panel_cog = self.cog.bot.get_cog("PanelCog")
        if panel_cog is None:
            await interaction.response.send_message("Archive storage settings are temporarily unavailable.", ephemeral=True)
            return
        await panel_cog.handle_archive_action(interaction, "configure")


class ArchiveAttachmentPromptView(FeedbackAwareView):
    def __init__(self, cog: "CommunityArchives", owner_id: int, guild_id: int,
                 archive_type: str, entry_id: int, upload_types: list[str]):
        super().__init__(timeout=900)
        self.cog, self.owner_id, self.guild_id = cog, owner_id, guild_id
        self.archive_type, self.entry_id, self.upload_types = archive_type, entry_id, upload_types
        attach = discord.ui.Button(label="Attach media", emoji="📎", style=discord.ButtonStyle.primary)
        attach.callback = self._attach
        self.add_item(attach)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.owner_id or interaction.guild_id != self.guild_id:
            await interaction.response.send_message("This upload belongs to another submission.", ephemeral=True)
            return False
        return True

    async def _attach(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_modal(ArchiveAttachmentModal(
            self.cog, self.owner_id, self.guild_id, self.archive_type, self.entry_id, self.upload_types,
        ))


class ArchiveAttachmentModal(FeedbackAwareModal):
    def __init__(self, cog: "CommunityArchives", owner_id: int, guild_id: int,
                 archive_type: str, entry_id: int, upload_types: list[str]):
        super().__init__(title="Attach Archive Media", timeout=180)
        self.cog, self.owner_id, self.guild_id = cog, owner_id, guild_id
        self.archive_type, self.entry_id, self.upload_types = archive_type, entry_id, upload_types
        self.upload = discord.ui.Label(
            text="📎 File",
            description="Allowed formats only · 20 MiB maximum",
            component=discord.ui.FileUpload(min_values=1, max_values=1, required=True),
        )
        self.rights = discord.ui.Label(
            text="📄 Sharing rights",
            description="Only upload media you own or are licensed to share.",
            component=discord.ui.TextInput(
                label="Type I own it or I have permission",
                max_length=32,
                required=True,
                placeholder="I own it",
            ),
        )
        self.add_item(self.upload)
        self.add_item(self.rights)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True, thinking=True)
        stored_asset = None
        stored_message = None
        asset_committed = False
        try:
            if (interaction.user.id != self.owner_id or interaction.guild_id != self.guild_id
                    or interaction.guild is None):
                raise ValueError("This upload belongs to another server or member.")
            settings = await get_archive_settings(self.guild_id)
            if self.archive_type not in settings["enabled_categories"]:
                raise ValueError("This archive category has been disabled by a server admin.")
            allowed = set(allowed_archive_upload_types(self.archive_type, settings["upload_types"]))
            selected = next(iter(self.upload.component.values or []), None)
            if selected is None:
                raise ValueError("Choose one file to attach.")
            rights = self.rights.component.value.strip().casefold()
            if rights not in {"i own it", "i have permission"}:
                raise ValueError("Only upload media you own or are licensed to share.")
            filename = str(getattr(selected, "filename", "archive-upload"))
            kind, mime = archive_upload_kind(filename, getattr(selected, "content_type", None))
            if kind not in allowed or kind not in self.upload_types:
                raise ValueError(f"This server does not accept {kind} uploads for this archive.")
            max_bytes = ARCHIVE_MAX_UPLOAD_BYTES
            for value in (getattr(interaction, "filesize_limit", None),
                          getattr(interaction.guild, "filesize_limit", None)):
                try:
                    limit = int(value)
                    if limit > 0:
                        max_bytes = min(max_bytes, limit)
                except (TypeError, ValueError):
                    pass
            reported = int(getattr(selected, "size", 0) or 0)
            if reported > max_bytes:
                raise ValueError(f"Files are limited to {max_bytes // (1024 * 1024)} MiB here.")
            data = await selected.read()
            if not data or len(data) > max_bytes:
                raise ValueError(f"Files must be non-empty and no larger than {max_bytes // (1024 * 1024)} MiB.")
            safe_filename = re.sub(
                r"[^A-Za-z0-9._ -]", "_", filename.replace("/", "_").replace("\\", "_"),
            )[:120].strip(". ") or "archive-upload"

            if media_storage.is_configured(private=True):
                stored_asset = await media_storage.store_media(
                    data, namespace=f"community-archives/{self.archive_type}",
                    filename=safe_filename, content_type=mime, private=True,
                )
                if stored_asset is None:
                    raise RuntimeError("Private media storage is not available.")
                pool = getattr(database, "_pool", None)
                if pool is None or getattr(pool, "_closed", False):
                    pool = await database.init_db_pool()
                async with pool.acquire() as conn:
                    async with conn.transaction():
                        asset_id = await media_storage.register_asset(
                            conn, stored_asset, namespace=f"community-archives/{self.archive_type}",
                            uploaded_by=interaction.user.id, guild_id=self.guild_id,
                        )
                        saved = await conn.fetchrow(
                            """UPDATE community_archive_entries
                               SET media_asset_id=$1, attachment_filename=$2, attachment_content_type=$3,
                                   status='pending'
                               WHERE id=$4 AND archive_type=$5 AND created_by=$6 AND created_guild_id=$7
                                 AND status IN ('pending', 'pending_upload')
                                 AND media_asset_id IS NULL AND storage_message_id IS NULL
                               RETURNING id""",
                            asset_id, safe_filename, mime, self.entry_id, self.archive_type,
                            interaction.user.id, self.guild_id,
                        )
                        if not saved:
                            raise ValueError("This submission is no longer available for an upload.")
                asset_committed = True
            else:
                storage = await _archive_storage_channel(self.cog.bot, interaction.guild)
                if storage is None:
                    raise ValueError("Configure private S3 storage or a private archive storage channel first.")
                storage_limit = int(getattr(storage.guild, "filesize_limit", max_bytes) or max_bytes)
                if len(data) > min(max_bytes, storage_limit):
                    raise ValueError("This file exceeds the archive storage channel's upload limit.")
                stored_message = await storage.send(
                    file=discord.File(io.BytesIO(data), filename=safe_filename),
                    allowed_mentions=discord.AllowedMentions.none(),
                )
                if not stored_message.attachments:
                    raise RuntimeError("The storage channel did not retain the uploaded file.")
                saved = await database.execute_db_operation(
                    "attach media to community archive entry",
                    """UPDATE community_archive_entries
                       SET attachment_url=?, attachment_filename=?, attachment_content_type=?,
                           storage_message_id=?, storage_channel_id=?, status='pending'
                       WHERE id=? AND archive_type=? AND created_by=? AND created_guild_id=?
                         AND status IN ('pending', 'pending_upload')
                         AND media_asset_id IS NULL AND storage_message_id IS NULL
                       RETURNING id""",
                    (stored_message.attachments[0].url, safe_filename, mime, stored_message.id, storage.id,
                     self.entry_id, self.archive_type, interaction.user.id, self.guild_id),
                    fetch_type="one",
                )
                if not saved:
                    raise ValueError("This submission is no longer available for an upload.")

            await interaction.followup.send(
                f"Media attached to submission **#{self.entry_id}**. It remains pending moderator approval.",
                ephemeral=True,
            )
        except ValueError as exc:
            if stored_message:
                try:
                    await stored_message.delete()
                except discord.HTTPException:
                    log.warning("Could not clean up rejected archive upload", exc_info=True)
            if stored_asset and not asset_committed:
                try:
                    await media_storage.delete_uploaded_object(stored_asset)
                except Exception:
                    log.warning("Could not clean up uncommitted archive media", exc_info=True)
            await interaction.followup.send(str(exc), ephemeral=True)
        except Exception:
            log.exception("Community archive media upload failed")
            if stored_message:
                try:
                    await stored_message.delete()
                except discord.HTTPException:
                    log.warning("Could not clean up failed archive upload", exc_info=True)
            if stored_asset and not asset_committed:
                try:
                    await media_storage.delete_uploaded_object(stored_asset)
                except Exception:
                    log.warning("Could not clean up failed archive media asset", exc_info=True)
            await interaction.followup.send(
                "The file could not be stored. Check archive storage configuration and try again.",
                ephemeral=True,
            )


class ArchiveSelectionModal(FeedbackAwareModal):
    """Compact entry point filtered to categories enabled in this server."""
    def __init__(
        self, cog: "CommunityArchives", enabled_categories: list[str] | None = None,
        allow_configure: bool = True,
    ):
        super().__init__(title="🗃️ Archive", timeout=180)
        self.cog = cog
        self.allow_configure = allow_configure
        enabled = set(DEFAULT_ARCHIVE_CATEGORIES if enabled_categories is None else enabled_categories)
        self.archive = discord.ui.Label(
            text="🗂️ Archive",
            component=discord.ui.Select(
                placeholder="Choose an archive",
                min_values=1,
                max_values=1,
                options=[
                    discord.SelectOption(label=label, value=value, emoji=emoji)
                    for label, value, emoji in ARCHIVE_UI_TYPES if value in enabled
                ],
            ),
        )
        self.media = discord.ui.Label(
            text="🎞️ Related media",
            component=discord.ui.Select(
                placeholder="Choose a media type",
                min_values=1,
                max_values=1,
                options=[
                    discord.SelectOption(
                        label=choice.name,
                        value=choice.value,
                        emoji=MEDIA_TYPE_EMOJIS.get(choice.value),
                        default=choice.value == "Other",
                    )
                    for choice in MEDIA_TYPES
                ],
            ),
        )
        self.action = discord.ui.Label(
            text="⚡ Action",
            component=discord.ui.Select(
                placeholder="Choose an action",
                min_values=1,
                max_values=1,
                options=[
                    discord.SelectOption(
                        label=label, value=value, emoji=emoji, description=description,
                        default=value == "browse",
                    )
                    for label, value, emoji, description in ARCHIVE_UI_ACTIONS
                    if allow_configure or value != "configure"
                ],
            ),
        )
        for item in (self.archive, self.media, self.action):
            self.add_item(item)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        await self.cog.dispatch_archive_action(
            interaction,
            self.archive.component.values[0],
            self.media.component.values[0],
            self.action.component.values[0],
        )


class CommunityArchives(commands.Cog):
    """Global public entries, guild-local moderation, and guild-local polls."""
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def cog_load(self) -> None:
        await media_storage.ensure_schema()
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
                media_asset_id BIGINT REFERENCES media_assets(id) ON DELETE SET NULL,
                attachment_filename TEXT,
                attachment_content_type VARCHAR(128),
                attachment_url TEXT,
                storage_message_id BIGINT,
                storage_channel_id BIGINT,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )"""),
            ("extend existing archive entries for media", """ALTER TABLE community_archive_entries
                ADD COLUMN IF NOT EXISTS media_asset_id BIGINT REFERENCES media_assets(id) ON DELETE SET NULL,
                ADD COLUMN IF NOT EXISTS attachment_filename TEXT,
                ADD COLUMN IF NOT EXISTS attachment_content_type VARCHAR(128),
                ADD COLUMN IF NOT EXISTS attachment_url TEXT,
                ADD COLUMN IF NOT EXISTS storage_message_id BIGINT,
                ADD COLUMN IF NOT EXISTS storage_channel_id BIGINT"""),
            ("create guild archive settings", """CREATE TABLE IF NOT EXISTS guild_archive_settings (
                guild_id BIGINT PRIMARY KEY,
                enabled_categories TEXT NOT NULL DEFAULT '["panels","quotes","fanworks","moodboards","soundtracks","scenes","recommendation-board","theories"]',
                upload_types TEXT NOT NULL DEFAULT '["image"]',
                updated_by BIGINT,
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
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
        settings = await get_archive_settings(interaction.guild_id)
        if archive_type not in settings["enabled_categories"]:
            await interaction.response.send_message(
                "That archive category is disabled in this server.", ephemeral=True,
            )
            return
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
            try:
                clean_url = _https_url(url, required=archive_type == "fanworks")
                tags = normalize_tags(tags_raw)
            except ValueError as exc:
                await interaction.response.send_message(str(exc), ephemeral=True)
                return
            needs_soundtrack_file = archive_type == "soundtracks" and not clean_url
            if needs_soundtrack_file and not ({"audio", "video"} & set(allowed_archive_upload_types(archive_type, settings["upload_types"]))):
                await interaction.response.send_message(
                    "Add a legitimate music/video link, or ask an admin to enable audio/video uploads.",
                    ephemeral=True,
                )
                return
            row = await database.execute_db_operation(
                "save community archive submission",
                """INSERT INTO community_archive_entries
                   (archive_type, title, content, source_title, creator, media_type, source_url, tags,
                    spoiler, status, created_by, created_guild_id)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) RETURNING id""",
                (archive_type, clean_title, clean_content, clean_source, clean_creator, media_type, clean_url,
                 json.dumps(tags), bool(spoiler), "pending_upload" if needs_soundtrack_file else "pending",
                 interaction.user.id, interaction.guild_id),
                fetch_type="one",
            )
            entry_id = row[0] if row else "unknown"
            allowed_uploads = allowed_archive_upload_types(archive_type, settings["upload_types"])
            upload_view = (
                ArchiveAttachmentPromptView(
                    self, interaction.user.id, interaction.guild_id,
                    archive_type, int(entry_id), allowed_uploads,
                )
                if allowed_uploads and row else None
            )
            message = (
                f"Submission **#{entry_id}** needs an attachment before moderator review."
                if needs_soundtrack_file else
                f"Submission **#{entry_id}** is saved for moderator review."
            )
            await interaction.response.send_message(message, view=upload_view, ephemeral=True)
            return

        clean_keyword = " ".join((keyword or title or "").split())
        query = """SELECT id, title, content, source_title, creator, media_type, source_url, tags, spoiler, created_at,
                          media_asset_id, attachment_filename, attachment_content_type, attachment_url,
                          storage_message_id, storage_channel_id
                   FROM community_archive_entries WHERE archive_type = ? AND status = 'approved'"""
        params: list[Any] = [archive_type]
        if interaction.guild_id is not None:
            try:
                scope_row = await database.execute_db_operation(
                    "load community archive visibility",
                    "SELECT archive_scope FROM guild_settings WHERE guild_id = ?",
                    (interaction.guild_id,),
                    fetch_type="one",
                )
                archive_scope = str(scope_row[0] or "global").casefold() if scope_row else "global"
            except Exception:
                log.warning("Could not load archive visibility for guild %s; using global visibility", interaction.guild_id, exc_info=True)
                archive_scope = "global"
            scope_sql, scope_params = archive_scope_filter(archive_scope, interaction.guild_id)
            query += scope_sql
            params.extend(scope_params)
        if action == "search":
            if not clean_keyword:
                await interaction.response.send_message("Provide a search keyword.", ephemeral=True)
                return
            query += """ AND (title ILIKE ? OR content ILIKE ? OR COALESCE(source_title, '') ILIKE ?
                          OR COALESCE(creator, '') ILIKE ? OR COALESCE(attachment_filename, '') ILIKE ?)"""
            pattern = f"%{clean_keyword[:100]}%"
            params.extend([pattern, pattern, pattern, pattern, pattern])
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
            embed=await view.build_embed(), view=view, ephemeral=True,
            allowed_mentions=discord.AllowedMentions.none(),
        )

    async def _archive_media_url(self, row: dict[str, Any]) -> str | None:
        if row.get("media_asset_id"):
            try:
                return await media_storage.asset_url(int(row["media_asset_id"]))
            except Exception:
                log.warning("Could not sign archive media asset %s", row["media_asset_id"], exc_info=True)
                return None
        if row.get("storage_message_id") and row.get("storage_channel_id"):
            try:
                channel = self.bot.get_channel(int(row["storage_channel_id"]))
                if channel is None:
                    channel = await self.bot.fetch_channel(int(row["storage_channel_id"]))
                message = await channel.fetch_message(int(row["storage_message_id"]))
                return message.attachments[0].url if message.attachments else None
            except (discord.HTTPException, AttributeError):
                log.warning("Could not resolve archive media message %s", row["storage_message_id"], exc_info=True)
                return None
        return row.get("attachment_url")

    async def _is_archive_moderator(self, interaction: discord.Interaction) -> bool:
        if interaction.guild_id is None:
            return False
        permissions = getattr(interaction.user, "guild_permissions", None)
        if getattr(permissions, "manage_guild", False) or getattr(permissions, "manage_messages", False):
            return True
        try:
            row = await database.execute_db_operation(
                "load archive moderator role",
                "SELECT panel_mod_role_id FROM guild_settings WHERE guild_id = ?",
                (interaction.guild_id,), fetch_type="one",
            )
            role_id = int(row[0]) if row and row[0] else None
            return bool(role_id and isinstance(interaction.user, discord.Member)
                        and any(role.id == role_id for role in interaction.user.roles))
        except Exception:
            log.exception("Could not resolve archive moderator role for guild %s", interaction.guild_id)
            return False

    async def _log_archive_moderation(
        self, interaction: discord.Interaction, archive_type: str,
        entry_id: int, action: str, note: str = "",
    ) -> None:
        if interaction.guild is None:
            return
        try:
            row = await database.execute_db_operation(
                "load shared archive moderation log channel",
                "SELECT panel_log_channel_id FROM guild_settings WHERE guild_id = ?",
                (interaction.guild_id,), fetch_type="one",
            )
            if not row or not row[0]:
                return
            channel = interaction.guild.get_channel(int(row[0]))
            if channel is None:
                channel = await self.bot.fetch_channel(int(row[0]))
            if not isinstance(channel, discord.TextChannel):
                return
            embed = discord.Embed(
                title="🛡️ Archive moderation",
                description=f"**{_safe(archive_type, 80)}** entry **#{entry_id}** · **{_safe(action, 40)}**",
                color=discord.Color.blurple(),
            )
            embed.add_field(name="Moderator", value=f"<@{interaction.user.id}>", inline=True)
            if note:
                embed.add_field(name="Note", value=_safe(note, 900), inline=False)
            await channel.send(embed=embed, allowed_mentions=discord.AllowedMentions.none())
        except Exception:
            log.warning("Could not write archive moderation log for entry %s", entry_id, exc_info=True)

    async def _delete_archive_attachment(self, row: dict[str, Any]) -> None:
        try:
            if row.get("media_asset_id"):
                await media_storage.delete_asset(int(row["media_asset_id"]))
            elif row.get("storage_message_id") and row.get("storage_channel_id"):
                channel = self.bot.get_channel(int(row["storage_channel_id"]))
                if channel is None:
                    channel = await self.bot.fetch_channel(int(row["storage_channel_id"]))
                message = await channel.fetch_message(int(row["storage_message_id"]))
                await message.delete()
            await database.execute_db_operation(
                "clear removed archive attachment metadata",
                """UPDATE community_archive_entries
                   SET media_asset_id=NULL, attachment_filename=NULL, attachment_content_type=NULL,
                       attachment_url=NULL, storage_message_id=NULL, storage_channel_id=NULL
                   WHERE id=?""",
                (row["id"],),
            )
        except Exception:
            log.warning("Could not delete archive media for entry %s", row.get("id"), exc_info=True)

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
        if not await self._is_archive_moderator(interaction):
            await interaction.response.send_message("Archive moderator permissions are required.", ephemeral=True)
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
            "SELECT id, archive_type, media_asset_id, storage_message_id, storage_channel_id FROM community_archive_entries WHERE id = ? AND created_guild_id = ? AND status IN ('pending', 'approved')",
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
        if new_status in {"rejected", "removed"} and any(row[index] for index in (2, 3, 4)):
            await self._delete_archive_attachment({
                "id": entry_id, "media_asset_id": row[2],
                "storage_message_id": row[3], "storage_channel_id": row[4],
            })
        await self._log_archive_moderation(interaction, str(row[1]), entry_id, new_status)
        await interaction.response.send_message(f"Archive entry **#{entry_id}** is now **{new_status}**.", ephemeral=True)


    async def dispatch_archive_action(
        self, interaction: discord.Interaction, archive_type: str, media_type: str, action: str,
    ) -> None:
        if action == "configure":
            if not interaction.guild_id or not interaction.permissions.manage_guild:
                await interaction.response.send_message("Manage Server permission is required.", ephemeral=True)
                return
            embed = discord.Embed(
                title="🗃️ Archive settings",
                description="Manage visible categories, accepted uploads, storage and moderation.",
                color=discord.Color.blurple(),
            )
            await interaction.response.send_message(
                embed=embed,
                view=ArchiveSettingsView(self, interaction.user.id, interaction.guild_id),
                ephemeral=True,
            )
            return

        settings = await get_archive_settings(interaction.guild_id)
        if archive_type not in settings["enabled_categories"]:
            await interaction.response.send_message("That archive category is disabled in this server.", ephemeral=True)
            return
        if archive_type == "panels":
            panel_cog = self.bot.get_cog("PanelCog")
            if panel_cog is None:
                await interaction.response.send_message("Manga Panels are temporarily unavailable.", ephemeral=True)
                return
            if action not in PANEL_ARCHIVE_ACTIONS:
                await interaction.response.send_message("That action is not available for Manga Panels.", ephemeral=True)
                return
            if action == "search":
                await interaction.response.send_message(
                    "Continue to open the selected form.",
                    view=ArchiveActionLauncherView(self, interaction.user.id, archive_type, media_type, action),
                    ephemeral=True,
                )
                return
            await panel_cog.handle_archive_action(interaction, action)
            return
        if action not in COMMUNITY_ARCHIVE_ACTIONS:
            await interaction.response.send_message("That action is not available for this archive.", ephemeral=True)
            return
        if action in {"search", "add", "report", "review-entry", "report-review"}:
            await interaction.response.send_message(
                "Continue to enter the details.",
                view=ArchiveActionLauncherView(self, interaction.user.id, archive_type, media_type, action),
                ephemeral=True,
            )
        elif action in {"browse", "random"}:
            await self._archive_action(
                interaction, archive_type, action, None, None, None, None, None,
                media_type, None, archive_type == "theories", None,
            )
        elif action == "mine":
            await self.archive_mine(interaction, archive_type)
        elif action == "review":
            await self._review_archive(interaction, "list", None)
        elif action == "reports":
            await self.archive_report_review(interaction, "list", None, "")

    @app_commands.command(name="archive", description="Open the server-configurable community archive")
    @app_commands.guild_only()
    @command_meta(section="Community Archives & Events", name="Archive")
    async def archive(self, interaction: discord.Interaction) -> None:
        settings = await get_archive_settings(interaction.guild_id)
        if not settings["enabled_categories"]:
            if interaction.permissions.manage_guild:
                await interaction.response.send_message(
                    "Archive settings need attention.",
                    view=ArchiveSettingsView(self, interaction.user.id, interaction.guild_id),
                    ephemeral=True,
                )
            else:
                await interaction.response.send_message("Archive settings are temporarily unavailable.", ephemeral=True)
            return
        await interaction.response.send_modal(
            ArchiveSelectionModal(
                self,
                enabled_categories=settings["enabled_categories"],
                allow_configure=bool(interaction.permissions.manage_guild),
            )
        )

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
        if not await self._is_archive_moderator(interaction):
            await interaction.response.send_message("Archive moderator permissions are required.", ephemeral=True)
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
            """SELECT r.id, r.entry_id, r.archive_type, e.created_guild_id,
                      e.media_asset_id, e.storage_message_id, e.storage_channel_id
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
            if any(row[index] for index in (4, 5, 6)):
                await self._delete_archive_attachment({
                    "id": row[1], "media_asset_id": row[4],
                    "storage_message_id": row[5], "storage_channel_id": row[6],
                })
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
        await self._log_archive_moderation(
            interaction, str(row[2]), int(row[1]),
            "removed" if decision == "remove" else new_status, reason,
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
        archive_settings = await get_archive_settings(interaction.guild_id)
        if "panels" not in archive_settings["enabled_categories"]:
            await interaction.response.send_message("Manga Panels are disabled in this server.", ephemeral=True)
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
