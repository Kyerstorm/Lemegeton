"""
Steam API Helper Functions
Centralized functions for Steam API interactions, data processing, and image generation
"""

import asyncio
import io
import logging
import math
import os
import random
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple

import aiohttp
import discord
from bs4 import BeautifulSoup

# Optional Pillow for friend-grid image rendering
try:
    from PIL import Image, ImageDraw, ImageFont
    PIL_AVAILABLE = True
except (ImportError, Exception):
    PIL_AVAILABLE = False

# Configuration constants
LOG_DIR = Path("logs")
LOG_FILE = LOG_DIR / "steam_helper.log"

# Ensure logs directory exists
LOG_DIR.mkdir(exist_ok=True)

# Set up file-based logging
logger = logging.getLogger("SteamHelper")
logger.setLevel(logging.DEBUG)

# Clear handlers to avoid duplicates
logger.handlers.clear()

# Create file handler
file_handler = logging.FileHandler(LOG_FILE, mode='w', encoding='utf-8')
file_handler.setLevel(logging.DEBUG)

# Create formatter
formatter = logging.Formatter(
    fmt="[%(asctime)s] [%(levelname)-8s] [%(name)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
file_handler.setFormatter(formatter)

# Add handler to logger
logger.addHandler(file_handler)

logger.info("Steam Helper logging system initialized")

# Configuration constants for Steam API
# Provide default values so cogs importing them won't fail
STEAM_API_KEY = os.getenv("STEAM_API_KEY", "")

# Import DB_PATH from main config to use the main database
import sys
from pathlib import Path
repo_root = Path(__file__).resolve().parents[1]
if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))

try:
    import config
    DB_PATH = config.DB_PATH
except ImportError:
    # Fallback if config import fails
    DB_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "database.db")


# ===== HTTP REQUEST HELPERS =====

async def safe_json(session: aiohttp.ClientSession, url: str, params: Optional[Dict] = None, timeout: int = 15) -> Optional[Dict]:
    """
    Safely make HTTP request and return JSON response.
    """
    try:
        async with session.get(url, params=params, timeout=timeout) as resp:
            if resp.status != 200:
                logger.debug(f"safe_json - {url} returned {resp.status}")
                return None
            return await resp.json()
    except Exception as e:
        logger.exception(f"safe_json failed for {url}: {e}")
        return None


async def fetch_text(session: aiohttp.ClientSession, url: str, timeout: int = 15) -> Optional[str]:
    """
    Safely fetch text content from URL.
    """
    try:
        async with session.get(url, timeout=timeout) as resp:
            if resp.status != 200:
                logger.debug(f"fetch_text - {url} returned {resp.status}")
                return None
            return await resp.text()
    except Exception as e:
        logger.exception(f"fetch_text failed for {url}: {e}")
        return None


async def fetch_steam_avatar(session: aiohttp.ClientSession, avatar_url: str) -> Optional[bytes]:
    """
    Fetch Steam avatar image as bytes.
    """
    if not avatar_url:
        return None
    
    try:
        async with session.get(avatar_url) as resp:
            if resp.status == 200:
                return await resp.read()
    except Exception as e:
        logger.debug(f"Failed to fetch avatar {avatar_url}: {e}")
    
    return None


# ===== STEAM API HELPERS =====

async def resolve_vanity_url(session: aiohttp.ClientSession, api_key: str, vanity_name: str) -> Optional[str]:
    """
    Resolve Steam vanity URL to SteamID64.
    """
    data = await safe_json(
        session,
        "https://api.steampowered.com/ISteamUser/ResolveVanityURL/v1/",
        params={"key": api_key, "vanityurl": vanity_name}
    )
    
    if data and data.get("response", {}).get("success") == 1:
        return data["response"]["steamid"]
    
    return None


async def get_player_summaries(session: aiohttp.ClientSession, api_key: str, steamids: str) -> List[Dict]:
    """
    Get player summaries from Steam API.
    """
    data = await safe_json(
        session,
        "https://api.steampowered.com/ISteamUser/GetPlayerSummaries/v2/",
        params={"key": api_key, "steamids": steamids}
    )
    
    if data:
        return data.get("response", {}).get("players", [])
    
    return []


async def get_user_friends(session: aiohttp.ClientSession, api_key: str, steamid: str) -> List[Dict]:
    """
    Get user's friends list from Steam API.
    """
    data = await safe_json(
        session,
        "https://api.steampowered.com/ISteamUser/GetFriendList/v1/",
        params={"key": api_key, "steamid": steamid}
    )
    
    if data:
        return data.get("friendslist", {}).get("friends", [])
    
    return []


async def get_owned_games(session: aiohttp.ClientSession, api_key: str, steamid: str, include_appinfo: bool = True) -> List[Dict]:
    """
    Get user's owned games from Steam API.
    """
    params = {
        "key": api_key,
        "steamid": steamid,
        "include_appinfo": 1 if include_appinfo else 0,
        "include_played_free_games": 1
    }
    
    data = await safe_json(
        session,
        "https://api.steampowered.com/IPlayerService/GetOwnedGames/v1/",
        params=params
    )
    
    if data:
        return data.get("response", {}).get("games", [])
    
    return []


