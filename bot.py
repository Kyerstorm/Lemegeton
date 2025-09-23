# bot.py
import sys
import os
import asyncio
import logging
import time
import aiohttp
import discord
from discord.ext import commands
from database import init_db

# Add project root to sys.path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from config import TOKEN, GUILD_ID, BOT_ID, ADMIN_DISCORD_ID

# ------------------------------------------------------
# Logging Setup
# ------------------------------------------------------
# Configuration constants
LOG_DIR = "logs"
LOG_FILE = "bot.log"
LOG_MAX_SIZE = 50 * 1024 * 1024  # 50MB max log file size
TRENDING_REFRESH_INTERVAL = 3 * 60 * 60  
STATUS_UPDATE_INTERVAL = 60 
COG_WATCH_INTERVAL = 2 
ANILIST_API_TIMEOUT = 10 
DEFAULT_TRENDING_FALLBACK = ["AniList API ❤️"]

# Ensure logs directory exists
os.makedirs(LOG_DIR, exist_ok=True)

# Configure comprehensive file-based logging
log_file_path = os.path.join(LOG_DIR, LOG_FILE)

# Clear existing log file if it's too large
if os.path.exists(log_file_path) and os.path.getsize(log_file_path) > LOG_MAX_SIZE:
    open(log_file_path, 'w').close()

# Setup file handler with detailed formatting
file_handler = logging.FileHandler(log_file_path, encoding='utf-8')
file_handler.setLevel(logging.DEBUG)

# Setup console handler
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)

# Create formatter
formatter = logging.Formatter(
    '[%(asctime)s] [%(levelname)s] [%(name)s] %(funcName)s:%(lineno)d - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

file_handler.setFormatter(formatter)
console_handler.setFormatter(formatter)

# Configure root logger
logging.basicConfig(
    level=logging.DEBUG,
    handlers=[file_handler, console_handler],
    force=True
)

# Create bot logger
logger = logging.getLogger("Bot")
logger.info("="*50)
logger.info("Bot logging system initialized")
logger.info(f"Log file: {log_file_path}")
logger.info("="*50)

# Import monitoring integration (optional)
try:
    from bot_monitoring import setup_bot_monitoring
    MONITORING_ENABLED = True
    logger.info("✅ Bot monitoring system available")
except ImportError:
    MONITORING_ENABLED = False
    logger.warning("⚠️ Bot monitoring system not available")

# ------------------------------------------------------
# Intents and Bot Setup
# ------------------------------------------------------
intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents, application_id=BOT_ID)

# Initialize monitoring system if available
monitoring = None
if MONITORING_ENABLED:
    try:
        monitoring = setup_bot_monitoring(bot)
        if monitoring:
            logger.info("✅ Bot monitoring integration initialized")
        else:
            logger.warning("⚠️ Bot monitoring setup failed")
    except Exception as e:
        logger.error(f"❌ Error setting up bot monitoring: {e}")
        MONITORING_ENABLED = False

# ------------------------------------------------------
# AniList API Function
# ------------------------------------------------------
ANILIST_API_URL = "https://graphql.anilist.co"

