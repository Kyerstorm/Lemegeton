"""Lunar Roles service layer: the one place that decides and applies role changes.

Slash commands, the web API and automatic events all call these functions.
Expected failures come back as a Result with a user-facing message; nothing
here raises to the caller for them.
"""
from __future__ import annotations

import asyncio
import os
import time
from dataclasses import dataclass, field, replace
from typing import Any, Awaitable, Callable, Dict, List, Optional, Tuple

import discord

import config
from helpers.color_palette import PALETTE
from helpers.logging_helper import get_logger
from helpers.lunar_roles import (
    ADMIN_GROUP,
    COMMAND_GROUP,
    FEATURE_GRADIENT,
    FEATURE_ICONS,
    HOLOGRAPHIC_COLORS,
    ROLE_LIMIT,
)
from helpers.lunar_roles import images, storage, validation
from helpers.lunar_roles.storage import CustomRole, GuildSettings

logger = get_logger("LunarRoles", logfile="lunar_roles.log")

NOT_SET_UP_MESSAGE = (
    "Lunar Roles isn't set up yet in this server. "
    f"Ask an admin to run `/{ADMIN_GROUP} anchor` and `/{ADMIN_GROUP} enable`."
)
NO_ROLE_MESSAGE = f"You don't have a Lunar role yet. Create one with `/{COMMAND_GROUP} role <name>`."
PERMISSION_MESSAGE = (
    "I couldn't manage your role. Ask an admin to check that I have **Manage Roles** "
    "and that my role is above the Lunar anchor role."
)
API_ERROR_MESSAGE = "Discord didn't accept that change. Please try again in a moment."
NO_GRADIENT_MESSAGE = (
    "This server doesn't have Discord's enhanced role colors, so gradient and holographic "
    "styles aren't available here. Solid colors still work."
)

MODE_SOLID = "solid"
MODE_GRADIENT = "gradient"
MODE_HOLOGRAPHIC = "holographic"

PLACE_BELOW = "below"
PLACE_ABOVE = "above"

# A role with any of these can moderate, so its name can't be copied into a custom role.
MODERATION_PERMISSIONS = (
    "administrator", "manage_guild", "manage_roles", "manage_channels", "manage_messages",
    "manage_nicknames", "manage_threads", "manage_webhooks", "manage_expressions", "manage_events",
    "kick_members", "ban_members", "moderate_members", "mute_members", "deafen_members", "move_members",
)


@dataclass
class Result:
    ok: bool
    message: str
    data: Any = None
    notes: List[str] = field(default_factory=list)  # warnings shown separately ("Heads up")


@dataclass
class FeatureStatus:
    gradient: bool
    icons: bool
    role_count: int
    role_limit: int = ROLE_LIMIT


# One lock per (guild, user) so two changes for the same member can't race.
_user_locks: Dict[Tuple[int, int], asyncio.Lock] = {}


def user_lock(guild_id: int, user_id: int) -> asyncio.Lock:
    key = (guild_id, user_id)
    lock = _user_locks.get(key)
    if lock is None:
        lock = _user_locks[key] = asyncio.Lock()
    return lock


# ------------------------------------------------------
# Checks
# ------------------------------------------------------

def feature_status(guild: discord.Guild) -> FeatureStatus:
    return FeatureStatus(
        gradient=FEATURE_GRADIENT in guild.features,
        icons=FEATURE_ICONS in guild.features,
        role_count=len(guild.roles),
    )


def ensure_ready(guild: discord.Guild, settings: GuildSettings) -> Result:
    """Gate for every user action: the feature is enabled and its anchor still exists."""
    if not settings.enabled or not settings.anchor_role_id:
        return Result(False, NOT_SET_UP_MESSAGE)
    if guild.get_role(settings.anchor_role_id) is None:
        return Result(False, NOT_SET_UP_MESSAGE)
    return Result(True, "ready")


def ensure_eligible(member: discord.Member, settings: GuildSettings) -> Result:
    """Boosters, plus members holding an admin-configured allowed role."""
    if member.premium_since is not None:
        return Result(True, "booster")
    allowed = set(settings.allowed_role_ids)
    if allowed and any(role.id in allowed for role in member.roles):
        return Result(True, "allowed role")
    return Result(False, "Lunar Roles are for server boosters. Boost the server to unlock your own role!")


def validate_anchor(guild: discord.Guild, role: discord.Role) -> Result:
    """Custom roles go directly below the anchor, so it must sit below the bot's top role."""
    if role.is_default():
        return Result(False, "`@everyone` can't be the anchor - nothing can be placed below it.")
    top = guild.me.top_role
    if role >= top:
        return Result(
            False,
            f"{role.mention} is at or above my highest role ({top.mention}), so I can't place roles "
            "below it. Pick a lower role, or move my role higher in Server Settings → Roles.",
        )
    return Result(True, "ok")


def has_colour(role: discord.Role) -> bool:
    return bool(role.colour.value) or role.secondary_colour is not None


def is_moderation_role(role: discord.Role) -> bool:
    perms = role.permissions
    return any(getattr(perms, name, False) for name in MODERATION_PERMISSIONS)


def colored_roles_above_custom(
    guild: discord.Guild, settings: GuildSettings, tracked_ids: set
) -> List[discord.Role]:
    """Colored roles (with members) above the custom roles; they hide custom colors for their members.

    Highest first. With no custom roles yet, uses where new ones would be placed.
    """
    custom_positions = [r.position for r in (guild.get_role(i) for i in tracked_ids) if r is not None]
    if custom_positions:
        threshold = min(custom_positions)
    else:
        anchor = guild.get_role(settings.anchor_role_id) if settings.anchor_role_id else None
        if anchor is None:
            return []
        # below: the anchor itself sits above new roles; above: only roles over the anchor do
        threshold = anchor.position - 0.5 if settings.anchor_place == PLACE_BELOW else anchor.position + 0.5
    found = [
        r for r in guild.roles
        if r.position > threshold and r.id not in tracked_ids and not r.is_default()
        and not r.is_bot_managed() and has_colour(r) and r.members
    ]
    return sorted(found, key=lambda r: r.position, reverse=True)


def hidden_colour_notice(
    member: discord.Member, role: discord.Role, positions: Optional[Dict[int, int]] = None
) -> Optional[str]:
    """Tell the member if a higher colored role of theirs hides their custom color.

    positions: fresh {role_id: position} right after a reorder (the cache can lag).
    """
    positions = positions or {}
    pos = lambda r: positions.get(r.id, r.position)  # noqa: E731
    mine = pos(role)
    higher = [
        r for r in member.roles
        if r.id != role.id and not r.is_default() and pos(r) > mine and has_colour(r)
    ]
    if not higher:
        return None
    top = max(higher, key=lambda r: r.position)
    return (
        f"Your **{top.name}** role is higher and has its own color, so Discord shows that color "
        "instead of yours. Ask an admin if they can move Lunar roles higher."
    )


def hidden_icon_notice(
    member: discord.Member, role: discord.Role, positions: Optional[Dict[int, int]] = None
) -> Optional[str]:
    """Discord shows the icon of a member's highest role that has one; warn if that isn't their custom role."""
    positions = positions or {}
    pos = lambda r: positions.get(r.id, r.position)  # noqa: E731
    mine = pos(role)
    higher = [
        r for r in member.roles
        if r.id != role.id and not r.is_default() and pos(r) > mine and r.display_icon
    ]
    if not higher:
        return None
    top = max(higher, key=lambda r: r.position)
    return (
        f"Your **{top.name}** role is higher and has its own icon, so Discord shows that icon "
        "instead of yours. Ask an admin if they can move Lunar roles higher."
    )


def setup_problems(guild: discord.Guild, settings: GuildSettings) -> List[str]:
    """Admin-facing list of things that would stop the feature from working."""
    problems = []
    me = guild.me
    if not me.guild_permissions.manage_roles:
        problems.append("I'm missing the **Manage Roles** permission.")
    if not settings.anchor_role_id:
        problems.append(f"No anchor role set - run `/{ADMIN_GROUP} anchor`.")
    else:
        anchor = guild.get_role(settings.anchor_role_id)
        if anchor is None:
            problems.append(f"The anchor role was deleted - run `/{ADMIN_GROUP} anchor` again.")
        elif anchor >= me.top_role:
            problems.append(f"The anchor {anchor.mention} is at or above my highest role {me.top_role.mention}.")
    if len(guild.roles) >= ROLE_LIMIT:
        problems.append(f"The server is at Discord's {ROLE_LIMIT}-role limit.")
    return problems


