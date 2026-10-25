"""Shared Manga Panel Archive for Lemegeton.

Panel records and tags are global across all guilds. Only archive settings and
moderation audit records are guild-scoped. Uses database.py's asyncpg pool.
"""
from __future__ import annotations

import asyncio
import io
import logging
import re
import secrets
from typing import Any
from urllib.parse import urlsplit

import aiohttp
import discord
from helpers.command_error_handler import FeedbackAwareModal, FeedbackAwareView, application_error_message
from discord import app_commands
from discord.ext import commands

import database
from cogs_test.general_commands.dashboard import command_meta
from helpers.anilist_helper import fetch_media_by_id
from helpers.color_palette import PALETTE
from helpers.crypto_random import secure_choice

log = logging.getLogger("Lemegeton.Panels")
# Fallback only; use Discord's effective interaction/storage limits when available.
MAX_IMAGE_BYTES = 20 * 1024 * 1024
IMAGE_TYPES = {"image/png", "image/jpeg", "image/gif", "image/webp", "image/avif"}
# Discord string selects allow at most 25 options each. Two documented selects provide
# a useful tag vocabulary without making the upload form unwieldy.
PANEL_TAGS = (
    "action", "adventure", "comedy", "drama", "fantasy",
    "horror", "mystery", "psychological", "romance", "sci-fi",
    "slice of life", "supernatural", "thriller", "tragedy", "isekai",
    "martial arts", "school life", "historical", "shounen", "shoujo",
    "seinen", "josei", "manhwa", "manhua", "manhua-style",
)
PANEL_VISUAL_TAGS = (
    "double spread", "splash page", "panel sequence", "iconic moment", "character close-up",
    "fight scene", "comedy panel", "emotional scene", "flashback", "worldbuilding",
    "monster / creature", "weapons", "magic", "cyberpunk", "post-apocalyptic",
    "folklore", "mythology", "politics", "survival", "revenge",
    "cultivation", "time travel", "reincarnation", "fan service", "mature",
)
PANEL_TAG_DESCRIPTIONS = {
    "action": "Fast-paced movement, combat, or physical conflict.",
    "adventure": "Journeys, quests, exploration, or discovery.",
    "comedy": "Humorous scenes, jokes, or visual gags.",
    "drama": "Character-focused conflict or serious emotional stakes.",
    "fantasy": "Magic, mythical worlds, or supernatural fantasy settings.",
    "horror": "Fear, dread, disturbing imagery, or horror themes.",
    "mystery": "Clues, secrets, investigations, or unanswered questions.",
    "psychological": "Mind games, inner conflict, or psychological tension.",
    "romance": "Romantic relationships or affectionate moments.",
    "sci-fi": "Science fiction, advanced technology, or space themes.",
    "slice of life": "Everyday activities and ordinary life moments.",
    "supernatural": "Ghosts, spirits, curses, or paranormal events.",
    "thriller": "Suspense, danger, urgency, or high tension.",
    "tragedy": "Loss, grief, suffering, or tragic developments.",
    "isekai": "Transported, reincarnated, or trapped in another world.",
    "martial arts": "Martial arts technique, tournaments, or hand-to-hand combat.",
    "school life": "School, academy, classroom, or campus settings.",
    "historical": "Historical eras, period clothing, or past civilizations.",
    "shounen": "Shounen demographic or action-adventure storytelling.",
    "shoujo": "Shoujo demographic or relationship-focused storytelling.",
    "seinen": "Seinen demographic or mature-targeted storytelling.",
    "josei": "Josei demographic or adult relationship-focused storytelling.",
    "manhwa": "Korean comics or manhwa-specific visual conventions.",
    "manhua": "Chinese comics or manhua-specific visual conventions.",
    "manhua-style": "Art inspired by Chinese comic styling.",
    "double spread": "Artwork spanning two facing pages.",
    "splash page": "A single large panel or full-page illustration.",
    "panel sequence": "A sequence of panels meant to be read together.",
    "iconic moment": "A memorable or especially recognizable scene.",
    "character close-up": "A close portrait or detailed character expression.",
    "fight scene": "Combat, duels, battles, or action choreography.",
    "comedy panel": "A standalone humorous panel or gag.",
    "emotional scene": "A scene focused on a strong emotional reaction.",
    "flashback": "A memory, flashback, or past-event scene.",
    "worldbuilding": "World details, maps, lore, architecture, or setting reveals.",
    "monster / creature": "Monsters, beasts, fantasy creatures, or unusual beings.",
    "weapons": "Weapons, equipment, or weapon-focused artwork.",
    "magic": "Spells, magical effects, rituals, or supernatural powers.",
    "cyberpunk": "Neon-lit urban futures, cybernetics, or dystopian technology.",
    "post-apocalyptic": "Ruined worlds, collapse, or post-disaster settings.",
    "folklore": "Folk tales, legends, and regional traditional motifs.",
    "mythology": "Gods, myths, divine beings, or myth-inspired imagery.",
    "politics": "Royal courts, factions, diplomacy, or political conflict.",
    "survival": "Endurance, harsh environments, or survival situations.",
    "revenge": "Retribution, vengeance, or revenge-driven scenes.",
    "cultivation": "Cultivation, martial progression, or xianxia/xuanhuan themes.",
    "time travel": "Time loops, timelines, time jumps, or temporal travel.",
    "reincarnation": "Rebirth, reincarnation, or a second-life premise.",
    "fan service": "Fan-service imagery or suggestive presentation; use the mature tag when age-restricted.",
    "mature": "Age-restricted content. The panel stays hidden in non-NSFW channels.",
}
CHAPTER_CAPTION_RE = re.compile(
    r"^\s*(?:(?:chapter|ch\.?)\s*)?#?(\d+(?:\.\d+)?|N/A)"
    r"(?:\s*(?:[-–—:|]\s*|\s+)(.*?))?\s*$",
    re.IGNORECASE,
)
BROWSER_TIMEOUT = 1800
DEFAULT_STORAGE_CHANNEL_ID = None  # Optional deployment-wide fallback.


async def _pool():
    """Return the existing pool from database.py; never create a second pool."""
    pool = getattr(database, "_pool", None)
    if pool is None:
        for name in ("get_pool", "init_pool", "initialize_pool", "init_db"):
            fn = getattr(database, name, None)
            if fn:
                result = fn()
                if asyncio.iscoroutine(result):
                    await result
                pool = getattr(database, "_pool", None)
                if pool is not None:
                    break
    if pool is None:
        raise RuntimeError("database.py PostgreSQL pool is not initialized")
    return pool


