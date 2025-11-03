# bot.py
import sys
import os
import asyncio
import logging
import time
import aiohttp
import discord
from discord.ext import commands
from database import init_db, get_all_users_guild_aware, remove_user, clear_guild_records, get_all_guild_ids_with_records
import signal
import random
from typing import Optional, Dict, List
from datetime import datetime

# Add project root to sys.path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from config import (
    TOKEN, GUILD_ID, BOT_ID, ADMIN_DISCORD_ID,
    DISCORD_WEBHOOK_URL, LOG_MAX_SIZE, TRENDING_REFRESH_INTERVAL,
    STATUS_UPDATE_INTERVAL, COG_WATCH_INTERVAL_PROD, COG_WATCH_INTERVAL_DEV,
    ANILIST_API_TIMEOUT, DEFAULT_TRENDING_FALLBACK, API_MAX_RETRIES,
    API_RETRY_BASE_DELAY, DB_CONNECTION_POOL_SIZE, USER_CLEANUP_INTERVAL,
    TWITCH_STREAMING_URL, ANILIST_API_URL
)
import hashlib
import json

# ------------------------------------------------------
# Logging Setup
# ------------------------------------------------------
# Configuration constants
LOG_DIR = "logs"
LOG_FILE = "bot.log"
# Adjust cog watch interval based on environment
COG_WATCH_INTERVAL = COG_WATCH_INTERVAL_PROD if os.getenv("ENVIRONMENT") == "production" else COG_WATCH_INTERVAL_DEV

# Ensure logs directory exists
os.makedirs(LOG_DIR, exist_ok=True)

# Clear all log files on startup
def clear_log_files():
    """Clear all .log files in the logs directory on bot startup"""
    try:
        log_files_cleared = 0
        for filename in os.listdir(LOG_DIR):
            if filename.endswith('.log'):
                file_path = os.path.join(LOG_DIR, filename)
                try:
                    # Clear the file content
                    with open(file_path, 'w') as f:
                        f.write('')
                    log_files_cleared += 1
                except Exception as e:
                    print(f"Warning: Could not clear {filename}: {e}")
        print(f"✅ Cleared {log_files_cleared} log files on startup")
        return log_files_cleared
    except Exception as e:
        print(f"⚠️ Error clearing log files: {e}")
        return 0

# Clear all logs on startup
cleared_count = clear_log_files()

# Configure comprehensive file-based logging
log_file_path = os.path.join(LOG_DIR, LOG_FILE)

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
logger.info(f"Cleared {cleared_count} log files on startup")
logger.info("="*50)

# Import monitoring integration (optional)
try:
    from utils.bot_monitoring import setup_bot_monitoring
    MONITORING_ENABLED = True
    logger.info("✅ Bot monitoring system available")
except ImportError:
    MONITORING_ENABLED = False
    logger.warning("⚠️ Bot monitoring system not available")

# ------------------------------------------------------
# Utility Classes - Enhanced Features
# ------------------------------------------------------

