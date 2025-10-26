# cogs/hltb.py
# =============================================================
# /hltb single-command
# - Searches HowLongToBeat with howlongtobeatpy
# - Scrapes https://howlongtobeat.com/game/<id> for full details
# - Dropdowns for selecting game and viewing sections
# - "Open on HLTB" link button
# =============================================================

import asyncio
import random
import re
from functools import lru_cache

import aiohttp
import discord
from bs4 import BeautifulSoup
from discord import app_commands, ui
from discord.ext import commands
from howlongtobeatpy import HowLongToBeat

# -----------------------
# Theme & Emoji palette
# -----------------------
COLOR_THEME = discord.Color.from_rgb(28, 37, 51)   # dark slate
ACCENT_COLOR = discord.Color.from_rgb(98, 114, 164)  # subtle accent
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
}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; DiscordBot/1.0; +https://github.com/)"
}

HLTB_BASE = "https://howlongtobeat.com"


# -----------------------
# Helper: scrape page
# -----------------------
async def fetch_page(session: aiohttp.ClientSession, url: str) -> str:
    async with session.get(url, headers=HEADERS, timeout=20) as resp:
        resp.raise_for_status()
        return await resp.text()


def parse_game_page(html: str) -> dict:
    """
    Attempt to parse the HLTB game page for:
    - description
    - genres
    - developers/publishers
    - release date / original_release
    - metadata table (time estimates)
    - any other stats visible
    Returns a dict; fields may be None if not found.
    Parsing is defensive: site changes will be tolerated.
    """
    soup = BeautifulSoup(html, "lxml")

    data = {
        "title": None,
        "description": None,
        "genres": [],
        "details": {},     # key -> value mapping for side labels (e.g., developer, publisher)
        "time_estimates": {},  # main, main_extra, completionist, etc.
        "image": None,
        "raw_html_excerpt": None,
    }

    # Title
    h1 = soup.find("h1")
    if h1 and h1.text.strip():
        data["title"] = h1.text.strip()
    else:
        og_title = soup.find("meta", property="og:title")
        if og_title and og_title.get("content"):
            data["title"] = og_title["content"]

    # Image (thumbnail)
    og_img = soup.find("meta", property="og:image")
    if og_img and og_img.get("content"):
        data["image"] = og_img["content"]

    # Description: look for description block (common HLTB layout uses 'profile'/'game_profile' or 'profile' p tags)
    desc = None
    # Try dedicated description div
    desc_selectors = [
        {"name": "div", "attrs": {"class": re.compile(r"(game_description|profile|game_profile)", re.I)}},
        {"name": "p", "attrs": {"class": re.compile(r"game_description|profile", re.I)}},
    ]
    for sel in desc_selectors:
        block = soup.find(sel["name"], sel.get("attrs"))
        if block and block.text.strip():
            desc = block.get_text(separator="\n").strip()
            break

    # fallback: meta description
    if not desc:
        meta_desc = soup.find("meta", attrs={"name": "description"})
        if meta_desc and meta_desc.get("content"):
            desc = meta_desc["content"].strip()

    data["description"] = desc

    # Genres and other chip-like labels (HLTB sometimes uses "profile_short" or "profile" with small anchor tags)
    try:
        # look for small detail list; many HLTB pages put the small metadata at .profile_small_box or similar
        small_boxes = soup.select(".profile .profile_links a, .profile_small_box a, .game_profile .details a")
        for a in small_boxes:
            text = a.get_text(strip=True)
            if text and text.lower() not in ("view",):
                data["genres"].append(text)
        # unique
        data["genres"] = list(dict.fromkeys([g for g in data["genres"] if g]))
    except Exception:
        data["genres"] = data.get("genres", [])

    # Details table: look for rows like "Developer:", "Publisher:", "Release Date:"
    # Many HLTB pages have a 'profile' or 'profile_info' area with spans/strong labels.
    try:
        detail_candidates = soup.select(".profile .profile_info, .game_profile .profile_info, .profile .search_list_details")
        found = False
        for block in detail_candidates:
            # find rows/labels inside
            rows = block.find_all(["div", "li", "p"])
            for r in rows:
                text = r.get_text(" ", strip=True)
                if ":" in text:
                    parts = text.split(":", 1)
                    key = parts[0].strip()
                    val = parts[1].strip()
                    if key and val:
                        data["details"][key] = val
                        found = True
        # Another fallback: a 'list' of stats under a class 'search_list_item_block' etc.
        if not found:
            table_rows = soup.select(".search_list_item_block .search_list_item_li, .search_list_details")
            for tr in table_rows:
                text = tr.get_text(" ", strip=True)
                if ":" in text:
                    k, v = text.split(":", 1)
                    data["details"][k.strip()] = v.strip()
    except Exception:
        pass

    # Time estimates parsing: the site prints times in boxes — attempt to catch numeric estimates
    try:
        time_labels = {
            "Main Story": "main",
            "Main + Extra": "main_extra",
            "Completionist": "completionist",
            "Solo": "solo",
            "Co-op": "coop",
        }
        # search for any element containing known labels
        for label, slug in time_labels.items():
            el = soup.find(string=re.compile(re.escape(label), re.I))
            if el:
                # get nearby number by finding parent and searching for a number + " Hours"
                parent = el.parent
                if parent:
                    nums = parent.find_next(string=re.compile(r"[\d]{1,4}\.?[\d]*\s*Hours", re.I))
                    if nums:
                        data["time_estimates"][slug] = nums.strip()
                    else:
                        # try to find numeric spans
                        num_span = parent.find_next(["span", "div"], string=re.compile(r"[\d]{1,4}\.?[\d]*"))
                        if num_span:
                            data["time_estimates"][slug] = num_span.text.strip()
    except Exception:
        pass

    # Raw excerpt fallback (small portion to show if parsing fails)
    data["raw_html_excerpt"] = soup.get_text(separator="\n")[:1000]

    return data