async def _schema() -> None:
    pool = await _pool()
    async with pool.acquire() as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS panels (
                id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
                uploader_id BIGINT NOT NULL,
                uploader_guild_id BIGINT,
                storage_message_id BIGINT,
                storage_channel_id BIGINT,
                attachment_url TEXT NOT NULL,
                filename TEXT NOT NULL,
                title VARCHAR(100) NOT NULL,
                anilist_id BIGINT,
                chapter_number VARCHAR(32),
                caption VARCHAR(500),
                source_url TEXT,
                is_nsfw BOOLEAN NOT NULL DEFAULT FALSE,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS panel_tags (
                panel_id BIGINT NOT NULL REFERENCES panels(id) ON DELETE CASCADE,
                tag VARCHAR(30) NOT NULL,
                PRIMARY KEY (panel_id, tag)
            )
        """)
        await conn.execute("ALTER TABLE panels ADD COLUMN IF NOT EXISTS anilist_id BIGINT")
        await conn.execute("ALTER TABLE panels ADD COLUMN IF NOT EXISTS chapter_number VARCHAR(32)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_panels_created_at ON panels(created_at DESC)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_panels_uploader_id ON panels(uploader_id)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_panel_tags_tag ON panel_tags(tag)")
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS guild_settings (
                guild_id BIGINT PRIMARY KEY
            )
        """)
        for col in ("panel_storage_channel_id", "panel_log_channel_id", "panel_mod_role_id"):
            await conn.execute(f"ALTER TABLE guild_settings ADD COLUMN IF NOT EXISTS {col} BIGINT")
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS mod_log (
                id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
                guild_id BIGINT NOT NULL,
                moderator_id BIGINT NOT NULL,
                panel_id BIGINT,
                panel_title VARCHAR(100),
                uploader_id BIGINT,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """)
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_mod_log_guild_created ON mod_log(guild_id, created_at DESC)")


def _tags(raw: str | None) -> list[str]:
    result: list[str] = []
    for part in (raw or "").split(","):
        tag = part.strip().lower()
        if not tag:
            continue
        if len(tag) > 30:
            raise ValueError("Each tag must be 30 characters or fewer.")
        if tag not in result:
            result.append(tag)
    if len(result) > 20:
        raise ValueError("Use no more than 20 unique tags across both selectors.")
    return result


def _parse_chapter_caption(value: str) -> tuple[str, str]:
    """Require a chapter number (or N/A) while allowing the caption to be omitted."""
    match = CHAPTER_CAPTION_RE.fullmatch(value.strip())
    if not match:
        raise ValueError(
            "Enter a chapter number, or **N/A** if unknown. A caption is optional. "
            "Examples: **Chapter 12 — Final battle**, **Chapter 12**, or **N/A**."
        )
    chapter_number = match.group(1).upper() if match.group(1).upper() == "N/A" else match.group(1)
    caption = (match.group(2) or "").strip()
    # Reject a dangling separator but accept a chapter number with no caption.
    if value.strip().endswith(("-", "–", "—", ":", "|")):
        raise ValueError("A caption may be omitted, but do not leave a separator at the end.")
    return chapter_number, caption


def _anilist_reference_id(value: str) -> int | None:
    """Extract a manga ID from a numeric value or canonical AniList manga URL."""
    raw = value.strip()
    if raw.isdecimal():
        media_id = int(raw)
        if media_id <= 0:
            raise ValueError("AniList manga IDs must be positive numbers.")
        return media_id

    if raw.lower().startswith(("www.anilist.co/", "anilist.co/")):
        raw = f"https://{raw}"
    parsed = urlsplit(raw)
    if parsed.scheme or parsed.netloc:
        host = (parsed.hostname or "").lower()
        if parsed.scheme not in {"http", "https"} or host not in {"anilist.co", "www.anilist.co"}:
            raise ValueError("Use a manga title, AniList manga ID, or AniList manga URL.")
        match = re.match(r"^/manga/(\d+)(?:/|$)", parsed.path, re.IGNORECASE)
        if not match:
            raise ValueError("That URL is not an AniList manga page. Use an AniList manga URL.")
        media_id = int(match.group(1))
        if media_id <= 0:
            raise ValueError("AniList manga IDs must be positive numbers.")
        return media_id
    return None


async def _resolve_manga_reference(value: str) -> tuple[str, int | None, str | None]:
    """Resolve explicit AniList IDs/URLs, leaving ordinary titles untouched."""
    media_id = _anilist_reference_id(value)
    if media_id is None:
        return value.strip(), None, None

    media = await fetch_media_by_id(media_id, "MANGA")
    if not media or not media.get("id"):
        raise ValueError(f"AniList could not resolve manga ID {media_id}. Check the ID/URL and try again.")
    titles = media.get("title") or {}
    title = str(titles.get("english") or titles.get("romaji") or titles.get("native") or "").strip()
    if not title:
        raise ValueError(f"AniList returned no usable title for manga ID {media_id}.")
    resolved_id = int(media["id"])
    return title, resolved_id, f"https://anilist.co/manga/{resolved_id}"


def _carry_anilist_link(panel: dict[str, Any] | None, title: str, requested_id: int | None,
                        source_url: str | None) -> tuple[int | None, str | None]:
    """Keep an edited panel's AniList link only while its title is unchanged."""
    if requested_id is not None or not panel or not panel.get("anilist_id"):
        return requested_id, source_url
    if title == panel.get("title"):
        return int(panel["anilist_id"]), source_url
    # Retitled to plain text: drop the old link and its AniList source URL, but keep
    # any other source (e.g. the Discord message the panel was saved from).
    if source_url == f"https://anilist.co/manga/{int(panel['anilist_id'])}":
        source_url = None
    return None, source_url


def _max_upload_bytes(interaction: discord.Interaction, storage: discord.TextChannel) -> int:
    """Use the tightest known upload limit across the interaction and storage server."""
    limits = []
    for candidate in (
        getattr(interaction, "filesize_limit", None),
        getattr(getattr(storage, "guild", None), "filesize_limit", None),
    ):
        try:
            limit = int(candidate)
        except (TypeError, ValueError):
            continue
        if limit > 0:
            limits.append(limit)
    return min(limits) if limits else MAX_IMAGE_BYTES


def _nsfw(interaction: discord.Interaction) -> bool:
    try:
        return bool(interaction.channel and interaction.channel.is_nsfw())
    except (AttributeError, TypeError):
        return False

async def _settings(guild_id: int) -> dict[str, Any]:
    pool = await _pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT * FROM guild_settings WHERE guild_id=$1", guild_id)
    return dict(row) if row else {}


async def _storage_channel(bot: commands.Bot, guild: discord.Guild | None):
    if guild:
        settings = await _settings(guild.id)
        channel_id = settings.get("panel_storage_channel_id")
        if channel_id:
            channel = guild.get_channel(int(channel_id))
            if isinstance(channel, discord.TextChannel):
                return channel
    if DEFAULT_STORAGE_CHANNEL_ID:
        channel = bot.get_channel(int(DEFAULT_STORAGE_CHANNEL_ID))
        if isinstance(channel, discord.TextChannel):
            return channel
    return None


async def _panel_ids(allow_mature: bool, user_id: int | None = None,
                     tags: list[str] | None = None, keyword: str | None = None) -> list[int]:
    clauses = ["($1::boolean OR p.is_nsfw=FALSE)"]
    args: list[Any] = [allow_mature]
    if user_id is not None:
        args.append(user_id)
        clauses.append(f"p.uploader_id=${len(args)}")
    if keyword:
        args.append(f"%{keyword}%")
        n = len(args)
        clauses.append(
            f"(p.title ILIKE ${n} OR COALESCE(p.caption,'') ILIKE ${n} "
            f"OR COALESCE(p.chapter_number,'') ILIKE ${n})"
        )
    if tags:
        args.append(tags)
        n = len(args)
        clauses.append(
            f"(SELECT COUNT(DISTINCT pt.tag) FROM panel_tags pt WHERE pt.panel_id=p.id "
            f"AND pt.tag=ANY(${n}::text[]))=cardinality(${n}::text[])"
        )
    pool = await _pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT p.id FROM panels p WHERE " + " AND ".join(clauses) + " ORDER BY p.created_at DESC, p.id DESC",
            *args,
        )
    return [int(row["id"]) for row in rows]


