"""Provider-attributed relationship explorer for anime, manga, books, movies, and TV."""
from __future__ import annotations

import asyncio
import logging
import os
import re

import aiohttp
import discord
import database
from discord import app_commands
from discord.ext import commands

from helpers.command_error_handler import FeedbackAwareView, handle_application_command_error
from helpers.anilist_helper import fetch_media_by_id, fetch_media_by_search
from cogs.media.browse import BrowseCog, search_novelupdates
from cogs_test.general_commands.dashboard import command_meta
from helpers.media_graph import find_linked_resources, find_media_relationships, normalize_media_title, record_media_relationship

log = logging.getLogger(__name__)


def media_title(item: dict) -> str:
    title = item.get("title") or {}
    if isinstance(title, dict):
        return title.get("english") or title.get("romaji") or title.get("native") or item.get("name") or "Untitled"
    return str(title or item.get("name") or "Untitled")


def _ani_release_date(item: dict) -> str | None:
    value = item.get("startDate") or {}
    year = value.get("year")
    if not year:
        return None
    parts = [f"{int(year):04d}"]
    if value.get("month"):
        parts.append(f"{int(value['month']):02d}")
        if value.get("day"):
            parts.append(f"{int(value['day']):02d}")
    return "-".join(parts)


def _has_full_release_date(item: dict) -> bool:
    value = item.get("startDate") or {}
    return all(value.get(key) for key in ("year", "month", "day"))


def _ani_release_sort(item: dict) -> tuple[int, int, int]:
    value = item.get("startDate") or {}
    return (int(value.get("year") or 0), int(value.get("month") or 0), int(value.get("day") or 0))


def _anilist_relation_edges(media: dict) -> list[dict]:
    return ((media.get("relations") or {}).get("edges") or [])


def relation_embed(media: dict, page: int = 0) -> discord.Embed:
    """Display provider-declared relations and keep recommendation links distinct."""
    title = media_title(media)
    provider = str(media.get("_provider") or "AniList")
    edges = _anilist_relation_edges(media)
    provider_related = media.get("_provider_related") or []
    graph_related = media.get("_graph_related") or []
    all_items = [
        {
            "title": media_title(edge.get("node") or {}),
            "url": (edge.get("node") or {}).get("siteUrl"),
            "relationType": str(edge.get("relationType") or "RELATED").replace("_", " ").title(),
            "type": (edge.get("node") or {}).get("type") or "Unknown type",
            "status": (edge.get("node") or {}).get("status") or "Status unavailable",
            "date": _ani_release_date(edge.get("node") or {}),
            "source": "AniList relationship",
        }
        for edge in edges
    ] + list(provider_related)
    existing_relation_keys = {
        (normalize_media_title(item.get("title")), str(item.get("type") or "").upper(), str(item.get("url") or ""))
        for item in all_items
    }
    for item in graph_related:
        key = (normalize_media_title(item.get("title")), str(item.get("type") or "").upper(), str(item.get("url") or ""))
        if key not in existing_relation_keys:
            all_items.append(item)
            existing_relation_keys.add(key)
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
            status = item.get("status")
            date = item.get("date")
            relation = item.get("relationType") or "RELATED"
            details_parts = [str(kind)] if kind else []
            if status:
                details_parts.append(f"Status/date: {status}")
            if date:
                details_parts.append(f"Release: {date}")
            if item.get("creators"):
                details_parts.append(f"Creators: {item['creators']}")
            details = " · ".join(details_parts)
            line = f"**{relation}**" + (f" · {details}" if details else "") + f"\n{linked}"
            if item.get("source"):
                line += f"\nSource: {item['source']}"
            lines.append(line)
        embed.add_field(
            name=f"Related entries ({start + 1}–{start + len(visible)} of {len(all_items)})",
            value="\n\n".join(lines)[:1024],
            inline=False,
        )
        embed.set_footer(text=f"{provider} metadata · Page {page + 1}/{max(1, (len(all_items) - 1) // page_size + 1)}")

    # A release order is shown only when every AniList entry has an exact release
    # date. It is never presented as chronological story order.
    if edges and _has_full_release_date(media) and all(_has_full_release_date(edge.get("node") or {}) for edge in edges):
        order_items = [media] + [edge.get("node") or {} for edge in edges]
        order_items.sort(key=lambda item: (_ani_release_sort(item), media_title(item).casefold()))
        order_lines = []
        for index, item in enumerate(order_items[:15], 1):
            label = media_title(item)
            url = item.get("siteUrl")
            if url:
                label = f"[{label}]({url})"
            order_lines.append(f"{index}. {label} · {_ani_release_date(item)}")
        if order_lines:
            embed.add_field(
                name="AniList release order · not story chronology",
                value="\n".join(order_lines)[:1024],
                inline=False,
            )

    collection_items = [
        item for item in provider_related
        if item.get("source") == "TMDB collection" and item.get("date")
    ]
    all_collection_items = [item for item in provider_related if item.get("source") == "TMDB collection"]
    if len(all_collection_items) > 1 and len(collection_items) == len(all_collection_items) and all(len(str(item.get("date"))) >= 10 for item in collection_items):
        collection_items.sort(key=lambda item: (str(item.get("date")), str(item.get("title") or "").casefold()))
        order_lines = []
        for index, item in enumerate(collection_items[:15], 1):
            label = str(item.get("title") or "Untitled")
            if item.get("url"):
                label = f"[{label}]({item['url']})"
            order_lines.append(f"{index}. {label} · {item['date']}")
        if order_lines:
            embed.add_field(
                name="TMDB collection release order · not story chronology",
                value="\n".join(order_lines)[:1024],
                inline=False,
            )

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

    resources = media.get("_community_resources") or []
    if resources:
        resource_lines = []
        for resource in resources[:8]:
            label = str(resource.get("title") or "Untitled resource").replace("[", "").replace("]", "").replace("(", "").replace(")", "")
            if resource.get("url"):
                label = f"[{label}]({resource['url']})"
            resource_lines.append(f"**{str(resource.get('kind') or 'Community resource')[:60]}** · {label}\nSource: {resource.get('source') or 'Lemegeton'}")
        embed.add_field(name="Connected community resources", value="\n\n".join(resource_lines)[:1024], inline=False)
    return embed


