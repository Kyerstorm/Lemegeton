import discord
from discord.ext import commands, tasks
import logging
import asyncio
from pathlib import Path
from typing import List, Dict, Set, Tuple, Any
from datetime import datetime

from database import execute_db_operation
from helpers.embed_helper import build_error_embed, build_success_embed, build_info_embed, build_warning_embed

# Configuration constants
LOG_DIR = Path("logs")
LOG_FILE = LOG_DIR / "user_cleanup.log"
CLEANUP_INTERVAL_HOURS = 24  # Run cleanup every 24 hours
CLEANUP_BATCH_SIZE = 50  # Process users in batches to avoid blocking
CLEANUP_DELAY = 1.0  # Delay between batches in seconds

# Ensure logs directory exists
LOG_DIR.mkdir(exist_ok=True)

# Set up file-based logging with auto-clearing
logger = logging.getLogger("UserCleanup")
logger.setLevel(logging.DEBUG)

# Clear handlers to avoid duplicates
logger.handlers.clear()

try:
    # Try to create a file handler (truncate on open). If the file is locked,
    # fall back to a stream handler to avoid import-time failures.
    file_handler = logging.FileHandler(LOG_FILE, mode='w', encoding='utf-8')
    file_handler.setLevel(logging.DEBUG)

    # Create formatter
    formatter = logging.Formatter(
        fmt="[%(asctime)s] [%(levelname)-8s] [%(name)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    file_handler.setFormatter(formatter)

    # Add handler to logger
    logger.addHandler(file_handler)
except Exception:
    # Fall back to console logging if the file cannot be opened
    stream_handler = logging.StreamHandler()
    stream_handler.setLevel(logging.DEBUG)
    stream_handler.setFormatter(logging.Formatter(fmt="[%(asctime)s] [%(levelname)-8s] [%(name)s] %(message)s",
                                                  datefmt="%Y-%m-%d %H:%M:%S"))
    logger.addHandler(stream_handler)

logger.info("User cleanup system initialized")


class UserCleanup(commands.Cog):
    """Cog for automatically cleaning up users who have left the server."""
    
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        logger.info("UserCleanup cog initialized - provides manual cleanup commands")

    async def cog_load(self):
        """Called when the cog is loaded."""
        logger.info("UserCleanup cog loaded - manual cleanup commands available")
        logger.info("Note: Automatic cleanup is handled by bot.py on startup and periodic schedule")

    async def cog_unload(self):
        """Called when the cog is unloaded."""
        logger.info("UserCleanup cog unloading")

    async def get_all_registered_users(self) -> List[Tuple[Any, ...]]:
        """Get all registered users from the database."""
        try:
            # Check if guild_id column exists, if not fall back to old schema
            schema_query = "PRAGMA table_info(users)"
            schema = await execute_db_operation("check users table schema", schema_query, fetch_type='all')
            columns = [col[1] for col in schema]
            
            if 'guild_id' in columns:
                # New guild-aware schema
                query = "SELECT id, discord_id, guild_id, username, anilist_username FROM users"
                logger.debug("Using guild-aware query for user cleanup")
            else:
                # Old schema without guild_id
                query = "SELECT id, discord_id, username, anilist_username FROM users"
                logger.debug("Using legacy query for user cleanup (no guild_id column)")
            
            users = await execute_db_operation("fetch all registered users", query, fetch_type='all')
            logger.info(f"Retrieved {len(users)} registered users from database")
            return users
            
        except Exception as e:
            logger.error(f"Failed to retrieve registered users: {e}", exc_info=True)
            return []

    async def get_guild_members(self, guild: discord.Guild) -> Set[int]:
        """Get all member IDs from a guild."""
        try:
            # Ensure we have the latest member list
            if not guild.chunked:
                await guild.chunk(cache=True)
            
            member_ids = {member.id for member in guild.members}
            logger.debug(f"Guild {guild.name} has {len(member_ids)} members")
            return member_ids
            
        except Exception as e:
            logger.error(f"Failed to get members for guild {guild.name} ({guild.id}): {e}", exc_info=True)
            return set()

    async def remove_user_from_database(self, user_id: int, discord_id: int, guild_id: int = None) -> bool:
        """Remove a user from the database."""
        try:
            if guild_id:
                # Guild-aware removal
                query = "DELETE FROM users WHERE id = ? AND discord_id = ? AND guild_id = ?"
                params = (user_id, discord_id, guild_id)
                operation_desc = f"remove user ID {user_id} (Discord: {discord_id}) from guild {guild_id}"
            else:
                # Legacy removal
                query = "DELETE FROM users WHERE id = ? AND discord_id = ?"
                params = (user_id, discord_id)
                operation_desc = f"remove user ID {user_id} (Discord: {discord_id})"
            
            result = await execute_db_operation(operation_desc, query, params)
            logger.info(f"✅ Successfully removed user from database: {operation_desc}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to remove user {user_id} (Discord: {discord_id}): {e}", exc_info=True)
            return False

    async def cleanup_users_for_guild(self, guild: discord.Guild) -> Dict[str, int]:
        """Clean up users who have left a specific guild."""
        stats = {
            'checked': 0,
            'removed': 0,
            'errors': 0,
            'not_found': 0
        }
        
        try:
            logger.info(f"🧹 Starting user cleanup for guild: {guild.name} (ID: {guild.id})")
            
            # Get all current guild members
            current_members = await self.get_guild_members(guild)
            if not current_members:
                logger.warning(f"No members found for guild {guild.name} - skipping cleanup")
                return stats
            
            # Get all registered users
            all_users = await self.get_all_registered_users()
            if not all_users:
                logger.warning("No registered users found in database")
                return stats
            
            # Check if we're using guild-aware schema
            has_guild_id = len(all_users[0]) > 4 if all_users else False
            
            # Filter users for this guild (if guild-aware) or all users (if legacy)
            if has_guild_id:
                guild_users = [user for user in all_users if user[2] == guild.id]  # guild_id is at index 2
                logger.info(f"Found {len(guild_users)} registered users for guild {guild.name}")
            else:
                guild_users = all_users
                logger.info(f"Using legacy mode - checking all {len(guild_users)} users against guild {guild.name}")
            
            # Process users in batches
            for i in range(0, len(guild_users), CLEANUP_BATCH_SIZE):
                batch = guild_users[i:i + CLEANUP_BATCH_SIZE]
                logger.debug(f"Processing batch {i//CLEANUP_BATCH_SIZE + 1} ({len(batch)} users)")
                
                for user in batch:
                    stats['checked'] += 1
                    
                    try:
                        if has_guild_id:
                            user_id, discord_id, guild_id, username, anilist_username = user
                        else:
                            user_id, discord_id, username, anilist_username = user
                            guild_id = None
                        
                        # Check if user is still in the guild
                        if discord_id not in current_members:
                            logger.info(f"👻 User {username} (Discord: {discord_id}) has left guild {guild.name}")
                            
                            # Remove user from database
                            if await self.remove_user_from_database(user_id, discord_id, guild_id):
                                stats['removed'] += 1
                                logger.info(f"🗑️ Cleaned up user: {username} (Discord: {discord_id})")
                            else:
                                stats['errors'] += 1
                        else:
                            logger.debug(f"✅ User {username} (Discord: {discord_id}) still in guild")
                            
                    except Exception as e:
                        logger.error(f"Error processing user {user}: {e}", exc_info=True)
                        stats['errors'] += 1
                
                # Small delay between batches to avoid blocking
                if i + CLEANUP_BATCH_SIZE < len(guild_users):
                    await asyncio.sleep(CLEANUP_DELAY)
            
            logger.info(f"🏁 Cleanup completed for guild {guild.name}: "
                       f"checked={stats['checked']}, removed={stats['removed']}, errors={stats['errors']}")
            
        except Exception as e:
            logger.error(f"Error during cleanup for guild {guild.name}: {e}", exc_info=True)
            stats['errors'] += 1
        
        return stats

    async def perform_full_cleanup(self) -> Dict[str, int]:
        """Perform cleanup for all guilds the bot is in."""
        total_stats = {
            'guilds_processed': 0,
            'total_checked': 0,
            'total_removed': 0,
            'total_errors': 0
        }
        
        try:
            logger.info("🚀 Starting full user cleanup across all guilds")
            start_time = datetime.now()
            
            for guild in self.bot.guilds:
                try:
                    guild_stats = await self.cleanup_users_for_guild(guild)
                    
                    total_stats['guilds_processed'] += 1
                    total_stats['total_checked'] += guild_stats['checked']
                    total_stats['total_removed'] += guild_stats['removed']
                    total_stats['total_errors'] += guild_stats['errors']
                    
                    # Small delay between guilds
                    await asyncio.sleep(2.0)
                    
                except Exception as e:
                    logger.error(f"Error processing guild {guild.name} ({guild.id}): {e}", exc_info=True)
                    total_stats['total_errors'] += 1
            
            end_time = datetime.now()
            duration = (end_time - start_time).total_seconds()
            
            logger.info(f"🎉 Full cleanup completed in {duration:.2f} seconds")
            logger.info(f"📊 Final stats: {total_stats}")
            
        except Exception as e:
            logger.error(f"Error during full cleanup: {e}", exc_info=True)
            total_stats['total_errors'] += 1
        
        return total_stats

    # Automatic cleanup is now handled by bot.py's schedule_user_cleanup()
    # This cog provides manual admin commands that call bot.py's cleanup functions

    @commands.command(name="cleanup_users")
    @commands.has_permissions(administrator=True)
    async def manual_cleanup(self, ctx):
        """Manually trigger user cleanup for the current guild."""
        try:
            info_embed = build_info_embed(
                "User Cleanup",
                "Starting manual user cleanup for this server..."
            )
            await ctx.send(embed=info_embed)
            
            stats = await self.cleanup_users_for_guild(ctx.guild)
            
            stats_text = (
                f"**Checked:** {stats['checked']} users\n"
                f"**Removed:** {stats['removed']} inactive users\n"
                f"**Errors:** {stats['errors']}"
            )
            
            if stats['removed'] > 0:
                embed = build_success_embed(
                    "User Cleanup Complete",
                    stats_text
                )
                embed.add_field(
                    name="✅ Result", 
                    value=f"Successfully cleaned up {stats['removed']} users who left the server.",
                    inline=False
                )
            else:
                embed = build_success_embed(
                    "User Cleanup Complete",
                    stats_text
                )
                embed.add_field(
                    name="✨ Result", 
                    value="No inactive users found - database is already clean!",
                    inline=False
                )
            
            await ctx.send(embed=embed)
            
        except Exception as e:
            logger.error(f"Error in manual cleanup command: {e}", exc_info=True)
            embed = build_error_embed(
                "Cleanup Error",
                f"Error during cleanup: {str(e)}"
            )
            await ctx.send(embed=embed)

    @commands.command(name="cleanup_all_guilds")
    @commands.has_permissions(administrator=True)
    async def manual_full_cleanup(self, ctx):
        """Manually trigger user cleanup for all guilds."""
        try:
            info_embed = build_info_embed(
                "Full User Cleanup",
                "Starting manual user cleanup for ALL servers..."
            )
            await ctx.send(embed=info_embed)
            
            stats = await self.perform_full_cleanup()
            
            stats_text = (
                f"**Guilds Processed:** {stats['guilds_processed']}\n"
                f"**Total Checked:** {stats['total_checked']} users\n"
                f"**Total Removed:** {stats['total_removed']} inactive users\n"
                f"**Total Errors:** {stats['total_errors']}"
            )
            
            if stats['total_removed'] > 0:
                embed = build_success_embed(
                    "Full User Cleanup Complete",
                    stats_text
                )
                embed.add_field(
                    name="✅ Result", 
                    value=f"Successfully cleaned up {stats['total_removed']} users across {stats['guilds_processed']} servers.",
                    inline=False
                )
            else:
                embed = build_success_embed(
                    "Full User Cleanup Complete",
                    stats_text
                )
                embed.add_field(
                    name="✨ Result", 
                    value="No inactive users found - all databases are clean!",
                    inline=False
                )
            
            await ctx.send(embed=embed)
            
        except Exception as e:
            logger.error(f"Error in manual full cleanup command: {e}", exc_info=True)
            embed = build_error_embed(
                "Full Cleanup Error",
                f"Error during full cleanup: {str(e)}"
            )
            await ctx.send(embed=embed)

    @commands.command(name="cleanup_status")
    @commands.has_permissions(administrator=True)
    async def cleanup_status(self, ctx):
        """Show the status of the user cleanup system."""
        try:
            embed = build_info_embed(
                "User Cleanup System Status",
                "Current status and configuration of the user cleanup system"
            )
            
            # Task status
            task_status = "🟢 Running" if self.cleanup_inactive_users.is_running() else "🔴 Stopped"
            embed.add_field(
                name="Task Status",
                value=task_status,
                inline=True
            )
            
            # Next run time
            if self.cleanup_inactive_users.next_iteration:
                next_run = discord.utils.format_dt(self.cleanup_inactive_users.next_iteration, style='R')
                embed.add_field(
                    name="Next Automatic Run",
                    value=next_run,
                    inline=True
                )
            
            # Configuration
            embed.add_field(
                name="⚙️ Configuration",
                value=f"**Interval:** Every {CLEANUP_INTERVAL_HOURS} hours\n"
                      f"**Batch Size:** {CLEANUP_BATCH_SIZE} users\n"
                      f"**Batch Delay:** {CLEANUP_DELAY}s",
                inline=False
            )
            
            # Available commands
            embed.add_field(
                name="🛠️ Available Commands",
                value="• `!cleanup_users` - Clean this server\n"
                      "• `!cleanup_all_guilds` - Clean all servers\n"
                      "• `!cleanup_status` - Show this status\n"
                      "• `!cleanup_test` - Test cleanup system",
                inline=False
            )
            
            embed.set_footer(text="User cleanup automatically removes database entries for users who have left the server")
            
            await ctx.send(embed=embed)
            
        except Exception as e:
            logger.error(f"Error in cleanup status command: {e}", exc_info=True)
            embed = build_error_embed(
                "Status Error",
                f"Error getting cleanup status: {str(e)}"
            )
            await ctx.send(embed=embed)

    @commands.command(name="cleanup_test")
    @commands.has_permissions(administrator=True)
    async def cleanup_test(self, ctx):
        """Test the user cleanup system with detailed output."""
        try:
            info_embed = build_info_embed(
                "Cleanup Test",
                "Testing user cleanup system..."
            )
            await ctx.send(embed=info_embed)
            
            # Get current statistics
            all_users = await self.get_all_registered_users()
            guild_members = await self.get_guild_members(ctx.guild)
            
            # Analyze users for this guild
            has_guild_id = len(all_users[0]) > 4 if all_users else False
            
            if has_guild_id:
                guild_users = [user for user in all_users if user[2] == ctx.guild.id]
            else:
                guild_users = all_users
            
            # Count users who have left
            users_left = []
            for user in guild_users:
                if has_guild_id:
                    discord_id = user[1]
                    username = user[3]
                else:
                    discord_id = user[1]
                    username = user[2]
                
                if discord_id not in guild_members:
                    users_left.append((discord_id, username))
            
            embed = build_info_embed(
                "User Cleanup Test Results",
                f"**Total Registered Users:** {len(all_users)}\n"
                f"**Guild Members:** {len(guild_members)}\n"
                f"**Guild Registered Users:** {len(guild_users)}\n"
                f"**Users Who Left:** {len(users_left)}"
            )
            
            if users_left:
                # Show first few users who left
                left_list = []
                for i, (discord_id, username) in enumerate(users_left[:5]):
                    left_list.append(f"{i+1}. {username} (ID: {discord_id})")
                
                if len(users_left) > 5:
                    left_list.append(f"... and {len(users_left) - 5} more")
                
                embed.add_field(
                    name="👻 Users Who Left Server",
                    value="\n".join(left_list),
                    inline=False
                )
            else:
                embed.add_field(
                    name="✨ Result",
                    value="No inactive users found - database is clean!",
                    inline=False
                )
            
            embed.add_field(
                name="🔧 Schema Info",
                value=f"**Multi-guild Support:** {'✅ Yes' if has_guild_id else '❌ No (Legacy mode)'}",
                inline=False
            )
            
            embed.set_footer(text="This is a test - no users were actually removed. Use !cleanup_users to perform actual cleanup.")
            
            await ctx.send(embed=embed)
            
        except Exception as e:
            logger.error(f"Error in cleanup test command: {e}", exc_info=True)
            embed = build_error_embed(
                "Cleanup Test Error",
                f"Error during cleanup test: {str(e)}"
            )
            await ctx.send(embed=embed)


async def setup(bot: commands.Bot):
    """Set up the UserCleanup cog."""
    try:
        await bot.add_cog(UserCleanup(bot))
        logger.info("UserCleanup cog successfully loaded")
    except Exception as e:
        logger.error(f"Failed to load UserCleanup cog: {e}", exc_info=True)
        raise