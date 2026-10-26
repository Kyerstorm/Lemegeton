"""Connected cross-media commands backed by existing providers and PostgreSQL."""
from __future__ import annotations

import asyncio
import logging
import os
import re
from urllib.parse import quote_plus, urlsplit

import aiohttp
import discord
from discord import app_commands
from discord.ext import commands

import database
from cogs.media.browse import TMDB_API_BASE_URL, TMDB_IMAGE_BASE_URL, search_novelupdates
from helpers.media_graph import record_media_relationship
from cogs_test.general_commands.dashboard import command_meta

log = logging.getLogger("Lemegeton.ConnectedMedia")
TMDB_TIMEOUT = aiohttp.ClientTimeout(total=12)
MEDIA_CATEGORIES = [
    app_commands.Choice(name="Anime", value="ANIME"),
    app_commands.Choice(name="Manga / manhwa / manhua", value="MANGA"),
    app_commands.Choice(name="Light novels", value="LIGHT_NOVEL"),
    app_commands.Choice(name="Books and novels", value="BOOK"),
    app_commands.Choice(name="Webnovels", value="WEBNOVEL"),
    app_commands.Choice(name="Movies", value="MOVIE"),
    app_commands.Choice(name="TV series", value="TV"),
    app_commands.Choice(name="Video games", value="GAME"),
]
RELATION_TYPES = [
    app_commands.Choice(name="Adaptation", value="adaptation"),
    app_commands.Choice(name="Source material", value="source material"),
    app_commands.Choice(name="Sequel", value="sequel"),
    app_commands.Choice(name="Prequel", value="prequel"),
    app_commands.Choice(name="Spin-off", value="spin-off"),
    app_commands.Choice(name="Side story", value="side story"),
    app_commands.Choice(name="Other (explain in evidence)", value="other"),
]


def normalize_title(value: str) -> str:
    """Normalize punctuation and whitespace for candidate matching, not proof of a link."""
    return re.sub(r"\W+", " ", (value or "").casefold(), flags=re.UNICODE).strip()


def validate_https_url(value: str | None, *, required: bool = False) -> str | None:
    """Accept complete HTTPS links without embedded usernames/passwords."""
    value = (value or "").strip()
    if not value:
        if required:
            raise ValueError("Provide a source URL.")
        return None
    parsed = urlsplit(value)
    if (
        parsed.scheme.lower() != "https"
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or len(value) > 1000
    ):
        raise ValueError("Use a complete HTTPS URL without embedded credentials (maximum 1,000 characters).")
    return value


def _safe_link_title(value: str | None) -> str:
    return discord.utils.escape_markdown(" ".join(str(value or "").split())[:180])


def _tmdb_token() -> str:
    return os.getenv("TMDB_BEARER_TOKEN", "").strip()


async def _tmdb_get(path: str, params: dict | None = None) -> dict | None:
    """Fetch one documented TMDB endpoint with bounded timeouts and no secret logging."""
    token = _tmdb_token()
    if not token:
        return None
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
    try:
        async with aiohttp.ClientSession(timeout=TMDB_TIMEOUT) as session:
            async with session.get(
                f"{TMDB_API_BASE_URL.rstrip('/')}/{path.lstrip('/')}",
                headers=headers,
                params=params or {"language": "en-US"},
            ) as response:
                if response.status != 200:
                    log.info("TMDB endpoint %s returned HTTP %s", path, response.status)
                    return None
                payload = await response.json(content_type=None)
                return payload if isinstance(payload, dict) else None
    except (aiohttp.ClientError, asyncio.TimeoutError, ValueError):
        log.warning("TMDB request failed for endpoint %s", path, exc_info=True)
        return None


async def _tmdb_search(query: str, media_type: str) -> list[dict]:
    endpoint = {"MOVIE": "search/movie", "TV": "search/tv", "PERSON": "search/person"}.get(media_type)
    if not endpoint:
        return []
    payload = await _tmdb_get(endpoint, {"query": query, "language": "en-US", "page": 1, "include_adult": "false"})
    return [item for item in (payload or {}).get("results", []) if isinstance(item, dict) and item.get("id")][:10]


def _tmdb_title(item: dict, media_type: str) -> str:
    if media_type == "PERSON":
        return str(item.get("name") or "Unknown person")
    if media_type in {"MOVIE", "COLLECTION", "VIDEOS_MOVIE"}:
        return str(item.get("title") or "Untitled")
    return str(item.get("name") or "Untitled")


def _tmdb_record_url(item: dict, media_type: str) -> str | None:
    item_id = item.get("id")
    if not item_id:
        return None
    segment = {"MOVIE": "movie", "TV": "tv", "PERSON": "person"}.get(media_type)
    return f"https://www.themoviedb.org/{segment}/{item_id}" if segment else None


