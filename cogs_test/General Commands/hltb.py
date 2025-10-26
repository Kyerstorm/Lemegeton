# cogs/hltb.py
# =============================================================
#
# /hltb - Blue Galaxy Themed, single-command Cog (Interactive)
# - Single slash command: /hltb
# - howlongtobeatpy search for results and game_id
# - Scrapes howlongtobeat.com for extended metadata (description, genres,
#   developers, publishers, release date, playstyles, reviews where present)
# - Dropdowns for selecting the correct game and selecting which section to view
# - Buttons:
#     🔗 Open on HLTB (link style) - always visible
#     📘 Description (primary blue) - edits the current embed into description view
#     ↩️ Return to Main (primary blue) - appears only when viewing Description
#     🎲 Random (secondary) - show a random top result
# - SQLite-backed cache (aiosqlite) + short memory cache
# - Defensive scraping (BeautifulSoup) with fallbacks to API-provided data
# - Short per-user cooldown
#
# =============================================================

import asyncio
import aiosqlite
import json
import os
import random
import re
import time
from functools import wraps
from typing import Any, Dict, List, Optional, Tuple

import aiohttp
import discord
from bs4 import BeautifulSoup
from discord import app_commands, ui
from discord.ext import commands
from howlongtobeatpy import HowLongToBeat

# -----------------------------
# CONFIGURATION
# -----------------------------
CACHE_DB_PATH = os.getenv("HLTB_CACHE_DB", "hltb_cache.sqlite")
CACHE_TTL_SECONDS = 60 * 60 * 24 * 14  # 14 days cache lifetime on disk
MEM_CACHE_TTL = 60 * 60  # 1 hour in-memory cache
USER_COOLDOWN_SECONDS = 3  # per-user cooldown to avoid spam
MAX_SELECT_OPTIONS = 5
REQUEST_TIMEOUT = 20  # seconds
HLTB_BASE = "https://howlongtobeat.com"

# Blue Galaxy Theme
COLOR_PRIMARY = discord.Color.from_rgb(11, 84, 166)
COLOR_ACCENT = discord.Color.from_rgb(38, 63, 139) 
COLOR_BACKGROUND = discord.Color.from_rgb(10, 12, 18) 
EMO = {
    "search": "🔎",
    "open": "🔗",
    "main": "🕐",
    "extra": "🎯",
    "complete": "🏆",
    "platform": "💻",
    "desc": "📘",
    "details": "🧾",
    "stats": "📊",
    "error": "❌",
    "sparkle": "✨",
    "choice": "🎮",
    "timeout": "⏳",
    "random": "🎲",
    "return": "↩️",
}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; DiscordBot/1.0; +https://github.com/)"
}

# -----------------------------
# UTILITIES
# -----------------------------
def now_ts() -> int:
    return int(time.time())


def format_hours(v) -> str:
    """Human-friendly formatting for hours fields."""
    if v is None:
        return "N/A"
    try:
        if isinstance(v, (int, float)):
            return f"{v} hrs"
        s = str(v).strip()
        if not s:
            return "N/A"
        return s
    except Exception:
        return "N/A"


def safe_truncate(text: Optional[str], length: int = 1024) -> str:
    if not text:
        return ""
    return text if len(text) <= length else text[: length - 3] + "..."


def compact_join(items: Optional[List[str]], limit: int = 8) -> str:
    if not items:
        return "Unknown"
    if len(items) <= limit:
        return ", ".join(items)
    return ", ".join(items[:limit]) + f", +{len(items)-limit} more"


def cooldown_per_user(seconds: int):
    """
    Simple per-user cooldown decorator for command handlers inside cogs.
    """
    def decorator(func):
        last_call = {}

        @wraps(func)
        async def wrapper(self, interaction: discord.Interaction, *args, **kwargs):
            uid = interaction.user.id
            t = now_ts()
            last = last_call.get(uid, 0)
            if t - last < seconds:
                await interaction.response.send_message(f"{EMO['timeout']} You're doing that too quickly. Try again in a moment.", ephemeral=True)
                return
            last_call[uid] = t
            return await func(self, interaction, *args, **kwargs)
        return wrapper
    return decorator


