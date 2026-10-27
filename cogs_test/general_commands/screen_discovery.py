"""Advanced TMDB movie and television discovery filters."""
from __future__ import annotations

import asyncio
import logging
import os
import re
from typing import Any

import aiohttp
import discord
from discord import app_commands
from discord.ext import commands

from cogs_test.general_commands.dashboard import command_meta

log = logging.getLogger("screen_discovery")
TMDB_BASE_URL = "https://api.themoviedb.org/3"
TMDB_IMAGE_BASE_URL = "https://image.tmdb.org/t/p/w500"

MOVIE_GENRES = {
    "action": 28, "adventure": 12, "animation": 16, "comedy": 35,
    "crime": 80, "documentary": 99, "drama": 18, "family": 10751,
    "fantasy": 14, "history": 36, "horror": 27, "music": 10402,
    "mystery": 9648, "romance": 10749, "science fiction": 878,
    "sci fi": 878, "thriller": 53, "war": 10752, "western": 37,
    "tv movie": 10770,
}
TV_GENRES = {
    "action": 10759, "action and adventure": 10759, "adventure": 10759,
    "animation": 16, "comedy": 35, "crime": 80, "documentary": 99,
    "drama": 18, "family": 10751, "kids": 10762, "mystery": 9648,
    "news": 10763, "reality": 10764, "sci fi and fantasy": 10765,
    "science fiction and fantasy": 10765, "soap": 10766,
    "talk": 10767, "war and politics": 10768, "western": 37,
}
SORT_OPTIONS = {
    "popularity": "popularity.desc",
    "rating": "vote_average.desc",
    "votes": "vote_count.desc",
}


def _genre_key(value: str) -> str:
    value = (value or "").strip().casefold().replace("&", " and ")
    return re.sub(r"[\s-]+", " ", value).strip()


def build_discover_params(
    media_type: str,
    sort_by: str = "popularity",
    genre: str | None = None,
    year: int | None = None,
    minimum_rating: float | None = None,
    language: str | None = None,
    region: str = "IE",
) -> dict[str, Any]:
    """Validate options and build a TMDB /discover request without network access."""
    category = (media_type or "").strip().upper()
    if category not in {"MOVIE", "TV"}:
        raise ValueError("Choose either Movies or TV series.")
    sort_key = (sort_by or "popularity").strip().casefold()
    if sort_key not in {*SORT_OPTIONS, "newest"}:
        raise ValueError("Sort by popularity, rating, votes, or newest.")
    params: dict[str, Any] = {
        "language": "en-US",
        "page": 1,
        "include_adult": "false",
        "sort_by": (
            "primary_release_date.desc" if category == "MOVIE" else "first_air_date.desc"
        ) if sort_key == "newest" else SORT_OPTIONS[sort_key],
    }

    if genre and genre.strip():
        genre_map = MOVIE_GENRES if category == "MOVIE" else TV_GENRES
        genre_id = genre_map.get(_genre_key(genre))
        if genre_id is None:
            choices = ", ".join(sorted(genre_map))
            raise ValueError(f"Unsupported {category.lower()} genre. Examples: {choices}.")
        params["with_genres"] = genre_id

    if year is not None:
        if isinstance(year, bool) or not 1888 <= int(year) <= 2100:
            raise ValueError("Year must be between 1888 and 2100.")
        params["primary_release_year" if category == "MOVIE" else "first_air_date_year"] = int(year)

    if minimum_rating is not None:
        rating = float(minimum_rating)
        if not 0.0 <= rating <= 10.0:
            raise ValueError("Minimum rating must be between 0 and 10.")
        params["vote_average.gte"] = rating
    if sort_key == "rating":
        params["vote_count.gte"] = 50

    if language and language.strip():
        language_code = language.strip().casefold()
        if not re.fullmatch(r"[a-z]{2}", language_code):
            raise ValueError("Original language must be a two-letter code, such as en, ja, ko, or fr.")
        params["with_original_language"] = language_code

    country = (region or "IE").strip().upper()
    if not re.fullmatch(r"[A-Z]{2}", country):
        raise ValueError("Region must be a two-letter country code, such as IE, GB, or US.")
    if category == "MOVIE":
        params["region"] = country
    return params