async def get_recently_played_games(session: aiohttp.ClientSession, api_key: str, steamid: str) -> List[Dict]:
    """
    Get user's recently played games from Steam API.
    """
    data = await safe_json(
        session,
        "https://api.steampowered.com/IPlayerService/GetRecentlyPlayedGames/v1/",
        params={"key": api_key, "steamid": steamid}
    )
    
    if data:
        return data.get("response", {}).get("games", [])
    
    return []


async def search_steam_apps(session: aiohttp.ClientSession, query: str, max_results: int = 10) -> List[Dict]:
    """
    Search Steam apps using Steam Community API (returns JSON).
    """
    try:
        # Use Steam Community search endpoint (returns clean JSON)
        search_url = f"https://steamcommunity.com/actions/SearchApps/{query}"

        data = await safe_json(session, search_url, timeout=10)
        if not data:
            logger.debug(f"No JSON data returned for query: {query}")
            return []

        # Steam Community API returns a list of results
        results = []
        for item in data[:max_results]:
            try:
                app_id = item.get('appid')
                name = item.get('name', 'Unknown')
                icon = item.get('icon')  # Small icon URL
                logo = item.get('logo')  # Larger logo URL

                if app_id:
                    results.append({
                        "appid": int(app_id),
                        "name": name,
                        "img_icon_url": logo or icon  # Prefer logo over icon
                    })
            except Exception as e:
                logger.debug(f"Error parsing search result: {e}")
                continue

        logger.info(f"Found {len(results)} results for '{query}'")
        return results

    except Exception as e:
        logger.error(f"Error searching Steam apps: {e}")
        return []


# ===== DATA PROCESSING HELPERS =====

def chunk_list(lst: List, n: int) -> List[List]:
    """
    Split list into chunks of size n.
    """
    return [lst[i:i + n] for i in range(0, len(lst), n)]


def safe_text(s: Any, fallback: str = "N/A") -> str:
    """
    Safely convert value to string with fallback.
    """
    if not s:
        return fallback
    return str(s)


def human_hours(minutes: int) -> str:
    """
    Convert minutes to human-readable hours format.
    """
    if minutes < 60:
        return f"{minutes}m"
    return f"{minutes // 60}h"


def format_playtime(minutes: int) -> str:
    """
    Format playtime minutes into readable string.
    """
    if minutes == 0:
        return "Never played"
    elif minutes < 60:
        return f"{minutes} minutes"
    elif minutes < 1440:  # Less than 24 hours
        hours = minutes // 60
        mins = minutes % 60
        if mins == 0:
            return f"{hours} hour{'s' if hours != 1 else ''}"
        return f"{hours}h {mins}m"
    else:  # 24+ hours
        hours = minutes // 60
        return f"{hours:,.1f} hours"


def get_steam_app_url(app_id: int) -> str:
    """
    Generate Steam store URL for app.
    """
    return f"https://store.steampowered.com/app/{app_id}/"


def get_steam_profile_url(steamid: str) -> str:
    """
    Generate Steam profile URL.
    """
    return f"https://steamcommunity.com/profiles/{steamid}/"


def get_steam_avatar_url(avatar_hash: str, size: str = "full") -> str:
    """
    Generate Steam avatar URL from hash.
    """
    if not avatar_hash:
        return ""
    
    size_suffix = ""
    if size == "small":
        size_suffix = ""
    elif size == "medium":
        size_suffix = "_medium"
    elif size == "full":
        size_suffix = "_full"
    
    return f"https://steamcdn-a.akamaihd.net/steamcommunity/public/images/avatars/{avatar_hash[:2]}/{avatar_hash}{size_suffix}.jpg"


# ===== DISCORD UTILITIES =====

def random_color() -> discord.Color:
    """
    Get random Discord color from predefined palette.
    """
    palette = [
        discord.Color.blurple(), discord.Color.blue(), discord.Color.teal(),
        discord.Color.green(), discord.Color.gold(), discord.Color.purple(),
        discord.Color.dark_blue(), discord.Color.dark_teal()
    ]
    return random.choice(palette)