class APIRetryHandler:
    """Handle API retries with exponential backoff for resilient network operations"""

    def __init__(self, max_retries: int = 3, base_delay: float = 1.0):
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.logger = logging.getLogger("APIRetryHandler")

    async def retry_with_backoff(self, func, *args, **kwargs):
        """
        Execute function with exponential backoff retry logic.

        Args:
            func: Async function to execute
            *args, **kwargs: Arguments to pass to function

        Returns:
            Result from function execution

        Raises:
            Exception: If all retries fail, raises the last exception
        """
        last_exception = None

        for attempt in range(self.max_retries):
            try:
                self.logger.debug(f"Attempt {attempt + 1}/{self.max_retries} for {func.__name__}")
                result = await func(*args, **kwargs)

                if attempt > 0:
                    self.logger.info(f"✅ {func.__name__} succeeded on attempt {attempt + 1}")

                return result

            except aiohttp.ClientTimeout as e:
                last_exception = e
                if attempt < self.max_retries - 1:
                    delay = self.base_delay * (2 ** attempt)
                    self.logger.warning(f"Timeout on {func.__name__}, retry {attempt + 1}/{self.max_retries} after {delay}s")
                    await asyncio.sleep(delay)
                else:
                    self.logger.error(f"❌ {func.__name__} failed after {self.max_retries} attempts: {e}")

            except aiohttp.ClientError as e:
                last_exception = e
                if attempt < self.max_retries - 1:
                    delay = self.base_delay * (2 ** attempt)
                    self.logger.warning(f"Client error on {func.__name__}, retry {attempt + 1}/{self.max_retries} after {delay}s")
                    await asyncio.sleep(delay)
                else:
                    self.logger.error(f"❌ {func.__name__} failed after {self.max_retries} attempts: {e}")

            except Exception as e:
                last_exception = e
                # For unknown exceptions, don't retry
                self.logger.error(f"❌ Unexpected error in {func.__name__}: {e}")
                raise

        # All retries exhausted
        raise last_exception


class WebhookNotifier:
    """Send notifications to external webhooks for monitoring and alerts"""

    def __init__(self, webhook_urls: Optional[Dict[str, str]] = None):
        self.webhook_urls = webhook_urls or {}
        self.logger = logging.getLogger("WebhookNotifier")
        self.enabled = bool(webhook_urls)

        if self.enabled:
            self.logger.info(f"✅ Webhook notifier initialized with {len(webhook_urls)} endpoints")
        else:
            self.logger.debug("Webhook notifier initialized but no endpoints configured")

    def format_discord_embed(self, event_type: str, data: Dict, priority: str) -> Dict:
        """Format data as Discord embed"""
        # Color based on priority
        colors = {
            'info': 0x3498db,      # Blue
            'warning': 0xf39c12,   # Orange
            'critical': 0xe74c3c   # Red
        }
        color = colors.get(priority, 0x95a5a6)

        # Event emoji mapping
        event_emojis = {
            'bot_ready': '✅',
            'bot_shutdown': '🛑',
            'error_occurred': '❌',
            'guild_joined': '🎉',
            'guild_removed': '👋'
        }
        emoji = event_emojis.get(event_type, '📢')

        # Format title
        title = f"{emoji} {event_type.replace('_', ' ').title()}"

        # Build fields from data
        fields = []
        for key, value in data.items():
            # Convert key to readable format
            field_name = key.replace('_', ' ').title()
            field_value = str(value)

            # Truncate long values
            if len(field_value) > 1024:
                field_value = field_value[:1021] + "..."

            fields.append({
                'name': field_name,
                'value': f"`{field_value}`",
                'inline': True
            })

        embed = {
            'title': title,
            'color': color,
            'timestamp': datetime.now().isoformat(),
            'fields': fields,
            'footer': {
                'text': f'Lemegeton Bot • {priority.upper()}'
            }
        }

        return embed

    async def notify(self, event_type: str, data: Dict, priority: str = "info"):
        """
        Send webhook notification for an event.

        Args:
            event_type: Type of event (e.g., 'bot_ready', 'error_occurred')
            data: Event data to send
            priority: Priority level ('info', 'warning', 'critical')
        """
        if not self.enabled:
            self.logger.debug(f"Webhook skipped (disabled): {event_type}")
            return

        webhook_url = self.webhook_urls.get(event_type)
        if not webhook_url:
            self.logger.debug(f"No webhook configured for event: {event_type}")
            return

        try:
            # Format as Discord embed
            embed = self.format_discord_embed(event_type, data, priority)

            payload = {
                'embeds': [embed]
            }

            timeout = aiohttp.ClientTimeout(total=5)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(webhook_url, json=payload) as response:
                    if response.status in [200, 204]:
                        self.logger.info(f"✅ Webhook sent for event: {event_type}")
                    else:
                        self.logger.warning(f"Webhook returned status {response.status} for event: {event_type}")

        except aiohttp.ClientTimeout:
            self.logger.warning(f"⏱️ Webhook timeout for event: {event_type}")
        except Exception as e:
            self.logger.error(f"❌ Webhook failed for event {event_type}: {e}")


