import discord
from discord.ext import commands
from discord import app_commands
import aiohttp
import asyncio
import random
import re
import logging
from pathlib import Path
from cogs_test.general_commands.dashboard import command_meta

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
ANILIST_ENDPOINT = "https://graphql.anilist.co"
TYPE_COLORS = {"ANIME": 0x1E90FF, "MANGA": 0xFF69B4, "LN": 0x8A2BE2}
TYPE_ICONS = {"ANIME": "🎬", "MANGA": "📖", "LN": "📚"}
REQUEST_TIMEOUT = 10


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
        media_type="Choose Anime, Manga, Light Novels, or All"
    )
    @app_commands.choices(
        media_type=[
            app_commands.Choice(name="Anime 🎬", value="ANIME"),
            app_commands.Choice(name="Manga 📖", value="MANGA"),
            app_commands.Choice(name="Light Novels 📚", value="LN"),
            app_commands.Choice(name="All 🌐", value="ALL")
        ]
    )
    async def trending(
        self,
        interaction: discord.Interaction,
        media_type: app_commands.Choice[str] = None
    ):
        selected_type = media_type.value if media_type else "ANIME"
        logger.info(f"Trending command invoked by {interaction.user} (ID: {interaction.user.id}) - Type: {selected_type}")
        
        await interaction.response.defer()

        try:
            # Handle "ALL" option
            media_types_to_fetch = []
            if selected_type == "ALL":
                media_types_to_fetch = [("ANIME", "ANIME"), ("MANGA", "MANGA"), ("MANGA", "LN")]
                logger.info("Fetching trending data for all media types")
            else:
                label = selected_type
                fetch_type = "MANGA" if label == "LN" else label
                media_types_to_fetch = [(fetch_type, label)]
                logger.info(f"Fetching trending data for {label}")

            all_embeds = []

            for fetch_type, label in media_types_to_fetch:
                logger.info(f"Processing {label} trending data (API type: {fetch_type})")
                media_list = await self._fetch_trending(fetch_type, label)
                
                if not media_list:
                    logger.warning(f"No trending results found for {label}")
                    continue
                
                logger.info(f"Found {len(media_list)} trending {label} entries")
                for i, media in enumerate(media_list):
                    embed = self._build_embed_entry(media, i + 1, label)
                    all_embeds.append(embed)

            if not all_embeds:
                logger.warning(f"No trending results found for any requested types: {[label for _, label in media_types_to_fetch]}")
                await interaction.followup.send("⚠️ No trending results found.", ephemeral=True)
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
            logger.error(f"Exception in trending command for {interaction.user} (ID: {interaction.user.id}): {e}")
            await interaction.followup.send("❌ An error occurred while fetching trending data. Please try again later.", ephemeral=True)

    async def _fetch_trending(self, fetch_type: str, label: str):
        """Fetch trending data from AniList API"""
        query = """
        query ($type: MediaType) {
          Page(page: 1, perPage: 10) {
            media(type: $type, sort: TRENDING_DESC) {
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
        
        variables = {"type": fetch_type}
        
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT)) as session:
                logger.info(f"Making API request to AniList for {label} trending data")
                async with session.post(
                    ANILIST_ENDPOINT,
                    json={"query": query, "variables": variables}
                ) as resp:
                    if resp.status != 200:
                        logger.warning(f"AniList API returned status {resp.status} for {label}")
                        return []

                    data = await resp.json()
                    logger.info(f"Successfully received API response for {label}")

        except asyncio.TimeoutError:
            logger.error(f"Timeout while fetching {label} trending data")
            return []
        except Exception as e:
            logger.error(f"Failed to fetch AniList trending data for {label}: {e}")
            return []

        # Process response
        page_data = data.get("data", {}).get("Page") if data else None
        if not page_data:
            logger.warning(f"No Page data returned from AniList for {label}: {data}")
            return []

        media_list = page_data.get("media", [])
        
        # Filter for light novels if needed
        if label == "LN":
            original_count = len(media_list)
            media_list = [m for m in media_list if m.get("format") == "NOVEL"]
            logger.info(f"Filtered {original_count} manga entries to {len(media_list)} light novels")

        logger.info(f"Successfully processed {len(media_list)} {label} trending entries")
        return media_list

    def _build_embed_entry(self, media: dict, rank: int, label: str):
        """Build a Discord embed for a single trending media entry"""
        color = discord.Color(TYPE_COLORS.get(label, 0x00CED1))
        
        title_data = media.get("title") or {}
        title = title_data.get("english") or title_data.get("romaji") or "Unknown Title"
        url = media.get("siteUrl") or "#"
        trending_score = media.get("trending") or 0
        format_ = media.get("format") or "Unknown"
        status = media.get("status") or "Unknown"
        episodes = media.get("episodes") or media.get("chapters") or "N/A"
        genres = ", ".join(media.get("genres") or []) or "N/A"
        avg_score = media.get("averageScore") or "N/A"

        # Clean description
        raw_desc = media.get("description") or "No description available"
        clean_desc = re.sub(r"<[^>]+>", "", raw_desc)
        clean_desc = (clean_desc[:500] + "...") if len(clean_desc) > 500 else clean_desc

        embed = discord.Embed(
            title=f"{TYPE_ICONS.get(label, '')} #{rank} • {title}",
            description=(
                f"**Trending Score:** {trending_score}\n"
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
            await interaction.response.send_message("❌ Only the command user can navigate.", ephemeral=True)
            return
            
        self.current = (self.current - 1) % len(self.embeds)
        logger.info(f"User {interaction.user} navigated to previous page ({self.current+1}/{len(self.embeds)})")
        await self.update_message(interaction)

    @discord.ui.button(label="➡️ Next", style=discord.ButtonStyle.secondary)
    async def next(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ Only the command user can navigate.", ephemeral=True)
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

        # AniList GraphQL query with full details
        query = """
        query ($type: MediaType) {
          Page(page: 1, perPage: 10) {
            media(type: $type, sort: TRENDING_DESC) {
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

        async def fetch_trending(fetch_type: str, label: str):
            variables = {"type": fetch_type}
            async with aiohttp.ClientSession() as session:
                try:
                    async with session.post(
                        "https://graphql.anilist.co",
                        json={"query": query, "variables": variables},
                        timeout=10
                    ) as resp:
                        if resp.status != 200:
                            # Log the failure
                            logger.warning(f"AniList request failed with status {resp.status}")
                            return []

                        data = await resp.json()
                except Exception as e:
                    logger.error(f"Failed to fetch AniList trending: {e}")
                    return []

            # Check if response contains data
            page_data = data.get("data", {}).get("Page") if data else None
            if not page_data:
                logger.warning(f"No Page data returned from AniList: {data}")
                return []

            media_list = page_data.get("media", [])
            if label == "LN":
                media_list = [m for m in media_list if m.get("format") == "NOVEL"]

            return media_list


        def build_embed_entry(m: dict, rank: int, label: str):
            type_colors = {"ANIME": 0x1E90FF, "MANGA": 0xFF69B4, "LN": 0x8A2BE2}
            color = discord.Color(type_colors.get(label, 0x00CED1))
            type_icons = {"ANIME": "🎬", "MANGA": "📖", "LN": "📚"}

            title_data = m.get("title") or {}
            title = title_data.get("english") or title_data.get("romaji") or "Unknown Title"
            url = m.get("siteUrl") or "#"
            score = m.get("trending") or 0
            format_ = m.get("format") or "Unknown"
            status = m.get("status") or "Unknown"
            episodes = m.get("episodes") or m.get("chapters") or "N/A"
            genres = ", ".join(m.get("genres") or []) or "N/A"
            avg_score = m.get("averageScore") or "N/A"

            # Clean description
            raw_desc = m.get("description") or "No description available"
            clean_desc = re.sub(r"<[^>]+>", "", raw_desc)
            clean_desc = (clean_desc[:500] + "...") if len(clean_desc) > 500 else clean_desc

            embed = discord.Embed(
                title=f"{type_icons.get(label, '')} #{rank} • {title}",
                description=(
                    f"Trending Score: {score}\n"
                    f"Format: {format_}\n"
                    f"Status: {status}\n"
                    f"Episodes/Chapters: {episodes}\n"
                    f"Genres: {genres}\n"
                    f"Average Score: {avg_score}\n\n"
                    f"Description: {clean_desc}"
                ),
                color=color
            )

            cover_url = m.get("coverImage", {}).get("large")
            if cover_url:
                embed.set_thumbnail(url=cover_url)

            embed.set_author(
                name="AniList Trending",
                url="https://anilist.co/",
                icon_url="https://anilist.co/img/icons/android-chrome-512x512.png"
            )

async def setup(bot: commands.Bot):
    await bot.add_cog(Trending(bot))
