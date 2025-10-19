# serverinfo.py
"""
Aesthetic Server Info Cog for discord.py v2 (app_commands)
Features:
- /server command (works in any guild the bot is in)
- Detailed, pastel-themed embed layout
- Banner/icon detection, stats (members, channels, roles, boosts, emojis, stickers)
- Human vs bot breakdown, presence stats
- Paginated sections with buttons
- Lightweight caching for repeated calls
- Logging to local SQLite DB for command usage stats
- Helpful utilities and graceful handling for DMs (choose a guild via menu)
"""

import discord
from discord import app_commands
from discord.ext import commands, tasks
from datetime import datetime, timezone
import asyncio
import sqlite3
import math
import textwrap
from typing import Optional, List

PALETTE = {
    "soft_pink": discord.Color.from_rgb(255, 182, 193),
    "muted_purple": discord.Color.from_rgb(197, 153, 210),
    "soft_peach": discord.Color.from_rgb(255, 218, 185),
    "accent": discord.Color.from_rgb(210, 180, 222)
}


# ---------------------------
# Simple SQLite logging utils
# ---------------------------
def init_db(path: str = "bot_meta.db"):
    conn = sqlite3.connect(path)
    cur = conn.cursor()
    cur.execute(
        """CREATE TABLE IF NOT EXISTS serverinfo_usage(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            guild_id INTEGER,
            guild_name TEXT,
            user_id INTEGER,
            invoked_at TEXT
        )"""
    )
    conn.commit()
    conn.close()


def log_serverinfo(guild: Optional[discord.Guild], user: discord.User, path: str = "bot_meta.db"):
    conn = sqlite3.connect(path)
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO serverinfo_usage(guild_id, guild_name, user_id, invoked_at) VALUES (?, ?, ?, ?)",
        (guild.id if guild else None, guild.name if guild else None, user.id, datetime.utcnow().isoformat())
    )
    conn.commit()
    conn.close()


# --------------------------------
# Helper / Utility functions
# --------------------------------
def fmt_date(dt: datetime) -> str:
    if not dt:
        return "Unknown"
    return dt.astimezone(timezone.utc).strftime("%b %d, %Y • %H:%M UTC")


