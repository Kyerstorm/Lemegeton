import os
from dotenv import load_dotenv

load_dotenv()


def _int_env(key, default=None):
    val = os.getenv(key)
    if val is None or val == "":
        return default
    try:
        return int(val)
    except ValueError:
        # Keep original string if it can't be parsed, caller can validate
        return default


TOKEN = os.getenv("DISCORD_TOKEN")
# Numeric IDs are parsed defensively to avoid exceptions at import time
GUILD_ID = _int_env("GUILD_ID")
BOT_ID = _int_env("BOT_ID")
CHANNEL_ID = _int_env("CHANNEL_ID")
STEAM_API_KEY = os.getenv("STEAM_API_KEY")
ADMIN_DISCORD_ID = _int_env("ADMIN_DISCORD_ID")

# Moderator role id - DEPRECATED: Use per-guild mod role system via /set_mod_role command instead
# Legacy support: Set MOD_ROLE_ID in your .env as the numeric role id for backward compatibility.
# This will be used as fallback if no guild-specific mod role is configured.
MOD_ROLE_ID = _int_env("MOD_ROLE_ID")

# Bot update notifications role ID (optional - will auto-create per guild if not specified)
BOT_UPDATE_ROLE_ID = _int_env("BOT_UPDATE_ROLE_ID")

# Primary Guild ID for backwards compatibility and default operations
PRIMARY_GUILD_ID = GUILD_ID

# Database path - Railway compatible
DB_PATH = os.getenv("DATABASE_PATH", os.path.join(os.path.dirname(__file__), "data", "database.db"))

# Default Challenge Role IDs for the primary guild (backwards compatibility)
# These will be automatically migrated to the database on first run
CHALLENGE_ROLE_IDS = {
    # challenge_id: {threshold: role_id}
    1: {  # Challenge ID 1
        1.0: 1093985707091046593,
    },
    2: {  # Challenge ID 2
        1.0: 1010651450239627417,
    },
    3: {  # Challenge ID 3
        1.0: 1020028721010319360,
    },
    4: {  # Challenge ID 4
        1.0: 1033338002820313121,
    },
    5: {  # Challenge ID 5
        1.0: 1075042063596392469,
    },
    6: {  # Challenge ID 6
        1.0: 1163794823657037874,
    },
    7: {  # Challenge ID 7
        1.0: 1075042050455650385,
    },
    8: {  # Challenge ID 8
        1.0: 1180150004279693392,
    },
    9: {  # Challenge ID 9
        1.0: 1004793487432106064,
    },
    10: {  # Challenge ID 10
        1.0: 1413986509631131708,
    },
    11: {  # Challenge ID 11
        1.0: 1414696905317023754,
    },
    12: {  # Challenge ID 12
        1.0: 1414697102474219611,
    },
    13: {  # Challenge ID 13
        1.0: 1414286327507321074,
    },
}

# Optional All Star role IDs (useful for mutual-exclusion logic). Set these in your .env as numeric role IDs.
ALL_STAR_STAGE1_ROLE_ID = int(os.getenv("ALL_STAR_STAGE1_ROLE_ID")) if os.getenv("ALL_STAR_STAGE1_ROLE_ID") else None
ALL_STAR_STAGE2_ROLE_ID = int(os.getenv("ALL_STAR_STAGE2_ROLE_ID")) if os.getenv("ALL_STAR_STAGE2_ROLE_ID") else None
ALL_STAR_COMPLETED_ROLE_ID = int(os.getenv("ALL_STAR_COMPLETED_ROLE_ID")) if os.getenv("ALL_STAR_COMPLETED_ROLE_ID") else None


# Chat GPT Configuration
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
OLLAMA_HOST = os.getenv("OLLAMA_HOST")
AURA_WEBHOOK_URL = os.getenv("AURA_WEBHOOK_URL")

# IGDB (Twitch) API credentials for game cover lookups
IGDB_CLIENT_ID = os.getenv("IGDB_CLIENT_ID")
IGDB_CLIENT_SECRET = os.getenv("IGDB_CLIENT_SECRET")

# fallback defaults
if OLLAMA_HOST == "":
    OLLAMA_HOST = None