async def _get_panel(panel_id: int, allow_mature: bool) -> dict[str, Any] | None:
    pool = await _pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM panels WHERE id=$1 AND ($2::boolean OR is_nsfw=FALSE)", panel_id, allow_mature
        )
        if not row:
            return None
        panel = dict(row)
        panel["tags"] = [r["tag"] for r in await conn.fetch(
            "SELECT tag FROM panel_tags WHERE panel_id=$1 ORDER BY tag", panel_id
        )]
        return panel


async def _count(allow_mature: bool, user_id: int | None = None) -> int:
    pool = await _pool()
    async with pool.acquire() as conn:
        if user_id is None:
            row = await conn.fetchrow("SELECT COUNT(*) AS n FROM panels WHERE ($1::boolean OR is_nsfw=FALSE)", allow_mature)
        else:
            row = await conn.fetchrow(
                "SELECT COUNT(*) AS n FROM panels WHERE uploader_id=$1 AND ($2::boolean OR is_nsfw=FALSE)",
                user_id, allow_mature,
            )
    return int(row["n"])


async def _fresh_attachment(bot: commands.Bot, panel: dict[str, Any]) -> str | None:
    url = str(panel["attachment_url"])
    match = re.search(r"(?:[?&])ex=([0-9a-fA-F]+)", url)
    if not match or int(match.group(1), 16) > __import__("time").time():
        return url
    channel = bot.get_channel(int(panel["storage_channel_id"])) if panel.get("storage_channel_id") else None
    if channel is None:
        try:
            channel = await bot.fetch_channel(int(panel["storage_channel_id"]))
        except (discord.HTTPException, TypeError, ValueError):
            return None
    try:
        message = await channel.fetch_message(int(panel["storage_message_id"]))
        attachment = next((a for a in message.attachments if a.filename == panel["filename"]), None)
        if attachment is None and message.attachments:
            attachment = message.attachments[0]
        if attachment is None:
            return None
        fresh = attachment.url
        pool = await _pool()
        async with pool.acquire() as conn:
            await conn.execute("UPDATE panels SET attachment_url=$1, updated_at=NOW() WHERE id=$2", fresh, panel["id"])
        panel["attachment_url"] = fresh
        return fresh
    except (discord.HTTPException, discord.NotFound, discord.Forbidden):
        return None


def _embed(panel: dict[str, Any], page: int, total: int, guild_name: str | None) -> discord.Embed:
    mature = bool(panel["is_nsfw"])
    anilist_id = panel.get("anilist_id")
    anilist_url = f"https://anilist.co/manga/{int(anilist_id)}" if anilist_id else None
    caption = str(panel.get("caption") or "").strip()
    chapter_number = panel.get("chapter_number")
    description_lines = []
    if chapter_number:
        chapter_label = discord.utils.escape_markdown(str(chapter_number))
        description_lines.append(f"**Chapter {chapter_label}**")
    description_lines.append(caption or "*No caption provided.*")
    description = "\n".join(description_lines)
    embed = discord.Embed(
        title=str(panel["title"])[:100],
        description=description[:4000],
        colour=PALETTE.DANGER if mature else PALETTE.PRIMARY,
        timestamp=panel.get("created_at"),
        url=anilist_url,
    )
    if panel.get("attachment_url"):
        embed.set_image(url=panel["attachment_url"])
    tags = ", ".join(panel.get("tags", [])) or "None"
    embed.add_field(name="🏷️ Tags", value=tags[:1024], inline=False)
    if anilist_id:
        embed.add_field(
            name="📚 AniList manga",
            value=f"[Open manga page]({anilist_url}) · ID: {int(anilist_id)}",
            inline=True,
        )
    embed.add_field(name="👤 Uploader", value=f"<@{panel['uploader_id']}>", inline=True)
    embed.add_field(name="🌐 Source server", value=guild_name or "Unknown / unavailable", inline=True)
    embed.add_field(name="🔞 Content rating", value="Age-restricted" if mature else "Safe", inline=True)
    embed.set_footer(text=f"📖 Panel #{panel['id']} • Page {page} of {max(total, 1)}")
    if panel.get("source_url") and panel.get("source_url") != anilist_url:
        embed.add_field(name="🔗 Source", value=f"[Open source link]({panel['source_url']})", inline=False)
    return embed

async def _is_mod(interaction: discord.Interaction) -> bool:
    if interaction.guild is None:
        return False
    if interaction.permissions.manage_messages:
        return True
    settings = await _settings(interaction.guild.id)
    role_id = settings.get("panel_mod_role_id")
    return bool(role_id and isinstance(interaction.user, discord.Member)
                and any(role.id == int(role_id) for role in interaction.user.roles))


async def _can_manage(interaction: discord.Interaction, panel: dict[str, Any]) -> bool:
    return interaction.user.id == int(panel["uploader_id"]) or await _is_mod(interaction)


async def _audit_delete(interaction: discord.Interaction, panel: dict[str, Any]) -> None:
    # The audit row is written in the same transaction as the delete; this helper
    # only delivers the optional guild-local notification.
    if interaction.guild_id is None:
        return
    settings = await _settings(interaction.guild_id)
    channel = interaction.guild.get_channel(int(settings["panel_log_channel_id"])) if settings.get("panel_log_channel_id") and interaction.guild else None
    if channel:
        try:
            await channel.send(
                f"Panel **{discord.utils.escape_markdown(panel['title'])}** (#{panel['id']}) deleted by {interaction.user.mention}; uploader <@{panel['uploader_id']}>."
            )
        except discord.HTTPException:
            log.warning("Could not post panel audit log to guild %s", interaction.guild_id)


