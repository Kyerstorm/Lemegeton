"""Shared, user-facing command error handling for Lemegeton."""
import logging

import discord
from discord import app_commands
from discord.ext import commands

logger = logging.getLogger(__name__)

EXCLUDED_COG_MODULES = {
    "cogs.social.anilist_site_embed",
    "cogs.social.feedback",
}

FEEDBACK_ERROR_GUIDANCE = (
    "⚠️ Something went wrong while running this command.\n\n"
    "Please report it with `/feedback` so the maintainers can investigate:\n"
    "1. Choose **Bugs**.\n"
    "2. Describe the command you ran and what happened (and what you expected).\n"
    "3. Include the relevant media URL, if applicable, and attach a screenshot if useful.\n"
    "4. Submit the report."
)


def _module_names(source) -> set[str]:
    """Return module names for the command callback and its owning cog, when available."""
    command = getattr(source, "command", None)
    names = set()

    callback = getattr(command, "callback", None)
    callback_module = getattr(callback, "__module__", None)
    if callback_module:
        names.add(callback_module)

    binding = getattr(command, "binding", None)
    cog = getattr(source, "cog", None) or binding
    if cog is not None:
        cog_module = getattr(type(cog), "__module__", None)
        if cog_module:
            names.add(cog_module)

    return names


def is_excluded_command(source) -> bool:
    """Keep AniList site embeds and Feedback on their existing error flows."""
    return bool(_module_names(source) & EXCLUDED_COG_MODULES)


def _actual_error(error):
    """Unwrap invocation wrappers for classification and logging."""
    return getattr(error, "original", error)


def _application_error_message(error: Exception) -> str:
    cause = _actual_error(error)
    if isinstance(cause, app_commands.CommandOnCooldown):
        return f"⏳ This command is on cooldown. Try again in {cause.retry_after:.1f} seconds."
    if isinstance(cause, (app_commands.MissingPermissions, app_commands.BotMissingPermissions)):
        return "🔒 You or the bot are missing permissions required for this command. Check the server permissions and try again."
    if isinstance(cause, app_commands.NoPrivateMessage):
        return "🏠 This command can only be used in a server."
    if isinstance(cause, app_commands.TransformerError):
        return "⚠️ One of the options could not be understood. Check your inputs and try again."
    if isinstance(cause, app_commands.CheckFailure):
        return "🔒 This command cannot be used in the current context. Check its requirements and try again."
    return FEEDBACK_ERROR_GUIDANCE


def _prefix_error_message(error: Exception) -> str | None:
    cause = _actual_error(error)
    if isinstance(cause, commands.CommandNotFound):
        return None
    if isinstance(cause, commands.CommandOnCooldown):
        return f"⏳ This command is on cooldown. Try again in {cause.retry_after:.1f} seconds."
    if isinstance(cause, (commands.MissingPermissions, commands.BotMissingPermissions)):
        return "🔒 You or the bot are missing permissions required for this command."
    if isinstance(cause, commands.NoPrivateMessage):
        return "🏠 This command can only be used in a server."
    if isinstance(cause, (commands.MissingRequiredArgument, commands.BadArgument)):
        return "⚠️ Some command arguments are missing or invalid. Check the command usage and try again."
    if isinstance(cause, commands.CheckFailure):
        return "🔒 This command cannot be used in the current context. Check its requirements and try again."
    return FEEDBACK_ERROR_GUIDANCE


async def _send_interaction_message(interaction: discord.Interaction, message: str) -> None:
    try:
        if interaction.response.is_done():
            await interaction.followup.send(message, ephemeral=True)
        else:
            await interaction.response.send_message(message, ephemeral=True)
    except (discord.HTTPException, discord.InteractionResponded):
        logger.debug("Could not send an error response for interaction %s", getattr(interaction, "id", None), exc_info=True)


def _log_command_error(source, error: Exception, *, label: str) -> None:
    command = getattr(source, "command", None)
    command_name = getattr(command, "qualified_name", None) or getattr(command, "name", None) or "unknown"
    user = getattr(source, "user", None) or getattr(source, "author", None)
    user_id = getattr(user, "id", None)
    guild_id = getattr(source, "guild_id", None) or getattr(getattr(source, "guild", None), "id", None)
    cause = _actual_error(error)
    logger.error(
        "%s error in command %s (user_id=%s, guild_id=%s): %r",
        label, command_name, user_id, guild_id, cause,
        exc_info=(type(cause), cause, cause.__traceback__),
    )


async def handle_application_command_error(interaction: discord.Interaction, error: Exception) -> None:
    """Log a slash-command failure and respond privately with actionable guidance."""
    if is_excluded_command(interaction):
        _log_command_error(interaction, error, label="Excluded application command")
        return

    _log_command_error(interaction, error, label="Application command")
    await _send_interaction_message(interaction, _application_error_message(error))


async def handle_prefix_command_error(ctx: commands.Context, error: Exception) -> None:
    """Log a prefix-command failure and provide the same reporting route."""
    if is_excluded_command(ctx):
        _log_command_error(ctx, error, label="Excluded prefix command")
        return

    message = _prefix_error_message(error)
    if message is None:
        return

    _log_command_error(ctx, error, label="Prefix command")
    try:
        await ctx.send(message, allowed_mentions=discord.AllowedMentions.none())
    except discord.HTTPException:
        logger.debug("Could not send an error response for prefix command", exc_info=True)
