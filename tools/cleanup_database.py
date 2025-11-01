"""
Database Cleanup Script
Safely removes unused tables, columns, and optimizes the database
"""
import aiosqlite
import shutil
from pathlib import Path
from datetime import datetime

DB_PATH = Path("data/database.db")
BACKUP_PATH = Path("data/database.backup")

def create_backup():
    """Create a backup before making changes"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_file = Path(f"data/database_backup_{timestamp}.db")
    shutil.copy2(DB_PATH, backup_file)
    print(f"✅ Created backup: {backup_file}")
    return backup_file

def drop_unused_tables(conn):
    """Drop tables that are no longer used"""
    cursor = conn.cursor()
    
    tables_to_drop = [
        'challenge_manga_backup',
        'global_challenges_backup',
        'challenges',  # Legacy - superseded by guild_challenges
        'manga_challenges',  # Legacy - superseded by guild_challenge_manga
    ]
    
    print("\n🗑️  Dropping unused tables:")
    for table in tables_to_drop:
        try:
            cursor.execute(f"DROP TABLE IF EXISTS {table}")
            print(f"   ✅ Dropped: {table}")
        except Exception as e:
            print(f"   ❌ Error dropping {table}: {e}")
    
    conn.commit()

def drop_unused_columns(conn):
    """Drop unused columns (requires table recreation in SQLite)"""
    cursor = conn.cursor()
    
    print("\n⚠️  Removing unused columns from cached_stats:")
    
    try:
        # Check if table exists
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='cached_stats'")
        if not cursor.fetchone():
            print("   ⚠️  cached_stats table doesn't exist, skipping...")
            return
        
        # Create new table without unused columns
        cursor.execute("""
            CREATE TABLE cached_stats_new (
                discord_id INTEGER PRIMARY KEY,
                guild_id INTEGER,
                username TEXT,
                anilist_username TEXT,
                total_manga INTEGER DEFAULT 0,
                total_anime INTEGER DEFAULT 0,
                avg_manga_score REAL DEFAULT 0,
                avg_anime_score REAL DEFAULT 0,
                total_chapters INTEGER DEFAULT 0,
                total_episodes INTEGER DEFAULT 0,
                last_updated TEXT
            )
        """)
        
        # Copy data (excluding unused columns)
        cursor.execute("""
            INSERT INTO cached_stats_new 
            SELECT discord_id, guild_id, username, anilist_username,
                   total_manga, total_anime, avg_manga_score, avg_anime_score,
                   total_chapters, total_episodes, last_updated
            FROM cached_stats
        """)
        
        # Drop old and rename new
        cursor.execute("DROP TABLE cached_stats")
        cursor.execute("ALTER TABLE cached_stats_new RENAME TO cached_stats")
        
        print("   ✅ Removed 5 unused columns from cached_stats")
        conn.commit()
        
    except Exception as e:
        print(f"   ❌ Error: {e}")
        conn.rollback()
    
    # Remove unused column from user_progress_checkpoint
    print("\n⚠️  Removing unused column from user_progress_checkpoint:")
    try:
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='user_progress_checkpoint'")
        if not cursor.fetchone():
            print("   ⚠️  user_progress_checkpoint table doesn't exist, skipping...")
            return
            
        cursor.execute("""
            CREATE TABLE user_progress_checkpoint_new (
                discord_id INTEGER PRIMARY KEY,
                last_updated TEXT
            )
        """)
        
        cursor.execute("""
            INSERT INTO user_progress_checkpoint_new 
            SELECT discord_id, last_updated
            FROM user_progress_checkpoint
        """)
        
        cursor.execute("DROP TABLE user_progress_checkpoint")
        cursor.execute("ALTER TABLE user_progress_checkpoint_new RENAME TO user_progress_checkpoint")
        
        print("   ✅ Removed last_manga_id column from user_progress_checkpoint")
        conn.commit()
        
    except Exception as e:
        print(f"   ❌ Error: {e}")
        conn.rollback()

def add_indexes(conn):
    """Add performance indexes"""
    cursor = conn.cursor()
    
    indexes = [
        ("idx_users_guild_id", "users", "guild_id"),
        ("idx_user_stats_guild_id", "user_stats", "guild_id"),
        ("idx_user_manga_progress_lookup", "user_manga_progress", "discord_id, guild_id"),
        ("idx_user_manga_progress_updated", "user_manga_progress", "updated_at"),
        ("idx_guild_challenge_manga_lookup", "guild_challenge_manga", "guild_id, challenge_id"),
        ("idx_achievements_lookup", "achievements", "discord_id, guild_id"),
        ("idx_steam_users_lookup", "steam_users", "discord_id"),
    ]
    
    print("\n📈 Adding performance indexes:")
    for idx_name, table, columns in indexes:
        try:
            cursor.execute(f"CREATE INDEX IF NOT EXISTS {idx_name} ON {table}({columns})")
            print(f"   ✅ Created index: {idx_name} on {table}({columns})")
        except Exception as e:
            print(f"   ⚠️  {idx_name}: {e}")
    
    conn.commit()

def vacuum_database(conn):
    """Vacuum database to reclaim space"""
    print("\n🧹 Vacuuming database to reclaim space...")
    try:
        conn.execute("VACUUM")
        print("   ✅ Database vacuumed successfully")
    except Exception as e:
        print(f"   ❌ Error vacuuming: {e}")

def get_database_stats(conn):
    """Get database statistics"""
    cursor = conn.cursor()
    
    print("\n📊 Database Statistics:")
    
    cursor.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='table'")
    table_count = cursor.fetchone()[0]
    print(f"   Tables: {table_count}")
    
    cursor.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='index' AND name NOT LIKE 'sqlite_%'")
    index_count = cursor.fetchone()[0]
    print(f"   Indexes: {index_count}")
    
    # Get database size
    cursor.execute("SELECT page_count * page_size as size FROM pragma_page_count(), pragma_page_size()")
    size = cursor.fetchone()[0]
    size_mb = size / (1024 * 1024)
    print(f"   Size: {size_mb:.2f} MB")

def main():
    """Main cleanup function"""
    print("=" * 80)
    print("DATABASE CLEANUP SCRIPT")
    print("=" * 80)
    
    if not DB_PATH.exists():
        print(f"❌ Database not found: {DB_PATH}")
        return
    
    # Create backup
    backup_file = create_backup()
    
    # Connect to database
    conn = aiosqlite.connect(DB_PATH)
    
    try:
        # Get before stats
        print("\n📊 BEFORE CLEANUP:")
        get_database_stats(conn)
        
        # Perform cleanup
        drop_unused_tables(conn)
        drop_unused_columns(conn)
        add_indexes(conn)
        vacuum_database(conn)
        
        # Get after stats
        print("\n📊 AFTER CLEANUP:")
        get_database_stats(conn)
        
        print("\n" + "=" * 80)
        print("✅ CLEANUP COMPLETED SUCCESSFULLY")
        print("=" * 80)
        print(f"\n💾 Backup saved at: {backup_file}")
        print("   You can restore from backup if needed: ")
        print(f"   copy {backup_file} {DB_PATH}")
        
    except Exception as e:
        print(f"\n❌ Error during cleanup: {e}")
        print("   Rolling back changes...")
        conn.rollback()
        print(f"   Restore from backup: copy {backup_file} {DB_PATH}")
    
    finally:
        conn.close()

if __name__ == "__main__":
    main()