async def fetch_trending_anime_list():
    """
    Fetch trending anime list from AniList API with comprehensive logging and error handling.
    Returns a list of anime titles or fallback list if API fails.
    """
    logger.debug("Starting AniList trending anime fetch")
    
    query = """
    query {
        Page(page: 1, perPage: 10) {
            media(sort: TRENDING_DESC, type: ANIME) {
                title {
                    romaji
                    english
                }
            }
        }
    }
    """
    
    try:
        logger.debug(f"Making request to AniList API: {ANILIST_API_URL}")
        
        timeout = aiohttp.ClientTimeout(total=ANILIST_API_TIMEOUT)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            start_time = time.time()
            
            async with session.post(
                ANILIST_API_URL, 
                json={"query": query},
                headers={'Content-Type': 'application/json'}
            ) as response:
                
                response_time = time.time() - start_time
                logger.debug(f"AniList API response received in {response_time:.2f}s - Status: {response.status}")
                
                if response.status != 200:
                    logger.error(f"AniList API request failed with status {response.status}")
                    logger.debug(f"Response headers: {dict(response.headers)}")
                    return DEFAULT_TRENDING_FALLBACK
                
                try:
                    data = await response.json()
                    logger.debug("Successfully parsed JSON response")
                except Exception as json_error:
                    logger.error(f"Failed to parse JSON response: {json_error}")
                    return DEFAULT_TRENDING_FALLBACK
                
                # Validate response structure
                if not isinstance(data, dict) or 'data' not in data:
                    logger.error(f"Invalid response structure: missing 'data' field")
                    return DEFAULT_TRENDING_FALLBACK
                
                if 'Page' not in data['data'] or 'media' not in data['data']['Page']:
                    logger.error("Invalid response structure: missing Page.media")
                    return DEFAULT_TRENDING_FALLBACK
                
                anime_list = data["data"]["Page"]["media"]
                logger.debug(f"Retrieved {len(anime_list)} anime entries from API")
                
                # Process anime titles with validation
                processed_titles = []
                for i, anime in enumerate(anime_list):
                    try:
                        if not isinstance(anime, dict) or 'title' not in anime:
                            logger.warning(f"Anime entry {i} missing title field")
                            continue
                            
                        title_data = anime['title']
                        if not isinstance(title_data, dict):
                            logger.warning(f"Anime entry {i} has invalid title data")
                            continue
                            
                        # Prefer English title, fallback to Romaji
                        title = title_data.get('english') or title_data.get('romaji')
                        if title and isinstance(title, str) and title.strip():
                            processed_titles.append(title.strip())
                            logger.debug(f"Added anime title: {title}")
                        else:
                            logger.warning(f"Anime entry {i} has no valid title")
                            
                    except Exception as title_error:
                        logger.warning(f"Error processing anime entry {i}: {title_error}")
                        continue
                
                if processed_titles:
                    logger.info(f"Successfully fetched {len(processed_titles)} trending anime titles")
                    return processed_titles
                else:
                    logger.warning("No valid anime titles found, using fallback")
                    return DEFAULT_TRENDING_FALLBACK
                    
    except aiohttp.ClientTimeout:
        logger.error(f"AniList API request timed out after {ANILIST_API_TIMEOUT}s")
        return DEFAULT_TRENDING_FALLBACK
    except aiohttp.ClientError as client_error:
        logger.error(f"AniList API client error: {client_error}")
        return DEFAULT_TRENDING_FALLBACK
    except Exception as e:
        logger.error(f"Unexpected error fetching trending anime: {e}", exc_info=True)
        return DEFAULT_TRENDING_FALLBACK

# ------------------------------------------------------
# Streaming Status Loop
# ------------------------------------------------------
async def update_streaming_status():
    """
    Continuously update bot's streaming status with trending anime titles.
    Cycles through anime list and refreshes trending data periodically.
    """
    logger.info("Starting streaming status updater")
    
    try:
        await bot.wait_until_ready()
        logger.debug("Bot ready, initializing streaming status")
        
        # Initial fetch of trending anime
        logger.debug("Fetching initial trending anime list")
        trending = await fetch_trending_anime_list()
        logger.info(f"Initialized with {len(trending)} anime titles")
        
        index = 0
        last_refresh = time.time()
        cycle_count = 0
        
        while not bot.is_closed():
            try:
                # Get current anime title
                if not trending or index >= len(trending):
                    logger.warning("Invalid trending list or index, resetting")
                    trending = await fetch_trending_anime_list()
                    index = 0
                    continue
                
                anime_title = trending[index]
                logger.debug(f"Setting streaming status to anime {index+1}/{len(trending)}: {anime_title}")
                
                # Create and set streaming activity
                stream = discord.Streaming(
                    name=f"🎥 {anime_title}",
                    url="https://www.twitch.tv/owobotplays"
                )
                
                await bot.change_presence(activity=stream)
                logger.info(f"🎥 Streaming status updated to: {anime_title}")
                
                # Move to next anime, loop back if at end
                index = (index + 1) % len(trending)
                if index == 0:
                    cycle_count += 1
                    logger.debug(f"Completed cycle {cycle_count} through trending anime list")
                
                # Check if it's time to refresh trending list
                time_since_refresh = time.time() - last_refresh
                if time_since_refresh >= TRENDING_REFRESH_INTERVAL:
                    logger.info(f"🔄 Refreshing trending list after {time_since_refresh/3600:.1f} hours")
                    
                    try:
                        new_trending = await fetch_trending_anime_list()
                        if new_trending != trending:
                            logger.info(f"Trending list updated: {len(new_trending)} titles (was {len(trending)})")
                            trending = new_trending
                            index = 0  # Reset to start of new list
                        else:
                            logger.debug("Trending list unchanged after refresh")
                    except Exception as refresh_error:
                        logger.error(f"Error refreshing trending list: {refresh_error}")
                        # Continue with existing list
                    
                    last_refresh = time.time()
                
                # Wait before next update
                logger.debug(f"Waiting {STATUS_UPDATE_INTERVAL}s before next status update")
                await asyncio.sleep(STATUS_UPDATE_INTERVAL)
                
            except discord.HTTPException as http_error:
                logger.error(f"Discord HTTP error updating status: {http_error}")
                await asyncio.sleep(STATUS_UPDATE_INTERVAL * 2)  # Wait longer on HTTP errors
            except Exception as status_error:
                logger.error(f"Unexpected error in status update loop: {status_error}", exc_info=True)
                await asyncio.sleep(STATUS_UPDATE_INTERVAL)
                
    except Exception as e:
        logger.error(f"Fatal error in streaming status updater: {e}", exc_info=True)
        # Try to restart after delay
        logger.info("Attempting to restart streaming status updater in 60 seconds")
        await asyncio.sleep(60)
        bot.loop.create_task(update_streaming_status())

