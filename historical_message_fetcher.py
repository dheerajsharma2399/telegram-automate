#!/usr/bin/env python3
"""
Improved Historical Message Fetcher
Uses batch processing technique from Colab script for efficient message capture
"""

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Optional
from database import Database
from config import DATABASE_URL
from telethon.sessions import StringSession
from telethon import TelegramClient
from psycopg2.extras import execute_batch

# Setup logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

from message_utils import extract_message_text, should_process_message, log_execution

class HistoricalMessageFetcher:
    def __init__(self, db: Database, client: TelegramClient):
        self.db = db
        self.client = client
        self.batch_size = 100  # Process messages in batches of 100
    
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
            return False
        except Exception as e:
            logger.error(f"Failed to connect Telegram client: {e}")
            return False
    
    async def get_monitored_groups(self):
        """Get list of monitored group IDs"""
        try:
            # Get groups from database
            groups_val = self.db.config.get_config('monitored_groups') or ''
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
    
    def _save_messages_batch(self, messages: List, group_id: int) -> int:
        """
        Save multiple messages in a single database transaction (EFFICIENT)
        Uses the batch insert technique from the Colab script
        
        Args:
            messages: List of Telethon message objects
            group_id: The group ID these messages belong to
            
        Returns:
            Number of messages successfully saved
        """
        if not messages:
            return 0
        
        sql = """
            INSERT INTO raw_messages 
                (message_id, message_text, sender_id, group_id, sent_at, status)
            VALUES 
                (%s, %s, %s, %s, %s, 'unprocessed')
            ON CONFLICT (group_id, message_id) DO NOTHING;
        """
        
        try:
            with self.db.get_connection() as conn:
                with conn.cursor() as cursor:
                    # Prepare batch data
                    batch_data = []
                    for message in messages:
                        message_text = extract_message_text(message)
                        
                        # Only add messages that should be processed
                        if message_text and should_process_message(message):
                            batch_data.append((
                                message.id,
                                message_text,
                                message.sender_id if message.sender_id else None,
                                group_id,
                                message.date
                            ))
                    
                    if not batch_data:
                        return 0
                    
                    # Execute batch insert - MUCH faster than individual inserts
                    execute_batch(cursor, sql, batch_data, page_size=100)
                    conn.commit()
                    
                    logger.info(f"✅ Saved batch of {len(batch_data)} messages to database")
                    return len(batch_data)

        except Exception as e:
            logger.error(f"Failed to save message batch: {e}")
            return 0

    @log_execution
    async def fetch_historical_messages(self, hours_back=12):
        """
        Fetch messages from the past N hours using efficient batch processing
        
        Args:
            hours_back: Number of hours to look back (default: 12)
            
        Returns:
            Total number of messages fetched and stored
        """
        try:
            # Ensure client is connected before proceeding
            if not await self.connect_client():
                logger.error("Cannot fetch historical messages, client connection failed.")
                return 0

            # Calculate time range
            end_time = datetime.now(timezone.utc)
            start_time = end_time - timedelta(hours=hours_back)
            
            logger.info(f"📥 Fetching messages from {start_time} to {end_time} (UTC)")
            logger.info(f"⏰ Time window: {hours_back} hours")
            
            # Get monitored groups
            groups = await self.get_monitored_groups()
            if not groups:
                logger.error("❌ No monitored groups found")
                return 0
            
            logger.info(f"📋 Monitoring {len(groups)} group(s)")
            
            total_fetched = 0
            
            for group in groups:
                try:
                    # Resolve entity
                    entity = await self.client.get_entity(group)
                    from telethon.utils import get_peer_id
                    group_id = get_peer_id(entity)
                    
                    logger.info(f"\n{'='*70}")
                    logger.info(f"📥 Fetching from: {getattr(entity, 'title', group)}")
                    logger.info(f"   Group ID: {group_id}")
                    logger.info(f"{'='*70}")
                    
                    messages_batch = []
                    total_scanned = 0
                    total_saved = 0
                    
                    # Iterate messages from newest to oldest
                    async for message in self.client.iter_messages(entity, limit=None):
                        total_scanned += 1
                        
                        # Convert message date to UTC for comparison
                        message_date = message.date.replace(tzinfo=timezone.utc) if message.date.tzinfo is None else message.date
                        
                        # Stop if message is older than our time range
                        if message_date < start_time:
                            logger.info(f"⏰ Reached time cutoff at message {message.id}")
                            
                            # Save any remaining messages in the batch
                            if messages_batch:
                                saved = self._save_messages_batch(messages_batch, group_id)
                                total_saved += saved
                                messages_batch = []
                            
                            break
                        
                        # Only process messages that pass our filters
                        if should_process_message(message):
                            messages_batch.append(message)
                            
                            # Save batch when it reaches batch_size
                            if len(messages_batch) >= self.batch_size:
                                saved = self._save_messages_batch(messages_batch, group_id)
                                total_saved += saved
                                messages_batch = []
                                
                                # Progress update
                                logger.info(f"   📊 Progress: Scanned {total_scanned} | Saved {total_saved} messages")
                        
                        # Safety limit to prevent infinite loops
                        if total_scanned >= 10000:
                            logger.warning(f"⚠️ Reached safety limit of 10,000 messages scanned")
                            break
                    
                    # Save any remaining messages in the final batch
                    if messages_batch:
                        saved = self._save_messages_batch(messages_batch, group_id)
                        total_saved += saved
                    
                    total_fetched += total_saved
                    
                    logger.info(f"\n✅ Group Summary:")
                    logger.info(f"   Total Scanned: {total_scanned}")
                    logger.info(f"   Total Saved: {total_saved}")
                    logger.info(f"   Duplicates Skipped: {total_scanned - total_saved}")
                    
                except (ValueError, TypeError) as e:
                    logger.error(f"❌ Failed to fetch from group {group}: {e}")
                    continue
                except Exception as e:
                    logger.error(f"❌ Unexpected error fetching from group {group}: {e}")
                    continue
            
            logger.info(f"\n{'='*70}")
            logger.info(f"🎉 HISTORICAL FETCH COMPLETE")
            logger.info(f"   Total messages fetched and stored: {total_fetched}")
            logger.info(f"{'='*70}")
            
            return total_fetched
            
        except Exception as e:
            logger.error(f"❌ Failed to fetch historical messages: {e}")
            return 0

    @log_execution
    async def fetch_and_process_historical_messages(self, hours_back: int = 12) -> dict:
        """
        Enhanced method: Fetch historical messages AND queue them for processing
        
        Args:
            hours_back: Number of hours to look back (default: 12)
            
        Returns:
            Dictionary with fetch results and processing status
        """
        try:
            logger.info(f"🚀 Starting enhanced historical fetch for {hours_back} hours")

            # Step 1: Fetch messages using efficient batch processing
            fetched_count = await self.fetch_historical_messages(hours_back)

            if fetched_count == 0:
                return {
                    "fetched_count": 0,
                    "status": "no_new_messages",
                    "message": "No new messages found in the specified time range"
                }

            # Step 2: Get statistics about unprocessed messages
            unprocessed_count = self.db.messages.get_unprocessed_count()

            # Step 3: Trigger the standard job processor to handle the newly added messages
            # We enqueue a command for the main bot to run the processor
            command_id = self.db.commands.enqueue_command("/process")
            logger.info(f"📤 Enqueued '/process' command (ID: {command_id}) to handle {fetched_count} newly fetched messages")

            return {
                "fetched_count": fetched_count,
                "unprocessed_count": unprocessed_count,
                "status": "success",
                "command_id": command_id,
                "message": f"Successfully fetched {fetched_count} new messages. Processing command enqueued.",
                "detail": f"Total unprocessed messages in queue: {unprocessed_count}"
            }

        except Exception as e:
            logger.error(f"❌ Error in enhanced historical fetch: {e}")
            return {
                "fetched_count": 0,
                "status": "error",
                "error": str(e),
                "message": "Failed to fetch historical messages"
            }
    
    def get_database_stats(self) -> dict:
        """Get statistics about messages in the database"""
        try:
            with self.db.get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute("""
                        SELECT 
                            COUNT(*) as total,
                            COUNT(*) FILTER (WHERE status = 'unprocessed') as unprocessed,
                            COUNT(*) FILTER (WHERE status = 'processed') as processed,
                            COUNT(*) FILTER (WHERE status = 'processing') as processing,
                            COUNT(*) FILTER (WHERE status = 'failed') as failed,
                            MIN(sent_at) as oldest,
                            MAX(sent_at) as newest,
                            COUNT(DISTINCT group_id) as groups
                        FROM raw_messages
                    """)
                    result = cursor.fetchone()
                    
                    return {
                        'total': result[0],
                        'unprocessed': result[1],
                        'processed': result[2],
                        'processing': result[3],
                        'failed': result[4],
                        'oldest': result[5],
                        'newest': result[6],
                        'groups': result[7]
                    }
        except Exception as e:
            logger.error(f"Failed to get database stats: {e}")
            return {}


