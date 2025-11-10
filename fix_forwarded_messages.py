#!/usr/bin/env python3
"""
Fix for forwarded messages in historical message fetcher
Updates the _store_message_if_new method to handle forwarded messages properly
"""

import asyncio
import logging
from datetime import datetime, timedelta
from database import Database
from config import DATABASE_URL
from telethon.sessions import StringSession
from telethon import TelegramClient
import json

# Setup logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

class FixedHistoricalMessageFetcher:
    def __init__(self, api_id: str, api_hash: str, phone: str, db: Database):
        self.api_id = int(api_id)
        self.api_hash = api_hash
        self.phone = phone
        self.db = db
        self.client = None
    
    async def connect_client(self):
        """Connect to Telegram client using stored session"""
        try:
            session_string = self.db.get_telegram_session()
            if not session_string:
                logger.error("No Telegram session found in database")
                return False
            
            if not self.client:
                self.client = TelegramClient(StringSession(session_string), self.api_id, self.api_hash)
                await self.client.connect()
                
                if not await self.client.is_user_authorized():
                    logger.error("Telegram session is invalid or expired")
                    return False
                    
            return True
            
        except Exception as e:
            logger.error(f"Failed to connect Telegram client: {e}")
            return False
    
    async def get_monitored_groups(self):
        """Get list of monitored group IDs"""
        try:
            # Get groups from database
            groups_val = self.db.get_config('monitored_groups') or ''
            groups = [s.strip() for s in groups_val.split(',') if s.strip()]
            
            # Convert to integers if they're numeric IDs
            group_entities = []
            for g in groups:
                if not g:  # Skip empty groups
                    continue
                try:
                    group_id = int(g)
                    group_entities.append(group_id)
                except (ValueError, TypeError):
                    # Try to get entity by username, but only if we have a client
                    if self.client:
                        try:
                            entity = await self.client.get_entity(g)
                            group_entities.append(entity)
                        except Exception as e:
                            logging.warning(f"Could not get entity for group '{g}': {e}")
                            continue
                    else:
                        logging.warning("No Telegram client available to resolve group entity")
                        continue
            
            return group_entities
            
        except Exception as e:
            logger.error(f"Failed to get monitored groups: {e}")
            return []
    
    async def fetch_historical_messages_fixed(self, hours_back=12):
        """Fixed version that handles forwarded messages properly"""
        try:
            # Calculate time range
            end_time = datetime.now()
            start_time = end_time - timedelta(hours=hours_back)
            
            logger.info(f"Fetching messages from {start_time} to {end_time} (FIXED VERSION)")
            
            # Get monitored groups
            groups = await self.get_monitored_groups()
            if not groups:
                logger.error("No monitored groups found")
                return 0
            
            total_fetched = 0
            
            for group in groups:
                try:
                    logger.info(f"Fetching messages from group: {group} (FIXED)")
                    
                    # Get messages in the time range
                    messages = []
                    async for message in self.client.iter_messages(
                        group, 
                        limit=1000,  # Increased limit to catch more messages
                        offset_date=end_time,
                        reverse=True
                    ):
                        # Stop if message is older than our time range
                        if message.date < start_time:
                            break
                        
                        # Enhanced filtering: Don't skip bot messages, let the content be processed
                        # Only skip messages that are completely empty
                        message_text = self._extract_message_text(message)
                        if not message_text or message_text.strip() == "":
                            continue
                        
                        messages.append(message)
                    
                    # Process and store messages
                    processed_count = 0
                    for message in messages:
                        if await self._store_message_if_new_fixed(message):
                            processed_count += 1
                    
                    total_fetched += processed_count
                    logger.info(f"Processed {processed_count} new messages from group {group} (FIXED)")
                    
                except Exception as e:
                    logger.error(f"Failed to fetch from group {group}: {e}")
                    continue
            
            logger.info(f"Total messages fetched and stored: {total_fetched} (FIXED)")
            return total_fetched
            
        except Exception as e:
            logger.error(f"Failed to fetch historical messages: {e}")
            return 0
    
    def _extract_message_text(self, message):
        """Extract text from message, handling forwarded messages properly"""
        try:
            # Try direct text first
            if message.text and message.text.strip():
                return message.text
            
            # Handle forwarded messages
            if hasattr(message, 'forward') and message.forward:
                forward_msg = message.forward
                
                # Try to get text from forwarded message
                if hasattr(forward_msg, 'text') and forward_msg.text:
                    return forward_msg.text
                
                # Try forwarded message's original text
                if hasattr(forward_msg, 'message') and forward_msg.message:
                    return forward_msg.message
            
            # Handle fwd_from structure (older Telegram versions)
            if hasattr(message, 'fwd_from') and message.fwd_from:
                fwd = message.fwd_from
                if hasattr(fwd, 'text') and fwd.text:
                    return fwd.text
                if hasattr(fwd, 'message') and fwd.message:
                    return fwd.message
            
            # Try message.message as fallback
            if hasattr(message, 'message') and message.message:
                return message.message
            
            return ""
            
        except Exception as e:
            logger.warning(f"Error extracting text from message {message.id}: {e}")
            return ""
    
    async def _store_message_if_new_fixed(self, message):
        """Fixed version that properly handles forwarded messages"""
        try:
            # Check if message is already in database
            import psycopg2
            conn = psycopg2.connect(DATABASE_URL)
            cur = conn.cursor()
            
            cur.execute(
                "SELECT id FROM raw_messages WHERE message_id = %s",
                (message.id,)
            )
            
            if cur.fetchone():
                conn.close()
                return False  # Message already exists
            
            # Extract message text using fixed method
            message_text = self._extract_message_text(message)
            
            # Log what we found
            if message_text and len(message_text) > 50:
                logger.info(f"Storing message {message.id} with text: {message_text[:100]}...")
            elif message_text:
                logger.info(f"Storing short message {message.id}: {message_text}")
            else:
                logger.info(f"Storing message {message.id} (no text content)")
            
            # Store new message
            self.db.add_raw_message(
                message_id=message.id,
                message_text=message_text,
                sender_id=message.sender_id,
                sent_at=message.date
            )
            
            conn.close()
            return True
            
        except Exception as e:
            logger.error(f"Failed to store message {message.id}: {e}")
            return False
    
    async def close(self):
        """Close Telegram client connection"""
        if self.client and self.client.is_connected():
            await self.client.disconnect()
            self.client = None

# Test function
async def test_fix():
    """Test the fixed version"""
    print("🧪 TESTING FIXED VERSION FOR FORWARDED MESSAGES")
    print("=" * 50)
    
    from config import TELEGRAM_API_ID, TELEGRAM_API_HASH, TELEGRAM_PHONE
    
    db = Database(DATABASE_URL)
    fetcher = FixedHistoricalMessageFetcher(TELEGRAM_API_ID, TELEGRAM_API_HASH, TELEGRAM_PHONE, db)
    
    try:
        # Connect to Telegram
        if await fetcher.connect_client():
            print("✅ Connected to Telegram successfully")
            
            # Test fetch with fixed version
            hours_back = 6  # Test with smaller range first
            fetched_count = await fetcher.fetch_historical_messages_fixed(hours_back)
            
            print(f"📊 Fixed version result: {fetched_count} messages found")
            
            if fetched_count > 0:
                print("🎉 SUCCESS! Fixed version found messages!")
            else:
                print("ℹ️ Still no messages (try 24+ hours or check group activity)")
            
        else:
            print("❌ Failed to connect to Telegram")
            
    except Exception as e:
        print(f"❌ Error: {e}")
    finally:
        await fetcher.close()

if __name__ == "__main__":
    asyncio.run(test_fix())