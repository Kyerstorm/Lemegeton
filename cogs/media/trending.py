import discord
from discord.ext import commands
from discord import app_commands
import aiohttp
import asyncio
import random
import re
import logging
import os
from pathlib import Path
from cogs_test.general_commands.dashboard import command_meta
from helpers.embed_helper import build_error_embed, build_warning_embed
from helpers.anilist_helper import post_graphql

# ------------------------------------------------------
# Logging Setup - Clears on each bot run
# ------------------------------------------------------
LOG_DIR = Path("logs")
LOG_DIR.mkdir(exist_ok=True)
LOG_FILE = LOG_DIR / "trending.log"

# Clear the log file on startup (best-effort)
try:
    if LOG_FILE.exists():
        try:
            LOG_FILE.unlink()
        except PermissionError:
            # File is in use by another process; continue
            pass
except Exception:
    # Best-effort only; do not fail import
    pass

# Create logger
logger = logging.getLogger("Trending")
logger.setLevel(logging.INFO)

for handler in logger.handlers[:]:
    logger.removeHandler(handler)

try:
    file_handler = logging.FileHandler(LOG_FILE, encoding="utf-8")
    file_handler.setLevel(logging.INFO)
    formatter = logging.Formatter(
        "[%(asctime)s] [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
except Exception:
    stream = logging.StreamHandler()
    stream.setLevel(logging.INFO)
    stream.setFormatter(logging.Formatter("[%(asctime)s] [%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S"))
    logger.addHandler(stream)

logger.info("Trending cog logging initialized - log file cleared")

# ------------------------------------------------------
# Constants
# ------------------------------------------------------
# Type colors are contextual (type-based), keeping them for visual distinction
TYPE_COLORS = {
    "ANIME": 0x1E90FF, "MANGA": 0xFF69B4, "LN": 0x8A2BE2,
    "MOVIE": 0x4C78A8, "TV": 0x7A5195,
}
TYPE_ICONS = {"ANIME": "🎬", "MANGA": "📖", "LN": "📚", "MOVIE": "🎞️", "TV": "📺"}
REQUEST_TIMEOUT = 10
TMDB_API_BASE_URL = "https://api.themoviedb.org/3"
TMDB_IMAGE_BASE_URL = "https://image.tmdb.org/t/p"
TMDB_GENRE_IDS = {
    "MOVIE": {
        "action": 28, "adventure": 12, "animation": 16, "comedy": 35, "crime": 80,
        "documentary": 99, "drama": 18, "family": 10751, "fantasy": 14,
        "history": 36, "horror": 27, "mystery": 9648, "romance": 10749,
        "sci-fi": 878, "thriller": 53,
    },
    "TV": {
        "action": 10759, "adventure": 10759, "animation": 16, "comedy": 35,
        "crime": 80, "documentary": 99, "drama": 18, "family": 10751,
        "fantasy": 10765, "mystery": 9648, "sci-fi": 10765,
    },
}
ANI_LIST_GENRES = [
    "Action", "Adventure", "Comedy", "Drama", "Fantasy", "Horror",
    "Mystery", "Romance", "Sci-Fi", "Thriller", "Psychological",
]


class Trending(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        logger.info("Trending cog initialized")

    @app_commands.command(
        name="trending",
        description="🔥 View the currently trending anime, manga, or light novels on AniList"
    )
    @command_meta(section="Media", name="Trending")
    @app_commands.describe(
        media_type="Choose Anime, Manga, Light Novels, Movies, TV, or All",
        time_window="TMDB trending period for movies and TV",
        genre="Optional provider-supported genre filter",
        media_format="AniList format filter for anime or manga",
        season="AniList season filter (anime only)",
        season_year="AniList season year filter (anime only)",
    )
    @app_commands.choices(
        media_type=[
            app_commands.Choice(name="Anime 🎬", value="ANIME"),
            app_commands.Choice(name="Manga 📖", value="MANGA"),
            app_commands.Choice(name="Light Novels 📚", value="LN"),
            app_commands.Choice(name="Movies 🎞️", value="MOVIE"),
            app_commands.Choice(name="TV Shows 📺", value="TV"),
            app_commands.Choice(name="All 🌐", value="ALL")
        ],
        time_window=[
            app_commands.Choice(name="Today", value="day"),
            app_commands.Choice(name="This Week", value="week"),
        ],
        genre=[
            app_commands.Choice(name=genre, value=genre) for genre in ANI_LIST_GENRES
        ],
        media_format=[
            app_commands.Choice(name="TV", value="TV"),
            app_commands.Choice(name="TV Short", value="TV_SHORT"),
            app_commands.Choice(name="Movie", value="MOVIE"),
            app_commands.Choice(name="Special", value="SPECIAL"),
            app_commands.Choice(name="OVA", value="OVA"),
            app_commands.Choice(name="ONA", value="ONA"),
            app_commands.Choice(name="Manga", value="MANGA"),
            app_commands.Choice(name="Novel / Light Novel", value="NOVEL"),
            app_commands.Choice(name="One-shot", value="ONE_SHOT"),
        ],
        season=[
            app_commands.Choice(name="Winter", value="WINTER"),
            app_commands.Choice(name="Spring", value="SPRING"),
            app_commands.Choice(name="Summer", value="SUMMER"),
            app_commands.Choice(name="Fall", value="FALL"),
        ],
    )
    async def trending(
        self,
        interaction: discord.Interaction,
        media_type: app_commands.Choice[str] = None,
        time_window: app_commands.Choice[str] = None,
        genre: app_commands.Choice[str] = None,
        media_format: app_commands.Choice[str] = None,
        season: app_commands.Choice[str] = None,
        season_year: app_commands.Range[int, 1970, 2100] = None,
    ):
        selected_type = media_type.value if media_type else "ANIME"
        tmdb_window = time_window.value if time_window else "week"
        genre_value = genre.value if genre else None
        format_value = media_format.value if media_format else None
        season_value = season.value if season else None
        year_value = season_year
        logger.info("Trending command invoked by %s (%s), type=%s", interaction.user, interaction.user.id, selected_type)

        if time_window and selected_type not in ("MOVIE", "TV", "ALL"):
            await interaction.response.send_message(
                embed=build_warning_embed(
                    "Unsupported Time Window",
                    "Day/week trend windows are available for TMDB movies and TV. AniList shows its current trending ranking.",
                ),
                ephemeral=True,
            )
            return

        if (season_value or year_value is not None) and selected_type != "ANIME":
            await interaction.response.send_message(
                embed=build_warning_embed("Unsupported Filter", "Season and season-year filters are available for AniList anime only."),
                ephemeral=True,
            )
            return
        if format_value:
            allowed_formats = {
                "ANIME": {"TV", "TV_SHORT", "MOVIE", "SPECIAL", "OVA", "ONA"},
                "MANGA": {"MANGA", "ONE_SHOT", "NOVEL"},
                "LN": {"NOVEL"},
            }
            if selected_type not in allowed_formats or format_value not in allowed_formats[selected_type]:
                await interaction.response.send_message(
                    embed=build_warning_embed(
                        "Unsupported Format",
                        "Select a format compatible with the chosen AniList category; format filters cannot be combined with All, Movies, or TV.",
                    ),
                    ephemeral=True,
                )
                return
        if (season_value or year_value is not None) and format_value and format_value not in ("TV", "TV_SHORT", "MOVIE", "SPECIAL", "OVA", "ONA"):
            await interaction.response.send_message(
                embed=build_warning_embed("Conflicting Filters", "Anime season filters require an anime format."),
                ephemeral=True,
            )
            return
        if selected_type == "ALL" and (format_value or season_value or year_value is not None):
            await interaction.response.send_message(
                embed=build_warning_embed("Unsupported Filter", "Choose Anime, Manga, or Light Novels to use format/season filters."),
                ephemeral=True,
            )
            return
        if selected_type in ("MOVIE", "TV") and genre_value and genre_value.casefold() not in TMDB_GENRE_IDS[selected_type]:
            await interaction.response.send_message(
                embed=build_warning_embed(
                    "Unsupported Genre",
                    f"{genre_value} is not exposed as a separate genre for TMDB {selected_type.lower()} trending.",
                ),
                ephemeral=True,
            )
            return

        await interaction.response.defer()

        try:
            if selected_type == "ALL":
                media_types_to_fetch = [
                    ("ANIME", "ANIME"), ("MANGA", "MANGA"), ("MANGA", "LN"),
                    ("TMDB", "MOVIE"), ("TMDB", "TV"),
                ]
            elif selected_type in ("MOVIE", "TV"):
                media_types_to_fetch = [("TMDB", selected_type)]
            else:
                label = "LN" if selected_type == "MANGA" and format_value == "NOVEL" else selected_type
                fetch_type = "MANGA" if label in ("MANGA", "LN") else label
                media_types_to_fetch = [(fetch_type, label)]

            all_embeds = []
            for fetch_type, label in media_types_to_fetch:
                if fetch_type == "TMDB":
                    media_list = await self._fetch_tmdb_trending(label, tmdb_window, genre_value)
                else:
                    media_list = await self._fetch_trending(
                        fetch_type, label, genre=genre_value, media_format=format_value,
                        season=season_value, season_year=year_value,
                    )
                if not media_list:
                    logger.warning("No trending results found for %s", label)
                    continue
                for i, media in enumerate(media_list):
                    if fetch_type == "TMDB":
                        embed = self._build_tmdb_embed_entry(media, i + 1, label, tmdb_window)
                    else:
                        embed = self._build_embed_entry(media, i + 1, label)
                    all_embeds.append(embed)

            if not all_embeds:
                logger.warning(f"No trending results found for any requested types: {[label for _, label in media_types_to_fetch]}")
                embed = build_warning_embed(
                    "No Results Found",
                    "No trending results found."
                )
                await interaction.followup.send(embed=embed, ephemeral=True)
                return

            logger.info(f"Successfully created {len(all_embeds)} trending embeds for {interaction.user}")
            
            # Send with pagination if multiple results
            if len(all_embeds) == 1:
                await interaction.followup.send(embed=all_embeds[0])
            else:
                view = TrendingPaginatedView(all_embeds, interaction.user.id)
                await interaction.followup.send(embed=all_embeds[0], view=view)
                
            logger.info(f"Trending command completed successfully for {interaction.user}")

        except Exception as e:
            logger.error(f"Exception in trending command for {interaction.user} (ID: {interaction.user.id}): {e}", exc_info=True)
            embed = build_error_embed(
                "Error",
                "An error occurred while fetching trending data. Please try again later."
            )
            await interaction.followup.send(embed=embed, ephemeral=True)

    async def _fetch_tmdb_trending(self, media_type: str, window: str, genre: str | None = None):
        """Fetch TMDB day/week trends and narrow them only using the provider's genre IDs."""
        token = os.getenv("TMDB_BEARER_TOKEN", "").strip()
        if not token:
            logger.warning("TMDB trending is disabled because TMDB_BEARER_TOKEN is not configured")
            return []
        endpoint = "movie" if media_type == "MOVIE" else "tv"
        headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT)) as session:
                async with session.get(
                    f"{TMDB_API_BASE_URL}/trending/{endpoint}/{window}", headers=headers
                ) as response:
                    if response.status != 200:
                        logger.warning("TMDB trending %s returned HTTP %s", endpoint, response.status)
                        return []
                    payload = await response.json()
                    results = payload.get("results") if isinstance(payload, dict) else None
                    if not isinstance(results, list):
                        return []
                    if genre:
                        genre_id = TMDB_GENRE_IDS.get(media_type, {}).get(genre.casefold())
                        if genre_id is None:
                            return []
                        results = [
                            item for item in results
                            if genre_id in (item.get("genre_ids") or [])
                            or (
                                media_type == "TV" and genre.casefold() == "adventure"
                                and 10759 in (item.get("genre_ids") or [])
                            )
                        ]
                    return results
        except (aiohttp.ClientError, asyncio.TimeoutError, ValueError) as exc:
            logger.warning("TMDB trending lookup failed for %s: %s", endpoint, exc)
            return []

    def _build_tmdb_embed_entry(self, media: dict, rank: int, label: str, window: str):
        is_movie = label == "MOVIE"
        title = (media.get("title") if is_movie else media.get("name")) or "Unknown title"
        date_value = media.get("release_date") if is_movie else media.get("first_air_date")
        year = date_value[:4] if date_value else "Year unknown"
        media_id = media.get("id")
        endpoint = "movie" if is_movie else "tv"
        overview = (media.get("overview") or "No overview available.").strip()
        if len(overview) > 800:
            overview = overview[:797].rstrip() + "..."
        embed = discord.Embed(
            title=f"{TYPE_ICONS[label]} #{rank} • {title} ({year})"[:256],
            url=f"https://www.themoviedb.org/{endpoint}/{media_id}" if media_id else "https://www.themoviedb.org/",
            description=overview,
            color=discord.Color(TYPE_COLORS[label]),
        )
        if media.get("poster_path"):
            embed.set_thumbnail(url=f"{TMDB_IMAGE_BASE_URL}/w500{media['poster_path']}")
        if media.get("vote_average") is not None:
            score = f"{media['vote_average']:.1f}/10"
            if isinstance(media.get("vote_count"), int):
                score += f" • {media['vote_count']:,} votes"
            embed.add_field(name="TMDB User Rating", value=score, inline=True)
        embed.set_author(name=f"TMDB {window.title()} Trending", url="https://www.themoviedb.org/")
        embed.set_footer(text="Rank comes from TMDB's trending endpoint; TMDB rating is shown separately.")
        return embed

    async def _fetch_trending(
        self, fetch_type: str, label: str, genre: str | None = None,
        media_format: str | None = None, season: str | None = None,
        season_year: int | None = None,
    ):
        """Fetch AniList trending data with provider-supported filters."""
        query = """
        query (
          $type: MediaType, $format: MediaFormat, $genreIn: [String],
          $season: MediaSeason, $seasonYear: Int
        ) {
          Page(page: 1, perPage: 10) {
            media(
              type: $type, format: $format, genre_in: $genreIn,
              season: $season, seasonYear: $seasonYear, sort: TRENDING_DESC
            ) {
              id
              title { romaji english }
              format
              status
              episodes
              chapters
              genres
              averageScore
              description(asHtml: false)
              coverImage { large }
              siteUrl
              trending
            }
          }
        }
        """
        
        variables = {
            "type": fetch_type,
            "format": "NOVEL" if label == "LN" else media_format,
            "genreIn": [genre] if genre else None,
            "season": season if label == "ANIME" else None,
            "seasonYear": season_year if label == "ANIME" else None,
        }
        
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT)) as session:
                logger.info(f"Making API request to AniList for {label} trending data")
                data = await post_graphql(session, query, variables, timeout=REQUEST_TIMEOUT)
                
                if data is None:
                    logger.warning(f"AniList API returned None for {label}")
                    return []

                logger.info(f"Successfully received API response for {label}")

        except asyncio.TimeoutError:
            logger.error(f"Timeout while fetching {label} trending data", exc_info=True)
            return []
        except Exception as e:
            logger.error(f"Failed to fetch AniList trending data for {label}: {e}", exc_info=True)
            return []

        # Process response
        page_data = data.get("Page") if data else None
        if not page_data:
            logger.warning(f"No Page data returned from AniList for {label}: {data}")
            return []

        media_list = page_data.get("media", [])
        
        logger.info(f"Successfully processed {len(media_list)} {label} trending entries")
        return media_list

    def _build_embed_entry(self, media: dict, rank: int, label: str):
        """Build a Discord embed for a single trending media entry"""
        color = discord.Color(TYPE_COLORS.get(label, 0x00CED1))
        
        title_data = media.get("title") or {}
        title = title_data.get("english") or title_data.get("romaji") or "Unknown Title"
        url = media.get("siteUrl") or "#"
        trending_score = media.get("trending")
        trending_score_text = str(trending_score) if trending_score is not None else "N/A"
        format_ = media.get("format") or "Unknown"
        status = media.get("status") or "Unknown"
        episodes = media.get("episodes") or media.get("chapters") or "N/A"
        genres = ", ".join(media.get("genres") or []) or "N/A"
        raw_score = media.get("averageScore")
        avg_score = f"{raw_score}/100" if raw_score is not None else "N/A"

        # Clean description
        raw_desc = media.get("description") or "No description available"
        clean_desc = re.sub(r"<[^>]+>", "", raw_desc)
        clean_desc = (clean_desc[:500] + "...") if len(clean_desc) > 500 else clean_desc

        embed = discord.Embed(
            title=f"{TYPE_ICONS.get(label, '')} #{rank} • {title}",
            description=(
                f"**Trending Score:** {trending_score_text}\n"
                f"**Format:** {format_}\n"
                f"**Status:** {status}\n"
                f"**Episodes/Chapters:** {episodes}\n"
                f"**Genres:** {genres}\n"
                f"**Average Score:** {avg_score}\n\n"
                f"**Description:** {clean_desc}"
            ),
            color=color
        )

        cover_url = media.get("coverImage", {}).get("large")
        if cover_url:
            embed.set_thumbnail(url=cover_url)

        embed.set_author(
            name="AniList Trending",
            url="https://anilist.co/",
            icon_url="https://anilist.co/img/icons/android-chrome-512x512.png"
        )
        embed.add_field(name="🔗 Link", value=f"[View on AniList]({url})", inline=False)
        
        return embed

    async def cog_load(self):
        """Called when the cog is loaded"""
        logger.info("Trending cog loaded successfully")

    async def cog_unload(self):
        """Called when the cog is unloaded"""
        logger.info("Trending cog unloaded")


