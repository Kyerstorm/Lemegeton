"""Side-by-side media comparisons using existing provider helpers."""
from __future__ import annotations
import asyncio
import logging
import os
import re
import aiohttp
import discord
from helpers.command_error_handler import FeedbackAwareView
from discord import app_commands
from discord.ext import commands
from helpers.anilist_helper import fetch_media_by_search
import helpers.igdb_helper as igdb
from helpers.steam_helper import search_steam_apps
from helpers.gaming_utils import is_steam_deck_verified, get_controller_support
from cogs.gaming.steam_game import fetch_game_details
from cogs_test.general_commands.game import fetch_igdb_details
from cogs.media.browse import BrowseCog, search_novelupdates
from cogs_test.general_commands.dashboard import command_meta

log = logging.getLogger(__name__)

def clean_igdb_query(value: str) -> str:
    """Keep user input from escaping IGDB's search expression."""
    return value.replace(chr(34), " ").replace(chr(59), " ").replace(chr(92), " ").strip()

def media_title(category: str, item: dict) -> str:
    if category in ("ANIME", "MANGA"):
        title = item.get("title") or {}
        return title.get("english") or title.get("romaji") or "Untitled"
    if category == "BOOK":
        return (item.get("volumeInfo") or {}).get("title") or "Untitled"
    return item.get("title") or item.get("name") or "Untitled"

def _rating_text(ratings: dict, key: str, label: str) -> str | None:
    value = ratings.get(key) if isinstance(ratings, dict) else None
    if isinstance(value, dict):
        score = value.get("value")
        if score is not None:
            return f"{label}: {score} (MDBList source)"
    return None

