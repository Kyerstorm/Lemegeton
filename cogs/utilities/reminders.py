import discord
from discord import app_commands
from discord.ext import commands, tasks
import logging
from pathlib import Path
from typing import Optional
from datetime import datetime, timedelta
import re
from database import execute_db_operation, init_reminders_table

# ------------------------------------------------------
# Logging Setup
# ------------------------------------------------------
LOG_DIR = Path("logs")
LOG_DIR.mkdir(exist_ok=True)
LOG_FILE = LOG_DIR / "reminders.log"

# Setup logger
logger = logging.getLogger("reminders")
logger.setLevel(logging.INFO)

# Only add handler if not already present
if not logger.handlers:
    try:
        file_handler = logging.FileHandler(LOG_FILE, encoding='utf-8')
        file_handler.setLevel(logging.INFO)
        formatter = logging.Formatter(
            '[%(asctime)s] [%(levelname)s] %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    except Exception as e:
        print(f"Failed to setup file logging for reminders: {e}")


# ------------------------------------------------------
# Natural Language Time Parser
# ------------------------------------------------------
class TimeParser:
    """Parse natural language time expressions into datetime objects"""

    @staticmethod
    def parse_time_string(time_str: str) -> Optional[datetime]:
        """
        Parse natural language time expressions like:
        - "in 5 minutes" / "in 5m"
        - "in 2 hours" / "in 2h"
        - "in 3 days" / "in 3d"
        - "tomorrow at 3pm"
        - "2025-12-25 18:00"
        - "next monday"

        Returns datetime object or None if parsing fails
        """
        time_str = time_str.lower().strip()
        now = datetime.utcnow()

        # Pattern: "in X minutes/hours/days"
        relative_pattern = r'in\s+(\d+)\s*(m|min|mins|minute|minutes|h|hr|hrs|hour|hours|d|day|days|w|week|weeks)'
        match = re.search(relative_pattern, time_str)
        if match:
            amount = int(match.group(1))
            unit = match.group(2)

            if unit in ['m', 'min', 'mins', 'minute', 'minutes']:
                return now + timedelta(minutes=amount)
            elif unit in ['h', 'hr', 'hrs', 'hour', 'hours']:
                return now + timedelta(hours=amount)
            elif unit in ['d', 'day', 'days']:
                return now + timedelta(days=amount)
            elif unit in ['w', 'week', 'weeks']:
                return now + timedelta(weeks=amount)

        # Pattern: "tomorrow at 3pm"
        if 'tomorrow' in time_str:
            tomorrow = now + timedelta(days=1)
            time_part = re.search(r'at\s+(\d+)\s*(am|pm)?', time_str)
            if time_part:
                hour = int(time_part.group(1))
                meridiem = time_part.group(2)
                if meridiem == 'pm' and hour != 12:
                    hour += 12
                elif meridiem == 'am' and hour == 12:
                    hour = 0
                return tomorrow.replace(hour=hour, minute=0, second=0, microsecond=0)
            else:
                # Default to tomorrow at 9am
                return tomorrow.replace(hour=9, minute=0, second=0, microsecond=0)

        # Pattern: "today at 3pm"
        if 'today' in time_str:
            time_part = re.search(r'at\s+(\d+)\s*(am|pm)?', time_str)
            if time_part:
                hour = int(time_part.group(1))
                meridiem = time_part.group(2)
                if meridiem == 'pm' and hour != 12:
                    hour += 12
                elif meridiem == 'am' and hour == 12:
                    hour = 0
                target = now.replace(hour=hour, minute=0, second=0, microsecond=0)
                if target <= now:
                    return None  # Time already passed today
                return target

        # Pattern: ISO format "2025-12-25 18:00"
        iso_pattern = r'(\d{4})-(\d{2})-(\d{2})\s+(\d{2}):(\d{2})'
        match = re.search(iso_pattern, time_str)
        if match:
            try:
                year, month, day, hour, minute = map(int, match.groups())
                return datetime(year, month, day, hour, minute)
            except ValueError:
                pass

        # Pattern: "next monday/tuesday/etc"
        weekdays = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']
        if 'next' in time_str:
            for i, day in enumerate(weekdays):
                if day in time_str:
                    days_ahead = (i - now.weekday() + 7) % 7
                    if days_ahead == 0:
                        days_ahead = 7
                    target = now + timedelta(days=days_ahead)
                    return target.replace(hour=9, minute=0, second=0, microsecond=0)

        return None


# ------------------------------------------------------
# Reminders Cog
# ------------------------------------------------------
class RemindersCog(commands.Cog):
    """Cog for managing user reminders with natural language parsing"""

    def __init__(self, bot):
        self.bot = bot
        self.time_parser = TimeParser()
        logger.info("RemindersCog initialized")

    async def cog_load(self):
        """Initialize database and start background task"""
        await init_reminders_table()
        self.check_reminders.start()
        logger.info("RemindersCog loaded - background task started")

    async def cog_unload(self):
        """Stop background task on unload"""
        self.check_reminders.cancel()
        logger.info("RemindersCog unloaded - background task stopped")

    @tasks.loop(minutes=1)
    async def check_reminders(self):
        """Background task to check for due reminders every minute"""
        try:
            now = datetime.utcnow()

            # Get all due reminders
            reminders = await execute_db_operation(
                "get due reminders",
                """SELECT * FROM reminders
                   WHERE is_completed = 0
                   AND remind_at <= ?
                   AND (snoozed_until IS NULL OR snoozed_until <= ?)
                   ORDER BY remind_at ASC
                   LIMIT 100""",
                (now.isoformat(), now.isoformat()),
                fetch_type='all'
            )

            if not reminders:
                return

            logger.info(f"Processing {len(reminders)} due reminders")

            for reminder in reminders:
                try:
                    await self.send_reminder(reminder)

                    # Mark as completed
                    await execute_db_operation(
                        "mark reminder completed",
                        """UPDATE reminders
                           SET is_completed = 1, completed_at = ?
                           WHERE id = ?""",
                        (now.isoformat(), reminder['id'])
                    )

                    logger.info(f"Sent reminder {reminder['id']} to user {reminder['user_id']}")

                except Exception as e:
                    logger.error(f"Error sending reminder {reminder['id']}: {e}", exc_info=True)

        except Exception as e:
            logger.error(f"Error in check_reminders task: {e}", exc_info=True)

    @check_reminders.before_loop
    async def before_check_reminders(self):
        """Wait for bot to be ready before starting reminder checks"""
        await self.bot.wait_until_ready()
        logger.info("Bot ready - starting reminder check loop")

    async def send_reminder(self, reminder: dict):
        """Send a reminder to the user"""
        user = await self.bot.fetch_user(reminder['user_id'])

        embed = discord.Embed(
            title="⏰ Reminder!",
            description=reminder['message'],
            color=discord.Color.gold(),
            timestamp=datetime.utcnow()
        )

        created_at = datetime.fromisoformat(reminder['created_at'])
        embed.add_field(
            name="Created",
            value=created_at.strftime('%Y-%m-%d %H:%M UTC'),
            inline=True
        )

        remind_at = datetime.fromisoformat(reminder['remind_at'])
        embed.add_field(
            name="Scheduled For",
            value=remind_at.strftime('%Y-%m-%d %H:%M UTC'),
            inline=True
        )

        embed.set_footer(text=f"Reminder ID: {reminder['id']}")

        # Send to channel or DM
        if reminder['channel_id']:
            try:
                channel = await self.bot.fetch_channel(reminder['channel_id'])
                await channel.send(f"<@{reminder['user_id']}>", embed=embed)
            except discord.NotFound:
                # Channel deleted, send DM instead
                await user.send(embed=embed)
            except discord.Forbidden:
                # No permission, send DM instead
                await user.send(embed=embed)
        else:
            # Send DM
            await user.send(embed=embed)

    @app_commands.command(
        name="remind",
        description="Set a reminder with natural language time parsing"
    )
    @app_commands.describe(
        when="When to remind you (e.g., 'in 5 minutes', 'tomorrow at 3pm', '2025-12-25 18:00')",
        message="What to remind you about",
        channel="Channel to send reminder in (optional, defaults to DM)"
    )
    async def remind(
        self,
        interaction: discord.Interaction,
        when: str,
        message: str,
        channel: Optional[discord.TextChannel] = None
    ):
        """Create a new reminder"""
        await interaction.response.defer(ephemeral=True)

        # Parse the time
        remind_at = self.time_parser.parse_time_string(when)

        if not remind_at:
            embed = discord.Embed(
                title="❌ Invalid Time Format",
                description=f"Could not understand the time format: `{when}`",
                color=discord.Color.red()
            )
            embed.add_field(
                name="Supported Formats",
                value=(
                    "• `in 5 minutes` / `in 5m`\n"
                    "• `in 2 hours` / `in 2h`\n"
                    "• `in 3 days` / `in 3d`\n"
                    "• `tomorrow at 3pm`\n"
                    "• `today at 5pm`\n"
                    "• `next monday`\n"
                    "• `2025-12-25 18:00`"
                ),
                inline=False
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
            return

        # Check if time is in the past
        if remind_at <= datetime.utcnow():
            await interaction.followup.send(
                "❌ Cannot set a reminder for a time in the past!",
                ephemeral=True
            )
            return

        # Validate message length
        if len(message) > 1000:
            await interaction.followup.send(
                "❌ Reminder message is too long! Maximum 1000 characters.",
                ephemeral=True
            )
            return

        # Determine guild and channel
        guild_id = interaction.guild_id if channel else None
        channel_id = channel.id if channel else None

        # Verify bot has permissions in target channel
        if channel:
            if not channel.permissions_for(interaction.guild.me).send_messages:
                await interaction.followup.send(
                    f"❌ I don't have permission to send messages in {channel.mention}!",
                    ephemeral=True
                )
                return

        # Create reminder
        try:
            reminder_id = await execute_db_operation(
                "create reminder",
                """INSERT INTO reminders (user_id, guild_id, channel_id, message, remind_at)
                   VALUES (?, ?, ?, ?, ?)""",
                (interaction.user.id, guild_id, channel_id, message, remind_at.isoformat()),
                fetch_type='lastrowid'
            )

            # Calculate time until reminder
            time_until = remind_at - datetime.utcnow()
            if time_until.days > 0:
                time_str = f"{time_until.days} day(s)"
            elif time_until.seconds >= 3600:
                hours = time_until.seconds // 3600
                time_str = f"{hours} hour(s)"
            else:
                minutes = time_until.seconds // 60
                time_str = f"{minutes} minute(s)"

            # Success embed
            embed = discord.Embed(
                title="✅ Reminder Created!",
                description=message,
                color=discord.Color.green(),
                timestamp=remind_at
            )

            location = channel.mention if channel else "📨 Direct Message"
            embed.add_field(name="Location", value=location, inline=True)
            embed.add_field(name="Time Until", value=time_str, inline=True)
            embed.add_field(name="Reminder ID", value=f"#{reminder_id}", inline=True)

            embed.set_footer(text=f"Scheduled for {remind_at.strftime('%Y-%m-%d %H:%M UTC')}")

            await interaction.followup.send(embed=embed, ephemeral=True)
            logger.info(f"User {interaction.user.id} created reminder {reminder_id} for {remind_at}")

        except Exception as e:
            logger.error(f"Error creating reminder: {e}", exc_info=True)
            await interaction.followup.send(
                "❌ An error occurred while creating the reminder. Please try again.",
                ephemeral=True
            )


async def setup(bot):
    """Setup function for the reminders cog"""
    await bot.add_cog(RemindersCog(bot))
    logger.info("RemindersCog successfully loaded")
