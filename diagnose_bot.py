import asyncio
import os
import sys
from datetime import datetime
from database import Database
from config import DATABASE_URL

async def diagnose():
    print(f"🔍 Diagnostic run at: {datetime.now()}")
    print(f"📂 Current working directory: {os.getcwd()}")
    
    # 1. Check Log File
    log_path = os.path.join("logs", "app.log")
    if os.path.exists(log_path):
        mtime = os.path.getmtime(log_path)
        last_modified = datetime.fromtimestamp(mtime)
        print(f"📄 Log file found. Last modified: {last_modified}")
        print(f"   (Difference from now: {datetime.now() - last_modified})")
    else:
        print("❌ Log file NOT found.")

    # 2. Check Database Connection & Config
    try:
        print("\nChecking Database...")
        db = Database(DATABASE_URL)
        
        # Check monitoring status
        status = db.config.get_config('monitoring_status')
        print(f"✅ Database connected.")
        print(f"📊 Monitoring Status in DB: '{status}'")
        
        # Check pending commands
        pending = db.commands.get_pending_commands()
        print(f"📥 Pending commands: {len(pending)}")
        
        # Check last message
        with db.get_connection() as conn:
             with conn.cursor() as cursor:
                cursor.execute("SELECT MAX(created_at) FROM raw_messages")
                last_msg = cursor.fetchone()[0]
                print(f"📨 Last message stored at: {last_msg}")
                
    except Exception as e:
        print(f"❌ Database check failed: {e}")

if __name__ == "__main__":
    asyncio.run(diagnose())
