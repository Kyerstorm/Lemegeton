"""Persistent, guild/channel-scoped media-night voting for AniList anime and manga."""
from __future__ import annotations
import asyncio
import json
import logging
import os
import secrets
from datetime import datetime, timedelta, timezone
import aiohttp
import discord
from helpers.command_error_handler import FeedbackAwareView
from discord import app_commands
from discord.ext import commands, tasks
from database import execute_db_operation
from helpers.anilist_helper import post_graphql
from cogs_test.general_commands.dashboard import command_meta

log = logging.getLogger(__name__)
CANDIDATE_QUERY = """
query($type: MediaType, $perPage: Int) {
  Page(page: 1, perPage: $perPage) {
    media(type: $type, sort: TRENDING_DESC, isAdult: false) {
      id
      title { romaji english }
      siteUrl
      coverImage { large }
      format
      genres
      tags { name isMediaSpoiler }
      startDate { year }
      duration
      isAdult
    }
  }
}
"""

MOOD_GENRES = {
    "cozy": {"slice of life", "comedy", "family"},
    "dark": {"horror", "thriller", "mystery", "psychological", "crime"},
    "uplifting": {"comedy", "adventure", "family", "sports"},
    "mind-bending": {"psychological", "mystery", "science fiction", "sci-fi", "thriller"},
    "tense": {"thriller", "action", "horror", "crime"},
}
MATURE_MARKERS = {"hentai", "erotica", "pornography", "explicit sexual content"}


def tally_votes(votes: dict[str, int], candidate_count: int) -> list[int]:
    totals = [0] * candidate_count
    for value in votes.values():
        if isinstance(value, int) and 0 <= value < candidate_count:
            totals[value] += 1
    return totals

def title_of(item: dict) -> str:
    titles = item.get("title") or {}
    if isinstance(titles, dict):
        return titles.get("english") or titles.get("romaji") or item.get("name") or "Untitled media"
    return str(titles or item.get("name") or "Untitled media")


def _matches_mood(item: dict, mood: str | None) -> bool:
    if not mood:
        return True
    target = MOOD_GENRES.get(mood.casefold())
    if not target:
        return False
    genres = {str(value).casefold() for value in (item.get("genres") or [])}
    tags = {str((tag or {}).get("name") or "").casefold() for tag in (item.get("tags") or [])}
    return bool(target.intersection(genres | tags))


def _family_friendly(item: dict) -> bool:
    if item.get("isAdult") is True or item.get("adult") is True:
        return False
    genres = {str(value).casefold() for value in (item.get("genres") or [])}
    tags = {str((tag or {}).get("name") or "").casefold() for tag in (item.get("tags") or [])}
    return not any(marker in value for value in genres | tags for marker in MATURE_MARKERS)

class MediaNightView(FeedbackAwareView):
    """Persistent vote buttons encode a session ID and candidate index."""
    def __init__(self, cog: "MediaNight", session_id: str, candidate_count: int):
        super().__init__(timeout=None)
        self.cog = cog
        self.session_id = session_id
        for index in range(candidate_count):
            button = discord.ui.Button(
                label=f"Vote {index + 1}",
                style=discord.ButtonStyle.primary,
                custom_id=f"media-night:{session_id}:vote:{index}",
            )
            async def callback(interaction: discord.Interaction, chosen: int = index) -> None:
                await self.cog.cast_vote(interaction, self.session_id, chosen)
            button.callback = callback
            self.add_item(button)

