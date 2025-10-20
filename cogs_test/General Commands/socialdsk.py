# social_dsk.py
"""
Social DSK — Enhanced AniList popout Cog
Features added in this version:
 - /social with mode option: "search" (resolve anime/manga and open popout linking to the item) or "home" (open interactive AniList popout + Connect button)
 - 4-layer lookup fallback for search: GraphQL -> HTML meta parse (BS4 or regex) -> search page parse -> local fallback
 - Live aesthetics chooser inside the popout (Select menu updates embed theme)
 - OAuth link generator for AniList "Connect" (requires ANILIST_CLIENT_ID and ANILIST_REDIRECT_URI environment variables)
 - Robust aiohttp usage, retries, timeouts; BeautifulSoup optional parsing
"""

from __future__ import annotations
import asyncio
import aiosqlite
import aiohttp
import os
import re
import json
import random
import logging
from typing import Optional, Dict, Any, Tuple, List

import discord
from discord import app_commands
from discord.ext import commands

# Attempt to import BeautifulSoup for better HTML parsing; if unavailable, use regex fallback
try:
    from bs4 import BeautifulSoup  # type: ignore
    BS4_AVAILABLE = True
except Exception:
    BS4_AVAILABLE = False

LOG = logging.getLogger("SocialDSK")
LOG.setLevel(logging.INFO)

# -------------------------
# Config / Constants
# -------------------------
DB_PATH = "data/social_dsk.db"
os.makedirs(os.path.dirname(DB_PATH), exist_ok=True) if os.path.dirname(DB_PATH) else None

ANILIST_GQL_URL = "https://graphql.anilist.co"
ANILIST_SEARCH_BASE = "https://anilist.co/search/anime?query="
ANILIST_BASE = "https://anilist.co"

# OAuth environment values (optional, provide to enable Connect button with working redirect)
ANILIST_CLIENT_ID = os.environ.get("ANILIST_CLIENT_ID")
ANILIST_REDIRECT_URI = os.environ.get("ANILIST_REDIRECT_URI")  # must be a public reachable endpoint you control

# Themes
THEMES = {
    "darklux": {"name": "DarkLux", "accent": discord.Color.from_rgb(212, 175, 55), "bg": "https://i.imgur.com/8fKQZ6B.jpg"},
    "royal": {"name": "Royal", "accent": discord.Color.from_rgb(65, 105, 225), "bg": "https://i.imgur.com/3G9JX2K.jpg"},
    "forest": {"name": "Forest", "accent": discord.Color.from_rgb(60, 179, 113), "bg": "https://i.imgur.com/2c4Xb4Z.jpg"},
    "sunset": {"name": "Sunset", "accent": discord.Color.from_rgb(255, 99, 71), "bg": "https://i.imgur.com/Lz4Q7jK.jpg"},
}
DEFAULT_THEME = "royal"
USER_COOLDOWN = 1.5  # seconds

# small fallback list to guarantee a result
FALLBACK = [
    {"id": None, "title": "Cowboy Bebop", "url": "https://anilist.co/anime/1", "image": "https://s4.anilist.co/file/anilistcdn/media/anime/cover/large/bx1-BxZQtcQKq9Bp.jpg"},
    {"id": None, "title": "Fullmetal Alchemist: Brotherhood", "url": "https://anilist.co/anime/5114", "image": "https://s4.anilist.co/file/anilistcdn/media/anime/cover/large/bx5114-Ug6rJwW2B0jX.jpg"},
    {"id": None, "title": "Steins;Gate", "url": "https://anilist.co/anime/9259", "image": "https://s4.anilist.co/file/anilistcdn/media/anime/cover/large/bx9259-lhICv3s5q0S8.jpg"},
]

# DB init SQL
SCHEMA = [
    """
    CREATE TABLE IF NOT EXISTS guild_settings (
        guild_id INTEGER PRIMARY KEY,
        theme TEXT,
        accent_hex TEXT,
        bg_url TEXT
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS social_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        guild_id INTEGER,
        user_id INTEGER,
        mode TEXT,
        query TEXT,
        result_url TEXT,
        created_at TEXT DEFAULT (datetime('now'))
    );
    """
]

# -------------------------
# Utilities
# -------------------------
def utcnow_str() -> str:
    from datetime import datetime
    return datetime.utcnow().isoformat() + "Z"

