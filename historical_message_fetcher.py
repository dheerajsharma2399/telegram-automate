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

from message_utils import extract_message_text, should_process_message

class HistoricalMessageFetcher:
    def __init__(self, db: Database, client: TelegramClient):
        self.db = db
        self.client = client
    
    async def connect_client(self):
        """
        Checks if the provided client is connected.
        The monitor is now responsible for creating and connecting the client.
        """
        try:
            if self.client and self.client.is_connected():
                logger.info("Using existing connected client for historical fetch.")
                return True
            logger.error("No connected Telegram client provided to HistoricalMessageFetcher.")
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
                # Convert numeric strings to integers, leave others as strings
                try:
                    # This will handle negative IDs like '-100...'
                    group_entities.append(int(g))
                except (ValueError, TypeError):
                    # If it's not a number, it's a username
                    group_entities.append(g)
            
            return group_entities
            
        except Exception as e:
            logger.error(f"Failed to get monitored groups: {e}")
            return []
    
    async def fetch_historical_messages(self, hours_back=12):
        """Fetch messages from the past N hours"""
        try:
            # Ensure client is connected before proceeding
            if not await self.connect_client():
                logger.error("Cannot fetch historical messages, client connection failed.")
                return 0

            # Calculate time range
            end_time = datetime.now()
            start_time = end_time - timedelta(hours=hours_back)
            
            logger.info(f"Fetching messages from {start_time} to {end_time}")
            
            # Get monitored groups
            groups = await self.get_monitored_groups()
            if not groups:
                logger.error("No monitored groups found")
                return 0
            
            total_fetched = 0
            
            for group in groups:
                try: # Try to resolve the entity before iterating
                    logger.info(f"Fetching messages from group: {group}")
                    
                    # Get messages in the time range
                    messages = []
                    async for message in self.client.iter_messages(group):
                        # Stop if message is older than our time range
                        message_date = message.date.replace(tzinfo=None) if message.date.tzinfo else message.date
                        if message_date < start_time:
                            break
                        
                        if should_process_message(message):
                            messages.append(message)
                    
                    from telethon.utils import get_peer_id
                    # Process and store messages
                    processed_count = 0
                    group_id_to_pass = get_peer_id(group)
                    for message in messages:
                        if self._store_message_if_new(message, group_id_to_pass):
                            processed_count += 1
                    
                    total_fetched += processed_count
                    logger.info(f"Processed {processed_count} new messages from group {group}")
                    
                except (ValueError, TypeError) as e:
                    logger.error(f"Failed to fetch from group {group}: {e}")
                    continue
            
            logger.info(f"Total messages fetched and stored: {total_fetched}")
            return total_fetched
            
        except Exception as e:
            logger.error(f"Failed to fetch historical messages: {e}")
            return 0

    def _store_message_if_new(self, message, group_id) -> bool:
        """Store message in database if it's not already stored."""
        try:
            message_text = extract_message_text(message)

            # The add_raw_message function uses ON CONFLICT DO NOTHING,
            # so we don't need to check for existence first.
            # It returns an ID if the message was new, or None if it already existed.
            new_id = self.db.add_raw_message(
                message_id=message.id,
                message_text=message_text,
                sender_id=message.sender_id,
                sent_at=message.date,
                group_id=group_id
            )

            if new_id:
                logger.debug(f"Stored new message {message.id}")
                return True
            else:
                # Message already existed
                return False

        except Exception as e:
            logger.error(f"Failed to store message {message.id}: {e}")
            return False
    
    async def fetch_and_process_historical_messages(self, hours_back: int = 12) -> dict:
        """
        Enhanced method: Fetch historical messages AND process them automatically
        Returns detailed results including duplicate processing
        """
        try:
            logger.info(f"Starting enhanced historical fetch and process for {hours_back} hours")

            # Step 1: Fetch messages
            fetched_count = await self.fetch_historical_messages(hours_back)

            if fetched_count == 0:
                return {
                    "fetched_count": 0,
                    "status": "no_new_messages"
                }

            # Step 2: Trigger the standard job processor to handle the newly added messages
            # We enqueue a command for the main bot to run the processor.
            # This avoids duplicating logic and potential race conditions.
            command_id = self.db.commands.enqueue_command("/process")
            logger.info(f"Enqueued '/process' command (ID: {command_id}) to handle {fetched_count} newly fetched messages.")

            return {
                "fetched_count": fetched_count,
                "status": "success",
                "detail": f"Successfully fetched {fetched_count} new messages. They have been queued for processing."
            }

        except Exception as e:
            logger.error(f"Error in enhanced historical fetch: {e}")
            return {
                "fetched_count": 0,
                "status": "error",
                "error": str(e)
            }