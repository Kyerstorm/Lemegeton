import discord
from discord.ext import commands
from discord import app_commands
import aiosqlite
import aiohttp
import asyncio
import time
import logging
from pathlib import Path
from typing import Dict, List, Tuple, Optional, Union
import json
from datetime import datetime, timedelta

from helpers.cache_helper import (
    load_timestamped_cache,
    save_timestamped_cache,
    get_cached_value,
    set_cached_value,
)

from database import (
    get_all_users, upsert_user_stats,
    # Guild-aware functions
    get_guild_leaderboard_data, get_all_users_guild_aware,
    upsert_user_stats_guild_aware
)
from helpers.media_helper import fetch_user_stats
from config import DB_PATH

# ------------------------------------------------------
# Logging Setup - Clears on each bot run
# ------------------------------------------------------
LOG_DIR = Path("logs")
LOG_DIR.mkdir(exist_ok=True)
LOG_FILE = LOG_DIR / "leaderboard.log"

# Clear the log file on startup
if LOG_FILE.exists():
    try:
        # Try to truncate the file in-place instead of deleting it. Deleting can fail on Windows
        # if another process has the file open. Truncating is safer and avoids raising.
        with open(LOG_FILE, 'w', encoding='utf-8'):
            pass
    except Exception as e:
        # If we cannot truncate (file locked), continue without failing the cog import.
        # Use a simple print because logger isn't configured yet.
        print(f"Warning: could not clear leaderboard log {LOG_FILE}: {e}")
 
# Create logger
logger = logging.getLogger("Leaderboard")
logger.setLevel(logging.INFO)

# Remove existing handlers to avoid duplicates
for handler in logger.handlers[:]:
    logger.removeHandler(handler)

