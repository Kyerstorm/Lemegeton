# cogs/utilities/steam_game.py
import discord
from discord.ext import commands
from discord import app_commands
import aiohttp
import aiosqlite
from bs4 import BeautifulSoup
import asyncio
import textwrap
import re
import math
import random
import io
from typing import Optional
from pathlib import Path
from difflib import SequenceMatcher
try:
    # Import helpers robustly: some deployment environments don't include the
    # project root on sys.path which causes `helpers` to be unresolvable. Try an
    # absolute import first, then add the repository root to sys.path and retry.
    try:
        from helpers.steam_helper import (
            logger, safe_json, fetch_text, chunk_list, random_color, human_hours,
            safe_text, make_friend_grid_image, STEAM_API_KEY, DB_PATH, PIL_AVAILABLE,
            ComparisonView, EnhancedGameView, ScreenshotView,
            create_comparison_embed, get_price_string
        )
    except Exception:
        import sys

        repo_root = Path(__file__).resolve().parents[2]
        if str(repo_root) not in sys.path:
            sys.path.insert(0, str(repo_root))

        # Retry import; capture missing-name errors and provide safe fallbacks
        try:
            from helpers.steam_helper import (
                logger, safe_json, fetch_text, chunk_list, random_color, human_hours,
                safe_text, make_friend_grid_image, STEAM_API_KEY, DB_PATH, PIL_AVAILABLE,
                ComparisonView, EnhancedGameView, ScreenshotView,
                create_comparison_embed, get_price_string
            )
        except Exception as e:
            # If import fails due to missing optional symbols, try importing the
            # common helpers and then define lightweight fallbacks for missing
            # UI classes so the cog can still load.
            from helpers.steam_helper import (
                logger, safe_json, fetch_text, chunk_list, random_color, human_hours,
                safe_text, make_friend_grid_image, STEAM_API_KEY, DB_PATH, PIL_AVAILABLE,
                ComparisonView, ScreenshotView, EnhancedGameView,
                create_comparison_embed, get_price_string
            )
except ModuleNotFoundError:
    # Some deployment environments don't put the project root on sys.path.
    # Try to add the repo root (two levels up from this file: ../..) to sys.path
    # and re-import. This makes the cog robust when run as a module from
    # different working directories.
    repo_root = Path(__file__).resolve().parents[2]
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))

    # Retry import; let any remaining ImportError bubble up to surface the
    # real problem (missing package, typo, etc.).
    from helpers.steam_helper import (
        logger, safe_json, fetch_text, chunk_list, random_color, human_hours,
        safe_text, make_friend_grid_image, STEAM_API_KEY, DB_PATH, PIL_AVAILABLE,
        ComparisonView, EnhancedGameView, ScreenshotView,
        create_comparison_embed, get_price_string
    )


