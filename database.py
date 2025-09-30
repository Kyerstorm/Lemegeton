import aiosqlite
from pathlib import Path
import aiohttp
import asyncio
import logging
import os
import time
from typing import List, Dict, Optional
from datetime import datetime
import config

# ------------------------------------------------------
# Logging Setup with File-based System
# ------------------------------------------------------
# Configuration constants
LOG_DIR = "logs"
LOG_FILE = "database.log"
LOG_MAX_SIZE = 50 * 1024 * 1024  # 50MB max log file size
DB_TIMEOUT = 30.0  # Database operation timeout in seconds
CONNECTION_RETRIES = 3  # Number of retry attempts for database connections
RETRY_DELAY = 1.0  # Delay between retries in seconds

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

# Configure logger
logger = logging.getLogger("Database")
logger.setLevel(logging.DEBUG)
logger.handlers.clear()  # Remove any existing handlers
logger.addHandler(file_handler)
logger.addHandler(console_handler)

# Prevent propagation to avoid duplicate logs
logger.propagate = False

logger.info("="*50)
logger.info("Database logging system initialized")
logger.info(f"Log file: {log_file_path}")
logger.info("="*50)

# ------------------------------------------------------
# Database Configuration with Enhanced Connection Management
# ------------------------------------------------------
DB_PATH = Path(config.DB_PATH).resolve()

logger.info(f"Database configuration initialized")
logger.info(f"Database file path: {DB_PATH}")
logger.info(f"Database file exists: {DB_PATH.exists()}")
if DB_PATH.exists():
    file_size = DB_PATH.stat().st_size
    logger.info(f"Database file size: {file_size:,} bytes ({file_size / (1024*1024):.2f} MB)")

async def get_db_connection():
    """
    Get database connection with comprehensive logging and retry logic.
    """
    for attempt in range(CONNECTION_RETRIES):
        try:
            logger.debug(f"Attempting database connection (attempt {attempt + 1}/{CONNECTION_RETRIES})")
            
            # Create a new connection each time to avoid thread reuse issues
            connection = aiosqlite.connect(
                DB_PATH, 
                timeout=DB_TIMEOUT,
                check_same_thread=False
            )
            
            # Don't await here - let the caller handle the async context
            logger.debug(f"Database connection object created successfully")
            return connection
            
        except Exception as e:
            logger.error(f"Database connection attempt {attempt + 1} failed: {e}")
            if attempt < CONNECTION_RETRIES - 1:
                logger.debug(f"Retrying in {RETRY_DELAY} seconds...")
                await asyncio.sleep(RETRY_DELAY)
            else:
                logger.error(f"All database connection attempts failed")
                raise

async def execute_db_operation(operation_name: str, query: str, params=None, fetch_type=None):
    """
    Execute database operation with comprehensive logging and error handling.
    
    Args:
        operation_name: Human-readable name for the operation
        query: SQL query to execute
        params: Query parameters
        fetch_type: 'one', 'all', or None for no fetch
    """
    logger.debug(f"Executing {operation_name}")
    logger.debug(f"Query: {query}")
    if params:
        logger.debug(f"Parameters: {params}")
    
    start_time = time.time()
    
    try:
        # Use direct aiosqlite.connect instead of the helper to avoid connection reuse issues
        async with aiosqlite.connect(DB_PATH, timeout=DB_TIMEOUT) as db:
            # Enable foreign key constraints
            await db.execute("PRAGMA foreign_keys = ON")
            
            cursor = await db.execute(query, params or ())
            
            result = None
            if fetch_type == 'one':
                result = await cursor.fetchone()
            elif fetch_type == 'all':
                result = await cursor.fetchall()
            elif fetch_type == 'lastrowid':
                result = cursor.lastrowid
            
            await cursor.close()
            await db.commit()
            
            execution_time = time.time() - start_time
            logger.debug(f"{operation_name} completed in {execution_time:.3f}s")
            
            if result is not None:
                if fetch_type == 'one':
                    logger.debug(f"Query returned 1 row")
                elif fetch_type == 'all':
                    logger.debug(f"Query returned {len(result)} rows")
                elif fetch_type == 'lastrowid':
                    logger.debug(f"Last inserted row ID: {result}")
            
            return result
            
    except aiosqlite.Error as db_error:
        execution_time = time.time() - start_time
        logger.error(f"{operation_name} failed after {execution_time:.3f}s: {db_error}")
        raise
    except Exception as e:
        execution_time = time.time() - start_time
        logger.error(f"Unexpected error in {operation_name} after {execution_time:.3f}s: {e}", exc_info=True)
        raise

# ------------------------------------------------------
# USERS TABLE FUNCTIONS with Enhanced Logging
# ------------------------------------------------------

async def migrate_to_multi_guild_schema():
    """Migrate the users table to support multi-guild by removing UNIQUE constraint on discord_id."""
    logger.info("🔄 Starting migration to multi-guild schema")
    
    try:
        # SQLite doesn't support dropping constraints, so we need to recreate the table
        # 1. Create new table with correct schema
        new_table_query = """
            CREATE TABLE users_new (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                discord_id INTEGER NOT NULL,
                guild_id INTEGER NOT NULL,
                username TEXT NOT NULL,
                anilist_username TEXT,
                anilist_id INTEGER,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(discord_id, guild_id)
            )
        """
        await execute_db_operation("create new users table", new_table_query)
        
        # 2. Copy data from old table to new table
        # Use environment variable for default guild ID
        default_guild_id = os.getenv("GUILD_ID", "897814031346319382")
        copy_query = """
            INSERT INTO users_new (id, discord_id, guild_id, username, anilist_username, anilist_id, created_at, updated_at)
            SELECT id, discord_id, COALESCE(guild_id, ?), username, anilist_username, anilist_id, created_at, updated_at
            FROM users
        """
        await execute_db_operation("copy data to new users table", copy_query, (default_guild_id,))
        
        # 3. Drop old table
        await execute_db_operation("drop old users table", "DROP TABLE users")
        
        # 4. Rename new table to original name
        await execute_db_operation("rename new users table", "ALTER TABLE users_new RENAME TO users")
        
        logger.info("✅ Successfully migrated to multi-guild schema")
        
    except Exception as e:
        logger.error(f"❌ Failed to migrate to multi-guild schema: {e}", exc_info=True)
        # Try to clean up any partial migration
        try:
            await execute_db_operation("cleanup failed migration", "DROP TABLE IF EXISTS users_new")
        except:
            pass
        raise

async def init_users_table():
    """Initialize users table with comprehensive logging and error handling."""
    logger.info("Initializing users table")
    
    try:
        create_query = """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                discord_id INTEGER UNIQUE NOT NULL,
                username TEXT NOT NULL,
                anilist_username TEXT,
                anilist_id INTEGER,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """
        
        await execute_db_operation("users table creation", create_query)
        
        # Add missing columns if they don't exist
        columns_to_add = [
            ("anilist_username", "TEXT"),
            ("anilist_id", "INTEGER"),
            ("guild_id", "INTEGER"),
            ("created_at", "DATETIME DEFAULT CURRENT_TIMESTAMP"),
            ("updated_at", "DATETIME DEFAULT CURRENT_TIMESTAMP")
        ]
        
        for column_name, column_type in columns_to_add:
            try:
                alter_query = f"ALTER TABLE users ADD COLUMN {column_name} {column_type}"
                await execute_db_operation(f"add {column_name} column to users", alter_query)
                logger.debug(f"Added missing column '{column_name}' to users table")
            except aiosqlite.OperationalError as e:
                if "duplicate column name" in str(e).lower():
                    logger.debug(f"Column '{column_name}' already exists in users table")
                else:
                    logger.warning(f"Error adding column '{column_name}' to users table: {e}")
        
        # Verify table structure
        schema_query = "PRAGMA table_info(users)"
        schema = await execute_db_operation("users table schema check", schema_query, fetch_type='all')
        logger.debug(f"Users table schema: {len(schema)} columns")
        for column in schema:
            logger.debug(f"  Column: {column[1]} ({column[2]})")
        
        # Check if we need to migrate to multi-guild support
        # The original table has UNIQUE constraint on discord_id, but for multi-guild we need to allow duplicates
        try:
            # Check if guild_id column exists and if we have multi-guild data
            has_guild_id = any(col[1] == 'guild_id' for col in schema)
            if has_guild_id:
                # Check if we have any users with guild_id (new schema)
                check_query = "SELECT COUNT(*) FROM users WHERE guild_id IS NOT NULL"
                count_result = await execute_db_operation("check guild_id usage", check_query, fetch_type='one')
                has_guild_data = count_result[0] > 0 if count_result else False
                
                if not has_guild_data:
                    # Migrate existing users to use default guild_id from environment
                    default_guild_id = os.getenv("GUILD_ID", "897814031346319382")
                    migrate_query = "UPDATE users SET guild_id = ? WHERE guild_id IS NULL"
                    await execute_db_operation("migrate existing users to default guild", migrate_query, (default_guild_id,))
                    logger.info(f"✅ Migrated existing users to default guild ID: {default_guild_id}")
                
                # Remove the UNIQUE constraint on discord_id to allow multi-guild support
                # SQLite doesn't support dropping constraints directly, so we need to recreate the table
                # But only if we still have the old constraint
                try:
                    # Test if we can insert duplicate discord_id (different guild_id)
                    test_discord_id = 999999999999999999  # Unlikely to exist
                    test_guild_id_1 = 1
                    test_guild_id_2 = 2
                    
                    # Try to insert two records with same discord_id but different guild_id
                    test_query = "INSERT INTO users (discord_id, guild_id, username) VALUES (?, ?, ?)"
                    await execute_db_operation("test multi-guild insert 1", test_query, (test_discord_id, test_guild_id_1, "test1"))
                    await execute_db_operation("test multi-guild insert 2", test_query, (test_discord_id, test_guild_id_2, "test2"))
                    
                    # Clean up test data
                    cleanup_query = "DELETE FROM users WHERE discord_id = ?"
                    await execute_db_operation("cleanup test data", cleanup_query, (test_discord_id,))
                    
                    logger.info("✅ Multi-guild support confirmed - table supports multiple guilds per user")
                    
                except aiosqlite.IntegrityError as e:
                    if "UNIQUE constraint failed" in str(e):
                        logger.warning("🔄 Table still has UNIQUE constraint on discord_id - migration needed")
                        await migrate_to_multi_guild_schema()
                    else:
                        logger.error(f"Unexpected integrity error during multi-guild test: {e}")
                except Exception as e:
                    logger.debug(f"Multi-guild test failed (may be normal): {e}")
                    
        except Exception as e:
            logger.error(f"Error during multi-guild migration check: {e}", exc_info=True)
        
        logger.info("✅ Users table initialization completed successfully")
        
    except Exception as e:
        logger.error(f"❌ Failed to initialize users table: {e}", exc_info=True)
        raise

async def add_user(discord_id: int, username: str, anilist_username: str = None, anilist_id: int = None):
    """Add new user with comprehensive logging and validation. (DEPRECATED: Use add_user_guild_aware instead)"""
    logger.warning("Using deprecated add_user function. Consider using add_user_guild_aware for multi-guild support")
    
    try:
        # Validate input
        if not isinstance(discord_id, int) or discord_id <= 0:
            raise ValueError(f"Invalid discord_id: {discord_id}")
        if not isinstance(username, str) or not username.strip():
            raise ValueError(f"Invalid username: {username}")
        
        logger.debug(f"User data - Discord ID: {discord_id}, Username: {username}")
        if anilist_username:
            logger.debug(f"AniList data - Username: {anilist_username}, ID: {anilist_id}")
        
        # For backwards compatibility, use a default guild_id (your current server)
        # This should be updated to use actual guild_id in all calling code
        default_guild_id = 897814031346319382
        
        query = """
            INSERT OR REPLACE INTO users (discord_id, guild_id, username, anilist_username, anilist_id, updated_at)
            VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        """
        
        await execute_db_operation(
            f"add user {username}",
            query,
            (discord_id, default_guild_id, username.strip(), anilist_username, anilist_id)
        )
        
        logger.info(f"✅ Successfully added user {username} (Discord ID: {discord_id}) to default guild")
        
    except aiosqlite.IntegrityError as integrity_error:
        if "UNIQUE constraint failed" in str(integrity_error):
            logger.warning(f"User {discord_id} already exists, cannot add duplicate")
        else:
            logger.error(f"Database integrity error adding user {discord_id}: {integrity_error}")
        raise
    except ValueError as validation_error:
        logger.error(f"Validation error adding user: {validation_error}")
        raise
    except Exception as e:
        logger.error(f"❌ Unexpected error adding user {discord_id}: {e}", exc_info=True)
        raise


