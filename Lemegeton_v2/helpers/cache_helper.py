"""
Cache Management Helper Functions
Centralized caching system for API responses, recommendations, and other data
"""

import json
import logging
import os
import pickle
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple, Union

# Configuration constants
LOG_DIR = Path("logs")
LOG_FILE = LOG_DIR / "cache_helper.log"
CACHE_DIR = Path("data")
DEFAULT_CACHE_DURATION = 3600  # 1 hour in seconds
RECOMMENDATION_CACHE_DURATION = 86400  # 24 hours for recommendations

# Ensure required directories exist
LOG_DIR.mkdir(exist_ok=True)
CACHE_DIR.mkdir(exist_ok=True)

# Set up file-based logging
logger = logging.getLogger("CacheHelper")
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

logger.info("Cache Helper logging system initialized")


# ===== CACHE FILE MANAGEMENT =====

def get_cache_file_path(cache_name: str, cache_type: str = "json") -> Path:
    """
    Get standardized cache file path.
    """
    extension = "json" if cache_type == "json" else "pkl"
    return CACHE_DIR / f"{cache_name}_cache.{extension}"


def ensure_cache_directory() -> bool:
    """
    Ensure cache directory exists.
    """
    try:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        return True
    except Exception as e:
        logger.error(f"Failed to create cache directory: {e}")
        return False


# ===== JSON CACHE OPERATIONS =====

