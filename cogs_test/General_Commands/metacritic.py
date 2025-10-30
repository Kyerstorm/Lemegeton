# cogs/metacritic.py
import discord
from discord import app_commands
from discord.ext import commands
import requests
from bs4 import BeautifulSoup
import aiosqlite
import asyncio
import re
import os
from datetime import datetime

DB_PATH = "data/metacritic.db"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 " \
             "(KHTML, like Gecko) Chrome/117.0 Safari/537.36"
HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept-Language": "en-US,en;q=0.9"
}

# ---------------------------
# Utility helpers
# ---------------------------

def ensure_db_path():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)

async def init_db():
    ensure_db_path()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS scores (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                platform TEXT,
                media_type TEXT NOT NULL,
                metascore INTEGER,
                user_score REAL,
                updated_at TEXT
            );
        """)
        await db.commit()

async def get_last_score(title, platform, media_type):
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT metascore, user_score, updated_at FROM scores WHERE title = ? AND platform = ? AND media_type = ? ORDER BY id DESC LIMIT 1",
            (title, platform, media_type)
        )
        row = await cursor.fetchone()
        await cursor.close()
        if row:
            return {"metascore": row[0], "user_score": row[1], "updated_at": row[2]}
    return None

async def save_score(title, platform, media_type, metascore, user_score):
    now = datetime.utcnow().isoformat()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO scores (title, platform, media_type, metascore, user_score, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
            (title, platform, media_type, metascore, user_score, now)
        )
        await db.commit()

def clamp(v, lo, hi):
    return max(lo, min(hi, v))

def percent_bar(value, max_value=100, length=12):
    """
    Return a textual bar representing value/max_value.
    Example: ███████▌── 70/100
    """
    try:
        pct = (value / max_value) if max_value else 0
    except Exception:
        pct = 0
    filled = int(round(pct * length))
    empty = length - filled
    bar = "█" * filled + "▌" * (1 if (pct * length - filled) >= 0.5 else 0) + "─" * max(0, empty - 1 if (pct * length - filled) >= 0.5 else empty)
    # If the bar has odd length issues, clamp
    return f"{bar} {int(round(pct * 100))}%"

def parse_int_from_text(text):
    if not text:
        return None
    digits = re.findall(r"\d+", text.replace(",", ""))
    if not digits:
        return None
    try:
        return int(digits[0])
    except:
        return None

def parse_float_from_text(text):
    if not text:
        return None
    # handle decimals like "8.6"
    m = re.search(r"(\d+(\.\d+)?)", text)
    if not m:
        return None
    try:
        return float(m.group(1))
    except:
        return None

def platform_icon(platform_text: str):
    if not platform_text:
        return "🕹️"
    s = platform_text.lower()
    if "ps5" in s or "playstation" in s:
        return "🎮"
    if "ps4" in s:
        return "🎮"
    if "xbox" in s:
        return "💚"
    if "switch" in s:
        return "🔀"
    if "pc" in s or "windows" in s:
        return "💻"
    if "stadia" in s:
        return "☁️"
    if "ios" in s or "android" in s or "mobile" in s:
        return "📱"
    # default
    return "🕹️"

# ---------------------------
# Scraper with multilayer fallback
# ---------------------------

def _safe_get(url, headers=HEADERS, timeout=10):
    """
    Synchronous requests call wrapped for use in async code with run_in_executor when necessary.
    """
    return requests.get(url, headers=headers, timeout=timeout)

def extract_from_detail_html(html_text):
    """
    Parse a Metacritic detail page with multiple selectors and fallback strategies.
    Returns dict or None.
    """
    soup = BeautifulSoup(html_text, "lxml")

    # Title
    title = None
    h1 = soup.find("h1")
    if h1:
        title = h1.get_text(strip=True)

    # Metascore: try several selectors / patterns
    metascore = None
    for sel in [
        ".metascore_w.xlarge.game",           # old classes
        ".metascore_w.metascore_w.xlarge",    # fallback patterns
        ".metascore_wrap .metascore",         # other patterns
        ".c-siteReviewScore",                 # new design
        ".score_value"                        # older site
    ]:
        el = soup.select_one(sel)
        if el:
            text = el.get_text(strip=True)
            metascore = parse_int_from_text(text)
            if metascore is not None:
                break

    # User score
    user_score = None
    for sel in [".userscore_wrap .metascore_w", ".c-siteUserScore", ".score_value.user", ".user_score"]:
        el = soup.select_one(sel)
        if el:
            text = el.get_text(strip=True)
            user_score = parse_float_from_text(text)
            if user_score is not None:
                break

    # Critic count and user count
    critic_count = None
    user_count = None
    # Look for text like "based on 89 Critic Reviews" or small counters
    critic_text = soup.find(string=re.compile(r"\bcritic(s)?\b", re.I))
    if critic_text:
        # search backwards for numbers in the same region
        nearby = critic_text.parent.get_text(" ", strip=True)
        critic_count = parse_int_from_text(nearby)

    # fallback selectors:
    for sel in [".based_on .count", ".c-siteReviewCount", ".metascore_count", ".critic_count"]:
        el = soup.select_one(sel)
        if el:
            critic_count = parse_int_from_text(el.get_text(strip=True)) or critic_count
            if critic_count is not None:
                break

    # user count selectors
    for sel in [".c-siteUserReviewCount", ".userscore_count", ".user_count"]:
        el = soup.select_one(sel)
        if el:
            user_count = parse_int_from_text(el.get_text(strip=True))
            if user_count is not None:
                break

    # Cover art
    cover_url = None
    for sel in ["img.product_image", "img.c-productHero_image", ".product_image img", ".main_art img", ".poster img"]:
        el = soup.select_one(sel)
        if el and el.get("src"):
            cover_url = el.get("src")
            break

    # Genre / categories
    genre = None
    for sel in [".genre", ".genres", ".c-genreList_item", ".product_genre", ".details .genre"]:
        el = soup.select_one(sel)
        if el:
            genre = el.get_text(" ", strip=True)
            break

    # Release year
    year = None
    # look for 4-digit year in the page near metadata
    ymatch = re.search(r"\b(19|20)\d{2}\b", soup.get_text(" ", strip=True))
    if ymatch:
        year = ymatch.group(0)

    # Summary / tagline / consensus
    summary = None
    for sel in [".summary_deck", ".blurb", ".c-productSummary", ".product_summary", ".deck"]:
        el = soup.select_one(sel)
        if el:
            summary = el.get_text(" ", strip=True)
            break

    # If we got nothing, return minimal None so caller can fallback
    if not any([title, metascore, user_score, cover_url]):
        return None

    return {
        "title": title or "Unknown",
        "metascore": metascore if metascore is not None else 0,
        "user_score": user_score if user_score is not None else 0.0,
        "critic_count": critic_count or "?",
        "user_count": user_count or "?",
        "cover": cover_url,
        "genre": genre or "Unknown",
        "year": year or "Unknown",
        "summary": summary or "",
    }

def parse_search_results(html_text):
    """
    Parse the Metacritic search results page to extract candidate items.
    Returns list of dict {title, url, platform}
    """
    soup = BeautifulSoup(html_text, "lxml")
    results = []

    # New-style cards
    cards = soup.select(".result_wrap .result")
    if not cards:
        # try old selectors
        cards = soup.select(".search_results.module .result")

    # Each card might have a link, a platform and maybe platform label
    for c in cards:
        link = c.find("a", href=True)
        if not link:
            continue
        href = link.get("href")
        if href and href.startswith("/"):
            url = "https://www.metacritic.com" + href
        else:
            url = href
        title = link.get_text(strip=True) or c.select_one(".title") and c.select_one(".title").get_text(strip=True)
        # platform text sometimes in small tags
        platform_el = c.select_one(".platform") or c.select_one(".platform span") or c.select_one(".result_platform")
        platform_text = platform_el.get_text(strip=True) if platform_el else None

        if title and url:
            results.append({"title": title, "url": url, "platform": platform_text})
    # fallback: find within search result anchors
    if not results:
        for a in soup.select("a[href*='/game/'], a[href*='/movie/'], a[href*='/tv/']"):
            href = a.get("href")
            url = "https://www.metacritic.com" + href if href.startswith("/") else href
            title = a.get_text(strip=True)
            # platform guess from href (e.g., /game/pc/...)
            platform_guess = None
            m = re.search(r"/(pc|ps5|ps4|xbox-one|xbox-series-x|switch|ios|android)/", href or "", re.I)
            if m:
                platform_guess = m.group(1)
            results.append({"title": title, "url": url, "platform": platform_guess})
    # Deduplicate by url
    seen = set()
    unique = []
    for r in results:
        if r["url"] in seen:
            continue
        seen.add(r["url"])
        unique.append(r)
    return unique

# ---------------------------
# Discord Cog
# ---------------------------

class PlatformSelect(discord.ui.Select):
    def __init__(self, parent_cog, choices, base_message_data):
        # choices: list of (label, url, platform_text)
        options = [discord.SelectOption(label=f"{platform_icon(c[2])} {c[2] or 'Platform'} — {c[0]}", value=str(i))
                   for i, c in enumerate(choices)]
        super().__init__(placeholder="Select platform/version...", min_values=1, max_values=1, options=options)
        self.parent_cog = parent_cog
        self.choices_data = choices
        self.base_message_data = base_message_data  # contains title, media_type, etc.

    async def callback(self, interaction: discord.Interaction):
        idx = int(self.values[0])
        choice = self.choices_data[idx]
        # choice: (title, url, platform)
        await interaction.response.defer(thinking=True)
        # fetch the detail page for the chosen platform
        data = await self.parent_cog.fetch_metacritic_detail(choice[1])
        if not data:
            await interaction.followup.send("⚠️ Failed to fetch that platform's page.", ephemeral=True)
            return
        data["media_type"] = self.base_message_data["media_type"]
        data["platform"] = choice[2] or data.get("platform", "N/A")
        # update DB and edit message
        await save_score(data["title"], data["platform"], data["media_type"], data["metascore"], data["user_score"])
        embed = self.parent_cog.build_embed(data)
        # Fresh view with refresh button
        view = RefreshView(self.parent_cog, data)
        view.add_item(discord.ui.Button(label="🌐 Open Website", url=data["url"]))
        # edit original message
        await interaction.message.edit(embed=embed, view=view)
        await interaction.followup.send(f"Switched to **{data['platform']}** version.", ephemeral=True)

class PlatformSelectView(discord.ui.View):
    def __init__(self, parent_cog, choices, base_message_data):
        super().__init__(timeout=120)  # keep dropdown available for 2 minutes
        self.add_item(PlatformSelect(parent_cog, choices, base_message_data))

class RefreshView(discord.ui.View):
    def __init__(self, parent_cog, data):
        super().__init__(timeout=None)  # persistent until restart
        self.parent_cog = parent_cog
        self.data = data

    @discord.ui.button(label="🔄 Refresh", style=discord.ButtonStyle.blurple)
    async def refresh(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Animated refresh: edit message to a temporary "updating" embed, then replace with final
        await interaction.response.defer(thinking=True)
        try:
            # Indicate update in-place for some "animation" feel
            updating_embed = self.parent_cog.build_embed(self.data)
            # Add small animated visual to description temporarily
            updating_embed.description = ("🔁 **Refreshing scores...** ⏳\n\n" +
                                         (updating_embed.description or ""))
            # subtle footer change
            updating_embed.set_footer(text="Updating...")

            # Edit original message to show updating embed
            await interaction.message.edit(embed=updating_embed, view=self)

            # perform the fetch (in executor to avoid blocking)
            new_data = await self.parent_cog.fetch_metacritic_data(
                self.data["media_type"], self.data["title"], self.data.get("platform"), self.data.get("year")
            )
            if not new_data:
                # failure: notify user and revert footer
                fail_embed = self.parent_cog.build_embed(self.data)
                fail_embed.set_footer(text="Failed to refresh — try again later.")
                await interaction.message.edit(embed=fail_embed, view=self)
                await interaction.followup.send("⚠️ Failed to refresh data. Try again later.", ephemeral=True)
                return

            new_data["media_type"] = self.data["media_type"]
            # compute trend vs stored score
            last = await get_last_score(new_data["title"], new_data.get("platform"), new_data["media_type"])
            trend_text = ""
            try:
                prev_score = last and last.get("metascore")
                if prev_score is not None and isinstance(prev_score, int):
                    diff = new_data["metascore"] - prev_score
                    if diff > 0:
                        trend_text = f" 📈 +{diff}"
                    elif diff < 0:
                        trend_text = f" 📉 {diff}"
            except Exception:
                trend_text = ""

            final_embed = self.parent_cog.build_embed(new_data, trend_text=trend_text)
            view = RefreshView(self.parent_cog, new_data)
            view.add_item(discord.ui.Button(label="🌐 Open Website", url=new_data["url"]))

            # save the new score to DB
            await save_score(new_data["title"], new_data.get("platform"), new_data["media_type"], new_data["metascore"], new_data["user_score"])

            # Finally edit message with final embed
            await interaction.message.edit(embed=final_embed, view=view)
            await interaction.followup.send("✅ Scores refreshed!", ephemeral=True)
        except Exception as ex:
            await interaction.followup.send("⚠️ An error occurred while refreshing.", ephemeral=True)
            print(f"[Refresh Error] {ex}")

class Metacritic(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        # ensure DB initialized
        bot.loop.create_task(init_db())

    # -------------------
    # Slash command
    # -------------------
    @app_commands.command(name="metacritic", description="Fetch Metacritic scores for games, movies, or TV shows.")
    @app_commands.describe(
        type="Select what to search (game, movie, tv).",
        title="Name of the game/movie/show.",
        platform="Optional platform (PC, PS5, Xbox, Switch) to refine search.",
        year="Optional release year to refine results."
    )
    @app_commands.choices(type=[
        app_commands.Choice(name="🎮 Game", value="game"),
        app_commands.Choice(name="🎬 Movie", value="movie"),
        app_commands.Choice(name="📺 TV Show", value="tv")
    ])
    async def metacritic(self, interaction: discord.Interaction, type: str, title: str, platform: str = None, year: int = None):
        await interaction.response.defer(thinking=True)
        try:
            # fetch search results
            search_url = f"https://www.metacritic.com/search/{type}/{requests.utils.requote_uri(title)}/results"
            # run requests in executor to avoid blocking event loop
            loop = asyncio.get_event_loop()
            resp = await loop.run_in_executor(None, _safe_get, search_url, HEADERS, 10)
            if resp.status_code != 200:
                await interaction.followup.send("⚠️ Metacritic search failed (HTTP {}).".format(resp.status_code))
                return

            candidates = parse_search_results(resp.text)

            # If no candidates found, provide helpful fallback: attempt direct URL guesses
            if not candidates:
                # try direct guess of /game/ or /movie/
                guess = f"https://www.metacritic.com/{type}/{requests.utils.requote_uri(title)}"
                resp2 = await loop.run_in_executor(None, _safe_get, guess, HEADERS, 10)
                if resp2.status_code == 200:
                    detail = await self.fetch_metacritic_detail(guess)
                    if detail:
                        data = detail
                        data["media_type"] = type
                        data["platform"] = platform or data.get("platform", "N/A")
                        await save_score(data["title"], data["platform"], data["media_type"], data["metascore"], data["user_score"])
                        embed = self.build_embed(data)
                        view = RefreshView(self, data)
                        view.add_item(discord.ui.Button(label="🌐 Open Website", url=data["url"]))
                        await interaction.followup.send(embed=embed, view=view)
                        return
                # No result
                embed = discord.Embed(title="😕 No data found", description=f"Couldn't find anything for **{title}** on Metacritic.", color=discord.Color.dark_grey())
                embed.set_footer(text="Powered by Metacritic | Data may vary.")
                await interaction.followup.send(embed=embed)
                return

            # If user supplied 'platform', try to match that first
            chosen = None
            if platform:
                lower_platform = platform.lower()
                for c in candidates:
                    p = (c.get("platform") or "").lower()
                    if lower_platform in p or lower_platform in c["title"].lower():
                        chosen = c
                        break

            # If only one candidate — use it
            if not chosen and len(candidates) == 1:
                chosen = candidates[0]

            # If multiple candidates across platforms, present a dropdown to pick
            if not chosen and len(candidates) > 1:
                # build a minimal "select platform" embed + dropdown
                base_message_data = {"title": title, "media_type": type}
                # prepare choices: (title, url, platform)
                choices = [(c["title"], c["url"], c.get("platform") or "Unknown") for c in candidates]
                # send an embed asking user to choose platform/version
                pick_embed = discord.Embed(
                    title=f"🔎 Multiple results for **{title}**",
                    description="Select the correct platform/version from the dropdown below.",
                    color=discord.Color.blurple()
                )
                # add a short list preview
                preview_text = "\n".join([f"{platform_icon(ch[2])} **{ch[2]}** — {ch[0]}" for ch in choices[:6]])
                pick_embed.add_field(name="Top matches", value=preview_text or "—", inline=False)
                pick_embed.set_footer(text="Pick the platform/version to load detailed info.")
                view = PlatformSelectView(self, choices, base_message_data)
                # include an ephemeral hint in followup
                await interaction.followup.send(embed=pick_embed, view=view)
                return

            # If we get here, we have a chosen candidate
            if not chosen:
                chosen = candidates[0]

            # fetch detail page and build embed
            detail = await self.fetch_metacritic_detail(chosen["url"])
            if not detail:
                await interaction.followup.send("⚠️ Failed to fetch detail page.", ephemeral=True)
                return

            detail["media_type"] = type
            # prefer provided platform param
            detail["platform"] = platform or chosen.get("platform") or detail.get("platform") or "N/A"
            detail["url"] = chosen["url"]
            # save initial score
            await save_score(detail["title"], detail["platform"], detail["media_type"], detail["metascore"], detail["user_score"])

            embed = self.build_embed(detail)
            view = RefreshView(self, detail)
            view.add_item(discord.ui.Button(label="🌐 Open Website", url=detail["url"]))
            await interaction.followup.send(embed=embed, view=view)
        except Exception as e:
            print(f"[metacritic command error] {e}")
            await interaction.followup.send("⚠️ An unexpected error occurred while fetching Metacritic data.", ephemeral=True)

    # -------------------
    # Fetch detail helpers
    # -------------------
    async def fetch_metacritic_detail(self, url):
        """
        Fetch a Metacritic detail page and parse it using extract_from_detail_html
        """
        try:
            loop = asyncio.get_event_loop()
            resp = await loop.run_in_executor(None, _safe_get, url, HEADERS, 10)
            if resp.status_code != 200:
                # try with trailing slash variations
                alt = url.rstrip("/") + "/"
                resp2 = await loop.run_in_executor(None, _safe_get, alt, HEADERS, 10)
                if resp2.status_code != 200:
                    return None
                resp = resp2
            parsed = extract_from_detail_html(resp.text)
            if not parsed:
                # fallback: try to fetch mobile site or an alternative path
                alt_url = url.replace("www.metacritic.com", "api.allorigins.win/raw?url=https://www.metacritic.com")
                resp2 = await loop.run_in_executor(None, _safe_get, alt_url, HEADERS, 10)
                if resp2.status_code == 200:
                    parsed = extract_from_detail_html(resp2.text)
            if parsed:
                parsed["url"] = url
                return parsed
            return None
        except Exception as e:
            print(f"[fetch_metacritic_detail] {e}")
            return None

    # -------------------
    # Embed builder
    # -------------------
    def build_embed(self, data, trend_text=""):
        """
        data: title, metascore, user_score, critic_count, user_count, cover, genre, year, summary, url, platform, media_type
        trend_text: optional small trend string like " 📈 +2"
        """
        metascore = int(data.get("metascore") or 0)
        user_score = float(data.get("user_score") or 0.0)
        critic_count = data.get("critic_count", "?")
        user_count = data.get("user_count", "?")
        cover = data.get("cover")
        title = data.get("title", "Unknown")
        platform_text = data.get("platform", "N/A")
        genre = data.get("genre", "Unknown")
        year = data.get("year", "Unknown")
        summary = data.get("summary", "")

        # choose color and emojis
        if metascore >= 90:
            color = discord.Color.gold()
            score_badge = "🟢"
            # add extra visual for elites
            elite_line = "✨ **Critics Love It!** ✨\n"
        elif metascore >= 80:
            color = discord.Color.gold()
            score_badge = "🟢"
            elite_line = ""
        elif metascore >= 50:
            color = discord.Color.orange()
            score_badge = "🟡"
            elite_line = ""
        else:
            color = discord.Color.red()
            score_badge = "🔴"
            elite_line = ""

        emo_type = "🎮" if data.get("media_type") == "game" else "🎬" if data.get("media_type") == "movie" else "📺"
        icon = platform_icon(platform_text)

        # build compact bar visuals
        critic_bar = percent_bar(metascore, 100, length=12)
        # user_score on Metacritic is usually 0-10 scale; convert to 0-100 for visual parity if >10 assume 0-100 already
        user_for_bar = user_score * 10 if user_score <= 10 else user_score
        user_bar = percent_bar(user_for_bar, 100, length=12)

        # Trend + header
        title_txt = f"{emo_type} **{title}** {trend_text}"
        description = f"{elite_line}{summary}\n\n{icon} **{platform_text}** • {year} • {genre}"

        embed = discord.Embed(title=title_txt, description=description, color=color)
        # fields: metascore, user score, comparison
        embed.add_field(name="Metascore", value=f"{score_badge} **{metascore}** • {critic_count} critics", inline=True)
        embed.add_field(name="User Score", value=f"⭐ **{user_score}** • {user_count} users", inline=True)

        embed.add_field(name="Critic vs Users", value=f"Critics: {critic_bar}\nUsers:   {user_bar}", inline=False)
        embed.add_field(name="Link", value=f"[View on Metacritic]({data.get('url')})", inline=False)

        if cover:
            embed.set_thumbnail(url=cover)

        # Footer
        embed.set_footer(text="Powered by Metacritic | Data may vary.")
        return embed

# ---------------------------
# Cog setup
# ---------------------------

async def setup(bot):
    await bot.add_cog(Metacritic(bot))