class GracefulShutdownHandler:
    """Handle graceful shutdown with cleanup operations"""

    def __init__(self, bot_instance):
        self.bot = bot_instance
        self.logger = logging.getLogger("GracefulShutdown")
        self.shutdown_event = asyncio.Event()
        self.shutdown_initiated = False

    def setup_signal_handlers(self):
        """Register signal handlers for graceful shutdown"""
        def signal_handler(sig, frame):
            if not self.shutdown_initiated:
                self.shutdown_initiated = True
                signal_name = signal.Signals(sig).name
                self.logger.info(f"🛑 Received signal {signal_name}, initiating graceful shutdown...")
                asyncio.create_task(self.shutdown())

        # Register handlers for common shutdown signals
        signal.signal(signal.SIGINT, signal_handler)   # Ctrl+C
        signal.signal(signal.SIGTERM, signal_handler)  # Docker/systemd stop

        self.logger.info("✅ Signal handlers registered for graceful shutdown")

    async def shutdown(self):
        """Perform graceful shutdown sequence"""
        if self.shutdown_event.is_set():
            return

        self.logger.info("="*60)
        self.logger.info("GRACEFUL SHUTDOWN SEQUENCE INITIATED")
        self.logger.info("="*60)

        try:
            # Notify administrators
            self.logger.info("📢 Notifying administrators of shutdown...")
            await self.notify_shutdown()

            # Stop accepting new commands
            self.logger.info("🔒 Stopping command processing...")
            # Note: discord.py automatically handles this during close()

            # Wait for pending operations (with timeout)
            self.logger.info("⏳ Waiting for pending operations (max 30s)...")
            try:
                await asyncio.wait_for(self.wait_for_pending_operations(), timeout=30)
            except asyncio.TimeoutError:
                self.logger.warning("⚠️ Timeout waiting for pending operations, forcing shutdown")

            # Close database connections
            self.logger.info("💾 Closing database connections...")
            # Note: Database connections are handled by database.py

            # Close bot connection
            self.logger.info("🔌 Closing Discord connection...")
            if not self.bot.is_closed():
                await self.bot.close()

            self.logger.info("✅ Graceful shutdown completed successfully")

        except Exception as e:
            self.logger.error(f"❌ Error during graceful shutdown: {e}", exc_info=True)
        finally:
            self.shutdown_event.set()
            self.logger.info("="*60)

    async def notify_shutdown(self):
        """Notify administrators of shutdown"""
        try:
            if ADMIN_DISCORD_ID:
                try:
                    admin_user = await self.bot.fetch_user(ADMIN_DISCORD_ID)
                    embed = discord.Embed(
                        title="🛑 Bot Shutdown",
                        description="The bot is shutting down gracefully.",
                        color=discord.Color.red(),
                        timestamp=datetime.now()
                    )
                    embed.add_field(name="Guilds", value=str(len(self.bot.guilds)))
                    embed.add_field(name="Uptime", value=get_uptime())
                    await admin_user.send(embed=embed)
                    self.logger.info("✅ Admin notified of shutdown")
                except Exception as e:
                    self.logger.warning(f"Could not notify admin: {e}")
        except Exception as e:
            self.logger.error(f"Error notifying shutdown: {e}")

    async def wait_for_pending_operations(self):
        """Wait for pending operations to complete"""
        # Give background tasks time to finish
        await asyncio.sleep(2)