def safe_int(v) -> Optional[int]:
    try:
        return int(v)
    except Exception:
        return None

def build_anilist_search_url(query: str) -> str:
    return ANILIST_SEARCH_BASE + (str(query).strip().replace(" ", "+"))

def build_anilist_item_url(media_type: str, media_id: int) -> str:
    # media_type: "anime" or "manga"
    return f"https://anilist.co/{media_type}/{media_id}"

def anilist_oauth_url(state: Optional[str] = None, scope: str = "read"):
    # Construct AniList OAuth URL for user connect (implicit grant / auth code depending on your app)
    # AniList's OAuth endpoint: https://anilist.co/api/v2/oauth/authorize
    # Note: You must register redirect uri in AniList developer app and implement the redirect handler server-side.
    client = ANILIST_CLIENT_ID
    redirect = ANILIST_REDIRECT_URI
    if not client or not redirect:
        return None
    base = "https://anilist.co/api/v2/oauth/authorize"
    params = f"?client_id={client}&redirect_uri={redirect}&response_type=code&scope={scope}"
    if state:
        params += f"&state={state}"
    return base + params

# -------------------------
# DB wrapper
# -------------------------
class SocialDB:
    def __init__(self, path: str = DB_PATH):
        self.path = path

    async def init(self):
        async with aiosqlite.connect(self.path) as db:
            for s in SCHEMA:
                await db.execute(s)
            await db.commit()

    async def get_guild(self, gid: int) -> Dict[str, Any]:
        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute("SELECT theme, accent_hex, bg_url FROM guild_settings WHERE guild_id = ?", (gid,))
            row = await cur.fetchone()
            await cur.close()
            if not row:
                return {}
            return dict(row)

    async def set_guild(self, gid: int, key: str, value: Any):
        async with aiosqlite.connect(self.path) as db:
            # Upsert pattern
            cur = await db.execute("SELECT guild_id FROM guild_settings WHERE guild_id = ?", (gid,))
            row = await cur.fetchone()
            await cur.close()
            if not row:
                theme = DEFAULT_THEME
                accent = None
                bg = None
                if key == "theme":
                    theme = value
                if key == "accent_hex":
                    accent = value
                if key == "bg_url":
                    bg = value
                await db.execute("INSERT INTO guild_settings (guild_id, theme, accent_hex, bg_url) VALUES (?, ?, ?, ?)", (gid, theme, accent, bg))
            else:
                if key == "theme":
                    await db.execute("UPDATE guild_settings SET theme = ? WHERE guild_id = ?", (value, gid))
                elif key == "accent_hex":
                    await db.execute("UPDATE guild_settings SET accent_hex = ? WHERE guild_id = ?", (value, gid))
                elif key == "bg_url":
                    await db.execute("UPDATE guild_settings SET bg_url = ? WHERE guild_id = ?", (value, gid))
            await db.commit()

    async def log(self, gid: Optional[int], uid: int, mode: str, query: Optional[str], result_url: Optional[str]):
        async with aiosqlite.connect(self.path) as db:
            await db.execute("INSERT INTO social_logs (guild_id, user_id, mode, query, result_url) VALUES (?, ?, ?, ?, ?)",
                             (gid, uid, mode, query, result_url))
            await db.commit()

db = SocialDB()

# -------------------------
# AniList lookup: 4-layer strategy
# -------------------------
# Layer 1: AniList GraphQL (primary)
ANILIST_GQL_QUERY = """
query ($search: String, $id: Int, $type: MediaType) {
  Media(search: $search, id: $id, type: $type) {
    id
    idMal
    title {
      romaji
      english
      native
    }
    type
    format
    status
    description(asHtml: false)
    coverImage {
      large
      extraLarge
      color
    }
    siteUrl
    genres
    averageScore
    episodes
    chapters
    volumes
  }
}
"""

async def fetch_from_gql(session: aiohttp.ClientSession, search: Optional[str] = None, media_id: Optional[int] = None, media_type: Optional[str] = "ANIME") -> Optional[Dict[str, Any]]:
    payload = {"query": ANILIST_GQL_QUERY, "variables": {"search": search, "id": media_id, "type": media_type.upper() if media_type else "ANIME"}}
    headers = {"Accept": "application/json", "Content-Type": "application/json"}
    try:
        async with session.post(ANILIST_GQL_URL, json=payload, headers=headers, timeout=10) as resp:
            if resp.status == 200:
                data = await resp.json()
                if data and isinstance(data, dict) and data.get("data") and data["data"].get("Media"):
                    return data["data"]["Media"]
            else:
                LOG.debug("AniList GQL returned status %s", resp.status)
    except Exception:
        LOG.exception("GraphQL fetch error")
    return None

