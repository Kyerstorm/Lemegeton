"""
Text Processing Helper Functions
Centralized functions for text processing, validation, and formatting
"""

import re
import logging
from typing import Optional, List, Dict, Any
from datetime import datetime, timezone, timedelta
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

def parse_time_string(time_str: str, date_str: Optional[str] = None) -> Optional[datetime]:
    """
    Parse various time string formats into datetime objects.
    Supports formats like:
    - "2:30 PM", "14:30", "2:30"
    - "in 5 minutes", "in 2 hours"
    - "tomorrow at 3 PM"
    """
    if not time_str:
        return None
        
    time_str = time_str.strip().lower()
    now = datetime.now(timezone.utc)
    
    # Handle relative times
    if "in " in time_str:
        try:
            # Extract number and unit
            match = re.search(r'in (\d+)\s*(minute|hour|day|week)s?', time_str)
            if match:
                amount = int(match.group(1))
                unit = match.group(2)
                
                if unit == "minute":
                    return now + timedelta(minutes=amount)
                elif unit == "hour":
                    return now + timedelta(hours=amount)
                elif unit == "day":
                    return now + timedelta(days=amount)
                elif unit == "week":
                    return now + timedelta(weeks=amount)
        except Exception:
            pass
    
    # Handle absolute times
    time_formats = [
        "%I:%M %p",  # 2:30 PM
        "%H:%M",     # 14:30
        "%I %p",     # 2 PM
        "%H",        # 14
    ]
    
    for fmt in time_formats:
        try:
            parsed_time = datetime.strptime(time_str, fmt).time()
            if date_str:
                try:
                    parsed_date = datetime.strptime(date_str, "%Y-%m-%d").date()
                    return datetime.combine(parsed_date, parsed_time, timezone.utc)
                except Exception:
                    pass
            # Use today's date
            return datetime.combine(now.date(), parsed_time, timezone.utc)
        except ValueError:
            continue
    
    logger.warning(f"Could not parse time string: {time_str}")
    return None


def format_duration(seconds: int) -> str:
    """
    Format duration in seconds to human-readable string.
    """
    if seconds < 60:
        return f"{seconds}s"
    elif seconds < 3600:
        minutes = seconds // 60
        secs = seconds % 60
        if secs == 0:
            return f"{minutes}m"
        return f"{minutes}m {secs}s"
    elif seconds < 86400:
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        if minutes == 0:
            return f"{hours}h"
        return f"{hours}h {minutes}m"
    else:
        days = seconds // 86400
        hours = (seconds % 86400) // 3600
        if hours == 0:
            return f"{days}d"
        return f"{days}d {hours}h"


def format_timestamp(dt: datetime, format_type: str = "relative") -> str:
    """
    Format datetime to Discord timestamp or human-readable string.
    """
    if format_type == "discord":
        # Discord timestamp format
        timestamp = int(dt.timestamp())
        return f"<t:{timestamp}:F>"
    elif format_type == "relative":
        # Relative time (e.g., "2 hours ago")
        now = datetime.now(timezone.utc)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        
        diff = now - dt
        total_seconds = int(diff.total_seconds())
        
        if total_seconds < 60:
            return "just now"
        elif total_seconds < 3600:
            minutes = total_seconds // 60
            return f"{minutes} minute{'s' if minutes != 1 else ''} ago"
        elif total_seconds < 86400:
            hours = total_seconds // 3600
            return f"{hours} hour{'s' if hours != 1 else ''} ago"
        else:
            days = total_seconds // 86400
            return f"{days} day{'s' if days != 1 else ''} ago"
    else:
        # Standard format
        return dt.strftime("%Y-%m-%d %H:%M:%S UTC")


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

def clean_html(text: str) -> str:
    """
    Remove HTML tags and entities from text.
    """
    if not text:
        return ""
    
    # Remove HTML tags
    text = re.sub(r'<[^>]+>', '', text)
    
    # Replace common HTML entities
    html_entities = {
        '&amp;': '&',
        '&lt;': '<',
        '&gt;': '>',
        '&quot;': '"',
        '&#39;': "'",
        '&nbsp;': ' ',
        '&copy;': '©',
        '&reg;': '®',
        '&trade;': '™'
    }
    
    for entity, replacement in html_entities.items():
        text = text.replace(entity, replacement)
    
    return text.strip()


def clean_markdown(text: str) -> str:
    """
    Remove or convert Markdown formatting.
    """
    if not text:
        return ""
    
    # Remove markdown links but keep text
    text = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', text)
    
    # Remove bold/italic markers
    text = re.sub(r'\*{1,3}([^*]+)\*{1,3}', r'\1', text)
    text = re.sub(r'_{1,3}([^_]+)_{1,3}', r'\1', text)
    
    # Remove strikethrough
    text = re.sub(r'~~([^~]+)~~', r'\1', text)
    
    # Remove headers
    text = re.sub(r'^#{1,6}\s*(.+)$', r'\1', text, flags=re.MULTILINE)
    
    # Remove code blocks
    text = re.sub(r'```[^`]*```', '', text)
    text = re.sub(r'`([^`]+)`', r'\1', text)
    
    return text.strip()


def truncate_text(text: str, max_length: int, suffix: str = "...") -> str:
    """
    Truncate text to specified length, adding suffix if truncated.
    """
    if not text or len(text) <= max_length:
        return text
    
    # Try to truncate at word boundary
    if max_length > len(suffix):
        truncate_at = max_length - len(suffix)
        # Find last space before truncate point
        space_index = text.rfind(' ', 0, truncate_at)
        if space_index > max_length // 2:  # Only use if not too far back
            return text[:space_index] + suffix
    
    # Fallback to hard truncation
    return text[:max_length - len(suffix)] + suffix


