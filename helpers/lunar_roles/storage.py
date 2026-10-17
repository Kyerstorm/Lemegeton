"""Database access for Lunar Roles (PostgreSQL via execute_db_operation)."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional

from database import execute_db_operation

STATUS_ACTIVE = "active"
STATUS_SAVED = "saved"
STATUS_MISSING = "missing"


@dataclass
class GuildSettings:
    guild_id: int
    enabled: bool = False
    anchor_role_id: Optional[int] = None
    command_channel_id: Optional[int] = None
    log_channel_id: Optional[int] = None
    cooldown_seconds: int = 0
    allowed_role_ids: List[int] = field(default_factory=list)
    blocked_words: List[str] = field(default_factory=list)


@dataclass
class CustomRole:
    guild_id: int
    user_id: int
    role_id: Optional[int]
    status: str
    name: Optional[str]
    color_mode: str
    primary_color: Optional[int]
    secondary_color: Optional[int]
    icon_png: Optional[bytes]
    position_hint: Optional[int]
    last_changed_at: Optional[datetime]
    created_at: Optional[datetime]
    updated_at: Optional[datetime]


_SETTINGS_COLUMNS = (
    "enabled",
    "anchor_role_id",
    "command_channel_id",
    "log_channel_id",
    "cooldown_seconds",
    "allowed_role_ids",
    "blocked_words",
)
_JSON_SETTINGS = {"allowed_role_ids", "blocked_words"}

_ROLE_COLUMNS = (
    "guild_id",
    "user_id",
    "role_id",
    "status",
    "name",
    "color_mode",
    "primary_color",
    "secondary_color",
    "icon_png",
    "position_hint",
    "last_changed_at",
    "created_at",
    "updated_at",
)
_ROLE_SELECT = ", ".join(_ROLE_COLUMNS)
_ROLE_UPDATABLE = set(_ROLE_COLUMNS) - {"guild_id", "user_id", "created_at", "updated_at"}


def _load_json_list(raw) -> list:
    try:
        value = json.loads(raw or "[]")
    except (TypeError, ValueError):
        return []
    return value if isinstance(value, list) else []


def _row_to_role(row) -> CustomRole:
    values = {column: row[index] for index, column in enumerate(_ROLE_COLUMNS)}
    if values["icon_png"] is not None:
        values["icon_png"] = bytes(values["icon_png"])
    return CustomRole(**values)


# ------------------------------------------------------
# Guild settings
# ------------------------------------------------------

async def get_guild_settings(guild_id: int) -> GuildSettings:
    """Return the guild's settings, or the defaults (feature off) if none are stored."""
    row = await execute_db_operation(
        "get lunar guild settings",
        f"SELECT {', '.join(_SETTINGS_COLUMNS)} FROM lunar_guild_settings WHERE guild_id = ?",
        (guild_id,),
        fetch_type="one",
    )
    if not row:
        return GuildSettings(guild_id=guild_id)
    return GuildSettings(
        guild_id=guild_id,
        enabled=bool(row[0]),
        anchor_role_id=row[1],
        command_channel_id=row[2],
        log_channel_id=row[3],
        cooldown_seconds=int(row[4] or 0),
        allowed_role_ids=[int(r) for r in _load_json_list(row[5])],
        blocked_words=[str(w) for w in _load_json_list(row[6])],
    )


async def update_guild_settings(guild_id: int, **fields) -> GuildSettings:
    """Upsert the given settings columns and return the updated settings."""
    unknown = set(fields) - set(_SETTINGS_COLUMNS)
    if unknown:
        raise ValueError(f"Unknown Lunar settings: {', '.join(sorted(unknown))}")
    if not fields:
        return await get_guild_settings(guild_id)

    columns = list(fields)
    values = []
    for column in columns:
        value = fields[column]
        if column in _JSON_SETTINGS:
            value = json.dumps(list(value))
        elif column == "enabled":
            value = bool(value)
        values.append(value)

    placeholders = ", ".join("?" for _ in columns)
    assignments = ", ".join(f"{column} = excluded.{column}" for column in columns)
    await execute_db_operation(
        "update lunar guild settings",
        f"""
        INSERT INTO lunar_guild_settings (guild_id, {', '.join(columns)}, updated_at)
        VALUES (?, {placeholders}, CURRENT_TIMESTAMP)
        ON CONFLICT (guild_id) DO UPDATE SET {assignments}, updated_at = CURRENT_TIMESTAMP
        """,
        (guild_id, *values),
    )
    return await get_guild_settings(guild_id)


# ------------------------------------------------------
# Custom roles
# ------------------------------------------------------

async def update_custom_role(guild_id: int, user_id: int, **fields) -> None:
    """Update columns on an existing record."""
    unknown = set(fields) - _ROLE_UPDATABLE
    if unknown:
        raise ValueError(f"Unknown Lunar role columns: {', '.join(sorted(unknown))}")
    if not fields:
        return
    assignments = ", ".join(f"{column} = ?" for column in fields)
    await execute_db_operation(
        "update lunar custom role",
        f"UPDATE lunar_custom_roles SET {assignments}, updated_at = CURRENT_TIMESTAMP "
        "WHERE guild_id = ? AND user_id = ?",
        (*fields.values(), guild_id, user_id),
    )


async def list_unhydrated_roles() -> List[CustomRole]:
    """Records copied from booster_roles whose name/colors haven't been read from Discord yet."""
    rows = await execute_db_operation(
        "list unhydrated lunar roles",
        f"SELECT {_ROLE_SELECT} FROM lunar_custom_roles "
        "WHERE status = ? AND name IS NULL AND role_id IS NOT NULL",
        (STATUS_ACTIVE,),
        fetch_type="all",
    )
    return [_row_to_role(row) for row in rows or []]


async def count_roles_by_status(guild_id: int) -> Dict[str, int]:
    rows = await execute_db_operation(
        "count lunar roles by status",
        "SELECT status, COUNT(*) FROM lunar_custom_roles WHERE guild_id = ? GROUP BY status",
        (guild_id,),
        fetch_type="all",
    )
    counts = {STATUS_ACTIVE: 0, STATUS_SAVED: 0, STATUS_MISSING: 0}
    for status, count in rows or []:
        counts[status] = int(count)
    return counts
