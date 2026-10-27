"""Interactive entry point for Lemegeton's media discovery and community features."""
from __future__ import annotations

import re

import discord
from discord import app_commands
from discord.ext import commands

from helpers.command_error_handler import FeedbackAwareView, handle_application_command_error
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
            "• /reading — explore publication relationships and reading order\n"
            "• /link-suggest — submit a missing relationship for review"
        ),
    },
    "novels": {
        "label": "Novel readers",
        "description": (
            "**Books, light novels and webnovels**\n"
            "• /reading — nominations, votes, selection, scheduling and reading order\n"
            "• /discussion — spoiler-aware chapter, volume, episode, season and general threads\n"
            "• /archive — discover quotes, fanworks, moodboards, scenes, soundtracks, recommendations and theories\n"
            "• /webnovel-updates — query Novel Updates metadata\n"
            "• /author-works — search Google Books by author"
        ),
    },
    "screen": {
        "label": "Movies and television",
        "description": (
            "**Explore films and TV series**\n"
            "• /browse — leave the title blank for multi-result movie/TV discovery and advanced filters\n"
            "• /where-to-watch — region-specific TMDB availability\n"
            "• /person-credits — cast and crew filmography\n"
            "• /trailers — TMDB-listed videos and trailers\n"
            "• /collection-guide — TMDB movie collections\n"
            "• /tv-guide — seasons, episodes and available air dates\n"
            "• /release-calendar — supported upcoming anime/movie/TV dates\n"
            "• /discussion — start a spoiler-aware episode or season thread\n"
            "• /media-region — set this server's default streaming region"
        ),
    },
    "archives": {
        "label": "Community archives",
        "description": (
            "**Browse and contribute**\n"
            "• /panels — manga panel archive\n"
            "• /archive — quotes, fanworks, moodboards, soundtracks, scenes, recommendations and theories\n"
            "• /panel-of-the-day — feature a safe archived panel"
        ),
    },
    "gaming": {
        "label": "Gaming",
        "description": (
            "**Discover games and connect them to other media**\n"
            "• /game — IGDB metadata with exact-title Steam enrichment\n"
            "• /link-suggest — submit a game-to-media relationship for moderator review\n"
            "• Approved cross-media links and this server's community resources appear in game results"
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
            "• /discussion — spoiler-aware chapter, volume, episode and season threads"
        ),
    },
}


class DiscoveryHubView(FeedbackAwareView):
    def __init__(self, owner_id: int, registered_command_names: set[str] | None = None):
        super().__init__(timeout=240)
        self.owner_id = owner_id
        self.registered_command_names = registered_command_names
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
        description = data["description"]
        if self.registered_command_names is not None:
            visible_lines = []
            for line in description.splitlines():
                mentioned = re.findall(r"/([a-z][a-z0-9_-]*)", line.casefold())
                if mentioned and any(name not in self.registered_command_names for name in mentioned):
                    continue
                visible_lines.append(line)
            description = "\n".join(visible_lines).strip()
            if not any(line.lstrip().startswith("•") for line in visible_lines):
                description += "\n\nNo commands in this section are currently registered."
        embed = discord.Embed(title=f"Lemegeton · {data['label']}", description=description[:4000], color=discord.Color.blurple())
        embed.set_footer(text="Only registered commands are listed; availability may also depend on server configuration.")
        await interaction.response.edit_message(embed=embed, view=self)

    async def _close(self, interaction: discord.Interaction) -> None:
        await interaction.response.edit_message(content="Discovery Hub closed.", embed=None, view=None)


class DiscoveryHub(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    def _registered_command_names(self) -> set[str] | None:
        """Return slash commands currently loaded; None disables filtering if introspection fails."""
        try:
            tree = getattr(self.bot, "tree", None)
            walker = getattr(tree, "walk_commands", None)
            if not callable(walker):
                return None
            return {str(command.name) for command in walker() if getattr(command, "name", None)}
        except Exception:
            log.exception("Could not inspect registered commands for the Discovery Hub")
            return None

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
        await interaction.response.send_message(
            embed=embed,
            view=DiscoveryHubView(interaction.user.id, self._registered_command_names()),
            ephemeral=True,
        )


    async def cog_app_command_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError) -> None:
        """Keep unexpected discovery UI failures private and traceable."""
        await handle_application_command_error(interaction, error)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(DiscoveryHub(bot))
