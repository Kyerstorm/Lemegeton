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
    anchor_place: str = "below"  # custom roles go "below" or "above" the anchor
    removed_default_words: List[str] = field(default_factory=list)  # built-in protected words switched off


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
    icon_emoji: Optional[str] = None  # a Unicode emoji icon; only one of icon_png / icon_emoji is set
    icon_source: Optional[bytes] = None  # the original image as uploaded (icon_png is cut from it)
    icon_crop: Optional[str] = None      # JSON {"x", "y", "size"}: the square cut from icon_source


_SETTINGS_COLUMNS = (
    "enabled",
    "anchor_role_id",
    "command_channel_id",
    "log_channel_id",
    "cooldown_seconds",
    "allowed_role_ids",
    "blocked_words",
    "anchor_place",
    "removed_default_words",
)
_JSON_SETTINGS = {"allowed_role_ids", "blocked_words", "removed_default_words"}

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
    "icon_emoji",
    "icon_source",
    "icon_crop",
)
_ROLE_SELECT = ", ".join(_ROLE_COLUMNS)
# Lists never need the images (an original can be several MB), so they read NULL instead.
# Records from these lists must never be written back with upsert_custom_role.
_IMAGE_COLUMNS = {"icon_png", "icon_source"}
_ROLE_SELECT_LIGHT = ", ".join(f"NULL AS {c}" if c in _IMAGE_COLUMNS else c for c in _ROLE_COLUMNS)
# Only update_custom_role writes these (upserts keep whatever is stored).
_UPSERT_SKIP = {"created_at", "updated_at", "last_changed_at", "icon_source", "icon_crop"}
_ROLE_UPDATABLE = set(_ROLE_COLUMNS) - {"guild_id", "user_id", "created_at", "updated_at"}


def _load_json_list(raw) -> list:
    try:
        value = json.loads(raw or "[]")
    except (TypeError, ValueError):
        return []
    return value if isinstance(value, list) else []


def _row_to_role(row) -> CustomRole:
    values = {column: row[index] for index, column in enumerate(_ROLE_COLUMNS)}
    for column in ("icon_png", "icon_source"):
        if values[column] is not None:
            values[column] = bytes(values[column])
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
        anchor_place=row[7] or "below",
        removed_default_words=[str(w) for w in _load_json_list(row[8])],
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

async def get_custom_role(guild_id: int, user_id: int) -> Optional[CustomRole]:
    row = await execute_db_operation(
        "get lunar custom role",
        f"SELECT {_ROLE_SELECT} FROM lunar_custom_roles WHERE guild_id = ? AND user_id = ?",
        (guild_id, user_id),
        fetch_type="one",
    )
    return _row_to_role(row) if row else None


async def get_custom_role_by_role_id(guild_id: int, role_id: int) -> Optional[CustomRole]:
    row = await execute_db_operation(
        "get lunar custom role by role id",
        f"SELECT {_ROLE_SELECT_LIGHT} FROM lunar_custom_roles WHERE guild_id = ? AND role_id = ?",
        (guild_id, role_id),
        fetch_type="one",
    )
    return _row_to_role(row) if row else None


async def upsert_custom_role(record: CustomRole) -> None:
    """Insert or fully replace a member's record (keeps created_at on update).

    Creating or restoring a role isn't a "change" for the cooldown, so
    last_changed_at is left as it was (NULL for a new record).
    """
    columns = [c for c in _ROLE_COLUMNS if c not in _UPSERT_SKIP]
    values = [getattr(record, c) for c in columns]
    assignments = ", ".join(
        f"{c} = excluded.{c}" for c in columns if c not in {"guild_id", "user_id"}
    )
    await execute_db_operation(
        "upsert lunar custom role",
        f"""
        INSERT INTO lunar_custom_roles ({', '.join(columns)}, created_at, updated_at)
        VALUES ({', '.join('?' for _ in columns)}, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        ON CONFLICT (guild_id, user_id) DO UPDATE SET {assignments},
            updated_at = CURRENT_TIMESTAMP
        """,
        tuple(values),
    )


async def delete_custom_role(guild_id: int, user_id: int) -> None:
    await execute_db_operation(
        "delete lunar custom role",
        "DELETE FROM lunar_custom_roles WHERE guild_id = ? AND user_id = ?",
        (guild_id, user_id),
    )


async def seconds_since_change(guild_id: int, user_id: int) -> Optional[float]:
    """Seconds since the member last changed their role, or None if never.

    Worked out in the database: last_changed_at is a TIMESTAMP in the database's
    own time zone, which may not match the bot's.
    """
    row = await execute_db_operation(
        "lunar seconds since last change",
        "SELECT EXTRACT(EPOCH FROM (CURRENT_TIMESTAMP - last_changed_at)) "
        "FROM lunar_custom_roles WHERE guild_id = ? AND user_id = ?",
        (guild_id, user_id),
        fetch_type="one",
    )
    if not row or row[0] is None:
        return None
    return float(row[0])