def create_steam_profile_embed(player_data: Dict, games_count: int = 0, playtime_total: int = 0) -> discord.Embed:
    """
    Create Discord embed for Steam profile.
    """
    name = player_data.get("personaname", "Unknown")
    steamid = player_data.get("steamid", "")
    avatar = player_data.get("avatarfull", "")
    profile_url = player_data.get("profileurl", "")
    
    # Parse persona state
    state = player_data.get("personastate", 0)
    status_map = {
        0: "Offline",
        1: "Online",
        2: "Busy",
        3: "Away",
        4: "Snooze",
        5: "Looking to trade",
        6: "Looking to play"
    }
    status = status_map.get(state, "Unknown")
    
    # Create embed
    embed = discord.Embed(
        title=f"Steam Profile: {name}",
        url=profile_url,
        color=random_color()
    )
    
    if avatar:
        embed.set_thumbnail(url=avatar)
    
    embed.add_field(name="Status", value=status, inline=True)
    embed.add_field(name="SteamID", value=steamid, inline=True)
    
    if games_count > 0:
        embed.add_field(name="Games Owned", value=f"{games_count:,}", inline=True)
    
    if playtime_total > 0:
        embed.add_field(name="Total Playtime", value=format_playtime(playtime_total), inline=True)
    
    # Add profile creation date if available
    if "timecreated" in player_data:
        import datetime
        created = datetime.datetime.fromtimestamp(player_data["timecreated"])
        embed.add_field(name="Member Since", value=created.strftime("%B %Y"), inline=True)
    
    return embed


def create_game_search_embed(games: List[Dict], query: str) -> discord.Embed:
    """
    Create Discord embed for game search results.
    """
    embed = discord.Embed(
        title=f"Steam Search: {query}",
        color=random_color()
    )
    
    if not games:
        embed.description = "No games found."
        return embed
    
    results = []
    for game in games[:10]:  # Limit to 10 results
        name = game.get("name", "Unknown")
        app_id = game.get("appid", "")
        url = get_steam_app_url(app_id) if app_id else ""
        
        if url:
            results.append(f"[{name}]({url})")
        else:
            results.append(name)
    
    embed.description = "\n".join(results)
    embed.set_footer(text=f"Showing {len(results)} of {len(games)} results")
    
    return embed


# ===== IMAGE GENERATION HELPERS =====

def make_friend_grid_image(friends_slice: List[Dict], thumb_size: int = 96, per_row: int = 5) -> Optional[io.BytesIO]:
    """
    Generate friend grid image using Pillow (optional).
    Returns BytesIO png or None if PIL not available.
    """
    if not PIL_AVAILABLE:
        logger.warning("PIL not available for friend grid generation")
        return None
    
    if not friends_slice:
        return None
    
    # Calculate grid dimensions
    cols = min(per_row, max(1, len(friends_slice)))
    rows = math.ceil(len(friends_slice) / per_row)
    padding = 12
    name_height = 20
    width = cols * (thumb_size + padding) + padding
    height = rows * (thumb_size + name_height + padding) + padding

    # Create image
    image = Image.new("RGBA", (width, height), (30, 30, 30, 255))
    draw = ImageDraw.Draw(image)

    # Try to use a TTF font if available
    try:
        font = ImageFont.truetype("arial.ttf", 14)
    except Exception:
        try:
            font = ImageFont.load_default()
        except Exception:
            font = None

    # Draw friends
    x = padding
    y = padding
    idx = 0
    
    for friend in friends_slice:
        avatar_bytes = friend.get("avatar_bytes")
        
        try:
            if avatar_bytes:
                av = Image.open(io.BytesIO(avatar_bytes)).convert("RGBA")
                av = av.resize((thumb_size, thumb_size))
                image.paste(av, (x, y), av)
            else:
                # Draw placeholder rectangle
                draw.rectangle([x, y, x + thumb_size, y + thumb_size], fill=(60, 60, 60))
        except Exception as e:
            logger.debug(f"Error processing friend avatar: {e}")
            # Draw placeholder rectangle
            draw.rectangle([x, y, x + thumb_size, y + thumb_size], fill=(60, 60, 60))
        
        # Draw name under avatar
        name = (friend.get("name") or "Unknown")[:22]
        tx = x
        ty = y + thumb_size + 4
        draw.text((tx, ty), name, fill=(240, 240, 240), font=font)
        
        # Move to next position
        x += thumb_size + padding
        idx += 1
        
        if idx % per_row == 0:
            x = padding
            y += thumb_size + name_height + padding

    # Save to BytesIO
    out = io.BytesIO()
    image.save(out, "PNG")
    out.seek(0)
    return out


# ===== VALIDATION HELPERS =====

def is_valid_steamid64(steamid: str) -> bool:
    """
    Validate SteamID64 format.
    """
    if not steamid or not steamid.isdigit():
        return False
    
    # SteamID64 should be 17 digits and start with 765
    return len(steamid) == 17 and steamid.startswith("765")


def is_valid_vanity_name(vanity: str) -> bool:
    """
    Validate Steam vanity name format.
    """
    if not vanity or len(vanity) < 3 or len(vanity) > 32:
        return False
    
    # Basic alphanumeric check (Steam allows some special chars but this is a safe subset)
    import re
    return bool(re.match(r'^[a-zA-Z0-9_-]+$', vanity))


# ===== CACHE HELPERS =====

def get_app_icon_url(app_id: int, icon_hash: str) -> str:
    """
    Generate Steam app icon URL.
    """
    if not icon_hash:
        return ""
    
    return f"https://steamcdn-a.akamaihd.net/steamcommunity/public/images/apps/{app_id}/{icon_hash}.jpg"


