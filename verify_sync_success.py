#!/usr/bin/env python3
"""
Verify that the .env to database sync was successful
"""

import asyncio
from database import Database
from config import DATABASE_URL, TELEGRAM_GROUP_USERNAMES

async def verify_sync():
    print("✅ SYNC VERIFICATION REPORT")
    print("=" * 30)
    
    try:
        db = Database(DATABASE_URL)
        
        # Check .env configuration
        print("📋 .ENV Configuration:")
        print(f"   TELEGRAM_GROUP_USERNAMES: {TELEGRAM_GROUP_USERNAMES}")
        
        # Check database configuration
        print("\n💾 Database Configuration:")
        groups = db.get_config('monitored_groups')
        print(f"   monitored_groups: {groups}")
        
        # Verify sync
        if groups and TELEGRAM_GROUP_USERNAMES:
            db_groups = groups.split(',')
            if set(db_groups) == set(TELEGRAM_GROUP_USERNAMES):
                print("\n🎉 SYNC SUCCESSFUL!")
                print("   ✅ Groups properly synced from .env to database")
                print("   ✅ Historical message fetcher will now work")
                
                print("\n📱 Ready to Use:")
                print("1. Web Dashboard: http://localhost:9501")
                print("2. API Test: POST /api/fetch_historical_messages")
                print("3. Manual Test: python quick_historical_debug.py")
                
            else:
                print("\n⚠️ PARTIAL SYNC")
                print(f"   Expected: {TELEGRAM_GROUP_USERNAMES}")
                print(f"   Got: {db_groups}")
        else:
            print("\n❌ SYNC FAILED")
            if not groups:
                print("   - No groups in database")
            if not TELEGRAM_GROUP_USERNAMES:
                print("   - No groups in .env")
        
    except Exception as e:
        print(f"❌ Verification error: {e}")

if __name__ == "__main__":
    asyncio.run(verify_sync())