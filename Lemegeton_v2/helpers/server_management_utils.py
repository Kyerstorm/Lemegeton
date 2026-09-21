"""
Server Management Utilities
Unified error handling for server management (invites/config/welcome) cogs
"""

import logging
import functools
from pathlib import Path

import discord

# Logging setup
LOG_DIR = Path("logs")
LOG_FILE = LOG_DIR / "server_management.log"
LOG_DIR.mkdir(exist_ok=True)

logger = logging.getLogger("ServerManagement")
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

logger.info("Server management utilities initialized")


# ===== ERROR HANDLING =====

class ServerManagementError(Exception):
    """Base exception for server management cogs"""
    pass


class ServerManagementAPIError(ServerManagementError):
    """Discord API specific errors"""
    pass


class ServerManagementNotFoundError(ServerManagementError):
    """Requested guild data or configuration not found"""
    pass


class RateLimitError(ServerManagementError):
    """Upstream API rate limit exceeded"""
    pass


def server_management_error_handler(func):
    """
    Decorator for unified error handling in server management commands.

    Note: this section has no upstream API helper layer (unlike
    anilist_helper.py/steam_helper.py) that could raise these typed
    exceptions itself. The typed branches below exist so a cog can
    optionally `raise ServerManagementNotFoundError(...)` etc. for a nicer
    user-facing message than the generic fallback. Today, no cog does this,
    so the practical effect of wiring this decorator on is the same safety
    net `media_error_handler`/`social_error_handler`/`account_error_handler`
    provide: expired-interaction handling and a consistent unexpected-error
    message.
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

        except ServerManagementNotFoundError as e:
            logger.warning(f"Server management data not found: {e}")
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
                        "Too many requests to the upstream API. Please try again in a few minutes.",
                        ephemeral=True
                    )
                except discord.NotFound:
                    logger.error("Interaction expired while sending rate limit error")

        except ServerManagementAPIError as e:
            logger.error(f"Server management API error: {e}")
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