class PanelForm(FeedbackAwareModal):
    def __init__(self, cog: "PanelCog", *, mode: str, user_id: int, guild_id: int,
                 panel: dict[str, Any] | None = None, source_url: str | None = None):
        super().__init__(title="Add Manga Panel" if mode == "add" else "Edit Manga Panel", timeout=300)
        self.cog, self.mode, self.user_id, self.guild_id = cog, mode, user_id, guild_id
        self.panel = panel
        self.source_url = source_url or (panel.get("source_url") if panel else None)
        self.image = discord.ui.Label(
            text="🖼️ Panel image",
            description="Discord's upload limit for this server applies. Optional when editing.",
            component=discord.ui.FileUpload(min_values=1 if mode == "add" else 0, max_values=1, required=mode == "add"),
        )
        self.title_field = discord.ui.Label(
            text="📚 Manga title, AniList ID or URL",
            description="Enter a title, numeric AniList manga ID, or an AniList manga URL.",
            component=discord.ui.TextInput(default=panel["title"] if panel else None, max_length=300, required=True),
        )
        selected_tags = list(panel.get("tags", [])) if panel else []
        if panel and panel.get("is_nsfw") and "mature" not in selected_tags:
            selected_tags.append("mature")
        tag_values = list(dict.fromkeys(
            [tag for tag in selected_tags if tag not in PANEL_VISUAL_TAGS] + list(PANEL_TAGS)
        ))[:25]
        visual_tag_values = list(dict.fromkeys(
            [tag for tag in selected_tags if tag in PANEL_VISUAL_TAGS] + list(PANEL_VISUAL_TAGS)
        ))[:25]
        self.tags_field = discord.ui.Label(
            text="🏷️ Genres & story (required)",
            description="Choose 1–10 tags. Each option includes a short description.",
            component=discord.ui.Select(
                placeholder="Choose genres and story themes",
                options=[
                    discord.SelectOption(
                        label=tag.title()[:100],
                        value=tag,
                        description=PANEL_TAG_DESCRIPTIONS.get(tag, "Saved tag from an earlier version.")[:100],
                        default=tag in selected_tags,
                    )
                    for tag in tag_values
                ],
                min_values=1,
                max_values=min(10, len(tag_values)),
            ),
        )
        self.visual_tags_field = discord.ui.Label(
            text="🎨 Themes & panel style (optional)",
            description="Choose up to 10 more tags. Select Mature for age-restricted content.",
            component=discord.ui.Select(
                placeholder="Choose visual, scene, or setting tags",
                options=[
                    discord.SelectOption(
                        label=tag.title()[:100],
                        value=tag,
                        description=PANEL_TAG_DESCRIPTIONS.get(tag, "Saved tag from an earlier version.")[:100],
                        default=tag in selected_tags,
                    )
                    for tag in visual_tag_values
                ],
                min_values=0,
                max_values=min(10, len(visual_tag_values)),
            ),
        )
        caption_default = "N/A"
        if panel:
            old_caption = str(panel.get("caption") or "")
            old_chapter = panel.get("chapter_number") or "N/A"
            chapter_label = f"Chapter {old_chapter}" if str(old_chapter).upper() != "N/A" else "N/A"
            caption_default = f"{chapter_label} — {old_caption}" if old_caption else chapter_label
        self.caption_field = discord.ui.Label(
            text="📖 Chapter number (required) • caption (optional)",
            description="Enter a chapter number; if unknown, enter N/A. Caption is optional. Examples: Chapter 12 — Final battle; Chapter 12; N/A.",
            component=discord.ui.TextInput(
                default=caption_default if panel else None,
                placeholder="Chapter 12 — final battle, or N/A",
                style=discord.TextStyle.paragraph,
                max_length=500,
                required=True,
            ),
        )
        for item in (self.image, self.title_field, self.tags_field, self.visual_tags_field, self.caption_field):
            self.add_item(item)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True, thinking=True)
        stored_message = None
        try:
            if interaction.user.id != self.user_id:
                await interaction.followup.send("This form belongs to another user.", ephemeral=True)
                return
            submitted_title = str(self.title_field.component.value or "").strip()
            chapter_input = str(self.caption_field.component.value or "").strip()
            chapter_number, caption = _parse_chapter_caption(chapter_input)
            if not submitted_title:
                await interaction.followup.send("A manga title, AniList ID, or AniList URL is required.", ephemeral=True)
                return
            title, requested_anilist_id, requested_anilist_url = await _resolve_manga_reference(submitted_title)
            if not title or len(title) > 100:
                await interaction.followup.send("The resolved manga title must be 100 characters or fewer.", ephemeral=True)
                return
            anilist_id, source_url = _carry_anilist_link(
                self.panel, title, requested_anilist_id, requested_anilist_url or self.source_url,
            )
            selected_tags = list(self.tags_field.component.values or []) + list(self.visual_tags_field.component.values or [])
            if not selected_tags:
                await interaction.followup.send("Select at least one tag for this panel.", ephemeral=True)
                return
            tags = _tags(",".join(selected_tags))
            values = self.image.component.values or []
            upload = values[0] if values else None
            image_bytes = None
            filename = self.panel["filename"] if self.panel else "panel-image"
            upload_size = 0
            if upload:
                content_type = (getattr(upload, "content_type", None) or "").lower()
                if content_type not in IMAGE_TYPES:
                    await interaction.followup.send("Only PNG, JPEG, GIF, WebP, or AVIF images are accepted.", ephemeral=True)
                    return
                upload_size = int(getattr(upload, "size", 0) or 0)
                filename = getattr(upload, "filename", filename)
            guild = interaction.guild
            if guild is None or guild.id != self.guild_id:
                await interaction.followup.send("This form must be submitted in the server where it was opened.", ephemeral=True)
                return
            settings = await _settings(guild.id)
            channel_id = settings.get("panel_storage_channel_id") or DEFAULT_STORAGE_CHANNEL_ID
            storage = await _storage_channel(self.cog.bot, guild)
            if storage is None:
                await interaction.followup.send(
                    "No panel storage channel is configured. Ask a Manage Server member to open /panels and select Configure.",
                    ephemeral=True,
                )
                return
            if channel_id and storage.id != int(channel_id) and not DEFAULT_STORAGE_CHANNEL_ID:
                await interaction.followup.send("Configured storage channel is unavailable; ask an admin to reconfigure it.", ephemeral=True)
                return
            max_image_bytes = _max_upload_bytes(interaction, storage)
            if upload and upload_size > max_image_bytes:
                uploaded_mib = upload_size / (1024 * 1024)
                limit_mib = max_image_bytes / (1024 * 1024)
                await interaction.followup.send(
                    f"That image is **{uploaded_mib:.1f} MiB**, but the configured archive server supports "
                    f"up to **{limit_mib:.1f} MiB** per file. Try a higher-limit storage server or a smaller export.",
                    ephemeral=True,
                )
                return
            if upload:
                image_bytes = await upload.read()
                if len(image_bytes) > max_image_bytes:
                    uploaded_mib = len(image_bytes) / (1024 * 1024)
                    limit_mib = max_image_bytes / (1024 * 1024)
                    await interaction.followup.send(
                        f"That image is **{uploaded_mib:.1f} MiB**, above this archive's "
                        f"**{limit_mib:.1f} MiB** per-file limit.",
                        ephemeral=True,
                    )
                    return

            attachment_url = self.panel["attachment_url"] if self.panel else None
            storage_message_id = self.panel.get("storage_message_id") if self.panel else None
            storage_channel_id = self.panel.get("storage_channel_id") if self.panel else None
            if image_bytes is not None:
                stored_message = await storage.send(file=discord.File(io.BytesIO(image_bytes), filename=filename))
                if not stored_message.attachments:
                    raise RuntimeError("Discord storage message returned no attachment")
                attachment_url = stored_message.attachments[0].url
                storage_message_id, storage_channel_id = stored_message.id, storage.id
            elif self.mode == "add":
                await interaction.followup.send("Please attach an image.", ephemeral=True)
                return
            mature = "mature" in tags
            pool = await _pool()
            async with pool.acquire() as conn:
                async with conn.transaction():
                    if self.mode == "add":
                        row = await conn.fetchrow("""
                            INSERT INTO panels(uploader_id,uploader_guild_id,storage_message_id,storage_channel_id,
                                attachment_url,filename,title,anilist_id,chapter_number,caption,source_url,is_nsfw)
                            VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12) RETURNING id
                        """, interaction.user.id, guild.id, storage_message_id, storage_channel_id,
                             attachment_url, filename, title, anilist_id, chapter_number, caption, source_url, mature)
                        panel_id = int(row["id"])
                    else:
                        panel_id = int(self.panel["id"])
                        await conn.execute("""
                            UPDATE panels SET storage_message_id=$1,storage_channel_id=$2,attachment_url=$3,
                                filename=$4,title=$5,anilist_id=$6,chapter_number=$7,caption=$8,source_url=$9,is_nsfw=$10,updated_at=NOW()
                            WHERE id=$11
                        """, storage_message_id, storage_channel_id, attachment_url, filename, title,
                             anilist_id, chapter_number, caption, source_url, mature, panel_id)
                        await conn.execute("DELETE FROM panel_tags WHERE panel_id=$1", panel_id)
                    for tag in tags:
                        await conn.execute("INSERT INTO panel_tags(panel_id,tag) VALUES($1,$2) ON CONFLICT DO NOTHING", panel_id, tag)
            if image_bytes is not None and self.mode == "edit" and self.panel.get("storage_message_id"):
                await self.cog._delete_storage_message(self.panel)
            panel = await _get_panel(panel_id, True)
            embed = _embed(panel, 1, 1, guild.name) if panel else discord.Embed(title=title)
            view = PanelResultView(self.cog, panel_id)
            await interaction.followup.send(content=f"Panel #{panel_id} {'saved' if self.mode == 'add' else 'updated'}.", embed=embed, view=view, ephemeral=True)
        except ValueError as exc:
            if stored_message:
                await self.cog._delete_message(stored_message.channel, stored_message.id)
            await interaction.followup.send(str(exc), ephemeral=True)
        except discord.HTTPException as exc:
            log.warning("Discord rejected panel storage upload/update: %s", exc)
            if stored_message:
                await self.cog._delete_message(stored_message.channel, stored_message.id)
            if getattr(exc, "code", None) == 40005:
                message = (
                    "Discord rejected the image because it exceeds the storage server's upload limit. "
                    "Try a higher-limit storage server or a smaller export."
                )
            else:
                message = "Discord could not store the panel image. Check the storage channel's Attach Files permission and try again."
            await interaction.followup.send(message, ephemeral=True)
        except Exception:
            log.exception("Panel form submit failed")
            if stored_message:
                await self.cog._delete_message(stored_message.channel, stored_message.id)
            await interaction.followup.send("Something went wrong while saving the panel.", ephemeral=True)


