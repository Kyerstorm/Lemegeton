# cogs/utilities/hltb.py

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

# =============================================================
# CONFIGURATION
# =============================================================
CACHE_DB_PATH = os.getenv("HLTB_CACHE_DB", "hltb_cache.sqlite")
CACHE_TTL_SECONDS = 60 * 60 * 24 * 14  # 14 days cache lifetime on disk
MEM_CACHE_TTL = 60 * 60  # 1 hour in-memory cache
USER_COOLDOWN_SECONDS = 3  # per-user cooldown to avoid spam
MAX_OPTIONS_BUTTONS = 5
REQUEST_TIMEOUT = 20  # seconds
HLTB_BASE = "https://howlongtobeat.com"

# Theme Colors
COLOR_PRIMARY = discord.Color.from_rgb(11, 84, 166)
COLOR_ACCENT = discord.Color.from_rgb(10, 12, 18)  # deep galactic background
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
    "steam": "🔵",
    "gog": "🟣",
    "epic": "🟥",
}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; DiscordBot/1.0; +https://github.com/)"
}

# =============================================================
# UTILITIES
# =============================================================
def now_ts() -> int:
    return int(time.time())


def format_hours(v) -> str:
    """Human-friendly formatting for hours fields."""
    if v is None:
        return "N/A"
    try:
        if isinstance(v, (int, float)):
            return f"{v:g} hrs"
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


# =============================================================
# CACHE: SQLite + in-memory
# =============================================================
class CacheDB:
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


# =============================================================
# NETWORK & SCRAPING
# =============================================================
async def fetch_text(session: aiohttp.ClientSession, url: str, timeout: int = REQUEST_TIMEOUT) -> str:
    async with session.get(url, headers=HEADERS, timeout=timeout) as resp:
        resp.raise_for_status()
        return await resp.text()


