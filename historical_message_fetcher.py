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
    
    async def fetch_historical_messages(self, hours_back=12):
        """Fetch messages from the past N hours"""
        try:
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
                try:
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
                    
                    # Process and store messages
                    processed_count = 0
                    group_id_to_pass = group.id if hasattr(group, 'id') else group
                    for message in messages:
                        if await self._store_message_if_new(message, group_id_to_pass):
                            processed_count += 1
                    
                    total_fetched += processed_count
                    logger.info(f"Processed {processed_count} new messages from group {group}")
                    
                except Exception as e:
                    logger.error(f"Failed to fetch from group {group}: {e}")
                    continue
            
            logger.info(f"Total messages fetched and stored: {total_fetched}")
            return total_fetched
            
        except Exception as e:
            logger.error(f"Failed to fetch historical messages: {e}")
            return 0

    async def _store_message_if_new(self, message, group_id):
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
    
    async def close(self):
        """Close Telegram client connection"""
        if self.client and self.client.is_connected():
            await self.client.disconnect()
            self.client = None
    
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
                    "processed_count": 0,
                    "duplicates_found": 0,
                    "duplicates_removed": 0,
                    "status": "no_new_messages"
                }
            
            # Step 2: Process the newly fetched messages
            logger.info("Processing newly fetched messages...")
            processed_count = await self._process_new_messages()
            
            # Step 3: Detect and handle duplicates
            logger.info("Running duplicate detection and removal...")
            duplicate_results = await self._detect_and_remove_duplicates()
            
            return {
                "fetched_count": fetched_count,
                "processed_count": processed_count,
                "duplicates_found": duplicate_results["found"],
                "duplicates_removed": duplicate_results["removed"],
                "status": "success",
                "details": {
                    "messages_fetched": fetched_count,
                    "jobs_extracted": processed_count,
                    "duplicate_groups": duplicate_results["groups"],
                    "processing_time": duplicate_results["processing_time"]
                }
            }
            
        except Exception as e:
            logger.error(f"Error in enhanced historical fetch: {e}")
            return {
                "fetched_count": 0,
                "processed_count": 0,
                "duplicates_found": 0,
                "duplicates_removed": 0,
                "status": "error",
                "error": str(e)
            }
    
    async def _process_new_messages(self) -> int:
        """Process newly fetched messages using the existing job processing pipeline"""
        try:
            # Import the LLM processor
            from llm_processor import LLMProcessor
            from config import OPENROUTER_API_KEY, OPENROUTER_MODEL, OPENROUTER_FALLBACK_MODEL
            
            llm_processor = LLMProcessor(OPENROUTER_API_KEY, OPENROUTER_MODEL, OPENROUTER_FALLBACK_MODEL)
            
            # Get unprocessed messages that were just added
            unprocessed_messages = self.db.get_unprocessed_messages(limit=100)  # Process more for historical
            
            processed_count = 0
            for message in unprocessed_messages:
                try:
                    self.db.update_message_status(message["id"], "processing")
                    
                    # Parse jobs using LLM
                    parsed_jobs = await llm_processor.parse_jobs(message["message_text"])
                    
                    if not parsed_jobs:
                        self.db.update_message_status(message["id"], "processed", "No jobs found")
                        continue

                    # Process each job
                    for job_data in parsed_jobs:
                        processed_data = llm_processor.process_job_data(job_data, message["id"])
                        
                        try:
                            job_id = self.db.add_processed_job(processed_data)
                            if job_id:
                                processed_count += 1
                                logger.info(f"Processed job {job_id} from message {message['id']}")
                        except Exception as e:
                            logger.error(f"Failed to add processed job: {e}")
                    
                    self.db.update_message_status(message["id"], "processed")
                    logger.info(f"Successfully processed message {message['id']} and found {len(parsed_jobs)} jobs.")
                    
                except Exception as e:
                    logger.error(f"Failed to process message {message['id']}: {e}")
                    self.db.update_message_status(message["id"], "failed", str(e))
            
            return processed_count
            
        except Exception as e:
            logger.error(f"Error processing new messages: {e}")
            return 0
    
    async def _detect_and_remove_duplicates(self) -> dict:
        """Enhanced duplicate detection and removal"""
        import time
        start_time = time.time()
        
        try:
            # Get all processed jobs from the last 48 hours (to focus on recent ones)
            with self.db.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT * FROM processed_jobs
                    WHERE created_at >= CURRENT_TIMESTAMP - INTERVAL '48 hours'
                    ORDER BY created_at DESC
                """)
                recent_jobs = [dict(row) for row in cursor.fetchall()]
            
            duplicate_groups = []
            processed_job_ids = set()
            removed_count = 0
            
            # Group jobs by company + role (with fuzzy matching)
            job_groups = self._group_similar_jobs(recent_jobs)
            
            for group in job_groups:
                if len(group) > 1:  # Potential duplicates found
                    # Mark all but the first as duplicates
                    primary_job = group[0]
                    duplicate_jobs = group[1:]
                    
                    for duplicate_job in duplicate_jobs:
                        try:
                            # Mark as duplicate
                            with self.db.get_connection() as conn:
                                cursor = conn.cursor()
                                cursor.execute("""
                                    UPDATE processed_jobs
                                    SET is_hidden = TRUE
                                    WHERE id = %s
                                """, (duplicate_job['id'],))
                                
                                if cursor.rowcount > 0:
                                    removed_count += 1
                                    processed_job_ids.add(duplicate_job['id'])
                            
                            logger.info(f"Marked duplicate job {duplicate_job['id']} as hidden (duplicate of {primary_job['id']})")
                            
                        except Exception as e:
                            logger.error(f"Error marking duplicate job {duplicate_job['id']}: {e}")
            
            # Also run the dashboard duplicate detection
            dashboard_duplicates = self.db.detect_duplicate_jobs()
            
            processing_time = time.time() - start_time
            
            return {
                "found": len(duplicate_groups),
                "removed": removed_count + dashboard_duplicates,
                "groups": len(duplicate_groups),
                "processing_time": round(processing_time, 2)
            }
            
        except Exception as e:
            logger.error(f"Error in duplicate detection: {e}")
            return {
                "found": 0,
                "removed": 0,
                "groups": 0,
                "processing_time": 0
            }
    
    def _group_similar_jobs(self, jobs: list) -> list:
        """Group jobs by similarity (company + role matching)"""
        import re
        from difflib import SequenceMatcher
        
        def normalize_text(text: str) -> str:
            """Normalize text for comparison"""
            if not text:
                return ""
            # Remove extra spaces, convert to lowercase
            text = re.sub(r'\s+', ' ', text.lower().strip())
            # Remove common company suffixes
            text = re.sub(r'\b(technologies|tech|solutions|services|systems|inc|corp|ltd|private|limited)\b', '', text)
            return text.strip()
        
        def similarity(a: str, b: str) -> float:
            """Calculate similarity between two strings"""
            return SequenceMatcher(None, normalize_text(a), normalize_text(b)).ratio()
        
        # Group jobs by company similarity
        groups = []
        used_jobs = set()
        
        for i, job1 in enumerate(jobs):
            if i in used_jobs:
                continue
                
            group = [job1]
            used_jobs.add(i)
            
            for j, job2 in enumerate(jobs[i+1:], i+1):
                if j in used_jobs:
                    continue
                
                # Check company and role similarity
                company_sim = similarity(job1.get('company_name', ''), job2.get('company_name', ''))
                role_sim = similarity(job1.get('job_role', ''), job2.get('job_role', ''))
                
                # If both company and role are similar enough, consider as duplicates
                if company_sim > 0.8 and role_sim > 0.7:
                    group.append(job2)
                    used_jobs.add(j)
            
            if len(group) > 1:  # Only keep groups with duplicates
                groups.append(group)
        
        return groups

# Main function to run from command line
async def main():
    from config import TELEGRAM_API_ID, TELEGRAM_API_HASH, TELEGRAM_PHONE
    
    # Initialize database and fetcher
    db = Database(DATABASE_URL)
    fetcher = HistoricalMessageFetcher(TELEGRAM_API_ID, TELEGRAM_API_HASH, TELEGRAM_PHONE, db)
    
    try:
        # Connect to Telegram
        if await fetcher.connect_client():
            logger.info("Connected to Telegram successfully")
            
            # Fetch historical messages
            hours_back = 12  # Change this to adjust time range
            fetched_count = await fetcher.fetch_historical_messages(hours_back)
            
            logger.info(f"Historical message fetch complete: {fetched_count} messages processed")
            
        else:
            logger.error("Failed to connect to Telegram")
            
    except Exception as e:
        logger.error(f"Error in main: {e}")
    finally:
        await fetcher.close()

if __name__ == "__main__":
    asyncio.run(main())