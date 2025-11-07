# serverinfo.py
"""
Dark Luxury ServerInfo Cog for discord.py v2
- /server command (works in any guild the bot is in)
- Elegant "Dark Luxury" embeds (deep blacks, royal gold accent)
- Paginated embeds with buttons (First / Prev / Next / Last / Close)
- Guild selection when used in DMs (select from bot's guilds)
- Lightweight caching for repeated calls
- SQLite logging of usage stats (bot_meta.db)
- Graceful error handling and fallbacks
"""

import discord
from discord.ext import commands, tasks
from discord import app_commands
from datetime import datetime, timezone
import aiosqlite
import math
import asyncio
from typing import List, Optional

from cogs_test.general_commands.dashboard import command_meta
from helpers.embed_helper import build_warning_embed

# ---------------------------
# Palette & Embed helper
# ---------------------------
PALETTE = {
    "deep_black": discord.Color.from_rgb(18, 18, 20),
    "midnight_blue": discord.Color.from_rgb(28, 30, 45),
    "royal_gold": discord.Color.from_rgb(212, 175, 55),
    "velvet_purple": discord.Color.from_rgb(85, 45, 110),
    "accent": discord.Color.from_rgb(100, 70, 140)
}


def create_darlux_embed(title: Optional[str] = None, description: Optional[str] = None, accent: str = "royal_gold"):
    emb = discord.Embed(
        title=title,
        description=description,
        color=PALETTE.get(accent, PALETTE["royal_gold"]),
        timestamp=datetime.utcnow()
    )
    return emb


# ---------------------------
# SQLite logging utilities
# ---------------------------
DB_PATH = "data/bot_meta.db"


async def init_db(path: str = DB_PATH):
    async with aiosqlite.connect(path) as conn:
        await conn.execute("""
        CREATE TABLE IF NOT EXISTS serverinfo_usage (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            guild_id INTEGER,
            guild_name TEXT,
            user_id INTEGER,
            invoked_at TEXT
        )
        """)
        await conn.commit()


async def log_serverinfo(guild: Optional[discord.Guild], user: discord.User, path: str = DB_PATH):
    try:
        async with aiosqlite.connect(path) as conn:
            await conn.execute(
                "INSERT INTO serverinfo_usage (guild_id, guild_name, user_id, invoked_at) VALUES (?, ?, ?, ?)",
                (guild.id if guild else None, guild.name if guild else None, user.id, datetime.utcnow().isoformat())
            )
            await conn.commit()
    except Exception:
        # don't crash — logging is best-effort
        pass


# ---------------------------
# Helper utilities
# ---------------------------
def fmt_date(dt: Optional[datetime]) -> str:
    if not dt:
        return "Unknown"
    # ensure timezone-aware
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).strftime("%b %d, %Y • %H:%M UTC")


def short_number(n: int) -> str:
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
            st = str(getattr(m, "status", "offline"))
            status_map[st] = status_map.get(st, 0) + 1
        except Exception:
            status_map["offline"] += 1
    return status_map


