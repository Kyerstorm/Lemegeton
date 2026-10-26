"""Guild-scoped release digests built only from provider-supplied dates."""
from __future__ import annotations

import asyncio
import json
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any

import aiohttp
import discord
from discord import app_commands
from discord.ext import commands, tasks

from database import execute_db_operation
from helpers.anilist_helper import post_graphql
from cogs_test.general_commands.dashboard import command_meta

log = logging.getLogger(__name__)

ANILIST_AIRINGS = """
query($from: Int, $to: Int) {
  Page(page: 1, perPage: 50) {
    airingSchedules(airingAt_greater: $from, airingAt_lesser: $to, sort: TIME) {
      airingAt
      episode
      media { title { romaji english } siteUrl coverImage { large } isAdult }
    }
  }
}
"""
ALLOWED_CATEGORIES = {"anime", "movies", "tv"}
TMDB_BASE = "https://api.themoviedb.org/3"
TMDB_IMAGE = "https://image.tmdb.org/t/p/w342"


def normalize_categories(value: str | list[str] | tuple[str, ...] | set[str]) -> list[str]:
    """Normalize a comma-separated category selection, rejecting unknown values."""
    if isinstance(value, str):
        values = value.split(",")
    else:
        values = list(value)
    categories = []
    for part in values:
        category = str(part).strip().lower()
        if category and category not in ALLOWED_CATEGORIES:
            raise ValueError(f"Unsupported release-calendar category: {category}")
        if category and category not in categories:
            categories.append(category)
    if not categories:
        raise ValueError("Choose at least one of anime, movies, or tv.")
    return categories