class PanelSearchModal(FeedbackAwareModal, title="Search Manga Panels"):
    keyword = discord.ui.TextInput(label="Keyword (2–50 chars)", min_length=2, max_length=50, required=True)
    tags = discord.ui.TextInput(label="Tags (optional, comma-separated)", max_length=300, required=False)

    def __init__(self, cog: "PanelCog"):
        super().__init__(timeout=180)
        self.cog = cog

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            keyword = str(self.keyword.value or "").strip()
            if not 2 <= len(keyword) <= 50:
                await interaction.followup.send("Keyword must be between 2 and 50 characters.", ephemeral=True)
                return
            ids = await _panel_ids(_nsfw(interaction), tags=_tags(str(self.tags.value or "")), keyword=keyword)
            await self.cog._post_browser(interaction, ids, tags=_tags(str(self.tags.value or "")), keyword=keyword)
        except ValueError as exc:
            await interaction.followup.send(str(exc), ephemeral=True)
        except Exception:
            log.exception("Panel search failed")
            await interaction.followup.send("Something went wrong while searching.", ephemeral=True)


class PanelConfigureModal(FeedbackAwareModal, title="Configure Panel Archive"):
    def __init__(self, cog: "PanelCog"):
        super().__init__(timeout=180)
        self.cog = cog
        self.storage = discord.ui.Label(text="Storage channel (required)", component=discord.ui.ChannelSelect(
            channel_types=[discord.ChannelType.text], min_values=1, max_values=1))
        self.log_channel = discord.ui.Label(text="Moderation log channel (optional)", component=discord.ui.ChannelSelect(
            channel_types=[discord.ChannelType.text], min_values=0, max_values=1, required=False))
        self.mod_role = discord.ui.Label(text="Moderator role (optional)", component=discord.ui.RoleSelect(
            min_values=0, max_values=1, required=False))
        for item in (self.storage, self.log_channel, self.mod_role):
            self.add_item(item)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True, thinking=True)
        guild = interaction.guild
        try:
            if guild is None or not interaction.permissions.manage_guild:
                await interaction.followup.send("Manage Server permission is required.", ephemeral=True)
                return
            # ChannelSelect yields AppCommandChannel stubs; resolve the real channel for permission checks.
            picked = self.storage.component.values
            storage = guild.get_channel(picked[0].id) if picked else None
            if not isinstance(storage, discord.TextChannel):
                await interaction.followup.send("Choose a text storage channel.", ephemeral=True)
                return
            me = guild.me
            perms = storage.permissions_for(me) if me else None
            if not perms or not (perms.view_channel and perms.send_messages and perms.attach_files):
                await interaction.followup.send("The bot needs View Channel, Send Messages, and Attach Files in the storage channel.", ephemeral=True)
                return
            logs = self.log_channel.component.values or []
            roles = self.mod_role.component.values or []
            pool = await _pool()
            async with pool.acquire() as conn:
                await conn.execute("""
                    INSERT INTO guild_settings(guild_id,panel_storage_channel_id,panel_log_channel_id,panel_mod_role_id)
                    VALUES($1,$2,$3,$4)
                    ON CONFLICT(guild_id) DO UPDATE SET
                    panel_storage_channel_id=EXCLUDED.panel_storage_channel_id,
                    panel_log_channel_id=EXCLUDED.panel_log_channel_id,
                    panel_mod_role_id=EXCLUDED.panel_mod_role_id
                """, guild.id, storage.id, logs[0].id if logs else None, roles[0].id if roles else None)
            await interaction.followup.send("Archive settings saved for this server.", ephemeral=True)
        except Exception:
            log.exception("Panel configuration failed")
            await interaction.followup.send("Something went wrong while saving settings.", ephemeral=True)


class PanelJumpModal(FeedbackAwareModal, title="Jump to Page"):
    page_number = discord.ui.TextInput(label="Page number", min_length=1, max_length=7, required=True)

    def __init__(self, view: "PanelBrowserView"):
        super().__init__(timeout=120)
        self.browser = view

    async def on_submit(self, interaction: discord.Interaction):
        try:
            page = int(str(self.page_number.value).strip())
            if not 1 <= page <= len(self.browser.panel_ids):
                await interaction.response.send_message(f"Enter a page from 1 to {len(self.browser.panel_ids)}.", ephemeral=True)
                return
            self.browser.page = page - 1
            await self.browser.cog._render(interaction, self.browser)
        except ValueError:
            await interaction.response.send_message("Enter a valid page number.", ephemeral=True)
        except Exception:
            log.exception("Panel jump failed")
            await interaction.response.send_message("Something went wrong.", ephemeral=True)


class PanelTagFilter(discord.ui.Select):
    def __init__(self, browser: "PanelBrowserView", options: list[discord.SelectOption]):
        super().__init__(placeholder="Filter by up to 5 tags (AND)", min_values=0, max_values=5,
                         options=options, custom_id=f"panels:filter:{browser.token}")
        self.browser = browser

    async def callback(self, interaction: discord.Interaction):
        try:
            chosen = list(self.values)
            if "other" in chosen:
                await interaction.response.send_modal(PanelSearchModal(self.browser.cog))
                return
            self.browser.tags = chosen
            self.browser.panel_ids = await _panel_ids(
                _nsfw(interaction), user_id=self.browser.user_id,
                tags=self.browser.tags, keyword=self.browser.keyword
            )
            self.browser.page = 0
            if self.browser.message is not None:
                if self.browser.panel_ids:
                    panel = await _get_panel(self.browser.panel_ids[0], _nsfw(interaction))
                    embed = await self.browser.cog._resolved_embed(panel, 1, len(self.browser.panel_ids)) if panel else None
                    self.browser._build()
                    await self.browser.message.edit(content=None, embed=embed, view=self.browser)
                else:
                    self.browser._build()
                    await self.browser.message.edit(
                        content="No panels match this filter. Some panels may be hidden in this channel (age-restricted).",
                        embed=None, view=self.browser
                    )
            await interaction.response.send_message("Filter applied to the public browser.", ephemeral=True)
        except Exception:
            log.exception("Panel filter failed")
            if interaction.response.is_done():
                await interaction.followup.send("Something went wrong applying the filter.", ephemeral=True)
            else:
                await interaction.response.send_message("Something went wrong applying the filter.", ephemeral=True)