# ---------------------------
# Interactive pagination view
# ---------------------------
class PaginatorView(discord.ui.View):
    def __init__(self, pages: List[discord.Embed], author: discord.User, timeout: int = 120):
        super().__init__(timeout=timeout)
        self.pages = pages
        self.author = author
        self.index = 0

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author.id:
            await interaction.response.send_message(
                embed=build_warning_embed(
                    description="This control is for the command user only."
                ),
                ephemeral=True
            )
            return False
        return True

    @discord.ui.button(label="⏮️ First", style=discord.ButtonStyle.secondary)
    async def first(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.index = 0
        await interaction.response.edit_message(embed=self.pages[self.index], view=self)

    @discord.ui.button(label="◀️ Prev", style=discord.ButtonStyle.secondary)
    async def prev(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.index = max(0, self.index - 1)
        await interaction.response.edit_message(embed=self.pages[self.index], view=self)

    @discord.ui.button(label="▶️ Next", style=discord.ButtonStyle.secondary)
    async def next(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.index = min(len(self.pages) - 1, self.index + 1)
        await interaction.response.edit_message(embed=self.pages[self.index], view=self)

    @discord.ui.button(label="⏭️ Last", style=discord.ButtonStyle.secondary)
    async def last(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.index = len(self.pages) - 1
        await interaction.response.edit_message(embed=self.pages[self.index], view=self)

    @discord.ui.button(label="❌ Close", style=discord.ButtonStyle.danger)
    async def close(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            await interaction.message.delete()
        except Exception:
            pass
        self.stop()


# ---------------------------
# Guild selection UI (for DMs)
# ---------------------------
class GuildSelect(discord.ui.Select):
    def __init__(self, bot: commands.Bot, author: discord.User):
        self.bot = bot
        self.author = author
        options = []
        guilds = sorted(bot.guilds, key=lambda g: g.member_count, reverse=True)[:25]
        for g in guilds:
            desc = f"{g.member_count} members"
            options.append(discord.SelectOption(label=g.name[:100], value=str(g.id), description=desc))
        super().__init__(placeholder="Select a server to inspect...", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.author.id:
            await interaction.response.send_message(
                embed=build_warning_embed(
                    description="This menu isn't for you."
                ),
                ephemeral=True
            )
            return
        gid = int(self.values[0])
        guild = self.bot.get_guild(gid)
        if not guild:
            await interaction.response.send_message(
                embed=build_warning_embed(
                    description="I cannot access that guild anymore."
                ),
                ephemeral=True
            )
            return
        # Build embed pages via cog method
        cog = interaction.client.get_cog("ServerInfo")
        if not cog:
            await interaction.response.send_message(
                embed=build_warning_embed(
                    description="ServerInfo cog not loaded."
                ),
                ephemeral=True
            )
            return
        pages = await cog.build_guild_pages(guild, interaction.user)
        view = PaginatorView(pages, interaction.user)
        await interaction.response.edit_message(content=f"Showing **{guild.name}**", embed=pages[0], view=view)


class GuildSelectView(discord.ui.View):
    def __init__(self, bot: commands.Bot, author: discord.User, timeout: int = 60):
        super().__init__(timeout=timeout)
        self.add_item(GuildSelect(bot, author))


# ---------------------------
# The Cog
# ---------------------------
class ServerInfo(commands.Cog):
    """Server Info Cog — Dark Luxury Edition"""
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._cache = {}  # guild_id -> (timestamp, pages)
        self.cache_ttl = 45  # seconds
        self.cleanup_cache.start()

    async def cog_load(self):
        """Initialize database when cog loads."""
        await init_db()

    def cog_unload(self):
        self.cleanup_cache.cancel()

    @tasks.loop(seconds=60.0)
    async def cleanup_cache(self):
        now = datetime.utcnow().timestamp()
        to_delete = []
        for gid, (ts, _) in list(self._cache.items()):
            if now - ts > self.cache_ttl:
                to_delete.append(gid)
        for gid in to_delete:
            self._cache.pop(gid, None)

    @cleanup_cache.before_loop
    async def before_cleanup(self):
        await self.bot.wait_until_ready()

    async def build_guild_pages(self, guild: discord.Guild, requester: discord.User) -> List[discord.Embed]:
        pages: List[discord.Embed] = []

        # Page 1 — Hero / Basic
        hero = create_darlux_embed(title=f"🖤 {guild.name} — Overview",
                                   description=guild.description or "No description set.",
                                   accent="royal_gold")
        try:
            if getattr(guild, "banner", None):
                hero.set_image(url=guild.banner.url)
            elif guild.icon:
                hero.set_thumbnail(url=guild.icon.url)
        except Exception:
            if guild.icon:
                hero.set_thumbnail(url=str(guild.icon.url))
        owner = getattr(guild, "owner", None)
        owner_txt = owner.mention if owner else "Unknown"
        hero.add_field(name="👑 Owner", value=owner_txt, inline=True)
        hero.add_field(name="🆔 Server ID", value=f"`{guild.id}`", inline=True)
        hero.add_field(name="🕰️ Created", value=fmt_date(guild.created_at), inline=True)

        # members breakdown
        members = guild.members
        humans = len([m for m in members if not m.bot])
        bots = len([m for m in members if m.bot])
        hero.add_field(name="👥 Members", value=f"{short_number(guild.member_count)} total\n🧍 {humans} humans • 🤖 {bots} bots", inline=False)
        hero.add_field(name="🗨️ Channels", value=f"📝 {len(guild.text_channels)} • 🔊 {len(guild.voice_channels)}", inline=True)
        hero.add_field(name="💠 Roles", value=f"{len(guild.roles)}", inline=True)
        hero.add_field(name="⚜️ Boosts", value=f"Tier {getattr(guild, 'premium_tier', 0)} • {getattr(guild, 'premium_subscription_count', 0)} boosts", inline=True)
        hero.set_footer(text=f"Requested by {requester}", icon_url=requester.display_avatar.url)
        pages.append(hero)

        # Page 2 — Presence & Activities
        pres = create_darlux_embed(title=f"🖤 {guild.name} — Presence & Activity", accent="velvet_purple")
        pmap = presence_breakdown(members)
        pres.add_field(name="🟢 Online", value=str(pmap.get("online", 0)), inline=True)
        pres.add_field(name="🌙 Idle", value=str(pmap.get("idle", 0)), inline=True)
        pres.add_field(name="⛔ DND", value=str(pmap.get("dnd", 0)), inline=True)
        pres.add_field(name="⚫ Offline", value=str(pmap.get("offline", 0)), inline=True)

        # top activities sample
        activity_map = {}
        for m in members:
            try:
                if m.activity:
                    name = getattr(m.activity, "name", str(m.activity))
                    activity_map[name] = activity_map.get(name, 0) + 1
            except Exception:
                continue
        top_acts = sorted(activity_map.items(), key=lambda x: x[1], reverse=True)[:8]
        pres.add_field(name="🎭 Top Activities", value="\n".join([f"{a} — {c}" for a, c in top_acts]) if top_acts else "No notable activities", inline=False)
        pages.append(pres)

        # Page 3 — Emojis & Stickers
        emo = create_darlux_embed(title=f"🖤 {guild.name} — Emojis & Stickers", accent="midnight_blue")
        try:
            emo.add_field(name="😄 Emojis", value=str(len(guild.emojis)), inline=True)
            emo.add_field(name="🏷️ Stickers", value=str(len(guild.stickers)), inline=True)
            sample = " ".join([str(e) for e in guild.emojis[:12]]) if guild.emojis else "No emojis"
            emo.add_field(name="Sample", value=sample, inline=False)
        except Exception:
            emo.add_field(name="Emojis", value="Could not retrieve emojis (permissions/API)", inline=False)
        pages.append(emo)

        # Page 4 — Roles & Top Members
        rolepage = create_darlux_embed(title=f"🖤 {guild.name} — Roles & Top Members", accent="accent")
        try:
            top_roles = [r for r in guild.roles if r != guild.default_role][-12:]
            top_roles = list(reversed(top_roles))
            role_list = "\n".join([f"{r.mention} — {len(r.members)}" for r in top_roles]) or "No roles"
            rolepage.add_field(name="Top Roles (sample)", value=role_list, inline=False)
        except Exception:
            rolepage.add_field(name="Roles", value="Could not fetch roles", inline=False)
        # oldest members sample
        try:
            oldest = sorted([m for m in members if not m.bot], key=lambda x: x.joined_at or datetime.utcnow())[:8]
            rolepage.add_field(name="Oldest Joins", value="\n".join([f"{m.display_name} — {fmt_date(m.joined_at)}" for m in oldest]) or "N/A", inline=False)
        except Exception:
            pass
        pages.append(rolepage)

        # Page 5 — Moderation & Safety
        safe = create_darlux_embed(title=f"🖤 {guild.name} — Moderation & Safety", accent="royal_gold")
        try:
            ver = str(guild.verification_level).replace("_", " ").title()
            safe.add_field(name="🛡️ Verification Level", value=ver, inline=True)
            safe.add_field(name="🔐 Explicit Filter", value=str(guild.explicit_content_filter).title(), inline=True)
            safe.add_field(name="🧭 Locale", value=str(guild.preferred_locale), inline=True)
        except Exception:
            safe.add_field(name="Moderation", value="Could not fetch moderation settings", inline=False)
        pages.append(safe)

        # Page 6 — Summary
        summ = create_darlux_embed(title=f"🖤 {guild.name} — Quick Summary", accent="velvet_purple")
        summ.add_field(name="Members (humans/bots)", value=f"{humans}/{bots}", inline=True)
        summ.add_field(name="Channels (text/voice)", value=f"{len(guild.text_channels)}/{len(guild.voice_channels)}", inline=True)
        summ.add_field(name="Roles / Emojis", value=f"{len(guild.roles)} roles • {len(guild.emojis)} emojis", inline=True)
        pages.append(summ)

        return pages

    @app_commands.command(name="server", description="Display refined server information (Dark Luxury).")
    @command_meta(section="Server Management", name="Server Info")
    async def server(self, interaction: discord.Interaction):
        await interaction.response.defer(thinking=True)
        # invoked in a guild
        if interaction.guild:
            guild = interaction.guild
            # caching
            cached = self._cache.get(guild.id)
            now_ts = datetime.utcnow().timestamp()
            if cached and (now_ts - cached[0]) <= self.cache_ttl:
                pages = cached[1]
            else:
                pages = await self.build_guild_pages(guild, interaction.user)
                self._cache[guild.id] = (now_ts, pages)
            # log usage
            await log_serverinfo(guild, interaction.user)
            view = PaginatorView(pages, interaction.user)
            await interaction.followup.send(embed=pages[0], view=view)
            return

        # DM context — show guild selector
        view = GuildSelectView(self.bot, interaction.user)
        await interaction.followup.send("You're in DMs — choose a server I am in:", view=view, ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(ServerInfo(bot))
