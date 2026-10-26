"""Interactive entry point for Lemegeton's media discovery and community features."""
from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from cogs_test.general_commands.dashboard import command_meta

HUB_SECTIONS = {
    "discovery": {
        "label": "Media discovery",
        "description": (
            "**Find and connect titles**\n"
            "• /browse — search supported media categories\n"
            "• /connections — explore known relationships and adaptations\n"
            "• /franchise — provider-attributed franchise relationships\n"
            "• /similar — provider recommendations and genre-overlap matches\n"
            "• /compare — compare two or more media entries\n"
            "• /reading-order — inspect known relationships and release dates\n"
            "• /link-suggest — submit a missing relationship for review"
        ),
    },
    "novels": {
        "label": "Novel readers",
        "description": (
            "**Books, light novels and webnovels**\n"
            "• /reading-club — nominate, vote and schedule community reads\n"
            "• /webnovel-updates — query Novel Updates metadata\n"
            "• /author-works — search Google Books by author\n"
            "• /reading-order — follow supported publication/adaptation relations\n"
            "• /chapter-discussion — start a spoiler-aware chapter thread\n"
            "• /quotes — discover short, attributed excerpts"
        ),
    },
    "screen": {
        "label": "Movies and television",
        "description": (
            "**Explore films and TV series**\n"
            "• /where-to-watch — region-specific TMDB availability\n"
            "• /person-credits — cast and crew filmography\n"
            "• /trailers — TMDB-listed videos and trailers\n"
            "• /collection-guide — TMDB movie collections\n"
            "• /tv-guide — seasons, episodes and available air dates\n"
            "• /release-calendar — supported upcoming anime/movie/TV dates\n"
            "• /episode-discussion — start an episode discussion\n"
            "• /media-region — set this server's default streaming region"
        ),
    },
    "archives": {
        "label": "Community archives",
        "description": (
            "**Browse and contribute**\n"
            "• /panels — manga panel archive\n"
            "• /quotes — short quotes with source attribution\n"
            "• /fanworks — credited fan art, edits and wallpapers\n"
            "• /moodboards — themed multi-work boards\n"
            "• /soundtracks — legal platform links for music\n"
            "• /scenes — memorable scenes and references\n"
            "• /recommendation-board — member-written recommendations\n"
            "• /theories — spoiler-marked fan theories\n"
            "• /panel-of-the-day — feature a safe archived panel\n"
            "• /archive-mine — check your submissions and review status\n"
            "• /archive-report — flag an approved entry for review\n"
            "• /archive-review — review submissions from this server\n"
            "• /archive-report-review — triage archive reports"
        ),
    },
    "events": {
        "label": "Community events",
        "description": (
            "**Make discovery social**\n"
            "• /media-night — community media voting\n"
            "• /media-bracket — title elimination poll\n"
            "• /adaptation-vote — vote between two versions\n"
            "• /media-quiz — source-linked community trivia\n"
            "• /episode-discussion and /chapter-discussion — spoiler-aware threads"
        ),
    },
}


class DiscoveryHubView(discord.ui.View):
    def __init__(self, owner_id: int):
        super().__init__(timeout=240)
        self.owner_id = owner_id
        options = [
            discord.SelectOption(label=item["label"], value=key, description=item["label"][:100])
            for key, item in HUB_SECTIONS.items()
        ]
        select = discord.ui.Select(placeholder="Choose a Lemegeton section", min_values=1, max_values=1, options=options)
        select.callback = self._select_section
        self.add_item(select)
        close = discord.ui.Button(label="Close", style=discord.ButtonStyle.secondary, emoji="✖️")
        close.callback = self._close
        self.add_item(close)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message("Only the person who opened this hub can control it.", ephemeral=True)
            return False
        return True

    async def _select_section(self, interaction: discord.Interaction) -> None:
        section = self.children[0].values[0]
        data = HUB_SECTIONS.get(section)
        if not data:
            await interaction.response.send_message("That section is not available.", ephemeral=True)
            return
        embed = discord.Embed(title=f"Lemegeton · {data['label']}", description=data["description"], color=discord.Color.blurple())
        embed.set_footer(text="Commands are available when registered and enabled in your server.")
        await interaction.response.edit_message(embed=embed, view=self)

    async def _close(self, interaction: discord.Interaction) -> None:
        await interaction.response.edit_message(content="Discovery Hub closed.", embed=None, view=None)


class DiscoveryHub(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="discovery-hub", description="Open the central guide to Lemegeton's media and community commands")
    @app_commands.guild_only()
    @command_meta(section="Media Discovery", name="Discovery Hub")
    async def discovery_hub(self, interaction: discord.Interaction) -> None:
        embed = discord.Embed(
            title="Lemegeton · Discovery Hub",
            description=(
                "One starting point for cross-media discovery, novel readers, movies, television and community archives.\n\n"
                "Choose a section from the menu below. Each section lists commands that connect into the existing Lemegeton ecosystem."
            ),
            color=discord.Color.blurple(),
        )
        embed.add_field(name="Connected providers", value="AniList · TMDB · Google Books · Novel Updates scraper", inline=False)
        embed.add_field(name="Community content", value="Contributions are stored in the database; archive submissions wait for a moderator from the originating server.", inline=False)
        embed.set_footer(text="Provider relationships, recommendations and community suggestions are labelled separately.")
        await interaction.response.send_message(embed=embed, view=DiscoveryHubView(interaction.user.id), ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(DiscoveryHub(bot))