def extract_urls(text: str) -> List[str]:
    """
    Extract URLs from text.
    """
    if not text:
        return []
    
    url_pattern = r'https?://[^\s<>"\']+|www\.[^\s<>"\']+\.[^\s<>"\']+'
    urls = re.findall(url_pattern, text, re.IGNORECASE)
    
    # Normalize URLs (add http:// to www. URLs)
    normalized_urls = []
    for url in urls:
        if url.startswith('www.'):
            url = 'http://' + url
        normalized_urls.append(url)
    
    return normalized_urls


def extract_mentions(text: str) -> Dict[str, List[str]]:
    """
    Extract Discord mentions from text.
    Returns dict with 'users', 'roles', and 'channels' lists.
    """
    if not text:
        return {"users": [], "roles": [], "channels": []}
    
    users = re.findall(r'<@!?(\d+)>', text)
    roles = re.findall(r'<@&(\d+)>', text)
    channels = re.findall(r'<#(\d+)>', text)
    
    return {
        "users": users,
        "roles": roles,
        "channels": channels
    }


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


def validate_url(url: str) -> bool:
    """
    Validate URL format.
    """
    if not url:
        return False
    
    url_pattern = r'^https?://[^\s<>"\']+\.[^\s<>"\']+'
    return bool(re.match(url_pattern, url))


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

def normalize_title(title: str) -> str:
    """
    Normalize title for comparison/searching.
    """
    if not title:
        return ""
    
    # Convert to lowercase
    title = title.lower()
    
    # Remove articles
    title = re.sub(r'^(the|a|an)\s+', '', title)
    
    # Remove punctuation and special characters
    title = re.sub(r'[^\w\s]', '', title)
    
    # Normalize whitespace
    title = re.sub(r'\s+', ' ', title).strip()
    
    return title


def similarity_ratio(str1: str, str2: str) -> float:
    """
    Calculate similarity ratio between two strings using simple algorithm.
    Returns value between 0.0 and 1.0.
    """
    if not str1 or not str2:
        return 0.0
    
    str1 = normalize_title(str1)
    str2 = normalize_title(str2)
    
    if str1 == str2:
        return 1.0
    
    # Simple Levenshtein-like ratio
    longer = str1 if len(str1) > len(str2) else str2
    shorter = str2 if len(str1) > len(str2) else str1
    
    if len(longer) == 0:
        return 1.0
    
    # Count matching characters
    matches = 0
    for char in shorter:
        if char in longer:
            matches += 1
    
    return matches / len(longer)


def parse_options_string(options: str) -> Dict[str, str]:
    """
    Parse command options string into dictionary.
    Example: "pages=3 concurrency=40 retries=5" -> {"pages": "3", "concurrency": "40", "retries": "5"}
    """
    opts = {}
    if not options:
        return opts
    
    for token in options.split():
        if "=" in token:
            k, v = token.split("=", 1)
            opts[k.lower()] = v
        else:
            # Allow bare tokens
            opts[token.lower()] = "true"
    
    return opts


def format_number(num: Any, format_type: str = "comma") -> str:
    """
    Format numbers for display.
    """
    try:
        if isinstance(num, str):
            num = float(num)
        
        if format_type == "comma":
            return f"{num:,}"
        elif format_type == "short":
            if num >= 1_000_000:
                return f"{num/1_000_000:.1f}M"
            elif num >= 1_000:
                return f"{num/1_000:.1f}K"
            else:
                return str(int(num))
        else:
            return str(num)
    except (ValueError, TypeError):
        return str(num)


def format_percentage(value: Any, total: Any) -> str:
    """
    Format percentage from value and total.
    """
    try:
        if isinstance(value, str):
            value = float(value)
        if isinstance(total, str):
            total = float(total)
        
        if total == 0:
            return "0%"
        
        percentage = (value / total) * 100
        return f"{percentage:.1f}%"
    except (ValueError, TypeError, ZeroDivisionError):
        return "N/A"


# ===== CONTENT FILTERING =====

def contains_spoilers(text: str) -> bool:
    """
    Check if text contains spoiler markers.
    """
    if not text:
        return False
    
    spoiler_patterns = [
        r'\|\|[^|]+\|\|',  # Discord spoilers
        r'~![^!]+!~',      # AniList spoilers
        r'\[spoiler\]',    # BBCode style
        r'<spoiler>',      # HTML style
    ]
    
    for pattern in spoiler_patterns:
        if re.search(pattern, text, re.IGNORECASE):
            return True
    
    return False


def remove_spoilers(text: str, replacement: str = "[SPOILER]") -> str:
    """
    Remove spoiler content from text.
    """
    if not text:
        return ""
    
    # Discord spoilers
    text = re.sub(r'\|\|([^|]+)\|\|', replacement, text)
    
    # AniList spoilers
    text = re.sub(r'~!([^!]+)!~', replacement, text)
    
    # BBCode spoilers
    text = re.sub(r'\[spoiler\].*?\[/spoiler\]', replacement, text, flags=re.IGNORECASE | re.DOTALL)
    
    # HTML spoilers
    text = re.sub(r'<spoiler>.*?</spoiler>', replacement, text, flags=re.IGNORECASE | re.DOTALL)
    
    return text