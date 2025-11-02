import discord
from discord.ext import commands
from discord import app_commands
import logging
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import aiosqlite
import asyncio
from datetime import datetime, timezone
import random
import json

from database import DB_PATH, execute_db_operation

# ------------------------------------------------------
# Logging Setup - Clears on each bot run
# ------------------------------------------------------
LOG_DIR = Path("logs")
LOG_DIR.mkdir(exist_ok=True)
LOG_FILE = LOG_DIR / "invite_tracker.log"

# Clear the log file on startup (best-effort)
try:
    if LOG_FILE.exists():
        try:
            LOG_FILE.unlink()
        except PermissionError:
            # File is in use, just continue with existing file
            pass
except Exception:
    # Best-effort only; do not fail import
    pass

# Create logger
logger = logging.getLogger("InviteTracker")
logger.setLevel(logging.INFO)

# Remove existing handlers to avoid duplicates
for handler in logger.handlers[:]:
    logger.removeHandler(handler)

# Create file handler with safe fallback to stream handler if file can't be opened
try:
    file_handler = logging.FileHandler(LOG_FILE, encoding="utf-8")
    file_handler.setLevel(logging.INFO)
    # Create formatter
    formatter = logging.Formatter(
        "[%(asctime)s] [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    file_handler.setFormatter(formatter)
    # Add handler to logger
    logger.addHandler(file_handler)
except Exception:
    # Fall back to console stream handler to avoid import-time failure
    stream_handler = logging.StreamHandler()
    stream_handler.setLevel(logging.INFO)
    stream_handler.setFormatter(logging.Formatter("[%(asctime)s] [%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S"))
    logger.addHandler(stream_handler)

logger.info("Invite Tracker cog logging initialized")

# ------------------------------------------------------
# Xianxia Themed Messages
# ------------------------------------------------------
XIANXIA_JOIN_MESSAGES = [
    "{joiner} has been recommended to the sect by {inviter} and is now a disciple of the sect.",
    "{joiner} has followed the dao of {inviter} and entered the sect as a new disciple.",
    "{joiner} was guided by Senior {inviter} and has joined the sect to cultivate.",
    "{joiner} has been brought into the sect by {inviter} to begin their cultivation journey.",
    "{joiner} answered the call of {inviter} and is now a disciple of our sect."
]

XIANXIA_LEAVE_MESSAGES = [
    "**{user}** left the sect. It seems their dao heart was shaken.",
    "**{user}** has departed from the sect. Their cultivation was insufficient.",
    "**{user}** abandoned the sect. Perhaps the path of cultivation was too arduous.",
    "**{user}** left the sect in search of their own dao. May they find enlightenment elsewhere.",
    "**{user}** has severed ties with the sect. Their heart demon proved too strong.",
    "**{user}** departed the sect. The heavenly tribulation of our community was too much.",
    "**{user}** left the sect to pursue a different cultivation method.",
    "**{user}** has gone into secluded cultivation... in another sect.",
]

RECRUITMENT_TITLES = [
    "has recruited",
    "has guided",
    "has brought",
    "has mentored",
    "has sponsored"
]


class InviteTracker(commands.Cog):
    """Track invites with Xianxia-themed join/leave messages"""
    
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.invite_cache: Dict[int, List[discord.Invite]] = {}
        self.announcement_channels: Dict[int, int] = {}  # guild_id -> channel_id
        logger.info("Invite Tracker cog initialized")
    
    async def cog_load(self):
        """Load invite cache when cog loads"""
        # Load channel settings from database
        await self._load_channel_settings()
        
        if self.bot.is_ready():
            await self._cache_invites()
            logger.info("Invite Tracker cog loaded and invite cache initialized")
        else:
            # Will cache invites in on_ready event
            logger.info("Invite Tracker cog loaded, will cache invites when bot is ready")
    
    async def _cache_invites(self):
        """Cache invites for configured guilds.

        By default this will only cache invites for guilds that have an
        announcement channel configured (opt-in behavior). Passing a
        list of guild IDs will cache only those guilds.
        """
        # Clear existing invite cache and prepare to populate configured guilds
        self.invite_cache = {}

        # Determine which guild IDs to cache: all configured guilds
        target_guild_ids = list(self.announcement_channels.keys())

        for guild_id in target_guild_ids:
            guild = self.bot.get_guild(guild_id)
            if not guild:
                logger.warning(f"Configured guild {guild_id} not found in bot.guilds")
                continue

            try:
                invites = await guild.invites()
                self.invite_cache[guild.id] = invites

                # Update database with current invites
                await self._update_invites_in_db(guild.id, invites)

                logger.info(f"Cached {len(invites)} invites for guild {guild.name}")
            except discord.Forbidden:
                logger.warning(f"Missing permissions to view invites in {guild.name}")
            except Exception as e:
                logger.error(f"Error caching invites for {guild.name}: {e}")
    
    @commands.Cog.listener()
    async def on_ready(self):
        """Cache invites when bot is ready if not already done"""
        if not self.invite_cache:
            await self._cache_invites()
    
    async def _load_channel_settings(self):
        """Load announcement channel settings from database"""
        try:
            settings = await execute_db_operation(
                "load channel settings",
                "SELECT guild_id, announcement_channel_id FROM invite_tracker_settings",
                fetch_type='all'
            )
            
            if settings:
                for guild_id, channel_id in settings:
                    self.announcement_channels[guild_id] = channel_id
                logger.info(f"Loaded announcement channel settings for {len(settings)} guilds")
            
        except Exception as e:
            logger.error(f"Error loading channel settings: {e}")
    
    async def _update_invites_in_db(self, guild_id: int, invites: List[discord.Invite]):
        """Update invite database with current invite data"""
        for invite in invites:
            try:
                await execute_db_operation(
                    "upsert invite",
                    """
                    INSERT OR REPLACE INTO invites 
                    (invite_code, guild_id, inviter_id, inviter_name, channel_id, max_uses, uses)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        invite.code,
                        guild_id,
                        invite.inviter.id if invite.inviter else 0,
                        invite.inviter.display_name if invite.inviter else "Unknown",
                        invite.channel.id if invite.channel else None,
                        invite.max_uses or -1,
                        invite.uses or 0
                    )
                )
            except Exception as e:
                logger.error(f"Error updating invite {invite.code} in database: {e}")
    
    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        """Handle member join and track which invite was used"""
        if member.bot:
            return

        guild = member.guild

        # Opt-in: only track joins for guilds that are configured
        if guild.id not in self.announcement_channels:
            logger.debug(f"Join in {guild.name} ignored - invite tracker not configured for this guild")
            return

        logger.info(f"{member} joined {guild.name}")
        
        try:
            # Get current invites
            current_invites = await guild.invites()
            cached_invites = self.invite_cache.get(guild.id, [])
            
            # Find which invite was used
            used_invite = None
            inviter = None
            
            for current_invite in current_invites:
                # Find matching cached invite
                cached_invite = next(
                    (inv for inv in cached_invites if inv.code == current_invite.code),
                    None
                )
                
                if cached_invite and current_invite.uses > cached_invite.uses:
                    used_invite = current_invite
                    inviter = current_invite.inviter
                    break
            
            # Update cache
            # Update cache for this (configured) guild
            self.invite_cache[guild.id] = current_invites

            if used_invite and inviter and inviter != member:
                await self._handle_invited_join(member, inviter, used_invite)
            else:
                await self._handle_unknown_join(member)

            await self._update_invites_in_db(guild.id, current_invites)
            
        except discord.Forbidden:
            logger.warning(f"Missing permissions to check invites in {guild.name}")
            await self._handle_unknown_join(member)
        except Exception as e:
            logger.error(f"Error handling member join for {member}: {e}")
            await self._handle_unknown_join(member)
    
    async def _handle_invited_join(self, member: discord.Member, inviter: discord.Member, invite: discord.Invite):
        """Handle when someone joins via a tracked invite"""
        guild = member.guild
        
        try:
            # Record the invite use in database
            await execute_db_operation(
                "record invite use",
                """
                INSERT INTO invite_uses 
                (guild_id, invite_code, inviter_id, inviter_name, joiner_id, joiner_name)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    guild.id,
                    invite.code,
                    inviter.id,
                    inviter.display_name,
                    member.id,
                    member.display_name
                )
            )
            
            # Update recruitment stats
            await execute_db_operation(
                "update recruitment stats",
                """
                INSERT OR REPLACE INTO recruitment_stats
                (user_id, guild_id, username, total_recruits)
                VALUES (?, ?, ?, COALESCE((
                    SELECT total_recruits + 1 FROM recruitment_stats 
                    WHERE user_id = ? AND guild_id = ?
                ), 1))
                """,
                (inviter.id, guild.id, inviter.display_name, inviter.id, guild.id)
            )
            
            # Get updated recruit count
            result = await execute_db_operation(
                "get recruit count",
                """
                SELECT total_recruits FROM recruitment_stats 
                WHERE user_id = ? AND guild_id = ?
                """,
                (inviter.id, guild.id),
                fetch_type='one'
            )
            
            recruit_count = result[0] if result else 1
            
        except Exception as e:
            logger.error(f"Error recording invite join for {member}: {e}")
            recruit_count = 1
        
        # Get appropriate messages based on theme settings
        join_messages = await self._get_theme_messages(guild.id, "join")
        message_template = random.choice(join_messages)
        recruitment_action = random.choice(RECRUITMENT_TITLES)

        # Format the message with placeholders
        join_message = message_template.format(
            joiner=member.mention,
            inviter=inviter.display_name,
            server=guild.name
        )
        join_message += f"\n{inviter.display_name} {recruitment_action} **{recruit_count}** disciples."
        
        # Find the configured announcement channel
        channel = await self._get_announcement_channel(guild)
        if channel:
            try:
                await channel.send(join_message)
                logger.info(f"Sent join message for {member} invited by {inviter} to #{channel.name}")
            except discord.Forbidden:
                logger.warning(f"Cannot send join message in {channel} - missing permissions")
            except Exception as e:
                logger.error(f"Error sending join message: {e}")
        else:
            logger.info(f"No announcement channel configured for {guild.name} - join message not sent. Use /set_invite_channel to configure.")  
        
        # Log the successful recruitment tracking
        logger.info(f"Tracked recruitment: {inviter.display_name} invited {member.display_name} (total recruits: {recruit_count})")
        
    async def _handle_unknown_join(self, member: discord.Member):
        """Handle when someone joins but we can't determine the inviter"""
        guild = member.guild
        # Only send generic messages for configured guilds
        if guild.id not in self.announcement_channels:
            logger.debug(f"Unknown join in {guild.name} ignored - invite tracker not configured for this guild")
            return

        # Get appropriate messages based on theme settings (for unknown joins)
        join_messages = await self._get_theme_messages(guild.id, "join")

        # For unknown joins, we don't have an inviter, so use a fallback format
        # Pick a message that doesn't require inviter info, or adapt it
        generic_messages = [
            f"{member.mention} has joined the sect through mysterious means.",
            f"{member.mention} has found their way to the sect. Welcome, new disciple!",
            f"{member.mention} has entered the sect. Their dao led them here.",
            f"{member.mention} has arrived at the sect to begin cultivation.",
            f"{member.mention} has joined {guild.name}!",
            f"Welcome {member.mention} to {guild.name}!"
        ]

        join_message = random.choice(generic_messages)
        
        channel = await self._get_announcement_channel(guild)
        if channel:
            try:
                await channel.send(join_message)
                logger.info(f"Sent generic join message for {member} to #{channel.name}")
            except discord.Forbidden:
                logger.warning(f"Cannot send join message in {channel} - missing permissions")
            except Exception as e:
                logger.error(f"Error sending generic join message: {e}")
        else:
            logger.info(f"No announcement channel configured for {guild.name} - generic join message not sent. Use /set_invite_channel to configure.")
    
    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        """Handle member leave with themed message"""
        if member.bot:
            return
        
        guild = member.guild
        
        # Opt-in: only track leaves for configured guilds
        if guild.id not in self.announcement_channels:
            logger.debug(f"Leave in {guild.name} ignored - invite tracker not configured for this guild")
            return

        # Calculate days in server (use timezone-aware subtraction)
        join_date = member.joined_at
        if join_date:
            # Convert join_date to UTC-aware datetime and compute difference
            try:
                join_dt = join_date.astimezone(timezone.utc)
            except Exception:
                # If astimezone fails (join_date naive), assume UTC
                join_dt = join_date.replace(tzinfo=timezone.utc)
            now_utc = datetime.now(timezone.utc)
            days_in_server = (now_utc - join_dt).days
        else:
            days_in_server = 0
        
        try:
            # Check if they were invited by someone
            result = await execute_db_operation(
                "get inviter for leaving member",
                """
                SELECT inviter_id FROM invite_uses 
                WHERE guild_id = ? AND joiner_id = ? 
                ORDER BY joined_at DESC LIMIT 1
                """,
                (guild.id, member.id),
                fetch_type='one'
            )
            
            inviter_id = result[0] if result else None
            
            # Record the leave
            await execute_db_operation(
                "record member leave",
                """
                INSERT INTO user_leaves 
                (guild_id, user_id, username, was_invited_by, days_in_server)
                VALUES (?, ?, ?, ?, ?)
                """,
                (guild.id, member.id, member.display_name, inviter_id, days_in_server)
            )
            
        except Exception as e:
            logger.error(f"Error recording member leave for {member}: {e}")
        
        # Get appropriate messages based on theme settings
        leave_messages = await self._get_theme_messages(guild.id, "leave")
        message_template = random.choice(leave_messages)

        # Format the message with placeholders
        leave_message = message_template.format(
            user=member.display_name,
            server=guild.name
        )

        channel = await self._get_announcement_channel(guild)
        if channel:
            try:
                await channel.send(leave_message)
                logger.info(f"Sent leave message for {member} to #{channel.name}")
            except discord.Forbidden:
                logger.warning(f"Cannot send leave message in {channel} - missing permissions")
            except Exception as e:
                logger.error(f"Error sending leave message: {e}")
        else:
            logger.info(f"No announcement channel configured for {guild.name} - leave message not sent. Use /set_invite_channel to configure.")
    
    async def _get_theme_messages(self, guild_id: int, message_type: str) -> List[str]:
        """Get appropriate messages based on theme settings

        Args:
            guild_id: The guild ID
            message_type: Either 'join' or 'leave'

        Returns:
            List of messages to randomly choose from
        """
        try:
            # Load theme settings from database
            settings = await execute_db_operation(
                "get theme settings for messages",
                """
                SELECT xianxia_theme_enabled, custom_join_messages, custom_leave_messages
                FROM invite_theme_settings
                WHERE guild_id = ?
                """,
                (guild_id,),
                fetch_type='one'
            )

            if settings:
                xianxia_enabled, custom_join_json, custom_leave_json = settings

                # Parse custom messages if they exist
                if message_type == "join" and custom_join_json:
                    custom_messages = json.loads(custom_join_json)
                    if custom_messages:
                        return custom_messages
                elif message_type == "leave" and custom_leave_json:
                    custom_messages = json.loads(custom_leave_json)
                    if custom_messages:
                        return custom_messages

                # If xianxia theme is disabled and no custom messages, use generic messages
                if not xianxia_enabled:
                    if message_type == "join":
                        return [
                            "{joiner} has joined the server!",
                            "{joiner} just arrived. Welcome!",
                            "Welcome {joiner} to {server}!",
                            "{joiner} has entered the server."
                        ]
                    else:  # leave
                        return [
                            "{user} has left the server.",
                            "{user} just left.",
                            "Goodbye, {user}.",
                            "{user} has departed."
                        ]

            # Default: use xianxia messages
            if message_type == "join":
                return XIANXIA_JOIN_MESSAGES
            else:
                return XIANXIA_LEAVE_MESSAGES

        except Exception as e:
            logger.error(f"Error loading theme messages: {e}")
            # Fallback to xianxia messages on error
            if message_type == "join":
                return XIANXIA_JOIN_MESSAGES
            else:
                return XIANXIA_LEAVE_MESSAGES

    async def _get_announcement_channel(self, guild: discord.Guild) -> Optional[discord.TextChannel]:
        """Get the configured announcement channel for invite messages"""
        # First priority: Check if a specific channel is configured for this guild
        if guild.id in self.announcement_channels:
            channel_id = self.announcement_channels[guild.id]
            configured_channel = guild.get_channel(channel_id)
            
            if configured_channel and isinstance(configured_channel, discord.TextChannel):
                permissions = configured_channel.permissions_for(guild.me)
                if permissions.send_messages:
                    logger.debug(f"Using configured announcement channel: {configured_channel.name}")
                    return configured_channel
                else:
                    logger.warning(f"No send permissions in configured channel {configured_channel.name} (ID: {channel_id})")
                    return None
            else:
                logger.warning(f"Configured channel {channel_id} not found or is not a text channel")
                return None
        
        # No configured channel - don't send messages to avoid spam
        logger.debug(f"No announcement channel configured for guild {guild.name}. Use /set_invite_channel to configure one.")
        return None
    
    @commands.Cog.listener()
    async def on_invite_create(self, invite: discord.Invite):
        """Update cache when new invite is created"""
        # Only track invite creation for configured guilds
        if invite.guild.id not in self.announcement_channels:
            logger.debug(f"Invite create in {invite.guild.name} ignored - invite tracker not configured for this guild")
            return

        guild_invites = self.invite_cache.get(invite.guild.id, [])
        guild_invites.append(invite)
        self.invite_cache[invite.guild.id] = guild_invites

        # Update database
        await self._update_invites_in_db(invite.guild.id, [invite])
        logger.info(f"Cached new invite {invite.code} for {invite.guild.name}")
    
    @commands.Cog.listener()
    async def on_invite_delete(self, invite: discord.Invite):
        """Update cache when invite is deleted"""
        if invite.guild.id not in self.announcement_channels:
            logger.debug(f"Invite delete in {invite.guild.name} ignored - invite tracker not configured for this guild")
            return

        guild_invites = self.invite_cache.get(invite.guild.id, [])
        self.invite_cache[invite.guild.id] = [inv for inv in guild_invites if inv.code != invite.code]
        logger.info(f"Removed deleted invite {invite.code} from cache")
    
    # ============================================================================
    # DEPRECATED COMMAND - USE /server-config INSTEAD
    # This command has been consolidated into the unified /server-config interface
    # Located in: cogs/server_management/server_config.py
    # Kept here commented for reference only
    # ============================================================================
    
    # @app_commands.command(
    #     name="set_invite_channel",
    #     description="⚠️ DEPRECATED - Use /server-config instead"
    # )
    # @app_commands.describe(
    #     channel="The channel where invite join/leave messages will be sent"
    # )
    # @app_commands.default_permissions(manage_guild=True)
    # async def set_invite_channel(
    #     self,
    #     interaction: discord.Interaction,
    #     channel: discord.TextChannel
    # ):
    #     """DEPRECATED: Set the announcement channel for invite tracking. Use /server-config instead."""
    #     await interaction.response.send_message(
    #         "⚠️ **This command has been deprecated**\n\n"
    #         "Please use `/server-config` for a unified configuration interface.\n"
    #         "You can manage invite channels, moderator roles, and all server settings there.",
    #         ephemeral=True
    #     )
    
    # ============================================================================
    # END DEPRECATED COMMAND
    # Leftover code from deprecated command above - commented out
    # ============================================================================
    #         value="• New members joining will trigger themed messages\n• Members leaving will trigger departure messages\n• All messages will only be sent to this channel",
    #         inline=False
    #     )
    #     
    #     embed.set_footer(text="Use /invite_channel_info to view current settings • Messages will only appear in the configured channel")
    #     
    #     await interaction.followup.send(embed=embed)
    #     logger.info(f"Set invite channel to #{channel.name} for guild {interaction.guild.name}")
    #     
    # except Exception as e:
    #     logger.error(f"Error setting invite channel: {e}")
    #     try:
    #         await interaction.followup.send(
    #             "❌ An error occurred while setting the invite channel.",
    #             ephemeral=True
    #         )
    #     except:
    #         logger.error("Failed to send error message - interaction may have expired")
    
    @app_commands.command(name="invite-stats", description="View recruitment statistics for the server or a specific user")
    @app_commands.describe(user="Optional: View stats for a specific user")
    @app_commands.default_permissions(manage_guild=True)
    async def invite_stats(self, interaction: discord.Interaction, user: Optional[discord.User] = None):
        """Display recruitment statistics for the server or a specific user"""
        await interaction.response.defer()

        guild_id = interaction.guild_id

        try:
            if user:
                # Show individual user stats
                await self._show_user_stats(interaction, user, guild_id)
            else:
                # Show guild-wide stats
                await self._show_guild_stats(interaction, guild_id)

        except Exception as e:
            logger.error(f"Error displaying invite stats: {e}", exc_info=True)
            await interaction.followup.send(
                "❌ An error occurred while fetching statistics. Please try again.",
                ephemeral=True
            )

    async def _show_guild_stats(self, interaction: discord.Interaction, guild_id: int):
        """Display guild-wide recruitment statistics"""
        # Get total invites used (all time)
        total_invites_result = await execute_db_operation(
            "get total invites",
            "SELECT COUNT(*) FROM invite_uses WHERE guild_id = ?",
            (guild_id,),
            fetch_type='one'
        )
        total_invites = total_invites_result[0] if total_invites_result else 0

        # Get invites used this month
        month_invites_result = await execute_db_operation(
            "get monthly invites",
            """
            SELECT COUNT(*) FROM invite_uses
            WHERE guild_id = ?
            AND strftime('%Y-%m', joined_at) = strftime('%Y-%m', 'now')
            """,
            (guild_id,),
            fetch_type='one'
        )
        month_invites = month_invites_result[0] if month_invites_result else 0

        # Get member retention rate
        total_leaves_result = await execute_db_operation(
            "get total leaves",
            "SELECT COUNT(*) FROM user_leaves WHERE guild_id = ?",
            (guild_id,),
            fetch_type='one'
        )
        total_leaves = total_leaves_result[0] if total_leaves_result else 0

        # Calculate retention rate
        if total_invites > 0:
            retention_rate = ((total_invites - total_leaves) / total_invites) * 100
        else:
            retention_rate = 0

        # Get top 3 recruiters
        top_recruiters = await execute_db_operation(
            "get top 3 recruiters",
            """
            SELECT user_id, username, total_recruits
            FROM recruitment_stats
            WHERE guild_id = ?
            ORDER BY total_recruits DESC
            LIMIT 3
            """,
            (guild_id,),
            fetch_type='all'
        )

        # Get average days in server for members who left
        avg_stay_result = await execute_db_operation(
            "get average stay duration",
            """
            SELECT AVG(days_in_server) FROM user_leaves
            WHERE guild_id = ? AND days_in_server > 0
            """,
            (guild_id,),
            fetch_type='one'
        )
        avg_stay_days = avg_stay_result[0] if avg_stay_result and avg_stay_result[0] else 0

        # Create embed
        embed = discord.Embed(
            title="📊 Sect Recruitment Statistics",
            description="*A comprehensive view of our sect's growth and prosperity*",
            color=discord.Color.blue()
        )

        # Overall stats
        embed.add_field(
            name="🎯 Overall Recruitment",
            value=f"**Total Disciples Recruited:** {total_invites}\n"
                  f"**This Month:** {month_invites}\n"
                  f"**Retention Rate:** {retention_rate:.1f}%",
            inline=False
        )

        # Member activity
        embed.add_field(
            name="👥 Member Activity",
            value=f"**Members Still in Sect:** {total_invites - total_leaves}\n"
                  f"**Departed Members:** {total_leaves}\n"
                  f"**Average Stay (departed):** {avg_stay_days:.1f} days",
            inline=False
        )

        # Top recruiters
        if top_recruiters:
            top_text = ""
            medals = ["🥇", "🥈", "🥉"]
            for idx, (user_id, username, recruits) in enumerate(top_recruiters):
                member = interaction.guild.get_member(user_id)
                display_name = member.mention if member else f"**{username}**"
                medal = medals[idx] if idx < 3 else "▪️"
                top_text += f"{medal} {display_name} — **{recruits}** disciples\n"

            embed.add_field(
                name="🌟 Top Recruiters",
                value=top_text,
                inline=False
            )

        embed.set_footer(text="Use /invite-leaderboard to see the full rankings • /invite-stats @user for individual stats")

        await interaction.followup.send(embed=embed)
        logger.info(f"Displayed guild-wide invite stats for guild {guild_id}")

    async def _show_user_stats(self, interaction: discord.Interaction, user: discord.User, guild_id: int):
        """Display individual user recruitment statistics"""
        # Get user's recruitment stats
        stats_result = await execute_db_operation(
            "get user recruitment stats",
            """
            SELECT total_recruits FROM recruitment_stats
            WHERE user_id = ? AND guild_id = ?
            """,
            (user.id, guild_id),
            fetch_type='one'
        )

        if not stats_result:
            await interaction.followup.send(
                f"📜 **{user.display_name}** has not recruited any disciples to the sect yet.",
                ephemeral=True
            )
            return

        total_recruits = stats_result[0]

        # Get list of members they invited
        invited_members = await execute_db_operation(
            "get invited members",
            """
            SELECT joiner_id, joiner_name, joined_at
            FROM invite_uses
            WHERE inviter_id = ? AND guild_id = ?
            ORDER BY joined_at DESC
            LIMIT 10
            """,
            (user.id, guild_id),
            fetch_type='all'
        )

        # Calculate how many are still in the server
        still_in_server = 0
        for joiner_id, _, _ in invited_members:
            member = interaction.guild.get_member(joiner_id)
            if member:
                still_in_server += 1

        # Calculate user retention rate
        user_retention_rate = (still_in_server / total_recruits * 100) if total_recruits > 0 else 0

        # Get user's rank
        rank_result = await execute_db_operation(
            "get user rank",
            """
            SELECT COUNT(*) + 1 FROM recruitment_stats
            WHERE guild_id = ? AND total_recruits > (
                SELECT total_recruits FROM recruitment_stats
                WHERE user_id = ? AND guild_id = ?
            )
            """,
            (guild_id, user.id, guild_id),
            fetch_type='one'
        )
        user_rank = rank_result[0] if rank_result else "Unranked"

        # Create embed
        embed = discord.Embed(
            title=f"📊 Recruitment Stats: {user.display_name}",
            description="*Individual contribution to the sect's growth*",
            color=discord.Color.green()
        )

        embed.set_thumbnail(url=user.display_avatar.url)

        embed.add_field(
            name="🎯 Recruitment Summary",
            value=f"**Total Disciples Recruited:** {total_recruits}\n"
                  f"**Still in Sect:** {still_in_server}\n"
                  f"**Retention Rate:** {user_retention_rate:.1f}%\n"
                  f"**Server Rank:** #{user_rank}",
            inline=False
        )

        # Show recent recruits
        if invited_members:
            recent_text = ""
            for joiner_id, joiner_name, joined_at in invited_members[:5]:
                member = interaction.guild.get_member(joiner_id)
                status = "✅ Active" if member else "❌ Left"
                recent_text += f"• **{joiner_name}** — {status}\n"

            embed.add_field(
                name="🎭 Recent Recruits (Last 5)",
                value=recent_text,
                inline=False
            )

        embed.set_footer(text="Use /invite-leaderboard to see all rankings")

        await interaction.followup.send(embed=embed)
        logger.info(f"Displayed user invite stats for {user.id} in guild {guild_id}")

    @app_commands.command(name="invite-leaderboard", description="View the top recruiters in the server")
    @app_commands.default_permissions(manage_guild=True)
    async def invite_leaderboard(self, interaction: discord.Interaction):
        """Display the top recruiters in the server with xianxia-themed presentation"""
        await interaction.response.defer()

        guild_id = interaction.guild_id

        try:
            # Fetch top 10 recruiters
            results = await execute_db_operation(
                "get top recruiters",
                """
                SELECT user_id, username, total_recruits
                FROM recruitment_stats
                WHERE guild_id = ?
                ORDER BY total_recruits DESC
                LIMIT 10
                """,
                (guild_id,),
                fetch_type='all'
            )

            if not results:
                await interaction.followup.send(
                    "📜 **No Recruitment Data**\n\n"
                    "No disciples have been recruited to the sect yet. "
                    "The path of cultivation begins with the first step.",
                    ephemeral=True
                )
                return

            # Create xianxia-themed embed
            embed = discord.Embed(
                title="🏆 Sect Recruitment Leaderboard",
                description="*The most distinguished cultivators who have brought disciples to our sect*",
                color=discord.Color.gold()
            )

            # Rank titles for top 3
            rank_titles = {
                1: "🥇 Grand Elder",
                2: "🥈 Core Elder",
                3: "🥉 Inner Elder"
            }

            leaderboard_text = ""
            for idx, (user_id, username, recruits) in enumerate(results, 1):
                # Try to get the member object for mention
                member = interaction.guild.get_member(user_id)
                display_name = member.mention if member else f"**{username}**"

                # Special titles for top 3
                if idx in rank_titles:
                    rank_display = rank_titles[idx]
                else:
                    rank_display = f"**#{idx}**"

                leaderboard_text += f"{rank_display} {display_name} — **{recruits}** disciples\n"

            embed.add_field(
                name="🌟 Hall of Honored Recruiters",
                value=leaderboard_text,
                inline=False
            )

            # Add footer with motivational text
            embed.set_footer(text="Continue recruiting to ascend the ranks • Use /invite-stats for detailed statistics")

            await interaction.followup.send(embed=embed)
            logger.info(f"Displayed invite leaderboard for guild {guild_id}")

        except Exception as e:
            logger.error(f"Error displaying invite leaderboard: {e}", exc_info=True)
            await interaction.followup.send(
                "❌ An error occurred while fetching the leaderboard. Please try again.",
                ephemeral=True
            )

    @app_commands.command(name="invite-theme", description="Customize join/leave messages and theme settings")
    @app_commands.default_permissions(manage_guild=True)
    async def invite_theme(self, interaction: discord.Interaction):
        """Display the theme customization menu"""
        await interaction.response.defer(ephemeral=True)

        guild_id = interaction.guild_id

        try:
            # Load current settings
            settings = await execute_db_operation(
                "get invite theme settings",
                """
                SELECT xianxia_theme_enabled, custom_join_messages, custom_leave_messages
                FROM invite_theme_settings
                WHERE guild_id = ?
                """,
                (guild_id,),
                fetch_type='one'
            )

            if settings:
                xianxia_enabled, custom_join_json, custom_leave_json = settings
                custom_join = json.loads(custom_join_json) if custom_join_json else []
                custom_leave = json.loads(custom_leave_json) if custom_leave_json else []
            else:
                xianxia_enabled = 1
                custom_join = []
                custom_leave = []

            # Create and send the theme menu
            view = InviteThemeView(guild_id, xianxia_enabled, custom_join, custom_leave, interaction.user.id)
            embed = await view.create_settings_embed(interaction.guild)
            await interaction.followup.send(embed=embed, view=view, ephemeral=True)

        except Exception as e:
            logger.error(f"Error displaying invite theme menu: {e}", exc_info=True)
            await interaction.followup.send(
                "❌ An error occurred while loading theme settings. Please try again.",
                ephemeral=True
            )

    async def cog_unload(self):
        """Clean up when cog is unloaded"""
        logger.info("Invite Tracker cog unloaded")


