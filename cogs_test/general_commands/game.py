"""IGDB-first game information with optional Steam store enrichment."""
from __future__ import annotations
import asyncio
import logging
from difflib import SequenceMatcher
import aiohttp
import discord
from discord import app_commands
from discord.ext import commands
import helpers.igdb_helper as igdb
from helpers.steam_helper import search_steam_apps
from cogs.gaming.steam_game import fetch_game_details
from helpers.gaming_utils import is_steam_deck_verified, get_controller_support
from cogs_test.general_commands.dashboard import command_meta

log = logging.getLogger(__name__)

async def fetch_igdb_details(session: aiohttp.ClientSession, slug: str, token: str) -> dict | None:
    """Fetch extended fields through the repository's existing IGDB authentication configuration."""
    safe_slug = "".join(ch for ch in slug if ch.isalnum() or ch in "-_")
    if not safe_slug or not igdb.IGDB_CLIENT_ID:
        return None
    query = f"""
    where slug = "{safe_slug}";
    fields name,slug,summary,cover.image_id,genres.name,platforms.name,
      involved_companies.company.name,involved_companies.developer,
      involved_companies.publisher,first_release_date,franchise.name,
      game_modes.name,status.name,websites.url,websites.category;
    limit 1;
    """
    headers = {"Client-ID": igdb.IGDB_CLIENT_ID, "Authorization": f"Bearer {token}", "Accept": "application/json"}
    try:
        async with session.post(f"{igdb.IGDB_API_URL}/games", headers=headers, data=query, timeout=igdb.API_TIMEOUT) as response:
            if response.status != 200:
                log.warning("IGDB detail query returned HTTP %s", response.status)
                return None
            data = await response.json()
            return data[0] if isinstance(data, list) and data else None
    except (aiohttp.ClientError, asyncio.TimeoutError, ValueError) as exc:
        log.warning("IGDB detail lookup failed: %s", exc)
        return None

def game_embed(game: dict, details: dict | None, steam_data: dict | None) -> discord.Embed:
    data = details or game
    name = data.get("name") or game.get("name") or "Unknown game"
    embed = discord.Embed(
        title=f"🎮 {name}"[:256],
        url=(f"https://www.igdb.com/games/{data.get('slug') or game.get('slug')}" if (data.get("slug") or game.get("slug")) else None),
        description=(data.get("summary") or "No synopsis is available from IGDB.")[:3500],
        color=discord.Color.blurple(),
    )
    cover = igdb.get_cover_image_url(data.get("cover") or game.get("cover") or {})
    if cover:
        embed.set_thumbnail(url=cover)
    for label, key in (("Genres", "genres"), ("Platforms", "platforms"), ("Game modes", "game_modes")):
        values = data.get(key) or []
        names = [item.get("name") for item in values if isinstance(item, dict) and item.get("name")]
        if names:
            embed.add_field(name=label, value=", ".join(names[:10])[:1024], inline=True)
    companies = data.get("involved_companies") or []
    developers = [item.get("company", {}).get("name") for item in companies if item.get("developer") and item.get("company")]
    publishers = [item.get("company", {}).get("name") for item in companies if item.get("publisher") and item.get("company")]
    if developers:
        embed.add_field(name="👨‍💻 Developers", value=", ".join(dict.fromkeys(developers))[:1024], inline=True)
    if publishers:
        embed.add_field(name="🏢 Publishers", value=", ".join(dict.fromkeys(publishers))[:1024], inline=True)
    release = data.get("first_release_date")
    if isinstance(release, (int, float)):
        embed.add_field(name="📅 First release", value=f"<t:{int(release)}:D>", inline=True)
    franchise = data.get("franchise")
    if isinstance(franchise, dict) and franchise.get("name"):
        embed.add_field(name="🧩 Franchise", value=franchise["name"][:1024], inline=True)
    if steam_data:
        app_id = steam_data.get("steam_appid")
        if app_id:
            embed.add_field(name="🛒 Steam", value=f"[Store page](https://store.steampowered.com/app/{app_id}/)", inline=True)
        price = steam_data.get("price_overview") or {}
        if steam_data.get("is_free"):
            embed.add_field(name="💰 Steam price", value="Free to Play", inline=True)
        elif price.get("final_formatted"):
            text = price["final_formatted"]
            if price.get("discount_percent"):
                text += f" (-{price['discount_percent']}%)"
            embed.add_field(name="Steam price", value=text[:1024], inline=True)
        deck = is_steam_deck_verified(steam_data)
        if deck:
            embed.add_field(name="🕹️ Steam Deck", value=str(deck)[:1024], inline=True)
        controller = get_controller_support(steam_data)
        if controller:
            embed.add_field(name="🎮 Controller support", value=str(controller)[:1024], inline=True)
    else:
        embed.add_field(name="Steam listing", value="No matching result was returned by the Steam search. This does not prove the game is unavailable on Steam.", inline=False)
    embed.set_footer(text="🎮 Game metadata: IGDB · Store details, when available: Steam")
    return embed