class MediaNight(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.sessions: dict[str, dict] = {}
        self.vote_locks: dict[str, asyncio.Lock] = {}

    async def cog_load(self) -> None:
        await execute_db_operation(
            "create persistent media-night sessions",
            """CREATE TABLE IF NOT EXISTS media_night_sessions (
                session_id TEXT PRIMARY KEY,
                guild_id BIGINT NOT NULL,
                channel_id BIGINT NOT NULL,
                host_id BIGINT NOT NULL,
                message_id BIGINT,
                category TEXT NOT NULL,
                candidates TEXT NOT NULL,
                votes TEXT NOT NULL DEFAULT '{}',
                status TEXT NOT NULL,
                expires_at TIMESTAMP NOT NULL,
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            )""",
        )
        await execute_db_operation(
            "cancel interrupted media-night setup sessions",
            "UPDATE media_night_sessions SET status = 'cancelled' WHERE status = 'setup'",
        )
        await execute_db_operation(
            "expire old media-night sessions",
            "UPDATE media_night_sessions SET status = 'expired' WHERE status = 'open' AND expires_at <= CURRENT_TIMESTAMP",
        )
        await execute_db_operation(
            "prevent duplicate active media-night sessions per guild channel",
            "CREATE UNIQUE INDEX IF NOT EXISTS media_night_one_active_per_channel_idx ON media_night_sessions (guild_id, channel_id) WHERE status IN ('setup', 'open')",
        )
        rows = await execute_db_operation(
            "restore active media-night sessions",
            "SELECT * FROM media_night_sessions WHERE status = 'open' AND expires_at > CURRENT_TIMESTAMP",
            fetch_type="all",
        )
        for row in rows or []:
            data = dict(row)
            session_id = str(data["session_id"])
            data["candidates"] = json.loads(data["candidates"])
            data["votes"] = json.loads(data["votes"] or "{}")
            expiry = data["expires_at"]
            if expiry.tzinfo is None:
                data["expires_at"] = expiry.replace(tzinfo=timezone.utc)
            self.sessions[session_id] = data
            self.vote_locks[session_id] = asyncio.Lock()
            if data.get("message_id"):
                self.bot.add_view(MediaNightView(self, session_id, len(data["candidates"])), message_id=int(data["message_id"]))
        if not self.expire_sessions.is_running():
            self.expire_sessions.start()

    async def cog_unload(self) -> None:
        self.expire_sessions.cancel()

    @tasks.loop(seconds=30)
    async def expire_sessions(self) -> None:
        """Close due sessions and update their public voting messages."""
        now = datetime.now(timezone.utc)
        for session_id in list(self.sessions):
            lock = self.vote_locks.setdefault(session_id, asyncio.Lock())
            async with lock:
                session = self.sessions.get(session_id)
                if not session or session.get("status") != "open" or now < session["expires_at"]:
                    continue
                session["status"] = "expired"
                try:
                    await execute_db_operation(
                        "expire media-night session",
                        "UPDATE media_night_sessions SET status = 'expired' WHERE session_id = ? AND guild_id = ? AND channel_id = ? AND status = 'open'",
                        (session_id, session["guild_id"], session["channel_id"]),
                    )
                    guild = self.bot.get_guild(int(session["guild_id"]))
                    channel = guild.get_channel_or_thread(int(session["channel_id"])) if guild else None
                    message = await channel.fetch_message(int(session["message_id"])) if channel and session.get("message_id") else None
                    if message:
                        await message.edit(
                            embed=self.session_embed(session, final=True),
                            view=None,
                            allowed_mentions=discord.AllowedMentions.none(),
                        )
                except (discord.NotFound, discord.Forbidden, discord.HTTPException, AttributeError):
                    log.info("Expired media-night session %s could not update its message", session_id)
                except Exception:
                    log.exception("Unable to expire media-night session %s", session_id)

    @expire_sessions.before_loop
    async def before_expire_sessions(self) -> None:
        await self.bot.wait_until_ready()

    def session_embed(self, session: dict, final: bool = False) -> discord.Embed:
        candidates = session["candidates"]
        totals = tally_votes(session["votes"], len(candidates))
        lines = []
        for index, item in enumerate(candidates):
            name = title_of(item)
            link = item.get("siteUrl") or item.get("url")
            label = f"[{name}]({link})" if link else name
            lines.append(f"**{index + 1}.** {label}\nVotes: **{totals[index]}**")
        embed = discord.Embed(title=f"🎬 Media Night · {session['category'].title()}", description="\n\n".join(lines)[:4000], color=discord.Color.blurple())
        embed.add_field(name="🗳️ Votes cast", value=str(sum(totals)), inline=True)
        if final:
            highest = max(totals, default=0)
            winners = [title_of(item) for i, item in enumerate(candidates) if totals[i] == highest]
            result = "No votes were cast." if highest == 0 else ("Tie: " + ", ".join(winners) if len(winners) > 1 else winners[0])
            embed.add_field(name="🏆 Result", value=result[:1024], inline=False)
        elif session["status"] == "open":
            embed.add_field(name="⏳ Voting closes", value=f"<t:{int(session['expires_at'].timestamp())}:R>", inline=True)
        note = " · Family-friendly mode is metadata-based, not a parental-rating guarantee" if session.get("suitability") == "family-friendly" else ""
        embed.set_footer(text="🗳️ One vote per person · You can change your vote while voting is open" + note)
        return embed

    media_night = app_commands.Group(name="media-night", description="Start and manage community media voting")

    @media_night.command(name="start", description="Start a filtered community vote for anime, manga, movies, or TV")
    @app_commands.guild_only()
    @app_commands.choices(category=[
        app_commands.Choice(name="Anime", value="ANIME"),
        app_commands.Choice(name="Manga", value="MANGA"),
        app_commands.Choice(name="Movie", value="MOVIE"),
        app_commands.Choice(name="TV show", value="TV"),
    ])
    @app_commands.choices(mood=[
        app_commands.Choice(name="Cozy", value="cozy"),
        app_commands.Choice(name="Dark", value="dark"),
        app_commands.Choice(name="Uplifting", value="uplifting"),
        app_commands.Choice(name="Mind-bending", value="mind-bending"),
        app_commands.Choice(name="Tense", value="tense"),
    ], suitability=[
        app_commands.Choice(name="General", value="general"),
        app_commands.Choice(name="Family-friendly best-effort", value="family-friendly"),
    ])
    @app_commands.describe(
        category="Media category", candidates="Number of candidates",
        duration="Voting duration in minutes (5–240)", genre="Optional provider genre filter",
        mood="Optional mood inferred from provider genres/tags", year_from="Earliest release/publication year",
        year_to="Latest release/publication year", max_runtime="Maximum runtime in minutes (TV runtime means per episode)",
        suitability="Exclude adult-flagged titles; family-friendly is a best-effort metadata filter",
    )
    @command_meta(section="Community", name="Media Night Start")
    async def start(
        self, interaction: discord.Interaction, category: str,
        candidates: app_commands.Range[int, 2, 5] = 4,
        duration: app_commands.Range[int, 5, 240] = 30,
        genre: str | None = None, mood: str | None = None,
        year_from: app_commands.Range[int, 1900, 2100] | None = None,
        year_to: app_commands.Range[int, 1900, 2100] | None = None,
        max_runtime: app_commands.Range[int, 1, 600] | None = None,
        suitability: str = "general",
    ) -> None:
        if interaction.guild is None or interaction.channel is None:
            await interaction.response.send_message("Media Night can only be started in a server channel.", ephemeral=True)
            return
        if year_from is not None and year_to is not None and year_from > year_to:
            await interaction.response.send_message("The earliest year cannot be later than the latest year.", ephemeral=True)
            return
        if max_runtime is not None and category == "MANGA":
            await interaction.response.send_message("Runtime filters do not apply to manga. Remove max_runtime or choose anime, movie, or TV.", ephemeral=True)
            return
        if category in ("MOVIE", "TV") and not os.getenv("TMDB_BEARER_TOKEN", "").strip():
            await interaction.response.send_message("Movie and TV Media Night require TMDB_BEARER_TOKEN. Configure it before starting this vote.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True, thinking=True)
        existing = await execute_db_operation(
            "check active media-night in this guild channel",
            "SELECT session_id FROM media_night_sessions WHERE guild_id = ? AND channel_id = ? AND status IN ('setup', 'open') AND expires_at > CURRENT_TIMESTAMP",
            (interaction.guild.id, interaction.channel.id),
            fetch_type="one",
        )
        if existing:
            await interaction.followup.send("This channel already has an open Media Night. Close it before starting another.", ephemeral=True)
            return
        try:
            pool = await self._candidate_pool(
                category, genre=genre, mood=mood, year_from=year_from, year_to=year_to,
                max_runtime=max_runtime, suitability=suitability,
            )
        except (aiohttp.ClientError, asyncio.TimeoutError, ValueError):
            log.warning("Media Night candidate search failed for %s", category, exc_info=True)
            pool = []
        unique = {str(item.get("id") or title_of(item)).casefold(): item for item in pool if item.get("id") or item.get("title") or item.get("name")}
        pool = list(unique.values())
        if len(pool) < candidates:
            await interaction.followup.send(f"The configured providers supplied only {len(pool)} distinct candidates matching these filters; {candidates} are required. Broaden the filters or try later. No session was created.", ephemeral=True)
            return
        chosen = secrets.SystemRandom().sample(pool, candidates)
        session_id = secrets.token_hex(5)
        expires_at = datetime.now(timezone.utc) + timedelta(minutes=duration)
        channel = interaction.channel
        session = {
            "session_id": session_id, "guild_id": interaction.guild.id, "channel_id": channel.id,
            "host_id": interaction.user.id, "message_id": None, "category": category.lower(),
            "candidates": chosen, "votes": {}, "status": "setup", "expires_at": expires_at,
            "suitability": suitability,
        }
        try:
            await execute_db_operation(
                "create media-night session",
                """INSERT INTO media_night_sessions
                (session_id, guild_id, channel_id, host_id, message_id, category, candidates, votes, status, expires_at)
                VALUES (?, ?, ?, ?, NULL, ?, ?, '{}', 'setup', ?)""",
                (session_id, interaction.guild.id, channel.id, interaction.user.id, category.lower(), json.dumps(chosen), expires_at.replace(tzinfo=None)),
            )
        except Exception:
            log.info("A concurrent Media Night start or database failure prevented session creation in guild %s channel %s", interaction.guild.id, channel.id, exc_info=True)
            await interaction.followup.send("A session was started in this channel already, or session storage is unavailable. Check the active vote and try again.", ephemeral=True)
            return
        self.sessions[session_id] = session
        self.vote_locks[session_id] = asyncio.Lock()
        view = MediaNightView(self, session_id, len(chosen))
        try:
            message = await channel.send(embed=self.session_embed(session), view=view, allowed_mentions=discord.AllowedMentions.none())
        except (discord.Forbidden, discord.HTTPException):
            session["status"] = "cancelled"
            await execute_db_operation("cancel media-night session whose message could not be sent", "UPDATE media_night_sessions SET status = 'cancelled' WHERE session_id = ? AND guild_id = ?", (session_id, interaction.guild.id))
            await interaction.followup.send("I couldn't post the voting message. Check this channel's View Channel, Send Messages, and Embed Links permissions.", ephemeral=True)
            return
        session["message_id"] = message.id
        session["status"] = "open"
        await execute_db_operation(
            "activate media-night session",
            "UPDATE media_night_sessions SET message_id = ?, status = 'open' WHERE session_id = ? AND guild_id = ? AND channel_id = ?",
            (message.id, session_id, interaction.guild.id, channel.id),
        )
        await message.edit(embed=self.session_embed(session), view=view)
        filters = [f"genre: {genre}" if genre else None, f"mood: {mood}" if mood else None, f"years: {year_from or 'any'}–{year_to or 'any'}" if year_from or year_to else None, f"runtime ≤ {max_runtime}m" if max_runtime else None]
        filter_summary = " · Filters: " + ", ".join(value for value in filters if value) if any(filters) else ""
        await interaction.followup.send(f"🎬 **Media Night is live!** Session ID: `{session_id}`\nUse `/media-night close` with this ID to close or cancel the vote. Voting closes in **{duration} minutes**.{filter_summary}", ephemeral=True)

    async def _candidate_pool(
        self, category: str, *, genre: str | None = None, mood: str | None = None,
        year_from: int | None = None, year_to: int | None = None,
        max_runtime: int | None = None, suitability: str = "general",
    ) -> list[dict]:
        if category in ("ANIME", "MANGA"):
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15)) as session:
                payload = await post_graphql(session, CANDIDATE_QUERY, {"type": category, "perPage": 50}, timeout=15)
            media = ((payload or {}).get("Page") or {}).get("media") or []
            filtered = []
            for item in media:
                if item.get("isAdult") is True:
                    continue
                genres = [str(value).casefold() for value in (item.get("genres") or [])]
                tags = [str((tag or {}).get("name") or "").casefold() for tag in (item.get("tags") or [])]
                if genre and not any(genre.casefold() in value for value in genres):
                    continue
                if not _matches_mood(item, mood):
                    continue
                year = ((item.get("startDate") or {}).get("year"))
                if year_from is not None and (not year or int(year) < year_from):
                    continue
                if year_to is not None and (not year or int(year) > year_to):
                    continue
                if max_runtime is not None and category == "ANIME":
                    duration_value = item.get("duration")
                    if not isinstance(duration_value, int) or duration_value > max_runtime:
                        continue
                if suitability == "family-friendly" and not _family_friendly(item):
                    continue
                filtered.append(item)
            return filtered

        token = os.getenv("TMDB_BEARER_TOKEN", "").strip()
        if not token:
            return []
        endpoint = "movie" if category == "MOVIE" else "tv"
        headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as session:
            async with session.get(f"https://api.themoviedb.org/3/genre/{endpoint}/list", headers=headers, params={"language": "en-US"}) as response:
                if response.status != 200:
                    return []
                genre_payload = await response.json(content_type=None)
            genre_map = {str(entry.get("name") or "").casefold(): int(entry["id"]) for entry in genre_payload.get("genres", []) if entry.get("id") is not None}
            explicit_genre_id = None
            if genre:
                explicit_genre_id = next((identifier for name, identifier in genre_map.items() if genre.casefold() in name), None)
                if explicit_genre_id is None:
                    return []
            mood_names = MOOD_GENRES.get(mood.casefold()) or set() if mood else set()
            mood_ids = sorted({identifier for name, identifier in genre_map.items() if name in mood_names and identifier != explicit_genre_id})
            params: dict[str, object] = {"language": "en-US", "include_adult": "false", "sort_by": "popularity.desc", "page": 1}
            if explicit_genre_id is not None and mood_ids:
                params["with_genres"] = f"{explicit_genre_id}," + "|".join(str(value) for value in mood_ids)
            elif explicit_genre_id is not None:
                params["with_genres"] = str(explicit_genre_id)
            elif mood_ids:
                params["with_genres"] = "|".join(str(value) for value in mood_ids)
            prefix = "primary_release_date" if category == "MOVIE" else "first_air_date"
            if year_from is not None:
                params[f"{prefix}.gte"] = f"{year_from}-01-01"
            if year_to is not None:
                params[f"{prefix}.lte"] = f"{year_to}-12-31"
            if max_runtime is not None:
                params["with_runtime.lte"] = max_runtime
            async with session.get(f"https://api.themoviedb.org/3/discover/{endpoint}", headers=headers, params=params) as response:
                if response.status != 200:
                    log.warning("TMDB media-night discover returned HTTP %s", response.status)
                    return []
                payload = await response.json(content_type=None)
        normalized = []
        id_to_genre = {identifier: name for name, identifier in genre_map.items()}
        for item in (payload.get("results") or [])[:50]:
            title = item.get("title") if category == "MOVIE" else item.get("name")
            item_id = item.get("id")
            if not title or not item_id:
                continue
            date = item.get("release_date") if category == "MOVIE" else item.get("first_air_date")
            try:
                year = int(date[:4]) if date else None
            except (TypeError, ValueError):
                year = None
            genres = [id_to_genre[identifier] for identifier in item.get("genre_ids", []) if identifier in id_to_genre]
            normalized_item = {
                "id": item_id,
                "title": title,
                "siteUrl": f"https://www.themoviedb.org/{endpoint}/{item_id}",
                "coverImage": {"large": f"https://image.tmdb.org/t/p/w500{item['poster_path']}"} if item.get("poster_path") else {},
                "genres": genres,
                "startDate": {"year": year} if year else {},
                "adult": item.get("adult") is True,
                "overview": item.get("overview") or "",
            }
            if suitability == "family-friendly" and (normalized_item["adult"] or any(value.casefold() in {"horror", "crime", "thriller"} for value in genres)):
                continue
            normalized.append(normalized_item)
        return normalized

    async def cast_vote(self, interaction: discord.Interaction, session_id: str, choice: int) -> None:
        session = self.sessions.get(session_id)
        if session is None or interaction.guild_id != int(session["guild_id"]) or interaction.channel_id != int(session["channel_id"]):
            await interaction.response.send_message("This vote belongs to another or unavailable session.", ephemeral=True)
            return
        lock = self.vote_locks.setdefault(session_id, asyncio.Lock())
        async with lock:
            session = self.sessions.get(session_id)
            if not session or session["status"] != "open":
                await interaction.response.send_message("Voting is no longer open.", ephemeral=True)
                return
            if datetime.now(timezone.utc) >= session["expires_at"]:
                session["status"] = "expired"
                await execute_db_operation("expire media-night after vote deadline", "UPDATE media_night_sessions SET status = 'expired' WHERE session_id = ? AND guild_id = ? AND status = 'open'", (session_id, interaction.guild_id))
                await interaction.response.edit_message(embed=self.session_embed(session, final=True), view=None)
                return
            if choice < 0 or choice >= len(session["candidates"]):
                await interaction.response.send_message("That candidate is no longer valid.", ephemeral=True)
                return
            await interaction.response.defer()
            session["votes"][str(interaction.user.id)] = choice
            await execute_db_operation(
                "save media-night vote",
                "UPDATE media_night_sessions SET votes = ? WHERE session_id = ? AND guild_id = ? AND channel_id = ? AND status = 'open'",
                (json.dumps(session["votes"]), session_id, interaction.guild_id, interaction.channel_id),
            )
            await interaction.edit_original_response(embed=self.session_embed(session), view=MediaNightView(self, session_id, len(session["candidates"])))

    @media_night.command(name="close", description="Close or cancel a Media Night session")
    @app_commands.guild_only()
    @app_commands.choices(action=[
        app_commands.Choice(name="Close voting and show the result", value="close"),
        app_commands.Choice(name="Cancel session", value="cancel"),
    ])
    @app_commands.describe(session_id="Session ID returned when the vote started", action="Close or cancel")
    @command_meta(section="Community", name="Media Night Close")
    async def close(self, interaction: discord.Interaction, session_id: str, action: str = "close") -> None:
        session = self.sessions.get(session_id)
        if (
            interaction.guild is None
            or session is None
            or int(session["guild_id"]) != interaction.guild.id
            or interaction.channel_id != int(session["channel_id"])
        ):
            await interaction.response.send_message("That session was not found in this server and channel.", ephemeral=True)
            return
        is_host = interaction.user.id == int(session["host_id"])
        is_mod = isinstance(interaction.user, discord.Member) and (interaction.user.guild_permissions.manage_guild or interaction.user.guild_permissions.manage_messages)
        if not (is_host or is_mod):
            await interaction.response.send_message("Only the session host or a server moderator can manage this session.", ephemeral=True)
            return
        if session["status"] != "open":
            await interaction.response.send_message(f"This session is already {session['status']}.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True, thinking=True)
        lock = self.vote_locks.setdefault(session_id, asyncio.Lock())
        async with lock:
            session = self.sessions.get(session_id)
            if not session or session["status"] != "open":
                await interaction.followup.send("This session has already closed or expired.", ephemeral=True)
                return
            session["status"] = "closed" if action == "close" else "cancelled"
            await execute_db_operation(
                "finish media-night session",
                "UPDATE media_night_sessions SET status = ? WHERE session_id = ? AND guild_id = ? AND channel_id = ? AND status = 'open'",
                (session["status"], session_id, interaction.guild.id, session["channel_id"]),
            )
        channel = interaction.guild.get_channel_or_thread(int(session["channel_id"]))
        try:
            message = await channel.fetch_message(int(session["message_id"])) if channel and session.get("message_id") else None
            if message:
                embed = self.session_embed(session, final=(action == "close"))
                if action == "cancel":
                    embed.title = "Media Night · Cancelled"
                    embed.add_field(name="Status", value="Voting was cancelled by the host or a moderator.", inline=False)
                await message.edit(embed=embed, view=None, allowed_mentions=discord.AllowedMentions.none())
        except (discord.NotFound, discord.Forbidden, discord.HTTPException, AttributeError):
            log.info("Media-night message %s could not be edited after closing", session.get("message_id"))
        await interaction.followup.send("✅ **Voting closed.** Ties remain ties; no automatic tie-breaker is applied." if action == "close" else "🛑 **Media Night cancelled.**", ephemeral=True)

async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(MediaNight(bot))