class DatabaseConnectionPool:
    """
    Simple connection pool for database operations.
    Note: This is a basic implementation. The actual database.py handles connections,
    so this serves as a foundation for future improvements.
    """

    def __init__(self, db_path: str, pool_size: int = 5):
        self.db_path = db_path
        self.pool_size = pool_size
        self.connections = asyncio.Queue(maxsize=pool_size)
        self.initialized = False
        self.logger = logging.getLogger("DatabasePool")

    async def initialize(self):
        """Create connection pool - currently a placeholder for future implementation"""
        try:
            # Note: Actual connection pooling would require changes to database.py
            # This is here as a framework for future enhancement
            self.initialized = True
            self.logger.info(f"📊 Database connection pool framework initialized (pool_size={self.pool_size})")
            self.logger.debug("Note: Full pooling requires database.py refactoring")
        except Exception as e:
            self.logger.error(f"Failed to initialize database pool: {e}")
            raise

    async def close(self):
        """Close all connections in pool"""
        if self.initialized:
            self.logger.info("Closing database connection pool")
            # Future implementation would close pooled connections here
            self.initialized = False


# Initialize utility instances (will be populated after bot creation)
api_retry_handler = APIRetryHandler(max_retries=API_MAX_RETRIES, base_delay=API_RETRY_BASE_DELAY)
webhook_notifier = None  # Initialized later with config
shutdown_handler = None  # Initialized after bot creation
db_pool = None  # Initialized in main()

# Uptime tracking
bot_start_time = time.time()

def get_uptime() -> str:
    """Get bot uptime as formatted string"""
    uptime_seconds = int(time.time() - bot_start_time)
    days = uptime_seconds // 86400
    hours = (uptime_seconds % 86400) // 3600
    minutes = (uptime_seconds % 3600) // 60

    if days > 0:
        return f"{days}d {hours}h {minutes}m"
    elif hours > 0:
        return f"{hours}h {minutes}m"
    else:
        return f"{minutes}m"

# ------------------------------------------------------
# Command Sync Optimization Functions
# ------------------------------------------------------
def get_command_signature(command):
    """Generate a signature for command comparison"""
    return {
        'name': command.name,
        'description': command.description,
        'type': str(type(command)),
        'params': len(command.parameters) if hasattr(command, 'parameters') else 0
    }

def commands_hash(commands):
    """Generate hash of command signatures for fast comparison"""
    signatures = [get_command_signature(cmd) for cmd in commands]
    signatures.sort(key=lambda x: x['name'])  # Sort for consistent hash
    return hashlib.md5(json.dumps(signatures, sort_keys=True).encode()).hexdigest()

# ------------------------------------------------------
# Intents and Bot Setup
# ------------------------------------------------------
intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents, application_id=BOT_ID)

# Initialize webhook notifier with Discord webhook from config
WEBHOOK_URLS = {
    'bot_ready': DISCORD_WEBHOOK_URL,
    'bot_shutdown': DISCORD_WEBHOOK_URL,
    'error_occurred': DISCORD_WEBHOOK_URL,
    'guild_joined': DISCORD_WEBHOOK_URL,
    'guild_removed': DISCORD_WEBHOOK_URL,
} if DISCORD_WEBHOOK_URL else {}
webhook_notifier = WebhookNotifier(WEBHOOK_URLS)

# Initialize graceful shutdown handler
shutdown_handler = GracefulShutdownHandler(bot)
try:
    shutdown_handler.setup_signal_handlers()
except Exception as e:
    logger.warning(f"Could not setup signal handlers (may not work on Windows): {e}")

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

async def _fetch_trending_anime_internal():
    """
    Internal function to fetch trending anime from AniList API.
    This is wrapped by fetch_trending_anime_list for retry logic.
    """
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

    except (aiohttp.ClientTimeout, aiohttp.ClientError) as e:
        # Re-raise for retry handler
        raise
    except Exception as e:
        logger.error(f"Unexpected error fetching trending anime: {e}", exc_info=True)
        # Don't retry unexpected errors
        return DEFAULT_TRENDING_FALLBACK


