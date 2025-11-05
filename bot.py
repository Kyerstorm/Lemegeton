# bot.py
import sys
import os
import asyncio
import logging
import time
import warnings
import aiohttp
import discord
from discord.ext import commands
import config

# Suppress deprecation warning from discord.py's internal WebSocket connection code
# This is a known issue in discord.py 2.6.0 that will be fixed in future versions
warnings.filterwarnings("ignore", category=DeprecationWarning, message=".*parameter 'timeout' of type 'float' is deprecated.*")
from database import init_db, get_all_users_guild_aware, remove_user, clear_guild_records, get_all_guild_ids_with_records
import signal
import random
from typing import Optional, Dict, List
from datetime import datetime

# Add project root to sys.path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

import hashlib
import json
from collections import deque

# ------------------------------------------------------
# Logging Setup
# ------------------------------------------------------
# Configuration constants
LOG_DIR = "logs"
LOG_FILE = "bot.log"
# Adjust cog watch interval based on environment
COG_WATCH_INTERVAL = config.COG_WATCH_INTERVAL_PROD if os.getenv("ENVIRONMENT") == "production" else config.COG_WATCH_INTERVAL_DEV

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


class CircuitBreaker:
    """Circuit breaker pattern for API resilience"""

    def __init__(self, failure_threshold: int = 5, timeout: int = 60, success_threshold: int = 2):
        self.failure_threshold = failure_threshold
        self.timeout = timeout
        self.success_threshold = success_threshold
        self.failure_count = 0
        self.success_count = 0
        self.last_failure_time: Optional[float] = None
        self.state = "closed"  # closed, open, half_open
        self.logger = logging.getLogger("CircuitBreaker")

    def can_execute(self) -> bool:
        """Check if execution is allowed"""
        if self.state == "closed":
            return True

        if self.state == "open":
            # Check if timeout has passed
            if self.last_failure_time and (time.time() - self.last_failure_time) >= self.timeout:
                self.state = "half_open"
                self.success_count = 0
                self.logger.info("Circuit breaker entering half-open state")
                return True
            return False

        # half_open state
        return True

    def record_success(self) -> None:
        """Record successful execution"""
        if self.state == "half_open":
            self.success_count += 1
            if self.success_count >= self.success_threshold:
                self.state = "closed"
                self.failure_count = 0
                self.logger.info("Circuit breaker closed after successful recovery")
        else:
            self.failure_count = max(0, self.failure_count - 1)

    def record_failure(self) -> None:
        """Record failed execution"""
        self.failure_count += 1
        self.last_failure_time = time.time()

        if self.failure_count >= self.failure_threshold:
            self.state = "open"
            self.logger.warning(f"Circuit breaker opened after {self.failure_count} failures")


