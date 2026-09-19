"""
Gaming Utilities
Unified error handling, caching, and utilities for gaming cogs
"""

import asyncio
import logging
import functools
import hashlib
import json
import time
from datetime import datetime, timedelta
from typing import Dict, Optional, Any, Callable
from pathlib import Path

import discord
import aiohttp

# Logging setup
LOG_DIR = Path("logs")
LOG_FILE = LOG_DIR / "gaming.log"
LOG_DIR.mkdir(exist_ok=True)

logger = logging.getLogger("Gaming")
logger.setLevel(logging.DEBUG)
logger.handlers.clear()

file_handler = logging.FileHandler(LOG_FILE, mode='a', encoding='utf-8')
file_handler.setLevel(logging.DEBUG)

formatter = logging.Formatter(
    fmt="[%(asctime)s] [%(levelname)-8s] [%(name)s] %(funcName)s:%(lineno)d - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
file_handler.setFormatter(formatter)
logger.addHandler(file_handler)

logger.info("Gaming utilities initialized")


# ===== CACHE SYSTEM =====

class GamingCache:
    """In-memory cache for gaming data with TTL support"""

    def __init__(self):
        self._cache: Dict[str, Dict[str, Any]] = {}
        logger.info("GamingCache initialized")

    def get(self, key: str) -> Optional[Any]:
        """Get cached value if not expired"""
        if key not in self._cache:
            return None

        entry = self._cache[key]
        if time.time() > entry['expires']:
            # Expired, remove it
            del self._cache[key]
            logger.debug(f"Cache expired for key: {key}")
            return None

        logger.debug(f"Cache hit for key: {key}")
        return entry['value']

    def set(self, key: str, value: Any, ttl_seconds: int = 3600):
        """Set cached value with TTL (default 1 hour)"""
        self._cache[key] = {
            'value': value,
            'expires': time.time() + ttl_seconds
        }
        logger.debug(f"Cache set for key: {key} (TTL: {ttl_seconds}s)")

    def clear(self):
        """Clear all cached data"""
        count = len(self._cache)
        self._cache.clear()
        logger.info(f"Cache cleared ({count} entries)")

    def cleanup_expired(self):
        """Remove expired entries"""
        now = time.time()
        expired = [k for k, v in self._cache.items() if now > v['expires']]
        for key in expired:
            del self._cache[key]
        if expired:
            logger.info(f"Cleaned up {len(expired)} expired cache entries")


# Global cache instance
gaming_cache = GamingCache()


# ===== CONNECTION POOL =====

class ConnectionPool:
    """Manages aiohttp ClientSession with connection pooling"""

    def __init__(self):
        self._session: Optional[aiohttp.ClientSession] = None
        self._connector: Optional[aiohttp.TCPConnector] = None
        logger.info("ConnectionPool initialized")

    async def get_session(self) -> aiohttp.ClientSession:
        """Get or create aiohttp session with connection pooling"""
        if self._session is None or self._session.closed:
            self._connector = aiohttp.TCPConnector(
                limit=100,  # Total connection limit
                limit_per_host=10,  # Per-host connection limit
                ttl_dns_cache=300,  # DNS cache for 5 minutes
                enable_cleanup_closed=True
            )

            timeout = aiohttp.ClientTimeout(total=30)

            self._session = aiohttp.ClientSession(
                connector=self._connector,
                timeout=timeout,
                headers={
                    'User-Agent': 'Lemegeton Discord Bot (Gaming Features)'
                }
            )
            logger.info("Created new aiohttp session with connection pooling")

        return self._session

    async def close(self):
        """Close the session and connector"""
        if self._session and not self._session.closed:
            await self._session.close()
            logger.info("Closed aiohttp session")

        if self._connector:
            await self._connector.close()
            logger.info("Closed TCP connector")


# Global connection pool
connection_pool = ConnectionPool()


# ===== ERROR HANDLING =====

class GamingError(Exception):
    """Base exception for gaming cogs"""
    pass


class SteamAPIError(GamingError):
    """Steam API specific errors"""
    pass


class ProfilePrivateError(GamingError):
    """User profile is private"""
    pass


class ProfileNotFoundError(GamingError):
    """Profile not found"""
    pass


class RateLimitError(GamingError):
    """API rate limit exceeded"""
    pass


def gaming_error_handler(func):
    """Decorator for unified error handling in gaming commands"""
    @functools.wraps(func)
    async def wrapper(*args, **kwargs):
        # Extract interaction from args (usually args[1] for commands)
        interaction = None
        for arg in args:
            if isinstance(arg, discord.Interaction):
                interaction = arg
                break

        try:
            return await func(*args, **kwargs)

        except ProfilePrivateError as e:
            logger.warning(f"Private profile error: {e}")
            if interaction:
                try:
                    await interaction.followup.send(
                        "❌ **Profile is Private**\n\n"
                        "This Steam profile is set to private. Please set your profile to public:\n"
                        "1. Go to Steam → Profile → Edit Profile\n"
                        "2. Set 'My Privacy Settings' to Public\n"
                        "3. Save changes and try again",
                        ephemeral=True
                    )
                except discord.NotFound:
                    logger.error("Interaction expired while sending private profile error")

        except ProfileNotFoundError as e:
            logger.warning(f"Profile not found: {e}")
            if interaction:
                try:
                    await interaction.followup.send(
                        f"❌ **Profile Not Found**\n\n{str(e)}",
                        ephemeral=True
                    )
                except discord.NotFound:
                    logger.error("Interaction expired while sending not found error")

        except RateLimitError as e:
            logger.error(f"Rate limit error: {e}")
            if interaction:
                try:
                    await interaction.followup.send(
                        "⏰ **Rate Limit Exceeded**\n\n"
                        "Too many requests. Please try again in a few minutes.",
                        ephemeral=True
                    )
                except discord.NotFound:
                    logger.error("Interaction expired while sending rate limit error")

        except SteamAPIError as e:
            logger.error(f"Steam API error: {e}")
            if interaction:
                try:
                    await interaction.followup.send(
                        f"❌ **Steam API Error**\n\n{str(e)}\n\n"
                        "Please try again later.",
                        ephemeral=True
                    )
                except discord.NotFound:
                    logger.error("Interaction expired while sending API error")

        except discord.NotFound:
            logger.error(f"Interaction expired in {func.__name__}")

        except Exception as e:
            logger.exception(f"Unexpected error in {func.__name__}: {e}")
            if interaction:
                try:
                    await interaction.followup.send(
                        "❌ **An unexpected error occurred**\n\n"
                        "Please try again later. If the issue persists, contact an administrator.",
                        ephemeral=True
                    )
                except:
                    pass  # Interaction expired

    return wrapper


# ===== API REQUEST HELPERS WITH CACHING =====

async def cached_api_request(
    url: str,
    params: Optional[Dict] = None,
    cache_ttl: int = 3600,
    cache_key: Optional[str] = None
) -> Optional[Dict]:
    """
    Make API request with automatic caching

    Args:
        url: API endpoint URL
        params: Query parameters
        cache_ttl: Cache time-to-live in seconds (default 1 hour)
        cache_key: Custom cache key (auto-generated if None)

    Returns:
        JSON response dict or None if failed
    """
    # Generate cache key from URL and params
    if cache_key is None:
        key_data = f"{url}:{json.dumps(params, sort_keys=True)}"
        cache_key = hashlib.md5(key_data.encode()).hexdigest()

    # Check cache first
    cached = gaming_cache.get(cache_key)
    if cached is not None:
        logger.debug(f"API cache hit: {url}")
        return cached

    # Make request
    try:
        session = await connection_pool.get_session()
        async with session.get(url, params=params) as resp:
            if resp.status == 429:
                logger.warning(f"Rate limited: {url}")
                raise RateLimitError("API rate limit exceeded")

            if resp.status != 200:
                logger.warning(f"API returned {resp.status}: {url}")
                return None

            data = await resp.json()

            # Cache the response
            gaming_cache.set(cache_key, data, cache_ttl)
            logger.debug(f"API request cached: {url}")

            return data

    except aiohttp.ClientError as e:
        logger.error(f"Client error for {url}: {e}")
        return None
    except asyncio.TimeoutError:
        logger.error(f"Timeout for {url}")
        return None
    except Exception as e:
        logger.exception(f"Unexpected error for {url}: {e}")
        return None


async def batch_api_requests(requests: list) -> list:
    """
    Execute multiple API requests concurrently

    Args:
        requests: List of dicts with 'url', 'params', 'cache_ttl', 'cache_key'

    Returns:
        List of responses in same order as requests
    """
    tasks = []
    for req in requests:
        task = cached_api_request(
            url=req['url'],
            params=req.get('params'),
            cache_ttl=req.get('cache_ttl', 3600),
            cache_key=req.get('cache_key')
        )
        tasks.append(task)

    logger.info(f"Executing {len(tasks)} batched API requests")
    results = await asyncio.gather(*tasks, return_exceptions=True)

    # Convert exceptions to None
    processed = []
    for result in results:
        if isinstance(result, Exception):
            logger.error(f"Batch request failed: {result}")
            processed.append(None)
        else:
            processed.append(result)

    return processed


# ===== UTILITY FUNCTIONS =====

def format_playtime(minutes: int) -> str:
    """Format playtime minutes to human-readable string"""
    if minutes == 0:
        return "Never played"

    hours = minutes / 60

    if hours < 1:
        return f"{minutes} minutes"
    elif hours < 100:
        return f"{hours:.1f} hours"
    else:
        return f"{int(hours):,} hours"


def format_price(cents: int) -> str:
    """Format price in cents to USD string"""
    if cents == 0:
        return "Free"

    dollars = cents / 100
    return f"${dollars:.2f}"


def get_steam_profile_url(steamid: str) -> str:
    """Get Steam profile URL from SteamID64"""
    return f"https://steamcommunity.com/profiles/{steamid}"


def get_steam_game_url(appid: int) -> str:
    """Get Steam store page URL"""
    return f"https://store.steampowered.com/app/{appid}"


def get_protondb_url(appid: int) -> str:
    """Get ProtonDB compatibility page URL"""
    return f"https://www.protondb.com/app/{appid}"


def is_steam_deck_verified(game_data: Dict) -> Optional[str]:
    """
    Check Steam Deck compatibility from game data
    Returns: 'verified', 'playable', 'unsupported', or None if unknown
    """
    # This data comes from Steam Store API
    categories = game_data.get('categories', [])

    for cat in categories:
        cat_id = cat.get('id')
        if cat_id == 59:  # Steam Deck Verified
            return 'verified'
        elif cat_id == 60:  # Steam Deck Playable
            return 'playable'
        elif cat_id == 61:  # Steam Deck Unsupported
            return 'unsupported'

    return None


def get_controller_support(game_data: Dict) -> Optional[str]:
    """
    Get controller support info from game data
    Returns: 'full', 'partial', or None
    """
    controller = game_data.get('controller_support')

    if not controller:
        return None

    controller_lower = controller.lower()

    if 'full' in controller_lower:
        return 'full'
    elif 'partial' in controller_lower:
        return 'partial'

    return None


def create_steam_deck_badge(compatibility: str) -> str:
    """Create emoji badge for Steam Deck compatibility"""
    badges = {
        'verified': '✅ Deck Verified',
        'playable': '⚠️ Deck Playable',
        'unsupported': '❌ Deck Unsupported'
    }
    return badges.get(compatibility, '')


def create_controller_badge(support: str) -> str:
    """Create emoji badge for controller support"""
    badges = {
        'full': '🎮 Full Controller',
        'partial': '🎮 Partial Controller'
    }
    return badges.get(support, '')


# ===== CLEANUP TASK =====

async def cleanup_expired_cache():
    """Periodic cleanup of expired cache entries"""
    while True:
        await asyncio.sleep(600)  # Run every 10 minutes
        gaming_cache.cleanup_expired()


# Start cleanup task on import
asyncio.create_task(cleanup_expired_cache())

logger.info("Gaming utilities module loaded successfully")