# ------------------------------------------------------
# Pagination View
# ------------------------------------------------------
class TrendingPaginatedView(discord.ui.View):
    def __init__(self, embeds, user_id: int):
        super().__init__(timeout=180)  # 3-minute timeout
        self.embeds = embeds
        self.current = 0
        self.user_id = user_id
        logger.info(f"Created TrendingPaginatedView with {len(embeds)} pages for user ID: {user_id}")

    async def update_message(self, interaction: discord.Interaction):
        embed = self.embeds[self.current]
        embed.set_footer(text=f"Page {self.current+1}/{len(self.embeds)} • ⚡ Powered by AniList")
        logger.info(f"Updated trending pagination to page {self.current+1}/{len(self.embeds)} for user {interaction.user}")
        
        try:
            await interaction.response.edit_message(embed=embed, view=self)
        except discord.errors.InteractionResponded:
            await interaction.followup.edit_message(
                message_id=interaction.message.id, embed=embed, view=self
            )

    @discord.ui.button(label="⬅️ Previous", style=discord.ButtonStyle.secondary)
    async def previous(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            embed = build_error_embed(
                "Permission Denied",
                "Only the command user can navigate."
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
            
        self.current = (self.current - 1) % len(self.embeds)
        logger.info(f"User {interaction.user} navigated to previous page ({self.current+1}/{len(self.embeds)})")
        await self.update_message(interaction)

    @discord.ui.button(label="➡️ Next", style=discord.ButtonStyle.secondary)
    async def next(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            embed = build_error_embed(
                "Permission Denied",
                "Only the command user can navigate."
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
            
        self.current = (self.current + 1) % len(self.embeds)
        logger.info(f"User {interaction.user} navigated to next page ({self.current+1}/{len(self.embeds)})")
        await self.update_message(interaction)

    async def on_timeout(self):
        """Handle view timeout"""
        logger.info(f"TrendingPaginatedView timed out for user ID: {self.user_id}")
        # Disable all buttons
        for item in self.children:
            item.disabled = True

async def setup(bot: commands.Bot):
    await bot.add_cog(Trending(bot))
