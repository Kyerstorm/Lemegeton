# userinfo.py
"""
Aesthetic User Info Cog for discord.py v2 (app_commands)
Features:
- /user command (optional user argument, defaults to invoker)
- Works in any guild the bot is in (reads member-specific info when available)
- Security section: account age, badges, bot/human, suspicious flags
- Moderation info when available (roles, top role, join date)
- Avatar & banner previews, avatar download button, copy ID button
- Pagination for larger displays and interactive buttons
- Logging to SQLite (integrated with serverinfo's DB)
- Graceful fallbacks and exception handling
"""

import discord
from discord import app_commands
from discord.ext import commands
from datetime import datetime, timezone, timedelta
import sqlite3
import textwrap
from typing import Optional, List

# --------------------------------
def fmt_date(dt: datetime) -> str:
    if not dt:
        return "Unknown"
    return dt.astimezone(timezone.utc).strftime("%b %d, %Y • %H:%M UTC")

PALETTE = {
    "soft_pink": discord.Color.from_rgb(255, 182, 193),
    "muted_purple": discord.Color.from_rgb(197, 153, 210),
}

# Reuse DB init from serverinfo module unless separate — safe to re-init
def init_db(path: str = "bot_meta.db"):
    conn = sqlite3.connect(path)
    cur = conn.cursor()
    cur.execute(
        """CREATE TABLE IF NOT EXISTS userinfo_usage(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            target_user_id INTEGER,
            target_user_name TEXT,
            invoked_by INTEGER,
            invoked_at TEXT
        )"""
    )
    conn.commit()
    conn.close()

def log_userinfo(target: discord.User, invoked_by: discord.User, path: str = "bot_meta.db"):
    conn = sqlite3.connect(path)
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO userinfo_usage(target_user_id, target_user_name, invoked_by, invoked_at) VALUES (?, ?, ?, ?)",
        (target.id, str(target), invoked_by.id, datetime.utcnow().isoformat())
    )
    conn.commit()
    conn.close()


