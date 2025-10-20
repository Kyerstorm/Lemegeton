# social_dsk.py
"""
Social DSK - AniList popout Cog
- /social [query?] -> opens a popout (embed + View) linking to AniList search or specific AniList page.
- /social settings ... (guild admin only) -> configure accent color, background image, theme.
- Uses aiosqlite for per-guild persistent configuration (data/social_dsk.db).
- Modal-based search (user types search query -> popout updates to AniList search link).
- Random anime button (uses built-in fallback list).
- Defensive: rate-limits users, robust DB ops, graceful error handling when images or links aren't available.

Design notes: (Will be integrated in a bit)
- We intentionally avoid using AniList API here. The "workaround" is to link to AniList search results (https://anilist.co/search/anime?query=...), or to known AniList page URLs when user supplies an exact AniList id or URL.
- The embed is visually styled; you can change theme palettes and default images via guild settings.
"""

from __future__ import annotations
import asyncio
import aiosqlite
import os
import re
import random
import logging
from dataclasses import dataclass
from typing import Optional, Dict, Any, Tuple, List

import discord
from discord import app_commands
from discord.ext import commands

# ----------------------------
# Basic config
# ----------------------------
LOG = logging.getLogger("SocialDSK")
LOG.setLevel(logging.INFO)

DB_PATH = "data/social_dsk.db"
os.makedirs(os.path.dirname(DB_PATH), exist_ok=True) if os.path.dirname(DB_PATH) else None

# Default theme palettes (name -> dict)
THEMES = {
    "darklux": {"accent": discord.Color.from_rgb(212, 175, 55), "bg_hint": "https://i.imgur.com/8fKQZ6B.jpg"},
    "royal": {"accent": discord.Color.from_rgb(65, 105, 225), "bg_hint": "https://i.imgur.com/3G9JX2K.jpg"},
    "forest": {"accent": discord.Color.from_rgb(60, 179, 113), "bg_hint": "https://i.imgur.com/2c4Xb4Z.jpg"},
    "sunset": {"accent": discord.Color.from_rgb(255, 99, 71), "bg_hint": "https://i.imgur.com/Lz4Q7jK.jpg"},
}

DEFAULT_THEME = "royal"
DEFAULT_BG = THEMES[DEFAULT_THEME]["bg_hint"]
DEFAULT_ACCENT = THEMES[DEFAULT_THEME]["accent"]

# Rate-limiting (simple in-memory)
USER_COOLDOWN = 2.0  # seconds per user for /social command

# Small curated fallback anime list for Random (id or title; titles will be searched)
FALLBACK_ANIME = [
    {"title": "Cowboy Bebop", "image": "https://s4.anilist.co/file/anilistcdn/media/anime/cover/large/bx1-BxZQtcQKq9Bp.jpg"},
    {"title": "Fullmetal Alchemist: Brotherhood", "image": "https://s4.anilist.co/file/anilistcdn/media/anime/cover/large/bx5114-Ug6rJwW2B0jX.jpg"},
    {"title": "Attack on Titan", "image": "https://s4.anilist.co/file/anilistcdn/media/anime/cover/large/bx16498-H9p8p6s5h5xG.jpg"},
    {"title": "Steins;Gate", "image": "https://s4.anilist.co/file/anilistcdn/media/anime/cover/large/bx9259-lhICv3s5q0S8.jpg"},
    {"title": "Your Name.", "image": "https://s4.anilist.co/file/anilistcdn/media/anime/cover/large/bx37219-MkWb9T5QYt3W.jpg"},
]

# AniList search URL base
ANILIST_SEARCH_BASE = "https://anilist.co/search/anime?query="