async def fetch_trending_anime_list():
    """
    Fetch trending anime list from AniList API with retry logic.
    Returns a list of anime titles or fallback list if API fails.
    """
    logger.debug("Starting AniList trending anime fetch with retry logic")

    try:
        # Use retry handler for resilient API calls
        result = await api_retry_handler.retry_with_backoff(_fetch_trending_anime_internal)
        return result
    except Exception as e:
        logger.error(f"All retry attempts exhausted for trending anime fetch: {e}")
        return DEFAULT_TRENDING_FALLBACK


# ------------------------------------------------------
# User Cleanup Task
# ------------------------------------------------------
async def cleanup_stale_users():
    """
    Clean up user records for users who are no longer in their registered guilds.
    Runs on startup and every 6 hours to maintain database integrity.
    """
    logger.info("Starting user cleanup task")

    try:
        total_cleaned = 0

        for guild in bot.guilds:
            logger.debug(f"Checking guild: {guild.name} (ID: {guild.id})")

            try:
                # Get all users registered in this guild
                guild_users = await get_all_users_guild_aware(guild.id)

                if not guild_users:
                    logger.debug(f"No registered users in guild {guild.name}")
                    continue

                logger.debug(f"Found {len(guild_users)} registered users in guild {guild.name}")

                for user_data in guild_users:
                    discord_id = user_data[1]  # discord_id is at index 1
                    username = user_data[3]    # username is at index 3

                    try:
                        # Check if user is still in the guild
                        member = guild.get_member(discord_id)

                        if member is None:
                            # User not found in guild, remove their records
                            logger.info(f"Removing stale user record: {username} (ID: {discord_id}) from guild {guild.name}")
                            success = await remove_user(discord_id, guild.id)
                            if success:
                                total_cleaned += 1
                                logger.info(f"Successfully removed records for user {username} from guild {guild.name}")
                            else:
                                logger.warning(f"Failed to remove records for user {username} from guild {guild.name}")

                    except Exception as member_check_error:
                        logger.error(f"Error checking membership for user {discord_id} in guild {guild.id}: {member_check_error}")
                        # Don't remove on error - could be permission issue

            except Exception as guild_error:
                logger.error(f"Error processing guild {guild.id}: {guild_error}")

        if total_cleaned > 0:
            logger.info(f"User cleanup completed: removed {total_cleaned} stale user records")
        else:
            logger.info("User cleanup completed: no stale records found")

    except Exception as e:
        logger.error(f"Fatal error in user cleanup task: {e}", exc_info=True)

async def schedule_user_cleanup():
    """
    Schedule user cleanup to run at configured interval.
    """
    logger.info(f"Starting user cleanup scheduler (runs every {USER_CLEANUP_INTERVAL/3600:.1f} hours)")

    try:
        while not bot.is_closed():
            # Wait for configured interval
            await asyncio.sleep(USER_CLEANUP_INTERVAL)
            
            try:
                logger.info("Running scheduled user cleanup")
                await cleanup_stale_users()
            except Exception as cleanup_error:
                logger.error(f"Error in scheduled user cleanup: {cleanup_error}")
                # Continue the loop despite errors
                
    except Exception as e:
        logger.error(f"Fatal error in user cleanup scheduler: {e}", exc_info=True)

