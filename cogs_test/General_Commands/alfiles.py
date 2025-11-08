# cogs/alfiles.py
"""
ALFiles - Fully featured cog:
- Multi-guild
- Auto DB migrations (safe)
- AniList GraphQL live lookup with file cache and rate-limiter
- Add More modal + guided multi-upload (up to 10 images in one message)
- Create draft, finalize (release) with 2-step confirm view
- Delete with select -> preview -> confirm
- File viewer with pagination, random, like toggle (green for liked, red for unliked)
- Like system persisted in DB, per-user cooldowns, caches, console logs
- /al-lb, /al-likes support server/global scope via choices dropdown
- /al-liked shows ephemeral paginated list of user's liked files
- /al-search <file_number> to lookup file by id
- Robust image validation on startup and on load (HEAD request); logs invalid images
"""
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

# Try to import project helpers; provide safe fallbacks if not present
try:
    from helpers.utility_helper import get_user_display_name, is_valid_url, make_http_request
except Exception:
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

logger = logging.getLogger("ALFiles")
DB_PATH = "data/alfiles.db"
CACHE_PATH = "data/anilist_cache.json"

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

# Config
ANILIST_CACHE_TTL = 60 * 60 * 24  # 24h
ANILIST_RATE_LIMIT = (5, 1.0)  # tokens, refill/sec
ANILIST_TIMEOUT = 10
MAX_MULTI_UPLOAD = 10
LIKE_TOGGLE_COOLDOWN = 5  # seconds
IMAGE_VALIDATION_TIMEOUT = 6  # seconds for HEAD/GET check
FALLBACK_IMAGE = "https://anilist.co/img/icons/icon.svg"  # used when image URLs are invalid

Path("data").mkdir(parents=True, exist_ok=True)

def get_color() -> discord.Color:
    return discord.Color.from_rgb(245, 245, 245)

# --- Utilities: rate-limiter (token bucket) and file-backed cache ---
class TokenBucket:
    def __init__(self, capacity: int, refill_per_sec: float):
        self.capacity = capacity
        self.tokens = capacity
        self.refill_per_sec = refill_per_sec
        self.last = time.monotonic()
        self.lock = asyncio.Lock()

    async def acquire(self):
        async with self.lock:
            now = time.monotonic()
            elapsed = now - self.last
            self.last = now
            self.tokens = min(self.capacity, self.tokens + elapsed * self.refill_per_sec)
            if self.tokens >= 1:
                self.tokens -= 1
                return
            needed = 1 - self.tokens
            wait = needed / self.refill_per_sec
        await asyncio.sleep(wait)
        async with self.lock:
            self.tokens = max(0, self.tokens - 1)
            return

class FileCache:
    def __init__(self, path: str = CACHE_PATH, ttl: int = ANILIST_CACHE_TTL):
        self.path = Path(path)
        self.ttl = ttl
        self._data: Dict[str, Any] = {}
        self.lock = asyncio.Lock()
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
        async with self.lock:
            rec = self._data.get(key)
            if not rec:
                return None
            if time.time() - rec.get("_ts", 0) > self.ttl:
                self._data.pop(key, None)
                return None
            return rec.get("value")

    async def set(self, key: str, value: Dict[str, Any]):
        async with self.lock:
            self._data[key] = {"_ts": time.time(), "value": value}
            try:
                with open(self.path, "w", encoding="utf-8") as f:
                    json.dump(self._data, f, ensure_ascii=False, indent=2)
            except Exception:
                logger.exception("Failed to persist AniList cache")