# Layer 2: fetch item page and parse meta (OpenGraph / meta tags)
META_OG_PATTERN = re.compile(r'<meta\s+(?:property|name)="(?P<k>[^"]+)"\s+content="(?P<v>[^"]+)"', re.IGNORECASE)
async def fetch_item_meta(session: aiohttp.ClientSession, url: str) -> Optional[Dict[str, str]]:
    try:
        async with session.get(url, timeout=10) as resp:
            if resp.status != 200:
                LOG.debug("Item meta fetch %s returned %s", url, resp.status)
                return None
            text = await resp.text()
            if BS4_AVAILABLE:
                try:
                    soup = BeautifulSoup(text, "html.parser")
                    metas = {}
                    for tag in soup.find_all("meta"):
                        k = tag.get("property") or tag.get("name")
                        v = tag.get("content")
                        if k and v:
                            metas[k] = v
                    return metas
                except Exception:
                    LOG.exception("BeautifulSoup parse error")
            # regex fallback
            metas = {}
            for m in META_OG_PATTERN.finditer(text):
                metas[m.group("k")] = m.group("v")
            return metas
    except Exception:
        LOG.exception("Item meta fetch exception")
    return None

# Layer 3: search page scraping
async def fetch_search_page(session: aiohttp.ClientSession, query: str) -> Optional[str]:
    url = build_anilist_search_url(query)
    try:
        async with session.get(url, timeout=10) as resp:
            if resp.status != 200:
                LOG.debug("Search page fetch failed %s -> %s", url, resp.status)
                return None
            text = await resp.text()
            # try to find first result link via regex for /anime/<id> or /manga/<id>
            # <a href="/anime/1234/Some-Title"
            m = re.search(r'href="(/(anime|manga)/\d+[^"]*)"', text)
            if m:
                return ANILIST_BASE + m.group(1)
    except Exception:
        LOG.exception("Search page exception")
    return None

# Layer 4: local fallback
def local_fallback(query: Optional[str]) -> Dict[str, Any]:
    entry = random.choice(FALLBACK)
    return {
        "id": None,
        "title": entry["title"],
        "coverImage": {"large": entry["image"]},
        "siteUrl": entry["url"],
        "description": None
    }

# Master resolver
async def resolve_anilist(session: aiohttp.ClientSession, query: Optional[str]) -> Dict[str, Any]:
    """
    Attempt: GraphQL -> item page meta -> search page -> local fallback
    Returns a dict with keys: title, url, image, description, raw
    """
    # 1) GraphQL (search)
    if query:
        try:
            media = await fetch_from_gql(session, search=query)
            if media:
                title = media["title"].get("english") or media["title"].get("romaji") or media["title"].get("native")
                img = (media.get("coverImage") or {}).get("extraLarge") or (media.get("coverImage") or {}).get("large")
                return {"title": title, "url": media.get("siteUrl"), "image": img, "description": media.get("description"), "raw": media}
        except Exception:
            LOG.exception("GQL layer error")
    # 2) try common item page url if query looks like anilist url already or try search->first result
    if query and "anilist.co" in query:
        try:
            # direct item url provided
            metas = await fetch_item_meta(session, query)
            if metas:
                title = metas.get("og:title") or metas.get("title")
                img = metas.get("og:image")
                return {"title": title, "url": query, "image": img, "description": metas.get("og:description") or metas.get("description"), "raw": metas}
        except Exception:
            LOG.exception("Direct page parse failed")
    # 2b) search for first result via search page parse
    if query:
        try:
            candidate = await fetch_search_page(session, query)
            if candidate:
                metas = await fetch_item_meta(session, candidate)
                title = None
                img = None
                if metas:
                    title = metas.get("og:title") or metas.get("title")
                    img = metas.get("og:image")
                return {"title": title or query, "url": candidate, "image": img, "description": metas.get("og:description") if metas else None, "raw": metas}
        except Exception:
            LOG.exception("Search-page layer failed")
    # 3) fallback to local curated list
    return {"title": local_fallback(query)["title"], "url": local_fallback(query)["siteUrl"], "image": local_fallback(query)["coverImage"]["large"], "description": None, "raw": None}