# ------------------------------------------------------
# Cog Management with Timestamps
# ------------------------------------------------------
cog_timestamps = {}
cog_loading_semaphore = asyncio.Semaphore(1)  # Prevent concurrent cog loading

async def load_cogs():
    """
    Load and manage cogs with timestamp tracking and comprehensive error handling.
    Only one cog loading operation can run at a time to prevent race conditions.
    """
    async with cog_loading_semaphore:
        logger.debug("Acquired cog loading semaphore")
        try:
            await _load_cogs_impl()
        finally:
            logger.debug("Released cog loading semaphore")

async def _load_cogs_impl():
    """
    Load or reload all cogs asynchronously with comprehensive logging and error handling.
    Tracks file modification times to only reload changed cogs.
    """
    logger.debug("Starting cog loading/reloading process")
    
    try:
        # Clean up any stuck extensions first (from previous crashes/forced shutdowns)
        loaded_extensions = list(bot.extensions.keys())
        for ext_name in loaded_extensions:
            if ext_name.startswith('cogs.'):
                try:
                    # Check if the corresponding file still exists
                    cog_file = f"./cogs/{ext_name[5:]}.py"
                    if not os.path.exists(cog_file):
                        logger.debug(f"Cleaning up orphaned extension: {ext_name}")
                        await bot.unload_extension(ext_name)
                        if ext_name in cog_timestamps:
                            del cog_timestamps[ext_name]
                except Exception as cleanup_error:
                    logger.error(f"Failed to cleanup extension {ext_name}: {cleanup_error}")
        
        cogs_dir = "./cogs"
        if not os.path.exists(cogs_dir):
            logger.error(f"Cogs directory not found: {cogs_dir}")
            return
            
        # Get all Python files in cogs directory
        cog_files = [f for f in os.listdir(cogs_dir) 
                     if f.endswith(".py") and f != "__init__.py"]
        
        logger.debug(f"Found {len(cog_files)} potential cog files")
        
        loaded_count = 0
        reloaded_count = 0
        failed_count = 0
        
        for filename in cog_files:
            cog_name = f"cogs.{filename[:-3]}"
            file_path = os.path.join(cogs_dir, filename)
            
            try:
                # Get file modification time
                if not os.path.exists(file_path):
                    logger.warning(f"Cog file not found: {file_path}")
                    continue
                    
                last_mod = os.path.getmtime(file_path)
                logger.debug(f"Checking cog {cog_name} - File modified: {time.ctime(last_mod)}")
                
                # Check if cog is already loaded
                if cog_name in bot.extensions:
                    stored_timestamp = cog_timestamps.get(cog_name, 0)
                    
                    # Ensure timestamp is always recorded for loaded cogs
                    if cog_name not in cog_timestamps:
                        cog_timestamps[cog_name] = last_mod
                        logger.debug(f"Added missing timestamp for already-loaded cog {cog_name}")
                    
                    # Only reload if file was modified since last load
                    elif stored_timestamp < last_mod:
                        logger.debug(f"File {filename} modified, reloading cog")
                        
                        try:
                            await bot.reload_extension(cog_name)
                            cog_timestamps[cog_name] = last_mod
                            logger.info(f"🔄 Successfully reloaded cog: {cog_name}")
                            reloaded_count += 1
                        except Exception as reload_error:
                            logger.error(f"❌ Failed to reload cog {cog_name}: {reload_error}", exc_info=True)
                            
                            # If reload fails, unload the broken extension
                            try:
                                await bot.unload_extension(cog_name)
                                logger.debug(f"Unloaded broken extension: {cog_name}")
                                if cog_name in cog_timestamps:
                                    del cog_timestamps[cog_name]
                            except Exception as unload_error:
                                logger.error(f"Failed to unload broken extension {cog_name}: {unload_error}")
                            
                            failed_count += 1
                    else:
                        logger.debug(f"Cog {cog_name} is up to date")
                else:
                    # Load new cog
                    logger.debug(f"Loading new cog: {cog_name}")
                    
                    try:
                        logger.debug(f"About to load extension: {cog_name}")
                        
                        # Check if cog is already loaded before attempting to load
                        cog_class_name = cog_name.split('.')[-1].capitalize()  # e.g., "steam" -> "Steam"
                        existing_cog = bot.get_cog(cog_class_name)
                        if existing_cog:
                            logger.warning(f"Cog {cog_class_name} is already loaded, attempting to unload first")
                            try:
                                await bot.remove_cog(cog_class_name)
                                logger.debug(f"Successfully unloaded existing cog: {cog_class_name}")
                            except Exception as unload_error:
                                logger.error(f"Failed to unload existing cog {cog_class_name}: {unload_error}")
                        
                        await bot.load_extension(cog_name)
                        cog_timestamps[cog_name] = last_mod
                        logger.info(f"✅ Successfully loaded cog: {cog_name}")
                        loaded_count += 1
                    except Exception as load_error:
                        logger.error(f"❌ Failed to load cog {cog_name}: {load_error}", exc_info=True)
                        
                        # If the extension was partially loaded but failed, try to unload it
                        if cog_name in bot.extensions:
                            try:
                                await bot.unload_extension(cog_name)
                                logger.debug(f"Cleaned up partially loaded extension: {cog_name}")
                            except Exception as cleanup_error:
                                logger.error(f"Failed to cleanup extension {cog_name}: {cleanup_error}")
                        
                        failed_count += 1
                        
            except OSError as file_error:
                logger.error(f"File system error accessing {file_path}: {file_error}")
                failed_count += 1
            except Exception as cog_error:
                logger.error(f"Unexpected error processing cog {cog_name}: {cog_error}", exc_info=True)
                failed_count += 1
        
        # Summary logging
        total_operations = loaded_count + reloaded_count + failed_count
        if total_operations > 0:
            logger.info(f"Cog loading summary: {loaded_count} loaded, {reloaded_count} reloaded, {failed_count} failed")
        
        # Log current cog status
        logger.debug(f"Total cogs tracked: {len(cog_timestamps)}")
        logger.debug(f"Currently loaded extensions: {len(bot.extensions)}")
        
    except Exception as e:
        logger.error(f"Fatal error in load_cogs: {e}", exc_info=True)

