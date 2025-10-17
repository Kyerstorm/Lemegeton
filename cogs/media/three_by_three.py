import discord
from discord.ext import commands
from discord import app_commands
import aiohttp
import asyncio
import logging
from typing import Optional, List, Dict, Tuple
import io
import json
import hashlib
from pathlib import Path
from datetime import datetime, timedelta
import database
import re
from difflib import SequenceMatcher

# IGDB integration
try:
    from helpers.igdb_helper import get_game_by_slug, get_cover_image_url, get_access_token
except ImportError:
    get_game_by_slug = None
    get_cover_image_url = None
    get_access_token = None

# Image processing
try:
    from PIL import Image, ImageDraw, ImageFont
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False

# Setup logging
LOG_DIR = Path("logs")
LOG_DIR.mkdir(exist_ok=True)
LOG_FILE = LOG_DIR / "three_by_three.log"

logger = logging.getLogger("ThreeByThree")
logger.setLevel(logging.INFO)

if not logger.handlers:
    try:
        file_handler = logging.FileHandler(LOG_FILE, encoding='utf-8')
        file_handler.setLevel(logging.INFO)
        formatter = logging.Formatter(
            '[%(asctime)s] [%(levelname)s] %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    except Exception as e:
        print(f"Failed to setup file logging for 3x3 generator: {e}")

# AniList API
API_URL = "https://graphql.anilist.co"

# Cache and data directories
DATA_DIR = Path("data")
DATA_DIR.mkdir(exist_ok=True)
COVER_CACHE_DIR = DATA_DIR / "cover_cache"
COVER_CACHE_DIR.mkdir(exist_ok=True)
CACHE_INDEX_FILE = DATA_DIR / "cover_cache_index.json"
PRESETS_FILE = DATA_DIR / "3x3_presets.json"

# Cache TTL: 30 days
CACHE_TTL_DAYS = 30

def parse_anilist_url(url: str) -> Optional[Tuple[str, int]]:
    """
    Parse AniList URL to extract media type and ID.
    
    Args:
        url: AniList URL (e.g., https://anilist.co/anime/98251/AHOGIRL/)
        
    Returns:
        Tuple of (media_type, media_id) or None if invalid
    """
    pattern = r'https?://anilist\.co/(anime|manga|character)/(\d+)/?.*'
    match = re.match(pattern, url.strip())
    
    if match:
        media_type = match.group(1)
        media_id = int(match.group(2))
        return media_type, media_id
    
    return None

def parse_igdb_url(url: str) -> Optional[str]:
    """
    Parse IGDB URL to extract game slug.
    
    Args:
        url: IGDB URL (e.g., https://www.igdb.com/games/pokemon-black-version)
        
    Returns:
        Game slug as string or None if invalid
    """
    pattern = r'https?://(?:www\.)?igdb\.com/games/([a-zA-Z0-9-]+(?:-[a-zA-Z0-9-]+)*)/?.*'
    match = re.match(pattern, url.strip())
    
    if match:
        return match.group(1)
    
    return None

def fuzzy_match_games(query: str, games: List[Dict], threshold: float = 0.6) -> List[Dict]:
    """
    Filter and sort games by similarity to query.
    
    Args:
        query: Search query string
        games: List of game dicts with 'name' field
        threshold: Minimum similarity score (0.0-1.0) to include
    
    Returns:
        Sorted list of games by relevance
    """
    query_lower = query.lower()
    scored_games = []
    
    for game in games:
        name = game.get("name", "").lower()
        
        # Base similarity score
        similarity = SequenceMatcher(None, query_lower, name).ratio()
        
        # Boost exact substring matches
        if query_lower in name:
            similarity = min(1.0, similarity + 0.3)
        
        # Boost word-level matches (all query words in name)
        query_words = set(query_lower.split())
        name_words = set(name.split())
        if query_words.issubset(name_words):
            similarity = min(1.0, similarity + 0.2)
        
        # Only include games above threshold
        if similarity >= threshold:
            scored_games.append((similarity, game))
    
    # Sort by similarity (highest first)
    scored_games.sort(key=lambda x: x[0], reverse=True)
    
    return [game for score, game in scored_games]

# Built-in templates
TEMPLATES = {
    "action": {
        "name": "Action Anime",
        "genre": "Action",
        "media_type": "anime",
        "description": "Top action-packed anime"
    },
    "romance": {
        "name": "Romance Anime",
        "genre": "Romance",
        "media_type": "anime",
        "description": "Best romance anime"
    },
    "shounen": {
        "name": "Shounen Classics",
        "genre": "Shounen",
        "media_type": "manga",
        "description": "Classic shounen manga"
    },
    "80s": {
        "name": "80s Classics",
        "decade": 1980,
        "media_type": "anime",
        "description": "Best anime from the 1980s"
    },
    "90s": {
        "name": "90s Classics",
        "decade": 1990,
        "media_type": "anime",
        "description": "Best anime from the 1990s"
    },
    "2000s": {
        "name": "2000s Classics",
        "decade": 2000,
        "media_type": "anime",
        "description": "Best anime from the 2000s"
    },
    "2010s": {
        "name": "2010s Hits",
        "decade": 2010,
        "media_type": "anime",
        "description": "Popular anime from the 2010s"
    },
    "thriller": {
        "name": "Psychological Thrillers",
        "genre": "Thriller",
        "media_type": "anime",
        "description": "Mind-bending psychological anime"
    },
    "comedy": {
        "name": "Comedy Gold",
        "genre": "Comedy",
        "media_type": "anime",
        "description": "Funniest anime series"
    },
    "fantasy": {
        "name": "Fantasy Worlds",
        "genre": "Fantasy",
        "media_type": "anime",
        "description": "Epic fantasy anime"
    }
}


class CoverCache:
    """Manage cover image caching"""
    
    def __init__(self):
        self.index = self._load_index()
    
    def _load_index(self) -> Dict:
        """Load cache index from disk"""
        if CACHE_INDEX_FILE.exists():
            try:
                with open(CACHE_INDEX_FILE, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"Error loading cache index: {e}")
        return {}
    
    def _save_index(self):
        """Save cache index to disk"""
        try:
            with open(CACHE_INDEX_FILE, 'w', encoding='utf-8') as f:
                json.dump(self.index, f, indent=2)
        except Exception as e:
            logger.error(f"Error saving cache index: {e}")
    
    def _get_cache_key(self, media_id, media_type: str) -> str:
        """Generate cache key from media ID and type"""
        if media_type == "games":
            # For games, media_id is the app ID (integer)
            key_str = f"{media_id}_{media_type.lower()}"
        else:
            key_str = f"{media_id}_{media_type.lower()}"
        return hashlib.md5(key_str.encode()).hexdigest()
    
    def get(self, media_id, media_type: str) -> Optional[Dict]:
        """Get cached cover data"""
        key = self._get_cache_key(media_id, media_type)
        
        if key in self.index:
            entry = self.index[key]
            cache_time = datetime.fromisoformat(entry["cached_at"])
            
            # Check if cache is expired
            if datetime.utcnow() - cache_time > timedelta(days=CACHE_TTL_DAYS):
                logger.debug(f"Cache expired for {media_type} {media_id}")
                return None
            
            # Load cover bytes from file
            cache_file = COVER_CACHE_DIR / f"{key}.png"
            if cache_file.exists():
                try:
                    with open(cache_file, 'rb') as f:
                        cover_bytes = f.read()
                    
                    logger.info(f"Cache HIT for {media_type} {media_id}")
                    return {
                        "title": entry["title"],
                        "cover_url": entry["cover_url"],
                        "cover_bytes": cover_bytes
                    }
                except Exception as e:
                    logger.error(f"Error reading cached cover: {e}")
        
        logger.debug(f"Cache MISS for {media_type} {media_id}")
        return None
    
    def set(self, media_id, media_type: str, data: Dict):
        """Cache cover data"""
        key = self._get_cache_key(media_id, media_type)
        
        try:
            # Save cover bytes to file
            cache_file = COVER_CACHE_DIR / f"{key}.png"
            with open(cache_file, 'wb') as f:
                f.write(data["cover_bytes"])
            
            # Update index
            self.index[key] = {
                "title": data["title"],
                "cover_url": data["cover_url"],
                "cached_at": datetime.utcnow().isoformat(),
                "media_id": media_id,
                "media_type": media_type
            }
            self._save_index()
            
            logger.info(f"Cached cover for {media_type} {media_id}")
        except Exception as e:
            logger.error(f"Error caching cover: {e}")
    
    def cleanup_old_cache(self):
        """Remove expired cache entries"""
        expired_keys = []
        cutoff_date = datetime.utcnow() - timedelta(days=CACHE_TTL_DAYS)
        
        for key, entry in self.index.items():
            cache_time = datetime.fromisoformat(entry["cached_at"])
            if cache_time < cutoff_date:
                expired_keys.append(key)
        
        for key in expired_keys:
            cache_file = COVER_CACHE_DIR / f"{key}.png"
            if cache_file.exists():
                cache_file.unlink()
            del self.index[key]
        
        if expired_keys:
            self._save_index()
            logger.info(f"Cleaned up {len(expired_keys)} expired cache entries")


class PresetManager:
    """Manage user 3x3 presets"""
    
    def __init__(self):
        self.presets = self._load_presets()
    
    def _load_presets(self) -> Dict:
        """Load presets from disk"""
        if PRESETS_FILE.exists():
            try:
                with open(PRESETS_FILE, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"Error loading presets: {e}")
        return {}
    
    def _save_presets(self):
        """Save presets to disk"""
        try:
            with open(PRESETS_FILE, 'w', encoding='utf-8') as f:
                json.dump(self.presets, f, indent=2)
        except Exception as e:
            logger.error(f"Error saving presets: {e}")
    
    def save_preset(self, user_id: int, preset_name: str, urls: List[str], media_type: str):
        """Save a user preset"""
        user_key = str(user_id)
        
        if user_key not in self.presets:
            self.presets[user_key] = {}
        
        self.presets[user_key][preset_name] = {
            "urls": urls,
            "media_type": media_type,
            "created_at": datetime.utcnow().isoformat()
        }
        
        self._save_presets()
        logger.info(f"Saved preset '{preset_name}' for user {user_id}")
    
    def get_preset(self, user_id: int, preset_name: str) -> Optional[Dict]:
        """Get a user preset"""
        user_key = str(user_id)
        
        if user_key in self.presets and preset_name in self.presets[user_key]:
            return self.presets[user_key][preset_name]
        
        return None
    
    def list_presets(self, user_id: int) -> List[str]:
        """List all presets for a user"""
        user_key = str(user_id)
        
        if user_key in self.presets:
            return list(self.presets[user_key].keys())
        
        return []
    
    def delete_preset(self, user_id: int, preset_name: str) -> bool:
        """Delete a user preset"""
        user_key = str(user_id)
        
        if user_key in self.presets and preset_name in self.presets[user_key]:
            del self.presets[user_key][preset_name]
            self._save_presets()
            logger.info(f"Deleted preset '{preset_name}' for user {user_id}")
            return True
        
        return False


class ThreeByThreeModal(discord.ui.Modal):
    """Modal for collecting 9 AniList URLs or IGDB game URLs"""
    
    def __init__(self, media_type: str, cog, preset_name: Optional[str] = None):
        super().__init__(title=f"Create Your 3x3 {media_type.title()} Grid")
        self.media_type = media_type
        self.cog = cog
        self.preset_name = preset_name
        
        # Determine placeholder text based on media type
        if media_type == "games":
            placeholder = "https://www.igdb.com/games/pokemon-black-version"
            label_prefix = "IGDB URL"
        elif media_type == "character":
            placeholder = "https://anilist.co/character/ID/Name/"
            label_prefix = "AniList URL"
        else:
            placeholder = f"https://anilist.co/{media_type}/ID/Title/"
            label_prefix = "AniList URL"
        
        # Create 9 input fields (3 rows)
        self.input1 = discord.ui.TextInput(
            label=f"Row 1 - {label_prefix} 1",
            placeholder=placeholder,
            required=True,
            max_length=200
        )
        self.input2 = discord.ui.TextInput(
            label=f"Row 1 - {label_prefix} 2",
            placeholder=placeholder,
            required=True,
            max_length=200
        )
        self.input3 = discord.ui.TextInput(
            label=f"Row 1 - {label_prefix} 3",
            placeholder=placeholder,
            required=True,
            max_length=200
        )
        self.input4 = discord.ui.TextInput(
            label=f"Row 2 - {label_prefix} 1",
            placeholder=placeholder,
            required=True,
            max_length=200
        )
        self.input5 = discord.ui.TextInput(
            label=f"Row 2 - {label_prefix} 2",
            placeholder=placeholder,
            required=True,
            max_length=200
        )
        
        # Add all fields
        self.add_item(self.input1)
        self.add_item(self.input2)
        self.add_item(self.input3)
        self.add_item(self.input4)
        self.add_item(self.input5)
    
    async def on_submit(self, interaction: discord.Interaction):
        """Handle modal submission - collect first 5 inputs"""
        await interaction.response.defer(ephemeral=True)
        
        # Store first 5 inputs
        inputs = [
            self.input1.value.strip(),
            self.input2.value.strip(),
            self.input3.value.strip(),
            self.input4.value.strip(),
            self.input5.value.strip()
        ]
        
        # Show second modal for remaining 4 inputs
        second_modal = ThreeByThreeModalPart2(self.media_type, inputs, self.cog, self.preset_name)
        await interaction.followup.send("Please enter the remaining 4 inputs:", ephemeral=True)
        await interaction.followup.send("", view=ContinueView(second_modal), ephemeral=True)


class ThreeByThreeModalPart2(discord.ui.Modal):
    """Second modal for collecting remaining 4 inputs"""
    
    def __init__(self, media_type: str, previous_inputs: List[str], cog, preset_name: Optional[str] = None):
        super().__init__(title=f"3x3 Grid - Remaining Inputs")
        self.media_type = media_type
        self.previous_inputs = previous_inputs
        self.cog = cog
        self.preset_name = preset_name
        
        # Determine placeholder text based on media type
        if media_type == "games":
            placeholder = "Enter game name (e.g., Narkaka: Bladepoint)"
            label_prefix = "Game"
        elif media_type == "character":
            placeholder = "https://anilist.co/character/ID/Name/"
            label_prefix = "AniList URL"
        else:
            placeholder = f"https://anilist.co/{media_type}/ID/Title/"
            label_prefix = "AniList URL"
        
        # Remaining 4 fields
        self.input6 = discord.ui.TextInput(
            label=f"Row 2 - {label_prefix} 3",
            placeholder=placeholder,
            required=True,
            max_length=200
        )
        self.input7 = discord.ui.TextInput(
            label=f"Row 3 - {label_prefix} 1",
            placeholder=placeholder,
            required=True,
            max_length=200
        )
        self.input8 = discord.ui.TextInput(
            label=f"Row 3 - {label_prefix} 2",
            placeholder=placeholder,
            required=True,
            max_length=200
        )
        self.input9 = discord.ui.TextInput(
            label=f"Row 3 - {label_prefix} 3",
            placeholder=placeholder,
            required=True,
            max_length=200
        )
        
        self.add_item(self.input6)
        self.add_item(self.input7)
        self.add_item(self.input8)
        self.add_item(self.input9)
    
    async def on_submit(self, interaction: discord.Interaction):
        """Handle second modal submission and generate 3x3"""
        await interaction.response.defer(ephemeral=False)
        
        # Combine all 9 inputs
        all_inputs = self.previous_inputs + [
            self.input6.value.strip(),
            self.input7.value.strip(),
            self.input8.value.strip(),
            self.input9.value.strip()
        ]
        
        # Validate all inputs based on media type
        invalid_inputs = []
        for i, input_val in enumerate(all_inputs, 1):
            if self.media_type == "games":
                # For games, validate IGDB URL format
                parsed = parse_igdb_url(input_val)
                if not parsed:
                    invalid_inputs.append(f"Input {i}: Invalid IGDB URL format")
            else:
                # For AniList types, validate URL format
                parsed = parse_anilist_url(input_val)
                if not parsed:
                    invalid_inputs.append(f"Input {i}: Invalid AniList URL format")
                elif parsed[0] != self.media_type:
                    invalid_inputs.append(f"Input {i}: Must be a {self.media_type} URL")
        
        if invalid_inputs:
            error_msg = "❌ Invalid inputs found:\n" + "\n".join(invalid_inputs)
            if self.media_type == "games":
                error_msg += "\n\nExpected format: https://www.igdb.com/games/game-slug"
            elif self.media_type != "games":
                error_msg += f"\n\nExpected format: https://anilist.co/{self.media_type}/ID/Title/"
            await interaction.followup.send(error_msg, ephemeral=True)
            return
        
        logger.info(f"Generating 3x3 for {interaction.user.name}: {all_inputs}")
        
        # Save as preset if name provided
        if self.preset_name:
            self.cog.preset_manager.save_preset(
                interaction.user.id,
                self.preset_name,
                all_inputs,
                self.media_type
            )
        
        # Generate the 3x3 grid
        try:
            image_bytes = await self.cog.generate_3x3(all_inputs, self.media_type, interaction.user)
            
            if image_bytes:
                file = discord.File(fp=image_bytes, filename=f"3x3_{self.media_type}.png")
                
                embed = discord.Embed(
                    title=f"🎨 {interaction.user.display_name}'s 3x3 {self.media_type.title()} Grid",
                    description=f"Your favorite {self.media_type}{'s' if self.media_type == 'character' else ''}!",
                    color=discord.Color.purple()
                )
                embed.set_image(url=f"attachment://3x3_{self.media_type}.png")
                embed.set_footer(text="Generated from AniList URLs" + (" character images" if self.media_type == "character" else " covers" if self.media_type != "games" else " IGDB game covers"))
                
                await interaction.followup.send(embed=embed, file=file)
                
                logger.info(f"Successfully generated 3x3 for {interaction.user.name}")
            else:
                await interaction.followup.send(
                    "❌ Failed to generate 3x3 grid. Please check your inputs and try again.",
                    ephemeral=True
                )
        except Exception as e:
            logger.error(f"Error generating 3x3: {e}", exc_info=True)
            await interaction.followup.send(
                "❌ An error occurred while generating your 3x3. Please try again.",
                ephemeral=True
            )


class ContinueView(discord.ui.View):
    """View with a button to show the second modal"""
    
    def __init__(self, modal: discord.ui.Modal):
        super().__init__(timeout=300)
        self.modal = modal
    
    @discord.ui.button(label="Continue →", style=discord.ButtonStyle.primary)
    async def continue_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(self.modal)


class ThreeByThree(commands.Cog):
    """Generate 3x3 image grids of anime/manga covers with advanced features"""
    
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.cover_cache = CoverCache()
        self.preset_manager = PresetManager()
        logger.info("Enhanced 3x3 Generator cog initialized with caching and presets")
        
        if not PIL_AVAILABLE:
            logger.warning("PIL/Pillow not available - 3x3 generation will not work!")
    
    async def fetch_media_by_id(self, session: aiohttp.ClientSession, media_id: int, media_type: str) -> Optional[Dict]:
        """
        Fetch media information and cover image from AniList using ID (with caching)
        
        Args:
            session: aiohttp session
            media_id: AniList media ID
            media_type: 'anime', 'manga', or 'character'
            
        Returns:
            Dict with 'title', 'cover_url', 'cover_bytes' or None
        """
        # Check cache first
        cached_data = self.cover_cache.get(media_id, media_type)
        if cached_data:
            return cached_data
        
        if media_type == "character":
            query = """
            query ($id: Int) {
                Character(id: $id) {
                    id
                    name {
                        full
                        native
                    }
                    image {
                        large
                        medium
                    }
                }
            }
            """
            variables = {"id": media_id}
        else:
            query = """
            query ($id: Int, $type: MediaType) {
                Media(id: $id, type: $type) {
                    id
                    title {
                        romaji
                        english
                    }
                    coverImage {
                        extraLarge
                        large
                    }
                }
            }
            """
            variables = {"id": media_id, "type": media_type.upper()}
        
        try:
            async with session.post(
                API_URL,
                json={"query": query, "variables": variables},
                timeout=aiohttp.ClientTimeout(total=30)
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    
                    if media_type == "character":
                        character = data.get("data", {}).get("Character")
                        if character:
                            image_url = character["image"].get("large") or character["image"].get("medium")
                            display_name = character["name"].get("full") or f"Character {media_id}"
                            
                            if image_url:
                                async with session.get(image_url, timeout=aiohttp.ClientTimeout(total=30)) as img_response:
                                    if img_response.status == 200:
                                        cover_bytes = await img_response.read()
                                        
                                        result = {
                                            "title": display_name,
                                            "cover_url": image_url,
                                            "cover_bytes": cover_bytes
                                        }
                                        
                                        self.cover_cache.set(media_id, media_type, result)
                                        return result
                    else:
                        media = data.get("data", {}).get("Media")
                        if media:
                            cover_url = media["coverImage"].get("extraLarge") or media["coverImage"].get("large")
                            title_obj = media["title"]
                            display_title = title_obj.get("english") or title_obj.get("romaji") or f"{media_type.title()} {media_id}"
                            
                            if cover_url:
                                async with session.get(cover_url, timeout=aiohttp.ClientTimeout(total=30)) as img_response:
                                    if img_response.status == 200:
                                        cover_bytes = await img_response.read()
                                        
                                        result = {
                                            "title": display_title,
                                            "cover_url": cover_url,
                                            "cover_bytes": cover_bytes
                                        }
                                        
                                        self.cover_cache.set(media_id, media_type, result)
                                        return result
                
                logger.warning(f"Failed to fetch {media_type} {media_id}: HTTP {response.status}")
                return None
                
        except asyncio.TimeoutError:
            logger.error(f"Timeout fetching {media_type} {media_id}")
            return None
        except Exception as e:
            logger.error(f"Error fetching {media_type} {media_id}: {e}")
            return None
    
    async def fetch_game_cover(self, session: aiohttp.ClientSession, slug: str) -> Optional[Dict]:
        """
        Fetch game cover from IGDB using game slug
        
        Args:
            session: aiohttp session
            slug: IGDB game slug
            
        Returns:
            Dict with 'title', 'cover_url', 'cover_bytes' or None
        """
        if not get_game_by_slug or not get_cover_image_url or not get_access_token:
            logger.error("IGDB helper not available")
            return None
        
        # Check cache first (use slug as key for games)
        cached_data = self.cover_cache.get(slug, "games")
        if cached_data:
            return cached_data
        
        try:
            # Get IGDB access token
            access_token = await get_access_token(session)
            if not access_token:
                logger.error("Failed to get IGDB access token")
                return None
            
            # Get game details from IGDB
            game_data = await get_game_by_slug(session, access_token, slug)
            if not game_data:
                logger.warning(f"No game found for slug '{slug}'")
                return None
            
            game_title = game_data.get("name", f"Game {slug}")
            cover_data = game_data.get("cover")
            
            if not cover_data:
                logger.warning(f"No cover image found for game '{game_title}'")
                return None
            
            # Get full cover image URL
            cover_url = get_cover_image_url(cover_data)
            if not cover_url:
                logger.warning(f"Failed to construct cover URL for '{game_title}'")
                return None
            
            # Download cover image
            async with session.get(cover_url, timeout=aiohttp.ClientTimeout(total=30)) as img_response:
                if img_response.status == 200:
                    cover_bytes = await img_response.read()
                    
                    result = {
                        "title": game_title,
                        "cover_url": cover_url,
                        "cover_bytes": cover_bytes
                    }
                    
                    # Cache the result (use slug as key for games)
                    self.cover_cache.set(slug, "games", result)
                    
                    logger.info(f"Fetched game cover for '{game_title}' (Slug: {slug})")
                    return result
                else:
                    logger.warning(f"Failed to download cover for '{game_title}': HTTP {img_response.status}")
                    return None
                        
        except asyncio.TimeoutError:
            logger.error(f"Timeout fetching game cover for slug {slug}")
            return None
        except Exception as e:
            logger.error(f"Error fetching game cover for slug {slug}: {e}")
            return None
    
    async def fetch_template_titles(self, template_key: str) -> List[str]:
        """Fetch titles for a template using AniList API"""
        template = TEMPLATES.get(template_key)
        if not template:
            return []
        
        query = """
        query ($genre: String, $startYear: Int, $endYear: Int, $type: MediaType) {
            Page(page: 1, perPage: 9) {
                media(
                    genre: $genre,
                    startDate_greater: $startYear,
                    startDate_lesser: $endYear,
                    type: $type,
                    sort: POPULARITY_DESC
                ) {
                    title {
                        romaji
                        english
                    }
                }
            }
        }
        """
        
        variables = {
            "type": template["media_type"].upper(),
            "genre": template.get("genre"),
        }
        
        if "decade" in template:
            variables["startYear"] = template["decade"] * 10000 + 101  # Jan 1, decade
            variables["endYear"] = (template["decade"] + 10) * 10000 + 1231  # Dec 31, decade+9
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    API_URL,
                    json={"query": query, "variables": variables},
                    timeout=aiohttp.ClientTimeout(total=30)
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        media_list = data.get("data", {}).get("Page", {}).get("media", [])
                        
                        titles = []
                        for media in media_list[:9]:
                            title = media["title"].get("english") or media["title"].get("romaji")
                            if title:
                                titles.append(title)
                        
                        return titles
        except Exception as e:
            logger.error(f"Error fetching template titles: {e}")
        
        return []
    
    async def generate_3x3(self, urls: List[str], media_type: str, user: discord.User) -> Optional[io.BytesIO]:
        """
        Generate a 3x3 grid image from 9 AniList URLs or IGDB game URLs
        
        Args:
            urls: List of 9 AniList URLs (for anime/manga/character) or IGDB game URLs (for games)
            media_type: 'anime', 'manga', 'character', or 'games'
            user: Discord user who requested the grid
            
        Returns:
            BytesIO containing PNG image or None
        """
        if not PIL_AVAILABLE:
            logger.error("PIL not available for 3x3 generation")
            return None
        
        if len(urls) != 9:
            logger.error(f"Expected 9 URLs/names, got {len(urls)}")
            return None
        
        # Handle different media types
        if media_type == "games":
            # For games, parse URLs to get slugs
            slugs = []
            for url in urls:
                parsed = parse_igdb_url(url)
                if not parsed:
                    logger.error(f"Invalid IGDB URL: {url}")
                    return None
                slugs.append(parsed)
        else:
            # For AniList types, parse URLs to get IDs
            media_ids = []
            for url in urls:
                parsed = parse_anilist_url(url)
                if not parsed or parsed[0] != media_type:
                    logger.error(f"Invalid URL or type mismatch: {url}")
                    return None
                media_ids.append(parsed[1])
        
        # Fetch all covers (with caching)
        async with aiohttp.ClientSession() as session:
            media_data = []
            
            if media_type == "games":
                # Fetch game covers by slug
                for slug in slugs:
                    data = await self.fetch_game_cover(session, slug)
                    media_data.append(data)
            else:
                # Fetch AniList covers
                for media_id in media_ids:
                    data = await self.fetch_media_by_id(session, media_id, media_type)
                    media_data.append(data)
        
        # Check if we got at least some covers
        valid_covers = [m for m in media_data if m is not None]
        if len(valid_covers) < 5:
            logger.warning(f"Only found {len(valid_covers)} valid covers out of 9")
            return None
        
        # Generate image
        try:
            # Image settings - using 2:3 aspect ratio (manga/anime cover proportions)
            cover_width = 200   # Width of each cover
            cover_height = 300  # Height of each cover (2:3 ratio)
            grid_size = 3
            padding = 10
            
            # Calculate total image size
            total_width = (cover_width * grid_size) + (padding * (grid_size + 1))
            total_height = (cover_height * grid_size) + (padding * (grid_size + 1))
            
            # Create base image with portrait-friendly dimensions
            image = Image.new("RGB", (total_width, total_height), (20, 20, 20))
            
            # Place covers in grid
            for idx, data in enumerate(media_data):
                row = idx // grid_size
                col = idx % grid_size
                
                x = padding + (col * (cover_width + padding))
                y = padding + (row * (cover_height + padding))
                
                if data and data.get("cover_bytes"):
                    try:
                        # Load and resize cover
                        cover_img = Image.open(io.BytesIO(data["cover_bytes"]))
                        cover_img = cover_img.convert("RGB")
                        cover_img = cover_img.resize((cover_width, cover_height), Image.Resampling.LANCZOS)
                        
                        # Paste into grid
                        image.paste(cover_img, (x, y))
                    except Exception as e:
                        logger.error(f"Error processing cover {idx}: {e}")
                        # Draw placeholder
                        draw = ImageDraw.Draw(image)
                        draw.rectangle([x, y, x + cover_width, y + cover_height], fill=(60, 60, 60))
                        
                        # Draw "Not Found" text
                        try:
                            font = ImageFont.truetype("arial.ttf", 20)
                        except:
                            font = ImageFont.load_default()
                        
                        text = "Not Found"
                        bbox = draw.textbbox((0, 0), text, font=font)
                        text_width = bbox[2] - bbox[0]
                        text_height = bbox[3] - bbox[1]
                        text_x = x + (cover_width - text_width) // 2
                        text_y = y + (cover_height - text_height) // 2
                        draw.text((text_x, text_y), text, fill=(150, 150, 150), font=font)
                else:
                    # Draw placeholder for missing cover
                    draw = ImageDraw.Draw(image)
                    draw.rectangle([x, y, x + cover_width, y + cover_height], fill=(60, 60, 60))
                    
                    # Draw URL text if available
                    url_text = urls[idx][:30] if idx < len(urls) else "Unknown"
                    try:
                        font = ImageFont.truetype("arial.ttf", 16)
                    except:
                        font = ImageFont.load_default()
                    
                    # Multi-line text for long URLs
                    words = url_text.split('/')
                    lines = []
                    current_line = []
                    
                    for word in words:
                        test_line = '/'.join(current_line + [word])
                        bbox = draw.textbbox((0, 0), test_line, font=font)
                        if bbox[2] - bbox[0] < cover_width - 20:
                            current_line.append(word)
                        else:
                            if current_line:
                                lines.append('/'.join(current_line))
                            current_line = [word]
                    
                    if current_line:
                        lines.append('/'.join(current_line))
                    
                    # Draw lines
                    text_y_start = y + (cover_height // 2) - (len(lines) * 10)
                    for i, line in enumerate(lines[:3]):  # Max 3 lines
                        bbox = draw.textbbox((0, 0), line, font=font)
                        text_width = bbox[2] - bbox[0]
                        text_x = x + (cover_width - text_width) // 2
                        text_y = text_y_start + (i * 22)
                        draw.text((text_x, text_y), line, fill=(180, 180, 180), font=font)
            
            # Save to BytesIO
            output = io.BytesIO()
            image.save(output, format="PNG", optimize=True)
            output.seek(0)
            
            logger.info(f"Successfully generated 3x3 grid for {user.name}")
            return output
            
        except Exception as e:
            logger.error(f"Error generating 3x3 image: {e}", exc_info=True)
            return None
    
    @app_commands.command(name="3x3", description="🎨 Create a 3x3 grid of your favorite anime, manga, or characters")
    @app_commands.describe(media_type="Choose anime, manga, or character")
    @app_commands.choices(media_type=[
        app_commands.Choice(name="Anime", value="anime"),
        app_commands.Choice(name="Manga", value="manga"),
        app_commands.Choice(name="Character", value="character"),
        app_commands.Choice(name="Games", value="games")
    ])
    async def three_by_three(self, interaction: discord.Interaction, media_type: app_commands.Choice[str]):
        """Create a 3x3 grid of anime/manga covers or character images"""
        
        if not PIL_AVAILABLE:
            await interaction.response.send_message(
                "❌ Image generation is not available. Please contact the bot administrator.",
                ephemeral=True
            )
            return
        
        logger.info(f"{interaction.user.name} started 3x3 creation for {media_type.value}")
        
        # Show modal to collect titles
        modal = ThreeByThreeModal(media_type.value, self)
        await interaction.response.send_modal(modal)
    
    @app_commands.command(name="3x3-preset", description="💾 Create a 3x3 from a saved preset or save current as preset")
    @app_commands.describe(
        action="Choose to load or save a preset",
        preset_name="Name of the preset"
    )
    @app_commands.choices(action=[
        app_commands.Choice(name="Load Preset", value="load"),
        app_commands.Choice(name="Save New Preset", value="save"),
        app_commands.Choice(name="List My Presets", value="list"),
        app_commands.Choice(name="Delete Preset", value="delete")
    ])
    async def three_by_three_preset(self, interaction: discord.Interaction, 
                                    action: app_commands.Choice[str],
                                    preset_name: Optional[str] = None):
        """Manage 3x3 presets"""
        
        if action.value == "list":
            presets = self.preset_manager.list_presets(interaction.user.id)
            
            if not presets:
                await interaction.response.send_message(
                    "📭 You don't have any saved presets yet.\n"
                    "Use `/3x3-preset save <name>` to save your next 3x3!",
                    ephemeral=True
                )
                return
            
            embed = discord.Embed(
                title="💾 Your 3x3 Presets",
                description="\n".join([f"• `{p}`" for p in presets]),
                color=discord.Color.blue()
            )
            embed.set_footer(text="Use /3x3-preset load <name> to load a preset")
            
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        
        if not preset_name:
            await interaction.response.send_message(
                "❌ Please provide a preset name!",
                ephemeral=True
            )
            return
        
        if action.value == "load":
            preset = self.preset_manager.get_preset(interaction.user.id, preset_name)
            
            if not preset:
                await interaction.response.send_message(
                    f"❌ Preset '{preset_name}' not found!\n"
                    f"Use `/3x3-preset list` to see your presets.",
                    ephemeral=True
                )
                return
            
            # Generate 3x3 from preset
            await interaction.response.defer(ephemeral=False)
            
            image_bytes = await self.generate_3x3(
                preset["urls"],
                preset["media_type"],
                interaction.user
            )
            
            if image_bytes:
                file = discord.File(fp=image_bytes, filename=f"3x3_{preset['media_type']}.png")
                
                embed = discord.Embed(
                    title=f"💾 {interaction.user.display_name}'s Preset: {preset_name}",
                    description=f"Media Type: {preset['media_type'].title()}",
                    color=discord.Color.green()
                )
                embed.set_image(url=f"attachment://3x3_{preset['media_type']}.png")
                embed.set_footer(text=f"Loaded from preset • Created {preset['created_at'][:10]}")
                
                await interaction.followup.send(embed=embed, file=file)
            else:
                await interaction.followup.send(
                    "❌ Failed to generate 3x3 from preset.",
                    ephemeral=True
                )
        
        elif action.value == "save":
            # Show modal to collect titles for saving
            await interaction.response.send_message(
                f"💾 Creating preset '{preset_name}'...\n"
                f"Please fill out the following forms to save your preset.",
                ephemeral=True
            )
            
            # Ask for media type first
            await interaction.followup.send(
                "What media type for this preset? (Use `/3x3 anime` or `/3x3 manga` and it will be saved)",
                ephemeral=True
            )
        
        elif action.value == "delete":
            success = self.preset_manager.delete_preset(interaction.user.id, preset_name)
            
            if success:
                await interaction.response.send_message(
                    f"✅ Preset '{preset_name}' deleted successfully!",
                    ephemeral=True
                )
            else:
                await interaction.response.send_message(
                    f"❌ Preset '{preset_name}' not found!",
                    ephemeral=True
                )
    
    @app_commands.command(name="3x3-cache", description="🗑️ Clear cover cache (Admin only)")
    async def three_by_three_cache(self, interaction: discord.Interaction):
        """Clear the cover cache"""
        
        # Check if user is admin
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message(
                "❌ This command requires Administrator permissions.",
                ephemeral=True
            )
            return
        
        await interaction.response.defer(ephemeral=True)
        
        # Clean up old cache
        self.cover_cache.cleanup_old_cache()
        
        # Get cache stats
        cache_size = len(self.cover_cache.index)
        
        embed = discord.Embed(
            title="🗑️ Cache Management",
            description=f"Cache cleaned successfully!\n\n"
                       f"**Current cache size:** {cache_size} covers",
            color=discord.Color.green()
        )
        
        await interaction.followup.send(embed=embed, ephemeral=True)
    
    async def cog_load(self):
        """Called when the cog is loaded"""
        logger.info("Enhanced 3x3 Generator cog loaded successfully")
        # Clean up old cache on startup
        self.cover_cache.cleanup_old_cache()
    
    async def cog_unload(self):
        """Called when the cog is unloaded"""
        logger.info("Enhanced 3x3 Generator cog unloaded")


async def setup(bot: commands.Bot):
    """Setup function for the cog"""
    await bot.add_cog(ThreeByThree(bot))
