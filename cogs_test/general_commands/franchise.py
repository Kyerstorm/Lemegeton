"""AniList relationship browser for source works, adaptations, sequels, and spin-offs."""
from __future__ import annotations
import discord
from discord import app_commands
from discord.ext import commands
from helpers.anilist_helper import fetch_media_by_id, fetch_media_by_search
from cogs_test.general_commands.dashboard import command_meta

def media_title(item: dict) -> str:
    title = item.get("title") or {}
    return title.get("english") or title.get("romaji") or title.get("native") or "Untitled"

def relation_embed(media: dict, page: int = 0) -> discord.Embed:
    relations = ((media.get("relations") or {}).get("edges") or [])
    title = media_title(media)
    embed = discord.Embed(
        title=f"🧬 Franchise · {title}"[:256],
        url=media.get("siteUrl"),
        description="Explore source material, sequels, prequels, spin-offs, and adaptations using **AniList's own relationship labels**. No single viewing or reading order is implied.",
        color=discord.Color.blurple(),
    )
    cover = (media.get("coverImage") or {}).get("large")
    if cover:
        embed.set_thumbnail(url=cover)
    if not relations:
        embed.description = "AniList does not supply related entries for this title. No sequel, source-material, or adaptation relationships were inferred."
        return embed
    page_size = 10
    start = page * page_size
    visible = relations[start:start + page_size]
    lines = []
    for edge in visible:
        node = edge.get("node") or {}
        node_title = media_title(node)
        url = node.get("siteUrl")
        linked_title = f"[{node_title}]({url})" if url else node_title
        kind = node.get("type") or "Unknown type"
        status = node.get("status") or "Status unavailable"
        lines.append(f"**{str(edge.get('relationType') or 'RELATED').replace('_', ' ').title()}** · {kind} · {status}\n{linked_title}")
    embed.add_field(
        name=f"🔗 Related entries ({start + 1}–{start + len(visible)} of {len(relations)})",
        value="\n\n".join(lines)[:3900],
        inline=False,
    )
    embed.set_footer(text=f"📚 Source: AniList relationships · Page {page + 1}/{max(1, (len(relations) - 1) // page_size + 1)}")
    return embed

class RelationView(discord.ui.View):
    def __init__(self, media: dict, owner_id: int):
        super().__init__(timeout=180)
        self.media = media
        self.owner_id = owner_id
        self.page = 0
        self.max_page = max(0, (len((media.get("relations") or {}).get("edges") or []) - 1) // 10)
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
        self.results = {str(item["id"]): item for item in results if item.get("id")}
        options = [
            discord.SelectOption(
                label=media_title(item)[:100],
                value=str(item["id"]),
                description=f"{item.get('format') or owner.category} · {item.get('status') or 'Status unavailable'}"[:100],
            )
            for item in results[:25] if item.get("id")
        ]
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
        media = await fetch_media_by_id(int(selected["id"]), view.category)
        if not media:
            await interaction.edit_original_response(content="AniList could not load relationships for this title.", embed=None, view=None)
            return
        relation_view = RelationView(media, view.owner_id)
        await interaction.edit_original_response(content=None, embed=relation_embed(media), view=relation_view)

class FranchiseSearchView(discord.ui.View):
    def __init__(self, owner_id: int, category: str, results: list[dict]):
        super().__init__(timeout=180)
        self.owner_id = owner_id
        self.category = category
        self.add_item(FranchiseSelect(self, results))

class Franchise(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="franchise", description="Explore AniList source material, sequels, prequels, and adaptations")
    @app_commands.guild_only()
    @app_commands.choices(category=[
        app_commands.Choice(name="Anime", value="ANIME"),
        app_commands.Choice(name="Manga", value="MANGA"),
    ])
    @app_commands.describe(title="Anime or manga title", category="AniList media category")
    @command_meta(section="Media Discovery", name="Franchise")
    async def franchise(self, interaction: discord.Interaction, title: str, category: str = "ANIME") -> None:
        if not title.strip():
            await interaction.response.send_message("Enter an anime or manga title.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True, thinking=True)
        results = await fetch_media_by_search(title.strip(), category, per_page=8)
        if not results:
            await interaction.followup.send("AniList returned no matching title. Try an alternate title or check the spelling.", ephemeral=True)
            return
        view = FranchiseSearchView(interaction.user.id, category, results)
        await interaction.followup.send(
            "🧬 **Choose the exact title** to explore its provider-supplied relationships. Similar names alone are not treated as franchise links.",
            view=view, ephemeral=True,
        )

async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Franchise(bot))