async def watch_cogs():
    """
    Continuously monitor cogs directory for changes with comprehensive logging.
    """
    logger.info("Starting cog file watcher")
    
    # Wait for bot to be ready to avoid race conditions during initial startup
    logger.debug("Waiting for bot to be ready before starting cog monitoring...")
    await bot.wait_until_ready()
    logger.debug("Bot is ready, starting cog file monitoring")
    
    # Additional delay to ensure initial loading is completely finished
    await asyncio.sleep(5)
    logger.debug("Initial delay completed, beginning cog watch cycles")
    
    watch_cycle = 0
    
    try:
        while True:
            try:
                watch_cycle += 1
                logger.debug(f"Cog watch cycle {watch_cycle}")
                
                await load_cogs()
                
                logger.debug(f"Waiting {COG_WATCH_INTERVAL}s before next cog check")
                await asyncio.sleep(COG_WATCH_INTERVAL)
                
            except Exception as watch_error:
                logger.error(f"Error in cog watch cycle {watch_cycle}: {watch_error}", exc_info=True)
                await asyncio.sleep(COG_WATCH_INTERVAL * 2)  # Wait longer on errors
                
    except Exception as e:
        logger.error(f"Fatal error in cog watcher: {e}", exc_info=True)
        # Attempt to restart watcher
        logger.info("Attempting to restart cog watcher in 30 seconds")
        await asyncio.sleep(30)
        asyncio.create_task(watch_cogs())