# ------------------------------------------------------
# Interactive UI Components for Invite Theme Customization
# ------------------------------------------------------

class CustomMessageModal(discord.ui.Modal, title="Custom Message Editor"):
    """Modal for editing custom join/leave messages"""

    def __init__(self, guild_id: int, message_type: str, existing_messages: List[str]):
        super().__init__()
        self.guild_id = guild_id
        self.message_type = message_type

        # Create text input with existing messages
        placeholder_text = (
            "Available placeholders:\n"
            "{joiner} - Mention the new member\n"
            "{inviter} - Inviter's display name\n"
            "{server} - Server name"
        ) if message_type == "join" else (
            "Available placeholders:\n"
            "{user} - Member's display name\n"
            "{server} - Server name"
        )

        self.message_input = discord.ui.TextInput(
            label=f"Custom {message_type.capitalize()} Messages",
            style=discord.TextStyle.paragraph,
            placeholder=placeholder_text,
            default="\n".join(existing_messages) if existing_messages else "",
            max_length=2000,
            required=False
        )
        self.add_item(self.message_input)

    async def on_submit(self, interaction: discord.Interaction):
        """Save the custom messages"""
        await interaction.response.defer(ephemeral=True)

        # Parse messages (one per line)
        raw_text = self.message_input.value.strip()
        if raw_text:
            messages = [msg.strip() for msg in raw_text.split('\n') if msg.strip()]
        else:
            messages = []

        try:
            # Update database
            if self.message_type == "join":
                await execute_db_operation(
                    "update custom join messages",
                    """
                    INSERT OR REPLACE INTO invite_theme_settings
                    (guild_id, custom_join_messages, xianxia_theme_enabled, custom_leave_messages)
                    VALUES (?, ?, COALESCE((
                        SELECT xianxia_theme_enabled FROM invite_theme_settings WHERE guild_id = ?
                    ), 1), COALESCE((
                        SELECT custom_leave_messages FROM invite_theme_settings WHERE guild_id = ?
                    ), NULL))
                    """,
                    (self.guild_id, json.dumps(messages) if messages else None, self.guild_id, self.guild_id)
                )
            else:  # leave messages
                await execute_db_operation(
                    "update custom leave messages",
                    """
                    INSERT OR REPLACE INTO invite_theme_settings
                    (guild_id, custom_leave_messages, xianxia_theme_enabled, custom_join_messages)
                    VALUES (?, ?, COALESCE((
                        SELECT xianxia_theme_enabled FROM invite_theme_settings WHERE guild_id = ?
                    ), 1), COALESCE((
                        SELECT custom_join_messages FROM invite_theme_settings WHERE guild_id = ?
                    ), NULL))
                    """,
                    (self.guild_id, json.dumps(messages) if messages else None, self.guild_id, self.guild_id)
                )

            message_count = len(messages)
            await interaction.followup.send(
                f"✅ Successfully saved **{message_count}** custom {self.message_type} message(s)!\n\n"
                f"These will be used randomly when members {self.message_type}.",
                ephemeral=True
            )
            logger.info(f"Updated custom {self.message_type} messages for guild {self.guild_id}: {message_count} messages")

        except Exception as e:
            logger.error(f"Error saving custom messages: {e}", exc_info=True)
            await interaction.followup.send(
                "❌ An error occurred while saving messages. Please try again.",
                ephemeral=True
            )