def get_app_header_url(app_id: int) -> str:
    """
    Generate Steam app header image URL.
    """
    return f"https://steamcdn-a.akamaihd.net/steam/apps/{app_id}/header.jpg"


# ===== ASYNC UTILITIES =====

async def batch_fetch_player_data(
    session: aiohttp.ClientSession,
    api_key: str,
    steamids: List[str],
    batch_size: int = 100
) -> List[Dict]:
    """
    Fetch player data for multiple SteamIDs in batches.
    """
    all_players = []
    
    for i in range(0, len(steamids), batch_size):
        batch = steamids[i:i + batch_size]
        steamids_str = ",".join(batch)
        
        players = await get_player_summaries(session, api_key, steamids_str)
        all_players.extend(players)
        
        # Small delay between batches to be nice to Steam API
        if i + batch_size < len(steamids):
            await asyncio.sleep(0.1)
    
    return all_players


# ===== UI COMPONENTS AND HELPERS =====
# Minimal stub implementations of View classes needed by steam.py

class ComparisonView(discord.ui.View):
    """Minimal stub for steam game comparison view."""
    def __init__(self):
        super().__init__(timeout=300)

class RecommendationView(discord.ui.View):
    """Interactive view for browsing game recommendations."""

    def __init__(self, recommendations, user):
        super().__init__(timeout=300)
        self.recommendations = recommendations
        self.user = user
        self.current_index = 0

    @discord.ui.button(label="⬅️ Previous", style=discord.ButtonStyle.secondary)
    async def previous_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Show previous recommendation"""
        if interaction.user.id != self.user.id:
            return await interaction.response.send_message("❌ This isn't your recommendation menu!", ephemeral=True)

        if self.current_index > 0:
            self.current_index -= 1
        else:
            self.current_index = len(self.recommendations) - 1

        embed = await self._create_recommendation_embed(
            self.recommendations[self.current_index],
            self.current_index + 1,
            len(self.recommendations)
        )
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="Next ➡️", style=discord.ButtonStyle.secondary)
    async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Show next recommendation"""
        if interaction.user.id != self.user.id:
            return await interaction.response.send_message("❌ This isn't your recommendation menu!", ephemeral=True)

        if self.current_index < len(self.recommendations) - 1:
            self.current_index += 1
        else:
            self.current_index = 0

        embed = await self._create_recommendation_embed(
            self.recommendations[self.current_index],
            self.current_index + 1,
            len(self.recommendations)
        )
        await interaction.response.edit_message(embed=embed, view=self)

    async def _create_recommendation_embed(self, game_data, index, total):
        """Create embed for a recommendation"""
        # Extract details from recommendation structure
        details = game_data.get("details", {})
        app_id = game_data.get("app_id", 0)
        match_score = game_data.get("score", 0)
        match_reasons = game_data.get("match_reasons", [])

        name = details.get("name", "Unknown Game")
        description = details.get("short_description", "No description available")[:500]

        embed = discord.Embed(
            title=f"🎮 {name}",
            url=f"https://store.steampowered.com/app/{app_id}",
            description=description,
            color=discord.Color.blue()
        )

        # Header image
        header_image = details.get("header_image")
        if header_image:
            embed.set_image(url=header_image)

        # Price
        price_info = details.get("price_overview", {})
        is_free = details.get("is_free", False)

        if is_free:
            price_str = "Free to Play"
            embed.color = discord.Color.green()
        elif price_info:
            price_str = price_info.get("final_formatted", "Unknown")
            discount = price_info.get("discount_percent", 0)
            if discount > 0:
                original = price_info.get("initial_formatted", "")
                price_str = f"~~{original}~~ **{price_str}** (-{discount}%)"
                embed.color = discord.Color.gold()
        else:
            price_str = "Price Unknown"

        embed.add_field(name="💰 Price", value=price_str, inline=True)

        # Match score (normalize to percentage)
        match_percent = min(100, match_score * 3)  # Scale score to percentage
        embed.add_field(name="🎯 Match Score", value=f"{match_percent:.0f}%", inline=True)

        # Release date
        release_date = details.get("release_date", {}).get("date", "Unknown")
        embed.add_field(name="📅 Release", value=release_date, inline=True)

        # Genres
        genres = [g.get("description", "") for g in details.get("genres", [])]
        if genres:
            embed.add_field(name="🏷️ Genres", value=", ".join(genres[:3]), inline=False)

        # Match reasons
        if match_reasons:
            reasons_text = "\n".join(f"• {reason}" for reason in match_reasons[:3])
            embed.add_field(name="✨ Why this matches", value=reasons_text, inline=False)

        embed.set_footer(text=f"Recommendation {index}/{total} • Click to view on Steam")

        return embed

