import discord
from discord.ext import commands
from discord import app_commands
import aiosqlite
import logging
from pathlib import Path

from config import DB_PATH
from database import get_guild_challenge_leaderboard_data

# ------------------------------------------------------
# Logging Setup - Clears on each bot run
# ------------------------------------------------------
LOG_DIR = Path("logs")
LOG_DIR.mkdir(exist_ok=True)
LOG_FILE = LOG_DIR / "challenge_leaderboard.log"

# Clear the log file on startup (best-effort)
try:
    if LOG_FILE.exists():
        try:
            LOG_FILE.unlink()
        except PermissionError:
            # File is in use by another process; continue
            pass
except Exception:
    # Best-effort only; do not fail import
    pass

# Create logger
logger = logging.getLogger("ChallengeLeaderboard")
logger.setLevel(logging.INFO)

for handler in logger.handlers[:]:
    logger.removeHandler(handler)

try:
    file_handler = logging.FileHandler(LOG_FILE, encoding="utf-8")
    file_handler.setLevel(logging.INFO)
    formatter = logging.Formatter(
        "[%(asctime)s] [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
except Exception:
    stream = logging.StreamHandler()
    stream.setLevel(logging.INFO)
    stream.setFormatter(logging.Formatter("[%(asctime)s] [%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S"))
    logger.addHandler(stream)

logger.info("Challenge Leaderboard cog logging initialized - log file cleared")

# ------------------------------------------------------
# Configuration Constants
# ------------------------------------------------------
DEFAULT_PAGE_SIZE = 10
VIEW_TIMEOUT = 60  # seconds


class LeaderboardView(discord.ui.View):
    """Interactive paginated view for the challenge leaderboard."""
    
    def __init__(self, interaction: discord.Interaction, leaderboard_data):
        super().__init__(timeout=VIEW_TIMEOUT)
        self.interaction = interaction
        self.leaderboard_data = leaderboard_data
        self.current_page = 0
        self.per_page = DEFAULT_PAGE_SIZE
        self.total_pages = max(1, (len(leaderboard_data) - 1) // self.per_page + 1)
        
        logger.info(f"Challenge leaderboard view initialized for {interaction.user.display_name} "
                   f"({len(leaderboard_data)} entries, {self.total_pages} pages)")

    def get_medal(self, rank: int) -> str:
        """Return appropriate medal emoji or rank number for position."""
        medals = {1: "🥇", 2: "🥈", 3: "🥉"}
        return medals.get(rank, f"#{rank}")

    def _get_user_display(self, discord_id: int) -> str:
        """Get user display name with fallback handling."""
        try:
            user = self.interaction.guild.get_member(discord_id)
            if user:
                return user.mention
            else:
                logger.debug(f"User {discord_id} not found in guild cache, using fallback mention")
                return f"<@{discord_id}>"
        except Exception as e:
            logger.warning(f"Error getting user display for {discord_id}: {e}")
            return f"<@{discord_id}>"

    def format_page(self) -> discord.Embed:
        """Format the current page as a Discord embed."""
        try:
            start = self.current_page * self.per_page
            end = start + self.per_page
            page_data = self.leaderboard_data[start:end]
            
            logger.debug(f"Formatting page {self.current_page + 1}/{self.total_pages} "
                        f"(entries {start + 1}-{min(end, len(self.leaderboard_data))})")

            if not page_data:
                logger.warning("No data available for current page")
                embed = discord.Embed(
                    title="🏆 Manga Challenge Leaderboard",
                    description="⚠️ No data available for this page.",
                    color=discord.Color.gold()
                )
                return embed

            leaderboard_entries = []
            for idx, (discord_id, total_points) in enumerate(page_data, start=start + 1):
                username = self._get_user_display(discord_id)
                rank_label = self.get_medal(idx)
                points = total_points or 0
                leaderboard_entries.append(f"**{rank_label}** — {username} • **{points:,} pts**")

            embed = discord.Embed(
                title="🏆 Manga Challenge Leaderboard",
                description="\n".join(leaderboard_entries),
                color=discord.Color.gold()
            )
            
            embed.set_footer(
                text=f"Page {self.current_page + 1}/{self.total_pages} • "
                     f"Total {len(self.leaderboard_data)} participants • Keep reading to climb!"
            )
            
            return embed
            
        except Exception as e:
            logger.error(f"Error formatting leaderboard page: {e}", exc_info=True)
            return discord.Embed(
                title="🏆 Manga Challenge Leaderboard",
                description="❌ Error displaying leaderboard. Please try again.",
                color=discord.Color.red()
            )

    async def update_message(self, interaction: discord.Interaction):
        """Update the message with the current page."""
        try:
            embed = self.format_page()
            await interaction.response.edit_message(embed=embed, view=self)
            logger.debug(f"Updated leaderboard to page {self.current_page + 1} for {interaction.user.display_name}")
        except Exception as e:
            logger.error(f"Error updating leaderboard message: {e}", exc_info=True)
            await interaction.response.defer()

    @discord.ui.button(label="⬅️ Previous", style=discord.ButtonStyle.primary)
    async def previous_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Navigate to the previous page."""
        if self.current_page > 0:
            self.current_page -= 1
            logger.debug(f"Navigating to previous page ({self.current_page + 1}) for {interaction.user.display_name}")
            await self.update_message(interaction)
        else:
            logger.debug(f"Already on first page, ignoring previous request from {interaction.user.display_name}")
            await interaction.response.defer()

    @discord.ui.button(label="➡️ Next", style=discord.ButtonStyle.primary)
    async def next_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Navigate to the next page."""
        if (self.current_page + 1) * self.per_page < len(self.leaderboard_data):
            self.current_page += 1
            logger.debug(f"Navigating to next page ({self.current_page + 1}) for {interaction.user.display_name}")
            await self.update_message(interaction)
        else:
            logger.debug(f"Already on last page, ignoring next request from {interaction.user.display_name}")
            await interaction.response.defer()

    async def on_timeout(self):
        """Handle view timeout by disabling buttons."""
        try:
            self.clear_items()
            logger.info("Challenge leaderboard view timed out, buttons removed")
        except Exception as e:
            logger.error(f"Error handling view timeout: {e}", exc_info=True)


class ChallengeLeaderboard(commands.Cog):
    """Discord cog for displaying manga challenge leaderboards."""
    
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        logger.info("Challenge Leaderboard cog initialized")

    async def _fetch_leaderboard_data(self, guild_id: int) -> list[tuple[int, int]]:
        """Fetch guild-specific leaderboard data from database with error handling."""
        try:
            logger.debug(f"Fetching challenge leaderboard data for guild {guild_id}")
            leaderboard_data = await get_guild_challenge_leaderboard_data(guild_id)
            
            logger.info(f"Retrieved {len(leaderboard_data)} leaderboard entries for guild {guild_id}")
            return leaderboard_data
            
        except Exception as e:
            logger.error(f"Database error fetching leaderboard data for guild {guild_id}: {e}", exc_info=True)
            return []

    @app_commands.command(
        name="challenge-leaderboard",
        description="🏆 View the top users ranked by manga challenge points"
    )
    async def challenge_leaderboard(self, interaction: discord.Interaction):
        """Display the manga challenge leaderboard with pagination."""
        try:
            logger.info(f"Challenge leaderboard command invoked by {interaction.user.display_name} "
                       f"({interaction.user.id}) in {interaction.guild.name}")
            
            await interaction.response.defer()
            
            # Fetch guild-specific leaderboard data
            leaderboard_data = await self._fetch_leaderboard_data(interaction.guild.id)
            
            if not leaderboard_data:
                logger.warning("No leaderboard data available to display")
                await interaction.followup.send(
                    "⚠️ No challenge participants found with points yet. "
                    "Start reading manga and tracking progress to appear on the leaderboard!"
                )
                return

            # Create and send paginated leaderboard
            view = LeaderboardView(interaction, leaderboard_data)
            embed = view.format_page()
            
            await interaction.followup.send(embed=embed, view=view)
            
            logger.info(f"Challenge leaderboard successfully displayed to {interaction.user.display_name} "
                       f"({len(leaderboard_data)} entries, {view.total_pages} pages)")
                       
        except Exception as e:
            logger.error(f"Error in challenge_leaderboard command: {e}", exc_info=True)
            try:
                if not interaction.response.is_done():
                    await interaction.response.defer()
                await interaction.followup.send(
                    "❌ An error occurred while loading the leaderboard. "
                    "Please try again later or contact support."
                )
            except Exception as follow_e:
                logger.error(f"Failed to send error message: {follow_e}", exc_info=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(ChallengeLeaderboard(bot))
