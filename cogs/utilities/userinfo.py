# userinfo.py
"""
Dark Luxury UserInfo Cog for discord.py v2
- /user command (optional user argument; defaults to invoker)
- Shows account info, badges, security heuristics
- Avatar/banner preview buttons and copy-ID
- Paginated visuals and technical info
- SQLite logging to bot_meta.db
- Neutral footer; interactive controls restricted to command user
"""

import discord
from discord.ext import commands
from discord import app_commands
from datetime import datetime, timezone
import sqlite3
from typing import Optional, List

# ---------------------------
# Palette & helpers
# ---------------------------
PALETTE = {
    "deep_black": discord.Color.from_rgb(18, 18, 20),
    "midnight_blue": discord.Color.from_rgb(28, 30, 45),
    "royal_gold": discord.Color.from_rgb(212, 175, 55),
    "velvet_purple": discord.Color.from_rgb(85, 45, 110),
    "soft_accent": discord.Color.from_rgb(110, 80, 150)
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
# DB logging
# ---------------------------
DB_PATH = "bot_meta.db"


def init_db(path: str = DB_PATH):
    conn = sqlite3.connect(path)
    cur = conn.cursor()
    cur.execute("""
    CREATE TABLE IF NOT EXISTS userinfo_usage (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        target_user_id INTEGER,
        target_user_name TEXT,
        invoked_by INTEGER,
        invoked_at TEXT
    )
    """)
    conn.commit()
    conn.close()


def log_userinfo(target: discord.User, invoked_by: discord.User, path: str = DB_PATH):
    try:
        conn = sqlite3.connect(path)
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO userinfo_usage (target_user_id, target_user_name, invoked_by, invoked_at) VALUES (?, ?, ?, ?)",
            (target.id, str(target), invoked_by.id, datetime.utcnow().isoformat())
        )
        conn.commit()
        conn.close()
    except Exception:
        pass


# ---------------------------
# Small utilities
# ---------------------------
def fmt_date(dt: Optional[datetime]) -> str:
    if not dt:
        return "Unknown"
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).strftime("%b %d, %Y • %H:%M UTC")


def account_age_days(user: discord.User) -> int:
    try:
        return (datetime.utcnow().replace(tzinfo=timezone.utc) - user.created_at).days
    except Exception:
        return 0


def account_age_label(user: discord.User) -> str:
    days = account_age_days(user)
    if days < 7:
        return f"⚠️ New Account — {days} day(s)"
    if days < 30:
        return f"🔰 Young Account — {days} day(s)"
    if days < 365:
        return f"✅ Established — {days} day(s)"
    return f"🌟 Veteran — {days} day(s)"


def badges_to_list(user: discord.User) -> List[str]:
    out = []
    try:
        pf = user.public_flags
        if pf.staff:
            out.append("🛡️ Staff")
        if pf.partner:
            out.append("🤝 Partner")
        if pf.hypesquad_balance:
            out.append("🏛️ HypeSquad Balance")
        if pf.hypesquad_bravery:
            out.append("🦁 HypeSquad Bravery")
        if pf.hypesquad_brilliance:
            out.append("🦉 HypeSquad Brilliance")
        if pf.verified_bot_developer:
            out.append("👨‍💻 Verified Bot Dev")
        if pf.early_supporter:
            out.append("🌱 Early Supporter")
        if pf.bug_hunter_level_1:
            out.append("🐛 Bug Hunter")
        if pf.bug_hunter_level_2:
            out.append("🐛🐛 Bug Hunter (L2)")
    except Exception:
        pass
    return out


def suspicious_checks(user: discord.User) -> List[str]:
    results = []
    days = account_age_days(user)
    if days < 3:
        results.append("Account created very recently (<3 days)")
    if user.bot:
        results.append("Bot account")
    try:
        pf = user.public_flags
        if pf and pf.value == 0 and days < 30:
            results.append("Young account with no public badges (suspicious)")
    except Exception:
        pass
    if not results:
        results.append("No immediate suspicious markers detected")
    return results


