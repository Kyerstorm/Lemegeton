#!/usr/bin/env python3
"""
Extract data_upload.zip to Railway volume at /app/data
Run this once after deploying with: railway run python extract_data_railway.py
"""

import os
import zipfile
import shutil
from pathlib import Path

def extract_data():
    """Extract uploaded data to Railway volume."""
    
    print("=" * 60)
    print("🚀 Railway Data Extractor")
    print("=" * 60)
    
    # Paths - look for zip in current directory or /app
    current_dir = Path.cwd()
    zip_path = current_dir / "data_upload.zip"
    
    # If running on Railway, data directory is /app/data
    # Otherwise use ./data for local testing
    if Path("/app/data").exists():
        data_dir = Path("/app/data")
    else:
        data_dir = current_dir / "data"
    
    print(f"\n🔍 Current directory: {current_dir}")
    print(f"📁 Target directory: {data_dir}")
    print(f"📦 Looking for archive at: {zip_path}")
    
    # Create data directory if it doesn't exist
    data_dir.mkdir(exist_ok=True, parents=True)
    
    # Check if zip file exists
    if not zip_path.exists():
        print(f"\n❌ ERROR: {zip_path} not found!")
        print("\n📋 Files found in current directory:")
        for item in sorted(current_dir.glob("*"))[:15]:
            if item.is_file() and not item.name.startswith('.'):
                print(f"  • {item.name}")
        
        print("\n📋 To fix this:")
        print("1. Make sure data_upload.zip is committed and pushed to git")
        print("2. Deploy to Railway with: railway up")
        print("3. Run this script again")
        
        return False
    
    print(f"✅ Found archive: {zip_path}")
    print(f"📊 Archive size: {zip_path.stat().st_size / 1024:.2f} KB")
    
    # Extract files
    print(f"\n📤 Extracting files to {data_dir}...")
    print("-" * 60)
    
    try:
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            file_list = zip_ref.namelist()
            print(f"📋 Found {len(file_list)} files in archive")
            
            for filename in file_list:
                print(f"  Extracting: {filename}...")
                zip_ref.extract(filename, data_dir)
                print(f"  ✓ {filename}")
            
        print("-" * 60)
        print(f"✅ Successfully extracted {len(file_list)} files!")
        
        # List extracted files
        print(f"\n📂 Files in {data_dir}:")
        for item in sorted(data_dir.glob("*")):
            if item.is_file():
                size = item.stat().st_size / 1024
                print(f"  • {item.name} ({size:.2f} KB)")
        
        print("\n" + "=" * 60)
        print("✅ Data extraction complete!")
        print("=" * 60)
        print("\n💡 Next steps:")
        print("1. Restart your bot: railway up --detach")
        print("2. Check logs: railway logs")
        print("3. Test in Discord with /help")
        
        return True
        
    except Exception as e:
        print(f"\n❌ ERROR during extraction: {e}")
        return False

if __name__ == "__main__":
    success = extract_data()
    exit(0 if success else 1)