def load_json_cache(cache_name: str) -> Dict[str, Any]:
    """
    Load cache from JSON file.
    """
    cache_file = get_cache_file_path(cache_name, "json")
    try:
        if cache_file.exists():
            with open(cache_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                logger.debug(f"Loaded JSON cache '{cache_name}' with {len(data)} entries")
                return data
    except Exception as e:
        logger.error(f"Error loading JSON cache '{cache_name}': {e}")
    
    logger.debug(f"JSON cache '{cache_name}' not found or invalid, returning empty dict")
    return {}


def save_json_cache(cache_name: str, data: Dict[str, Any]) -> bool:
    """
    Save cache to JSON file.
    """
    if not ensure_cache_directory():
        return False
    
    cache_file = get_cache_file_path(cache_name, "json")
    try:
        # Atomic write using temporary file
        temp_file = cache_file.with_suffix('.tmp')
        with open(temp_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        
        # Replace original file
        temp_file.replace(cache_file)
        logger.debug(f"Saved JSON cache '{cache_name}' with {len(data)} entries")
        return True
    except Exception as e:
        logger.error(f"Error saving JSON cache '{cache_name}': {e}")
        return False


def is_json_cache_valid(cache_name: str, max_age_seconds: int = DEFAULT_CACHE_DURATION) -> bool:
    """
    Check if JSON cache file exists and is within max age.
    """
    cache_file = get_cache_file_path(cache_name, "json")
    if not cache_file.exists():
        return False
    
    try:
        cache_age = time.time() - cache_file.stat().st_mtime
        is_valid = cache_age < max_age_seconds
        logger.debug(f"JSON cache '{cache_name}' age: {cache_age:.1f}s, valid: {is_valid}")
        return is_valid
    except Exception as e:
        logger.error(f"Error checking JSON cache validity '{cache_name}': {e}")
        return False


# ===== PICKLE CACHE OPERATIONS =====

def load_pickle_cache(cache_name: str) -> Any:
    """
    Load cache from pickle file.
    """
    cache_file = get_cache_file_path(cache_name, "pickle")
    try:
        if cache_file.exists():
            with open(cache_file, 'rb') as f:
                data = pickle.load(f)
                logger.debug(f"Loaded pickle cache '{cache_name}'")
                return data
    except Exception as e:
        logger.error(f"Error loading pickle cache '{cache_name}': {e}")
    
    logger.debug(f"Pickle cache '{cache_name}' not found or invalid, returning None")
    return None


def save_pickle_cache(cache_name: str, data: Any) -> bool:
    """
    Save cache to pickle file.
    """
    if not ensure_cache_directory():
        return False
    
    cache_file = get_cache_file_path(cache_name, "pickle")
    try:
        # Atomic write using temporary file
        temp_file = cache_file.with_suffix('.tmp')
        with open(temp_file, 'wb') as f:
            pickle.dump(data, f)
        
        # Replace original file
        temp_file.replace(cache_file)
        logger.debug(f"Saved pickle cache '{cache_name}'")
        return True
    except Exception as e:
        logger.error(f"Error saving pickle cache '{cache_name}': {e}")
        return False


def is_pickle_cache_valid(cache_name: str, max_age_seconds: int = DEFAULT_CACHE_DURATION) -> bool:
    """
    Check if pickle cache file exists and is within max age.
    """
    cache_file = get_cache_file_path(cache_name, "pickle")
    if not cache_file.exists():
        return False
    
    try:
        cache_age = time.time() - cache_file.stat().st_mtime
        is_valid = cache_age < max_age_seconds
        logger.debug(f"Pickle cache '{cache_name}' age: {cache_age:.1f}s, valid: {is_valid}")
        return is_valid
    except Exception as e:
        logger.error(f"Error checking pickle cache validity '{cache_name}': {e}")
        return False


# ===== TIMESTAMPED CACHE OPERATIONS =====

def load_timestamped_cache(cache_name: str) -> Dict[str, Tuple[Any, float]]:
    """
    Load cache with timestamps from JSON file.
    Format: {key: [value, timestamp]}
    """
    data = load_json_cache(cache_name)
    
    # Convert to internal format: {key: (value, timestamp)}
    timestamped_data = {}
    for key, entry in data.items():
        if isinstance(entry, list) and len(entry) == 2:
            value, timestamp = entry
            timestamped_data[key] = (value, timestamp)
    
    return timestamped_data


def save_timestamped_cache(cache_name: str, data: Dict[str, Tuple[Any, float]]) -> bool:
    """
    Save cache with timestamps to JSON file.
    """
    # Convert to JSON-serializable format: {key: [value, timestamp]}
    json_data = {}
    for key, (value, timestamp) in data.items():
        json_data[key] = [value, timestamp]
    
    return save_json_cache(cache_name, json_data)


def get_cached_value(cache_data: Dict[str, Tuple[Any, float]], key: str, max_age_seconds: int = DEFAULT_CACHE_DURATION) -> Optional[Any]:
    """
    Get value from timestamped cache if not expired.
    """
    if key not in cache_data:
        return None
    
    value, timestamp = cache_data[key]
    current_time = time.time()
    
    if current_time - timestamp < max_age_seconds:
        return value
    
    # Remove expired entry
    del cache_data[key]
    return None


def set_cached_value(cache_data: Dict[str, Tuple[Any, float]], key: str, value: Any) -> None:
    """
    Set value in timestamped cache with current timestamp.
    """
    current_time = time.time()
    cache_data[key] = (value, current_time)


def clean_expired_cache(cache_data: Dict[str, Tuple[Any, float]], max_age_seconds: int = DEFAULT_CACHE_DURATION) -> int:
    """
    Remove expired entries from timestamped cache.
    Returns number of entries removed.
    """
    current_time = time.time()
    expired_keys = []
    
    for key, (value, timestamp) in cache_data.items():
        if current_time - timestamp >= max_age_seconds:
            expired_keys.append(key)
    
    for key in expired_keys:
        del cache_data[key]
    
    if expired_keys:
        logger.debug(f"Cleaned {len(expired_keys)} expired cache entries")
    
    return len(expired_keys)


# ===== RECOMMENDATION CACHE MANAGEMENT =====

class RecommendationCache:
    """
    ⚠️ DEPRECATED: This class is deprecated as of October 2, 2025.
    
    Use database functions instead:
    - `database.get_recommendation_count(media_id)` to get count
    - `database.set_recommendation_count(media_id, count, expires_hours)` to set count
    - `database.clean_expired_cache()` to clean expired entries
    
    This class still uses JSON file persistence which has been replaced by
    the database. It remains here for backwards compatibility but is not
    used by any active code.
    
    Original purpose: Specialized cache for recommendation data with persistence.
    """
    
    def __init__(self, cache_name: str = "recommendation", cache_duration: int = RECOMMENDATION_CACHE_DURATION):
        logger.warning(
            "RecommendationCache is DEPRECATED. Use database functions instead:\n"
            "  - database.get_recommendation_count(media_id)\n"
            "  - database.set_recommendation_count(media_id, count, expires_hours)\n"
            "  - database.clean_expired_cache()"
        )
        self.cache_name = cache_name
        self.cache_duration = cache_duration
        self.data: Dict[int, Tuple[int, float]] = {}  # {media_id: (count, timestamp)}
        self.load_cache()
    
    def load_cache(self) -> None:
        """
        Load recommendation cache from persistent storage.
        """
        try:
            cache_data = load_timestamped_cache(self.cache_name)
            
            # Convert string keys back to integers and validate timestamps
            current_time = time.time()
            valid_entries = 0
            
            for str_key, (count, timestamp) in cache_data.items():
                if current_time - timestamp < self.cache_duration:
                    try:
                        media_id = int(str_key)
                        self.data[media_id] = (count, timestamp)
                        valid_entries += 1
                    except ValueError:
                        logger.warning(f"Invalid media ID in cache: {str_key}")
            
            logger.info(f"Loaded {valid_entries} valid recommendation cache entries")
        except Exception as e:
            logger.error(f"Failed to load recommendation cache: {e}")
            self.data = {}
    
    def save_cache(self) -> bool:
        """
        Save recommendation cache to persistent storage.
        """
        try:
            # Clean expired entries before saving
            self.clean_expired()
            
            # Convert integer keys to strings for JSON serialization
            string_data = {
                str(media_id): (count, timestamp)
                for media_id, (count, timestamp) in self.data.items()
            }
            
            success = save_timestamped_cache(self.cache_name, string_data)
            if success:
                logger.debug(f"Saved {len(self.data)} recommendation cache entries")
            return success
        except Exception as e:
            logger.error(f"Failed to save recommendation cache: {e}")
            return False
    
    def get_count(self, media_id: int) -> Optional[int]:
        """
        Get recommendation count for media ID.
        """
        if media_id in self.data:
            count, timestamp = self.data[media_id]
            current_time = time.time()
            
            if current_time - timestamp < self.cache_duration:
                return count
            else:
                # Remove expired entry
                del self.data[media_id]
        
        return None
    
    def set_count(self, media_id: int, count: int) -> None:
        """
        Set recommendation count for media ID.
        """
        current_time = time.time()
        self.data[media_id] = (count, current_time)
    
    def increment_count(self, media_id: int) -> int:
        """
        Increment recommendation count for media ID.
        Returns new count.
        """
        current_count = self.get_count(media_id) or 0
        new_count = current_count + 1
        self.set_count(media_id, new_count)
        return new_count
    
    def clean_expired(self) -> int:
        """
        Remove expired entries from cache.
        """
        return clean_expired_cache(self.data, self.cache_duration)
    
    def get_popular_media(self, min_count: int = 5, limit: int = 100) -> List[Tuple[int, int]]:
        """
        Get list of popular media IDs with their counts.
        Returns list of (media_id, count) tuples sorted by count descending.
        """
        self.clean_expired()
        
        popular = [
            (media_id, count)
            for media_id, (count, timestamp) in self.data.items()
            if count >= min_count
        ]
        
        popular.sort(key=lambda x: x[1], reverse=True)
        return popular[:limit]


# ===== POPULAR TITLES CACHE =====

class PopularTitlesCache:
    """
    Cache for tracking popular/trending titles.
    """
    
    def __init__(self, cache_name: str = "popular_titles"):
        self.cache_name = cache_name
        self.titles: Set[int] = set()
        self.load_cache()
    
    def load_cache(self) -> None:
        """
        Load popular titles from cache.
        """
        try:
            data = load_json_cache(self.cache_name)
            if isinstance(data, list):
                self.titles = set(data)
                logger.info(f"Loaded {len(self.titles)} popular titles from cache")
            else:
                logger.warning("Popular titles cache format invalid, starting fresh")
                self.titles = set()
        except Exception as e:
            logger.error(f"Failed to load popular titles cache: {e}")
            self.titles = set()
    
    def save_cache(self) -> bool:
        """
        Save popular titles to cache.
        """
        try:
            data = list(self.titles)
            success = save_json_cache(self.cache_name, data)
            if success:
                logger.debug(f"Saved {len(self.titles)} popular titles to cache")
            return success
        except Exception as e:
            logger.error(f"Failed to save popular titles cache: {e}")
            return False
    
    def add_title(self, media_id: int) -> None:
        """
        Add title to popular cache.
        """
        self.titles.add(media_id)
    
    def remove_title(self, media_id: int) -> None:
        """
        Remove title from popular cache.
        """
        self.titles.discard(media_id)
    
    def is_popular(self, media_id: int) -> bool:
        """
        Check if title is in popular cache.
        """
        return media_id in self.titles
    
    def get_popular_ids(self) -> List[int]:
        """
        Get list of popular media IDs.
        """
        return list(self.titles)
    
    def clear(self) -> None:
        """
        Clear all popular titles.
        """
        self.titles.clear()


# ===== CACHE CLEANUP UTILITIES =====

def clear_cache(cache_name: str, cache_type: str = "json") -> bool:
    """
    Clear specific cache file.
    """
    cache_file = get_cache_file_path(cache_name, cache_type)
    try:
        if cache_file.exists():
            try:
                cache_file.unlink()
                logger.info(f"Cleared cache '{cache_name}' ({cache_type})")
            except PermissionError:
                logger.warning(f"Cache file {cache_file} is in use and could not be removed")
        return True
    except Exception as e:
        logger.error(f"Error clearing cache '{cache_name}': {e}")
        return False


def clear_all_caches() -> int:
    """
    Clear all cache files.
    Returns number of files cleared.
    """
    if not CACHE_DIR.exists():
        return 0
    
    cleared_count = 0
    try:
        for cache_file in CACHE_DIR.glob("*_cache.*"):
            try:
                try:
                    cache_file.unlink()
                    cleared_count += 1
                    logger.debug(f"Cleared cache file: {cache_file.name}")
                except PermissionError:
                    logger.warning(f"Cache file {cache_file} is in use and could not be removed")
            except Exception as e:
                logger.error(f"Error clearing cache file {cache_file.name}: {e}")
    except Exception as e:
        logger.error(f"Error clearing caches: {e}")
    
    if cleared_count > 0:
        logger.info(f"Cleared {cleared_count} cache files")
    
    return cleared_count


def get_cache_info() -> Dict[str, Dict[str, Any]]:
    """
    Get information about all cache files.
    """
    info = {}
    
    if not CACHE_DIR.exists():
        return info
    
    try:
        for cache_file in CACHE_DIR.glob("*_cache.*"):
            try:
                stat = cache_file.stat()
                cache_name = cache_file.stem.replace("_cache", "")
                
                info[cache_name] = {
                    "file": cache_file.name,
                    "size_bytes": stat.st_size,
                    "modified": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc),
                    "age_seconds": time.time() - stat.st_mtime
                }
            except Exception as e:
                logger.error(f"Error getting info for cache file {cache_file.name}: {e}")
    except Exception as e:
        logger.error(f"Error getting cache info: {e}")
    
    return info


def cleanup_old_caches(max_age_days: int = 7) -> int:
    """
    Remove cache files older than specified days.
    Returns number of files removed.
    """
    if not CACHE_DIR.exists():
        return 0
    
    max_age_seconds = max_age_days * 24 * 3600
    current_time = time.time()
    removed_count = 0
    
    try:
        for cache_file in CACHE_DIR.glob("*_cache.*"):
            try:
                file_age = current_time - cache_file.stat().st_mtime
                if file_age > max_age_seconds:
                    try:
                        cache_file.unlink()
                        removed_count += 1
                        logger.debug(f"Removed old cache file: {cache_file.name}")
                    except PermissionError:
                        logger.warning(f"Old cache file {cache_file} is in use and could not be removed")
            except Exception as e:
                logger.error(f"Error removing old cache file {cache_file.name}: {e}")
    except Exception as e:
        logger.error(f"Error cleaning old caches: {e}")
    
    if removed_count > 0:
        logger.info(f"Removed {removed_count} old cache files")
    
    return removed_count


# ===== MEMORY CACHE UTILITIES =====

class MemoryCache:
    """
    Simple in-memory cache with expiration.
    """
    
    def __init__(self, default_ttl: int = DEFAULT_CACHE_DURATION):
        self.data: Dict[str, Tuple[Any, float]] = {}
        self.default_ttl = default_ttl
    
    def get(self, key: str, default: Any = None) -> Any:
        """
        Get value from cache.
        """
        if key in self.data:
            value, expires_at = self.data[key]
            if time.time() < expires_at:
                return value
            else:
                del self.data[key]
        return default
    
    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        """
        Set value in cache with TTL.
        """
        if ttl is None:
            ttl = self.default_ttl
        
        expires_at = time.time() + ttl
        self.data[key] = (value, expires_at)
    
    def delete(self, key: str) -> bool:
        """
        Delete key from cache.
        """
        if key in self.data:
            del self.data[key]
            return True
        return False
    
    def clear(self) -> None:
        """
        Clear all cache entries.
        """
        self.data.clear()
    
    def cleanup_expired(self) -> int:
        """
        Remove expired entries.
        """
        current_time = time.time()
        expired_keys = [
            key for key, (value, expires_at) in self.data.items()
            if current_time >= expires_at
        ]
        
        for key in expired_keys:
            del self.data[key]
        
        return len(expired_keys)
    
    def size(self) -> int:
        """
        Get number of cached entries.
        """
        return len(self.data)