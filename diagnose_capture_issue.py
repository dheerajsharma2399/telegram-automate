#!/usr/bin/env python3
"""
Detailed diagnosis of why some Premium Referrals messages aren't being captured
"""

import asyncio
import logging
from datetime import datetime
from database import Database
from config import DATABASE_URL, TELEGRAM_API_ID, TELEGRAM_API_HASH, TELEGRAM_PHONE
from message_utils import extract_message_text, get_message_info
from telethon.sessions import StringSession
from telethon import TelegramClient
from telethon.tl.types import Message

# Setup logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

async def diagnose_capture_issue():
    """Diagnose why some Premium Referrals messages aren't being captured"""
    print("🔍 DIAGNOSING PREMIUM REFERRALS CAPTURE ISSUE")
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
        
        # Get the Premium Referrals group
        premium_referrals_group = "-1002947896517"
        group_entity = await client.get_entity(premium_referrals_group)
        print(f"✅ Group: {group_entity.title}")
        
        # Get messages from today (2025-11-10)
        print(f"🕐 Getting messages from 2025-11-10...")
        
        captured_message_ids = set()
        with db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT DISTINCT message_id 
                FROM raw_messages 
                WHERE created_at >= '2025-11-10 00:00:00'::timestamp
                ORDER BY message_id DESC
            """)
            captured_ids = cursor.fetchall()
            captured_message_ids = {msg_id[0] for msg_id in captured_ids}
        
        print(f"📊 Already captured messages: {len(captured_message_ids)}")
        
        # Get recent messages from Premium Referrals
        messages_found = []
        missing_messages = []
        
        message_count = 0
        async for message in client.iter_messages(
            group_entity,
            limit=100,  # Get recent messages
            reverse=True
        ):
            message_count += 1
            
            if message_count > 50:  # Limit to avoid too many
                break
                
            # Skip if no text
            msg_info = get_message_info(message)
            if not msg_info['text']:
                continue
                
            # Check if this contains job information
            text = msg_info['text'].lower()
            job_keywords = ['job', 'hiring', 'intern', 'engineer', 'developer', 'salary', 'stipend', 'company', 'role']
            has_job_content = any(keyword in text for keyword in job_keywords)
            
            if has_job_content:
                is_captured = message.id in captured_message_ids
                
                message_data = {
                    'id': message.id,
                    'date': message.date,
                    'text': msg_info['text'][:200] + "..." if len(msg_info['text']) > 200 else msg_info['text'],
                    'type': msg_info['type'],
                    'is_forwarded': msg_info['has_forward'],
                    'has_media': msg_info['has_media'],
                    'is_captured': is_captured,
                    'raw_text': msg_info['text'][:100] if msg_info['text'] else "NO TEXT"
                }
                
                messages_found.append(message_data)
                
                if not is_captured:
                    missing_messages.append(message_data)
                    missing_companies = []
                    # Check for specific companies mentioned by user
                    if 'synap' in text:
                        missing_companies.append('Synap')
                    if 'veradigm' in text:
                        missing_companies.append('Veradigm')
                    if 'mandrake' in text:
                        missing_companies.append('Mandrake Bioworks')
                    if 'clarivate' in text:
                        missing_companies.append('Clarivate')
                    if 'iit bhubaneswar' in text:
                        missing_companies.append('IIT Bhubaneswar')
                    if 'refex' in text:
                        missing_companies.append('Refex Mobility')
                    if 'exl' in text:
                        missing_companies.append('EXL')
                    if 'ukg' in text:
                        missing_companies.append('UKG')
                    
                    if missing_companies:
                        print(f"   ❌ Missing companies: {', '.join(missing_companies)}")
        
        print(f"\n📊 ANALYSIS RESULTS")
        print("-" * 40)
        print(f"📋 Total messages found: {len(messages_found)}")
        print(f"✅ Successfully captured: {len(messages_found) - len(missing_messages)}")
        print(f"❌ Missing/Not captured: {len(missing_messages)}")
        
        if messages_found:
            print(f"\n📝 CAPTURED MESSAGES:")
            captured_count = 0
            for msg in messages_found[:5]:
                if msg['is_captured']:
                    captured_count += 1
                    company_preview = "Unknown"
                    if 'company' in msg['text'].lower():
                        company_lines = [line for line in msg['text'].split('\n') if 'company' in line.lower()]
                        if company_lines:
                            company_preview = company_lines[0][:50] + "..."
                    print(f"   ✅ {msg['date']}: {company_preview} (Type: {msg['type']})")
            if captured_count == 0:
                print("   ❌ No captured messages found")
        
        if missing_messages:
            print(f"\n❌ MISSING/UNCAPTURED MESSAGES:")
            for i, msg in enumerate(missing_messages[:5], 1):
                print(f"   {i}. ID: {msg['id']} - Date: {msg['date']}")
                print(f"      Type: {msg['type']} | Forwarded: {msg['is_forwarded']} | Media: {msg['has_media']}")
                print(f"      Text: {msg['raw_text'][:100]}...")
                
                # Diagnose why it wasn't captured
                if not msg['is_forwarded'] and not msg['has_media']:
                    print(f"      💡 Diagnosis: Direct message with text - should have been captured")
                elif msg['is_forwarded']:
                    print(f"      💡 Diagnosis: Forwarded message - checking text extraction")
                elif msg['has_media']:
                    print(f"      💡 Diagnosis: Media message - checking caption extraction")
                print()
        
        # Check real-time monitoring status
        print(f"\n🔍 CHECKING REAL-TIME MONITORING STATUS")
        print("-" * 40)
        
        # Check if bot is connected
        login_status = db.get_telegram_login_status()
        print(f"🤖 Bot login status: {login_status}")
        
        # Check monitoring status
        monitoring_status = db.get_config('monitoring_status')
        print(f"⚙️  Monitoring status: {monitoring_status}")
        
        # Check unprocessed messages
        with db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM raw_messages WHERE status = 'unprocessed'")
            unprocessed_count = cursor.fetchone()[0]
            print(f"📋 Unprocessed messages: {unprocessed_count}")
        
        # Provide recommendations
        print(f"\n💡 RECOMMENDATIONS:")
        print("-" * 40)
        if login_status != 'connected':
            print("❌ Bot not connected to Telegram - check session")
        if monitoring_status != 'running':
            print("❌ Monitoring not running - start with /start command")
        if len(missing_messages) > 0:
            print("⚠️  Some messages not captured - check message type detection")
            print("   - Check if messages are forwarded vs direct")
            print("   - Verify enhanced text extraction is working")
            print("   - Check if bot has proper group permissions")
        
    except Exception as e:
        print(f"❌ Diagnosis error: {e}")
    finally:
        if client and client.is_connected():
            await client.disconnect()

if __name__ == "__main__":
    asyncio.run(diagnose_capture_issue())