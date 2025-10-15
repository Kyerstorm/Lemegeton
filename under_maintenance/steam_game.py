import discord
from discord import app_commands
from discord.ext import commands
import aiohttp
import logging
from difflib import SequenceMatcher
from typing import List, Dict, Optional
from helpers.steam_helper import search_steam_apps, get_steam_app_url, get_app_header_url
import config

# Logging setup
logger = logging.getLogger("SteamGame")

class SteamGame(commands.Cog):
    """Steam game search and details commands."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def _get_app_details(self, session: aiohttp.ClientSession, appid: int) -> Optional[Dict]:
        """Fetch app details from Steam API."""
        try:
            url = f"https://store.steampowered.com/api/appdetails"
            params = {"appids": appid, "cc": "US", "l": "english"}
            async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    if str(appid) in data and data[str(appid)]["success"]:
                        return data[str(appid)]["data"]
            return None
        except Exception as e:
            logger.error(f"Error fetching app details for {appid}: {e}")
            return None

    def _fuzzy_match_games(self, query: str, games: List[Dict], threshold: float = 0.6) -> List[Dict]:
        """Apply fuzzy matching to games list."""
        query_lower = query.lower()
        scored_games = []
        for game in games:
            name = game.get("name", "").lower()
            similarity = SequenceMatcher(None, query_lower, name).ratio()
            if similarity >= threshold:
                scored_games.append((similarity, game))
        scored_games.sort(key=lambda x: x[0], reverse=True)
        return [game for score, game in scored_games[:5]]

    @app_commands.command(name="steam-game", description="Search for a game on Steam")
    @app_commands.describe(game_name="Name of the game to search for")
    async def steam_game(self, interaction: discord.Interaction, game_name: str):
        await interaction.response.defer(ephemeral=True)

        try:
            async with aiohttp.ClientSession() as session:
                # Search for games
                games = await search_steam_apps(session, game_name, max_results=20)
                if not games:
                    await interaction.followup.send("No games found matching your query.", ephemeral=True)
                    return

                # Apply fuzzy matching
                matched_games = self._fuzzy_match_games(game_name, games)
                if not matched_games:
                    await interaction.followup.send("No games found with sufficient match.", ephemeral=True)
                    return

                # Create select menu
                options = [
                    discord.SelectOption(
                        label=game["name"][:100],  # Truncate if too long
                        value=str(game["appid"]),
                        description=f"App ID: {game['appid']}"
                    ) for game in matched_games[:5]
                ]

                select = GameSelect(options, self, session)
                view = discord.ui.View()
                view.add_item(select)

                embed = discord.Embed(
                    title=f"Steam Game Search: {game_name}",
                    description=f"Found {len(matched_games)} matches. Select one for details:",
                    color=discord.Color.blue()
                )

                await interaction.followup.send(embed=embed, view=view, ephemeral=True)

        except Exception as e:
            logger.error(f"Error in steam_game command: {e}")
            await interaction.followup.send("An error occurred while searching.", ephemeral=True)

class GameSelect(discord.ui.Select):
    def __init__(self, options, cog, session):
        super().__init__(placeholder="Choose a game...", options=options)
        self.cog = cog
        self.session = session

    async def callback(self, interaction: discord.Interaction):
        appid = int(self.values[0])
        details = await self.cog._get_app_details(self.session, appid)
        if not details:
            await interaction.response.send_message("Failed to fetch game details.", ephemeral=True)
            return

        # Create embed
        embed = discord.Embed(
            title=details.get("name", "Unknown"),
            description=details.get("short_description", "No description available.")[:500],
            color=discord.Color.blue(),
            url=get_steam_app_url(appid)
        )

        # Price
        price_overview = details.get("price_overview")
        if price_overview:
            price = price_overview.get("final_formatted", "Free")
            embed.add_field(name="Price", value=price, inline=True)
        else:
            embed.add_field(name="Price", value="Free", inline=True)

        # Release date
        release_date = details.get("release_date", {})
        if release_date.get("date"):
            embed.add_field(name="Release Date", value=release_date["date"], inline=True)

        # Genres
        genres = details.get("genres", [])
        if genres:
            genre_names = [g["description"] for g in genres[:3]]
            embed.add_field(name="Genres", value=", ".join(genre_names), inline=True)

        # Platforms
        platforms = details.get("platforms", {})
        platform_list = [k for k, v in platforms.items() if v]
        if platform_list:
            embed.add_field(name="Platforms", value=", ".join(platform_list), inline=True)

        # Header image
        header_image = details.get("header_image")
        if header_image:
            embed.set_image(url=header_image)

        await interaction.response.send_message(embed=embed, ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(SteamGame(bot))
