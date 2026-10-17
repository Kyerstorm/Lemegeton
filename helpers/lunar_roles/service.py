"""Lunar Roles service layer: the one place that decides and applies role changes.

Slash commands, the web API and automatic events all call these functions.
Expected failures come back as a Result with a user-facing message; nothing
here raises to the caller for them.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

import discord

from helpers.logging_helper import get_logger
from helpers.lunar_roles import (
    ADMIN_GROUP,
    FEATURE_GRADIENT,
    FEATURE_ICONS,
    HOLOGRAPHIC_COLORS,
    ROLE_LIMIT,
)
from helpers.lunar_roles import storage
from helpers.lunar_roles.storage import GuildSettings

logger = get_logger("LunarRoles", logfile="lunar_roles.log")

NOT_SET_UP_MESSAGE = (
    "Lunar Roles isn't set up yet in this server. "
    f"Ask an admin to run `/{ADMIN_GROUP} anchor` and `/{ADMIN_GROUP} enable`."
)


@dataclass
class Result:
    ok: bool
    message: str
    data: Any = None


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
    return Result(True, f"Custom roles will be placed directly below {role.mention}.")


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

async def set_anchor(guild: discord.Guild, role: discord.Role) -> Result:
    check = validate_anchor(guild, role)
    if not check.ok:
        return check
    settings = await storage.update_guild_settings(guild.id, anchor_role_id=role.id)
    logger.info("Guild %s anchor set to role %s", guild.id, role.id)
    return Result(True, check.message, settings)


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