# -----------------------------
# CACHE: SQLite + in-memory
# -----------------------------
class CacheDB:
    """
    Simple async SQLite wrapper to store cached parsed pages and API results:
    Table: cache (key TEXT PRIMARY KEY, timestamp INTEGER, value TEXT)
    """

    def __init__(self, path: str = CACHE_DB_PATH):
        self.path = path
        self._conn: Optional[aiosqlite.Connection] = None
        self._init_lock = asyncio.Lock()

    async def init(self):
        if self._conn:
            return
        async with self._init_lock:
            if self._conn:
                return
            self._conn = await aiosqlite.connect(self.path)
            await self._conn.execute(
                "CREATE TABLE IF NOT EXISTS cache (key TEXT PRIMARY KEY, timestamp INTEGER, value TEXT)"
            )
            await self._conn.commit()

    async def get(self, key: str) -> Optional[Dict[str, Any]]:
        await self.init()
        cur = await self._conn.execute("SELECT timestamp, value FROM cache WHERE key = ?", (key,))
        row = await cur.fetchone()
        await cur.close()
        if not row:
            return None
        ts, val = row
        try:
            obj = json.loads(val)
            return {"timestamp": ts, "value": obj}
        except Exception:
            return None

    async def set(self, key: str, value: Any):
        await self.init()
        val = json.dumps(value, ensure_ascii=False)
        ts = now_ts()
        await self._conn.execute("REPLACE INTO cache (key, timestamp, value) VALUES (?, ?, ?)", (key, ts, val))
        await self._conn.commit()

    async def delete(self, key: str):
        await self.init()
        await self._conn.execute("DELETE FROM cache WHERE key = ?", (key,))
        await self._conn.commit()

    async def close(self):
        if self._conn:
            await self._conn.close()
            self._conn = None


# -----------------------------
# NETWORK & SCRAPING
# -----------------------------
async def fetch_text(session: aiohttp.ClientSession, url: str, timeout: int = REQUEST_TIMEOUT) -> str:
    async with session.get(url, headers=HEADERS, timeout=timeout) as resp:
        resp.raise_for_status()
        return await resp.text()