class EnhancedGameView(discord.ui.View):
    """Enhanced game view with detailed information and interactive buttons."""
    
    def __init__(self, app_data, appid, session, user):
        super().__init__(timeout=300)
        self.app_data = app_data
        self.appid = appid
        self.session = session
        self.user = user
        
        # Extract screenshots and movies from app_data
        self.screenshots = app_data.get("screenshots", [])
        self.movies = app_data.get("movies", [])
    
    async def create_main_embed(self):
        """Create the main game information embed"""
        name = self.app_data.get("name", "Unknown Game")
        description = self.app_data.get("short_description", "No description available.")
        if len(description) > 300:
            description = description[:297] + "..."
        
        header_image = self.app_data.get("header_image", "")
        
        # Get genre and pricing info
        genres = [g["description"] for g in self.app_data.get("genres", [])]
        price_info = self.app_data.get("price_overview", {})
        is_free = self.app_data.get("is_free", False)
        release_date = self.app_data.get("release_date", {}).get("date", "Unknown")
        
        # Format price
        if is_free:
            price_str = "Free to Play"
            color = discord.Color.green()
        elif price_info:
            price_str = price_info.get("final_formatted", "Price unknown")
            discount = price_info.get("discount_percent", 0)
            if discount > 0:
                original = price_info.get("initial_formatted", "")
                price_str = f"~~{original}~~ → **{price_str}** ({discount}% off)"
                color = discord.Color.gold()
            else:
                color = discord.Color.blue()
        else:
            price_str = "Price not available"
            color = discord.Color.dark_gray()
        
        embed = discord.Embed(
            title=name,
            description=description,
            color=color,
            url=f"https://store.steampowered.com/app/{self.appid}"
        )
        
        if header_image:
            embed.set_image(url=header_image)
        
        embed.add_field(name="💰 Price", value=price_str, inline=True)
        embed.add_field(name="📅 Release Date", value=release_date, inline=True)
        embed.add_field(name="🎮 Genres", value=", ".join(genres[:3]) if genres else "Unknown", inline=True)
        
        # Add additional info
        platform_info = self._format_platform_info()
        if platform_info:
            embed.add_field(name="🖥️ Platforms", value=platform_info, inline=True)
        
        dev_pub_info = self._format_developer_publisher()
        if dev_pub_info:
            embed.add_field(name="👥 Developer/Publisher", value=dev_pub_info, inline=True)
        
        additional_features = self._format_additional_features()
        if additional_features:
            embed.add_field(name="✨ Features", value=additional_features, inline=False)
        
        return embed
    
    def _format_platform_info(self):
        """Format platform support information"""
        platforms = self.app_data.get("platforms", {})
        supported = []
        
        if platforms.get("windows"):
            supported.append("🪟 Windows")
        if platforms.get("mac"):
            supported.append("🍎 Mac")
        if platforms.get("linux"):
            supported.append("🐧 Linux")
        
        return "\n".join(supported) if supported else "❓ Unknown"
    
    def _format_developer_publisher(self):
        """Format developer and publisher information"""
        developers = self.app_data.get("developers", [])
        publishers = self.app_data.get("publishers", [])
        
        dev_str = developers[0] if developers else "Unknown"
        pub_str = publishers[0] if publishers else "Unknown"
        
        if dev_str == pub_str:
            return f"🏢 **{dev_str}**"
        else:
            return f"🏢 **{dev_str}**\n📰 {pub_str}"
    
    def _format_ratings_info(self):
        """Format rating and review information"""
        metacritic = self.app_data.get("metacritic", {})
        
        parts = []
        if metacritic:
            score = metacritic.get("score")
            if score:
                parts.append(f"🏆 Metacritic: {score}/100")
        
        # Add estimated review sentiment (would need Steam reviews API for real data)
        categories = self.app_data.get("categories", [])
        positive_indicators = ["multiplayer", "co-op", "steam achievements"]
        
        for cat in categories:
            desc = cat.get("description", "").lower()
            if any(indicator in desc for indicator in positive_indicators):
                parts.append("👍 Community Features")
                break
        
        return "\n".join(parts) if parts else "📊 No ratings available"
    
    async def _get_player_count(self):
        """Attempt to get current player count"""
        # This would require additional API calls to Steam Charts or similar
        # For now, return a placeholder
        return "📈 See Steam Charts"
    
    def _format_genres_tags(self):
        """Format genres and popular tags"""
        genres = [g["description"] for g in self.app_data.get("genres", [])]
        categories = [c["description"] for c in self.app_data.get("categories", [])]
        
        # Combine and limit
        all_tags = genres + categories
        display_tags = all_tags[:6]  # Show top 6
        
        if not display_tags:
            return "🏷️ No tags available"
        
        tag_str = " • ".join(display_tags)
        if len(all_tags) > 6:
            tag_str += f" • +{len(all_tags) - 6} more"
        
        return tag_str
    
    def _format_system_requirements(self):
        """Format system requirements (brief version)"""
        pc_req = self.app_data.get("pc_requirements")
        if not pc_req:
            return None
        
        minimum = pc_req.get("minimum", "")
        if minimum:
            # Extract key info (simplified)
            if "Windows" in minimum:
                return "🪟 Windows Compatible"
            elif "Mac" in minimum:
                return "🍎 Mac Compatible" 
            elif "Linux" in minimum:
                return "🐧 Linux Compatible"
        
        return "⚙️ See Steam page for details"
    
    def _format_additional_features(self):
        """Format additional game features"""
        features = []
        categories = self.app_data.get("categories", [])
        
        feature_mapping = {
            "Multi-player": "👥 Multiplayer",
            "Co-op": "🤝 Cooperative",
            "Steam Achievements": "🏆 Achievements", 
            "Steam Trading Cards": "🃏 Trading Cards",
            "Steam Workshop": "🔧 Workshop",
            "Steam Cloud": "☁️ Cloud Saves",
            "Controller Support": "🎮 Controller",
            "VR Support": "🥽 VR Ready"
        }
        
        for cat in categories:
            desc = cat.get("description", "")
            for key, icon_desc in feature_mapping.items():
                if key.lower() in desc.lower():
                    features.append(icon_desc)
                    break
        
        return " • ".join(features[:5]) if features else None
    
    @discord.ui.button(label="📷 Screenshots", style=discord.ButtonStyle.secondary)
    async def view_screenshots(self, interaction: discord.Interaction, button: discord.ui.Button):
        """View game screenshots carousel"""
        if not self.screenshots:
            return await interaction.response.send_message("📷 No screenshots available for this game.", ephemeral=True)
        
        await interaction.response.defer()
        
        screenshot_view = ScreenshotView(self.screenshots, self.app_data.get("name", "Game"))
        embed = screenshot_view.create_screenshot_embed(0)
        
        await interaction.followup.send(embed=embed, view=screenshot_view, ephemeral=True)
    
    @discord.ui.button(label="📹 Videos", style=discord.ButtonStyle.secondary) 
    async def view_videos(self, interaction: discord.Interaction, button: discord.ui.Button):
        """View game trailers and videos"""
        if not self.movies:
            return await interaction.response.send_message("📹 No videos available for this game.", ephemeral=True)
        
        await interaction.response.defer()
        
        video_embed = self._create_video_embed()
        await interaction.followup.send(embed=video_embed, ephemeral=True)
    
    @discord.ui.button(label="⚙️ System Requirements", style=discord.ButtonStyle.secondary)
    async def view_requirements(self, interaction: discord.Interaction, button: discord.ui.Button):
        """View detailed system requirements"""
        await interaction.response.defer()
        
        req_embed = self._create_requirements_embed()
        await interaction.followup.send(embed=req_embed, ephemeral=True)
    
    @discord.ui.button(label="🎯 Similar Games", style=discord.ButtonStyle.primary)
    async def find_similar(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Find similar games based on tags and genres"""
        await interaction.response.defer()
        
        similar_embed = await self._create_similar_games_embed()
        await interaction.followup.send(embed=similar_embed, ephemeral=True)
    
    @discord.ui.button(label="💾 Save Game", style=discord.ButtonStyle.success)
    async def save_game(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Save game to user's personal list"""
        # This would integrate with your bot's database
        await interaction.response.send_message(
            f"💾 **{self.app_data.get('name')}** has been saved to your game list!", 
            ephemeral=True
        )
    
    def _create_video_embed(self):
        """Create embed with video information"""
        name = self.app_data.get("name", "Game")
        embed = discord.Embed(title=f"📹 {name} - Videos", color=0xFF0000)
        
        video_list = []
        for i, movie in enumerate(self.movies[:5], 1):
            movie_name = movie.get("name", f"Video {i}")
            thumbnail = movie.get("thumbnail")
            mp4_url = movie.get("mp4", {}).get("480") or movie.get("webm", {}).get("480")
            
            if mp4_url:
                video_list.append(f"[{movie_name}]({mp4_url})")
            else:
                video_list.append(movie_name)
        
        if video_list:
            embed.description = "\n".join(video_list)
        else:
            embed.description = "No video links available"
        
        if self.movies and self.movies[0].get("thumbnail"):
            embed.set_thumbnail(url=self.movies[0]["thumbnail"])
        
        return embed
    
    def _create_requirements_embed(self):
        """Create detailed system requirements embed"""
        name = self.app_data.get("name", "Game")
        embed = discord.Embed(title=f"⚙️ {name} - System Requirements", color=0x00FF00)
        
        pc_req = self.app_data.get("pc_requirements", {})
        mac_req = self.app_data.get("mac_requirements", {})
        linux_req = self.app_data.get("linux_requirements", {})
        
        if pc_req.get("minimum"):
            min_req = pc_req["minimum"].replace("<br>", "\n").replace("<strong>", "**").replace("</strong>", "**")
            # Remove HTML tags
            import re
            min_req = re.sub('<[^<]+?>', '', min_req)
            embed.add_field(name="🪟 Windows - Minimum", value=min_req[:1000], inline=False)
        
        if pc_req.get("recommended"):
            rec_req = pc_req["recommended"].replace("<br>", "\n").replace("<strong>", "**").replace("</strong>", "**")
            rec_req = re.sub('<[^<]+?>', '', rec_req)
            embed.add_field(name="🪟 Windows - Recommended", value=rec_req[:1000], inline=False)
        
        if not pc_req and not mac_req and not linux_req:
            embed.description = "System requirements not available for this game."
        
        return embed
    
    async def _create_similar_games_embed(self):
        """Create embed with similar game suggestions"""
        name = self.app_data.get("name", "Game")
        embed = discord.Embed(title=f"🎯 Games Similar to {name}", color=0x9B59B6)
        
        # Extract tags for similarity matching
        genres = [g["description"] for g in self.app_data.get("genres", [])]
        tags = [c["description"] for c in self.app_data.get("categories", [])]
        all_tags = genres + tags
        
        # This would ideally use Steam's recommendation API or similar
        # For now, provide general suggestions based on genre
        similar_suggestions = []
        
        if "Action" in genres:
            similar_suggestions.extend(["DOOM Eternal", "Cyberpunk 2077", "Grand Theft Auto V"])
        if "RPG" in genres:
            similar_suggestions.extend(["The Witcher 3", "Skyrim", "Fallout 4"])
        if "Strategy" in genres:
            similar_suggestions.extend(["Age of Empires IV", "Civilization VI", "StarCraft II"])
        if "Indie" in genres:
            similar_suggestions.extend(["Hades", "Celeste", "Hollow Knight"])
        
        # Remove duplicates and limit
        unique_suggestions = list(dict.fromkeys(similar_suggestions))[:8]
        
        if unique_suggestions:
            embed.description = "Based on genres and tags:\n" + "\n".join(f"• {game}" for game in unique_suggestions)
        else:
            embed.description = "No similar games found. Try browsing Steam's recommendation system!"
        
        embed.add_field(name="🏷️ Shared Tags", value=" • ".join(all_tags[:5]), inline=False)
        
        return embed

class ScreenshotView(discord.ui.View):
    """Screenshot carousel view with navigation buttons."""
    
    def __init__(self, screenshots, game_name):
        super().__init__(timeout=300)
        self.screenshots = screenshots
        self.game_name = game_name
        self.current_index = 0
    
    def create_screenshot_embed(self, index):
        """Create embed for a specific screenshot"""
        if not self.screenshots or index >= len(self.screenshots):
            embed = discord.Embed(title="📷 No Screenshots", description="No screenshots available.", color=discord.Color.dark_gray())
            return embed
        
        screenshot = self.screenshots[index]
        embed = discord.Embed(
            title=f"📷 {self.game_name} - Screenshots",
            color=discord.Color.blue()
        )
        
        if isinstance(screenshot, dict):
            img_url = screenshot.get("path_full") or screenshot.get("path_thumbnail")
        else:
            img_url = screenshot
        
        if img_url:
            embed.set_image(url=img_url)
        
        embed.set_footer(text=f"Screenshot {index + 1}/{len(self.screenshots)}")
        return embed
    
    @discord.ui.button(label="⬅️ Previous", style=discord.ButtonStyle.secondary)
    async def previous_screenshot(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Go to previous screenshot"""
        if self.current_index > 0:
            self.current_index -= 1
        else:
            self.current_index = len(self.screenshots) - 1
        
        embed = self.create_screenshot_embed(self.current_index)
        await interaction.response.edit_message(embed=embed, view=self)
    
    @discord.ui.button(label="Next ➡️", style=discord.ButtonStyle.secondary)
    async def next_screenshot(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Go to next screenshot"""
        if self.current_index < len(self.screenshots) - 1:
            self.current_index += 1
        else:
            self.current_index = 0
        
        embed = self.create_screenshot_embed(self.current_index)
        await interaction.response.edit_message(embed=embed, view=self)


# ===== IMPORT GAMING UTILITIES =====
try:
    from helpers.gaming_utils import (
        gaming_cache, connection_pool, cached_api_request, batch_api_requests,
        format_playtime, format_price, get_steam_profile_url, get_steam_game_url,
        get_protondb_url, is_steam_deck_verified, get_controller_support,
        create_steam_deck_badge, create_controller_badge,
        ProfilePrivateError, ProfileNotFoundError, SteamAPIError
    )
    GAMING_UTILS_AVAILABLE = True
    logger.info("Gaming utilities imported successfully")
except ImportError as e:
    GAMING_UTILS_AVAILABLE = False
    logger.warning(f"Gaming utilities not available: {e}")


# ===== ENHANCED BATCH API OPERATIONS =====

async def batch_get_player_summaries(api_key: str, steamids: List[str]) -> Dict[str, Dict]:
    """
    Batch fetch player summaries for multiple Steam IDs
    Returns dict mapping steamid -> player data
    """
    if not GAMING_UTILS_AVAILABLE:
        # Fallback to individual requests
        result = {}
        session = await connection_pool.get_session() if GAMING_UTILS_AVAILABLE else aiohttp.ClientSession()
        try:
            for steamid in steamids:
                players = await get_player_summaries(session, api_key, steamid)
                if players:
                    result[steamid] = players[0]
        finally:
            if not GAMING_UTILS_AVAILABLE:
                await session.close()
        return result

    # Use batched requests with caching
    requests = []
    for steamid in steamids:
        requests.append({
            'url': "https://api.steampowered.com/ISteamUser/GetPlayerSummaries/v2/",
            'params': {"key": api_key, "steamids": steamid},
            'cache_ttl': 3600,  # 1 hour cache
            'cache_key': f"player_summary_{steamid}"
        })

    responses = await batch_api_requests(requests)

    result = {}
    for steamid, response in zip(steamids, responses):
        if response and response.get("response", {}).get("players"):
            result[steamid] = response["response"]["players"][0]

    logger.info(f"Batch fetched {len(result)} player summaries")
    return result


async def get_library_stats(api_key: str, steamid: str) -> Dict[str, Any]:
    """
    Get comprehensive library statistics for a user
    Returns dict with library analytics
    """
    session = await connection_pool.get_session() if GAMING_UTILS_AVAILABLE else aiohttp.ClientSession()

    try:
        # Fetch owned games with app info
        owned = await get_owned_games(session, api_key, steamid, include_appinfo=True)

        if not owned:
            return {
                'total_games': 0,
                'total_playtime': 0,
                'never_played': 0,
                'most_played': [],
                'genres': {},
                'recent_purchases': []
            }

        # Calculate statistics
        total_games = len(owned)
        total_playtime = sum(game.get('playtime_forever', 0) for game in owned)
        never_played = sum(1 for game in owned if game.get('playtime_forever', 0) == 0)

        # Most played games (top 5)
        most_played = sorted(
            owned,
            key=lambda x: x.get('playtime_forever', 0),
            reverse=True
        )[:5]

        # Calculate library value (rough estimate)
        # Average game price $20, sales 50% off = $10 avg
        estimated_value = total_games * 10

        # Calculate percentage of unplayed games
        unplayed_percentage = (never_played / total_games * 100) if total_games > 0 else 0

        stats = {
            'total_games': total_games,
            'total_playtime': total_playtime,
            'total_playtime_hours': total_playtime / 60,
            'never_played': never_played,
            'never_played_percentage': unplayed_percentage,
            'most_played': most_played,
            'estimated_value': estimated_value,
            'average_playtime_per_game': total_playtime / total_games if total_games > 0 else 0
        }

        logger.info(f"Generated library stats for {steamid}: {total_games} games, {total_playtime/60:.1f} hours")
        return stats

    finally:
        if not GAMING_UTILS_AVAILABLE:
            await session.close()


async def get_vac_ban_status(api_key: str, steamid: str) -> Optional[Dict]:
    """
    Check VAC ban status for a user
    Returns dict with ban info or None
    """
    if GAMING_UTILS_AVAILABLE:
        data = await cached_api_request(
            url="https://api.steampowered.com/ISteamUser/GetPlayerBans/v1/",
            params={"key": api_key, "steamids": steamid},
            cache_ttl=86400,  # 24 hour cache
            cache_key=f"vac_ban_{steamid}"
        )
    else:
        session = aiohttp.ClientSession()
        try:
            data = await safe_json(
                session,
                "https://api.steampowered.com/ISteamUser/GetPlayerBans/v1/",
                params={"key": api_key, "steamids": steamid}
            )
        finally:
            await session.close()

    if data and data.get("players"):
        return data["players"][0]

    return None


async def check_profile_privacy(player_data: Dict) -> bool:
    """
    Check if a Steam profile is private
    Returns True if profile is public, False if private
    Raises ProfilePrivateError if private
    """
    communityvisibilitystate = player_data.get("communityvisibilitystate", 1)

    # 1 = Private, 2 = Friends only, 3 = Public
    if communityvisibilitystate == 3:
        return True

    # Profile is private or friends-only
    personaname = player_data.get("personaname", "User")
    if GAMING_UTILS_AVAILABLE:
        raise ProfilePrivateError(f"{personaname}'s profile is private")
    else:
        return False


# Helper functions needed by steam.py
def create_comparison_embed(*args, **kwargs):
    """Minimal stub for comparison embed creation."""
    embed = discord.Embed(title="Steam Game Comparison", color=0x1b2838)
    embed.description = "Comparison functionality temporarily unavailable."
    return embed

def get_price_string(price_info):
    """Extract price string from Steam price info."""
    if not price_info:
        return "Free"
    
    if price_info.get("is_free"):
        return "Free"
    
    initial = price_info.get("initial", 0)
    final = price_info.get("final", 0)
    currency = price_info.get("currency", "USD")
    
    if initial == final:
        return f"${final/100:.2f} {currency}"
    else:
        return f"~~${initial/100:.2f}~~ ${final/100:.2f} {currency}"

def create_recommendation_embed(*args, **kwargs):
    """Minimal stub for recommendation embed creation."""
    embed = discord.Embed(title="Steam Game Recommendations", color=0x1b2838)
    embed.description = "Recommendation functionality temporarily unavailable."
    return embed