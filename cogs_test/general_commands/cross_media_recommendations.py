"""Cross-media similarity discovery using existing AniList, Google Books, and TMDB providers."""
from __future__ import annotations

import asyncio
import logging
import os
from typing import Any

import aiohttp
import discord
from discord import app_commands
from discord.ext import commands

from cogs.media.browse import BrowseCog, search_novelupdates
from helpers.anilist_helper import fetch_media_by_id
from cogs_test.general_commands.dashboard import command_meta

log = logging.getLogger(__name__)
TMDB_BASE = "https://api.themoviedb.org/3"
TMDB_IMAGE = "https://image.tmdb.org/t/p/w500"

GENRE_ALIASES = {
    "science fiction": "sci-fi", "sci-fi": "sci-fi", "fantasy": "fantasy",
    "adventure": "adventure", "action": "action", "comedy": "comedy",
    "drama": "drama", "horror": "horror", "mystery": "mystery",
    "romance": "romance", "thriller": "thriller", "crime": "crime",
    "family": "family", "historical": "historical", "history": "historical",
    "supernatural": "supernatural", "psychological": "psychological",
    "slice of life": "slice of life", "sports": "sports",
    "documentary": "documentary", "animation": "animation", "war": "war",
}


def genre_tokens(values: list[str] | None) -> set[str]:
    """Map provider genre labels to a conservative shared vocabulary."""
    normalized: set[str] = set()
    for value in values or []:
        text = str(value or "").casefold()
        for alias, canonical in GENRE_ALIASES.items():
            if alias in text:
                normalized.add(canonical)
    return normalized


def local_match_reason(seed_genres: set[str], candidate_genres: set[str]) -> tuple[int, list[str]]:
    """Return shared-genre count and explicit explanation for local ranking."""
    shared = sorted(seed_genres.intersection(candidate_genres))
    return len(shared), shared


def provider_title(item: dict[str, Any], category: str) -> str:
    if category in ("ANIME", "MANGA"):
        title = item.get("title") or {}
        return str(title.get("english") or title.get("romaji") or title.get("native") or "Untitled")
    if category == "BOOK":
        return str((item.get("volumeInfo") or {}).get("title") or "Untitled")
    return str(item.get("title") or item.get("name") or "Untitled")


