"""
Text Processing Helper Functions
Centralized functions for text processing, validation, and formatting
"""

import re
import logging
from typing import Optional, Any
from datetime import datetime
from pathlib import Path

# Configuration constants
LOG_DIR = Path("logs")
LOG_FILE = LOG_DIR / "text_helper.log"

# Ensure logs directory exists
LOG_DIR.mkdir(exist_ok=True)

# Set up file-based logging
logger = logging.getLogger("TextHelper")
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

logger.info("Text Helper logging system initialized")


# ===== TIME PARSING FUNCTIONS =====


def format_discord_timestamp(created_at: Any, format_type: str = "R") -> str:
    """
    Format created_at value to Discord timestamp format.
    Handles various input types (str, datetime, int, timestamp).
    
    Args:
        created_at: Timestamp value (str, datetime, int, or timestamp object)
        format_type: Discord timestamp format (default: "R" for relative)
                     Options: "t", "T", "d", "D", "f", "F", "R"
    
    Returns:
        Discord timestamp string (e.g., "<t:1234567890:R>") or fallback string
    """
    from datetime import datetime
    
    try:
        if isinstance(created_at, str):
            # Try parsing common datetime formats
            try:
                dt = datetime.strptime(created_at, "%Y-%m-%d %H:%M:%S")
                timestamp = int(dt.timestamp())
            except ValueError:
                # Try ISO format
                try:
                    dt = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
                    timestamp = int(dt.timestamp())
                except ValueError:
                    return str(created_at)
        elif hasattr(created_at, 'timestamp'):
            # datetime object
            timestamp = int(created_at.timestamp())
        elif isinstance(created_at, (int, float)):
            # Already a timestamp
            timestamp = int(created_at)
        else:
            return str(created_at)
        
        return f"<t:{timestamp}:{format_type}>"
    
    except (ValueError, TypeError, AttributeError):
        return str(created_at)


# ===== TEXT CLEANING FUNCTIONS =====


# ===== VALIDATION FUNCTIONS =====

def validate_discord_id(user_input: str) -> Optional[int]:
    """
    Validate and extract Discord ID from user input.
    Accepts raw ID, mention format, or user#discriminator.
    """
    if not user_input:
        return None
    
    user_input = user_input.strip()
    
    # Direct ID
    if user_input.isdigit() and len(user_input) >= 17:
        return int(user_input)
    
    # Mention format
    mention_match = re.match(r'<@!?(\d+)>', user_input)
    if mention_match:
        return int(mention_match.group(1))
    
    return None


def sanitize_url(url: str) -> Optional[str]:
    """
    Ensure URL is well-formed and safe for Discord embeds.
    Removes whitespace, validates scheme and netloc, and rebuilds safely.
    """
    import urllib.parse
    
    if not url or not isinstance(url, str):
        return None
    
    url = url.strip()  # Remove leading/trailing spaces
    # Encode spaces or illegal characters in query
    url = re.sub(r'\s+', '', url)
    parsed = urllib.parse.urlparse(url)
    
    if not parsed.scheme or not parsed.netloc:
        return None
    
    # Rebuild a safe URL
    return urllib.parse.urlunparse(parsed)


def validate_anilist_username(username: str, max_length: int = 50) -> bool:
    """
    Validate AniList username format.
    Supports both strict (alphanumeric + underscore, max 20) and relaxed (alphanumeric + underscore + hyphen, max 50) formats.
    """
    if not username:
        return False
    
    # Length validation
    if len(username) < 1 or len(username) > max_length:
        return False
    
    # Pattern validation: allow alphanumeric, underscore, and hyphen
    return bool(re.match(r'^[\w-]+$', username))


# ===== STRING PROCESSING FUNCTIONS =====


# ===== CONTENT FILTERING =====