def parse_hltb_game_page(html: str) -> Dict[str, Any]:
    """
    Defensive parser for HLTB game pages.
    Extracts:
      - title
      - image (og:image)
      - description (various heuristics)
      - genres/chips
      - details dict (developer, publisher, release, etc.)
      - time_estimates dict (main, main_extra, completionist, etc.)
      - reviews list (if user-review-like text blocks exist; best-effort)
      - raw_excerpt (short text excerpt for debug)
    """
    soup = BeautifulSoup(html, "lxml")
    data: Dict[str, Any] = {
        "title": None,
        "image": None,
        "description": None,
        "genres": [],
        "details": {},
        "time_estimates": {},
        "reviews": [],  # list of (author?, rating?, text?) best-effort
        "raw_excerpt": None,
    }

    # Title: h1 or og:title
    h1 = soup.find("h1")
    if h1 and h1.text.strip():
        data["title"] = h1.text.strip()
    else:
        og = soup.find("meta", property="og:title")
        if og and og.get("content"):
            data["title"] = og["content"].strip()

    # Image
    og_img = soup.find("meta", property="og:image")
    if og_img and og_img.get("content"):
        data["image"] = og_img["content"]

    # Description: try a handful of likely containers
    desc = None
    selectors = [
        {"name": "div", "class": re.compile(r"(game_description|profile|game_profile|game_profile_summary)", re.I)},
        {"name": "div", "id": re.compile(r"(game_description|profile)", re.I)},
        {"name": "p", "class": re.compile(r"(game_description|profile)", re.I)},
    ]
    for sel in selectors:
        try:
            block = soup.find(sel["name"], sel.get("class") or sel.get("id"))
            if block and block.get_text(strip=True):
                desc = block.get_text("\n", strip=True)
                break
        except Exception:
            continue
    if not desc:
        meta_desc = soup.find("meta", attrs={"name": "description"})
        if meta_desc and meta_desc.get("content"):
            desc = meta_desc["content"].strip()
    data["description"] = desc

    # Genres / chips - many HLTB pages include small links/chips for tags
    try:
        chip_selectors = [
            ".profile .profile_links a", ".game_profile .profile_links a",
            ".profile_short .search_list_tidbit a", ".search_list_item_block .search_list_tidbit a"
        ]
        chips = []
        for sel in chip_selectors:
            for a in soup.select(sel):
                t = a.get_text(strip=True)
                if t:
                    chips.append(t)
        # unique preserve order
        data["genres"] = list(dict.fromkeys([c for c in chips if c]))
    except Exception:
        data["genres"] = data.get("genres", [])

    # Details parsing: blocks containing "Developer: X", "Publisher: Y", etc.
    try:
        detail_blocks = soup.select(".profile .profile_info, .game_profile .profile_info, .search_list_details")
        for block in detail_blocks:
            # check for lines with colon
            for item in block.find_all(["div", "li", "p", "span"]):
                txt = item.get_text(" ", strip=True)
                if ":" in txt:
                    k, v = txt.split(":", 1)
                    k = k.strip()
                    v = v.strip()
                    if k and v:
                        data["details"][k] = v
    except Exception:
        pass

    # Time estimates - try to find common labels and numbers
    try:
        label_map = {
            "Main Story": "main",
            "Main + Extra": "main_extra",
            "Completionist": "completionist",
            "Solo": "solo",
            "Co-op": "coop",
        }
        for label, key in label_map.items():
            el = soup.find(string=re.compile(re.escape(label), re.I))
            if el:
                parent = el.parent
                if parent:
                    # search nearby for numeric patterns
                    found = None
                    near = parent.find_next(string=re.compile(r"\d{1,4}[\d\.\½\�]*\s*(Hours|hrs|h)?", re.I))
                    if near:
                        found = near.strip()
                    else:
                        txt = parent.get_text(" ", strip=True)
                        m = re.search(r"(\d{1,4}[\d\.\½\�]*)\s*(Hours|hrs|h)?", txt)
                        if m:
                            found = m.group(0)
                    if found:
                        data["time_estimates"][key] = found
    except Exception:
        pass

    # Reviews: best-effort: find blocks with class or ids that suggest reviews or user submissions
    try:
        # common patterns: review-like divs, comments, user reviews inside a section
        review_candidates = soup.select(".user_reviews, .reviews, .comments, .review, .userreview")
        for rc in review_candidates:
            # find smaller blocks that might be single reviews
            for item in rc.find_all(["div", "article", "li"], limit=8):
                txt = item.get_text("\n", strip=True)
                if txt and len(txt) > 30:
                    # keep short excerpt of review
                    data["reviews"].append(safe_truncate(txt, 800))
        # fallback: look for blocks with the word 'review' near text
        if not data["reviews"]:
            for block in soup.find_all(text=re.compile(r"\b(review|user review|posted)\b", re.I)):
                parent = block.parent
                if parent:
                    txt = parent.get_text(" ", strip=True)
                    if txt and len(txt) > 40:
                        data["reviews"].append(safe_truncate(txt, 800))
        # unique
        data["reviews"] = list(dict.fromkeys(data["reviews"]))[:8]
    except Exception:
        data["reviews"] = []

    # Raw excerpt fallback
    try:
        txt = soup.get_text("\n", strip=True)
        data["raw_excerpt"] = txt[:1500]
    except Exception:
        data["raw_excerpt"] = None

    return data


