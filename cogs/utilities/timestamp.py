"""
Discord Timestamp Converter Cog
Converts dates and times to Discord's universal timestamp format
"""

import discord
from discord.ext import commands
from discord import app_commands
import logging
import re
from datetime import datetime
from typing import Optional
import calendar

# Import command logger
import sys
from pathlib import Path
repo_root = Path(__file__).resolve().parents[2]
if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))

from helpers.command_logger import log_command
from cogs_test.general_commands.dashboard import command_meta

# Logging setup
logger = logging.getLogger("Timestamp")


# ===== VALIDATION FUNCTIONS =====

def validate_date_format(date_str: str) -> bool:
    """
    Validate date string is in YYYY-MM-DD format.
    Returns True if valid format, False otherwise.
    """
    pattern = r'^\d{4}-\d{2}-\d{2}$'
    return bool(re.match(pattern, date_str))


def validate_time_format(time_str: str) -> bool:
    """
    Validate time string is in HH:MM format (24-hour).
    Returns True if valid format, False otherwise.
    """
    pattern = r'^\d{2}:\d{2}$'
    if not re.match(pattern, time_str):
        return False

    # Validate hour and minute ranges
    try:
        hour, minute = time_str.split(':')
        hour = int(hour)
        minute = int(minute)

        # Hour must be 00-23, minute must be 00-59
        return 0 <= hour <= 23 and 0 <= minute <= 59
    except:
        return False


def parse_datetime(date_str: str, time_str: Optional[str] = None) -> Optional[datetime]:
    """
    Parse date and time strings into datetime object.
    Returns datetime object or None if parsing fails.

    Args:
        date_str: Date in YYYY-MM-DD format
        time_str: Time in HH:MM format (optional, defaults to 00:00)
    """
    try:
        # Default time to midnight if not provided
        if not time_str:
            time_str = "00:00"

        # Combine date and time
        datetime_str = f"{date_str} {time_str}"

        # Parse into datetime object
        dt = datetime.strptime(datetime_str, "%Y-%m-%d %H:%M")

        return dt

    except ValueError as e:
        logger.debug(f"Failed to parse datetime: {date_str} {time_str} - {e}")
        return None


def datetime_to_unix(dt: datetime) -> int:
    """
    Convert datetime object to Unix timestamp.

    Args:
        dt: datetime object

    Returns:
        Unix timestamp (seconds since epoch)
    """
    return int(calendar.timegm(dt.timetuple()))


def create_discord_timestamp(unix_timestamp: int, format_type: str = "F") -> str:
    """
    Create Discord timestamp syntax.

    Args:
        unix_timestamp: Unix timestamp
        format_type: Discord timestamp format (default: F for long date/time)

    Returns:
        Discord timestamp syntax string
    """
    return f"<t:{unix_timestamp}:{format_type}>"


# ===== MAIN COG CLASS =====

class TimestampConverter(commands.Cog):
    """Discord timestamp converter for easy timestamp creation"""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        logger.info("TimestampConverter cog initialized")

    @app_commands.command(
        name="timestamp",
        description="Convert a date and time to Discord's universal timestamp format"
    )
    @command_meta(section="Utilities", name="Timestamp Generator")
    @app_commands.describe(
        time="Time in HH:MM format, 24-hour (e.g., 18:00)",
        date="Date in YYYY-MM-DD format (e.g., 2025-12-25) - Optional, defaults to today"
    )
    @log_command
    async def timestamp(
        self,
        interaction: discord.Interaction,
        time: str,
        date: Optional[str] = None
    ):
        """
        Convert date and time to Discord timestamp format.
        """

        # Default to today's date if not provided
        if not date:
            date = datetime.now().strftime("%Y-%m-%d")
            logger.debug(f"No date provided, using today: {date}")

        # Validate time format (required)
        if not validate_time_format(time):
            await interaction.response.send_message(
                "❌ **Invalid Time Format**\n\n"
                f"Time must be in **HH:MM** format (24-hour).\n"
                f"You provided: `{time}`\n\n"
                "**Examples:**\n"
                "• `18:00` (6:00 PM)\n"
                "• `09:30` (9:30 AM)\n"
                "• `23:45` (11:45 PM)\n"
                "• `00:00` (Midnight)",
                ephemeral=True
            )
            return

        # Validate date format
        if not validate_date_format(date):
            await interaction.response.send_message(
                "❌ **Invalid Date Format**\n\n"
                f"Date must be in **YYYY-MM-DD** format.\n"
                f"You provided: `{date}`\n\n"
                "**Examples:**\n"
                "• `2025-12-25` (December 25, 2025)\n"
                "• `2026-01-01` (January 1, 2026)\n"
                "• `2025-07-04` (July 4, 2025)\n\n"
                "💡 Tip: Leave date blank to use today's date",
                ephemeral=True
            )
            return

        # Parse datetime
        dt = parse_datetime(date, time)

        if not dt:
            await interaction.response.send_message(
                "❌ **Invalid Date**\n\n"
                f"The date `{date}` is not valid.\n\n"
                "**Common issues:**\n"
                "• Month must be 01-12\n"
                "• Day must be valid for the month (e.g., no February 30)\n"
                "• Year must be a valid 4-digit year\n\n"
                "**Example valid dates:**\n"
                "• `2025-02-28` (February has max 28 days in 2025)\n"
                "• `2025-04-30` (April has max 30 days)\n"
                "• `2025-12-31` (December has 31 days)",
                ephemeral=True
            )
            return

        # Convert to Unix timestamp
        unix_timestamp = datetime_to_unix(dt)

        # Create Discord timestamp syntax
        discord_syntax = create_discord_timestamp(unix_timestamp, "F")

        # Format the datetime for display
        formatted_datetime = dt.strftime("%A, %B %d, %Y %I:%M %p")

        # Create embed
        embed = discord.Embed(
            title="📅 Discord Timestamp",
            description=f"**Copy this:**\n```\n{discord_syntax}\n```",
            color=discord.Color.blue()
        )

        # Add preview field
        embed.add_field(
            name="Preview",
            value=discord_syntax,
            inline=False
        )

        # Add Unix timestamp
        embed.add_field(
            name="Unix Timestamp",
            value=f"`{unix_timestamp}`",
            inline=True
        )

        # Add input info
        # Check if today's date was used
        date_display = f"{date} (today)" if date == datetime.now().strftime("%Y-%m-%d") else date
        embed.add_field(
            name="Input",
            value=f"📅 {date_display}\n🕐 {time}",
            inline=True
        )

        # Footer with format info
        embed.set_footer(
            text="Format: F (Long Date/Time) • Paste the timestamp anywhere in Discord!"
        )

        await interaction.response.send_message(embed=embed, ephemeral=True)

        logger.info(f"Generated timestamp for {date} {time}: {unix_timestamp}")

    async def cog_load(self):
        """Called when the cog loads"""
        logger.info("TimestampConverter cog loaded successfully")

    async def cog_unload(self):
        """Called when the cog unloads"""
        logger.info("TimestampConverter cog unloaded")


async def setup(bot: commands.Bot):
    """Setup function required for cog loading"""
    await bot.add_cog(TimestampConverter(bot))