async def add_user_guild_aware(discord_id: int, guild_id: int, username: str, anilist_username: str = None, anilist_id: int = None):
    """Add new user or update existing user with guild context for multi-server support."""
    logger.info(f"Upserting user: {username} (Discord ID: {discord_id}) to guild {guild_id}")
    
    try:
        # Validate input
        if not isinstance(discord_id, int) or discord_id <= 0:
            raise ValueError(f"Invalid discord_id: {discord_id}")
        if not isinstance(guild_id, int) or guild_id <= 0:
            raise ValueError(f"Invalid guild_id: {guild_id}")
        if not isinstance(username, str) or not username.strip():
            raise ValueError(f"Invalid username: {username}")
        
        logger.debug(f"User data - Discord ID: {discord_id}, Guild ID: {guild_id}, Username: {username}")
        if anilist_username:
            logger.debug(f"AniList data - Username: {anilist_username}, ID: {anilist_id}")
        
        query = """
            INSERT INTO users (discord_id, guild_id, username, anilist_username, anilist_id, updated_at)
            VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(discord_id, guild_id) DO UPDATE SET 
                username=excluded.username,
                anilist_username=excluded.anilist_username,
                anilist_id=excluded.anilist_id,
                updated_at=CURRENT_TIMESTAMP
        """
        
        await execute_db_operation(
            f"upsert user {username} to guild {guild_id}",
            query,
            (discord_id, guild_id, username.strip(), anilist_username, anilist_id)
        )
        
        logger.info(f"✅ Successfully upserted user {username} (Discord ID: {discord_id}) to guild {guild_id}")
        
    except aiosqlite.IntegrityError as integrity_error:
        if "UNIQUE constraint failed" in str(integrity_error):
            logger.warning(f"User {discord_id} already exists in guild {guild_id}, but ON CONFLICT should handle this")
            # This shouldn't happen with ON CONFLICT DO UPDATE, but log it for debugging
        else:
            logger.error(f"Database integrity error adding user {discord_id} to guild {guild_id}: {integrity_error}")
        raise
    except ValueError as validation_error:
        logger.error(f"Validation error adding user: {validation_error}")
        raise
    except Exception as e:
        logger.error(f"❌ Unexpected error adding user {discord_id} to guild {guild_id}: {e}", exc_info=True)
        raise


async def get_user(discord_id: int):
    """Get user by Discord ID with comprehensive logging. (DEPRECATED: Use get_user_guild_aware instead)"""
    logger.warning("Using deprecated get_user function. Consider using get_user_guild_aware for multi-guild support")
    logger.debug(f"Retrieving user data for Discord ID: {discord_id}")
    
    try:
        if not isinstance(discord_id, int) or discord_id <= 0:
            raise ValueError(f"Invalid discord_id: {discord_id}")
        
        # For backwards compatibility, try to get user from default guild first
        default_guild_id = 897814031346319382
        query = "SELECT * FROM users WHERE discord_id = ? AND guild_id = ?"
        user = await execute_db_operation(
            f"get user {discord_id} from default guild",
            query,
            (discord_id, default_guild_id),
            fetch_type='one'
        )
        
        if user:
            logger.debug(f"✅ Found user: {user[3]} (ID: {user[0]}) in default guild")  # username at index 3
        else:
            logger.debug(f"No user found for Discord ID: {discord_id} in default guild")
        
        return user
        
    except ValueError as validation_error:
        logger.error(f"Validation error getting user: {validation_error}")
        raise
    except Exception as e:
        logger.error(f"❌ Unexpected error getting user {discord_id}: {e}", exc_info=True)
        raise


async def get_user_guild_aware(discord_id: int, guild_id: int):
    """Get user by Discord ID and Guild ID for multi-server support."""
    logger.debug(f"Retrieving user data for Discord ID: {discord_id} in guild: {guild_id}")
    
    try:
        if not isinstance(discord_id, int) or discord_id <= 0:
            raise ValueError(f"Invalid discord_id: {discord_id}")
        if not isinstance(guild_id, int) or guild_id <= 0:
            raise ValueError(f"Invalid guild_id: {guild_id}")
        
        query = "SELECT * FROM users WHERE discord_id = ? AND guild_id = ?"
        user = await execute_db_operation(
            f"get user {discord_id} from guild {guild_id}",
            query,
            (discord_id, guild_id),
            fetch_type='one'
        )
        
        if user:
            logger.debug(f"✅ Found user: {user[3]} (ID: {user[0]}) in guild {guild_id}")  # username at index 3
        else:
            logger.debug(f"No user found for Discord ID: {discord_id} in guild {guild_id}")
        
        return user
        
    except ValueError as validation_error:
        logger.error(f"Validation error getting user: {validation_error}")
        raise
    except Exception as e:
        logger.error(f"❌ Unexpected error getting user {discord_id} from guild {guild_id}: {e}", exc_info=True)
        raise
        
    except ValueError as validation_error:
        logger.error(f"Validation error getting user: {validation_error}")
        raise
    except Exception as e:
        logger.error(f"❌ Error retrieving user {discord_id}: {e}", exc_info=True)
        raise

async def get_all_users():
    """Get all users with comprehensive logging."""
    logger.debug("Retrieving all users from database")
    
    try:
        query = "SELECT * FROM users ORDER BY username"
        users = await execute_db_operation(
            "get all users",
            query,
            fetch_type='all'
        )
        
        logger.info(f"✅ Retrieved {len(users)} users from database")
        return users
        
    except Exception as e:
        logger.error(f"❌ Error retrieving all users: {e}", exc_info=True)
        raise

async def update_username(discord_id: int, username: str):
    """Update username with comprehensive logging and validation."""
    logger.info(f"Updating username for Discord ID {discord_id} to '{username}'")
    
    try:
        # Validate input
        if not isinstance(discord_id, int) or discord_id <= 0:
            raise ValueError(f"Invalid discord_id: {discord_id}")
        if not isinstance(username, str) or not username.strip():
            raise ValueError(f"Invalid username: {username}")
        
        # Check if user exists first
        existing_user = await get_user(discord_id)
        if not existing_user:
            logger.warning(f"Cannot update username - user {discord_id} not found")
            return False
        
        old_username = existing_user[2]  # username at index 2
        
        query = "UPDATE users SET username = ? WHERE discord_id = ?"
        await execute_db_operation(
            f"update username for {discord_id}",
            query,
            (username.strip(), discord_id)
        )
        
        logger.info(f"✅ Updated username for {discord_id}: '{old_username}' → '{username}'")
        return True
        
    except ValueError as validation_error:
        logger.error(f"Validation error updating username: {validation_error}")
        raise
    except Exception as e:
        logger.error(f"❌ Error updating username for {discord_id}: {e}", exc_info=True)
        raise

async def remove_user(discord_id: int, guild_id: int = None):
    """Remove user with comprehensive logging and validation.

    If guild_id is provided the removal will be scoped to that guild only. If guild_id
    is None the operation will remove all records for that discord_id across all guilds
    (backwards-compatible global delete).
    """
    logger.info(f"Removing user with Discord ID: {discord_id} guild_id={guild_id}")
    
    try:
        if not isinstance(discord_id, int) or discord_id <= 0:
            raise ValueError(f"Invalid discord_id: {discord_id}")
        
        # Check if user exists first (guild-aware when possible)
        existing_user = None
        if guild_id is not None:
            try:
                existing_user = await get_user_guild_aware(discord_id, guild_id)
            except Exception:
                # Fall back to legacy get_user
                existing_user = await get_user(discord_id)
        else:
            existing_user = await get_user(discord_id)
        if not existing_user:
            logger.warning(f"Cannot remove user - user {discord_id} not found")
            return False
        
        username = existing_user[2]  # username at index 2
        logger.info(f"Beginning cascading deletion for user: {username} (Discord ID: {discord_id})")
        
        # Check related records for debugging
        related_records = await check_user_related_records(discord_id)
        if any(count > 0 for count in related_records.values() if isinstance(count, int)):
            logger.info(f"Found related records to delete: {related_records}")
        
        # Use direct connection to ensure all operations are in a single transaction
        async with aiosqlite.connect(DB_PATH, timeout=DB_TIMEOUT) as db:
            db.row_factory = aiosqlite.Row
            
            # Begin transaction for atomic deletion
            await db.execute("BEGIN TRANSACTION")
            
            try:
                # Delete from all related tables first (in order to avoid foreign key conflicts)
                
                # 1. Delete user manga progress
                if guild_id is not None:
                    result = await db.execute("DELETE FROM user_manga_progress WHERE discord_id = ? AND guild_id = ?", (discord_id, guild_id))
                else:
                    result = await db.execute("DELETE FROM user_manga_progress WHERE discord_id = ?", (discord_id,))
                progress_deleted = result.rowcount
                logger.debug(f"Deleted {progress_deleted} manga progress records for user {discord_id}")
                
                # 2. Delete user stats
                if guild_id is not None:
                    result = await db.execute("DELETE FROM user_stats WHERE discord_id = ? AND guild_id = ?", (discord_id, guild_id))
                else:
                    result = await db.execute("DELETE FROM user_stats WHERE discord_id = ?", (discord_id,))
                stats_deleted = result.rowcount
                logger.debug(f"Deleted {stats_deleted} user stats records for user {discord_id}")
                
                # 3. Delete cached stats
                try:
                    if guild_id is not None:
                        result = await db.execute("DELETE FROM cached_stats WHERE discord_id = ? AND guild_id = ?", (discord_id, guild_id))
                    else:
                        result = await db.execute("DELETE FROM cached_stats WHERE discord_id = ?", (discord_id,))
                    cached_deleted = result.rowcount
                    logger.debug(f"Deleted {cached_deleted} cached stats records for user {discord_id}")
                except Exception as e:
                    logger.debug(f"Cached stats deletion failed (table may not exist): {e}")
                    cached_deleted = 0
                
                # 4. Delete manga recommendation votes (voter_id column)
                try:
                    if guild_id is not None:
                        result = await db.execute("DELETE FROM manga_recommendations_votes WHERE voter_id = ? AND guild_id = ?", (discord_id, guild_id))
                    else:
                        result = await db.execute("DELETE FROM manga_recommendations_votes WHERE voter_id = ?", (discord_id,))
                    votes_deleted = result.rowcount
                    logger.debug(f"Deleted {votes_deleted} recommendation votes for user {discord_id}")
                except Exception as e:
                    logger.debug(f"Manga recommendations votes deletion failed (table may not exist): {e}")
                    votes_deleted = 0
                
                # 5. Delete achievements
                try:
                    if guild_id is not None:
                        result = await db.execute("DELETE FROM achievements WHERE discord_id = ? AND guild_id = ?", (discord_id, guild_id))
                    else:
                        result = await db.execute("DELETE FROM achievements WHERE discord_id = ?", (discord_id,))
                    achievements_deleted = result.rowcount
                    logger.debug(f"Deleted {achievements_deleted} achievements for user {discord_id}")
                except Exception as e:
                    logger.debug(f"Achievements table deletion failed (table may not exist): {e}")
                    achievements_deleted = 0
                
                # 6. Delete steam user mapping
                try:
                    if guild_id is not None:
                        result = await db.execute("DELETE FROM steam_users WHERE discord_id = ? AND guild_id = ?", (discord_id, guild_id))
                    else:
                        result = await db.execute("DELETE FROM steam_users WHERE discord_id = ?", (discord_id,))
                    steam_deleted = result.rowcount
                    logger.debug(f"Deleted {steam_deleted} steam user mappings for user {discord_id}")
                except Exception as e:
                    logger.debug(f"Steam users table deletion failed (table may not exist): {e}")
                    steam_deleted = 0
                
                # 7. Delete user progress checkpoint
                try:
                    if guild_id is not None:
                        result = await db.execute("DELETE FROM user_progress_checkpoint WHERE discord_id = ? AND guild_id = ?", (discord_id, guild_id))
                    else:
                        result = await db.execute("DELETE FROM user_progress_checkpoint WHERE discord_id = ?", (discord_id,))
                    checkpoint_deleted = result.rowcount
                    logger.debug(f"Deleted {checkpoint_deleted} progress checkpoint records for user {discord_id}")
                except Exception as e:
                    logger.debug(f"Progress checkpoint deletion failed (table may not exist): {e}")
                    checkpoint_deleted = 0
                
                # 8. Delete manga challenges (user_id column)
                try:
                    if guild_id is not None:
                        result = await db.execute("DELETE FROM manga_challenges WHERE user_id = ? AND guild_id = ?", (discord_id, guild_id))
                    else:
                        result = await db.execute("DELETE FROM manga_challenges WHERE user_id = ?", (discord_id,))
                    manga_challenges_deleted = result.rowcount
                    logger.debug(f"Deleted {manga_challenges_deleted} manga challenges for user {discord_id}")
                except Exception as e:
                    logger.debug(f"Manga challenges deletion failed (table may not exist): {e}")
                    manga_challenges_deleted = 0
                
                # 9. Delete user progress (user_id column)
                try:
                    if guild_id is not None:
                        result = await db.execute("DELETE FROM user_progress WHERE user_id = ? AND guild_id = ?", (discord_id, guild_id))
                    else:
                        result = await db.execute("DELETE FROM user_progress WHERE user_id = ?", (discord_id,))
                    user_progress_deleted = result.rowcount
                    logger.debug(f"Deleted {user_progress_deleted} user progress records for user {discord_id}")
                except Exception as e:
                    logger.debug(f"User progress deletion failed (table may not exist): {e}")
                    user_progress_deleted = 0
                
                # 6. Finally, delete from users table
                if guild_id is not None:
                    result = await db.execute("DELETE FROM users WHERE discord_id = ? AND guild_id = ?", (discord_id, guild_id))
                else:
                    result = await db.execute("DELETE FROM users WHERE discord_id = ?", (discord_id,))
                user_deleted = result.rowcount
                
                if user_deleted == 0:
                    logger.error(f"Failed to delete user {discord_id} from users table")
                    await db.execute("ROLLBACK")
                    return False
                
                # Commit the transaction
                await db.commit()
                
                # Log summary of deletion
                logger.info(f"✅ Successfully removed user: {username} (Discord ID: {discord_id})")
                logger.info(f"   Deleted records: manga_progress={progress_deleted}, stats={stats_deleted}, "
                           f"cached_stats={cached_deleted}, votes={votes_deleted}, achievements={achievements_deleted}, "
                           f"steam={steam_deleted}, checkpoint={checkpoint_deleted}, "
                           f"manga_challenges={manga_challenges_deleted}, user_progress={user_progress_deleted}")
                
                return True
                
            except Exception as e:
                # Rollback on any error
                await db.execute("ROLLBACK")
                logger.error(f"Failed to delete user data, transaction rolled back: {e}")
                raise
        
    except ValueError as validation_error:
        logger.error(f"Validation error removing user: {validation_error}")
        raise
    except Exception as e:
        logger.error(f"❌ Error removing user {discord_id}: {e}", exc_info=True)
        raise

