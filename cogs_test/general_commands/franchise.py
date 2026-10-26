"""Provider-attributed relationship explorer for anime, manga, books, movies, and TV."""
from __future__ import annotations

import asyncio
import logging
import os
import re

import aiohttp
import discord
from discord import app_commands
from discord.ext import commands

from helpers.command_error_handler import FeedbackAwareView
from helpers.anilist_helper import fetch_media_by_id, fetch_media_by_search
from cogs.media.browse import BrowseCog
from cogs_test.general_commands.dashboard import command_meta

log = logging.getLogger(__name__)


def media_title(item: dict) -> str:
    title = item.get("title") or {}
    if isinstance(title, dict):
        return title.get("english") or title.get("romaji") or title.get("native") or item.get("name") or "Untitled"
    return str(title or item.get("name") or "Untitled")


def _anilist_relation_edges(media: dict) -> list[dict]:
    return ((media.get("relations") or {}).get("edges") or [])


def relation_embed(media: dict, page: int = 0) -> discord.Embed:
    """Display provider-declared relations and keep recommendation links distinct."""
    title = media_title(media)
    provider = str(media.get("_provider") or "AniList")
    edges = _anilist_relation_edges(media)
    provider_related = media.get("_provider_related") or []
    all_items = [
        {
            "title": media_title(edge.get("node") or {}),
            "url": (edge.get("node") or {}).get("siteUrl"),
            "relationType": str(edge.get("relationType") or "RELATED").replace("_", " ").title(),
            "type": (edge.get("node") or {}).get("type") or "Unknown type",
            "status": (edge.get("node") or {}).get("status") or "Status unavailable",
            "date": None,
            "source": "AniList relationship",
        }
        for edge in edges
    ] + list(provider_related)
    embed = discord.Embed(
        title=f"🧬 Franchise · {title}"[:256],
        url=media.get("siteUrl"),
        description="Related entries use their provider's own labels. Cross-provider title matches and recommendation-only links are explicitly unverified, and no chapter-to-episode mapping is inferred.",
        color=discord.Color.blurple(),
    )
    if media.get("description"):
        embed.description = str(media["description"]).replace("<br>", "\n").replace("<i>", "").replace("</i>", "")[:800]
        embed.description += "\n\nRelationships are attributed to their metadata provider; release dates do not imply chronological story order."
    cover = (media.get("coverImage") or {}).get("large")
    if cover:
        embed.set_thumbnail(url=cover)

    if not all_items:
        embed.add_field(
            name="No provider-declared relationships",
            value=(
                "The selected provider does not expose related entries for this title. "
                "The bot will not infer sequels, source novels, or adaptations from similar names."
            ),
            inline=False,
        )
    else:
        page_size = 8
        start = page * page_size
        visible = all_items[start:start + page_size]
        lines = []
        for item in visible:
            name = str(item.get("title") or "Untitled")
            url = item.get("url")
            linked = f"[{name}]({url})" if url else name
            kind = item.get("type") or ""
            status = item.get("status") or ""
            date = item.get("date")
            relation = item.get("relationType") or "RELATED"
            details = " · ".join(str(v) for v in (kind, status, date) if v)
            line = f"**{relation}**" + (f" · {details}" if details else "") + f"\n{linked}"
            if item.get("source"):
                line += f"\nSource: {item['source']}"
            lines.append(line)
        embed.add_field(
            name=f"Related entries ({start + 1}–{start + len(visible)} of {len(all_items)})",
            value="\n\n".join(lines)[:3900],
            inline=False,
        )
        embed.set_footer(text=f"{provider} metadata · Page {page + 1}/{max(1, (len(all_items) - 1) // page_size + 1)}")

    links = media.get("externalLinks") or []
    link_lines = []
    for link in links[:8]:
        label, url = link.get("site"), link.get("url")
        if label and url:
            link_lines.append(f"[{str(label)[:60]}]({url})")
    if media.get("_source_url") and media.get("_source_label"):
        link_lines.append(f"[{media['_source_label']}]({media['_source_url']})")
    if link_lines:
        embed.add_field(name="Provider and external links", value=" · ".join(link_lines)[:1024], inline=False)
    return embed


