"""
Lemegeton Discord Bot - Configuration Module

This module loads and manages all configuration from environment variables.
All settings are loaded from the .env file using python-dotenv.

Configuration is organized into logical sections for maintainability.
"""

import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# ==============================================================================
# UTILITY FUNCTIONS
# ==============================================================================

def _int_env(key, default=None):
    """
    Safely parse integer environment variables.

    Args:
        key: Environment variable name
        default: Default value if parsing fails or variable is empty

    Returns:
        Parsed integer or default value
    """
    val = os.getenv(key)
    if val is None or val == "":
        return default
    try:
        return int(val)
    except ValueError:
        return default


def _float_env(key, default=None):
    """
    Safely parse float environment variables.

    Args:
        key: Environment variable name
        default: Default value if parsing fails or variable is empty

    Returns:
        Parsed float or default value
    """
    val = os.getenv(key)
    if val is None or val == "":
        return default
    try:
        return float(val)
    except ValueError:
        return default


# ==============================================================================
# CORE DISCORD CONFIGURATION
# ==============================================================================

# Authentication
TOKEN = os.getenv("DISCORD_TOKEN")

# Bot Identifiers (parsed as integers)
BOT_ID = _int_env("BOT_ID")
GUILD_ID = _int_env("GUILD_ID")
CHANNEL_ID = _int_env("CHANNEL_ID")
ADMIN_DISCORD_ID = _int_env("ADMIN_DISCORD_ID")

# Primary Guild ID for backwards compatibility
PRIMARY_GUILD_ID = GUILD_ID

# Role IDs
MOD_ROLE_ID = _int_env("MOD_ROLE_ID")  # DEPRECATED: Use per-guild mod role system
BOT_UPDATE_ROLE_ID = _int_env("BOT_UPDATE_ROLE_ID")

# Optional All Star Challenge Role IDs
ALL_STAR_STAGE1_ROLE_ID = _int_env("ALL_STAR_STAGE1_ROLE_ID")
ALL_STAR_STAGE2_ROLE_ID = _int_env("ALL_STAR_STAGE2_ROLE_ID")
ALL_STAR_COMPLETED_ROLE_ID = _int_env("ALL_STAR_COMPLETED_ROLE_ID")

# ==============================================================================
# BOT MONITORING & NOTIFICATIONS
# ==============================================================================

# Webhook URLs for notifications
DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL")
AURA_WEBHOOK_URL = os.getenv("AURA_WEBHOOK_URL")

# ==============================================================================
# BOT BEHAVIOR CONFIGURATION
# ==============================================================================

# Logging Configuration
LOG_MAX_SIZE = _int_env("LOG_MAX_SIZE", 52428800)  # 50MB default

# Status Update Intervals (seconds)
STATUS_UPDATE_INTERVAL = _int_env("STATUS_UPDATE_INTERVAL", 3600)  # 1 hour
TRENDING_REFRESH_INTERVAL = _int_env("TRENDING_REFRESH_INTERVAL", 10800)  # 3 hours

# Cog Development (seconds)
COG_WATCH_INTERVAL_PROD = _int_env("COG_WATCH_INTERVAL_PROD", 10)  # Production: 10s
COG_WATCH_INTERVAL_DEV = _int_env("COG_WATCH_INTERVAL_DEV", 2)  # Development: 2s

# Cleanup Tasks (seconds)
USER_CLEANUP_INTERVAL = _int_env("USER_CLEANUP_INTERVAL", 21600)  # 6 hours

# ==============================================================================
# ANILIST API CONFIGURATION
# ==============================================================================

ANILIST_API_URL = os.getenv("ANILIST_API_URL", "https://graphql.anilist.co")
ANILIST_API_TIMEOUT = _int_env("ANILIST_API_TIMEOUT", 10)  # 10 seconds

# Fallback anime titles when API is unavailable (comma-separated in .env)
DEFAULT_TRENDING_FALLBACK = os.getenv("DEFAULT_TRENDING_FALLBACK", "AniList API ❤️").split(",")

# ==============================================================================
# GAMING INTEGRATIONS
# ==============================================================================

# Steam API
STEAM_API_KEY = os.getenv("STEAM_API_KEY")

# IGDB (Twitch) API for game cover lookups
IGDB_CLIENT_ID = os.getenv("IGDB_CLIENT_ID")
IGDB_CLIENT_SECRET = os.getenv("IGDB_CLIENT_SECRET")

# Twitch Streaming
TWITCH_STREAMING_URL = os.getenv("TWITCH_STREAMING_URL", "https://www.twitch.tv/owobotplays")

# ==============================================================================
# AI/LLM CONFIGURATION
# ==============================================================================

# OpenAI
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# OpenRouter (primary AI provider)
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")

