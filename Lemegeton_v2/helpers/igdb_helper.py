"""
IGDB API Helper Functions
Centralized functions for interacting with IGDB (Internet Game Database) API
"""

import aiohttp
import asyncio
import logging
from typing import Optional, Dict, Any, List
from pathlib import Path
import os

# Configuration constants
LOG_DIR = Path("logs")
LOG_FILE = LOG_DIR / "igdb_helper.log"
IGDB_API_URL = "https://api.igdb.com/v4"
API_TIMEOUT = 30
MAX_RETRIES = 3

# IGDB requires authentication
IGDB_CLIENT_ID = os.getenv("IGDB_CLIENT_ID", "")
IGDB_CLIENT_SECRET = os.getenv("IGDB_CLIENT_SECRET", "")

# Ensure logs directory exists
LOG_DIR.mkdir(exist_ok=True)

# Set up file-based logging
logger = logging.getLogger("IGDBHelper")
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

logger.info("IGDB Helper logging system initialized")


# ===== AUTHENTICATION =====

_cached_token: Optional[str] = None
_cached_token_expires_at: Optional[float] = None

async def _fetch_token_data(session: aiohttp.ClientSession) -> Optional[Dict[str, Any]]:
    """Fetch raw token data from Twitch (IGDB auth via Twitch).

    Returns the full JSON response (contains access_token and expires_in) or None.
    """
    if not IGDB_CLIENT_ID or not IGDB_CLIENT_SECRET:
        logger.error("IGDB_CLIENT_ID and IGDB_CLIENT_SECRET environment variables not set")
        return None

    url = "https://id.twitch.tv/oauth2/token"
    data = {
        "client_id": IGDB_CLIENT_ID,
        "client_secret": IGDB_CLIENT_SECRET,
        "grant_type": "client_credentials"
    }

    try:
        async with session.post(url, data=data, timeout=API_TIMEOUT) as response:
            if response.status == 200:
                token_data = await response.json()
                logger.info("Successfully obtained IGDB access token data")
                return token_data
            else:
                text = await response.text()
                logger.error(f"Failed to get IGDB access token: HTTP {response.status} - {text}")
                return None
    except Exception as e:
        logger.error(f"Error getting IGDB access token: {e}")
        return None


async def get_access_token(session: aiohttp.ClientSession) -> Optional[str]:
    """Get a valid IGDB access token (cached in-memory during process lifetime).

    This wrapper will reuse a cached token until it's near expiry, then refresh.
    Returns the access token string or None on failure.
    """
    global _cached_token, _cached_token_expires_at

    # If cached token exists and not expired, return it
    if _cached_token and _cached_token_expires_at:
        # Add a small safety margin (60s)
        if _cached_token_expires_at - 60 > asyncio.get_event_loop().time():
            return _cached_token

    # Otherwise fetch fresh token data
    token_data = await _fetch_token_data(session)
    if not token_data:
        return None

    access_token = token_data.get("access_token")
    expires_in = token_data.get("expires_in")
    if not access_token:
        logger.error("IGDB token response missing access_token")
        return None

    # Compute expiry timestamp using event loop time
    try:
        now = asyncio.get_event_loop().time()
        if isinstance(expires_in, (int, float)):
            _cached_token_expires_at = now + float(expires_in)
        else:
            # Default to 1 hour if unknown
            _cached_token_expires_at = now + 3600.0
    except Exception:
        _cached_token_expires_at = None

    _cached_token = access_token
    return _cached_token


# ===== API FUNCTIONS =====

async def search_games(session: aiohttp.ClientSession, access_token: str, query: str, limit: int = 10) -> List[Dict]:
    """
    Search for games on IGDB.
    """
    url = f"{IGDB_API_URL}/games"
    headers = {
        "Client-ID": IGDB_CLIENT_ID,
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/json"
    }

    # IGDB query format
    body = f"""
    search "{query}";
    fields name, slug, cover.url, cover.image_id;
    limit {limit};
    """

    try:
        async with session.post(url, headers=headers, data=body, timeout=API_TIMEOUT) as response:
            if response.status == 200:
                games = await response.json()
                logger.info(f"Found {len(games)} games for query '{query}'")
                return games
            else:
                logger.error(f"IGDB search failed: HTTP {response.status}")
                return []
    except Exception as e:
        logger.error(f"Error searching IGDB: {e}")
        return []


async def get_game_by_slug(session: aiohttp.ClientSession, access_token: str, slug: str) -> Optional[Dict]:
    """
    Get game details by slug.
    """
    url = f"{IGDB_API_URL}/games"
    headers = {
        "Client-ID": IGDB_CLIENT_ID,
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/json"
    }

    # IGDB query format
    body = f"""
    where slug = "{slug}";
    fields name, slug, cover.url, cover.image_id;
    limit 1;
    """

    try:
        async with session.post(url, headers=headers, data=body, timeout=API_TIMEOUT) as response:
            if response.status == 200:
                games = await response.json()
                if games:
                    game = games[0]
                    logger.info(f"Found game '{game.get('name')}' for slug '{slug}'")
                    return game
                else:
                    logger.warning(f"No game found for slug '{slug}'")
                    return None
            else:
                logger.error(f"IGDB game lookup failed: HTTP {response.status}")
                return None
    except Exception as e:
        logger.error(f"Error getting game by slug: {e}")
        return None


def get_cover_image_url(cover_data: Dict) -> Optional[str]:
    """
    Convert IGDB cover data to full image URL.
    IGDB provides image_id, need to construct full URL.
    """
    if not cover_data or not cover_data.get("image_id"):
        return None

    image_id = cover_data["image_id"]
    # IGDB images are available in different sizes
    # Using 'cover_big' for good quality (300x420)
    return f"https://images.igdb.com/igdb/image/upload/t_cover_big/{image_id}.jpg"