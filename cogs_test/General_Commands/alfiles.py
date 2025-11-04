# cogs/alfiles.py
# ALFiles cog — multi-guild, auto-migrating, AniList live fetch + cache, guided multi-upload (up to 10 images)
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
try:
    from helpers.utility_helper import get_user_display_name, is_valid_url, make_http_request
except Exception:
    # provide simple fallbacks
    async def get_user_display_name(user_id: int, guild_id: int) -> Optional[str]:
        return None

    def is_valid_url(url: str) -> bool:
        try:
            return url.startswith("http://") or url.startswith("https://")
        except Exception:
            return False

    async def make_http_request(url: str, method: str = "GET", json_data: Any = None, timeout: int = 10, headers: Dict[str, str] = None):
        # naive fallback using aiohttp returning parsed json for POST JSON requests
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

# configuration
ANILIST_CACHE_TTL = 60 * 60 * 24  # 24 hours
ANILIST_RATE_LIMIT = (5, 1.0)  # token capacity 5, refill 1 token/sec (naive)
ANILIST_TIMEOUT = 10
MAX_MULTI_UPLOAD = 10  # limit per message


def get_color() -> discord.Color:
    return discord.Color.from_rgb(245, 245, 245)


# --------------------
# Utilities: rate limiter & cache
# --------------------
class TokenBucket:
    def __init__(self, capacity: int, refill_per_sec: float):
        self.capacity = capacity
        self.tokens = capacity
        self.refill_per_sec = refill_per_sec
        self.last = time.monotonic()
        self._lock = asyncio.Lock()

    async def acquire(self):
        async with self._lock:
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
        # post-wait consume
        async with self._lock:
            self.tokens = max(0, self.tokens - 1)
            return


class FileCache:
    def __init__(self, path: str = CACHE_PATH, ttl: int = ANILIST_CACHE_TTL):
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
            logger.exception("Failed to load cache")
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
                logger.exception("Failed to persist cache")


