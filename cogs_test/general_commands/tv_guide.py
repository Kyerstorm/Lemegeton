"""TMDB-backed TV season and episode guide."""
from __future__ import annotations

import asyncio
import logging
import os

import aiohttp
import discord
from discord import app_commands
from discord.ext import commands

from cogs.media.browse import BrowseCog, TMDB_API_BASE_URL, TMDB_IMAGE_BASE_URL
from helpers.command_error_handler import FeedbackAwareView
from cogs_test.general_commands.dashboard import command_meta

log = logging.getLogger(__name__)


def episode_line(episode: dict) -> str:
    number = episode.get("episode_number", "?")
    name = str(episode.get("name") or "Untitled episode")
    date = str(episode.get("air_date") or "Date not announced")
    runtime = episode.get("runtime")
    runtime_text = f" · {runtime} min" if isinstance(runtime, int) and runtime > 0 else ""
    overview = " ".join(str(episode.get("overview") or "Synopsis unavailable.").split())
    if len(overview) > 220:
        overview = overview[:217].rstrip() + "..."
    return f"**E{number}: {name}** · {date}{runtime_text}\n||{overview}||"


def season_embed(show: dict, season: dict, page: int = 0) -> discord.Embed:
    episodes = season.get("episodes") or []
    page_size = 6
    start = page * page_size
    visible = episodes[start:start + page_size]
    show_name = str(show.get("name") or "TV series")
    season_name = str(season.get("name") or f"Season {season.get('season_number', '?')}")
    description = "\n\n".join(episode_line(episode) for episode in visible) or "TMDB has not listed episodes for this season."
    embed = discord.Embed(
        title=f"📺 {show_name} · {season_name}"[:256],
        url=f"https://www.themoviedb.org/tv/{show.get('id')}/season/{season.get('season_number')}" if show.get("id") and season.get("season_number") is not None else None,
        description=description[:4000],
        color=discord.Color.blurple(),
    )
    poster = season.get("poster_path") or show.get("poster_path")
    if poster:
        embed.set_thumbnail(url=f"{TMDB_IMAGE_BASE_URL}/w500{poster}")
    if episodes:
        embed.set_footer(text=f"TMDB episode data · Page {page + 1}/{max(1, (len(episodes) - 1) // page_size + 1)} · Episode synopses are spoiler-marked")
    else:
        embed.set_footer(text="Source: TMDB · No episode entries supplied")
    return embed