def parse_hltb_game_page(html: str) -> Dict[str, Any]:
    soup = BeautifulSoup(html, "lxml")
    data: Dict[str, Any] = {
        "title": None,
        "image": None,
        "description": None,
        "genres": [],
        "details": {},
        "time_estimates": {},
        "playstyles": {},
        "reviews": [],
        "raw_excerpt": None,
        "stores": {},  # store_key -> {"url":..., "price":...}
        "stats": {},   # playing, backlogs, replays, retired, rating, beat
        "release_dates": {},  # NA, EU, JP
        "updated": None,
    }

    # Title
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

    # Description
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

    # Genres / chips
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
        data["genres"] = list(dict.fromkeys([c for c in chips if c]))
    except Exception:
        data["genres"] = data.get("genres", [])

    # Details parsing: Developer, Publisher, Release
    try:
        detail_blocks = soup.select(".profile .profile_info, .game_profile .profile_info, .search_list_details")
        for block in detail_blocks:
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

    # Release dates & updated - try to parse by label words in details and anywhere in page
    try:
        # look for patterns like "NA:", "EU:", "JP:", "Updated:"
        for label in ["NA", "EU", "JP", "Updated", "Release", "Released"]:
            el = soup.find(string=re.compile(rf"\b{label}\b", re.I))
            if el:
                parent = el.parent
                if parent:
                    txt = parent.get_text(" ", strip=True)
                    # attempt to extract date-like substring after colon
                    m = re.search(rf"{label}\s*[:\-]\s*([A-Za-z0-9, \-]+)", txt)
                    if m:
                        val = m.group(1).strip()
                        if label in ["NA", "EU", "JP"]:
                            data["release_dates"][label] = val
                        elif label == "Updated":
                            data["updated"] = val
                        else:
                            data["details"][label] = val
    except Exception:
        pass

    # Time estimates + playstyles
    try:
        # common labels to keys
        label_map = {
            "Main Story": "main",
            "Main + Extra": "main_extra",
            "Completionist": "completionist",
            "Solo": "solo",
            "Co-op": "coop",
            "Solo Play": "solo",
            "Co-op Play": "coop",
        }
        # find blocks with time entries: many HLTB pages have list items or spans with label+value
        for label_text, key in label_map.items():
            el = soup.find(string=re.compile(re.escape(label_text), re.I))
            if el:
                parent = el.parent
                if parent:
                    # search siblings and parent text for hours format
                    found = None
                    near = parent.find_next(string=re.compile(r"\d{1,4}[\d\.\½\¾]*\s*(Hours|hrs|h)?", re.I))
                    if near:
                        found = near.strip()
                    else:
                        txt = parent.get_text(" ", strip=True)
                        m = re.search(r"(\d{1,4}[\d\.\½\¾]*)\s*(Hours|hrs|h)?", txt)
                        if m:
                            found = m.group(0)
                    if found:
                        data["time_estimates"][key] = found
                        data["playstyles"][key] = found
    except Exception:
        pass

    # Best-effort: find other time strings in the page and add to time_estimates if not already present
    try:
        all_text = soup.get_text(" ", strip=True)
        for m in re.finditer(r"(Main Story|Main \+ Extra|Completionist|Solo|Co-?op)\s*[:\-]?\s*(\d{1,4}[\d\.\½\¾]*\s*(?:Hours|hrs|h)?)", all_text, re.I):
            label = m.group(1)
            val = m.group(2)
            canonical = label_map.get(label, label.lower())
            data["time_estimates"][canonical] = val.strip()
            data["playstyles"][canonical] = val.strip()
    except Exception:
        pass

    # Reviews - best-effort
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

    # Stores detection (Steam, GOG, Epic) + price detection near anchors
    try:
        store_map = {
            "steampowered.com": "steam",
            "gog.com": "gog",
            "epicgames.com": "epic",
            "epicstore": "epic",
        }
        stores: Dict[str, Dict[str, str]] = {}
        # anchors first
        for a in soup.find_all("a", href=True):
            href = a["href"].strip()
            for key in store_map:
                if key in href.lower():
                    store_key = store_map[key]
                    # try to find price: check anchor text, sibling spans, parent text
                    price = None
                    txt = a.get_text(" ", strip=True) or ""
                    # sibling price
                    sib = a.find_next_sibling(text=re.compile(r"[$€£]\s?\d+[.,]?\d*"))
                    if sib:
                        price = sib.strip()
                    # parent search
                    if not price:
                        parent_text = a.parent.get_text(" ", strip=True) if a.parent else ""
                        m = re.search(r"([$€£]\s?\d+[.,]?\d*)", parent_text)
                        if m:
                            price = m.group(1).strip()
                    # fallback: scan near the anchor in the page text (nearby 200 chars)
                    if not price:
                        raw = str(a)[:400] + (a.parent and str(a.parent)[:400] or "")
                        m2 = re.search(r"([$€£]\s?\d+[.,]?\d*)", raw)
                        if m2:
                            price = m2.group(1).strip()
                    stores[store_key] = {"url": href, "price": price}
        # additional pattern scan in raw text for store links without anchors
        raw_text = soup.get_text(" ", strip=True)
        for dom, store_key in store_map.items():
            m = re.search(rf"(https?://[^\s)\"']*{re.escape(dom)}[^\s)\"']*)", raw_text, re.I)
            if m and store_key not in stores:
                stores[store_key] = {"url": m.group(1), "price": None}
        data["stores"] = stores
    except Exception:
        data["stores"] = {}

    # Stats: Playing, Backlogs, Replays, Retired, Rating, Beat
    try:
        stats = {}
        # common labels and regexes
        stats_labels = {
            "Playing": r"\bPlaying\b",
            "Backlogs": r"\bBacklog(?:s)?\b|\bBacklogs\b",
            "Replays": r"\bReplays?\b",
            "Retired": r"\bRetired\b",
            "Rating": r"\bRating\b|\bAvg Rating\b",
            "Beat": r"\bBeat\b|\bBeaten\b",
        }
        page_text = soup.get_text(" ", strip=True)
        # try to find "Label: value" occurrences
        for label, regex in stats_labels.items():
            m = re.search(rf"{label}\s*[:\-]?\s*([0-9\.,Kk%]+)", page_text)
            if m:
                stats[label.lower()] = m.group(1).strip()
            else:
                # fallback search for patterns like "21.4K Backlogs" or "Backlogs 21.4K"
                m2 = re.search(rf"([0-9\.,Kk%]+)\s+{regex}", page_text)
                if m2:
                    stats[label.lower()] = m2.group(1).strip()
                else:
                    m3 = re.search(rf"{regex}\s+([0-9\.,Kk%]+)", page_text)
                    if m3:
                        stats[label.lower()] = m3.group(1).strip()
        data["stats"] = stats
    except Exception:
        data["stats"] = {}

    # Raw excerpt fallback
    try:
        txt = soup.get_text("\n", strip=True)
        data["raw_excerpt"] = txt[:1500]
    except Exception:
        data["raw_excerpt"] = None

    return data