class RelationView(FeedbackAwareView):
    def __init__(self, media: dict, owner_id: int):
        super().__init__(timeout=180)
        self.media = media
        self.owner_id = owner_id
        relation_count = len(_anilist_relation_edges(media)) + len(media.get("_provider_related") or [])
        self.max_page = max(0, (relation_count - 1) // 8)
        self.page = 0
        self.previous.disabled = True
        self.next.disabled = self.max_page == 0

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message("Only the user who opened this franchise view can navigate it.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="◀ Previous", style=discord.ButtonStyle.secondary)
    async def previous(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        self.page = max(0, self.page - 1)
        self.previous.disabled = self.page == 0
        self.next.disabled = self.page >= self.max_page
        await interaction.response.edit_message(embed=relation_embed(self.media, self.page), view=self)

    @discord.ui.button(label="Next ▶", style=discord.ButtonStyle.secondary)
    async def next(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        self.page = min(self.max_page, self.page + 1)
        self.previous.disabled = self.page == 0
        self.next.disabled = self.page >= self.max_page
        await interaction.response.edit_message(embed=relation_embed(self.media, self.page), view=self)


class FranchiseSelect(discord.ui.Select):
    def __init__(self, owner: "FranchiseSearchView", results: list[dict]):
        self.owner_view = owner
        self.results = {str(item.get("id") or item.get("volumeInfo", {}).get("title")): item for item in results}
        options = []
        for item in results[:25]:
            value = str(item.get("id") or item.get("volumeInfo", {}).get("title") or "")
            if not value:
                continue
            if owner.category == "BOOK":
                info = item.get("volumeInfo") or {}
                subtitle = ", ".join(info.get("authors") or []) or info.get("publisher") or "Google Books"
                label = info.get("title") or "Untitled"
                description = subtitle
            else:
                label = media_title(item)
                if owner.category in ("ANIME", "MANGA"):
                    description = f"{item.get('format') or owner.category} · {item.get('status') or 'Status unavailable'}"
                else:
                    date = item.get("release_date") if owner.category == "MOVIE" else item.get("first_air_date")
                    description = (date[:4] if date else "TMDB result")
            options.append(discord.SelectOption(label=str(label)[:100], value=value[:100], description=str(description)[:100]))
        super().__init__(placeholder="🔎 Choose the intended title", options=options, min_values=1, max_values=1)

    async def callback(self, interaction: discord.Interaction) -> None:
        view = self.owner_view
        if interaction.user.id != view.owner_id:
            await interaction.response.send_message("Only the user who started this search can select a title.", ephemeral=True)
            return
        selected = self.results.get(self.values[0])
        if not selected:
            await interaction.response.send_message("That title is no longer available.", ephemeral=True)
            return
        await interaction.response.defer()
        try:
            if view.category in ("ANIME", "MANGA"):
                media = await fetch_media_by_id(int(selected["id"]), view.category)
            elif view.category in ("MOVIE", "TV"):
                media = await view.cog.fetch_tmdb_relationships(selected, view.category)
            else:
                info = selected.get("volumeInfo") or {}
                url = info.get("infoLink") or selected.get("selfLink")
                image = (info.get("imageLinks") or {}).get("thumbnail")
                media = {
                    "title": info.get("title") or "Untitled",
                    "description": info.get("description") or "",
                    "siteUrl": url,
                    "coverImage": {"large": image} if image else {},
                    "type": "BOOK",
                    "_provider": "Google Books",
                    "_source_url": url,
                    "_source_label": "Google Books",
                    "_provider_related": [],
                }
                authors = info.get("authors") or []
                if authors:
                    media["description"] = f"Authors: {', '.join(authors)}\n\n" + media["description"]
            if not media:
                await interaction.edit_original_response(content="The selected provider could not load relationship metadata.", embed=None, view=None)
                return
        except (aiohttp.ClientError, asyncio.TimeoutError, ValueError, KeyError):
            log.exception("Franchise metadata request failed for category %s", view.category)
            await interaction.edit_original_response(content="The metadata provider failed while loading this title. Please try again later.", embed=None, view=None)
            return
        try:
            await view.cog.enrich_cross_provider_matches(media, view.category)
        except (aiohttp.ClientError, asyncio.TimeoutError, ValueError):
            log.warning("Cross-provider franchise enrichment failed", exc_info=True)
        relation_view = RelationView(media, view.owner_id)
        await interaction.edit_original_response(content=None, embed=relation_embed(media), view=relation_view)


class FranchiseSearchView(FeedbackAwareView):
    def __init__(self, owner_id: int, category: str, results: list[dict], cog: "Franchise"):
        super().__init__(timeout=180)
        self.owner_id = owner_id
        self.category = category
        self.cog = cog
        self.add_item(FranchiseSelect(self, results))


class Franchise(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.browse = BrowseCog(bot)

    @staticmethod
    def _normalized_title(value: str) -> str:
        return re.sub(r"\W+", " ", (value or "").casefold()).strip()

    async def enrich_cross_provider_matches(self, media: dict, category: str) -> None:
        """Add exact-title matches from other providers, never claiming verified adaptations."""
        source_title = media_title(media)
        normalized = self._normalized_title(source_title)
        if not normalized:
            return
        if category == "ANIME":
            anilist_types = ["MANGA"]
            tmdb_types = ["MOVIE", "TV"]
        elif category == "MANGA":
            anilist_types = ["ANIME"]
            tmdb_types = ["MOVIE", "TV"]
        elif category == "MOVIE":
            anilist_types = ["ANIME", "MANGA"]
            tmdb_types = ["TV"]
        elif category == "TV":
            anilist_types = ["ANIME", "MANGA"]
            tmdb_types = ["MOVIE"]
        else:
            anilist_types = ["ANIME", "MANGA"]
            tmdb_types = ["MOVIE", "TV"]

        jobs = []
        job_descriptors = []
        for target_type in anilist_types:
            jobs.append(fetch_media_by_search(source_title, target_type, per_page=8))
            job_descriptors.append(("anilist", target_type))
        for target_type in tmdb_types:
            jobs.append(self.browse.search_tmdb_titles(source_title, target_type))
            job_descriptors.append(("tmdb", target_type))
        if category != "BOOK":
            jobs.append(self.browse.fetch_book_results(source_title, "fiction"))
            job_descriptors.append(("books-fiction", "BOOK"))
            jobs.append(self.browse.fetch_book_results(source_title, "nonfiction"))
            job_descriptors.append(("books-nonfiction", "BOOK"))

        results = await asyncio.gather(*jobs, return_exceptions=True)
        existing = list(media.get("_provider_related") or [])
        seen = {
            str(item.get("url") or "").casefold()
            for item in existing if item.get("url")
        }
        for descriptor, result in zip(job_descriptors, results):
            if isinstance(result, Exception):
                log.debug("Cross-provider title matching failed for %s: %r", descriptor, result)
                continue
            provider_key, target_type = descriptor
            for candidate in result or []:
                if provider_key == "anilist":
                    titles = [
                        (candidate.get("title") or {}).get("english"),
                        (candidate.get("title") or {}).get("romaji"),
                        (candidate.get("title") or {}).get("native"),
                    ]
                    candidate_title = next((value for value in titles if value), None)
                    url = candidate.get("siteUrl")
                    candidate_type = target_type.title()
                    status = candidate.get("status")
                    cover = (candidate.get("coverImage") or {}).get("large")
                    source_name = "AniList"
                elif provider_key.startswith("books-"):
                    info = candidate.get("volumeInfo") or {}
                    candidate_title = info.get("title")
                    url = info.get("infoLink") or candidate.get("selfLink")
                    authors = info.get("authors") or []
                    status = ", ".join(authors) if authors else None
                    candidate_type = "Book / novel"
                    cover = (info.get("imageLinks") or {}).get("thumbnail")
                    source_name = "Google Books"
                else:
                    candidate_title = (
                        candidate.get("title") if target_type == "MOVIE" else candidate.get("name")
                    )
                    alternatives = [
                        candidate_title, candidate.get("original_title"),
                        candidate.get("original_name"), candidate.get("title"), candidate.get("name"),
                    ]
                    candidate_title = next((value for value in alternatives if value and self._normalized_title(value) == normalized), candidate_title)
                    candidate_id = candidate.get("id")
                    url = f"https://www.themoviedb.org/{'movie' if target_type == 'MOVIE' else 'tv'}/{candidate_id}" if candidate_id else None
                    status = candidate.get("release_date") if target_type == "MOVIE" else candidate.get("first_air_date")
                    candidate_type = "Movie" if target_type == "MOVIE" else "TV series"
                    cover = f"https://image.tmdb.org/t/p/w500{candidate['poster_path']}" if candidate.get("poster_path") else None
                    source_name = "TMDB"
                if not candidate_title or self._normalized_title(str(candidate_title)) != normalized:
                    continue
                if url and url.casefold() in seen:
                    continue
                if url:
                    seen.add(url.casefold())
                entry = {
                    "title": str(candidate_title)[:256],
                    "url": url,
                    "relationType": "Exact-title match · adaptation relationship unverified",
                    "type": candidate_type,
                    "status": status,
                    "date": None,
                    "source": f"{source_name} title match only",
                }
                if cover:
                    entry["image"] = cover
                existing.append(entry)
                if len(existing) >= 24:
                    break
            if len(existing) >= 24:
                break
        media["_provider_related"] = existing

    async def search_options(self, title: str, category: str) -> list[dict]:
        if category in ("ANIME", "MANGA"):
            return await fetch_media_by_search(title, category, per_page=10)
        if category in ("MOVIE", "TV"):
            return await self.browse.search_tmdb_titles(title, category)
        fiction, nonfiction = await asyncio.gather(
            self.browse.fetch_book_results(title, "fiction"),
            self.browse.fetch_book_results(title, "nonfiction"),
        )
        books = {}
        for item in [*fiction, *nonfiction]:
            info = item.get("volumeInfo") or {}
            key = (info.get("title") or "").casefold(), tuple(info.get("authors") or [])
            if info.get("title"):
                books[key] = item
        return list(books.values())[:10]

    async def fetch_tmdb_relationships(self, selected: dict, category: str) -> dict | None:
        token = os.getenv("TMDB_BEARER_TOKEN", "").strip()
        media_id = selected.get("id")
        if not token or not media_id:
            return None
        is_movie = category == "MOVIE"
        endpoint = "movie" if is_movie else "tv"
        headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
        params = {"language": "en-US"}
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=12)) as session:
                async with session.get(f"https://api.themoviedb.org/3/{endpoint}/{media_id}", headers=headers, params=params) as response:
                    if response.status != 200:
                        return None
                    media = await response.json(content_type=None)
                title = media.get("title") if is_movie else media.get("name")
                tmdb_url = f"https://www.themoviedb.org/{endpoint}/{media_id}"
                related: list[dict] = []
                if is_movie and (media.get("belongs_to_collection") or {}).get("id"):
                    collection_id = media["belongs_to_collection"]["id"]
                    async with session.get(f"https://api.themoviedb.org/3/collection/{collection_id}", headers=headers, params=params) as response:
                        if response.status == 200:
                            collection = await response.json(content_type=None)
                            for part in collection.get("parts") or []:
                                release_date = part.get("release_date") or ""
                                related.append({
                                    "title": part.get("title") or "Untitled",
                                    "url": f"https://www.themoviedb.org/movie/{part['id']}" if part.get("id") else None,
                                    "relationType": "Collection member",
                                    "type": "Movie",
                                    "status": None,
                                    "date": release_date or None,
                                    "source": "TMDB collection",
                                    "_sort": release_date,
                                })
                    # The collection order is reported by TMDB. Release dates are displayed
                    # for reference; they are not treated as in-universe chronology.
                    related.sort(key=lambda item: item.get("_sort") or "9999-99-99")
                    for item in related:
                        item.pop("_sort", None)
                    relation_source = "TMDB collection"
                else:
                    field = "recommendations" if is_movie else "recommendations"
                    results = await self._tmdb_recommendations(session, endpoint, media_id, headers)
                    for entry in results:
                        entry_title = entry.get("title") if is_movie else entry.get("name")
                        entry_id = entry.get("id")
                        if not entry_title or not entry_id:
                            continue
                        related.append({
                            "title": entry_title,
                            "url": f"https://www.themoviedb.org/{endpoint}/{entry_id}",
                            "relationType": "TMDB recommendation · not a confirmed franchise link",
                            "type": "Movie" if is_movie else "TV",
                            "status": None,
                            "date": entry.get("release_date") if is_movie else entry.get("first_air_date"),
                            "source": "TMDB recommendations",
                        })
                    relation_source = "TMDB recommendations"
                cover_path = media.get("poster_path")
                return {
                    "title": title or media_title(selected),
                    "description": media.get("overview") or "",
                    "siteUrl": tmdb_url,
                    "coverImage": {"large": f"https://image.tmdb.org/t/p/w500{cover_path}"} if cover_path else {},
                    "type": category,
                    "status": media.get("status"),
                    "_provider": relation_source,
                    "_provider_related": related,
                    "_source_url": tmdb_url,
                    "_source_label": "TMDB",
                }
        except (aiohttp.ClientError, asyncio.TimeoutError, ValueError):
            log.exception("TMDB franchise lookup failed for id %s", media_id)
            return None

    @staticmethod
    async def _tmdb_recommendations(session: aiohttp.ClientSession, endpoint: str, media_id: int, headers: dict) -> list[dict]:
        async with session.get(
            f"https://api.themoviedb.org/3/{endpoint}/{media_id}/recommendations",
            headers=headers, params={"language": "en-US", "page": 1},
        ) as response:
            if response.status != 200:
                return []
            payload = await response.json(content_type=None)
            return (payload.get("results") or [])[:16] if isinstance(payload, dict) else []

    @app_commands.command(name="franchise", description="Explore provider-declared media relationships and adaptations")
    @app_commands.guild_only()
    @app_commands.choices(category=[
        app_commands.Choice(name="Anime", value="ANIME"),
        app_commands.Choice(name="Manga / manhwa / manhua", value="MANGA"),
        app_commands.Choice(name="Movies", value="MOVIE"),
        app_commands.Choice(name="TV shows", value="TV"),
        app_commands.Choice(name="Books and novels", value="BOOK"),
    ])
    @app_commands.describe(title="Title to explore", category="Metadata provider to search")
    @command_meta(section="Media Discovery", name="Franchise")
    async def franchise(self, interaction: discord.Interaction, title: str, category: str = "ANIME") -> None:
        title = " ".join((title or "").split())
        if not title:
            await interaction.response.send_message("Enter a title to explore.", ephemeral=True)
            return
        if category in ("MOVIE", "TV") and not os.getenv("TMDB_BEARER_TOKEN", "").strip():
            await interaction.response.send_message("Movies and TV relationships require TMDB_BEARER_TOKEN.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            results = await self.search_options(title, category)
        except (aiohttp.ClientError, asyncio.TimeoutError, ValueError):
            log.exception("Franchise search failed for %r (%s)", title, category)
            results = []
        if not results:
            await interaction.followup.send(
                f"No {category.lower()} match was found for {title!r}, or the provider is unavailable. Try an alternate title or check its API configuration.",
                ephemeral=True,
            )
            return
        view = FranchiseSearchView(interaction.user.id, category, results, self)
        await interaction.followup.send(
            "🧬 **Choose the exact title.** AniList relationships and TMDB collection membership are shown as provider metadata; TMDB recommendations are labelled separately. Google Books does not expose a reliable adaptation graph, so the book view only shows its edition/source link.",
            view=view, ephemeral=True,
        )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Franchise(bot))
