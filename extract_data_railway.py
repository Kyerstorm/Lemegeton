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
    
    # Paths
    zip_path = Path("/app/data_upload.zip")
    data_dir = Path("/app/data")
    
    # Create data directory if it doesn't exist
    data_dir.mkdir(exist_ok=True, parents=True)
    
    print(f"\n📁 Target directory: {data_dir}")
    print(f"📦 Archive path: {zip_path}")
    
    # Check if zip file exists
    if not zip_path.exists():
        print(f"\n❌ ERROR: {zip_path} not found!")
        print("\n📋 Instructions:")
        print("1. Upload data_upload.zip to your Railway deployment")
        print("2. Place it in /app/data_upload.zip")
        print("3. Run this script again")
        
        # Show current files
        print(f"\n📂 Files in /app:")
        for item in Path("/app").glob("*"):
            print(f"  • {item.name}")
        
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