# Standalone execution for testing
async def main():
    """Test the historical message fetcher"""
    from config import TELEGRAM_API_ID, TELEGRAM_API_HASH, TELEGRAM_PHONE
    
    print("🧪 Testing Historical Message Fetcher\n")
    
    # Initialize database
    db = Database(DATABASE_URL)
    
    # Get stored session
    session_string = db.auth.get_telegram_session()
    if not session_string:
        print("❌ No Telegram session found. Please authenticate first.")
        return
    
    # Create client
    client = TelegramClient(StringSession(session_string), int(TELEGRAM_API_ID), TELEGRAM_API_HASH)
    
    try:
        # Connect
        await client.connect()
        if not await client.is_user_authorized():
            print("❌ Telegram session is invalid or expired.")
            return
        
        print("✅ Connected to Telegram\n")
        
        # Create fetcher
        fetcher = HistoricalMessageFetcher(db, client)
        
        # Show current stats
        print("📊 Current Database Stats:")
        stats = fetcher.get_database_stats()
        for key, value in stats.items():
            print(f"   {key}: {value}")
        print()
        
        # Fetch messages (default: last 12 hours)
        result = await fetcher.fetch_and_process_historical_messages(hours_back=24)
        
        print("\n" + "="*70)
        print("📋 FETCH RESULTS:")
        print("="*70)
        for key, value in result.items():
            print(f"   {key}: {value}")
        
        # Show updated stats
        print("\n📊 Updated Database Stats:")
        stats = fetcher.get_database_stats()
        for key, value in stats.items():
            print(f"   {key}: {value}")
        
    finally:
        if client.is_connected():
            await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())