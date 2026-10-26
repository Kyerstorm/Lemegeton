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

COMPARE_CATEGORY_CHOICES = [
    app_commands.Choice(name="Anime", value="ANIME"),
    app_commands.Choice(name="Manga", value="MANGA"),
    app_commands.Choice(name="Light novels", value="LIGHT_NOVEL"),
    app_commands.Choice(name="Books and novels", value="BOOK"),
    app_commands.Choice(name="Webnovels (Novel Updates)", value="WEBNOVEL"),
    app_commands.Choice(name="Movie", value="MOVIE"),
    app_commands.Choice(name="TV show", value="TV"),
    app_commands.Choice(name="Video game", value="GAME"),
]

def clean_igdb_query(value: str) -> str:
    """Keep user input from escaping IGDB's search expression."""
    return value.replace(chr(34), " ").replace(chr(59), " ").replace(chr(92), " ").strip()

def media_title(category: str, item: dict) -> str:
    if category in ("ANIME", "MANGA", "LIGHT_NOVEL"):
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

def comparison_embed(category: str | list[str], first: dict, second: dict, *additional: dict) -> discord.Embed:
    items = (first, second, *additional)
    categories = [category] * len(items) if isinstance(category, str) else list(category[:len(items)])
    if not categories:
        categories = ["ANIME"] * len(items)
    while len(categories) < len(items):
        categories.append(categories[-1])
    mixed = len(set(categories)) > 1
    heading = f"Cross-media Comparison · {len(items)} titles" if mixed else f"{categories[0].title()} Comparison · {len(items)} titles"
    embed = discord.Embed(
        title=f"⚖️ {heading}",
        description="Compare provider-reported details side by side. Missing data is marked unavailable; **no overall winner is calculated.**",
        color=discord.Color.blurple(),
    )
    for item, item_category in zip(items, categories):
        title = media_title(item_category, item)
        lines: list[str] = []
        url = None
        cover = None
        if item_category in ("ANIME", "MANGA", "LIGHT_NOVEL"):
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
        elif item_category == "BOOK":
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
        elif item_category == "WEBNOVEL":
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
        elif item_category in ("MOVIE", "TV"):
            is_movie = item_category == "MOVIE"
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
        field_name = f"{item_category.title()} · {title}" if mixed else title
        embed.add_field(name=field_name[:256], value="\n".join(lines)[:1024] or "No additional provider metadata was supplied.", inline=True)
        if url:
            embed.add_field(name="Provider page", value=f"[Open {title[:80]}]({url})", inline=False)
        if cover and not embed.thumbnail:
            embed.set_thumbnail(url=cover)
    embed.set_footer(text="📊 Sources: AniList · Novel Updates · Google Books · Goodreads · TMDB · MDBList · IGDB · Steam")
    return embed

class CompareSelect(discord.ui.Select):
    def __init__(self, owner: "CompareView", side: str, results: list[dict]):
        self.owner_view = owner
        self.side = side
        self.results = results
        selected_category = owner.category_by_side[side]
        options = [
            discord.SelectOption(label=media_title(selected_category, item)[:100], value=str(index))
            for index, item in enumerate(results[:25])
        ]
        super().__init__(placeholder=f"🔎 Choose the {side} title", options=options, min_values=1, max_values=1)

    async def callback(self, interaction: discord.Interaction) -> None:
        self.owner_view.selected_indices[self.side] = int(self.values[0])
        await interaction.response.defer()