# ------------------------------------------------------
# Server Logging Function
# ------------------------------------------------------
async def log_server_information():
    """
    Log detailed information about all servers the bot is connected to.
    Creates a separate log file with server details for monitoring purposes.
    """
    try:
        # Create server log file
        server_log_path = os.path.join(LOG_DIR, "servers.log")
        
        with open(server_log_path, 'w', encoding='utf-8') as server_log:
            server_log.write("=" * 80 + "\n")
            server_log.write(f"BOT SERVER INFORMATION - {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
            server_log.write("=" * 80 + "\n")
            server_log.write(f"Bot User: {bot.user} (ID: {bot.user.id})\n")
            server_log.write(f"Total Servers: {len(bot.guilds)}\n")
            server_log.write(f"Bot Latency: {bot.latency*1000:.2f}ms\n")
            server_log.write("-" * 80 + "\n\n")
            
            total_members = 0
            
            for i, guild in enumerate(bot.guilds, 1):
                try:
                    # Get guild information
                    owner = guild.owner
                    owner_info = f"{owner} (ID: {owner.id})" if owner else "Unknown"
                    created_date = guild.created_at.strftime('%Y-%m-%d')
                    
                    # Count text and voice channels
                    text_channels = len([c for c in guild.channels if isinstance(c, discord.TextChannel)])
                    voice_channels = len([c for c in guild.channels if isinstance(c, discord.VoiceChannel)])
                    
                    # Count roles
                    role_count = len(guild.roles)
                    
                    # Add to total members
                    total_members += guild.member_count
                    
                    # Write server information
                    server_log.write(f"[{i}] SERVER: {guild.name}\n")
                    server_log.write(f"     Guild ID: {guild.id}\n")
                    server_log.write(f"     Owner: {owner_info}\n")
                    server_log.write(f"     Members: {guild.member_count:,}\n")
                    server_log.write(f"     Created: {created_date}\n")
                    server_log.write(f"     Channels: {text_channels} text, {voice_channels} voice\n")
                    server_log.write(f"     Roles: {role_count}\n")
                    server_log.write(f"     Features: {', '.join(guild.features) if guild.features else 'None'}\n")
                    
                    # Check bot permissions
                    try:
                        bot_member = guild.get_member(bot.user.id)
                        if bot_member:
                            permissions = bot_member.guild_permissions
                            admin = permissions.administrator
                            manage_server = permissions.manage_guild
                            send_messages = permissions.send_messages
                            
                            server_log.write(f"     Bot Perms: Admin={admin}, Manage Server={manage_server}, Send Messages={send_messages}\n")
                    except Exception as perm_error:
                        server_log.write(f"     Bot Perms: Error retrieving - {perm_error}\n")
                    
                    server_log.write("\n")
                    
                except Exception as guild_error:
                    server_log.write(f"[{i}] ERROR processing guild {guild.id}: {guild_error}\n\n")
                    logger.warning(f"Error processing guild {guild.id}: {guild_error}")
            
            # Write summary
            server_log.write("-" * 80 + "\n")
            server_log.write("SUMMARY:\n")
            server_log.write(f"Total Servers: {len(bot.guilds)}\n")
            server_log.write(f"Total Members Across All Servers: {total_members:,}\n")
            server_log.write(f"Average Members per Server: {total_members/len(bot.guilds):.1f}\n" if bot.guilds else "")
            server_log.write("=" * 80 + "\n")
        
        logger.info(f"✅ Server information logged to: {server_log_path}")
        logger.info(f"Bot is connected to {len(bot.guilds)} servers with {total_members:,} total members")
        
    except Exception as e:
        logger.error(f"Error logging server information: {e}", exc_info=True)

# ------------------------------------------------------
# Bot Events with Comprehensive Logging
# ------------------------------------------------------
@bot.event
async def on_ready():
    """
    Bot ready event handler with comprehensive logging and initialization.
    """
    logger.info("="*60)
    logger.info("BOT READY EVENT TRIGGERED")
    logger.info(f"✅ Logged in as: {bot.user} (ID: {bot.user.id})")
    logger.info(f"Connected to {len(bot.guilds)} guilds")
    logger.info(f"Bot latency: {bot.latency*1000:.2f}ms")
    logger.info("="*60)
    
    try:
        # Log guild information with detailed server logging
        await log_server_information()
        
        for guild in bot.guilds:
            logger.debug(f"Connected to guild: {guild.name} (ID: {guild.id}) - {guild.member_count} members")
        
        # Force ALL commands to be global by copying from guild to global and clearing guild tree
        logger.info("Starting global command synchronization")
        guild = discord.Object(id=GUILD_ID)
        
        try:
            # First clear any existing global commands
            bot.tree.clear_commands(guild=None)
            logger.debug("Cleared existing global commands")
            
            # Copy all commands from the guild tree to the global tree
            guild_commands = bot.tree.get_commands(guild=guild)
            if guild_commands:
                logger.debug(f"Found {len(guild_commands)} guild commands to copy to global")
                for cmd in guild_commands:
                    bot.tree.add_command(cmd, guild=None)
                    logger.debug(f"Copied command '{cmd.name}' to global scope")
            
            # Now sync everything globally to make ALL commands available everywhere
            logger.debug("Syncing all commands globally")
            global_synced = await bot.tree.sync()
            logger.info(f"✅ Successfully synced {len(global_synced)} global commands")
            logger.info("🌍 ALL COMMANDS are now available in EVERY server the bot joins!")
            
            # Log each synced global command
            for cmd in global_synced:
                logger.info(f"Global command available: {cmd.name}")
                
        except discord.HTTPException as http_error:
            logger.error(f"HTTP error syncing global commands: {http_error}")
        except Exception as sync_error:
            logger.error(f"Error syncing global commands: {sync_error}", exc_info=True)
        except Exception as global_sync_error:
            logger.error(f"Error syncing global commands: {global_sync_error}", exc_info=True)
        
        # Start background tasks
        logger.info("Starting background tasks")
        
        try:
            logger.debug("Creating streaming status updater task")
            bot.loop.create_task(update_streaming_status())
            logger.info("✅ Streaming status updater started")
        except Exception as status_task_error:
            logger.error(f"Failed to start streaming status updater: {status_task_error}")
        
        logger.info("Bot initialization completed successfully")
        logger.info("="*60)
        
    except Exception as e:
        logger.error(f"Error in on_ready event: {e}", exc_info=True)

@bot.event
async def on_disconnect():
    """Log bot disconnection events."""
    logger.warning("🔌 Bot disconnected from Discord")

@bot.event
async def on_resumed():
    """Log bot reconnection events."""
    logger.info("🔄 Bot connection resumed")

@bot.event
async def on_error(event, *args, **kwargs):
    """Log unhandled errors in bot events."""
    logger.error(f"Unhandled error in event '{event}': {args}, {kwargs}", exc_info=True)

@bot.event 
async def on_command_error(ctx, error):
    """Log command errors."""
    logger.error(f"Command error in '{ctx.command}' by {ctx.author}: {error}", exc_info=True)

@bot.event
async def on_guild_join(guild):
    """Log when bot joins a new server."""
    logger.info(f"🎉 Bot joined new server: {guild.name} (ID: {guild.id}) - {guild.member_count} members")
    
    # Update server log when joining new server
    try:
        await log_server_information()
    except Exception as e:
        logger.error(f"Error updating server log after guild join: {e}")

@bot.event
async def on_guild_remove(guild):
    """Log when bot leaves a server."""
    logger.info(f"👋 Bot removed from server: {guild.name} (ID: {guild.id})")
    
    # Update server log when leaving server
    try:
        await log_server_information()
    except Exception as e:
        logger.error(f"Error updating server log after guild remove: {e}")

# Manual server logging command (for debugging)
@bot.tree.command(name="log_servers", description="🔍 Manually log server information (Owner only)")
async def manual_server_log(interaction: discord.Interaction):
    """Manually trigger server logging (restricted to bot owner)."""
    # Check if user is bot owner or admin
    if interaction.user.id != ADMIN_DISCORD_ID:
        await interaction.response.send_message("❌ This command is restricted to the bot owner.", ephemeral=True)
        return
    
    try:
        await interaction.response.defer(ephemeral=True)
        await log_server_information()
        
        embed = discord.Embed(
            title="🔍 Server Information Logged",
            description=f"Successfully logged information for {len(bot.guilds)} servers to `logs/servers.log`",
            color=0x00FF00
        )
        
        total_members = sum(guild.member_count for guild in bot.guilds)
        embed.add_field(name="Total Servers", value=str(len(bot.guilds)), inline=True)
        embed.add_field(name="Total Members", value=f"{total_members:,}", inline=True)
        embed.add_field(name="Average Members/Server", value=f"{total_members/len(bot.guilds):.1f}" if bot.guilds else "0", inline=True)
        
        await interaction.followup.send(embed=embed, ephemeral=True)
        logger.info(f"Manual server log triggered by {interaction.user}")
        
    except Exception as e:
        logger.error(f"Error in manual server log command: {e}")
        await interaction.followup.send("❌ Error occurred while logging server information.", ephemeral=True)

# ------------------------------------------------------
# Main Function with Comprehensive Logging
# ------------------------------------------------------
async def main():
    """
    Main bot initialization function with comprehensive logging and error handling.
    """
    logger.info("="*60)
    logger.info("STARTING BOT INITIALIZATION")
    logger.info("="*60)
    
    try:
        # Initialize database with logging
        logger.info("Initializing database...")
        try:
            await init_db()
            logger.info("✅ Database initialization completed")
        except Exception as db_error:
            logger.error(f"❌ Database initialization failed: {db_error}", exc_info=True)
            raise
        
        # Load cogs with logging
        logger.info("Loading bot cogs...")
        try:
            await load_cogs()
            logger.info("✅ Initial cog loading completed")
        except Exception as cog_error:
            logger.error(f"❌ Cog loading failed: {cog_error}", exc_info=True)
            # Continue anyway - some cogs might have loaded successfully
        
        # Start cog watcher with logging
        logger.info("Starting cog file watcher...")
        try:
            asyncio.create_task(watch_cogs())
            logger.info("✅ Cog watcher started")
        except Exception as watcher_error:
            logger.error(f"❌ Cog watcher failed to start: {watcher_error}", exc_info=True)
            # Continue without watcher
        
        # Validate configuration
        logger.info("Validating configuration...")
        if not TOKEN:
            logger.error("❌ Bot token not found in configuration")
            raise ValueError("Bot token is required")
        if not GUILD_ID:
            logger.error("❌ Guild ID not found in configuration")
            raise ValueError("Guild ID is required")
        if not BOT_ID:
            logger.error("❌ Bot ID not found in configuration")
            raise ValueError("Bot ID is required")
        
        logger.info("✅ Configuration validation passed")
        
        # Start the bot with comprehensive logging
        logger.info("Starting Discord bot connection...")
        logger.info(f"Bot ID: {BOT_ID}")
        logger.info(f"Target Guild: {GUILD_ID}")
        logger.info("="*60)
        
        try:
            await bot.start(TOKEN)
        except discord.LoginFailure as login_error:
            logger.error(f"❌ Bot login failed - Invalid token: {login_error}")
            raise
        except discord.ConnectionClosed as connection_error:
            logger.error(f"❌ Bot connection closed: {connection_error}")
            raise
        except Exception as bot_error:
            logger.error(f"❌ Bot startup failed: {bot_error}", exc_info=True)
            raise
            
    except KeyboardInterrupt:
        logger.info("Bot shutdown requested by user (Ctrl+C)")
    except Exception as e:
        logger.error(f"❌ Fatal error in main function: {e}", exc_info=True)
        raise
    finally:
        logger.info("Bot shutdown sequence initiated")
        if not bot.is_closed():
            logger.debug("Closing bot connection...")
            await bot.close()
        logger.info("Bot shutdown completed")
        logger.info("="*60)

# ------------------------------------------------------
# Entry Point with Enhanced Error Handling
# ------------------------------------------------------
if __name__ == "__main__":
    try:
        logger.info("Bot entry point started")
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot stopped by user interrupt")
    except Exception as entry_error:
        logger.error(f"Fatal error at entry point: {entry_error}", exc_info=True)
        sys.exit(1)