# -------------------------
# UI components: Select for theme
# -------------------------
class ThemeSelect(discord.ui.Select):
    def __init__(self, cog: "SocialDSK", guild: Optional[discord.Guild]):
        options = [discord.SelectOption(label=THEMES[k]["name"], value=k) for k in THEMES.keys()]
        super().__init__(placeholder="Choose aesthetics...", min_values=1, max_values=1, options=options)
        self.cog = cog
        self.guild = guild

    async def callback(self, interaction: discord.Interaction):
        chosen = self.values[0]
        # apply immediately (session-only). Provide a small confirmation and update embed
        accent = THEMES[chosen]["accent"]
        bg = THEMES[chosen]["bg"]
        # update guild cache for session if exists
        if self.guild:
            # not persisting yet, just show preview
            embed = interaction.message.embeds[0] if interaction.message.embeds else None
            if embed:
                new = embed.copy()
                new.color = accent
                try:
                    new.set_image(url=bg)
                except Exception:
                    pass
                await interaction.response.edit_message(embed=new)
                await interaction.followup.send(f"Previewed theme: {THEMES[chosen]['name']}. Use `/social settings set_theme {chosen}` to save.", ephemeral=True)
                # update cache in cog
                self.cog._guild_settings_cache[self.guild.id] = self.cog._guild_settings_cache.get(self.guild.id, {})
                self.cog._guild_settings_cache[self.guild.id]["theme"] = chosen
                self.cog._guild_settings_cache[self.guild.id]["accent_hex"] = None
                self.cog._guild_settings_cache[self.guild.id]["bg_url"] = bg
                return
        await interaction.response.send_message(f"Previewed theme: {THEMES[chosen]['name']} (no guild).", ephemeral=True)

# Main view for popout — contains dynamic link button and controls
class SocialPopoutView(discord.ui.View):
    def __init__(self, cog: "SocialDSK", guild: Optional[discord.Guild], user: discord.User, title: str, url: Optional[str], image: Optional[str]):
        super().__init__(timeout=300)
        self.cog = cog
        self.guild = guild
        self.user = user
        self.title_text = title
        self.target_url = url
        # Add the theme select
        self.add_item(ThemeSelect(cog, guild))
        # Add Search, Random, Connect, Close buttons (Search opens modal, Random selects local)
        self.add_item(discord.ui.Button(label="Search", style=discord.ButtonStyle.primary, custom_id="social_search_btn"))
        self.add_item(discord.ui.Button(label="Random", style=discord.ButtonStyle.secondary, custom_id="social_random_btn"))
        # Connect AniList (if configured)
        if ANILIST_CLIENT_ID and ANILIST_REDIRECT_URI:
            self.add_item(discord.ui.Button(label="Connect AniList", style=discord.ButtonStyle.link, url=anilist_oauth_url()))
        else:
            # when OAuth not set, provide disabled-looking button via ephemeral instruction
            self.add_item(discord.ui.Button(label="Connect AniList (config needed)", style=discord.ButtonStyle.secondary, custom_id="social_connect_info"))
        # If a url is present, include an Open button
        if url:
            self.add_item(discord.ui.Button(label="Open on AniList", style=discord.ButtonStyle.link, url=url))
        # Close
        self.add_item(discord.ui.Button(label="Close", style=discord.ButtonStyle.danger, custom_id="social_close_btn"))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        # allow anyone to use buttons in public, but prefer only original user to interact in ephemeral flows
        # We'll allow it; ephemeral responses will be used for subs.
        return True

    @discord.ui.button(label="Search", style=discord.ButtonStyle.primary, custom_id="social_search_action")
    async def search_button(self, button: discord.ui.Button, interaction: discord.Interaction):
        modal = SocialSearchModal(self.cog, author=interaction.user)
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="Random", style=discord.ButtonStyle.secondary, custom_id="social_random_action")
    async def random_button(self, button: discord.ui.Button, interaction: discord.Interaction):
        # choose fallback and update embed
        entry = random.choice(FALLBACK)
        emb = self.cog.build_social_embed(title=entry["title"], query=entry["title"], guild=self.guild, bg_url=entry["image"], accent=self.cog.get_guild_accent(self.guild))
        view = SocialPopoutView(self.cog, self.guild, interaction.user, title=entry["title"], url=entry["url"], image=entry["image"])
        try:
            await interaction.response.edit_message(embed=emb, view=view)
        except Exception:
            await interaction.response.send_message(embed=emb, view=view, ephemeral=True)
        await self.cog._db.log(self.guild.id if self.guild else None, interaction.user.id, "random", entry["title"], entry["url"])

    @discord.ui.button(label="Connect AniList", style=discord.ButtonStyle.link, custom_id="social_connect_btn")
    async def connect_button(self, button: discord.ui.Button, interaction: discord.Interaction):
        # If OAuth configured, button will be link; this handler is fallback when not
        if not (ANILIST_CLIENT_ID and ANILIST_REDIRECT_URI):
            await interaction.response.send_message("AniList OAuth is not configured on this bot. Provide ANILIST_CLIENT_ID and ANILIST_REDIRECT_URI environment variables.", ephemeral=True)
        else:
            await interaction.response.send_message("Click the Connect link button to authenticate via AniList.", ephemeral=True)

    @discord.ui.button(label="Close", style=discord.ButtonStyle.danger, custom_id="social_close_action")
    async def close_button(self, button: discord.ui.Button, interaction: discord.Interaction):
        try:
            await interaction.message.delete()
        except Exception:
            await interaction.response.send_message("Closed.", ephemeral=True)
        finally:
            self.stop()