def date_is_in_window(value: str | None, start: datetime, end: datetime) -> bool:
    """Return whether an ISO date falls within an inclusive UTC calendar window."""
    if not value:
        return False
    try:
        release_date = datetime.strptime(value[:10], "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return False
    return start.date() <= release_date.date() <= end.date()


def _title(record: dict[str, Any], tv: bool = False) -> str:
    return str(record.get("name" if tv else "title") or record.get("original_name" if tv else "original_title") or "Untitled").strip()


class ReleaseCalendar(commands.Cog):
    """Sends daily or weekly, multi-guild release digests."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._feed_cache: dict[tuple[str, ...], tuple[float, list[dict[str, Any]]]] = {}
        self._feed_lock = asyncio.Lock()

    async def cog_load(self) -> None:
        await execute_db_operation(
            "create guild release calendar settings",
            """CREATE TABLE IF NOT EXISTS media_release_calendar_settings (
                guild_id BIGINT PRIMARY KEY,
                channel_id BIGINT NOT NULL,
                frequency TEXT NOT NULL,
                categories TEXT NOT NULL,
                enabled INTEGER NOT NULL DEFAULT 1,
                next_run TIMESTAMP NOT NULL,
                updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            )""",
        )
        if not self.dispatch_due_digests.is_running():
            self.dispatch_due_digests.start()

    async def cog_unload(self) -> None:
        self.dispatch_due_digests.cancel()

    async def _get_json(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any] | None:
        token = os.getenv("TMDB_BEARER_TOKEN", "").strip()
        if not token:
            return None
        headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=8)) as session:
                async with session.get(f"{TMDB_BASE}{path}", params=params or {}, headers=headers) as response:
                    if response.status != 200:
                        log.warning("TMDB release-calendar endpoint %s returned HTTP %s", path, response.status)
                        return None
                    payload = await response.json(content_type=None)
                    return payload if isinstance(payload, dict) else None
        except (aiohttp.ClientError, asyncio.TimeoutError, ValueError):
            log.warning("TMDB release-calendar request failed for %s", path, exc_info=True)
            return None

    async def _anime_airings(self, start: datetime, end: datetime) -> list[dict[str, Any]]:
        lower, upper = int(start.timestamp()), int(end.timestamp()) + 1
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=12)) as session:
                payload = await post_graphql(session, ANILIST_AIRINGS, {"from": lower, "to": upper}, timeout=12)
        except (aiohttp.ClientError, asyncio.TimeoutError, ValueError):
            log.warning("AniList airing calendar request failed", exc_info=True)
            return []
        schedule = ((payload or {}).get("Page") or {}).get("airingSchedules") or []
        items = []
        for entry in schedule:
            media = entry.get("media") or {}
            if media.get("isAdult") is True:
                continue
            title = _title({"title": (media.get("title") or {})})
            try:
                when = datetime.fromtimestamp(int(entry["airingAt"]), timezone.utc)
            except (KeyError, TypeError, ValueError, OSError):
                continue
            items.append({
                "category": "Anime", "title": title, "date": when,
                "detail": f"Episode {entry.get('episode', '?')}",
                "url": media.get("siteUrl"), "image": (media.get("coverImage") or {}).get("large"),
                "source": "AniList",
            })
        return items

    async def _movie_releases(self, start: datetime, end: datetime) -> list[dict[str, Any]]:
        payload = await self._get_json("/movie/upcoming", {"language": "en-US", "region": "US", "page": 1})
        items = []
        for movie in (payload or {}).get("results", [])[:30]:
            release = movie.get("release_date")
            if movie.get("adult") is True or not date_is_in_window(release, start, end):
                continue
            try:
                when = datetime.strptime(release[:10], "%Y-%m-%d").replace(tzinfo=timezone.utc)
            except (TypeError, ValueError):
                continue
            movie_id = movie.get("id")
            items.append({
                "category": "Movie", "title": _title(movie), "date": when,
                "detail": (movie.get("overview") or "Synopsis unavailable.")[:240],
                "url": f"https://www.themoviedb.org/movie/{movie_id}" if movie_id else None,
                "image": f"{TMDB_IMAGE}{movie['poster_path']}" if movie.get("poster_path") else None,
                "source": "TMDB",
            })
        return items

    async def _tv_episode_releases(self, start: datetime, end: datetime) -> list[dict[str, Any]]:
        payload = await self._get_json("/tv/on_the_air", {"language": "en-US", "page": 1})
        shows = (payload or {}).get("results", [])[:8]
        if not shows:
            return []

        async def fetch_show(show: dict[str, Any]) -> dict[str, Any] | None:
            show_id = show.get("id")
            if not show_id:
                return None
            details = await self._get_json(f"/tv/{show_id}", {"language": "en-US"})
            return details if isinstance(details, dict) else None

        # Keep the number of detail requests bounded; each request has a firm timeout.
        details_list = await asyncio.gather(*(fetch_show(show) for show in shows), return_exceptions=True)
        items = []
        for details in details_list:
            if not isinstance(details, dict):
                continue
            episode = details.get("next_episode_to_air") or {}
            release = episode.get("air_date")
            if details.get("adult") is True or not date_is_in_window(release, start, end):
                continue
            try:
                when = datetime.strptime(release[:10], "%Y-%m-%d").replace(tzinfo=timezone.utc)
            except (TypeError, ValueError):
                continue
            show_id = details.get("id")
            episode_name = episode.get("name") or "Upcoming episode"
            season = episode.get("season_number")
            number = episode.get("episode_number")
            numbers = f" · S{season:02d}E{number:02d}" if isinstance(season, int) and isinstance(number, int) else ""
            items.append({
                "category": "TV", "title": _title(details, tv=True), "date": when,
                "detail": f"{episode_name}{numbers}",
                "url": f"https://www.themoviedb.org/tv/{show_id}" if show_id else None,
                "image": f"{TMDB_IMAGE}{details['poster_path']}" if details.get("poster_path") else None,
                "source": "TMDB",
            })
        return items

    async def fetch_feed(self, categories: list[str] | str, days: int = 7) -> list[dict[str, Any]]:
        """Fetch and cache a bounded future window, retaining provider attribution."""
        window_days = max(1, min(int(days), 14))
        normalized = tuple(sorted(normalize_categories(categories))) + (f"days:{window_days}",)
        now = datetime.now(timezone.utc)
        cached = self._feed_cache.get(normalized)
        if cached and cached[0] > now.timestamp():
            return list(cached[1])
        async with self._feed_lock:
            cached = self._feed_cache.get(normalized)
            if cached and cached[0] > now.timestamp():
                return list(cached[1])
            end = now + timedelta(days=window_days)
            jobs = []
            if "anime" in normalized:
                jobs.append(self._anime_airings(now, end))
            if "movies" in normalized:
                jobs.append(self._movie_releases(now, end))
            if "tv" in normalized:
                jobs.append(self._tv_episode_releases(now, end))
            resolved = await asyncio.gather(*jobs, return_exceptions=True)
            items: list[dict[str, Any]] = []
            for result in resolved:
                if isinstance(result, Exception):
                    log.warning("One release-calendar provider failed: %r", result)
                    continue
                items.extend(result)
            items.sort(key=lambda item: (item["date"], item["category"], item["title"].casefold()))
            self._feed_cache[normalized] = (now.timestamp() + 600, items)
            return list(items)

    @staticmethod
    def build_embed(items: list[dict[str, Any]], title: str = "Release Calendar") -> discord.Embed:
        embed = discord.Embed(
            title=f"🗓️ {title}",
            description="Provider-verified anime airings, film release dates, and TV next-episode dates. Entries without a usable date are omitted.",
            color=discord.Color.blurple(),
        )
        if not items:
            embed.description = "No supported provider returned a release date in this window. Novel and manga release announcements are not included unless a provider exposes a verifiable date."
            embed.set_footer(text="Sources: AniList · TMDB")
            return embed
        lines = []
        for item in items[:25]:
            date = item["date"]
            label = f"**{item['category']}** · <t:{int(date.timestamp())}:D> · {item['title']}"
            detail = item.get("detail")
            url = item.get("url")
            if url:
                label = f"[{label}]({url})"
            if detail:
                label += f"\n{str(detail)[:240]}"
            label += f" · {item['source']}"
            lines.append(label)
        embed.description = "\n\n".join(lines)[:4000]
        embed.set_footer(text=f"{len(items)} dated items · Sources are listed per entry · AniList · TMDB")
        images = next((item.get("image") for item in items if item.get("image")), None)
        if images:
            embed.set_thumbnail(url=images)
        return embed

    calendar = app_commands.Group(name="release-calendar", description="Configure provider-backed release digests")

    @calendar.command(name="configure", description="Set this server's release digest channel and schedule")
    @app_commands.guild_only()
    @app_commands.choices(frequency=[
        app_commands.Choice(name="Daily", value="daily"),
        app_commands.Choice(name="Weekly", value="weekly"),
    ])
    @app_commands.describe(
        channel="Channel where the digest should be sent",
        frequency="How often the server receives a digest",
        categories="Comma-separated categories: anime,movies,tv",
    )
    @app_commands.checks.has_permissions(manage_guild=True)
    @command_meta(section="Community", name="Release Calendar Configure")
    async def configure(self, interaction: discord.Interaction, channel: discord.TextChannel, frequency: str = "weekly", categories: str = "anime,movies,tv") -> None:
        if interaction.guild is None:
            await interaction.response.send_message("This setting is server-specific.", ephemeral=True)
            return
        try:
            normalized = normalize_categories(categories)
        except ValueError as exc:
            await interaction.response.send_message(str(exc), ephemeral=True)
            return
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        next_run = now + timedelta(days=1 if frequency == "daily" else 7)
        try:
            existing = await execute_db_operation(
                "check existing guild release-calendar settings",
                "SELECT guild_id FROM media_release_calendar_settings WHERE guild_id = ?",
                (interaction.guild.id,), fetch_type="one",
            )
            if existing:
                await execute_db_operation(
                    "update guild release-calendar settings",
                    "UPDATE media_release_calendar_settings SET channel_id = ?, frequency = ?, categories = ?, enabled = 1, next_run = ?, updated_at = CURRENT_TIMESTAMP WHERE guild_id = ?",
                    (channel.id, frequency, json.dumps(normalized), next_run, interaction.guild.id),
                )
            else:
                await execute_db_operation(
                    "insert guild release-calendar settings",
                    "INSERT INTO media_release_calendar_settings (guild_id, channel_id, frequency, categories, enabled, next_run) VALUES (?, ?, ?, ?, 1, ?)",
                    (interaction.guild.id, channel.id, frequency, json.dumps(normalized), next_run),
                )
        except Exception:
            log.exception("Could not save release-calendar settings for guild %s", interaction.guild.id)
            await interaction.response.send_message("The release-calendar settings could not be saved. Check database availability and try again.", ephemeral=True)
            return
        await interaction.response.send_message(
            f"✅ Release digests configured for <#{channel.id}> ({frequency}). Categories: {', '.join(normalized)}. The first digest is scheduled for <t:{int(next_run.replace(tzinfo=timezone.utc).timestamp())}:F>.",
            ephemeral=True,
        )

    @calendar.command(name="disable", description="Disable this server's release digest")
    @app_commands.guild_only()
    @app_commands.checks.has_permissions(manage_guild=True)
    @command_meta(section="Community", name="Release Calendar Disable")
    async def disable(self, interaction: discord.Interaction) -> None:
        if interaction.guild is None:
            await interaction.response.send_message("This setting is server-specific.", ephemeral=True)
            return
        await execute_db_operation(
            "disable guild release calendar",
            "UPDATE media_release_calendar_settings SET enabled = 0 WHERE guild_id = ?",
            (interaction.guild.id,),
        )
        await interaction.response.send_message("Release digests are disabled for this server.", ephemeral=True)

    @calendar.command(name="preview", description="Preview the next seven days of supported release dates")
    @app_commands.guild_only()
    @app_commands.describe(categories="Comma-separated categories: anime,movies,tv")
    @command_meta(section="Community", name="Release Calendar Preview")
    async def preview(self, interaction: discord.Interaction, categories: str = "anime,movies,tv") -> None:
        try:
            normalized = normalize_categories(categories)
        except ValueError as exc:
            await interaction.response.send_message(str(exc), ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            items = await self.fetch_feed(normalized, 7)
        except Exception:
            log.exception("Release-calendar preview failed")
            await interaction.followup.send("The release providers could not be queried right now. Please try again later.", ephemeral=True)
            return
        await interaction.followup.send(embed=self.build_embed(items, "Release Calendar Preview"), ephemeral=True)

    @tasks.loop(seconds=60)
    async def dispatch_due_digests(self) -> None:
        rows = await execute_db_operation(
            "find due release-calendar digests",
            "SELECT * FROM media_release_calendar_settings WHERE enabled = 1 AND next_run <= CURRENT_TIMESTAMP",
            fetch_type="all",
        )
        for row in rows or []:
            settings = dict(row)
            guild_id = int(settings["guild_id"])
            channel_id = int(settings["channel_id"])
            frequency = str(settings.get("frequency") or "weekly")
            try:
                categories = normalize_categories(json.loads(settings.get("categories") or "[]"))
                items = await self.fetch_feed(categories, 7)
                channel = self.bot.get_channel(channel_id)
                if channel is None:
                    guild = self.bot.get_guild(guild_id)
                    channel = guild.get_channel(channel_id) if guild else None
                if channel is None:
                    log.warning("Configured release-calendar channel %s no longer exists", channel_id)
                else:
                    await channel.send(embed=self.build_embed(items), allowed_mentions=discord.AllowedMentions.none())
            except Exception:
                log.exception("Release digest delivery failed for guild %s", guild_id)
            finally:
                delay = timedelta(days=1 if frequency == "daily" else 7)
                await execute_db_operation(
                    "advance guild release-calendar schedule",
                    "UPDATE media_release_calendar_settings SET next_run = ?, updated_at = CURRENT_TIMESTAMP WHERE guild_id = ?",
                    (datetime.now(timezone.utc).replace(tzinfo=None) + delay, guild_id),
                )

    @dispatch_due_digests.before_loop
    async def before_dispatch_due_digests(self) -> None:
        await self.bot.wait_until_ready()


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(ReleaseCalendar(bot))
