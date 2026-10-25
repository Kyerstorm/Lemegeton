from helpers.color_palette import PALETTE
import discord
from discord.ext import commands
from discord import app_commands
from discord.ui import View, Button
import asyncio
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
from cogs.media.browse import search_novelupdates
from helpers.web_scraper import ScrapeBlockedError
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


class RandomResultView(View):
    """Private, invoking-user-scoped controls for a random media result."""

    def __init__(self, cog, owner_id: int, media_type: str, filters: Dict,
                 source_url: Optional[str] = None, seen_urls: Optional[set] = None):
        super().__init__(timeout=300)
        self.cog = cog
        self.owner_id = owner_id
        self.media_type = media_type
        self.filters = filters
        self.seen_urls = set(seen_urls or ())
        if source_url:
            self.seen_urls.add(source_url)

        reroll = Button(label="🎲 Reroll", style=discord.ButtonStyle.primary)

        async def reroll_callback(interaction: discord.Interaction):
            if interaction.user.id != self.owner_id:
                await interaction.response.send_message("These random controls belong to another user.", ephemeral=True)
                return
            await self.cog._process_random_request(
                interaction, self.media_type, seen_urls=self.seen_urls, **self.filters,
            )

        reroll.callback = reroll_callback
        self.add_item(reroll)
        if source_url and source_url.startswith("https://"):
            self.add_item(Button(label="Open Source", style=discord.ButtonStyle.link, url=source_url))


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

    @staticmethod
    def _extract_seen_ids(seen_urls: Optional[set]) -> set:
        """Extract stable numeric AniList IDs from previously displayed source URLs."""
        identifiers = set()
        for url in seen_urls or ():
            segment = str(url).split("?", 1)[0].rstrip("/").rsplit("/", 1)[-1]
            if segment.isdigit():
                identifiers.add(int(segment))
        return identifiers

    async def _fetch_filtered_random_media(
        self, media_type: str, genre: Optional[str] = None,
        year_from: Optional[int] = None, year_to: Optional[int] = None,
        status: Optional[str] = None, media_format: Optional[str] = None,
        excluded_ids: Optional[set] = None,
    ) -> Optional[int]:
        """Uniformly select from AniList's provider-filtered result set using secure_randbelow."""
        query = """
        query (
            $page: Int, $type: MediaType, $genreIn: [String],
            $startDateGreater: FuzzyDateInt, $startDateLesser: FuzzyDateInt,
            $status: MediaStatus, $format: MediaFormat, $excludedIds: [Int]
        ) {
            Page(page: $page, perPage: 50) {
                pageInfo { lastPage }
                media(
                    type: $type, genre_in: $genreIn,
                    startDate_greater: $startDateGreater, startDate_lesser: $startDateLesser,
                    status: $status, format: $format, id_not_in: $excludedIds, sort: ID_DESC
                ) { id }
            }
        }
        """
        api_type = "MANGA" if media_type == "LN" else media_type
        variables = {
            "type": api_type,
            "genreIn": [genre] if genre else None,
            "startDateGreater": year_from * 10000 if year_from is not None else None,
            "startDateLesser": year_to * 10000 + 1231 if year_to is not None else None,
            "status": status,
            "format": "NOVEL" if media_type == "LN" else media_format,
            "excludedIds": sorted(excluded_ids or ()) or None,
        }

        async def fetch_page(session, page_number):
            payload = await post_graphql(session, query, {**variables, "page": page_number})
            return (payload or {}).get("Page") or {}

        try:
            timeout = aiohttp.ClientTimeout(total=15)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                first = await fetch_page(session, 1)
                first_items = first.get("media") or []
                if not first_items:
                    return None
                page_info = first.get("pageInfo") or {}
                last_page = max(1, int(page_info.get("lastPage") or 1))
                last_items = first_items if last_page == 1 else (
                    await fetch_page(session, last_page)
                ).get("media") or []
                eligible_count = (last_page - 1) * 50 + len(last_items)
                if eligible_count <= 0:
                    return None
                offset = secure_randbelow(eligible_count)
                page_number = offset // 50 + 1
                position = offset % 50
                if page_number == 1:
                    selected_page = first_items
                elif page_number == last_page:
                    selected_page = last_items
                else:
                    selected_page = (await fetch_page(session, page_number)).get("media") or []
                if position >= len(selected_page):
                    return None
                selected_id = selected_page[position].get("id")
                return int(selected_id) if selected_id else None
        except (aiohttp.ClientError, asyncio.TimeoutError, ValueError, TypeError) as exc:
            logger.warning("Filtered AniList random selection failed: %s", exc)
            return None

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

    async def _fetch_random_tmdb_media(
        self, media_type: str, genre: Optional[str] = None,
        year_from: Optional[int] = None, year_to: Optional[int] = None,
    ) -> Optional[Dict]:
        """Select from TMDB's discover window using unbiased cryptographic indexing."""
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
        if genre:
            movie_genres = {
                "action": 28, "adventure": 12, "animation": 16, "comedy": 35,
                "crime": 80, "documentary": 99, "drama": 18, "family": 10751,
                "fantasy": 14, "history": 36, "horror": 27, "mystery": 9648,
                "romance": 10749, "sci-fi": 878, "thriller": 53,
            }
            tv_genres = {
                "action": 10759, "adventure": 10759, "animation": 16, "comedy": 35,
                "crime": 80, "documentary": 99, "drama": 18, "family": 10751,
                "fantasy": 10765, "mystery": 9648, "sci-fi": 10765,
            }
            genre_id = (movie_genres if media_type == "MOVIE" else tv_genres).get(genre.casefold())
            if genre_id is None:
                return None
            params["with_genres"] = genre_id
        date_field = "primary_release_date" if media_type == "MOVIE" else "first_air_date"
        if year_from is not None:
            params[f"{date_field}.gte"] = f"{year_from}-01-01"
        if year_to is not None:
            params[f"{date_field}.lte"] = f"{year_to}-12-31"

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

                # TMDB caps discovery at 500 pages. Index the reachable titles, not pages,
                # so a shorter final page does not receive the same weight as a full page.
                total_pages = min(500, max(1, int(page_data.get("total_pages") or 1)))
                first_candidates = page_data.get("results") or []
                total_results = max(0, int(page_data.get("total_results") or len(first_candidates)))
                total_results = min(total_results, total_pages * 20)
                if total_results == 0:
                    return None
                selected_index = secure_randbelow(total_results)
                page = selected_index // 20 + 1
                position = selected_index % 20
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
                if position >= len(candidates):
                    return None
                selected = candidates[position]
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

    async def _process_external_random_request(
        self, interaction: discord.Interaction, media_type: str,
        genre: Optional[str] = None, year_from: Optional[int] = None,
        year_to: Optional[int] = None, seen_urls: Optional[set] = None,
    ) -> None:
        """Reuse configured providers for filtered book, webnovel, movie, and TV picks."""
        browse = self.bot.get_cog("BrowseCog")
        if browse is None:
            await interaction.followup.send(embed=build_error_embed(
                "Browse Unavailable", "The Browse integration is not loaded."
            ), ephemeral=True)
            return

        query = genre or secure_choice([
            "fantasy", "adventure", "mystery", "drama", "science fiction",
            "romance", "historical", "thriller", "comedy", "popular"
        ])
        try:
            if media_type == "WEBNOVEL":
                if year_from is not None or year_to is not None:
                    raise LookupError("Novel Updates results do not expose consistent publication-year data for filtering.")
                results = await search_novelupdates(query, require_genres=bool(genre))
                if genre:
                    results = [
                        item for item in results
                        if genre.casefold() in " ".join(item.get("genres") or []).casefold()
                    ]
                results = [
                    item for item in results
                    if (item.get("url") or item.get("link")) not in (seen_urls or set())
                ]
                if not results:
                    raise LookupError("No unseen Novel Updates results matched the selected genre.")
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
                results = await browse.fetch_book_results(
                    query, book_type, genre=genre, year_from=year_from, year_to=year_to,
                )
                results = [
                    item for item in results
                    if ((item.get("volumeInfo") or {}).get("infoLink")
                        or (item.get("volumeInfo") or {}).get("previewLink")) not in (seen_urls or set())
                ]
                if not results:
                    raise LookupError("No unseen Google Books or Goodreads results matched those filters.")
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
                media = None
                for _ in range(5 if seen_urls else 1):
                    candidate = await self._fetch_random_tmdb_media(
                        media_type, genre=genre, year_from=year_from, year_to=year_to,
                    )
                    if not candidate:
                        break
                    candidate_url = (
                        f"https://www.themoviedb.org/{'movie' if media_type == 'MOVIE' else 'tv'}/{candidate.get('id')}"
                    )
                    if candidate_url not in (seen_urls or set()):
                        media = candidate
                        break
                if not media:
                    raise LookupError("No unseen TMDB titles matched the selected filters.")
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
            view = RandomResultView(
                self, interaction.user.id, media_type,
                {"genre": genre, "year_from": year_from, "year_to": year_to},
                source_url=embed.url, seen_urls=seen_urls,
            )
            await interaction.followup.send(embed=embed, view=view)
        except ScrapeBlockedError as exc:
            logger.warning("Novel Updates blocked random search: %s", exc)
            await interaction.followup.send(embed=build_error_embed(
                "Novel Updates Temporarily Unavailable",
                "Novel Updates blocked or rate-limited automated access. Please try again later.",
            ), ephemeral=True)
        except LookupError as exc:
            await interaction.followup.send(embed=build_error_embed("No Random Results", str(exc)), ephemeral=True)
        except Exception:
            logger.exception("Random %s lookup failed", media_type)
            await interaction.followup.send(embed=build_error_embed(
                "Lookup Failed", "Could not fetch a random suggestion right now. Please try again later."
            ), ephemeral=True)

    async def _process_random_request(
        self, interaction: discord.Interaction, media_type: str,
        genre: Optional[str] = None, year_from: Optional[int] = None,
        year_to: Optional[int] = None, status: Optional[str] = None,
        media_format: Optional[str] = None, seen_urls: Optional[set] = None,
    ) -> None:
        """Process provider-filtered suggestions while retaining cryptographic selection."""
        for label, year in (("year_from", year_from), ("year_to", year_to)):
            if year is not None and not 1000 <= year <= 2100:
                await interaction.response.send_message(
                    embed=build_error_embed("Invalid Year", f"{label} must be between 1000 and 2100."),
                    ephemeral=True,
                )
                return
        if year_from is not None and year_to is not None and year_from > year_to:
            await interaction.response.send_message(
                embed=build_error_embed("Invalid Year Range", "year_from cannot be later than year_to."),
                ephemeral=True,
            )
            return
        has_filters = bool(genre or year_from is not None or year_to is not None or status or media_format)
        if media_type.upper() == "ALL" and has_filters:
            await interaction.response.send_message(
                embed=build_error_embed(
                    "Choose a Media Type",
                    "Select a specific category so the filters can be applied by the correct provider.",
                ),
                ephemeral=True,
            )
            return
        if media_type.upper() == "ALL":
            media_type = self._get_random_media_type()
            logger.info(
                "User %s requested all media; cryptographically selected %s",
                interaction.user.id, media_type,
            )

        if media_type.upper() in ("GENERAL_NOVEL", "BOOKS", "MOVIE", "TV", "WEBNOVEL"):
            if status or media_format:
                await interaction.response.send_message(
                    embed=build_error_embed(
                        "Unsupported Filter",
                        "Status and format filters are available only for AniList categories.",
                    ),
                    ephemeral=True,
                )
                return
            if media_type.upper() == "WEBNOVEL" and (year_from is not None or year_to is not None):
                await interaction.response.send_message(
                    embed=build_error_embed(
                        "Unsupported Filter",
                        "Novel Updates results do not expose consistent publication-year data.",
                    ),
                    ephemeral=True,
                )
                return
            await interaction.response.defer()
            await self._process_external_random_request(
                interaction, media_type.upper(), genre=genre,
                year_from=year_from, year_to=year_to, seen_urls=seen_urls,
            )
            return
        try:
            selected_type = media_type.upper()
            if selected_type == "MANGA" and media_format == "NOVEL":
                selected_type = "LN"
            allowed_formats = {
                "ANIME": {"TV", "TV_SHORT", "MOVIE", "SPECIAL", "OVA", "ONA"},
                "MANGA": {"MANGA", "ONE_SHOT", "NOVEL"},
                "LN": {"NOVEL"},
            }
            if media_format and (
                selected_type not in allowed_formats or media_format not in allowed_formats[selected_type]
            ):
                await interaction.response.send_message(
                    embed=build_error_embed(
                        "Unsupported Format",
                        "Choose a format compatible with Anime, Manga, or Light Novels. Novel format is reserved for Light Novels.",
                    ),
                    ephemeral=True,
                )
                return
            logger.info("User %s requested random %s", interaction.user.id, selected_type)

            # Defer the response since API call might take time.
            await interaction.response.defer()

            if has_filters or selected_type in ("ANIME", "MANGA", "LN"):
                if selected_type == "LN" and media_format and media_format != "NOVEL":
                    await interaction.followup.send(
                        embed=build_error_embed(
                            "Conflicting Format",
                            "Light Novel selection requires the AniList Novel format.",
                        ),
                        ephemeral=True,
                    )
                    return
                media_id = await self._fetch_filtered_random_media(
                    selected_type, genre=genre, year_from=year_from, year_to=year_to,
                    status=status, media_format=media_format,
                    excluded_ids=self._extract_seen_ids(seen_urls),
                )
                if not media_id:
                    await interaction.followup.send(
                        embed=build_error_embed(
                            "No Random Results",
                            "AniList returned no titles matching these filters. Try broader criteria.",
                        ),
                        ephemeral=True,
                    )
                    return
                api_type = "MANGA" if selected_type == "LN" else selected_type
                detailed_media = await self.fetch_detailed_media(media_id, api_type)
                if not detailed_media:
                    await interaction.followup.send(
                        embed=build_error_embed(
                            "Lookup Failed",
                            "A filtered title was selected, but its details could not be loaded.",
                        ),
                        ephemeral=True,
                    )
                    return
                enhanced_embed = await self.create_enhanced_embed(detailed_media, selected_type)
                progress_embed = None if selected_type == "LN" else await self.create_progress_embed(
                    detailed_media, selected_type, interaction.guild_id,
                )
                if progress_embed:
                    await interaction.followup.send(
                        embed=enhanced_embed,
                        view=self.PageView(
                            enhanced_embed, progress_embed, selected_type,
                            cog=self, owner_id=interaction.user.id,
                            filters={
                                "genre": genre, "year_from": year_from, "year_to": year_to,
                                "status": status, "media_format": media_format,
                            },
                            seen_urls=seen_urls,
                        ),
                    )
                else:
                    await interaction.followup.send(
                        embed=enhanced_embed,
                        view=RandomResultView(
                            self, interaction.user.id, selected_type,
                            {
                                "genre": genre, "year_from": year_from, "year_to": year_to,
                                "status": status, "media_format": media_format,
                            },
                            source_url=enhanced_embed.url, seen_urls=seen_urls,
                        ),
                    )
                return

            # Existing unfiltered random selection remains unchanged.
            # Fetch basic random media first to get the ID
            logger.info(f"Fetching random {selected_type} for user {interaction.user.id}")
            basic_embed = None
            for _ in range(5 if seen_urls else 1):
                candidate_embed = await fetch_random_media(selected_type)
                if not candidate_embed or candidate_embed.url not in (seen_urls or set()):
                    basic_embed = candidate_embed
                    break

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
                        view = self.PageView(
                            enhanced_embed, progress_embed, selected_type,
                            cog=self, owner_id=interaction.user.id,
                            filters={
                                "genre": genre, "year_from": year_from, "year_to": year_to,
                                "status": status, "media_format": media_format,
                            },
                            seen_urls=seen_urls,
                        )
                        await interaction.followup.send(embed=enhanced_embed, view=view)
                        logger.info(f"Successfully sent enhanced random {selected_type} with user progress to user {interaction.user.id}")
                    else:
                        # Just send the enhanced embed without progress
                        await interaction.followup.send(
                            embed=enhanced_embed,
                            view=RandomResultView(
                                self, interaction.user.id, selected_type,
                                {
                                    "genre": genre, "year_from": year_from, "year_to": year_to,
                                    "status": status, "media_format": media_format,
                                },
                                source_url=enhanced_embed.url, seen_urls=seen_urls,
                            ),
                        )
                        logger.info(f"Successfully sent enhanced random {selected_type} to user {interaction.user.id}")
                    return

            # Fallback to basic embed if detailed fetch failed
            basic_embed = self._apply_random_color(basic_embed)
            await interaction.followup.send(
                embed=basic_embed,
                view=RandomResultView(
                    self, interaction.user.id, selected_type,
                    {
                        "genre": genre, "year_from": year_from, "year_to": year_to,
                        "status": status, "media_format": media_format,
                    },
                    source_url=basic_embed.url, seen_urls=seen_urls,
                ),
            )
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
        
        def __init__(
            self, media_embed: discord.Embed, progress_embed: discord.Embed, media_type: str,
            cog=None, owner_id: Optional[int] = None, filters: Optional[Dict] = None,
            seen_urls: Optional[set] = None,
        ):
            super().__init__(timeout=300)
            self.media_embed = media_embed
            self.progress_embed = progress_embed
            self.media_type = media_type
            self.cog = cog
            self.owner_id = owner_id
            self.filters = filters or {}
            self.seen_urls = set(seen_urls or ())
            if media_embed.url:
                self.seen_urls.add(media_embed.url)
            self.current = "info"
            self.rebuild_buttons()

        async def interaction_check(self, interaction: discord.Interaction) -> bool:
            if self.owner_id is not None and interaction.user.id != self.owner_id:
                await interaction.response.send_message("These random controls belong to another user.", ephemeral=True)
                return False
            return True

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

            if self.owner_id is not None and self.cog is not None:
                reroll = Button(label="🎲 Reroll", style=discord.ButtonStyle.primary)

                async def reroll_callback(interaction: discord.Interaction):
                    if interaction.user.id != self.owner_id:
                        await interaction.response.send_message("These random controls belong to another user.", ephemeral=True)
                        return
                    await self.cog._process_random_request(
                        interaction, self.media_type, seen_urls=self.seen_urls, **self.filters,
                    )

                reroll.callback = reroll_callback
                self.add_item(reroll)
                if self.media_embed.url and self.media_embed.url.startswith("https://"):
                    self.add_item(Button(label="Open Source", style=discord.ButtonStyle.link, url=self.media_embed.url))

        async def on_timeout(self):
            """Remove all buttons when view times out."""
            self.clear_items()

    @app_commands.command(
        name="random",
        description="🎲 Get a random Anime, Manga, Light Novel, Novel, Book, Movie, TV Show, Webnovel, or All suggestion"
    )
    @command_meta(section="Media", name="Random")
    @app_commands.describe(
        media_type="Choose the type of media to get a random suggestion for",
        genre="Optional genre or subject filter",
        year_from="Earliest release/publication year",
        year_to="Latest release/publication year",
        status="AniList release status filter",
        media_format="AniList format filter",
    )
    @app_commands.choices(
        media_type=MEDIA_TYPE_CHOICES,
        genre=[
            app_commands.Choice(name="Action", value="Action"),
            app_commands.Choice(name="Adventure", value="Adventure"),
            app_commands.Choice(name="Comedy", value="Comedy"),
            app_commands.Choice(name="Drama", value="Drama"),
            app_commands.Choice(name="Fantasy", value="Fantasy"),
            app_commands.Choice(name="Horror", value="Horror"),
            app_commands.Choice(name="Mystery", value="Mystery"),
            app_commands.Choice(name="Romance", value="Romance"),
            app_commands.Choice(name="Sci-Fi", value="Sci-Fi"),
            app_commands.Choice(name="Thriller", value="Thriller"),
        ],
        status=[
            app_commands.Choice(name="Releasing", value="RELEASING"),
            app_commands.Choice(name="Finished", value="FINISHED"),
            app_commands.Choice(name="Not Yet Released", value="NOT_YET_RELEASED"),
            app_commands.Choice(name="Cancelled", value="CANCELLED"),
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
    )
    async def random_media(
        self, interaction: discord.Interaction, media_type: app_commands.Choice[str],
        genre: Optional[app_commands.Choice[str]] = None,
        year_from: Optional[int] = None, year_to: Optional[int] = None,
        status: Optional[app_commands.Choice[str]] = None,
        media_format: Optional[app_commands.Choice[str]] = None,
    ) -> None:
        """Generate a random media suggestion from AniList.
        
        Args:
            interaction: The Discord interaction
            media_type: The type of media to get a random suggestion for
        """
        logger.info("Random command invoked by %s (%s)", interaction.user, interaction.user.id)
        await self._process_random_request(
            interaction,
            media_type.value,
            genre=genre.value if genre else None,
            year_from=year_from,
            year_to=year_to,
            status=status.value if status else None,
            media_format=media_format.value if media_format else None,
        )


async def setup(bot: commands.Bot):
    """Set up the Random cog."""
    await bot.add_cog(Random(bot))
    logger.info("Random cog successfully loaded")