# ---------------------------
# Interactive buttons for avatar/banner/copy ID
# ---------------------------
class AvatarButtons(discord.ui.View):
    def __init__(self, user: discord.User, timeout: int = 120):
        super().__init__(timeout=timeout)
        self.user = user

    @discord.ui.button(label="🔗 Avatar URL", style=discord.ButtonStyle.secondary)
    async def avatar_url(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message(self.user.display_avatar.url, ephemeral=True)

    @discord.ui.button(label="🖼️ Banner Preview", style=discord.ButtonStyle.primary)
    async def banner_preview(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Fetch member profile to get banner (requires privileged intent or user object from API)
        try:
            fetched = await interaction.client.fetch_user(self.user.id)
            if getattr(fetched, "banner", None):
                await interaction.response.send_message(fetched.banner.url, ephemeral=True)
            else:
                await interaction.response.send_message("This user doesn't have a banner or it's not visible to me.", ephemeral=True)
        except discord.NotFound:
            await interaction.response.send_message("Could not fetch banner.", ephemeral=True)
        except Exception:
            await interaction.response.send_message("An error occurred while fetching the banner.", ephemeral=True)

    @discord.ui.button(label="📋 Copy ID", style=discord.ButtonStyle.secondary)
    async def copy_id(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message(f"`{self.user.id}`", ephemeral=True)

    @discord.ui.button(label="❌ Close", style=discord.ButtonStyle.danger)
    async def close(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.message.delete()
        self.stop()


# ---------------------------
# Security heuristics
# ---------------------------
def account_age_label(user: discord.User) -> str:
    age_days = (datetime.utcnow().replace(tzinfo=timezone.utc) - user.created_at).days
    if age_days < 7:
        return f"⚠️ New Account — {age_days} days old"
    if age_days < 30:
        return f"🔰 Young Account — {age_days} days old"
    if age_days < 365:
        return f"✅ Established — {age_days} days old"
    return f"🌟 Veteran — {age_days} days old"

def suspicious_check(user: discord.User) -> List[str]:
    flags = []
    # Basic heuristics:
    age_days = (datetime.utcnow().replace(tzinfo=timezone.utc) - user.created_at).days
    if age_days < 3:
        flags.append("Account created very recently (<3 days)")
    if user.bot:
        flags.append("Bot account (automations may be allowed)")
    # Public flags (badges) can be informative: if none and new account, mark as suspicious
    try:
        pf = user.public_flags
        if pf and pf.value == 0 and age_days < 30:
            flags.append("No public badges on a young account (suspiciously empty)")
    except Exception:
        pass
    return flags


# ---------------------------
# The Cog
# ---------------------------
class UserInfo(commands.Cog):
    """Detailed user info with security checks and aesthetic embeds"""
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        init_db()
        # small in-memory cache for resolved users to avoid heavy fetches during rapid requests
        self._user_cache = {}  # user_id -> (timestamp, user)
        self.cache_ttl = 30

    async def fetch_user_safe(self, user: Optional[discord.User]) -> discord.User:
        if user is None:
            raise ValueError("User cannot be None for fetch_user_safe")
        cached = self._user_cache.get(user.id)
        now_ts = datetime.utcnow().timestamp()
        if cached and (now_ts - cached[0]) <= self.cache_ttl:
            return cached[1]
        try:
            fetched = await self.bot.fetch_user(user.id)
            self._user_cache[user.id] = (now_ts, fetched)
            return fetched
        except Exception:
            # fallback to original
            return user

    def badges_to_list(self, user: discord.User) -> List[str]:
        out = []
        try:
            pf = user.public_flags
            if pf.staff:
                out.append("🛡️ Discord Staff")
            if pf.partner:
                out.append("🤝 Partner")
            if pf.hypesquad_balance:
                out.append("🏛️ HypeSquad Balance")
            if pf.hypesquad_bravery:
                out.append("🦁 HypeSquad Bravery")
            if pf.hypesquad_brilliance:
                out.append("🦉 HypeSquad Brilliance")
            if pf.verified_bot_developer:
                out.append("👨‍💻 Verified Bot Developer")
            if pf.early_supporter:
                out.append("🌱 Early Supporter")
            if pf.bug_hunter_level_1:
                out.append("🐛 Bug Hunter")
            if pf.bug_hunter_level_2:
                out.append("🐛🐛 Bug Hunter (Level 2)")
        except Exception:
            pass
        return out

    @app_commands.command(name="user", description="Displays detailed and aesthetic information about a user.")
    @app_commands.describe(user="Select a user to view their profile information (defaults to you)")
    async def user(self, interaction: discord.Interaction, user: Optional[discord.User] = None):
        """
        Main handler for /user. Works across any guild the bot is present in.
        - If user is omitted, shows info for the invoker.
        - If invoked in a guild, attempts to show member-specific info.
        - Includes a Security section and interactive buttons for avatars/banners.
        """
        await interaction.response.defer(thinking=True, ephemeral=False)
        target = user or interaction.user
        # Attempt to fetch richer user object via fetch_user
        fetched = await self.fetch_user_safe(target)
        member = None
        if interaction.guild:
            member = interaction.guild.get_member(fetched.id)

        # Basic embed
        emb = discord.Embed(
            title=f"🌸 User Info — {fetched}",
            color=PALETTE["soft_pink"],
            timestamp=datetime.utcnow()
        )
        # thumbnail
        emb.set_thumbnail(url=fetched.display_avatar.url)

        # Basic fields
        emb.add_field(name="📛 Username", value=f"{fetched} • `{fetched.id}`", inline=False)
        emb.add_field(name="📅 Account Created", value=fmt_date(fetched.created_at), inline=True)

        # Member-specific fields if available
        if member:
            try:
                emb.add_field(name="💬 Joined Server", value=fmt_date(member.joined_at), inline=True)
                roles = [r for r in member.roles if r != interaction.guild.default_role]
                roles_display = ", ".join([r.mention for r in roles[:12]]) or "None"
                emb.add_field(name=f"🎭 Roles ({len(roles)})", value=roles_display, inline=False)
                emb.add_field(name="💎 Top Role", value=member.top_role.mention if member.top_role else "None", inline=True)
            except Exception:
                pass

        # Badges & Public Flags
        badges = self.badges_to_list(fetched)
        emb.add_field(name="🎖️ Badges", value=", ".join(badges) if badges else "None", inline=False)

        # Security Section
        sec_lines = []
        sec_lines.append(account_age_label(fetched))
        sec_lines.extend(suspicious_check(fetched) or ["No immediate suspicious markers found."])
        # MFA availability is not reliably exposed via user objects in bots; attempt best-effort
        try:
            # NOTE: user._user_attrs or fetched.__dict__ will not reliably expose mfa_enabled
            # so we avoid claiming it. Keep statement conservative.
            sec_lines.append("🔒 MFA: Not available to bots (cannot determine)")
        except Exception:
            sec_lines.append("🔒 MFA: Unknown")
        emb.add_field(name="🛡️ Security Summary", value="\n".join(sec_lines), inline=False)

        # Activity / Presence if member
        if member:
            try:
                act = member.activity
                if act:
                    act_name = getattr(act, "name", str(act))
                    emb.add_field(name="🎮 Current Activity", value=act_name, inline=True)
                else:
                    emb.add_field(name="🎮 Current Activity", value="None", inline=True)
                emb.add_field(name="🔔 Status", value=str(member.status), inline=True)
            except Exception:
                pass

        # Mutual guilds summary (how many servers bot shares with target) — limited
        try:
            mutual_count = sum(1 for g in self.bot.guilds if g.get_member(fetched.id))
            emb.add_field(name="🤝 Mutual Servers", value=str(mutual_count), inline=True)
        except Exception:
            pass

        # Footer & timestamp
        emb.set_footer(text=f"Requested by {interaction.user}", icon_url=interaction.user.display_avatar.url)

        # Build optional extended embed pages (avatar / extra info)
        pages = [emb]

        # EXTENDED: avatar + banner display embed
        ext = discord.Embed(
            title=f"🌸 Visuals — {fetched}",
            color=PALETTE["muted_purple"],
            timestamp=datetime.utcnow()
        )
        ext.set_image(url=fetched.display_avatar.url.replace("?size=1024", "?size=2048"))
        ext.add_field(name="Avatar Resolution", value="2048x2048 (requested)", inline=True)
        try:
            fetched_more = await self.fetch_user_safe(fetched)
            if getattr(fetched_more, "banner", None):
                ext.add_field(name="Banner", value="Available (use the Banner Preview button)", inline=True)
            else:
                ext.add_field(name="Banner", value="No banner or not visible to me", inline=True)
        except Exception:
            ext.add_field(name="Banner", value="Could not determine banner", inline=True)
        pages.append(ext)

        # EXTENDED: nitty-gritty technical
        tech = discord.Embed(
            title=f"🌸 Technical Info — {fetched}",
            color=PALETTE["soft_peach"] if "soft_peach" in PALETTE else PALETTE["soft_pink"],
            timestamp=datetime.utcnow()
        )
        tech.add_field(name="Avatar URL", value=fetched.display_avatar.url, inline=False)
        tech.add_field(name="Creation Timestamp", value=str(fetched.created_at.timestamp()), inline=True)
        # safe check: display mutual guild names (small sample)
        try:
            mutuals = [g.name for g in self.bot.guilds if g.get_member(fetched.id)]
            tech.add_field(name="Mutual Server Examples", value=", ".join(mutuals[:6]) or "None", inline=False)
        except Exception:
            pass
        pages.append(tech)

        # log the usage
        try:
            log_userinfo(fetched, interaction.user)
        except Exception:
            pass

        # send with AvatarButtons view for interactivity
        view = AvatarButtons(fetched)
        # If multiple pages, offer paginator via simple buttons (just send first page + view)
        if len(pages) > 1:
            # Use a simple paginator implemented here (3 pages)
            # Build a lightweight page switcher via custom view with Next/Prev if needed
            class SimplePaginator(discord.ui.View):
                def __init__(self, pages, author):
                    super().__init__(timeout=120)
                    self.pages = pages
                    self.idx = 0
                    self.author = author

                async def interaction_check(self, interaction: discord.Interaction) -> bool:
                    if interaction.user.id != self.author.id:
                        await interaction.response.send_message("This control isn't for you.", ephemeral=True)
                        return False
                    return True

                @discord.ui.button(label="◀️ Prev", style=discord.ButtonStyle.secondary)
                async def prev(self, interaction: discord.Interaction, button: discord.ui.Button):
                    self.idx = max(0, self.idx - 1)
                    await interaction.response.edit_message(embed=self.pages[self.idx], view=self)

                @discord.ui.button(label="▶️ Next", style=discord.ButtonStyle.secondary)
                async def next(self, interaction: discord.Interaction, button: discord.ui.Button):
                    self.idx = min(len(self.pages) - 1, self.idx + 1)
                    await interaction.response.edit_message(embed=self.pages[self.idx], view=self)

                @discord.ui.button(label="🔗 Visuals", style=discord.ButtonStyle.primary)
                async def to_visuals(self, interaction: discord.Interaction, button: discord.ui.Button):
                    self.idx = 1
                    await interaction.response.edit_message(embed=self.pages[self.idx], view=self)

                @discord.ui.button(label="❌ Close", style=discord.ButtonStyle.danger)
                async def cl(self, interaction: discord.Interaction, button: discord.ui.Button):
                    await interaction.message.delete()
                    self.stop()

            paginator = SimplePaginator(pages, interaction.user)
            # merge avatar buttons into the paginator view by adding them as children as well
            # (We recreate AvatarButtons' buttons inside paginator for simplicity.)
            # Add ephemeral quick actions by attaching AvatarButtons as an additional ephemeral response when requested (user can press Visuals).
            await interaction.followup.send(embed=pages[0], view=paginator)
            # Also send the avatar controls as a separate ephemeral message to keep interface clean
            await interaction.followup.send("Quick actions (avatar & banner):", view=view, ephemeral=True)
        else:
            await interaction.followup.send(embed=pages[0], view=view)


async def setup(bot: commands.Bot):
    await bot.add_cog(UserInfo(bot))