class PanelBrowserView(FeedbackAwareView):
    """Public single-message browser. Navigation re-queries against current channel NSFW status."""
    def __init__(self, cog: "PanelCog", ids: list[int], *, tags: list[str] | None = None,
                 keyword: str | None = None, user_id: int | None = None, fixed_ids: bool = False):
        super().__init__(timeout=BROWSER_TIMEOUT)
        self.cog, self.panel_ids = cog, ids
        self.message = None
        self.tags, self.keyword = list(tags or []), keyword
        self.user_id, self.fixed_ids = user_id, fixed_ids
        self.page = 0
        self.token = secrets.token_hex(3)
        self._build()

    def _build(self):
        self.clear_items()
        controls = [
            ("First", "first", self.page > 0, "⏮️"), ("Prev", "prev", self.page > 0, "◀️"),
            ("Next", "next", self.page < len(self.panel_ids)-1, "▶️"), ("Last", "last", self.page < len(self.panel_ids)-1, "⏭️"),
            ("Random", "random", bool(self.panel_ids), "🎲"),
        ]
        for label, action, enabled, emoji in controls:
            b = discord.ui.Button(label=label, emoji=emoji, style=discord.ButtonStyle.secondary, disabled=not enabled,
                                  custom_id=f"panels:{action}:{self.token}")
            async def cb(interaction: discord.Interaction, act=action):
                await self._navigate(interaction, act)
            b.callback = cb
            self.add_item(b)
        if self.panel_ids:
            self.add_item(discord.ui.Button(label="Jump", emoji="↗️", style=discord.ButtonStyle.secondary,
                                            custom_id=f"panels:jump:{self.token}"))
            self.children[-1].callback = self._jump
            self.add_item(discord.ui.Button(label="Filter", emoji="🏷️", style=discord.ButtonStyle.secondary,
                                            custom_id=f"panels:filteropen:{self.token}"))
            self.children[-1].callback = self._filter
            self.add_item(discord.ui.Button(label="Edit", emoji="✏️", style=discord.ButtonStyle.primary,
                                            custom_id=f"panels:edit:{self.token}"))
            self.children[-1].callback = self._edit
            self.add_item(discord.ui.Button(label="Delete", emoji="🗑️", style=discord.ButtonStyle.danger,
                                            custom_id=f"panels:delete:{self.token}"))
            self.children[-1].callback = self._delete
        self.add_item(discord.ui.Button(label="Clear Filter", emoji="🧹", style=discord.ButtonStyle.secondary,
                                        custom_id=f"panels:clear:{self.token}", disabled=not (self.tags or self.keyword)))
        self.children[-1].callback = self._clear
        self.add_item(discord.ui.Button(label="Close", emoji="✖️", style=discord.ButtonStyle.danger,
                                        custom_id=f"panels:close:{self.token}"))
        self.children[-1].callback = self._close

    async def _navigate(self, interaction: discord.Interaction, action: str):
        try:
            if action == "first": self.page = 0
            elif action == "prev": self.page -= 1
            elif action == "next": self.page += 1
            elif action == "last": self.page = len(self.panel_ids)-1
            elif action == "random" and self.panel_ids: self.page = secure_choice(range(len(self.panel_ids)))
            self.page = max(0, min(self.page, max(0, len(self.panel_ids)-1)))
            await self.cog._render(interaction, self)
        except Exception:
            log.exception("Panel navigation failed")
            await interaction.response.send_message("Something went wrong.", ephemeral=True)

    async def _jump(self, interaction: discord.Interaction):
        if self.panel_ids:
            await interaction.response.send_modal(PanelJumpModal(self))
        else:
            await interaction.response.send_message("No results to jump through.", ephemeral=True)

    async def _filter(self, interaction: discord.Interaction):
        try:
            pool = await _pool()
            async with pool.acquire() as conn:
                rows = await conn.fetch("""
                    SELECT tag,COUNT(*) AS usage FROM panel_tags GROUP BY tag
                    ORDER BY usage DESC, tag ASC LIMIT 24
                """)
            options = [discord.SelectOption(label=str(r["tag"])[:100], value=str(r["tag"])) for r in rows]
            options.append(discord.SelectOption(label="Other (search)", value="other"))
            view = FeedbackAwareView(timeout=120)
            view.add_item(PanelTagFilter(self, options))
            await interaction.response.send_message("Choose up to five tags; all selected tags must match.", view=view, ephemeral=True)
        except Exception:
            log.exception("Open panel filter failed")
            await interaction.response.send_message("Something went wrong.", ephemeral=True)

    async def _clear(self, interaction: discord.Interaction):
        try:
            self.tags, self.keyword = [], None
            self.panel_ids = await _panel_ids(_nsfw(interaction))
            self.page = 0
            await self.cog._render(interaction, self)
        except Exception:
            log.exception("Clear panel filter failed")
            await interaction.response.send_message("Something went wrong.", ephemeral=True)

    async def _edit(self, interaction: discord.Interaction):
        try:
            if not self.panel_ids:
                await interaction.response.send_message("No panel to edit.", ephemeral=True); return
            panel = await _get_panel(self.panel_ids[self.page], _nsfw(interaction))
            if not panel:
                await interaction.response.send_message("Image unavailable or hidden in this channel.", ephemeral=True); return
            if not await _can_manage(interaction, panel):
                await interaction.response.send_message("Only the uploader or a moderator of this server can edit this panel.", ephemeral=True); return
            await interaction.response.send_modal(PanelForm(self.cog, mode="edit", user_id=interaction.user.id,
                                                            guild_id=interaction.guild_id or 0, panel=panel))
        except Exception:
            log.exception("Edit panel action failed")
            await interaction.response.send_message("Something went wrong.", ephemeral=True)

    async def _delete(self, interaction: discord.Interaction):
        try:
            if not self.panel_ids:
                await interaction.response.send_message("No panel to delete.", ephemeral=True); return
            panel = await _get_panel(self.panel_ids[self.page], _nsfw(interaction))
            if not panel:
                await interaction.response.send_message("Image unavailable or hidden in this channel.", ephemeral=True); return
            if not await _can_manage(interaction, panel):
                await interaction.response.send_message("Only the uploader or a moderator of this server can delete this panel.", ephemeral=True); return
            await interaction.response.send_message(
                f"Delete panel **{discord.utils.escape_markdown(panel['title'])}** (#{panel['id']}) permanently?",
                view=PanelDeleteConfirm(self.cog, panel, self), ephemeral=True,
            )
        except Exception as exc:
            log.exception("Delete panel action failed")
            if interaction.response.is_done():
                await interaction.followup.send(application_error_message(exc), ephemeral=True)
            else:
                await interaction.response.send_message(application_error_message(exc), ephemeral=True)

    async def _close(self, interaction: discord.Interaction):
        try:
            await interaction.response.edit_message(content="Panel browser closed.", embed=None, view=None)
        except Exception as exc:
            log.exception("Close panel browser failed")
            if interaction.response.is_done():
                await interaction.followup.send(application_error_message(exc), ephemeral=True)
            else:
                await interaction.response.send_message(application_error_message(exc), ephemeral=True)


