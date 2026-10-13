"""
Error Utilities
Unified error handling for account, media, social, server management and utility cogs
"""

import logging
import functools
from pathlib import Path

import discord

LOG_DIR = Path("logs")
LOG_DIR.mkdir(exist_ok=True)


# ===== ERROR HANDLING =====

class CogError(Exception):
    """Base exception for cog commands"""
    pass


class CogAPIError(CogError):
    """Upstream API specific errors (AniList, Steam, Discord)"""
    pass


class CogNotFoundError(CogError):
    """Requested data not found"""
    pass


class RateLimitError(CogError):
    """Upstream API rate limit exceeded"""
    pass


def _setup_section_logger(logger_name: str, log_file: str) -> logging.Logger:
    """Create the file logger for one cog section."""
    logger = logging.getLogger(logger_name)
    logger.setLevel(logging.DEBUG)
    logger.handlers.clear()

    file_handler = logging.FileHandler(LOG_DIR / log_file, mode='a', encoding='utf-8')
    file_handler.setLevel(logging.DEBUG)

    formatter = logging.Formatter(
        fmt="[%(asctime)s] [%(levelname)-8s] [%(name)s] %(funcName)s:%(lineno)d - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    return logger


def make_error_handler(
    logger_name: str,
    log_file: str,
    not_found_label: str,
    api_label: str = "API",
    api_title: str = "API Error",
    rate_limit_target: str = " to the upstream API",
):
    """
    Build the error-handling decorator for one cog section.

    Note: `anilist_helper.py` and `steam_helper.py` never raise the typed
    exceptions above themselves — on failure they log internally and return
    None/empty results instead. The typed branches exist so a cog can
    optionally `raise CogNotFoundError(...)` etc. after checking a helper's
    return value, for a nicer user-facing message than the generic fallback.
    Today, no cog does this, so the practical effect of the decorator is
    expired-interaction handling and a consistent unexpected-error message.

    Args:
        logger_name: Name of the section logger (e.g. "Account")
        log_file: File name inside `logs/` (e.g. "account.log")
        not_found_label: Subject used when logging a not-found error
        api_label: Subject used when logging an API error
        api_title: Title of the user-facing API error message
        rate_limit_target: Suffix naming who was sent too many requests

    Returns:
        A decorator for app command callbacks.
    """
    logger = _setup_section_logger(logger_name, log_file)

    def decorator(func):
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

            except CogNotFoundError as e:
                logger.warning(f"{not_found_label} not found: {e}")
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
                            f"Too many requests{rate_limit_target}. Please try again in a few minutes.",
                            ephemeral=True
                        )
                    except discord.NotFound:
                        logger.error("Interaction expired while sending rate limit error")

            except CogAPIError as e:
                logger.error(f"{api_label} error: {e}")
                if interaction:
                    try:
                        await interaction.followup.send(
                            f"❌ **{api_title}**\n\n{str(e)}\n\n"
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
                    except Exception:
                        pass  # Interaction expired

        return wrapper

    return decorator


account_error_handler = make_error_handler(
    "Account", "account.log", "Account data", api_label="Account API"
)
media_error_handler = make_error_handler(
    "Media", "media.log", "Media",
    api_label="AniList API", api_title="AniList API Error", rate_limit_target=" to AniList"
)
social_error_handler = make_error_handler(
    "Social", "social.log", "Social data",
    api_label="AniList API", api_title="AniList API Error", rate_limit_target=" to AniList"
)
server_management_error_handler = make_error_handler(
    "ServerManagement", "server_management.log", "Server management data",
    api_label="Server management API"
)
utilities_error_handler = make_error_handler(
    "Utilities", "utilities.log", "Data", rate_limit_target=""
)