async def list_active_roles(guild_id: int) -> List[CustomRole]:
    rows = await execute_db_operation(
        "list lunar active roles",
        f"SELECT {_ROLE_SELECT_LIGHT} FROM lunar_custom_roles "
        "WHERE guild_id = ? AND status = ? AND role_id IS NOT NULL",
        (guild_id, STATUS_ACTIVE),
        fetch_type="all",
    )
    return [_row_to_role(row) for row in rows or []]


async def list_guilds_with_active_roles() -> List[int]:
    rows = await execute_db_operation(
        "list guilds with lunar roles",
        "SELECT DISTINCT guild_id FROM lunar_custom_roles WHERE status = ? AND role_id IS NOT NULL",
        (STATUS_ACTIVE,),
        fetch_type="all",
    )
    return [int(row[0]) for row in rows or []]


async def list_active_role_ids(guild_id: int) -> set:
    """Discord role IDs currently tracked as custom roles in a guild."""
    rows = await execute_db_operation(
        "list lunar active role ids",
        "SELECT role_id FROM lunar_custom_roles WHERE guild_id = ? AND role_id IS NOT NULL",
        (guild_id,),
        fetch_type="all",
    )
    return {int(row[0]) for row in rows or []}


async def update_custom_role(guild_id: int, user_id: int, changed: bool = False, **fields) -> None:
    """Update columns on an existing record. changed=True also stamps last_changed_at."""
    unknown = set(fields) - _ROLE_UPDATABLE
    if unknown:
        raise ValueError(f"Unknown Lunar role columns: {', '.join(sorted(unknown))}")
    if not fields and not changed:
        return
    assignments = [f"{column} = ?" for column in fields]
    if changed:
        assignments.append("last_changed_at = CURRENT_TIMESTAMP")
    await execute_db_operation(
        "update lunar custom role",
        f"UPDATE lunar_custom_roles SET {', '.join(assignments)}, updated_at = CURRENT_TIMESTAMP "
        "WHERE guild_id = ? AND user_id = ?",
        (*fields.values(), guild_id, user_id),
    )