# Try to create a file handler; fall back to stream handler if the file is locked.
try:
    file_handler = logging.FileHandler(LOG_FILE, encoding="utf-8")
    file_handler.setLevel(logging.INFO)

    # Create formatter
    formatter = logging.Formatter(
        "[%(asctime)s] [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
except Exception:
    # Fall back to a console stream handler to avoid import-time failure
    stream_handler = logging.StreamHandler()
    stream_handler.setLevel(logging.INFO)
    stream_handler.setFormatter(logging.Formatter("[%(asctime)s] [%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S"))
    logger.addHandler(stream_handler)

logger.info("Leaderboard cog logging initialized - log file cleared (or stream fallback used)")

# ------------------------------------------------------
# Origin-Based Weighting System
# ------------------------------------------------------
# Media origin multipliers for enhanced scoring diversity
ORIGIN_MULTIPLIERS = {
    # Manga (Japanese comics) - baseline
    "manga": {
        "chapter_weight": 1.0,
        "variety_weight": 1.0,
        "efficiency_bonus": 1.0
    },
    # Manhwa (Korean webtoons) - slightly higher due to longer chapters
    "manhwa": {
        "chapter_weight": 1.1,
        "variety_weight": 1.05,
        "efficiency_bonus": 1.1
    },
    # Manhua (Chinese comics) - moderate weighting
    "manhua": {
        "chapter_weight": 0.95,
        "variety_weight": 0.98,
        "efficiency_bonus": 0.95
    },
    # Anime origins
    # Japanese anime - standard weighting
    "japanese_anime": {
        "episode_weight": 1.0,
        "variety_weight": 1.0,
        "efficiency_bonus": 1.0
    },
    # Korean animation/ONA - higher weight due to rarity
    "korean_anime": {
        "episode_weight": 1.15,
        "variety_weight": 1.1,
        "efficiency_bonus": 1.15
    },
    # Chinese donghua - moderate weight
    "chinese_anime": {
        "episode_weight": 1.05,
        "variety_weight": 1.02,
        "efficiency_bonus": 1.05
    }
}

# Regional consumption patterns (estimated distributions)
REGIONAL_PATTERNS = {
    # Estimated percentage breakdown for typical users
    "manga_distribution": {"manga": 0.75, "manhwa": 0.20, "manhua": 0.05},
    "anime_distribution": {"japanese_anime": 0.85, "korean_anime": 0.05, "chinese_anime": 0.10}
}

# Anime format multipliers for enhanced scoring diversity
ANIME_FORMAT_MULTIPLIERS = {
    # TV Series - standard baseline
    "TV": {
        "episode_weight": 1.0,
        "variety_weight": 1.0,
        "efficiency_bonus": 1.0
    },
    # ONA (Original Net Animation) - slightly higher due to modern format
    "ONA": {
        "episode_weight": 1.05,
        "variety_weight": 1.03,
        "efficiency_bonus": 1.05
    },
    # OVA (Original Video Animation) - higher weight due to quality/rarity
    "OVA": {
        "episode_weight": 1.15,
        "variety_weight": 1.10,
        "efficiency_bonus": 1.15
    },
    # TV Short - lower weight due to shorter episodes
    "TV_SHORT": {
        "episode_weight": 0.75,
        "variety_weight": 0.90,
        "efficiency_bonus": 0.85
    },
    # Movies - high weight due to cinematic quality and length
    "MOVIE": {
        "episode_weight": 2.0,  # Movies are typically 1.5-3 hours = multiple episodes worth
        "variety_weight": 1.25,
        "efficiency_bonus": 1.30
    },
    # Special - moderate weight for special episodes
    "SPECIAL": {
        "episode_weight": 1.08,
        "variety_weight": 1.05,
        "efficiency_bonus": 1.08
    }
}

# Anime format distribution patterns (estimated based on consumption behavior)
ANIME_FORMAT_PATTERNS = {
    # Estimated percentage breakdown for typical users
    "format_distribution": {
        "TV": 0.65,         # Most anime consumption is TV series
        "ONA": 0.12,        # Growing segment (web anime)
        "OVA": 0.08,        # Niche but valuable content
        "TV_SHORT": 0.06,   # Short-form content
        "MOVIE": 0.07,      # Anime movies
        "SPECIAL": 0.02     # Special episodes/OADs
    }
}

# Manga format multipliers for enhanced scoring diversity
MANGA_FORMAT_MULTIPLIERS = {
    # Regular Manga - standard baseline
    "MANGA": {
        "chapter_weight": 1.0,
        "variety_weight": 1.0,
        "efficiency_bonus": 1.0
    },
    # Light Novel - higher weight due to text density and reading time
    "LIGHT_NOVEL": {
        "chapter_weight": 1.35,  # LN chapters are denser, take longer to read
        "variety_weight": 1.20,
        "efficiency_bonus": 1.25
    },
    # One Shot - moderate weight, self-contained stories
    "ONE_SHOT": {
        "chapter_weight": 1.15,  # Complete stories in one chapter
        "variety_weight": 1.10,
        "efficiency_bonus": 0.90   # Lower efficiency since always 1 chapter
    },
    # Doujinshi - slightly lower weight due to fan-made nature
    "DOUJINSHI": {
        "chapter_weight": 0.85,
        "variety_weight": 0.95,
        "efficiency_bonus": 0.80
    },
    # Novel - highest weight for full text novels
    "NOVEL": {
        "chapter_weight": 1.50,  # Full novels are very dense content
        "variety_weight": 1.30,
        "efficiency_bonus": 1.40
    }
}

# Manga format distribution patterns (estimated based on consumption behavior)
MANGA_FORMAT_PATTERNS = {
    # Estimated percentage breakdown for typical users
    "format_distribution": {
        "MANGA": 0.75,      # Most manga consumption is regular manga
        "LIGHT_NOVEL": 0.15, # Growing segment, especially for anime watchers
        "ONE_SHOT": 0.05,   # Occasional one-shots
        "DOUJINSHI": 0.03,  # Fan works
        "NOVEL": 0.02       # Full text novels (rare but valuable)
    }
}

# ------------------------------------------------------
# Constants
# ------------------------------------------------------
CACHE_TTL = 86400  # 1 day in seconds
PAGE_SIZE = 5  # Users per page
TIMEOUT_DURATION = 300  # 5 minutes for view timeout

# Leaderboard cache settings (30 days)
LEADERBOARD_CACHE_FILE = Path("data") / "leaderboard_cache.json"
LEADERBOARD_CACHE_DURATION_DAYS = 30
LEADERBOARD_CACHE_DURATION_SECONDS = LEADERBOARD_CACHE_DURATION_DAYS * 24 * 60 * 60

# ------------------------------------------------------
# Leaderboard Cache Management Functions
# ------------------------------------------------------
def load_leaderboard_cache() -> dict:
    """Load leaderboard cache from disk."""
    if not LEADERBOARD_CACHE_FILE.exists():
        return {}
    
    try:
        with open(LEADERBOARD_CACHE_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        logger.warning(f"Failed to load leaderboard cache: {e}")
        return {}

def save_leaderboard_cache(cache: dict):
    """Save leaderboard cache to disk."""
    try:
        LEADERBOARD_CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(LEADERBOARD_CACHE_FILE, 'w', encoding='utf-8') as f:
            json.dump(cache, f, indent=2, ensure_ascii=False)
        logger.debug("Leaderboard cache saved")
    except Exception as e:
        logger.error(f"Failed to save leaderboard cache: {e}")

def get_leaderboard_cache_key(guild_id: int, medium: str) -> str:
    """Generate cache key for leaderboard results."""
    return f"{guild_id}_{medium}"

def get_cached_leaderboard(cache_key: str) -> Optional[List[Tuple]]:
    """Get cached leaderboard data if still valid."""
    cache = load_leaderboard_cache()
    entry = cache.get(cache_key)
    
    if not entry:
        return None
    
    cached_time = datetime.fromisoformat(entry["timestamp"])
    if datetime.utcnow() - cached_time > timedelta(seconds=LEADERBOARD_CACHE_DURATION_SECONDS):
        logger.debug(f"Leaderboard cache expired for key {cache_key}")
        return None
    
    logger.info(f"Using cached leaderboard data for key {cache_key}")
    return entry["data"]

def set_cached_leaderboard(cache_key: str, data: List[Tuple]):
    """Cache leaderboard data with current timestamp."""
    cache = load_leaderboard_cache()
    cache[cache_key] = {
        "timestamp": datetime.utcnow().isoformat(),
        "data": data
    }
    save_leaderboard_cache(cache)

# Global cache for user fetch timestamps
_FETCH_CACHE_NAME = "leaderboard_last_fetch"

# Persistent timestamped cache: {str(discord_id): (timestamp)} stored via helpers/cache_helper
fetch_timestamps = load_timestamped_cache(_FETCH_CACHE_NAME)

# Media type configuration
MEDIA_TYPES = {
    "manga": {
        "title": "📖 Manga Golden Ratio",
        "description": "Users ranked by Average Chapters per Manga",
        "sql": "SELECT username, total_manga, total_chapters FROM user_stats",
        "unit_label": "Chapters",
        "media_label": "Manga"
    },
    "anime": {
        "title": "🎬 Anime Golden Ratio", 
        "description": "Users ranked by Average Episodes per Anime",
        "sql": "SELECT username, total_anime, total_episodes FROM user_stats",
        "unit_label": "Episodes",
        "media_label": "Anime"
    },
    "combined": {
        "title": "🌟 Ultimate Otaku Ranking",
        "description": "Users ranked by Origin-Weighted Activity Score",
        "sql": "SELECT username, total_manga, total_chapters, total_anime, total_episodes FROM user_stats",
        "unit_label": "Activity Score",
        "media_label": "Combined"
    }
    ,
    "chapters": {
        "title": "📚 Most Chapters Read",
        "description": "Users ranked by total chapters read",
        "sql": "SELECT username, total_chapters FROM user_stats",
        "unit_label": "Chapters",
        "media_label": "Chapters"
    }
    ,
    "episodes": {
        "title": "📺 Most Episodes Watched",
        "description": "Users ranked by total episodes watched",
        "sql": "SELECT username, total_episodes FROM user_stats",
        "unit_label": "Episodes",
        "media_label": "Episodes"
    }
    ,
    "manga_completed": {
        "title": "🏁 Most Manga Completed",
        "description": "Users ranked by total manga entries completed",
        "sql": "SELECT username, manga_completed FROM user_stats",
        "unit_label": "Completed",
        "media_label": "Manga"
    },
    "anime_completed": {
        "title": "🏁 Most Anime Completed",
        "description": "Users ranked by total anime entries completed",
        "sql": "SELECT username, anime_completed FROM user_stats",
        "unit_label": "Completed",
        "media_label": "Anime"
    }
}
class LeaderboardView(discord.ui.View):
    """Interactive paginated view for leaderboard display."""
    
    def __init__(self, leaderboard_data: List[Tuple], medium: str = "manga"):
        super().__init__(timeout=TIMEOUT_DURATION)
        self.leaderboard_data = leaderboard_data
        self.current_page = 0
        self.max_page = (len(leaderboard_data) - 1) // PAGE_SIZE if leaderboard_data else 0
        self.medium = medium.lower()
        self.media_config = MEDIA_TYPES.get(self.medium, MEDIA_TYPES["manga"])
        
        logger.info(f"Created leaderboard view for {medium} with {len(leaderboard_data)} users, {self.max_page + 1} pages")
        
        # Initialize button states
        self._update_button_states()

    def _update_button_states(self) -> None:
        """Update button disabled states based on current page."""
        self.prev_button.disabled = self.current_page == 0
        self.next_button.disabled = self.current_page >= self.max_page

    def _create_embed(self) -> discord.Embed:
        """Create the leaderboard embed for the current page."""
        start = self.current_page * PAGE_SIZE
        end = start + PAGE_SIZE
        page_data = self.leaderboard_data[start:end]

        embed = discord.Embed(
            title=f"🏆 {self.media_config['title']}",
            description=f"{self.media_config['description']} (Page {self.current_page + 1}/{self.max_page + 1})",
            color=discord.Color.gold()
        )

        if not page_data:
            embed.add_field(name="No Data", value="No users found for this page.", inline=False)
            return embed

        for idx, data_tuple in enumerate(page_data, start=start + 1):
            # Add ranking emoji for top 3
            rank_emoji = {1: "🥇", 2: "🥈", 3: "🥉"}.get(idx, f"{idx}.")
            
            if self.medium == "combined":
                # Combined format: (username, total_manga, total_chapters, total_anime, total_episodes, activity_score, breakdown)
                if len(data_tuple) >= 7:  # New format with breakdown
                    username, total_manga, total_chapters, total_anime, total_episodes, activity_score, breakdown = data_tuple
                    
                    embed.add_field(
                        name=f"{rank_emoji} {username}",
                        value=(
                            f"**📖 Manga:** {total_manga:,} titles, {total_chapters:,} chapters\n"
                            f"**🎬 Anime:** {total_anime:,} titles, {total_episodes:,} episodes\n"
                            f"**🌟 Activity Score:** {int(activity_score):,} points"
                        ),
                        inline=False
                    )
                else:  # Fallback for old format
                    username, total_manga, total_chapters, total_anime, total_episodes, activity_score = data_tuple
                    
                    embed.add_field(
                        name=f"{rank_emoji} {username}",
                        value=(
                            f"**📖 Manga:** {total_manga:,} titles, {total_chapters:,} chapters\n"
                            f"**🎬 Anime:** {total_anime:,} titles, {total_episodes:,} episodes\n"
                            f"**🌟 Activity Score:** {int(activity_score):,} points"
                        ),
                        inline=False
                    )
            else:
                # Standard format: (username, total_media, total_units, avg_units)
                # Special-case chapters/episodes mediums to show only unit totals
                if self.medium == "chapters":
                    # total_chapters is stored as the third element in the tuple
                    username = data_tuple[0]
                    total_chapters = int(data_tuple[2]) if len(data_tuple) > 2 else 0

                    embed.add_field(
                        name=f"{rank_emoji} {username}",
                        value=(
                            f"**Total Chapters Read:** {total_chapters:,}"
                        ),
                        inline=False
                    )
                elif self.medium == "episodes":
                    username = data_tuple[0]
                    total_episodes = int(data_tuple[2]) if len(data_tuple) > 2 else 0

                    embed.add_field(
                        name=f"{rank_emoji} {username}",
                        value=(
                            f"**Total Episodes Watched:** {total_episodes:,}"
                        ),
                        inline=False
                    )
                elif self.medium in ("manga_completed", "anime_completed"):
                    # For completed leaderboards, only show the total completed count
                    username = data_tuple[0]
                    total_completed = int(data_tuple[2]) if len(data_tuple) > 2 else 0

                    embed.add_field(
                        name=f"{rank_emoji} {username}",
                        value=(
                            f"**Total Completed:** {total_completed:,}"
                        ),
                        inline=False
                    )
                else:
                    username, total_media, total_units, avg_units = data_tuple
                    
                    embed.add_field(
                        name=f"{rank_emoji} {username}",
                        value=(
                            f"**Total {self.media_config['media_label']}:** {total_media:,}\n"
                            f"**Total {self.media_config['unit_label']}:** {total_units:,}\n"
                            f"**Average {self.media_config['unit_label']} per {self.media_config['media_label']}:** {avg_units:.2f}"
                        ),
                        inline=False
                    )

        embed.set_footer(
            text="🔄 Leaderboard based on cached AniList stats (updates once per day)",
            icon_url="https://anilist.co/img/icons/android-chrome-512x512.png"
        )
        return embed

    async def update_embed(self, message: discord.Message) -> None:
        """Update the message with the current page embed."""
        try:
            embed = self._create_embed()
            self._update_button_states()
            await message.edit(embed=embed, view=self)
            logger.info(f"Updated leaderboard to page {self.current_page + 1}/{self.max_page + 1}")
        except Exception as e:
            logger.error(f"Error updating leaderboard embed: {e}", exc_info=True)

    @discord.ui.button(label="◀️ Previous", style=discord.ButtonStyle.blurple, emoji="◀️")
    async def prev_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Handle previous page button click."""
        try:
            if self.current_page > 0:
                self.current_page -= 1
                logger.info(f"User {interaction.user.id} navigated to page {self.current_page + 1}")
                await self.update_embed(interaction.message)
            await interaction.response.defer()
        except Exception as e:
            logger.error(f"Error handling previous button: {e}", exc_info=True)
            await interaction.response.defer()

    @discord.ui.button(label="Next ▶️", style=discord.ButtonStyle.blurple, emoji="▶️")
    async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Handle next page button click."""
        try:
            if self.current_page < self.max_page:
                self.current_page += 1
                logger.info(f"User {interaction.user.id} navigated to page {self.current_page + 1}")
                await self.update_embed(interaction.message)
            await interaction.response.defer()
        except Exception as e:
            logger.error(f"Error handling next button: {e}", exc_info=True)
            await interaction.response.defer()

    async def on_timeout(self) -> None:
        """Remove buttons when view times out."""
        self.clear_items()
        logger.info("Leaderboard view timed out, buttons removed")


class Leaderboard(commands.Cog):
    """Cog for displaying user leaderboards based on manga/anime statistics."""
    
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        logger.info("Leaderboard cog initialized")

    def _estimate_origin_distribution(self, total_manga: int, total_anime: int, 
                                    total_chapters: int, total_episodes: int) -> Dict:
        """
        Estimate the distribution of media origins based on consumption patterns.
        Uses statistical models and typical user behavior patterns.
        Creates variations based on multiple consumption indicators.
        """
        # Base distribution patterns
        manga_dist = REGIONAL_PATTERNS["manga_distribution"].copy()
        anime_dist = REGIONAL_PATTERNS["anime_distribution"].copy()
        
        # Calculate consumption ratios for more nuanced patterns
        avg_chapters_per_manga = total_chapters / max(total_manga, 1)
        avg_episodes_per_anime = total_episodes / max(total_anime, 1)
        manga_intensity = total_manga + (total_chapters / 100)  # Composite intensity
        anime_intensity = total_anime + (total_episodes / 50)   # Composite intensity
        
        # Pattern 1: High chapter-per-manga ratio suggests manhwa preference (longer series)
        if avg_chapters_per_manga > 80:  # Manhwa tend to have 100+ chapters
            manga_dist["manhwa"] = min(0.45, manga_dist["manhwa"] * 2.2)
            manga_dist["manga"] = max(0.50, 1.0 - manga_dist["manhwa"] - manga_dist["manhua"])
            manga_dist["manhua"] = 1.0 - manga_dist["manga"] - manga_dist["manhwa"]
        elif avg_chapters_per_manga > 40:  # Moderate manhwa preference
            manga_dist["manhwa"] = min(0.35, manga_dist["manhwa"] * 1.6)
            manga_dist["manga"] = max(0.60, 1.0 - manga_dist["manhwa"] - manga_dist["manhua"])
            manga_dist["manhua"] = 1.0 - manga_dist["manga"] - manga_dist["manhwa"]
        
        # Pattern 2: Very high total chapters suggests broader reading (more diverse origins)
        if total_chapters > 8000:
            manga_dist["manhua"] = min(0.08, manga_dist["manhua"] * 1.6)
            manga_dist["manhwa"] = min(0.30, manga_dist["manhwa"] * 1.3)
            manga_dist["manga"] = max(0.62, 1.0 - manga_dist["manhwa"] - manga_dist["manhua"])
        elif total_chapters > 5000:
            manga_dist["manhwa"] = min(0.25, manga_dist["manhwa"] * 1.2)
            manga_dist["manga"] = max(0.70, 1.0 - manga_dist["manhwa"] - manga_dist["manhua"])
        
        # Pattern 3: High manga count suggests variety-seeking behavior
        if total_manga > 150:
            manga_dist["manhwa"] = min(0.30, manga_dist["manhwa"] * 1.4)
            manga_dist["manhua"] = min(0.07, manga_dist["manhua"] * 1.4)
            manga_dist["manga"] = max(0.63, 1.0 - manga_dist["manhwa"] - manga_dist["manhua"])
        elif total_manga > 80:
            manga_dist["manhwa"] = min(0.25, manga_dist["manhwa"] * 1.2)
            manga_dist["manga"] = max(0.70, 1.0 - manga_dist["manhwa"] - manga_dist["manhua"])
        
        # Pattern 4: Anime consumption patterns
        if avg_episodes_per_anime > 30:  # Long series preference (often Chinese donghua)
            anime_dist["chinese_anime"] = min(0.18, anime_dist["chinese_anime"] * 1.6)
            anime_dist["japanese_anime"] = max(0.77, 1.0 - anime_dist["chinese_anime"] - anime_dist["korean_anime"])
        
        if total_anime > 300:  # Heavy anime watchers explore more origins
            anime_dist["chinese_anime"] = min(0.15, anime_dist["chinese_anime"] * 1.4)
            anime_dist["korean_anime"] = min(0.08, anime_dist["korean_anime"] * 1.3)
            anime_dist["japanese_anime"] = max(0.77, 1.0 - anime_dist["chinese_anime"] - anime_dist["korean_anime"])
        elif total_anime > 150:
            anime_dist["chinese_anime"] = min(0.12, anime_dist["chinese_anime"] * 1.2)
            anime_dist["japanese_anime"] = max(0.83, 1.0 - anime_dist["chinese_anime"] - anime_dist["korean_anime"])
        
        # Pattern 5: Consumption balance affects diversity
        manga_anime_ratio = manga_intensity / max(anime_intensity, 1)
        if manga_anime_ratio > 3:  # Heavily manga-focused users
            manga_dist["manhwa"] = min(0.35, manga_dist["manhwa"] * 1.3)
            manga_dist["manga"] = max(0.60, 1.0 - manga_dist["manhwa"] - manga_dist["manhua"])
        elif manga_anime_ratio < 0.5:  # Anime-focused users
            anime_dist["chinese_anime"] = min(0.15, anime_dist["chinese_anime"] * 1.3)
            anime_dist["japanese_anime"] = max(0.80, 1.0 - anime_dist["chinese_anime"] - anime_dist["korean_anime"])
        
        return {
            "manga_distribution": manga_dist,
            "anime_distribution": anime_dist,
            "estimated_manga_counts": {
                "manga": int(total_manga * manga_dist["manga"]),
                "manhwa": int(total_manga * manga_dist["manhwa"]),
                "manhua": int(total_manga * manga_dist["manhua"])
            },
            "estimated_chapter_counts": {
                "manga": int(total_chapters * manga_dist["manga"]),
                "manhwa": int(total_chapters * manga_dist["manhwa"]),
                "manhua": int(total_chapters * manga_dist["manhua"])
            },
            "estimated_anime_counts": {
                "japanese_anime": int(total_anime * anime_dist["japanese_anime"]),
                "korean_anime": int(total_anime * anime_dist["korean_anime"]),
                "chinese_anime": int(total_anime * anime_dist["chinese_anime"])
            },
            "estimated_episode_counts": {
                "japanese_anime": int(total_episodes * anime_dist["japanese_anime"]),
                "korean_anime": int(total_episodes * anime_dist["korean_anime"]),
                "chinese_anime": int(total_episodes * anime_dist["chinese_anime"])
            },
            "anime_format_distribution": self._estimate_anime_format_distribution(total_anime, total_episodes, avg_episodes_per_anime),
            "estimated_format_counts": self._get_format_counts(total_anime, avg_episodes_per_anime),
            "estimated_format_episodes": self._get_format_episodes(total_episodes, avg_episodes_per_anime),
            "manga_format_distribution": self._estimate_manga_format_distribution(total_manga, total_chapters, avg_chapters_per_manga),
            "estimated_manga_format_counts": self._get_manga_format_counts(total_manga, avg_chapters_per_manga),
            "estimated_manga_format_chapters": self._get_manga_format_chapters(total_chapters, avg_chapters_per_manga)
        }

    def _estimate_anime_format_distribution(self, total_anime: int, total_episodes: int, avg_episodes_per_anime: float) -> Dict:
        """
        Estimate anime format distribution based on consumption patterns.
        Different viewing patterns suggest different format preferences.
        """
        format_dist = ANIME_FORMAT_PATTERNS["format_distribution"].copy()
        
        # Pattern 1: High episode-per-anime ratio suggests TV series preference
        if avg_episodes_per_anime > 25:  # Long series watchers
            format_dist["TV"] = min(0.80, format_dist["TV"] * 1.2)
            format_dist["ONA"] = max(0.08, format_dist["ONA"] * 0.8)
            format_dist["MOVIE"] = max(0.05, format_dist["MOVIE"] * 0.7)
        elif avg_episodes_per_anime > 15:  # Moderate series length
            format_dist["TV"] = min(0.75, format_dist["TV"] * 1.1)
        elif avg_episodes_per_anime < 8:  # Short content preference
            format_dist["TV_SHORT"] = min(0.12, format_dist["TV_SHORT"] * 1.8)
            format_dist["OVA"] = min(0.15, format_dist["OVA"] * 1.5)
            format_dist["MOVIE"] = min(0.12, format_dist["MOVIE"] * 1.4)
            format_dist["TV"] = max(0.50, format_dist["TV"] * 0.8)
        
        # Pattern 2: Very high anime count suggests diverse format consumption
        if total_anime > 500:  # Heavy watchers explore all formats
            format_dist["ONA"] = min(0.18, format_dist["ONA"] * 1.4)
            format_dist["OVA"] = min(0.12, format_dist["OVA"] * 1.3)
            format_dist["SPECIAL"] = min(0.04, format_dist["SPECIAL"] * 1.5)
        elif total_anime > 200:
            format_dist["ONA"] = min(0.15, format_dist["ONA"] * 1.2)
            format_dist["OVA"] = min(0.10, format_dist["OVA"] * 1.1)
        
        # Pattern 3: Moderate anime with high episodes suggests movie preference
        if total_anime < 100 and total_episodes > 1500:
            format_dist["MOVIE"] = min(0.15, format_dist["MOVIE"] * 1.8)
            format_dist["TV"] = max(0.55, format_dist["TV"] * 0.9)
        
        # Normalize to ensure total = 1.0
        total = sum(format_dist.values())
        for key in format_dist:
            format_dist[key] /= total
            
        return format_dist

    def _get_format_counts(self, total_anime: int, avg_episodes_per_anime: float) -> Dict:
        """Calculate estimated anime counts by format."""
        format_dist = self._estimate_anime_format_distribution(total_anime, 0, avg_episodes_per_anime)
        return {
            "TV": int(total_anime * format_dist["TV"]),
            "ONA": int(total_anime * format_dist["ONA"]),
            "OVA": int(total_anime * format_dist["OVA"]),
            "TV_SHORT": int(total_anime * format_dist["TV_SHORT"]),
            "MOVIE": int(total_anime * format_dist["MOVIE"]),
            "SPECIAL": int(total_anime * format_dist["SPECIAL"])
        }

    def _get_format_episodes(self, total_episodes: int, avg_episodes_per_anime: float) -> Dict:
        """Calculate estimated episode counts by format."""
        format_dist = self._estimate_anime_format_distribution(0, total_episodes, avg_episodes_per_anime)
        return {
            "TV": int(total_episodes * format_dist["TV"]),
            "ONA": int(total_episodes * format_dist["ONA"]),
            "OVA": int(total_episodes * format_dist["OVA"]),
            "TV_SHORT": int(total_episodes * format_dist["TV_SHORT"]),
            "MOVIE": int(total_episodes * format_dist["MOVIE"]),
            "SPECIAL": int(total_episodes * format_dist["SPECIAL"])
        }

    def _estimate_manga_format_distribution(self, total_manga: int, total_chapters: int, avg_chapters_per_manga: float) -> Dict:
        """
        Estimate manga format distribution based on consumption patterns.
        Different reading patterns suggest different format preferences.
        """
        format_dist = MANGA_FORMAT_PATTERNS["format_distribution"].copy()
        
        # Pattern 1: Very low chapters-per-manga suggests one-shots
        if avg_chapters_per_manga < 5:  # One-shot heavy readers
            format_dist["ONE_SHOT"] = min(0.25, format_dist["ONE_SHOT"] * 4.0)
            format_dist["MANGA"] = max(0.60, format_dist["MANGA"] * 0.8)
            format_dist["LIGHT_NOVEL"] = max(0.10, format_dist["LIGHT_NOVEL"] * 0.7)
        elif avg_chapters_per_manga < 15:  # Mixed short content
            format_dist["ONE_SHOT"] = min(0.12, format_dist["ONE_SHOT"] * 2.0)
            format_dist["MANGA"] = max(0.70, format_dist["MANGA"] * 0.9)
        
        # Pattern 2: High chapters-per-manga but low total suggests light novels
        if avg_chapters_per_manga > 200 and total_manga < 100:  # LN pattern
            format_dist["LIGHT_NOVEL"] = min(0.40, format_dist["LIGHT_NOVEL"] * 2.5)
            format_dist["NOVEL"] = min(0.08, format_dist["NOVEL"] * 3.0)
            format_dist["MANGA"] = max(0.45, format_dist["MANGA"] * 0.6)
        elif avg_chapters_per_manga > 100:  # Heavy LN preference
            format_dist["LIGHT_NOVEL"] = min(0.30, format_dist["LIGHT_NOVEL"] * 1.8)
            format_dist["NOVEL"] = min(0.05, format_dist["NOVEL"] * 2.0)
            format_dist["MANGA"] = max(0.60, format_dist["MANGA"] * 0.8)
        elif avg_chapters_per_manga > 50:  # Moderate LN consumption
            format_dist["LIGHT_NOVEL"] = min(0.25, format_dist["LIGHT_NOVEL"] * 1.4)
            format_dist["MANGA"] = max(0.65, format_dist["MANGA"] * 0.9)
        
        # Pattern 3: Very high manga count suggests diverse format consumption
        if total_manga > 500:  # Heavy readers explore all formats
            format_dist["DOUJINSHI"] = min(0.08, format_dist["DOUJINSHI"] * 2.0)
            format_dist["ONE_SHOT"] = min(0.08, format_dist["ONE_SHOT"] * 1.5)
            format_dist["LIGHT_NOVEL"] = min(0.20, format_dist["LIGHT_NOVEL"] * 1.2)
        elif total_manga > 200:
            format_dist["DOUJINSHI"] = min(0.05, format_dist["DOUJINSHI"] * 1.5)
            format_dist["LIGHT_NOVEL"] = min(0.18, format_dist["LIGHT_NOVEL"] * 1.1)
        
        # Pattern 4: Very high total chapters suggests novel consumption
        if total_chapters > 10000:
            format_dist["NOVEL"] = min(0.05, format_dist["NOVEL"] * 2.5)
            format_dist["LIGHT_NOVEL"] = min(0.20, format_dist["LIGHT_NOVEL"] * 1.1)
        
        # Normalize to ensure total = 1.0
        total = sum(format_dist.values())
        for key in format_dist:
            format_dist[key] /= total
            
        return format_dist

    def _get_manga_format_counts(self, total_manga: int, avg_chapters_per_manga: float) -> Dict:
        """Calculate estimated manga counts by format."""
        format_dist = self._estimate_manga_format_distribution(total_manga, 0, avg_chapters_per_manga)
        return {
            "MANGA": int(total_manga * format_dist["MANGA"]),
            "LIGHT_NOVEL": int(total_manga * format_dist["LIGHT_NOVEL"]),
            "ONE_SHOT": int(total_manga * format_dist["ONE_SHOT"]),
            "DOUJINSHI": int(total_manga * format_dist["DOUJINSHI"]),
            "NOVEL": int(total_manga * format_dist["NOVEL"])
        }

    def _get_manga_format_chapters(self, total_chapters: int, avg_chapters_per_manga: float) -> Dict:
        """Calculate estimated chapter counts by format."""
        format_dist = self._estimate_manga_format_distribution(0, total_chapters, avg_chapters_per_manga)
        return {
            "MANGA": int(total_chapters * format_dist["MANGA"]),
            "LIGHT_NOVEL": int(total_chapters * format_dist["LIGHT_NOVEL"]),
            "ONE_SHOT": int(total_chapters * format_dist["ONE_SHOT"]),
            "DOUJINSHI": int(total_chapters * format_dist["DOUJINSHI"]),
            "NOVEL": int(total_chapters * format_dist["NOVEL"])
        }

    def _calculate_origin_weighted_score(self, total_manga: int, total_anime: int,
                                       total_chapters: int, total_episodes: int) -> Tuple[float, Dict]:
        """
        Calculate activity score with origin-based weighting.
        Returns the final score and a breakdown dictionary.
        """
        # Get origin distribution estimates
        distribution = self._estimate_origin_distribution(total_manga, total_anime, total_chapters, total_episodes)
        
        # Calculate weighted manga scoring with both origin and format multipliers
        manga_score = 0
        manga_variety_score = 0
        manga_efficiency_score = 0
        
        # Get format distribution for enhanced weighting
        manga_format_counts = distribution["estimated_manga_format_counts"]
        manga_format_chapters = distribution["estimated_manga_format_chapters"]
        
        # Apply both origin and format weighting for manga
        for origin, chapter_count in distribution["estimated_chapter_counts"].items():
            if chapter_count > 0:
                origin_multipliers = ORIGIN_MULTIPLIERS[origin]
                title_count = distribution["estimated_manga_counts"][origin]
                
                # Distribute chapters across formats for this origin
                origin_format_chapters = {
                    format_type: int(chapter_count * (manga_format_chapters[format_type] / max(sum(manga_format_chapters.values()), 1)))
                    for format_type in manga_format_chapters.keys()
                }
                
                origin_format_counts = {
                    format_type: int(title_count * (manga_format_counts[format_type] / max(sum(manga_format_counts.values()), 1)))
                    for format_type in manga_format_counts.keys()
                }
                
                # Calculate scores with combined origin and format multipliers
                for format_type, format_chapter_count in origin_format_chapters.items():
                    if format_chapter_count > 0:
                        format_multipliers = MANGA_FORMAT_MULTIPLIERS[format_type]
                        
                        # Base chapter score with combined multipliers
                        combined_chapter_weight = origin_multipliers["chapter_weight"] * format_multipliers["chapter_weight"]
                        manga_score += format_chapter_count * 2.5 * combined_chapter_weight
                        
                        # Variety bonus with combined multipliers
                        format_title_count = origin_format_counts[format_type]
                        combined_variety_weight = origin_multipliers["variety_weight"] * format_multipliers["variety_weight"]
                        manga_variety_score += format_title_count * 25 * combined_variety_weight
                        
                        # Efficiency bonus with combined multipliers
                        if format_title_count > 0:
                            avg_chapters = format_chapter_count / format_title_count
                            combined_efficiency_weight = origin_multipliers["efficiency_bonus"] * format_multipliers["efficiency_bonus"]
                            efficiency = min(avg_chapters * 5, 500) * combined_efficiency_weight
                            manga_efficiency_score += efficiency
        
        # Calculate weighted anime scoring with both origin and format multipliers
        anime_score = 0
        anime_variety_score = 0
        anime_efficiency_score = 0
        
        # Get format distribution for enhanced weighting
        format_counts = distribution["estimated_format_counts"]
        format_episodes = distribution["estimated_format_episodes"]
        
        # Apply both origin and format weighting
        for origin, episode_count in distribution["estimated_episode_counts"].items():
            if episode_count > 0:
                origin_multipliers = ORIGIN_MULTIPLIERS[origin]
                title_count = distribution["estimated_anime_counts"][origin]
                
                # Distribute episodes across formats for this origin
                origin_format_episodes = {
                    format_type: int(episode_count * (format_episodes[format_type] / max(sum(format_episodes.values()), 1)))
                    for format_type in format_episodes.keys()
                }
                
                origin_format_counts = {
                    format_type: int(title_count * (format_counts[format_type] / max(sum(format_counts.values()), 1)))
                    for format_type in format_counts.keys()
                }
                
                # Calculate scores with combined origin and format multipliers
                for format_type, format_episode_count in origin_format_episodes.items():
                    if format_episode_count > 0:
                        format_multipliers = ANIME_FORMAT_MULTIPLIERS[format_type]
                        
                        # Base episode score with combined multipliers
                        combined_episode_weight = origin_multipliers["episode_weight"] * format_multipliers["episode_weight"]
                        anime_score += format_episode_count * 1.8 * combined_episode_weight
                        
                        # Variety bonus with combined multipliers
                        format_title_count = origin_format_counts[format_type]
                        combined_variety_weight = origin_multipliers["variety_weight"] * format_multipliers["variety_weight"]
                        anime_variety_score += format_title_count * 20 * combined_variety_weight
                        
                        # Efficiency bonus with combined multipliers
                        if format_title_count > 0:
                            avg_episodes = format_episode_count / format_title_count
                            combined_efficiency_weight = origin_multipliers["efficiency_bonus"] * format_multipliers["efficiency_bonus"]
                            efficiency = min(avg_episodes * 8, 400) * combined_efficiency_weight
                            anime_efficiency_score += efficiency
        
        total_score = (
            manga_score + anime_score +
            manga_variety_score + anime_variety_score +
            manga_efficiency_score + anime_efficiency_score
        )
        
        breakdown = {
            "manga_base": manga_score,
            "anime_base": anime_score,
            "manga_variety": manga_variety_score,
            "anime_variety": anime_variety_score,
            "manga_efficiency": manga_efficiency_score,
            "anime_efficiency": anime_efficiency_score,
            "total": total_score,
            "distribution": distribution,
            "format_breakdown": {
                "estimated_format_counts": format_counts,
                "estimated_format_episodes": format_episodes,
                "estimated_manga_format_counts": manga_format_counts,
                "estimated_manga_format_chapters": manga_format_chapters
            }
        }
        
        return total_score, breakdown

    async def _fetch_user_data(self, session: aiohttp.ClientSession, user: Tuple) -> Optional[Dict]:
        """Fetch and process individual user's AniList data."""
        try:
            # Correct structure: (id, discord_id, username, anilist_username, anilist_id)
            discord_id, username = user[1], user[3]  # discord_id is at index 1, anilist_username at index 3
            
            # Check persistent cache (per-user last fetch timestamp)
            now = time.time()
            cached_ts = get_cached_value(fetch_timestamps, str(discord_id), max_age_seconds=CACHE_TTL)
            if cached_ts is not None:
                logger.debug(f"Using cached data for user {username} (ID: {discord_id}) - last fetch within TTL")
                return None
            
            logger.info(f"Fetching fresh data for user {username} (discord_id: {discord_id})")
            data = await fetch_user_stats(username)
            
            if not data or "data" not in data or "User" not in data["data"]:
                logger.warning(f"No valid data returned for user {username}")
                return None

            user_data = data["data"]["User"]
            
            # Extract manga statistics
            manga_stats = user_data.get("statistics", {}).get("manga", {})
            total_manga = manga_stats.get("count", 0)
            total_chapters = manga_stats.get("chaptersRead", 0)
            avg_manga_score = manga_stats.get("meanScore", 0)
            
            # Extract anime statistics
            anime_stats = user_data.get("statistics", {}).get("anime", {})
            total_anime = anime_stats.get("count", 0)
            # Handle potential field name variations
            total_episodes = anime_stats.get("episodesWatched", 0) or anime_stats.get("chaptersRead", 0)
            avg_anime_score = anime_stats.get("meanScore", 0)

            # Update database
            await upsert_user_stats(
                discord_id,
                username,
                total_manga,
                total_anime,
                avg_manga_score,
                avg_anime_score,
                total_chapters,
                total_episodes
            )
            
            # Persist last fetch timestamp for this user
            set_cached_value(fetch_timestamps, str(discord_id), now)
            # Save the fetch_timestamps cache to disk
            try:
                save_timestamped_cache(_FETCH_CACHE_NAME, fetch_timestamps)
            except Exception:
                logger.debug("Failed to persist fetch timestamps cache (non-fatal)")
            logger.info(f"Successfully updated stats for {username}: {total_manga} manga, {total_anime} anime")
            
            return {
                "discord_id": discord_id,
                "username": username,
                "manga": {"count": total_manga, "chapters": total_chapters, "score": avg_manga_score},
                "anime": {"count": total_anime, "episodes": total_episodes, "score": avg_anime_score}
            }
            
        except Exception as e:
            logger.error(f"Error fetching data for user {username if 'username' in locals() else 'unknown'}: {e}", exc_info=True)
            return None

    async def cleanup_duplicate_user_stats(self) -> None:
        """Clean up duplicate entries in user_stats table."""
        try:
            logger.info("Starting cleanup of duplicate user_stats entries")
            
            async with aiosqlite.connect(DB_PATH) as db:
                # Find all duplicated usernames
                cursor = await db.execute("""
                    SELECT username, COUNT(*) as count 
                    FROM user_stats 
                    GROUP BY username 
                    HAVING count > 1
                """)
                duplicates = await cursor.fetchall()
                await cursor.close()
                
                if not duplicates:
                    logger.info("No duplicate user_stats entries found")
                    return
                
                logger.info(f"Found {len(duplicates)} users with duplicate entries")
                
                # For each duplicated username, keep only the entry with the correct discord_id from users table
                for username, count in duplicates:
                    logger.info(f"Cleaning up {count} duplicate entries for {username}")
                    
                    # Get the correct discord_id from the users table
                    cursor = await db.execute("""
                        SELECT discord_id FROM users WHERE anilist_username = ? OR username = ?
                    """, (username, username))
                    correct_user = await cursor.fetchone()
                    await cursor.close()
                    
                    if not correct_user:
                        logger.warning(f"No user found in users table for {username}, skipping cleanup")
                        continue
                    
                    correct_discord_id = correct_user[0]
                    logger.info(f"Correct discord_id for {username}: {correct_discord_id}")
                    
                    # Get all entries for this username, prioritizing the one with correct discord_id
                    cursor = await db.execute("""
                        SELECT discord_id, username, total_manga, total_anime, 
                               avg_manga_score, avg_anime_score, total_chapters, total_episodes
                        FROM user_stats 
                        WHERE username = ?
                        ORDER BY 
                            CASE WHEN discord_id = ? THEN 0 ELSE 1 END,  -- Prioritize correct discord_id
                            (total_manga + total_anime + COALESCE(total_chapters, 0) + COALESCE(total_episodes, 0)) DESC,
                            discord_id DESC
                    """, (username, correct_discord_id))
                    entries = await cursor.fetchall()
                    await cursor.close()
                    
                    if entries:
                        # Keep the first (most preferred) entry, but update discord_id to be correct
                        keep_entry = list(entries[0])
                        keep_entry[0] = correct_discord_id  # Ensure discord_id is correct
                        
                        logger.info(f"Keeping entry for {username} with discord_id={correct_discord_id}")
                        
                        # Delete all entries for this username
                        await db.execute("DELETE FROM user_stats WHERE username = ?", (username,))
                        
                        # Re-insert the corrected entry
                        await db.execute("""
                            INSERT INTO user_stats (
                                discord_id, username, total_manga, total_anime,
                                avg_manga_score, avg_anime_score, total_chapters, total_episodes
                            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                        """, keep_entry)
                        
                        logger.info(f"Successfully cleaned up duplicates for {username}")
                
                await db.commit()
                logger.info("Successfully cleaned up duplicate user_stats entries")
                
        except Exception as e:
            logger.error(f"Error cleaning up duplicate user_stats: {e}", exc_info=True)

    async def fetch_and_cache_stats(self) -> None:
        """Fetch and cache statistics for all registered users."""
        try:
            users = await get_all_users()
            if not users:
                logger.warning("No registered users found")
                return
            
            logger.info(f"Starting stats fetch for {len(users)} users")
            
            async with aiohttp.ClientSession() as session:
                # Process users in batches to avoid overwhelming the API
                batch_size = 5
                for i in range(0, len(users), batch_size):
                    batch = users[i:i + batch_size]
                    tasks = [self._fetch_user_data(session, user) for user in batch]
                    
                    results = await asyncio.gather(*tasks, return_exceptions=True)
                    
                    # Count successful updates
                    successful_updates = sum(1 for result in results if result and not isinstance(result, Exception))
                    logger.info(f"Processed batch {i//batch_size + 1}: {successful_updates}/{len(batch)} successful updates")
                    
                    # Small delay between batches to be respectful to the API
                    if i + batch_size < len(users):
                        await asyncio.sleep(1)
            
            logger.info("Completed stats fetching for all users")
            
        except Exception as e:
            logger.error(f"Error in fetch_and_cache_stats: {e}", exc_info=True)

    async def _get_leaderboard_data(self, medium: str) -> List[Tuple]:
        """Get leaderboard data from database for specified medium."""
        try:
            media_config = MEDIA_TYPES.get(medium, MEDIA_TYPES["manga"])
            sql = media_config["sql"]
            
            async with aiosqlite.connect(DB_PATH) as db:
                cursor = await db.execute(sql)
                rows = await cursor.fetchall()
                await cursor.close()

            if not rows:
                logger.warning(f"No database rows found for {medium} leaderboard")
                return []

            leaderboard_data = []
            
            if medium == "combined":
                # Combined leaderboard: calculate origin-weighted activity score
                for username, total_manga, total_chapters, total_anime, total_episodes in rows:
                    # Guard against None values
                    total_manga = total_manga or 0
                    total_chapters = total_chapters or 0
                    total_anime = total_anime or 0
                    total_episodes = total_episodes or 0
                    
                    # Calculate origin-weighted activity score
                    # This enhanced scoring system accounts for different media origins:
                    # - Japanese manga/anime (baseline weighting)
                    # - Korean manhwa/animation (higher weight due to longer content/rarity)
                    # - Chinese manhua/donghua (moderate weighting)
                    # - Estimated distribution based on consumption patterns
                    # - Scores typically range from 0-15,000+ points with better distinction
                    
                    activity_score, breakdown = self._calculate_origin_weighted_score(
                        total_manga, total_anime, total_chapters, total_episodes
                    )
                    
                    if activity_score > 0:  # Only include users with activity
                        # Store breakdown data for enhanced display
                        leaderboard_data.append((
                            username, total_manga, total_chapters, 
                            total_anime, total_episodes, activity_score, breakdown
                        ))
                
                # Sort by activity score in descending order
                leaderboard_data.sort(key=lambda x: x[5], reverse=True)
                
            else:
                # Standard manga/anime leaderboard
                # Some media queries (two-column: username, total_units)
                if medium in ("chapters", "episodes", "manga_completed", "anime_completed"):
                    for username, total_units in rows:
                        total_units = int(total_units or 0)
                        # For two-column queries we don't have a total_media count; use 0 for that field
                        leaderboard_data.append((username, 0, total_units, float(total_units)))
                else:
                    for username, total_media, total_units in rows:
                        # Guard against zero/None divisions
                        total_media = total_media or 0
                        total_units = total_units if total_units is not None else 0
                        
                        if total_media and total_units is not None:
                            avg_units = total_units / total_media if total_media > 0 else 0
                            leaderboard_data.append((username, total_media, total_units, avg_units))

                # Sort by average units per media in descending order
                leaderboard_data.sort(key=lambda x: x[3], reverse=True)
            
            logger.info(f"Generated {medium} leaderboard with {len(leaderboard_data)} valid entries")
            return leaderboard_data
            
        except Exception as e:
            logger.error(f"Error generating {medium} leaderboard data: {e}", exc_info=True)
            return []

    @app_commands.choices(medium=[
        app_commands.Choice(name="📖 Best Manga Average", value="manga"),
        app_commands.Choice(name="🎬 Best Anime Average", value="anime"),
        app_commands.Choice(name="🌟 Combined Animanga Average", value="combined"),
    app_commands.Choice(name="📚 Most Chapters Read", value="chapters"),
    app_commands.Choice(name="📺 Most Episodes Watched", value="episodes"),
    app_commands.Choice(name="📚 Most Manga Completed", value="manga_completed"),
    app_commands.Choice(name="📺 Most Anime Completed", value="anime_completed"),
    ])
    @app_commands.command(
        name="anilist_leaderboard",
        description="🏆 Show leaderboard ranked by manga, anime, or combined activity"
    )
    async def anilist_leaderboard(self, interaction: discord.Interaction, medium: app_commands.Choice[str]) -> None:
        """Display the leaderboard for the specified medium.
        
        Args:
            interaction: The Discord interaction
            medium: The media type (manga or anime) to show leaderboard for
        """
        logger.info(f"Leaderboard command invoked by {interaction.user} ({interaction.user.id}) for {medium.value}")
        
        # Check if command is used in a guild
        if not interaction.guild:
            await interaction.response.send_message(
                "❌ This command can only be used in a server!",
                ephemeral=True
            )
            return
        
        guild_id = interaction.guild.id
        
        try:
            await interaction.response.defer()
            
            chosen_medium = medium.value.lower()
            media_config = MEDIA_TYPES.get(chosen_medium, MEDIA_TYPES["manga"])
            
            # Check cache first
            cache_key = get_leaderboard_cache_key(guild_id, chosen_medium)
            cached_data = get_cached_leaderboard(cache_key)
            
            if cached_data:
                logger.info(f"Using cached leaderboard data for {chosen_medium} in guild {guild_id}")
                
                # Create and send the leaderboard view with cached data
                view = LeaderboardView(cached_data, medium=chosen_medium)
                
                # Create loading embed
                loading_embed = discord.Embed(
                    title="🔄 Loading Cached Leaderboard...",
                    description=f"Generating {media_config['title']} (from cache)",
                    color=discord.Color.blue()
                )
                
                message = await interaction.followup.send(embed=loading_embed, view=view)
                
                # Update with actual leaderboard content
                await view.update_embed(message)
                
                logger.info(f"Successfully displayed cached {chosen_medium} leaderboard with {len(cached_data)} users")
                return
            
            # Send wait message for fresh calculations
            await interaction.followup.send(
                "⏳ Please wait up to 2 minutes for leaderboard generation. You will only have to do this once a month due to caching.",
                ephemeral=True
            )
            
            # Clean up any duplicate entries first
            await self.cleanup_duplicate_user_stats()
            
            # Fetch and cache latest stats for users in this guild
            logger.info(f"Fetching and caching stats for {chosen_medium} leaderboard in guild {guild_id}")
            await self.fetch_and_cache_stats_guild_aware(guild_id)

            # Get guild-specific leaderboard data
            leaderboard_data = await self._get_leaderboard_data_guild_aware(chosen_medium, guild_id)
            
            if not leaderboard_data:
                error_embed = discord.Embed(
                    title="⚠️ No Data Found",
                    description=f"No progress data found for {media_config['media_label'].lower()}. Users need to have their AniList profiles linked and have consumed some {media_config['media_label'].lower()}!",
                    color=discord.Color.orange()
                )
                await interaction.followup.send(embed=error_embed, ephemeral=True)
                logger.warning(f"No leaderboard data found for {chosen_medium}")
                return

            # Cache the leaderboard data
            set_cached_leaderboard(cache_key, leaderboard_data)
            logger.info(f"Cached leaderboard data for {chosen_medium} in guild {guild_id}")

            # Create and send the leaderboard view
            view = LeaderboardView(leaderboard_data, medium=chosen_medium)
            
            # Create loading embed
            loading_embed = discord.Embed(
                title="🔄 Loading Leaderboard...",
                description=f"Generating {media_config['title']}",
                color=discord.Color.blue()
            )
            
            message = await interaction.followup.send(embed=loading_embed, view=view)
            
            # Update with actual leaderboard content
            await view.update_embed(message)
            
            logger.info(f"Successfully displayed {chosen_medium} leaderboard with {len(leaderboard_data)} users")
            
        except Exception as e:
            logger.error(f"Error processing leaderboard command: {e}", exc_info=True)
            
            error_embed = discord.Embed(
                title="❌ Something Went Wrong",
                description="An error occurred while generating the leaderboard. Please try again later!",
                color=discord.Color.red()
            )
            
            if not interaction.response.is_done():
                await interaction.response.send_message(embed=error_embed, ephemeral=True)
            else:
                await interaction.followup.send(embed=error_embed, ephemeral=True)


    async def _get_leaderboard_data_guild_aware(self, medium: str, guild_id: int) -> List[Tuple]:
        """Get guild-specific leaderboard data from database for specified medium."""
        try:
            logger.info(f"Getting {medium} leaderboard data for guild {guild_id}")
            
            # Use the new guild-aware leaderboard function
            leaderboard_entries = await get_guild_leaderboard_data(guild_id, medium)
            
            if not leaderboard_entries:
                logger.warning(f"No leaderboard entries found for {medium} in guild {guild_id}")
                return []

            leaderboard_data = []
            
            if medium == "combined":
                # Combined leaderboard: calculate origin-weighted activity score
                for entry in leaderboard_entries:
                    # Entry may be a dict (from DB helper) or a tuple/list
                    try:
                        if isinstance(entry, dict):
                            username = entry.get('username') or entry.get('anilist_username')
                            total_manga = int(entry.get('total_manga', 0) or 0)
                            total_chapters = int(entry.get('total_chapters', 0) or 0)
                            total_anime = int(entry.get('total_anime', 0) or 0)
                            total_episodes = int(entry.get('total_episodes', 0) or 0)
                        else:
                            username = entry[0]
                            total_manga = int(entry[1] if len(entry) > 1 else 0)
                            total_chapters = int(entry[2] if len(entry) > 2 else 0)
                            total_anime = int(entry[3] if len(entry) > 3 else 0)
                            total_episodes = int(entry[4] if len(entry) > 4 else 0)
                    except Exception:
                        logger.debug(f"Malformed combined entry for guild {guild_id}: {entry}")
                        continue

                    score, breakdown = self._calculate_origin_weighted_score(total_manga, total_anime, total_chapters, total_episodes)
                    leaderboard_data.append((username, total_manga, total_chapters, total_anime, total_episodes, score, breakdown))
                
                # Sort by activity score in descending order
                leaderboard_data.sort(key=lambda x: x[5], reverse=True)
                
            else:
                # Regular medium leaderboard (manga, anime, chapters, or episodes)
                if medium in ("chapters", "episodes", "manga_completed", "anime_completed"):
                    # For these mediums we want to rank by total units (chapters or episodes) only
                    for entry in leaderboard_entries:
                        try:
                            if isinstance(entry, dict):
                                username = entry.get('username') or entry.get('anilist_username')
                                if medium == 'chapters':
                                    total_units = int(entry.get('total_chapters', 0) or 0)
                                elif medium == 'episodes':
                                    total_units = int(entry.get('total_episodes', 0) or 0)
                                elif medium == 'manga_completed':
                                    total_units = int(entry.get('manga_completed', 0) or 0)
                                else:  # anime_completed
                                    total_units = int(entry.get('anime_completed', 0) or 0)
                            else:
                                # tuple layout from DB helper: (anilist_username, total_manga, total_anime, total_chapters, total_episodes, ...)
                                username = entry[0]
                                if medium == 'chapters':
                                    total_units = int(entry[3] if len(entry) > 3 else 0)
                                elif medium == 'episodes':
                                    total_units = int(entry[4] if len(entry) > 4 else 0)
                                elif medium == 'manga_completed':
                                    # completed counts are not part of the original SELECT; try named keys first (dict path), otherwise 0
                                    total_units = 0
                                else:
                                    total_units = 0
                        except Exception:
                            logger.debug(f"Malformed {medium} entry for guild {guild_id}: {entry}")
                            continue

                        # Shape to the standard (username, total_media, total_units, avg_units) where total_media is unused (0)
                        leaderboard_data.append((username, 0, total_units, float(total_units)))
                else:
                    # Entries expected: (username, total_media, total_units)
                    for entry in leaderboard_entries:
                        try:
                            if isinstance(entry, dict):
                                username = entry.get('username') or entry.get('anilist_username')
                                # For manga medium 'total_manga' is primary and 'total_chapters' is units
                                if medium == 'manga':
                                    total_media = int(entry.get('total_manga', 0) or 0)
                                    total_units = int(entry.get('total_chapters', 0) or 0)
                                else:  # anime
                                    total_media = int(entry.get('total_anime', 0) or 0)
                                    total_units = int(entry.get('total_episodes', 0) or 0)
                            else:
                                username = entry[0]
                                total_media = int(entry[1] if len(entry) > 1 else 0)
                                total_units = int(entry[2] if len(entry) > 2 else 0)
                        except Exception:
                            logger.debug(f"Malformed entry for guild {guild_id}: {entry}")
                            continue

                        avg_units = (total_units / total_media) if total_media > 0 else float(total_units)
                        leaderboard_data.append((username, total_media, total_units, avg_units))

                # Debug: log ordering before sort
                try:
                    logger.debug(f"Leaderboard data pre-sort sample for {medium} (first 10): %s", [(d[0], d[2]) for d in leaderboard_data[:10]])
                except Exception:
                    logger.debug("Could not serialize pre-sort leaderboard sample")

                # Sort by average units per media (or total units for chapters/episodes) in descending order
                leaderboard_data.sort(key=lambda x: x[3], reverse=True)

                # Debug: log ordering after sort
                try:
                    logger.debug(f"Leaderboard data post-sort sample for {medium} (first 10): %s", [(d[0], d[2]) for d in leaderboard_data[:10]])
                except Exception:
                    logger.debug("Could not serialize post-sort leaderboard sample")
            
            logger.info(f"✅ Generated {len(leaderboard_data)} entries for {medium} leaderboard in guild {guild_id}")
            return leaderboard_data
            
        except Exception as e:
            logger.error(f"Error getting guild leaderboard data for {medium} in guild {guild_id}: {e}", exc_info=True)
            return []


    async def fetch_and_cache_stats_guild_aware(self, guild_id: int):
        """Fetch and cache AniList stats for all users in a specific guild."""
        logger.info(f"Starting to fetch and cache stats for guild {guild_id}")
        
        try:
            # Get all users in this guild
            guild_users = await get_all_users_guild_aware(guild_id)
            
            if not guild_users:
                logger.info(f"No users found in guild {guild_id}")
                return
            
            logger.info(f"Found {len(guild_users)} users to process in guild {guild_id}")
            
            successful_updates = 0
            failed_updates = 0
            
            for user_record in guild_users:
                try:
                    # Extract user info from record (id, discord_id, guild_id, username, anilist_username, anilist_id, created_at, updated_at)
                    discord_id = user_record[1]
                    anilist_username = user_record[4] 
                    
                    if not anilist_username:
                        logger.debug(f"User {discord_id} in guild {guild_id} has no AniList username, skipping")
                        continue
                    
                    logger.info(f"Processing user {anilist_username} (Discord: {discord_id}) in guild {guild_id}")
                    
                    # Fetch stats from AniList API
                    updated = await self._update_user_stats_guild_aware(anilist_username, discord_id, guild_id)
                    
                    if updated:
                        successful_updates += 1
                    else:
                        failed_updates += 1
                    
                    # Small delay to avoid rate limiting (2 seconds between requests)
                    await asyncio.sleep(2)
                    
                except Exception as e:
                    logger.error(f"Error processing user {user_record}: {e}")
                    failed_updates += 1
            
            logger.info(f"✅ Completed guild {guild_id} stats update: {successful_updates} successful, {failed_updates} failed")
            
        except Exception as e:
            logger.error(f"Error in fetch_and_cache_stats_guild_aware for guild {guild_id}: {e}", exc_info=True)


    async def _update_user_stats_guild_aware(self, username: str, discord_id: int, guild_id: int) -> bool:
        """Update user stats for a specific guild context."""
        try:
            # Fetch user stats from AniList
            user_data = await fetch_user_stats(username)
            if not user_data:
                logger.warning(f"No AniList data found for {username}")
                return False

            # Some helpers return the raw GraphQL wrapper: { 'data': { 'User': {...} } }
            if isinstance(user_data, dict) and "data" in user_data and "User" in user_data["data"]:
                user_data = user_data["data"]["User"]

            # Defensive: ensure 'statistics' exists before indexing into it
            if "statistics" not in user_data:
                # Log a trimmed diagnostic so we can see why AniList returned unexpected data
                try:
                    top_keys = list(user_data.keys()) if isinstance(user_data, dict) else []
                except Exception:
                    top_keys = []
                logger.warning(
                    f"AniList payload for user {username} missing 'statistics' key. Top-level keys: {top_keys}"
                )
                return False

            stats_anime = user_data["statistics"].get("anime", {})
            stats_manga = user_data["statistics"].get("manga", {})

            total_manga = int(stats_manga.get("count", 0) or 0)
            total_anime = int(stats_anime.get("count", 0) or 0)
            # Extract chapter/episode totals when available
            total_chapters = int(stats_manga.get("chaptersRead", 0) or 0)
            # AniList sometimes uses 'episodesWatched' or other field names
            total_episodes = int(stats_anime.get("episodesWatched", 0) or stats_anime.get("episodes", 0) or 0)
            # Extract completed counts from status distributions when present
            manga_statuses = {s.get('status', '').upper(): int(s.get('count', 0) or 0) for s in stats_manga.get('statuses', [])}
            anime_statuses = {s.get('status', '').upper(): int(s.get('count', 0) or 0) for s in stats_anime.get('statuses', [])}

            manga_completed = manga_statuses.get('COMPLETED', 0)
            anime_completed = anime_statuses.get('COMPLETED', 0)
            
            # Calculate weighted averages from score distribution
            manga_avg = self._calc_weighted_avg(stats_manga.get("scores", [])) if isinstance(stats_manga.get("scores", []), list) else 0.0
            anime_avg = self._calc_weighted_avg(stats_anime.get("scores", [])) if isinstance(stats_anime.get("scores", []), list) else 0.0
            
            # Log the totals we will upsert (helps diagnose zero-value cases)
            logger.debug(
                "Upserting stats guild_aware: username=%s guild=%s discord_id=%s total_manga=%s total_chapters=%s total_anime=%s total_episodes=%s",
                user_data.get("name") or username, guild_id, discord_id, total_manga, total_chapters, total_anime, total_episodes
            )

            # Update database with guild context
            await upsert_user_stats_guild_aware(
                discord_id=discord_id,
                guild_id=guild_id,
                username=user_data.get("name") or username,
                total_manga=total_manga,
                total_anime=total_anime,
                avg_manga_score=manga_avg,
                avg_anime_score=anime_avg,
                total_chapters=total_chapters,
                total_episodes=total_episodes,
                # Pass completed counts to DB upsert (DB will ignore if column missing)
                manga_completed=manga_completed,
                anime_completed=anime_completed
            )
            
            logger.info(f"Successfully updated stats for {username} (Guild: {guild_id}): {total_manga} manga, {total_anime} anime")
            return True
            
        except Exception as e:
            logger.error(f"Error updating stats for {username} in guild {guild_id}: {e}")
            return False


    def _calc_weighted_avg(self, scores: List[Dict]) -> float:
        """Calculate weighted average from AniList score distribution."""
        if not scores:
            return 0.0
        
        total_weighted = 0
        total_count = 0
        
        for score_entry in scores:
            score = score_entry.get("score", 0)
            count = score_entry.get("count", 0)
            total_weighted += score * count
            total_count += count
        
        return round(total_weighted / total_count, 2) if total_count > 0 else 0.0


async def setup(bot: commands.Bot):
    """Set up the Leaderboard cog."""
    await bot.add_cog(Leaderboard(bot))
    logger.info("Leaderboard cog successfully loaded")