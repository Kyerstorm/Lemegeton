"""Lunar Roles service layer: the one place that decides and applies role changes.

Slash commands, the web API and automatic events all call these functions.
Expected failures come back as a Result with a user-facing message; nothing
here raises to the caller for them.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field, replace
from typing import Any, Dict, List, Optional, Tuple

import discord

from helpers.logging_helper import get_logger
from helpers.lunar_roles import (
    ADMIN_GROUP,
    COMMAND_GROUP,
    FEATURE_GRADIENT,
    FEATURE_ICONS,
    HOLOGRAPHIC_COLORS,
    ROLE_LIMIT,
)
from helpers.lunar_roles import storage, validation
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

async def _discord(action: str, coro) -> Tuple[Any, Optional[Result]]:
    """Await a Discord call, turning expected failures into a Result."""
    try:
        return await coro, None
    except discord.Forbidden:
        logger.warning("Forbidden while %s", action)
        return None, Result(False, PERMISSION_MESSAGE)
    except discord.HTTPException:
        logger.exception("Discord API error while %s", action)
        return None, Result(False, API_ERROR_MESSAGE)


async def _check_member(member: discord.Member) -> Tuple[Optional[GuildSettings], Optional[Result]]:
    settings = await storage.get_guild_settings(member.guild.id)
    for check in (ensure_ready(member.guild, settings), ensure_eligible(member, settings)):
        if not check.ok:
            return settings, check
    return settings, None


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
    if record.icon_png and FEATURE_ICONS in guild.features:
        style["display_icon"] = record.icon_png

    role, error = await _discord(
        f"creating role for {member.id} in {guild.id}",
        guild.create_role(
            name=record.name,
            permissions=discord.Permissions.none(),
            reason=f"Lunar Roles: custom role for {member} ({member.id})",
            **style,
        ),
    )
    if error:
        return None, None, error

    # Save first so the role is never left untracked.
    await storage.upsert_custom_role(replace(record, role_id=role.id, status=storage.STATUS_ACTIVE))

    positions = None
    try:
        positions = await _place_by_anchor(guild, role, anchor.id, settings.anchor_place)
    except discord.HTTPException:
        logger.exception("Couldn't place role %s %s anchor %s in guild %s", role.id, settings.anchor_place, anchor.id, guild.id)
        notes.append(f"I couldn't move it into place - an admin may need to drag it {settings.anchor_place} the anchor.")

    _, error = await _discord(f"assigning role {role.id} to {member.id}", member.add_roles(role, reason="Lunar Roles"))
    if error:
        return role, notes, Result(False, f"Your role was created, but I couldn't give it to you. Try `/{COMMAND_GROUP} assign`.")
    # The cached positions may lag; use the ones we just set.
    if positions is not None and has_colour(role):
        hidden = hidden_colour_notice(member, role, positions)
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
        await _mark_missing(guild.id, member.id, record.role_id, "found deleted while changing it")

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
    else:
        message = f"Created **{role.name}** and gave it to you. Color it with `/{COMMAND_GROUP} color set`."
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
        role, created, notes, error = await _ensure_live_role(member, record, settings, name=clean)
        if error:
            return error
        if not created:
            _, error = await _discord(f"renaming role {role.id}", role.edit(name=clean, reason=f"Lunar Roles: renamed by {member}"))
            if error:
                return error
        await storage.update_custom_role(guild.id, member.id, changed=True, name=clean)
    logger.info("Renamed role %s for %s in guild %s", role.id, member.id, guild.id)
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
            _, error = await _discord(f"recoloring role {role.id}", role.edit(reason=f"Lunar Roles: recolored by {member}", **style))
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
        _, error = await _discord(f"assigning role {role.id}", member.add_roles(role, reason="Lunar Roles: assign"))
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
        _, error = await _discord(f"unassigning role {role.id}", member.remove_roles(role, reason="Lunar Roles: unassign"))
        if error:
            return error
    return Result(
        True, f"Took **{role.name}** off you. It's still yours - use `/{COMMAND_GROUP} assign` to wear it again.", role
    )


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
        await _mark_missing(viewer.guild.id, target.id, record.role_id, "found deleted by /info")
        record = replace(record, status=storage.STATUS_MISSING, role_id=None)
    return Result(True, "ok", (record, role))


async def _mark_missing(guild_id: int, user_id: int, role_id: Optional[int], why: str) -> None:
    await storage.update_custom_role(guild_id, user_id, status=storage.STATUS_MISSING, role_id=None)
    logger.info("Custom role %s of user %s in guild %s marked missing (%s)", role_id, user_id, guild_id, why)


async def handle_role_deleted(role: discord.Role) -> None:
    """on_guild_role_delete: a tracked custom role was deleted outside the bot."""
    guild = role.guild
    record = await storage.get_custom_role_by_role_id(guild.id, role.id)
    if record is not None:
        async with user_lock(guild.id, record.user_id):
            # Re-read under the lock: the bot itself may have just archived this role.
            current = await storage.get_custom_role(guild.id, record.user_id)
            if current and current.role_id == role.id and current.status == storage.STATUS_ACTIVE:
                await _mark_missing(guild.id, record.user_id, role.id, f"role {role.name!r} deleted in Discord")
        return
    settings = await storage.get_guild_settings(guild.id)
    if settings.anchor_role_id == role.id:
        logger.warning("Lunar anchor role %s was deleted in guild %s; user commands are paused", role.id, guild.id)


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