async def check_user_related_records(discord_id: int, guild_id: int = None):
    """Check for related records before user deletion (for debugging).

    If guild_id is provided, counts will be limited to that guild when possible.
    """
    logger.debug(f"Checking related records for user {discord_id} (guild_id={guild_id})")

    try:
        async with aiosqlite.connect(DB_PATH, timeout=DB_TIMEOUT) as db:
            related_counts = {}

            # Check each table that might reference the user
            tables_to_check = [
                ("user_manga_progress", "discord_id"),
                ("user_stats", "discord_id"),
                ("cached_stats", "discord_id"),
                ("manga_recommendations_votes", "voter_id"),
                ("achievements", "discord_id"),
                ("steam_users", "discord_id"),
                ("user_progress_checkpoint", "discord_id"),
                ("manga_challenges", "user_id"),
                ("user_progress", "user_id")
            ]

            for table_name, column_name in tables_to_check:
                try:
                    if guild_id is not None:
                        # Try guild-scoped count first; if table lacks guild_id column this will fail
                        try:
                            cursor = await db.execute(f"SELECT COUNT(*) FROM {table_name} WHERE {column_name} = ? AND guild_id = ?", (discord_id, guild_id))
                            count = await cursor.fetchone()
                            related_counts[table_name] = count[0] if count else 0
                            await cursor.close()
                            continue
                        except Exception:
                            # Table probably doesn't have guild_id; fall back to global count
                            pass

                    cursor = await db.execute(f"SELECT COUNT(*) FROM {table_name} WHERE {column_name} = ?", (discord_id,))
                    count = await cursor.fetchone()
                    related_counts[table_name] = count[0] if count else 0
                    await cursor.close()
                except Exception as e:
                    logger.debug(f"Could not check table {table_name}: {e}")
                    related_counts[table_name] = "ERROR"

            logger.debug(f"Related records for user {discord_id}: {related_counts}")
            return related_counts

    except Exception as e:
        logger.error(f"Error checking related records for user {discord_id}: {e}")
        return {}

async def update_anilist_info(discord_id: int, anilist_username: str, anilist_id: int):
    """Update AniList information with comprehensive logging and validation."""
    logger.info(f"Updating AniList info for Discord ID {discord_id}")
    logger.debug(f"AniList data - Username: {anilist_username}, ID: {anilist_id}")
    
    try:
        # Validate input
        if not isinstance(discord_id, int) or discord_id <= 0:
            raise ValueError(f"Invalid discord_id: {discord_id}")
        if not isinstance(anilist_username, str) or not anilist_username.strip():
            raise ValueError(f"Invalid anilist_username: {anilist_username}")
        if not isinstance(anilist_id, int) or anilist_id <= 0:
            raise ValueError(f"Invalid anilist_id: {anilist_id}")
        
        # Check if user exists
        existing_user = await get_user(discord_id)
        if not existing_user:
            logger.error(f"Cannot update AniList info - user {discord_id} not found")
            return False
        
        query = """
            UPDATE users
            SET anilist_username = ?, anilist_id = ?, updated_at = CURRENT_TIMESTAMP
            WHERE discord_id = ?
        """
        
        await execute_db_operation(
            f"update AniList info for {discord_id}",
            query,
            (anilist_username.strip(), anilist_id, discord_id)
        )
        
        logger.info(f"✅ Updated AniList info for {discord_id}: {anilist_username} (ID: {anilist_id})")
        return True
        
    except ValueError as validation_error:
        logger.error(f"Validation error updating AniList info: {validation_error}")
        raise
    except Exception as e:
        logger.error(f"❌ Error updating AniList info for {discord_id}: {e}", exc_info=True)
        raise

# ------------------------------------------------------
# CHALLENGE RULES TABLE FUNCTIONS with Enhanced Logging
# ------------------------------------------------------
async def init_challenge_rules_table():
    """Initialize challenge rules table with comprehensive logging."""
    logger.info("Initializing challenge rules table")
    
    try:
        create_query = """
            CREATE TABLE IF NOT EXISTS challenge_rules (
                id INTEGER PRIMARY KEY,
                rules TEXT NOT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """
        
        await execute_db_operation("challenge rules table creation", create_query)
        
        # Add missing timestamp columns if they don't exist
        # SQLite doesn't support DEFAULT CURRENT_TIMESTAMP with ALTER TABLE, so we use NULL default
        for column_name, column_type in [("created_at", "DATETIME"), ("updated_at", "DATETIME")]:
            try:
                alter_query = f"ALTER TABLE challenge_rules ADD COLUMN {column_name} {column_type}"
                await execute_db_operation(f"add {column_name} to challenge_rules", alter_query)
                logger.debug(f"Added missing column '{column_name}' to challenge_rules table")
            except aiosqlite.OperationalError as e:
                if "duplicate column name" in str(e).lower():
                    logger.debug(f"Column '{column_name}' already exists in challenge_rules table")
                else:
                    logger.warning(f"Could not add column '{column_name}' to challenge_rules: {e}")
            except Exception as e:
                logger.warning(f"Could not add column '{column_name}' to challenge_rules: {e}")
        
        logger.info("✅ Challenge rules table initialization completed")
        
    except Exception as e:
        logger.error(f"❌ Failed to initialize challenge rules table: {e}", exc_info=True)
        raise

async def set_challenge_rules(rules: str):
    """Set challenge rules with comprehensive logging and validation."""
    logger.info("Setting challenge rules")
    
    try:
        if not isinstance(rules, str) or not rules.strip():
            raise ValueError("Rules must be a non-empty string")
        
        logger.debug(f"Rules length: {len(rules)} characters")
        
        query = """
            INSERT INTO challenge_rules (id, rules, updated_at)
            VALUES (1, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(id) DO UPDATE SET 
                rules=excluded.rules,
                updated_at=CURRENT_TIMESTAMP
        """
        
        await execute_db_operation("set challenge rules", query, (rules.strip(),))
        logger.info("✅ Challenge rules updated successfully")
        
    except ValueError as validation_error:
        logger.error(f"Validation error setting challenge rules: {validation_error}")
        raise
    except Exception as e:
        logger.error(f"❌ Error setting challenge rules: {e}", exc_info=True)
        raise

async def get_challenge_rules() -> Optional[str]:
    """Get challenge rules with comprehensive logging."""
    logger.debug("Retrieving challenge rules")
    
    try:
        query = "SELECT rules FROM challenge_rules WHERE id = 1"
        result = await execute_db_operation("get challenge rules", query, fetch_type='one')
        
        if result:
            rules = result[0]
            logger.debug(f"Retrieved challenge rules ({len(rules)} characters)")
            return rules
        else:
            logger.debug("No challenge rules found")
            return None
            
    except Exception as e:
        logger.error(f"❌ Error retrieving challenge rules: {e}", exc_info=True)
        raise

# ------------------------------------------------------
# MANGA RECOMMENDATION VOTES TABLE
# ------------------------------------------------------
async def init_recommendation_votes_table():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS manga_recommendations_votes (
                manga_id INTEGER NOT NULL,
                voter_id INTEGER NOT NULL,
                vote INTEGER NOT NULL,
                PRIMARY KEY (manga_id, voter_id)
            )
        """)
        await db.commit()
        logger.info("Manga recommendation votes table ready.")

# ------------------------------------------------------
# USER STATS TABLE
# ------------------------------------------------------
async def init_user_stats_table():
    async with aiosqlite.connect(DB_PATH) as db:
        # Check if table exists and get its schema
        cursor = await db.execute("PRAGMA table_info(user_stats)")
        schema = await cursor.fetchall()
        await cursor.close()
        
        if not schema:
            # Create new table with proper guild-aware schema
            await db.execute("""
                CREATE TABLE user_stats (
                    discord_id INTEGER NOT NULL,
                    guild_id INTEGER NOT NULL,
                    username TEXT,
                    total_manga INTEGER DEFAULT 0,
                    total_anime INTEGER DEFAULT 0,
                    avg_manga_score REAL DEFAULT 0,
                    avg_anime_score REAL DEFAULT 0,
                    total_chapters INTEGER DEFAULT 0,
                    total_episodes INTEGER DEFAULT 0,
                    manga_completed INTEGER DEFAULT 0,
                    anime_completed INTEGER DEFAULT 0,
                    PRIMARY KEY (discord_id, guild_id)
                )
            """)
            logger.info("Created new guild-aware user_stats table")
        else:
            # Table exists, ensure all columns are present
            await db.execute("""
                CREATE TABLE IF NOT EXISTS user_stats (
                    discord_id INTEGER PRIMARY KEY,
                    username TEXT,
                    total_manga INTEGER DEFAULT 0,
                    total_anime INTEGER DEFAULT 0,
                    avg_manga_score REAL DEFAULT 0,
                    avg_anime_score REAL DEFAULT 0
                )
            """)
            
            # Add missing columns for compatibility
            try:
                await db.execute("ALTER TABLE user_stats ADD COLUMN total_chapters INTEGER DEFAULT 0")
            except aiosqlite.OperationalError:
                pass
            try:
                await db.execute("ALTER TABLE user_stats ADD COLUMN total_episodes INTEGER DEFAULT 0")
            except aiosqlite.OperationalError:
                pass
            try:
                await db.execute("ALTER TABLE user_stats ADD COLUMN manga_completed INTEGER DEFAULT 0")
            except aiosqlite.OperationalError:
                pass
            try:
                await db.execute("ALTER TABLE user_stats ADD COLUMN anime_completed INTEGER DEFAULT 0")
            except aiosqlite.OperationalError:
                pass
            try:
                await db.execute("ALTER TABLE user_stats ADD COLUMN guild_id INTEGER")
            except aiosqlite.OperationalError:
                pass
                
        await db.commit()
        logger.info("User stats table ready.")

# ------------------------------------------------------
# ACHIEVEMENTS TABLE
# ------------------------------------------------------
async def init_achievements_table():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS achievements (
                discord_id INTEGER,
                achievement TEXT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (discord_id, achievement)
            )
        """)
        await db.commit()
        logger.info("Achievements table ready.")


# ------------------------------------------------------
# USER MANGA PROGRESS TABLE
# ------------------------------------------------------
async def init_user_manga_progress_table():
    async with aiosqlite.connect(DB_PATH) as db:
        # Create table if not exists
        await db.execute("""
            CREATE TABLE IF NOT EXISTS user_manga_progress (
                discord_id INTEGER NOT NULL,
                manga_id INTEGER NOT NULL,
                title TEXT DEFAULT '',
                current_chapter INTEGER DEFAULT 0,
                rating REAL DEFAULT 0,
                status TEXT DEFAULT 'Not Started',
                points INTEGER DEFAULT 0,
                repeat INTEGER DEFAULT 0,
                started_at TEXT DEFAULT NULL,
                updated_at TEXT DEFAULT NULL,   -- NEW COLUMN
                PRIMARY KEY (discord_id, manga_id)
            )
        """)
        # Add 'repeat' column if missing
        try:
            await db.execute("ALTER TABLE user_manga_progress ADD COLUMN repeat INTEGER DEFAULT 0")
        except aiosqlite.OperationalError:
            pass
        # Add 'updated_at' column if missing
        try:
            await db.execute("ALTER TABLE user_manga_progress ADD COLUMN updated_at TEXT DEFAULT NULL")
        except aiosqlite.OperationalError:
            pass

        await db.commit()
        logger.info("User manga progress table ready (with started_at, repeat, and updated_at).")



async def set_user_manga_progress(discord_id: int, manga_id: int, chapter: int, rating: float):
    """Set user manga progress with comprehensive logging and validation."""
    logger.info(f"Setting manga progress for user {discord_id}, manga {manga_id}")
    
    try:
        # Validate input
        if not isinstance(discord_id, int) or discord_id <= 0:
            raise ValueError(f"Invalid discord_id: {discord_id}")
        if not isinstance(manga_id, int) or manga_id <= 0:
            raise ValueError(f"Invalid manga_id: {manga_id}")
        if not isinstance(chapter, int) or chapter < 0:
            raise ValueError(f"Invalid chapter: {chapter}")
        if not isinstance(rating, (int, float)) or not (0 <= rating <= 10):
            logger.warning(f"Invalid rating {rating}, clamping to 0-10 range")
            rating = max(0, min(10, float(rating)))
        
        logger.debug(f"Progress data - Chapter: {chapter}, Rating: {rating}")
        
        query = """
            INSERT INTO user_manga_progress (discord_id, manga_id, current_chapter, rating, updated_at)
            VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(discord_id, manga_id) DO UPDATE SET
                current_chapter=excluded.current_chapter,
                rating=excluded.rating,
                updated_at=CURRENT_TIMESTAMP
        """
        
        await execute_db_operation(
            f"set manga progress for user {discord_id}",
            query,
            (discord_id, manga_id, chapter, rating)
        )
        
        logger.info(f"✅ Set manga {manga_id} progress for user {discord_id}: Chapter {chapter}, Rating {rating}")
        
    except ValueError as validation_error:
        logger.error(f"Validation error setting manga progress: {validation_error}")
        raise
    except Exception as e:
        logger.error(f"❌ Error setting manga progress for user {discord_id}: {e}", exc_info=True)
        raise