# =============================================================
# Parsers / Helpers for times & bars
# =============================================================
def parse_hours_to_number(hours_str: Optional[str]) -> Optional[float]:
    if not hours_str:
        return None
    s = str(hours_str).strip()
    s = s.replace("½", " 1/2 ").replace("–", "-").replace("—", "-")
    m = re.search(r"(\d{1,4}(?:[.,]\d+)?(?:\s*\d+/\d+)?|\d+/\d+)", s)
    if not m:
        return None
    token = m.group(0).strip()
    try:
        token_clean = token.replace(",", ".")
        if "/" in token_clean and " " in token_clean:
            parts = token_clean.split()
            whole = float(parts[0])
            frac = float(Fraction(parts[1]))
            return whole + frac
        if "/" in token_clean:
            return float(Fraction(token_clean))
        return float(token_clean)
    except Exception:
        try:
            mm = re.search(r"\d+(\.\d+)?", s)
            if mm:
                return float(mm.group(0))
        except Exception:
            return None
    return None


def build_progress_bar(values: Dict[str, Optional[float]], labels_map: Dict[str, str], width: int = 24) -> List[str]:
    nums = {k: (None if values.get(k) is None else float(values.get(k))) for k in ["main", "main_extra", "completionist"]}
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
        ratio = min(val / maxv, 1.0)
        filled = int(round(ratio * width))
        empty = width - filled
        bar = "█" * filled + "░" * empty
        lines.append(f"{label}: [{bar}] {val:g}h")
    return lines


# =============================================================
# UI COMPONENTS (buttons & views)
# =============================================================
class OptionButton(ui.Button):
    def __init__(self, label: str, index: int):
        super().__init__(label=safe_truncate(label, 80), style=discord.ButtonStyle.secondary, emoji=EMO["choice"], custom_id=f"hltb_opt_{index}")
        self.index = index
        self.clicked = False

    async def callback(self, interaction: discord.Interaction):
        self.clicked = True
        if isinstance(self.view, OptionSelectionView):
            self.view.chosen_index = self.index
        await interaction.response.defer()
        self.view.stop()


class OptionSelectionView(ui.View):
    def __init__(self, results: List[Any], timeout: int = 30):
        super().__init__(timeout=timeout)
        self.results = results
        self.chosen_index: Optional[int] = None
        for i, r in enumerate(results[:MAX_OPTIONS_BUTTONS]):
            label = getattr(r, "game_name", "Unknown")
            btn = OptionButton(label=label, index=i)
            self.add_item(btn)


class DescriptionButton(ui.Button):
    def __init__(self):
        super().__init__(label="Description", style=discord.ButtonStyle.primary, emoji=EMO["desc"])
        self.clicked = False

    async def callback(self, interaction: discord.Interaction):
        self.clicked = True
        await interaction.response.defer()
        self.view.stop()


class ReturnMainButton(ui.Button):
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


class StoreButton(ui.Button):
    def __init__(self, label: str, url: str):
        super().__init__(label=label, style=discord.ButtonStyle.link, url=url)


class RandomButton(ui.Button):
    def __init__(self):
        super().__init__(label="Random", style=discord.ButtonStyle.secondary, emoji=EMO["random"])
        self.clicked = False

    async def callback(self, interaction: discord.Interaction):
        self.clicked = True
        await interaction.response.defer()
        self.view.stop()


