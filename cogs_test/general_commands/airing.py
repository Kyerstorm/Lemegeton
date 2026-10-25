"""AniList-backed upcoming anime episode schedule, displayed consistently in UTC."""
from __future__ import annotations
import asyncio
import logging
from datetime import datetime, timezone
import aiohttp
import discord
from helpers.command_error_handler import FeedbackAwareView
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

def filter_schedule(
    entries: list[dict], day: str | None = None, season: str | None = None,
    year: int | None = None, days: int | None = None,
) -> list[dict]:
    """Filter actual future AniList timestamps, using UTC for weekday and window comparisons."""
    now = datetime.now(timezone.utc)
    deadline = now.timestamp() + days * 86400 if days is not None else None
    result = []
    for entry in entries:
        timestamp = entry.get("airingAt")
        media = entry.get("media") or {}
        if not isinstance(timestamp, (int, float)):
            continue
        moment = datetime.fromtimestamp(timestamp, timezone.utc)
        if moment <= now or (deadline is not None and timestamp > deadline):
            continue
        if day and moment.strftime("%A").casefold() != day.casefold():
            continue
        if season and media.get("season") != season.upper():
            continue
        if year and media.get("seasonYear") != year:
            continue
        result.append(entry)
    return sorted(result, key=lambda item: item["airingAt"])


def format_utc_airing_time(timestamp: int) -> str:
    """Render the provider timestamp explicitly in UTC for an unambiguous schedule."""
    return datetime.fromtimestamp(timestamp, timezone.utc).strftime("%a, %d %b %Y %H:%M UTC")

def schedule_embed(entries: list[dict], title_filter: str | None, page: int) -> discord.Embed:
    start = page * 5
    visible = entries[start:start + 5]
    description = f"{len(entries)} expected episode entries within the selected window. Explicit times are UTC."
    if title_filter:
        description = f"Expected upcoming episodes matching {title_filter!r}. Explicit times are UTC."
    embed = discord.Embed(title="📅 Anime Airing Schedule", description=description, color=discord.Color.blurple())
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
            value=f"UTC: **{format_utc_airing_time(timestamp)}** · <t:{timestamp}:R>\nStatus: {media.get('status') or 'Unavailable'} · {media.get('format') or 'Format unavailable'}",
            inline=False,
        )
        image = (media.get("coverImage") or {}).get("large")
        if image and not embed.thumbnail:
            embed.set_thumbnail(url=image)
    embed.set_footer(text=f"🕒 Times in UTC · Source: AniList · Page {page + 1} · Schedule may change")
    return embed

class AiringView(FeedbackAwareView):
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

    @discord.ui.button(label="◀ Previous", style=discord.ButtonStyle.secondary)
    async def previous(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        self.page = max(0, self.page - 1)
        self.previous.disabled = self.page == 0
        self.next.disabled = (self.page + 1) * 5 >= len(self.entries)
        await interaction.response.edit_message(embed=schedule_embed(self.entries, self.filters.get("title"), self.page), view=self)

    @discord.ui.button(label="Next ▶", style=discord.ButtonStyle.secondary)
    async def next(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        self.page = min(max(0, (len(self.entries) - 1) // 5), self.page + 1)
        self.previous.disabled = self.page == 0
        self.next.disabled = (self.page + 1) * 5 >= len(self.entries)
        await interaction.response.edit_message(embed=schedule_embed(self.entries, self.filters.get("title"), self.page), view=self)

    @discord.ui.button(label="🔄 Refresh", style=discord.ButtonStyle.primary)
    async def refresh(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await interaction.response.defer()
        self.entries = await self.cog.fetch_schedule(**self.filters)
        self.page = 0
        self.previous.disabled = True
        self.next.disabled = len(self.entries) <= 5
        await interaction.edit_original_response(embed=schedule_embed(self.entries, self.filters.get("title"), 0), view=self)

    async def on_timeout(self) -> None:
        for item in self.children:
            item.disabled = True
        message = self.message
        if message is not None:
            try:
                await message.edit(view=self)
            except discord.HTTPException:
                pass

class Airing(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def fetch_schedule(
        self, title: str | None = None, day: str | None = None,
        season: str | None = None, year: int | None = None, days: int = 7,
    ) -> list[dict]:
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
                    return filter_schedule(entries, day=day, season=season, year=year, days=days)
                if season or year:
                    payload = await post_graphql(session, SEASON_QUERY, {"season": season, "year": year}, timeout=15)
                    media_items = ((payload or {}).get("Page") or {}).get("media") or []
                    entries = [
                        {"airingAt": node.get("airingAt"), "episode": node.get("episode"), "media": media}
                        for media in media_items
                        for node in ((media.get("airingSchedule") or {}).get("nodes") or [])
                    ]
                    return filter_schedule(entries, day=day, season=season, year=year, days=days)
                now = int(datetime.now(timezone.utc).timestamp())
                end = now + days * 86400
                payload = await post_graphql(session, SCHEDULE_QUERY, {"from": now, "to": end}, timeout=15)
            entries = (((payload or {}).get("Page") or {}).get("airingSchedules") or [])
            return filter_schedule(entries, day=day, days=days)
        except Exception as exc:
            log.warning("AniList airing schedule request failed: %s", exc, exc_info=True)
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
        window=[
            app_commands.Choice(name="Next 24 Hours", value=1),
            app_commands.Choice(name="Next 3 Days", value=3),
            app_commands.Choice(name="Next 7 Days", value=7),
            app_commands.Choice(name="Next 14 Days", value=14),
        ],
    )
    @app_commands.describe(
        title="Optional anime title",
        day="Filter upcoming episodes by UTC weekday",
        season="Filter by AniList season",
        year="Season year",
        window="How far ahead to show expected episodes",
    )
    @command_meta(section="Media Discovery", name="Airing")
    async def airing(
        self,
        interaction: discord.Interaction,
        title: str | None = None,
        day: str | None = None,
        season: str | None = None,
        year: app_commands.Range[int, 1970, 2100] | None = None,
        window: app_commands.Choice[int] | None = None,
    ) -> None:
        await interaction.response.defer(ephemeral=True, thinking=True)
        filters = {
            "title": title.strip() if title else None,
            "day": day,
            "season": season,
            "year": year,
            "days": window.value if window else 7,
        }
        entries = await self.fetch_schedule(**filters)
        if not entries:
            await interaction.followup.send("📭 **No upcoming episodes found** for these filters, or AniList is temporarily unavailable. This does not mean the title is cancelled.", ephemeral=True)
            return
        await interaction.followup.send(
            embed=schedule_embed(entries, title, 0),
            view=AiringView(self, entries, filters, interaction.user.id),
            ephemeral=True,
        )

async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Airing(bot))