# Google Gemini
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# Ollama (local AI)
OLLAMA_HOST = os.getenv("OLLAMA_HOST")
if OLLAMA_HOST == "":
    OLLAMA_HOST = None

# ==============================================================================
# API RESILIENCE CONFIGURATION
# ==============================================================================

API_MAX_RETRIES = _int_env("API_MAX_RETRIES", 3)  # 3 retries default
API_RETRY_BASE_DELAY = _float_env("API_RETRY_BASE_DELAY", 1.0)  # 1.0 seconds default

# ==============================================================================
# DATABASE CONFIGURATION
# ==============================================================================

# Database path (Railway compatible)
DB_PATH = os.getenv("DATABASE_PATH", os.path.join(os.path.dirname(__file__), "data", "database.db"))

# Connection pool size (framework for future implementation)
DB_CONNECTION_POOL_SIZE = _int_env("DB_CONNECTION_POOL_SIZE", 5)

# ==============================================================================
# LEGACY CHALLENGE ROLE IDS (Backwards Compatibility)
# ==============================================================================
# These are hardcoded role IDs for the primary guild's challenges.
# In multi-guild setup, these are automatically migrated to the database.

CHALLENGE_ROLE_IDS = {
    # challenge_id: {threshold: role_id}
    1: {1.0: 1093985707091046593},
    2: {1.0: 1010651450239627417},
    3: {1.0: 1020028721010319360},
    4: {1.0: 1033338002820313121},
    5: {1.0: 1075042063596392469},
    6: {1.0: 1163794823657037874},
    7: {1.0: 1075042050455650385},
    8: {1.0: 1180150004279693392},
    9: {1.0: 1004793487432106064},
    10: {1.0: 1413986509631131708},
    11: {1.0: 1414696905317023754},
    12: {1.0: 1414697102474219611},
    13: {1.0: 1414286327507321074},
}

# ==============================================================================
# CONFIGURATION VALIDATION
# ==============================================================================

def validate_required_config():
    """
    Validate that all required configuration variables are present.

    Returns:
        tuple: (is_valid: bool, missing_vars: list)
    """
    required_vars = {
        'DISCORD_TOKEN': TOKEN,
        'BOT_ID': BOT_ID,
        'GUILD_ID': GUILD_ID,
    }

    missing = [key for key, value in required_vars.items() if not value]
    return (len(missing) == 0, missing)


def get_config_summary():
    """
    Get a summary of loaded configuration (safe for logging).

    Returns:
        dict: Configuration summary with sensitive values masked
    """
    return {
        'bot_id': BOT_ID,
        'guild_id': GUILD_ID,
        'has_token': bool(TOKEN),
        'has_webhook': bool(DISCORD_WEBHOOK_URL),
        'has_steam_api': bool(STEAM_API_KEY),
        'has_openai': bool(OPENAI_API_KEY),
        'has_openrouter': bool(OPENROUTER_API_KEY),
        'db_path': DB_PATH,
        'environment': os.getenv('ENVIRONMENT', 'development'),
    }


# ==============================================================================
# EXPORTS (for backwards compatibility with older import patterns)
# ==============================================================================

__all__ = [
    # Core
    'TOKEN', 'BOT_ID', 'GUILD_ID', 'CHANNEL_ID', 'ADMIN_DISCORD_ID',
    'PRIMARY_GUILD_ID', 'MOD_ROLE_ID', 'BOT_UPDATE_ROLE_ID',

    # Monitoring
    'DISCORD_WEBHOOK_URL', 'AURA_WEBHOOK_URL',

    # Behavior
    'LOG_MAX_SIZE', 'STATUS_UPDATE_INTERVAL', 'TRENDING_REFRESH_INTERVAL',
    'COG_WATCH_INTERVAL_PROD', 'COG_WATCH_INTERVAL_DEV', 'USER_CLEANUP_INTERVAL',

    # AniList
    'ANILIST_API_URL', 'ANILIST_API_TIMEOUT', 'DEFAULT_TRENDING_FALLBACK',

    # Gaming
    'STEAM_API_KEY', 'IGDB_CLIENT_ID', 'IGDB_CLIENT_SECRET', 'TWITCH_STREAMING_URL',

    # AI/LLM
    'OPENAI_API_KEY', 'OPENROUTER_API_KEY', 'GEMINI_API_KEY', 'OLLAMA_HOST',

    # API Resilience
    'API_MAX_RETRIES', 'API_RETRY_BASE_DELAY',

    # Database
    'DB_PATH', 'DB_CONNECTION_POOL_SIZE',

    # Legacy
    'CHALLENGE_ROLE_IDS', 'ALL_STAR_STAGE1_ROLE_ID', 'ALL_STAR_STAGE2_ROLE_ID',
    'ALL_STAR_COMPLETED_ROLE_ID',

    # Utilities
    'validate_required_config', 'get_config_summary',
]
