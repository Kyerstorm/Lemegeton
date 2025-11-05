"""
Steam Game Search Cog
Allows users to search for Steam games by name and view detailed information
with an interactive carousel for browsing results.
"""

import discord
from discord.ext import commands
from discord import app_commands
import aiohttp
import asyncio
import logging
from typing import List, Dict, Optional
from pathlib import Path

# Import helpers
import sys
from pathlib import Path
repo_root = Path(__file__).resolve().parents[2]
if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))

from helpers.steam_helper import (
    search_steam_apps,
    EnhancedGameView,
    random_color
)
from helpers.gaming_utils import (
    is_steam_deck_verified,
    get_controller_support,
    create_steam_deck_badge,
    create_controller_badge,
    get_protondb_url
)
from helpers.command_logger import log_command
from helpers.embed_helper import build_error_embed, build_info_embed
from cogs_test.general_commands.dashboard import command_meta

# Logging setup
logger = logging.getLogger("SteamGame")


# ===== STEAM STORE API FUNCTIONS =====

async def fetch_game_details(session: aiohttp.ClientSession, app_id: int) -> Optional[Dict]:
    """
    Fetch detailed game information from Steam Store API.
    Returns game data dict or None if failed.
    """
    url = "https://store.steampowered.com/api/appdetails"
    params = {
        "appids": app_id,
        "cc": "us",  # Currency: USD
        "l": "english"
    }

    try:
        async with session.get(url, params=params, timeout=10) as resp:
            if resp.status != 200:
                logger.warning(f"Store API returned {resp.status} for app {app_id}")
                return None

            data = await resp.json()

            # Steam API returns: {appid: {success: bool, data: {...}}}
            app_data = data.get(str(app_id), {})

            if app_data.get("success"):
                return app_data.get("data")
            else:
                logger.warning(f"Store API success=false for app {app_id}")
                return None

    except asyncio.TimeoutError:
        logger.error(f"Timeout fetching details for app {app_id}", exc_info=True)
        return None
    except Exception as e:
        logger.error(f"Error fetching game details for {app_id}: {e}", exc_info=True)
        return None


async def batch_fetch_game_details(session: aiohttp.ClientSession,
                                   app_ids: List[int]) -> List[Dict]:
    """
    Fetch details for multiple games concurrently.
    Returns list of game data dicts (None entries for failed fetches).
    """
    tasks = [fetch_game_details(session, app_id) for app_id in app_ids]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    # Filter out exceptions and None values
    valid_results = []
    for result in results:
        if isinstance(result, dict):
            valid_results.append(result)
        elif result is None:
            logger.warning("Game details fetch returned None")
        else:
            logger.error(f"Exception in batch fetch: {result}", exc_info=True)

    return valid_results


# ===== GAME SEARCH VIEW CLASS =====