# =============================================================
# MAIN COG
# =============================================================
class HLTBCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.cache = CacheDB()
        self.http = aiohttp.ClientSession(headers=HEADERS)
        self.mem_cache: Dict[int, Tuple[int, Dict[str, Any]]] = {}

    async def cog_load(self):
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
        results = await h.async_search(query)
        if not results:
            return []
        results = sorted(results, key=lambda r: getattr(r, "similarity", 0), reverse=True)
        return results

    async def fetch_and_parse_game(self, game_id: int) -> Dict[str, Any]:
        now = now_ts()
        mem = self.mem_cache.get(game_id)
        if mem:
            ts, parsed = mem
            if now - ts < MEM_CACHE_TTL:
                return parsed
        cache_key = f"game_parsed:{game_id}"
        cached = await self.cache.get(cache_key)
        if cached:
            ts = cached["timestamp"]
            if now - ts < CACHE_TTL_SECONDS:
                parsed = cached["value"]
                self.mem_cache[game_id] = (now, parsed)
                return parsed
        urls = [f"{HLTB_BASE}/game/{game_id}", f"{HLTB_BASE}/game?id={game_id}"]
        last_exc = None
        for url in urls:
            try:
                text = await fetch_text(self.http, url)
                parsed = parse_hltb_game_page(text)
                parsed["_source_url"] = url
                parsed["_fetched_at"] = now
                self.mem_cache[game_id] = (now, parsed)
                await self.cache.set(cache_key, parsed)
                return parsed
            except Exception as exc:
                last_exc = exc
                continue
        raise last_exc or RuntimeError("Failed to fetch game page")

    def build_game_stats_field(self, stats: Dict[str, Any]) -> Optional[str]:
        # Build a 2-column aligned text block (if any stats exist)
        if not stats:
            return None
        # normalize keys
        mapping = {
            "playing": "🕹️ Playing",
            "backlogs": "🕒 Backlogs",
            "replays": "🔁 Replays",
            "retired": "🚫 Retired",
            "rating": "⭐ Rating",
            "beat": "🏁 Beat",
        }
        left = []
        right = []
        keys_order = ["playing", "backlogs", "replays", "retired", "rating", "beat"]
        # create pairs
        pairs = []
        vals = []
        for k in keys_order:
            if k in stats:
                v = stats[k]
                pairs.append((mapping.get(k, k.title()), v))
        if not pairs:
            return None
        # format into rows of two columns
        rows = []
        for i in range(0, len(pairs), 2):
            left = f"{pairs[i][0]}: {pairs[i][1]}"
            right = ""
            if i + 1 < len(pairs):
                right = f"{pairs[i+1][0]}: {pairs[i+1][1]}"
            # pad left to fixed width for mono-like look
            rows.append(f"{left:<30} {right}")
        return "\n".join(rows)

    def build_summary_embed(self, api_obj, parsed, requester):
        """Build the main summary embed for a game."""
        title = getattr(api_obj, "game_name", parsed.get("title", "Unknown"))
        url = parsed.get("_source_url", HLTB_BASE)
        image = parsed.get("image")

        e = discord.Embed(
            title=f"✨ {title}",
            url=url,
            color=discord.Color.from_str("#0A0C12")
        )
        if image:
            e.set_thumbnail(url=image)

        # Platforms
        pfs = ", ".join(getattr(api_obj, "profile_platforms", []) or [])
        if pfs:
            e.description = f"💻 **Platforms:** {pfs}\n"

        # Full description (not truncated)
        if parsed.get("description"):
            e.description = (e.description or "") + f"\n📘 **Description:**\n{parsed['description']}\n"

        # Estimated times
        times = parsed.get("time_estimates", {})
        if times:
            lines = []
            label = {
                "main": "🕐 Main Story",
                "main_extra": "🎯 Main + Extra",
                "completionist": "🏆 Completionist",
                "solo": "⚔️ Solo",
                "coop": "🤝 Co-op",
            }
            for k, v in times.items():
                lines.append(f"{label.get(k, k.title())}: {v}")
            e.add_field(name="⏱️ Estimated Times", value="\n".join(lines), inline=False)

        # Genres / Developer / Publisher
        genres = parsed.get("genres")
        if genres:
            e.add_field(name="📂 Genres", value=", ".join(genres), inline=False)
        for k in ("Developer", "Publisher"):
            if k in parsed.get("details", {}):
                e.add_field(name=f"👨‍💻 {k}", value=parsed['details'][k], inline=True)

        # Release dates
        rd = parsed.get("release_dates", {})
        if rd:
            val = []
            if "NA" in rd: val.append(f"🇺🇸 **NA:** {rd['NA']}")
            if "EU" in rd: val.append(f"🇪🇺 **EU:** {rd['EU']}")
            if "JP" in rd: val.append(f"🇯🇵 **JP:** {rd['JP']}")
            if parsed.get("updated"): val.append(f"🕓 **Updated:** {parsed['updated']}")
            e.add_field(name="🌍 Release Dates", value="\n".join(val), inline=False)

        # Stats
        st = parsed.get("stats", {})
        if st:
            rows = []
            pairs = [
                ("🕹️ Playing", st.get("playing")),
                ("🕒 Backlogs", st.get("backlogs")),
                ("🔁 Replays", st.get("replays")),
                ("🚫 Retired", st.get("retired")),
                ("⭐ Rating",  st.get("rating")),
                ("🏁 Beat",    st.get("beat")),
            ]
            line = []
            for i,(k,v) in enumerate(pairs):
                if not v: continue
                line.append(f"{k}: {v}")
                if len(line)==2:
                    rows.append("     ".join(line))
                    line=[]
            if line: rows.append("     ".join(line))
            e.add_field(name="📊 Game Stats", value="\n".join(rows), inline=False)

        e.set_footer(text=f"🌌 Requested by {requester.display_name} • Data from HowLongToBeat.com")
        return e

    def build_description_embeds(self, title: str, parsed: Dict[str, Any], requester: discord.User) -> List[discord.Embed]:
        """Build embeds for full description display."""
        desc_text = parsed.get("description") or "No description available."
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

    def detect_store_buttons(self, stores: dict, hltb_url: str) -> list:
        """Return link buttons for any detected store plus HowLongToBeat link."""
        buttons = []

        def add(label, emoji, url):
            buttons.append(discord.ui.Button(label=label, style=discord.ButtonStyle.link, url=url, emoji=emoji))

        if "gog" in stores:
            price = stores["gog"].get("price")
            lbl = f"GOG — {price}" if price else "GOG (DRM-free)"
            add(lbl, "🟣", stores["gog"]["url"])

        if "steam" in stores:
            price = stores["steam"].get("price")
            lbl = f"Steam — {price}" if price else "Steam"
            add(lbl, "🔵", stores["steam"]["url"])

        if "epic" in stores:
            price = stores["epic"].get("price")
            lbl = f"Epic — {price}" if price else "Epic"
            add(lbl, "🟥", stores["epic"]["url"])

        add("Open on HLTB", "🔗", hltb_url)
        return buttons

    # =============================================================
    # Slash command
    # =============================================================
    @app_commands.command(name="hltb", description="⏳ Look up a game's HowLongToBeat profile & times.")
    @app_commands.describe(game="Full or partial game name to search for.")
    @cooldown_per_user(USER_COOLDOWN_SECONDS)
    async def hltb(self, interaction: discord.Interaction, game: str):
        await interaction.response.defer(thinking=True)

        try:
            results = await self.search_api(game)
        except Exception as exc:
            await interaction.followup.send(f"{EMO['error']} Search failed: `{exc}`", ephemeral=True)
            return

        if not results:
            await interaction.followup.send(f"{EMO['error']} No results found for **{game}**.", ephemeral=True)
            return

        chosen_api_obj = None
        if len(results) > 1:
            preview_embed = discord.Embed(title=f"{EMO['search']} Multiple matches found", description=f"Click the button matching the correct game for **{game}** (you have 30s).", color=COLOR_PRIMARY)
            preview_lines = []
            for i, r in enumerate(results[:MAX_OPTIONS_BUTTONS]):
                pfs = ", ".join(getattr(r, "profile_platforms", []) or [])
                preview_lines.append(f"**{i+1}.** {safe_truncate(r.game_name, 80)} — {pfs}")
            if preview_lines:
                preview_embed.add_field(name="Top matches", value="\n".join(preview_lines), inline=False)

            opt_view = OptionSelectionView(results, timeout=30)
            prompt_msg = await interaction.followup.send(embed=preview_embed, view=opt_view)
            await opt_view.wait()

            if opt_view.chosen_index is None:
                try:
                    await prompt_msg.edit(content=f"{EMO['timeout']} Selection timed out. Try again.", embed=None, view=None)
                    await asyncio.sleep(2)
                    await prompt_msg.delete()
                except Exception:
                    pass
                return

            chosen_api_obj = results[opt_view.chosen_index]
            try:
                await prompt_msg.delete()
            except Exception:
                try:
                    await prompt_msg.edit(embed=None, view=None, content=None)
                except Exception:
                    pass
        else:
            chosen_api_obj = results[0]

        game_id = getattr(chosen_api_obj, "game_id", None)
        title = getattr(chosen_api_obj, "game_name", "Unknown")

        api_img = getattr(chosen_api_obj, "game_image_url", None)
        platforms = getattr(chosen_api_obj, "profile_platforms", []) or []
        hltb_url = f"{HLTB_BASE}/game/{game_id}" if game_id else HLTB_BASE

        parsed = {}
        try:
            if game_id:
                parsed = await self.fetch_and_parse_game(game_id)
            else:
                parsed = {"title": title, "description": None, "genres": [], "details": {}, "time_estimates": {}, "playstyles": {}, "reviews":[], "image": api_img, "_source_url": hltb_url, "raw_excerpt": "", "stores": {}, "stats": {}, "release_dates": {}, "updated": None}
        except Exception:
            parsed = {"title": title, "description": None, "genres": [], "details": {}, "time_estimates": {}, "playstyles": {}, "reviews":[], "image": api_img, "_source_url": hltb_url, "raw_excerpt": "", "stores": {}, "stats": {}, "release_dates": {}, "updated": None}

        # build summary + view
        summary_embed = self.build_summary_embed(chosen_api_obj, parsed, interaction.user)
        main_view = ui.View(timeout=300)

        full_desc = parsed.get("description") or ""
        desc_btn = None
        if full_desc:
            if len(full_desc) > 4000:
                preview_text = safe_truncate(full_desc, 1800)
                summary_embed.description = (summary_embed.description or "") + f"\n\n{safe_truncate(preview_text, 1500)}"
                desc_btn = DescriptionButton()
                main_view.add_item(desc_btn)
            else:
                summary_embed.add_field(name=f"{EMO['desc']} Short Description", value=safe_truncate(full_desc, 1024), inline=False)

        rand_button = RandomButton()
        main_view.add_item(rand_button)

        # detect stores and add store buttons if present
        store_buttons = self.detect_store_buttons(parsed.get("stores", {}), parsed.get("_source_url", HLTB_BASE))
        for btn in store_buttons:
            main_view.add_item(btn)

        # Send the summary embed and wait for interactions
        summary_message = await interaction.followup.send(embed=summary_embed, view=main_view)
        await main_view.wait()

        # Description flow
        if desc_btn and desc_btn.clicked:
            desc_embeds = self.build_description_embeds(title, parsed, interaction.user)
            dv = ui.View(timeout=300)
            rb = ReturnMainButton()
            dv.add_item(rb)
            # add store buttons & HLTB link
            for b in store_buttons:
                dv.add_item(b)
            dv.add_item(OpenHLTBButton(parsed.get("_source_url", hltb_url)))
            try:
                first_batch = desc_embeds[:10]
                await summary_message.edit(embeds=first_batch, view=dv, content=None)
                if len(desc_embeds) > 10:
                    for more in range(10, len(desc_embeds)):
                        await interaction.followup.send(embed=desc_embeds[more])
                await dv.wait()
                if rb.clicked:
                    await summary_message.edit(embed=summary_embed, view=main_view)
                    rb.clicked = False
                    for child in main_view.children:
                        if isinstance(child, DescriptionButton):
                            child.clicked = False
                    return
                else:
                    await summary_message.edit(view=None)
                    return
            except Exception:
                try:
                    for e in desc_embeds:
                        await interaction.followup.send(embed=e)
                except Exception:
                    pass
                return

        # Random flow
        if any(isinstance(i, RandomButton) and i.clicked for i in main_view.children):
            idx = random.randint(0, min(len(results) - 1, MAX_OPTIONS_BUTTONS - 1))
            random_obj = results[idx]
            new_id = getattr(random_obj, "game_id", None)
            new_title = getattr(random_obj, "game_name", "Unknown")
            new_img = getattr(random_obj, "game_image_url", None)
            new_url = f"{HLTB_BASE}/game/{new_id}" if new_id else HLTB_BASE
            try:
                new_parsed = await self.fetch_and_parse_game(new_id) if new_id else {"title": new_title, "image": new_img, "_source_url": new_url, "description": None, "genres": [], "details": {}, "time_estimates": {}, "playstyles": {}, "reviews":[], "stores": {}, "stats": {}}
            except Exception:
                new_parsed = {"title": new_title, "image": new_img, "_source_url": new_url, "description": None, "genres": [], "details": {}, "time_estimates": {}, "playstyles": {}, "reviews":[], "stores": {}, "stats": {}}
            new_summary = self.build_summary_embed(random_obj, new_parsed, interaction.user)
            new_view = ui.View(timeout=180)
            if new_parsed.get("description") and len(new_parsed.get("description", "")) > 4000:
                new_view.add_item(DescriptionButton())
            new_stores = new_parsed.get("stores", {}) or {}
            new_store_buttons = self.detect_store_buttons(new_stores, new_parsed.get("_source_url", new_url))
            for b in new_store_buttons:
                new_view.add_item(b)
            new_view.add_item(OpenHLTBButton(new_parsed.get("_source_url", new_url)))
            await summary_message.edit(embed=new_summary, view=new_view)
            return

        try:
            final_view = ui.View()
            final_view.add_item(OpenHLTBButton(parsed.get("_source_url", hltb_url)))
            await summary_message.edit(content="No action selected. Use the link to open the HowLongToBeat page.", view=final_view)
        except Exception:
            pass


# Setup
async def setup(bot: commands.Bot):
    await bot.add_cog(HLTBCog(bot))
