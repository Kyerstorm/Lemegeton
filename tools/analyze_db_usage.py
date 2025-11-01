"""Analyze database table and column usage"""
import aiosqlite
import os
import re
from pathlib import Path

DB_PATH = Path("data/database.db")
PROJECT_ROOT = Path(".")

def get_all_tables_and_columns():
    """Get all tables and their columns from the database"""
    conn = aiosqlite.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
    tables = cursor.fetchall()
    
    table_info = {}
    for table_name in tables:
        table_name = table_name[0]
        cursor.execute(f"PRAGMA table_info({table_name})")
        columns = cursor.fetchall()
        table_info[table_name] = {
            'columns': [col[1] for col in columns],
            'column_details': columns
        }
    
    conn.close()
    return table_info

def search_codebase_for_usage(pattern):
    """Search all Python files for a pattern"""
    matches = []
    for py_file in PROJECT_ROOT.rglob("*.py"):
        if '__pycache__' in str(py_file) or 'tools' in str(py_file):
            continue
        try:
            with open(py_file, 'r', encoding='utf-8') as f:
                content = f.read()
                if re.search(pattern, content, re.IGNORECASE):
                    matches.append(str(py_file))
        except Exception as e:
            pass
    return matches

def analyze_table_usage(table_info):
    """Analyze which tables and columns are used in the codebase"""
    print("=" * 80)
    print("DATABASE USAGE ANALYSIS")
    print("=" * 80)
    print()
    
    unused_tables = []
    unused_columns = {}
    
    for table_name, info in sorted(table_info.items()):
        # Check if table is referenced
        table_pattern = f"(FROM|INTO|TABLE|JOIN)\\s+{table_name}"
        table_uses = search_codebase_for_usage(table_pattern)
        
        print(f"\n📊 TABLE: {table_name}")
        print(f"   Columns: {len(info['columns'])}")
        
        if not table_uses:
            print(f"   ❌ UNUSED TABLE - Not found in codebase!")
            unused_tables.append(table_name)
        else:
            print(f"   ✅ Used in {len(table_uses)} file(s)")
            
            # Check columns
            unused_cols = []
            for col_name in info['columns']:
                if col_name in ['id', 'created_at', 'updated_at']:  # Skip common columns
                    continue
                col_pattern = f"{col_name}"
                col_uses = search_codebase_for_usage(col_pattern)
                
                if not col_uses:
                    unused_cols.append(col_name)
            
            if unused_cols:
                print(f"   ⚠️  Unused columns: {', '.join(unused_cols)}")
                unused_columns[table_name] = unused_cols
    
    print("\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80)
    print(f"\n📋 Total tables: {len(table_info)}")
    print(f"❌ Unused tables: {len(unused_tables)}")
    if unused_tables:
        print(f"   - {', '.join(unused_tables)}")
    
    print(f"\n⚠️  Tables with unused columns: {len(unused_columns)}")
    for table, cols in unused_columns.items():
        print(f"   - {table}: {', '.join(cols)}")
    
    return unused_tables, unused_columns

def get_table_row_counts():
    """Get row counts for all tables"""
    conn = aiosqlite.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = cursor.fetchall()
    
    print("\n" + "=" * 80)
    print("TABLE ROW COUNTS")
    print("=" * 80)
    
    for table_name in sorted([t[0] for t in tables]):
        try:
            cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
            count = cursor.fetchone()[0]
            status = "📦 Empty" if count == 0 else f"📊 {count} rows"
            print(f"{table_name:40} {status}")
        except Exception as e:
            print(f"{table_name:40} ❌ Error: {e}")
    
    conn.close()

if __name__ == "__main__":
    table_info = get_all_tables_and_columns()
    unused_tables, unused_columns = analyze_table_usage(table_info)
    get_table_row_counts()
