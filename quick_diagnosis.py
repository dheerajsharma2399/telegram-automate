#!/usr/bin/env python3
"""
Quick Diagnostic Script for Telegram Monitoring Issues
Run this inside your Docker container to diagnose message capture problems
"""

import asyncio
import os
import sys
from database import Database
from config import DATABASE_URL, TELEGRAM_BOT_TOKEN, ADMIN_USER_ID
import aiohttp
import json
from datetime import datetime, timedelta

async def quick_diagnosis():
    print("🔍 TELEGRAM MONITORING - QUICK DIAGNOSIS")
    print("=" * 50)
    
    # 1. Database Connection Check
    try:
        db = Database(DATABASE_URL)
        print("✅ Database connection: OK")
    except Exception as e:
        print(f"❌ Database connection failed: {e}")
        return
    
    # 2. Telegram Connection Status
    try:
        status = db.get_telegram_login_status()
        print(f"📱 Telegram status: {status}")
        
        # Check if session exists
        session = db.get_telegram_session()
        if session and len(session) > 10:
            print("✅ Session string exists")
        else:
            print("❌ No valid session found")
    except Exception as e:
        print(f"❌ Telegram status check failed: {e}")
    
    # 3. Monitored Groups Check
    try:
        groups = db.get_config('monitored_groups')
        if groups:
            print(f"👥 Monitored groups: {groups}")
        else:
            print("⚠️ No groups configured in database")
    except Exception as e:
        print(f"❌ Groups check failed: {e}")
    
    # 4. Message Statistics (Today)
    try:
        import psycopg2
        from psycopg2.extras import RealDictCursor
        
        conn = psycopg2.connect(DATABASE_URL)
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        # Total messages today
        cur.execute("""
            SELECT COUNT(*) as count 
            FROM raw_messages 
            WHERE DATE(created_at) = CURRENT_DATE
        """)
        total_today = cur.fetchone()['count']
        
        # Unprocessed messages
        cur.execute("""
            SELECT COUNT(*) as count 
            FROM raw_messages 
            WHERE status = 'unprocessed' AND DATE(created_at) = CURRENT_DATE
        """)
        unprocessed_today = cur.fetchone()['count']
        
        # Processed messages
        cur.execute("""
            SELECT COUNT(*) as count 
            FROM raw_messages 
            WHERE status = 'processed' AND DATE(created_at) = CURRENT_DATE
        """)
        processed_today = cur.fetchone()['count']
        
        # Failed messages
        cur.execute("""
            SELECT COUNT(*) as count 
            FROM raw_messages 
            WHERE status = 'failed' AND DATE(created_at) = CURRENT_DATE
        """)
        failed_today = cur.fetchone()['count']
        
        print(f"📊 Messages today:")
        print(f"   Total: {total_today}")
        print(f"   Unprocessed: {unprocessed_today}")
        print(f"   Processed: {processed_today}")
        print(f"   Failed: {failed_today}")
        
        if total_today == 0:
            print("⚠️ No messages captured today!")
        
        if failed_today > 0:
            print(f"⚠️ {failed_today} messages failed to process!")
        
        # Last 5 messages
        cur.execute("""
            SELECT message_id, status, message_text, created_at, error_message
            FROM raw_messages 
            WHERE DATE(created_at) = CURRENT_DATE
            ORDER BY created_at DESC 
            LIMIT 5
        """)
        recent = cur.fetchall()
        
        if recent:
            print(f"📝 Last 5 messages:")
            for msg in recent:
                text_preview = (msg['message_text'] or '')[:50].replace('\n', ' ')
                error_info = f" (Error: {msg['error_message']})" if msg['error_message'] else ""
                print(f"   ID {msg['message_id']}: {msg['status']} - {text_preview}...{error_info}")
        
        conn.close()
        
    except Exception as e:
        print(f"❌ Message statistics failed: {e}")
    
    # 5. Processing Status
    try:
        processing_status = db.get_config('monitoring_status')
        print(f"⚙️ Processing status: {processing_status}")
        
        # Check job processing today
        import psycopg2
        from psycopg2.extras import RealDictCursor
        conn = psycopg2.connect(DATABASE_URL)
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        cur.execute("""
            SELECT COUNT(*) as count
            FROM processed_jobs
            WHERE DATE(created_at) = CURRENT_DATE
        """)
        jobs_processed = cur.fetchone()['count']
        
        print(f"✅ Jobs processed today: {jobs_processed}")
        
        conn.close()
        
    except Exception as e:
        print(f"❌ Processing status failed: {e}")
    
    # 6. Web Server Health Check
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get('http://localhost:9501/health') as response:
                if response.status == 200:
                    print("🌐 Web server: Running")
                else:
                    print(f"⚠️ Web server: HTTP {response.status}")
    except Exception as e:
        print(f"⚠️ Web server: Not responding ({e})")
    
    # 7. Bot Connection Test
    try:
        if TELEGRAM_BOT_TOKEN and ADMIN_USER_ID:
            url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getMe"
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as response:
                    if response.status == 200:
                        data = await response.json()
                        if data.get('ok'):
                            bot_info = data.get('result', {})
                            print(f"🤖 Bot: Connected (@{bot_info.get('username', 'unknown')})")
                        else:
                            print(f"❌ Bot API: {data.get('description', 'Unknown error')}")
                    else:
                        print(f"❌ Bot API: HTTP {response.status}")
    except Exception as e:
        print(f"⚠️ Bot connection: Failed to check ({e})")
    
    print("\n" + "=" * 50)
    print("🏁 DIAGNOSIS COMPLETE")
    
    # Recommendations
    if total_today == 0:
        print("\n💡 RECOMMENDATIONS:")
        print("1. Check if bot is added to the groups")
        print("2. Verify monitored groups are set correctly")
        print("3. Check Telegram connection status")
        print("4. Restart the bot container")
    
    elif failed_today > 0:
        print(f"\n💡 RECOMMENDATIONS:")
        print(f"1. {failed_today} messages failed to process - check error messages")
        print("2. Check LLM API key and quota")
        print("3. Check database connectivity")
    
    elif unprocessed_today > processed_today:
        print(f"\n💡 RECOMMENDATIONS:")
        print("1. Trigger manual processing: /process")
        print("2. Check if processing scheduler is running")
        print("3. Verify OpenRouter API key and quota")

if __name__ == "__main__":
    asyncio.run(quick_diagnosis())