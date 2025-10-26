# cogs/hltb.py
# =============================================================
# /hltb - Beautiful Interactive HowLongToBeat Cog
# - Single command: /hltb
# - Async howlongtobeatpy search
# - Scrapes howlongtobeat.com for rich metadata
# - Dropdowns for selection and section views
# - Buttons: Open on HLTB (link), 📜 Description (primary blue), 🎲 Random
# - Persistent SQLite cache (disk-backed) to reduce scraping & API calls
# - Defensive parsing, error handling, and rate-limiting
# =============================================================

import asyncio
import aiosqlite
import json
import math
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
CACHE_TTL_SECONDS = 60 * 60 * 24 * 7  # 7 days
USER_COOLDOWN_SECONDS = 3  # short per-user cooldown to prevent accidental spam
MAX_SELECT_OPTIONS = 5  # how many search results to show in dropdown
REQUEST_TIMEOUT = 20  # seconds for HTTP requests
HLTB_BASE = "https://howlongtobeat.com"

# Visual theme
COLOR_PRIMARY = discord.Color.from_rgb(11, 84, 166)      # deep blue (for primary buttons / accents)
COLOR_ACCENT = discord.Color.from_rgb(98, 114, 164)     # subtle accent
COLOR_BACKGROUND = discord.Color.from_rgb(24, 26, 31)   # embed base color (if used)
EMO = {
    "search": "🔎",
    "open": "🔗",
    "main": "🕐",
    "extra": "🎯",
    "complete": "🏆",
    "platform": "💻",
    "desc": "📜",
    "details": "🧾",
    "stats": "📊",
    "error": "❌",
    "sparkle": "✨",
    "choice": "🎮",
    "timeout": "⏳",
    "random": "🎲",
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
    if v is None:
        return "N/A"
    try:
        # accept floats/ints and strings
        if isinstance(v, (int, float)):
            return f"{v} hrs"
        s = str(v).strip()
        if not s:
            return "N/A"
        # already often in "xx Hours" or "xx hrs"
        return s
    except Exception:
        return "N/A"


def safe_truncate(text: Optional[str], length: int = 1024) -> str:
    if not text:
        return ""
    return text if len(text) <= length else text[: length - 3] + "..."


def attach_if_not_none(embed: discord.Embed, name: str, value: Optional[str], inline: bool = False):
    if value and value.strip():
        embed.add_field(name=name, value=value, inline=inline)


def cooldown_per_user(seconds: int):
    """
    Simple per-user cooldown decorator for command handlers inside cogs.
    Usage: @cooldown_per_user(3)
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
# DATABASE: Simple SQLite Cache
# -----------------------------
class CacheDB:
    """
    Simple async SQLite wrapper to store cached parsed pages and API results.
    Schema:
      - cache(key TEXT PRIMARY KEY, timestamp INTEGER, value TEXT)
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

    async def invalidate(self, key: str):
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
    Defensive parser for HLTB game pages. Returns a dict with keys:
      - title, description, genres (list), details (dict), time_estimates (dict), image, raw_excerpt
    """
    soup = BeautifulSoup(html, "lxml")
    data: Dict[str, Any] = {
        "title": None,
        "description": None,
        "genres": [],
        "details": {},
        "time_estimates": {},
        "image": None,
        "raw_excerpt": None,
    }

    # Title: common h1 or og:title
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

    # Description: try common containers
    desc_candidates = [
        soup.find("div", class_=re.compile(r"(game_description|profile|game_profile)", re.I)),
        soup.find("div", id=re.compile(r"(game_description|profile)", re.I)),
        soup.find("meta", attrs={"name": "description"}),
    ]
    description = None
    for c in desc_candidates:
        if not c:
            continue
        if c.name == "meta":
            if c.get("content"):
                description = c["content"].strip()
                break
        else:
            txt = c.get_text("\n", strip=True)
            if txt:
                description = txt
                break
    data["description"] = description

    # Genres / chips: search for links or small tags in profile area
    try:
        chips = soup.select(".profile .search_list_details a, .profile .profile_links a, .game_profile .profile_links a, .search_list_tidbit a")
        for a in chips:
            t = a.get_text(strip=True)
            if t:
                data["genres"].append(t)
        # unique
        data["genres"] = list(dict.fromkeys(data["genres"]))
    except Exception:
        data["genres"] = data.get("genres", [])

    # Details: developer, publisher, released, etc.
    try:
        detail_blocks = soup.select(".profile .profile_info, .game_profile .profile_info, .profile .search_list_details")
        for block in detail_blocks:
            items = block.find_all(["div", "li", "p", "span"])
            for item in items:
                text = item.get_text(" ", strip=True)
                if ":" in text:
                    k, v = text.split(":", 1)
                    k = k.strip()
                    v = v.strip()
                    if k and v:
                        data["details"][k] = v
    except Exception:
        pass

    # Time estimates - attempt to parse numbers and labels near known labels
    try:
        # common labels on the page
        labels = {
            "Main Story": "main",
            "Main + Extra": "main_extra",
            "Completionist": "completionist",
            "Solo": "solo",
            "Co-op": "coop",
        }
        for label_text, key in labels.items():
            # find an element that contains label_text
            el = soup.find(string=re.compile(re.escape(label_text), re.I))
            if el:
                # try parent siblings for numbers
                parent = el.parent
                if parent:
                    # search for nearby pattern like '12½ Hours' or '12 Hours'
                    nearby = parent.find_next(string=re.compile(r"\d{1,4}[\d\.\½\�]*\s*(Hours|hrs|h)?", re.I))
                    if nearby:
                        data["time_estimates"][key] = nearby.strip()
                    else:
                        # search in parent text
                        text_block = parent.get_text(" ", strip=True)
                        found = re.search(r"(\d{1,4}[\d\.\½\�]*)\s*(Hours|hrs|h)?", text_block)
                        if found:
                            data["time_estimates"][key] = found.group(0)
    except Exception:
        pass

    # Raw excerpt: a short chunk of page text
    try:
        txt = soup.get_text("\n", strip=True)
        data["raw_excerpt"] = txt[:1200]
    except Exception:
        data["raw_excerpt"] = None

    return data


# -----------------------------
# UI COMPONENTS
# -----------------------------
class ResultSelect(ui.Select):
    """
    Dropdown to pick one of the search results.
    The options' value is the index string (0..n) to ease matching.
    """

    def __init__(self, results: List[Any]):
        options = []
        for i, r in enumerate(results[:MAX_SELECT_OPTIONS]):
            label = (r.game_name[:95] + "...") if len(r.game_name) > 95 else r.game_name
            desc = f"Score: {getattr(r, 'similarity', 0):.2f} • Platforms: {', '.join(getattr(r, 'profile_platforms', []) or [])[:50]}"
            options.append(ui.SelectOption(label=label, description=desc[:100], value=str(i), emoji=EMO["choice"]))
        super().__init__(placeholder="Select the matching game...", min_values=1, max_values=1, options=options)
        self.results = results
        self.chosen_index: Optional[int] = None

    async def callback(self, interaction: discord.Interaction):
        try:
            idx = int(self.values[0])
            self.chosen_index = idx
        except Exception:
            self.chosen_index = None
        # stop and let caller continue
        self.view.stop()
        await interaction.response.defer()


class SectionSelect(ui.Select):
    """
    Dropdown to choose which section to view: Overview / Times / Description / Details / Raw
    """

    def __init__(self):
        sections = [
            ("Overview", EMO["sparkle"], "Summary overview with key fields"),
            ("Times", EMO["main"], "Show time estimates"),
            ("Description", EMO["desc"], "Long game description"),
            ("Details", EMO["details"], "Developer / Publisher / Release, etc."),
            ("Raw", EMO["stats"], "Sanitized raw excerpt for debugging"),
        ]
        options = [ui.SelectOption(label=s[0], description=s[2], emoji=s[1]) for s in sections]
        super().__init__(placeholder="Choose section to view...", min_values=1, max_values=1, options=options)
        self.chosen: Optional[str] = None

    async def callback(self, interaction: discord.Interaction):
        self.chosen = self.values[0]
        self.view.stop()
        await interaction.response.defer()


class OpenHLTBButton(ui.Button):
    def __init__(self, url: str):
        super().__init__(label="Open on HLTB", style=discord.ButtonStyle.link, url=url, emoji=EMO["open"])


class DescriptionButton(ui.Button):
    """
    Blue primary description button with emoji (📜 Description).
    When pressed, this will send or switch to the Description embed view.
    """

    def __init__(self):
        super().__init__(label="Description", style=discord.ButtonStyle.primary, emoji=EMO["desc"])
        self.pressed = False

    async def callback(self, interaction: discord.Interaction):
        # mark pressed; parent view handler will detect via custom_id or by replacing view.
        self.pressed = True
        # respond with a defer to avoid "This interaction failed"
        await interaction.response.defer()


class RandomButton(ui.Button):
    def __init__(self):
        super().__init__(label="Random", style=discord.ButtonStyle.secondary, emoji=EMO["random"])
        self.pressed_index: Optional[int] = None

    async def callback(self, interaction: discord.Interaction):
        # simply store that it was pressed; the parent view will handle the randomization by checking the view state
        self.pressed_index = random.randint(0, 4)  # placeholder; will be overwritten
        await interaction.response.defer()


# -----------------------------
# MAIN COG
# -----------------------------
class HLTBCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.cache = CacheDB()
        self.http_session = aiohttp.ClientSession(headers=HEADERS)
        # in-memory short cache for quick reuse while bot runs (id -> parsed)
        self.mem_cache: Dict[int, Tuple[int, Dict[str, Any]]] = {}  # game_id -> (ts, parsed)
        # ensure DB init in background
        bot.loop.create_task(self.cache.init())

    async def cog_unload(self):
        try:
            await self.http_session.close()
        except Exception:
            pass
        try:
            await self.cache.close()
        except Exception:
            pass

    async def search_api(self, query: str):
        h = HowLongToBeat()
        try:
            results = await h.async_search(query)
        except Exception as exc:
            # worst case, rethrow for calling code to handle
            raise
        # sort by similarity descending
        results = sorted(results, key=lambda r: getattr(r, "similarity", 0), reverse=True)
        return results

    async def fetch_and_parse_game(self, game_id: int) -> Dict[str, Any]:
        """
        Fetch HLTB page for game_id and parse. Use layered caching:
           1) Memory cache (self.mem_cache) with small TTL
           2) Disk cache (SQLite) with longer TTL
           3) Fetch remote & parse, then store both
        """
        now = now_ts()

        # 1) In-memory cache short-circuit
        mem = self.mem_cache.get(game_id)
        if mem:
            ts, parsed = mem
            if now - ts < 60 * 60:  # 1 hour mem cache
                return parsed

        # 2) Disk cache
        cache_key = f"game_parsed:{game_id}"
        cached = await self.cache.get(cache_key)
        if cached:
            ts = cached["timestamp"]
            if now - ts < CACHE_TTL_SECONDS:
                parsed = cached["value"]
                # repopulate mem cache
                self.mem_cache[game_id] = (now, parsed)
                return parsed

        # 3) Fetch remote
        # Try canonical /game/{id} then /game?id={id}
        urls = [f"{HLTB_BASE}/game/{game_id}", f"{HLTB_BASE}/game?id={game_id}"]
        last_exc = None
        for url in urls:
            try:
                text = await fetch_text(self.http_session, url)
                parsed = parse_hltb_game_page(text)
                parsed["_source_url"] = url
                parsed["_fetched_at"] = now
                # write to caches
                self.mem_cache[game_id] = (now, parsed)
                await self.cache.set(cache_key, parsed)
                return parsed
            except Exception as exc:
                last_exc = exc
                continue
        # if all fail, raise last exception
        raise last_exc or RuntimeError("Failed to fetch game page")

    def build_summary_embed(self, api_obj, parsed: Dict[str, Any], requester: discord.User) -> discord.Embed:
        """
        Create the main summary embed with times, thumbnails, platforms, short meta
        """
        title = getattr(api_obj, "game_name", parsed.get("title", "Unknown"))
        url = parsed.get("_source_url", f"{HLTB_BASE}/")
        image = parsed.get("image") or getattr(api_obj, "game_image_url", None)
        platforms = getattr(api_obj, "profile_platforms", []) or []

        embed = discord.Embed(
            title=f"{EMO['sparkle']} {safe_truncate(title, 256)}",
            url=url,
            color=COLOR_ACCENT,
            description=f"{EMO['platform']} Platforms: {', '.join(platforms) if platforms else 'Unknown'}\n\n"
                        f"{EMO['choice']} Search score: {getattr(api_obj, 'similarity', 0):.2f}"
        )
        if image:
            embed.set_thumbnail(url=image)

        # times (prefer API fields)
        lines = []
        if hasattr(api_obj, "main_story"):
            lines.append(f"{EMO['main']} **Main:** {format_hours(api_obj.main_story)}")
        if hasattr(api_obj, "main_extra"):
            lines.append(f"{EMO['extra']} **Main + Extra:** {format_hours(api_obj.main_extra)}")
        if hasattr(api_obj, "completionist"):
            lines.append(f"{EMO['complete']} **Completionist:** {format_hours(api_obj.completionist)}")
        if not lines:
            # fallback to scraped
            te = parsed.get("time_estimates", {})
            for k, v in te.items():
                lines.append(f"{EMO['stats']} **{k.title()}:** {v}")

        embed.add_field(name="⏱️ Estimated Times", value="\n".join(lines) if lines else "No time data available", inline=False)

        genres = parsed.get("genres") or []
        if genres:
            embed.add_field(name=f"{EMO['desc']} Genres / Tags", value=self.compact_list(genres, limit=8), inline=False)

        details = parsed.get("details") or {}
        if details:
            # show a few detail fields inline
            items = list(details.items())[:3]
            for k, v in items:
                embed.add_field(name=k, value=safe_truncate(v, 200), inline=True)

        embed.set_footer(text=f"Requested by {requester.display_name} • Data from howlongtobeat.com")
        return embed

    def compact_list(self, items: List[str], limit: int = 6) -> str:
        if not items:
            return "Unknown"
        if len(items) <= limit:
            return ", ".join(items)
        return ", ".join(items[:limit]) + f", +{len(items)-limit} more"

    # Main command
    @app_commands.command(name="hltb", description="⏳ Look up a game's HowLongToBeat profile & times.")
    @app_commands.describe(game="Full or partial game name to search for.")
    @cooldown_per_user(USER_COOLDOWN_SECONDS)
    async def hltb(self, interaction: discord.Interaction, game: str):
        """
        Single slash command handler implementing the full flow:
           1) search using howlongtobeatpy
           2) if multiple results, show a dropdown to pick
           3) fetch & parse chosen game's HLtB page (cached)
           4) show summary embed with buttons + section dropdown
           5) support Description button (blue), Random button, Open link
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

        # If multiple results -> ask to pick via dropdown
        chosen_api_obj = None
        if len(results) > 1:
            view = ui.View(timeout=30)
            select = ResultSelect(results)
            view.add_item(select)
            pick_embed = discord.Embed(
                title=f"{EMO['search']} Multiple results found",
                description=f"I found multiple matches for **{game}**. Please select the correct one from the dropdown.",
                color=COLOR_PRIMARY
            )
            # include top results preview in the embed description to make it look better
            preview_lines = []
            for i, r in enumerate(results[:MAX_SELECT_OPTIONS]):
                name = r.game_name
                sim = getattr(r, "similarity", 0)
                pfs = ", ".join(getattr(r, "profile_platforms", []) or [])
                preview_lines.append(f"**{i+1}.** {safe_truncate(name, 80)} — `{sim:.2f}` • {pfs}")
            if preview_lines:
                pick_embed.add_field(name="Top results", value="\n".join(preview_lines), inline=False)

            prompt_msg = await interaction.followup.send(embed=pick_embed, view=view)
            # wait for selection or timeout
            await view.wait()

            if select.chosen_index is None:
                # timed out or user didn't pick
                await prompt_msg.edit(content=f"{EMO['timeout']} Selection timed out. Try again.", embed=None, view=None)
                return

            chosen_api_obj = results[select.chosen_index]
            # tidy the pick message
            await prompt_msg.edit(content=None, embed=None, view=None)
        else:
            chosen_api_obj = results[0]

        # Now we have chosen_api_obj
        game_id = getattr(chosen_api_obj, "game_id", None)
        title = getattr(chosen_api_obj, "game_name", "Unknown").strip()
        img = getattr(chosen_api_obj, "game_image_url", None)
        platforms = getattr(chosen_api_obj, "profile_platforms", []) or []
        hltb_url = f"{HLTB_BASE}/game/{game_id}" if game_id else HLTB_BASE

        # Fetch parsed page (cache-aware)
        parsed = {}
        try:
            if game_id:
                parsed = await self.fetch_and_parse_game(game_id)
            else:
                parsed = {"title": title, "description": None, "genres": [], "details": {}, "time_estimates": {}, "image": img, "_source_url": hltb_url}
        except Exception:
            # fallback: best-effort from API
            parsed = {"title": title, "description": None, "genres": [], "details": {}, "time_estimates": {}, "image": img, "_source_url": hltb_url}

        # Build summary embed and view with buttons & section dropdown
        summary_embed = self.build_summary_embed(chosen_api_obj, parsed, interaction.user)

        # Compose view: Section dropdown + Description (primary) + Random + Open link
        main_view = ui.View(timeout=120)
        sec_select = SectionSelect()
        main_view.add_item(sec_select)

        # Description blue button
        desc_button = DescriptionButton()
        main_view.add_item(desc_button)

        # Random button (secondary)
        rand_button = RandomButton()
        main_view.add_item(rand_button)

        # Open HLTB link
        main_view.add_item(OpenHLTBButton(parsed.get("_source_url", hltb_url)))

        # Send the summary (with buttons)
        summary_msg = await interaction.followup.send(embed=summary_embed, view=main_view)

        # Wait for any of: sec_select chosen, desc_button pressed, rand_button pressed, or timeout
        await main_view.wait()

        # If description button pressed: show description embed/page
        if desc_button.pressed:
            # build description embed
            desc_text = parsed.get("description") or "No description available."
            desc_embed = discord.Embed(
                title=f"{EMO['desc']} Description — {title}",
                description=safe_truncate(desc_text, 4000),
                color=COLOR_PRIMARY,
                url=parsed.get("_source_url", hltb_url)
            )
            if parsed.get("image"):
                desc_embed.set_thumbnail(url=parsed.get("image"))
            desc_embed.set_footer(text=f"Requested by {interaction.user.display_name}")
            await summary_msg.edit(embed=desc_embed, view=ui.View().add_item(OpenHLTBButton(parsed.get("_source_url", hltb_url))))
            return

        # If random button pressed: pick a random result from the original results and show it
        if isinstance(rand_button.pressed_index, int) and results:
            # pick randomly from the results list (bounded by available results)
            idx = random.randint(0, min(len(results) - 1, MAX_SELECT_OPTIONS - 1))
            chosen_api_obj = results[idx]
            # refetch parsed for new choice
            game_id = getattr(chosen_api_obj, "game_id", None)
            title = getattr(chosen_api_obj, "game_name", "Unknown")
            img = getattr(chosen_api_obj, "game_image_url", None)
            hltb_url = f"{HLTB_BASE}/game/{game_id}" if game_id else HLTB_BASE
            try:
                parsed = await self.fetch_and_parse_game(game_id) if game_id else {}
            except Exception:
                parsed = {"title": title, "description": None, "genres": [], "details": {}, "time_estimates": {}, "image": img, "_source_url": hltb_url}
            # send new summary
            new_summary = self.build_summary_embed(chosen_api_obj, parsed, interaction.user)
            new_view = ui.View(timeout=120)
            new_view.add_item(SectionSelect())
            new_view.add_item(DescriptionButton())
            new_view.add_item(OpenHLTBButton(parsed.get("_source_url", hltb_url)))
            await summary_msg.edit(embed=new_summary, view=new_view)
            return

        # If section select was used
        if sec_select.chosen:
            chosen_section = sec_select.chosen
            # Build corresponding embed
            if chosen_section == "Overview":
                ov_embed = discord.Embed(
                    title=f"{EMO['sparkle']} Overview — {title}",
                    color=COLOR_ACCENT,
                    url=parsed.get("_source_url", hltb_url)
                )
                # short description if present
                short_desc = (parsed.get("description") or "")
                if short_desc:
                    ov_embed.description = safe_truncate(short_desc, 1024)
                else:
                    ov_embed.description = "No description available."
                # details (a few)
                details = parsed.get("details", {})
                if details:
                    for i, (k, v) in enumerate(details.items()):
                        if i >= 6:
                            break
                        ov_embed.add_field(name=k, value=safe_truncate(v, 256), inline=True)
                if parsed.get("image"):
                    ov_embed.set_thumbnail(url=parsed.get("image"))
                ov_embed.set_footer(text=f"Requested by {interaction.user.display_name}")
                await summary_msg.edit(embed=ov_embed, view=ui.View().add_item(OpenHLTBButton(parsed.get("_source_url", hltb_url))))
                return

            elif chosen_section == "Times":
                times_embed = discord.Embed(
                    title=f"{EMO['main']} Times — {title}",
                    url=parsed.get("_source_url", hltb_url),
                    color=COLOR_ACCENT
                )
                lines = []
                # prefer API fields first
                try:
                    api_main = getattr(chosen_api_obj, "main_story", None)
                    api_main_extra = getattr(chosen_api_obj, "main_extra", None)
                    api_comp = getattr(chosen_api_obj, "completionist", None)
                    lines.append(f"{EMO['main']} **Main:** {format_hours(api_main)}")
                    lines.append(f"{EMO['extra']} **Main + Extra:** {format_hours(api_main_extra)}")
                    lines.append(f"{EMO['complete']} **Completionist:** {format_hours(api_comp)}")
                except Exception:
                    pass
                # scraped times
                te = parsed.get("time_estimates", {})
                for k, v in te.items():
                    lines.append(f"{EMO['stats']} **{k.title()}:** {v}")
                if not lines:
                    times_embed.description = "No time data available."
                else:
                    times_embed.description = "\n".join(lines)
                times_embed.set_footer(text=f"Data may be approximate • Requested by {interaction.user.display_name}")
                await summary_msg.edit(embed=times_embed, view=ui.View().add_item(OpenHLTBButton(parsed.get("_source_url", hltb_url))))
                return

            elif chosen_section == "Description":
                desc_text = parsed.get("description") or "No description available."
                desc_embed = discord.Embed(
                    title=f"{EMO['desc']} Description — {title}",
                    description=safe_truncate(desc_text, 4000),
                    url=parsed.get("_source_url", hltb_url),
                    color=COLOR_PRIMARY
                )
                if parsed.get("image"):
                    desc_embed.set_thumbnail(url=parsed.get("image"))
                desc_embed.set_footer(text=f"Requested by {interaction.user.display_name}")
                await summary_msg.edit(embed=desc_embed, view=ui.View().add_item(OpenHLTBButton(parsed.get("_source_url", hltb_url))))
                return

            elif chosen_section == "Details":
                details = parsed.get("details") or {}
                details_embed = discord.Embed(title=f"{EMO['details']} Details — {title}", color=COLOR_ACCENT, url=parsed.get("_source_url", hltb_url))
                if not details:
                    details_embed.description = "No structured details scraped."
                else:
                    for k, v in details.items():
                        details_embed.add_field(name=k, value=safe_truncate(v, 1024), inline=False)
                details_embed.set_footer(text=f"Requested by {interaction.user.display_name}")
                await summary_msg.edit(embed=details_embed, view=ui.View().add_item(OpenHLTBButton(parsed.get("_source_url", hltb_url))))
                return

            elif chosen_section == "Raw":
                raw = parsed.get("raw_excerpt", "No raw excerpt available.")
                raw_embed = discord.Embed(title=f"{EMO['stats']} Raw Excerpt — {title}", color=COLOR_ACCENT, url=parsed.get("_source_url", hltb_url))
                raw_embed.description = f"```\n{safe_truncate(raw, 1900)}\n```"
                raw_embed.set_footer(text="Raw excerpt (sanitized).")
                await summary_msg.edit(embed=raw_embed, view=ui.View().add_item(OpenHLTBButton(parsed.get("_source_url", hltb_url))))
                return

        # fallback if nothing else happened
        await summary_msg.edit(content="No selection made. Use the buttons to open the HowLongToBeat page.", view=ui.View().add_item(OpenHLTBButton(parsed.get("_source_url", hltb_url))))

# Setup function for the cog
async def setup(bot: commands.Bot):
    await bot.add_cog(HLTBCog(bot))
