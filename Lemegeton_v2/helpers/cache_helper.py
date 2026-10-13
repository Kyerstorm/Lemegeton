"""
Cache Management Helper Functions
Centralized caching system for API responses, recommendations, and other data
"""

import json
import logging
import os
import time
from pathlib import Path
from typing import Any, Dict, Optional, Set, Tuple, Union

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


# ===== POPULAR TITLES CACHE =====


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


# ===== MEMORY CACHE UTILITIES =====
