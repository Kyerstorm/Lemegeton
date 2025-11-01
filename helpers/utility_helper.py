"""
Utility Helper Functions
Common utility functions used across multiple cogs and components
"""

import asyncio
import json
import logging
import os
import pickle
import random
import aiosqlite
import string
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Union, Tuple

import aiohttp
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

async def make_http_request(
    url: str,
    method: str = "GET",
    headers: Optional[Dict[str, str]] = None,
    data: Optional[Dict[str, Any]] = None,
    json_data: Optional[Dict[str, Any]] = None,
    timeout: int = REQUEST_TIMEOUT,
    retries: int = MAX_RETRIES
) -> Optional[Dict[str, Any]]:
    """
    Make HTTP request with retry logic and error handling.
    """
    if headers is None:
        headers = {}
    
    for attempt in range(retries + 1):
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=timeout)) as session:
                if method.upper() == "GET":
                    async with session.get(url, headers=headers, params=data) as response:
                        if response.status == 200:
                            return await response.json()
                        else:
                            logger.warning(f"HTTP {response.status} for {url} (attempt {attempt + 1})")
                
                elif method.upper() == "POST":
                    kwargs = {"headers": headers}
                    if json_data:
                        kwargs["json"] = json_data
                    elif data:
                        kwargs["data"] = data
                    
                    async with session.post(url, **kwargs) as response:
                        if response.status == 200:
                            return await response.json()
                        else:
                            logger.warning(f"HTTP {response.status} for {url} (attempt {attempt + 1})")
        
        except asyncio.TimeoutError:
            logger.warning(f"Timeout for {url} (attempt {attempt + 1})")
        except aiohttp.ClientError as e:
            logger.warning(f"Client error for {url}: {e} (attempt {attempt + 1})")
        except Exception as e:
            logger.error(f"Unexpected error for {url}: {e} (attempt {attempt + 1})")
        
        if attempt < retries:
            await asyncio.sleep(2 ** attempt)  # Exponential backoff
    
    logger.error(f"Failed to make request to {url} after {retries + 1} attempts")
    return None


async def download_image(url: str, max_size: int = 8 * 1024 * 1024) -> Optional[bytes]:
    """
    Download image from URL with size validation.
    """
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                if response.status != 200:
                    return None
                
                # Check content type
                content_type = response.headers.get('content-type', '')
                if not content_type.startswith('image/'):
                    return None
                
                # Check content length
                content_length = response.headers.get('content-length')
                if content_length and int(content_length) > max_size:
                    return None
                
                # Read data with size limit
                data = await response.read()
                if len(data) > max_size:
                    return None
                
                return data
    
    except Exception as e:
        logger.error(f"Error downloading image from {url}: {e}")
        return None


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


def is_cache_valid(cache_name: str, max_age_seconds: int = 3600) -> bool:
    """
    Check if cache file exists and is within max age.
    """
    cache_file = get_cache_file_path(cache_name)
    if not cache_file.exists():
        return False
    
    try:
        cache_age = datetime.now().timestamp() - cache_file.stat().st_mtime
        return cache_age < max_age_seconds
    except Exception:
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

