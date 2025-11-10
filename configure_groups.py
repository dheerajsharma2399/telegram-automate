#!/usr/bin/env python3
"""
Quick Group Configuration Script
Run this to set up your Telegram group monitoring
"""

import asyncio
from database import Database
from config import DATABASE_URL

async def configure_groups():
    """Configure monitored groups interactively"""
    
    print("🔧 TELEGRAM GROUP CONFIGURATION")
    print("=" * 40)
    print()
    
    try:
        db = Database(DATABASE_URL)
        
        # Check current configuration
        current = db.get_config('monitored_groups')
        print(f"Current groups: {current or 'None configured'}")
        print()
        
        # Get user input
        print("📋 How to find your group usernames:")
        print("1. Open Telegram app")
        print("2. Go to your job group")
        print("3. Click group name → look for '@groupname'")
        print("4. Add bot to group: @your_bot_username")
        print()
        
        print("Enter your group usernames (comma-separated):")
        print("Examples: @jobgroup1,@techjobs,@hiring123")
        print("(Leave blank to skip)")
        
        groups_input = input("Groups: ").strip()
        
        if not groups_input:
            print("❌ No groups entered. Exiting.")
            return
        
        # Update configuration
        db.set_config('monitored_groups', groups_input)
        print(f"✅ Groups configured: {groups_input}")
        
        # Verify update
        updated = db.get_config('monitored_groups')
        print(f"✅ Verified in database: {updated}")
        
        print()
        print("🎉 Configuration complete!")
        print()
        print("📋 Next steps:")
        print("1. Make sure your bot is added to these groups")
        print("2. Test historical fetch:")
        print("   curl -X POST http://localhost:9501/api/fetch_historical_messages \\")
        print("     -H 'Content-Type: application/json' \\")
        print("     -d '{\"hours_back\": 12}'")
        print()
        print("3. Or use the web dashboard: http://localhost:9501")
        
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    asyncio.run(configure_groups())