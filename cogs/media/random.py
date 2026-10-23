from helpers.color_palette import PALETTE
import discord
from discord.ext import commands
from discord import app_commands
from discord.ui import View, Button
import os
import logging
import aiohttp
from pathlib import Path
from typing import List, Dict, Optional

from helpers.media_helper import fetch_random_media
from helpers.embed_helper import build_error_embed
from helpers.anilist_helper import post_graphql
from database import get_all_users_guild_aware
from cogs_test.general_commands.dashboard import command_meta
from cogs.media.browse import scrape_novelupdates
from helpers.crypto_random import secure_choice, secure_randbelow

# ------------------------------------------------------
# Logging Setup - Clears on each bot run
# ------------------------------------------------------
LOG_DIR = Path("logs")
LOG_DIR.mkdir(exist_ok=True)
LOG_FILE = LOG_DIR / "random.log"

# Clear the log file on startup
if LOG_FILE.exists():
    try:
        # Try to truncate the file instead of unlinking; unlink can fail if another
        # process has the file open (PermissionError on Windows). Truncation is
        # less likely to raise, but wrap in try/except to be safe.
        with open(LOG_FILE, 'w'):
            pass
    except Exception as e:
        # If we can't clear the file, continue — we'll append to it or fall back
        # to console logging when we create the handler below.
        try:
            print(f"Warning: could not clear log file {LOG_FILE}: {e}")
        except Exception:
            pass

# Create logger
logger = logging.getLogger("Random")
logger.setLevel(logging.INFO)

# Remove existing handlers to avoid duplicates
for handler in logger.handlers[:]:
    logger.removeHandler(handler)

# Create file handler with safe fallback
try:
    file_handler = logging.FileHandler(LOG_FILE, encoding="utf-8")
    file_handler.setLevel(logging.INFO)
except Exception:
    # Fall back to console logging if the file cannot be opened
    try:
        print(f"Warning: could not open log file {LOG_FILE}, falling back to console")
    except Exception:
        pass
    file_handler = logging.StreamHandler()
    file_handler.setLevel(logging.INFO)

