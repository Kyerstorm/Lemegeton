import discord
from discord.ext import commands
import logging
from pathlib import Path
from database import is_user_bot_moderator, get_user_guild_aware, register_user_guild_aware
from helpers.command_logger import log_command
from helpers.anilist_helper import fetch_anilist_user_basic
from helpers.text_helper import validate_anilist_username
from helpers.embed_helper import build_error_embed, build_success_embed

# ────────────────────────────────────────────────────────────────
# Configuration and constants
# ────────────────────────────────────────────────────────────────
LOG_DIR = Path("logs")
LOG_FILE = LOG_DIR / "admin_login.log"
MAX_USERNAME_LENGTH = 50

LOG_DIR.mkdir(exist_ok=True)

logger = logging.getLogger("AdminLogin")
logger.setLevel(logging.DEBUG)

if not any(isinstance(h, logging.FileHandler) and getattr(h, "baseFilename", None) == str(LOG_FILE)
           for h in logger.handlers):
    try:
        handler = logging.FileHandler(LOG_FILE, mode='w', encoding='utf-8')
        handler.setLevel(logging.DEBUG)
        formatter = logging.Formatter(
            fmt="[%(asctime)s] [%(levelname)-8s] [%(name)s] %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)
    except Exception:
        stream = logging.StreamHandler()
        stream.setFormatter(logging.Formatter(fmt="[%(asctime)s] [%(levelname)-8s] [%(name)s] %(message)s"))
        logger.addHandler(stream)

logger.info("AdminLogin cog logging initialized")


# ────────────────────────────────────────────────────────────────
# View for swapping AniList usernames
# ────────────────────────────────────────────────────────────────
class SwapAniListView(discord.ui.View):
    def __init__(self, cog, target_user: discord.Member, new_username: str, guild_id: int):
        super().__init__(timeout=60)
        self.cog = cog
        self.target_user = target_user
        self.new_username = new_username
        self.guild_id = guild_id

    @discord.ui.button(label="🔁 Swap AniList Username", style=discord.ButtonStyle.primary, emoji="🔁")
    async def swap_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Silent mod check
        if not await is_user_bot_moderator(interaction.user):
            return

        await interaction.response.defer(ephemeral=True)
        logger.info(f"Swap AniList username clicked by {interaction.user} for {self.target_user}")

        # Fetch new AniList data
        user_data = await self.cog._fetch_anilist_user(self.new_username)
        if not user_data:
            embed = build_error_embed(
                "AniList Swap Failed",
                f"Could not find AniList user **{self.new_username}**."
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
            return

        anilist_id = user_data["id"]
        actual_name = user_data["name"]
        avatar = user_data.get("avatar")

        await self.cog._register_user(
            self.target_user.id, self.guild_id, str(self.target_user), actual_name, anilist_id
        )

        embed = build_success_embed(
            "AniList Username Updated",
            f"Successfully updated **{self.target_user.mention}**'s AniList username to **{actual_name}**."
        )
        embed.add_field(name="Profile", value=f"[View AniList Profile](https://anilist.co/user/{actual_name})", inline=False)
        if avatar:
            embed.set_thumbnail(url=avatar)
        embed.set_footer(text="AniList profile updated successfully!")

        await interaction.followup.send(embed=embed, ephemeral=True)
        self.stop()


# ────────────────────────────────────────────────────────────────
# Cog Implementation
# ────────────────────────────────────────────────────────────────
class AdminLogin(commands.Cog):
    """Prefix-only AniList login command for bot moderators."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        logger.info("AdminLogin cog initialized")

    # -------------------------
    # Helpers
    # -------------------------
    async def _is_valid_username(self, username: str) -> bool:
        return validate_anilist_username(username, max_length=MAX_USERNAME_LENGTH)

    async def _fetch_anilist_user(self, username: str):
        logger.debug(f"Fetching AniList user data for {username}")
        return await fetch_anilist_user_basic(username)

    async def _get_existing_user(self, user_id: int, guild_id: int):
        try:
            user = await get_user_guild_aware(user_id, guild_id)
            if user:
                return (user[4], user[5]) if len(user) > 5 else (user[4], None)
            return None
        except Exception as e:
            logger.error(f"Error checking existing AniList user: {e}", exc_info=True)
            return None

    async def _register_user(self, user_id: int, guild_id: int, discord_user: str, anilist_name: str, anilist_id: int):
        try:
            await register_user_guild_aware(user_id, guild_id, discord_user, anilist_name, anilist_id)
            logger.info(f"Registered/updated AniList user {anilist_name} for {discord_user} ({user_id}) in guild {guild_id}")
        except Exception as e:
            logger.error(f"Database error registering AniList user {discord_user}: {e}", exc_info=True)
            raise

    # ────────────────────────────────────────────────────────────────
    # Admin Login Command
    # ────────────────────────────────────────────────────────────────
    @commands.command(name="adminlogin")
    @log_command
    async def admin_login_prefix(self, ctx: commands.Context, discord_user: discord.Member, *, anilist_user: str):

        # Silent mod check
        if not await is_user_bot_moderator(ctx.author):
            return

        guild = ctx.guild
        if not guild:
            await ctx.send("❌ This command must be used in a server.")
            return

        guild_id = guild.id
        user_id = discord_user.id
        anilist_user = anilist_user.strip()

        logger.info(f"Prefix adminlogin invoked by {ctx.author} → Target: {discord_user}, AniList: {anilist_user}")

        # Validate username
        if not anilist_user or not await self._is_valid_username(anilist_user):
            await ctx.send("❌ Invalid AniList username. Only letters, numbers, underscores, and hyphens allowed.")
            return

        # Check existing
        existing = await self._get_existing_user(user_id, guild_id)
        if existing:
            current_name = existing[0]

            embed = discord.Embed(
                title="⚠️ AniList Already Linked",
                description=(
                    f"**{discord_user.mention}** is already linked to AniList user **{current_name}**.\n\n"
                    f"Would you like to swap to **{anilist_user}** instead?"
                ),
                color=discord.Color.gold()
            )
            embed.set_footer(text="You can safely update this connection.")

            view = SwapAniListView(self, discord_user, anilist_user, guild_id)
            await ctx.send(embed=embed, view=view)
            return

        # Fetch AniList data
        user_data = await self._fetch_anilist_user(anilist_user)
        if not user_data:
            embed = build_error_embed(
                "AniList Login Failed",
                f"Could not find AniList user **{anilist_user}**."
            )
            await ctx.send(embed=embed)
            return

        anilist_id = user_data["id"]
        actual_name = user_data["name"]
        avatar = user_data.get("avatar")

        # Register
        await self._register_user(user_id, guild_id, str(discord_user), actual_name, anilist_id)

        # Success embed
        embed = discord.Embed(
            title="🎉 AniList Login Successful",
            description=(
                f"Successfully linked **{discord_user.mention}** with AniList user "
                f"**{actual_name}** in **{guild.name}**!"
            ),
            color=discord.Color.blue()
        )

        embed.add_field(name="Profile", value=f"[View AniList Profile](https://anilist.co/user/{actual_name})")
        embed.set_thumbnail(url=avatar)
        embed.set_footer(text="AniList account successfully connected!")

        await ctx.send(embed=embed)

    async def cog_load(self):
        logger.info("AdminLogin cog loaded successfully")

    async def cog_unload(self):
        logger.info("AdminLogin cog unloaded")


async def setup(bot: commands.Bot):
    try:
        await bot.add_cog(AdminLogin(bot))
        logger.info("AdminLogin cog loaded")
    except Exception as e:
        logger.error(f"Failed to load AdminLogin cog: {e}", exc_info=True)
        raise