# -----------------------------
# UI COMPONENTS
# -----------------------------
class ResultSelect(ui.Select):
    """Dropdown to pick one of the search results; values store index as string."""

    def __init__(self, results: List[Any]):
        options = []
        for i, r in enumerate(results[:MAX_SELECT_OPTIONS]):
            label = (r.game_name[:95] + "...") if len(r.game_name) > 95 else r.game_name
            platforms = ", ".join(getattr(r, "profile_platforms", []) or [])
            desc = f"Score: {getattr(r, 'similarity', 0):.2f} • {platforms}" if platforms else f"Score: {getattr(r, 'similarity', 0):.2f}"
            options.append(ui.SelectOption(label=label, description=(desc[:100] if desc else ""), value=str(i), emoji=EMO["choice"]))
        super().__init__(placeholder="Select the matching game...", min_values=1, max_values=1, options=options)
        self.results = results
        self.chosen_index: Optional[int] = None

    async def callback(self, interaction: discord.Interaction):
        try:
            self.chosen_index = int(self.values[0])
        except Exception:
            self.chosen_index = None
        self.view.stop()
        # defer so we can edit later
        await interaction.response.defer()


class SectionSelect(ui.Select):
    """Dropdown to choose viewing section."""

    def __init__(self):
        opts = [
            ui.SelectOption(label="Overview", description="Summary & quick metadata", emoji=EMO["sparkle"]),
            ui.SelectOption(label="Times", description="Time estimates", emoji=EMO["main"]),
            ui.SelectOption(label="Description", description="Full scraped description", emoji=EMO["desc"]),
            ui.SelectOption(label="Details", description="Dev / Publisher / Release", emoji=EMO["details"]),
            ui.SelectOption(label="Reviews", description="User reviews & excerpts", emoji=EMO["stats"]),
            ui.SelectOption(label="Raw", description="Sanitized raw excerpt", emoji="🧪"),
        ]
        super().__init__(placeholder="Choose section to view...", min_values=1, max_values=1, options=opts)
        self.chosen: Optional[str] = None

    async def callback(self, interaction: discord.Interaction):
        self.chosen = self.values[0]
        self.view.stop()
        await interaction.response.defer()


class OpenHLTBButton(ui.Button):
    def __init__(self, url: str):
        # link-style button; always visible
        super().__init__(label="Open on HLTB", style=discord.ButtonStyle.link, url=url, emoji=EMO["open"])


class DescriptionButton(ui.Button):
    """Primary Blue button that switches the embed to Description view."""

    def __init__(self):
        super().__init__(label="Description", style=discord.ButtonStyle.primary, emoji=EMO["desc"])
        self.clicked = False

    async def callback(self, interaction: discord.Interaction):
        # mark clicked; parent view handler will detect this state
        self.clicked = True
        await interaction.response.defer()


class ReturnMainButton(ui.Button):
    """Primary Blue 'Return to Main' - shown only when in Description view."""

    def __init__(self):
        super().__init__(label="Return to Main", style=discord.ButtonStyle.primary, emoji=EMO["return"])
        self.clicked = False

    async def callback(self, interaction: discord.Interaction):
        self.clicked = True
        await interaction.response.defer()


class RandomButton(ui.Button):
    def __init__(self):
        super().__init__(label="Random", style=discord.ButtonStyle.secondary, emoji=EMO["random"])
        self.clicked = False

    async def callback(self, interaction: discord.Interaction):
        self.clicked = True
        await interaction.response.defer()