# Create formatter
formatter = logging.Formatter(
    "[%(asctime)s] [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
file_handler.setFormatter(formatter)

# Add handler to logger
logger.addHandler(file_handler)

logger.info("Random cog logging initialized - log file cleared")

# ------------------------------------------------------
# Constants
# ------------------------------------------------------
MEDIA_TYPES = ["ANIME", "MANGA", "LN", "GENERAL_NOVEL", "BOOKS", "MOVIE", "TV", "WEBNOVEL"]
MEDIA_TYPE_CHOICES = [
    app_commands.Choice(name="Anime 🎬", value="ANIME"),
    app_commands.Choice(name="Manga 📖", value="MANGA"),
    app_commands.Choice(name="Light Novel 📚", value="LN"),
    app_commands.Choice(name="General Novels 📕", value="GENERAL_NOVEL"),
    app_commands.Choice(name="Books 📚", value="BOOKS"),
    app_commands.Choice(name="Movies 🎞️", value="MOVIE"),
    app_commands.Choice(name="TV Shows 📺", value="TV"),
    app_commands.Choice(name="Webnovels 🌐", value="WEBNOVEL"),
    app_commands.Choice(name="All 🎲", value="ALL"),
]


class Random(commands.Cog):
    """Generate random suggestions across AniList, books, webnovels, movies, and TV."""
    
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        logger.info("Random cog initialized")

    def _get_random_media_type(self) -> str:
        """Select a random media type from available options."""
        return secure_choice(MEDIA_TYPES)
    
    def _apply_random_color(self, embed: discord.Embed) -> discord.Embed:
        """Apply a random color to the embed."""
        embed.color = discord.Color(secure_randbelow(0x1000000))
        return embed

    async def fetch_detailed_media(self, media_id: int, media_type: str) -> Optional[Dict]:
        """Fetch detailed media information from AniList API."""
        query = """
        query ($id: Int, $type: MediaType) {
            Media(id: $id, type: $type) {
                id
                title { romaji english native }
                description(asHtml: false)
                averageScore
                siteUrl
                status
                episodes
                chapters
                volumes
                startDate { year month day }
                endDate { year month day }
                genres
                coverImage { large medium }
                bannerImage
                externalLinks { site url }
                format
            }
        }
        """
        
        variables = {"id": media_id, "type": media_type}
        
        try:
            async with aiohttp.ClientSession() as session:
                data = await post_graphql(session, query, variables)
                if data is None:
                    logger.warning(f"Failed to fetch detailed media info for media_id={media_id}, type={media_type}")
                    return None
                return data.get("Media")
        except Exception as e:
            logger.error(f"Error fetching detailed media info: {e}", exc_info=True)
            return None

    async def fetch_user_anilist_progress(self, anilist_username: str, media_id: int, media_type: str) -> Optional[Dict]:
        """Fetch AniList progress & rating for a user."""
        if not anilist_username or not media_id:
            return None

        query = """
        query($userName: String, $mediaId: Int, $type: MediaType) {
            User(name: $userName) {
                mediaListOptions {
                    scoreFormat
                }
            }
            MediaList(userName: $userName, mediaId: $mediaId, type: $type) {
                progress
                score
            }
        }
        """
        variables = {"userName": anilist_username, "mediaId": media_id, "type": media_type}

        try:
            async with aiohttp.ClientSession() as session:
                payload = await post_graphql(session, query, variables)
                if payload is None:
                    logger.warning(f"AniList fetch failed for {anilist_username=} {media_id=}")
                    return None
        except Exception as e:
            logger.exception("Error requesting AniList user progress", exc_info=True)
            return None

        user_opts = payload.get("User", {}).get("mediaListOptions", {})
        score_format = user_opts.get("scoreFormat", "POINT_100")

        entry = payload.get("MediaList")
        if not entry:
            return None

        progress = entry.get("progress")
        score = entry.get("score")

        # Normalize based on score format
        rating10: Optional[float] = None
        if score is not None:
            try:
                if score_format == "POINT_100":
                    rating10 = round(score / 10.0, 1)
                elif score_format in ("POINT_10", "POINT_10_DECIMAL"):
                    rating10 = float(score)
                elif score_format == "POINT_5":
                    rating10 = round((score / 5) * 10, 1)
                elif score_format == "POINT_3":
                    mapping = {1: 3.0, 2: 6.0, 3: 9.0}
                    rating10 = mapping.get(score, None)
            except Exception:
                rating10 = None

        return {"progress": progress, "rating10": rating10}

    async def create_enhanced_embed(self, media_data: Dict, media_type: str) -> discord.Embed:
        """Create an enhanced embed with detailed media information."""
        # Format dates
        start_date = media_data.get("startDate", {})
        end_date = media_data.get("endDate", {})
        start_str = f"{start_date.get('year','?')}-{start_date.get('month','?')}-{start_date.get('day','?')}"
        end_str = (
            f"{end_date.get('year','?')}-{end_date.get('month','?')}-{end_date.get('day','?')}"
            if end_date and any(end_date.values()) else "Ongoing"
        )

        # Description
        raw_description = media_data.get("description") or "No description available."
        description = raw_description[:400] + "..." if len(raw_description) > 400 else raw_description
        genres = ", ".join(media_data.get("genres", [])) or "Unknown"

        # Create enhanced embed
        title_name = (media_data.get("title", {}).get("romaji") or 
                     media_data.get("title", {}).get("english") or 
                     media_data.get("title", {}).get("native") or "Unknown")
        
        embed = discord.Embed(
            title=f"{'🎬' if media_type=='ANIME' else '📖'} {title_name}",
            url=media_data.get("siteUrl"),
            description=description,
            color=discord.Color(secure_randbelow(0x1000000))
        )

        # Set thumbnail and banner
        cover_url = media_data.get("coverImage", {}).get("medium") or media_data.get("coverImage", {}).get("large")
        if cover_url:
            embed.set_thumbnail(url=cover_url)

        banner_url = media_data.get("bannerImage")
        if banner_url:
            embed.set_image(url=banner_url)

        # Add detailed fields
        embed.add_field(name="⭐ Average Score", value=f"{media_data.get('averageScore', 'N/A')}%", inline=True)
        embed.add_field(name="📌 Status", value=media_data.get("status", "Unknown"), inline=True)

        if media_type == "ANIME":
            embed.add_field(name="📺 Episodes", value=media_data.get("episodes", '?'), inline=True)
        else:
            embed.add_field(name="📖 Chapters", value=media_data.get("chapters", '?'), inline=True)
            embed.add_field(name="📚 Volumes", value=media_data.get("volumes", '?'), inline=True)

        embed.add_field(name="🎭 Genres", value=genres, inline=False)
        embed.add_field(name="📅 Published", value=f"**Start:** {start_str}\n**End:** {end_str}", inline=False)

        # Add MyAnimeList link if available
        mal_link = None
        for link in media_data.get("externalLinks", []):
            if link.get("site") == "MyAnimeList":
                mal_link = link.get("url")
                break
        if mal_link:
            embed.add_field(name="🔗 MyAnimeList", value=f"[View on MAL]({mal_link})", inline=False)

        embed.set_footer(text="🎲 Random suggestion from AniList")
        return embed

    async def create_progress_embed(self, media_data: Dict, media_type: str, guild_id: int) -> Optional[discord.Embed]:
        """Create user progress embed showing registered users' progress."""
        users = await get_all_users_guild_aware(guild_id)
        if not users:
            return None

        col_name = "Episodes" if media_type == "ANIME" else "Chapters"
        progress_lines = [f"`{'User':<20} {col_name:<10} {'Rating':<7}`"]
        progress_lines.append("`{:-<20} {:-<10} {:-<7}`".format("", "", ""))

        has_progress = False
        for user in users:
            discord_name = user[1]  # Assuming: (discord_id, discord_name, anilist_username)
            anilist_username = user[2] if len(user) > 2 else None

            if not anilist_username:
                continue

            anilist_progress = await self.fetch_user_anilist_progress(
                anilist_username, media_data.get("id", 0), media_type
            )

            # Skip this user entirely if they don't have the anime/manga
            if not anilist_progress:
                continue

            has_progress = True
            total = media_data.get("episodes") if media_type == "ANIME" else media_data.get("chapters")
            progress_text = f"{anilist_progress['progress']}/{total or '?'}" if anilist_progress.get("progress") is not None else "—"
            rating_text = f"{anilist_progress['rating10']}/10" if anilist_progress.get("rating10") is not None else "—"

            progress_lines.append(f"`{discord_name:<20} {progress_text:<10} {rating_text:<7}`")

        # Only build the embed if there's at least one valid user
        if not has_progress:
            return None

        progress_embed = discord.Embed(
            title="👥 Registered Users' Progress",
            description="\n".join(progress_lines),
            color=PALETTE.PRIMARY
        )
        progress_embed.set_footer(text="🎲 Random suggestion from AniList")
        return progress_embed

    async def _fetch_random_tmdb_media(self, media_type: str) -> Optional[Dict]:
        """Select a random movie/show from TMDB discovery pages, then fetch full metadata.

        Discovery pages are popularity-sorted, but the page and title are selected
        cryptographically rather than always taking the first search match.
        """
        token = os.getenv("TMDB_BEARER_TOKEN", "").strip()
        if not token:
            return None

        endpoint = "movie" if media_type == "MOVIE" else "tv"
        base_url = "https://api.themoviedb.org/3"
        headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
        params = {
            "include_adult": "false",
            "language": "en-US",
            "page": 1,
            "sort_by": "popularity.desc",
        }

        try:
            timeout = aiohttp.ClientTimeout(total=12)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(
                    f"{base_url}/discover/{endpoint}", params=params, headers=headers
                ) as response:
                    if response.status != 200:
                        logger.warning("TMDB %s discovery returned HTTP %s", endpoint, response.status)
                        return None
                    page_data = await response.json()

                # TMDB exposes at most 500 discover pages; choose a page and then a title.
                total_pages = min(500, max(1, int(page_data.get("total_pages") or 1)))
                page = secure_randbelow(total_pages) + 1
                if page > 1:
                    params["page"] = page
                    async with session.get(
                        f"{base_url}/discover/{endpoint}", params=params, headers=headers
                    ) as response:
                        if response.status != 200:
                            logger.warning("TMDB %s random page returned HTTP %s", endpoint, response.status)
                            return None
                        page_data = await response.json()

                candidates = page_data.get("results") or []
                if not candidates:
                    return None
                selected = secure_choice(candidates)
                media_id = selected.get("id")
                if not media_id:
                    return None

                append_fields = (
                    "credits,videos,keywords,release_dates,external_ids,images,recommendations"
                    if media_type == "MOVIE"
                    else "aggregate_credits,videos,keywords,content_ratings,external_ids,images,recommendations"
                )
                async with session.get(
                    f"{base_url}/{endpoint}/{media_id}",
                    params={"append_to_response": append_fields, "language": "en-US"},
                    headers=headers,
                ) as response:
                    if response.status != 200:
                        logger.warning("TMDB %s detail lookup returned HTTP %s", endpoint, response.status)
                        return None
                    details = await response.json()
                    details["_media_type"] = media_type
                    return details
        except (aiohttp.ClientError, asyncio.TimeoutError, ValueError, TypeError) as exc:
            logger.warning("TMDB random %s lookup failed: %s", endpoint, exc)
            return None

    async def _process_external_random_request(self, interaction: discord.Interaction, media_type: str) -> None:
        """Reuse BrowseCog providers for random novel, book, movie, TV, and webnovel picks."""
        browse = self.bot.get_cog("BrowseCog")
        if browse is None:
            await interaction.followup.send(embed=build_error_embed(
                "Browse Unavailable", "The Browse integration is not loaded."
            ), ephemeral=True)
            return

        query = secure_choice([
            "fantasy", "adventure", "mystery", "drama", "science fiction",
            "romance", "historical", "thriller", "comedy", "popular"
        ])
        try:
            if media_type == "WEBNOVEL":
                import asyncio
                results = await asyncio.to_thread(scrape_novelupdates, {"query": query}, output=None)
                if not results:
                    raise LookupError("No Novel Updates results were found.")
                item = secure_choice(results)
                embed = discord.Embed(
                    title=f"🌐 {item.get('title') or 'Unknown webnovel'}"[:256],
                    url=item.get("url"),
                    description=(item.get("description") or "No description available.")[:900],
                    color=PALETTE.PRIMARY,
                )
                if item.get("image"):
                    embed.set_thumbnail(url=item["image"])
                if item.get("rating"):
                    embed.add_field(name="⭐ Rating", value=str(item["rating"])[:1024])
                if item.get("genres"):
                    embed.add_field(name="🎭 Genres", value=", ".join(item["genres"])[:1024], inline=False)
                embed.set_footer(text="Random pick • Novel Updates")
            elif media_type in ("GENERAL_NOVEL", "BOOKS"):
                book_type = "fiction" if media_type == "GENERAL_NOVEL" else "nonfiction"
                results = await browse.fetch_book_results(query, book_type)
                if not results:
                    raise LookupError("No matching Google Books or Goodreads results were found.")
                book = secure_choice(results).get("volumeInfo", {})
                embed = discord.Embed(
                    title=f"{'📖' if book_type == 'fiction' else '📚'} {book.get('title') or 'Unknown title'}"[:256],
                    url=book.get("infoLink") or book.get("previewLink"),
                    description=(book.get("description") or "No description available.")[:900],
                    color=PALETTE.PRIMARY,
                )
                image = book.get("imageLinks") or {}
                thumbnail = image.get("thumbnail") or image.get("smallThumbnail")
                if thumbnail:
                    embed.set_thumbnail(url=thumbnail.replace("http://", "https://", 1))
                if book.get("authors"):
                    embed.add_field(name="✍️ Author(s)", value=", ".join(book["authors"])[:1024])
                if book.get("publishedDate"):
                    embed.add_field(name="📅 Published", value=str(book["publishedDate"])[:1024])
                if book.get("publisher"):
                    embed.add_field(name="🏢 Publisher", value=str(book["publisher"])[:1024])
                if book.get("pageCount"):
                    embed.add_field(name="📄 Pages", value=str(book["pageCount"])[:1024])
                if book.get("averageRating") is not None:
                    embed.add_field(name="⭐ Rating", value=f"{book['averageRating']}/5")
                if book.get("categories"):
                    embed.add_field(name="🏷️ Categories", value=", ".join(book["categories"])[:1024], inline=False)
                embed.set_footer(text=f"Random pick • {book.get('source') or 'Google Books'}")
            else:
                import os
                if not os.getenv("TMDB_BEARER_TOKEN", "").strip():
                    await interaction.followup.send(embed=build_error_embed(
                        "TMDB Setup Required",
                        "Movies and TV random picks require TMDB_BEARER_TOKEN."
                    ), ephemeral=True)
                    return
                media = await self._fetch_random_tmdb_media(media_type)
                if not media:
                    raise LookupError("No TMDB results were found.")
                ratings = await browse.fetch_mdblist_ratings(media.get("id"), media_type)
                is_movie = media_type == "MOVIE"
                title = media.get("title") if is_movie else media.get("name")
                year_date = media.get("release_date") if is_movie else media.get("first_air_date")
                year = year_date[:4] if year_date else "Year unknown"
                embed = discord.Embed(
                    title=f"{'🎞️' if is_movie else '📺'} {title or 'Unknown title'} ({year})"[:256],
                    url=f"https://www.themoviedb.org/{'movie' if is_movie else 'tv'}/{media['id']}",
                    description=(media.get("overview") or "No overview available.")[:900],
                    color=PALETTE.PRIMARY,
                )
                if media.get("poster_path"):
                    embed.set_thumbnail(url=f"https://image.tmdb.org/t/p/w500{media['poster_path']}")
                if media.get("vote_average") is not None:
                    embed.add_field(name="⭐ TMDB Rating", value=f"{media['vote_average']:.1f}/10 · {media.get('vote_count', 0):,} votes")
                for source, label, scale in (
                    ("metacritic", "🎞️ Metacritic Metascore", 100),
                    ("metacriticuser", "👥 Metacritic User Score", 10),
                ):
                    record = ratings.get(source)
                    if record:
                        value = f"{record['value']:g}/{scale}"
                        if record.get("url"):
                            value += f" · [Metacritic]({record['url']})"
                        embed.add_field(name=label, value=value[:1024])
                genres = ", ".join(g.get("name", "") for g in media.get("genres", []) if g.get("name"))
                if genres:
                    embed.add_field(name="🎭 Genres", value=genres[:1024], inline=False)
                embed.set_footer(text="Random pick • TMDB" + (" • Metacritic via MDBList" if ratings else ""))
            await interaction.followup.send(embed=embed)
        except LookupError as exc:
            await interaction.followup.send(embed=build_error_embed("No Random Results", str(exc)), ephemeral=True)
        except Exception:
            logger.exception("Random %s lookup failed", media_type)
            await interaction.followup.send(embed=build_error_embed(
                "Lookup Failed", "Could not fetch a random suggestion right now. Please try again later."
            ), ephemeral=True)

    async def _process_random_request(self, interaction: discord.Interaction, media_type: str) -> None:
        """Process random suggestions from AniList or the existing Browse providers."""
        if media_type.upper() == "ALL":
            media_type = self._get_random_media_type()
            logger.info(
                "User %s requested all media; cryptographically selected %s",
                interaction.user.id, media_type,
            )

        if media_type.upper() in ("GENERAL_NOVEL", "BOOKS", "MOVIE", "TV", "WEBNOVEL"):
            await interaction.response.defer()
            await self._process_external_random_request(interaction, media_type.upper())
            return
        try:
            selected_type = media_type.upper()
            logger.info("User %s requested random %s", interaction.user.id, selected_type)

            # Defer the response since API call might take time
            await interaction.response.defer()
            
            # Fetch basic random media first to get the ID
            logger.info(f"Fetching random {selected_type} for user {interaction.user.id}")
            basic_embed = await fetch_random_media(selected_type)
            
            if not basic_embed:
                logger.warning(f"No random {selected_type} found for user {interaction.user.id}")
                error_embed = build_error_embed(
                    "No Results",
                    f"Sorry, couldn't find any random {selected_type.lower()} right now. Please try again later!"
                )
                await interaction.followup.send(embed=error_embed)
                return

            # Extract media ID from the basic embed URL to get detailed info
            media_id = None
            if basic_embed.url:
                try:
                    # AniList URLs are like: https://anilist.co/anime/123456
                    media_id = int(basic_embed.url.split('/')[-1])
                except (ValueError, IndexError):
                    logger.warning(f"Could not extract media ID from URL: {basic_embed.url}")

            if media_id:
                # Fetch detailed media information
                logger.info(f"Fetching detailed info for media ID {media_id}")
                detailed_media = await self.fetch_detailed_media(media_id, selected_type)
                
                if detailed_media:
                    # Create enhanced embed with detailed information
                    enhanced_embed = await self.create_enhanced_embed(detailed_media, selected_type)
                    
                    # Create user progress embed
                    progress_embed = await self.create_progress_embed(detailed_media, selected_type, interaction.guild_id)
                    
                    if progress_embed:
                        # Create interactive view with both embeds
                        view = self.PageView(enhanced_embed, progress_embed, selected_type)
                        await interaction.followup.send(embed=enhanced_embed, view=view)
                        logger.info(f"Successfully sent enhanced random {selected_type} with user progress to user {interaction.user.id}")
                    else:
                        # Just send the enhanced embed without progress
                        await interaction.followup.send(embed=enhanced_embed)
                        logger.info(f"Successfully sent enhanced random {selected_type} to user {interaction.user.id}")
                    return

            # Fallback to basic embed if detailed fetch failed
            basic_embed = self._apply_random_color(basic_embed)
            await interaction.followup.send(embed=basic_embed)
            logger.info(f"Successfully sent basic random {selected_type} to user {interaction.user.id}")
            
        except Exception as e:
            logger.error(f"Error processing random request for user {interaction.user.id}: {e}", exc_info=True)
            
            # Create error embed
            error_embed = build_error_embed(
                "Error",
                "An error occurred while fetching random media. Please try again later!"
            )
            
            # Send error response
            if not interaction.response.is_done():
                await interaction.response.send_message(embed=error_embed)
            else:
                await interaction.followup.send(embed=error_embed)

    class PageView(View):
        """Interactive view for switching between media info and user progress."""
        
        def __init__(self, media_embed: discord.Embed, progress_embed: discord.Embed, media_type: str):
            super().__init__(timeout=120)
            self.media_embed = media_embed
            self.progress_embed = progress_embed
            self.media_type = media_type
            self.current = "info"
            self.rebuild_buttons()

        def rebuild_buttons(self):
            """Rebuild buttons based on current page."""
            self.clear_items()

            if self.current == "info":
                btn = Button(
                    label="👥 User Progress",
                    style=discord.ButtonStyle.green,
                    emoji="👥"
                )

                async def user_progress_callback(interaction: discord.Interaction):
                    self.current = "progress"
                    self.rebuild_buttons()
                    await interaction.response.edit_message(embed=self.progress_embed, view=self)

                btn.callback = user_progress_callback
                self.add_item(btn)

            else:  # current == "progress"
                media_label = {
                    "ANIME": "🎬 Anime Info",
                    "MANGA": "📖 Manga Info", 
                    "LN": "📚 Light Novel Info"
                }.get(self.media_type, "📖 Media Info")
                
                btn = Button(
                    label=media_label,
                    style=discord.ButtonStyle.blurple,
                    emoji="📖" if self.media_type != "ANIME" else "🎬"
                )

                async def media_info_callback(interaction: discord.Interaction):
                    self.current = "info"
                    self.rebuild_buttons()
                    await interaction.response.edit_message(embed=self.media_embed, view=self)

                btn.callback = media_info_callback
                self.add_item(btn)

        async def on_timeout(self):
            """Remove all buttons when view times out."""
            self.clear_items()

    @app_commands.command(
        name="random",
        description="🎲 Get a random Anime, Manga, Light Novel, Novel, Book, Movie, TV Show, Webnovel, or All suggestion"
    )
    @command_meta(section="Media", name="Random")
    @app_commands.describe(media_type="Choose the type of media to get a random suggestion for")
    @app_commands.choices(media_type=MEDIA_TYPE_CHOICES)
    async def random_media(self, interaction: discord.Interaction, media_type: app_commands.Choice[str]) -> None:
        """Generate a random media suggestion from AniList.
        
        Args:
            interaction: The Discord interaction
            media_type: The type of media to get a random suggestion for
        """
        logger.info(f"Random command invoked by {interaction.user} ({interaction.user.id})")
        await self._process_random_request(interaction, media_type.value)


async def setup(bot: commands.Bot):
    """Set up the Random cog."""
    await bot.add_cog(Random(bot))
    logger.info("Random cog successfully loaded")