class GameSearchView(discord.ui.View):
    """Carousel view for browsing top 3 search results"""

    def __init__(self, search_results: List[Dict], game_details: List[Dict],
                 query: str, user_id: int, bot: commands.Bot):
        super().__init__(timeout=180)  # 3 minute timeout
        self.search_results = search_results  # Basic search data
        self.game_details = game_details      # Full Store API data
        self.query = query
        self.user_id = user_id
        self.bot = bot
        self.current_index = 0

    def create_carousel_embed(self, index: int) -> discord.Embed:
        """Create embed for current game in carousel"""

        current_game = self.game_details[index]

        # Extract data
        name = current_game.get("name", "Unknown")
        app_id = current_game.get("steam_appid")
        header_img = current_game.get("header_image")
        short_desc = current_game.get("short_description", "")
        if len(short_desc) > 200:
            short_desc = short_desc[:197] + "..."

        # Price formatting
        price_info = current_game.get("price_overview", {})
        is_free = current_game.get("is_free", False)
        if is_free:
            price = "Free to Play"
            color = discord.Color.green()
        elif price_info:
            final_price = price_info.get("final_formatted", "N/A")
            discount = price_info.get("discount_percent", 0)
            if discount > 0:
                original = price_info.get("initial_formatted")
                price = f"~~{original}~~ **{final_price}** (-{discount}%)"
                color = discord.Color.gold()
            else:
                price = final_price
                color = discord.Color.blue()
        else:
            price = "Price N/A"
            color = discord.Color.dark_gray()

        # Release date & genres
        release_data = current_game.get("release_date", {})
        release = release_data.get("date", "Unknown")
        coming_soon = release_data.get("coming_soon", False)
        is_early_access = any(cat.get("description") == "Early Access" for cat in current_game.get("categories", []))

        genres = [g["description"] for g in current_game.get("genres", [])][:3]
        genre_str = ", ".join(genres) if genres else "Unknown"

        # Steam Deck & Controller support
        deck_compat = is_steam_deck_verified(current_game)
        controller = get_controller_support(current_game)

        # Build embed with enhanced badges
        title_badges = []
        if coming_soon:
            title_badges.append("🔜 Coming Soon")
        elif is_early_access:
            title_badges.append("🚧 Early Access")

        title_suffix = f" ({' • '.join(title_badges)})" if title_badges else ""

        embed = discord.Embed(
            title=f"🎮 {name}{title_suffix}",
            description=short_desc,
            color=color,
            url=f"https://store.steampowered.com/app/{app_id}"
        )

        # Large header image
        if header_img:
            embed.set_image(url=header_img)

        # Info fields - Row 1
        embed.add_field(name="💰 Price", value=price, inline=True)
        embed.add_field(name="📅 Release", value=release, inline=True)
        embed.add_field(name="🎯 Genres", value=genre_str, inline=True)

        # Compatibility badges - Row 2
        compat_badges = []
        if deck_compat:
            compat_badges.append(create_steam_deck_badge(deck_compat))
        if controller:
            compat_badges.append(create_controller_badge(controller))

        if compat_badges:
            embed.add_field(
                name="🎮 Compatibility",
                value="\n".join(compat_badges),
                inline=False
            )

        # Multiplayer support
        categories = [c.get("description", "") for c in current_game.get("categories", [])]
        multiplayer_types = []
        if any("Multi-player" in c for c in categories):
            multiplayer_types.append("Multiplayer")
        if any("Co-op" in c for c in categories):
            multiplayer_types.append("Co-op")
        if any("Online PvP" in c for c in categories):
            multiplayer_types.append("PvP")
        if any("Cross-Platform" in c for c in categories):
            multiplayer_types.append("Cross-Platform")

        if multiplayer_types:
            embed.add_field(
                name="👥 Play Modes",
                value=" • ".join(multiplayer_types),
                inline=True
            )

        # Current players (if available in categories)
        if "Online Co-op" in categories or "Online PvP" in categories:
            embed.add_field(
                name="🔗 Links",
                value=f"[ProtonDB]({get_protondb_url(app_id)}) • [Steam Store](https://store.steampowered.com/app/{app_id})",
                inline=True
            )

        # Show other results in the list
        other_results = []
        for i, result in enumerate(self.search_results):
            if i != index:
                other_results.append(f"• {result['name']}")

        if other_results:
            embed.add_field(
                name="Other Results:",
                value="\n".join(other_results),
                inline=False
            )

        # Footer with position
        embed.set_footer(text=f"Result {index + 1} of {len(self.search_results)} • Search: '{self.query}'")

        return embed

    @discord.ui.button(label="⬅️ Previous", style=discord.ButtonStyle.secondary)
    async def previous_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Navigate to previous game in results"""

        # Verify button ownership
        if interaction.user.id != self.user_id:
            embed = build_error_embed(
                "Permission Denied",
                "This isn't your search!"
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        # Wrap around to last result
        if self.current_index > 0:
            self.current_index -= 1
        else:
            self.current_index = len(self.search_results) - 1

        # Update embed
        embed = self.create_carousel_embed(self.current_index)
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="✅ Select This Game", style=discord.ButtonStyle.primary)
    async def select_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Select current game and show full details"""

        # Verify button ownership
        if interaction.user.id != self.user_id:
            embed = build_error_embed(
                "Permission Denied",
                "This isn't your search!"
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        await interaction.response.defer()

        try:
            # Get selected game data
            selected_game = self.game_details[self.current_index]
            app_id = selected_game.get("steam_appid")

            # Create session for EnhancedGameView
            async with aiohttp.ClientSession() as session:
                # Create full details view
                enhanced_view = EnhancedGameView(
                    selected_game,
                    app_id,
                    session,
                    interaction.user
                )

                # Create main embed
                main_embed = await enhanced_view.create_main_embed()

                # Send full details with interactive buttons (public, not ephemeral)
                await interaction.followup.send(
                    embed=main_embed,
                    view=enhanced_view,
                    ephemeral=False
                )

            # Disable search view buttons
            for item in self.children:
                item.disabled = True
            await interaction.edit_original_response(view=self)

        except discord.NotFound:
            logger.error("Interaction expired before selection could be processed")
        except Exception as e:
            logger.error(f"Error showing game details: {e}", exc_info=True)
            try:
                embed = build_error_embed(
                    "Error Loading Details",
                    "An error occurred while loading game details."
                )
                await interaction.followup.send(embed=embed, ephemeral=True)
            except:
                pass

    @discord.ui.button(label="Next ➡️", style=discord.ButtonStyle.secondary)
    async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Navigate to next game in results"""

        # Verify button ownership
        if interaction.user.id != self.user_id:
            embed = build_error_embed(
                "Permission Denied",
                "This isn't your search!"
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        # Wrap around to first result
        if self.current_index < len(self.search_results) - 1:
            self.current_index += 1
        else:
            self.current_index = 0

        # Update embed
        embed = self.create_carousel_embed(self.current_index)
        await interaction.response.edit_message(embed=embed, view=self)

    async def on_timeout(self):
        """Disable buttons when view times out"""
        for item in self.children:
            item.disabled = True
        # Note: Can't edit message here without storing interaction


# ===== MAIN COG CLASS =====

class SteamGame(commands.Cog):
    """Steam game search and information display"""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        logger.info("SteamGame cog initialized")

    @app_commands.command(
        name="steam-game",
        description="Search for a Steam game and view detailed information"
    )
    @command_meta(section="Gaming", name="Steam Game")
    @app_commands.describe(query="Name of the game to search for")
    @log_command
    async def steam_game(self, interaction: discord.Interaction, query: str):
        """
        Search Steam for games and display interactive results carousel.
        """

        # Validate input
        if not query or len(query.strip()) < 2:
            embed = build_error_embed(
                "Invalid Input",
                "Please provide a game name with at least 2 characters."
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        query = query.strip()

        # Defer response (search + API calls may take time)
        await interaction.response.defer(ephemeral=True)

        try:
            async with aiohttp.ClientSession() as session:
                # Step 1: Search for games
                logger.info(f"Searching Steam for: '{query}'")
                search_results = await search_steam_apps(session, query, max_results=3)

                if not search_results:
                    embed = build_info_embed(
                        f"No Games Found for '{query}'",
                        "Try:\n"
                        "• Checking your spelling\n"
                        "• Using fewer/different keywords\n"
                        "• Searching for the full game title"
                    )
                    await interaction.followup.send(embed=embed, ephemeral=True)
                    return

                # Step 2: Fetch detailed info for top 3 results
                app_ids = [game["appid"] for game in search_results]
                logger.info(f"Fetching details for app IDs: {app_ids}")

                game_details = await batch_fetch_game_details(session, app_ids)

                # Filter out failed fetches
                if not game_details:
                    embed = build_error_embed(
                        "Failed to Fetch Details",
                        "Failed to fetch game details from Steam. Please try again."
                    )
                    await interaction.followup.send(embed=embed, ephemeral=True)
                    return

                # Match search results with detailed data
                # (Some may have failed, so we need to align them)
                matched_results = []
                matched_details = []

                for search_game in search_results:
                    app_id = search_game["appid"]
                    # Find corresponding detailed data
                    detail = next(
                        (d for d in game_details if d.get("steam_appid") == app_id),
                        None
                    )
                    if detail:
                        matched_results.append(search_game)
                        matched_details.append(detail)

                if not matched_details:
                    embed = build_error_embed(
                        "Details Unavailable",
                        "Could not retrieve detailed information for these games. Try again later."
                    )
                    await interaction.followup.send(embed=embed, ephemeral=True)
                    return

                # Step 3: Create carousel view
                view = GameSearchView(
                    matched_results,
                    matched_details,
                    query,
                    interaction.user.id,
                    self.bot
                )

                # Create initial embed (first result)
                initial_embed = view.create_carousel_embed(0)

                # Send interactive carousel
                await interaction.followup.send(
                    embed=initial_embed,
                    view=view,
                    ephemeral=True
                )

                logger.info(f"Steam search completed for '{query}' - {len(matched_results)} results")

        except aiohttp.ClientError as e:
            logger.error(f"Network error during Steam search: {e}", exc_info=True)
            embed = build_error_embed(
                "Network Error",
                "Network error while connecting to Steam. Please try again."
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
        except discord.NotFound:
            logger.error("Interaction expired before command could complete", exc_info=True)
        except Exception as e:
            logger.error(f"Error in steam_game command: {e}", exc_info=True)
            try:
                embed = build_error_embed(
                    "Unexpected Error",
                    "An unexpected error occurred. Please try again later."
                )
                await interaction.followup.send(embed=embed, ephemeral=True)
            except:
                pass

    async def cog_load(self):
        """Called when the cog loads"""
        logger.info("SteamGame cog loaded successfully")

    async def cog_unload(self):
        """Called when the cog unloads"""
        logger.info("SteamGame cog unloaded")


async def setup(bot: commands.Bot):
    """Setup function required for cog loading"""
    await bot.add_cog(SteamGame(bot))
