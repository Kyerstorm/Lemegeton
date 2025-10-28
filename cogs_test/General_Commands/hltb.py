# cogs/hltb.py
# =============================================================
# /hltb - Blue Galaxy Themed, Option-Button UI replacement for dropdowns
# - Buttons for pre-selection (before main embed)
# - Cleaner main embed: only important metadata (title, platforms, times, genres)
# - Visual completion timeline bar
# - Steam button detected from scraped text (only shown when found)
# - Full description support: if >4096 chars, show preview + Description button,
#   clicking it replaces embed with full description split across multiple embeds,
#   with Return to Main button.
# =============================================================

import asyncio
import aiohttp
import aiosqlite
import json
import os
import random
import re
import time
from functools import wraps
from typing import Any, Dict, List, Optional, Tuple
from fractions import Fraction

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
MAX_OPTIONS_BUTTONS = 5
REQUEST_TIMEOUT = 20  # seconds
HLTB_BASE = "https://howlongtobeat.com"

# Galaxy/Dark theme
COLOR_PRIMARY = discord.Color.from_rgb(11, 84, 166)
COLOR_ACCENT = discord.Color.from_rgb(10, 12, 18)  # deeper galaxy background
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
    "steam": "🎮",
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
    if text is None:
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
                # ephemeral response so it doesn't clutter the channel
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
        # iterate through all text nodes to find matches
        for label, key in label_map.items():
            # find elements containing the label text
            el = soup.find(string=re.compile(re.escape(label), re.I))
            if el:
                parent = el.parent
                if parent:
                    # search nearby for numeric patterns
                    found = None
                    # look for a sibling or nearby number
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

    # Reviews: best-effort
    try:
        review_candidates = soup.select(".user_reviews, .reviews, .comments, .review, .userreview")
        for rc in review_candidates:
            for item in rc.find_all(["div", "article", "li"], limit=8):
                txt = item.get_text("\n", strip=True)
                if txt and len(txt) > 30:
                    data["reviews"].append(safe_truncate(txt, 800))
        if not data["reviews"]:
            for block in soup.find_all(text=re.compile(r"\b(review|user review|posted)\b", re.I)):
                parent = block.parent
                if parent:
                    txt = parent.get_text(" ", strip=True)
                    if txt and len(txt) > 40:
                        data["reviews"].append(safe_truncate(txt, 800))
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
# Parsers / Helpers for times & bars
# -----------------------------
def parse_hours_to_number(hours_str: Optional[str]) -> Optional[float]:
    """
    Try to extract a numeric hour value from a variety of string formats:
      - "35 Hours"
      - "35.5"
      - "35½"
      - "1 1/2"
    Returns float hours or None if can't parse.
    """
    if not hours_str:
        return None
    s = str(hours_str).strip()
    # normalize unicode halves
    s = s.replace("½", " 1/2 ").replace("–", "-").replace("—", "-")
    # common patterns: number optionally with fraction
    # extract the first numeric/fraction sequence
    m = re.search(r"(\d{1,4}(?:[.,]\d+)?(?:\s*\d+/\d+)?|\d+/\d+)", s)
    if not m:
        return None
    token = m.group(0).strip()
    # Try direct float
    try:
        token_clean = token.replace(",", ".")
        if "/" in token_clean and " " in token_clean:
            # e.g. "1 1/2"
            parts = token_clean.split()
            whole = float(parts[0])
            frac = float(Fraction(parts[1]))
            return whole + frac
        if "/" in token_clean:
            return float(Fraction(token_clean))
        return float(token_clean)
    except Exception:
        try:
            # fallback: find all numbers and take first
            mm = re.search(r"\d+(\.\d+)?", s)
            if mm:
                return float(mm.group(0))
        except Exception:
            return None
    return None


