"""AniList-backed upcoming anime episode schedule, displayed consistently in UTC."""
from __future__ import annotations
import asyncio
import logging
from datetime import datetime, timezone
import aiohttp
import discord
from discord import app_commands
from discord.ext import commands
from helpers.anilist_helper import post_graphql
from cogs_test.general_commands.dashboard import command_meta

log = logging.getLogger(__name__)
SCHEDULE_QUERY = """
query($from: Int, $to: Int) {
  Page(page: 1, perPage: 50) {
    airingSchedules(airingAt_greater: $from, airingAt_lesser: $to, sort: TIME) {
      airingAt
      episode
      media {
        id
        siteUrl
        title { romaji english }
        coverImage { large }
        format
        status
        season
        seasonYear
      }
    }
  }
}
"""
SEASON_QUERY = """
query($season: MediaSeason, $year: Int) {
  Page(page: 1, perPage: 50) {
    media(type: ANIME, season: $season, seasonYear: $year, sort: POPULARITY_DESC, isAdult: false) {
      id
      siteUrl
      title { romaji english }
      coverImage { large }
      format
      status
      season
      seasonYear
      airingSchedule(notYetAired: true, perPage: 10) { nodes { airingAt episode } }
    }
  }
}
"""
TITLE_QUERY = """
query($search: String) {
  Media(search: $search, type: ANIME, isAdult: false) {
    id
    siteUrl
    title { romaji english }
    coverImage { large }
    format
    status
    season
    seasonYear
    airingSchedule(notYetAired: true, perPage: 10) { nodes { airingAt episode } }
  }
}
"""

def filter_schedule(entries: list[dict], day: str | None = None, season: str | None = None, year: int | None = None) -> list[dict]:
    """Filter valid provider timestamps and sort chronologically in UTC."""
    result = []
    for entry in entries:
        timestamp = entry.get("airingAt")
        media = entry.get("media") or {}
        if not isinstance(timestamp, (int, float)):
            continue
        moment = datetime.fromtimestamp(timestamp, timezone.utc)
        if moment <= datetime.now(timezone.utc):
            continue
        if day and moment.strftime("%A").casefold() != day.casefold():
            continue
        if season and media.get("season") != season.upper():
            continue
        if year and media.get("seasonYear") != year:
            continue
        result.append(entry)
    return sorted(result, key=lambda item: item["airingAt"])

def schedule_embed(entries: list[dict], title_filter: str | None, page: int) -> discord.Embed:
    start = page * 5
    visible = entries[start:start + 5]
    description = f"{len(entries)} matching expected episode entries. Times are shown in UTC."
    if title_filter:
        description = f"Upcoming expected episodes matching {title_filter!r}. Times are shown in UTC."
    embed = discord.Embed(title="Anime Airing Schedule", description=description, color=discord.Color.blurple())
    if not visible:
        embed.description = "No matching expected airing events were returned by AniList for these filters."
    for entry in visible:
        media = entry.get("media") or {}
        titles = media.get("title") or {}
        title = titles.get("english") or titles.get("romaji") or "Unknown anime"
        timestamp = int(entry["airingAt"])
        url = media.get("siteUrl")
        label = f"[{title}]({url})" if url else title
        embed.add_field(
            name=f"{label} · Episode {entry.get('episode') or '?'}"[:256],
            value=f"<t:{timestamp}:F> · <t:{timestamp}:R>\nStatus: {media.get('status') or 'Unavailable'} · {media.get('format') or 'Format unavailable'}",
            inline=False,
        )
        image = (media.get("coverImage") or {}).get("large")
        if image and not embed.thumbnail:
            embed.set_thumbnail(url=image)
    embed.set_footer(text=f"Page {page + 1} · Source: AniList. Expected times can change and are not guarantees.")
    return embed