# --- The Cog ---
class ALFiles(commands.Cog):
    """AL Files cog — robust, auto-migrating, likes, search, AniList integration."""
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.db_path = DB_PATH
        self.anilist_cache = FileCache()
        self.anilist_rl = TokenBucket(ANILIST_RATE_LIMIT[0], ANILIST_RATE_LIMIT[1])
        self.like_count_cache: Dict[int, int] = {}
        self.user_likes_cache: Dict[int, set] = {}  # optional per-user liked file ids (ephemeral)
        self.like_cooldowns: Dict[int, float] = {}
        Path("data").mkdir(parents=True, exist_ok=True)
        # Start background startup tasks after cog is loaded (we will call them in cog_load)
        logger.info("ALFiles cog initialized")

    # ------------------------------
    # DB migration and validation
    # ------------------------------
    async def setup_db(self):
        """
        Create required tables and add missing columns safely (idempotent).
        Tables:
            files, images, likes
        """
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
        )
        """
        create_images = """
        CREATE TABLE IF NOT EXISTS images (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            file_id INTEGER,
            image_url TEXT,
            FOREIGN KEY(file_id) REFERENCES files(id) ON DELETE CASCADE
        )
        """
        create_likes = """
        CREATE TABLE IF NOT EXISTS likes (
            file_id INTEGER,
            user_id INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (file_id, user_id),
            FOREIGN KEY (file_id) REFERENCES files(id) ON DELETE CASCADE
        )
        """
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(create_files)
            await db.execute(create_images)
            await db.execute(create_likes)
            await db.commit()

            # Ensure indexes for performance
            try:
                await db.execute("CREATE INDEX IF NOT EXISTS idx_files_guild ON files(guild_id)")
                await db.execute("CREATE INDEX IF NOT EXISTS idx_images_file ON images(file_id)")
                await db.execute("CREATE INDEX IF NOT EXISTS idx_likes_file ON likes(file_id)")
                await db.commit()
            except Exception:
                logger.exception("Failed creating indexes")

            # Check and add missing columns if older DB lacks them
            required_cols = {
                "anilist_username": "TEXT",
                "anilist_id": "INTEGER",
                "title": "TEXT",
                "description": "TEXT",
                "owner_id": "INTEGER",
                "owner_name": "TEXT",
                "contributor_name": "TEXT"
            }
            async with db.execute("PRAGMA table_info(files)") as cur:
                rows = await cur.fetchall()
                existing = {r[1] for r in rows}
            for col, coltype in required_cols.items():
                if col not in existing:
                    try:
                        await db.execute(f"ALTER TABLE files ADD COLUMN {col} {coltype}")
                        logger.info("[DB] Added missing column: %s", col)
                    except Exception:
                        logger.exception("Failed to add column %s", col)
            await db.commit()

    # ------------------------------
    # AniList helper (live fetch, cache, rate-limit)
    # ------------------------------
    async def _fetch_anilist_live(self, username: Optional[str] = None, anilist_id: Optional[int] = None) -> Tuple[Optional[int], Optional[str], Optional[str], Optional[str]]:
        if not username and not anilist_id:
            return None, None, None, None
        key = f"id:{anilist_id}" if anilist_id else f"name:{username}"
        cached = await self.anilist_cache.get(key)
        if cached:
            return cached.get("id"), cached.get("name"), cached.get("avatar"), cached.get("siteUrl")
        # rate-limit
        await self.anilist_rl.acquire()
        variables = {}
        if anilist_id:
            variables["id"] = int(anilist_id)
        else:
            variables["name"] = username
        payload = {"query": ANILIST_USER_QUERY, "variables": variables}
        # try helper
        try:
            resp = await make_http_request(ANILIST_API, method="POST", json_data=payload, timeout=ANILIST_TIMEOUT)
            if resp and resp.get("data", {}).get("User"):
                u = resp["data"]["User"]
                value = {"id": u.get("id"), "name": u.get("name"), "avatar": (u.get("avatar") or {}).get("large"), "siteUrl": u.get("siteUrl")}
                await self.anilist_cache.set(key, value)
                return value["id"], value["name"], value["avatar"], value["siteUrl"]
        except Exception:
            logger.debug("make_http_request for AniList failed; falling back to aiohttp", exc_info=True)
        # fallback to aiohttp
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=ANILIST_TIMEOUT)) as session:
                async with session.post(ANILIST_API, json=payload) as resp:
                    if resp.status == 200:
                        j = await resp.json()
                        u = j.get("data", {}).get("User")
                        if u:
                            value = {"id": u.get("id"), "name": u.get("name"), "avatar": (u.get("avatar") or {}).get("large"), "siteUrl": u.get("siteUrl")}
                            await self.anilist_cache.set(key, value)
                            return value["id"], value["name"], value["avatar"], value["siteUrl"]
                    else:
                        logger.debug("AniList returned status %s", resp.status)
        except Exception:
            logger.exception("AniList aiohttp fallback failed")
        return None, None, None, None

    # ------------------------------
    # Image validation
    # ------------------------------
    async def _validate_image_url(self, url: str) -> bool:
        """
        HEAD (or GET if HEAD not allowed) the URL and ensure status 200 and content-type image.
        Timeout ~ IMAGE_VALIDATION_TIMEOUT.
        """
        if not url:
            return False
        if not is_valid_url(url):
            return False
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=IMAGE_VALIDATION_TIMEOUT)) as session:
                # prefer HEAD
                try:
                    async with session.head(url) as resp:
                        if resp.status == 200:
                            ctype = resp.headers.get("Content-Type", "")
                            return ctype.startswith("image/")
                except Exception:
                    # fallback to GET small request
                    async with session.get(url) as resp:
                        if resp.status == 200:
                            ctype = resp.headers.get("Content-Type", "")
                            return ctype.startswith("image/")
        except Exception:
            return False
        return False

    async def _validate_and_fix_images_for_file(self, file_id: int) -> List[str]:
        """
        Validate each image for a file. Return list of valid URLs. If none valid, return [FALLBACK_IMAGE].
        Also log invalid/expired URLs to console.
        """
        images = await self.get_file_images(file_id)
        valid = []
        for url in images:
            ok = await self._validate_image_url(url)
            if ok:
                valid.append(url)
            else:
                logger.warning("[ALFiles] File #%s image invalid or unreachable: %s", file_id, url)
        if not valid:
            logger.warning("[ALFiles] File #%s has zero valid images; using fallback", file_id)
            return [FALLBACK_IMAGE]
        return valid

    # ------------------------------
    # DB CRUD helpers (files/images)
    # ------------------------------
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
            logger.debug("get_user_display_name failed or not present", exc_info=True)

        async with aiosqlite.connect(self.db_path) as db:
            cur = await db.execute(
                "INSERT INTO files (guild_id, contributor_id, owner_id, owner_name, contributor_name, anilist_username, anilist_id, al_link, finalized) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0)",
                (guild_id, contributor_id, owner_id, owner_name, contributor_name, anilist_username, anilist_id, al_link)
            )
            await db.commit()
            fid = cur.lastrowid
            logger.info("[ALFiles] Created draft #%s (owner=%s, contributor=%s)", fid, owner_id, contributor_id)
            return fid

    async def get_draft(self, guild_id: int, owner_id: int) -> Optional[Tuple[int]]:
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute("SELECT id FROM files WHERE guild_id = ? AND owner_id = ? AND finalized = 0", (guild_id, owner_id)) as cur:
                return await cur.fetchone()

    async def add_image_to_draft(self, file_id: int, url: str) -> bool:
        if not is_valid_url(url):
            logger.debug("[ALFiles] rejected invalid URL when adding image: %s", url)
            return False
        async with aiosqlite.connect(self.db_path) as db:
            try:
                await db.execute("INSERT INTO images (file_id, image_url) VALUES (?, ?)", (file_id, url))
                await db.commit()
                # invalidate cache
                self.like_count_cache.pop(file_id, None)
                return True
            except Exception:
                logger.exception("Failed to insert image into DB")
                return False

    async def update_draft_meta(self, file_id: int, title: Optional[str], description: Optional[str]):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("UPDATE files SET title = ?, description = ? WHERE id = ?", (title, description, file_id))
            await db.commit()

    async def finalize_file(self, file_id: int) -> bool:
        """
        Mark file as finalized. Returns True if successful.
        """
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("UPDATE files SET finalized = 1 WHERE id = ?", (file_id,))
            await db.commit()
        logger.info("[ALFiles] Finalized file #%s", file_id)
        return True

    async def delete_file(self, file_id: int):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("DELETE FROM images WHERE file_id = ?", (file_id,))
            await db.execute("DELETE FROM likes WHERE file_id = ?", (file_id,))
            await db.execute("DELETE FROM files WHERE id = ?", (file_id,))
            await db.commit()
        self.like_count_cache.pop(file_id, None)
        logger.info("[ALFiles] Deleted file #%s", file_id)

    async def list_user_files(self, guild_id: int, user_id: int) -> List[Tuple[int, bool, str, int]]:
        out = []
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute("SELECT id, finalized, created_at FROM files WHERE guild_id = ? AND contributor_id = ? ORDER BY created_at DESC", (guild_id, user_id)) as cur:
                rows = await cur.fetchall()
            for fid, finalized, created_at in rows:
                async with aiosqlite.connect(self.db_path) as db2:
                    async with db2.execute("SELECT COUNT(*) FROM images WHERE file_id = ?", (fid,)) as c2:
                        cnt = await c2.fetchone()
                        image_count = cnt[0] if cnt else 0
                out.append((fid, bool(finalized), created_at, image_count))
        return out

    async def get_file_images(self, file_id: int) -> List[str]:
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute("SELECT image_url FROM images WHERE file_id = ?", (file_id,)) as cur:
                rows = await cur.fetchall()
            return [r[0] for r in rows] if rows else []

    async def get_file_info(self, file_id: int):
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute("SELECT contributor_name, anilist_username, anilist_id, al_link, title, description, created_at, contributor_id, owner_id, owner_name, finalized, guild_id FROM files WHERE id = ?", (file_id,)) as cur:
                return await cur.fetchone()

    async def get_random_file(self, guild_id: int, exclude_id: Optional[int] = None) -> Optional[int]:
        async with aiosqlite.connect(self.db_path) as db:
            if exclude_id:
                async with db.execute("SELECT id FROM files WHERE guild_id = ? AND finalized = 1 AND id != ?", (guild_id, exclude_id)) as cur:
                    rows = await cur.fetchall()
            else:
                async with db.execute("SELECT id FROM files WHERE guild_id = ? AND finalized = 1", (guild_id,)) as cur:
                    rows = await cur.fetchall()
        if not rows:
            return None
        return random.choice(rows)[0]

    # ------------------------------
    # Likes system
    # ------------------------------
    async def has_liked(self, file_id: int, user_id: int) -> bool:
        # check in-memory user cache if present
        try:
            if user_id in self.user_likes_cache:
                return file_id in self.user_likes_cache[user_id]
        except Exception:
            pass
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute("SELECT 1 FROM likes WHERE file_id = ? AND user_id = ?", (file_id, user_id)) as cur:
                r = await cur.fetchone()
                return bool(r)

    async def get_like_count(self, file_id: int) -> int:
        if file_id in self.like_count_cache:
            return self.like_count_cache[file_id]
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute("SELECT COUNT(*) FROM likes WHERE file_id = ?", (file_id,)) as cur:
                r = await cur.fetchone()
                count = r[0] if r else 0
        self.like_count_cache[file_id] = count
        return count

    async def toggle_like(self, file_id: int, user_id: int) -> Tuple[bool, int]:
        """
        Toggle like for a user on a file.
        Returns (is_now_liked, new_count)
        Uses transaction to avoid race conditions.
        """
        async with aiosqlite.connect(self.db_path) as db:
            try:
                async with db.execute("SELECT 1 FROM likes WHERE file_id = ? AND user_id = ?", (file_id, user_id)) as cur:
                    exists = await cur.fetchone()
                if exists:
                    await db.execute("DELETE FROM likes WHERE file_id = ? AND user_id = ?", (file_id, user_id))
                    await db.commit()
                    # update caches
                    self.like_count_cache[file_id] = max(0, self.like_count_cache.get(file_id, 1) - 1)
                    if user_id in self.user_likes_cache:
                        self.user_likes_cache[user_id].discard(file_id)
                    logger.info("[ALFiles] User %s unliked File #%s", user_id, file_id)
                    return False, self.like_count_cache[file_id]
                else:
                    await db.execute("INSERT INTO likes (file_id, user_id) VALUES (?, ?)", (file_id, user_id))
                    await db.commit()
                    self.like_count_cache[file_id] = self.like_count_cache.get(file_id, 0) + 1
                    if user_id not in self.user_likes_cache:
                        self.user_likes_cache[user_id] = set()
                    self.user_likes_cache[user_id].add(file_id)
                    logger.info("[ALFiles] User %s liked File #%s", user_id, file_id)
                    return True, self.like_count_cache[file_id]
            except Exception:
                logger.exception("toggle_like DB error")
                # fallback count query
                count = await self.get_like_count(file_id)
                return False, count

    async def get_top_liked(self, guild_id: Optional[int], limit: int = 10) -> List[Tuple[int, int]]:
        async with aiosqlite.connect(self.db_path) as db:
            if guild_id:
                query = """
                SELECT l.file_id, COUNT(l.user_id) as cnt
                FROM likes l JOIN files f ON f.id = l.file_id
                WHERE f.guild_id = ?
                GROUP BY l.file_id
                ORDER BY cnt DESC
                LIMIT ?
                """
                async with db.execute(query, (guild_id, limit)) as cur:
                    rows = await cur.fetchall()
            else:
                query = """
                SELECT file_id, COUNT(user_id) as cnt
                FROM likes
                GROUP BY file_id
                ORDER BY cnt DESC
                LIMIT ?
                """
                async with db.execute(query, (limit,)) as cur:
                    rows = await cur.fetchall()
        return [(r[0], r[1]) for r in rows] if rows else []

    async def get_files_liked_by_user(self, user_id: int) -> List[Tuple[int, int]]:
        """
        Return list of (file_id, like_count) for files the user liked, ordered newest liked first.
        """
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute("""
                SELECT l.file_id, COUNT(x.user_id) as total
                FROM likes l
                LEFT JOIN likes x ON x.file_id = l.file_id
                WHERE l.user_id = ?
                GROUP BY l.file_id
                ORDER BY l.created_at DESC
                LIMIT 100
            """, (user_id,)) as cur:
                rows = await cur.fetchall()
        return [(r[0], r[1]) for r in rows] if rows else []

    # ------------------------------
    # Guided upload: accept up to 10 attachments or URLs in a single message
    # ------------------------------
    async def prompt_for_attachments(self, interaction: discord.Interaction, timeout: int = 60) -> Optional[List[str]]:
        user = interaction.user
        channel = interaction.channel
        try:
            await interaction.followup.send(f"📤 Please upload up to {MAX_MULTI_UPLOAD} images in one message (attach them), or paste direct image URLs. You have {timeout}s.", ephemeral=True)
        except Exception:
            await interaction.response.send_message(f"📤 Please upload up to {MAX_MULTI_UPLOAD} images in one message (attach them), or paste direct image URLs. You have {timeout}s.", ephemeral=True)

        def check(msg: discord.Message):
            return msg.author.id == user.id and msg.channel.id == (channel.id if channel else None)

        try:
            msg = await self.bot.wait_for("message", timeout=timeout, check=check)
        except asyncio.TimeoutError:
            return None

        urls: List[str] = []
        for att in (msg.attachments or [])[:MAX_MULTI_UPLOAD]:
            try:
                if att.content_type and att.content_type.startswith("image/"):
                    urls.append(att.url)
                elif is_valid_url(att.url):
                    urls.append(att.url)
            except Exception:
                if is_valid_url(att.url):
                    urls.append(att.url)
        tokens = (msg.content or "").split()
        for t in tokens:
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

    # ------------------------------
    # Helper to fetch contributor avatar (discord)
    # ------------------------------
    async def _get_discord_avatar(self, user_id: int) -> Optional[str]:
        try:
            user = self.bot.get_user(user_id) or await self.bot.fetch_user(user_id)
            if user:
                return str(user.display_avatar.url)
        except Exception:
            logger.debug("Failed to fetch avatar for user %s", user_id, exc_info=True)
        return None

    # ------------------------------
    # UI: Modals & Views
    # ------------------------------
    class AddImageModal(discord.ui.Modal, title="Add Image URL"):
        image_url = discord.ui.TextInput(label="Image URL (direct link)", required=False, placeholder="https://...")

        def __init__(self, cog, file_id: int):
            super().__init__()
            self.cog = cog
            self.file_id = file_id

        async def on_submit(self, interaction: discord.Interaction):
            url = self.image_url.value.strip() if self.image_url.value else None
            if not url:
                await interaction.response.send_message("❌ No URL provided. Use the guided upload to attach files or paste a URL.", ephemeral=True)
                return
            if not is_valid_url(url):
                await interaction.response.send_message("❌ That doesn't look like a valid URL.", ephemeral=True)
                return
            ok = await self.cog.add_image_to_draft(self.file_id, url)
            if ok:
                await interaction.response.send_message("✅ Image added to your draft.", ephemeral=True)
            else:
                await interaction.response.send_message("❌ Failed to add image to draft.", ephemeral=True)

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

    class ALReleaseConfirm(discord.ui.View):
        def __init__(self, cog, file_id: int):
            super().__init__(timeout=60)
            self.cog = cog
            self.file_id = file_id

        @discord.ui.button(label="✅ Confirm Release", style=discord.ButtonStyle.success)
        async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
            # Only the owner should confirm
            info = await self.cog.get_file_info(self.file_id)
            if info:
                _, _, _, _, _, _, _, _, owner_id, _, _, _ = info
                if interaction.user.id != owner_id:
                    await interaction.response.send_message("❌ Only the draft owner can confirm release.", ephemeral=True)
                    return
            await self.cog.finalize_file(self.file_id)
            await interaction.response.edit_message(content=f"✅ File #{self.file_id} released successfully!", embed=None, view=None)

        @discord.ui.button(label="❌ Cancel", style=discord.ButtonStyle.danger)
        async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
            await interaction.response.edit_message(content="❌ Release cancelled.", embed=None, view=None)

    class DeleteConfirmButton(discord.ui.Button):
        def __init__(self, cog, file_id: int):
            super().__init__(label="Delete File", style=discord.ButtonStyle.danger)
            self.cog = cog
            self.file_id = file_id

        async def callback(self, interaction: discord.Interaction):
            # verify owner or contributor
            info = await self.cog.get_file_info(self.file_id)
            if info:
                _, _, _, _, _, _, _, contributor_id, owner_id, _, _, _ = info
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
            embed = discord.Embed(title=f"Delete Preview — File #{file_id}", description=desc or None, color=get_color())
            if images:
                # Validate first image to ensure visible
                valid_images = await self.cog._validate_and_fix_images_for_file(file_id)
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

    class DeleteSelectView(discord.ui.View):
        def __init__(self, cog, options: List[discord.SelectOption]):
            super().__init__(timeout=120)
            self.add_item(ALFiles.DeleteSelect(cog, options))

    # File Viewer with decorated buttons (Prev, Next, Random, Like)
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
            # Like button will be added dynamically in on_timeout or when view constructed
            # We'll create it here with placeholder label and replace/update later
            self.like_btn = discord.ui.Button(label="💙 0", style=discord.ButtonStyle.blurple)
            self.add_item(self.like_btn)

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

        async def on_timeout(self):
            for i in self.children:
                i.disabled = True
            try:
                # try edit the message to disable buttons
                # Note: we cannot access the message object reliably from here; it's okay.
                pass
            except Exception:
                pass

        # We attach decorated buttons with callbacks below to have proper introspection

        @discord.ui.button(label="⬅️ Prev", style=discord.ButtonStyle.secondary)
        async def prev_button(self, interaction: discord.Interaction, button: discord.ui.Button):
            if not self.images:
                await interaction.response.send_message("No images", ephemeral=True)
                return
            self.index = (self.index - 1) % len(self.images)
            embed = await self._build_embed()
            await interaction.response.edit_message(embed=embed, view=self)

        @discord.ui.button(label="➡️ Next", style=discord.ButtonStyle.secondary)
        async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button):
            if not self.images:
                await interaction.response.send_message("No images", ephemeral=True)
                return
            self.index = (self.index + 1) % len(self.images)
            embed = await self._build_embed()
            await interaction.response.edit_message(embed=embed, view=self)

        @discord.ui.button(label="🔀 Random", style=discord.ButtonStyle.primary)
        async def random_button(self, interaction: discord.Interaction, button: discord.ui.Button):
            guild_id = interaction.guild.id if interaction.guild else 0
            new_id = await self.cog.get_random_file(guild_id=guild_id, exclude_id=self.file_id)
            if not new_id:
                await interaction.response.send_message("No other files available!", ephemeral=True)
                return
            images = await self.cog._validate_and_fix_images_for_file(new_id)
            info = await self.cog.get_file_info(new_id)
            if not info:
                await interaction.response.send_message("Failed to load file.", ephemeral=True)
                return
            contributor_name, anilist_username, anilist_id, al_link, title, desc, created_at, contributor_id, owner_id, owner_name, finalized, file_guild_id = info
            uid, display_name, avatar_url, siteUrl = await self.cog._fetch_anilist_live(anilist_username, anilist_id)
            anilist_name = display_name or anilist_username
            anilist_avatar = avatar_url
            anilist_url = siteUrl or al_link
            new_view = ALFiles.FileView(self.cog, new_id, images, contributor_name, anilist_name, anilist_avatar, anilist_url, title, desc, contributor_id, owner_id)
            # initialize like label and style for the invoking user
            await new_view._refresh_like_button_for_user(interaction.user.id)
            embed = await new_view._build_embed()
            await interaction.response.edit_message(embed=embed, view=new_view)

        # dynamic Like button handler/creator
        async def _refresh_like_button_for_user(self, user_id: int):
            """
            Ensure like_btn label and style reflect current like count and whether 'user_id' has liked it.
            """
            count = await self.cog.get_like_count(self.file_id)
            liked = await self.cog.has_liked(self.file_id, user_id)
            self.like_btn.label = f"💙 {count}"
            # style: green if liked, blurple if neutral
            if liked:
                self.like_btn.style = discord.ButtonStyle.success  # green
            else:
                self.like_btn.style = discord.ButtonStyle.blurple  # blue-ish
            # callback already bound to handler below (we assign via attribute)
            # ensure callback set
            self.like_btn.callback = self._on_like_pressed

        async def _on_like_pressed(self, interaction: discord.Interaction):
            user = interaction.user
            last = self.cog.like_cooldowns.get(user.id, 0)
            if time.time() - last < LIKE_TOGGLE_COOLDOWN:
                await interaction.response.send_message(f"You're liking too fast — wait {LIKE_TOGGLE_COOLDOWN}s between toggles.", ephemeral=True)
                return
            self.cog.like_cooldowns[user.id] = time.time()
            try:
                is_now_liked, new_count = await self.cog.toggle_like(self.file_id, user.id)
                # update button label & style
                self.like_btn.label = f"💙 {new_count}"
                if is_now_liked:
                    self.like_btn.style = discord.ButtonStyle.success  # green
                    await interaction.response.send_message("✅ You liked this file!", ephemeral=True)
                else:
                    # for unliked make it red briefly then neutral
                    self.like_btn.style = discord.ButtonStyle.danger
                    await interaction.response.send_message("💔 Like removed.", ephemeral=True)
                    # set to blurple after small delay to indicate neutral
                    await asyncio.sleep(0.25)
                    self.like_btn.style = discord.ButtonStyle.blurple
                # update displayed message
                embed = await self._build_embed()
                try:
                    await interaction.message.edit(embed=embed, view=self)
                except Exception:
                    # fallback: respond without editing
                    pass
            except Exception:
                logger.exception("like toggle failed")
                await interaction.response.send_message("❌ Failed to toggle like. Try again later.", ephemeral=True)

    # ------------------------------
    # Commands
    # ------------------------------
    # Scope choices for leaderboards and likes
    SCOPE_CHOICES = [
        app_commands.Choice(name="🏠 Server", value="server"),
        app_commands.Choice(name="🌐 Global", value="global"),
    ]

    @app_commands.command(name="al-files", description="📁 View or contribute AL Files")
    @app_commands.describe(upload="Attach an image (single). Use 'Upload Another (Guided)' to attach up to 10 images in the guided message.", as_user="(Optional) Credit this upload to another Discord user")
    async def al_files(self, interaction: discord.Interaction, upload: Optional[discord.Attachment] = None, as_user: Optional[discord.User] = None):
        guild_id = interaction.guild.id if interaction.guild else 0
        owner = interaction.user
        contributor = as_user or owner

        if upload:
            if not upload.content_type or not upload.content_type.startswith("image/"):
                await interaction.response.send_message("❌ Please attach an image file (png/jpg/gif).", ephemeral=True)
                return
            draft = await self.get_draft(guild_id, owner.id)
            if not draft:
                file_id = await self.create_draft(guild_id, owner, contributor)
            else:
                file_id = draft[0]
                # update contributor credit if it changed
                async with aiosqlite.connect(self.db_path) as db:
                    await db.execute("UPDATE files SET contributor_id = ?, contributor_name = ? WHERE id = ?", (contributor.id, str(contributor), file_id))
                    await db.commit()
            ok = await self.add_image_to_draft(file_id, upload.url)
            if not ok:
                await interaction.response.send_message("❌ Failed to add image to draft.", ephemeral=True)
                return
            embed = discord.Embed(title=f"📁 Draft #{file_id}", description=f"Image added to draft (credited to {str(contributor)}).", color=get_color())
            embed.add_field(name="Next", value="Use the buttons below to add more (URL) or attach multiple images in one message with 'Upload Another (Guided)'.", inline=False)
            view = ALFiles.AddMoreView(self, file_id)
            await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
            return

        # VIEW random finalized file
        await interaction.response.defer()
        rand_id = await self.get_random_file(guild_id=guild_id)
        if not rand_id:
            await interaction.followup.send("❌ No finalized files yet in this server.", ephemeral=True)
            return
        # validate images to ensure they are still accessible
        images = await self._validate_and_fix_images_for_file(rand_id)
        info = await self.get_file_info(rand_id)
        if not info:
            await interaction.followup.send("❌ Failed to load file metadata.", ephemeral=True)
            return
        contributor_name, anilist_username, anilist_id, al_link, title, desc, created_at, contributor_id, owner_id, owner_name, finalized, file_guild_id = info
        uid, display_name, avatar_url, siteUrl = await self._fetch_anilist_live(anilist_username, anilist_id)
        anilist_name = display_name or anilist_username
        anilist_avatar = avatar_url
        anilist_url = siteUrl or al_link
        embed = discord.Embed(title=title or f"📁 File #{rand_id}", description=desc or None, color=get_color())
        if images:
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
        # initialize like button label & style for the invoking user
        await view._refresh_like_button_for_user(interaction.user.id)
        await interaction.followup.send(embed=embed, view=view)

    @app_commands.command(name="al-release", description="✅ Release your drafted AL file")
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
        # Attempt to refresh AniList info and persist
        try:
            info = await self.get_file_info(file_id)
            if info:
                anilist_username = info[1]
                anilist_id = info[2]
                uid, display_name, avatar_url, siteUrl = await self._fetch_anilist_live(anilist_username, anilist_id)
                if uid or display_name or avatar_url or siteUrl:
                    al_link = siteUrl or (f"https://anilist.co/user/{anilist_username}" if anilist_username else None)
                    async with aiosqlite.connect(self.db_path) as db:
                        await db.execute("UPDATE files SET anilist_id = ?, anilist_username = ?, al_link = ? WHERE id = ?", (uid, display_name or anilist_username, al_link, file_id))
                        await db.commit()
        except Exception:
            logger.debug("Non-fatal: failed to refresh AniList on release", exc_info=True)
        # Validate images before asking for confirmation
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
            await interaction.followup.send("You have not contributed any files.", ephemeral=True)
            return
        options = []
        for fid, finalized, created_at, image_count in files:
            options.append(discord.SelectOption(label=f"#{fid} • {image_count} img{'s' if image_count != 1 else ''}", value=str(fid), description="finalized" if finalized else "draft"))
        view = ALFiles.DeleteSelectView(self, options)
        await interaction.followup.send("Select the file you want to delete:", view=view, ephemeral=True)

    @app_commands.command(name="al-lb", description="🏆 View contributors leaderboard (server/global)")
    @app_commands.choices(scope=SCOPE_CHOICES)
    async def al_lb(self, interaction: discord.Interaction, scope: app_commands.Choice[str]):
        await interaction.response.defer()
        guild_id = interaction.guild.id if interaction.guild else None
        if scope.value == "global":
            query = """
                SELECT contributor_name, COUNT(id) as total
                FROM files WHERE finalized = 1
                GROUP BY contributor_id
                ORDER BY total DESC
                LIMIT 25
            """
            title = "🏆 AL Contributors — Global"
            params = ()
        else:
            query = """
                SELECT contributor_name, COUNT(id) as total
                FROM files WHERE finalized = 1 AND guild_id = ?
                GROUP BY contributor_id
                ORDER BY total DESC
                LIMIT 25
            """
            title = f"🏆 AL Contributors — Server: {interaction.guild.name if interaction.guild else 'DM'}"
            params = (guild_id,)
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(query, params) as cur:
                rows = await cur.fetchall()
        if not rows:
            await interaction.followup.send("❌ No contributors yet for that scope.", ephemeral=True)
            return
        embed = discord.Embed(title=title, description="Top contributors", color=get_color())
        medals = ["🥇", "🥈", "🥉"]
        for i, (name, count) in enumerate(rows, start=1):
            medal = medals[i-1] if i <= 3 else f"#{i}"
            embed.add_field(name=f"{medal} {name}", value=f"📁 {count} file{'s' if count != 1 else ''}", inline=False)
        # totals
        async with aiosqlite.connect(self.db_path) as db:
            if scope.value == "global":
                async with db.execute("SELECT COUNT(DISTINCT contributor_id) FROM files WHERE finalized = 1") as c:
                    total_contrib = (await c.fetchone())[0]
                async with db.execute("SELECT COUNT(id) FROM files WHERE finalized = 1") as c:
                    total_files = (await c.fetchone())[0]
                async with db.execute("SELECT COUNT(id) FROM images WHERE file_id IN (SELECT id FROM files WHERE finalized = 1)") as c:
                    total_images = (await c.fetchone())[0]
            else:
                async with db.execute("SELECT COUNT(DISTINCT contributor_id) FROM files WHERE finalized = 1 AND guild_id = ?", (guild_id,)) as c:
                    total_contrib = (await c.fetchone())[0]
                async with db.execute("SELECT COUNT(id) FROM files WHERE finalized = 1 AND guild_id = ?", (guild_id,)) as c:
                    total_files = (await c.fetchone())[0]
                async with db.execute("SELECT COUNT(i.id) FROM images i JOIN files f ON f.id = i.file_id WHERE f.finalized = 1 AND f.guild_id = ?", (guild_id,)) as c:
                    total_images = (await c.fetchone())[0]
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
        for i, (file_id, cnt) in enumerate(top, start=1):
            info = await self.get_file_info(file_id)
            if not info:
                continue
            contributor_name, anilist_username, anilist_id, al_link, title_text, description, created_at, contributor_id, owner_id, owner_name, finalized, file_guild_id = info
            embed.add_field(name=f"{i}. #{file_id} — {contributor_name} • {cnt} like{'s' if cnt != 1 else ''}", value=title_text or "—", inline=False)
        await interaction.followup.send(embed=embed)

    @app_commands.command(name="al-liked", description="💾 Show files you have liked (ephemeral)")
    async def al_liked(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        user_id = interaction.user.id
        liked = await self.get_files_liked_by_user(user_id)
        if not liked:
            await interaction.followup.send("You haven't liked any files yet.", ephemeral=True)
            return
        # paginate 5 per page if many
        per_page = 5
        pages = [liked[i:i+per_page] for i in range(0, len(liked), per_page)]
        # show first page with buttons to navigate ephemeral (we'll supply simple navigation)
        current_page = 0

        async def make_embed_for_page(page_idx: int):
            page = pages[page_idx]
            embed = discord.Embed(title=f"💾 Your liked files — page {page_idx+1}/{len(pages)}", color=get_color())
            for fid, cnt in page:
                info = await self.get_file_info(fid)
                if not info:
                    embed.add_field(name=f"#{fid}", value=f"{cnt} likes — (metadata missing)", inline=False)
                    continue
                contributor_name, anilist_username, anilist_id, al_link, title_text, description, created_at, contributor_id, owner_id, owner_name, finalized, file_guild_id = info
                # small preview: embed field with title & contributor
                embed.add_field(name=f"#{fid} — {title_text or '—'}", value=f"{contributor_name} • {cnt} like{'s' if cnt != 1 else ''}", inline=False)
            return embed

        view = discord.ui.View(timeout=120)

        # nav buttons
        class Prev(discord.ui.Button):
            def __init__(self):
                super().__init__(label="⬅️ Prev", style=discord.ButtonStyle.secondary)
            async def callback(_, inter: discord.Interaction):
                nonlocal current_page
                if current_page == 0:
                    await inter.response.send_message("You're on the first page.", ephemeral=True)
                    return
                current_page -= 1
                await inter.response.edit_message(embed=await make_embed_for_page(current_page), view=view)

        class Next(discord.ui.Button):
            def __init__(self):
                super().__init__(label="➡️ Next", style=discord.ButtonStyle.secondary)
            async def callback(_, inter: discord.Interaction):
                nonlocal current_page
                if current_page >= len(pages)-1:
                    await inter.response.send_message("You're on the last page.", ephemeral=True)
                    return
                current_page += 1
                await inter.response.edit_message(embed=await make_embed_for_page(current_page), view=view)

        view.add_item(Prev())
        view.add_item(Next())
        await interaction.followup.send(embed=await make_embed_for_page(current_page), view=view, ephemeral=True)

    @app_commands.command(name="al-search", description="🔍 Search a file by number (ID)")
    @app_commands.describe(file_number="ID number of the file to search")
    async def al_search(self, interaction: discord.Interaction, file_number: int):
        await interaction.response.defer()
        info = await self.get_file_info(file_number)
        if not info:
            await interaction.followup.send(f"❌ No file found with ID #{file_number}.", ephemeral=True)
            return
        # validate images
        images = await self._validate_and_fix_images_for_file(file_number)
        contributor_name, anilist_username, anilist_id, al_link, title, desc, created_at, contributor_id, owner_id, owner_name, finalized, file_guild_id = info
        uid, display_name, avatar_url, siteUrl = await self._fetch_anilist_live(anilist_username, anilist_id)
        anilist_name = display_name or anilist_username
        anilist_avatar = avatar_url
        anilist_url = siteUrl or al_link
        embed = discord.Embed(title=title or f"📁 File #{file_number}", description=desc or None, color=get_color())
        if images:
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
        embed = discord.Embed(title=f"📋 Draft #{file_id}", description=desc or "Your current draft", color=get_color())
        embed.add_field(name="📸 Images", value=f"{len(images)} image{'s' if len(images) != 1 else ''}", inline=True)
        embed.add_field(name="✅ Status", value="Ready to release!" if images else "⚠️ No images yet", inline=True)
        if images:
            embed.set_thumbnail(url=images[0])
            embed.add_field(name="📤 Next Step", value="Use `/al-release` to publish your file (confirm required).", inline=False)
        else:
            embed.add_field(name="📤 Next Step", value="Use `/al-files` with an attachment to add images!", inline=False)
        view = ALFiles.AddMoreView(self, file_id)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    # ------------------------------
    # Lifecycle hooks
    # ------------------------------
    async def cog_load(self):
        await self.setup_db()
        # Validate all images in DB on startup (non-blocking but we run in background)
        asyncio.create_task(self._validate_all_images_on_startup())
        logger.info("[ALFiles] Cog loaded and DB ready")

    async def cog_unload(self):
        logger.info("[ALFiles] Cog unloading")

    async def _validate_all_images_on_startup(self):
        """
        Validate images for all files at startup. This logs invalid images to console.
        Runs asynchronously to avoid blocking startup for too long.
        """
        logger.info("[ALFiles] Starting image validation for existing files (background)...")
        try:
            async with aiosqlite.connect(self.db_path) as db:
                async with db.execute("SELECT id FROM files") as cur:
                    rows = await cur.fetchall()
                # Iterate but don't hog event loop
                for (fid,) in rows:
                    images = await self.get_file_images(fid)
                    for url in images:
                        ok = await self._validate_image_url(url)
                        if not ok:
                            logger.warning("[ALFiles] Startup check: File #%s image invalid/expired: %s", fid, url)
                    await asyncio.sleep(0.01)  # small yield
        except Exception:
            logger.exception("[ALFiles] Error during startup image validation")
        logger.info("[ALFiles] Image validation background task complete")

# Entrypoint
async def setup(bot: commands.Bot):
    await bot.add_cog(ALFiles(bot))
    logger.info("ALFiles cog setup complete")