class ScreenDiscovery(commands.Cog):
    """Discover films and television using TMDB's supported discover filters."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(
        name="screen-discover",
        description="Discover films or TV by genre, year, rating, language, and sort order",
    )
    @app_commands.guild_only()
    @app_commands.choices(
        media_type=[
            app_commands.Choice(name="Movies", value="MOVIE"),
            app_commands.Choice(name="TV series", value="TV"),
        ],
        sort_by=[
            app_commands.Choice(name="Most popular", value="popularity"),
            app_commands.Choice(name="Highest rated", value="rating"),
            app_commands.Choice(name="Most votes", value="votes"),
            app_commands.Choice(name="Newest first", value="newest"),
        ],
    )
    @app_commands.describe(
        media_type="Discover movies or television series",
        sort_by="How matching titles should be ordered",
        genre="A TMDB genre, for example science fiction, fantasy, or drama",
        year="Filter by release year (movie) or first-air year (TV)",
        minimum_rating="Minimum TMDB user rating from 0 to 10",
        language="Optional original-language code, for example en, ja, ko, or fr",
    )
    @command_meta(section="Media Discovery", name="Screen Discovery")
    async def screen_discover(
        self,
        interaction: discord.Interaction,
        media_type: str,
        sort_by: str = "popularity",
        genre: str | None = None,
        year: int | None = None,
        minimum_rating: float | None = None,
        language: str | None = None,
    ) -> None:
        if not os.getenv("TMDB_BEARER_TOKEN", "").strip():
            await interaction.response.send_message(
                "Movie and TV discovery requires the TMDB_BEARER_TOKEN configuration.",
                ephemeral=True,
            )
            return
        try:
            build_discover_params(media_type, sort_by, genre, year, minimum_rating, language)
        except (TypeError, ValueError) as exc:
            await interaction.response.send_message(str(exc), ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True, thinking=True)
        region = "IE"
        if media_type.upper() == "MOVIE" and interaction.guild_id:
            region_cog = self.bot.get_cog("ConnectedMedia")
            getter = getattr(region_cog, "_default_region", None)
            if callable(getter):
                try:
                    configured_region = await getter(interaction.guild_id)
                    if isinstance(configured_region, str) and re.fullmatch(r"[A-Za-z]{2}", configured_region.strip()):
                        region = configured_region.strip().upper()
                except Exception:
                    log.warning("Could not resolve guild %s media region; using IE", interaction.guild_id, exc_info=True)
        params = build_discover_params(media_type, sort_by, genre, year, minimum_rating, language, region)
        token = os.getenv("TMDB_BEARER_TOKEN", "").strip()
        endpoint = "movie" if media_type.upper() == "MOVIE" else "tv"
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as session:
                async with session.get(
                    f"{TMDB_BASE_URL}/discover/{endpoint}",
                    headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
                    params=params,
                ) as response:
                    if response.status != 200:
                        log.warning("TMDB discover/%s returned HTTP %s", endpoint, response.status)
                        await interaction.followup.send(
                            f"TMDB could not complete this discovery request (HTTP {response.status}). Try again later.",
                            ephemeral=True,
                        )
                        return
                    payload = await response.json(content_type=None)
        except (aiohttp.ClientError, asyncio.TimeoutError, ValueError):
            log.warning("TMDB discover request failed for %s", endpoint, exc_info=True)
            await interaction.followup.send(
                "TMDB is unavailable right now. Please try the discovery search again later.",
                ephemeral=True,
            )
            return

        results = [
            item for item in (payload.get("results") or [])
            if isinstance(item, dict) and item.get("id")
        ] if isinstance(payload, dict) else []
        if not results:
            await interaction.followup.send(
                "No TMDB titles matched these filters. Try a broader genre, year, rating, or language.",
                ephemeral=True,
            )
            return

        heading = "Movies" if endpoint == "movie" else "TV series"
        sort_labels = {"popularity": "Most popular", "rating": "Highest rated", "votes": "Most votes", "newest": "Newest first"}
        embed = discord.Embed(
            title=f"🎬 Screen Discovery · {heading}",
            description=(
                f"Sorted by **{sort_labels[sort_by]}**. "
                f"Results are sourced from TMDB's discover endpoint"
                + (f" for **{region}**." if endpoint == "movie" else ".")
            ),
            color=discord.Color.from_rgb(86, 112, 165),
        )
        shown = 0
        for item in results[:5]:
            title_value = item.get("title") if endpoint == "movie" else item.get("name")
            title = str(title_value or "Untitled")
            date_value = item.get("release_date") if endpoint == "movie" else item.get("first_air_date")
            year_label = str(date_value)[:4] if date_value else "year unknown"
            try:
                score = float(item.get("vote_average"))
                rating_text = f"⭐ {score:.1f}/10"
            except (TypeError, ValueError):
                rating_text = "⭐ Rating unavailable"
            try:
                vote_count = max(0, int(item.get("vote_count") or 0))
            except (TypeError, ValueError):
                vote_count = 0
            overview = discord.utils.escape_markdown(
                str(item.get("overview") or "No synopsis supplied by TMDB.").strip()
            )[:550]
            title_text = discord.utils.escape_markdown(title)[:180]
            embed.add_field(
                name=f"{shown + 1}. {title_text} · {year_label}"[:256],
                value=f"{rating_text} · {vote_count:,} votes\n{overview}",
                inline=False,
            )
            if shown == 0 and item.get("poster_path"):
                embed.set_thumbnail(url=f"{TMDB_IMAGE_BASE_URL}{item['poster_path']}")
            shown += 1

        embed.set_footer(text=f"TMDB · Showing {shown} results from the first results page · Rating and dates may be unavailable")
        await interaction.followup.send(
            embed=embed,
            ephemeral=True,
            allowed_mentions=discord.AllowedMentions.none(),
        )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(ScreenDiscovery(bot))