# ------------------------------------------------------
# Guild Cleanup Task
# ------------------------------------------------------
async def cleanup_left_guilds():
    """
    Clean up records for guilds that the bot is no longer in.
    Runs on startup and every 6 hours to maintain database integrity.
    """
    logger.info("Starting guild cleanup task")

    try:
        total_guilds_cleaned = 0
        total_records_deleted = 0

        # Get all guild IDs that have records in the database
        guild_ids_with_records = await get_all_guild_ids_with_records()
        
        if not guild_ids_with_records:
            logger.info("No guild records found in database")
            return

        logger.info(f"Found {len(guild_ids_with_records)} guilds with records in database")

        # Get current guilds the bot is in
        current_guild_ids = {guild.id for guild in bot.guilds}
        logger.debug(f"Bot is currently in {len(current_guild_ids)} guilds: {sorted(current_guild_ids)}")

        for guild_id in guild_ids_with_records:
            try:
                if guild_id not in current_guild_ids:
                    # Bot is no longer in this guild, clean up records
                    logger.info(f"Bot no longer in guild {guild_id}, cleaning up records")
                    
                    success, deleted_counts = await clear_guild_records(guild_id)
                    
                    if success:
                        records_deleted = sum(deleted_counts.values())
                        total_guilds_cleaned += 1
                        total_records_deleted += records_deleted
                        logger.info(f"Successfully cleaned up guild {guild_id}: {records_deleted} records deleted")
                        logger.debug(f"Breakdown for guild {guild_id}: {deleted_counts}")
                    else:
                        logger.error(f"Failed to clean up records for guild {guild_id}")
                else:
                    logger.debug(f"Bot still in guild {guild_id}, keeping records")

            except Exception as guild_error:
                logger.error(f"Error processing guild {guild_id}: {guild_error}")

        if total_guilds_cleaned > 0:
            logger.info(f"Guild cleanup completed: cleaned {total_guilds_cleaned} guilds, deleted {total_records_deleted} total records")
        else:
            logger.info("Guild cleanup completed: no guilds needed cleanup")

    except Exception as e:
        logger.error(f"Fatal error in guild cleanup task: {e}", exc_info=True)

async def schedule_guild_cleanup():
    """
    Schedule guild cleanup to run at configured interval.
    """
    logger.info(f"Starting guild cleanup scheduler (runs every {USER_CLEANUP_INTERVAL/3600:.1f} hours)")

    try:
        while not bot.is_closed():
            # Wait for configured interval
            await asyncio.sleep(USER_CLEANUP_INTERVAL)
            
            try:
                logger.info("Running scheduled guild cleanup")
                await cleanup_left_guilds()
            except Exception as cleanup_error:
                logger.error(f"Error in scheduled guild cleanup: {cleanup_error}")
                # Continue the loop despite errors
                
    except Exception as e:
        logger.error(f"Fatal error in guild cleanup scheduler: {e}", exc_info=True)

# ------------------------------------------------------
# Streaming Status Loop with Enhanced Templates
# ------------------------------------------------------

# Dynamic status message templates for variety
STATUS_TEMPLATES = [
    "🎥 {anime}",
    "📺 Trending: {anime}",
    "⭐ {anime}",
    "🔥 Hot: {anime}",
    "💫 Now: {anime}",
    "🎬 Watching: {anime}",
    "✨ Popular: {anime}",
    "🌟 {anime}",
]