def execute_db_query(
    db_path: str,
    query: str,
    params: Optional[Tuple] = None,
    fetch_one: bool = False,
    fetch_all: bool = False
) -> Any:
    """
    Execute database query with proper error handling.
    """
    try:
        with aiosqlite.connect(db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            if params:
                cursor.execute(query, params)
            else:
                cursor.execute(query)
            
            if fetch_one:
                return cursor.fetchone()
            elif fetch_all:
                return cursor.fetchall()
            else:
                conn.commit()
                return cursor.rowcount
    
    except sqlite3.Error as e:
        logger.error(f"Database error: {e}")
        return None


def backup_database(db_path: str, backup_dir: str = "backups") -> Optional[str]:
    """
    Create database backup with timestamp.
    """
    try:
        backup_path = Path(backup_dir)
        backup_path.mkdir(exist_ok=True)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        db_name = Path(db_path).stem
        backup_file = backup_path / f"{db_name}_backup_{timestamp}.db"
        
        # Copy database file
        import shutil
        shutil.copy2(db_path, backup_file)
        
        logger.info(f"Database backed up to {backup_file}")
        return str(backup_file)
    
    except Exception as e:
        logger.error(f"Error creating database backup: {e}")
        return None


# ===== DISCORD UTILITIES =====

def get_user_display_name(user: Union[discord.User, discord.Member]) -> str:
    """
    Get appropriate display name for user.
    """
    if isinstance(user, discord.Member) and user.nick:
        return user.nick
    return user.display_name


def format_user_mention(user_id: int) -> str:
    """
    Format user ID as Discord mention.
    """
    return f"<@{user_id}>"


def format_channel_mention(channel_id: int) -> str:
    """
    Format channel ID as Discord mention.
    """
    return f"<#{channel_id}>"


def format_role_mention(role_id: int) -> str:
    """
    Format role ID as Discord mention.
    """
    return f"<@&{role_id}>"


def safe_send_message(
    messageable: discord.abc.Messageable,
    content: str = None,
    embed: discord.Embed = None,
    file: discord.File = None,
    view: discord.ui.View = None
) -> bool:
    """
    Safely send message with error handling.
    Returns True if successful, False otherwise.
    """
    try:
        # Ensure content doesn't exceed Discord limits
        if content and len(content) > 2000:
            content = content[:1997] + "..."
        
        # Validate embed
        if embed and len(embed) > 6000:
            embed.description = embed.description[:1997] + "..." if embed.description else None
        
        return True  # This is a helper - actual sending should be done by caller
    except Exception as e:
        logger.error(f"Error preparing message: {e}")
        return False


def get_emoji_url(emoji_id: int, animated: bool = False) -> str:
    """
    Generate Discord emoji URL from ID.
    """
    extension = "gif" if animated else "png"
    return f"https://cdn.discordapp.com/emojis/{emoji_id}.{extension}"


# ===== FILE UTILITIES =====

def ensure_directory(path: Union[str, Path]) -> bool:
    """
    Ensure directory exists, create if necessary.
    """
    try:
        Path(path).mkdir(parents=True, exist_ok=True)
        return True
    except Exception as e:
        logger.error(f"Error creating directory {path}: {e}")
        return False


def safe_read_file(file_path: Union[str, Path], encoding: str = 'utf-8') -> Optional[str]:
    """
    Safely read file contents.
    """
    try:
        with open(file_path, 'r', encoding=encoding) as f:
            return f.read()
    except Exception as e:
        logger.error(f"Error reading file {file_path}: {e}")
        return None


def safe_write_file(
    file_path: Union[str, Path],
    content: str,
    encoding: str = 'utf-8',
    create_dirs: bool = True
) -> bool:
    """
    Safely write content to file.
    """
    try:
        file_path = Path(file_path)
        if create_dirs:
            file_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(file_path, 'w', encoding=encoding) as f:
            f.write(content)
        return True
    except Exception as e:
        logger.error(f"Error writing file {file_path}: {e}")
        return False


def get_file_size(file_path: Union[str, Path]) -> int:
    """
    Get file size in bytes.
    """
    try:
        return Path(file_path).stat().st_size
    except Exception:
        return 0


def clean_old_files(directory: Union[str, Path], max_age_days: int = 7) -> int:
    """
    Clean files older than specified days.
    Returns number of files deleted.
    """
    try:
        directory = Path(directory)
        if not directory.exists():
            return 0
        
        now = datetime.now().timestamp()
        max_age_seconds = max_age_days * 24 * 3600
        deleted_count = 0
        
        for file_path in directory.iterdir():
            if file_path.is_file():
                file_age = now - file_path.stat().st_mtime
                if file_age > max_age_seconds:
                    try:
                        file_path.unlink()
                        deleted_count += 1
                    except PermissionError:
                        logger.warning(f"Old file {file_path} is in use and could not be removed")
        
        return deleted_count
    except Exception as e:
        logger.error(f"Error cleaning old files: {e}")
        return 0


# ===== RANDOM UTILITIES =====

def generate_random_string(length: int = 8, include_numbers: bool = True) -> str:
    """
    Generate random string for IDs, tokens, etc.
    """
    chars = string.ascii_letters
    if include_numbers:
        chars += string.digits
    
    return ''.join(random.choice(chars) for _ in range(length))


def get_random_choice(items: List[Any], exclude: List[Any] = None) -> Any:
    """
    Get random choice from list with optional exclusions.
    """
    if exclude:
        items = [item for item in items if item not in exclude]
    
    return random.choice(items) if items else None


def shuffle_list(items: List[Any]) -> List[Any]:
    """
    Return shuffled copy of list.
    """
    shuffled = items.copy()
    random.shuffle(shuffled)
    return shuffled


# ===== VALIDATION UTILITIES =====

def is_valid_json(json_string: str) -> bool:
    """
    Check if string is valid JSON.
    """
    try:
        json.loads(json_string)
        return True
    except (json.JSONDecodeError, TypeError):
        return False


def is_valid_url(url: str) -> bool:
    """
    Basic URL validation.
    """
    if not url or not isinstance(url, str):
        return False
    
    return url.startswith(('http://', 'https://')) and '.' in url


def sanitize_filename(filename: str) -> str:
    """
    Sanitize filename for safe file system usage.
    """
    # Remove/replace invalid characters
    invalid_chars = '<>:"/\\|?*'
    for char in invalid_chars:
        filename = filename.replace(char, '_')
    
    # Remove leading/trailing dots and spaces
    filename = filename.strip('. ')
    
    # Limit length
    if len(filename) > 255:
        name, ext = os.path.splitext(filename)
        max_name_length = 255 - len(ext)
        filename = name[:max_name_length] + ext
    
    return filename or "untitled"


# ===== FORMATTING UTILITIES =====

def format_bytes(bytes_value: int) -> str:
    """
    Format bytes into human-readable string.
    """
    for unit in ['B', 'KB', 'MB', 'GB']:
        if bytes_value < 1024:
            return f"{bytes_value:.1f} {unit}"
        bytes_value /= 1024
    return f"{bytes_value:.1f} TB"


def format_list(items: List[str], conjunction: str = "and") -> str:
    """
    Format list into grammatically correct string.
    """
    if not items:
        return ""
    elif len(items) == 1:
        return items[0]
    elif len(items) == 2:
        return f"{items[0]} {conjunction} {items[1]}"
    else:
        return f"{', '.join(items[:-1])}, {conjunction} {items[-1]}"


def ordinal(n: int) -> str:
    """
    Convert number to ordinal (1st, 2nd, 3rd, etc.).
    """
    suffix = ['th', 'st', 'nd', 'rd', 'th'][min(n % 10, 4)]
    if 11 <= (n % 100) <= 13:
        suffix = 'th'
    return f"{n}{suffix}"


# ===== ASYNC UTILITIES =====

async def gather_with_limit(tasks: List, limit: int = 10):
    """
    Execute tasks with concurrency limit.
    """
    semaphore = asyncio.Semaphore(limit)
    
    async def limited_task(task):
        async with semaphore:
            return await task
    
    return await asyncio.gather(*[limited_task(task) for task in tasks])


async def retry_async(
    func,
    *args,
    max_retries: int = 3,
    delay: float = 1.0,
    backoff: float = 2.0,
    **kwargs
):
    """
    Retry async function with exponential backoff.
    """
    last_exception = None
    
    for attempt in range(max_retries + 1):
        try:
            return await func(*args, **kwargs)
        except Exception as e:
            last_exception = e
            if attempt < max_retries:
                await asyncio.sleep(delay * (backoff ** attempt))
            else:
                logger.error(f"Failed after {max_retries + 1} attempts: {e}")
    
    raise last_exception


# ===== ENVIRONMENT UTILITIES =====

def get_env_var(name: str, default: Any = None, required: bool = False) -> Any:
    """
    Get environment variable with optional default and validation.
    """
    value = os.getenv(name, default)
    if required and value is None:
        raise ValueError(f"Required environment variable {name} not set")
    return value


def get_env_bool(name: str, default: bool = False) -> bool:
    """
    Get boolean environment variable.
    """
    value = os.getenv(name, str(default)).lower()
    return value in ('true', '1', 'yes', 'on')


def get_env_int(name: str, default: int = 0) -> int:
    """
    Get integer environment variable.
    """
    try:
        return int(os.getenv(name, default))
    except (ValueError, TypeError):
        return default