# Modal for search
class SocialSearchModal(discord.ui.Modal, title="Search AniList"):
    query = discord.ui.TextInput(label="Anime / Manga Title or keywords", required=True, max_length=200)

    def __init__(self, cog: "SocialDSK", author: discord.User):
        super().__init__()
        self.cog = cog
        self.author = author

    async def on_submit(self, interaction: discord.Interaction):
        if interaction.user.id != self.author.id:
            return await interaction.response.send_message("This modal isn't for you.", ephemeral=True)
        q = self.query.value.strip()
        if not q:
            return await interaction.response.send_message("Empty query.", ephemeral=True)
        # resolve via multi-layer lookup
        async with aiohttp.ClientSession() as session:
            res = await resolve_anilist(session, q)
        title = res.get("title") or q
        url = res.get("url")
        image = res.get("image")
        emb = self.cog.build_social_embed(title=title, query=q, guild=interaction.guild, bg_url=image, accent=self.cog.get_guild_accent(interaction.guild))
        view = SocialPopoutView(self.cog, interaction.guild, interaction.user, title=title, url=url, image=image)
        try:
            await interaction.response.send_message(embed=emb, view=view, ephemeral=True)
        except Exception:
            await interaction.followup.send(embed=emb, view=view, ephemeral=True)
        # log
        await db.log(interaction.guild.id if interaction.guild else None, interaction.user.id, "search", q, url)

