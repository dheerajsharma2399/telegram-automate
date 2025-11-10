#!/usr/bin/env python3
"""
Telegram API-based Message Monitor
Uses Telegram User API (not Bot API) for message monitoring
Bot only used for commands and notifications
"""

import asyncio
import logging
from datetime import datetime, timedelta
from database import Database
from config import DATABASE_URL, TELEGRAM_API_ID, TELEGRAM_API_HASH, TELEGRAM_PHONE
from message_utils import extract_message_text, should_process_message, get_message_info
from telethon.sessions import StringSession
from telethon import TelegramClient
import json

# Setup logging
logging.basicConfig(
    level=logging.INFO, 
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("telegram_api_monitor.log"),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)

class TelegramAPIMonitor:
    def __init__(self, api_id: str, api_hash: str, phone: str, db: Database):
        self.api_id = int(api_id)
        self.api_hash = api_hash
        self.phone = phone
        self.db = db
        self.client = None
        self.is_running = False
        self.last_message_id = {}
        self.monitored_groups = []
        
    async def connect(self):
        """Connect to Telegram using User API"""
        try:
            # Get stored session
            session_string = self.db.get_telegram_session()
            if not session_string:
                logger.error("No Telegram session found in database")
                return False
            
            # Create client with session
            self.client = TelegramClient(StringSession(session_string), self.api_id, self.api_hash)
            
            # Connect and verify authorization
            await self.client.connect()
            
            if not await self.client.is_user_authorized():
                logger.error("Telegram session is invalid or expired")
                return False
            
            # Update login status
            self.db.set_telegram_login_status('connected')
            logger.info("✅ Connected to Telegram via User API")
            return True
            
        except Exception as e:
            logger.error(f"Failed to connect to Telegram: {e}")
            self.db.set_telegram_login_status('connection_failed')
            return False
    
    async def get_monitored_groups(self):
        """Get list of monitored group entities"""
        try:
            # Get group IDs from database
            groups_val = self.db.get_config('monitored_groups') or ''
            group_ids = [s.strip() for s in groups_val.split(',') if s.strip()]
            
            if not group_ids:
                # Use default groups from config if not in database
                from config import TELEGRAM_GROUP_USERNAMES
                group_ids = TELEGRAM_GROUP_USERNAMES or []
            
            # Get group entities
            group_entities = []
            for group_id in group_ids:
                try:
                    if isinstance(group_id, str) and group_id.startswith('-'):
                        # Try as numeric ID first
                        entity = await self.client.get_entity(int(group_id))
                    else:
                        # Try as username
                        entity = await self.client.get_entity(group_id)
                    
                    group_entities.append(entity)
                    logger.info(f"📋 Monitoring group: {entity.title} (ID: {entity.id})")
                    
                except Exception as e:
                    logger.warning(f"Cannot access group {group_id}: {e}")
                    continue
            
            self.monitored_groups = group_entities
            logger.info(f"✅ Loaded {len(group_entities)} monitored groups")
            return group_entities
            
        except Exception as e:
            logger.error(f"Failed to get monitored groups: {e}")
            return []
    
    async def initialize_message_tracking(self):
        """Initialize message ID tracking for each group"""
        try:
            for group in self.monitored_groups:
                # Get the most recent message ID in each group
                async for message in self.client.iter_messages(group, limit=1):
                    self.last_message_id[group.id] = message.id
                    logger.info(f"📍 Tracking {group.title}: starting from message {message.id}")
                    break
                else:
                    # No messages found, start from beginning
                    self.last_message_id[group.id] = 0
                    logger.info(f"📍 Tracking {group.title}: no recent messages, starting fresh")
                    
        except Exception as e:
            logger.error(f"Failed to initialize message tracking: {e}")
    
    async def monitor_messages(self):
        """Main message monitoring loop using Telegram User API"""
        logger.info("🔄 Starting Telegram API message monitoring...")
        
        if not await self.connect():
            logger.error("❌ Failed to connect to Telegram")
            return
        
        # Get monitored groups
        groups = await self.get_monitored_groups()
        if not groups:
            logger.error("❌ No monitored groups found")
            return
        
        # Initialize message tracking
        await self.initialize_message_tracking()
        
        self.is_running = True
        logger.info("✅ Telegram API monitoring started successfully")
        
        # Main monitoring loop
        while self.is_running:
            try:
                await self._check_new_messages()
                await asyncio.sleep(2)  # Check every 2 seconds
                
            except asyncio.CancelledError:
                logger.info("🛑 Message monitoring cancelled")
                break
            except Exception as e:
                logger.error(f"Error in message monitoring loop: {e}")
                await asyncio.sleep(10)  # Wait before retrying
        
        # Cleanup
        if self.client:
            await self.client.disconnect()
            self.client = None
    
    async def _check_new_messages(self):
        """Check for new messages in all monitored groups"""
        for group in self.monitored_groups:
            try:
                await self._check_group_messages(group)
            except Exception as e:
                logger.error(f"Error checking messages in {group.title}: {e}")
    
    async def _check_group_messages(self, group_entity):
        """Check for new messages in a specific group"""
        try:
            # Get messages after our last tracked message
            new_messages = []
            async for message in self.client.iter_messages(
                group_entity, 
                min_id=self.last_message_id[group_entity.id],
                limit=50,  # Check up to 50 new messages
                reverse=True  # Get newest first
            ):
                new_messages.append(message)
            
            if not new_messages:
                return
            
            # Process new messages (oldest to newest)
            for message in reversed(new_messages):
                await self._process_message(message, group_entity)
                
                # Update last message ID
                self.last_message_id[group_entity.id] = max(
                    self.last_message_id[group_entity.id], 
                    message.id
                )
            
            if len(new_messages) > 0:
                logger.info(f"📝 {group_entity.title}: Processed {len(new_messages)} new messages")
            
        except Exception as e:
            logger.error(f"Error checking group {group_entity.title}: {e}")
    
    async def _process_message(self, message, group_entity):
        """Process a single message with enhanced forwarded message support"""
        try:
            # Check if message should be processed
            if not should_process_message(message):
                return
            
            # Get enhanced message info
            msg_info = get_message_info(message)
            
            # Skip empty messages
            if not msg_info['text']:
                return
            
            # Skip bot commands to avoid duplication
            if msg_info['is_bot_command']:
                logger.info(f"Skipping bot command in {group_entity.title}: {msg_info['text'][:50]}")
                return
            
            # Log message detection
            if msg_info['has_forward']:
                logger.info(f"🔄 New FORWARDED job message in {group_entity.title}: {message.id} (type: {msg_info['type']})")
            else:
                logger.info(f"📝 New direct job message in {group_entity.title}: {message.id}")
            
            # Add to database
            try:
                message_id = self.db.add_raw_message(
                    message_id=message.id,
                    message_text=msg_info['text'],
                    sender_id=message.sender_id,
                    sent_at=message.date,
                )
                
                if message_id:
                    # Log successful storage with preview
                    text_preview = msg_info['text_preview'] or msg_info['text'][:100]
                    logger.info(f"💾 Stored message {message.id} from {group_entity.title}: {text_preview}")
                else:
                    logger.warning(f"⚠️  Message {message.id} may already exist in database")
                    
            except Exception as e:
                logger.error(f"❌ Failed to store message {message.id}: {e}")
            
        except Exception as e:
            logger.error(f"❌ Error processing message {message.id}: {e}")
    
    def stop(self):
        """Stop the monitoring"""
        self.is_running = False
        logger.info("🛑 Stopping Telegram API monitoring...")

# Main monitoring function
async def start_telegram_api_monitoring():
    """Start the Telegram API-based monitoring"""
    try:
        logger.info("🚀 Starting Telegram API Monitor...")
        
        # Initialize database
        db = Database(DATABASE_URL)
        
        # Create and start monitor
        monitor = TelegramAPIMonitor(
            TELEGRAM_API_ID,
            TELEGRAM_API_HASH, 
            TELEGRAM_PHONE,
            db
        )
        
        # Start monitoring
        await monitor.monitor_messages()
        
    except Exception as e:
        logger.error(f"Error in Telegram API monitoring: {e}")
    finally:
        logger.info("👋 Telegram API monitoring stopped")

if __name__ == "__main__":
    # Run the monitoring
    asyncio.run(start_telegram_api_monitoring())