class RelationView(FeedbackAwareView):
    def __init__(self, media: dict, owner_id: int):
        super().__init__(timeout=180)
        self.media = media
        self.owner_id = owner_id
        relation_count = (
            len(_anilist_relation_edges(media))
            + len(media.get("_provider_related") or [])
            + len(media.get("_graph_related") or [])
        )
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
        self.results = {
            str(item.get("id") or item.get("volumeInfo", {}).get("title") or (item.get("url") if owner.category == "WEBNOVEL" else item.get("title")) or "")[:100]: item
            for item in results
        }
        options = []
        for item in results[:25]:
            value = str(item.get("id") or item.get("volumeInfo", {}).get("title") or (item.get("url") if owner.category == "WEBNOVEL" else item.get("title")) or "")
            if not value:
                continue
            if owner.category == "BOOK":
                info = item.get("volumeInfo") or {}
                subtitle = ", ".join(info.get("authors") or []) or info.get("publisher") or "Google Books"
                label = info.get("title") or "Untitled"
                description = subtitle
            else:
                label = media_title(item)
                if owner.category in ("ANIME", "MANGA", "LIGHT_NOVEL"):
                    description = f"{item.get('format') or owner.category} · {item.get('status') or 'Status unavailable'}"
                elif owner.category == "WEBNOVEL":
                    description = f"{item.get('author') or 'Author unavailable'} · {item.get('status') or 'Status unavailable'}"
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
            if view.category in ("ANIME", "MANGA", "LIGHT_NOVEL"):
                ani_type = "ANIME" if view.category == "ANIME" else "MANGA"
                media = await fetch_media_by_id(int(selected["id"]), ani_type)
            elif view.category in ("MOVIE", "TV"):
                media = await view.cog.fetch_tmdb_relationships(selected, view.category)
            elif view.category == "WEBNOVEL":
                url = selected.get("url")
                image = selected.get("image")
                details = []
                if selected.get("author"):
                    details.append(f"Author: {selected['author']}")
                if selected.get("status"):
                    details.append(f"Status: {selected['status']}")
                if selected.get("genres"):
                    details.append("Genres: " + ", ".join(str(value) for value in selected["genres"]))
                if selected.get("description"):
                    details.append(str(selected["description"]))
                media = {
                    "title": selected.get("title") or "Untitled",
                    "description": "\n\n".join(details),
                    "siteUrl": url,
                    "coverImage": {"large": image} if image else {},
                    "type": "WEBNOVEL",
                    "_provider": "Novel Updates",
                    "_source_url": url,
                    "_source_label": "Novel Updates",
                    "_provider_related": [],
                }
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
        try:
            await view.cog.enrich_community_links(media, view.category, interaction.guild_id)
        except Exception:
            log.debug("Community relationship enrichment failed", exc_info=True)
        try:
            await view.cog.index_and_load_graph(media, view.category, interaction.guild_id)
        except Exception:
            log.warning("Cross-system relationship graph lookup failed", exc_info=True)
            media["_graph_related"] = []
            media["_community_resources"] = []
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

    @staticmethod
    def _relationship_url_key(value: str | None) -> str:
        from urllib.parse import urlsplit
        parsed = urlsplit(str(value or "").strip())
        if parsed.scheme.lower() != "https" or not parsed.hostname:
            return ""
        host = (parsed.hostname or "").lower()
        if host.startswith("www."):
            host = host[4:]
        return f"{host}{parsed.path.rstrip('/')}".casefold()

    async def enrich_community_links(self, media: dict, category: str, guild_id: int | None) -> None:
        """Add only this server's approved community links, clearly not provider-confirmed."""
        if not guild_id:
            return
        try:
            rows = await database.execute_db_operation(
                "load approved community media links for guild",
                """SELECT source_title, source_category, source_url, relationship_type,
                          target_title, target_category, target_url
                   FROM media_link_suggestions
                   WHERE guild_id = ? AND status = 'approved'
                   ORDER BY reviewed_at DESC NULLS LAST, id DESC LIMIT 100""",
                (guild_id,), fetch_type="all",
            ) or []
        except Exception:
            # The ConnectedMedia cog may not have initialized its table yet, or an
            # older deployment may not have upgraded. Provider-backed relations still work.
            log.debug("Community link suggestions table is unavailable", exc_info=True)
            return

        current_title = self._normalized_title(media_title(media))
        current_category = str(category or "").upper()
        current_url = self._relationship_url_key(media.get("_source_url") or media.get("siteUrl"))
        if not current_title:
            return
        related = media.setdefault("_provider_related", [])
        existing_urls = {
            self._relationship_url_key(item.get("url"))
            for item in related if item.get("url")
        }
        labels = {
            "ANIME": "Anime", "MANGA": "Manga / manhwa / manhua",
            "LIGHT_NOVEL": "Light novel", "WEBNOVEL": "Webnovel",
            "BOOK": "Book / novel", "MOVIE": "Movie", "TV": "TV series",
        }
        added = 0
        for row in rows:
            item = dict(row)
            src_title = str(item.get("source_title") or "")
            dst_title = str(item.get("target_title") or "")
            src_category = str(item.get("source_category") or "").upper()
            dst_category = str(item.get("target_category") or "").upper()
            src_url = self._relationship_url_key(item.get("source_url"))
            dst_url = self._relationship_url_key(item.get("target_url"))
            if (
                self._normalized_title(src_title) == current_title
                and src_category == current_category
                and (not current_url or current_url == src_url)
            ):
                title, url, kind = dst_title, item.get("target_url"), dst_category
            elif (
                self._normalized_title(dst_title) == current_title
                and dst_category == current_category
                and (not current_url or current_url == dst_url)
            ):
                title, url, kind = src_title, item.get("source_url"), src_category
            else:
                continue
            url_key = self._relationship_url_key(url)
            if not title or not url or (url_key and url_key in existing_urls):
                continue
            related.append({
                "title": title,
                "url": url,
                "relationType": f"Community-verified: {item.get('relationship_type') or 'related'} (not provider-confirmed)",
                "type": labels.get(kind, kind.title()),
                "status": None,
                "date": None,
                "source": "Community suggestion approved in this server",
            })
            existing_urls.add(url_key)
            added += 1
            if added >= 10 or len(related) >= 34:
                break

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
        if category != "WEBNOVEL":
            jobs.append(asyncio.wait_for(search_novelupdates(source_title), timeout=45))
            job_descriptors.append(("novelupdates", "WEBNOVEL"))

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
                    status = None
                    candidate_type = "Book / novel"
                    cover = (info.get("imageLinks") or {}).get("thumbnail")
                    source_name = "Google Books"
                elif provider_key == "novelupdates":
                    candidate_title = candidate.get("title")
                    url = candidate.get("url")
                    status = candidate.get("status") or candidate.get("author")
                    candidate_type = "Webnovel"
                    cover = candidate.get("image")
                    source_name = "Novel Updates"
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
                    "creators": ", ".join(authors[:4]) if provider_key.startswith("books-") and authors else (
                        str(candidate.get("author")) if provider_key == "novelupdates" and candidate.get("author") else None
                    ),
                }
                if cover:
                    entry["image"] = cover
                existing.append(entry)
                if len(existing) >= 24:
                    break
            if len(existing) >= 24:
                break
        media["_provider_related"] = existing

    async def index_and_load_graph(self, media: dict, category: str, guild_id: int | None) -> None:
        """Index only provider-declared relations and load safe, visible graph neighbors."""
        source_title = media_title(media)
        source_url = media.get("_source_url") or media.get("siteUrl")
        for edge in _anilist_relation_edges(media):
            node = edge.get("node") or {}
            if not node:
                continue
            target_category = str(node.get("type") or "").upper()
            if target_category == "MANGA" and str(node.get("format") or "").upper() == "NOVEL":
                target_category = "LIGHT_NOVEL"
            try:
                await record_media_relationship(
                    source_title, category, source_url,
                    media_title(node), target_category, node.get("siteUrl"),
                    str(edge.get("relationType") or "related"),
                    source_kind="provider", source_label="AniList provider relationship",
                )
            except Exception:
                log.debug("Could not index AniList relation for %s", source_title, exc_info=True)

        for item in media.get("_provider_related") or []:
            if item.get("source") != "TMDB collection":
                continue
            target_category = str(item.get("type") or "Movie").upper()
            if target_category not in {"MOVIE", "TV"}:
                target_category = "MOVIE" if "MOVIE" in target_category or "FILM" in target_category else "TV"
            try:
                await record_media_relationship(
                    source_title, category, source_url,
                    str(item.get("title") or ""), target_category, item.get("url"),
                    str(item.get("relationType") or "collection member"),
                    source_kind="provider", source_label="TMDB collection membership",
                )
            except Exception:
                log.debug("Could not index TMDB collection member for %s", source_title, exc_info=True)

        media["_graph_related"], media["_community_resources"] = await asyncio.gather(
            find_media_relationships(source_title, category, source_url, guild_id),
            find_linked_resources(
                source_title,
                category,
                guild_id,
                media_id=int(media["id"]) if str(media.get("id") or "").isdigit() and category in {"MANGA", "LIGHT_NOVEL"} else None,
                url=source_url,
            ),
        )

    async def search_options(self, title: str, category: str) -> list[dict]:
        if category in ("ANIME", "MANGA", "LIGHT_NOVEL"):
            ani_type = "ANIME" if category == "ANIME" else "MANGA"
            results = await fetch_media_by_search(title, ani_type, per_page=10)
            if category == "LIGHT_NOVEL":
                return [item for item in results if str(item.get("format") or "").upper() == "NOVEL"]
            if category == "MANGA":
                return [item for item in results if str(item.get("format") or "").upper() != "NOVEL"]
            return results
        if category == "WEBNOVEL":
            return await asyncio.wait_for(search_novelupdates(title), timeout=45)
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
        app_commands.Choice(name="Light novels", value="LIGHT_NOVEL"),
        app_commands.Choice(name="Movies", value="MOVIE"),
        app_commands.Choice(name="TV shows", value="TV"),
        app_commands.Choice(name="Books and novels", value="BOOK"),
        app_commands.Choice(name="Webnovels (Novel Updates)", value="WEBNOVEL"),
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
        except Exception:
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
            "🧬 **Choose the exact title.** AniList relationships and TMDB collection membership are shown as provider metadata; TMDB recommendations and exact-title cross-provider matches are labelled separately. Google Books and Novel Updates do not expose a reliable adaptation graph, so those entries link to source metadata without invented relationships.",
            view=view, ephemeral=True,
        )


    async def cog_app_command_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError) -> None:
        """Report unexpected provider and graph failures without exposing internals."""
        await handle_application_command_error(interaction, error)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Franchise(bot))
