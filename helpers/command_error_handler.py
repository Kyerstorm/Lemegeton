"""Centralized, privacy-conscious error reporting for Lemegeton commands and interactions.

Unhandled command failures are reported privately to the user, logged with enough context
to diagnose them, and routed to /feedback. Known user-correctable errors get a useful
explanation instead of being incorrectly reported as bot bugs.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

import discord
from discord import app_commands
from discord.ext import commands

logger = logging.getLogger(__name__)

# These cogs already own a separate reporting flow; do not replace their user-facing
# response with the generic one. Errors in those paths are still recorded when routed here.
EXCLUDED_COG_MODULES = frozenset({
    "cogs.social.anilist_site_embed",
    "cogs.social.feedback",
})

FEEDBACK_ERROR_GUIDANCE = (
    "⚠️ Something went wrong while running this command.\n\n"
    "Please report it with `/feedback` so the maintainers can investigate:\n"
    "1. Choose **Bugs**.\n"
    "2. Describe the command you ran and what happened, including what you expected.\n"
    "3. Include the relevant media URL, if applicable, and attach a screenshot if useful.\n"
    "4. Submit the report."
)

_PERMISSION_ERROR = (
    "🔒 You or the bot are missing permissions required for this action. "
    "Check the server and channel permissions, then try again."
)
_CONTEXT_ERROR = (
    "🔒 This command cannot be used in the current context. "
    "Check the command requirements and try again."
)
_DISCORD_FORBIDDEN = (
    "🔒 Discord denied permission for that action. Check the bot’s role and channel "
    "permissions. If they look correct and the issue persists, report it with `/feedback`."
)
_DISCORD_NOT_FOUND = (
    "🔎 The Discord item this command needed could not be found. It may have been deleted "
    "or is no longer accessible. Try again, and use `/feedback` if the problem persists."
)
_DISCORD_HTTP_ERROR = (
    "⚠️ Discord could not complete that request. Please try again. "
    "If it keeps happening, report it with `/feedback`."
)


@dataclass(frozen=True)
class ErrorContext:
    """Non-sensitive identifiers useful for connecting a user report to server logs."""

    source: str
    command: str
    user_id: int | str | None
    guild_id: int | str | None
    channel_id: int | str | None
    interaction_id: int | str | None

    def as_log_fields(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "command": self.command,
            "user_id": self.user_id,
            "guild_id": self.guild_id,
            "channel_id": self.channel_id,
            "interaction_id": self.interaction_id,
        }


def _exception_type(namespace: Any, name: str) -> type[BaseException] | None:
    """Look up optional discord.py exception classes without assuming every version exposes them."""
    candidate = getattr(namespace, name, None)
    if isinstance(candidate, type) and issubclass(candidate, BaseException):
        return candidate
    return None


def _is_error(error: BaseException, *namespaces_and_names: tuple[Any, str]) -> bool:
    for namespace, name in namespaces_and_names:
        error_type = _exception_type(namespace, name)
        if error_type is not None and isinstance(error, error_type):
            return True
    return False


def _unwrap_error(error: BaseException) -> BaseException:
    """Unwrap discord.py invocation wrappers without looping on malformed exception chains."""
    seen: set[int] = set()
    current = error
    while id(current) not in seen:
        seen.add(id(current))
        original = getattr(current, "original", None)
        if not isinstance(original, BaseException) or original is current:
            break
        current = original
    return current


def _command_from(source: Any) -> Any:
    command = getattr(source, "command", None)
    if command is not None:
        return command
    return getattr(source, "app_command", None)


def _module_names(source: Any) -> set[str]:
    """Find the source module for slash commands, prefix commands, and component handlers."""
    names: set[str] = set()
    command = _command_from(source)
    callback = getattr(command, "callback", None)
    callback_module = getattr(callback, "__module__", None)
    if callback_module:
        names.add(callback_module)

    for owner in (getattr(source, "cog", None), getattr(command, "binding", None), source):
        if owner is None:
            continue
        module = getattr(type(owner), "__module__", None)
        if module:
            names.add(module)
        callback = getattr(owner, "callback", None)
        callback_module = getattr(callback, "__module__", None)
        if callback_module:
            names.add(callback_module)
    return names


def is_excluded_command(source: Any) -> bool:
    """Keep AniList site embeds and Feedback on their existing error-response paths."""
    return bool(_module_names(source) & EXCLUDED_COG_MODULES)


def _command_name(source: Any) -> str:
    command = _command_from(source)
    return (
        getattr(command, "qualified_name", None)
        or getattr(command, "name", None)
        or getattr(source, "custom_id", None)
        or type(source).__name__
    )


def _make_context(source: Any, label: str) -> ErrorContext:
    user = getattr(source, "user", None) or getattr(source, "author", None)
    guild = getattr(source, "guild", None)
    channel = getattr(source, "channel", None)
    return ErrorContext(
        source=label,
        command=_command_name(source),
        user_id=getattr(user, "id", None),
        guild_id=getattr(source, "guild_id", None) or getattr(guild, "id", None),
        channel_id=getattr(source, "channel_id", None) or getattr(channel, "id", None),
        interaction_id=getattr(source, "id", None),
    )


def _log_error(source: Any, error: BaseException, *, label: str) -> None:
    """Write actionable metadata and a traceback, but never log user message contents."""
    cause = _unwrap_error(error)
    context = _make_context(source, label)
    logger.error(
        "Command failure | source=%s command=%s user_id=%s guild_id=%s channel_id=%s interaction_id=%s | %s: %s",
        context.source, context.command, context.user_id, context.guild_id,
        context.channel_id, context.interaction_id, type(cause).__name__, cause,
        exc_info=(type(cause), cause, cause.__traceback__),
        extra={"lemeg_error_context": context.as_log_fields()},
    )


def application_error_message(error: BaseException) -> str:
    """Return safe user-facing text for a slash-command exception."""
    cause = _unwrap_error(error)
    if _is_error(cause, (app_commands, "CommandOnCooldown")):
        retry_after = getattr(cause, "retry_after", None)
        if isinstance(retry_after, (int, float)) and retry_after >= 0:
            return f"⏳ This command is on cooldown. Try again in {retry_after:.1f} seconds."
        return "⏳ This command is on cooldown. Please wait a little and try again."
    if _is_error(
        cause,
        (app_commands, "MissingPermissions"),
        (app_commands, "BotMissingPermissions"),
        (commands, "MissingPermissions"),
        (commands, "BotMissingPermissions"),
    ):
        return _PERMISSION_ERROR
    if _is_error(cause, (app_commands, "NoPrivateMessage"), (commands, "NoPrivateMessage")):
        return "🏠 This command can only be used in a server."
    if _is_error(cause, (app_commands, "TransformerError")):
        return "⚠️ One of the options could not be understood. Check your inputs and try again."
    if _is_error(cause, (app_commands, "CommandSignatureMismatch")):
        return "⚠️ Discord’s command options appear to be out of date. Reopen the command and try again."
    if _is_error(cause, (app_commands, "CheckFailure"), (commands, "CheckFailure")):
        return _CONTEXT_ERROR
    if isinstance(cause, discord.Forbidden):
        return _DISCORD_FORBIDDEN
    if isinstance(cause, discord.NotFound):
        return _DISCORD_NOT_FOUND
    if isinstance(cause, discord.HTTPException):
        return _DISCORD_HTTP_ERROR
    return FEEDBACK_ERROR_GUIDANCE


def prefix_error_message(error: BaseException) -> str | None:
    """Return safe user-facing text for prefix commands; unknown commands stay quiet."""
    cause = _unwrap_error(error)
    if _is_error(cause, (commands, "CommandNotFound")):
        return None
    if _is_error(cause, (commands, "CommandOnCooldown")):
        retry_after = getattr(cause, "retry_after", None)
        if isinstance(retry_after, (int, float)) and retry_after >= 0:
            return f"⏳ This command is on cooldown. Try again in {retry_after:.1f} seconds."
        return "⏳ This command is on cooldown. Please wait a little and try again."
    if _is_error(
        cause,
        (commands, "MissingPermissions"),
        (commands, "BotMissingPermissions"),
    ):
        return _PERMISSION_ERROR
    if _is_error(cause, (commands, "NoPrivateMessage")):
        return "🏠 This command can only be used in a server."
    if _is_error(cause, (commands, "MissingRequiredArgument"), (commands, "BadArgument"), (commands, "TooManyArguments")):
        return "⚠️ Some command arguments are missing or invalid. Check the command usage and try again."
    if _is_error(cause, (commands, "DisabledCommand")):
        return "⚠️ This command is currently disabled."
    if _is_error(cause, (commands, "NotOwner")):
        return "🔒 This command is restricted to the bot owner."
    if _is_error(cause, (commands, "CheckFailure")):
        return _CONTEXT_ERROR
    if isinstance(cause, discord.Forbidden):
        return _DISCORD_FORBIDDEN
    if isinstance(cause, discord.NotFound):
        return _DISCORD_NOT_FOUND
    if isinstance(cause, discord.HTTPException):
        return _DISCORD_HTTP_ERROR
    return FEEDBACK_ERROR_GUIDANCE


async def _send_interaction_message(
    interaction: discord.Interaction,
    message: str,
    *,
    ephemeral: bool = True,
) -> bool:
    """Reply privately, including after defer/initial response, without leaking a second error."""
    try:
        response = getattr(interaction, "response", None)
        is_done = getattr(response, "is_done", None)
        already_done = bool(is_done()) if callable(is_done) else False
        if already_done:
            await interaction.followup.send(message, ephemeral=ephemeral)
        else:
            await response.send_message(message, ephemeral=ephemeral)
        return True
    except (discord.HTTPException, discord.InteractionResponded):
        logger.debug(
            "Could not send error response for interaction_id=%s",
            getattr(interaction, "id", None),
            exc_info=True,
        )
        return False


async def handle_application_command_error(
    interaction: discord.Interaction,
    error: BaseException,
    *,
    source: Any | None = None,
    log_error: bool = True,
) -> None:
    """Log and respond to an unhandled slash-command error.

    The handler keeps the underlying exception private, avoids duplicate responses after
    an interaction has already replied, and respects the AniList/Feedback exclusions.
    """
    error_source = source or interaction
    if log_error:
        _log_error(error_source, error, label="application-command")
    if is_excluded_command(error_source):
        return
    await _send_interaction_message(interaction, application_error_message(error))


async def handle_prefix_command_error(ctx: commands.Context, error: BaseException) -> None:
    """Handle prefix-command failures with specific common errors and shared bug-report guidance."""
    message = prefix_error_message(error)
    if message is None:
        return
    _log_error(ctx, error, label="prefix-command")
    if is_excluded_command(ctx):
        return
    try:
        await ctx.send(message, allowed_mentions=discord.AllowedMentions.none())
    except discord.HTTPException:
        logger.debug(
            "Could not send error response for prefix command %s",
            _command_name(ctx),
            exc_info=True,
        )


async def handle_component_error(
    interaction: discord.Interaction,
    error: BaseException,
    *,
    component: str = "interactive component",
    source: Any | None = None,
    log_error: bool = True,
) -> None:
    """Report failures from button/select/view callbacks using the same private guidance.

    Pass the view or component as `source` when its module matters for the AniList/Feedback
    exclusions. Call this from a view’s `on_error`; command-tree error hooks do not catch
    button and select callback failures.
    """
    error_source = source or interaction
    if log_error:
        # Log the interaction, not only the View/Modal object, so user/guild/channel IDs
        # remain available while the component object is used to resolve exclusions.
        _log_error(interaction, error, label=f"component:{component}")
    if is_excluded_command(error_source):
        return
    await _send_interaction_message(interaction, FEEDBACK_ERROR_GUIDANCE)


async def handle_modal_error(
    interaction: discord.Interaction,
    error: BaseException,
    *,
    source: Any | None = None,
    log_error: bool = True,
) -> None:
    """Report modal submission failures without exposing exception details to the user."""
    await handle_component_error(
        interaction, error, component="modal", source=source, log_error=log_error
    )

class FeedbackAwareView(discord.ui.View):
    """Base view for cog UI components with consistent logging and private feedback guidance.

    Subclass this instead of discord.ui.View when component callback failures should use
    Lemegeton's shared failure reporting. Views with their own specialized flow may keep
    a custom on_error override.
    """

    async def on_error(
        self,
        interaction: discord.Interaction,
        error: Exception,
        item: discord.ui.Item[Any],
    ) -> None:
        """Catch button/select callback errors that the command tree never sees."""
        item_name = (
            getattr(item, "label", None)
            or getattr(item, "custom_id", None)
            or type(item).__name__
        )
        await handle_component_error(
            interaction,
            error,
            component=f"{type(self).__name__}/{item_name}",
            source=self,
        )

class FeedbackAwareModal(discord.ui.Modal):
    """Base modal that logs and reports uncaught modal submission failures privately."""

    async def on_error(
        self,
        interaction: discord.Interaction,
        error: Exception,
    ) -> None:
        """Catch modal callback failures that aren't handled inside on_submit."""
        await handle_modal_error(interaction, error, source=self)
