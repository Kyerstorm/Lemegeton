# cogs/alfiles.py
"""
ALFiles Cog - production-ready single-file cog
Features:
- Multi-guild storage with auto DB migration
- Uses helpers.* (utility_helper, anilist_helper) when present; falls back to internal methods
- AniList GraphQL lookup with file-based cache + rate-limiter
- Robust image validation (retries, UA, redirects, magic bytes, caching)
- Background image validation on startup with console logs
- Drafts (create, add images, edit meta), Add More modal & guided upload (up to 10)
- Release with 2-step confirmation
- Delete flow (select, preview, confirm)
- File viewer with Prev/Next/Random and Like toggle (green when liked)
- Likes persisted in DB; leaderboards (server/global); /al-liked ephemeral list
- /al-search by numeric ID
- Self-contained, ready to drop in cogs folder as alfiles.py
"""

from __future__ import annotations

import asyncio
import json
import logging
import random
import time
from pathlib import Path
from typing import Optional, List, Tuple, Dict, Any

import aiohttp
import aiosqlite
import discord
from discord import app_commands
from discord.ext import commands
from database import is_user_moderator
try:
    from helpers.utility_helper import get_user_display_name, is_valid_url, make_http_request
except Exception:
    # Fallbacks if helper missing
    async def get_user_display_name(user_id: int, guild_id: int) -> Optional[str]:
        return None

    def is_valid_url(url: str) -> bool:
        try:
            return url.startswith("http://") or url.startswith("https://")
        except Exception:
            return False

    async def make_http_request(url: str, method: str = "GET", json_data: Any = None, timeout: int = 10, headers: Dict[str, str] = None):
        headers = headers or {"Accept": "application/json"}
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=timeout)) as session:
            if method.upper() == "POST":
                async with session.post(url, json=json_data, headers=headers) as resp:
                    try:
                        return await resp.json()
                    except Exception:
                        return None
            else:
                async with session.get(url, headers=headers) as resp:
                    try:
                        return await resp.json()
                    except Exception:
                        return None

# Optional anilist helper
try:
    from helpers.anilist_helper import fetch_anilist_profile  # expected: async def fetch_anilist_profile(name=None, id=None) -> dict or None
except Exception:
    fetch_anilist_profile = None

# Optional project database helper
try:
    import database  # your database.py
    HAS_DATABASE_HELPER = True
except Exception:
    database = None
    HAS_DATABASE_HELPER = False

# Logging
logger = logging.getLogger("ALFiles")
logger.setLevel(logging.INFO)
if not logger.handlers:
    ch = logging.StreamHandler()
    ch.setFormatter(logging.Formatter("[%(levelname)s] [ALFiles] %(message)s"))
    logger.addHandler(ch)

# Files/paths
Path("data").mkdir(parents=True, exist_ok=True)
DB_PATH = "data/alfiles.db"
ANILIST_CACHE_PATH = "data/anilist_cache.json"

# AniList GraphQL query (only used if fetch_anilist_profile helper missing)
ANILIST_API = "https://graphql.anilist.co"
ANILIST_USER_QUERY = """
query ($name: String, $id: Int) {
  User(name: $name, id: $id) {
    id
    name
    avatar { large }
    siteUrl
  }
}
"""

# Config values
ANILIST_CACHE_TTL = 60 * 60 * 24  # 24h
ANILIST_RATE_LIMIT = (5, 1.0)  # capacity, refill per second
ANILIST_TIMEOUT = 10
MAX_MULTI_UPLOAD = 10
LIKE_TOGGLE_COOLDOWN = 5  # seconds
FALLBACK_IMAGE = "https://anilist.co/img/icons/icon.svg"

# Validation config (per user's request)
VALID_STATUS_CODES = {200, 201, 202, 204}
VALID_IMAGE_MIME_PREFIXES = ("image/",)
MAGIC_BYTES = {
    "jpeg": b"\xFF\xD8\xFF",
    "png": b"\x89PNG\r\n\x1A\n",
    "gif": b"GIF8",
    "webp_riff": b"RIFF",
    # We'll check for "WEBP" in the header chunk
}
VALID_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp"}
VALIDATION_TIMEOUT = 10  # increased from 6
VALIDATION_MAX_RETRIES = 3
MAX_SIGNATURE_BYTES = 32
VALID_CACHE_TTL_GOOD = 86400  # 24h
VALID_CACHE_TTL_BAD = 3600    # 1h

# Helper color
def get_color() -> discord.Color:
    return discord.Color.from_rgb(245, 245, 245)

# Small token bucket for AniList rate limiting
class TokenBucket:
    def __init__(self, capacity: int, refill_per_sec: float):
        self.capacity = capacity
        self.tokens = capacity
        self.refill = refill_per_sec
        self.last = time.monotonic()
        self._lock = asyncio.Lock()

    async def acquire(self):
        async with self._lock:
            now = time.monotonic()
            elapsed = now - self.last
            self.last = now
            self.tokens = min(self.capacity, self.tokens + elapsed * self.refill)
            if self.tokens >= 1:
                self.tokens -= 1
                return
            needed = 1 - self.tokens
            wait = needed / self.refill
        await asyncio.sleep(wait)
        async with self._lock:
            self.tokens = max(0, self.tokens - 1)
            return

# Local file-based cache for AniList (simple)
class FileCache:
    def __init__(self, path: str = ANILIST_CACHE_PATH, ttl: int = ANILIST_CACHE_TTL):
        self.path = Path(path)
        self.ttl = ttl
        self._data: Dict[str, Any] = {}
        self._lock = asyncio.Lock()
        self._load()

    def _load(self):
        try:
            if self.path.exists():
                with open(self.path, "r", encoding="utf-8") as f:
                    self._data = json.load(f)
            else:
                self._data = {}
        except Exception:
            logger.exception("Failed to load AniList cache")
            self._data = {}

    async def get(self, key: str) -> Optional[Dict[str, Any]]:
        async with self._lock:
            rec = self._data.get(key)
            if not rec:
                return None
            if time.time() - rec.get("_ts", 0) > self.ttl:
                self._data.pop(key, None)
                return None
            return rec.get("value")

    async def set(self, key: str, value: Dict[str, Any]):
        async with self._lock:
            self._data[key] = {"_ts": time.time(), "value": value}
            try:
                with open(self.path, "w", encoding="utf-8") as f:
                    json.dump(self._data, f, ensure_ascii=False, indent=2)
            except Exception:
                logger.exception("Failed to persist AniList cache")

# DB wrapper that uses your database helper if available, else aiosqlite
class DBWrapper:
    def __init__(self, path: str = DB_PATH):
        self.path = path
        self.helper = database if HAS_DATABASE_HELPER else None

    async def executescript(self, sql_script: str):
        if self.helper and hasattr(self.helper, "executescript"):
            try:
                return await asyncio.get_event_loop().run_in_executor(None, lambda: self.helper.executescript(sql_script))
            except Exception:
                logger.debug("database.executescript failed, falling back to aiosqlite", exc_info=True)
        async with aiosqlite.connect(self.path) as conn:
            await conn.executescript(sql_script)
            await conn.commit()

    async def _execute(self, sql: str, params: Tuple = ()):
        if self.helper and hasattr(self.helper, "execute"):
            try:
                return await asyncio.get_event_loop().run_in_executor(None, lambda: self.helper.execute(sql, params))
            except Exception:
                logger.debug("database.execute failed, falling back to aiosqlite", exc_info=True)
        async with aiosqlite.connect(self.path) as conn:
            cur = await conn.execute(sql, params)
            await conn.commit()
            return cur

    async def fetchone(self, sql: str, params: Tuple = ()):
        if self.helper and hasattr(self.helper, "fetchone"):
            try:
                return await asyncio.get_event_loop().run_in_executor(None, lambda: self.helper.fetchone(sql, params))
            except Exception:
                logger.debug("database.fetchone failed, falling back to aiosqlite", exc_info=True)
        async with aiosqlite.connect(self.path) as conn:
            async with conn.execute(sql, params) as cur:
                return await cur.fetchone()

    async def fetchall(self, sql: str, params: Tuple = ()):
        if self.helper and hasattr(self.helper, "fetchall"):
            try:
                return await asyncio.get_event_loop().run_in_executor(None, lambda: self.helper.fetchall(sql, params))
            except Exception:
                logger.debug("database.fetchall failed, falling back to aiosqlite", exc_info=True)
        async with aiosqlite.connect(self.path) as conn:
            async with conn.execute(sql, params) as cur:
                return await cur.fetchall()