class AiringView(discord.ui.View):
    def __init__(self, cog: "Airing", entries: list[dict], filters: dict, owner_id: int):
        super().__init__(timeout=180)
        self.cog = cog
        self.entries = entries
        self.filters = filters
        self.owner_id = owner_id
        self.page = 0
        self.previous.disabled = True
        self.next.disabled = len(entries) <= 5

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message("Only the user who ran this schedule query can operate its controls.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Previous", style=discord.ButtonStyle.secondary)
    async def previous(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        self.page = max(0, self.page - 1)
        self.previous.disabled = self.page == 0
        self.next.disabled = (self.page + 1) * 5 >= len(self.entries)
        await interaction.response.edit_message(embed=schedule_embed(self.entries, self.filters.get("title"), self.page), view=self)

    @discord.ui.button(label="Next", style=discord.ButtonStyle.secondary)
    async def next(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        self.page = min(max(0, (len(self.entries) - 1) // 5), self.page + 1)
        self.previous.disabled = self.page == 0
        self.next.disabled = (self.page + 1) * 5 >= len(self.entries)
        await interaction.response.edit_message(embed=schedule_embed(self.entries, self.filters.get("title"), self.page), view=self)

    @discord.ui.button(label="Refresh", style=discord.ButtonStyle.primary)
    async def refresh(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await interaction.response.defer()
        self.entries = await self.cog.fetch_schedule(**self.filters)
        self.page = 0
        self.previous.disabled = True
        self.next.disabled = len(self.entries) <= 5
        await interaction.edit_original_response(embed=schedule_embed(self.entries, self.filters.get("title"), 0), view=self)

class Airing(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def fetch_schedule(self, title: str | None = None, day: str | None = None, season: str | None = None, year: int | None = None) -> list[dict]:
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15)) as session:
                if title:
                    payload = await post_graphql(session, TITLE_QUERY, {"search": title}, timeout=15)
                    media = (payload or {}).get("Media")
                    if not media:
                        return []
                    entries = [
                        {"airingAt": node.get("airingAt"), "episode": node.get("episode"), "media": media}
                        for node in ((media.get("airingSchedule") or {}).get("nodes") or [])
                    ]
                    return filter_schedule(entries, day=day, season=season, year=year)
                if season or year:
                    payload = await post_graphql(session, SEASON_QUERY, {"season": season, "year": year}, timeout=15)
                    media_items = ((payload or {}).get("Page") or {}).get("media") or []
                    entries = [
                        {"airingAt": node.get("airingAt"), "episode": node.get("episode"), "media": media}
                        for media in media_items
                        for node in ((media.get("airingSchedule") or {}).get("nodes") or [])
                    ]
                    return filter_schedule(entries, day=day, season=season, year=year)
                now = int(datetime.now(timezone.utc).timestamp())
                end = now + (14 * 86400 if day else 7 * 86400)
                payload = await post_graphql(session, SCHEDULE_QUERY, {"from": now, "to": end}, timeout=15)
            entries = (((payload or {}).get("Page") or {}).get("airingSchedules") or [])
            return filter_schedule(entries, day=day)
        except (aiohttp.ClientError, asyncio.TimeoutError, ValueError, TypeError) as exc:
            log.warning("AniList airing schedule request failed: %s", exc)
            return []

    @app_commands.command(name="airing", description="Browse expected upcoming anime episode times from AniList")
    @app_commands.guild_only()
    @app_commands.choices(
        day=[app_commands.Choice(name=name, value=name) for name in ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")],
        season=[
            app_commands.Choice(name="Winter", value="WINTER"),
            app_commands.Choice(name="Spring", value="SPRING"),
            app_commands.Choice(name="Summer", value="SUMMER"),
            app_commands.Choice(name="Fall", value="FALL"),
        ],
    )
    @app_commands.describe(title="Optional anime title", day="Filter upcoming episodes by UTC weekday", season="Filter by AniList season", year="Season year")
    @command_meta(section="Media Discovery", name="Airing")
    async def airing(
        self,
        interaction: discord.Interaction,
        title: str | None = None,
        day: str | None = None,
        season: str | None = None,
        year: app_commands.Range[int, 1970, 2100] | None = None,
    ) -> None:
        await interaction.response.defer(ephemeral=True, thinking=True)
        filters = {"title": title, "day": day, "season": season, "year": year}
        entries = await self.fetch_schedule(**filters)
        if not entries:
            await interaction.followup.send("AniList returned no expected airing times for these filters, or the schedule service is unavailable. This does not mean the title is cancelled or not airing.", ephemeral=True)
            return
        await interaction.followup.send(
            embed=schedule_embed(entries, title, 0),
            view=AiringView(self, entries, filters, interaction.user.id),
            ephemeral=True,
        )

async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Airing(bot))