def comparison_embed(category: str, first: dict, second: dict) -> discord.Embed:
    embed = discord.Embed(
        title=f"⚖️ Media Comparison · {category.title()}",
        description="Compare provider-reported details side by side. Missing data is marked unavailable; **no overall winner is calculated.**",
        color=discord.Color.blurple(),
    )
    for item in (first, second):
        title = media_title(category, item)
        lines: list[str] = []
        url = None
        cover = None
        if category in ("ANIME", "MANGA"):
            if item.get("format"):
                lines.append(f"Format: {item['format']}")
            if item.get("status"):
                lines.append(f"Status: {item['status']}")
            if item.get("genres"):
                lines.append("Genres: " + ", ".join(item["genres"][:8]))
            if item.get("averageScore") is not None:
                lines.append(f"AniList average score: {item['averageScore']}/100")
            date = item.get("startDate") or {}
            if date.get("year"):
                lines.append(f"Start date: {date['year']}-{date.get('month') or 1:02d}-{date.get('day') or 1:02d}")
            for key in ("episodes", "chapters", "volumes"):
                if item.get(key) is not None:
                    lines.append(f"{key.title()}: {item[key]}")
            nodes = (item.get("studios") or {}).get("nodes") or []
            names = [node.get("name") for node in nodes if node.get("name")]
            if names:
                lines.append("Studios: " + ", ".join(names[:5]))
            url = item.get("siteUrl")
            cover = (item.get("coverImage") or {}).get("large")
        elif category == "BOOK":
            info = item.get("volumeInfo") or {}
            for key, label in (("authors", "Authors"), ("publisher", "Publisher"), ("publishedDate", "Published"), ("language", "Language"), ("pageCount", "Pages")):
                value = info.get(key)
                if value:
                    lines.append(f"{label}: {', '.join(value) if isinstance(value, list) else value}")
            isbn = [entry.get("identifier") for entry in (info.get("industryIdentifiers") or []) if entry.get("identifier")]
            if isbn:
                lines.append("ISBN: " + ", ".join(isbn[:2]))
            if info.get("averageRating") is not None:
                if info.get("source") == "Goodreads":
                    lines.append(f"Goodreads rating: {info['averageRating']} (rating scale not normalized)")
                else:
                    lines.append(f"Google Books rating: {info['averageRating']}/5")
            if info.get("description"):
                lines.append(info["description"][:300])
            url = info.get("infoLink")
            cover = (info.get("imageLinks") or {}).get("thumbnail")
        elif category == "WEBNOVEL":
            for key, label in (("author", "Author"), ("status", "Status"), ("rating", "Novel Updates rating")):
                value = item.get(key)
                if value:
                    lines.append(f"{label}: {value}")
            if item.get("genres"):
                lines.append("Genres: " + ", ".join(str(value) for value in item["genres"][:8]))
            if item.get("description"):
                lines.append(str(item["description"])[:300])
            url = item.get("url")
            cover = item.get("image")
        elif category in ("MOVIE", "TV"):
            is_movie = category == "MOVIE"
            date = item.get("release_date") if is_movie else item.get("first_air_date")
            if date:
                lines.append(f"Release date: {date}")
            if item.get("runtime"):
                lines.append(f"Runtime: {item['runtime']} minutes")
            if item.get("number_of_seasons") is not None:
                lines.append(f"Seasons: {item['number_of_seasons']}")
            if item.get("number_of_episodes") is not None:
                lines.append(f"Episodes: {item['number_of_episodes']}")
            genres = [entry.get("name") for entry in (item.get("genres") or []) if isinstance(entry, dict) and entry.get("name")]
            if genres:
                lines.append("Genres: " + ", ".join(genres[:8]))
            credits = item.get("credits") or {}
            crew = credits.get("crew") or []
            directors = [entry.get("name") for entry in crew if entry.get("job") == "Director" and entry.get("name")]
            if directors:
                lines.append("Director: " + ", ".join(directors[:3]))
            if item.get("vote_average") is not None:
                lines.append(f"TMDB user rating: {item['vote_average']}/10")
            ratings = item.get("_mdblist") or {}
            for key, label in (("metacritic", "Metacritic critic score"), ("metacriticuser", "Metacritic user score")):
                rating = _rating_text(ratings, key, label)
                if rating:
                    lines.append(rating)
            url = f"https://www.themoviedb.org/{'movie' if is_movie else 'tv'}/{item['id']}" if item.get("id") else None
            image_path = item.get("poster_path")
            cover = f"https://image.tmdb.org/t/p/w500{image_path}" if image_path else None
        else:
            details = item.get("_igdb") or item
            if details.get("summary"):
                lines.append(details["summary"][:300])
            for key in ("genres", "platforms", "game_modes"):
                names = [value.get("name") for value in (details.get(key) or []) if isinstance(value, dict) and value.get("name")]
                if names:
                    lines.append(f"{key.replace('_', ' ').title()}: " + ", ".join(names[:8]))
            companies = details.get("involved_companies") or []
            devs = [entry.get("company", {}).get("name") for entry in companies if entry.get("developer") and entry.get("company")]
            pubs = [entry.get("company", {}).get("name") for entry in companies if entry.get("publisher") and entry.get("company")]
            if devs:
                lines.append("Developers: " + ", ".join(devs[:4]))
            if pubs:
                lines.append("Publishers: " + ", ".join(pubs[:4]))
            release = details.get("first_release_date")
            if isinstance(release, (int, float)):
                lines.append(f"First release: <t:{int(release)}:D>")
            cover = igdb.get_cover_image_url(details.get("cover") or item.get("cover") or {})
            url = f"https://www.igdb.com/games/{details.get('slug') or item.get('slug')}" if (details.get("slug") or item.get("slug")) else None
            steam = item.get("_steam")
            if steam:
                price = steam.get("price_overview") or {}
                if steam.get("is_free"):
                    lines.append("Steam price: Free to Play")
                elif price.get("final_formatted"):
                    price_text = price["final_formatted"]
                    if price.get("discount_percent"):
                        price_text += f" (-{price['discount_percent']}%)"
                    lines.append("Steam price: " + price_text)
                deck = is_steam_deck_verified(steam)
                controller = get_controller_support(steam)
                if deck:
                    lines.append("Steam Deck: " + str(deck))
                if controller:
                    lines.append("Controller support: " + str(controller))
                if steam.get("steam_appid"):
                    lines.append(f"[Steam store listing](https://store.steampowered.com/app/{steam['steam_appid']}/)")
        embed.add_field(name=title[:256], value="\n".join(lines)[:1024] or "No additional provider metadata was supplied.", inline=True)
        if url:
            embed.add_field(name="Provider page", value=f"[Open {title[:80]}]({url})", inline=False)
        if cover and not embed.thumbnail:
            embed.set_thumbnail(url=cover)
    embed.set_footer(text="📊 Sources: AniList · Google Books · Goodreads · TMDB · MDBList · IGDB · Steam")
    return embed

class CompareSelect(discord.ui.Select):
    def __init__(self, owner: "CompareView", side: str, results: list[dict]):
        self.owner_view = owner
        self.side = side
        self.results = results
        options = [
            discord.SelectOption(label=media_title(owner.category, item)[:100], value=str(index))
            for index, item in enumerate(results[:25])
        ]
        super().__init__(placeholder=f"🔎 Choose the {side} title", options=options, min_values=1, max_values=1)

    async def callback(self, interaction: discord.Interaction) -> None:
        if self.side == "first":
            self.owner_view.first_index = int(self.values[0])
        else:
            self.owner_view.second_index = int(self.values[0])
        await interaction.response.defer()