# -----------------------------
# MAIN COG
# -----------------------------
class HLTBCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.cache = CacheDB()
        self.http = aiohttp.ClientSession(headers=HEADERS)
        self.mem_cache: Dict[int, Tuple[int, Dict[str, Any]]] = {}  # game_id -> (ts, parsed)
        # schedule DB init in background
        bot.loop.create_task(self.cache.init())

    async def cog_unload(self):
        try:
            await self.http.close()
        except Exception:
            pass
        try:
            await self.cache.close()
        except Exception:
            pass

    async def search_api(self, query: str):
        h = HowLongToBeat()
        results = await h.async_search(query)
        if not results:
            return []
        results = sorted(results, key=lambda r: getattr(r, "similarity", 0), reverse=True)
        return results

    async def fetch_and_parse_game(self, game_id: int) -> Dict[str, Any]:
        """
        Multi-layered cache:
         - memory cache (short)
         - disk cache (longer TTL)
         - remote fetch & parse otherwise
        """
        now = now_ts()
        # memory cache
        mem = self.mem_cache.get(game_id)
        if mem:
            ts, parsed = mem
            if now - ts < MEM_CACHE_TTL:
                return parsed

        # disk cache
        cache_key = f"game_parsed:{game_id}"
        cached = await self.cache.get(cache_key)
        if cached:
            ts = cached["timestamp"]
            if now - ts < CACHE_TTL_SECONDS:
                parsed = cached["value"]
                self.mem_cache[game_id] = (now, parsed)
                return parsed

        # try fetch
        urls = [f"{HLTB_BASE}/game/{game_id}", f"{HLTB_BASE}/game?id={game_id}"]
        last_exc = None
        for url in urls:
            try:
                text = await fetch_text(self.http, url)
                parsed = parse_hltb_game_page(text)
                parsed["_source_url"] = url
                parsed["_fetched_at"] = now
                # store
                self.mem_cache[game_id] = (now, parsed)
                await self.cache.set(cache_key, parsed)
                return parsed
            except Exception as exc:
                last_exc = exc
                continue
        # fallback error
        raise last_exc or RuntimeError("Failed to fetch game page")

    def build_summary_embed(self, api_obj, parsed: Dict[str, Any], requester: discord.User) -> discord.Embed:
        """
        Builds the main summary embed shown initially.
        """
        title = getattr(api_obj, "game_name", parsed.get("title", "Unknown"))
        url = parsed.get("_source_url", f"{HLTB_BASE}/")
        image = parsed.get("image") or getattr(api_obj, "game_image_url", None)
        platforms = getattr(api_obj, "profile_platforms", []) or []

        embed = discord.Embed(
            title=f"{EMO['sparkle']} {safe_truncate(title, 256)}",
            url=url,
            color=COLOR_ACCENT,
            description=f"{EMO['platform']} Platforms: {compact_join(platforms, limit=6)}\n\n"
                        f"{EMO['choice']} Search score: {getattr(api_obj, 'similarity', 0):.2f}"
        )
        if image:
            embed.set_thumbnail(url=image)

        # times
        lines = []
        try:
            api_main = getattr(api_obj, "main_story", None)
            api_main_extra = getattr(api_obj, "main_extra", None)
            api_comp = getattr(api_obj, "completionist", None)
            if api_main is not None:
                lines.append(f"{EMO['main']} **Main:** {format_hours(api_main)}")
            if api_main_extra is not None:
                lines.append(f"{EMO['extra']} **Main + Extra:** {format_hours(api_main_extra)}")
            if api_comp is not None:
                lines.append(f"{EMO['complete']} **Completionist:** {format_hours(api_comp)}")
        except Exception:
            pass

        # fallback scraped times
        te = parsed.get("time_estimates", {})
        for k, v in te.items():
            lines.append(f"{EMO['stats']} **{k.title()}:** {v}")

        embed.add_field(name="⏱️ Estimated Times", value="\n".join(lines) if lines else "No time data available", inline=False)

        # genres/tags
        genres = parsed.get("genres", []) or []
        if genres:
            embed.add_field(name=f"{EMO['desc']} Genres / Tags", value=compact_join(genres, limit=8), inline=False)

        # show a few details inline if present
        details = parsed.get("details", {}) or {}
        if details:
            items = list(details.items())[:4]
            for k, v in items:
                embed.add_field(name=k, value=safe_truncate(v, 200), inline=True)

        embed.set_footer(text=f"Requested by {requester.display_name} • data from howlongtobeat.com")
        return embed

    def build_description_embed(self, title: str, parsed: Dict[str, Any], requester: discord.User) -> discord.Embed:
        desc_text = parsed.get("description") or "No description available."
        embed = discord.Embed(
            title=f"{EMO['desc']} Description — {safe_truncate(title, 200)}",
            description=safe_truncate(desc_text, 4000),
            color=COLOR_PRIMARY,
            url=parsed.get("_source_url", f"{HLTB_BASE}/")
        )
        if parsed.get("image"):
            embed.set_thumbnail(url=parsed.get("image"))
        embed.set_footer(text=f"Requested by {requester.display_name}")
        return embed

    def build_times_embed(self, title: str, api_obj, parsed: Dict[str, Any], requester: discord.User) -> discord.Embed:
        embed = discord.Embed(title=f"{EMO['main']} Times — {safe_truncate(title,200)}", url=parsed.get("_source_url", f"{HLTB_BASE}/"), color=COLOR_ACCENT)
        lines = []
        try:
            api_main = getattr(api_obj, "main_story", None)
            api_main_extra = getattr(api_obj, "main_extra", None)
            api_comp = getattr(api_obj, "completionist", None)
            lines.append(f"{EMO['main']} **Main:** {format_hours(api_main)}")
            lines.append(f"{EMO['extra']} **Main + Extra:** {format_hours(api_main_extra)}")
            lines.append(f"{EMO['complete']} **Completionist:** {format_hours(api_comp)}")
        except Exception:
            pass
        te = parsed.get("time_estimates", {})
        for k, v in te.items():
            lines.append(f"{EMO['stats']} **{k.title()}:** {v}")
        embed.description = "\n".join(lines) if lines else "No time estimates available."
        embed.set_footer(text=f"Requested by {requester.display_name}")
        return embed

    def build_details_embed(self, title: str, parsed: Dict[str, Any], requester: discord.User) -> discord.Embed:
        embed = discord.Embed(title=f"{EMO['details']} Details — {safe_truncate(title,200)}", url=parsed.get("_source_url", f"{HLTB_BASE}/"), color=COLOR_ACCENT)
        details = parsed.get("details") or {}
        if not details:
            embed.description = "No structured details scraped."
        else:
            for k, v in details.items():
                embed.add_field(name=k, value=safe_truncate(v, 1024), inline=False)
        embed.set_footer(text=f"Requested by {requester.display_name}")
        return embed

    def build_reviews_embed(self, title: str, parsed: Dict[str, Any], requester: discord.User) -> discord.Embed:
        embed = discord.Embed(title=f"{EMO['stats']} Reviews — {safe_truncate(title,200)}", url=parsed.get("_source_url", f"{HLTB_BASE}/"), color=COLOR_ACCENT)
        reviews = parsed.get("reviews", []) or []
        if not reviews:
            embed.description = "No reviews scraped from the page."
        else:
            # Add up to 6 reviews as fields or as concatenated description
            for i, r in enumerate(reviews[:6], start=1):
                embed.add_field(name=f"Review #{i}", value=safe_truncate(r, 1024), inline=False)
        embed.set_footer(text=f"Scraped reviews (best-effort) • Requested by {requester.display_name}")
        return embed

    def build_raw_embed(self, title: str, parsed: Dict[str, Any], requester: discord.User) -> discord.Embed:
        raw = parsed.get("raw_excerpt") or "No raw excerpt available."
        embed = discord.Embed(title=f"🧪 Raw Excerpt — {safe_truncate(title,200)}", description=f"```\n{safe_truncate(raw, 1900)}\n```", color=COLOR_ACCENT, url=parsed.get("_source_url", f"{HLTB_BASE}/"))
        embed.set_footer(text="Raw excerpt (sanitized).")
        return embed

    # -----------------------
    # Slash command
    # -----------------------
    @app_commands.command(name="hltb", description="⏳ Look up a game's HowLongToBeat profile & times.")
    @app_commands.describe(game="Full or partial game name to search for.")
    @cooldown_per_user(USER_COOLDOWN_SECONDS)
    async def hltb(self, interaction: discord.Interaction, game: str):
        """
        Flow:
         1) search howlongtobeatpy
         2) if multiple results, show a dropdown to pick
         3) fetch & parse page (cache-aware)
         4) show summary embed with interactive view: section select, Description (blue), Random, Open link
         5) if Description pressed -> edit message to description embed and swap to Return to Main button
        """
        await interaction.response.defer(thinking=True)

        # 1) search
        try:
            results = await self.search_api(game)
        except Exception as exc:
            await interaction.followup.send(f"{EMO['error']} Search failed: `{exc}`")
            return

        if not results:
            await interaction.followup.send(f"{EMO['error']} No results found for **{game}**.")
            return

        # 2) pick result if multiple
        chosen_api_obj = None
        if len(results) > 1:
            pick_view = ui.View(timeout=30)
            select = ResultSelect(results)
            pick_view.add_item(select)
            pick_embed = discord.Embed(
                title=f"{EMO['search']} Multiple results found",
                description=f"I found multiple matches for **{game}**. Please select the correct one from the dropdown.",
                color=COLOR_PRIMARY
            )
            preview_lines = []
            for i, r in enumerate(results[:MAX_SELECT_OPTIONS]):
                pfs = ", ".join(getattr(r, "profile_platforms", []) or [])
                preview_lines.append(f"**{i+1}.** {safe_truncate(r.game_name, 80)} — `{getattr(r,'similarity',0):.2f}` • {pfs}")
            if preview_lines:
                pick_embed.add_field(name="Top results", value="\n".join(preview_lines), inline=False)

            prompt_msg = await interaction.followup.send(embed=pick_embed, view=pick_view)
            await pick_view.wait()

            if select.chosen_index is None:
                await prompt_msg.edit(content=f"{EMO['timeout']} Selection timed out. Try again.", embed=None, view=None)
                return

            chosen_api_obj = results[select.chosen_index]
            # clear the prompt
            await prompt_msg.edit(content=None, embed=None, view=None)
        else:
            chosen_api_obj = results[0]

        # Build data for chosen game
        game_id = getattr(chosen_api_obj, "game_id", None)
        title = getattr(chosen_api_obj, "game_name", "Unknown")
        api_img = getattr(chosen_api_obj, "game_image_url", None)
        platforms = getattr(chosen_api_obj, "profile_platforms", []) or []
        hltb_url = f"{HLTB_BASE}/game/{game_id}" if game_id else HLTB_BASE

        # 3) fetch parsed page (cache-aware)
        parsed = {}
        try:
            if game_id:
                parsed = await self.fetch_and_parse_game(game_id)
            else:
                parsed = {"title": title, "description": None, "genres": [], "details": {}, "time_estimates": {}, "reviews":[], "image": api_img, "_source_url": hltb_url}
        except Exception:
            parsed = {"title": title, "description": None, "genres": [], "details": {}, "time_estimates": {}, "reviews":[], "image": api_img, "_source_url": hltb_url}

        # 4) build summary embed and interactive view
        summary_embed = self.build_summary_embed(chosen_api_obj, parsed, interaction.user)

        main_view = ui.View(timeout=180)
        section_select = SectionSelect()
        main_view.add_item(section_select)

        desc_button = DescriptionButton()
        main_view.add_item(desc_button)

        rand_button = RandomButton()
        main_view.add_item(rand_button)

        main_view.add_item(OpenHLTBButton(parsed.get("_source_url", hltb_url)))

        # Send message
        summary_message = await interaction.followup.send(embed=summary_embed, view=main_view)

        # Wait for interactions (section select / description / random) or timeout
        await main_view.wait()

        # If description button clicked -> edit to description embed and show Return button
        if desc_button.clicked:
            desc_embed = self.build_description_embed(title, parsed, interaction.user)
            # view with Return to Main (only appears here) + Open button
            return_view = ui.View(timeout=300)
            return_button = ReturnMainButton()
            return_view.add_item(return_button)
            return_view.add_item(OpenHLTBButton(parsed.get("_source_url", hltb_url)))
            await summary_message.edit(embed=desc_embed, view=return_view)

            # wait for return button or timeout
            await return_view.wait()
            if return_button.clicked:
                # go back to main summary embed
                await summary_message.edit(embed=summary_embed, view=main_view)
                # reset states in case user clicks again
                desc_button.clicked = False
                return_button.clicked = False
            else:
                # timed out, keep as-is but remove buttons to avoid stale interactions
                await summary_message.edit(embed=desc_embed, view=None)
            return

        # If random button clicked
        if rand_button.clicked:
            # pick a random index within available results
            idx = random.randint(0, min(len(results) - 1, MAX_SELECT_OPTIONS - 1))
            random_obj = results[idx]
            # refetch parsed for the new selection
            new_id = getattr(random_obj, "game_id", None)
            new_title = getattr(random_obj, "game_name", "Unknown")
            new_img = getattr(random_obj, "game_image_url", None)
            new_url = f"{HLTB_BASE}/game/{new_id}" if new_id else HLTB_BASE
            try:
                new_parsed = await self.fetch_and_parse_game(new_id) if new_id else {"title": new_title, "image": new_img, "_source_url": new_url, "description": None, "genres": [], "details": {}, "time_estimates": {}, "reviews":[]}
            except Exception:
                new_parsed = {"title": new_title, "image": new_img, "_source_url": new_url, "description": None, "genres": [], "details": {}, "time_estimates": {}, "reviews":[]}

            new_summary = self.build_summary_embed(random_obj, new_parsed, interaction.user)
            new_view = ui.View(timeout=180)
            new_view.add_item(SectionSelect())
            new_view.add_item(DescriptionButton())
            new_view.add_item(OpenHLTBButton(new_parsed.get("_source_url", new_url)))
            await summary_message.edit(embed=new_summary, view=new_view)
            return

        # If section select was used
        if section_select.chosen:
            chosen_section = section_select.chosen
            if chosen_section == "Overview":
                ov_embed = discord.Embed(title=f"{EMO['sparkle']} Overview — {safe_truncate(title,200)}", url=parsed.get("_source_url", hltb_url), color=COLOR_ACCENT)
                short_desc = parsed.get("description") or ""
                ov_embed.description = safe_truncate(short_desc, 900) if short_desc else "No description available."
                # key details
                details = parsed.get("details", {})
                if details:
                    for i, (k, v) in enumerate(details.items()):
                        if i >= 6:
                            break
                        ov_embed.add_field(name=k, value=safe_truncate(v, 200), inline=True)
                if parsed.get("image"):
                    ov_embed.set_thumbnail(url=parsed.get("image"))
                ov_embed.set_footer(text=f"Requested by {interaction.user.display_name}")
                await summary_message.edit(embed=ov_embed, view=ui.View().add_item(OpenHLTBButton(parsed.get("_source_url", hltb_url))))
                return

            if chosen_section == "Times":
                times_embed = self.build_times_embed(title, chosen_api_obj, parsed, interaction.user)
                await summary_message.edit(embed=times_embed, view=ui.View().add_item(OpenHLTBButton(parsed.get("_source_url", hltb_url))))
                return

            if chosen_section == "Description":
                desc_embed = self.build_description_embed(title, parsed, interaction.user)
                # include return button
                dv = ui.View(timeout=300)
                rb = ReturnMainButton()
                dv.add_item(rb)
                dv.add_item(OpenHLTBButton(parsed.get("_source_url", hltb_url)))
                await summary_message.edit(embed=desc_embed, view=dv)
                await dv.wait()
                if rb.clicked:
                    # return to summary
                    await summary_message.edit(embed=summary_embed, view=main_view)
                    rb.clicked = False
                else:
                    await summary_message.edit(embed=desc_embed, view=None)
                return

            if chosen_section == "Details":
                det_embed = self.build_details_embed(title, parsed, interaction.user)
                await summary_message.edit(embed=det_embed, view=ui.View().add_item(OpenHLTBButton(parsed.get("_source_url", hltb_url))))
                return

            if chosen_section == "Reviews":
                rev_embed = self.build_reviews_embed(title, parsed, interaction.user)
                await summary_message.edit(embed=rev_embed, view=ui.View().add_item(OpenHLTBButton(parsed.get("_source_url", hltb_url))))
                return

            if chosen_section == "Raw":
                raw_embed = self.build_raw_embed(title, parsed, interaction.user)
                await summary_message.edit(embed=raw_embed, view=ui.View().add_item(OpenHLTBButton(parsed.get("_source_url", hltb_url))))
                return

        # Fallback: no actionable interaction or timed out without selection
        await summary_message.edit(content="No action selected. Use the buttons or the link to open the HowLongToBeat page.", view=ui.View().add_item(OpenHLTBButton(parsed.get("_source_url", hltb_url))))

# Setup
async def setup(bot: commands.Bot):
    await bot.add_cog(HLTBCog(bot))
