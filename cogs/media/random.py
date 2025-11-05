import discord
from discord.ext import commands
from discord import app_commands
from discord.ui import View, Button
import random
import logging
import aiohttp
from pathlib import Path
from typing import List, Dict, Optional

from helpers.media_helper import fetch_random_media
from helpers.embed_helper import build_error_embed
from helpers.anilist_helper import post_graphql
from database import get_all_users_guild_aware
from cogs_test.general_commands.dashboard import command_meta

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
MEDIA_TYPES = ["ANIME", "MANGA", "LN"]
MEDIA_TYPE_CHOICES = [
    app_commands.Choice(name="Anime 🎬", value="ANIME"),
    app_commands.Choice(name="Manga 📖", value="MANGA"),
    app_commands.Choice(name="Light Novel 📚", value="LN"),
    app_commands.Choice(name="All 🎲", value="ALL"),
]


class Random(commands.Cog):
    """Cog for generating random anime, manga, and light novel suggestions."""
    
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        logger.info("Random cog initialized")

    def _get_random_media_type(self) -> str:
        """Select a random media type from available options."""
        return random.choice(MEDIA_TYPES)
    
    def _apply_random_color(self, embed: discord.Embed) -> discord.Embed:
        """Apply a random color to the embed."""
        embed.color = discord.Color(random.randint(0, 0xFFFFFF))
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
            color=discord.Color(random.randint(0, 0xFFFFFF))
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
            color=discord.Color.blue()
        )
        progress_embed.set_footer(text="🎲 Random suggestion from AniList")
        return progress_embed

    async def _process_random_request(self, interaction: discord.Interaction, media_type: str) -> None:
        """Process a random media request with enhanced visual functionality."""
        try:
            # Determine actual media type to fetch
            if media_type.upper() == "ALL":
                selected_type = self._get_random_media_type()
                logger.info(f"User {interaction.user.id} requested random media (all types), selected: {selected_type}")
            else:
                selected_type = media_type.upper()
                logger.info(f"User {interaction.user.id} requested random {selected_type}")

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
        description="🎲 Get a completely random Anime, Manga, Light Novel, or All suggestion from AniList"
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