class CompareView(FeedbackAwareView):
    def __init__(self, cog: "Compare", owner_id: int, categories: list[str], results: list[list[dict]]):
        super().__init__(timeout=180)
        self.cog = cog
        self.owner_id = owner_id
        self.sides = ("first", "second", "third", "fourth")
        self.category_by_side = {side: category for side, category in zip(self.sides, categories)}
        self.results = {side: entries[:25] for side, entries in zip(self.sides, results)}
        self.selected_indices = {side: 0 for side in self.results}
        for side, entries in self.results.items():
            self.add_item(CompareSelect(self, side, entries))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message("Only the user who started this comparison can use these controls.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="⚖️ Compare selected titles", style=discord.ButtonStyle.primary)
    async def compare_selected(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await interaction.response.defer()
        selected = [
            self.cog.enrich(self.category_by_side[side], entries[self.selected_indices[side]])
            for side, entries in self.results.items()
        ]
        selected_categories = [self.category_by_side[side] for side in self.results]
        enriched = await asyncio.gather(*selected, return_exceptions=True)
        if any(isinstance(item, Exception) for item in enriched):
            log.warning("A selected title could not be enriched for comparison")
            await interaction.edit_original_response(
                content="At least one provider failed while loading the comparison. Try again with fewer titles or retry later.",
                embed=None,
                view=None,
            )
            return
        await interaction.edit_original_response(
            embed=comparison_embed(selected_categories, enriched[0], enriched[1], *enriched[2:]),
            view=None,
        )

class Compare(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.browse = BrowseCog(bot)

    async def search_options(self, category: str, query: str) -> list[dict]:
        if category in ("ANIME", "MANGA", "LIGHT_NOVEL"):
            ani_type = "ANIME" if category == "ANIME" else "MANGA"
            results = await fetch_media_by_search(query, ani_type, per_page=8)
            if category == "LIGHT_NOVEL":
                return [item for item in results if str(item.get("format") or "").upper() == "NOVEL"]
            if category == "MANGA":
                return [item for item in results if str(item.get("format") or "").upper() != "NOVEL"]
            return results
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

    @app_commands.command(name="compare", description="Compare two to four titles through existing metadata providers")
    @app_commands.guild_only()
    @app_commands.choices(
        category=COMPARE_CATEGORY_CHOICES,
        first_category=COMPARE_CATEGORY_CHOICES,
        second_category=COMPARE_CATEGORY_CHOICES,
        third_category=COMPARE_CATEGORY_CHOICES,
        fourth_category=COMPARE_CATEGORY_CHOICES,
    )
    @app_commands.describe(
        first="First title", second="Second title",
        category="Default category used unless overridden for a title",
        third="Optional third title", fourth="Optional fourth title",
        first_category="Optional category override for the first title",
        second_category="Optional category override for the second title",
        third_category="Optional category override (requires a third title)",
        fourth_category="Optional category override (requires a fourth title)",
    )
    @command_meta(section="Media Discovery", name="Compare")
    async def compare(
        self, interaction: discord.Interaction, first: str, second: str, category: str,
        third: str | None = None, fourth: str | None = None,
        first_category: str | None = None, second_category: str | None = None,
        third_category: str | None = None, fourth_category: str | None = None,
    ) -> None:
        queries = [first, second, *[value for value in (third, fourth) if value and value.strip()]]
        if any(not value.strip() for value in queries):
            await interaction.response.send_message("Enter a title for every supplied comparison slot.", ephemeral=True)
            return
        if third_category and not (third and third.strip()):
            await interaction.response.send_message("A third-category override requires a third title.", ephemeral=True)
            return
        if fourth_category and not (fourth and fourth.strip()):
            await interaction.response.send_message("A fourth-category override requires a fourth title.", ephemeral=True)
            return
        categories = [first_category or category, second_category or category]
        if third and third.strip():
            categories.append(third_category or category)
        if fourth and fourth.strip():
            categories.append(fourth_category or category)
        await interaction.response.defer(ephemeral=True, thinking=True)
        results = await asyncio.gather(
            *(self.search_options(item_category, value.strip()) for item_category, value in zip(categories, queries)),
            return_exceptions=True,
        )
        missing = [
            f"{categories[index].title()} {['first', 'second', 'third', 'fourth'][index]} title {queries[index]!r}"
            for index, result in enumerate(results)
            if isinstance(result, Exception) or not result
        ]
        if missing:
            await interaction.followup.send(
                "Could not resolve " + ", ".join(missing) + ". Check provider configuration or try a more specific title.",
                ephemeral=True,
            )
            return
        view = CompareView(self, interaction.user.id, categories, results)
        await interaction.followup.send(
            "🔎 **Choose the exact result for each title**, then compare. Ratings retain their provider attribution.",
            view=view, ephemeral=True,
        )

async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Compare(bot))