# --------------------
# The Cog
# --------------------
class ALFiles(commands.Cog):
    """AL Files: AniList profile image gallery with multi-guild support and rich UX."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.db_path = DB_PATH
        self.anilist_cache = FileCache()
        self.anilist_rl = TokenBucket(ANILIST_RATE_LIMIT[0], ANILIST_RATE_LIMIT[1])
        Path("data").mkdir(parents=True, exist_ok=True)

    # --------------------
    # DB migration & init
    # --------------------
    async def setup_db(self):
        """
        Create tables if missing and add missing columns (safe ALTER TABLE migrations).
        """
        create_files = """
            CREATE TABLE IF NOT EXISTS files (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id INTEGER,
                contributor_id INTEGER,
                contributor_name TEXT,
                al_link TEXT,
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
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(create_files)
            await db.execute(create_images)
            await db.commit()

            # required extra columns
            wanted_cols = {
                "anilist_username": "TEXT",
                "anilist_id": "INTEGER",
                "title": "TEXT",
                "description": "TEXT"
            }
            async with db.execute("PRAGMA table_info(files)") as cursor:
                rows = await cursor.fetchall()
                existing = {r[1] for r in rows}
            for col, coltype in wanted_cols.items():
                if col not in existing:
                    try:
                        await db.execute(f"ALTER TABLE files ADD COLUMN {col} {coltype}")
                        logger.info("Added column '%s' to files table", col)
                    except Exception:
                        logger.exception("Failed to add column %s", col)
            await db.commit()

    # --------------------
    # AniList live fetch (with cache & rate-limit)
    # --------------------
    async def _fetch_anilist_live(self, username: Optional[str] = None, anilist_id: Optional[int] = None) -> Tuple[Optional[int], Optional[str], Optional[str], Optional[str]]:
        if not username and not anilist_id:
            return None, None, None, None

        key = f"id:{anilist_id}" if anilist_id else f"name:{username}"
        cached = await self.anilist_cache.get(key)
        if cached:
            return cached.get("id"), cached.get("name"), cached.get("avatar"), cached.get("siteUrl")

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
            logger.debug("make_http_request failed; falling back to aiohttp", exc_info=True)

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
            logger.exception("AniList aiohttp fetch failed")

        return None, None, None, None

    # --------------------
    # DB CRUD helpers
    # --------------------
    async def create_draft(self, guild_id: int, user: discord.abc.User) -> int:
        # try to fetch anilist mapping from helper if available
        anilist_username = None
        anilist_id = None
        al_link = None
        try:
            possible = await get_user_display_name(user.id, guild_id)
            if possible and isinstance(possible, str):
                anilist_username = possible
                al_link = f"https://anilist.co/user/{anilist_username}"
        except Exception:
            logger.debug("get_user_display_name not available or failed", exc_info=True)

        async with aiosqlite.connect(self.db_path) as db:
            cur = await db.execute(
                "INSERT INTO files (guild_id, contributor_id, contributor_name, anilist_username, anilist_id, al_link, finalized) VALUES (?, ?, ?, ?, ?, ?, 0)",
                (guild_id, user.id, str(user), anilist_username, anilist_id, al_link)
            )
            await db.commit()
            return cur.lastrowid

    async def get_draft(self, guild_id: int, user_id: int) -> Optional[Tuple[int]]:
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute("SELECT id FROM files WHERE guild_id = ? AND contributor_id = ? AND finalized = 0", (guild_id, user_id)) as cur:
                return await cur.fetchone()

    async def add_image_to_draft(self, file_id: int, url: str) -> bool:
        if not is_valid_url(url):
            logger.debug("Rejected invalid url for draft %s: %s", file_id, url)
            return False
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("INSERT INTO images (file_id, image_url) VALUES (?, ?)", (file_id, url))
            await db.commit()
        return True

    async def update_draft_meta(self, file_id: int, title: Optional[str], description: Optional[str]):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("UPDATE files SET title = ?, description = ? WHERE id = ?", (title, description, file_id))
            await db.commit()

    async def finalize_file(self, file_id: int):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("UPDATE files SET finalized = 1 WHERE id = ?", (file_id,))
            await db.commit()

    async def delete_file(self, file_id: int):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("DELETE FROM images WHERE file_id = ?", (file_id,))
            await db.execute("DELETE FROM files WHERE id = ?", (file_id,))
            await db.commit()

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
            async with db.execute("SELECT contributor_name, anilist_username, anilist_id, al_link, title, description, created_at, contributor_id, finalized, guild_id FROM files WHERE id = ?", (file_id,)) as cur:
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

    # --------------------
    # Guided upload: accept up to 10 attachments or URLs in a single message
    # --------------------
    async def prompt_for_attachments(self, interaction: discord.Interaction, timeout: int = 60) -> Optional[List[str]]:
        """
        Send an ephemeral prompt and wait for the user to post a message in the same channel
        containing attachments and/or URLs. Returns up to MAX_MULTI_UPLOAD unique image URLs, or None on timeout.
        """
        user = interaction.user
        channel = interaction.channel
        try:
            await interaction.followup.send("📤 Please upload up to 10 images in one message (attach them) or paste direct image URLs in the message. You have 60s.", ephemeral=True)
        except Exception:
            # fallback
            await interaction.response.send_message("📤 Please upload up to 10 images in one message (attach them) or paste direct image URLs in the message. You have 60s.", ephemeral=True)

        def check(msg: discord.Message):
            return msg.author.id == user.id and msg.channel.id == (channel.id if channel else None)

        try:
            msg = await self.bot.wait_for("message", timeout=timeout, check=check)
        except asyncio.TimeoutError:
            return None

        urls: List[str] = []
        # attachments
        for att in msg.attachments[:MAX_MULTI_UPLOAD]:
            try:
                if att.content_type and att.content_type.startswith("image/"):
                    urls.append(att.url)
                elif is_valid_url(att.url):
                    urls.append(att.url)
            except Exception:
                # still try to use .url if looks like http
                if is_valid_url(att.url):
                    urls.append(att.url)
        # also parse message content for URLs (naive token split)
        tokens = (msg.content or "").split()
        for t in tokens:
            if len(urls) >= MAX_MULTI_UPLOAD:
                break
            if is_valid_url(t):
                urls.append(t)
        # deduplicate while preserving order
        seen = set()
        deduped = []
        for u in urls:
            if u not in seen:
                seen.add(u)
                deduped.append(u)
            if len(deduped) >= MAX_MULTI_UPLOAD:
                break
        return deduped if deduped else None

    # --------------------
    # Small helper: resolve discord avatar for contributor (returns URL or None)
    # --------------------
    async def _get_contributor_avatar_url(self, contributor_id: int) -> Optional[str]:
        # Try a cached/get_user then fetch_user fallback
        try:
            user = self.bot.get_user(contributor_id)
            if not user:
                user = await self.bot.fetch_user(contributor_id)
            if user:
                return str(user.display_avatar.url)
        except Exception:
            logger.debug("Could not fetch contributor avatar for %s", contributor_id, exc_info=True)
        return None

    # --------------------
    # UI: Modals & Views
    # --------------------
    class AddImageModal(discord.ui.Modal, title="Add Image URL"):
        image_url = discord.ui.TextInput(label="Image URL (optional)", required=False, placeholder="https://...")

        def __init__(self, cog, file_id: int):
            super().__init__()
            self.cog = cog
            self.file_id = file_id

        async def on_submit(self, interaction: discord.Interaction):
            url = self.image_url.value.strip() if self.image_url.value else None
            if not url:
                await interaction.response.send_message("❌ No URL provided. Use the guided upload button to attach files or paste a URL.", ephemeral=True)
                return
            if not is_valid_url(url):
                await interaction.response.send_message("❌ That doesn't look like a direct image URL.", ephemeral=True)
                return
            ok = await self.cog.add_image_to_draft(self.file_id, url)
            if ok:
                await interaction.response.send_message("✅ Image added to draft.", ephemeral=True)
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

    class AddMoreView(discord.ui.View):
        def __init__(self, cog, file_id: int):
            super().__init__(timeout=180)
            self.cog = cog
            self.file_id = file_id

        @discord.ui.button(label="➕ Add (URL)", style=discord.ButtonStyle.primary)
        async def add_url(self, interaction: discord.Interaction, _):
            await interaction.response.send_modal(ALFiles.AddImageModal(self.cog, self.file_id))

        @discord.ui.button(label="📤 Upload Another (Guided)", style=discord.ButtonStyle.success)
        async def guided_upload(self, interaction: discord.Interaction, _):
            # Defer ephemeral while waiting
            await interaction.response.defer(ephemeral=True)
            urls = await self.cog.prompt_for_attachments(interaction, timeout=60)
            if not urls:
                await interaction.followup.send("⌛ Timed out — no images received.", ephemeral=True)
                return
            added = 0
            for url in urls:
                if await self.cog.add_image_to_draft(self.file_id, url):
                    added += 1
            await interaction.followup.send(f"✅ Added {added}/{len(urls)} image{'s' if added != 1 else ''} to your draft.", ephemeral=True)

        @discord.ui.button(label="📝 Edit Title & Description", style=discord.ButtonStyle.secondary)
        async def edit_meta(self, interaction: discord.Interaction, _):
            await interaction.response.send_modal(ALFiles.EditMetaModal(self.cog, self.file_id))

        @discord.ui.button(label="Done", style=discord.ButtonStyle.success)
        async def done(self, interaction: discord.Interaction, _):
            await interaction.response.send_message("Saved. Use `/al-release` to publish your draft when ready.", ephemeral=True)

    class FileView(discord.ui.View):
        def __init__(self, cog, file_id: int, images: List[str], contributor_name: str, anilist_name: Optional[str], anilist_avatar: Optional[str], anilist_url: Optional[str], title: Optional[str], description: Optional[str], contributor_id: Optional[int]):
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

        async def _build_embed(self):
            embed = discord.Embed(title=self.title or f"📁 File #{self.file_id}", description=self.description or None, color=get_color())
            if self.images:
                embed.set_image(url=self.images[self.index])
            # AniList author at top if available
            if self.anilist_name and self.anilist_url:
                embed.set_author(name=self.anilist_name, url=self.anilist_url, icon_url=self.anilist_avatar)
            else:
                embed.set_author(name=self.contributor_name)
            # Contributor info in footer (discord username + pfp if resolvable)
            footer_text = f"Contributed by {self.contributor_name}"
            footer_icon = None
            if self.contributor_id:
                footer_icon = await self.cog._get_contributor_avatar_url(self.contributor_id)
            if footer_icon:
                embed.set_footer(text=footer_text, icon_url=footer_icon)
            else:
                embed.set_footer(text=footer_text)
            return embed

        async def update_embed(self, interaction: discord.Interaction):
            embed = await self._build_embed()
            await interaction.response.edit_message(embed=embed, view=self)

        @discord.ui.button(label="⬅️ Prev", style=discord.ButtonStyle.secondary)
        async def prev(self, interaction: discord.Interaction, _):
            if not self.images:
                await interaction.response.send_message("No images", ephemeral=True)
                return
            self.index = (self.index - 1) % len(self.images)
            await self.update_embed(interaction)

        @discord.ui.button(label="➡️ Next", style=discord.ButtonStyle.secondary)
        async def next(self, interaction: discord.Interaction, _):
            if not self.images:
                await interaction.response.send_message("No images", ephemeral=True)
                return
            self.index = (self.index + 1) % len(self.images)
            await self.update_embed(interaction)

        @discord.ui.button(label="🔀 Random", style=discord.ButtonStyle.primary)
        async def random_btn(self, interaction: discord.Interaction, _):
            guild_id = interaction.guild.id if interaction.guild else 0
            new_id = await self.cog.get_random_file(guild_id=guild_id, exclude_id=self.file_id)
            if not new_id:
                await interaction.response.send_message("No other files available!", ephemeral=True)
                return
            images = await self.cog.get_file_images(new_id)
            info = await self.cog.get_file_info(new_id)
            if not info or not images:
                await interaction.response.send_message("Failed to load file.", ephemeral=True)
                return
            contributor_name, anilist_username, anilist_id, al_link, title, description, created_at, contributor_id, finalized, file_guild_id = info
            uid, display_name, avatar_url, siteUrl = await self.cog._fetch_anilist_live(anilist_username, anilist_id)
            anilist_name = display_name or anilist_username
            anilist_avatar = avatar_url
            anilist_url = siteUrl or al_link
            new_view = ALFiles.FileView(self.cog, new_id, images, contributor_name, anilist_name, anilist_avatar, anilist_url, title, description, contributor_id)
            embed = await new_view._build_embed()
            await interaction.response.edit_message(embed=embed, view=new_view)

    class ALReleaseConfirm(discord.ui.View):
        def __init__(self, cog, file_id: int):
            super().__init__(timeout=60)
            self.cog = cog
            self.file_id = file_id

        @discord.ui.button(label="✅ Confirm Release", style=discord.ButtonStyle.success)
        async def confirm(self, interaction: discord.Interaction, _):
            await self.cog.finalize_file(self.file_id)
            await interaction.response.edit_message(content=f"✅ File #{self.file_id} released successfully!", embed=None, view=None)

        @discord.ui.button(label="❌ Cancel", style=discord.ButtonStyle.danger)
        async def cancel(self, interaction: discord.Interaction, _):
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
            contributor_name, anilist_username, anilist_id, al_link, title, desc, created_at, contributor_id, finalized, file_guild_id = info
            uid, display_name, avatar_url, siteUrl = await self.cog._fetch_anilist_live(anilist_username, anilist_id)
            anilist_name = display_name or anilist_username
            anilist_avatar = avatar_url
            anilist_url = siteUrl or al_link
            embed = discord.Embed(title=f"Delete Preview — File #{file_id}", description=desc or None, color=get_color())
            if images:
                embed.set_image(url=images[0])
            if anilist_name and anilist_url:
                embed.set_author(name=anilist_name, url=anilist_url, icon_url=anilist_avatar)
            else:
                embed.set_author(name=contributor_name)
            # footer: contributor discord avatar if resolvable
            footer_icon = await self.cog._get_contributor_avatar_url(contributor_id)
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

    class DeleteConfirmButton(discord.ui.Button):
        def __init__(self, cog, file_id: int):
            super().__init__(label="Delete File", style=discord.ButtonStyle.danger)
            self.cog = cog
            self.file_id = file_id

        async def callback(self, interaction: discord.Interaction):
            await self.cog.delete_file(self.file_id)
            await interaction.response.edit_message(content=f"🗑️ File #{self.file_id} has been deleted.", embed=None, view=None)

    class CancelButton(discord.ui.Button):
        def __init__(self):
            super().__init__(label="Cancel", style=discord.ButtonStyle.secondary)

        async def callback(self, interaction: discord.Interaction):
            await interaction.response.edit_message(content="Cancelled.", embed=None, view=None)

    # --------------------
    # Commands (slash only)
    # --------------------
    @app_commands.command(name="al-files", description="📁 View or contribute AL Files (AniList profile images)")
    @app_commands.describe(upload="Attach an image to add to your draft (single attachment). To add multiple in one go, use 'Upload Another (Guided)' and attach up to 10 images in the guided message.)")
    async def al_files(self, interaction: discord.Interaction, upload: Optional[discord.Attachment] = None):
        guild_id = interaction.guild.id if interaction.guild else 0
        user = interaction.user

        # UPLOAD flow (single attachment per slash invocation)
        if upload:
            if not upload.content_type or not upload.content_type.startswith("image/"):
                await interaction.response.send_message("❌ Please upload a valid image file!", ephemeral=True)
                return
            draft = await self.get_draft(guild_id, user.id)
            if not draft:
                file_id = await self.create_draft(guild_id, user)
            else:
                file_id = draft[0]
            ok = await self.add_image_to_draft(file_id, upload.url)
            if not ok:
                await interaction.response.send_message("❌ Failed to add image. URL invalid or DB error.", ephemeral=True)
                return
            embed = discord.Embed(title=f"📁 Draft #{file_id}", description="Image added to your draft.", color=get_color())
            embed.add_field(name="Next", value="Use 'Add (URL)' to paste a direct link or 'Upload Another (Guided)' to attach up to 10 images in one message.", inline=False)
            view = ALFiles.AddMoreView(self, file_id)
            await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
            return

        # VIEW random finalized file in this guild
        await interaction.response.defer()
        rand_id = await self.get_random_file(guild_id=guild_id)
        if not rand_id:
            await interaction.followup.send("❌ No finalized files yet in this server.", ephemeral=True)
            return
        images = await self.get_file_images(rand_id)
        info = await self.get_file_info(rand_id)
        if not info or not images:
            await interaction.followup.send("❌ Failed to load file.", ephemeral=True)
            return
        contributor_name, anilist_username, anilist_id, al_link, title, desc, created_at, contributor_id, finalized, file_guild_id = info
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
        footer_icon = await self._get_contributor_avatar_url(contributor_id)
        if footer_icon:
            embed.set_footer(text=f"Contributed by {contributor_name}", icon_url=footer_icon)
        else:
            embed.set_footer(text=f"Contributed by {contributor_name}")
        view = ALFiles.FileView(self, rand_id, images, contributor_name, anilist_name, anilist_avatar, anilist_url, title, desc, contributor_id)
        await interaction.followup.send(embed=embed, view=view)

    @app_commands.command(name="al-release", description="✅ Release your drafted AL file to the public gallery")
    async def al_release(self, interaction: discord.Interaction):
        guild_id = interaction.guild.id if interaction.guild else 0
        draft = await self.get_draft(guild_id, interaction.user.id)
        if not draft:
            await interaction.response.send_message("❌ You don't have an active draft.", ephemeral=True)
            return
        file_id = draft[0]
        images = await self.get_file_images(file_id)
        if not images:
            await interaction.response.send_message("❌ Draft has no images.", ephemeral=True)
            return

        # refresh AniList live info if possible, persist
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
            logger.debug("Non-fatal: refresh AniList failed on release", exc_info=True)

        embed = discord.Embed(title=f"Confirm release — File #{file_id}", color=get_color())
        embed.set_image(url=images[0])
        embed.add_field(name="Images", value=str(len(images)), inline=True)
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
            label = f"#{fid} • {image_count} img{'s' if image_count != 1 else ''}"
            desc = "finalized" if finalized else "draft"
            options.append(discord.SelectOption(label=label, value=str(fid), description=desc))
        view = ALFiles.DeleteSelectView(self, options)
        await interaction.followup.send("Select which file you want to delete:", view=view, ephemeral=True)

    @app_commands.command(name="al-lb", description="🏆 Show AL contributors leaderboard")
    async def al_lb(self, interaction: discord.Interaction):
        guild_id = interaction.guild.id if interaction.guild else 0
        await interaction.response.defer()
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute("""
                SELECT contributor_name, COUNT(id) as total
                FROM files WHERE finalized = 1 AND guild_id = ?
                GROUP BY contributor_id
                ORDER BY total DESC
                LIMIT 25
            """, (guild_id,)) as cur:
                rows = await cur.fetchall()
            if not rows:
                await interaction.followup.send("❌ No contributors yet in this server.", ephemeral=True)
                return
            embed = discord.Embed(title="🏆 AL Contributors Leaderboard", description="Top contributors in this server", color=get_color())
            medals = ["🥇", "🥈", "🥉"]
            for i, (name, count) in enumerate(rows, start=1):
                medal = medals[i-1] if i <= 3 else f"#{i}"
                embed.add_field(name=f"{medal} {name}", value=f"📁 {count} file{'s' if count != 1 else ''}", inline=False)
            async with db.execute("SELECT COUNT(DISTINCT contributor_id) FROM files WHERE finalized = 1 AND guild_id = ?", (guild_id,)) as c:
                total_contrib = (await c.fetchone())[0]
            async with db.execute("SELECT COUNT(id) FROM files WHERE finalized = 1 AND guild_id = ?", (guild_id,)) as c:
                total_files = (await c.fetchone())[0]
            async with db.execute("SELECT COUNT(i.id) FROM images i JOIN files f ON f.id = i.file_id WHERE f.finalized = 1 AND f.guild_id = ?", (guild_id,)) as c:
                total_images = (await c.fetchone())[0]
            embed.set_footer(text=f"👥 {total_contrib} contributors • 📁 {total_files} files • 📸 {total_images}")
            await interaction.followup.send(embed=embed)

    @app_commands.command(name="al-draft", description="📋 View your current draft status")
    async def al_draft(self, interaction: discord.Interaction):
        guild_id = interaction.guild.id if interaction.guild else 0
        draft = await self.get_draft(guild_id, interaction.user.id)
        if not draft:
            await interaction.response.send_message("📭 You don't have an active draft. Use `/al-files upload:[image]` to create one!", ephemeral=True)
            return
        file_id = draft[0]
        images = await self.get_file_images(file_id)
        info = await self.get_file_info(file_id)
        title = info[4] if info else None
        desc = info[5] if info else None
        embed = discord.Embed(title=f"📋 Draft #{file_id}", description=desc or "Your current draft file", color=get_color())
        embed.add_field(name="📸 Images", value=f"{len(images)} image{'s' if len(images) != 1 else ''}", inline=True)
        embed.add_field(name="✅ Status", value="Ready to release!" if images else "⚠️ No images yet", inline=True)
        if images:
            embed.set_thumbnail(url=images[0])
            embed.add_field(name="📤 Next Step", value="Use `/al-release` to publish your file! (You will be asked to confirm)", inline=False)
        else:
            embed.add_field(name="📤 Next Step", value="Use `/al-files` with an attachment to add images!", inline=False)
        view = ALFiles.AddMoreView(self, file_id)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    # --------------------
    # Lifecycle
    # --------------------
    async def cog_load(self):
        await self.setup_db()
        logger.info("ALFiles cog loaded")

    async def cog_unload(self):
        logger.info("ALFiles cog unloaded")


async def setup(bot: commands.Bot):
    await bot.add_cog(ALFiles(bot))
    logger.info("ALFiles cog setup complete")
