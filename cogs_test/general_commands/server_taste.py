"""Guild-scoped, opt-in aggregate AniList taste report."""
from __future__ import annotations
import asyncio
from collections import Counter
import logging
import aiohttp
import discord
from discord import app_commands
from discord.ext import commands
from database import execute_db_operation, get_all_users_guild_aware
from helpers.anilist_helper import post_graphql
from cogs_test.general_commands.dashboard import command_meta

log = logging.getLogger(__name__)
TASTE_QUERY = """
query($name: String, $type: MediaType) {
  MediaListCollection(userName: $name, type: $type) {
    lists { entries { media { genres tags { name rank isMediaSpoiler } } } }
  }
}
"""

def aggregate_member_interests(entries: list[dict]) -> tuple[set[str], set[str]]:
    """Return unique genres and high-ranked, non-spoiler tags for one public list."""
    genres: set[str] = set()
    tags: set[str] = set()
    for entry in entries:
        media = (entry or {}).get("media") or {}
        genres.update(g for g in (media.get("genres") or []) if isinstance(g, str))
        for tag in media.get("tags") or []:
            if isinstance(tag, dict) and not tag.get("isMediaSpoiler") and (tag.get("rank") or 0) >= 75 and tag.get("name"):
                tags.add(tag["name"])
    return genres, tags

class ServerTaste(commands.Cog):
    """Reports only guild members who explicitly opted in."""
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def cog_load(self) -> None:
        await execute_db_operation(
            "create guild-scoped server taste opt-ins",
            """CREATE TABLE IF NOT EXISTS server_taste_opt_ins (
                guild_id BIGINT NOT NULL,
                discord_id BIGINT NOT NULL,
                opted_in_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (guild_id, discord_id)
            )""",
        )

    @app_commands.command(name="server-taste", description="View opt-in, aggregate AniList interests for this server")
    @app_commands.guild_only()
    @app_commands.choices(
        action=[
            app_commands.Choice(name="View aggregate report", value="report"),
            app_commands.Choice(name="Opt in", value="opt-in"),
            app_commands.Choice(name="Opt out", value="opt-out"),
        ],
        category=[
            app_commands.Choice(name="Anime", value="ANIME"),
            app_commands.Choice(name="Manga", value="MANGA"),
        ],
    )
    @app_commands.describe(action="View the report or change your participation", category="Media category used for the aggregate report")
    @command_meta(section="Community", name="Server Taste")
    async def server_taste(self, interaction: discord.Interaction, action: str = "report", category: str = "ANIME") -> None:
        if interaction.guild is None:
            await interaction.response.send_message("This command is only available in a server.", ephemeral=True)
            return
        guild_id = interaction.guild.id
        user_id = interaction.user.id
        if action == "opt-in":
            await interaction.response.defer(ephemeral=True, thinking=True)
            await execute_db_operation(
                "opt user into guild server taste",
                "INSERT INTO server_taste_opt_ins (guild_id, discord_id) VALUES (?, ?) ON CONFLICT (guild_id, discord_id) DO NOTHING",
                (guild_id, user_id),
            )
            await interaction.followup.send(
                "You opted in to this server's aggregate taste report. Only public AniList list metadata is counted; individual profiles and titles are not shown. This consent applies only to this server.",
                ephemeral=True,
            )
            return
        if action == "opt-out":
            await interaction.response.defer(ephemeral=True, thinking=True)
            await execute_db_operation(
                "opt user out of guild server taste",
                "DELETE FROM server_taste_opt_ins WHERE guild_id = ? AND discord_id = ?",
                (guild_id, user_id),
            )
            await interaction.followup.send("You are opted out of this server's taste report. The opt-out applies only to this server.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=False, thinking=True)
        try:
            consented = await execute_db_operation(
                "list server taste participants for current guild",
                "SELECT discord_id FROM server_taste_opt_ins WHERE guild_id = ?",
                (guild_id,),
                fetch_type="all",
            )
            opted_ids = {int(row["discord_id"]) for row in (consented or [])}
            guild_users = await get_all_users_guild_aware(guild_id)
            usernames = {
                int(row["discord_id"]): row.get("anilist_username")
                for row in (dict(row) for row in (guild_users or []))
                if int(row["discord_id"]) in opted_ids and row.get("anilist_username")
            }
            if not usernames:
                await interaction.followup.send(
                    "No participating members with a linked AniList username were found. Members may opt in with action:Opt in; their AniList account must also be linked in this server.",
                    ephemeral=True,
                )
                return
            genre_counts: Counter[str] = Counter()
            tag_counts: Counter[str] = Counter()
            successful = 0
            semaphore = asyncio.Semaphore(4)

            async def collect(username: str) -> tuple[set[str], set[str]] | None:
                async with semaphore:
                    try:
                        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15)) as session:
                            payload = await post_graphql(session, TASTE_QUERY, {"name": username, "type": category}, timeout=15)
                        collection = (payload or {}).get("MediaListCollection")
                        if not collection:
                            return None
                        entries = [entry for listing in (collection.get("lists") or []) for entry in (listing.get("entries") or [])]
                        return aggregate_member_interests(entries)
                    except (aiohttp.ClientError, asyncio.TimeoutError, ValueError, TypeError):
                        log.info("AniList taste sample unavailable for a participant in guild %s", guild_id)
                        return None

            results = await asyncio.gather(*(collect(name) for name in usernames.values()))
            for result in results:
                if result is None:
                    continue
                successful += 1
                genres, tags = result
                genre_counts.update(genres)
                tag_counts.update(tags)
            embed = discord.Embed(
                title=f"Server Taste · {'Anime' if category == 'ANIME' else 'Manga'}",
                color=discord.Color.blurple(),
                description=f"**Participating public accounts:** {successful}\nInterests are counted at most once per account. Individual member names, titles, scores, and list contents are not displayed.",
            )
            if successful < 3:
                embed.add_field(name="Sample too small", value="At least 3 participating accounts with publicly accessible AniList lists are required before showing aggregate interests.", inline=False)
            else:
                embed.add_field(name="Most represented genres", value="\n".join(f"• {name} — {count} accounts" for name, count in genre_counts.most_common(8)) or "No genre metadata was available.", inline=True)
                embed.add_field(name="Common themes", value="\n".join(f"• {name} — {count} accounts" for name, count in tag_counts.most_common(8)) or "No eligible tag metadata was available.", inline=True)
            embed.set_footer(text="Source: public AniList list metadata from opted-in accounts. Private/unavailable lists are excluded; results are not representative of nonparticipants.")
            await interaction.followup.send(embed=embed)
        except Exception:
            log.exception("Failed to produce server taste report for guild %s", guild_id)
            await interaction.followup.send("The report could not be generated because guild data or AniList was unavailable. No report data was changed.", ephemeral=True)

async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(ServerTaste(bot))