# The main Cog
class ALFiles(commands.Cog):
    """AL Files - robust multi-guild AniList profile images manager."""
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.db = DBWrapper(DB_PATH)
        self.anilist_cache = FileCache()
        self.anilist_rl = TokenBucket(ANILIST_RATE_LIMIT[0], ANILIST_RATE_LIMIT[1])
        # validation cache: url -> (is_valid: bool, ts: float)
        self._validation_cache: Dict[str, Tuple[bool, float]] = {}
        self._validation_counter = 0
        self.like_count_cache: Dict[int, int] = {}
        self.user_likes_cache: Dict[int, set] = {}
        self.like_cooldowns: Dict[int, float] = {}
        Path("data").mkdir(parents=True, exist_ok=True)
        logger.info("ALFiles cog initialized")

    # ---------------------
    # DB setup / migration
    # ---------------------
    async def setup_db(self):
        create_files = """
        CREATE TABLE IF NOT EXISTS files (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            guild_id INTEGER,
            contributor_id INTEGER,
            owner_id INTEGER,
            owner_name TEXT,
            contributor_name TEXT,
            anilist_username TEXT,
            anilist_id INTEGER,
            al_link TEXT,
            title TEXT,
            description TEXT,
            finalized BOOLEAN DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """
        create_images = """
        CREATE TABLE IF NOT EXISTS images (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            file_id INTEGER,
            image_url TEXT,
            FOREIGN KEY(file_id) REFERENCES files(id) ON DELETE CASCADE
        );
        """
        create_likes = """
        CREATE TABLE IF NOT EXISTS likes (
            file_id INTEGER,
            user_id INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY(file_id, user_id),
            FOREIGN KEY(file_id) REFERENCES files(id) ON DELETE CASCADE
        );
        """
        await self.db.executescript(create_files + "\n" + create_images + "\n" + create_likes)
        # indexes
        try:
            await self.db._execute("CREATE INDEX IF NOT EXISTS idx_files_guild ON files(guild_id)")
            await self.db._execute("CREATE INDEX IF NOT EXISTS idx_images_file ON images(file_id)")
            await self.db._execute("CREATE INDEX IF NOT EXISTS idx_likes_file ON likes(file_id)")
        except Exception:
            logger.exception("Index creation failed (non-fatal)")
        # ensure columns (idempotent)
        try:
            rows = await self.db.fetchall("PRAGMA table_info(files)")
            existing = {r[1] for r in rows}
            required = {"anilist_username", "anilist_id", "title", "description", "owner_id", "owner_name", "contributor_name"}
            for col in required:
                if col not in existing:
                    # choosing TEXT for simplicity for all types except anilist_id
                    sql = f"ALTER TABLE files ADD COLUMN {col} TEXT"
                    if col == "anilist_id":
                        sql = f"ALTER TABLE files ADD COLUMN {col} INTEGER"
                    try:
                        await self.db._execute(sql)
                        logger.info("DB migration: added column %s", col)
                    except Exception:
                        logger.exception("Failed adding column %s", col)
        except Exception:
            logger.exception("Failed to ensure DB columns")

    # ---------------------
    # AniList fetch
    # ---------------------
    async def _fetch_anilist_live(self, username: Optional[str] = None, anilist_id: Optional[int] = None) -> Tuple[Optional[int], Optional[str], Optional[str], Optional[str]]:
        """
        Returns: (id, name, avatar_url, siteUrl) or (None, None, None, None)
        """
        if not username and not anilist_id:
            return None, None, None, None
        key = f"id:{anilist_id}" if anilist_id else f"name:{username}"
        cached = await self.anilist_cache.get(key)
        if cached:
            return cached.get("id"), cached.get("name"), cached.get("avatar"), cached.get("siteUrl")
        # If helper present, use it
        if fetch_anilist_profile:
            try:
                profile = await fetch_anilist_profile(name=username, id=anilist_id)
                if profile:
                    val = {"id": profile.get("id"), "name": profile.get("name"), "avatar": profile.get("avatar"), "siteUrl": profile.get("siteUrl")}
                    await self.anilist_cache.set(key, val)
                    return val["id"], val["name"], val["avatar"], val["siteUrl"]
            except Exception:
                logger.debug("anilist_helper failed, falling back to graphql direct", exc_info=True)
        # rate-limit
        await self.anilist_rl.acquire()
        variables = {}
        if anilist_id:
            variables["id"] = int(anilist_id)
        else:
            variables["name"] = username
        payload = {"query": ANILIST_USER_QUERY, "variables": variables}
        try:
            resp = await make_http_request(ANILIST_API, method="POST", json_data=payload, timeout=ANILIST_TIMEOUT)
            if resp and resp.get("data", {}).get("User"):
                u = resp["data"]["User"]
                val = {"id": u.get("id"), "name": u.get("name"), "avatar": (u.get("avatar") or {}).get("large"), "siteUrl": u.get("siteUrl")}
                await self.anilist_cache.set(key, val)
                return val["id"], val["name"], val["avatar"], val["siteUrl"]
        except Exception:
            logger.debug("make_http_request to AniList failed", exc_info=True)
        # fallback aiohttp
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=ANILIST_TIMEOUT)) as session:
                async with session.post(ANILIST_API, json=payload) as resp:
                    if resp.status == 200:
                        j = await resp.json()
                        u = j.get("data", {}).get("User")
                        if u:
                            val = {"id": u.get("id"), "name": u.get("name"), "avatar": (u.get("avatar") or {}).get("large"), "siteUrl": u.get("siteUrl")}
                            await self.anilist_cache.set(key, val)
                            return val["id"], val["name"], val["avatar"], val["siteUrl"]
        except Exception:
            logger.exception("AniList aiohttp fallback failed")
        return None, None, None, None

    # ---------------------
    # Robust image validation (full)
    # ---------------------
    async def _validate_image_url(self, url: str) -> bool:
        """
        Enhanced validation:
        - caching (positive 24h, negative 1h)
        - retries with exponential backoff
        - HEAD then GET
        - User-Agent header
        - checks Content-Type first
        - fallback to magic-bytes read (first 32 bytes)
        - fallback to extension check
        """
        if not url or not is_valid_url(url):
            return False

        # cached?
        now = time.time()
        cached = self._validation_cache.get(url)
        if cached:
            ok, ts = cached
            ttl = VALID_CACHE_TTL_GOOD if ok else VALID_CACHE_TTL_BAD
            if now - ts < ttl:
                return ok

        headers = {
            "User-Agent": "Mozilla/5.0 (compatible; ALFilesBot/3.0; +https://anilist.co)",
            "Accept": "image/*,*/*;q=0.8"
        }

        async def attempt_once(attempt: int) -> bool:
            try:
                timeout = aiohttp.ClientTimeout(total=VALIDATION_TIMEOUT)
                async with aiohttp.ClientSession(timeout=timeout) as session:
                    # HEAD
                    try:
                        async with session.head(url, allow_redirects=True, headers=headers) as resp:
                            if resp.status in VALID_STATUS_CODES:
                                ctype = resp.headers.get("Content-Type", "")
                                if ctype and any(ctype.startswith(pref) for pref in VALID_IMAGE_MIME_PREFIXES):
                                    return True
                                # else we will GET below to read magic bytes
                            else:
                                # If HEAD returned non-success, still attempt GET (some servers disallow HEAD)
                                pass
                    except aiohttp.ClientResponseError as e:
                        logger.debug("HEAD request failed for %s: %s", url, e)
                    except asyncio.TimeoutError:
                        logger.warning("Timeout on HEAD for %s", url)
                    except Exception as e:
                        logger.debug("HEAD exception for %s: %s", url, e)

                    # GET small portion of content
                    try:
                        async with session.get(url, allow_redirects=True, headers=headers) as resp:
                            if resp.status not in VALID_STATUS_CODES:
                                return False
                            ctype = resp.headers.get("Content-Type", "")
                            if ctype and any(ctype.startswith(pref) for pref in VALID_IMAGE_MIME_PREFIXES):
                                return True
                            # read limited bytes
                            chunk = await resp.content.read(MAX_SIGNATURE_BYTES)
                            if self._looks_like_image(chunk):
                                return True
                            # extension fallback
                            low = url.lower()
                            for ext in VALID_EXTENSIONS:
                                if low.endswith(ext):
                                    return True
                            return False
                    except asyncio.TimeoutError:
                        logger.warning("Timeout on GET for %s", url)
                        return False
                    except aiohttp.ClientError as e:
                        logger.warning("Network error for %s: %s", url, e)
                        return False
            except Exception as e:
                logger.debug("Unexpected error validating %s: %s", url, e, exc_info=True)
                return False

        backoff_base = 0.5
        for attempt in range(VALIDATION_MAX_RETRIES):
            ok = await attempt_once(attempt)
            if ok:
                self._validation_cache[url] = (True, time.time())
                return True
            await asyncio.sleep(backoff_base * (2 ** attempt))

        self._validation_cache[url] = (False, time.time())
        # occasional cleanup
        self._validation_counter += 1
        if self._validation_counter % 100 == 0:
            self._cleanup_validation_cache()
        return False

    def _looks_like_image(self, data: bytes) -> bool:
        if not data:
            return False
        try:
            if data.startswith(MAGIC_BYTES["jpeg"]):
                return True
            if data.startswith(MAGIC_BYTES["png"]):
                return True
            if data.startswith(MAGIC_BYTES["gif"]):
                return True
            if data.startswith(MAGIC_BYTES["webp_riff"]) and b"WEBP" in data[:16]:
                return True
        except Exception:
            logger.debug("Signature check failed", exc_info=True)
        return False

    def _cleanup_validation_cache(self):
        now = time.time()
        to_remove = []
        for url, (ok, ts) in list(self._validation_cache.items()):
            ttl = VALID_CACHE_TTL_GOOD if ok else VALID_CACHE_TTL_BAD
            if now - ts > ttl:
                to_remove.append(url)
        for u in to_remove:
            self._validation_cache.pop(u, None)
        if to_remove:
            logger.info("Cleaned %d expired validation cache entries", len(to_remove))

    async def _validate_and_fix_images_for_file(self, file_id: int) -> List[str]:
        images = await self.get_file_images(file_id)
        if not images:
            return [FALLBACK_IMAGE]
        valid = []
        for url in images:
            try:
                ok = await self._validate_image_url(url)
                if ok:
                    valid.append(url)
                else:
                    logger.warning("Invalid image for file %s: %s", file_id, url)
            except Exception:
                logger.exception("Error validating image for file %s: %s", file_id, url)
        if not valid:
            logger.warning("No valid images for file %s; using fallback", file_id)
            return [FALLBACK_IMAGE]
        return valid

    async def _validate_all_images_on_startup(self):
        logger.info("Starting background image validation of all files...")
        try:
            rows = await self.db.fetchall("SELECT id FROM files")
            total = len(rows)
            checked = 0
            for (fid,) in rows:
                images = await self.get_file_images(fid)
                for url in images:
                    await self._validate_image_url(url)
                checked += 1
                if checked % 20 == 0:
                    logger.info("Validated %d/%d files...", checked, total)
                await asyncio.sleep(0.01)
        except Exception:
            logger.exception("Error during startup image validation")
        self._cleanup_validation_cache()
        logger.info("Background image validation complete")

    # ---------------------
    # DB operations for files/images
    # ---------------------
    async def create_draft(self, guild_id: int, owner: discord.abc.User, contributor: Optional[discord.User] = None) -> int:
        contributor_id = contributor.id if contributor else owner.id
        contributor_name = str(contributor) if contributor else str(owner)
        owner_id = owner.id
        owner_name = str(owner)
        anilist_username = None
        anilist_id = None
        al_link = None
        try:
            possible = await get_user_display_name(contributor_id, guild_id)
            if possible and isinstance(possible, str):
                anilist_username = possible
                al_link = f"https://anilist.co/user/{anilist_username}"
        except Exception:
            logger.debug("get_user_display_name not available", exc_info=True)
        await self.db._execute(
            "INSERT INTO files (guild_id, contributor_id, owner_id, owner_name, contributor_name, anilist_username, anilist_id, al_link, finalized) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0)",
            (guild_id, contributor_id, owner_id, owner_name, contributor_name, anilist_username, anilist_id, al_link)
        )
        row = await self.db.fetchone("SELECT last_insert_rowid()")
        fid = row[0] if row else None
        logger.info("Created draft #%s (owner=%s, contributor=%s)", fid, owner_id, contributor_id)
        return fid

    async def get_draft(self, guild_id: int, owner_id: int) -> Optional[Tuple[int]]:
        return await self.db.fetchone("SELECT id FROM files WHERE guild_id = ? AND owner_id = ? AND finalized = 0", (guild_id, owner_id))

    async def add_image_to_draft(self, file_id: int, url: str) -> bool:
        if not is_valid_url(url):
            logger.debug("Rejected invalid URL: %s", url)
            return False
        try:
            await self.db._execute("INSERT INTO images (file_id, image_url) VALUES (?, ?)", (file_id, url))
            self.like_count_cache.pop(file_id, None)
            return True
        except Exception:
            logger.exception("Failed to add image to draft")
            return False

    async def update_draft_meta(self, file_id: int, title: Optional[str], description: Optional[str]):
        await self.db._execute("UPDATE files SET title = ?, description = ? WHERE id = ?", (title, description, file_id))

    async def finalize_file(self, file_id: int) -> bool:
        try:
            await self.db._execute("UPDATE files SET finalized = 1 WHERE id = ?", (file_id,))
            logger.info("Finalized file #%s", file_id)
            return True
        except Exception:
            logger.exception("Failed finalize file")
            return False

    async def delete_file(self, file_id: int):
        try:
            await self.db._execute("DELETE FROM images WHERE file_id = ?", (file_id,))
            await self.db._execute("DELETE FROM likes WHERE file_id = ?", (file_id,))
            await self.db._execute("DELETE FROM files WHERE id = ?", (file_id,))
            self.like_count_cache.pop(file_id, None)
            logger.info("Deleted file #%s", file_id)
        except Exception:
            logger.exception("Failed to delete file")

    async def list_user_files(self, guild_id: int, user_id: int) -> List[Tuple[int, bool, str, int]]:
        rows = await self.db.fetchall("SELECT id, finalized, created_at FROM files WHERE guild_id = ? AND contributor_id = ? ORDER BY created_at DESC", (guild_id, user_id))
        out = []
        for fid, finalized, created_at in rows:
            cnt_row = await self.db.fetchone("SELECT COUNT(*) FROM images WHERE file_id = ?", (fid,))
            img_count = cnt_row[0] if cnt_row else 0
            out.append((fid, bool(finalized), created_at, img_count))
        return out

    async def get_file_images(self, file_id: int) -> List[str]:
        rows = await self.db.fetchall("SELECT image_url FROM images WHERE file_id = ?", (file_id,))
        return [r[0] for r in rows] if rows else []

    async def get_file_info(self, file_id: int):
        return await self.db.fetchone("SELECT contributor_name, anilist_username, anilist_id, al_link, title, description, created_at, contributor_id, owner_id, owner_name, finalized, guild_id FROM files WHERE id = ?", (file_id,))

    async def get_random_file(self, guild_id: int, exclude_id: Optional[int] = None) -> Optional[int]:
        if exclude_id:
            rows = await self.db.fetchall("SELECT id FROM files WHERE guild_id = ? AND finalized = 1 AND id != ?", (guild_id, exclude_id))
        else:
            rows = await self.db.fetchall("SELECT id FROM files WHERE guild_id = ? AND finalized = 1", (guild_id,))
        if not rows:
            return None
        return random.choice(rows)[0]

    # ---------------------
    # Like system
    # ---------------------
    async def has_liked(self, file_id: int, user_id: int) -> bool:
        if user_id in self.user_likes_cache:
            return file_id in self.user_likes_cache[user_id]
        row = await self.db.fetchone("SELECT 1 FROM likes WHERE file_id = ? AND user_id = ?", (file_id, user_id))
        return bool(row)

    async def get_like_count(self, file_id: int) -> int:
        if file_id in self.like_count_cache:
            return self.like_count_cache[file_id]
        row = await self.db.fetchone("SELECT COUNT(*) FROM likes WHERE file_id = ?", (file_id,))
        count = row[0] if row else 0
        self.like_count_cache[file_id] = count
        return count

    async def toggle_like(self, file_id: int, user_id: int) -> Tuple[bool, int]:
        try:
            exists = await self.db.fetchone("SELECT 1 FROM likes WHERE file_id = ? AND user_id = ?", (file_id, user_id))
            if exists:
                await self.db._execute("DELETE FROM likes WHERE file_id = ? AND user_id = ?", (file_id, user_id))
                self.like_count_cache[file_id] = max(0, self.like_count_cache.get(file_id, 1) - 1)
                if user_id in self.user_likes_cache:
                    self.user_likes_cache[user_id].discard(file_id)
                logger.info("User %s unliked File #%s", user_id, file_id)
                return False, self.like_count_cache[file_id]
            else:
                await self.db._execute("INSERT INTO likes (file_id, user_id) VALUES (?, ?)", (file_id, user_id))
                self.like_count_cache[file_id] = self.like_count_cache.get(file_id, 0) + 1
                self.user_likes_cache.setdefault(user_id, set()).add(file_id)
                logger.info("User %s liked File #%s", user_id, file_id)
                return True, self.like_count_cache[file_id]
        except Exception:
            logger.exception("toggle_like failed")
            cnt = await self.get_like_count(file_id)
            return False, cnt

    async def get_top_liked(self, guild_id: Optional[int], limit: int = 10) -> List[Tuple[int, int]]:
        if guild_id:
            rows = await self.db.fetchall("SELECT l.file_id, COUNT(l.user_id) as cnt FROM likes l JOIN files f ON f.id = l.file_id WHERE f.guild_id = ? GROUP BY l.file_id ORDER BY cnt DESC LIMIT ?", (guild_id, limit))
        else:
            rows = await self.db.fetchall("SELECT file_id, COUNT(user_id) as cnt FROM likes GROUP BY file_id ORDER BY cnt DESC LIMIT ?", (limit,))
        return [(r[0], r[1]) for r in rows] if rows else []

    async def get_files_liked_by_user(self, user_id: int) -> List[Tuple[int, int]]:
        rows = await self.db.fetchall("""
            SELECT l.file_id, COUNT(x.user_id) as total
            FROM likes l
            LEFT JOIN likes x ON x.file_id = l.file_id
            WHERE l.user_id = ?
            GROUP BY l.file_id
            ORDER BY l.created_at DESC
            LIMIT 100
        """, (user_id,))
        return [(r[0], r[1]) for r in rows] if rows else []

    # ---------------------
    # Upload prompt helpers
    # ---------------------
    async def prompt_for_attachments(self, interaction: discord.Interaction, timeout: int = 60) -> Optional[List[str]]:
        user = interaction.user
        channel = interaction.channel
        try:
            await interaction.followup.send(f"📤 Upload up to {MAX_MULTI_UPLOAD} images in one message (attach them) or paste image URLs. You have {timeout}s.", ephemeral=True)
        except Exception:
            await interaction.response.send_message(f"📤 Upload up to {MAX_MULTI_UPLOAD} images in one message (attach them) or paste image URLs. You have {timeout}s.", ephemeral=True)

        def check(m: discord.Message):
            return m.author.id == user.id and m.channel.id == (channel.id if channel else None)

        try:
            msg = await self.bot.wait_for("message", timeout=timeout, check=check)
        except asyncio.TimeoutError:
            return None

        urls = []
        for att in (msg.attachments or [])[:MAX_MULTI_UPLOAD]:
            try:
                if att.content_type and att.content_type.startswith("image/"):
                    urls.append(att.url)
                elif is_valid_url(att.url):
                    urls.append(att.url)
            except Exception:
                if is_valid_url(att.url):
                    urls.append(att.url)
        for t in (msg.content or "").split():
            if len(urls) >= MAX_MULTI_UPLOAD:
                break
            if is_valid_url(t):
                urls.append(t)
        # dedupe and limit
        seen = set()
        out = []
        for u in urls:
            if u not in seen:
                seen.add(u)
                out.append(u)
            if len(out) >= MAX_MULTI_UPLOAD:
                break
        return out if out else None

    async def _get_discord_avatar(self, user_id: int) -> Optional[str]:
        try:
            user = self.bot.get_user(user_id) or await self.bot.fetch_user(user_id)
            if user:
                return str(user.display_avatar.url)
        except Exception:
            logger.debug("Failed to get avatar for user %s", user_id, exc_info=True)
        return None

    # ---------------------
    # Modals & Views
    # ---------------------
    class AddImageModal(discord.ui.Modal, title="Add Image URL"):
        image_url = discord.ui.TextInput(label="Image URL (direct)", required=False, placeholder="https://...")

        def __init__(self, cog, file_id: int):
            super().__init__()
            self.cog = cog
            self.file_id = file_id

        async def on_submit(self, interaction: discord.Interaction):
            url = self.image_url.value.strip() if self.image_url.value else None
            if not url or not is_valid_url(url):
                await interaction.response.send_message("❌ Invalid or empty URL.", ephemeral=True)
                return
            ok = await self.cog.add_image_to_draft(self.file_id, url)
            if ok:
                await interaction.response.send_message("✅ Image added to draft.", ephemeral=True)
            else:
                await interaction.response.send_message("❌ Failed to add image.", ephemeral=True)

    class EditMetaModal(discord.ui.Modal, title="Edit Title & Description"):
        title_input = discord.ui.TextInput(label="Title (optional)", required=False, max_length=200)
        desc_input = discord.ui.TextInput(label="Description (optional)", style=discord.TextStyle.paragraph, required=False, max_length=2000)

        def __init__(self, cog, file_id: int):
            super().__init__()
            self.cog = cog
            self.file_id = file_id

        async def on_submit(self, interaction: discord.Interaction):
            title = self.title_input.value.strip() or None
            desc = self.desc_input.value.strip() or None
            await self.cog.update_draft_meta(self.file_id, title, desc)
            await interaction.response.send_message("✅ Draft metadata updated.", ephemeral=True)

    class AddMoreView(discord.ui.View):
        def __init__(self, cog, file_id: int):
            super().__init__(timeout=180)
            self.cog = cog
            self.file_id = file_id

        @discord.ui.button(label="➕ Add (URL)", style=discord.ButtonStyle.primary)
        async def add_url(self, interaction: discord.Interaction, button: discord.ui.Button):
            await interaction.response.send_modal(ALFiles.AddImageModal(self.cog, self.file_id))

        @discord.ui.button(label="📤 Upload Another (Guided)", style=discord.ButtonStyle.success)
        async def guided_upload(self, interaction: discord.Interaction, button: discord.ui.Button):
            await interaction.response.defer(ephemeral=True)
            urls = await self.cog.prompt_for_attachments(interaction)
            if not urls:
                await interaction.followup.send("⌛ Timed out — no images received.", ephemeral=True)
                return
            added = 0
            for url in urls:
                if await self.cog.add_image_to_draft(self.file_id, url):
                    added += 1
            await interaction.followup.send(f"✅ Added {added}/{len(urls)} image{'s' if added != 1 else ''} to your draft.", ephemeral=True)

        @discord.ui.button(label="📝 Edit Title & Description", style=discord.ButtonStyle.secondary)
        async def edit_meta(self, interaction: discord.Interaction, button: discord.ui.Button):
            await interaction.response.send_modal(ALFiles.EditMetaModal(self.cog, self.file_id))

        @discord.ui.button(label="Done", style=discord.ButtonStyle.success)
        async def done(self, interaction: discord.Interaction, button: discord.ui.Button):
            await interaction.response.send_message("Saved. Use `/al-release` to publish your draft when ready.", ephemeral=True)

    class ALReleaseConfirm(discord.ui.View):
        def __init__(self, cog, file_id: int):
            super().__init__(timeout=60)
            self.cog = cog
            self.file_id = file_id

        @discord.ui.button(label="✅ Confirm Release", style=discord.ButtonStyle.success)
        async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
            info = await self.cog.get_file_info(self.file_id)
            if info:
                _, _, _, _, _, _, _, _, owner_id, _, _, _ = info
                if interaction.user.id != owner_id:
                    await interaction.response.send_message("❌ Only the draft owner can confirm release.", ephemeral=True)
                    return
            ok = await self.cog.finalize_file(self.file_id)
            if ok:
                await interaction.response.edit_message(content=f"✅ File #{self.file_id} released successfully!", embed=None, view=None)
            else:
                await interaction.response.send_message("❌ Failed to release file.", ephemeral=True)

        @discord.ui.button(label="❌ Cancel", style=discord.ButtonStyle.danger)
        async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
            await interaction.response.edit_message(content="❌ Release cancelled.", embed=None, view=None)

    class DeleteSelect(discord.ui.Select):
        def __init__(self, cog, options: List[discord.SelectOption]):
            super().__init__(placeholder="Select a file to delete...", min_values=1, max_values=1, options=options)
            self.cog = cog

        async def callback(self, interaction: discord.Interaction):
            try:
                file_id = int(self.values[0])
            except Exception:
                await interaction.response.send_message("Invalid selection", ephemeral=True)
                return
            images = await self.cog.get_file_images(file_id)
            info = await self.cog.get_file_info(file_id)
            if not info:
                await interaction.response.send_message("Failed to load file info.", ephemeral=True)
                return
            contributor_name, anilist_username, anilist_id, al_link, title, desc, created_at, contributor_id, owner_id, owner_name, finalized, guild_id = info
            uid, display_name, avatar_url, siteUrl = await self.cog._fetch_anilist_live(anilist_username, anilist_id)
            anilist_name = display_name or anilist_username
            anilist_avatar = avatar_url
            anilist_url = siteUrl or al_link
            valid_images = await self.cog._validate_and_fix_images_for_file(file_id)
            embed = discord.Embed(title=f"Delete Preview — File #{file_id}", description=desc or None, color=get_color())
            embed.set_image(url=valid_images[0])
            if anilist_name and anilist_url:
                embed.set_author(name=anilist_name, url=anilist_url, icon_url=anilist_avatar)
            else:
                embed.set_author(name=contributor_name)
            footer_icon = await self.cog._get_discord_avatar(contributor_id)
            if footer_icon:
                embed.set_footer(text=f"Contributed by {contributor_name}", icon_url=footer_icon)
            else:
                embed.set_footer(text=f"Contributed by {contributor_name}")
            view = discord.ui.View()
            view.add_item(ALFiles.DeleteConfirmButton(self.cog, file_id))
            view.add_item(ALFiles.CancelButton())
            await interaction.response.edit_message(embed=embed, view=view)

    class DeleteConfirmButton(discord.ui.Button):
        def __init__(self, cog, file_id: int):
            super().__init__(label="Delete File", style=discord.ButtonStyle.danger)
            self.cog = cog
            self.file_id = file_id

        async def callback(self, interaction: discord.Interaction):
            info = await self.cog.get_file_info(self.file_id)
            if info:
                _, _, _, _, _, _, _, contributor_id, owner_id, owner_name, _, _ = info
                if interaction.user.id not in (owner_id, contributor_id):
                    await interaction.response.send_message("❌ Only the owner or contributor can delete this file.", ephemeral=True)
                    return
            await self.cog.delete_file(self.file_id)
            await interaction.response.edit_message(content=f"🗑️ File #{self.file_id} has been deleted.", embed=None, view=None)

    class CancelButton(discord.ui.Button):
        def __init__(self):
            super().__init__(label="Cancel", style=discord.ButtonStyle.secondary)

        async def callback(self, interaction: discord.Interaction):
            await interaction.response.edit_message(content="Cancelled.", embed=None, view=None)

    # File viewer view
    class FileView(discord.ui.View):
        def __init__(self, cog, file_id: int, images: List[str], contributor_name: str, anilist_name: Optional[str], anilist_avatar: Optional[str], anilist_url: Optional[str], title: Optional[str], description: Optional[str], contributor_id: Optional[int], owner_id: Optional[int]):
            super().__init__(timeout=300)
            self.cog = cog
            self.file_id = file_id
            self.images = images or []
            self.index = 0
            self.contributor_name = contributor_name
            self.anilist_name = anilist_name
            self.anilist_avatar = anilist_avatar
            self.anilist_url = anilist_url
            self.title = title
            self.description = description
            self.contributor_id = contributor_id
            self.owner_id = owner_id
            # like button created dynamically per user in _refresh_like_button_for_user

        async def _build_embed(self):
            embed = discord.Embed(title=self.title or f"📁 File #{self.file_id}", description=self.description or None, color=get_color())
            if self.images:
                embed.set_image(url=self.images[self.index])
            if self.anilist_name and self.anilist_url:
                embed.set_author(name=self.anilist_name, url=self.anilist_url, icon_url=self.anilist_avatar)
            else:
                embed.set_author(name=self.contributor_name)
            footer_text = f"Contributed by {self.contributor_name}"
            footer_icon = None
            if self.contributor_id:
                footer_icon = await self.cog._get_discord_avatar(self.contributor_id)
            if footer_icon:
                embed.set_footer(text=footer_text, icon_url=footer_icon)
            else:
                embed.set_footer(text=footer_text)
            return embed

        @discord.ui.button(label="⬅️ Prev", style=discord.ButtonStyle.secondary)
        async def prev(self, interaction: discord.Interaction, button: discord.ui.Button):
            if not self.images:
                await interaction.response.send_message("No images", ephemeral=True)
                return
            self.index = (self.index - 1) % len(self.images)
            embed = await self._build_embed()
            await interaction.response.edit_message(embed=embed, view=self)

        @discord.ui.button(label="➡️ Next", style=discord.ButtonStyle.secondary)
        async def next(self, interaction: discord.Interaction, button: discord.ui.Button):
            if not self.images:
                await interaction.response.send_message("No images", ephemeral=True)
                return
            self.index = (self.index + 1) % len(self.images)
            embed = await self._build_embed()
            await interaction.response.edit_message(embed=embed, view=self)

        @discord.ui.button(label="🔀 Random", style=discord.ButtonStyle.primary)
        async def rand(self, interaction: discord.Interaction, button: discord.ui.Button):
            guild_id = interaction.guild.id if interaction.guild else 0
            new_id = await self.cog.get_random_file(guild_id=guild_id, exclude_id=self.file_id)
            if not new_id:
                await interaction.response.send_message("No other files available!", ephemeral=True)
                return
            valid_images = await self.cog._validate_and_fix_images_for_file(new_id)
            info = await self.cog.get_file_info(new_id)
            if not info:
                await interaction.response.send_message("Failed to load file.", ephemeral=True)
                return
            contributor_name, anilist_username, anilist_id, al_link, title, desc, created_at, contributor_id, owner_id, owner_name, finalized, file_guild_id = info
            uid, display_name, avatar_url, siteUrl = await self.cog._fetch_anilist_live(anilist_username, anilist_id)
            anilist_name = display_name or anilist_username
            anilist_avatar = avatar_url
            anilist_url = siteUrl or al_link
            new_view = ALFiles.FileView(self.cog, new_id, valid_images, contributor_name, anilist_name, anilist_avatar, anilist_url, title, desc, contributor_id, owner_id)
            await new_view._refresh_like_button_for_user(interaction.user.id)
            embed = await new_view._build_embed()
            await interaction.response.edit_message(embed=embed, view=new_view)

        async def _refresh_like_button_for_user(self, user_id: int):
            # remove previous like-button(s)
            for child in list(self.children):
                if isinstance(child, discord.ui.Button) and child.label and child.label.startswith("💙"):
                    try:
                        self.remove_item(child)
                    except Exception:
                        pass
            count = await self.cog.get_like_count(self.file_id)
            liked = await self.cog.has_liked(self.file_id, user_id)
            style = discord.ButtonStyle.success if liked else discord.ButtonStyle.blurple
            like_btn = discord.ui.Button(label=f"💙 {count}", style=style)
            async def like_cb(inter: discord.Interaction):
                last = self.cog.like_cooldowns.get(inter.user.id, 0)
                if time.time() - last < LIKE_TOGGLE_COOLDOWN:
                    await inter.response.send_message(f"You're toggling too fast — wait {LIKE_TOGGLE_COOLDOWN}s.", ephemeral=True)
                    return
                self.cog.like_cooldowns[inter.user.id] = time.time()
                try:
                    now_liked, new_count = await self.cog.toggle_like(self.file_id, inter.user.id)
                    like_btn.label = f"💙 {new_count}"
                    if now_liked:
                        like_btn.style = discord.ButtonStyle.success
                        await inter.response.send_message("✅ You liked this file!", ephemeral=True)
                    else:
                        like_btn.style = discord.ButtonStyle.danger
                        await inter.response.send_message("💔 Like removed.", ephemeral=True)
                        await asyncio.sleep(0.2)
                        like_btn.style = discord.ButtonStyle.blurple
                    # update view
                    embed = await self._build_embed()
                    try:
                        await inter.message.edit(embed=embed, view=self)
                    except Exception:
                        pass
                except Exception:
                    logger.exception("Like toggle error")
                    await inter.response.send_message("❌ Failed to toggle like.", ephemeral=True)
            like_btn.callback = like_cb
            # insert like button as first child
            self.add_item(like_btn)

    # ---------------------
    # Commands (slash)
    # ---------------------
    SCOPE_CHOICES = [
        app_commands.Choice(name="🏠 Server", value="server"),
        app_commands.Choice(name="🌐 Global", value="global"),
    ]

    @app_commands.command(name="al-files", description="📁 View or contribute AL Files")
    @app_commands.describe(upload="Attach an image (single). Use guided upload to add multiple images.", as_user="(Optional) credit another Discord user as contributor")
    async def al_files(self, interaction: discord.Interaction, upload: Optional[discord.Attachment] = None, as_user: Optional[discord.User] = None):
        guild_id = interaction.guild.id if interaction.guild else 0
        owner = interaction.user
        contributor = as_user or owner

        # Upload flow
        if upload:
            # immediate defer to avoid interaction timeout
            await interaction.response.defer(ephemeral=True, thinking=True)

            if not upload.content_type or not upload.content_type.startswith("image/"):
                await interaction.followup.send("❌ Please attach a valid image file.", ephemeral=True)
                return

            draft = await self.get_draft(guild_id, owner.id)
            if not draft:
                file_id = await self.create_draft(guild_id, owner, contributor)
            else:
                file_id = draft[0]
                # update contributor metadata if changed
                try:
                    await self.db._execute("UPDATE files SET contributor_id = ?, contributor_name = ? WHERE id = ?", (contributor.id, str(contributor), file_id))
                except Exception:
                    logger.exception("Failed to update contributor info for draft")

            ok = await self.add_image_to_draft(file_id, upload.url)
            if not ok:
                await interaction.followup.send("❌ Failed to add image to draft.", ephemeral=True)
                return

            embed = discord.Embed(title=f"📁 Draft #{file_id}", description=f"Image added to draft (credited to {str(contributor)}).", color=get_color())
            embed.add_field(name="Next", value="Use 'Add (URL)' to paste direct links or 'Upload Another (Guided)' to attach up to 10 images in one message.", inline=False)
            view = ALFiles.AddMoreView(self, file_id)
            await interaction.followup.send(embed=embed, view=view, ephemeral=True)
            return

        # View random finalized file
        await interaction.response.defer()
        rand_id = await self.get_random_file(guild_id=guild_id)
        if not rand_id:
            await interaction.followup.send("❌ No finalized files yet in this server.", ephemeral=True)
            return
        images = await self._validate_and_fix_images_for_file(rand_id)
        info = await self.get_file_info(rand_id)
        if not info:
            await interaction.followup.send("❌ Failed to load file info.", ephemeral=True)
            return
        contributor_name, anilist_username, anilist_id, al_link, title, desc, created_at, contributor_id, owner_id, owner_name, finalized, file_guild_id = info
        uid, display_name, avatar_url, siteUrl = await self._fetch_anilist_live(anilist_username, anilist_id)
        anilist_name = display_name or anilist_username
        anilist_avatar = avatar_url
        anilist_url = siteUrl or al_link
        embed = discord.Embed(title=title or f"📁 File #{rand_id}", description=desc or None, color=get_color())
        embed.set_image(url=images[0])
        if anilist_name and anilist_url:
            embed.set_author(name=anilist_name, url=anilist_url, icon_url=anilist_avatar)
        else:
            embed.set_author(name=contributor_name)
        footer_icon = await self._get_discord_avatar(contributor_id)
        if footer_icon:
            embed.set_footer(text=f"Contributed by {contributor_name}", icon_url=footer_icon)
        else:
            embed.set_footer(text=f"Contributed by {contributor_name}")
        view = ALFiles.FileView(self, rand_id, images, contributor_name, anilist_name, anilist_avatar, anilist_url, title, desc, contributor_id, owner_id)
        await view._refresh_like_button_for_user(interaction.user.id)
        await interaction.followup.send(embed=embed, view=view)

    @app_commands.command(name="al-release", description="✅ Release your drafted AL file (confirm required)")
    async def al_release(self, interaction: discord.Interaction):
        guild_id = interaction.guild.id if interaction.guild else 0
        owner_id = interaction.user.id
        draft = await self.get_draft(guild_id, owner_id)
        if not draft:
            await interaction.response.send_message("❌ You don't have an active draft!", ephemeral=True)
            return
        file_id = draft[0]
        images = await self.get_file_images(file_id)
        if not images:
            await interaction.response.send_message("❌ Draft has no images!", ephemeral=True)
            return
        # try to refresh AniList info
        try:
            info = await self.get_file_info(file_id)
            if info:
                anilist_username = info[1]
                anilist_id = info[2]
                uid, display_name, avatar_url, siteUrl = await self._fetch_anilist_live(anilist_username, anilist_id)
                if uid or display_name or avatar_url or siteUrl:
                    al_link = siteUrl or (f"https://anilist.co/user/{anilist_username}" if anilist_username else None)
                    try:
                        await self.db._execute("UPDATE files SET anilist_id = ?, anilist_username = ?, al_link = ? WHERE id = ?", (uid, display_name or anilist_username, al_link, file_id))
                    except Exception:
                        logger.exception("Failed to update file anilist info on release")
        except Exception:
            logger.debug("Non-fatal: AniList refresh failed", exc_info=True)

        valid_images = await self._validate_and_fix_images_for_file(file_id)
        embed = discord.Embed(title=f"Confirm release — File #{file_id}", color=get_color())
        embed.set_image(url=valid_images[0])
        embed.add_field(name="Images", value=str(len(valid_images)), inline=True)
        view = ALFiles.ALReleaseConfirm(self, file_id)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    @app_commands.command(name="al-delete", description="🗑️ Delete an AL file you contributed")
    async def al_delete(self, interaction: discord.Interaction):
        guild_id = interaction.guild.id if interaction.guild else 0
        await interaction.response.defer(ephemeral=True)
        files = await self.list_user_files(guild_id, interaction.user.id)
        if not files:
            await interaction.followup.send("You have no contributions.", ephemeral=True)
            return
        options = []
        for fid, finalized, created_at, image_count in files:
            options.append(discord.SelectOption(label=f"#{fid} • {image_count} img{'s' if image_count != 1 else ''}", value=str(fid), description="finalized" if finalized else "draft"))
        view = discord.ui.View()
        view.add_item(ALFiles.DeleteSelect(self, options))
        await interaction.followup.send("Select file to delete:", view=view, ephemeral=True)

    @app_commands.command(name="al-lb", description="🏆 View contributors leaderboard (server/global)")
    @app_commands.choices(scope=SCOPE_CHOICES)
    async def al_lb(self, interaction: discord.Interaction, scope: app_commands.Choice[str]):
        await interaction.response.defer()
        guild_id = interaction.guild.id if interaction.guild else None
        if scope.value == "global":
            rows = await self.db.fetchall("SELECT contributor_name, COUNT(id) as total FROM files WHERE finalized = 1 GROUP BY contributor_id ORDER BY total DESC LIMIT 25")
            title = "🏆 AL Contributors — Global"
        else:
            rows = await self.db.fetchall("SELECT contributor_name, COUNT(id) as total FROM files WHERE finalized = 1 AND guild_id = ? GROUP BY contributor_id ORDER BY total DESC LIMIT 25", (guild_id,))
            title = f"🏆 AL Contributors — Server: {interaction.guild.name if interaction.guild else 'DM'}"
        if not rows:
            await interaction.followup.send("❌ No contributors for that scope.", ephemeral=True)
            return
        embed = discord.Embed(title=title, description="Top contributors", color=get_color())
        medals = ["🥇", "🥈", "🥉"]
        for i,(name,count) in enumerate(rows, start=1):
            medal = medals[i-1] if i<=3 else f"#{i}"
            embed.add_field(name=f"{medal} {name}", value=f"📁 {count} file{'s' if count!=1 else ''}", inline=False)
        # totals
        if scope.value == "global":
            total_contrib = (await self.db.fetchone("SELECT COUNT(DISTINCT contributor_id) FROM files"))[0]
            total_files = (await self.db.fetchone("SELECT COUNT(id) FROM files"))[0]
            total_images = (await self.db.fetchone("SELECT COUNT(id) FROM images WHERE file_id IN (SELECT id FROM files WHERE finalized = 1)"))[0]
        else:
            total_contrib = (await self.db.fetchone("SELECT COUNT(DISTINCT contributor_id) FROM files WHERE finalized = 1 AND guild_id = ?", (guild_id,)))[0]
            total_files = (await self.db.fetchone("SELECT COUNT(id) FROM files WHERE finalized = 1 AND guild_id = ?", (guild_id,)))[0]
            total_images = (await self.db.fetchone("SELECT COUNT(i.id) FROM images i JOIN files f ON f.id = i.file_id WHERE f.finalized = 1 AND f.guild_id = ?", (guild_id,)))[0]
        embed.set_footer(text=f"👥 {total_contrib} contributors • 📁 {total_files} files • 📸 {total_images} images")
        await interaction.followup.send(embed=embed)

    @app_commands.command(name="al-likes", description="💙 Show Most Liked Files (server/global)")
    @app_commands.choices(scope=SCOPE_CHOICES)
    async def al_likes(self, interaction: discord.Interaction, scope: app_commands.Choice[str]):
        await interaction.response.defer()
        guild_id = interaction.guild.id if interaction.guild else None
        if scope.value == "global":
            top = await self.get_top_liked(None, limit=10)
            title = "💙 Most Liked Files — Global"
        else:
            top = await self.get_top_liked(guild_id, limit=10)
            title = f"💙 Most Liked Files — Server: {interaction.guild.name if interaction.guild else 'DM'}"
        if not top:
            await interaction.followup.send("❌ No likes yet in that scope.", ephemeral=True)
            return
        embed = discord.Embed(title=title, color=get_color())
        for i,(file_id,cnt) in enumerate(top, start=1):
            info = await self.get_file_info(file_id)
            if not info:
                continue
            contributor_name, anilist_username, anilist_id, al_link, title_text, description, created_at, contributor_id, owner_id, owner_name, finalized, file_guild_id = info
            embed.add_field(name=f"{i}. #{file_id} — {contributor_name} • {cnt} like{'s' if cnt!=1 else ''}", value=title_text or "—", inline=False)
        await interaction.followup.send(embed=embed)

    @app_commands.command(name="al-search", description="🔍 Search a file by number (ID)")
    @app_commands.describe(file_number="ID number of the file to search")
    async def al_search(self, interaction: discord.Interaction, file_number: int):
        await interaction.response.defer()
        info = await self.get_file_info(file_number)
        if not info:
            await interaction.followup.send(f"❌ No file found with ID #{file_number}.", ephemeral=True)
            return
        images = await self._validate_and_fix_images_for_file(file_number)
        contributor_name, anilist_username, anilist_id, al_link, title, desc, created_at, contributor_id, owner_id, owner_name, finalized, file_guild_id = info
        uid, display_name, avatar_url, siteUrl = await self._fetch_anilist_live(anilist_username, anilist_id)
        anilist_name = display_name or anilist_username
        anilist_avatar = avatar_url
        anilist_url = siteUrl or al_link
        embed = discord.Embed(title=title or f"📁 File #{file_number}", description=desc or None, color=get_color())
        embed.set_image(url=images[0])
        if anilist_name and anilist_url:
            embed.set_author(name=anilist_name, url=anilist_url, icon_url=anilist_avatar)
        else:
            embed.set_author(name=contributor_name)
        footer_icon = await self._get_discord_avatar(contributor_id)
        if footer_icon:
            embed.set_footer(text=f"Contributed by {contributor_name}", icon_url=footer_icon)
        else:
            embed.set_footer(text=f"Contributed by {contributor_name}")
        view = ALFiles.FileView(self, file_number, images, contributor_name, anilist_name, anilist_avatar, anilist_url, title, desc, contributor_id, owner_id)
        await view._refresh_like_button_for_user(interaction.user.id)
        await interaction.followup.send(embed=embed, view=view)

    @app_commands.command(name="al-draft", description="📋 View your current draft status")
    async def al_draft(self, interaction: discord.Interaction):
        guild_id = interaction.guild.id if interaction.guild else 0
        owner_id = interaction.user.id
        draft = await self.get_draft(guild_id, owner_id)
        if not draft:
            await interaction.response.send_message("📭 You don't have an active draft. Use `/al-files upload:[image]` to create one!", ephemeral=True)
            return
        file_id = draft[0]
        images = await self.get_file_images(file_id)
        info = await self.get_file_info(file_id)
        title = info[4] if info else None
        desc = info[5] if info else None
        embed = discord.Embed(title=f"📋 Draft #{file_id}", description=desc or "Your current draft file", color=get_color())
        embed.add_field(name="📸 Images", value=f"{len(images)} image{'s' if len(images)!=1 else ''}", inline=True)
        embed.add_field(name="✅ Status", value="Ready to release!" if images else "⚠️ No images yet", inline=True)
        if images:
            embed.set_thumbnail(url=images[0])
            embed.add_field(name="📤 Next Step", value="Use `/al-release` to publish your file! (Confirm required)", inline=False)
        else:
            embed.add_field(name="📤 Next Step", value="Use `/al-files upload:[image]` to add images!", inline=False)
        view = ALFiles.AddMoreView(self, file_id)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)


    @app_commands.command(name="al-liked", description="💾 View and open your liked files interactively (ephemeral)")
    async def al_liked(self, interaction: discord.Interaction):
        """Interactive dropdown to explore your liked files."""
        await interaction.response.defer(ephemeral=True)
        user_id = interaction.user.id
        liked = await self.get_files_liked_by_user(user_id)
        if not liked:
            await interaction.followup.send("💙 You haven't liked any files yet.", ephemeral=True)
            return

        options = []
        for fid, cnt in liked[:25]:
            options.append(
                discord.SelectOption(
                    label=f"#{fid} • {cnt} like{'s' if cnt != 1 else ''}",
                    value=str(fid),
                    description="Click to view this liked file"
                )
            )

        class ReturnButton(discord.ui.Button):
            def __init__(self, parent_view):
                super().__init__(label="↩️ Return to Liked List", style=discord.ButtonStyle.secondary)
                self.parent_view = parent_view

            async def callback(self, interaction: discord.Interaction):
                await interaction.response.edit_message(
                    content="💾 Select one of your liked files below:",
                    embed=None,
                    view=self.parent_view
                )

        class LikedSelect(discord.ui.Select):
            def __init__(self, cog: "ALFiles", parent_view: discord.ui.View):
                super().__init__(placeholder="Select a liked file to view...", min_values=1, max_values=1, options=options)
                self.cog = cog
                self.parent_view = parent_view

            async def callback(self, interaction: discord.Interaction):
                file_id = int(self.values[0])
                info = await self.cog.get_file_info(file_id)
                if not info:
                    await interaction.response.send_message(f"❌ File #{file_id} no longer exists.", ephemeral=True)
                    return

                images = await self.cog._validate_and_fix_images_for_file(file_id)
                contributor_name, anilist_username, anilist_id, al_link, title, desc, created_at, contributor_id, owner_id, owner_name, finalized, file_guild_id = info
                uid, display_name, avatar_url, siteUrl = await self.cog._fetch_anilist_live(anilist_username, anilist_id)
                anilist_name = display_name or anilist_username
                anilist_avatar = avatar_url
                anilist_url = siteUrl or al_link

                embed = discord.Embed(
                    title=title or f"📁 File #{file_id}",
                    description=desc or None,
                    color=get_color()
                )
                embed.set_image(url=images[0])
                if anilist_name and anilist_url:
                    embed.set_author(name=anilist_name, url=anilist_url, icon_url=anilist_avatar)
                else:
                    embed.set_author(name=contributor_name)

                footer_icon = await self.cog._get_discord_avatar(contributor_id)
                if footer_icon:
                    embed.set_footer(text=f"Contributed by {contributor_name}", icon_url=footer_icon)
                else:
                    embed.set_footer(text=f"Contributed by {contributor_name}")

                view = ALFiles.FileView(
                    self.cog, file_id, images,
                    contributor_name, anilist_name, anilist_avatar, anilist_url,
                    title, desc, contributor_id, owner_id
                )
                await view._refresh_like_button_for_user(interaction.user.id)
                view.add_item(ReturnButton(self.parent_view))
                await interaction.response.edit_message(embed=embed, view=view, content=None)

        liked_view = discord.ui.View(timeout=180)
        select = LikedSelect(self, liked_view)
        liked_view.add_item(select)
        await interaction.followup.send("💾 Select one of your liked files below:", view=liked_view, ephemeral=True)

    # ---------------------
    # Admin / Mod command
    # ---------------------
    @app_commands.command(name="al-reset", description="⚠️ Moderator only: Reset all AL Files data")
    async def al_reset(self, interaction: discord.Interaction):
        """Deletes all ALFiles data (requires moderator permissions)."""

        guild_id = interaction.guild.id if interaction.guild else 0
        if not is_user_moderator(interaction.user.id, guild_id):
            await interaction.response.send_message("❌ You do not have moderator permissions.", ephemeral=True)
            return

        class ConfirmReset(discord.ui.View):
            def __init__(self, cog):
                super().__init__(timeout=60)
                self.cog = cog

            @discord.ui.button(label="✅ Confirm Reset", style=discord.ButtonStyle.danger)
            async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
                try:
                    await self.cog.db._execute("DROP TABLE IF EXISTS likes")
                    await self.cog.db._execute("DROP TABLE IF EXISTS images")
                    await self.cog.db._execute("DROP TABLE IF EXISTS files")
                    await self.cog.setup_db()
                    self.cog.like_count_cache.clear()
                    self.cog.user_likes_cache.clear()
                    await interaction.response.edit_message(
                        content="✅ All AL Files data has been **wiped clean** and reset.",
                        view=None, embed=None
                    )
                    logger.warning("ALFiles database has been reset by %s in guild %s", interaction.user.id, guild_id)
                except Exception:
                    logger.exception("Failed full reset")
                    await interaction.response.send_message("❌ Database reset failed. Check logs.", ephemeral=True)

            @discord.ui.button(label="❌ Cancel", style=discord.ButtonStyle.secondary)
            async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
                await interaction.response.edit_message(content="❌ Reset cancelled.", view=None, embed=None)

        view = ConfirmReset(self)
        await interaction.response.send_message(
            "⚠️ This will delete **ALL** AL Files, images, likes, and contributor data.\nAre you sure you want to continue?",
            view=view,
            ephemeral=True
        )

    # ---------------------
    # Lifecycle hooks
    # ---------------------
    async def cog_load(self):
        await self.setup_db()
        asyncio.create_task(self._validate_all_images_on_startup())
        logger.info("ALFiles cog loaded")

    async def cog_unload(self):
        logger.info("ALFiles cog unloaded")

# Setup function for extension
async def setup(bot: commands.Bot):
    await bot.add_cog(ALFiles(bot))
    logger.info("ALFiles cog setup complete")