# ----------------------------
# DB helpers (aiosqlite)
# ----------------------------
INIT_SCHEMA = [
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
        query TEXT,
        action TEXT,
        created_at TEXT
    );
    """,
]


async def init_db():
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            for s in INIT_SCHEMA:
                await db.execute(s)
            await db.commit()
    except Exception:
        LOG.exception("Failed to initialize DB for Social DSK")


class SocialDB:
    """Small wrapper around aiosqlite operations we need."""
    def __init__(self, path: str = DB_PATH):
        self.path = path

    async def fetchone(self, sql: str, params: tuple = ()):
        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute(sql, params)
            row = await cur.fetchone()
            await cur.close()
            return row

    async def execute(self, sql: str, params: tuple = ()):
        async with aiosqlite.connect(self.path) as db:
            await db.execute(sql, params)
            await db.commit()

    async def fetchall(self, sql: str, params: tuple = ()):
        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute(sql, params)
            rows = await cur.fetchall()
            await cur.close()
            return rows


db = SocialDB()

# ----------------------------
# Utilities: validation + formatting
# ----------------------------
HEX_RE = re.compile(r"^#?([A-Fa-f0-9]{6})$")


def parse_hex_color(s: str) -> Optional[discord.Colour]:
    if not s:
        return None
    m = HEX_RE.match(s.strip())
    if not m:
        return None
    hex_str = m.group(1)
    return discord.Color(int(hex_str, 16))


def build_anilist_search_url(query: str) -> str:
    # Query needs URL encoding; use basic safe replace for spaces -> + (good enough for our purpose)
    q = str(query).strip()
    q = q.replace(" ", "+")
    return ANILIST_SEARCH_BASE + q


def is_anilist_url(s: str) -> Optional[str]:
    # Very relaxed check: returns URL if contains 'anilist.co'
    if not s:
        return None
    s = s.strip()
    if "anilist.co" in s:
        return s
    return None


# ----------------------------
# UI: Views & Modals
# ----------------------------
class SocialSearchModal(discord.ui.Modal, title="Search AniList"):
    """Modal that collects a search query and returns to the invoking interaction."""
    query = discord.ui.TextInput(label="Search AniList (anime title or keywords)", required=True, max_length=200)

    def __init__(self, cog: "SocialDSK", author: discord.User):
        super().__init__()
        self.cog = cog
        self.author = author

    async def on_submit(self, interaction: discord.Interaction):
        # ensure same user
        if interaction.user.id != self.author.id:
            await interaction.response.send_message("This search modal isn't for you.", ephemeral=True)
            return
        q = str(self.query.value).strip()
        if not q:
            await interaction.response.send_message("Empty query.", ephemeral=True)
            return
        # produce popout for this search
        await self.cog._send_popout_for_query(interaction, q)


class SocialPopoutView(discord.ui.View):
    """The interactive popout that accompanies the /social response."""
    def __init__(self, cog: "SocialDSK", guild: Optional[discord.Guild], user: discord.User, initial_query: Optional[str] = None):
        super().__init__(timeout=300)  # 5 minutes active
        self.cog = cog
        self.guild = guild
        self.user = user
        self.query = initial_query
        # Buttons: Open AniList (URL), Search (modal), Random, Theme, Settings (if admin), Close
        # NOTE: URL buttons are added dynamically when building the popout embed

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        # allow only the command user to use Search / Random / Theme / Close in ephemeral context;
        # buttons can be used by others when response is not ephemeral - we'll allow it but require ephemeral responses for settings.
        return True

    @discord.ui.button(label="Search", style=discord.ButtonStyle.primary, row=1, custom_id="social_search")
    async def search_button(self, button: discord.ui.Button, interaction: discord.Interaction):
        # open a modal to get a query
        try:
            modal = SocialSearchModal(self.cog, author=interaction.user)
            await interaction.response.send_modal(modal)
        except Exception:
            await interaction.response.send_message("Failed to open search modal.", ephemeral=True)

    @discord.ui.button(label="Random", style=discord.ButtonStyle.secondary, row=1, custom_id="social_random")
    async def random_button(self, button: discord.ui.Button, interaction: discord.Interaction):
        # Pick a random entry from fallback list (we can extend later)
        entry = random.choice(FALLBACK_ANIME)
        title = entry.get("title")
        image = entry.get("image")
        # Build an embed and update message
        emb = self.cog._build_social_embed(title=title, query=title, guild=self.guild, bg_url=image, accent=self.cog._get_guild_accent(self.guild))
        # provide AniList link
        url = build_anilist_search_url(title)
        # create a URL button for AniList
        view = discord.ui.View(timeout=300)
        view.add_item(discord.ui.Button(label="Open on AniList", url=url))
        # keep other buttons
        view.add_item(discord.ui.Button(label="Search", style=discord.ButtonStyle.primary, custom_id="social_search2"))
        view.add_item(discord.ui.Button(label="Theme", style=discord.ButtonStyle.secondary, custom_id="social_theme"))
        view.add_item(discord.ui.Button(label="Close", style=discord.ButtonStyle.danger, custom_id="social_close"))
        try:
            await interaction.response.edit_message(embed=emb, view=view)
        except Exception:
            # if editing fails (maybe original ephemeral), send new ephemeral
            await interaction.response.send_message(embed=emb, view=view, ephemeral=True)
        # log action
        await self.cog._log_action(self.guild, interaction.user, title, action="random")

    @discord.ui.button(label="Theme", style=discord.ButtonStyle.secondary, row=1, custom_id="social_theme")
    async def theme_button(self, button: discord.ui.Button, interaction: discord.Interaction):
        # Cycle themes (for this session) — show small chooser (ephemeral)
        choices = ", ".join(THEMES.keys())
        await interaction.response.send_message(f"Available themes: {choices}\nUse `/social settings set_theme <name>` to persist a theme for this guild.", ephemeral=True)

    @discord.ui.button(label="Settings", style=discord.ButtonStyle.secondary, row=1, custom_id="social_settings")
    async def settings_button(self, button: discord.ui.Button, interaction: discord.Interaction):
        # Only allow guild admins (Manage Guild or Administrator) to access settings
        if not interaction.guild:
            await interaction.response.send_message("Settings are only available in servers.", ephemeral=True)
            return
        member = interaction.user
        if not isinstance(member, discord.Member) or not (member.guild_permissions.manage_guild or member.guild_permissions.administrator):
            await interaction.response.send_message("You need Manage Server or Administrator to change settings.", ephemeral=True)
            return
        # Present simple ephemeral instructions (we have slash subcommands for settings)
        await interaction.response.send_message("Use the `/social settings` commands to change persistent settings for this server (set_theme, set_color, set_bg, show, reset).", ephemeral=True)

    @discord.ui.button(label="Close", style=discord.ButtonStyle.danger, row=2, custom_id="social_close")
    async def close_button(self, button: discord.ui.Button, interaction: discord.Interaction):
        try:
            await interaction.message.delete()
        except Exception:
            # fallback: respond ephemeral
            await interaction.response.send_message("Closed.", ephemeral=True)
        finally:
            self.stop()

# ----------------------------
# Cog
# ----------------------------
class SocialDSK(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._db_ready_task = asyncio.create_task(init_db())
        self._db = db
        # per-user cooldown map
        self._last_used: Dict[int, float] = {}
        # in-memory cache of guild settings to reduce DB hits
        self._guild_settings_cache: Dict[int, Dict[str, Any]] = {}
        LOG.info("SocialDSK cog loaded")

    # ------------------------
    # Internal DB helpers (safe wrappers)
    # ------------------------
    async def _ensure_db(self):
        await self._db_ready_task

    async def _get_guild_settings(self, guild: Optional[discord.Guild]) -> Dict[str, Any]:
        """Return the settings dict for a guild (with defaults applied)."""
        await self._ensure_db()
        if not guild:
            return {"theme": DEFAULT_THEME, "accent_hex": None, "bg_url": DEFAULT_BG}
        gid = guild.id
        # cache
        if gid in self._guild_settings_cache:
            return self._guild_settings_cache[gid]
        row = await self._db.fetchone("SELECT theme, accent_hex, bg_url FROM guild_settings WHERE guild_id = ?", (gid,))
        if not row:
            settings = {"theme": DEFAULT_THEME, "accent_hex": None, "bg_url": DEFAULT_BG}
        else:
            settings = {
                "theme": row["theme"] or DEFAULT_THEME,
                "accent_hex": row["accent_hex"],
                "bg_url": row["bg_url"] or DEFAULT_BG
            }
        self._guild_settings_cache[gid] = settings
        return settings

    async def _set_guild_setting(self, guild: discord.Guild, key: str, value: Any):
        await self._ensure_db()
        gid = guild.id
        # write-through to DB
        existing = await self._db.fetchone("SELECT guild_id FROM guild_settings WHERE guild_id = ?", (gid,))
        if not existing:
            # insert defaults and set key
            theme = DEFAULT_THEME
            accent = None
            bg = DEFAULT_BG
            if key == "theme":
                theme = value
            elif key == "accent_hex":
                accent = value
            elif key == "bg_url":
                bg = value
            await self._db.execute("INSERT OR REPLACE INTO guild_settings (guild_id, theme, accent_hex, bg_url) VALUES (?, ?, ?, ?)", (gid, theme, accent, bg))
        else:
            if key == "theme":
                await self._db.execute("UPDATE guild_settings SET theme = ? WHERE guild_id = ?", (value, gid))
            elif key == "accent_hex":
                await self._db.execute("UPDATE guild_settings SET accent_hex = ? WHERE guild_id = ?", (value, gid))
            elif key == "bg_url":
                await self._db.execute("UPDATE guild_settings SET bg_url = ? WHERE guild_id = ?", (value, gid))
        # update cache
        if gid in self._guild_settings_cache:
            self._guild_settings_cache[gid][key] = value

    async def _reset_guild_settings(self, guild: discord.Guild):
        await self._ensure_db()
        gid = guild.id
        await self._db.execute("DELETE FROM guild_settings WHERE guild_id = ?", (gid,))
        # update cache
        if gid in self._guild_settings_cache:
            del self._guild_settings_cache[gid]

    # ------------------------
    # Helpers: visual + logging
    # ------------------------
    def _get_guild_accent(self, guild: Optional[discord.Guild]) -> discord.Color:
        # prefer configured accent_hex, else theme default
        if not guild:
            return DEFAULT_ACCENT
        cached = self._guild_settings_cache.get(guild.id)
        if cached:
            accent_hex = cached.get("accent_hex")
            theme = cached.get("theme", DEFAULT_THEME)
            if accent_hex:
                try:
                    return discord.Color(int(accent_hex, 16))
                except Exception:
                    pass
            if theme and theme in THEMES:
                return THEMES[theme]["accent"]
        # fallback to default
        return DEFAULT_ACCENT

    async def _log_action(self, guild: Optional[discord.Guild], user: discord.User, query: Optional[str], action: str):
        try:
            gid = guild.id if guild else None
            await self._db.execute("INSERT INTO social_logs (guild_id, user_id, query, action, created_at) VALUES (?, ?, ?, ?, datetime('now'))", (gid, user.id, query, action))
        except Exception:
            LOG.exception("Failed to persist social log")

    def _build_social_embed(self, title: str, query: Optional[str], guild: Optional[discord.Guild], bg_url: Optional[str], accent: discord.Color) -> discord.Embed:
        # Compose a visually attractive embed (popout)
        emb = discord.Embed(title=title, description=(f"Search AniList for **{query}**" if query else "Explore anime on AniList."), color=accent)
        # footer and aesthetic
        emb.set_footer(text="Social DSK • AniList Popout")
        # background image: put in embed image (Discord will show it)
        if bg_url:
            try:
                emb.set_image(url=bg_url)
            except Exception:
                pass
        # small extra fields
        emb.add_field(name="Source", value="[AniList](https://anilist.co)", inline=True)
        emb.add_field(name="Tip", value="Use the Search button to enter a query, or click the AniList button to open AniList.", inline=True)
        return emb

    # ------------------------
    # Public command: /social
    # ------------------------
    @app_commands.command(name="social", description="Open the Social DSK popout and link to AniList (search or open).")
    @app_commands.describe(query="Optional quick query (anime title or keywords). If empty, a generic popout opens.")
    async def social(self, interaction: discord.Interaction, query: Optional[str] = None):
        """Main entrypoint: opens popout with AniList link and interactive buttons."""
        await interaction.response.defer(thinking=True)
        # rate limit per user
        uid = interaction.user.id
        now = asyncio.get_event_loop().time()
        last = self._last_used.get(uid)
        if last and (now - last) < USER_COOLDOWN:
            return await interaction.followup.send("You're using that too quickly — please wait a moment.", ephemeral=True)
        self._last_used[uid] = now

        # load guild settings
        guild = interaction.guild
        settings = await self._get_guild_settings(guild)
        # determine accent and bg
        accent = self._get_guild_accent(guild)
        bg = settings.get("bg_url") or DEFAULT_BG

        # If query is provided and is an AniList URL, use it directly
        target_url = None
        if query:
            maybe_url = is_anilist_url(query)
            if maybe_url:
                target_url = maybe_url
            else:
                target_url = build_anilist_search_url(query)

        # Build the embed: if query present use it in title
        title = f"Social — AniList"
        if query:
            title = f"Search: {query}"

        embed = self._build_social_embed(title=title, query=query, guild=guild, bg_url=bg, accent=accent)

        # Build view: we will include a URL button if we have a target_url
        view = SocialPopoutView(self, guild, interaction.user, initial_query=query)
        # If target_url exists, add a heavy link button that opens AniList
        if target_url:
            view_with_url = discord.ui.View(timeout=view.timeout)
            # URL button
            view_with_url.add_item(discord.ui.Button(label="Open on AniList", url=target_url))
            # Add functional buttons
            view_with_url.add_item(discord.ui.Button(label="Search", style=discord.ButtonStyle.primary, custom_id="social_search_main"))
            view_with_url.add_item(discord.ui.Button(label="Random", style=discord.ButtonStyle.secondary, custom_id="social_random_main"))
            view_with_url.add_item(discord.ui.Button(label="Theme", style=discord.ButtonStyle.secondary, custom_id="social_theme_main"))
            # Settings only for guild admins; add button regardless, the view will check permissions
            view_with_url.add_item(discord.ui.Button(label="Settings", style=discord.ButtonStyle.secondary, custom_id="social_settings_main"))
            view_with_url.add_item(discord.ui.Button(label="Close", style=discord.ButtonStyle.danger, custom_id="social_close_main"))
            # We can't attach both a custom view and a plain View; instead, we'll send the URL view to user
            try:
                await interaction.followup.send(embed=embed, view=view_with_url, ephemeral=True)
            except Exception:
                # fallback: send embed without view
                try:
                    await interaction.followup.send(embed=embed, ephemeral=True)
                except Exception:
                    await interaction.followup.send("Failed to open Social popout.", ephemeral=True)
        else:
            # No URL yet, show view that enables Search & Random; the Random button will prepare a URL
            try:
                await interaction.followup.send(embed=embed, view=view, ephemeral=True)
            except Exception:
                await interaction.followup.send(embed=embed, ephemeral=True)

        # log
        await self._log_action(guild, interaction.user, query or "", action="open")

    # ------------------------
    # Helper: send popout for a query (used by modal)
    # ------------------------
    async def _send_popout_for_query(self, interaction: discord.Interaction, query: str):
        # Build target AniList URL
        url = build_anilist_search_url(query)
        guild = interaction.guild
        settings = await self._get_guild_settings(guild)
        accent = self._get_guild_accent(guild)
        bg = settings.get("bg_url") or DEFAULT_BG
        title = f"Search: {query}"
        embed = self._build_social_embed(title=title, query=query, guild=guild, bg_url=bg, accent=accent)
        view = discord.ui.View(timeout=300)
        view.add_item(discord.ui.Button(label="Open on AniList", url=url))
        view.add_item(discord.ui.Button(label="Search again", style=discord.ButtonStyle.primary, custom_id="social_search_again"))
        view.add_item(discord.ui.Button(label="Random", style=discord.ButtonStyle.secondary, custom_id="social_random_again"))
        view.add_item(discord.ui.Button(label="Close", style=discord.ButtonStyle.danger, custom_id="social_close_again"))
        try:
            await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
        except Exception:
            try:
                await interaction.followup.send(embed=embed, view=view, ephemeral=True)
            except Exception:
                await interaction.response.send_message("Failed to open popout for your query.", ephemeral=True)
        await self._log_action(guild, interaction.user, query, action="search")

    # ------------------------
    # Settings group
    # ------------------------
    social_settings = app_commands.Group(name="settings", description="Social popout settings (guild administrators only).")

    @social_settings.command(name="set_color", description="Set an accent color (hex) for this server's popouts (e.g., #FFAA00).")
    async def set_color(self, interaction: discord.Interaction, hex_color: str):
        await interaction.response.defer(thinking=True, ephemeral=True)
        if not interaction.guild:
            return await interaction.followup.send("This command must be used in a server.", ephemeral=True)
        member = interaction.user
        if not isinstance(member, discord.Member) or not (member.guild_permissions.manage_guild or member.guild_permissions.administrator):
            return await interaction.followup.send("You need Manage Server or Administrator to change settings.", ephemeral=True)
        parsed = HEX_RE.match(hex_color)
        if not parsed:
            return await interaction.followup.send("Invalid hex color. Use a 6-digit hex like `#FFAA00` or `FFAA00`.", ephemeral=True)
        hex_str = parsed.group(1)
        try:
            await self._set_guild_setting(interaction.guild, "accent_hex", hex_str)
            # update cache now
            if interaction.guild.id in self._guild_settings_cache:
                self._guild_settings_cache[interaction.guild.id]["accent_hex"] = hex_str
            await interaction.followup.send(f"Accent color set to `#{hex_str}` for this server.", ephemeral=True)
        except Exception:
            LOG.exception("Failed to set accent color")
            await interaction.followup.send("Failed to persist setting.", ephemeral=True)

    @social_settings.command(name="set_bg", description="Set a background image URL for popouts in this server.")
    async def set_bg(self, interaction: discord.Interaction, url: str):
        await interaction.response.defer(thinking=True, ephemeral=True)
        if not interaction.guild:
            return await interaction.followup.send("Use this in a server.", ephemeral=True)
        member = interaction.user
        if not isinstance(member, discord.Member) or not (member.guild_permissions.manage_guild or member.guild_permissions.administrator):
            return await interaction.followup.send("You need Manage Server or Administrator to change settings.", ephemeral=True)
        # basic validation: must be http(s)
        if not (url.startswith("http://") or url.startswith("https://")):
            return await interaction.followup.send("Background URL must start with http:// or https://", ephemeral=True)
        try:
            await self._set_guild_setting(interaction.guild, "bg_url", url)
            if interaction.guild.id in self._guild_settings_cache:
                self._guild_settings_cache[interaction.guild.id]["bg_url"] = url
            await interaction.followup.send("Background image URL saved for this server.", ephemeral=True)
        except Exception:
            LOG.exception("Failed to set bg url")
            await interaction.followup.send("Failed to persist setting.", ephemeral=True)

    @social_settings.command(name="set_theme", description="Set a named theme for this server (DarkLux, Royal, Forest, Sunset).")
    async def set_theme(self, interaction: discord.Interaction, theme_name: str):
        await interaction.response.defer(thinking=True, ephemeral=True)
        if not interaction.guild:
            return await interaction.followup.send("Use this in a server.", ephemeral=True)
        member = interaction.user
        if not isinstance(member, discord.Member) or not (member.guild_permissions.manage_guild or member.guild_permissions.administrator):
            return await interaction.followup.send("You need Manage Server or Administrator to change settings.", ephemeral=True)
        name = theme_name.strip().lower()
        if name not in THEMES:
            choices = ", ".join(THEMES.keys())
            return await interaction.followup.send(f"Unknown theme. Available: {choices}", ephemeral=True)
        try:
            await self._set_guild_setting(interaction.guild, "theme", name)
            if interaction.guild.id in self._guild_settings_cache:
                self._guild_settings_cache[interaction.guild.id]["theme"] = name
            await interaction.followup.send(f"Theme set to {name}.", ephemeral=True)
        except Exception:
            LOG.exception("Failed to set theme")
            await interaction.followup.send("Failed to persist setting.", ephemeral=True)

    @social_settings.command(name="reset", description="Reset social popout settings for this server to defaults.")
    async def reset(self, interaction: discord.Interaction):
        await interaction.response.defer(thinking=True, ephemeral=True)
        if not interaction.guild:
            return await interaction.followup.send("Use this in a server.", ephemeral=True)
        member = interaction.user
        if not isinstance(member, discord.Member) or not (member.guild_permissions.manage_guild or member.guild_permissions.administrator):
            return await interaction.followup.send("You need Manage Server or Administrator to reset settings.", ephemeral=True)
        try:
            await self._reset_guild_settings(interaction.guild)
            await interaction.followup.send("Social popout settings reset to defaults.", ephemeral=True)
        except Exception:
            LOG.exception("Failed to reset settings")
            await interaction.followup.send("Failed to reset settings.", ephemeral=True)

    @social_settings.command(name="show", description="Show current social popout settings for this server.")
    async def show(self, interaction: discord.Interaction):
        await interaction.response.defer(thinking=True, ephemeral=True)
        if not interaction.guild:
            return await interaction.followup.send("Use this in a server.", ephemeral=True)
        cfg = await self._get_guild_settings(interaction.guild)
        theme = cfg.get("theme", DEFAULT_THEME)
        bg = cfg.get("bg_url", DEFAULT_BG)
        accent_hex = cfg.get("accent_hex")
        text = f"Theme: {theme}\nBackground: {bg}\nAccent hex: {('#' + accent_hex) if accent_hex else 'Default'}"
        emb = discord.Embed(title=f"Social Settings — {interaction.guild.name}", description=text, color=self._get_guild_accent(interaction.guild))
        await interaction.followup.send(embed=emb, ephemeral=True)

    # ------------------------
    # Cog unload
    # ------------------------
    def cog_unload(self):
        # nothing special to cleanup
        pass


# ----------------------------
# setup
# ----------------------------
async def setup(bot: commands.Bot):
    cog = SocialDSK(bot)
    await bot.add_cog(cog)