# -----------------------
# LRU cache wrapper around network fetch+parse
# -----------------------
@lru_cache(maxsize=256)
def cached_parse(html_text: str):
    return parse_game_page(html_text)


async def get_game_details(game_id: int) -> dict:
    """
    Fetch and parse the howlongtobeat.com game page.
    Uses aiohttp, returns a dict of parsed data.
    """
    url = f"{HLTB_BASE}/game?id={game_id}" if "?" in HLTB_BASE else f"{HLTB_BASE}/game/{game_id}"
    # Many HLTB game page URLs are either /game?id=NNN or /game/NNN depending on site routing.
    # We'll try both forms; prefer canonical /game/{id} first then fallback.
    possible_urls = [
        f"{HLTB_BASE}/game/{game_id}",
        f"{HLTB_BASE}/game?id={game_id}",
    ]
    async with aiohttp.ClientSession() as session:
        last_exc = None
        for u in possible_urls:
            try:
                html = await fetch_page(session, u)
                parsed = cached_parse(html)  # uses lru_cache internally (keyed on html)
                # attach canonical url we used
                parsed["_source_url"] = u
                return parsed
            except Exception as exc:
                last_exc = exc
                continue
        # if both failed, raise the last
        raise last_exc if last_exc else RuntimeError("Failed to fetch game page")


# -----------------------
# UI Components: Game selection + section selection + open button
# -----------------------
class GamePickSelect(ui.Select):
    def __init__(self, results):
        options = []
        for r in results[:5]:
            title = r.game_name if len(r.game_name) <= 100 else r.game_name[:97] + "..."
            desc = f"Score: {r.similarity:.2f}"
            options.append(ui.SelectOption(label=title, description=desc, emoji=EMO["choice"]))
        super().__init__(placeholder="Choose the correct game...", min_values=1, max_values=1, options=options)
        self.results = results
        self.selected: int | None = None

    async def callback(self, interaction: discord.Interaction):
        # map selected label to result via index
        idx = self.values[0]
        # find option index
        opt_index = [opt.value for opt in self.options].index(self.values[0]) if any(opt.value for opt in self.options) else None
        # simpler: select by label matching
        for i, opt in enumerate(self.options):
            if opt.label == self.values[0]:
                self.selected = i
                break
        # stop the view; parent will read selection
        self.view.stop()
        await interaction.response.defer()


