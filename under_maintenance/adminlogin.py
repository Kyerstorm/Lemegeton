import discord
from discord import app_commands
from discord.ext import commands
import aiohttp
import aiosqlite
import logging
import re
from pathlib import Path

# ────────────────────────────────────────────────────────────────
# Configuration and constants (same style as login.py)
# ────────────────────────────────────────────────────────────────
LOG_DIR = Path("logs")
LOG_FILE = LOG_DIR / "admin_login.log"
DB_PATH = Path("data/database.db")  # adjust if your DB path differs
ANILIST_ENDPOINT = "https://graphql.anilist.co"
MAX_USERNAME_LENGTH = 50
USERNAME_REGEX = r"^[\w-]+$"

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
# Cog implementation
# ────────────────────────────────────────────────────────────────
class AdminLogin(commands.Cog):
    """Aesthetic AniList login command (AniList only)."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        logger.info("AdminLogin cog initialized")

    async def _is_valid_username(self, username: str) -> bool:
        return bool(re.match(USERNAME_REGEX, username)) and 0 < len(username) <= MAX_USERNAME_LENGTH

    async def _fetch_anilist_user(self, username: str):
        """Fetch AniList user info using GraphQL."""
        query = """
        query ($name: String) {
          User(name: $name) {
            id
            name
            avatar {
              large
              medium
            }
          }
        }
        """

        logger.debug(f"Fetching AniList user data for {username}")
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30)) as session:
                async with session.post(
                    ANILIST_ENDPOINT,
                    json={"query": query, "variables": {"name": username}}
                ) as resp:
                    data = await resp.json()
                    if resp.status != 200 or "data" not in data:
                        logger.warning(f"AniList API error: {resp.status} → {data}")
                        return None
                    return data["data"]["User"]
        except Exception as e:
            logger.error(f"Error fetching AniList user: {e}", exc_info=True)
            return None

    async def _register_user(self, user_id: int, guild_id: int, discord_user: str, anilist_name: str, anilist_id: int):
        """Register or update user info in the guild-aware DB."""
        try:
            async with aiosqlite.connect(DB_PATH) as db:
                await db.execute("""
                    INSERT OR REPLACE INTO users (discord_id, guild_id, discord_username, anilist_username, anilist_id)
                    VALUES (?, ?, ?, ?, ?)
                """, (user_id, guild_id, discord_user, anilist_name, anilist_id))
                await db.commit()
                logger.info(f"Registered/updated AniList user {anilist_name} for {discord_user} ({user_id}) in guild {guild_id}")
        except Exception as e:
            logger.error(f"Database error registering AniList user {discord_user}: {e}", exc_info=True)
            raise

    @app_commands.command(
        name="login",
        description="🔐 Link your Discord account with your AniList username."
    )
    @app_commands.describe(
        discord_user="The Discord user to link.",
        anilist_user="The AniList username to link."
    )
    async def admin_login(self, interaction: discord.Interaction, discord_user: discord.Member, anilist_user: str):
        """Anyone can link an AniList account to a Discord user."""
        try:
            if not interaction.guild:
                await interaction.response.send_message("❌ This command must be used in a server.", ephemeral=True)
                return

            guild_id = interaction.guild.id
            user_id = discord_user.id
            anilist_user = anilist_user.strip()

            logger.info(f"Login command invoked by {interaction.user} → Target: {discord_user}, AniList: {anilist_user}")

            if not anilist_user or not await self._is_valid_username(anilist_user):
                await interaction.response.send_message(
                    "❌ Invalid AniList username. Only letters, numbers, underscores, and hyphens allowed.",
                    ephemeral=True
                )
                return

            await interaction.response.defer(ephemeral=True)

            # Fetch AniList data
            user_data = await self._fetch_anilist_user(anilist_user)
            if not user_data:
                embed = discord.Embed(
                    title="❌ AniList Login Failed",
                    description=f"Could not find AniList user **{anilist_user}**.\n\n"
                                f"💡 Check the username is correct and exists on AniList.",
                    color=discord.Color.red()
                )
                await interaction.followup.send(embed=embed, ephemeral=True)
                return

            anilist_id = user_data["id"]
            actual_name = user_data["name"]
            avatar = user_data["avatar"]["large"] or user_data["avatar"]["medium"]

            # Save or update DB record
            await self._register_user(user_id, guild_id, str(discord_user), actual_name, anilist_id)

            # Success embed — same aesthetic as login.py
            embed = discord.Embed(
                title="🎉 AniList Login Successful",
                description=(
                    f"Successfully linked **{discord_user.mention}** with AniList user "
                    f"**{actual_name}** in **{interaction.guild.name}**!"
                ),
                color=discord.Color.blue()
            )
            embed.add_field(name="Profile", value=f"[View AniList Profile](https://anilist.co/user/{actual_name})", inline=False)
            embed.set_thumbnail(url=avatar)
            embed.set_footer(text="Your AniList data is now connected. Enjoy the features!")

            await interaction.followup.send(embed=embed, ephemeral=True)

        except Exception as e:
            logger.error(f"Error during AniList login: {e}", exc_info=True)
            await interaction.followup.send(
                "❌ An unexpected error occurred. Please try again later.",
                ephemeral=True
            )

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
