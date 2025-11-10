#!/usr/bin/env python3
"""
Sync Environment Variables to Database
Fixes the disconnect between .env configuration and database lookup
"""

import asyncio
from database import Database
from config import DATABASE_URL, TELEGRAM_GROUP_USERNAMES, TELEGRAM_API_ID, TELEGRAM_API_HASH, TELEGRAM_PHONE

async def sync_env_to_database():
    """Sync .env configuration to database for historical message fetcher"""
    
    print("🔄 SYNCING ENVIRONMENT TO DATABASE")
    print("=" * 40)
    
    try:
        db = Database(DATABASE_URL)
        
        # Sync Telegram group usernames
        if TELEGRAM_GROUP_USERNAMES:
            groups_str = ','.join(TELEGRAM_GROUP_USERNAMES)
            db.set_config('monitored_groups', groups_str)
            print(f"✅ Groups synced: {groups_str}")
        else:
            print("❌ No TELEGRAM_GROUP_USERNAMES found in .env")
        
        # Sync other important config
        if TELEGRAM_API_ID:
            db.set_config('telegram_api_id', str(TELEGRAM_API_ID))
            print(f"✅ API ID synced: {TELEGRAM_API_ID}")
        
        if TELEGRAM_API_HASH:
            db.set_config('telegram_api_hash', TELEGRAM_API_HASH)
            print(f"✅ API Hash synced: {TELEGRAM_API_HASH[:10]}...")
        
        if TELEGRAM_PHONE:
            db.set_config('telegram_phone', TELEGRAM_PHONE)
            print(f"✅ Phone synced: {TELEGRAM_PHONE}")
        
        # Verify sync
        print("\n📋 VERIFICATION:")
        groups = db.get_config('monitored_groups')
        print(f"Database groups: {groups}")
        
        if groups and TELEGRAM_GROUP_USERNAMES:
            db_groups = groups.split(',')
            if set(db_groups) == set(TELEGRAM_GROUP_USERNAMES):
                print("✅ Groups successfully synced!")
            else:
                print("⚠️ Groups partially synced")
        else:
            print("❌ Sync failed")
        
        print("\n🧪 TESTING:")
        print("Now test historical fetch:")
        print("curl -X POST http://localhost:9501/api/fetch_historical_messages \\")
        print("  -H 'Content-Type: application/json' \\")
        print("  -d '{\"hours_back\": 12}'")
        
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    asyncio.run(sync_env_to_database())