def build_progress_bar(values: Dict[str, Optional[float]], labels_map: Dict[str, str], width: int = 24) -> List[str]:
    """
    Build Unicode progress bars for 'main', 'main_extra', 'completionist' using width blocks.
    values: mapping to numeric hours or None.
    labels_map: mapping key -> emoji+label prefix.
    Returns list of formatted lines.
    """
    # extract the numeric values
    nums = {k: (None if values.get(k) is None else float(values.get(k))) for k in ["main", "main_extra", "completionist"]}
    # if none present, fallback to show scraped text lines instead (handled elsewhere)
    present = [v for v in nums.values() if v is not None]
    if not present:
        return []

    maxv = max(present)
    if maxv <= 0:
        maxv = 1.0

    lines = []
    for key in ["main", "main_extra", "completionist"]:
        val = nums.get(key)
        label = labels_map.get(key, key.title())
        if val is None:
            line = f"{label}: No data"
            lines.append(line)
            continue
        # scale to width
        ratio = min(val / maxv, 1.0)
        filled = int(round(ratio * width))
        empty = width - filled
        bar = "█" * filled + "░" * empty
        # align label for neatness
        lines.append(f"{label}: [{bar}] {val:g}h")
    return lines


# -----------------------------
# UI COMPONENTS (buttons & views)
# -----------------------------
class OptionButton(ui.Button):
    def __init__(self, label: str, index: int, details: str = ""):
        super().__init__(label=safe_truncate(label, 80), style=discord.ButtonStyle.secondary, emoji=EMO["choice"], custom_id=f"hltb_opt_{index}")
        self.index = index
        self.details = details
        self.clicked = False

    async def callback(self, interaction: discord.Interaction):
        # mark which button was clicked and stop view
        self.clicked = True
        # store chosen index on the parent view for retrieval
        if isinstance(self.view, OptionSelectionView):
            self.view.chosen_index = self.index
        # acknowledge
        await interaction.response.defer()
        self.view.stop()


class OptionSelectionView(ui.View):
    def __init__(self, results: List[Any], timeout: int = 30):
        super().__init__(timeout=timeout)
        self.results = results
        self.chosen_index: Optional[int] = None
        # create up to MAX_OPTIONS_BUTTONS
        for i, r in enumerate(results[:MAX_OPTIONS_BUTTONS]):
            label = getattr(r, "game_name", "Unknown")
            # add a second-line hint by setting `details` stored on button (not visible)
            btn = OptionButton(label=label, index=i)
            self.add_item(btn)


class DescriptionButton(ui.Button):
    """Primary Description button to show full description view if required."""
    def __init__(self):
        super().__init__(label="Description", style=discord.ButtonStyle.primary, emoji=EMO["desc"])
        self.clicked = False

    async def callback(self, interaction: discord.Interaction):
        self.clicked = True
        await interaction.response.defer()
        self.view.stop()


class ReturnMainButton(ui.Button):
    """Return to Main button to go back from description to main embed."""
    def __init__(self):
        super().__init__(label="Return to Main", style=discord.ButtonStyle.primary, emoji=EMO["return"])
        self.clicked = False

    async def callback(self, interaction: discord.Interaction):
        self.clicked = True
        await interaction.response.defer()
        self.view.stop()


class OpenHLTBButton(ui.Button):
    def __init__(self, url: str):
        super().__init__(label="Open on HLTB", style=discord.ButtonStyle.link, url=url, emoji=EMO["open"])


class SteamButton(ui.Button):
    def __init__(self, url: str):
        super().__init__(label="Steam Page", style=discord.ButtonStyle.link, url=url, emoji=EMO["steam"])


class RandomButton(ui.Button):
    def __init__(self):
        super().__init__(label="Random", style=discord.ButtonStyle.secondary, emoji=EMO["random"])
        self.clicked = False

    async def callback(self, interaction: discord.Interaction):
        self.clicked = True
        await interaction.response.defer()
        self.view.stop()