def _display_year(item: dict, media_type: str) -> str:
    if media_type == "PERSON":
        return str(item.get("known_for_department") or "Person")
    key = "release_date" if media_type in {"MOVIE", "COLLECTION", "VIDEOS_MOVIE"} else "first_air_date"
    value = str(item.get(key) or "")
    return value[:4] if value else "year unknown"


class _TMDBPicker(discord.ui.View):
    """Owner-bound title selection shared by TMDB commands."""
    def __init__(self, cog: "ConnectedMedia", owner_id: int, kind: str, results: list[dict], region: str = "IE"):
        super().__init__(timeout=150)
        self.cog, self.owner_id, self.kind, self.results, self.region = cog, owner_id, kind, results, region
        options = []
        for result in results[:25]:
            label = _tmdb_title(result, "PERSON" if kind == "PERSON" else kind)
            year = _display_year(result, "PERSON" if kind == "PERSON" else kind)
            options.append(discord.SelectOption(
                label=f"{label[:75]} ({year})"[:100],
                value=str(result["id"]),
                description=str(result.get("overview") or result.get("known_for_department") or "TMDB result")[:100],
            ))
        select = discord.ui.Select(placeholder="Choose the exact result", min_values=1, max_values=1, options=options)
        select.callback = self._choose
        self.add_item(select)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message("Only the person who started this search can choose a result.", ephemeral=True)
            return False
        return True

    async def _choose(self, interaction: discord.Interaction) -> None:
        selected_id = int(self.children[0].values[0])
        selected = next((item for item in self.results if int(item.get("id", 0)) == selected_id), None)
        if not selected:
            await interaction.response.send_message("That result is no longer available. Run the command again.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True, thinking=True)
        if self.kind == "PERSON":
            await self.cog._show_person_credits(interaction, selected)
        elif self.kind == "COLLECTION":
            await self.cog._show_collection(interaction, selected)
        elif self.kind == "VIDEOS_MOVIE":
            await self.cog._show_videos(interaction, selected, "MOVIE")
        elif self.kind == "VIDEOS_TV":
            await self.cog._show_videos(interaction, selected, "TV")
        else:
            await self.cog._show_watch_providers(interaction, selected, self.kind, self.region)


class ConnectedMedia(commands.Cog):
    """Navigation and TMDB utilities layered over existing Lemegeton provider helpers."""
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._schema_ready = False
        self._schema_lock = asyncio.Lock()

    async def cog_load(self) -> None:
        async with self._schema_lock:
            if self._schema_ready:
                return
            await database.execute_db_operation(
                "create connected media guild settings",
                """CREATE TABLE IF NOT EXISTS connected_media_guild_settings (
                    guild_id BIGINT PRIMARY KEY,
                    release_region VARCHAR(2) NOT NULL DEFAULT 'IE',
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )""",
            )
            await database.execute_db_operation(
                "create connected media relationship suggestions",
                """CREATE TABLE IF NOT EXISTS media_link_suggestions (
                    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
                    guild_id BIGINT NOT NULL,
                    submitter_id BIGINT NOT NULL,
                    source_title VARCHAR(200) NOT NULL,
                    source_category VARCHAR(32) NOT NULL,
                    source_url TEXT NOT NULL,
                    relationship_type VARCHAR(32) NOT NULL,
                    target_title VARCHAR(200) NOT NULL,
                    target_category VARCHAR(32) NOT NULL,
                    target_url TEXT NOT NULL,
                    evidence TEXT NOT NULL,
                    status VARCHAR(16) NOT NULL DEFAULT 'pending',
                    reviewer_id BIGINT,
                    review_reason TEXT,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    reviewed_at TIMESTAMPTZ
                )""",
            )
            await database.execute_db_operation(
                "index media link suggestions by guild and status",
                "CREATE INDEX IF NOT EXISTS media_link_suggestions_guild_status_idx ON media_link_suggestions (guild_id, status, created_at DESC)",
            )
            await database.execute_db_operation(
                "create connected media discussion records",
                """CREATE TABLE IF NOT EXISTS connected_media_discussions (
                    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
                    guild_id BIGINT NOT NULL,
                    channel_id BIGINT NOT NULL,
                    thread_id BIGINT NOT NULL,
                    creator_id BIGINT NOT NULL,
                    media_type VARCHAR(16) NOT NULL,
                    title VARCHAR(200) NOT NULL,
                    reference VARCHAR(100) NOT NULL,
                    source_url TEXT,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )""",
            )
            self._schema_ready = True

    async def _default_region(self, guild_id: int | None) -> str:
        if guild_id is None:
            return "IE"
        row = await database.execute_db_operation(
            "get connected media region", "SELECT release_region FROM connected_media_guild_settings WHERE guild_id = ?",
            (guild_id,), fetch_type="one",
        )
        try:
            return str(row[0]).upper() if row else "IE"
        except (IndexError, TypeError):
            return "IE"

    @app_commands.command(name="media-region", description="Set this server's default country for streaming availability")
    @app_commands.guild_only()
    @app_commands.describe(region="Two-letter country code, for example IE, US, GB, or JP")
    @command_meta(section="Media Discovery", name="Media Region")
    async def media_region(self, interaction: discord.Interaction, region: str) -> None:
        if not interaction.guild_id:
            await interaction.response.send_message("This setting is available inside a server.", ephemeral=True)
            return
        if not getattr(interaction.user.guild_permissions, "manage_guild", False):
            await interaction.response.send_message("Manage Server permission is required to change the media region.", ephemeral=True)
            return
        code = (region or "").strip().upper()
        if not re.fullmatch(r"[A-Z]{2}", code):
            await interaction.response.send_message("Enter a two-letter country code, such as IE or US.", ephemeral=True)
            return
        await database.execute_db_operation(
            "save connected media region",
            """INSERT INTO connected_media_guild_settings (guild_id, release_region)
               VALUES (?, ?) ON CONFLICT (guild_id) DO UPDATE
               SET release_region = EXCLUDED.release_region, updated_at = NOW()""",
            (interaction.guild_id, code),
        )
        await interaction.response.send_message(
            f"Default streaming region saved as **{code}** for this server.",
            ephemeral=True,
        )

    @app_commands.command(name="connections", description="Explore supported relationships between a title and its adaptations")
    @app_commands.guild_only()
    @app_commands.choices(category=MEDIA_CATEGORIES)
    @app_commands.describe(title="Media title to resolve", category="Choose the provider/category to search")
    @command_meta(section="Media Discovery", name="Connections")
    async def connections(self, interaction: discord.Interaction, title: str, category: str = "ANIME") -> None:
        await self._show_franchise_picker(interaction, title, category, reading_order=False)

    @app_commands.command(name="reading-order", description="Explore known release relationships without guessing story chronology")
    @app_commands.guild_only()
    @app_commands.choices(category=MEDIA_CATEGORIES)
    @app_commands.describe(title="Book, webnovel, manga, anime, movie or TV title", category="Provider/category to search")
    @command_meta(section="Media Discovery", name="Reading Order")
    async def reading_order(self, interaction: discord.Interaction, title: str, category: str = "LIGHT_NOVEL") -> None:
        await self._show_franchise_picker(interaction, title, category, reading_order=True)

    async def _show_franchise_picker(self, interaction: discord.Interaction, title: str, category: str, reading_order: bool) -> None:
        title = " ".join((title or "").split())
        if not title:
            await interaction.response.send_message("Enter a title to explore.", ephemeral=True)
            return
        franchise = self.bot.get_cog("Franchise")
        if franchise is None or not hasattr(franchise, "search_options"):
            await interaction.response.send_message("The existing franchise resolver is unavailable. Please try /franchise.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            results = await franchise.search_options(title, category)
        except Exception:
            log.exception("Cross-media resolution failed for category %s", category)
            results = []
        if not results:
            await interaction.followup.send(
                f"No usable {category.lower()} result was returned for {title!r}. The provider may be unavailable, or the title may need an alternate spelling.",
                ephemeral=True,
            )
            return
        from cogs_test.general_commands.franchise import FranchiseSearchView
        note = (
            "Choose the exact title. Provider-declared relationships and TMDB collection membership remain distinct from recommendations."
            if not reading_order else
            "Choose the exact title. The source may expose release relationships, but release order is not story chronology; chapter-to-episode and volume-to-season mappings are never guessed."
        )
        await interaction.followup.send(
            note, view=FranchiseSearchView(interaction.user.id, category, results, franchise), ephemeral=True,
        )

    @app_commands.command(name="where-to-watch", description="Find region-specific TMDB streaming, rental and purchase availability")
    @app_commands.guild_only()
    @app_commands.choices(media_type=[
        app_commands.Choice(name="Movie", value="MOVIE"),
        app_commands.Choice(name="TV series", value="TV"),
    ])
    @app_commands.describe(title="Movie or TV title", media_type="Select the type", region="Optional two-letter country code; defaults to this server's media region")
    @command_meta(section="Media Discovery", name="Where to Watch")
    async def where_to_watch(self, interaction: discord.Interaction, title: str, media_type: str, region: str | None = None) -> None:
        if not _tmdb_token():
            await interaction.response.send_message("Streaming discovery requires TMDB_BEARER_TOKEN.", ephemeral=True)
            return
        code = (region or await self._default_region(interaction.guild_id)).strip().upper()
        if not re.fullmatch(r"[A-Z]{2}", code):
            await interaction.response.send_message("Region must be a two-letter country code, such as IE or US.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True, thinking=True)
        results = await _tmdb_search(title.strip(), media_type)
        if not results:
            await interaction.followup.send("TMDB returned no title results, or the service is unavailable.", ephemeral=True)
            return
        await interaction.followup.send(
            "Choose the exact title to inspect availability in **" + code + "**.",
            view=_TMDBPicker(self, interaction.user.id, media_type, results, code),
            ephemeral=True,
        )

    async def _show_watch_providers(self, interaction: discord.Interaction, item: dict, media_type: str, region: str) -> None:
        segment = "movie" if media_type == "MOVIE" else "tv"
        payload = await _tmdb_get(f"{segment}/{item['id']}/watch/providers")
        result = ((payload or {}).get("results") or {}).get(region.upper())
        if not result:
            await interaction.followup.send(
                f"TMDB reports no watch-provider record for this title in **{region.upper()}**. This does not prove the title is unavailable.",
                ephemeral=True,
            )
            return
        title = _tmdb_title(item, media_type)
        tmdb_url = _tmdb_record_url(item, media_type)
        embed = discord.Embed(
            title=f"Where to watch · {title}"[:256],
            description=f"Region: **{region.upper()}**\nAvailability can change; verify it with the provider.",
            url=tmdb_url, color=discord.Color.blurple(),
        )
        for key, label in (("flatrate", "Streaming"), ("rent", "Rent"), ("buy", "Buy"), ("free", "Free"), ("ads", "Ad-supported")):
            providers = result.get(key) or []
            names = list(dict.fromkeys(str(p.get("provider_name")) for p in providers if p.get("provider_name")))
            if names:
                embed.add_field(name=label, value=", ".join(names[:20])[:1024], inline=False)
        if result.get("link"):
            embed.add_field(name="Availability details", value=f"[Open TMDB / JustWatch provider details]({result['link']})", inline=False)
        embed.set_footer(text="Watch-provider data powered by JustWatch · TMDB metadata")
        await interaction.followup.send(embed=embed, ephemeral=True, allowed_mentions=discord.AllowedMentions.none())

    @app_commands.command(name="person-credits", description="Browse a TMDB actor, director or other credited person's filmography")
    @app_commands.guild_only()
    @app_commands.describe(name="Person to search in TMDB")
    @command_meta(section="Media Discovery", name="Person Credits")
    async def person_credits(self, interaction: discord.Interaction, name: str) -> None:
        if not _tmdb_token():
            await interaction.response.send_message("Person discovery requires TMDB_BEARER_TOKEN.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True, thinking=True)
        results = await _tmdb_search(name.strip(), "PERSON")
        if not results:
            await interaction.followup.send("TMDB returned no people, or the service is unavailable.", ephemeral=True)
            return
        await interaction.followup.send("Choose the correct person; people with similar names are kept separate.", view=_TMDBPicker(self, interaction.user.id, "PERSON", results), ephemeral=True)

    async def _show_person_credits(self, interaction: discord.Interaction, person: dict) -> None:
        payload = await _tmdb_get(f"person/{person['id']}/combined_credits")
        if not payload:
            await interaction.followup.send("TMDB could not retrieve this person's credits.", ephemeral=True)
            return
        credits = (payload.get("cast") or []) + (payload.get("crew") or [])
        deduped: dict[tuple, dict] = {}
        for item in credits:
            category = "MOVIE" if item.get("media_type") == "movie" else "TV"
            title = item.get("title") or item.get("name")
            if title and item.get("id"):
                deduped[(category, item["id"])] = item
        values = sorted(deduped.items(), key=lambda pair: float(pair[1].get("popularity") or 0), reverse=True)[:12]
        lines = []
        for (category, _), item in values:
            title = _tmdb_title(item, category)
            date = item.get("release_date") if category == "MOVIE" else item.get("first_air_date")
            role = item.get("character") or item.get("job") or item.get("department")
            url = _tmdb_record_url(item, category)
            label = f"[{discord.utils.escape_markdown(title)}]({url})" if url else discord.utils.escape_markdown(title)
            lines.append(f"• **{label}** · {category} · {date or 'date unavailable'}" + (f" · {role}" if role else ""))
        embed = discord.Embed(
            title=f"Credits · {person.get('name') or 'Person'}"[:256],
            url=_tmdb_record_url(person, "PERSON"),
            description="\n".join(lines)[:4000] or "TMDB did not return a combined filmography for this person.",
            color=discord.Color.blurple(),
        )
        embed.set_footer(text="Source: TMDB · Popularity is used only to order the displayed credits")
        await interaction.followup.send(embed=embed, ephemeral=True, allowed_mentions=discord.AllowedMentions.none())

    @app_commands.command(name="trailers", description="Find TMDB-listed videos, trailers and teasers for a movie or TV series")
    @app_commands.guild_only()
    @app_commands.choices(media_type=[
        app_commands.Choice(name="Movie", value="MOVIE"),
        app_commands.Choice(name="TV series", value="TV"),
    ])
    @app_commands.describe(title="Title to search", media_type="Movie or TV series")
    @command_meta(section="Media Discovery", name="Trailers")
    async def trailers(self, interaction: discord.Interaction, title: str, media_type: str) -> None:
        if not _tmdb_token():
            await interaction.response.send_message("Video discovery requires TMDB_BEARER_TOKEN.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True, thinking=True)
        results = await _tmdb_search(title.strip(), media_type)
        if not results:
            await interaction.followup.send("TMDB returned no title results, or the service is unavailable.", ephemeral=True)
            return
        await interaction.followup.send("Choose the exact title to see its listed videos.", view=_TMDBPicker(self, interaction.user.id, "VIDEOS_" + media_type, results), ephemeral=True)

    async def _show_videos(self, interaction: discord.Interaction, item: dict, media_type: str) -> None:
        segment = "movie" if media_type == "MOVIE" else "tv"
        payload = await _tmdb_get(f"{segment}/{item['id']}/videos")
        videos = [v for v in (payload or {}).get("results", []) if isinstance(v, dict)]
        if not videos:
            await interaction.followup.send("TMDB has no video records for this title.", ephemeral=True)
            return
        lines = []
        for video in videos[:12]:
            name = discord.utils.escape_markdown(str(video.get("name") or "Untitled video"))
            site, key, kind = video.get("site"), video.get("key"), video.get("type") or "Video"
            if site == "YouTube" and key:
                url = f"https://www.youtube.com/watch?v={quote_plus(str(key))}"
            elif site == "Vimeo" and key:
                url = f"https://vimeo.com/{quote_plus(str(key))}"
            else:
                continue
            lines.append(f"• [{name}]({url}) · {kind} · {site}" + (" · Officially flagged" if video.get("official") else ""))
        embed = discord.Embed(
            title=f"Videos · {_tmdb_title(item, media_type)}"[:256],
            url=_tmdb_record_url(item, media_type),
            description="\n".join(lines)[:4000] or "TMDB returned no supported YouTube or Vimeo links.",
            color=discord.Color.blurple(),
        )
        embed.set_footer(text="TMDB video metadata · Video type and official flag are shown as returned")
        await interaction.followup.send(embed=embed, ephemeral=True, allowed_mentions=discord.AllowedMentions.none())

    @app_commands.command(name="collection-guide", description="Explore a TMDB movie collection and its listed films")
    @app_commands.guild_only()
    @app_commands.describe(title="Movie title used to locate its collection")
    @command_meta(section="Media Discovery", name="Collection Guide")
    async def collection_guide(self, interaction: discord.Interaction, title: str) -> None:
        if not _tmdb_token():
            await interaction.response.send_message("Collection discovery requires TMDB_BEARER_TOKEN.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True, thinking=True)
        results = await _tmdb_search(title.strip(), "MOVIE")
        if not results:
            await interaction.followup.send("TMDB returned no movie results, or the service is unavailable.", ephemeral=True)
            return
        await interaction.followup.send("Choose the movie whose collection you want to inspect.", view=_TMDBPicker(self, interaction.user.id, "COLLECTION", results), ephemeral=True)

    async def _show_collection(self, interaction: discord.Interaction, item: dict) -> None:
        detail = await _tmdb_get(f"movie/{item['id']}")
        collection_ref = (detail or {}).get("belongs_to_collection") or {}
        if not collection_ref.get("id"):
            await interaction.followup.send("TMDB does not list this movie as a member of a collection.", ephemeral=True)
            return
        collection = await _tmdb_get(f"collection/{collection_ref['id']}")
        if not collection:
            await interaction.followup.send("TMDB could not retrieve the collection details.", ephemeral=True)
            return
        parts = collection.get("parts") or []
        parts = sorted(parts, key=lambda p: (p.get("release_date") or "9999-99-99", str(p.get("title") or "").casefold()))
        lines = []
        for part in parts[:20]:
            title = discord.utils.escape_markdown(str(part.get("title") or "Untitled"))
            url = f"https://www.themoviedb.org/movie/{part['id']}" if part.get("id") else None
            label = f"[{title}]({url})" if url else title
            lines.append(f"• {label} · {part.get('release_date') or 'date unavailable'}")
        poster = collection.get("poster_path")
        embed = discord.Embed(
            title=f"Collection · {collection.get('name') or 'TMDB collection'}"[:256],
            url=f"https://www.themoviedb.org/collection/{collection_ref['id']}",
            description="\n".join(lines)[:4000] or "TMDB returned no member films.",
            color=discord.Color.blurple(),
        )
        if poster:
            embed.set_thumbnail(url=f"{TMDB_IMAGE_BASE_URL}/w500{poster}")
        embed.set_footer(text="TMDB collection membership · Release dates do not establish story chronology")
        await interaction.followup.send(embed=embed, ephemeral=True, allowed_mentions=discord.AllowedMentions.none())

    @app_commands.command(name="author-works", description="Search Google Books for books attributed to an author")
    @app_commands.guild_only()
    @app_commands.describe(author="Author or co-author name")
    @command_meta(section="Media Discovery", name="Author Works")
    async def author_works(self, interaction: discord.Interaction, author: str) -> None:
        query = " ".join((author or "").split())
        if not query:
            await interaction.response.send_message("Enter an author name.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=12)) as session:
                async with session.get(
                    "https://www.googleapis.com/books/v1/volumes",
                    params={"q": f"inauthor:{query}", "maxResults": 10, "orderBy": "relevance"},
                ) as response:
                    if response.status != 200:
                        await interaction.followup.send(f"Google Books returned HTTP {response.status}.", ephemeral=True)
                        return
                    payload = await response.json(content_type=None)
        except (aiohttp.ClientError, asyncio.TimeoutError, ValueError):
            log.warning("Google Books author search failed", exc_info=True)
            await interaction.followup.send("Google Books could not be reached. Please try again later.", ephemeral=True)
            return
        items = payload.get("items") or []
        lines = []
        for item in items[:10]:
            info = item.get("volumeInfo") or {}
            title = discord.utils.escape_markdown(str(info.get("title") or "Untitled"))
            authors = ", ".join(info.get("authors") or [])
            url = info.get("infoLink")
            label = f"[{title}]({url})" if url else title
            lines.append(f"• **{label}**" + (f" · {authors}" if authors else "") + (f" · {info['publishedDate']}" if info.get("publishedDate") else ""))
        embed = discord.Embed(
            title=f"Google Books · Works attributed to {query}"[:256],
            description="\n".join(lines)[:4000] or "Google Books returned no matching volumes.",
            color=discord.Color.blurple(),
        )
        embed.set_footer(text="Google Books metadata · This may include editions and co-authored works")
        await interaction.followup.send(embed=embed, ephemeral=True, allowed_mentions=discord.AllowedMentions.none())

    @app_commands.command(name="webnovel-updates", description="Search Novel Updates for available webnovel metadata")
    @app_commands.guild_only()
    @app_commands.describe(title="Webnovel title or alternative title")
    @command_meta(section="Media Discovery", name="Webnovel Updates")
    async def webnovel_updates(self, interaction: discord.Interaction, title: str) -> None:
        query = " ".join((title or "").split())
        if not query:
            await interaction.response.send_message("Enter a webnovel title.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            results = await asyncio.wait_for(search_novelupdates(query), timeout=30)
        except asyncio.TimeoutError:
            results = None
        except Exception:
            log.warning("Novel Updates lookup failed", exc_info=True)
            results = None
        if results is None:
            await interaction.followup.send("Novel Updates could not be reached reliably. This is a provider failure, not a confirmed no-results search.", ephemeral=True)
            return
        lines = []
        for item in results[:10]:
            name = discord.utils.escape_markdown(str(item.get("title") or "Untitled"))
            url = item.get("url")
            title_text = f"[{name}]({url})" if url else name
            details = [str(item[key]) for key in ("author", "status", "rating") if item.get(key)]
            lines.append(f"• **{title_text}**" + (f" · {' · '.join(details)}" if details else ""))
        embed = discord.Embed(title=f"Novel Updates · {query}"[:256], description="\n".join(lines)[:4000] or "Novel Updates returned no matching records.", color=discord.Color.blurple())
        embed.set_footer(text="Source: Novel Updates · Only fields supplied by the current scraper are shown")
        await interaction.followup.send(embed=embed, ephemeral=True, allowed_mentions=discord.AllowedMentions.none())

    @app_commands.command(name="link-suggest", description="Suggest a cross-media relationship for moderator review")
    @app_commands.guild_only()
    @app_commands.choices(source_category=MEDIA_CATEGORIES, target_category=MEDIA_CATEGORIES, relationship=RELATION_TYPES)
    @app_commands.describe(
        source_title="First work title", source_category="First work category", source_url="HTTPS metadata URL for the first work",
        relationship="Proposed relationship", target_title="Related work title", target_category="Related work category",
        target_url="HTTPS metadata URL for the related work", evidence="Why the relationship should be accepted",
    )
    @command_meta(section="Media Discovery", name="Suggest Media Link")
    async def link_suggest(
        self, interaction: discord.Interaction, source_title: str, source_category: str, source_url: str,
        relationship: str, target_title: str, target_category: str, target_url: str, evidence: str,
    ) -> None:
        if not interaction.guild_id:
            await interaction.response.send_message("Link suggestions are server-scoped.", ephemeral=True)
            return
        try:
            source_url = validate_https_url(source_url, required=True) or ""
            target_url = validate_https_url(target_url, required=True) or ""
        except ValueError as exc:
            await interaction.response.send_message(str(exc), ephemeral=True)
            return
        source_title, target_title, evidence = " ".join(source_title.split()), " ".join(target_title.split()), " ".join(evidence.split())
        if not source_title or not target_title or normalize_title(source_title) == normalize_title(target_title):
            await interaction.response.send_message("Provide two distinct media titles.", ephemeral=True)
            return
        if len(evidence) < 15:
            await interaction.response.send_message("Add a brief evidence explanation (at least 15 characters).", ephemeral=True)
            return
        row = await database.execute_db_operation(
            "save cross-media link suggestion",
            """INSERT INTO media_link_suggestions
               (guild_id, submitter_id, source_title, source_category, source_url, relationship_type,
                target_title, target_category, target_url, evidence)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?) RETURNING id""",
            (interaction.guild_id, interaction.user.id, source_title[:200], source_category, source_url,
             relationship, target_title[:200], target_category, target_url, evidence[:1500]),
            fetch_type="one",
        )
        suggestion_id = row[0] if row else "unknown"
        await interaction.response.send_message(
            f"Suggestion **#{suggestion_id}** saved for moderator review in this server. It is not presented as a confirmed relationship.",
            ephemeral=True,
        )

    @app_commands.command(name="link-review", description="List, inspect and review relationship suggestions for this server")
    @app_commands.guild_only()
    @app_commands.choices(decision=[
        app_commands.Choice(name="List pending suggestions", value="list"),
        app_commands.Choice(name="Inspect without deciding", value="inspect"),
        app_commands.Choice(name="Approve as community-verified", value="approved"),
        app_commands.Choice(name="Reject", value="rejected"),
    ])
    @app_commands.describe(suggestion_id="ID returned by /link-suggest (not needed for List)", decision="List, inspect, approve, or reject", reason="Optional moderator explanation")
    @command_meta(section="Media Discovery", name="Review Media Link")
    async def link_review(self, interaction: discord.Interaction, decision: str = "list", suggestion_id: int | None = None, reason: str = "") -> None:
        if not interaction.guild_id:
            await interaction.response.send_message("Link review is server-scoped.", ephemeral=True)
            return
        permissions = getattr(interaction.user, "guild_permissions", None)
        if not (getattr(permissions, "manage_guild", False) or getattr(permissions, "manage_messages", False)):
            await interaction.response.send_message("Manage Server or Manage Messages permission is required.", ephemeral=True)
            return
        if decision == "list":
            rows = await database.execute_db_operation(
                "list pending media link suggestions for guild",
                """SELECT id, source_title, relationship_type, target_title, created_at
                   FROM media_link_suggestions WHERE guild_id = ? AND status = 'pending'
                   ORDER BY created_at ASC LIMIT 20""",
                (interaction.guild_id,), fetch_type="all",
            ) or []
            lines = [
                f"**#{row[0]}** · {_safe_link_title(row[1])} → {row[2]} → {_safe_link_title(row[3])}"
                for row in rows
            ]
            embed = discord.Embed(
                title="Pending media-link suggestions",
                description="\n".join(lines)[:3900] or "No pending suggestions for this server.",
                color=discord.Color.blurple(),
            )
            embed.set_footer(text="Use /link-review decision:inspect with an ID before approving or rejecting.")
            await interaction.response.send_message(embed=embed, ephemeral=True, allowed_mentions=discord.AllowedMentions.none())
            return
        if suggestion_id is None:
            await interaction.response.send_message("Provide a suggestion ID. Use decision List to see pending IDs.", ephemeral=True)
            return
        row = await database.execute_db_operation(
            "find pending media link suggestion in guild",
            """SELECT id, source_title, source_category, source_url, relationship_type,
                      target_title, target_category, target_url, evidence, status
               FROM media_link_suggestions WHERE id = ? AND guild_id = ? AND status = 'pending'""",
            (suggestion_id, interaction.guild_id), fetch_type="one",
        )
        if not row:
            await interaction.response.send_message("No pending suggestion with that ID exists in this server.", ephemeral=True)
            return
        if decision == "inspect":
            embed = discord.Embed(title=f"Media-link suggestion #{row[0]}", color=discord.Color.blurple())
            embed.add_field(name="Source", value=f"[{_safe_link_title(row[1])}]({row[3]})\nCategory: {row[2]}", inline=False)
            embed.add_field(name="Proposed relationship", value=str(row[4])[:200], inline=True)
            embed.add_field(name="Target", value=f"[{_safe_link_title(row[5])}]({row[7]})\nCategory: {row[6]}", inline=False)
            embed.add_field(name="Submitter evidence", value=str(row[8] or "No evidence provided.")[:1024], inline=False)
            embed.set_footer(text="An approval is community-verified, not provider-confirmed.")
            await interaction.response.send_message(embed=embed, ephemeral=True, allowed_mentions=discord.AllowedMentions.none())
            return
        if decision not in {"approved", "rejected"}:
            await interaction.response.send_message("Choose List, Inspect, Approve or Reject.", ephemeral=True)
            return
        update = await database.execute_db_operation(
            "review media link suggestion",
            """UPDATE media_link_suggestions SET status = ?, reviewer_id = ?, review_reason = ?, reviewed_at = NOW()
               WHERE id = ? AND guild_id = ? AND status = 'pending' RETURNING id""",
            (decision, interaction.user.id, (reason or "")[:1000], suggestion_id, interaction.guild_id),
            fetch_type="one",
        )
        if not update:
            await interaction.response.send_message("That suggestion was reviewed by another moderator. Refresh the pending list.", ephemeral=True)
            return
        status = "approved as a community-verified suggestion (not provider-confirmed)" if decision == "approved" else "rejected"
        if decision == "approved":
            try:
                await record_media_relationship(
                    row[1], row[2], row[3], row[5], row[6], row[7], row[4],
                    source_kind="community",
                    source_label="Moderator-approved suggestion in this server",
                    guild_id=interaction.guild_id,
                    evidence=row[8],
                    created_by=interaction.user.id,
                )
            except Exception:
                log.warning("Approved media link #%s could not be indexed in the shared graph", suggestion_id, exc_info=True)
        await interaction.response.send_message(f"Suggestion **#{suggestion_id}** was {status}.", ephemeral=True)

    async def _create_discussion(self, interaction: discord.Interaction, media_type: str, title: str, reference: str, source_url: str | None) -> None:
        if not interaction.guild or not isinstance(interaction.channel, discord.TextChannel):
            await interaction.response.send_message("Create discussions in a server text channel.", ephemeral=True)
            return
        try:
            source_url = validate_https_url(source_url)
        except ValueError as exc:
            await interaction.response.send_message(str(exc), ephemeral=True)
            return
        title = " ".join((title or "").split())[:200]
        reference = " ".join((reference or "").split())[:100]
        if not title or not reference:
            await interaction.response.send_message("Provide a title and chapter/episode reference.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True, thinking=True)
        message = await interaction.channel.send(
            f"## {discord.utils.escape_markdown(title)}\n**Spoiler cutoff:** {discord.utils.escape_markdown(reference)}\nDiscuss only up to this point. Mark spoilers using Discord's spoiler syntax.\n" + (f"Source: {source_url}" if source_url else ""),
            allowed_mentions=discord.AllowedMentions.none(),
        )
        thread = await interaction.channel.create_thread(
            name=f"{media_type.title()} discussion · {title}"[:100],
            message=message,
            auto_archive_duration=1440,
            reason=f"{media_type} discussion created by {interaction.user.id}",
        )
        await database.execute_db_operation(
            "save connected media discussion thread",
            """INSERT INTO connected_media_discussions
               (guild_id, channel_id, thread_id, creator_id, media_type, title, reference, source_url)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (interaction.guild.id, interaction.channel.id, thread.id, interaction.user.id, media_type, title, reference, source_url),
        )
        await interaction.followup.send(f"Discussion thread created: {thread.mention}", ephemeral=True, allowed_mentions=discord.AllowedMentions.none())

    @app_commands.command(name="chapter-discussion", description="Start a spoiler-aware novel or manga chapter discussion thread")
    @app_commands.guild_only()
    @app_commands.describe(title="Work being discussed", chapter="Chapter or volume cutoff", source_url="Optional official or metadata URL")
    @command_meta(section="Community", name="Chapter Discussion")
    async def chapter_discussion(self, interaction: discord.Interaction, title: str, chapter: str, source_url: str | None = None) -> None:
        await self._create_discussion(interaction, "chapter", title, chapter, source_url)

    @app_commands.command(name="episode-discussion", description="Start a spoiler-aware TV episode discussion thread")
    @app_commands.guild_only()
    @app_commands.describe(series="TV series title", episode="Season/episode reference, for example S2E4", source_url="Optional TMDB or metadata URL")
    @command_meta(section="Community", name="Episode Discussion")
    async def episode_discussion(self, interaction: discord.Interaction, series: str, episode: str, source_url: str | None = None) -> None:
        await self._create_discussion(interaction, "episode", series, episode, source_url)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(ConnectedMedia(bot))