class GameSelect(discord.ui.Select):
    def __init__(self, cog: "Game", owner_id: int, results: list[dict]):
        self.cog = cog
        self.owner_id = owner_id
        self.results_by_slug = {str(item.get("slug")): item for item in results if item.get("slug")}
        options = [
            discord.SelectOption(label=str(item.get("name") or "Unknown game")[:100], value=str(item["slug"])[:100], description=str(item.get("slug") or "")[:100])
            for item in results[:25] if item.get("slug")
        ]
        super().__init__(placeholder="🎮 Choose the correct game", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction) -> None:
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message("Only the user who started this search can choose a result.", ephemeral=True)
            return
        selected = self.results_by_slug.get(self.values[0])
        if not selected:
            await interaction.response.send_message("That search result is no longer available.", ephemeral=True)
            return
        await interaction.response.defer()
        embed = await self.cog.resolve_embed(selected)
        await interaction.edit_original_response(embed=embed, view=None)

class GameSelectView(discord.ui.View):
    def __init__(self, cog: "Game", owner_id: int, results: list[dict]):
        super().__init__(timeout=180)
        self.add_item(GameSelect(cog, owner_id, results))

class Game(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def resolve_embed(self, game: dict) -> discord.Embed:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=20)) as session:
            token = await igdb.get_access_token(session)
            details = await fetch_igdb_details(session, str(game.get("slug") or ""), token) if token else None
            steam_data = None
            try:
                steam_matches = await search_steam_apps(session, (details or game).get("name", ""), max_results=5)
                wanted = str((details or game).get("name", "")).casefold().strip()
                exact = next((item for item in steam_matches if str(item.get("name", "")).casefold().strip() == wanted), None)
                if exact:
                    app_id = exact.get("appid") or exact.get("app_id")
                    if app_id:
                        steam_data = await fetch_game_details(session, int(app_id))
            except (aiohttp.ClientError, asyncio.TimeoutError, ValueError, TypeError):
                log.info("Steam enrichment unavailable for selected game")
        return game_embed(game, details, steam_data)

    @app_commands.command(name="game", description="Search IGDB game metadata and matching Steam store details")
    @app_commands.guild_only()
    @app_commands.describe(title="Game title to search for")
    @command_meta(section="Gaming", name="Game")
    async def game(self, interaction: discord.Interaction, title: str) -> None:
        if len(title.strip()) < 2:
            await interaction.response.send_message("Enter at least two characters for the game title.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True, thinking=True)
        if not igdb.IGDB_CLIENT_ID or not igdb.IGDB_CLIENT_SECRET:
            await interaction.followup.send("IGDB is unavailable because IGDB_CLIENT_ID or IGDB_CLIENT_SECRET is not configured. No game metadata was fabricated.", ephemeral=True)
            return
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=20)) as session:
                token = await igdb.get_access_token(session)
                safe_query = title.strip().replace(chr(34), " ").replace(chr(59), " ").replace(chr(92), " ").strip()
                results = await igdb.search_games(session, token, safe_query, limit=10) if token and safe_query else []
            if not results:
                await interaction.followup.send("IGDB returned no matches or could not be reached. Check provider credentials and try again.", ephemeral=True)
                return
            best = max(results, key=lambda item: SequenceMatcher(None, title.casefold(), str(item.get("name", "")).casefold()).ratio())
            ratio = SequenceMatcher(None, title.casefold(), str(best.get("name", "")).casefold()).ratio()
            if len(results) == 1 or ratio >= 0.92:
                await interaction.followup.send(embed=await self.resolve_embed(best), ephemeral=True)
                return
            selectable = [item for item in results if item.get("slug")]
            if not selectable:
                await interaction.followup.send("IGDB returned matches without selectable identifiers. Try a more specific title.", ephemeral=True)
                return
            await interaction.followup.send("🔎 **Several games match.** Choose the correct title below. Steam details are added only for an exact title match.", view=GameSelectView(self, interaction.user.id, selectable), ephemeral=True)
        except (aiohttp.ClientError, asyncio.TimeoutError, ValueError) as exc:
            log.warning("Game search failed: %s", exc)
            await interaction.followup.send("Game search is temporarily unavailable. Please try again later.", ephemeral=True)

async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Game(bot))