# ------------------------------------------------------
# Admin setup actions
# ------------------------------------------------------

async def set_anchor(guild: discord.Guild, role: discord.Role, place: str = PLACE_BELOW) -> Result:
    if place not in (PLACE_BELOW, PLACE_ABOVE):
        return Result(False, "Placement must be `above` or `below`.")
    check = validate_anchor(guild, role)
    if not check.ok:
        return check
    settings = await storage.update_guild_settings(guild.id, anchor_role_id=role.id, anchor_place=place)
    logger.info("Guild %s anchor set to role %s (%s)", guild.id, role.id, place)
    return Result(True, f"Custom roles will be placed directly **{place}** {role.mention}.", settings)


async def set_enabled(guild: discord.Guild, enabled: bool) -> Result:
    settings = await storage.get_guild_settings(guild.id)
    if enabled:
        anchor = guild.get_role(settings.anchor_role_id) if settings.anchor_role_id else None
        if anchor is None:
            return Result(False, f"Set an anchor role first with `/{ADMIN_GROUP} anchor`.", settings)
        check = validate_anchor(guild, anchor)
        if not check.ok:
            return Result(False, check.message, settings)
    settings = await storage.update_guild_settings(guild.id, enabled=enabled)
    logger.info("Guild %s Lunar Roles %s", guild.id, "enabled" if enabled else "disabled")
    return Result(True, "Lunar Roles is now **on**." if enabled else "Lunar Roles is now **off**.", settings)


async def add_allowed_role(guild: discord.Guild, role: discord.Role) -> Result:
    if role.is_default():
        return Result(False, "`@everyone` can't be an allowed role.")
    settings = await storage.get_guild_settings(guild.id)
    if role.id in settings.allowed_role_ids:
        return Result(False, f"{role.mention} is already allowed.", settings)
    settings = await storage.update_guild_settings(
        guild.id, allowed_role_ids=[*settings.allowed_role_ids, role.id]
    )
    logger.info("Guild %s allowed role %s", guild.id, role.id)
    return Result(True, f"Members with {role.mention} can now use Lunar Roles, as well as boosters.", settings)


async def remove_allowed_role(guild: discord.Guild, role: discord.Role) -> Result:
    settings = await storage.get_guild_settings(guild.id)
    if role.id not in settings.allowed_role_ids:
        return Result(False, f"{role.mention} isn't on the allowed list.", settings)
    settings = await storage.update_guild_settings(
        guild.id, allowed_role_ids=[r for r in settings.allowed_role_ids if r != role.id]
    )
    logger.info("Guild %s removed allowed role %s", guild.id, role.id)
    return Result(True, f"{role.mention} removed. Only boosters (and other allowed roles) can use Lunar Roles.", settings)


async def list_allowed_roles(guild: discord.Guild) -> List[discord.Role]:
    """Allowed roles that still exist; deleted ones are pruned from the settings."""
    settings = await storage.get_guild_settings(guild.id)
    roles = [guild.get_role(r) for r in settings.allowed_role_ids]
    existing = [r for r in roles if r is not None]
    if len(existing) != len(settings.allowed_role_ids):
        await storage.update_guild_settings(guild.id, allowed_role_ids=[r.id for r in existing])
    return existing


def active_protected_words(settings: GuildSettings) -> List[str]:
    removed = set(settings.removed_default_words)
    return [w for w in validation.DEFAULT_PROTECTED_WORDS if w not in removed]


async def add_blocked_word(guild: discord.Guild, raw: str) -> Result:
    word = validation.clean_word(raw)
    if word is None:
        return Result(False, f"Blocked words must be 1-{validation.WORD_MAX} characters and include a letter or number.")
    settings = await storage.get_guild_settings(guild.id)
    if word in validation.DEFAULT_PROTECTED_WORDS:
        if word not in settings.removed_default_words:
            return Result(False, f"{validation.code(word)} is already a built-in protected word.", settings)
        settings = await storage.update_guild_settings(
            guild.id, removed_default_words=[w for w in settings.removed_default_words if w != word]
        )
        return Result(True, f"Built-in protected word {validation.code(word)} is back on.", settings)
    if word in settings.blocked_words:
        return Result(False, f"{validation.code(word)} is already blocked.", settings)
    settings = await storage.update_guild_settings(guild.id, blocked_words=[*settings.blocked_words, word])
    logger.info("Guild %s blocked word added", guild.id)
    return Result(True, f"Blocked {validation.code(word)} anywhere in role names.", settings)


async def remove_blocked_word(guild: discord.Guild, raw: str) -> Result:
    word = validation.clean_word(raw)
    settings = await storage.get_guild_settings(guild.id)
    if word and word in settings.blocked_words:
        settings = await storage.update_guild_settings(
            guild.id, blocked_words=[w for w in settings.blocked_words if w != word]
        )
        return Result(True, f"Unblocked {validation.code(word)}.", settings)
    if word and word in validation.DEFAULT_PROTECTED_WORDS:
        if word in settings.removed_default_words:
            return Result(False, f"Built-in word {validation.code(word)} is already off.", settings)
        settings = await storage.update_guild_settings(
            guild.id, removed_default_words=[*settings.removed_default_words, word]
        )
        return Result(True, f"Built-in protected word {validation.code(word)} is now off. Add it again to turn it back on.", settings)
    return Result(False, f"{validation.code(raw)} isn't on the blocked list.", settings)


# ------------------------------------------------------
# Member role actions
# ------------------------------------------------------

async def _discord(guild: discord.Guild, action: str, coro) -> Tuple[Any, Optional[Result]]:
    """Await a Discord call, turning expected failures into a Result (and a log-channel line)."""
    try:
        return await coro, None
    except discord.Forbidden:
        logger.warning("Forbidden while %s", action)
        await log_event(guild, f"Missing permission while {action}. Check I have Manage Roles and my role is high enough.", "error")
        return None, Result(False, PERMISSION_MESSAGE)
    except discord.HTTPException as exc:
        logger.exception("Discord API error while %s", action)
        await log_event(guild, f"Discord error while {action}: {validation.code(f'{exc.status} {exc.text[:150]}')}", "error")
        return None, Result(False, API_ERROR_MESSAGE)


async def _check_member(member: discord.Member) -> Tuple[Optional[GuildSettings], Optional[Result]]:
    settings = await storage.get_guild_settings(member.guild.id)
    for check in (ensure_ready(member.guild, settings), ensure_eligible(member, settings)):
        if not check.ok:
            return settings, check
    return settings, None


async def precheck(member: discord.Member, need_role: bool = True) -> Optional[Result]:
    """The usual gates (set up, eligible, has a role) for commands that do their own work first."""
    _, error = await _check_member(member)
    if error:
        return error
    if need_role and await storage.get_custom_role(member.guild.id, member.id) is None:
        return Result(False, NO_ROLE_MESSAGE)
    return None


async def _clean_name(
    guild: discord.Guild, raw: str, settings: GuildSettings, own_role_id: Optional[int],
    tracked: Optional[set] = None,
) -> Tuple[Optional[str], Optional[str]]:
    if tracked is None:
        tracked = await storage.list_active_role_ids(guild.id)
    others = [
        role for role in guild.roles
        if not role.is_default() and role.id not in tracked and role.id != own_role_id
    ]
    return validation.check_role_name(
        raw,
        reserved_names=[r.name for r in others],
        blocked_words=settings.blocked_words,
        protected_words=active_protected_words(settings),
        protected_role_names=[r.name for r in others if is_moderation_role(r)],
    )


