import aiosqlite
import os
import config

# Use configured DB path when available
db_path = os.getenv('DATABASE_PATH', getattr(config, 'DB_PATH', os.path.join('..', 'data', 'database.db')))
conn = aiosqlite.connect(db_path)
cursor = conn.cursor()

print("=== DATABASE ANALYSIS FOR PUBLIC BOT ===")
print()

# Get all tables
cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
tables = cursor.fetchall()

print("CURRENT TABLES:")
for table in tables:
    table_name = table[0]
    print(f"\n📋 TABLE: {table_name}")
    
    # Get table schema
    cursor.execute(f"PRAGMA table_info({table_name})")
    columns = cursor.fetchall()
    
    # Check if table has guild_id column
    has_guild_id = any(col[1] == 'guild_id' for col in columns)
    
    print(f"   Guild-Aware: {'✅ YES' if has_guild_id else '❌ NO'}")
    print("   Columns:")
    for col in columns:
        col_name, col_type, not_null, default, is_pk = col[1], col[2], col[3], col[4], col[5]
        pk_indicator = " (PK)" if is_pk else ""
        guild_indicator = " 🏰" if col_name == 'guild_id' else ""
        print(f"     • {col_name}: {col_type}{pk_indicator}{guild_indicator}")
    
    # Get sample data count
    cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
    count = cursor.fetchone()[0]
    print(f"   Records: {count}")

print("\n" + "="*60)
print("MULTI-GUILD READINESS ASSESSMENT:")
print("="*60)

# Analyze guild-awareness
guild_aware_tables = []
non_guild_tables = []

for table in tables:
    table_name = table[0]
    cursor.execute(f"PRAGMA table_info({table_name})")
    columns = cursor.fetchall()
    
    has_guild_id = any(col[1] == 'guild_id' for col in columns)
    
    if has_guild_id:
        guild_aware_tables.append(table_name)
    else:
        non_guild_tables.append(table_name)

print(f"✅ Guild-Aware Tables ({len(guild_aware_tables)}):")
for table in guild_aware_tables:
    print(f"   • {table}")

print(f"\n❌ Non-Guild-Aware Tables ({len(non_guild_tables)}):")
for table in non_guild_tables:
    print(f"   • {table}")

print(f"\n📊 SUMMARY:")
print(f"   Total Tables: {len(tables)}")
print(f"   Ready for Multi-Guild: {len(guild_aware_tables)}")
print(f"   Need Migration: {len(non_guild_tables)}")
print(f"   Readiness: {(len(guild_aware_tables)/len(tables)*100):.1f}%")

conn.close()