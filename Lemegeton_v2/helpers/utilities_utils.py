"""
Utilities Utilities
Unified error handling for utility cogs (help, notifications, timestamp, invite, say, userinfo, convertlinks)
"""

import logging
import functools
from pathlib import Path

import discord

# Logging setup
LOG_DIR = Path("logs")
LOG_FILE = LOG_DIR / "utilities.log"
LOG_DIR.mkdir(exist_ok=True)

logger = logging.getLogger("Utilities")
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

logger.info("Utilities utilities initialized")


# ===== ERROR HANDLING =====

class UtilitiesError(Exception):
    """Base exception for utility cogs"""
    pass


class UtilitiesAPIError(UtilitiesError):
    """External API specific errors (AniList, etc.)"""
    pass


class UtilitiesNotFoundError(UtilitiesError):
    """Requested data not found"""
    pass


class RateLimitError(UtilitiesError):
    """Rate limit exceeded"""
    pass


def utilities_error_handler(func):
    """
    Decorator for unified error handling in utility commands.

    Note: this section's helpers (anilist_helper.py, etc.) never raise these typed
    exceptions themselves — on failure they log internally and return None/empty
    results instead. The typed branches below exist so a cog can optionally
    `raise UtilitiesNotFoundError(...)` etc. after checking a helper's return value,
    for a nicer user-facing message than the generic fallback. Today, no cog does
    this, so the practical effect of wiring this decorator on is the same safety
    net `social_error_handler`/`account_error_handler`/`server_management_error_handler`
    provide: expired-interaction handling and a consistent unexpected-error message.
    """
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

        except UtilitiesNotFoundError as e:
            logger.warning(f"Data not found: {e}")
            if interaction:
                try:
                    await interaction.followup.send(
                        f"❌ **Not Found**\n\n{str(e)}",
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

        except UtilitiesAPIError as e:
            logger.error(f"API error: {e}")
            if interaction:
                try:
                    await interaction.followup.send(
                        f"❌ **API Error**\n\n{str(e)}\n\n"
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
