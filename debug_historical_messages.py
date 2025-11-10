#!/usr/bin/env python3
"""
Debug Historical Message Detection
Comprehensive debugging to find out WHY historical messages aren't being detected
"""

import asyncio
import logging
from datetime import datetime, timedelta
from database import Database
from config import DATABASE_URL, TELEGRAM_API_ID, TELEGRAM_API_HASH, TELEGRAM_PHONE
from message_utils import extract_message_text, get_message_info
from telethon.sessions import StringSession
from telethon import TelegramClient

# Setup detailed logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    handlers=[
        logging.FileHandler("historical_debug.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

async def deep_message_analysis():
    """Deep analysis of why historical messages aren't being detected"""
    print("🔍 DEEP HISTORICAL MESSAGE ANALYSIS")
    print("=" * 60)
    
    db = Database(DATABASE_URL)
    client = None
    
    try:
        # Connect to Telegram
        session_string = db.get_telegram_session()
        if not session_string:
            print("❌ No Telegram session found")
            return
        
        client = TelegramClient(StringSession(session_string), int(TELEGRAM_API_ID), TELEGRAM_API_HASH)
        await client.connect()
        
        if not await client.is_user_authorized():
            print("❌ Telegram session invalid")
            return
        
        print("✅ Connected to Telegram")
        
        # Get monitored groups
        groups_val = db.get_config('monitored_groups') or ''
        groups = [s.strip() for s in groups_val.split(',') if s.strip()]
        print(f"📋 Monitored groups: {groups}")
        
        # Test with various time ranges
        time_ranges = [
            (1, "1 hour"),
            (6, "6 hours"), 
            (24, "24 hours"),
            (48, "48 hours"),
            (72, "72 hours"),
            (168, "7 days")
        ]
        
        for group in groups:
            print(f"\n🔍 ANALYZING GROUP: {group}")
            print("-" * 40)
            
            try:
                # Get group entity
                group_entity = await client.get_entity(int(group))
                print(f"✅ Group: {group_entity.title}")
                
                # Test each time range
                for hours_back, time_name in time_ranges:
                    print(f"\n  🕐 Testing {time_name} ({hours_back}h back):")
                    
                    # Calculate time range
                    end_time = datetime.now()
                    start_time = end_time - timedelta(hours=hours_back)
                    
                    print(f"     From: {start_time}")
                    print(f"     To: {end_time}")
                    
                    # Get messages without any filtering first
                    all_messages = []
                    forward_messages = []
                    text_messages = []
                    
                    async for message in client.iter_messages(
                        group_entity,
                        limit=100,  # Get 100 messages to test
                        offset_date=end_time,
                        reverse=True
                    ):
                        # Stop if message is too old
                        if message.date < start_time:
                            break
                            
                        all_messages.append(message)
                        
                        # Analyze message content
                        msg_info = get_message_info(message)
                        
                        if msg_info['has_forward']:
                            forward_messages.append(message)
                        if msg_info['text']:
                            text_messages.append(message)
                    
                    print(f"     📊 Total messages found: {len(all_messages)}")
                    print(f"     📤 Messages with text: {len(text_messages)}")
                    print(f"     🔄 Forwarded messages: {len(forward_messages)}")
                    
                    # Show sample messages
                    if all_messages:
                        print("     📝 Sample messages:")
                        for i, msg in enumerate(all_messages[:3], 1):
                            msg_info = get_message_info(msg)
                            text_preview = msg_info['text_preview'] or "(no text)"
                            print(f"        {i}. [{msg_info['type']}] {msg.date} - '{text_preview}'")
                    
                    # Check if messages are already in database
                    if all_messages:
                        print("     💾 Checking database for duplicates...")
                        with db.get_connection() as conn:
                            cursor = conn.cursor()
                            message_ids = [msg.id for msg in all_messages]
                            cursor.execute(
                                f"SELECT message_id FROM raw_messages WHERE message_id IN ({','.join(['%s'] * len(message_ids))})",
                                message_ids
                            )
                            existing_ids = [row[0] for row in cursor.fetchall()]
                        
                        existing_count = len(existing_ids)
                        new_count = len(all_messages) - existing_count
                        
                        print(f"     📋 Already in database: {existing_count}")
                        print(f"     🆕 New messages: {new_count}")
                        
                        if new_count > 0:
                            print(f"     🎉 Found {new_count} NEW messages for {time_name}!")
                            
                            # Show some new message details
                            new_messages = [msg for msg in all_messages if msg.id not in existing_ids]
                            for i, msg in enumerate(new_messages[:2], 1):
                                msg_info = get_message_info(msg)
                                print(f"        New {i}: {msg_info['type']} - {msg_info['text_preview']}")
                        else:
                            print(f"     ❌ All {len(all_messages)} messages already processed")
                            
            except Exception as e:
                print(f"❌ Error analyzing group {group}: {e}")
                continue
        
        # Test database state
        print(f"\n💾 DATABASE STATE ANALYSIS")
        print("-" * 40)
        
        with db.get_connection() as conn:
            cursor = conn.cursor()
            
            # Count messages by time periods
            periods = [
                (1, "last hour"),
                (6, "last 6 hours"),
                (24, "last 24 hours"), 
                (168, "last 7 days"),
                (24*30, "last 30 days")
            ]
            
            for hours, period_name in periods:
                cursor.execute("""
                    SELECT COUNT(*) FROM raw_messages 
                    WHERE created_at >= CURRENT_TIMESTAMP - INTERVAL '%s hours'
                """, (hours,))
                count = cursor.fetchone()[0]
                print(f"📅 {period_name}: {count} messages")
            
            # Check processed vs unprocessed
            cursor.execute("""
                SELECT status, COUNT(*) FROM raw_messages 
                GROUP BY status
            """)
            status_counts = cursor.fetchall()
            print("📊 Message statuses:")
            for status, count in status_counts:
                print(f"   {status}: {count}")
            
            # Check recent raw messages
            cursor.execute("""
                SELECT message_id, message_text, created_at 
                FROM raw_messages 
                ORDER BY created_at DESC 
                LIMIT 5
            """)
            recent_messages = cursor.fetchall()
            
            if recent_messages:
                print("📝 Recent raw messages:")
                for msg_id, text, created_at in recent_messages:
                    preview = text[:100] + "..." if len(text) > 100 else text
                    print(f"   ID {msg_id}: '{preview}' ({created_at})")
            else:
                print("❌ No raw messages in database")
        
    except Exception as e:
        print(f"❌ Debug error: {e}")
    finally:
        if client and client.is_connected():
            await client.disconnect()

async def test_enhanced_historical_fetch():
    """Test the enhanced historical fetch with detailed logging"""
    print(f"\n\n🚀 TESTING ENHANCED HISTORICAL FETCH")
    print("=" * 60)
    
    from historical_message_fetcher import HistoricalMessageFetcher
    
    db = Database(DATABASE_URL)
    fetcher = HistoricalMessageFetcher(TELEGRAM_API_ID, TELEGRAM_API_HASH, TELEGRAM_PHONE, db)
    
    try:
        if await fetcher.connect_client():
            print("✅ Connected to Telegram")
            
            # Test with 48 hours to maximize chance of finding messages
            hours_back = 48
            print(f"🕐 Testing enhanced fetch with {hours_back} hours back...")
            
            # Use the enhanced method
            result = await fetcher.fetch_and_process_historical_messages(hours_back)
            
            print("📊 Enhanced fetch result:")
            for key, value in result.items():
                print(f"   {key}: {value}")
                
        else:
            print("❌ Failed to connect to Telegram")
            
    except Exception as e:
        print(f"❌ Enhanced fetch error: {e}")
    finally:
        await fetcher.close()

if __name__ == "__main__":
    asyncio.run(deep_message_analysis())
    asyncio.run(test_enhanced_historical_fetch())