class TVSeasonView(FeedbackAwareView):
    def __init__(self, owner_id: int, show: dict, season: dict):
        super().__init__(timeout=180)
        self.owner_id = owner_id
        self.show = show
        self.season = season
        self.page = 0
        self.max_page = max(0, (len(season.get("episodes") or []) - 1) // 6)
        self.previous.disabled = True
        self.next.disabled = self.max_page == 0

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message("Only the user who requested this guide can navigate it.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="◀ Previous episodes", style=discord.ButtonStyle.secondary)
    async def previous(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        self.page = max(0, self.page - 1)
        self.previous.disabled = self.page == 0
        self.next.disabled = self.page >= self.max_page
        await interaction.response.edit_message(embed=season_embed(self.show, self.season, self.page), view=self)

    @discord.ui.button(label="Next episodes ▶", style=discord.ButtonStyle.secondary)
    async def next(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        self.page = min(self.max_page, self.page + 1)
        self.previous.disabled = self.page == 0
        self.next.disabled = self.page >= self.max_page
        await interaction.response.edit_message(embed=season_embed(self.show, self.season, self.page), view=self)


class TVGuide(commands.Cog):
    """TV season guide using TMDB's documented title and season endpoints."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.browse = BrowseCog(bot)

    async def fetch_season(self, show_id: int, season_number: int) -> dict | None:
        token = os.getenv("TMDB_BEARER_TOKEN", "").strip()
        if not token:
            return None
        headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=12)) as session:
                async with session.get(
                    f"{TMDB_API_BASE_URL}/tv/{show_id}/season/{season_number}",
                    headers=headers,
                    params={"language": "en-US"},
                ) as response:
                    if response.status != 200:
                        log.info("TMDB season %s for show %s returned HTTP %s", season_number, show_id, response.status)
                        return None
                    data = await response.json(content_type=None)
                    return data if isinstance(data, dict) else None
        except (aiohttp.ClientError, asyncio.TimeoutError, ValueError):
            log.warning("TMDB season lookup failed for show %s season %s", show_id, season_number, exc_info=True)
            return None

    @app_commands.command(name="tv-guide", description="Browse TMDB TV seasons, episode dates, runtimes, cast, and status")
    @app_commands.guild_only()
    @app_commands.describe(title="TV series title", season="Optional season number from the series overview")
    @command_meta(section="Media Discovery", name="TV Guide")
    async def tv_guide(self, interaction: discord.Interaction, title: str, season: app_commands.Range[int, 0, 100] | None = None) -> None:
        title = " ".join((title or "").split())
        if not title:
            await interaction.response.send_message("Enter a TV series title.", ephemeral=True)
            return
        if not os.getenv("TMDB_BEARER_TOKEN", "").strip():
            await interaction.response.send_message("The TV guide requires TMDB_BEARER_TOKEN.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            results = await self.browse.search_tmdb_titles(title, "TV")
            selected = self.browse.choose_best_title_match(
                results, title,
                lambda item: (item.get("name"), item.get("original_name")),
            )
            if not selected:
                await interaction.followup.send("TMDB did not return a matching TV series.", ephemeral=True)
                return
            details = await self.browse.fetch_tmdb_media(
                str(selected.get("name") or selected.get("original_name") or title), "TV"
            )
            if not details:
                await interaction.followup.send("TMDB could not load the selected series details.", ephemeral=True)
                return
        except (aiohttp.ClientError, asyncio.TimeoutError, ValueError, KeyError):
            log.exception("TV guide lookup failed for %r", title)
            await interaction.followup.send("TMDB failed while loading this series. Please try again later.", ephemeral=True)
            return

        show_title = str(details.get("name") or "TV series")
        seasons = details.get("seasons") or []
        tmdb_url = f"https://www.themoviedb.org/tv/{details.get('id')}" if details.get("id") else None
        if season is not None:
            if not any(item.get("season_number") == season for item in seasons):
                available = ", ".join(str(item.get("season_number")) for item in seasons if item.get("season_number") is not None) or "none listed"
                await interaction.followup.send(f"Season {season} was not listed by TMDB for **{show_title}**. Available season numbers: {available}.", ephemeral=True)
                return
            season_data = await self.fetch_season(int(details["id"]), season)
            if not season_data:
                await interaction.followup.send("TMDB did not return episode details for that season.", ephemeral=True)
                return
            view = TVSeasonView(interaction.user.id, details, season_data)
            await interaction.followup.send(embed=season_embed(details, season_data), view=view, ephemeral=True)
            return

        embed = discord.Embed(
            title=f"📺 {show_title}"[:256],
            url=tmdb_url,
            description=str(details.get("overview") or "No synopsis is available.")[:900],
            color=discord.Color.blurple(),
        )
        poster = details.get("poster_path")
        if poster:
            embed.set_thumbnail(url=f"{TMDB_IMAGE_BASE_URL}/w500{poster}")
        for label, value in (
            ("Status", details.get("status")),
            ("Original language", details.get("original_language")),
            ("First air date", details.get("first_air_date")),
            ("Last air date", details.get("last_air_date")),
            ("Seasons", details.get("number_of_seasons")),
            ("Episodes", details.get("number_of_episodes")),
        ):
            if value is not None and value != "":
                embed.add_field(name=label, value=str(value)[:1024], inline=True)
        runtimes = details.get("episode_run_time") or []
        if runtimes:
            embed.add_field(name="Episode runtime", value=", ".join(f"{value} min" for value in runtimes[:6]), inline=True)
        creators = [entry.get("name") for entry in (details.get("created_by") or []) if entry.get("name")]
        if creators:
            embed.add_field(name="Created by", value=", ".join(creators[:8])[:1024], inline=False)
        networks = [entry.get("name") for entry in (details.get("networks") or []) if entry.get("name")]
        if networks:
            embed.add_field(name="Networks", value=", ".join(networks[:8])[:1024], inline=False)
        credits = details.get("aggregate_credits") or details.get("credits") or {}
        cast = [entry.get("name") for entry in (credits.get("cast") or [])[:10] if entry.get("name")]
        if cast:
            embed.add_field(name="Cast", value=", ".join(cast)[:1024], inline=False)
        ratings = (details.get("content_ratings") or {}).get("results") or []
        us_rating = next((entry.get("rating") for entry in ratings if entry.get("iso_3166_1") == "US" and entry.get("rating")), None)
        if us_rating:
            embed.add_field(name="US content rating", value=us_rating, inline=True)
        next_episode = details.get("next_episode_to_air") or {}
        if next_episode:
            episode_date = next_episode.get("air_date") or "Date unavailable"
            episode_name = next_episode.get("name") or "Upcoming episode"
            number = next_episode.get("episode_number")
            season_number = next_episode.get("season_number")
            identifier = f"S{season_number:02d}E{number:02d}" if isinstance(season_number, int) and isinstance(number, int) else ""
            label = f"**{episode_name}** {identifier} · {episode_date}"
            if details.get("id"):
                label += f"\n[Open TMDB series guide]({tmdb_url})"
            embed.add_field(name="Next episode", value=label[:1024], inline=False)
        season_lines = []
        for entry in seasons[:18]:
            name = str(entry.get("name") or f"Season {entry.get('season_number', '?')}")
            number = entry.get("season_number")
            episodes = entry.get("episode_count")
            first_air = entry.get("air_date") or "Date not listed"
            season_lines.append(f"**{name}** (#{number}) · {episodes if episodes is not None else '?'} episodes · {first_air}")
        if season_lines:
            embed.add_field(name="Seasons", value="\n".join(season_lines)[:1024], inline=False)
        embed.set_footer(text="Metadata and episode availability from TMDB · Episode descriptions are spoiler-marked in season views")
        await interaction.followup.send(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(TVGuide(bot))