def _style_kwargs(
    guild: discord.Guild, mode: str, primary: Optional[int], secondary: Optional[int], strict: bool
) -> Tuple[Dict[str, Any], Optional[str], Optional[Result]]:
    """Build create_role/edit colour kwargs. Returns (kwargs, notice, error).

    strict=True refuses styles the server can't show; strict=False (restoring
    saved settings) falls back to solid with a notice.
    """
    gradient_ok = FEATURE_GRADIENT in guild.features
    notice = None
    if mode in (MODE_GRADIENT, MODE_HOLOGRAPHIC) and not gradient_ok:
        if strict:
            return {}, None, Result(False, NO_GRADIENT_MESSAGE)
        mode = MODE_SOLID
        notice = "This server can't show gradients right now, so your role uses a solid color for now."

    if mode == MODE_HOLOGRAPHIC:
        colours = HOLOGRAPHIC_COLORS
    elif mode == MODE_GRADIENT:
        colours = (primary, secondary, None)
    else:
        colours = (primary, None, None)

    kwargs: Dict[str, Any] = {"colour": discord.Colour(colours[0] or 0)}
    if gradient_ok:
        # discord.py reads `secondary_colour or secondary_color`, so clearing
        # with None only works if both spellings are passed.
        for key, value in (("secondary", colours[1]), ("tertiary", colours[2])):
            colour = discord.Colour(value) if value is not None else None
            kwargs[f"{key}_colour"] = colour
            kwargs[f"{key}_color"] = colour
    return kwargs, notice, None


async def _place_by_anchor(
    guild: discord.Guild, role: discord.Role, anchor_id: int, place: str
) -> Optional[Dict[int, int]]:
    """Move role directly below/above the anchor using fresh positions.

    Returns every role's position afterwards ({role_id: position}), or None if the anchor is gone.
    """
    fresh = await guild.fetch_roles()
    anchor = next((r for r in fresh if r.id == anchor_id), None)
    if anchor is None:
        return None
    order = sorted(
        (r for r in fresh if r.id != role.id and not r.is_default()),
        key=lambda r: (r.position, r.id),
    )
    index = order.index(anchor) + (1 if place == PLACE_ABOVE else 0)
    order.insert(index, role)
    # Only roles up to the new one move; all of them are at or below the anchor's
    # neighbour, which is below the bot's top role (checked by validate_anchor).
    positions = {r: i for i, r in enumerate(order[: index + 1], start=1)}
    current = {r.id: r.position for r in fresh}
    if any(current.get(r.id) != p for r, p in positions.items()):
        await guild.edit_role_positions(positions=positions, reason=f"Lunar Roles: place {place} anchor")
    return {**current, **{r.id: p for r, p in positions.items()}}


async def _create_discord_role(
    member: discord.Member, settings: GuildSettings, record: CustomRole
) -> Tuple[Optional[discord.Role], List[str], Optional[Result]]:
    """Create the member's role from record, save it, place it and assign it."""
    guild = member.guild
    me = guild.me
    if not me.guild_permissions.manage_roles:
        return None, [], Result(False, PERMISSION_MESSAGE)
    if len(guild.roles) >= ROLE_LIMIT:
        logger.warning("Guild %s is at the %s-role limit; refused role for %s", guild.id, ROLE_LIMIT, member.id)
        await log_event(guild, f"The server is at Discord's {ROLE_LIMIT}-role limit, so I couldn't create a role for {member.mention}.", "warning")
        return None, [], Result(
            False, f"This server has reached Discord's {ROLE_LIMIT}-role limit, so I can't create your role. "
                   "Please let an admin know."
        )
    anchor = guild.get_role(settings.anchor_role_id)
    if anchor is None:
        return None, [], Result(False, NOT_SET_UP_MESSAGE)
    if anchor >= me.top_role:
        return None, [], Result(False, PERMISSION_MESSAGE)

    style, notice, _ = _style_kwargs(guild, record.color_mode, record.primary_color, record.secondary_color, strict=False)
    notes = [notice] if notice else []
    if FEATURE_ICONS in guild.features and (record.icon_png or record.icon_emoji):
        style["display_icon"] = record.icon_png or record.icon_emoji  # bytes = image, str = Unicode emoji

    role, error = await _discord(
        guild,
        f"creating role for {member.id} in {guild.id}",
        guild.create_role(
            name=record.name,
            permissions=discord.Permissions.none(),
            reason=f"Lunar Roles: custom role for {member} ({member.id})",
            **style,
        ),
    )
    if error:
        return None, [], error

    # Save first so the role is never left untracked.
    await storage.upsert_custom_role(replace(record, role_id=role.id, status=storage.STATUS_ACTIVE))

    positions = None
    try:
        positions = await _place_by_anchor(guild, role, anchor.id, settings.anchor_place)
    except discord.HTTPException:
        logger.exception("Couldn't place role %s %s anchor %s in guild %s", role.id, settings.anchor_place, anchor.id, guild.id)
        notes.append(f"I couldn't move it into place - an admin may need to drag it {settings.anchor_place} the anchor.")

    _, error = await _discord(guild, f"assigning role {role.id} to {member.id}", member.add_roles(role, reason="Lunar Roles"))
    if error:
        return role, notes, Result(False, f"Your role was created, but I couldn't give it to you. Try `/{COMMAND_GROUP} assign`.")
    # The cached positions may lag; use the ones we just set.
    if positions is not None and has_colour(role):
        hidden = hidden_colour_notice(member, role, positions)
        if hidden:
            notes.append(hidden)
    if positions is not None and "display_icon" in style:
        hidden = hidden_icon_notice(member, role, positions)
        if hidden:
            notes.append(hidden)
    logger.info("Created role %s for %s in guild %s", role.id, member.id, guild.id)
    return role, notes, None


async def _ensure_live_role(
    member: discord.Member, record: CustomRole, settings: GuildSettings, **overrides
) -> Tuple[Optional[discord.Role], bool, List[str], Optional[Result]]:
    """Return (role, created, notes, error). Recreates a saved/missing role with overrides applied."""
    guild = member.guild
    role = guild.get_role(record.role_id) if record.role_id else None
    if role is not None:
        if role >= guild.me.top_role:
            return None, False, [], Result(
                False, "Your role is above my highest role, so I can't change it. "
                       "Ask an admin to move it back below the Lunar anchor."
            )
        if record.status != storage.STATUS_ACTIVE:
            await storage.update_custom_role(guild.id, member.id, status=storage.STATUS_ACTIVE)
        return role, False, [], None

    if record.status == storage.STATUS_ACTIVE:
        await _mark_missing(guild, member.id, record.role_id, "found deleted while changing it")

    desired = replace(record, **overrides)
    if not desired.name:
        return None, False, [], Result(
            False, f"Your old role was deleted. Make a new one with `/{COMMAND_GROUP} role <name>`."
        )
    role, notes, error = await _create_discord_role(member, settings, desired)
    return role, role is not None, notes, error


async def create_role(member: discord.Member, name: str) -> Result:
    settings, error = await _check_member(member)
    if error:
        return error
    guild = member.guild
    async with user_lock(guild.id, member.id):
        record = await storage.get_custom_role(guild.id, member.id)
        existing = guild.get_role(record.role_id) if record and record.role_id else None
        if existing is not None:
            return Result(
                False,
                f"Your role already exists by the name {validation.code(existing.name)}.\n"
                f"Use `/{COMMAND_GROUP} assign` to put it on, or `/{COMMAND_GROUP} name` to rename it.",
                existing,
            )
        clean, reason = await _clean_name(guild, name, settings, own_role_id=None)
        if reason:
            return Result(False, reason)

        restoring = record is not None
        if restoring:
            if record.status == storage.STATUS_ACTIVE:
                await storage.update_custom_role(guild.id, member.id, status=storage.STATUS_MISSING, role_id=None)
            desired = replace(record, name=clean)
        else:
            desired = CustomRole(
                guild_id=guild.id, user_id=member.id, role_id=None, status=storage.STATUS_ACTIVE,
                name=clean, color_mode=MODE_SOLID, primary_color=None, secondary_color=None,
                icon_png=None, position_hint=None, last_changed_at=None, created_at=None, updated_at=None,
            )
        role, notes, error = await _create_discord_role(member, settings, desired)
        if error:
            return error
    if restoring:
        message = f"Your role **{role.name}** is back, with your saved colors."
        await log_event(guild, f"{member.mention} recreated their role {role.mention} from saved settings.")
    else:
        message = f"Created **{role.name}** and gave it to you. Color it with `/{COMMAND_GROUP} color set`."
        await log_event(guild, f"{member.mention} created their role {role.mention}.", "success")
    return Result(True, message, role, notes)


