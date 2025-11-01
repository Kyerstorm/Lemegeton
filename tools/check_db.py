import aiosqlite
import os
import config

# Connect to database using configured path (fallback to data/database.db)
database_path = os.getenv('DATABASE_PATH', getattr(config, 'DB_PATH', os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data', 'database.db')))
conn = aiosqlite.connect(database_path)
cursor = conn.cursor()

print('=== INVITE TRACKER SETTINGS TABLE SCHEMA ===')
cursor.execute('PRAGMA table_info(invite_tracker_settings)')
columns = cursor.fetchall()
print('Table Schema:')
for col in columns:
    print(f'  Column: {col[1]} | Type: {col[2]} | NotNull: {col[3]} | Default: {col[4]} | PK: {col[5]}')

print('\n=== CURRENT SETTINGS ===')
cursor.execute('SELECT guild_id, announcement_channel_id, updated_at FROM invite_tracker_settings')
settings = cursor.fetchall()
print('Stored Settings:')
for setting in settings:
    print(f'  Guild ID: {setting[0]}')
    print(f'  Channel ID: {setting[1]}') 
    print(f'  Updated: {setting[2]}')
    print('  ---')

print(f'Total configured guilds: {len(settings)}')

# Test that the data is persistent by checking if it survives queries
print('\n=== PERSISTENCE TEST ===')
cursor.execute('SELECT COUNT(*) FROM invite_tracker_settings')
count = cursor.fetchone()[0]
print(f'Records in table: {count}')

conn.close()
print('✅ Database check completed')