async def get_user_manga_progress(discord_id: int, manga_id: int):
    """Get user manga progress with comprehensive logging and validation."""
    logger.debug(f"Getting manga progress for user {discord_id}, manga {manga_id}")
    
    try:
        # Validate input
        if not isinstance(discord_id, int) or discord_id <= 0:
            raise ValueError(f"Invalid discord_id: {discord_id}")
        if not isinstance(manga_id, int) or manga_id <= 0:
            raise ValueError(f"Invalid manga_id: {manga_id}")
        
        query = """
            SELECT current_chapter, rating, status, repeat FROM user_manga_progress
            WHERE discord_id = ? AND manga_id = ?
        """
        
        result = await execute_db_operation(
            f"get manga progress for user {discord_id}",
            query,
            (discord_id, manga_id),
            fetch_type='one'
        )
        
        if result:
            progress_data = {
                "current_chapter": result[0],
                "rating": result[1],
                "status": result[2],
                "repeat": result[3]
            }
            logger.debug(f"✅ Retrieved manga progress: {progress_data}")
            return progress_data
        else:
            logger.debug(f"No progress found for user {discord_id}, manga {manga_id}")
            return None
            
    except ValueError as validation_error:
        logger.error(f"Validation error getting manga progress: {validation_error}")
        raise
    except Exception as e:
        logger.error(f"❌ Error getting manga progress for user {discord_id}: {e}", exc_info=True)
        raise

async def upsert_user_manga_progress(discord_id, manga_id, title, chapters, points, status, repeat=0, started_at=None):
    """Upsert user manga progress with comprehensive logging and validation."""
    logger.info(f"Upserting manga progress for user {discord_id}: {title}")
    
    try:
        # Validate input
        if not isinstance(discord_id, int) or discord_id <= 0:
            raise ValueError(f"Invalid discord_id: {discord_id}")
        if not isinstance(manga_id, int) or manga_id <= 0:
            raise ValueError(f"Invalid manga_id: {manga_id}")
        if not isinstance(title, str) or not title.strip():
            raise ValueError(f"Invalid title: {title}")
        if not isinstance(chapters, int) or chapters < 0:
            logger.warning(f"Invalid chapters {chapters}, setting to 0")
            chapters = 0
        if not isinstance(points, int) or points < 0:
            logger.warning(f"Invalid points {points}, setting to 0")
            points = 0
        if not isinstance(repeat, int) or repeat < 0:
            logger.warning(f"Invalid repeat {repeat}, setting to 0")
            repeat = 0
        
        logger.debug(f"Manga progress - Title: {title}, Chapters: {chapters}, Points: {points}, Status: {status}, Repeat: {repeat}")
        
        now = datetime.utcnow().isoformat()
        
        query = """
            INSERT INTO user_manga_progress(
                discord_id, manga_id, title, current_chapter, points, status, repeat, started_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(discord_id, manga_id) DO UPDATE SET
                title=excluded.title,
                current_chapter=excluded.current_chapter,
                points=excluded.points,
                status=excluded.status,
                repeat=excluded.repeat,
                started_at=excluded.started_at,
                updated_at=excluded.updated_at
        """
        
        await execute_db_operation(
            f"upsert manga progress for user {discord_id}",
            query,
            (discord_id, manga_id, title.strip(), chapters, points, status, repeat, started_at, now)
        )
        
        logger.info(f"✅ Upserted manga progress for user {discord_id}: {title} ({status})")
        
    except ValueError as validation_error:
        logger.error(f"Validation error upserting manga progress: {validation_error}")
        raise
    except Exception as e:
        logger.error(f"❌ Error upserting manga progress for user {discord_id}: {e}", exc_info=True)
        raise
        
async def upsert_user_stats(
    discord_id: int,
    username: str,
    total_manga: int,
    total_anime: int,
    avg_manga_score: float,
    avg_anime_score: float,
    total_chapters: int = 0,
    total_episodes: int = 0,
    manga_completed: int = 0,
    anime_completed: int = 0
):
    """Upsert user stats with comprehensive logging and validation."""
    logger.info(f"Upserting stats for user {username} (Discord ID: {discord_id})")
    
    try:
        # Validate input data
        if not isinstance(discord_id, int) or discord_id <= 0:
            raise ValueError(f"Invalid discord_id: {discord_id}")
        if not isinstance(username, str) or not username.strip():
            raise ValueError(f"Invalid username: {username}")
        
        # Validate numeric fields
        numeric_fields = {
            'total_manga': total_manga,
            'total_anime': total_anime,
            'avg_manga_score': avg_manga_score,
            'avg_anime_score': avg_anime_score,
            'total_chapters': total_chapters,
            'total_episodes': total_episodes,
            'manga_completed': manga_completed,
            'anime_completed': anime_completed
        }
        
        for field_name, value in numeric_fields.items():
            if not isinstance(value, (int, float)) or value < 0:
                logger.warning(f"Invalid {field_name}: {value}, setting to 0")
                numeric_fields[field_name] = 0
        
        logger.debug(f"User stats - Manga: {total_manga}, Anime: {total_anime}, Chapters: {total_chapters}, Episodes: {total_episodes}")
        logger.debug(f"Average scores - Manga: {avg_manga_score:.2f}, Anime: {avg_anime_score:.2f}")
        
        # Upsert with completed counts when available (backwards compatible)
        query = """
            INSERT INTO user_stats (
                discord_id, username, total_manga, total_anime,
                avg_manga_score, avg_anime_score, total_chapters, total_episodes, manga_completed, anime_completed
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(discord_id) DO UPDATE SET
                username=excluded.username,
                total_manga=excluded.total_manga,
                total_anime=excluded.total_anime,
                avg_manga_score=excluded.avg_manga_score,
                avg_anime_score=excluded.avg_anime_score,
                total_chapters=excluded.total_chapters,
                total_episodes=excluded.total_episodes,
                manga_completed=excluded.manga_completed,
                anime_completed=excluded.anime_completed
        """

        await execute_db_operation(
            f"upsert user stats for {username}",
            query,
            (
                discord_id,
                username.strip(),
                numeric_fields['total_manga'],
                numeric_fields['total_anime'],
                numeric_fields['avg_manga_score'],
                numeric_fields['avg_anime_score'],
                numeric_fields['total_chapters'],
                numeric_fields['total_episodes'],
                numeric_fields.get('manga_completed', 0),
                numeric_fields.get('anime_completed', 0)
            )
        )
        
        logger.info(f"✅ Successfully upserted stats for {username}")
        
    except ValueError as validation_error:
        logger.error(f"Validation error upserting user stats: {validation_error}")
        raise
    except Exception as e:
        logger.error(f"❌ Error upserting stats for {discord_id}: {e}", exc_info=True)
        raise

# Save or update a user with comprehensive logging
async def save_user(discord_id: int, username: str):
    """Save or update user with comprehensive logging and validation."""
    logger.info(f"Saving user: {username} (Discord ID: {discord_id})")
    
    try:
        if not isinstance(discord_id, int) or discord_id <= 0:
            raise ValueError(f"Invalid discord_id: {discord_id}")
        if not isinstance(username, str) or not username.strip():
            raise ValueError(f"Invalid username: {username}")
        
        # Check if user already exists
        existing_user = await get_user(discord_id)
        operation_type = "update" if existing_user else "insert"
        
        query = """
            INSERT INTO users (discord_id, username, updated_at)
            VALUES (?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(discord_id) DO UPDATE SET 
                username=excluded.username,
                updated_at=CURRENT_TIMESTAMP
        """
        
        await execute_db_operation(
            f"save user {username} ({operation_type})",
            query,
            (discord_id, username.strip())
        )
        
        logger.info(f"✅ Successfully saved user: {username} ({operation_type})")
        
    except ValueError as validation_error:
        logger.error(f"Validation error saving user: {validation_error}")
        raise
    except Exception as e:
        logger.error(f"❌ Error saving user {discord_id}: {e}", exc_info=True)
        raise


# ------------------------------------------------------
# MANGA CHALLENGES TABLE
# ------------------------------------------------------
async def init_manga_challenges_table():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS manga_challenges (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                manga_id INTEGER NOT NULL,
                title TEXT NOT NULL,
                total_chapters INTEGER NOT NULL,
                chapters_read INTEGER NOT NULL DEFAULT 0,
                status TEXT NOT NULL DEFAULT 'in_progress',
                FOREIGN KEY(user_id) REFERENCES users(id)
            );
        """)
        await db.commit()

async def init_global_challenges_table():
    async with aiosqlite.connect(DB_PATH) as db:
        # Create table if it doesn't exist (without the difficulty column first)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS global_challenges (
                challenge_id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                total_chapters INTEGER DEFAULT 0
            )
        """)
        # Try adding the column (if it doesn't exist yet)
        try:
            await db.execute("ALTER TABLE global_challenges ADD COLUMN difficulty TEXT DEFAULT 'Medium'")
        except aiosqlite.OperationalError:
            # Column already exists
            pass

        # Optional: Add a start_date column too if you need it
        try:
            await db.execute("ALTER TABLE global_challenges ADD COLUMN start_date TEXT DEFAULT NULL")
        except aiosqlite.OperationalError:
            pass

        await db.commit()
        logger.info("Global challenges table ready with difficulty column.")

async def init_user_progress_table():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS user_progress (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                challenge_manga_id INTEGER NOT NULL,
                chapters_read INTEGER NOT NULL DEFAULT 0,
                status TEXT NOT NULL DEFAULT 'in_progress',
                FOREIGN KEY(user_id) REFERENCES users(id),
                FOREIGN KEY(challenge_manga_id) REFERENCES challenge_manga(id)
            )
        """)
        await db.commit()

async def add_global_challenge(manga_id: int, title: str, total_chapters: int, start_date: datetime = None):
    if start_date is None:
        start_date = datetime.utcnow()  # Use UTC for consistency

    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            """
            INSERT INTO global_challenges (manga_id, title, total_chapters, start_date)
            VALUES (?, ?, ?, ?)
            """,
            (manga_id, title, total_chapters, start_date)
        )
        challenge_id = cursor.lastrowid

        users = await db.execute_fetchall("SELECT id FROM users")
        for (user_id,) in users:
            await db.execute(
                "INSERT INTO user_progress (user_id, challenge_id) VALUES (?, ?)",
                (user_id, challenge_id)
            )

        await db.commit()
        return challenge_id
    
async def init_challenge_manga_table():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS challenge_manga (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                challenge_id INTEGER NOT NULL,
                manga_id INTEGER NOT NULL UNIQUE,
                title TEXT NOT NULL,
                total_chapters INTEGER NOT NULL,
                medium_type TEXT DEFAULT 'manga',
                FOREIGN KEY(challenge_id) REFERENCES global_challenges(challenge_id)
            )
        """)
        # Ensure medium_type exists if the table already existed
        try:
            await db.execute("ALTER TABLE challenge_manga ADD COLUMN medium_type TEXT DEFAULT 'manga'")
        except aiosqlite.OperationalError:
            # Column already exists, ignore
            pass
        await db.commit()

from datetime import datetime