class WebhookNotifier:
    """Send notifications to external webhooks for monitoring and alerts with rate limiting"""

    def __init__(self, webhook_urls: Optional[Dict[str, str]] = None, rate_limit: int = 5):
        self.webhook_urls = webhook_urls or {}
        self.logger = logging.getLogger("WebhookNotifier")
        self.enabled = bool(webhook_urls)
        self.rate_limit = rate_limit  # Max webhooks per minute
        self.webhook_times: deque = deque(maxlen=rate_limit)

        if self.enabled:
            self.logger.info(f"✅ Webhook notifier initialized with {len(webhook_urls)} endpoints (rate limit: {rate_limit}/min)")
        else:
            self.logger.debug("Webhook notifier initialized but no endpoints configured")

    def _check_rate_limit(self) -> bool:
        """Check if we're within rate limit"""
        now = time.time()
        # Remove timestamps older than 1 minute
        while self.webhook_times and (now - self.webhook_times[0]) > 60:
            self.webhook_times.popleft()

        return len(self.webhook_times) < self.rate_limit

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
        Send webhook notification for an event with rate limiting.

        Args:
            event_type: Type of event (e.g., 'bot_ready', 'error_occurred')
            data: Event data to send
            priority: Priority level ('info', 'warning', 'critical')
        """
        if not self.enabled:
            self.logger.debug(f"Webhook skipped (disabled): {event_type}")
            return

        # Check rate limit
        if not self._check_rate_limit():
            self.logger.warning(f"Webhook rate limit exceeded, skipping event: {event_type}")
            return

        webhook_url = self.webhook_urls.get(event_type)
        if not webhook_url:
            self.logger.debug(f"No webhook configured for event: {event_type}")
            return

        try:
            # Record webhook send time
            self.webhook_times.append(time.time())
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
            if config.ADMIN_DISCORD_ID:
                try:
                    admin_user = await self.bot.fetch_user(config.ADMIN_DISCORD_ID)
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


# Initialize utility instances (will be populated after bot creation)
api_retry_handler = APIRetryHandler(max_retries=config.API_MAX_RETRIES, base_delay=config.API_RETRY_BASE_DELAY)
anilist_circuit_breaker = CircuitBreaker(
    failure_threshold=config.CIRCUIT_BREAKER_FAILURE_THRESHOLD,
    timeout=config.CIRCUIT_BREAKER_TIMEOUT,
    success_threshold=config.CIRCUIT_BREAKER_SUCCESS_THRESHOLD
)
webhook_notifier = None  # Initialized later with config
shutdown_handler = None  # Initialized after bot creation
background_tasks: List[asyncio.Task] = []  # Track all background tasks for proper cleanup

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

bot = commands.Bot(command_prefix="!", intents=intents, application_id=config.BOT_ID)

# Initialize webhook notifier with Discord webhook from config
WEBHOOK_URLS = {
    'bot_ready': config.DISCORD_WEBHOOK_URL,
    'bot_shutdown': config.DISCORD_WEBHOOK_URL,
    'error_occurred': config.DISCORD_WEBHOOK_URL,
    'guild_joined': config.DISCORD_WEBHOOK_URL,
    'guild_removed': config.DISCORD_WEBHOOK_URL,
} if config.DISCORD_WEBHOOK_URL else {}
webhook_notifier = WebhookNotifier(WEBHOOK_URLS, rate_limit=config.WEBHOOK_RATE_LIMIT)

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

async def _fetch_trending_anime_internal() -> List[str]:
    """
    Internal function to fetch trending anime from AniList API with circuit breaker.
    This is wrapped by fetch_trending_anime_list for retry logic.

    Returns:
        List of anime titles or fallback list if API fails
    """
    # Check circuit breaker
    if not anilist_circuit_breaker.can_execute():
        logger.warning("AniList API circuit breaker is open, using fallback")
        return config.DEFAULT_TRENDING_FALLBACK

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
        logger.debug(f"Making request to AniList API: {config.ANILIST_API_URL}")

        timeout = aiohttp.ClientTimeout(total=config.ANILIST_API_TIMEOUT)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            start_time = time.time()
            
            async with session.post(
                config.ANILIST_API_URL,
                json={"query": query},
                headers={'Content-Type': 'application/json'}
            ) as response:

                response_time = time.time() - start_time
                logger.debug(f"AniList API response received in {response_time:.2f}s - Status: {response.status}")

                if response.status != 200:
                    logger.error(f"AniList API request failed with status {response.status}")
                    logger.debug(f"Response headers: {dict(response.headers)}")
                    anilist_circuit_breaker.record_failure()
                    return config.DEFAULT_TRENDING_FALLBACK
                
                try:
                    data = await response.json()
                    logger.debug("Successfully parsed JSON response")
                except Exception as json_error:
                    logger.error(f"Failed to parse JSON response: {json_error}")
                    anilist_circuit_breaker.record_failure()
                    return config.DEFAULT_TRENDING_FALLBACK

                # Validate response structure
                if not isinstance(data, dict) or 'data' not in data:
                    logger.error(f"Invalid response structure: missing 'data' field")
                    anilist_circuit_breaker.record_failure()
                    return config.DEFAULT_TRENDING_FALLBACK

                if 'Page' not in data['data'] or 'media' not in data['data']['Page']:
                    logger.error("Invalid response structure: missing Page.media")
                    anilist_circuit_breaker.record_failure()
                    return config.DEFAULT_TRENDING_FALLBACK
                
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
                    anilist_circuit_breaker.record_success()
                    return processed_titles
                else:
                    logger.warning("No valid anime titles found, using fallback")
                    anilist_circuit_breaker.record_failure()
                    return config.DEFAULT_TRENDING_FALLBACK

    except (aiohttp.ClientTimeout, aiohttp.ClientError) as e:
        # Re-raise for retry handler
        anilist_circuit_breaker.record_failure()
        raise
    except Exception as e:
        logger.error(f"Unexpected error fetching trending anime: {e}", exc_info=True)
        anilist_circuit_breaker.record_failure()
        # Don't retry unexpected errors
        return config.DEFAULT_TRENDING_FALLBACK


async def fetch_trending_anime_list() -> List[str]:
    """
    Fetch trending anime list from AniList API with retry logic and circuit breaker.

    Returns:
        List of anime titles or fallback list if API fails
    """
    logger.debug("Starting AniList trending anime fetch with retry logic")

    try:
        # Use retry handler for resilient API calls
        result = await api_retry_handler.retry_with_backoff(_fetch_trending_anime_internal)
        return result
    except Exception as e:
        logger.error(f"All retry attempts exhausted for trending anime fetch: {e}")
        return config.DEFAULT_TRENDING_FALLBACK


# ------------------------------------------------------
# User Cleanup Task (Enhanced with chunking and batching)
# ------------------------------------------------------

async def get_guild_members_set(guild: discord.Guild) -> set[int]:
    """
    Get all member IDs from a guild, ensuring complete member list by chunking if needed.

    Args:
        guild: The Discord guild to get members from

    Returns:
        Set of member IDs for fast lookup
    """
    try:
        # Ensure we have the latest member list by chunking if needed
        if not guild.chunked:
            logger.debug(f"Chunking guild {guild.name} to get complete member list")
            await guild.chunk(cache=True)
        
        member_ids = {member.id for member in guild.members}
        logger.debug(f"Guild {guild.name} has {len(member_ids)} members")
        return member_ids
        
    except Exception as e:
        logger.error(f"Failed to get members for guild {guild.name} ({guild.id}): {e}", exc_info=True)
        return set()

async def cleanup_stale_users() -> Dict[str, int]:
    """
    Clean up user records for users who are no longer in their registered guilds.
    Enhanced with chunking, batching, detailed statistics, and timeout protection.
    Runs on startup and every USER_CLEANUP_INTERVAL to maintain database integrity.

    Returns:
        Dict with statistics: {'checked': int, 'removed': int, 'errors': int, 'guilds_processed': int}
    """
    logger.info("🧹 Starting user cleanup task (enhanced)")

    try:
        # Apply timeout to prevent cleanup from running too long
        return await asyncio.wait_for(_cleanup_stale_users_impl(), timeout=config.CLEANUP_TIMEOUT)
    except asyncio.TimeoutError:
        logger.error(f"❌ User cleanup timed out after {config.CLEANUP_TIMEOUT} seconds")
        return {'checked': 0, 'removed': 0, 'errors': 1, 'guilds_processed': 0}


async def _cleanup_stale_users_impl():
    
    stats = {
        'checked': 0,
        'removed': 0,
        'errors': 0,
        'guilds_processed': 0
    }

    try:
        for guild in bot.guilds:
            logger.debug(f"Checking guild: {guild.name} (ID: {guild.id})")

            try:
                # Get all users registered in this guild
                guild_users = await get_all_users_guild_aware(guild.id)

                if not guild_users:
                    logger.debug(f"No registered users in guild {guild.name}")
                    continue

                logger.debug(f"Found {len(guild_users)} registered users in guild {guild.name}")
                
                # Get complete member list with chunking
                current_members = await get_guild_members_set(guild)
                
                if not current_members:
                    logger.warning(f"No members found for guild {guild.name} - skipping cleanup")
                    continue
                
                # Process users in batches to avoid blocking
                for i in range(0, len(guild_users), config.CLEANUP_BATCH_SIZE):
                    batch = guild_users[i:i + config.CLEANUP_BATCH_SIZE]
                    logger.debug(f"Processing batch {i//config.CLEANUP_BATCH_SIZE + 1} ({len(batch)} users) for guild {guild.name}")

                    for user_data in batch:
                        stats['checked'] += 1
                        discord_id = user_data[1]  # discord_id is at index 1
                        username = user_data[3] if len(user_data) > 3 else f"User {discord_id}"  # username is at index 3

                        try:
                            # Check if user is still in the guild (fast set lookup)
                            if discord_id not in current_members:
                                # User not found in guild, remove their records
                                logger.info(f"👻 Removing stale user record: {username} (ID: {discord_id}) from guild {guild.name}")
                                success = await remove_user(discord_id, guild.id)
                                if success:
                                    stats['removed'] += 1
                                    logger.info(f"🗑️ Successfully removed records for user {username} from guild {guild.name}")
                                else:
                                    stats['errors'] += 1
                                    logger.warning(f"Failed to remove records for user {username} from guild {guild.name}")

                        except Exception as user_error:
                            stats['errors'] += 1
                            logger.error(f"Error processing user {discord_id} in guild {guild.id}: {user_error}", exc_info=True)
                    
                    # Small delay between batches to avoid blocking
                    if i + config.CLEANUP_BATCH_SIZE < len(guild_users):
                        await asyncio.sleep(config.CLEANUP_BATCH_DELAY)
                
                stats['guilds_processed'] += 1
                logger.info(f"🏁 Cleanup completed for guild {guild.name}: "
                           f"checked={stats['checked']}, removed={stats['removed']}, errors={stats['errors']}")

            except Exception as guild_error:
                stats['errors'] += 1
                logger.error(f"Error processing guild {guild.id}: {guild_error}", exc_info=True)

        # Summary logging
        if stats['removed'] > 0:
            logger.info(f"✅ User cleanup completed: removed {stats['removed']} stale user records "
                       f"from {stats['guilds_processed']} guilds (checked {stats['checked']} users, {stats['errors']} errors)")
        else:
            logger.info(f"✨ User cleanup completed: no stale records found "
                       f"({stats['checked']} users checked across {stats['guilds_processed']} guilds)")

    except Exception as e:
        logger.error(f"Fatal error in user cleanup task: {e}", exc_info=True)
        stats['errors'] += 1
    
    return stats

async def schedule_user_cleanup():
    """
    Schedule user cleanup to run at configured interval.
    Enhanced with better error handling and statistics reporting.
    """
    logger.info(f"Starting user cleanup scheduler (runs every {config.USER_CLEANUP_INTERVAL/3600:.1f} hours)")

    try:
        while not bot.is_closed():
            # Wait for configured interval
            await asyncio.sleep(config.USER_CLEANUP_INTERVAL)
            
            try:
                logger.info("⏰ Running scheduled user cleanup")
                stats = await cleanup_stale_users()
                
                # Log summary
                if stats['removed'] > 0:
                    logger.info(f"🧹 Scheduled cleanup summary: Removed {stats['removed']} inactive users "
                               f"from {stats['guilds_processed']} guilds")
                else:
                    logger.info("✨ Scheduled cleanup: No inactive users found - database is clean!")
                    
            except Exception as cleanup_error:
                logger.error(f"Error in scheduled user cleanup: {cleanup_error}", exc_info=True)
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
    logger.info(f"Starting guild cleanup scheduler (runs every {config.GUILD_CLEANUP_INTERVAL/3600:.1f} hours)")

    try:
        while not bot.is_closed():
            # Wait for configured interval
            await asyncio.sleep(config.GUILD_CLEANUP_INTERVAL)
            
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
                template = random.choice(config.STATUS_TEMPLATES)
                status_text = template.format(anime=anime_title)

                logger.debug(f"Setting streaming status ({index+1}/{len(trending)}): {status_text}")

                # Create and set streaming activity
                stream = discord.Streaming(
                    name=status_text,
                    url=config.TWITCH_STREAMING_URL
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
                if time_since_refresh >= config.TRENDING_REFRESH_INTERVAL:
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
                logger.debug(f"Waiting {config.STATUS_UPDATE_INTERVAL}s before next status update")
                await asyncio.sleep(config.STATUS_UPDATE_INTERVAL)
                
            except discord.HTTPException as http_error:
                logger.error(f"Discord HTTP error updating status: {http_error}")
                await asyncio.sleep(config.STATUS_UPDATE_INTERVAL * 2)  # Wait longer on HTTP errors
            except Exception as status_error:
                logger.error(f"Unexpected error in status update loop: {status_error}", exc_info=True)
                await asyncio.sleep(config.STATUS_UPDATE_INTERVAL)
                
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
    try:
        async with asyncio.timeout(config.COG_LOAD_TIMEOUT):
            async with cog_loading_semaphore:
                logger.debug("Acquired cog loading semaphore")
                try:
                    await _load_cogs_impl()
                finally:
                    logger.debug("Released cog loading semaphore")
    except asyncio.TimeoutError:
        logger.error(f"❌ Cog loading timed out after {config.COG_LOAD_TIMEOUT} seconds")

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
        
        # Start background tasks with tracking
        logger.info("Starting background tasks")

        try:
            logger.debug("Creating streaming status updater task")
            task = bot.loop.create_task(update_streaming_status())
            background_tasks.append(task)
            logger.info("✅ Streaming status updater started")
        except Exception as status_task_error:
            logger.error(f"Failed to start streaming status updater: {status_task_error}")

        try:
            logger.debug("Running initial user cleanup on startup")
            startup_stats = await cleanup_stale_users()
            if startup_stats['removed'] > 0:
                logger.info(f"✅ Initial user cleanup completed: removed {startup_stats['removed']} stale records")
            else:
                logger.info("✅ Initial user cleanup completed: no stale records found")

            logger.debug("Running initial guild cleanup")
            await cleanup_left_guilds()
            logger.info("✅ Initial guild cleanup completed")

            logger.debug("Creating user cleanup scheduler task")
            task = bot.loop.create_task(schedule_user_cleanup())
            background_tasks.append(task)
            logger.info("✅ User cleanup scheduler started")

            logger.debug("Creating guild cleanup scheduler task")
            task = bot.loop.create_task(schedule_guild_cleanup())
            background_tasks.append(task)
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

    # Initialize variables in case cleanup fails
    success = False
    total_deleted = 0

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
        'records_deleted': total_deleted,
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
        # Validate configuration FIRST for fail-fast behavior
        logger.info("Validating configuration...")
        is_valid, missing_vars = config.validate_required_config()
        if not is_valid:
            logger.error(f"❌ Configuration validation failed. Missing variables: {', '.join(missing_vars)}")
            raise ValueError(f"Required configuration missing: {', '.join(missing_vars)}")

        logger.info("✅ Configuration validation passed")
        config_summary = config.get_config_summary()
        logger.info(f"Configuration summary: {config_summary}")

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
            task = asyncio.create_task(watch_cogs())
            background_tasks.append(task)
            logger.info("✅ Cog watcher started")
        except Exception as watcher_error:
            logger.error(f"❌ Cog watcher failed to start: {watcher_error}", exc_info=True)
            # Continue without watcher

        # Start the bot with comprehensive logging
        logger.info("Starting Discord bot connection...")
        logger.info(f"Bot ID: {config.BOT_ID}")
        logger.info(f"Target Guild: {config.GUILD_ID}")
        logger.info("="*60)

        try:
            await bot.start(config.TOKEN)
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
        try:
            await webhook_notifier.notify('bot_shutdown', {
                'uptime': get_uptime(),
                'reason': 'Normal shutdown'
            }, priority='info')
        except Exception as webhook_error:
            logger.warning(f"Failed to send shutdown webhook: {webhook_error}")

        # Cancel all background tasks
        logger.info(f"Cancelling {len(background_tasks)} background tasks...")
        for task in background_tasks:
            if not task.done():
                task.cancel()

        # Wait for tasks to complete cancellation
        if background_tasks:
            await asyncio.gather(*background_tasks, return_exceptions=True)
            logger.info("✅ All background tasks cancelled")

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