class CompareView(FeedbackAwareView):
    def __init__(self, cog: "Compare", owner_id: int, category: str, first: list[dict], second: list[dict]):
        super().__init__(timeout=180)
        self.cog = cog
        self.owner_id = owner_id
        self.category = category
        self.first = first[:25]
        self.second = second[:25]
        self.first_index = 0
        self.second_index = 0
        self.add_item(CompareSelect(self, "first", self.first))
        self.add_item(CompareSelect(self, "second", self.second))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message("Only the user who started this comparison can use these controls.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="⚖️ Compare selected titles", style=discord.ButtonStyle.primary)
    async def compare_selected(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await interaction.response.defer()
        first = await self.cog.enrich(self.category, self.first[self.first_index])
        second = await self.cog.enrich(self.category, self.second[self.second_index])
        await interaction.edit_original_response(embed=comparison_embed(self.category, first, second), view=None)

class Compare(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.browse = BrowseCog(bot)

    async def search_options(self, category: str, query: str) -> list[dict]:
        if category in ("ANIME", "MANGA"):
            return await fetch_media_by_search(query, category, per_page=8)
        if category == "WEBNOVEL":
            return await asyncio.wait_for(search_novelupdates(query), timeout=45)
        if category == "BOOK":
            fiction, nonfiction = await asyncio.gather(
                self.browse.fetch_book_results(query, "fiction"),
                self.browse.fetch_book_results(query, "nonfiction"),
            )
            by_key = {}
            for item in fiction + nonfiction:
                info = item.get("volumeInfo") or {}
                key = (info.get("title", "").casefold(), tuple(info.get("authors") or []))
                by_key[key] = item
            return list(by_key.values())[:8]
        if category in ("MOVIE", "TV"):
            return await self.browse.search_tmdb_titles(query, category)
        if not igdb.IGDB_CLIENT_ID or not igdb.IGDB_CLIENT_SECRET:
            return []
        safe_query = clean_igdb_query(query)
        if not safe_query:
            return []
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15)) as session:
            token = await igdb.get_access_token(session)
            return await igdb.search_games(session, token, safe_query, limit=8) if token else []

    async def enrich(self, category: str, item: dict) -> dict:
        item = dict(item)
        if category in ("MOVIE", "TV") and item.get("id") and os.getenv("TMDB_BEARER_TOKEN", "").strip():
            endpoint = "movie" if category == "MOVIE" else "tv"
            headers = {"Authorization": f"Bearer {os.getenv('TMDB_BEARER_TOKEN').strip()}", "Accept": "application/json"}
            try:
                async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=12)) as session:
                    async with session.get(
                        f"https://api.themoviedb.org/3/{endpoint}/{int(item['id'])}",
                        params={"language": "en-US", "append_to_response": "credits"},
                        headers=headers,
                    ) as response:
                        if response.status == 200:
                            details = await response.json()
                            details["_mdblist"] = await self.browse.fetch_mdblist_ratings(int(item["id"]), category)
                            return details
            except (aiohttp.ClientError, asyncio.TimeoutError, ValueError):
                log.info("Unable to enrich selected TMDB comparison result")
        if category == "GAME" and item.get("slug") and igdb.IGDB_CLIENT_ID:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15)) as session:
                token = await igdb.get_access_token(session)
                details = await fetch_igdb_details(session, item["slug"], token) if token else None
                if details:
                    item["_igdb"] = details
                search_name = (details or item).get("name", "")
                matches = await search_steam_apps(session, search_name, max_results=5)
                exact = next((candidate for candidate in matches if candidate.get("name", "").casefold() == search_name.casefold()), None)
                if exact and exact.get("appid"):
                    item["_steam"] = await fetch_game_details(session, int(exact["appid"]))
        return item

    @app_commands.command(name="compare", description="Compare two titles through their existing metadata providers")
    @app_commands.guild_only()
    @app_commands.choices(category=[
        app_commands.Choice(name="Anime", value="ANIME"),
        app_commands.Choice(name="Manga", value="MANGA"),
        app_commands.Choice(name="Books and novels", value="BOOK"),
        app_commands.Choice(name="Webnovels (Novel Updates)", value="WEBNOVEL"),
        app_commands.Choice(name="Movie", value="MOVIE"),
        app_commands.Choice(name="TV show", value="TV"),
        app_commands.Choice(name="Video game", value="GAME"),
    ])
    @app_commands.describe(first="First title", second="Second title", category="Category shared by both entries")
    @command_meta(section="Media Discovery", name="Compare")
    async def compare(self, interaction: discord.Interaction, first: str, second: str, category: str) -> None:
        if not first.strip() or not second.strip():
            await interaction.response.send_message("Enter a title for both sides of the comparison.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            left, right = await asyncio.gather(self.search_options(category, first.strip()), self.search_options(category, second.strip()))
        except (aiohttp.ClientError, asyncio.TimeoutError, ValueError):
            left, right = [], []
        if not left or not right:
            missing = []
            if not left:
                missing.append(f"the first title {first!r}")
            if not right:
                missing.append(f"the second title {second!r}")
            await interaction.followup.send("Could not resolve " + " and ".join(missing) + ". Check provider configuration or try a more specific title.", ephemeral=True)
            return
        view = CompareView(self, interaction.user.id, category, left, right)
        await interaction.followup.send(
            "🔎 **Choose the exact result for each side**, then compare. All ratings keep their original provider attribution.",
            view=view, ephemeral=True,
        )

async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Compare(bot))
