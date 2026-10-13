"""
Utility Helper Functions
Common utility functions used across multiple cogs and components
"""

import json
import logging
import pickle
from datetime import timezone
from pathlib import Path
from typing import Any, Dict, Optional

import discord
from discord.ext import commands

# Configuration constants
LOG_DIR = Path("logs")
LOG_FILE = LOG_DIR / "utility_helper.log"
CACHE_DIR = Path("data")
MAX_RETRIES = 3
REQUEST_TIMEOUT = 30

# Ensure required directories exist
LOG_DIR.mkdir(exist_ok=True)
CACHE_DIR.mkdir(exist_ok=True)

# Set up file-based logging
logger = logging.getLogger("UtilityHelper")
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

logger.info("Utility Helper logging system initialized")


# ===== HTTP REQUEST UTILITIES =====


# ===== CACHING UTILITIES =====

def get_cache_file_path(cache_name: str) -> Path:
    """
    Get standardized cache file path.
    """
    return CACHE_DIR / f"{cache_name}_cache.json"


def load_cache(cache_name: str) -> Dict[str, Any]:
    """
    Load cache from JSON file.
    """
    cache_file = get_cache_file_path(cache_name)
    try:
        if cache_file.exists():
            with open(cache_file, 'r', encoding='utf-8') as f:
                return json.load(f)
    except Exception as e:
        logger.error(f"Error loading cache {cache_name}: {e}")
    
    return {}


def save_cache(cache_name: str, data: Dict[str, Any]) -> bool:
    """
    Save cache to JSON file.
    """
    cache_file = get_cache_file_path(cache_name)
    try:
        with open(cache_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        return True
    except Exception as e:
        logger.error(f"Error saving cache {cache_name}: {e}")
        return False


def clear_cache(cache_name: str) -> bool:
    """
    Clear specific cache file.
    """
    cache_file = get_cache_file_path(cache_name)
    try:
        if cache_file.exists():
            try:
                cache_file.unlink()
            except PermissionError:
                logger.warning(f"Cache file {cache_file} is in use and could not be removed")
        return True
    except Exception as e:
        logger.error(f"Error clearing cache {cache_name}: {e}")
        return False


# ===== DATABASE UTILITIES =====


# ===== DISCORD UTILITIES =====


async def fetch_user_safe(bot: commands.Bot, user_id: int) -> Optional[discord.User]:
    """
    Fetch Discord user with fallback logic (get_user -> fetch_user).
    Returns None if user not found.
    
    Args:
        bot: Discord bot instance
        user_id: Discord user ID to fetch
    
    Returns:
        discord.User if found, None otherwise
    """
    # Try cache first
    user = bot.get_user(user_id)
    if user:
        return user
    
    # Try to fetch if not in cache
    try:
        user = await bot.fetch_user(user_id)
        return user
    except discord.NotFound:
        return None
    except Exception as e:
        logger.error(f"Error fetching user {user_id}: {e}")
        return None


# ===== FILE UTILITIES =====


# ===== RANDOM UTILITIES =====


# ===== VALIDATION UTILITIES =====


# ===== FORMATTING UTILITIES =====


# ===== ASYNC UTILITIES =====


# ===== ENVIRONMENT UTILITIES =====