class PanelDeleteConfirm(FeedbackAwareView):
    def __init__(self, cog: "PanelCog", panel: dict[str, Any], browser: PanelBrowserView):
        super().__init__(timeout=60)
        self.cog, self.panel, self.browser = cog, panel, browser

    @discord.ui.button(label="Confirm delete", style=discord.ButtonStyle.danger)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            panel = await _get_panel(int(self.panel["id"]), True)
            if not panel:
                await interaction.followup.send("Panel has already been deleted.", ephemeral=True); return
            if not await _can_manage(interaction, panel):
                await interaction.followup.send("You no longer have permission to delete this panel.", ephemeral=True); return
            is_mod_delete = interaction.user.id != int(panel["uploader_id"])
            await self.cog._delete_storage_message(panel)
            pool = await _pool()
            async with pool.acquire() as conn:
                async with conn.transaction():
                    await conn.execute("DELETE FROM panels WHERE id=$1", panel["id"])
                    if is_mod_delete and interaction.guild_id:
                        await conn.execute(
                            "INSERT INTO mod_log(guild_id,moderator_id,panel_id,panel_title,uploader_id) VALUES($1,$2,$3,$4,$5)",
                            interaction.guild_id, interaction.user.id, panel["id"], panel["title"], panel["uploader_id"],
                        )
            if is_mod_delete:
                try: await _audit_delete(interaction, panel)
                except Exception: log.exception("Could not send moderation log notification")
            await interaction.followup.send("Panel deleted.", ephemeral=True)
            self.browser.panel_ids = [pid for pid in self.browser.panel_ids if pid != int(panel["id"])]
            self.browser.page = min(self.browser.page, max(0, len(self.browser.panel_ids)-1))
        except Exception:
            log.exception("Confirm panel deletion failed")
            await interaction.followup.send(application_error_message(exc), ephemeral=True)

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(content="Deletion cancelled.", view=None)


