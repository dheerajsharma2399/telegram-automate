#!/usr/bin/env python3
"""
Check if Telegram API monitoring is capturing new messages
"""

import asyncio
import logging
from datetime import datetime, timedelta
from database import Database
from config import DATABASE_URL

# Setup logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

async def check_monitoring_status():
    """Check if monitoring is capturing new messages"""
    print("🔍 CHECKING TELEGRAM API MONITORING STATUS")
    print("=" * 60)
    
    db = Database(DATABASE_URL)
    
    try:
        # Check monitoring service status
        service_status = db.get_config('monitoring_service_status') or 'unknown'
        service_started = db.get_config('monitoring_service_started')
        monitoring_status = db.get_config('monitoring_status') or 'unknown'
        
        print(f"📡 **Monitoring Service Status:** {service_status}")
        if service_started:
            print(f"🕐 **Service Started:** {service_started[:19]}")
        print(f"⚙️ **Auto Processing Status:** {monitoring_status}")
        
        # Check recent messages (last 5 minutes)
        print(f"\n📊 CHECKING RECENT MESSAGE CAPTURE (Last 5 minutes)")
        print("-" * 50)
        
        recent_cutoff = datetime.now() - timedelta(minutes=5)
        
        with db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, message_id, message_text, created_at, status
                FROM raw_messages 
                WHERE created_at >= %s
                ORDER BY created_at DESC
            """, (recent_cutoff,))
            recent_messages = cursor.fetchall()
        
        print(f"📨 **Messages captured in last 5 minutes:** {len(recent_messages)}")
        
        if recent_messages:
            print("📝 **Recent messages:**")
            for msg_id, message_id, text, created_at, status in recent_messages[:5]:
                preview = text[:80] + "..." if len(text) > 80 else text
                print(f"   • {created_at.strftime('%H:%M:%S')}: ID {message_id} - {status}")
                print(f"     Content: {preview}")
        else:
            print("⏳ No new messages in last 5 minutes")
            print("   💡 This is normal if no job messages posted recently")
        
        # Check unprocessed messages
        unprocessed_count = db.get_unprocessed_count()
        print(f"\n📋 **Unprocessed Messages:** {unprocessed_count}")
        
        if unprocessed_count > 0:
            with db.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT id, message_id, message_text, created_at
                    FROM raw_messages 
                    WHERE status = 'unprocessed'
                    ORDER BY created_at ASC
                    LIMIT 3
                """)
                unprocessed_samples = cursor.fetchall()
            
            print("📝 **Sample unprocessed messages:**")
            for msg_id, message_id, text, created_at in unprocessed_samples:
                preview = text[:80] + "..." if len(text) > 80 else text
                print(f"   • {created_at.strftime('%H:%M:%S')}: ID {message_id}")
                print(f"     Content: {preview}")
        
        # Check job processing stats
        jobs_today = db.get_jobs_today_stats()
        print(f"\n💼 **Jobs Processed Today:**")
        print(f"   Total: {jobs_today.get('total', 0)}")
        print(f"   With Email: {jobs_today.get('with_email', 0)}")
        print(f"   Without Email: {jobs_today.get('without_email', 0)}")
        
        # Overall assessment
        print(f"\n🎯 **MONITORING STATUS ASSESSMENT**")
        print("=" * 60)
        
        if service_status == 'running':
            print("✅ **Telegram API monitoring is ACTIVE**")
        elif service_status == 'not_started':
            print("❌ **Monitoring service not started**")
        elif service_status == 'failed':
            print("❌ **Monitoring service failed**")
        else:
            print(f"⚠️ **Monitoring service status: {service_status}**")
        
        if len(recent_messages) > 0:
            print("✅ **Recent messages are being captured**")
        else:
            print("⏳ **No recent messages (may be normal if no job posts)**")
        
        if unprocessed_count > 0:
            print(f"✅ **Message processing queue: {unprocessed_count} messages**")
        
        print(f"\n💡 **Next Steps:**")
        if service_status == 'running':
            print("   • Monitoring is working - forward a test job message")
            print("   • Check if it gets captured within 2-5 seconds")
            print("   • Verify enhanced forwarded message detection")
        else:
            print("   • Start the monitoring service: python monitoring_service.py")
            print("   • Verify Telegram session is valid")
            print("   • Check Premium Referrals group access")
        
    except Exception as e:
        print(f"❌ Error checking monitoring status: {e}")

if __name__ == "__main__":
    asyncio.run(check_monitoring_status())