# -----------------------------
# MAIN COG
# -----------------------------
class HLTBCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.cache = CacheDB()
        self.http = aiohttp.ClientSession(headers=HEADERS)
        self.mem_cache: Dict[int, Tuple[int, Dict[str, Any]]] = {}  # game_id -> (ts, parsed)

    async def cog_load(self):
        """Initialize cache when cog loads."""
        await self.cache.init()

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
        # async_search is used in original; if blocking, you may need to adapt
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

    def detect_steam_link(self, parsed: Dict[str, Any], api_obj=None) -> Optional[str]:
        """
        Try to find a Steam store link in parsed data or in api_obj fields.
        Search parsed raw excerpt and details for 'store.steampowered.com/app/<id>'.
        """
        # check parsed details values
        patterns = []
        raw = ""
        try:
            details = parsed.get("details", {}) or {}
            for k, v in details.items():
                raw += " " + str(v)
        except Exception:
            pass
        raw += " " + (parsed.get("raw_excerpt") or "")
        # also check api_obj fields
        try:
            if api_obj:
                raw += " " + str(getattr(api_obj, "game_name", "")) + " " + str(getattr(api_obj, "game_image_url", "") or "")
        except Exception:
            pass
        # search for steam URL
        m = re.search(r"(https?://store\.steampowered\.com/app/\d+[^)\s]*)", raw, re.I)
        if m:
            return m.group(1)
        return None

    def build_summary_embed(self, api_obj, parsed: Dict[str, Any], requester: discord.User) -> discord.Embed:
        """
        Builds the main summary embed shown initially.
        Only includes the important metadata: title, platforms, times (+ completion bar), genres, and minimal details.
        """
        title = getattr(api_obj, "game_name", parsed.get("title", "Unknown"))
        url = parsed.get("_source_url", f"{HLTB_BASE}/")
        image = parsed.get("image") or getattr(api_obj, "game_image_url", None)
        platforms = getattr(api_obj, "profile_platforms", []) or []

        embed = discord.Embed(
            title=f"{EMO['sparkle']} {safe_truncate(title, 256)}",
            url=url,
            color=COLOR_ACCENT,
        )
        # Thumbnail
        if image:
            embed.set_thumbnail(url=image)

        # Platforms line in description
        embed.description = f"{EMO['platform']} **Platforms:** {compact_join(platforms, limit=6)}"

        # Times & Progress bar
        # Try to collect numeric time values (from API object first, then parsed text)
        numeric_times = {}
        try:
            api_main = getattr(api_obj, "main_story", None)
            api_main_extra = getattr(api_obj, "main_extra", None)
            api_comp = getattr(api_obj, "completionist", None)
            numeric_times["main"] = parse_hours_to_number(api_main) or parse_hours_to_number(parsed.get("time_estimates", {}).get("main"))
            numeric_times["main_extra"] = parse_hours_to_number(api_main_extra) or parse_hours_to_number(parsed.get("time_estimates", {}).get("main_extra"))
            numeric_times["completionist"] = parse_hours_to_number(api_comp) or parse_hours_to_number(parsed.get("time_estimates", {}).get("completionist"))
        except Exception:
            numeric_times["main"] = parse_hours_to_number(parsed.get("time_estimates", {}).get("main"))
            numeric_times["main_extra"] = parse_hours_to_number(parsed.get("time_estimates", {}).get("main_extra"))
            numeric_times["completionist"] = parse_hours_to_number(parsed.get("time_estimates", {}).get("completionist"))

        # Build the visual progress bar lines
        labels_map = {
            "main": f"{EMO['main']} Main",
            "main_extra": f"{EMO['extra']} Main + Extra",
            "completionist": f"{EMO['complete']} Completionist",
        }
        bar_lines = build_progress_bar(numeric_times, labels_map, width=24)

        # Build times textual fallback lines (if non-numeric values exist)
        textual_lines = []
        te = parsed.get("time_estimates", {}) or {}
        for key in ["main", "main_extra", "completionist"]:
            raw_val = te.get(key)
            if raw_val:
                textual_lines.append(f"{labels_map.get(key)}: {raw_val}")

        # Add fields: Estimated Times (bar + textual)
        if bar_lines:
            embed.add_field(name="⏱️ Estimated Times (relative)", value="\n".join(bar_lines), inline=False)
        elif textual_lines:
            embed.add_field(name="⏱️ Estimated Times", value="\n".join(textual_lines), inline=False)
        else:
            embed.add_field(name="⏱️ Estimated Times", value="No time data available", inline=False)

        # Genres / Tags (compact)
        genres = parsed.get("genres", []) or []
        if genres:
            embed.add_field(name=f"{EMO['desc']} Genres", value=compact_join(genres, limit=8), inline=False)

        # Minimal details (Developer / Publisher / Release) if present, only show up to 3 small fields
        details = parsed.get("details", {}) or {}
        # prefer Developer, Publisher, Release
        for key in ["Developer", "Publisher", "Release", "Released"]:
            if key in details:
                embed.add_field(name=key, value=safe_truncate(details[key], 200), inline=True)

        embed.set_footer(text=f"🌌 Requested by {requester.display_name} • data from howlongtobeat.com")
        return embed

    def build_description_embeds(self, title: str, parsed: Dict[str, Any], requester: discord.User) -> List[discord.Embed]:
        """
        Create a list of embeds that contain the full description split across Discord embed limits (4096).
        Returns a list of embeds where first embed includes a title header.
        """
        desc_text = parsed.get("description") or "No description available."
        # split into chunks <= 4096
        max_len = 4096
        chunks = []
        i = 0
        while i < len(desc_text):
            chunks.append(desc_text[i:i+max_len])
            i += max_len
        embeds = []
        for idx, chunk in enumerate(chunks):
            if idx == 0:
                e = discord.Embed(title=f"{EMO['desc']} Description — {safe_truncate(title,200)}", description=chunk, color=COLOR_PRIMARY, url=parsed.get("_source_url", f"{HLTB_BASE}/"))
            else:
                e = discord.Embed(description=chunk, color=COLOR_PRIMARY)
            if parsed.get("image"):
                e.set_thumbnail(url=parsed.get("image"))
            e.set_footer(text=f"Requested by {requester.display_name} • Part {idx+1}/{len(chunks)}")
            embeds.append(e)
        return embeds

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
         2) if multiple results, show an OptionSelectionView (buttons) before main message
         3) on selection, fetch & parse page (cache-aware)
         4) show clean summary embed with times + progress bar, genres, minimal details
         5) if Description exceeds embed limit: show preview + Description button which when clicked shows full description embeds and Return button
         6) Steam button shown only when Steam link detected
        """
        # Immediately defer to avoid interaction failing on longer searches
        await interaction.response.defer(thinking=True)

        # 1) search
        try:
            results = await self.search_api(game)
        except Exception as exc:
            await interaction.followup.send(f"{EMO['error']} Search failed: `{exc}`", ephemeral=True)
            return

        if not results:
            await interaction.followup.send(f"{EMO['error']} No results found for **{game}**.", ephemeral=True)
            return

        # 2) if multiple, show OptionSelectionView BEFORE sending the main embed
        chosen_api_obj = None
        if len(results) > 1:
            # send a prompt message with option buttons and a short preview
            preview_embed = discord.Embed(title=f"{EMO['search']} Multiple matches found", description=f"Click the button matching the correct game for **{game}** (you have 30s).", color=COLOR_PRIMARY)
            preview_lines = []
            for i, r in enumerate(results[:MAX_OPTIONS_BUTTONS]):
                pfs = ", ".join(getattr(r, "profile_platforms", []) or [])
                preview_lines.append(f"**{i+1}.** {safe_truncate(r.game_name, 80)} — {pfs}")
            if preview_lines:
                preview_embed.add_field(name="Top matches", value="\n".join(preview_lines), inline=False)

            opt_view = OptionSelectionView(results, timeout=30)
            # send ephemeral so the selection doesn't clutter the channel — but user asked it should be before the message is sent.
            # Instead of ephemeral, we'll send it as a normal message but delete it later to "disappear".
            prompt_msg = await interaction.followup.send(embed=preview_embed, view=opt_view)
            # wait for selection (OptionButton callback will set chosen_index and stop the view)
            await opt_view.wait()

            if opt_view.chosen_index is None:
                # remove the prompt and notify
                try:
                    await prompt_msg.edit(content=f"{EMO['timeout']} Selection timed out. Try again.", embed=None, view=None)
                    await asyncio.sleep(2)
                    await prompt_msg.delete()
                except Exception:
                    pass
                return

            # chosen object
            chosen_api_obj = results[opt_view.chosen_index]
            # delete prompt to remove options from chat
            try:
                await prompt_msg.delete()
            except Exception:
                # best-effort
                try:
                    await prompt_msg.edit(embed=None, view=None, content=None)
                except Exception:
                    pass
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
                parsed = {"title": title, "description": None, "genres": [], "details": {}, "time_estimates": {}, "reviews":[], "image": api_img, "_source_url": hltb_url, "raw_excerpt": ""}
        except Exception:
            parsed = {"title": title, "description": None, "genres": [], "details": {}, "time_estimates": {}, "reviews":[], "image": api_img, "_source_url": hltb_url, "raw_excerpt": ""}

        # 4) build summary embed and interactive view
        summary_embed = self.build_summary_embed(chosen_api_obj, parsed, interaction.user)

        main_view = ui.View(timeout=300)
        # Add Description button only if description exists and is long
        full_desc = parsed.get("description") or ""
        # If description length <= 4096, we can include it in a description view if user wants, else small preview
        if full_desc:
            if len(full_desc) > 4000:  # keep some headroom
                # add a preview to embed description
                preview_text = safe_truncate(full_desc, 1800)
                # append to existing description to give a hint
                summary_embed.description += f"\n\n{safe_truncate(preview_text, 1500)}"
                # add Description button to view
                desc_btn = DescriptionButton()
                main_view.add_item(desc_btn)
            else:
                # small description fits; include it as an extra field
                summary_embed.add_field(name=f"{EMO['desc']} Short Description", value=safe_truncate(full_desc, 1024), inline=False)

        # Random button
        rand_button = RandomButton()
        main_view.add_item(rand_button)

        # Steam button detection
        steam_link = self.detect_steam_link(parsed, chosen_api_obj)
        if steam_link:
            main_view.add_item(SteamButton(steam_link))

        # Open HLTB button always present
        main_view.add_item(OpenHLTBButton(parsed.get("_source_url", hltb_url)))

        # Send the summary as followup (we already deferred earlier)
        summary_message = await interaction.followup.send(embed=summary_embed, view=main_view)

        # Wait for view interactions (desc, random, return handled below)
        await main_view.wait()

        # If Description button clicked
        if any(isinstance(i, DescriptionButton) and i.clicked for i in main_view.children):
            # Build full description embeds
            desc_embeds = self.build_description_embeds(title, parsed, interaction.user)
            # Create view with Return button and Open link (and Steam if available)
            dv = ui.View(timeout=300)
            rb = ReturnMainButton()
            dv.add_item(rb)
            if steam_link:
                dv.add_item(SteamButton(steam_link))
            dv.add_item(OpenHLTBButton(parsed.get("_source_url", hltb_url)))
            # Try to edit the original summary message to show the entire description embeds
            try:
                # Discord limits embedding up to 10 embeds per message. We'll send the first up to 10 in one edit,
                # and if more are needed, send them as followups without views.
                first_batch = desc_embeds[:10]
                await summary_message.edit(embeds=first_batch, view=dv, content=None)
                # send the remaining as followups (no view)
                if len(desc_embeds) > 10:
                    for more in range(10, len(desc_embeds)):
                        await interaction.followup.send(embed=desc_embeds[more])
                # wait for return
                await dv.wait()
                if rb.clicked:
                    # return to main summary
                    await summary_message.edit(embed=summary_embed, view=main_view)
                    rb.clicked = False
                    # reset desc button state if present
                    for child in main_view.children:
                        if isinstance(child, DescriptionButton):
                            child.clicked = False
                    return
                else:
                    # timed out: remove buttons to avoid stale interactions
                    await summary_message.edit(view=None)
                    return
            except Exception:
                # best-effort fallback: send the description in multiple followups
                try:
                    await interaction.followup.send("Full Description:", ephemeral=True)
                    for e in desc_embeds:
                        await interaction.followup.send(embed=e)
                except Exception:
                    pass
                return

        # If Random button clicked
        if any(isinstance(i, RandomButton) and i.clicked for i in main_view.children):
            # pick a random index within available results
            idx = random.randint(0, min(len(results) - 1, MAX_OPTIONS_BUTTONS - 1))
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
            # attach description button if needed
            if new_parsed.get("description") and len(new_parsed.get("description", "")) > 4000:
                new_view.add_item(DescriptionButton())
            # steam detection
            new_steam = self.detect_steam_link(new_parsed, random_obj)
            if new_steam:
                new_view.add_item(SteamButton(new_steam))
            new_view.add_item(OpenHLTBButton(new_parsed.get("_source_url", new_url)))
            await summary_message.edit(embed=new_summary, view=new_view)
            return

        # fallback: timed out without actionable interaction
        try:
            await summary_message.edit(content="No action selected. Use the buttons or the link to open the HowLongToBeat page.", view=ui.View().add_item(OpenHLTBButton(parsed.get("_source_url", hltb_url))))
        except Exception:
            pass


# Setup
async def setup(bot: commands.Bot):
    await bot.add_cog(HLTBCog(bot))