async def update_streaming_status():
    """
    Continuously update bot's streaming status with trending anime titles.
    Uses dynamic templates for variety and cycles through anime list.
    Refreshes trending data periodically with retry logic.
    """
    logger.info("Starting enhanced streaming status updater with templates")
    
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

                # Select random template for variety
                template = random.choice(STATUS_TEMPLATES)
                status_text = template.format(anime=anime_title)

                logger.debug(f"Setting streaming status ({index+1}/{len(trending)}): {status_text}")

                # Create and set streaming activity
                stream = discord.Streaming(
                    name=status_text,
                    url=TWITCH_STREAMING_URL
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
                    # Map dotted extension name to possible filesystem paths under ./cogs
                    # e.g. cogs.anilist.watchlist -> ./cogs/anilist/watchlist.py
                    rel_parts = ext_name.split('.')[1:]
                    cog_file_py = os.path.join('.', 'cogs', *rel_parts) + '.py'
                    cog_package_init = os.path.join('.', 'cogs', *rel_parts, '__init__.py')

                    if not (os.path.exists(cog_file_py) or os.path.exists(cog_package_init)):
                        logger.debug(f"Cleaning up orphaned extension: {ext_name}")
                        await bot.unload_extension(ext_name)
                        if ext_name in cog_timestamps:
                            del cog_timestamps[ext_name]
                except Exception as cleanup_error:
                    logger.error(f"Failed to cleanup extension {ext_name}: {cleanup_error}")
        
        # Check both cogs and cogs_test directories
        cog_dirs = ['cogs', 'cogs_test']
        cog_files = []  # list of tuples (module_relative_path, file_path, base_dir)
        
        for base_dir in cog_dirs:
            cogs_dir = os.path.join('.', base_dir)
            if not os.path.exists(cogs_dir):
                if base_dir == 'cogs':
                    logger.warning(f"Cogs directory not found: {cogs_dir}")
                else:
                    logger.debug(f"Optional cogs directory not found: {cogs_dir}")
                continue

            # Recursively find all Python files under this cog directory (skip package __init__.py files)
            for root, dirs, files in os.walk(cogs_dir):
                for f in files:
                    if not f.endswith('.py'):
                        continue
                    if f == '__init__.py':
                        continue
                    # Skip backup/old files
                    if f.endswith('_old.py') or f.endswith('.backup.py'):
                        continue
                    full_path = os.path.join(root, f)
                    rel_path = os.path.relpath(full_path, cogs_dir)  # e.g. 'anilist/watchlist.py'
                    module_rel = rel_path.replace(os.path.sep, '.')  # e.g. 'anilist.watchlist.py'
                    module_rel = module_rel[:-3]  # strip .py
                    cog_files.append((module_rel, full_path, base_dir))

        logger.debug(f"Found {len(cog_files)} potential cog files (recursive)")
        
        loaded_count = 0
        reloaded_count = 0
        failed_count = 0
        
        for module_rel, file_path, base_dir in cog_files:
            cog_name = f"{base_dir}.{module_rel}"
            
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
                        logger.debug(f"File {file_path} modified, reloading cog")
                        
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
        
        # Sync all global commands with smart optimization
        logger.info("Starting global command synchronization")
        
        try:
            # Get current commands from loaded cogs
            current_commands = bot.tree.get_commands()
            logger.debug(f"Found {len(current_commands)} local commands")
            
            if not current_commands:
                logger.warning("No commands found to sync")
                return
            
            # Ultra-fast sync detection using command hashing
            needs_sync = True
            current_hash = commands_hash(current_commands)
            
            try:
                # Try to get existing commands for comparison
                existing_commands = await bot.tree.fetch_commands()
                if existing_commands:
                    existing_hash = commands_hash(existing_commands)
                    
                    if current_hash == existing_hash:
                        needs_sync = False
                        logger.info(f"🚀 FAST SYNC: No changes detected - skipping sync ({len(current_commands)} commands)")
                        logger.info("🌍 All commands already up-to-date globally!")
                        
                        # Still log available commands for verification
                        for cmd in current_commands:
                            logger.info(f"Global command available: {cmd.name}")
                
            except Exception as fetch_error:
                logger.debug(f"Could not fetch existing commands for comparison: {fetch_error}")
                # Fall back to full sync for safety
            
            if needs_sync:
                logger.info("📤 Command changes detected - performing sync...")
                start_time = asyncio.get_event_loop().time()
                
                global_synced = await bot.tree.sync()
                
                sync_time = asyncio.get_event_loop().time() - start_time
                logger.info(f"✅ Successfully synced {len(global_synced)} global commands in {sync_time:.2f}s")
                logger.info("🌍 ALL COMMANDS are now available in EVERY server the bot joins!")
                
                # Log each synced global command
                for cmd in global_synced:
                    logger.info(f"Global command available: {cmd.name}")
            
        except discord.HTTPException as http_error:
            logger.error(f"HTTP error syncing global commands: {http_error}")
            if http_error.status == 429:  # Rate limited
                logger.error("Rate limited! Consider using the smart sync to reduce API calls.")
        except Exception as sync_error:
            logger.error(f"Error syncing global commands: {sync_error}", exc_info=True)
        
        # Start background tasks
        logger.info("Starting background tasks")
        
        try:
            logger.debug("Creating streaming status updater task")
            bot.loop.create_task(update_streaming_status())
            logger.info("✅ Streaming status updater started")
        except Exception as status_task_error:
            logger.error(f"Failed to start streaming status updater: {status_task_error}")
        
        try:
            logger.debug("Running initial user cleanup")
            await cleanup_stale_users()
            logger.info("✅ Initial user cleanup completed")
            
            logger.debug("Running initial guild cleanup")
            await cleanup_left_guilds()
            logger.info("✅ Initial guild cleanup completed")
            
            logger.debug("Creating user cleanup scheduler task")
            bot.loop.create_task(schedule_user_cleanup())
            logger.info("✅ User cleanup scheduler started")
            
            logger.debug("Creating guild cleanup scheduler task")
            bot.loop.create_task(schedule_guild_cleanup())
            logger.info("✅ Guild cleanup scheduler started")
        except Exception as cleanup_task_error:
            logger.error(f"Failed to start cleanup tasks: {cleanup_task_error}")
        
        logger.info("Bot initialization completed successfully")
        logger.info("="*60)

        # Send webhook notification for bot ready
        await webhook_notifier.notify('bot_ready', {
            'bot_user': str(bot.user),
            'bot_id': bot.user.id,
            'guilds': len(bot.guilds),
            'latency_ms': round(bot.latency * 1000, 2),
            'uptime': get_uptime()
        }, priority='info')

    except Exception as e:
        logger.error(f"Error in on_ready event: {e}", exc_info=True)
        # Send error webhook
        await webhook_notifier.notify('error_occurred', {
            'event': 'on_ready',
            'error': str(e),
            'error_type': type(e).__name__
        }, priority='critical')

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

    # Send webhook notification
    await webhook_notifier.notify('guild_joined', {
        'guild_name': guild.name,
        'guild_id': guild.id,
        'member_count': guild.member_count,
        'owner': str(guild.owner) if guild.owner else 'Unknown',
        'created_at': guild.created_at.isoformat(),
        'total_guilds': len(bot.guilds)
    }, priority='info')

    # Update server log when joining new server
    try:
        await log_server_information()
    except Exception as e:
        logger.error(f"Error updating server log after guild join: {e}")

@bot.event
async def on_guild_remove(guild):
    """
    Handle bot removal from a server.
    Immediately cleans up all guild-related data from the database.
    """
    logger.info(f"👋 Bot removed from server: {guild.name} (ID: {guild.id})")

    # Immediately clean up all guild data
    try:
        logger.info(f"Starting immediate cleanup for guild {guild.id}")
        success, deleted_counts = await clear_guild_records(guild.id)

        if success:
            total_deleted = sum(deleted_counts.values())
            logger.info(f"✅ Successfully cleaned up guild {guild.id}: {total_deleted} records deleted")
            logger.info(f"   Breakdown: {deleted_counts}")
        else:
            logger.error(f"❌ Failed to clean up guild {guild.id}")

    except Exception as cleanup_error:
        logger.error(f"Error cleaning up guild {guild.id}: {cleanup_error}", exc_info=True)

    # Send webhook notification
    await webhook_notifier.notify('guild_removed', {
        'guild_name': guild.name,
        'guild_id': guild.id,
        'records_deleted': total_deleted if success else 0,
        'cleanup_success': success,
        'remaining_guilds': len(bot.guilds)
    }, priority='warning')

    # Update server log when leaving server
    try:
        await log_server_information()
    except Exception as e:
        logger.error(f"Error updating server log after guild remove: {e}")


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

            # Initialize database connection pool
            global db_pool
            db_pool = DatabaseConnectionPool(db_path="data/database.db", pool_size=DB_CONNECTION_POOL_SIZE)
            await db_pool.initialize()

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

        # Send shutdown webhook
        await webhook_notifier.notify('bot_shutdown', {
            'uptime': get_uptime(),
            'reason': 'Normal shutdown'
        }, priority='info')

        # Close database pool
        if db_pool and db_pool.initialized:
            logger.debug("Closing database connection pool...")
            await db_pool.close()

        # Close bot connection
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