# ---------------------------
# Interactive view: Avatar actions
# ---------------------------
class AvatarButtons(discord.ui.View):
    def __init__(self, target: discord.User, timeout: int = 120):
        super().__init__(timeout=timeout)
        self.target = target

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        # allow only the command invoker to use the ephemeral quick actions (enforced by caller)
        return True

    @discord.ui.button(label="🔗 Avatar URL", style=discord.ButtonStyle.secondary)
    async def avatar_url(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message(self.target.display_avatar.url, ephemeral=True)

    @discord.ui.button(label="🖼️ Banner", style=discord.ButtonStyle.primary)
    async def banner(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            fetched = await interaction.client.fetch_user(self.target.id)
            if getattr(fetched, "banner", None):
                await interaction.response.send_message(fetched.banner.url, ephemeral=True)
            else:
                await interaction.response.send_message("No banner visible.", ephemeral=True)
        except Exception:
            await interaction.response.send_message("Unable to fetch banner.", ephemeral=True)

    @discord.ui.button(label="📋 Copy ID", style=discord.ButtonStyle.secondary)
    async def copy_id(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message(f"`{self.target.id}`", ephemeral=True)

    @discord.ui.button(label="❌ Close", style=discord.ButtonStyle.danger)
    async def close(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            await interaction.message.delete()
        except Exception:
            pass
        self.stop()


# ---------------------------
# Simple paginator for user pages
# ---------------------------
class SimplePaginator(discord.ui.View):
    def __init__(self, pages: List[discord.Embed], author: discord.User, timeout: int = 120):
        super().__init__(timeout=timeout)
        self.pages = pages
        self.author = author
        self.index = 0

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author.id:
            await interaction.response.send_message("This control is for the command user.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="◀️ Prev", style=discord.ButtonStyle.secondary)
    async def prev(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.index = max(0, self.index - 1)
        await interaction.response.edit_message(embed=self.pages[self.index], view=self)

    @discord.ui.button(label="▶️ Next", style=discord.ButtonStyle.secondary)
    async def next(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.index = min(len(self.pages) - 1, self.index + 1)
        await interaction.response.edit_message(embed=self.pages[self.index], view=self)

    @discord.ui.button(label="🔗 Visuals", style=discord.ButtonStyle.primary)
    async def visuals(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.index = 1 if len(self.pages) > 1 else 0
        await interaction.response.edit_message(embed=self.pages[self.index], view=self)

    @discord.ui.button(label="❌ Close", style=discord.ButtonStyle.danger)
    async def close(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            await interaction.message.delete()
        except Exception:
            pass
        self.stop()


# ---------------------------
# The Cog
# ---------------------------
class UserInfo(commands.Cog):
    """User Info Cog — Dark Luxury Edition"""
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        init_db()
        self._user_cache = {}  # user_id -> (timestamp, user)
        self.cache_ttl = 30

    async def fetch_user_safe(self, user: discord.User) -> discord.User:
        # try to fetch a fuller user object from the API (may reveal banner)
        try:
            fetched = await self.bot.fetch_user(user.id)
            return fetched
        except Exception:
            return user

    @app_commands.command(name="user", description="Display refined user information (Dark Luxury).")
    @app_commands.describe(user="Select a user (defaults to you)")
    async def user(self, interaction: discord.Interaction, user: Optional[discord.User] = None):
        await interaction.response.defer(thinking=True)
        target = user or interaction.user
        fetched = await self.fetch_user_safe(target)
        member = interaction.guild.get_member(fetched.id) if interaction.guild else None

        # Main embed
        main = create_darlux_embed(title=f"🖤 User — {fetched}", description=None, accent="royal_gold")
        main.set_thumbnail(url=fetched.display_avatar.url)
        main.add_field(name="📛 Username", value=f"{fetched} • `{fetched.id}`", inline=False)
        main.add_field(name="🕰️ Account Created", value=fmt_date(fetched.created_at), inline=True)

        if member:
            try:
                main.add_field(name="💬 Joined Server", value=fmt_date(member.joined_at), inline=True)
                roles = [r for r in member.roles if r != interaction.guild.default_role]
                main.add_field(name=f"🎭 Roles ({len(roles)})", value=", ".join([r.mention for r in roles[:12]]) or "None", inline=False)
                main.add_field(name="👑 Top Role", value=member.top_role.mention if member.top_role else "None", inline=True)
            except Exception:
                pass

        # Badges
        badges = badges_to_list(fetched)
        main.add_field(name="💠 Badges", value=", ".join(badges) if badges else "None", inline=False)

        # Security section
        sec = []
        sec.append(account_age_label(fetched))
        sec.extend(suspicious_checks(fetched))
        # bots can't reliably detect mfa_enabled; be conservative
        sec.append("🔒 MFA: Not visible to bots")
        main.add_field(name="🛡️ Security Summary", value="\n".join(sec), inline=False)

        # Presence / Activity
        if member:
            try:
                act = getattr(member, "activity", None)
                main.add_field(name="🎮 Current Activity", value=(getattr(act, "name", str(act)) if act else "None"), inline=True)
                main.add_field(name="🔔 Status", value=str(member.status), inline=True)
            except Exception:
                pass

        # Mutual servers (count & sample)
        try:
            mutuals = [g.name for g in self.bot.guilds if g.get_member(fetched.id)]
            main.add_field(name="🤝 Mutual Servers", value=str(len(mutuals)), inline=True)
        except Exception:
            pass

        main.set_footer(text=f"Requested by {interaction.user}", icon_url=interaction.user.display_avatar.url)

        # Page 2: Visuals (avatar + banner)
        visual = create_darlux_embed(title=f"🖤 Visuals — {fetched}", accent="velvet_purple")
        visual.set_image(url=fetched.display_avatar.url.replace("?size=1024", "?size=2048"))
        visual.add_field(name="Avatar", value="High-resolution preview", inline=True)
        try:
            fetched_more = await self.fetch_user_safe(fetched)
            if getattr(fetched_more, "banner", None):
                visual.add_field(name="Banner", value="Available (use Banner button)", inline=True)
            else:
                visual.add_field(name="Banner", value="None or not visible", inline=True)
        except Exception:
            visual.add_field(name="Banner", value="Unknown", inline=True)

        # Page 3: Technical
        tech = create_darlux_embed(title=f"🖤 Technical — {fetched}", accent="midnight_blue")
        tech.add_field(name="Avatar URL", value=fetched.display_avatar.url, inline=False)
        try:
            tech.add_field(name="Account Timestamp", value=str(fetched.created_at.timestamp()), inline=True)
        except Exception:
            pass

        # combine pages
        pages = [main, visual, tech]

        # log usage
        log_userinfo(fetched, interaction.user)

        # interactive controls
        avatar_view = AvatarButtons(fetched)
        paginator = SimplePaginator(pages, interaction.user)

        # send main message with paginator; ephemeral avatar controls to avoid clutter
        await interaction.followup.send(embed=pages[0], view=paginator)
        await interaction.followup.send("Quick actions (avatar & banner):", view=avatar_view, ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(UserInfo(bot))
