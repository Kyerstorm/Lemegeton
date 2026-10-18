"""Color picker link tokens, kept in memory.

- One active link per member per server: a new link replaces the old one.
- Only a SHA-256 hash of each token is stored, so the tokens themselves never sit in memory
  dumps or logs after they're handed out.
- Links expire after LUNAR_PICKER_TTL seconds and all stop working when the bot restarts.
- Each token has its own read/write rate limits.
"""
from __future__ import annotations

import hashlib
import secrets
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Deque, Dict, Optional, Tuple

import config

READ_LIMIT = 60    # API reads per token per RATE_WINDOW
WRITE_LIMIT = 20   # API writes per token per RATE_WINDOW
RATE_WINDOW = 60.0


@dataclass
class PickerLink:
    guild_id: int
    user_id: int
    expires_at: float  # wall clock (time.time()), so it can be shown as a Discord timestamp
    reads: Deque[float] = field(default_factory=deque)
    writes: Deque[float] = field(default_factory=deque)


_links: Dict[str, PickerLink] = {}               # token hash -> link
_by_member: Dict[Tuple[int, int], str] = {}      # (guild_id, user_id) -> token hash


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _drop(token_hash: str) -> None:
    link = _links.pop(token_hash, None)
    if link is not None and _by_member.get((link.guild_id, link.user_id)) == token_hash:
        del _by_member[(link.guild_id, link.user_id)]


def _prune() -> None:
    now = time.time()
    for token_hash in [h for h, link in _links.items() if link.expires_at <= now]:
        _drop(token_hash)


def create(guild_id: int, user_id: int, ttl: Optional[int] = None) -> Tuple[str, float]:
    """Make a new link for this member, replacing any older one. Returns (token, expires_at)."""
    _prune()
    revoke(guild_id, user_id)
    token = secrets.token_urlsafe(32)
    expires_at = time.time() + (ttl if ttl is not None else config.LUNAR_PICKER_TTL)
    token_hash = _hash(token)
    _links[token_hash] = PickerLink(guild_id, user_id, expires_at)
    _by_member[(guild_id, user_id)] = token_hash
    return token, expires_at


def lookup(token: str) -> Optional[PickerLink]:
    """The live link for this token, or None if it's unknown, replaced or expired."""
    if not token or len(token) > 128:
        return None
    token_hash = _hash(token)
    link = _links.get(token_hash)
    if link is None:
        return None
    if link.expires_at <= time.time():
        _drop(token_hash)
        return None
    return link


def revoke(guild_id: int, user_id: int) -> bool:
    """End this member's link (if any). Returns True if there was one."""
    token_hash = _by_member.get((guild_id, user_id))
    if token_hash is None:
        return False
    _drop(token_hash)
    return True


def allow(link: PickerLink, write: bool = False) -> bool:
    """Count one API call against the link's rate limit. False = over the limit."""
    bucket, limit = (link.writes, WRITE_LIMIT) if write else (link.reads, READ_LIMIT)
    now = time.monotonic()
    while bucket and bucket[0] <= now - RATE_WINDOW:
        bucket.popleft()
    if len(bucket) >= limit:
        return False
    bucket.append(now)
    return True


def clear() -> None:
    """Forget every link (tests)."""
    _links.clear()
    _by_member.clear()