class PanelResultView(FeedbackAwareView):
    def __init__(self, cog: "PanelCog", panel_id: int):
        super().__init__(timeout=180)
        self.cog, self.panel_id = cog, panel_id

    @discord.ui.button(label="View", style=discord.ButtonStyle.primary)
    async def view_panel(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            ids = [self.panel_id] if await _get_panel(self.panel_id, _nsfw(interaction)) else []
            await self.cog._post_browser(interaction, ids)
        except Exception:
            log.exception("View saved panel failed")
            await interaction.response.send_message("Something went wrong.", ephemeral=True)

    @discord.ui.button(label="Edit", style=discord.ButtonStyle.secondary)
    async def edit_panel(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            panel = await _get_panel(self.panel_id, True)
            if not panel or not await _can_manage(interaction, panel):
                await interaction.response.send_message("You cannot edit this panel.", ephemeral=True); return
            await interaction.response.send_modal(PanelForm(self.cog, mode="edit", user_id=interaction.user.id,
                                                            guild_id=interaction.guild_id or 0, panel=panel))
        except Exception:
            log.exception("Edit saved panel failed")
            await interaction.response.send_message("Something went wrong.", ephemeral=True)

    @discord.ui.button(label="Done", style=discord.ButtonStyle.secondary)
    async def done(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(content="Done.", embed=None, view=None)


class PanelHomeView(FeedbackAwareView):
    def __init__(self, cog: "PanelCog"):
        super().__init__(timeout=300)
        self.cog = cog

    @discord.ui.button(label="Browse All", emoji="📚", style=discord.ButtonStyle.primary, row=0)
    async def browse(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.cog._safe_home_action(interaction, "browse")

    @discord.ui.button(label="My Panels", emoji="🗂️", style=discord.ButtonStyle.secondary, row=0)
    async def mine(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.cog._safe_home_action(interaction, "mine")

    @discord.ui.button(label="Random", emoji="🎲", style=discord.ButtonStyle.secondary, row=0)
    async def random_panel(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.cog._safe_home_action(interaction, "random")

    @discord.ui.button(label="Search", emoji="🔎", style=discord.ButtonStyle.secondary, row=0)
    async def search(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(PanelSearchModal(self.cog))

    @discord.ui.button(label="Add Panel", emoji="➕", style=discord.ButtonStyle.success, row=0)
    async def add(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.guild_id is None:
            await interaction.response.send_message("Adding panels is only available in a server.", ephemeral=True); return
        await interaction.response.send_modal(PanelForm(self.cog, mode="add", user_id=interaction.user.id, guild_id=interaction.guild_id))

    @discord.ui.button(label="Configure", emoji="⚙️", style=discord.ButtonStyle.secondary, row=1)
    async def configure(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.guild_id is None or not interaction.permissions.manage_guild:
            await interaction.response.send_message("Manage Server permission is required in a server.", ephemeral=True); return
        await interaction.response.send_modal(PanelConfigureModal(self.cog))

    @discord.ui.button(label="Moderation Log", emoji="🛡️", style=discord.ButtonStyle.secondary, row=1)
    async def moderation_log(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            if not await _is_mod(interaction):
                await interaction.response.send_message("Moderator permissions are required.", ephemeral=True); return
            pool = await _pool()
            async with pool.acquire() as conn:
                rows = await conn.fetch("SELECT * FROM mod_log WHERE guild_id=$1 ORDER BY created_at DESC LIMIT 15", interaction.guild_id)
            embed = discord.Embed(title="🛡️ Panel Moderation Log", colour=PALETTE.WARNING)
            embed.description = "\n".join(
                f"• <t:{int(r['created_at'].timestamp())}:R> — <@{r['moderator_id']}> deleted **{discord.utils.escape_markdown(r['panel_title'] or 'Untitled')}** (#{r['panel_id']})"
                for r in rows
            ) or "No moderation actions have been logged for this server."
            await interaction.response.send_message(embed=embed, ephemeral=True)
        except Exception:
            log.exception("Moderation log view failed")
            if interaction.response.is_done(): await interaction.followup.send("Something went wrong.", ephemeral=True)
            else: await interaction.response.send_message("Something went wrong.", ephemeral=True)


class PanelAttachmentPicker(FeedbackAwareView):
    def __init__(self, cog: "PanelCog", message: discord.Message, attachments: list[discord.Attachment]):
        super().__init__(timeout=120)
        self.cog, self.message, self.attachments = cog, message, attachments
        options = [discord.SelectOption(label=(a.filename[:90] or f"Image {i+1}"), value=str(i),
                                        description=f"{a.content_type or 'image'} • {a.size // 1024} KB")
                   for i, a in enumerate(attachments[:25])]
        select = discord.ui.Select(placeholder="Choose an image from this message", min_values=1, max_values=1, options=options)
        select.callback = self.choose
        self.add_item(select)

    async def choose(self, interaction: discord.Interaction):
        try:
            selected = self.attachments[int(self.children[0].values[0])]
            await interaction.response.send_modal(PanelForm(self.cog, mode="add", user_id=interaction.user.id,
                                                            guild_id=interaction.guild_id or 0, source_url=self.message.jump_url))
        except Exception:
            log.exception("Attachment selection failed")
            await interaction.response.send_message("Something went wrong.", ephemeral=True)


class PanelCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # discord.py doesn't allow context menus as cog methods, so this one is added to the tree by hand.
        self.save_menu = app_commands.ContextMenu(name="Save to Panels", callback=self.save_message)

    async def cog_load(self):
        await _schema()
        self.bot.tree.add_command(self.save_menu, override=True)

    async def cog_unload(self):
        self.bot.tree.remove_command(self.save_menu.name, type=self.save_menu.type)

    async def _delete_message(self, channel, message_id: int):
        try:
            msg = await channel.fetch_message(message_id)
            await msg.delete()
        except (discord.NotFound, discord.Forbidden, discord.HTTPException):
            log.warning("Could not delete archive storage message %s", message_id)

    async def _delete_storage_message(self, panel: dict[str, Any]):
        if not panel.get("storage_channel_id") or not panel.get("storage_message_id"):
            return
        channel = self.bot.get_channel(int(panel["storage_channel_id"]))
        if channel is None:
            try: channel = await self.bot.fetch_channel(int(panel["storage_channel_id"]))
            except discord.HTTPException: return
        await self._delete_message(channel, int(panel["storage_message_id"]))

    async def _post_browser(self, interaction: discord.Interaction, ids: list[int], tags: list[str] | None = None,
                            keyword: str | None = None, user_id: int | None = None, fixed_ids: bool = False):
        try:
            if not ids:
                msg = "No panels match this filter."
                if not _nsfw(interaction):
                    msg += " Some panels are hidden in this channel (age-restricted)."
                if interaction.response.is_done(): await interaction.followup.send(msg, ephemeral=True)
                else: await interaction.response.send_message(msg, ephemeral=True)
                return
            channel = interaction.channel
            if channel is None or not hasattr(channel, "send"):
                if interaction.response.is_done(): await interaction.followup.send("Open the archive in a server text channel to browse publicly.", ephemeral=True)
                else: await interaction.response.send_message("Open the archive in a server text channel to browse publicly.", ephemeral=True)
                return
            view = PanelBrowserView(self, ids, tags=tags, keyword=keyword, user_id=user_id, fixed_ids=fixed_ids)
            await self._render_data(interaction, view)
            panel = await _get_panel(ids[0], _nsfw(interaction))
            if panel is None:
                raise RuntimeError("First panel is no longer visible")
            view.message = await channel.send(embed=await self._resolved_embed(panel, 1, len(ids)), view=view)
            msg = "Public panel browser posted in this channel."
            if interaction.response.is_done(): await interaction.followup.send(msg, ephemeral=True)
            else: await interaction.response.send_message(msg, ephemeral=True)
        except Exception:
            log.exception("Could not post panel browser")
            if interaction.response.is_done(): await interaction.followup.send(application_error_message(exc), ephemeral=True)
            else: await interaction.response.send_message("Something went wrong opening the browser.", ephemeral=True)

    async def _resolved_embed(self, panel, page, total):
        url = await _fresh_attachment(self.bot, panel)
        if url:
            panel["attachment_url"] = url
        else:
            panel["attachment_url"] = None
        guild = self.bot.get_guild(int(panel["uploader_guild_id"])) if panel.get("uploader_guild_id") else None
        embed = _embed(panel, page, total, guild.name if guild else None)
        if not url:
            embed.description = (embed.description or "") + "\n\n**Image unavailable.** Edit or delete this panel."
        return embed

    async def _render_data(self, interaction, browser):
        return None

    async def _render(self, interaction: discord.Interaction, browser: PanelBrowserView):
        try:
            # Re-query each time, so mature content is never leaked if the view is used in an SFW channel.
            ids = browser.panel_ids if browser.fixed_ids else await _panel_ids(
                _nsfw(interaction), user_id=browser.user_id, tags=browser.tags, keyword=browser.keyword
            )
            browser.panel_ids = ids
            browser.page = max(0, min(browser.page, max(0, len(ids)-1)))
            browser._build()
            if not ids:
                await interaction.response.edit_message(content="No panels match this filter. Some panels may be hidden in this channel (age-restricted).", embed=None, view=browser)
                return
            panel = await _get_panel(ids[browser.page], _nsfw(interaction))
            if panel is None:
                await interaction.response.edit_message(content="No panels match this filter.", embed=None, view=browser); return
            embed = await self._resolved_embed(panel, browser.page+1, len(ids))
            await interaction.response.edit_message(content=None, embed=embed, view=browser)
        except Exception:
            log.exception("Rendering panel browser failed")
            if interaction.response.is_done(): await interaction.followup.send("Something went wrong.", ephemeral=True)
            else: await interaction.response.send_message("Something went wrong.", ephemeral=True)

    async def _safe_home_action(self, interaction: discord.Interaction, action: str):
        try:
            await interaction.response.defer(ephemeral=True, thinking=True)
            if action == "mine":
                ids = await _panel_ids(_nsfw(interaction), user_id=interaction.user.id)
            else:
                ids = await _panel_ids(_nsfw(interaction))
            if action == "random" and ids:
                ids = [secure_choice(ids)]
            await self._post_browser(
                interaction, ids, user_id=interaction.user.id if action == "mine" else None,
                fixed_ids=(action == "random"),
            )
        except Exception:
            log.exception("Panel home action failed")
            if interaction.response.is_done(): await interaction.followup.send("Something went wrong.", ephemeral=True)
            else: await interaction.response.send_message("Something went wrong.", ephemeral=True)

    @app_commands.command(name="panels", description="Open the shared Manga Panel Archive")
    @command_meta(section="Media", name="Panel Archive")
    async def panels(self, interaction: discord.Interaction):
        try:
            await interaction.response.defer(ephemeral=True, thinking=True)
            count = await _count(_nsfw(interaction))
            embed = discord.Embed(
                title="📚 Manga Panel Archive",
                description=(
                    "A shared gallery of manga moments, double spreads, and standout artwork.\n"
                    f"**{count:,}** panels are visible in this channel."
                ),
                colour=PALETTE.PRIMARY,
            )
            embed.add_field(name="🖼️ Browse", value="Explore the archive, jump between panels, or pick a random find.", inline=True)
            embed.add_field(name="➕ Contribute", value="Upload a panel, add tags, and link its AniList manga entry.", inline=True)
            embed.set_footer(text="Panels are shared across servers • Storage is configured per server")
            if not _nsfw(interaction):
                embed.add_field(name="🔞 Content visibility", value="Mature panels are hidden in channels that are not age-restricted.", inline=False)
            await interaction.followup.send(embed=embed, view=PanelHomeView(self), ephemeral=True)
        except Exception:
            log.exception("/panels failed")
            if interaction.response.is_done(): await interaction.followup.send("Something went wrong.", ephemeral=True)
            else: await interaction.response.send_message("Something went wrong.", ephemeral=True)

    async def save_message(self, interaction: discord.Interaction, message: discord.Message):
        try:
            if interaction.guild_id is None:
                await interaction.response.send_message("This action is only available in a server.", ephemeral=True); return
            images = [a for a in message.attachments if (a.content_type or "").lower() in IMAGE_TYPES]
            if not images:
                await interaction.response.send_message("That message has no supported image attachments.", ephemeral=True); return
            if len(images) == 1:
                await interaction.response.send_modal(PanelForm(self, mode="add", user_id=interaction.user.id,
                                                                guild_id=interaction.guild_id, source_url=message.jump_url))
            else:
                await interaction.response.send_message("Choose the image to save, then complete the Add Panel form.", view=PanelAttachmentPicker(self, message, images), ephemeral=True)
        except Exception:
            log.exception("Save to Panels context menu failed")
            if interaction.response.is_done(): await interaction.followup.send("Something went wrong.", ephemeral=True)
            else: await interaction.response.send_message("Something went wrong.", ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(PanelCog(bot))
