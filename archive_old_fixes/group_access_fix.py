#!/usr/bin/env python3
"""
Fix group access issues and diagnose message capture problems
"""

import asyncio
import logging
from datetime import datetime
from database import Database
from config import DATABASE_URL, TELEGRAM_API_ID, TELEGRAM_API_HASH, TELEGRAM_PHONE
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
    level=logging.INFO
)
logger = logging.getLogger(__name__)

async def check_and_fix_group_access():
    """Check group access and fix issues"""
    print("🔍 GROUP ACCESS DIAGNOSIS & FIX")
    print("=" * 60)
    
    db = Database(DATABASE_URL)
    client = None
    
    try:
        # Connect to Telegram
        session_string = db.get_telegram_session()
        if not session_string:
            print("❌ No Telegram session found - bot needs re-authentication")
            return
        
        client = TelegramClient(StringSession(session_string), int(TELEGRAM_API_ID), TELEGRAM_API_HASH)
        await client.connect()
        
        if not await client.is_user_authorized():
            print("❌ Telegram session invalid - bot needs re-authentication")
            return
        
        print("✅ Connected to Telegram")
        
        # Get current groups from database
        groups_val = db.get_config('monitored_groups') or ''
        groups = [s.strip() for s in groups_val.split(',') if s.strip()]
        print(f"📋 Groups in database: {groups}")
        
        # Check each group's access
        accessible_groups = []
        inaccessible_groups = []
        
        for group_id in groups:
            print(f"\n🔍 Checking group: {group_id}")
            try:
                # Try to get entity
                group_entity = await client.get_entity(group_id)
                print(f"✅ Accessible: {group_entity.title}")
                accessible_groups.append(group_id)
                
                # Get recent messages
                message_count = 0
                async for msg in client.iter_messages(group_entity, limit=10):
                    if message_count == 0:
                        print(f"   Latest message: {msg.date}")
                        # Check if it's job-related
                        msg_text = str(getattr(msg, 'text', '')) or str(getattr(msg, 'message', '')) or str(getattr(msg, 'caption', ''))
                        if any(keyword in msg_text.lower() for keyword in ['job', 'hiring', 'intern', 'company']):
                            print(f"   📋 Contains job content")
                        else:
                            print(f"   📝 Non-job content")
                    message_count += 1
                    if message_count >= 5:
                        break
                        
            except ChannelPrivateError:
                print(f"❌ Private channel - bot needs to be added")
                inaccessible_groups.append((group_id, "Private - needs bot addition"))
            except ChatWriteForbiddenError:
                print(f"❌ No write permission")
                inaccessible_groups.append((group_id, "No write permission"))
            except ChannelInvalidError:
                print(f"❌ Invalid channel")
                inaccessible_groups.append((group_id, "Invalid channel"))
            except Exception as e:
                print(f"❌ Access error: {type(e).__name__} - {e}")
                inaccessible_groups.append((group_id, f"{type(e).__name__}: {e}"))
        
        # Summary
        print(f"\n📊 ACCESS SUMMARY")
        print("-" * 40)
        print(f"✅ Accessible groups: {len(accessible_groups)}")
        print(f"❌ Inaccessible groups: {len(inaccessible_groups)}")
        
        if accessible_groups:
            print("✅ Accessible groups list:")
            for group_id in accessible_groups:
                print(f"   - {group_id}")
        
        if inaccessible_groups:
            print("❌ Inaccessible groups list:")
            for group_id, reason in inaccessible_groups:
                print(f"   - {group_id}: {reason}")
        
        # Update monitored groups to only accessible ones
        if accessible_groups and len(accessible_groups) != len(groups):
            print(f"\n🔧 UPDATING MONITORED GROUPS")
            print("-" * 40)
            new_groups_str = ','.join(accessible_groups)
            db.set_config('monitored_groups', new_groups_str)
            print(f"✅ Updated to: {new_groups_str}")
            print("📋 Real-time monitoring will now work for accessible groups only")
        
        # Check recent captured messages
        print(f"\n📋 CHECKING RECENT CAPTURED MESSAGES")
        print("-" * 40)
        
        with db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, message_id, message_text, created_at, status
                FROM raw_messages 
                WHERE created_at >= CURRENT_TIMESTAMP - INTERVAL '12 hours'
                ORDER BY created_at DESC
                LIMIT 10
            """)
            recent_messages = cursor.fetchall()
        
        if recent_messages:
            print(f"📊 Recent messages captured (12h): {len(recent_messages)}")
            for msg_id, message_id, text, created_at, status in recent_messages:
                preview = text[:80] + "..." if len(text) > 80 else text
                print(f"   ID {message_id}: '{preview}' ({created_at}) - {status}")
        else:
            print("❌ No recent messages captured")
        
        # Recommendations
        print(f"\n💡 SOLUTIONS")
        print("-" * 40)
        if not accessible_groups:
            print("❌ NO ACCESSIBLE GROUPS FOUND")
            print("   1. Re-authenticate bot with Telegram")
            print("   2. Add bot to your Premium Referrals group")
            print("   3. Verify bot permissions in groups")
        else:
            print("✅ SOME GROUPS ACCESSIBLE - FORWARDED MESSAGE HANDLING WILL WORK")
            print("   1. Test with live forwarded messages")
            print("   2. Monitor logs for enhanced forwarded message detection")
            print("   3. Use historical fetch to recover missed messages")
            
        if inaccessible_groups:
            print("\n🔧 FIX INACCESSIBLE GROUPS:")
            print("   1. Add bot to private groups as admin")
            print("   2. Verify bot still has access permissions")
            print("   3. Re-authenticate Telegram session if needed")
        
    except Exception as e:
        print(f"❌ Group access check error: {e}")
    finally:
        if client and client.is_connected():
            await client.disconnect()

async def test_real_time_capture():
    """Test real-time message capture functionality"""
    print(f"\n🧪 TESTING REAL-TIME CAPTURE")
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
        
        # Get accessible groups
        groups_val = db.get_config('monitored_groups') or ''
        groups = [s.strip() for s in groups_val.split(',') if s.strip()]
        
        if not groups:
            print("❌ No groups configured")
            return
        
        print(f"📋 Testing capture for groups: {groups}")
        
        # Test message capture simulation
        for group_id in groups:
            try:
                group_entity = await client.get_entity(group_id)
                print(f"\n🔍 Testing group: {group_entity.title}")
                
                # Get a few recent messages
                async for message in client.iter_messages(group_entity, limit=5):
                    if hasattr(message, 'text') and message.text:
                        print(f"   📝 Message {message.id}: {message.text[:50]}...")
                        # This would be the message that should be captured
                        break
                
            except Exception as e:
                print(f"   ❌ Error testing group {group_id}: {e}")
        
        print("✅ Real-time monitoring test complete")
        
    except Exception as e:
        print(f"❌ Real-time test error: {e}")
    finally:
        if client and client.is_connected():
            await client.disconnect()

if __name__ == "__main__":
    asyncio.run(check_and_fix_group_access())
    asyncio.run(test_real_time_capture())