class CrossMediaRecommendations(commands.Cog):
    """Recommend related titles with the reason and provider type attached."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.browse = BrowseCog(bot)

    async def resolve_seed(self, query: str, category: str) -> dict[str, Any] | None:
        if category in ("ANIME", "MANGA"):
            results = await self.browse.fetch_media(query, category)
            seed = self.browse.choose_best_title_match(
                results, query,
                lambda item: (
                    (item.get("title") or {}).get("english"),
                    (item.get("title") or {}).get("romaji"),
                    (item.get("title") or {}).get("native"),
                ),
            )
            if not seed:
                return None
            details = await fetch_media_by_id(int(seed["id"]), category)
            return details or seed
        if category == "WEBNOVEL":
            results = await asyncio.wait_for(search_novelupdates(query), timeout=45)
            return self.browse.choose_best_title_match(results, query, lambda item: item.get("title"))
        if category == "BOOK":
            fiction, nonfiction = await asyncio.gather(
                self.browse.fetch_book_results(query, "fiction"),
                self.browse.fetch_book_results(query, "nonfiction"),
            )
            results = fiction + nonfiction
            seed = self.browse.choose_best_title_match(
                results, query, lambda item: (item.get("volumeInfo") or {}).get("title"),
            )
            if not seed:
                return None
            seed = dict(seed)
            seed["_category"] = "BOOK"
            return seed
        return await self.browse.fetch_tmdb_media(query, category)

    @staticmethod
    def seed_metadata(seed: dict[str, Any], category: str) -> tuple[str, str | None, list[str], list[str], list[dict]]:
        title = provider_title(seed, category)
        if category in ("ANIME", "MANGA"):
            genres = list(seed.get("genres") or [])
            tags = [
                str(tag.get("name")) for tag in (seed.get("tags") or [])
                if isinstance(tag, dict) and tag.get("name") and not tag.get("isMediaSpoiler")
            ]
            return title, seed.get("siteUrl"), genres, tags, []
        if category == "BOOK":
            info = seed.get("volumeInfo") or {}
            return title, info.get("infoLink") or seed.get("selfLink"), list(info.get("categories") or []), [], []
        if category == "WEBNOVEL":
            return title, seed.get("url"), list(seed.get("genres") or []), [], []
        is_movie = category == "MOVIE"
        endpoint = "movie" if is_movie else "tv"
        item_id = seed.get("id")
        source_url = f"https://www.themoviedb.org/{endpoint}/{item_id}" if item_id else None
        genres = [str(item.get("name")) for item in (seed.get("genres") or []) if item.get("name")]
        keywords_section = seed.get("keywords") or {}
        keyword_items = keywords_section.get("keywords" if is_movie else "results") or []
        keywords = [str(item.get("name")) for item in keyword_items if item.get("name")]
        return title, source_url, genres, keywords, []

    async def _anilist_pool(self, category: str, genres: list[str], tags: list[str]) -> list[dict[str, Any]]:
        anilist_names = {
            "action": "Action", "adventure": "Adventure", "comedy": "Comedy",
            "drama": "Drama", "fantasy": "Fantasy", "horror": "Horror",
            "mystery": "Mystery", "romance": "Romance", "sci-fi": "Sci-Fi",
            "slice of life": "Slice of Life", "sports": "Sports",
            "supernatural": "Supernatural", "thriller": "Thriller",
            "psychological": "Psychological",
        }
        genre_filter = [anilist_names[key] for key in sorted(genre_tokens(genres)) if key in anilist_names][:3]
        tag_filter = list(dict.fromkeys(tags))[:3]
        if not genre_filter and not tag_filter:
            return []
        query = """
        query($type: MediaType, $genres: [String], $tags: [String]) {
          Page(page: 1, perPage: 15) {
            media(type: $type, genre_in: $genres, tag_in: $tags, sort: POPULARITY_DESC, isAdult: false) {
              id
              title { english romaji native }
              description(asHtml: false)
              siteUrl
              genres
              tags { name isMediaSpoiler }
              coverImage { large }
              status
              format
              isAdult
            }
          }
        }
        """
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=12)) as session:
                from helpers.anilist_helper import post_graphql
                payload = await post_graphql(session, query, {"type": category, "genres": genre_filter, "tags": tag_filter}, timeout=12)
        except (aiohttp.ClientError, asyncio.TimeoutError, ValueError):
            log.warning("AniList cross-media recommendations failed for %s", category, exc_info=True)
            return []
        return ((payload or {}).get("Page") or {}).get("media") or []

    async def _book_pool(self, genres: list[str]) -> list[dict[str, Any]]:
        mapped = sorted(genre_tokens(genres))[:3]
        if not mapped:
            return []
        results = await asyncio.gather(
            *(self.browse.fetch_book_results("", "fiction", genre=genre) for genre in mapped),
            return_exceptions=True,
        )
        books = []
        seen = set()
        for result in results:
            if isinstance(result, Exception):
                log.warning("Google Books cross-media lookup failed: %r", result)
                continue
            for item in result or []:
                info = item.get("volumeInfo") or {}
                key = (info.get("title") or "").casefold(), tuple(info.get("authors") or [])
                if info.get("title") and key not in seen:
                    seen.add(key)
                    item["_cross_category"] = "BOOK"
                    books.append(item)
        return books[:15]

    async def _tmdb_pool(self, category: str, genres: list[str]) -> list[dict[str, Any]]:
        token = os.getenv("TMDB_BEARER_TOKEN", "").strip()
        mapped = genre_tokens(genres)
        if not token or not mapped:
            return []
        endpoint = "movie" if category == "MOVIE" else "tv"
        headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as session:
                async with session.get(f"{TMDB_BASE}/genre/{endpoint}/list", headers=headers, params={"language": "en-US"}) as response:
                    if response.status != 200:
                        return []
                    payload = await response.json(content_type=None)
                genres_by_name = {
                    str(item.get("name") or "").casefold(): int(item["id"])
                    for item in (payload.get("genres") or []) if item.get("id") is not None
                }
                ids = [identifier for name, identifier in genres_by_name.items() if genre_tokens([name]).intersection(mapped)]
                if not ids:
                    return []
                async with session.get(
                    f"{TMDB_BASE}/discover/{endpoint}",
                    headers=headers,
                    params={"language": "en-US", "include_adult": "false", "sort_by": "popularity.desc", "page": 1, "with_genres": "|".join(str(value) for value in ids)},
                ) as response:
                    if response.status != 200:
                        return []
                    discover = await response.json(content_type=None)
            id_to_name = {identifier: name for name, identifier in genres_by_name.items()}
            normalized = []
            for item in (discover.get("results") or [])[:20]:
                item_id = item.get("id")
                title = item.get("title") if category == "MOVIE" else item.get("name")
                if not item_id or not title:
                    continue
                item_genres = [id_to_name[identifier] for identifier in item.get("genre_ids", []) if identifier in id_to_name]
                normalized.append({
                    "id": item_id,
                    "title": title,
                    "overview": item.get("overview") or "",
                    "genres": [{"name": value} for value in item_genres],
                    "poster_path": item.get("poster_path"),
                    "siteUrl": f"https://www.themoviedb.org/{endpoint}/{item_id}",
                    "_category": category,
                })
            return normalized
        except (aiohttp.ClientError, asyncio.TimeoutError, ValueError):
            log.warning("TMDB cross-media recommendations failed for %s", category, exc_info=True)
            return []

    async def local_candidates(self, genres: list[str], tags: list[str]) -> list[dict[str, Any]]:
        genre_keys = genre_tokens(genres)
        if not genre_keys and not tags:
            return []
        jobs = [
            self._anilist_pool("ANIME", genres, tags),
            self._anilist_pool("MANGA", genres, tags),
            self._book_pool(genres),
            self._tmdb_pool("MOVIE", genres),
            self._tmdb_pool("TV", genres),
        ]
        responses = await asyncio.gather(*jobs, return_exceptions=True)
        candidates: list[dict[str, Any]] = []
        for category, response in zip(("ANIME", "MANGA", "BOOK", "MOVIE", "TV"), responses):
            if isinstance(response, Exception):
                log.warning("Cross-media provider failed for %s: %r", category, response)
                continue
            for item in response or []:
                item_category = str(item.get("_cross_category") or item.get("_category") or category)
                if item_category in ("ANIME", "MANGA"):
                    candidate_genres = genre_tokens(list(item.get("genres") or []))
                    item_title = provider_title(item, item_category)
                    url = item.get("siteUrl")
                    cover = (item.get("coverImage") or {}).get("large")
                elif item_category == "BOOK":
                    info = item.get("volumeInfo") or {}
                    candidate_genres = genre_tokens(list(info.get("categories") or []))
                    item_title = provider_title(item, "BOOK")
                    url = info.get("infoLink") or item.get("selfLink")
                    cover = (info.get("imageLinks") or {}).get("thumbnail")
                else:
                    candidate_genres = genre_tokens([str(v.get("name")) for v in (item.get("genres") or []) if isinstance(v, dict)])
                    item_title = provider_title(item, item_category)
                    url = item.get("siteUrl")
                    cover = f"{TMDB_IMAGE}{item['poster_path']}" if item.get("poster_path") else None
                match_count, shared = local_match_reason(genre_keys, candidate_genres)
                if not match_count or not item_title:
                    continue
                candidates.append({
                    "title": item_title, "url": url, "category": item_category,
                    "source": "local genre overlap", "shared": shared, "score": match_count,
                    "cover": cover,
                })
        candidates.sort(key=lambda item: (-item["score"], item["category"], item["title"].casefold()))
        # Keep results cross-category and avoid flooding the embed with one source.
        output = []
        counts: dict[str, int] = {}
        seen_titles = set()
        for item in candidates:
            key = (item["category"], item["title"].casefold())
            if key in seen_titles or counts.get(item["category"], 0) >= 3:
                continue
            seen_titles.add(key)
            counts[item["category"]] = counts.get(item["category"], 0) + 1
            output.append(item)
            if len(output) >= 10:
                break
        return output

    @app_commands.command(name="similar", description="Find related anime, manga, novels, movies, and TV across providers")
    @app_commands.guild_only()
    @app_commands.choices(category=[
        app_commands.Choice(name="Anime", value="ANIME"),
        app_commands.Choice(name="Manga / manhwa / manhua", value="MANGA"),
        app_commands.Choice(name="Books and novels", value="BOOK"),
        app_commands.Choice(name="Webnovels (Novel Updates)", value="WEBNOVEL"),
        app_commands.Choice(name="Movie", value="MOVIE"),
        app_commands.Choice(name="TV show", value="TV"),
    ])
    @app_commands.describe(title="A title to use as the starting point", category="Provider to search for the starting title")
    @command_meta(section="Media Discovery", name="Cross-media Similarity")
    async def similar(self, interaction: discord.Interaction, title: str, category: str) -> None:
        title = " ".join((title or "").split())
        if not title:
            await interaction.response.send_message("Enter a title to use as the starting point.", ephemeral=True)
            return
        if category in ("MOVIE", "TV") and not os.getenv("TMDB_BEARER_TOKEN", "").strip():
            await interaction.response.send_message("Movie and TV similarity requires TMDB_BEARER_TOKEN.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            seed = await self.resolve_seed(title, category)
        except (aiohttp.ClientError, asyncio.TimeoutError, ValueError, KeyError):
            log.exception("Cross-media seed lookup failed for %r (%s)", title, category)
            seed = None
        if not seed:
            await interaction.followup.send(f"Could not resolve {title!r} through the selected metadata provider.", ephemeral=True)
            return
        seed_title, seed_url, seed_genres, seed_tags, _ = self.seed_metadata(seed, category)
        local_results = await self.local_candidates(seed_genres, seed_tags)

        embed = discord.Embed(
            title=f"✨ Similar to {seed_title}"[:256],
            description=(
                "Local suggestions are ranked by shared provider-reported genres. The explanation beside each result names the overlap; this is a transparent heuristic, not an AI-generated score. "
                "AniList/TMDB provider recommendations, when present, are a separate source and are not mixed into these local rankings."
            ),
            color=discord.Color.blurple(),
        )
        if seed_url:
            embed.url = seed_url
        if category in ("ANIME", "MANGA"):
            cover = (seed.get("coverImage") or {}).get("large")
        elif category == "BOOK":
            cover = ((seed.get("volumeInfo") or {}).get("imageLinks") or {}).get("thumbnail")
        else:
            cover_path = seed.get("poster_path")
            cover = f"{TMDB_IMAGE}{cover_path}" if cover_path else None
        if cover:
            embed.set_thumbnail(url=cover)

        provider_suggestions = []
        if category in ("ANIME", "MANGA"):
            connections = ((seed.get("recommendations") or {}).get("edges") or [])
            for edge in connections[:4]:
                rec = ((edge.get("node") or {}).get("mediaRecommendation") or {})
                if rec.get("id") and provider_title(rec, category) != seed_title:
                    provider_suggestions.append({
                        "title": provider_title(rec, category), "url": rec.get("siteUrl"),
                        "source": "AniList provider recommendation",
                        "cover": (rec.get("coverImage") or {}).get("large"),
                    })
        elif category in ("MOVIE", "TV"):
            recs = ((seed.get("recommendations") or {}).get("results") or [])
            endpoint = "movie" if category == "MOVIE" else "tv"
            for rec in recs[:4]:
                rec_title = rec.get("title") if category == "MOVIE" else rec.get("name")
                if rec.get("id") and rec_title and rec_title.casefold() != seed_title.casefold():
                    provider_suggestions.append({
                        "title": rec_title,
                        "url": f"https://www.themoviedb.org/{endpoint}/{rec['id']}",
                        "source": "TMDB provider recommendation",
                        "cover": f"{TMDB_IMAGE}{rec['poster_path']}" if rec.get("poster_path") else None,
                    })
        if provider_suggestions:
            lines = []
            for rec in provider_suggestions:
                label = f"[{rec['title']}]({rec['url']})" if rec.get("url") else rec["title"]
                lines.append(f"**{label}** — {rec['source']}")
            embed.add_field(name="Provider-generated recommendations", value="\n".join(lines)[:1024], inline=False)
        if local_results:
            lines = []
            for rec in local_results:
                label = f"[{rec['title']}]({rec['url']})" if rec.get("url") else rec["title"]
                overlap = ", ".join(rec["shared"])
                lines.append(f"**{rec['category']} · {label}**\nShared genres: {overlap} · Source: {rec['source']}")
            embed.add_field(name="Cross-media matches · local ranking", value="\n\n".join(lines)[:3900], inline=False)
        if not local_results and not provider_suggestions:
            embed.description += "\n\nNo comparable genre metadata or provider recommendations were returned. Try a different starting title or provider."
        embed.set_footer(text="Sources: AniList · Google Books · TMDB · Provider recommendations are labelled separately")
        await interaction.followup.send(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(CrossMediaRecommendations(bot))