class SectionSelect(ui.Select):
    def __init__(self, sections: list[str]):
        options = []
        mapping = {
            "Overview": EMO["sparkle"],
            "Times": EMO["main"],
            "Description": EMO["desc"],
            "Details": EMO["details"],
            "Raw": EMO["stats"],
        }
        for s in sections:
            emoji = mapping.get(s, EMO["choice"])
            options.append(ui.SelectOption(label=s, description=f"View {s}", emoji=emoji))
        super().__init__(placeholder="Pick a section to view...", min_values=1, max_values=1, options=options)
        self.chosen = None

    async def callback(self, interaction: discord.Interaction):
        self.chosen = self.values[0]
        self.view.stop()
        await interaction.response.defer()


class OpenHLTBButton(ui.Button):
    def __init__(self, url: str):
        super().__init__(label="Open on HLTB", style=discord.ButtonStyle.link, url=url, emoji=EMO["open"])


# -----------------------
# Main Cog
# -----------------------
class HLTBCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # small in-memory cache to avoid repeated network on same id in quick succession
        self._mini_cache: dict[int, dict] = {}

    async def search_hltb(self, query: str):
        """Wrap howlongtobeatpy async search"""
        h = HowLongToBeat()
        results = await h.async_search(query)
        return sorted(results, key=lambda r: r.similarity, reverse=True)

    def format_times_field(self, raw: dict, api_obj) -> str:
        """
        Build a clean times block using both the scraped raw (if any) and the API object fields.
        """
        lines = []
        # prefer API numeric fields if present
        try:
            def fmt(v):
                return f"{v} hrs" if (v is not None and str(v).strip() != "") else "N/A"
            # API attributes: main_story, main_extra, completionist
            if hasattr(api_obj, "main_story"):
                lines.append(f"{EMO['main']} **Main:** {fmt(api_obj.main_story)}")
            if hasattr(api_obj, "main_extra"):
                lines.append(f"{EMO['extra']} **Main + Extra:** {fmt(api_obj.main_extra)}")
            if hasattr(api_obj, "completionist"):
                lines.append(f"{EMO['complete']} **Completionist:** {fmt(api_obj.completionist)}")
        except Exception:
            pass

        # fallback to scraped estimates
        for k, v in raw.get("time_estimates", {}).items():
            label = k.replace("_", " ").title()
            lines.append(f"{EMO['stats']} **{label}:** {v}")

        return "\n".join(lines) or "No time data found."

    def compact_list(self, items):
        if not items:
            return "Unknown"
        if isinstance(items, (list, tuple)):
            return ", ".join(items[:8])
        return str(items)

    # -----------------------
    # single slash command
    # -----------------------
    @app_commands.command(name="hltb", description="⏳ Look up a game's HowLongToBeat profile & times.")
    @app_commands.describe(game="Full or partial game name to search for.")
    async def hltb(self, interaction: discord.Interaction, game: str):
        await interaction.response.defer(thinking=True)
        try:
            results = await self.search_hltb(game)
        except Exception as exc:
            await interaction.followup.send(f"{EMO['error']} Search failed: {exc}")
            return

        if not results:
            await interaction.followup.send(f"{EMO['error']} No results for **{game}**.")
            return

        # If multiple results: show selection dropdown (top 5)
        chosen_result = None
        if len(results) > 1:
            view = ui.View(timeout=30)
            select = GamePickSelect(results)
            view.add_item(select)
            prompt_embed = discord.Embed(
                title=f"{EMO['search']} Select a result",
                description=f"I found multiple games matching **{game}** — pick the one you meant.",
                color=ACCENT_COLOR,
            )
            follow = await interaction.followup.send(embed=prompt_embed, view=view)
            await view.wait()
            # if view timed out or no selection
            if select.selected is None:
                await follow.edit(content=f"{EMO['timeout']} Selection timed out.", embed=None, view=None)
                return
            chosen_result = results[select.selected]
            # tidy the prompt message
            await follow.edit(embed=None, view=None, content=None)
        else:
            chosen_result = results[0]

        # Now we have a chosen_result (howlongtobeatpy result object)
        game_id = getattr(chosen_result, "game_id", None)
        title = getattr(chosen_result, "game_name", "Unknown Title")
        image = getattr(chosen_result, "game_image_url", None)
        platforms = getattr(chosen_result, "profile_platforms", []) or []
        hltb_url = f"{HLTB_BASE}/game/{game_id}" if game_id else HLTB_BASE

        # attempt to use mini cache
        parsed = None
        if game_id and game_id in self._mini_cache:
            parsed = self._mini_cache[game_id]
        else:
            # fetch + parse
            try:
                parsed = await get_game_details(game_id) if game_id else {}
            except Exception as exc:
                # parsing failed; we'll continue with best-effort using API-only data
                parsed = {"description": None, "genres": [], "details": {}, "time_estimates": {}, "image": image, "_source_url": hltb_url}
            # store in mini cache
            if game_id:
                self._mini_cache[game_id] = parsed

        # Build initial embed (summary)
        summary_embed = discord.Embed(
            title=f"{EMO['sparkle']} {title}",
            url=parsed.get("_source_url", hltb_url),
            color=COLOR_THEME,
            description=f"{EMO['platform']} Platforms: {self.compact_list(platforms)}\n\n"
                        f"{EMO['details']} Source: HowLongToBeat"
        )
        if parsed.get("image"):
            summary_embed.set_thumbnail(url=parsed["image"])
        elif image:
            summary_embed.set_thumbnail(url=image)

        # Add times (prefer API numeric fields)
        times_block = self.format_times_field(parsed, chosen_result)
        summary_embed.add_field(name="⏱️ Estimated Times", value=times_block, inline=False)

        # Genres / short details
        genres = parsed.get("genres") or []
        summary_embed.add_field(name=f"{EMO['desc']} Genres / Tags", value=self.compact_list(genres), inline=False)

        # Footer with requesting user
        summary_embed.set_footer(text=f"Requested by {interaction.user.display_name} • data from howlongtobeat.com")

        # Buttons: Open on HLTB
        buttons = ui.View()
        buttons.add_item(OpenHLTBButton(parsed.get("_source_url", hltb_url)))

        # Section selection view (dropdown) to show specific scraped details
        sections = ["Overview", "Times", "Description", "Details", "Raw"]
        sec_view = ui.View(timeout=60)
        sec_select = SectionSelect(sections)
        sec_view.add_item(sec_select)
        sec_view.add_item(OpenHLTBButton(parsed.get("_source_url", hltb_url)))

        # Send summary with section chooser
        summary_msg = await interaction.followup.send(embed=summary_embed, view=sec_view)

        # Wait for section selection
        await sec_view.wait()
        if sec_select.chosen is None:
            # timeout -> do nothing further
            await summary_msg.edit(content=f"{EMO['timeout']} Section selection timed out. Use the button to open the HLTB page.", view=None)
            return

        # Build embed for selected section
        chosen_section = sec_select.chosen
        content_embed = discord.Embed(color=ACCENT_COLOR, title=f"{EMO['choice']} {chosen_section} — {title}", url=parsed.get("_source_url", hltb_url))
        content_embed.set_thumbnail(url=parsed.get("image", image))

        if chosen_section == "Overview":
            # Combine short description + key details
            short_desc = parsed.get("description") or "No description available."
            details = parsed.get("details") or {}
            overview_text = (short_desc[:1000] + "...") if len(short_desc or "") > 1000 else short_desc
            content_embed.description = overview_text
            # add a details mini-table if present
            if details:
                for k, v in list(details.items())[:6]:
                    content_embed.add_field(name=k, value=v, inline=True)

        elif chosen_section == "Times":
            times_block = self.format_times_field(parsed, chosen_result)
            content_embed.description = times_block

        elif chosen_section == "Description":
            desc_long = parsed.get("description") or "No description available."
            # break into pages if very long (show first 2048 chars)
            content_embed.description = desc_long[:2048] if len(desc_long) > 2048 else desc_long

        elif chosen_section == "Details":
            details = parsed.get("details") or {}
            if not details:
                content_embed.description = "No detailed metadata scraped."
            else:
                for k, v in details.items():
                    content_embed.add_field(name=k, value=v[:1024], inline=False)

        elif chosen_section == "Raw":
            # Show a sanitized excerpt of the page text (debug style)
            excerpt = parsed.get("raw_html_excerpt", "No raw excerpt available.")
            content_embed.description = f"```\n{excerpt[:1000]}\n```"

        # Send the chosen section (with an Open button)
        final_view = ui.View()
        final_view.add_item(OpenHLTBButton(parsed.get("_source_url", hltb_url)))

        await summary_msg.edit(embed=content_embed, view=final_view)


# Cog setup
async def setup(bot: commands.Bot):
    await bot.add_cog(HLTBCog(bot))