async def rename(member: discord.Member, new_name: str) -> Result:
    settings, error = await _check_member(member)
    if error:
        return error
    guild = member.guild
    async with user_lock(guild.id, member.id):
        record = await storage.get_custom_role(guild.id, member.id)
        if record is None:
            return Result(False, NO_ROLE_MESSAGE)
        clean, reason = await _clean_name(guild, new_name, settings, own_role_id=record.role_id)
        if reason:
            return Result(False, reason)
        old_name = record.name
        role, created, notes, error = await _ensure_live_role(member, record, settings, name=clean)
        if error:
            return error
        if not created:
            old_name = role.name
            _, error = await _discord(guild, f"renaming role {role.id}", role.edit(name=clean, reason=f"Lunar Roles: renamed by {member}"))
            if error:
                return error
        await storage.update_custom_role(guild.id, member.id, changed=True, name=clean)
    logger.info("Renamed role %s for %s in guild %s", role.id, member.id, guild.id)
    await log_event(guild, f"{member.mention} renamed their role {validation.code(old_name or '?')} → {role.mention}.")
    return Result(True, f"Your role is now called **{clean}**.", role, notes)


async def set_colors(
    member: discord.Member, mode: str, primary: Optional[int] = None, secondary: Optional[int] = None
) -> Result:
    settings, error = await _check_member(member)
    if error:
        return error
    guild = member.guild
    if mode == MODE_HOLOGRAPHIC:
        primary, secondary = HOLOGRAPHIC_COLORS[0], HOLOGRAPHIC_COLORS[1]
    style, _, error = _style_kwargs(guild, mode, primary, secondary, strict=True)
    if error:
        return error
    async with user_lock(guild.id, member.id):
        record = await storage.get_custom_role(guild.id, member.id)
        if record is None:
            return Result(False, NO_ROLE_MESSAGE)
        changes = {"color_mode": mode, "primary_color": primary, "secondary_color": secondary}
        role, created, notes, error = await _ensure_live_role(member, record, settings, **changes)
        if error:
            return error
        if not created:
            _, error = await _discord(guild, f"recoloring role {role.id}", role.edit(reason=f"Lunar Roles: recolored by {member}", **style))
            if error:
                return error
            hidden = hidden_colour_notice(member, role)
            if hidden:
                notes.append(hidden)
        await storage.update_custom_role(guild.id, member.id, changed=True, **changes)
    logger.info("Set %s colors on role %s for %s in guild %s", mode, role.id, member.id, guild.id)
    if mode == MODE_HOLOGRAPHIC:
        message = "Your role is now **holographic**."
    elif mode == MODE_GRADIENT:
        message = f"Your role is now a gradient from `{validation.format_hex(primary)}` to `{validation.format_hex(secondary)}`."
    else:
        message = f"Your role color is now `{validation.format_hex(primary)}`."
    style_text = {
        MODE_HOLOGRAPHIC: "holographic",
        MODE_GRADIENT: f"gradient `{validation.format_hex(primary)}` → `{validation.format_hex(secondary)}`",
    }.get(mode, f"`{validation.format_hex(primary)}`")
    await log_event(guild, f"{member.mention} recolored {role.mention}: {style_text}.")
    return Result(True, message, role, notes)


async def assign(member: discord.Member) -> Result:
    settings, error = await _check_member(member)
    if error:
        return error
    guild = member.guild
    async with user_lock(guild.id, member.id):
        record = await storage.get_custom_role(guild.id, member.id)
        if record is None:
            return Result(False, NO_ROLE_MESSAGE)
        role, created, notes, error = await _ensure_live_role(member, record, settings)
        if error:
            return error
        if created:
            return Result(True, f"Your role **{role.name}** was missing, so I recreated it and put it on you.", role, notes)
        if role in member.roles:
            return Result(False, f"You're already wearing **{role.name}**.", role)
        _, error = await _discord(guild, f"assigning role {role.id}", member.add_roles(role, reason="Lunar Roles: assign"))
        if error:
            return error
    return Result(True, f"Put **{role.name}** back on you.", role)


async def unassign(member: discord.Member) -> Result:
    settings, error = await _check_member(member)
    if error:
        return error
    guild = member.guild
    async with user_lock(guild.id, member.id):
        record = await storage.get_custom_role(guild.id, member.id)
        if record is None:
            return Result(False, NO_ROLE_MESSAGE)
        role = guild.get_role(record.role_id) if record.role_id else None
        if role is None or role not in member.roles:
            return Result(False, "You're not wearing your Lunar role right now.")
        _, error = await _discord(guild, f"unassigning role {role.id}", member.remove_roles(role, reason="Lunar Roles: unassign"))
        if error:
            return error
    return Result(
        True, f"Took **{role.name}** off you. It's still yours - use `/{COMMAND_GROUP} assign` to wear it again.", role
    )


NO_ICONS_MESSAGE = (
    "Role icons need **Boost Level 2** (Discord's Role Icons perk), and this server doesn't have it yet."
)


async def set_icon(member: discord.Member, image: Optional[bytes] = None, emoji: Optional[str] = None) -> Result:
    """Set the role icon from an uploaded PNG/JPEG or a standard emoji (exactly one of them).

    The image/emoji is checked before the server's Role Icons perk, so members learn
    whether it's usable even where icons aren't available.
    """
    if (image is None) == (emoji is None):
        return Result(False, "Send either an image or an emoji, not both.")
    settings, error = await _check_member(member)
    if error:
        return error
    guild = member.guild
    if await storage.get_custom_role(guild.id, member.id) is None:
        return Result(False, NO_ROLE_MESSAGE)

    try:
        if image is not None:
            value: Any = await asyncio.to_thread(images.prepare_icon, image)
            changes = {"icon_png": value, "icon_emoji": None}
        else:
            value = images.check_emoji(emoji)
            changes = {"icon_png": None, "icon_emoji": value}
    except images.ImageError as exc:
        return Result(False, exc.message)
    if FEATURE_ICONS not in guild.features:
        what = "image" if image is not None else "emoji"
        return Result(False, f"Your {what} is fine, but {NO_ICONS_MESSAGE[0].lower()}{NO_ICONS_MESSAGE[1:]}")

    async with user_lock(guild.id, member.id):
        record = await storage.get_custom_role(guild.id, member.id)
        if record is None:
            return Result(False, NO_ROLE_MESSAGE)
        role, created, notes, error = await _ensure_live_role(member, record, settings, **changes)
        if error:
            return error
        if not created:
            _, error = await _discord(guild, f"setting the icon of role {role.id}",
                                      role.edit(display_icon=value, reason=f"Lunar Roles: icon set by {member}"))
            if error:
                if emoji is not None and error.message == API_ERROR_MESSAGE:
                    return Result(False, "Discord didn't accept that emoji as a role icon. Try a different one.")
                return error
            hidden = hidden_icon_notice(member, role)
            if hidden:
                notes.append(hidden)
        await storage.update_custom_role(guild.id, member.id, changed=True, **changes)
    logger.info("Set %s icon on role %s for %s in guild %s", "emoji" if emoji else "image", role.id, member.id, guild.id)
    shown = value if emoji is not None else "an image"
    await log_event(guild, f"{member.mention} set the icon of {role.mention} to {shown}.")
    if emoji is not None:
        return Result(True, f"Your role icon is now {value}.", role, notes)
    return Result(True, "Your role icon is set. Images are cropped to the center square and resized to 64x64.", role, notes)


async def remove_icon(member: discord.Member) -> Result:
    settings, error = await _check_member(member)
    if error:
        return error
    guild = member.guild
    async with user_lock(guild.id, member.id):
        record = await storage.get_custom_role(guild.id, member.id)
        if record is None:
            return Result(False, NO_ROLE_MESSAGE)
        role = guild.get_role(record.role_id) if record.role_id else None
        has_icon = bool(record.icon_png or record.icon_emoji or (role is not None and role.display_icon))
        if not has_icon:
            if FEATURE_ICONS not in guild.features:
                return Result(False, NO_ICONS_MESSAGE)
            return Result(False, "Your role doesn't have an icon to remove.")
        if role is not None and role.display_icon:
            _, error = await _discord(guild, f"removing the icon of role {role.id}",
                                      role.edit(display_icon=None, reason=f"Lunar Roles: icon removed by {member}"))
            if error:
                return error
        await storage.update_custom_role(guild.id, member.id, changed=True, icon_png=None, icon_emoji=None)
    logger.info("Removed icon for %s in guild %s", member.id, guild.id)
    await log_event(guild, f"{member.mention} removed their role icon.")
    return Result(True, "Your role icon was removed.", role)