async def upsert_user_manga_progress(discord_id, manga_id, title, chapters, points, status, repeat=0, started_at=None):
    """Upsert user manga progress including repeat, started_at, and updated_at"""
    now = datetime.utcnow().isoformat()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            INSERT INTO user_manga_progress(discord_id, manga_id, title, current_chapter, points, status, repeat, started_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(discord_id, manga_id) DO UPDATE SET
                title=excluded.title,
                current_chapter=excluded.current_chapter,
                points=excluded.points,
                status=excluded.status,
                repeat=excluded.repeat,
                started_at=excluded.started_at,
                updated_at=excluded.updated_at
            """,
            (discord_id, manga_id, title, chapters, points, status, repeat, started_at, now)
        )
        await db.commit()

# ------------------------------------------------------
# INVITE TRACKER TABLES
# ------------------------------------------------------
async def init_invite_tracker_tables():
    """Initialize all invite tracker tables in the main database"""
    logger.info("Initializing invite tracker tables")
    
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            # Invites table - tracks all invites
            await db.execute("""
                CREATE TABLE IF NOT EXISTS invites (
                    invite_code TEXT PRIMARY KEY,
                    guild_id INTEGER NOT NULL,
                    inviter_id INTEGER NOT NULL,
                    inviter_name TEXT NOT NULL,
                    channel_id INTEGER,
                    max_uses INTEGER,
                    uses INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Invite uses table - tracks who used which invite
            await db.execute("""
                CREATE TABLE IF NOT EXISTS invite_uses (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    guild_id INTEGER NOT NULL,
                    invite_code TEXT NOT NULL,
                    inviter_id INTEGER NOT NULL,
                    inviter_name TEXT NOT NULL,
                    joiner_id INTEGER NOT NULL,
                    joiner_name TEXT NOT NULL,
                    joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (invite_code) REFERENCES invites (invite_code)
                )
            """)
            
            # Recruitment stats table - tracks total recruits per user
            await db.execute("""
                CREATE TABLE IF NOT EXISTS recruitment_stats (
                    user_id INTEGER PRIMARY KEY,
                    guild_id INTEGER NOT NULL,
                    username TEXT NOT NULL,
                    total_recruits INTEGER DEFAULT 0,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Leave tracking table - tracks when users leave
            await db.execute("""
                CREATE TABLE IF NOT EXISTS user_leaves (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    guild_id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL,
                    username TEXT NOT NULL,
                    left_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    was_invited_by INTEGER,
                    days_in_server INTEGER DEFAULT 0
                )
            """)
            
            # Invite tracker settings - stores channel configuration
            await db.execute("""
                CREATE TABLE IF NOT EXISTS invite_tracker_settings (
                    guild_id INTEGER PRIMARY KEY,
                    announcement_channel_id INTEGER NOT NULL,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            await db.commit()
            logger.info("✅ Invite tracker tables initialized successfully")
    
    except Exception as e:
        logger.error(f"❌ Failed to initialize invite tracker tables: {e}", exc_info=True)
        raise

# ------------------------------------------------------
# STEAM USERS TABLE
# ------------------------------------------------------
async def init_steam_users_table():
    """Create a table to store Discord -> Steam account mapping"""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS steam_users (
                discord_id INTEGER PRIMARY KEY,
                steam_id TEXT NOT NULL,
                vanity_name TEXT
            )
        """)
        await db.commit()
        logger.info("Steam users table ready.")


async def init_guild_challenge_roles_table():
    """Initialize the guild challenge roles table for multi-guild support."""
    logger.info("🔧 Initializing guild challenge roles table...")
    
    async with aiosqlite.connect(config.DB_PATH, timeout=DB_TIMEOUT) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS guild_challenge_roles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id INTEGER NOT NULL,
                challenge_id INTEGER NOT NULL,
                threshold REAL NOT NULL,
                role_id INTEGER NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(guild_id, challenge_id, threshold)
            )
        """)
        await db.commit()
        
        # Migrate default roles for primary guild if they don't exist
        await migrate_default_challenge_roles()
        
        # Migrate global challenges to guild-specific tables for primary guild
        await migrate_global_challenges_to_guild()
        
        logger.info("✅ Guild challenge roles table ready.")

async def init_guild_challenges_table():
    """Initialize the guild challenges table for guild-specific challenge management."""
    logger.info("🔧 Initializing guild challenges table...")
    
    async with aiosqlite.connect(config.DB_PATH, timeout=DB_TIMEOUT) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS guild_challenges (
                challenge_id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id INTEGER NOT NULL,
                title TEXT NOT NULL,
                description TEXT,
                difficulty TEXT DEFAULT 'Medium',
                start_date TEXT DEFAULT NULL,
                end_date TEXT DEFAULT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(guild_id, title)
            )
        """)
        await db.commit()
        logger.info("✅ Guild challenges table ready.")

async def init_guild_challenge_manga_table():
    """Initialize the guild challenge manga table for guild-specific challenge manga management."""
    logger.info("🔧 Initializing guild challenge manga table...")
    
    async with aiosqlite.connect(config.DB_PATH, timeout=DB_TIMEOUT) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS guild_challenge_manga (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id INTEGER NOT NULL,
                challenge_id INTEGER NOT NULL,
                manga_id INTEGER NOT NULL,
                title TEXT NOT NULL,
                total_chapters INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(guild_id, challenge_id, manga_id),
                FOREIGN KEY(guild_id, challenge_id) REFERENCES guild_challenges(guild_id, challenge_id) ON DELETE CASCADE
            )
        """)
        await db.commit()
        logger.info("✅ Guild challenge manga table ready.")

async def init_guild_manga_channels_table():
    """Initialize the guild manga channels table for multi-guild animanga completion support."""
    logger.info("🔧 Initializing guild manga channels table...")
    
    async with aiosqlite.connect(config.DB_PATH, timeout=DB_TIMEOUT) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS guild_manga_channels (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id INTEGER NOT NULL UNIQUE,
                channel_id INTEGER NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await db.commit()
        
        logger.info("✅ Guild manga channels table ready.")


async def init_guild_bot_update_channels_table():
    """Initialize the guild bot update channels table."""
    logger.info("🔧 Initializing guild bot update channels table...")
    
    async with aiosqlite.connect(config.DB_PATH, timeout=DB_TIMEOUT) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS guild_bot_update_channels (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id INTEGER NOT NULL UNIQUE,
                channel_id INTEGER NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await db.commit()
        
        logger.info("✅ Guild bot update channels table ready.")


async def init_guild_mod_roles_table():
    """Initialize the guild mod roles table."""
    logger.info("🔧 Initializing guild mod roles table...")
    
    async with aiosqlite.connect(config.DB_PATH, timeout=DB_TIMEOUT) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS guild_mod_roles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id INTEGER NOT NULL UNIQUE,
                role_id INTEGER NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await db.commit()
        
        logger.info("✅ Guild mod roles table ready.")


async def init_bot_moderators_table():
    """Initialize the bot moderators table for bot-wide moderation."""
    logger.info("🔧 Initializing bot moderators table...")
    
    async with aiosqlite.connect(config.DB_PATH, timeout=DB_TIMEOUT) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS bot_moderators (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                discord_id INTEGER NOT NULL UNIQUE,
                username TEXT NOT NULL,
                added_by INTEGER NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await db.commit()
        
        logger.info("✅ Bot moderators table ready.")


async def add_bot_moderator(discord_id: int, username: str, added_by: int):
    """Add a bot moderator."""
    try:
        async with aiosqlite.connect(config.DB_PATH, timeout=DB_TIMEOUT) as db:
            await db.execute("""
                INSERT OR REPLACE INTO bot_moderators (discord_id, username, added_by, updated_at)
                VALUES (?, ?, ?, CURRENT_TIMESTAMP)
            """, (discord_id, username, added_by))
            await db.commit()
            
        logger.info(f"Added bot moderator: {username} (Discord ID: {discord_id})")
        return True
        
    except Exception as e:
        logger.error(f"Error adding bot moderator {discord_id}: {e}")
        return False


async def remove_bot_moderator(discord_id: int):
    """Remove a bot moderator."""
    try:
        async with aiosqlite.connect(config.DB_PATH, timeout=DB_TIMEOUT) as db:
            await db.execute("""
                DELETE FROM bot_moderators WHERE discord_id = ?
            """, (discord_id,))
            await db.commit()
            
        logger.info(f"Removed bot moderator: Discord ID {discord_id}")
        return True
        
    except Exception as e:
        logger.error(f"Error removing bot moderator {discord_id}: {e}")
        return False


async def is_bot_moderator(discord_id: int):
    """Check if a user is a bot moderator."""
    try:
        async with aiosqlite.connect(config.DB_PATH, timeout=DB_TIMEOUT) as db:
            async with db.execute("""
                SELECT discord_id FROM bot_moderators WHERE discord_id = ?
            """, (discord_id,)) as cursor:
                result = await cursor.fetchone()
                return result is not None
                
    except Exception as e:
        logger.error(f"Error checking if user {discord_id} is bot moderator: {e}")
        return False


async def get_all_bot_moderators():
    """Get all bot moderators."""
    try:
        async with aiosqlite.connect(config.DB_PATH, timeout=DB_TIMEOUT) as db:
            async with db.execute("""
                SELECT discord_id, username, added_by, created_at FROM bot_moderators ORDER BY username
            """) as cursor:
                return await cursor.fetchall()
                
    except Exception as e:
        logger.error(f"Error getting all bot moderators: {e}")
        return []


async def is_user_bot_moderator(user):
    """
    Check if a user is a bot moderator or admin.
    Bot moderators can perform bot-wide actions like publishing changelogs.
    """
    try:
        import config
        
        # Check if user is the admin
        if hasattr(user, 'id') and user.id == config.ADMIN_DISCORD_ID:
            return True
            
        # Check if user is in bot moderators table
        if hasattr(user, 'id'):
            return await is_bot_moderator(user.id)
        
        return False
        
    except Exception as e:
        logger.error(f"Error checking if user is bot moderator: {e}")
        return False


async def set_guild_mod_role(guild_id: int, role_id: int):
    """Set the moderator role for a guild."""
    try:
        async with aiosqlite.connect(config.DB_PATH, timeout=DB_TIMEOUT) as db:
            await db.execute("""
                INSERT OR REPLACE INTO guild_mod_roles (guild_id, role_id, updated_at)
                VALUES (?, ?, CURRENT_TIMESTAMP)
            """, (guild_id, role_id))
            await db.commit()
            
        logger.info(f"Set mod role {role_id} for guild {guild_id}")
        return True
        
    except Exception as e:
        logger.error(f"Error setting mod role for guild {guild_id}: {e}")
        return False


async def get_guild_mod_role(guild_id: int):
    """Get the moderator role for a guild."""
    try:
        async with aiosqlite.connect(config.DB_PATH, timeout=DB_TIMEOUT) as db:
            async with db.execute("""
                SELECT role_id FROM guild_mod_roles WHERE guild_id = ?
            """, (guild_id,)) as cursor:
                result = await cursor.fetchone()
                return result[0] if result else None
                
    except Exception as e:
        logger.error(f"Error getting mod role for guild {guild_id}: {e}")
        return None


async def remove_guild_mod_role(guild_id: int):
    """Remove the moderator role configuration for a guild."""
    try:
        async with aiosqlite.connect(config.DB_PATH, timeout=DB_TIMEOUT) as db:
            await db.execute("""
                DELETE FROM guild_mod_roles WHERE guild_id = ?
            """, (guild_id,))
            await db.commit()
            
        logger.info(f"Removed mod role configuration for guild {guild_id}")
        return True
        
    except Exception as e:
        logger.error(f"Error removing mod role for guild {guild_id}: {e}")
        return False


async def get_all_guild_mod_roles():
    """Get all guild mod role configurations."""
    try:
        async with aiosqlite.connect(config.DB_PATH, timeout=DB_TIMEOUT) as db:
            async with db.execute("""
                SELECT guild_id, role_id FROM guild_mod_roles ORDER BY guild_id
            """) as cursor:
                return await cursor.fetchall()
                
    except Exception as e:
        logger.error(f"Error getting all mod roles: {e}")
        return []


async def is_user_moderator(user, guild_id: int):
    """
    Check if a user is a moderator based on guild mod role configuration.
    Falls back to config.MOD_ROLE_ID if no guild-specific role is set.
    """
    try:
        # First check guild-specific mod role
        guild_mod_role_id = await get_guild_mod_role(guild_id)
        
        if guild_mod_role_id:
            # Check if user has the guild-specific mod role
            if hasattr(user, 'roles'):
                for role in user.roles:
                    if getattr(role, 'id', None) == guild_mod_role_id:
                        return True
        else:
            # Fall back to global config MOD_ROLE_ID if no guild-specific role
            import config
            if config.MOD_ROLE_ID and hasattr(user, 'roles'):
                for role in user.roles:
                    if getattr(role, 'id', None) == config.MOD_ROLE_ID:
                        return True
        
        # Final fallback to permission checks
        if hasattr(user, 'guild_permissions'):
            return user.guild_permissions.manage_messages or user.guild_permissions.administrator
        
        return False
        
    except Exception as e:
        logger.error(f"Error checking if user is moderator: {e}")
        # Fallback to permission check on error
        if hasattr(user, 'guild_permissions'):
            return user.guild_permissions.manage_messages or user.guild_permissions.administrator
        return False


async def migrate_default_challenge_roles():
    """Migrate default challenge roles from config.py to the database for the primary guild."""
    try:
        primary_guild_id = int(os.getenv("GUILD_ID"))
        
        # Check if roles already exist for primary guild
        existing_roles = await get_guild_challenge_roles(primary_guild_id)
        
        if existing_roles:
            logger.info(f"Default challenge roles already exist for primary guild {primary_guild_id}")
            return
        
        # Migrate roles from config.CHALLENGE_ROLE_IDS
        logger.info(f"Migrating default challenge roles for primary guild {primary_guild_id}")
        
        for challenge_id, thresholds in config.CHALLENGE_ROLE_IDS.items():
            for threshold, role_id in thresholds.items():
                await set_guild_challenge_role(primary_guild_id, challenge_id, threshold, role_id)
                logger.info(f"Migrated: Challenge {challenge_id}, threshold {threshold} -> role {role_id}")
        
        logger.info(f"✅ Successfully migrated {len(config.CHALLENGE_ROLE_IDS)} default challenge roles")
        
    except Exception as e:
        logger.error(f"Error migrating default challenge roles: {e}", exc_info=True)


async def migrate_global_challenges_to_guild():
    """Migrate existing global challenges and challenge_manga to guild-specific tables for the primary guild."""
    try:
        primary_guild_id = int(os.getenv("GUILD_ID"))
        
        logger.info("="*60)
        logger.info("STARTING GLOBAL CHALLENGES MIGRATION")
        logger.info("="*60)
        
        async with aiosqlite.connect(DB_PATH) as db:
            # Check if guild-specific tables already have data
            cursor = await db.execute("SELECT COUNT(*) FROM guild_challenges WHERE guild_id = ?", (primary_guild_id,))
            existing_guild_challenges = (await cursor.fetchone())[0]
            
            if existing_guild_challenges > 0:
                logger.info(f"Guild-specific challenges already exist for primary guild {primary_guild_id} ({existing_guild_challenges} challenges)")
                return
            
            # Check the structure of global_challenges table to handle different schemas
            cursor = await db.execute("PRAGMA table_info(global_challenges)")
            columns = await cursor.fetchall()
            column_names = [col[1] for col in columns]
            
            # Build SELECT query based on available columns
            select_fields = ["challenge_id", "title"]
            if "difficulty" in column_names:
                select_fields.append("difficulty")
            if "start_date" in column_names:
                select_fields.append("start_date")
            
            # Get all global challenges for the primary guild (if guild_id exists) or all challenges (legacy)
            if "guild_id" in column_names:
                # Handle case where global_challenges already has guild_id column
                query = f"SELECT {', '.join(select_fields)} FROM global_challenges WHERE guild_id = ? OR guild_id IS NULL"
                cursor = await db.execute(query, (primary_guild_id,))
            else:
                # Handle legacy case where global_challenges has no guild_id
                query = f"SELECT {', '.join(select_fields)} FROM global_challenges"
                cursor = await db.execute(query)
            
            global_challenges = await cursor.fetchall()
            
            if not global_challenges:
                logger.info("No global challenges found to migrate")
                return
            
            logger.info(f"Found {len(global_challenges)} global challenges to migrate")
            
            # Migrate each challenge
            challenge_id_mapping = {}  # old_id -> new_id
            
            for challenge_data in global_challenges:
                old_challenge_id = challenge_data[0]
                title = challenge_data[1]
                
                # Insert into guild_challenges (only guild_id and title are required)
                cursor = await db.execute(
                    "INSERT INTO guild_challenges (guild_id, title) VALUES (?, ?)",
                    (primary_guild_id, title)
                )
                new_challenge_id = cursor.lastrowid
                challenge_id_mapping[old_challenge_id] = new_challenge_id
                
                logger.info(f"Migrated challenge: '{title}' (old ID: {old_challenge_id} -> new ID: {new_challenge_id})")
            
            # Get all challenge manga entries
            cursor = await db.execute("SELECT challenge_id, manga_id, title, total_chapters FROM challenge_manga")
            challenge_manga_entries = await cursor.fetchall()
            
            if challenge_manga_entries:
                logger.info(f"Found {len(challenge_manga_entries)} manga entries to migrate")
                
                # Migrate manga entries
                migrated_manga = 0
                for old_challenge_id, manga_id, manga_title, total_chapters in challenge_manga_entries:
                    if old_challenge_id in challenge_id_mapping:
                        new_challenge_id = challenge_id_mapping[old_challenge_id]
                        
                        # Insert into guild_challenge_manga
                        await db.execute(
                            "INSERT INTO guild_challenge_manga (guild_id, challenge_id, manga_id, title, total_chapters) VALUES (?, ?, ?, ?, ?)",
                            (primary_guild_id, new_challenge_id, manga_id, manga_title, total_chapters)
                        )
                        migrated_manga += 1
                        
                        logger.debug(f"Migrated manga: '{manga_title}' (ID: {manga_id}) to challenge {new_challenge_id}")
                    else:
                        logger.warning(f"Could not find mapping for challenge ID {old_challenge_id} for manga '{manga_title}' (ID: {manga_id})")
                
                logger.info(f"✅ Successfully migrated {migrated_manga} manga entries")
            
            await db.commit()
            
            logger.info("="*60)
            logger.info(f"✅ MIGRATION COMPLETED SUCCESSFULLY")
            logger.info(f"✅ Migrated {len(global_challenges)} challenges")
            logger.info(f"✅ Migrated {migrated_manga if challenge_manga_entries else 0} manga entries")
            logger.info(f"✅ All data moved to guild {primary_guild_id}")
            logger.info("="*60)
            
            # Optional: Create backup of global tables before cleanup
            logger.info("Creating backup of global challenge tables...")
            
            # Backup global_challenges
            await db.execute("""
                CREATE TABLE IF NOT EXISTS global_challenges_backup AS 
                SELECT * FROM global_challenges
            """)
            
            # Backup challenge_manga  
            await db.execute("""
                CREATE TABLE IF NOT EXISTS challenge_manga_backup AS 
                SELECT * FROM challenge_manga
            """)
            
            await db.commit()
            logger.info("✅ Backup tables created: global_challenges_backup, challenge_manga_backup")
            
            # Note: We don't automatically delete the old tables to be safe
            logger.info("🔸 Original global tables preserved for safety (global_challenges, challenge_manga)")
            logger.info("🔸 You can manually drop them after verifying the migration worked correctly")
            
    except Exception as e:
        logger.error(f"❌ Error during global challenges migration: {e}", exc_info=True)
        raise


# ------------------------------------------------------
# INITIALIZE ALL DATABASE TABLES with Enhanced Logging
# ------------------------------------------------------
async def init_db():
    """Initialize all database tables with comprehensive logging and error handling."""
    logger.info("="*60)
    logger.info("STARTING DATABASE INITIALIZATION")
    logger.info("="*60)
    
    # List of table initialization functions and their names
    table_init_functions = [
        ("Users", init_users_table),
        ("Challenge Rules", init_challenge_rules_table),
        ("Recommendation Votes", init_recommendation_votes_table),
        ("User Stats", init_user_stats_table),
        ("Achievements", init_achievements_table),
        ("User Manga Progress", init_user_manga_progress_table),
        ("Manga Challenges", init_manga_challenges_table),
        ("User Progress", init_user_progress_table),
        ("Global Challenges", init_global_challenges_table),
        ("Guild Challenges", init_guild_challenges_table),
        ("Guild Challenge Manga", init_guild_challenge_manga_table),
        ("Guild Challenge Roles", init_guild_challenge_roles_table),
        ("Guild Manga Channels", init_guild_manga_channels_table),
        ("Guild Bot Update Channels", init_guild_bot_update_channels_table),
        ("Guild Mod Roles", init_guild_mod_roles_table),
        ("Bot Moderators", init_bot_moderators_table),
        ("Invite Tracker", init_invite_tracker_tables),
        ("Steam Users", init_steam_users_table),
        ("Challenge Manga", init_challenge_manga_table),
    ]
    
    start_time = time.time()
    success_count = 0
    failure_count = 0
    
    try:
        # Verify database connectivity first
        logger.info("Verifying database connectivity...")
        async with aiosqlite.connect(DB_PATH, timeout=DB_TIMEOUT) as test_db:
            await test_db.execute("SELECT 1")
        logger.info("✅ Database connectivity verified")
        
        # Initialize each table
        for table_name, init_function in table_init_functions:
            try:
                logger.debug(f"Initializing {table_name} table...")
                await init_function()
                success_count += 1
                logger.debug(f"✅ {table_name} table initialized successfully")
                
            except Exception as table_error:
                failure_count += 1
                logger.error(f"❌ Failed to initialize {table_name} table: {table_error}", exc_info=True)
                # Continue with other tables instead of failing completely
        
        # Log final statistics
        total_time = time.time() - start_time
        total_tables = len(table_init_functions)
        
        logger.info("="*60)
        logger.info("DATABASE INITIALIZATION SUMMARY")
        logger.info(f"Total tables: {total_tables}")
        logger.info(f"Successfully initialized: {success_count}")
        logger.info(f"Failed to initialize: {failure_count}")
        logger.info(f"Total time: {total_time:.2f} seconds")
        
        if failure_count > 0:
            logger.warning(f"⚠️  {failure_count} tables failed to initialize - some functionality may be limited")
        else:
            logger.info("✅ All database tables initialized successfully")
        
        logger.info("="*60)
        
        # Log database file statistics
        if DB_PATH.exists():
            file_size = DB_PATH.stat().st_size
            logger.info(f"Final database file size: {file_size:,} bytes ({file_size / (1024*1024):.2f} MB)")
        
    except Exception as e:
        total_time = time.time() - start_time
        logger.error(f"❌ Fatal error during database initialization after {total_time:.2f}s: {e}", exc_info=True)
        raise


# ------------------------------------------------------
# MULTI-GUILD HELPER FUNCTIONS
# ------------------------------------------------------

async def get_user_progress_guild_aware(discord_id: int, guild_id: int):
    """Get user challenge progress for a specific guild."""
    logger.debug(f"Getting progress for user {discord_id} in guild {guild_id}")
    
    try:
        if not isinstance(discord_id, int) or discord_id <= 0:
            raise ValueError(f"Invalid discord_id: {discord_id}")
        if not isinstance(guild_id, int) or guild_id <= 0:
            raise ValueError(f"Invalid guild_id: {guild_id}")
        
        query = """
            SELECT up.*, gc.title as challenge_title
            FROM user_progress up
            LEFT JOIN global_challenges gc ON up.challenge_manga_id = gc.challenge_id
            WHERE up.user_id = ? AND up.guild_id = ?
        """
        
        progress = await execute_db_operation(
            f"get user progress for {discord_id} in guild {guild_id}",
            query,
            (discord_id, guild_id),
            fetch_type='all'
        )
        
        if progress:
            logger.debug(f"✅ Found {len(progress)} progress records for user {discord_id} in guild {guild_id}")
        else:
            logger.debug(f"No progress found for user {discord_id} in guild {guild_id}")
        
        return progress
        
    except ValueError as validation_error:
        logger.error(f"Validation error getting user progress: {validation_error}")
        raise
    except Exception as e:
        logger.error(f"❌ Unexpected error getting user progress for {discord_id} in guild {guild_id}: {e}", exc_info=True)
        raise


async def get_guild_leaderboard(guild_id: int, limit: int = 10):
    """Get leaderboard for a specific guild."""
    logger.debug(f"Getting leaderboard for guild {guild_id} (limit: {limit})")
    
    try:
        if not isinstance(guild_id, int) or guild_id <= 0:
            raise ValueError(f"Invalid guild_id: {guild_id}")
        if not isinstance(limit, int) or limit <= 0:
            raise ValueError(f"Invalid limit: {limit}")
        
        query = """
            SELECT u.username, 
                   COUNT(up.id) as completed_challenges,
                   SUM(CASE WHEN up.status = 'completed' THEN 1 ELSE 0 END) as total_points
            FROM users u
            LEFT JOIN user_progress up ON u.discord_id = up.user_id AND u.guild_id = up.guild_id
            WHERE u.guild_id = ?
            GROUP BY u.discord_id, u.username
            ORDER BY total_points DESC, completed_challenges DESC
            LIMIT ?
        """
        
        leaderboard = await execute_db_operation(
            f"get leaderboard for guild {guild_id}",
            query,
            (guild_id, limit),
            fetch_type='all'
        )
        
        if leaderboard:
            logger.debug(f"✅ Found {len(leaderboard)} users in leaderboard for guild {guild_id}")
        else:
            logger.debug(f"No users found in leaderboard for guild {guild_id}")
        
        return leaderboard
        
    except ValueError as validation_error:
        logger.error(f"Validation error getting guild leaderboard: {validation_error}")
        raise
    except Exception as e:
        logger.error(f"❌ Unexpected error getting leaderboard for guild {guild_id}: {e}", exc_info=True)
        raise


async def get_user_achievements_guild_aware(discord_id: int, guild_id: int):
    """Get user achievements for a specific guild."""
    logger.debug(f"Getting achievements for user {discord_id} in guild {guild_id}")
    
    try:
        if not isinstance(discord_id, int) or discord_id <= 0:
            raise ValueError(f"Invalid discord_id: {discord_id}")
        if not isinstance(guild_id, int) or guild_id <= 0:
            raise ValueError(f"Invalid guild_id: {guild_id}")
        
        query = """
            SELECT achievement, timestamp
            FROM achievements
            WHERE discord_id = ? AND guild_id = ?
            ORDER BY timestamp DESC
        """
        
        achievements = await execute_db_operation(
            f"get achievements for user {discord_id} in guild {guild_id}",
            query,
            (discord_id, guild_id),
            fetch_type='all'
        )
        
        if achievements:
            logger.debug(f"✅ Found {len(achievements)} achievements for user {discord_id} in guild {guild_id}")
        else:
            logger.debug(f"No achievements found for user {discord_id} in guild {guild_id}")
        
        return achievements
        
    except ValueError as validation_error:
        logger.error(f"Validation error getting user achievements: {validation_error}")
        raise
    except Exception as e:
        logger.error(f"❌ Unexpected error getting achievements for {discord_id} in guild {guild_id}: {e}", exc_info=True)
        raise


async def get_user_manga_progress_guild_aware(discord_id: int, guild_id: int, manga_id: int = None):
    """Get user manga progress for a specific guild."""
    logger.debug(f"Getting manga progress for user {discord_id} in guild {guild_id}")
    
    try:
        if not isinstance(discord_id, int) or discord_id <= 0:
            raise ValueError(f"Invalid discord_id: {discord_id}")
        if not isinstance(guild_id, int) or guild_id <= 0:
            raise ValueError(f"Invalid guild_id: {guild_id}")
        
        if manga_id:
            query = """
                SELECT * FROM user_manga_progress
                WHERE discord_id = ? AND guild_id = ? AND manga_id = ?
            """
            params = (discord_id, guild_id, manga_id)
            fetch_type = 'one'
        else:
            query = """
                SELECT * FROM user_manga_progress
                WHERE discord_id = ? AND guild_id = ?
                ORDER BY updated_at DESC
            """
            params = (discord_id, guild_id)
            fetch_type = 'all'
        
        progress = await execute_db_operation(
            f"get manga progress for user {discord_id} in guild {guild_id}",
            query,
            params,
            fetch_type=fetch_type
        )
        
        if progress:
            if manga_id:
                logger.debug(f"✅ Found manga progress for user {discord_id}, manga {manga_id} in guild {guild_id}")
            else:
                logger.debug(f"✅ Found {len(progress)} manga progress records for user {discord_id} in guild {guild_id}")
        else:
            logger.debug(f"No manga progress found for user {discord_id} in guild {guild_id}")
        
        return progress
        
    except ValueError as validation_error:
        logger.error(f"Validation error getting manga progress: {validation_error}")
        raise
    except Exception as e:
        logger.error(f"❌ Unexpected error getting manga progress for {discord_id} in guild {guild_id}: {e}", exc_info=True)
        raise


async def register_user_guild_aware(discord_id: int, guild_id: int, username: str, anilist_username: str = None, anilist_id: int = None):
    """Register a user in a specific guild (alias for add_user_guild_aware)."""
    logger.info(f"Registering user {username} (ID: {discord_id}) in guild {guild_id}")
    
    try:
        await add_user_guild_aware(discord_id, guild_id, username, anilist_username, anilist_id)
        logger.info(f"✅ Successfully registered user {username} in guild {guild_id}")
        return True
        
    except Exception as e:
        logger.error(f"❌ Failed to register user {discord_id} in guild {guild_id}: {e}")
        raise


async def is_user_registered_in_guild(discord_id: int, guild_id: int):
    """Check if a user is registered in a specific guild."""
    logger.debug(f"Checking if user {discord_id} is registered in guild {guild_id}")
    
    try:
        user = await get_user_guild_aware(discord_id, guild_id)
        is_registered = user is not None
        
        logger.debug(f"User {discord_id} registration status in guild {guild_id}: {is_registered}")
        return is_registered
        
    except Exception as e:
        logger.error(f"❌ Error checking user registration for {discord_id} in guild {guild_id}: {e}")
        return False


async def get_guild_user_count(guild_id: int):
    """Get the number of registered users in a guild."""
    logger.debug(f"Getting user count for guild {guild_id}")
    
    try:
        if not isinstance(guild_id, int) or guild_id <= 0:
            raise ValueError(f"Invalid guild_id: {guild_id}")
        
        query = "SELECT COUNT(*) FROM users WHERE guild_id = ?"
        result = await execute_db_operation(
            f"get user count for guild {guild_id}",
            query,
            (guild_id,),
            fetch_type='one'
        )
        
        count = result[0] if result else 0
        logger.debug(f"✅ Found {count} users in guild {guild_id}")
        return count
        
    except ValueError as validation_error:
        logger.error(f"Validation error getting guild user count: {validation_error}")
        raise
    except Exception as e:
        logger.error(f"❌ Unexpected error getting user count for guild {guild_id}: {e}", exc_info=True)
        raise


# ------------------------------------------------------
# GUILD-AWARE USER FUNCTIONS
# ------------------------------------------------------

async def save_user_guild_aware(discord_id: int, guild_id: int, username: str):
    """Save or update user with guild context - guild-aware version of save_user."""
    logger.info(f"Saving user (guild-aware): {username} (Discord ID: {discord_id}, Guild ID: {guild_id})")
    
    try:
        if not isinstance(discord_id, int) or discord_id <= 0:
            raise ValueError(f"Invalid discord_id: {discord_id}")
        if not isinstance(guild_id, int) or guild_id <= 0:
            raise ValueError(f"Invalid guild_id: {guild_id}")
        if not isinstance(username, str) or not username.strip():
            raise ValueError(f"Invalid username: {username}")
        
        # Check if user already exists in this guild
        existing_user = await get_user_guild_aware(discord_id, guild_id)
        operation_type = "update" if existing_user else "insert"
        
        query = """
            INSERT INTO users (discord_id, guild_id, username, updated_at)
            VALUES (?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(discord_id, guild_id) DO UPDATE SET 
                username=excluded.username,
                updated_at=CURRENT_TIMESTAMP
        """
        
        await execute_db_operation(
            f"save user {username} in guild {guild_id} ({operation_type})",
            query,
            (discord_id, guild_id, username.strip())
        )
        
        logger.info(f"✅ Successfully saved user: {username} in guild {guild_id} ({operation_type})")
        
    except ValueError as validation_error:
        logger.error(f"Validation error saving user: {validation_error}")
        raise
    except Exception as e:
        logger.error(f"❌ Error saving user {discord_id} in guild {guild_id}: {e}", exc_info=True)
        raise


async def upsert_user_stats_guild_aware(
    discord_id: int,
    guild_id: int,
    username: str,
    total_manga: int,
    total_anime: int,
    avg_manga_score: float,
    avg_anime_score: float,
    total_chapters: int = 0,
    total_episodes: int = 0,
    manga_completed: int = 0,
    anime_completed: int = 0
):
    """Upsert user stats with guild context using guild_id column for proper guild isolation."""
    logger.info(f"Upserting stats (guild-aware) for user {username} (Discord ID: {discord_id}, Guild ID: {guild_id})")
    
    try:
        async with aiosqlite.connect(DB_PATH, timeout=DB_TIMEOUT) as db:
            # Try to insert or update with guild_id
            await db.execute("""
                INSERT INTO user_stats (
                    discord_id, guild_id, username, total_manga, total_anime, 
                    avg_manga_score, avg_anime_score, total_chapters, total_episodes,
                    manga_completed, anime_completed
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT (discord_id, guild_id) DO UPDATE SET
                    username = excluded.username,
                    total_manga = excluded.total_manga,
                    total_anime = excluded.total_anime,
                    avg_manga_score = excluded.avg_manga_score,
                    avg_anime_score = excluded.avg_anime_score,
                    total_chapters = excluded.total_chapters,
                    total_episodes = excluded.total_episodes,
                    manga_completed = excluded.manga_completed,
                    anime_completed = excluded.anime_completed
            """, (
                discord_id, guild_id, username, total_manga, total_anime,
                avg_manga_score, avg_anime_score, total_chapters, total_episodes,
                manga_completed, anime_completed
            ))
            await db.commit()
            logger.info(f"✅ Successfully upserted guild-aware stats for {username} in guild {guild_id}")
            
    except aiosqlite.OperationalError as e:
        if "UNIQUE constraint failed" in str(e) or "no such column: guild_id" in str(e):
            # Fall back to global stats if guild_id column doesn't exist yet
            logger.warning(f"Guild-aware stats not available, falling back to global stats for user {discord_id}")
            return await upsert_user_stats(
                discord_id=discord_id,
                username=username,
                total_manga=total_manga,
                total_anime=total_anime,
                avg_manga_score=avg_manga_score,
                avg_anime_score=avg_anime_score,
                total_chapters=total_chapters,
                total_episodes=total_episodes,
                manga_completed=manga_completed,
                anime_completed=anime_completed
            )
        else:
            logger.error(f"Database error during guild-aware stats upsert: {e}")
            raise


async def get_guild_leaderboard_data(guild_id: int, leaderboard_type: str = "manga"):
    """Get leaderboard data for a specific guild"""
    logger.info(f"Getting {leaderboard_type} leaderboard data for guild {guild_id}")
    
    try:
        if not isinstance(guild_id, int) or guild_id <= 0:
            raise ValueError(f"Invalid guild_id: {guild_id}")
        if leaderboard_type not in ["manga", "anime", "combined", "chapters", "episodes", "manga_completed", "anime_completed"]:
            raise ValueError(f"Invalid leaderboard_type: {leaderboard_type}")

        query = """
            SELECT u.anilist_username, us.total_manga, us.total_anime, 
                   us.total_chapters, us.total_episodes, us.avg_manga_score, us.avg_anime_score,
                   us.manga_completed, us.anime_completed
            FROM users u 
            JOIN user_stats us ON u.discord_id = us.discord_id
            WHERE u.guild_id = ? AND u.anilist_username IS NOT NULL
        """
        
        results = await execute_db_operation(
            f"get {leaderboard_type} leaderboard for guild {guild_id}",
            query,
            (guild_id,),
            fetch_type='all'
        )
        
        if not results:
            logger.info(f"No leaderboard data found for guild {guild_id}")
            return []
        
        # Filter and sort based on leaderboard type
        leaderboard_data = []
        for row in results:
            # The SELECT may include added completed columns; safely unpack the first 7
            username, total_manga, total_anime, total_chapters, total_episodes, avg_manga_score, avg_anime_score = row[:7]

            # Pull completed counts if present (we added to SELECT)
            manga_completed = row[7] if len(row) > 7 else 0
            anime_completed = row[8] if len(row) > 8 else 0

            if leaderboard_type == "manga":
                score = total_manga or 0
                secondary_score = total_chapters or 0
            elif leaderboard_type == "anime":
                score = total_anime or 0
                secondary_score = total_episodes or 0
            elif leaderboard_type == "chapters":
                # Primary sort by total chapters read, secondary by number of manga titles
                score = total_chapters or 0
                secondary_score = total_manga or 0
            elif leaderboard_type == "episodes":
                # Primary sort by total episodes watched, secondary by number of anime titles
                score = total_episodes or 0
                secondary_score = total_anime or 0
            elif leaderboard_type == "manga_completed":
                # Primary sort by completed manga count, secondary by total manga titles
                score = manga_completed or 0
                secondary_score = total_manga or 0
            elif leaderboard_type == "anime_completed":
                # Primary sort by completed anime count, secondary by total anime titles
                score = anime_completed or 0
                secondary_score = total_anime or 0
            else:  # combined
                score = (total_manga or 0) + (total_anime or 0)
                secondary_score = (total_chapters or 0) + (total_episodes or 0)
            
            leaderboard_data.append({
                'username': username,
                'total_manga': total_manga or 0,
                'total_anime': total_anime or 0,
                'total_chapters': total_chapters or 0,
                'total_episodes': total_episodes or 0,
                'avg_manga_score': avg_manga_score or 0.0,
                'avg_anime_score': avg_anime_score or 0.0,
                'manga_completed': manga_completed or 0,
                'anime_completed': anime_completed or 0,
                'score': score,
                'secondary_score': secondary_score
            })
        
        # Sort by primary score, then secondary score
        leaderboard_data.sort(key=lambda x: (x['score'], x['secondary_score']), reverse=True)
        
        logger.info(f"✅ Retrieved {len(leaderboard_data)} entries for {leaderboard_type} leaderboard in guild {guild_id}")
        return leaderboard_data
        
    except ValueError as validation_error:
        logger.error(f"Validation error getting guild leaderboard: {validation_error}")
        raise
    except Exception as e:
        logger.error(f"❌ Error getting leaderboard data for guild {guild_id}: {e}", exc_info=True)
        raise


async def get_all_users_guild_aware(guild_id: int):
    """Get all users for a specific guild - guild-aware version of get_all_users"""
    logger.info(f"Getting all users for guild {guild_id}")
    
    try:
        if not isinstance(guild_id, int) or guild_id <= 0:
            raise ValueError(f"Invalid guild_id: {guild_id}")
        
        query = "SELECT * FROM users WHERE guild_id = ?"
        users = await execute_db_operation(
            f"get all users for guild {guild_id}",
            query,
            (guild_id,),
            fetch_type='all'
        )
        
        logger.info(f"✅ Retrieved {len(users) if users else 0} users for guild {guild_id}")
        return users or []
        
    except ValueError as validation_error:
        logger.error(f"Validation error getting guild users: {validation_error}")
        raise
    except Exception as e:
        logger.error(f"❌ Error getting users for guild {guild_id}: {e}", exc_info=True)
        raise


async def set_user_manga_progress_guild_aware(discord_id: int, guild_id: int, manga_id: int, chapter: int, rating: float):
    """Set user manga progress with guild context - guild-aware version."""
    logger.info(f"Setting manga progress (guild-aware) for user {discord_id}, manga {manga_id}, guild {guild_id}")
    
    try:
        # Validate input
        if not isinstance(discord_id, int) or discord_id <= 0:
            raise ValueError(f"Invalid discord_id: {discord_id}")
        if not isinstance(guild_id, int) or guild_id <= 0:
            raise ValueError(f"Invalid guild_id: {guild_id}")
        if not isinstance(manga_id, int) or manga_id <= 0:
            raise ValueError(f"Invalid manga_id: {manga_id}")
        if not isinstance(chapter, int) or chapter < 0:
            raise ValueError(f"Invalid chapter: {chapter}")
        if not isinstance(rating, (int, float)) or not (0 <= rating <= 10):
            logger.warning(f"Invalid rating {rating}, clamping to 0-10 range")
            rating = max(0, min(10, float(rating)))
        
        logger.debug(f"Progress data - Chapter: {chapter}, Rating: {rating}")
        
        query = """
            INSERT INTO user_manga_progress (discord_id, guild_id, manga_id, current_chapter, rating, updated_at)
            VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(discord_id, guild_id, manga_id) DO UPDATE SET
                current_chapter=excluded.current_chapter,
                rating=excluded.rating,
                updated_at=CURRENT_TIMESTAMP
        """
        
        await execute_db_operation(
            f"set manga progress for user {discord_id} in guild {guild_id}",
            query,
            (discord_id, guild_id, manga_id, chapter, rating)
        )
        
        logger.info(f"✅ Set manga {manga_id} progress for user {discord_id} in guild {guild_id}: Chapter {chapter}, Rating {rating}")
        
    except ValueError as validation_error:
        logger.error(f"Validation error setting manga progress: {validation_error}")
        raise
    except Exception as e:
        logger.error(f"❌ Error setting manga progress for user {discord_id} in guild {guild_id}: {e}", exc_info=True)
        raise


async def upsert_user_manga_progress_guild_aware(discord_id, guild_id, manga_id, title, chapters, points, status, repeat=0, started_at=None):
    """Upsert user manga progress with guild context - guild-aware version."""
    logger.info(f"Upserting manga progress (guild-aware) for user {discord_id}, manga {manga_id}, guild {guild_id}")
    
    try:
        # Validate input
        if not isinstance(discord_id, int) or discord_id <= 0:
            raise ValueError(f"Invalid discord_id: {discord_id}")
        if not isinstance(guild_id, int) or guild_id <= 0:
            raise ValueError(f"Invalid guild_id: {guild_id}")
        if not isinstance(manga_id, int) or manga_id <= 0:
            raise ValueError(f"Invalid manga_id: {manga_id}")
        if not isinstance(title, str) or not title.strip():
            raise ValueError(f"Invalid title: {title}")
        if not isinstance(chapters, int) or chapters < 0:
            raise ValueError(f"Invalid chapters: {chapters}")
        if not isinstance(points, (int, float)) or points < 0:
            raise ValueError(f"Invalid points: {points}")
        if not isinstance(status, str) or not status.strip():
            raise ValueError(f"Invalid status: {status}")
        if not isinstance(repeat, int) or repeat < 0:
            repeat = 0
        
        logger.debug(f"Manga progress data - Title: {title}, Chapters: {chapters}, Points: {points}, Status: {status}")
        
        query = """
            INSERT INTO user_manga_progress (
                discord_id, guild_id, manga_id, current_chapter, title, 
                points, status, repeat, started_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(discord_id, guild_id, manga_id) DO UPDATE SET
                current_chapter=excluded.current_chapter,
                title=excluded.title,
                points=excluded.points,
                status=excluded.status,
                repeat=excluded.repeat,
                started_at=COALESCE(excluded.started_at, user_manga_progress.started_at),
                updated_at=CURRENT_TIMESTAMP
        """
        
        await execute_db_operation(
            f"upsert manga progress for user {discord_id} in guild {guild_id}",
            query,
            (discord_id, guild_id, manga_id, chapters, title, points, status, repeat, started_at)
        )
        
        logger.info(f"✅ Upserted manga {manga_id} progress for user {discord_id} in guild {guild_id}: {chapters} chapters, {points} points")
        
    except ValueError as validation_error:
        logger.error(f"Validation error upserting manga progress: {validation_error}")
        raise
    except Exception as e:
        logger.error(f"❌ Error upserting manga progress for user {discord_id} in guild {guild_id}: {e}", exc_info=True)
        raise


async def get_guild_challenge_leaderboard_data(guild_id: int):
    """Get challenge leaderboard data for a specific guild"""
    logger.info(f"Getting challenge leaderboard data for guild {guild_id}")
    
    try:
        if not isinstance(guild_id, int) or guild_id <= 0:
            raise ValueError(f"Invalid guild_id: {guild_id}")
        
        query = """
            SELECT u.discord_id, COALESCE(SUM(ump.points), 0) AS total_points
            FROM users u
            LEFT JOIN user_manga_progress ump ON u.discord_id = ump.discord_id AND u.guild_id = ump.guild_id
            WHERE u.guild_id = ?
            GROUP BY u.discord_id
            HAVING total_points > 0
            ORDER BY total_points DESC
        """
        
        leaderboard_data = await execute_db_operation(
            f"get challenge leaderboard for guild {guild_id}",
            query,
            (guild_id,),
            fetch_type='all'
        )
        
        logger.info(f"✅ Retrieved {len(leaderboard_data) if leaderboard_data else 0} challenge leaderboard entries for guild {guild_id}")
        return leaderboard_data or []
        
    except ValueError as validation_error:
        logger.error(f"Validation error getting guild challenge leaderboard: {validation_error}")
        raise
    except Exception as e:
        logger.error(f"❌ Error getting challenge leaderboard for guild {guild_id}: {e}", exc_info=True)
        raise


# ------------------------------------------------------
# Guild Challenge Roles Management Functions
# ------------------------------------------------------

async def set_guild_challenge_role(guild_id: int, challenge_id: int, threshold: float, role_id: int):
    """Set a challenge role for a specific guild."""
    logger.info(f"Setting challenge role for guild {guild_id}, challenge {challenge_id}, threshold {threshold} -> role {role_id}")
    
    try:
        if not isinstance(guild_id, int) or guild_id <= 0:
            raise ValueError(f"Invalid guild_id: {guild_id}")
        if not isinstance(challenge_id, int) or challenge_id <= 0:
            raise ValueError(f"Invalid challenge_id: {challenge_id}")
        if not isinstance(role_id, int) or role_id <= 0:
            raise ValueError(f"Invalid role_id: {role_id}")
        if not isinstance(threshold, (int, float)) or threshold <= 0:
            raise ValueError(f"Invalid threshold: {threshold}")
        
        query = """
            INSERT OR REPLACE INTO guild_challenge_roles 
            (guild_id, challenge_id, threshold, role_id, updated_at)
            VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
        """
        
        await execute_db_operation(
            f"set challenge role for guild {guild_id}",
            query,
            (guild_id, challenge_id, threshold, role_id)
        )
        
        logger.info(f"✅ Set challenge role for guild {guild_id}, challenge {challenge_id} -> role {role_id}")
        
    except ValueError as validation_error:
        logger.error(f"Validation error setting guild challenge role: {validation_error}")
        raise
    except Exception as e:
        logger.error(f"❌ Error setting challenge role for guild {guild_id}: {e}", exc_info=True)
        raise


async def get_guild_challenge_roles(guild_id: int) -> Dict[int, Dict[float, int]]:
    """Get all challenge roles for a specific guild."""
    logger.info(f"Getting challenge roles for guild {guild_id}")
    
    try:
        if not isinstance(guild_id, int) or guild_id <= 0:
            raise ValueError(f"Invalid guild_id: {guild_id}")
        
        query = """
            SELECT challenge_id, threshold, role_id 
            FROM guild_challenge_roles 
            WHERE guild_id = ?
            ORDER BY challenge_id, threshold
        """
        
        result = await execute_db_operation(
            f"get challenge roles for guild {guild_id}",
            query,
            (guild_id,),
            fetch_type='all'
        )
        
        # Format as nested dictionary: {challenge_id: {threshold: role_id}}
        roles = {}
        if result:
            for challenge_id, threshold, role_id in result:
                if challenge_id not in roles:
                    roles[challenge_id] = {}
                roles[challenge_id][threshold] = role_id
        
        logger.info(f"✅ Retrieved {len(roles)} challenge role configurations for guild {guild_id}")
        return roles
        
    except ValueError as validation_error:
        logger.error(f"Validation error getting guild challenge roles: {validation_error}")
        raise
    except Exception as e:
        logger.error(f"❌ Error getting challenge roles for guild {guild_id}: {e}", exc_info=True)
        raise


async def remove_guild_challenge_role(guild_id: int, challenge_id: int, threshold: float = None):
    """Remove challenge role(s) for a specific guild."""
    logger.info(f"Removing challenge role for guild {guild_id}, challenge {challenge_id}, threshold {threshold}")
    
    try:
        if not isinstance(guild_id, int) or guild_id <= 0:
            raise ValueError(f"Invalid guild_id: {guild_id}")
        if not isinstance(challenge_id, int) or challenge_id <= 0:
            raise ValueError(f"Invalid challenge_id: {challenge_id}")
        
        if threshold is not None:
            # Remove specific threshold
            query = "DELETE FROM guild_challenge_roles WHERE guild_id = ? AND challenge_id = ? AND threshold = ?"
            params = (guild_id, challenge_id, threshold)
        else:
            # Remove all thresholds for this challenge
            query = "DELETE FROM guild_challenge_roles WHERE guild_id = ? AND challenge_id = ?"
            params = (guild_id, challenge_id)
        
        await execute_db_operation(
            f"remove challenge role for guild {guild_id}",
            query,
            params
        )
        
        logger.info(f"✅ Removed challenge role for guild {guild_id}, challenge {challenge_id}")
        
    except ValueError as validation_error:
        logger.error(f"Validation error removing guild challenge role: {validation_error}")
        raise
    except Exception as e:
        logger.error(f"❌ Error removing challenge role for guild {guild_id}: {e}", exc_info=True)
        raise


# ------------------------------------------------------
# Guild Manga Channels Management Functions
# ------------------------------------------------------

async def set_guild_manga_channel(guild_id: int, channel_id: int):
    """Set the manga completion channel for a specific guild."""
    logger.info(f"Setting manga channel for guild {guild_id} to channel {channel_id}")
    
    try:
        # Validate input
        if not isinstance(guild_id, int) or guild_id <= 0:
            raise ValueError(f"Invalid guild_id: {guild_id}")
        if not isinstance(channel_id, int) or channel_id <= 0:
            raise ValueError(f"Invalid channel_id: {channel_id}")
        
        query = """
            INSERT INTO guild_manga_channels (guild_id, channel_id, updated_at)
            VALUES (?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(guild_id) DO UPDATE SET
                channel_id=excluded.channel_id,
                updated_at=CURRENT_TIMESTAMP
        """
        
        await execute_db_operation(
            f"set manga channel for guild {guild_id}",
            query,
            (guild_id, channel_id)
        )
        
        logger.info(f"✅ Set manga channel for guild {guild_id} to channel {channel_id}")
        
    except ValueError as validation_error:
        logger.error(f"Validation error setting manga channel: {validation_error}")
        raise
    except Exception as e:
        logger.error(f"❌ Error setting manga channel for guild {guild_id}: {e}", exc_info=True)
        raise

async def get_guild_manga_channel(guild_id: int) -> Optional[int]:
    """Get the manga completion channel for a specific guild."""
    logger.debug(f"Getting manga channel for guild {guild_id}")
    
    try:
        if not isinstance(guild_id, int) or guild_id <= 0:
            raise ValueError(f"Invalid guild_id: {guild_id}")
        
        query = """
            SELECT channel_id FROM guild_manga_channels
            WHERE guild_id = ?
        """
        
        result = await execute_db_operation(
            f"get manga channel for guild {guild_id}",
            query,
            (guild_id,),
            fetch_type='one'
        )
        
        if result:
            channel_id = result[0]
            logger.debug(f"✅ Found manga channel {channel_id} for guild {guild_id}")
            return channel_id
        else:
            logger.debug(f"No manga channel configured for guild {guild_id}")
            return None
            
    except ValueError as validation_error:
        logger.error(f"Validation error getting manga channel: {validation_error}")
        raise
    except Exception as e:
        logger.error(f"❌ Error getting manga channel for guild {guild_id}: {e}", exc_info=True)
        raise

async def get_all_guild_manga_channels() -> Dict[int, int]:
    """Get all guild manga channel configurations."""
    logger.debug("Getting all guild manga channels")
    
    try:
        query = """
            SELECT guild_id, channel_id FROM guild_manga_channels
            ORDER BY guild_id
        """
        
        result = await execute_db_operation(
            "get all guild manga channels",
            query,
            fetch_type='all'
        )
        
        channels = {row[0]: row[1] for row in result} if result else {}
        
        logger.info(f"✅ Retrieved {len(channels)} guild manga channel configurations")
        return channels
        
    except Exception as e:
        logger.error(f"❌ Error getting all guild manga channels: {e}", exc_info=True)
        raise


# ============================================================
# Guild Bot Update Channels Functions
# ============================================================

async def set_guild_bot_update_channel(guild_id: int, channel_id: int):
    """Set or update the bot update channel for a guild."""
    try:
        logger.info(f"Setting bot update channel for guild {guild_id} to channel {channel_id}")
        
        query = """
            INSERT OR REPLACE INTO guild_bot_update_channels 
            (guild_id, channel_id, updated_at)
            VALUES (?, ?, CURRENT_TIMESTAMP)
        """
        
        result = await execute_db_operation(
            "set guild bot update channel",
            query,
            params=(guild_id, channel_id)
        )
        
        logger.info(f"✅ Successfully set bot update channel for guild {guild_id}")
        return result
        
    except Exception as e:
        logger.error(f"❌ Error setting bot update channel for guild {guild_id}: {e}", exc_info=True)
        raise


async def get_guild_bot_update_channel(guild_id: int) -> Optional[int]:
    """Get the bot update channel ID for a specific guild."""
    try:
        logger.info(f"Getting bot update channel for guild {guild_id}")
        
        query = """
            SELECT channel_id 
            FROM guild_bot_update_channels 
            WHERE guild_id = ?
        """
        
        result = await execute_db_operation(
            "get guild bot update channel",
            query,
            params=(guild_id,),
            fetch_type='one'
        )
        
        channel_id = result[0] if result else None
        
        if channel_id:
            logger.info(f"✅ Found bot update channel {channel_id} for guild {guild_id}")
        else:
            logger.info(f"ℹ️ No bot update channel configured for guild {guild_id}")
            
        return channel_id
        
    except Exception as e:
        logger.error(f"❌ Error getting bot update channel for guild {guild_id}: {e}", exc_info=True)
        raise


async def get_all_guild_bot_update_channels() -> Dict[int, int]:
    """Get all guild bot update channel configurations."""
    try:
        logger.info("Getting all guild bot update channel configurations")
        
        query = """
            SELECT guild_id, channel_id 
            FROM guild_bot_update_channels 
            ORDER BY guild_id
        """
        
        result = await execute_db_operation(
            "get all guild bot update channels",
            query,
            fetch_type='all'
        )
        
        channels = {row[0]: row[1] for row in result} if result else {}
        
        logger.info(f"✅ Retrieved {len(channels)} guild bot update channel configurations")
        return channels
        
    except Exception as e:
        logger.error(f"❌ Error getting all guild bot update channels: {e}", exc_info=True)
        raise


async def remove_guild_bot_update_channel(guild_id: int):
    """Remove the bot update channel configuration for a guild."""
    try:
        logger.info(f"Removing bot update channel for guild {guild_id}")
        
        query = """
            DELETE FROM guild_bot_update_channels 
            WHERE guild_id = ?
        """
        
        result = await execute_db_operation(
            "remove guild bot update channel",
            query,
            params=(guild_id,)
        )
        
        logger.info(f"✅ Successfully removed bot update channel for guild {guild_id}")
        return result
        
    except Exception as e:
        logger.error(f"❌ Error removing bot update channel for guild {guild_id}: {e}", exc_info=True)
        raise


async def get_challenge_role_ids_for_guild(guild_id: int) -> Dict[int, Dict[float, int]]:
    """
    Get challenge role IDs for a specific guild.
    Falls back to config.CHALLENGE_ROLE_IDS if guild has no custom configuration.
    """
    try:
        # Try to get guild-specific roles from database
        guild_roles = await get_guild_challenge_roles(guild_id)
        
        if guild_roles:
            logger.debug(f"Using database challenge roles for guild {guild_id}")
            return guild_roles
        
        # Check if this is the primary guild - use config as fallback
        primary_guild_id = int(os.getenv("GUILD_ID"))
        if guild_id == primary_guild_id:
            logger.debug(f"Using config fallback challenge roles for primary guild {guild_id}")
            return config.CHALLENGE_ROLE_IDS
        
        # For other guilds, return empty dict (no roles configured)
        logger.info(f"No challenge roles configured for guild {guild_id}")
        return {}
        
    except Exception as e:
        logger.error(f"Error getting challenge role IDs for guild {guild_id}: {e}", exc_info=True)
        # Return config as ultimate fallback
        return config.CHALLENGE_ROLE_IDS