def short_number(n: int) -> str:
    # 1,200 -> 1.2K etc.
    if n < 1000:
        return str(n)
    magnitude = int(math.log10(n) // 3)
    suffixes = ["", "K", "M", "B", "T"]
    value = n / (1000 ** magnitude)
    return f"{value:.1f}{suffixes[magnitude]}"


def presence_breakdown(members: List[discord.Member]) -> dict:
    status_map = {"online": 0, "idle": 0, "dnd": 0, "offline": 0}
    for m in members:
        try:
            st = str(m.status)
            status_map[st] = status_map.get(st, 0) + 1
        except Exception:
            status_map["offline"] += 1
    return status_map


# ---------------------------
# Interactive View: Page Nav
# ---------------------------
class PaginatorView(discord.ui.View):
    def __init__(self, pages: List[discord.Embed], author: discord.User, timeout: int = 120):
        super().__init__(timeout=timeout)
        self.pages = pages
        self.current = 0
        self.author = author

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        # only allow the person who invoked the command to use the paginator
        if interaction.user.id != self.author.id:
            await interaction.response.send_message("This paginator isn't for you — use your own command!", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="⏮️ First", style=discord.ButtonStyle.secondary)
    async def first(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.current = 0
        await interaction.response.edit_message(embed=self.pages[self.current], view=self)

    @discord.ui.button(label="◀️ Prev", style=discord.ButtonStyle.secondary)
    async def prev(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.current = max(0, self.current - 1)
        await interaction.response.edit_message(embed=self.pages[self.current], view=self)

    @discord.ui.button(label="▶️ Next", style=discord.ButtonStyle.secondary)
    async def next(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.current = min(len(self.pages) - 1, self.current + 1)
        await interaction.response.edit_message(embed=self.pages[self.current], view=self)

    @discord.ui.button(label="⏭️ Last", style=discord.ButtonStyle.secondary)
    async def last(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.current = len(self.pages) - 1
        await interaction.response.edit_message(embed=self.pages[self.current], view=self)

    @discord.ui.button(label="❌ Close", style=discord.ButtonStyle.danger)
    async def close(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.message.delete()
        self.stop()


# ---------------------------
# Guild select for DMs fallback
# ---------------------------
class GuildSelect(discord.ui.Select):
    def __init__(self, bot: commands.Bot, author: discord.User):
        self.bot = bot
        self.author = author
        options = []
        # list first 25 guilds (Discord limit)
        guilds = sorted(bot.guilds, key=lambda g: g.member_count, reverse=True)[:25]
        for g in guilds:
            options.append(discord.SelectOption(label=g.name, value=str(g.id), description=f"{g.member_count} members"))
        super().__init__(placeholder="Select a server...", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.author.id:
            await interaction.response.send_message("This menu isn't for you.", ephemeral=True)
            return
        guild_id = int(self.values[0])
        guild = self.bot.get_guild(guild_id)
        if not guild:
            await interaction.response.send_message("I can't access that guild anymore.", ephemeral=True)
            return
        # build an embed for the selected guild and replace the message
        cog = interaction.client.get_cog("ServerInfo")
        if cog:
            embed_pages = await cog.build_guild_pages(guild, interaction.user)
            view = PaginatorView(embed_pages, interaction.user)
            await interaction.response.edit_message(content=f"Showing info for **{guild.name}**", embed=embed_pages[0], view=view)
        else:
            await interaction.response.send_message("Something went wrong (cog missing).", ephemeral=True)


class GuildSelectView(discord.ui.View):
    def __init__(self, bot: commands.Bot, author: discord.User):
        super().__init__(timeout=60)
        self.add_item(GuildSelect(bot, author))


# ---------------------------
# The Cog
# ---------------------------
class ServerInfo(commands.Cog):
    """Server info with aesthetic embeds, paginator, and caching"""
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        init_db()
        self._cache = {}  # guild_id -> (timestamp, pages)
        self.cache_ttl = 45  # seconds
        self.cleanup_cache.start()

    def cog_unload(self):
        self.cleanup_cache.cancel()

    @tasks.loop(seconds=60.0)
    async def cleanup_cache(self):
        # remove expired cache entries
        now = datetime.utcnow().timestamp()
        to_del = []
        for gid, (ts, _) in list(self._cache.items()):
            if now - ts > self.cache_ttl:
                to_del.append(gid)
        for gid in to_del:
            del self._cache[gid]

    @cleanup_cache.before_loop
    async def before_cleanup(self):
        await self.bot.wait_until_ready()

    # ---------------------------
    # Core builder: create embed pages for a guild
    # ---------------------------
    async def build_guild_pages(self, guild: discord.Guild, requester: discord.User) -> List[discord.Embed]:
        """
        Construct multiple embed pages for the guild info. Returns a list of embeds for pagination.
        """
        pages: List[discord.Embed] = []
        # BASIC / HERO EMBED
        emb = discord.Embed(
            title=f"🌸 {guild.name}",
            description=guild.description or "No server description set.",
            color=PALETTE["soft_pink"],
            timestamp=datetime.utcnow()
        )
        # banner vs icon
        try:
            if getattr(guild, "banner", None):
                emb.set_image(url=guild.banner.url)
            elif guild.icon:
                emb.set_thumbnail(url=guild.icon.url)
        except Exception:
            # some guilds and intents might not expose banner/icon
            if guild.icon:
                emb.set_thumbnail(url=str(guild.icon.url))

        # Header fields
        owner = guild.owner.mention if guild.owner else f"{guild.owner if guild.owner else 'Unknown'}"
        emb.add_field(name="👑 Owner", value=owner, inline=True)
        emb.add_field(name="🆔 Server ID", value=f"`{guild.id}`", inline=True)
        emb.add_field(name="📆 Created", value=fmt_date(guild.created_at), inline=True)

        # membership summary
        members = guild.members
        humans = len([m for m in members if not m.bot])
        bots = len([m for m in members if m.bot])
        emb.add_field(name="👥 Members", value=f"{short_number(guild.member_count)} total\n🧍 {humans} humans\n🤖 {bots} bots", inline=False)

        emb.add_field(name="💬 Channels", value=f"📝 {len(guild.text_channels)} text\n🔊 {len(guild.voice_channels)} voice\n📁 {len(guild.categories)} categories", inline=True)
        emb.add_field(name="🎭 Roles", value=f"{len(guild.roles)} total", inline=True)
        emb.add_field(name="🚀 Boosts", value=f"Tier {getattr(guild, 'premium_tier', getattr(guild, 'premium_tier', 0))}\n{getattr(guild, 'premium_subscription_count', 0)} boosts", inline=True)

        # quick stats footer
        emb.set_footer(text=f"Requested by {requester}", icon_url=requester.display_avatar.url)
        pages.append(emb)

        # PRESENCE / STATUS PAGE
        presence = presence_breakdown(members)
        emb2 = discord.Embed(
            title=f"🌸 {guild.name} — Presence & Activity",
            color=PALETTE["muted_purple"],
            timestamp=datetime.utcnow()
        )
        emb2.add_field(name="🟢 Online", value=str(presence.get("online", 0)), inline=True)
        emb2.add_field(name="🌙 Idle", value=str(presence.get("idle", 0)), inline=True)
        emb2.add_field(name="⛔ DND", value=str(presence.get("dnd", 0)), inline=True)
        emb2.add_field(name="⚫ Offline", value=str(presence.get("offline", 0)), inline=True)

        # top 8 activities summary (approx)
        activity_map = {}
        for m in members:
            act = None
            try:
                if m.activity:
                    act = getattr(m.activity, "name", str(m.activity))
            except Exception:
                pass
            if act:
                activity_map[act] = activity_map.get(act, 0) + 1
        top_activities = sorted(activity_map.items(), key=lambda x: x[1], reverse=True)[:8]
        if top_activities:
            emb2.add_field(name="🎮 Top Activities", value="\n".join([f"{a} — {c}" for a, c in top_activities]), inline=False)
        else:
            emb2.add_field(name="🎮 Top Activities", value="No notable activities detected", inline=False)
        pages.append(emb2)

        # EMOJI & STICKERS PAGE
        emb3 = discord.Embed(
            title=f"🌸 {guild.name} — Emojis & Stickers",
            color=PALETTE["soft_peach"],
            timestamp=datetime.utcnow()
        )
        try:
            emb3.add_field(name="😄 Emojis", value=f"{len(guild.emojis)} total", inline=True)
            emb3.add_field(name="🏷️ Stickers", value=f"{len(guild.stickers)} total", inline=True)
            # show a sample of up to 10 emojis (by name)
            sample_emoji_names = [str(e) for e in guild.emojis[:10]]
            emb3.add_field(name="Sample Emojis", value=" ".join(sample_emoji_names) if sample_emoji_names else "No emojis", inline=False)
        except Exception:
            emb3.add_field(name="Emojis / Stickers", value="Permission or API limitation prevented access", inline=False)
        pages.append(emb3)

        # ROLES & HIERARCHY PAGE
        emb4 = discord.Embed(
            title=f"🌸 {guild.name} — Roles & Top Members",
            color=PALETTE["accent"],
            timestamp=datetime.utcnow()
        )
        try:
            top_roles = [r for r in guild.roles if r != guild.default_role][-10:]
            top_roles = list(reversed(top_roles))
            roles_display = "\n".join([f"{r.mention} — {r.members and len(r.members) or 0} members" for r in top_roles]) or "No roles"
            emb4.add_field(name="Top Roles (sample)", value=roles_display, inline=False)
        except Exception:
            emb4.add_field(name="Roles", value="Could not fetch role details", inline=False)

        # show top 8 members by join date (oldest 8)
        try:
            sorted_members = sorted([m for m in members if not m.bot], key=lambda m: m.joined_at or datetime.utcnow())[:8]
            emb4.add_field(name="Members (Oldest joins)", value="\n".join([f"{m.display_name} — {fmt_date(m.joined_at)}" for m in sorted_members]), inline=False)
        except Exception:
            pass
        pages.append(emb4)

        # MODERATION / SAFETY PAGE (basic)
        emb5 = discord.Embed(
            title=f"🌸 {guild.name} — Moderation & Safety",
            color=PALETTE["soft_pink"],
            timestamp=datetime.utcnow()
        )
        # basic server settings
        try:
            verification = str(guild.verification_level).replace("_", " ").title()
            emb5.add_field(name="🛡️ Verification Level", value=verification, inline=True)
            emb5.add_field(name="🔐 Explicit Content Filter", value=str(guild.explicit_content_filter).title(), inline=True)
            emb5.add_field(name="🧭 Preferred Locale", value=str(guild.preferred_locale), inline=True)
        except Exception:
            emb5.add_field(name="Moderation Info", value="Some guild settings couldn't be fetched.", inline=False)
        pages.append(emb5)

        # STATS SUMMARY PAGE
        emb6 = discord.Embed(
            title=f"🌸 {guild.name} — Quick Summary",
            color=PALETTE["muted_purple"],
            timestamp=datetime.utcnow()
        )
        emb6.add_field(name="Members (humans/bots)", value=f"{humans}/{bots}", inline=True)
        emb6.add_field(name="Channels (text/voice)", value=f"{len(guild.text_channels)}/{len(guild.voice_channels)}", inline=True)
        emb6.add_field(name="Roles / Emojis", value=f"{len(guild.roles)} roles • {len(guild.emojis)} emojis", inline=True)
        pages.append(emb6)

        return pages

    # ---------------------------
    # /server command
    # ---------------------------
    @app_commands.command(name="server", description="Displays detailed and aesthetic server information.")
    async def server(self, interaction: discord.Interaction):
        """
        Public slash command handler. Works in any guild the bot is present in.
        If used in DMs, offers the user to pick one of the bot's guilds.
        """
        await interaction.response.defer(thinking=True, ephemeral=False)  # quick ack
        # If invoked in a guild, use that guild
        if interaction.guild:
            guild = interaction.guild
            # Use cache if present
            cached = self._cache.get(guild.id)
            now_ts = datetime.utcnow().timestamp()
            if cached and (now_ts - cached[0]) <= self.cache_ttl:
                pages = cached[1]
            else:
                pages = await self.build_guild_pages(guild, interaction.user)
                self._cache[guild.id] = (now_ts, pages)
            # log
            try:
                log_serverinfo(guild, interaction.user)
            except Exception:
                pass
            view = PaginatorView(pages, interaction.user)
            await interaction.followup.send(embed=pages[0], view=view)
            return

        # Otherwise (DM context) — offer to select a guild
        view = GuildSelectView(self.bot, interaction.user)
        await interaction.followup.send(
            "You're in DMs — pick a server I am in to view its info:", view=view, ephemeral=True
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(ServerInfo(bot))