# ------------------------------------------------------
# Avatar palette (shared by /lunar palette and, later, the web picker)
# ------------------------------------------------------

def palette_avatar(member: discord.Member) -> discord.Asset:
    """Server avatar if set, else main avatar, else Discord's default; animated ones as a still PNG."""
    asset = member.guild_avatar or member.avatar or member.default_avatar
    try:
        return asset.replace(size=128, format="png")
    except ValueError:
        return asset  # default avatars can't be resized or reformatted


async def get_palette(member: discord.Member) -> Result:
    """Result.data = list of 0xRRGGBB colours from the member's avatar (most prominent first)."""
    asset = palette_avatar(member)
    key = asset.url
    colors = images.cached_palette(key)
    if colors is None:
        try:
            data = await asset.read()
        except (discord.HTTPException, discord.DiscordException, ValueError):
            logger.exception("Couldn't download avatar for palette (%s)", member.id)
            return Result(False, "I couldn't download your avatar right now. Please try again in a moment.")
        try:
            colors = await asyncio.to_thread(images.extract_palette, data)
        except Exception:
            logger.exception("Palette extraction failed for %s", member.id)
            return Result(False, "I couldn't read colors from your avatar.")
        images.remember_palette(key, colors)
    if not colors:
        return Result(False, "I couldn't find any colors in your avatar.")
    return Result(True, "ok", colors)


async def get_info(viewer: discord.Member, target: discord.Member) -> Result:
    """Result.data = (record, role or None) for the target member."""
    _, error = await _check_member(viewer)
    if error:
        return error
    record = await storage.get_custom_role(viewer.guild.id, target.id)
    if record is None:
        if target.id == viewer.id:
            return Result(False, NO_ROLE_MESSAGE)
        return Result(False, f"{target.mention} doesn't have a Lunar role.")
    role = viewer.guild.get_role(record.role_id) if record.role_id else None
    if role is None and record.status == storage.STATUS_ACTIVE:
        await _mark_missing(viewer.guild, target.id, record.role_id, "found deleted by /info")
        record = replace(record, status=storage.STATUS_MISSING, role_id=None)
    return Result(True, "ok", (record, role))


async def _mark_missing(guild: discord.Guild, user_id: int, role_id: Optional[int], why: str) -> None:
    await storage.update_custom_role(guild.id, user_id, status=storage.STATUS_MISSING, role_id=None)
    logger.info("Custom role %s of user %s in guild %s marked missing (%s)", role_id, user_id, guild.id, why)
    await log_event(guild, f"<@{user_id}>'s custom role is missing ({why}). It'll be recreated from saved settings next time they change it.", "warning")


async def handle_role_deleted(role: discord.Role) -> None:
    """on_guild_role_delete: a tracked custom role was deleted outside the bot."""
    guild = role.guild
    record = await storage.get_custom_role_by_role_id(guild.id, role.id)
    if record is not None:
        async with user_lock(guild.id, record.user_id):
            # Re-read under the lock: the bot itself may have just archived this role.
            current = await storage.get_custom_role(guild.id, record.user_id)
            if current and current.role_id == role.id and current.status == storage.STATUS_ACTIVE:
                await _mark_missing(guild, record.user_id, role.id, f"role {role.name!r} deleted in Discord")
        return
    settings = await storage.get_guild_settings(guild.id)
    if settings.anchor_role_id == role.id:
        logger.warning("Lunar anchor role %s was deleted in guild %s; user commands are paused", role.id, guild.id)
        await log_event(
            guild, f"The Lunar anchor role **{role.name}** was deleted, so user commands are paused. "
                   f"Run `/{ADMIN_GROUP} anchor` to pick a new one.", "error", settings,
        )
    if role.id in settings.allowed_role_ids:
        settings = await storage.update_guild_settings(
            guild.id, allowed_role_ids=[r for r in settings.allowed_role_ids if r != role.id]
        )
        await log_event(guild, f"Allowed role **{role.name}** was deleted. Checking who still qualifies.", "warning", settings)
        await archive_ineligible(guild, f"allowed role {role.name!r} was deleted")


# ------------------------------------------------------
# Name rules sweep (existing names that break the filter)
# ------------------------------------------------------

FALLBACK_ROLE_NAME = "Lunar Role"
RENAMED_DM = (
    "Your role name was reset because it contains a blocked word. "
    f"Use /{COMMAND_GROUP} name to choose a new one."
)


@dataclass
class SweepResult:
    renamed: List[Tuple[int, str, str]] = field(default_factory=list)  # (user_id, old name, new name)
    failed: List[Tuple[int, str, str]] = field(default_factory=list)   # (user_id, name, why)


_guild_sweep_locks: Dict[int, asyncio.Lock] = {}


async def names_breaking_rules(guild: discord.Guild) -> List[Tuple[CustomRole, discord.Role, str]]:
    """Active custom roles whose current name fails the name filter: (record, role, reason)."""
    settings = await storage.get_guild_settings(guild.id)
    records = await storage.list_active_roles(guild.id)
    tracked = {r.role_id for r in records}
    breaking = []
    for record in records:
        role = guild.get_role(record.role_id)
        if role is None:
            continue
        _, reason = await _clean_name(guild, role.name, settings, own_role_id=role.id, tracked=tracked)
        if reason:
            breaking.append((record, role, reason))
    return breaking


async def _fallback_name(
    guild: discord.Guild, member: Optional[discord.Member], settings: GuildSettings, role_id: int, tracked: set
) -> str:
    if member is not None:
        candidate = f"{member.name}'s role"
        clean, reason = await _clean_name(guild, candidate, settings, own_role_id=role_id, tracked=tracked)
        if clean and not reason:
            return clean
    return FALLBACK_ROLE_NAME


async def enforce_name_rules(guild: discord.Guild, why: str) -> SweepResult:
    """Rename every active custom role whose name breaks the filter, and DM its owner."""
    result = SweepResult()
    lock = _guild_sweep_locks.setdefault(guild.id, asyncio.Lock())
    async with lock:
        breaking = await names_breaking_rules(guild)
        if not breaking:
            return result
        settings = await storage.get_guild_settings(guild.id)
        tracked = await storage.list_active_role_ids(guild.id)
        for record, _, _ in breaking:
            member = guild.get_member(record.user_id)
            renamed_to = None
            async with user_lock(guild.id, record.user_id):
                current = await storage.get_custom_role(guild.id, record.user_id)
                role = guild.get_role(record.role_id)
                if not current or current.role_id != record.role_id or role is None:
                    continue
                _, reason = await _clean_name(guild, role.name, settings, own_role_id=role.id, tracked=tracked)
                if not reason:
                    continue  # fixed meanwhile
                old_name = role.name
                if role >= guild.me.top_role:
                    result.failed.append((record.user_id, old_name, "role is above my highest role"))
                    continue
                new_name = await _fallback_name(guild, member, settings, role.id, tracked)
                try:
                    await role.edit(name=new_name, reason=f"Lunar Roles: name broke the rules ({why})")
                except discord.Forbidden:
                    result.failed.append((record.user_id, old_name, "missing permission to edit it"))
                    continue
                except discord.HTTPException:
                    logger.exception("Couldn't rename role %s in guild %s", role.id, guild.id)
                    result.failed.append((record.user_id, old_name, "Discord error"))
                    continue
                await storage.update_custom_role(guild.id, record.user_id, name=new_name)
                logger.info("Renamed custom role %s of user %s in guild %s from %r to %r (%s)",
                            role.id, record.user_id, guild.id, old_name, new_name, why)
                result.renamed.append((record.user_id, old_name, new_name))
                renamed_to = new_name
            if renamed_to and member is not None:
                try:
                    await member.send(RENAMED_DM)
                except discord.HTTPException:
                    pass  # DMs closed
    if result.failed:
        logger.warning("Name sweep in guild %s (%s): %s role(s) couldn't be renamed", guild.id, why, len(result.failed))
    if result.renamed or result.failed:
        lines = [f"<@{uid}>: {validation.code(old)} → {validation.code(new)}" for uid, old, new in result.renamed[:15]]
        lines += [f"<@{uid}>: {validation.code(name)} - couldn't rename ({reason})" for uid, name, reason in result.failed[:10]]
        await log_event(
            guild, f"Name check ({why}): renamed {len(result.renamed)}, failed {len(result.failed)}.\n" + "\n".join(lines),
            "warning" if result.failed else "info",
        )
    return result


