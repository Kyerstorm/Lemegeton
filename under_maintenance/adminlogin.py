import discord
from discord import app_commands
from discord.ext import commands
import aiohttp
import aiosqlite
import logging
import re
from pathlib import Path
import config

# ────────────────────────────────────────────────────────────────
# Configuration and constants (same style as login.py)
# ────────────────────────────────────────────────────────────────
LOG_DIR = Path("logs")
LOG_FILE = LOG_DIR / "admin_login.log"
DB_PATH = Path(config.DB_PATH)
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
# Helper View for swapping AniList usernames
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
        await interaction.response.defer(ephemeral=True)
        logger.info(f"Swap AniList username clicked by {interaction.user} for {self.target_user}")

        # Fetch new AniList data
        user_data = await self.cog._fetch_anilist_user(self.new_username)
        if not user_data:
            embed = discord.Embed(
                title="❌ AniList Swap Failed",
                description=f"Could not find AniList user **{self.new_username}**.",
                color=discord.Color.red()
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
            return

        anilist_id = user_data["id"]
        actual_name = user_data["name"]
        avatar = user_data["avatar"]["large"] or user_data["avatar"]["medium"]

        await self.cog._register_user(
            self.target_user.id, self.guild_id, str(self.target_user), actual_name, anilist_id
        )

        embed = discord.Embed(
            title="✅ AniList Username Updated",
            description=f"Successfully updated **{self.target_user.mention}**'s AniList username to **{actual_name}**.",
            color=discord.Color.green()
        )
        embed.add_field(name="Profile", value=f"[View AniList Profile](https://anilist.co/user/{actual_name})", inline=False)
        embed.set_thumbnail(url=avatar)
        embed.set_footer(text="AniList profile updated successfully!")

        await interaction.followup.send(embed=embed, ephemeral=True)
        self.stop()


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

    # Permission helper: restrict to configured MOD_ROLE_ID or administrators
    def mod_role_check():
        async def predicate(interaction: discord.Interaction):
            if not interaction.guild:
                return False
            if interaction.user.guild_permissions.administrator:
                return True
            mod_id = getattr(config, "MOD_ROLE_ID", None)
            if mod_id:
                try:
                    return any(getattr(r, "id", None) == mod_id for r in interaction.user.roles)
                except Exception:
                    return False
            return False
        return app_commands.check(predicate)

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

    async def _get_existing_user(self, user_id: int, guild_id: int):
        """Check if user is already registered in DB."""
        try:
            async with aiosqlite.connect(DB_PATH) as db:
                cursor = await db.execute(
                    "SELECT anilist_username, anilist_id FROM users WHERE discord_id = ? AND guild_id = ?",
                    (user_id, guild_id)
                )
                result = await cursor.fetchone()
                await cursor.close()
                return result
        except Exception as e:
            logger.error(f"Error checking existing AniList user: {e}", exc_info=True)
            return None

    async def _register_user(self, user_id: int, guild_id: int, discord_user: str, anilist_name: str, anilist_id: int):
        """Register or update user info in the guild-aware DB."""
        try:
            async with aiosqlite.connect(DB_PATH) as db:
                await db.execute("""
                    INSERT OR REPLACE INTO users (discord_id, guild_id, username, anilist_username, anilist_id)
                    VALUES (?, ?, ?, ?, ?)
                """, (user_id, guild_id, discord_user, anilist_name, anilist_id))
                await db.commit()
                logger.info(f"Registered/updated AniList user {anilist_name} for {discord_user} ({user_id}) in guild {guild_id}")
        except Exception as e:
            logger.error(f"Database error registering AniList user {discord_user}: {e}", exc_info=True)
            raise

    @app_commands.command(
        name="admin-login",
        description="🔐 Link a Discord user with an AniList username."
    )
    @app_commands.default_permissions(manage_guild=True)
    @mod_role_check()
    @app_commands.describe(
        discord_user="The Discord user to link.",
        anilist_user="The AniList username to link."
    )
    async def admin_login(self, interaction: discord.Interaction, discord_user: discord.Member, anilist_user: str):
        """Link or update AniList account."""
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

            # Check if already registered
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
                embed.set_footer(text="You can update this connection safely.")
                view = SwapAniListView(self, discord_user, anilist_user, guild_id)
                await interaction.followup.send(embed=embed, view=view, ephemeral=True)
                return

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