async def list_unhydrated_roles() -> List[CustomRole]:
    """Records copied from booster_roles whose name/colors haven't been read from Discord yet."""
    rows = await execute_db_operation(
        "list unhydrated lunar roles",
        f"SELECT {_ROLE_SELECT_LIGHT} FROM lunar_custom_roles "
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


async def list_roles(guild_id: int) -> List[CustomRole]:
    """Every record in a guild (any status)."""
    rows = await execute_db_operation(
        "list lunar roles",
        f"SELECT {_ROLE_SELECT_LIGHT} FROM lunar_custom_roles WHERE guild_id = ?",
        (guild_id,),
        fetch_type="all",
    )
    return [_row_to_role(row) for row in rows or []]


async def list_guilds_with_records() -> List[int]:
    rows = await execute_db_operation(
        "list guilds with lunar records",
        "SELECT DISTINCT guild_id FROM lunar_custom_roles",
        fetch_type="all",
    )
    return [int(row[0]) for row in rows or []]


# ------------------------------------------------------
# Old /nitro-role-set roles (read only: booster_roles is never changed)
# ------------------------------------------------------

async def list_legacy_roles(guild_id: int) -> List[tuple]:
    """(user_id, role_id) for every old /nitro-role-set role recorded in this server, oldest first."""
    rows = await execute_db_operation(
        "list legacy booster roles",
        "SELECT discord_id, role_id FROM booster_roles WHERE guild_id = ? ORDER BY created_at, discord_id",
        (guild_id,),
        fetch_type="all",
    )
    return [(int(row[0]), int(row[1])) for row in rows or []]


async def get_legacy_role_id(guild_id: int, user_id: int) -> Optional[int]:
    row = await execute_db_operation(
        "get legacy booster role",
        "SELECT role_id FROM booster_roles WHERE guild_id = ? AND discord_id = ?",
        (guild_id, user_id),
        fetch_type="one",
    )
    return int(row[0]) if row else None


# ------------------------------------------------------
# Pending mass removals
# ------------------------------------------------------

PENDING = "pending"
PENDING_CONFIRMED = "confirmed"
PENDING_CANCELLED = "cancelled"
PENDING_WITHDRAWN = "withdrawn"  # everyone in it was removed by /lunar-admin remove first


@dataclass
class PendingRemoval:
    id: int
    guild_id: int
    user_ids: List[int]
    reason: str
    status: str
    log_channel_id: Optional[int]
    log_message_id: Optional[int]
    created_at: Optional[datetime]


_PENDING_SELECT = "id, guild_id, user_ids, reason, status, log_channel_id, log_message_id, created_at"


def _row_to_pending(row) -> PendingRemoval:
    return PendingRemoval(
        id=int(row[0]), guild_id=int(row[1]), user_ids=[int(u) for u in _load_json_list(row[2])],
        reason=row[3], status=row[4], log_channel_id=row[5], log_message_id=row[6], created_at=row[7],
    )


async def create_pending(guild_id: int, user_ids: List[int], reason: str) -> PendingRemoval:
    row = await execute_db_operation(
        "create lunar pending removal",
        f"INSERT INTO lunar_pending_removals (guild_id, user_ids, reason) VALUES (?, ?, ?) RETURNING {_PENDING_SELECT}",
        (guild_id, json.dumps(sorted(set(user_ids))), reason),
        fetch_type="one",
    )
    return _row_to_pending(row)


async def get_open_pending(guild_id: int) -> Optional[PendingRemoval]:
    row = await execute_db_operation(
        "get open lunar pending removal",
        f"SELECT {_PENDING_SELECT} FROM lunar_pending_removals WHERE guild_id = ? AND status = ? ORDER BY id LIMIT 1",
        (guild_id, PENDING),
        fetch_type="one",
    )
    return _row_to_pending(row) if row else None


async def get_pending(pending_id: int) -> Optional[PendingRemoval]:
    row = await execute_db_operation(
        "get lunar pending removal",
        f"SELECT {_PENDING_SELECT} FROM lunar_pending_removals WHERE id = ?",
        (pending_id,),
        fetch_type="one",
    )
    return _row_to_pending(row) if row else None


async def update_pending(pending_id: int, user_ids: Optional[List[int]] = None,
                         reason: Optional[str] = None, log_channel_id: Optional[int] = None,
                         log_message_id: Optional[int] = None) -> None:
    fields = {}
    if user_ids is not None:
        fields["user_ids"] = json.dumps(sorted(set(user_ids)))
    if reason is not None:
        fields["reason"] = reason
    if log_channel_id is not None:
        fields["log_channel_id"] = log_channel_id
    if log_message_id is not None:
        fields["log_message_id"] = log_message_id
    if not fields:
        return
    await execute_db_operation(
        "update lunar pending removal",
        f"UPDATE lunar_pending_removals SET {', '.join(f'{k} = ?' for k in fields)} WHERE id = ?",
        (*fields.values(), pending_id),
    )


async def resolve_pending(pending_id: int, status: str, resolved_by: Optional[int]) -> bool:
    """Close a pending removal. Returns False if it was already resolved (double click)."""
    rows = await execute_db_operation(
        "resolve lunar pending removal",
        "UPDATE lunar_pending_removals SET status = ?, resolved_by = ?, resolved_at = CURRENT_TIMESTAMP "
        "WHERE id = ? AND status = ? RETURNING id",
        (status, resolved_by, pending_id, PENDING),
        fetch_type="all",
    )
    return bool(rows)


async def pending_user_ids(guild_id: int) -> set:
    pending = await get_open_pending(guild_id)
    return set(pending.user_ids) if pending else set()


# ------------------------------------------------------
# Snoozes (members kept after a cancelled pending removal)
# ------------------------------------------------------

async def snooze_users(guild_id: int, user_ids: List[int], hours: int = 24) -> None:
    for user_id in set(user_ids):
        await execute_db_operation(
            "snooze lunar archive",
            """
            INSERT INTO lunar_archive_snoozes (guild_id, user_id, until)
            VALUES (?, ?, CURRENT_TIMESTAMP + make_interval(hours => ?))
            ON CONFLICT (guild_id, user_id) DO UPDATE SET until = excluded.until
            """,
            (guild_id, user_id, hours),
        )


async def snoozed_user_ids(guild_id: int) -> set:
    """Members whose snooze is still running."""
    rows = await execute_db_operation(
        "list active lunar snoozes",
        "SELECT user_id FROM lunar_archive_snoozes WHERE guild_id = ? AND until > CURRENT_TIMESTAMP",
        (guild_id,),
        fetch_type="all",
    )
    return {int(r[0]) for r in rows or []}


async def expired_snooze_user_ids(guild_id: int) -> set:
    """Members whose snooze ran out: they get asked about once more, never removed silently."""
    rows = await execute_db_operation(
        "list expired lunar snoozes",
        "SELECT user_id FROM lunar_archive_snoozes WHERE guild_id = ? AND until <= CURRENT_TIMESTAMP",
        (guild_id,),
        fetch_type="all",
    )
    return {int(r[0]) for r in rows or []}


async def clear_snoozes(guild_id: int, user_ids) -> None:
    for user_id in set(user_ids):
        await execute_db_operation(
            "clear lunar snooze",
            "DELETE FROM lunar_archive_snoozes WHERE guild_id = ? AND user_id = ?",
            (guild_id, user_id),
        )