# ------------------------------------------------------
# Legacy migration
# ------------------------------------------------------

def describe_role_colors(role: discord.Role) -> Tuple[str, Optional[int], Optional[int]]:
    """Return (color_mode, primary, secondary) for a Discord role's current style."""
    primary = role.colour.value or None
    secondary = role.secondary_colour.value if role.secondary_colour else None
    tertiary = role.tertiary_colour.value if role.tertiary_colour else None
    if tertiary is not None and (primary, secondary, tertiary) == HOLOGRAPHIC_COLORS:
        return "holographic", primary, secondary
    if secondary is not None:
        return "gradient", primary, secondary
    return "solid", primary, None


async def hydrate_migrated_roles(bot: discord.Client) -> int:
    """Fill name/colors for rows copied from booster_roles; mark deleted roles missing.

    Rows for servers the bot can't see right now are left for a later run.
    """
    updated = 0
    for record in await storage.list_unhydrated_roles():
        guild = bot.get_guild(record.guild_id)
        if guild is None:
            continue
        try:
            role = guild.get_role(record.role_id)
            if role is None:
                await storage.update_custom_role(
                    record.guild_id, record.user_id, status=storage.STATUS_MISSING, role_id=None
                )
                logger.info("Migrated role %s for user %s in guild %s no longer exists; marked missing",
                            record.role_id, record.user_id, record.guild_id)
            else:
                mode, primary, secondary = describe_role_colors(role)
                await storage.update_custom_role(
                    record.guild_id, record.user_id,
                    name=role.name, color_mode=mode,
                    primary_color=primary, secondary_color=secondary,
                )
                logger.info("Migrated role %s for user %s in guild %s", role.id, record.user_id, record.guild_id)
            updated += 1
        except Exception:
            logger.exception("Failed to migrate role record %s/%s", record.guild_id, record.user_id)
    return updated


# ------------------------------------------------------
# Log channel
# ------------------------------------------------------

_LOG_COLOURS = {
    "info": PALETTE.INFO,
    "success": PALETTE.SUCCESS,
    "warning": PALETTE.WARNING,
    "error": PALETTE.DANGER,
}


async def log_event(
    guild: discord.Guild,
    message: str,
    level: str = "info",
    settings: Optional[GuildSettings] = None,
    view: Optional[discord.ui.View] = None,
) -> Optional[discord.Message]:
    """Post a short line to the guild's Lunar log channel, if one is set. Never raises."""
    try:
        settings = settings or await storage.get_guild_settings(guild.id)
        channel = guild.get_channel(settings.log_channel_id) if settings.log_channel_id else None
        if channel is None:
            return None
        embed = discord.Embed(description=message[:4000], colour=_LOG_COLOURS.get(level, PALETTE.INFO),
                              timestamp=discord.utils.utcnow())
        embed.set_footer(text="Lunar Roles")
        kwargs: Dict[str, Any] = {"embed": embed, "allowed_mentions": discord.AllowedMentions.none()}
        if view is not None:
            kwargs["view"] = view
        return await channel.send(**kwargs)
    except Exception:
        logger.warning("Couldn't post to the Lunar log channel in guild %s", guild.id, exc_info=True)
        return None


# ------------------------------------------------------
# Lifecycle: eligibility, archive (stop boosting) and restore (boost again)
# ------------------------------------------------------

ARCHIVE_BATCH_SIZE = 5       # roles removed per batch when many are processed
ARCHIVE_BATCH_PAUSE = 2.0    # seconds between batches
EVENT_BATCH_SECONDS = 10.0   # member events are collected this long, then handled together
SNOOZE_HOURS = 24
MEMBER_FETCH_TIMEOUT = 60.0

RESTORE_DM = "Welcome back — your role **{name}** is back in **{guild}**."

# archive() results that mean "left alone on purpose", not failures
SKIP_STILL_QUALIFIES = "still qualifies"
SKIP_NOTHING = "nothing to remove"
SKIP_PENDING = "waiting for an admin to confirm"


def mass_archive_threshold() -> int:
    return config.LUNAR_MASS_ARCHIVE_THRESHOLD


def debug_fetch_fail_active() -> bool:
    """LUNAR_DEBUG_FAIL_MEMBER_FETCH is honoured only in development (the default ENVIRONMENT)."""
    return config.LUNAR_DEBUG_FAIL_MEMBER_FETCH and os.getenv("ENVIRONMENT", "development") == "development"


def is_eligible(member: discord.Member, settings: GuildSettings) -> bool:
    return ensure_eligible(member, settings).ok


def archive_blocker(guild: discord.Guild) -> Optional[str]:
    """Why roles can't be removed in this guild right now, or None."""
    if guild.unavailable:
        return "the server is unavailable"
    me = guild.me
    if me is None or not me.guild_permissions.manage_roles:
        return "I'm missing the Manage Roles permission"
    return None


async def member_data_problem(guild: discord.Guild) -> Optional[str]:
    """Why the member list can't be trusted right now (so nobody may be treated as ineligible), or None."""
    if guild.unavailable:
        return "the server is unavailable"
    if debug_fetch_fail_active():
        return "the member list is incomplete (LUNAR_DEBUG_FAIL_MEMBER_FETCH is on)"
    if not guild.chunked:
        try:
            await asyncio.wait_for(guild.chunk(cache=True), timeout=MEMBER_FETCH_TIMEOUT)
        except asyncio.TimeoutError:
            return "the member list timed out while loading"
        except (discord.HTTPException, discord.ClientException) as exc:
            return f"the member list couldn't be loaded ({type(exc).__name__})"
    if not guild.chunked:
        return "the member list is incomplete"
    return None


@dataclass
class ArchiveReport:
    archived: List[Tuple[int, str]] = field(default_factory=list)  # (user_id, role name)
    skipped: List[Tuple[int, str]] = field(default_factory=list)   # (user_id, why)
    failed: List[Tuple[int, str]] = field(default_factory=list)    # (user_id, why)

    def summary(self) -> str:
        return f"Removed {len(self.archived)}, skipped {len(self.skipped)}, failed {len(self.failed)}."


async def archive(
    guild: discord.Guild, user_id: int, reason: str, *,
    respect_pending: bool = True, settings: Optional[GuildSettings] = None,
) -> Result:
    """Delete a member's custom role and keep its settings as 'saved'.

    Re-checks eligibility first, so a member who qualifies again is never archived.
    """
    blocker = archive_blocker(guild)
    if blocker:
        return Result(False, blocker)
    settings = settings or await storage.get_guild_settings(guild.id)
    member = guild.get_member(user_id)
    if member is not None and is_eligible(member, settings):
        return Result(False, SKIP_STILL_QUALIFIES)
    if respect_pending and user_id in await storage.pending_user_ids(guild.id):
        return Result(False, SKIP_PENDING)

    async with user_lock(guild.id, user_id):
        record = await storage.get_custom_role(guild.id, user_id)
        if record is None or record.status == storage.STATUS_SAVED:
            return Result(False, SKIP_NOTHING)
        role = guild.get_role(record.role_id) if record.role_id else None
        fields: Dict[str, Any] = {"status": storage.STATUS_SAVED, "role_id": None}
        name = record.name or (role.name if role else None)
        if role is not None:
            if role >= guild.me.top_role:
                return Result(False, "their role is above my highest role")
            fields["position_hint"] = role.position
            fields["name"] = name = role.name
            if record.icon_png is None and record.icon_emoji is None:
                # Keep an icon set outside the bot so restore can re-apply it.
                if isinstance(role.display_icon, discord.Asset):
                    try:
                        fields["icon_png"] = await role.display_icon.read()
                    except discord.HTTPException:
                        logger.warning("Couldn't download icon of role %s before archiving", role.id)
                elif isinstance(role.display_icon, str):
                    fields["icon_emoji"] = role.display_icon
            _, error = await _discord(guild, f"removing role {role.id} of <@{user_id}>", role.delete(reason=f"Lunar Roles: {reason}"))
            if error:
                return Result(False, "Discord refused to delete it")
        await storage.update_custom_role(guild.id, user_id, **fields)
    logger.info("Archived role of user %s in guild %s (%s)", user_id, guild.id, reason)
    return Result(True, name or "unnamed")