# -------------------------
# Cog Implementation
# -------------------------
class SocialDSK(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._db_ready = False
        self._db_task = asyncio.create_task(self._init_db())
        self._last_used: Dict[int, float] = {}
        self._guild_settings_cache: Dict[int, Dict[str, Any]] = {}
        LOG.info("SocialDSK loaded")

    async def _init_db(self):
        await db.init()
        self._db_ready = True

    async def cog_load(self):
        await self._db_task

    # ---------- DB helpers ----------
    async def get_guild_settings(self, guild: Optional[discord.Guild]) -> Dict[str, Any]:
        if not guild:
            return {"theme": DEFAULT_THEME, "accent_hex": None, "bg_url": THEMES[DEFAULT_THEME]["bg"]}
        if guild.id in self._guild_settings_cache:
            return self._guild_settings_cache[guild.id]
        row = await db.get_guild(guild.id)
        if not row:
            settings = {"theme": DEFAULT_THEME, "accent_hex": None, "bg_url": THEMES[DEFAULT_THEME]["bg"]}
        else:
            settings = {"theme": row.get("theme") or DEFAULT_THEME, "accent_hex": row.get("accent_hex"), "bg_url": row.get("bg_url") or THEMES[row.get("theme") or DEFAULT_THEME]["bg"]}
        self._guild_settings_cache[guild.id] = settings
        return settings

    async def set_guild_setting(self, guild: discord.Guild, key: str, value: Any):
        await db.set_guild(guild.id, key, value)
        # update cache
        self._guild_settings_cache[guild.id] = self._guild_settings_cache.get(guild.id, {})
        self._guild_settings_cache[guild.id][key] = value

    # ---------- visual helpers ----------
    def get_guild_accent(self, guild: Optional[discord.Guild]) -> discord.Color:
        if not guild:
            return THEMES[DEFAULT_THEME]["accent"]
        s = self._guild_settings_cache.get(guild.id)
        if s:
            accent_hex = s.get("accent_hex")
            theme = s.get("theme", DEFAULT_THEME)
            if accent_hex:
                try:
                    return discord.Color(int(accent_hex, 16))
                except Exception:
                    pass
            if theme in THEMES:
                return THEMES[theme]["accent"]
        # try fresh synchronous fallback (non-blocking assumption)
        # if nothing, default
        return THEMES[DEFAULT_THEME]["accent"]

    def build_social_embed(self, title: str, query: Optional[str], guild: Optional[discord.Guild], bg_url: Optional[str], accent: discord.Color) -> discord.Embed:
        emb = discord.Embed(title=title, description=(f"Search AniList for **{query}**" if query else "Open AniList"), color=accent)
        if bg_url:
            try:
                emb.set_image(url=bg_url)
            except Exception:
                pass
        emb.set_footer(text="Social DSK — AniList Popout")
        emb.add_field(name="Source", value="[AniList](https://anilist.co)", inline=True)
        emb.add_field(name="Tips", value="Use Search to find a title, or Connect to link your AniList account.", inline=True)
        return emb

    # ---------- main command ----------
    @app_commands.command(name="social", description="Open Social DSK popout — search AniList or open home.")
    @app_commands.describe(mode="Choose mode: search (open a specific anime/manga) or home (open interactive popout with Connect)", query="Optional query when using search mode")
    async def social(self, interaction: discord.Interaction, mode: Optional[str] = "home", query: Optional[str] = None):
        await interaction.response.defer(thinking=True)
        # rate limit per user
        now = asyncio.get_event_loop().time()
        last = self._last_used.get(interaction.user.id)
        if last and now - last < USER_COOLDOWN:
            return await interaction.followup.send("You're using that too quickly — wait a moment.", ephemeral=True)
        self._last_used[interaction.user.id] = now

        mode = (mode or "home").lower()
        guild = interaction.guild
        settings = await self.get_guild_settings(guild)
        accent = self.get_guild_accent(guild)
        bg = settings.get("bg_url") or THEMES[DEFAULT_THEME]["bg"]

        # Mode: home -> open interactive popout referencing AniList home / search
        if mode == "home":
            title = "Social — AniList"
            emb = self.build_social_embed(title=title, query=None, guild=guild, bg_url=bg, accent=accent)
            # Build view with Connect link if configured
            connect_url = anilist_oauth_url()
            view = SocialPopoutView(self, guild, interaction.user, title=title, url=(connect_url or ANILIST_BASE), image=bg)
            # If OAuth configured, ensure Connect button is link (view adds it). Send ephemeral
            try:
                await interaction.followup.send(embed=emb, view=view, ephemeral=True)
            except Exception:
                await interaction.followup.send(embed=emb, ephemeral=True)
            await db.log(guild.id if guild else None, interaction.user.id, "open_home", None, connect_url or ANILIST_BASE)
            return

        # Mode: search -> resolve item and link to AniList item
        if mode == "search":
            if not query:
                return await interaction.followup.send("You must provide a query when using search mode.", ephemeral=True)
            # Resolve via 4-layer approach
            async with aiohttp.ClientSession() as session:
                try:
                    res = await resolve_anilist(session, query)
                except Exception:
                    LOG.exception("resolve_anilist raised")
                    res = local_fallback(query)
            title = res.get("title") or query
            url = res.get("url") or build_anilist_search_url(query)
            image = res.get("image") or bg
            # Build embed and view with direct link to item
            emb = self.build_social_embed(title=title, query=query, guild=guild, bg_url=image, accent=accent)
            view = SocialPopoutView(self, guild, interaction.user, title=title, url=url, image=image)
            # Add the Open button explicitly if not added
            try:
                await interaction.followup.send(embed=emb, view=view, ephemeral=True)
            except Exception:
                await interaction.followup.send(embed=emb, ephemeral=True)
            # log
            await db.log(guild.id if guild else None, interaction.user.id, "search", query, url)
            return

        # Unknown mode
        await interaction.followup.send("Unknown mode. Use mode=home or mode=search.", ephemeral=True)

    # ---------- Settings subcommands (same as earlier) ----------
    social_settings = app_commands.Group(name="settings", description="Social popout settings (guild admins only).")

    @social_settings.command(name="set_theme", description="Persist a theme for this guild (DarkLux, Royal, Forest, Sunset).")
    async def set_theme(self, interaction: discord.Interaction, theme_name: str):
        await interaction.response.defer(thinking=True, ephemeral=True)
        if not interaction.guild:
            return await interaction.followup.send("Use in a server.", ephemeral=True)
        member = interaction.user
        if not isinstance(member, discord.Member) or not (member.guild_permissions.manage_guild or member.guild_permissions.administrator):
            return await interaction.followup.send("You need Manage Server / Administrator to change settings.", ephemeral=True)
        name = theme_name.strip().lower()
        if name not in THEMES:
            return await interaction.followup.send(f"Unknown theme. Options: {', '.join(THEMES.keys())}", ephemeral=True)
        await self.set_guild_setting(interaction.guild, "theme", name)
        # update cached bg too
        await self.set_guild_setting(interaction.guild, "bg_url", THEMES[name]["bg"])
        await interaction.followup.send(f"Theme set to {THEMES[name]['name']}.", ephemeral=True)

    @social_settings.command(name="set_color", description="Set a custom accent hex color for popouts in this server (e.g., #FFAA00).")
    async def set_color(self, interaction: discord.Interaction, hex_color: str):
        await interaction.response.defer(thinking=True, ephemeral=True)
        if not interaction.guild:
            return await interaction.followup.send("Use in a server.", ephemeral=True)
        member = interaction.user
        if not isinstance(member, discord.Member) or not (member.guild_permissions.manage_guild or member.guild_permissions.administrator):
            return await interaction.followup.send("You need Manage Server / Administrator to change settings.", ephemeral=True)
        m = re.match(r"#?([A-Fa-f0-9]{6})$", hex_color.strip())
        if not m:
            return await interaction.followup.send("Invalid hex. Use like `#FFAA00` or `FFAA00`.", ephemeral=True)
        hexstr = m.group(1)
        await self.set_guild_setting(interaction.guild, "accent_hex", hexstr)
        await interaction.followup.send(f"Accent color set to #{hexstr}. Use `set_theme` to choose a theme or keep custom accent.", ephemeral=True)

    @social_settings.command(name="set_bg", description="Set background image URL for popouts in this server.")
    async def set_bg(self, interaction: discord.Interaction, url: str):
        await interaction.response.defer(thinking=True, ephemeral=True)
        if not interaction.guild:
            return await interaction.followup.send("Use in a server.", ephemeral=True)
        member = interaction.user
        if not isinstance(member, discord.Member) or not (member.guild_permissions.manage_guild or member.guild_permissions.administrator):
            return await interaction.followup.send("You need Manage Server / Administrator to change settings.", ephemeral=True)
        if not (url.lower().startswith("http://") or url.lower().startswith("https://")):
            return await interaction.followup.send("Must be a valid http(s) URL.", ephemeral=True)
        await self.set_guild_setting(interaction.guild, "bg_url", url)
        await interaction.followup.send("Background URL saved for this server.", ephemeral=True)

    @social_settings.command(name="show", description="Show current social popout settings for this server.")
    async def show(self, interaction: discord.Interaction):
        await interaction.response.defer(thinking=True, ephemeral=True)
        if not interaction.guild:
            return await interaction.followup.send("Use in a server.", ephemeral=True)
        cfg = await self.get_guild_settings(interaction.guild)
        theme = cfg.get("theme", DEFAULT_THEME)
        bg = cfg.get("bg_url") or THEMES[theme]["bg"]
        accent_hex = cfg.get("accent_hex")
        text = f"Theme: {theme}\nBackground: {bg}\nAccent hex: {('#' + accent_hex) if accent_hex else 'Default'}"
        emb = discord.Embed(title=f"Social Settings — {interaction.guild.name}", description=text, color=self.get_guild_accent(interaction.guild))
        await interaction.followup.send(embed=emb, ephemeral=True)

# -------------------------
# Cog setup
# -------------------------
async def setup(bot: commands.Bot):
    cog = SocialDSK(bot)
    await bot.add_cog(cog)
