#!/usr/bin/env python3
"""Script to convert synchronous sqlite database functions to async aiosqlite."""

import sys
import re

def convert_file(filepath):
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    # Make functions async
    content = re.sub(r'^(def (?:init_db|set_mute_role_db|get_mute_role_db|add_mute_db|remove_mute_db|fetch_all_pending_mutes|fetch_active_mute|log_mute_action|set_lock_role_db|get_lock_role_db|add_lock_db|remove_lock_db|fetch_active_lock|log_lock_action)\()', r'async \1', content, flags=re.MULTILINE)

    # Convert conn = aiosqlite.connect() to async with
    content = re.sub(r'(\s+)conn = aiosqlite\.connect\((.*?)\)\s*\n(\s+)cur = conn\.cursor\(\)\s*\n', r'\1async with aiosqlite.connect(\2) as conn:\n', content, flags=re.MULTILINE)

    # Add await to execute calls
    content = re.sub(r'(\s+)cur\.execute\(', r'\1await conn.execute(', content)
    content = re.sub(r'(\s+)conn\.commit\(\)', r'\1await conn.commit()', content)

    # Remove conn.close() calls
    content = re.sub(r'\s+conn\.close\(\)\s*\n', '', content)

    # Fix fetchone/fetchall
    content = re.sub(r'row = cur\.fetchone\(\)', r'row = await cursor.fetchone()', content)
    content = re.sub(r'rows = cur\.fetchall\(\)', r'rows = await cursor.fetchall()', content)

    # Need to get cursor from execute
    content = re.sub(r'await conn\.execute\((.*?)\)\s*\n(\s+)(row|rows) = await cursor\.',
                     r'async with await conn.execute(\1) as cursor:\n\2\3 = await cursor.',
                     content)

    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(content)

    print(f"Converted {filepath}")

if __name__ == "__main__":
    for filepath in sys.argv[1:]:
        convert_file(filepath)