async def restore(member: discord.Member, settings: Optional[GuildSettings] = None, dm: bool = True) -> Result:
    """Recreate a saved role for a member who qualifies again. Only while the feature is set up."""
    guild = member.guild
    settings = settings or await storage.get_guild_settings(guild.id)
    if not ensure_ready(guild, settings).ok:
        return Result(False, "not set up")
    if not is_eligible(member, settings):
        return Result(False, "doesn't qualify")
    async with user_lock(guild.id, member.id):
        record = await storage.get_custom_role(guild.id, member.id)
        if record is None or record.status != storage.STATUS_SAVED or not record.name:
            return Result(False, "nothing saved")
        role, notes, error = await _create_discord_role(
            member, settings, replace(record, status=storage.STATUS_ACTIVE, role_id=None)
        )
        if error:
            await log_event(guild, f"Couldn't restore {member.mention}'s role: {error.message}", "error", settings)
            return error
    logger.info("Restored role %s for %s in guild %s", role.id, member.id, guild.id)
    await log_event(guild, f"Restored {member.mention}'s role {role.mention} from saved settings.", "success", settings)
    if dm:
        try:
            await member.send(RESTORE_DM.format(name=role.name, guild=guild.name))
        except discord.HTTPException:
            pass  # DMs closed
    return Result(True, f"Restored **{role.name}**.", role, notes)


async def restore_saved(guild: discord.Guild) -> int:
    """Restore every saved role whose member qualifies again (e.g. after enable or allow-role add)."""
    settings = await storage.get_guild_settings(guild.id)
    if not ensure_ready(guild, settings).ok or archive_blocker(guild):
        return 0  # the blocker was already reported by the archive step
    restored = 0
    for record in await storage.list_roles(guild.id):
        if record.status != storage.STATUS_SAVED:
            continue
        member = guild.get_member(record.user_id)
        if member is not None and is_eligible(member, settings):
            if (await restore(member, settings)).ok:
                restored += 1
    return restored


ProgressCallback = Callable[[int, int, "ArchiveReport"], Awaitable[None]]


async def process_archives(
    guild: discord.Guild, reasons: Dict[int, str], *,
    respect_pending: bool = True, progress: Optional[ProgressCallback] = None, log_title: str = "",
) -> ArchiveReport:
    """Archive members gradually (small batches with pauses) and post one summary to the log channel."""
    report = ArchiveReport()
    settings = await storage.get_guild_settings(guild.id)
    user_ids = list(reasons)
    total = len(user_ids)
    for start in range(0, total, ARCHIVE_BATCH_SIZE):
        for user_id in user_ids[start:start + ARCHIVE_BATCH_SIZE]:
            result = await archive(guild, user_id, reasons[user_id], respect_pending=respect_pending, settings=settings)
            if result.ok:
                report.archived.append((user_id, result.message))
            elif result.message in (SKIP_STILL_QUALIFIES, SKIP_NOTHING, SKIP_PENDING):
                report.skipped.append((user_id, result.message))
            else:
                report.failed.append((user_id, result.message))
        done = min(start + ARCHIVE_BATCH_SIZE, total)
        if progress is not None:
            await progress(done, total, report)
        if done < total:
            await asyncio.sleep(ARCHIVE_BATCH_PAUSE)

    if report.archived or report.failed:
        lines = [f"<@{uid}>: {validation.code(name)} ({reasons[uid]})" for uid, name in report.archived[:20]]
        if len(report.archived) > 20:
            lines.append(f"…and {len(report.archived) - 20} more")
        lines += [f"<@{uid}>: couldn't remove ({why})" for uid, why in report.failed[:10]]
        title = log_title or "Removed custom roles"
        await log_event(guild, f"**{title}.** {report.summary()} Settings were saved.\n" + "\n".join(lines),
                        "warning" if report.failed else "info", settings)
    return report


# ------------------------------------------------------
# Mass-removal guard for automatic removals (events and reconcile)
# ------------------------------------------------------

# Set by the cog: builds the Confirm/Cancel view for a pending removal id.
pending_view_factory: Optional[Callable[[int], discord.ui.View]] = None

_skip_warned: Dict[int, str] = {}


async def _warn_skip(guild: discord.Guild, problem: str, count: int) -> None:
    logger.warning("Skipped archiving %s role(s) in guild %s: %s", count, guild.id, problem)
    if _skip_warned.get(guild.id) != problem:  # tell the channel once per new problem, not every run
        _skip_warned[guild.id] = problem
        await log_event(
            guild, f"Skipped removing {count} custom role(s) because {problem}. I'll try again on the next check.",
            "warning",
        )


def pending_text(pending: storage.PendingRemoval, threshold: int) -> str:
    members = ", ".join(f"<@{u}>" for u in pending.user_ids[:25])
    if len(pending.user_ids) > 25:
        members += f" and {len(pending.user_ids) - 25} more"
    return (
        f"⚠️ **{len(pending.user_ids)} custom role(s)** are waiting to be removed ({pending.reason}).\n"
        f"That's more than the safety limit of {threshold}, so nothing has been removed yet.\n\n"
        f"**Members:** {members}\n\n"
        f"**Confirm** removes them (settings are saved, so they come back if they qualify again). "
        f"**Cancel** keeps them and asks again in {SNOOZE_HOURS} hours if they still don't qualify. "
        f"You can also use `/{ADMIN_GROUP} pending`."
    )


async def _open_or_extend_pending(guild: discord.Guild, user_ids: List[int], reason: str) -> storage.PendingRemoval:
    existing = await storage.get_open_pending(guild.id)
    threshold = mass_archive_threshold()
    if existing is not None:
        merged = sorted(set(existing.user_ids) | set(user_ids))
        if merged != existing.user_ids:
            await storage.update_pending(existing.id, user_ids=merged)
            existing = await storage.get_pending(existing.id)
            await _refresh_alert(guild, existing, pending_text(existing, threshold), keep_buttons=True)
            logger.warning("Pending removal %s in guild %s now has %s member(s)", existing.id, guild.id, len(merged))
        return existing

    pending = await storage.create_pending(guild.id, user_ids, reason)
    logger.warning("Holding %s removal(s) in guild %s for admin confirmation (pending %s): %s",
                   len(pending.user_ids), guild.id, pending.id, reason)
    view = pending_view_factory(pending.id) if pending_view_factory else None
    message = await log_event(guild, pending_text(pending, threshold), "warning", view=view)
    if message is not None:
        await storage.update_pending(pending.id, log_channel_id=message.channel.id, log_message_id=message.id)
    return pending


async def _refresh_alert(guild: discord.Guild, pending: storage.PendingRemoval, text: str, keep_buttons: bool) -> None:
    """Edit the log-channel alert of a pending removal (if it was posted)."""
    if not pending.log_channel_id or not pending.log_message_id:
        return
    channel = guild.get_channel(pending.log_channel_id)
    if channel is None:
        return
    embed = discord.Embed(description=text[:4000], colour=PALETTE.WARNING if keep_buttons else PALETTE.NEUTRAL,
                          timestamp=discord.utils.utcnow())
    embed.set_footer(text="Lunar Roles")
    view = pending_view_factory(pending.id) if keep_buttons and pending_view_factory else None
    try:
        await channel.get_partial_message(pending.log_message_id).edit(embed=embed, view=view)
    except discord.HTTPException:
        logger.warning("Couldn't update pending alert %s in guild %s", pending.id, guild.id)


