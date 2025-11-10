#!/usr/bin/env python3
"""
Comprehensive Historical Message Recovery
Tests for older messages and different access methods beyond 7 days
"""

import asyncio
import logging
from datetime import datetime, timedelta
from database import Database
from config import DATABASE_URL, TELEGRAM_API_ID, TELEGRAM_API_HASH, TELEGRAM_PHONE
from message_utils import extract_message_text, get_message_info
from telethon.sessions import StringSession
from telethon import TelegramClient
from telethon.errors import (
    ChannelPrivateError, 
    UserPrivacyRestrictedError,
    ChatWriteForbiddenError,
    ChannelInvalidError
)

# Setup logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    handlers=[
        logging.FileHandler("comprehensive_historical.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

async def test_comprehensive_message_retrieval():
    """Test message retrieval with multiple approaches and time ranges"""
    print("🔍 COMPREHENSIVE HISTORICAL MESSAGE RECOVERY")
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
        
        for group in groups:
            print(f"\n🔍 TESTING GROUP: {group}")
            print("-" * 40)
            
            try:
                # Method 1: Standard group access
                group_entity = None
                try:
                    group_entity = await client.get_entity(int(group))
                    print(f"✅ Method 1 - Standard access: {group_entity.title}")
                except Exception as e:
                    print(f"❌ Method 1 - Standard access failed: {e}")
                    
                    # Method 2: Try as username if numeric failed
                    if not group.startswith('-'):
                        try:
                            group_entity = await client.get_entity(group)
                            print(f"✅ Method 2 - Username access: {group_entity.title}")
                        except Exception as e2:
                            print(f"❌ Method 2 - Username access failed: {e2}")
                    
                    # Method 3: Try different date ranges
                    if not group_entity:
                        print("🔄 Trying different access methods...")
                        # This is where we'd try different approaches
                        continue
                
                if not group_entity:
                    continue
                
                # Test multiple time ranges beyond 7 days
                extended_time_ranges = [
                    (24, "24 hours"),
                    (48, "48 hours"), 
                    (72, "72 hours"),
                    (168, "7 days"),
                    (336, "14 days"),
                    (720, "30 days"),
                    (2160, "90 days"),
                    ("unlimited", "Unlimited")
                ]
                
                for limit_value, time_name in extended_time_ranges:
                    print(f"\n  🕐 Testing {time_name}:")
                    
                    # Method A: Limited by time
                    if isinstance(limit_value, int):
                        end_time = datetime.now()
                        start_time = end_time - timedelta(hours=limit_value)
                        limit = min(1000, limit_value * 10)  # Scale limit with time
                        
                        messages = []
                        async for message in client.iter_messages(
                            group_entity,
                            limit=limit,
                            offset_date=end_time,
                            reverse=True,
                            archive=True  # Include archived messages
                        ):
                            if isinstance(limit_value, int) and message.date < start_time:
                                break
                            messages.append(message)
                    
                    # Method B: Unlimited (get many recent messages)
                    else:
                        messages = []
                        async for message in client.iter_messages(
                            group_entity,
                            limit=1000,  # Large limit to get many messages
                            reverse=True,
                            archive=True  # Include archived messages
                        ):
                            messages.append(message)
                    
                    print(f"     📊 Total messages found: {len(messages)}")
                    
                    if messages:
                        # Analyze message types
                        text_messages = 0
                        forward_messages = 0
                        media_messages = 0
                        
                        for msg in messages:
                            msg_info = get_message_info(msg)
                            if msg_info['text']:
                                text_messages += 1
                            if msg_info['has_forward']:
                                forward_messages += 1
                            if msg_info['has_media']:
                                media_messages += 1
                        
                        print(f"     📤 With text: {text_messages}")
                        print(f"     🔄 Forwarded: {forward_messages}")
                        print(f"     🖼️  Media: {media_messages}")
                        
                        # Show oldest and newest message dates
                        oldest_date = min(msg.date for msg in messages)
                        newest_date = max(msg.date for msg in messages)
                        print(f"     📅 Date range: {oldest_date} to {newest_date}")
                        
                        # Check database for existing messages
                        if messages:
                            with db.get_connection() as conn:
                                cursor = conn.cursor()
                                message_ids = [msg.id for msg in messages]
                                cursor.execute(
                                    f"SELECT message_id FROM raw_messages WHERE message_id IN ({','.join(['%s'] * len(message_ids))})",
                                    message_ids
                                )
                                existing_ids = [row[0] for row in cursor.fetchall()]
                            
                            new_messages = len(messages) - len(existing_ids)
                            print(f"     🆕 New messages (not in DB): {new_messages}")
                            
                            if new_messages > 0:
                                print(f"     🎉 SUCCESS! Found {new_messages} messages to process!")
                                
                                # Show sample new messages
                                new_msg_samples = [msg for msg in messages if msg.id not in existing_ids][:3]
                                for i, msg in enumerate(new_msg_samples, 1):
                                    msg_info = get_message_info(msg)
                                    print(f"        New {i}: {msg_info['type']} - {msg_info['text_preview']}")
                                
                                # Option to process these messages
                                if new_messages > 0:
                                    print(f"     💾 Ready to process {new_messages} messages")
                                    return True
                        
                        # Show some sample messages
                        print("     📝 Sample messages:")
                        for i, msg in enumerate(messages[:3], 1):
                            msg_info = get_message_info(msg)
                            print(f"        {i}. [{msg_info['type']}] {msg.date} - '{msg_info['text_preview']}'")
                    else:
                        print("     ❌ No messages found in this range")
                        
            except ChannelPrivateError:
                print(f"❌ Group {group}: Private channel - bot needs to be added")
            except ChatWriteForbiddenError:
                print(f"❌ Group {group}: No write permission")
            except Exception as e:
                print(f"❌ Group {group}: {type(e).__name__} - {e}")
                continue
        
        print(f"\n💡 RECOMMENDATIONS:")
        print("-" * 40)
        print("1. If groups show 0 messages:")
        print("   - Groups may be inactive or archived")
        print("   - Bot may have been removed from groups")
        print("   - Groups may be private/restricted")
        print("")
        print("2. If you know messages exist:")
        print("   - Check if bot still has access to groups")
        print("   - Verify groups haven't been archived")
        print("   - Try adding more active job groups")
        print("")
        print("3. Real-time monitoring is working:")
        print("   - Will capture new forwarded messages immediately")
        print("   - Historical fetch will work when messages are available")
        
        return False
        
    except Exception as e:
        print(f"❌ Comprehensive recovery error: {e}")
        return False
    finally:
        if client and client.is_connected():
            await client.disconnect()

async def test_manual_message_search():
    """Test manual search for specific message patterns"""
    print(f"\n\n🔍 MANUAL MESSAGE PATTERN SEARCH")
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
        
        # Get monitored groups
        groups_val = db.get_config('monitored_groups') or ''
        groups = [s.strip() for s in groups_val.split(',') if s.strip()]
        
        job_keywords = [
            'job', 'hiring', 'position', 'vacancy', 'career', 'recruitment',
            'company', 'salary', 'experience', 'fresher', 'graduate',
            'apply', 'application', 'interview', 'openings'
        ]
        
        for group in groups:
            print(f"\n🔍 Searching group {group} for job-related messages:")
            
            try:
                group_entity = await client.get_entity(int(group))
                
                # Search for job-related messages
                found_messages = []
                message_count = 0
                
                async for message in client.iter_messages(
                    group_entity,
                    limit=2000,  # Large limit to search thoroughly
                    reverse=True,
                    archive=True
                ):
                    message_count += 1
                    
                    if message_count % 500 == 0:
                        print(f"     Searched {message_count} messages...")
                    
                    # Check if message contains job keywords
                    msg_info = get_message_info(message)
                    text = msg_info['text'].lower() if msg_info['text'] else ""
                    
                    for keyword in job_keywords:
                        if keyword in text:
                            found_messages.append((message, keyword))
                            break
                
                print(f"     📊 Searched {message_count} messages")
                print(f"     🎯 Found {len(found_messages)} job-related messages")
                
                if found_messages:
                    print("     📝 Sample job messages found:")
                    for i, (msg, keyword) in enumerate(found_messages[:5], 1):
                        msg_info = get_message_info(msg)
                        preview = msg_info['text_preview'] or "(no text)"
                        print(f"        {i}. [{msg_info['type']}] {keyword} - {msg.date}")
                        print(f"           '{preview}'")
                
            except Exception as e:
                print(f"❌ Error searching group {group}: {e}")
                
    except Exception as e:
        print(f"❌ Manual search error: {e}")
    finally:
        if client and client.is_connected():
            await client.disconnect()

if __name__ == "__main__":
    result = asyncio.run(test_comprehensive_message_retrieval())
    if not result:
        asyncio.run(test_manual_message_search())