class InviteThemeView(discord.ui.View):
    """Interactive view for invite theme customization"""

    def __init__(self, guild_id: int, xianxia_enabled: int, custom_join: List[str], custom_leave: List[str], owner_id: int):
        super().__init__(timeout=180)
        self.guild_id = guild_id
        self.xianxia_enabled = bool(xianxia_enabled)
        self.custom_join = custom_join
        self.custom_leave = custom_leave
        self.owner_id = owner_id

    async def create_settings_embed(self, guild: discord.Guild) -> discord.Embed:
        """Create the settings overview embed"""
        embed = discord.Embed(
            title="🎨 Invite Theme Customization",
            description="Customize how join and leave messages appear in your server",
            color=discord.Color.purple()
        )

        # Theme status
        theme_status = "✅ Enabled (Xianxia cultivation theme)" if self.xianxia_enabled else "❌ Disabled"
        embed.add_field(
            name="📜 Current Theme",
            value=theme_status,
            inline=False
        )

        # Custom messages status
        join_count = len(self.custom_join)
        leave_count = len(self.custom_leave)

        embed.add_field(
            name="💬 Custom Join Messages",
            value=f"**{join_count}** custom message(s) configured" if join_count > 0 else "No custom messages (using default xianxia messages)",
            inline=True
        )

        embed.add_field(
            name="👋 Custom Leave Messages",
            value=f"**{leave_count}** custom message(s) configured" if leave_count > 0 else "No custom messages (using default xianxia messages)",
            inline=True
        )

        embed.set_footer(text="Use the buttons below to customize your theme settings")

        return embed

    @discord.ui.button(label="Toggle Xianxia Theme", style=discord.ButtonStyle.primary, emoji="📜", row=0)
    async def toggle_theme(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Toggle the xianxia theme on/off"""
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message("❌ This isn't your menu!", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)

        try:
            # Toggle the theme
            new_status = 0 if self.xianxia_enabled else 1

            await execute_db_operation(
                "toggle xianxia theme",
                """
                INSERT OR REPLACE INTO invite_theme_settings
                (guild_id, xianxia_theme_enabled, custom_join_messages, custom_leave_messages)
                VALUES (?, ?, COALESCE((
                    SELECT custom_join_messages FROM invite_theme_settings WHERE guild_id = ?
                ), NULL), COALESCE((
                    SELECT custom_leave_messages FROM invite_theme_settings WHERE guild_id = ?
                ), NULL))
                """,
                (self.guild_id, new_status, self.guild_id, self.guild_id)
            )

            self.xianxia_enabled = bool(new_status)

            # Update embed
            embed = await self.create_settings_embed(interaction.guild)
            await interaction.edit_original_response(embed=embed, view=self)

            status_text = "enabled" if new_status else "disabled"
            await interaction.followup.send(
                f"✅ Xianxia theme **{status_text}**!",
                ephemeral=True
            )
            logger.info(f"Toggled xianxia theme to {status_text} for guild {self.guild_id}")

        except Exception as e:
            logger.error(f"Error toggling theme: {e}", exc_info=True)
            await interaction.followup.send("❌ An error occurred. Please try again.", ephemeral=True)

    @discord.ui.button(label="Edit Join Messages", style=discord.ButtonStyle.secondary, emoji="💬", row=1)
    async def edit_join_messages(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Open modal to edit join messages"""
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message("❌ This isn't your menu!", ephemeral=True)
            return

        modal = CustomMessageModal(self.guild_id, "join", self.custom_join)
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="Edit Leave Messages", style=discord.ButtonStyle.secondary, emoji="👋", row=1)
    async def edit_leave_messages(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Open modal to edit leave messages"""
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message("❌ This isn't your menu!", ephemeral=True)
            return

        modal = CustomMessageModal(self.guild_id, "leave", self.custom_leave)
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="Reset to Defaults", style=discord.ButtonStyle.danger, emoji="🔄", row=2)
    async def reset_to_defaults(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Reset all customizations to default xianxia theme"""
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message("❌ This isn't your menu!", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)

        try:
            # Reset to defaults
            await execute_db_operation(
                "reset theme to defaults",
                """
                INSERT OR REPLACE INTO invite_theme_settings
                (guild_id, xianxia_theme_enabled, custom_join_messages, custom_leave_messages)
                VALUES (?, 1, NULL, NULL)
                """,
                (self.guild_id,)
            )

            self.xianxia_enabled = True
            self.custom_join = []
            self.custom_leave = []

            # Update embed
            embed = await self.create_settings_embed(interaction.guild)
            await interaction.edit_original_response(embed=embed, view=self)

            await interaction.followup.send(
                "✅ Reset to default xianxia theme!\n\n"
                "All custom messages have been cleared and the xianxia theme has been re-enabled.",
                ephemeral=True
            )
            logger.info(f"Reset invite theme to defaults for guild {self.guild_id}")

        except Exception as e:
            logger.error(f"Error resetting theme: {e}", exc_info=True)
            await interaction.followup.send("❌ An error occurred. Please try again.", ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(InviteTracker(bot))