async def archive_automatically(guild: discord.Guild, reasons: Dict[int, str], why: str) -> Optional[Any]:
    """Archive members found by events or reconcile, holding mass removals for an admin.

    Members in an open pending removal or a running snooze are left alone. Members
    whose snooze ran out are always asked about again (never removed silently).
    Returns the PendingRemoval, an ArchiveReport, or None if nothing was done.
    """
    blocker = archive_blocker(guild)
    if blocker:
        await _warn_skip(guild, blocker, len(reasons))
        return None
    _skip_warned.pop(guild.id, None)

    open_pending = await storage.get_open_pending(guild.id)
    held = set(open_pending.user_ids) if open_pending else set()
    snoozed = await storage.snoozed_user_ids(guild.id)
    expired = await storage.expired_snooze_user_ids(guild.id)
    candidates = {u: r for u, r in reasons.items() if u not in held and u not in snoozed}
    if not candidates:
        return None

    # Hold everything while a removal is already pending (an ongoing mass event), or when
    # this batch plus recent automatic removals goes over the limit (catches slow strips).
    recent = _recent_automatic(guild.id)
    if open_pending is not None or recent + len(candidates) > mass_archive_threshold():
        ask, now = list(candidates), {}
    else:
        ask = [u for u in candidates if u in expired]
        now = {u: r for u, r in candidates.items() if u not in expired}

    pending = None
    if ask:
        await storage.clear_snoozes(guild.id, ask)  # this is the "ask once more"
        pending = await _open_or_extend_pending(guild, ask, why)
    report = None
    if now:
        report = await process_archives(guild, now, log_title=f"Removed custom roles ({why})")
        _note_automatic(guild.id, len(report.archived))
    return pending or report


RECENT_WINDOW_SECONDS = 600.0
_recent_archives: Dict[int, List[float]] = {}


def _recent_automatic(guild_id: int) -> int:
    """Automatic removals in this guild during the last RECENT_WINDOW_SECONDS."""
    cutoff = time.monotonic() - RECENT_WINDOW_SECONDS
    stamps = [t for t in _recent_archives.get(guild_id, []) if t > cutoff]
    _recent_archives[guild_id] = stamps
    return len(stamps)


def _note_automatic(guild_id: int, count: int) -> None:
    now = time.monotonic()
    _recent_archives.setdefault(guild_id, []).extend([now] * count)


async def confirm_pending(guild: discord.Guild, pending_id: int, admin: discord.abc.User,
                          progress: Optional[ProgressCallback] = None) -> Result:
    pending = await storage.get_pending(pending_id)
    if pending is None or pending.guild_id != guild.id:
        return Result(False, "That pending removal doesn't exist.")
    if not await storage.resolve_pending(pending_id, storage.PENDING_CONFIRMED, admin.id):
        return Result(False, "That pending removal was already handled.")
    logger.info("Pending removal %s in guild %s confirmed by %s", pending_id, guild.id, admin.id)
    await _refresh_alert(guild, pending, f"✅ Confirmed by {admin.mention}. Removing {len(pending.user_ids)} role(s)…", False)
    report = await process_archives(
        guild, {u: pending.reason for u in pending.user_ids}, respect_pending=False, progress=progress,
        log_title=f"Pending removal confirmed by {admin}",
    )
    await _refresh_alert(guild, pending, f"✅ Confirmed by {admin.mention}. {report.summary()}", False)
    return Result(True, report.summary(), report)


async def cancel_pending(guild: discord.Guild, pending_id: int, admin: discord.abc.User) -> Result:
    pending = await storage.get_pending(pending_id)
    if pending is None or pending.guild_id != guild.id:
        return Result(False, "That pending removal doesn't exist.")
    if not await storage.resolve_pending(pending_id, storage.PENDING_CANCELLED, admin.id):
        return Result(False, "That pending removal was already handled.")
    await storage.snooze_users(guild.id, pending.user_ids, SNOOZE_HOURS)
    logger.info("Pending removal %s in guild %s cancelled by %s", pending_id, guild.id, admin.id)
    text = (f"❎ Cancelled by {admin.mention}. Kept {len(pending.user_ids)} role(s); "
            f"I'll ask again in {SNOOZE_HOURS} hours if they still don't qualify.")
    await _refresh_alert(guild, pending, text, False)
    await log_event(guild, text, "info")
    return Result(True, f"Kept {len(pending.user_ids)} role(s). I'll ask again in {SNOOZE_HOURS} hours if they still don't qualify.")


# ------------------------------------------------------
# Member events are batched per guild so bursts hit the guard
# ------------------------------------------------------

_event_queue: Dict[int, Dict[int, str]] = {}
_event_tasks: Dict[int, asyncio.Task] = {}


def queue_archive(guild: discord.Guild, user_id: int, reason: str) -> None:
    """Archive a member soon. Events within EVENT_BATCH_SECONDS are handled together."""
    _event_queue.setdefault(guild.id, {})[user_id] = reason
    task = _event_tasks.get(guild.id)
    if task is None or task.done():
        _event_tasks[guild.id] = asyncio.create_task(_flush_events_later(guild))


def unqueue_archive(guild_id: int, user_id: int) -> None:
    _event_queue.get(guild_id, {}).pop(user_id, None)


async def _flush_events_later(guild: discord.Guild) -> None:
    await asyncio.sleep(EVENT_BATCH_SECONDS)
    reasons = _event_queue.pop(guild.id, {})
    if not reasons:
        return
    why = "members stopped qualifying" if len(reasons) > 1 else next(iter(reasons.values()))
    try:
        await archive_automatically(guild, reasons, why)
    except Exception:
        logger.exception("Handling queued removals failed in guild %s", guild.id)


# ------------------------------------------------------
# Reconcile (startup + every LUNAR_RECONCILE_MINUTES)
# ------------------------------------------------------

def _ineligible_reasons(guild: discord.Guild, settings: GuildSettings, records: List[CustomRole]) -> Dict[int, str]:
    reasons = {}
    for record in records:
        if record.status not in (storage.STATUS_ACTIVE, storage.STATUS_MISSING):
            continue
        member = guild.get_member(record.user_id)
        if member is None:
            reasons[record.user_id] = "left the server"
        elif not is_eligible(member, settings):
            reasons[record.user_id] = "no longer boosting or allowed"
    return reasons


async def archive_ineligible(guild: discord.Guild, why: str) -> Optional[Any]:
    """Find members who no longer qualify and archive them (guarded). Skips on untrustworthy data."""
    problem = await member_data_problem(guild)
    settings = await storage.get_guild_settings(guild.id)
    reasons = _ineligible_reasons(guild, settings, await storage.list_roles(guild.id))
    if not reasons:
        _skip_warned.pop(guild.id, None)
        return None
    if problem:
        await _warn_skip(guild, problem, len(reasons))
        return None
    return await archive_automatically(guild, reasons, why)


async def reconcile_guild(guild: discord.Guild) -> None:
    """Fix anything missed while the bot was offline or events were lost."""
    records = await storage.list_roles(guild.id)
    if not records:
        return
    for record in records:
        if record.status == storage.STATUS_ACTIVE and record.role_id and guild.get_role(record.role_id) is None:
            async with user_lock(guild.id, record.user_id):
                current = await storage.get_custom_role(guild.id, record.user_id)
                if current and current.status == storage.STATUS_ACTIVE and current.role_id == record.role_id:
                    await _mark_missing(guild, record.user_id, record.role_id, "deleted while I was offline")
    await archive_ineligible(guild, "found during the regular check")
    await restore_saved(guild)


async def preview_allowed_role_removal(guild: discord.Guild, role: discord.Role) -> List[int]:
    """Members whose custom role would be removed if `role` stopped granting access."""
    settings = await storage.get_guild_settings(guild.id)
    after = replace(settings, allowed_role_ids=[r for r in settings.allowed_role_ids if r != role.id])
    affected = []
    for record in await storage.list_roles(guild.id):
        if record.status not in (storage.STATUS_ACTIVE, storage.STATUS_MISSING):
            continue
        member = guild.get_member(record.user_id)
        if member is not None and is_eligible(member, settings) and not is_eligible(member, after):
            affected.append(record.user_id)
    return affected