# -------------------- Cog --------------------
class SteamGame(commands.Cog):
    """Steam game search cog with advanced filtering and enhanced game display."""

    # Add an application command group so these methods become slash commands
    steam_group = app_commands.Group(name="steam", description="Steam related commands")

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # -------------------- Enhanced Game search command --------------------
    @steam_group.command(name="game", description="Search for a game on Steam with optional filters")
    @app_commands.describe(game_name="Name of the game", genre="Filter by genre", max_price="Maximum price (USD)", platform="Platform (windows/mac/linux)", tag="Tag to filter", sort_by="Sort by (relevance/price/release_date/reviews)")
    async def game(self, interaction: discord.Interaction, game_name: str, genre: Optional[str] = None, max_price: Optional[float] = None, platform: Optional[str] = None, tag: Optional[str] = None, sort_by: str = "relevance"):
        await interaction.response.defer(ephemeral=True)
        
        # Build search URL with filters
        search_params = {
            "term": game_name,
            "l": "en",
            "cc": "us",
            "category1": "998"  # Games category
        }
        
        # Add genre filter
        if genre:
            genre_map = {
                "action": "19", "adventure": "25", "casual": "597", "indie": "492",
                "massively multiplayer": "128", "racing": "699", "rpg": "122",
                "simulation": "599", "sports": "701", "strategy": "2"
            }
            if genre.lower() in genre_map:
                search_params["category2"] = genre_map[genre.lower()]
        
        search_url = f"https://store.steampowered.com/api/storesearch/"
        
        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(search_url, params=search_params) as resp:
                    if resp.status != 200:
                        return await interaction.followup.send(f"❌ Failed to search for '{game_name}'")
                    search_data = await resp.json()
            except Exception:
                return await interaction.followup.send("❌ Failed to search Steam.")

        items = search_data.get("items", [])
        if not items:
            return await interaction.followup.send(f"❌ No results found for '{game_name}'" + 
                                                 (f" with filters" if any([genre, max_price, platform, tag]) else ""))

        # Filter to only include games and DLC (exclude demos, videos, soundtracks, etc.)
        items = [item for item in items if item.get("type", "").lower() in ["game", "dlc"]]
        
        if not items:
            return await interaction.followup.send(f"❌ No games or DLC found for '{game_name}'" + 
                                                 (f" with filters" if any([genre, max_price, platform, tag]) else ""))

        # Apply fuzzy matching to improve search results
        items = self._fuzzy_match_games(game_name, items)
        
        # Apply additional filters
        filtered_items = await self._apply_filters(session, items, max_price, platform, tag)
        
        # Sort results
        filtered_items = self._sort_results(filtered_items, sort_by)
        
        top_items = filtered_items[:5]  # Show top 5 instead of 3
        view = discord.ui.View(timeout=120)  # Longer timeout for complex view

        for item in top_items:
            await self._create_game_button(view, item, session)

        filter_info = []
        if genre: filter_info.append(f"Genre: {genre}")
        if max_price: filter_info.append(f"Max Price: ${max_price}")
        if platform: filter_info.append(f"Platform: {platform}")
        if tag: filter_info.append(f"Tag: {tag}")
        if sort_by != "relevance": filter_info.append(f"Sort: {sort_by}")
        
        filter_text = f" | Filters: {', '.join(filter_info)}" if filter_info else ""
        
        try:
            await interaction.followup.send(
                content=f"🎮 **Steam Game Search Results** ({len(filtered_items)} found){filter_text}\n"
                       f"Select a game for detailed information:",
                view=view, ephemeral=True
            )
        except Exception:
            try:
                await interaction.response.send_message(
                    content=f"🎮 **Steam Game Search Results** ({len(filtered_items)} found){filter_text}\n"
                           f"Select a game for detailed information:",
                    view=view, ephemeral=True
                )
            except Exception:
                pass

    # ==================== ENHANCED GAME SEARCH HELPER METHODS ====================
    
    def _fuzzy_match_games(self, query, items, threshold=0.6):
        """
        Apply fuzzy matching to search results to improve relevance.
        Returns items sorted by similarity score, filtering out low matches.
        
        Args:
            query: User's search query
            items: List of game items from Steam API
            threshold: Minimum similarity score (0.0-1.0) to include in results
        """
        query_lower = query.lower()
        scored_items = []
        
        for item in items:
            name = item.get("name", "").lower()
            
            # Calculate similarity score using SequenceMatcher
            similarity = SequenceMatcher(None, query_lower, name).ratio()
            
            # Boost score for exact substring matches
            if query_lower in name:
                similarity = min(1.0, similarity + 0.3)
            
            # Boost score for word-level matches
            query_words = set(query_lower.split())
            name_words = set(name.split())
            if query_words.issubset(name_words):
                similarity = min(1.0, similarity + 0.2)
            
            # Only include items above threshold
            if similarity >= threshold:
                scored_items.append((similarity, item))
        
        # Sort by similarity score (highest first)
        scored_items.sort(key=lambda x: x[0], reverse=True)
        
        # Return sorted items without scores
        return [item for score, item in scored_items]
    
    async def _apply_filters(self, session, items, max_price=None, platform=None, tag=None):
        """Apply additional filters to search results"""
        if not any([max_price, platform, tag]):
            return items
        
        filtered_items = []
        
        for item in items[:20]:  # Limit API calls
            try:
                appid = item["id"]
                app_data = await self._get_app_details(session, appid)
                
                if not app_data:
                    continue
                
                # Price filter
                if max_price is not None:
                    price_info = app_data.get("price_overview")
                    if price_info:
                        price_cents = price_info.get("final", 0)
                        price_dollars = price_cents / 100.0
                        if price_dollars > max_price:
                            continue
                    elif not app_data.get("is_free", False):
                        continue  # Skip if price unknown and not free
                
                # Platform filter
                if platform:
                    platforms = app_data.get("platforms", {})
                    platform_key = platform.lower()
                    if platform_key not in platforms or not platforms[platform_key]:
                        continue
                
                # Tag filter (check categories and tags)
                if tag:
                    tag_lower = tag.lower()
                    categories = app_data.get("categories", [])
                    genres = app_data.get("genres", [])
                    
                    found_tag = False
                    for cat in categories:
                        if tag_lower in cat.get("description", "").lower():
                            found_tag = True
                            break
                    
                    if not found_tag:
                        for genre in genres:
                            if tag_lower in genre.get("description", "").lower():
                                found_tag = True
                                break
                    
                    if not found_tag:
                        continue
                
                # Add enriched item data
                item["_app_data"] = app_data
                filtered_items.append(item)
                
            except Exception as e:
                logger.debug(f"Error filtering item {item.get('id')}: {e}")
                continue
        
        return filtered_items
    
    def _sort_results(self, items, sort_by):
        """Sort search results by specified criteria"""
        if sort_by == "relevance":
            return items  # Already sorted by relevance
        
        def sort_key(item):
            app_data = item.get("_app_data", {})
            
            if sort_by == "price":
                price_info = app_data.get("price_overview")
                if price_info:
                    return price_info.get("final", 0)
                return 0 if app_data.get("is_free") else float('inf')
            
            elif sort_by == "release_date":
                release_info = app_data.get("release_date", {})
                date_str = release_info.get("date", "")
                try:
                    from datetime import datetime
                    # Try to parse date
                    date_obj = datetime.strptime(date_str, "%b %d, %Y")
                    return date_obj.timestamp()
                except:
                    return 0
            
            elif sort_by == "reviews":
                # Sort by positive review percentage
                reviews = app_data.get("reviews", {})
                positive = reviews.get("positive", 0)
                total = reviews.get("total", 1)
                return (positive / total) * 100 if total > 0 else 0
            
            return 0
        
        reverse = sort_by in ["release_date", "reviews"]  # Newest first, best reviews first
        return sorted(items, key=sort_key, reverse=reverse)
    
    async def _get_app_details(self, session, appid):
        """Get detailed app information from Steam API"""
        try:
            url = "https://store.steampowered.com/api/appdetails"
            params = {"appids": appid, "cc": "us", "l": "en"}
            headers = {"User-Agent": "Mozilla/5.0 (compatible; LemegetonBot/1.0)", "Accept-Language": "en-US,en;q=0.9"}
            logger.debug(f"_get_app_details requesting appid={appid} params={params} headers={headers}")
            async with session.get(url, params=params, headers=headers, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                logger.debug(f"_get_app_details resp.status={resp.status} for appid={appid}")
                if resp.status == 200:
                    try:
                        data = await resp.json()
                    except Exception as e:
                        text = await resp.text()
                        logger.debug(f"_get_app_details failed parsing json for {appid}; text[:200]={text[:200]!r}")
                        raise
                    entry = data.get(str(appid))
                    if entry is None:
                        logger.debug(f"_get_app_details no entry for {appid} in response")
                        return None
                    # entry may be {success: bool, data: {...}}
                    if not entry.get("success", False):
                        logger.debug(f"_get_app_details success=false for {appid}; attempting fallback without cc")
                        # Retry without country code (some apps are region-locked or return success:false)
                        params2 = {"appids": appid, "l": "en"}
                        async with session.get(url, params=params2, headers=headers, timeout=aiohttp.ClientTimeout(total=15)) as resp2:
                            logger.debug(f"_get_app_details retry resp.status={resp2.status} for appid={appid}")
                            if resp2.status == 200:
                                try:
                                    data2 = await resp2.json()
                                except Exception:
                                    logger.debug("_get_app_details retry failed to parse json")
                                    return None
                                entry2 = data2.get(str(appid))
                                if entry2 and entry2.get("success", False):
                                    logger.debug(f"_get_app_details retry succeeded for {appid}")
                                    return entry2.get("data")
                        return None
                    appdata = entry.get("data")
                    logger.debug(f"_get_app_details found data for {appid}: {bool(appdata)}")
                    return appdata
        except Exception as e:
            logger.exception(f"Error getting app details for {appid}: {e}")
        return None
    
    async def _create_game_button(self, view, item, session):
        """Create an enhanced game button with rich information"""
        name = item.get("name", "Unknown Game")
        label = name[:75] + "..." if len(name) > 75 else name
        
        button = discord.ui.Button(label=label, style=discord.ButtonStyle.primary)
        
        async def enhanced_callback(button_inter: discord.Interaction):
            # Defer publicly so the detailed embed is posted to the channel (not ephemeral)
            await button_inter.response.defer(ephemeral=False)
            
            appid = item["id"]
            app_data = item.get("_app_data")

            # Prefer cached data; otherwise try to use the provided session if it's still open.
            if not app_data:
                try:
                    use_session = None
                    if session is not None and not getattr(session, "closed", False):
                        use_session = session
                    if use_session is not None:
                        app_data = await self._get_app_details(use_session, appid)
                    else:
                        logger.debug(f"enhanced_callback: provided session closed or None for appid={appid}; creating temp session")
                        async with aiohttp.ClientSession() as tmp_sess:
                            app_data = await self._get_app_details(tmp_sess, appid)
                except Exception:
                    logger.exception(f"enhanced_callback: exception while fetching app details for appid={appid}")
                    # final attempt with a fresh session
                    try:
                        async with aiohttp.ClientSession() as tmp_sess:
                            app_data = await self._get_app_details(tmp_sess, appid)
                    except Exception:
                        logger.exception(f"enhanced_callback: final attempt failed for appid={appid}")

            if not app_data:
                logger.warning(f"enhanced_callback: failed to load app_data for appid={appid} name={name}")
                return await button_inter.followup.send(f"❌ Could not load details for '{name}'", ephemeral=False)
            
            # Create enhanced game view and send embed; guard against embed creation errors
            try:
                game_view = EnhancedGameView(app_data, appid, session, button_inter.user)
                embed = await game_view.create_main_embed()
                # Send non-ephemeral so the embed is visible to the channel
                await button_inter.followup.send(embed=embed, view=game_view, ephemeral=False)
                logger.debug(f"enhanced_callback: sent enhanced embed for appid={appid} name={name}")
            except Exception as e:
                logger.exception(f"enhanced_callback: failed to build/send embed for appid={appid} name={name}: {e}")
                # Fallback: send a simple text/embed with basic info so the user gets something
                try:
                    simple_embed = discord.Embed(title=name, url=f"https://store.steampowered.com/app/{appid}", description="Details unavailable; displaying a quick link.", color=discord.Color.dark_gray())
                    await button_inter.followup.send(embed=simple_embed, ephemeral=False)
                except Exception:
                    try:
                        await button_inter.followup.send(f"❌ Could not display detailed info for '{name}', but you can view it on the store: https://store.steampowered.com/app/{appid}", ephemeral=False)
                    except Exception:
                        logger.exception(f"enhanced_callback: failed to send fallback message for appid={appid} name={name}")
        
        button.callback = enhanced_callback
        view.add_item(button)


# -------------------- Setup --------------------
async def setup(bot: commands.Bot):
    cog = SteamGame(bot)
    await bot.add_cog(cog)
    # Register the app command group with the bot tree so bot.py's sync logic will detect & sync it
    try:
        # Avoid duplicate registration errors if already present
        if not any(cmd.name == cog.steam_group.name for cmd in bot.tree.get_commands()):
            bot.tree.add_command(cog.steam_group)
            logger.info("Registered app command group: /steam")
        else:
            logger.debug("App command group '/steam' already registered in tree")
    except Exception as e:
        logger.debug(f"Failed to add steam command group to tree: {e}")