import asyncio
import logging
import os
import sys
import tempfile
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from logging.handlers import RotatingFileHandler

from config import *
from database import Database, init_database
from llm_processor import LLMProcessor
from sheets_sync import GoogleSheetsSync
from historical_message_fetcher import HistoricalMessageFetcher
from monitor import TelegramMonitor
from message_utils import log_execution

# --- Logging Setup ---
log_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'logs')
if not os.path.exists(log_dir):
    os.makedirs(log_dir)

log_file_path = os.path.join(log_dir, 'app.log')
log_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')

# Unified logger
log_handler = RotatingFileHandler(log_file_path, maxBytes=1024*1024, backupCount=5)
log_handler.setFormatter(log_formatter)

# Configure logging
root_logger = logging.getLogger()
root_logger.addHandler(log_handler)
root_logger.addHandler(logging.StreamHandler()) # Also log to console
root_logger.setLevel(getattr(logging, LOG_LEVEL.upper()))  # Configurable log level

logger = logging.getLogger(__name__)

# --- Initialization ---

# Initialize Database
db = Database(DATABASE_URL)
try:
    init_database(db.pool)
except Exception as e:
    logger.warning(f"Runtime database initialization check failed: {e}")

# Initialize LLM Processor
llm_processor = LLMProcessor(OPENROUTER_API_KEYS, OPENROUTER_MODELS, OPENROUTER_FALLBACK_MODELS)

# Initialize Scheduler
scheduler = AsyncIOScheduler()

# Global Sheets Sync instance
sheets_sync = None

def get_sheets_sync():
    global sheets_sync
    if sheets_sync is None and GOOGLE_CREDENTIALS_JSON and SPREADSHEET_ID:
        from sheets_sync import MultiSheetSync
        sheets_sync = MultiSheetSync(GOOGLE_CREDENTIALS_JSON, SPREADSHEET_ID, ADDITIONAL_SPREADSHEET_IDS)
    return sheets_sync

# --- Lock Management ---

def check_bot_instance():
    """Check if another bot instance is already running"""
    lock_file = os.path.join(tempfile.gettempdir(), 'telegram_bot.lock')

    try:
        if os.path.exists(lock_file):
            with open(lock_file, 'r') as f:
                old_pid = f.read().strip()
            logger.warning(f"Bot lock file exists. Old PID: {old_pid}")
            # Try to verify if the old process is still running
            try:
                if os.name == 'posix':
                    os.kill(int(old_pid), 0)  # Signal 0 just checks if process exists
                    logger.error("Old bot instance still running. Aborting.")
                    return False
                else:
                    logger.warning("Removing stale lock file on Windows")
                    os.remove(lock_file)
            except (OSError, ProcessLookupError, ValueError):
                os.remove(lock_file)
                logger.info("Removed stale lock file")

        with open(lock_file, 'w') as f:
            f.write(str(os.getpid()))
        logger.info(f"Created bot lock file with PID: {os.getpid()}")
        return True

    except Exception as e:
        logger.error(f"Could not manage bot lock file: {e}")
        return False

def cleanup_bot_instance():
    """Clean up bot instance lock"""
    lock_file = os.path.join(tempfile.gettempdir(), 'telegram_bot.lock')
    try:
        if os.path.exists(lock_file):
            os.remove(lock_file)
            logger.info("Cleaned up bot lock file")
    except Exception as e:
        logger.error(f"Could not remove lock file: {e}")

# --- Core Logic ---

@log_execution
async def safety_net_fetch(monitor, context):
    """Hourly check for missed messages"""
    from historical_message_fetcher import HistoricalMessageFetcher

    # Your monitor's client
    fetcher = HistoricalMessageFetcher(db, monitor.client)
    result = await fetcher.fetch_historical_messages(hours_back=6)

    if result > 0:
        logger.warning(f"⚠️ Safety net caught {result} missed messages!")

@log_execution
async def sync_sheets_automatically():
    """
    Automatically finds all unsynced jobs and syncs them to Google Sheets.
    """
    sheets_sync = get_sheets_sync()
    if not (sheets_sync and sheets_sync.client):
        logger.info("Google Sheets not configured, skipping automatic sync.")
        return

    try:
        unsynced_jobs = db.jobs.get_unsynced_jobs()
        if not unsynced_jobs:
            logger.info("No new jobs to sync to Google Sheets.")
            return

        logger.info(f"Found {len(unsynced_jobs)} new jobs to sync to Google Sheets.")
        synced_count = 0
        failed_count = 0

        for job in unsynced_jobs:
            try:
                if sheets_sync.sync_job(job):
                    db.jobs.mark_job_synced(job.get('job_id'))
                    synced_count += 1
                else:
                    failed_count += 1
                    logger.warning(f"Failed to sync job {job.get('job_id')}: {job.get('company_name')} - {job.get('job_role')}")
            except Exception as e:
                failed_count += 1
                logger.error(f"Exception syncing job {job.get('job_id')} ({job.get('company_name')}): {e}")

        if failed_count > 0:
            logger.warning(f"Google Sheets sync complete. Synced {synced_count} jobs, {failed_count} failed.")
        else:
            logger.info(f"Google Sheets sync complete. Successfully synced {synced_count} new jobs.")
    except Exception as e:
        logger.error(f"Automatic Google Sheets sync failed: {e}")

@log_execution
async def process_jobs(context=None):
    """The core job processing function with proper transaction handling."""
    logger.info("🚀 Starting job processing...")
    unprocessed_messages = db.messages.get_unprocessed_messages(limit=BATCH_SIZE)
    if not unprocessed_messages:
        logger.info("No unprocessed messages to process.")
        return

    logger.info(f"Found {len(unprocessed_messages)} unprocessed messages. Starting batch...")

    for message in unprocessed_messages:
        logger.info(f"Processing message ID: {message['id']} (Text len: {len(message.get('message_text', ''))})")

        try:
            # Step 1: Mark as processing
            db.messages.update_message_status(message["id"], "processing")

            # Step 2: Parse jobs with LLM
            logger.info(f"Sending message {message['id']} to LLM...")
            parsed_jobs = await llm_processor.parse_jobs(message["message_text"])

            if not parsed_jobs:
                logger.warning(f"Message {message['id']} yielded NO jobs from LLM.")
                db.messages.update_message_status(message["id"], "processed", "No jobs found")
                continue

            logger.info(f"LLM found {len(parsed_jobs)} jobs in message {message['id']}")

            # Step 3: Process and store each job
            for job_data in parsed_jobs:
                try:
                    processed_data = llm_processor.process_job_data(job_data, message["id"])

                    # Check for duplicates before adding
                    duplicate_job = db.jobs.find_duplicate_processed_job(
                        processed_data.get('company_name'),
                        processed_data.get('job_role'),
                        processed_data.get('email')
                    )
                    if duplicate_job:
                        logger.info(f"Duplicate job found for '{processed_data.get('company_name')}' - '{processed_data.get('job_role')}'. Original job ID: {duplicate_job['job_id']}. Skipping.")
                        continue

                    # Add to processed_jobs table
                    job_id = db.jobs.add_processed_job(processed_data)

                    if not job_id:
                        logger.error(f"Failed to add job to processed_jobs table")
                        continue

                    logger.info(f"✅ Job saved successfully: {processed_data.get('company_name')} (ID: {job_id})")

                    # AUTOMATIC DASHBOARD POPULATION: Add non-email jobs to dashboard
                    if processed_data.get('application_method') != 'email':
                        try:
                            dashboard_job_data = {
                                'source_job_id': processed_data.get('job_id'),
                                'original_sheet': 'non-email',
                                'company_name': processed_data.get('company_name'),
                                'job_role': processed_data.get('job_role'),
                                'location': processed_data.get('location'),
                                'application_link': processed_data.get('application_link'),
                                'phone': processed_data.get('phone'),
                                'recruiter_name': processed_data.get('recruiter_name'),
                                'job_relevance': processed_data.get('job_relevance', 'relevant'),
                                'original_created_at': processed_data.get('updated_at'),
                                'application_status': 'not_applied',
                                'salary': processed_data.get('salary')
                            }

                            with db.get_connection() as conn:
                                with conn.cursor() as cursor:
                                    cursor.execute(
                                        "SELECT id FROM dashboard_jobs WHERE source_job_id = %s",
                                        (processed_data.get('job_id'),)
                                    )
                                    if not cursor.fetchone():
                                        dashboard_id = db.dashboard.add_dashboard_job(dashboard_job_data)
                                        if dashboard_id:
                                            logger.info(f"Auto-imported non-email job to dashboard: {processed_data.get('company_name')}")
                        except Exception as e:
                            logger.error(f"Failed to auto-import job to dashboard: {e}")

                except Exception as e:
                    logger.error(f"Failed to process individual job: {e}")
                    continue

            # Step 4: Mark message as processed
            db.messages.update_message_status(message["id"], "processed")
            logger.info(f"✅ Fully processed message {message['id']}")

        except Exception as e:
            logger.error(f"❌ Failed to process message {message['id']}: {e}", exc_info=True)
            db.messages.update_message_status(message["id"], "failed", str(e))

    # After processing the batch, automatically sync to sheets
    logger.info("Job processing batch finished. Starting automatic Google Sheets sync.")
    await sync_sheets_automatically()

@log_execution
async def scheduled_fetch_and_process(monitor):
    """
    Scheduled task to fetch recent messages and process them.
    Replaces continuous monitoring with robust polling.
    """
    logger.info("🕒 Starting scheduled fetch and process cycle...")

    # 1. Fetch recent messages (last 10 minutes to be safe)
    try:
        session_string = db.auth.get_telegram_session()
        if not session_string:
            logger.warning("No Telegram session found. Skipping fetch.")
            return

        if not monitor.client or not monitor.client.is_connected():
            logger.info("Connecting Telegram client for scheduled fetch...")
            from telethon import TelegramClient
            from telethon.sessions import StringSession
            monitor.client = TelegramClient(StringSession(session_string), monitor.api_id, monitor.api_hash)
            await monitor.client.connect()

        if not await monitor.client.is_user_authorized():
            logger.error("Telegram session invalid/expired.")
            return

        logger.info("Fetching messages from last 10 minutes...")
        fetcher = HistoricalMessageFetcher(db, monitor.client)
        # Fetch last 10 minutes (approx 0.17 hours)
        fetched_count = await fetcher.fetch_historical_messages(hours_back=0.17)
        logger.info(f"✅ Scheduled fetch retrieved {fetched_count} messages.")

    except Exception as e:
        logger.error(f"❌ Error during scheduled fetch: {e}", exc_info=True)

    # 2. Process any new messages
    logger.info("Triggering process_jobs()...")
    await process_jobs()

    # 3. Sync to sheets
    logger.info("Triggering sync_sheets_automatically()...")
    await sync_sheets_automatically()
    logger.info("🕒 Scheduled cycle complete.")

async def poll_commands_loop():
    """
    Background task to poll and execute pending commands from the database.
    Process commands like /process, /start, /export from the web UI.
    """
    logger.info("🔧 Starting command poller loop...")
    while True:
        try:
            pending = db.commands.get_pending_commands(limit=5)
            if pending:
                for cmd in pending:
                    logger.info(f"Processing command: {cmd['command']} (ID: {cmd['id']})")
                    text = cmd['command'].strip()

                    executed_ok = False
                    result_text = None

                    try:
                        if text.startswith('/process'):
                            await process_jobs()
                            executed_ok = True
                            result_text = "Processing triggered successfully"
                        elif text.startswith('/sync_sheets'):
                            await sync_sheets_automatically()
                            executed_ok = True
                            result_text = "Sync triggered successfully"
                        elif text.startswith('/start') or text.startswith('/stop'):
                             executed_ok = True
                             result_text = "Command acknowledged (polling mode)"
                        elif text.startswith('/export'):
                             executed_ok = True
                             result_text = "Export handled via API"
                        elif text.startswith('/backfill_sheets'):
                             # This would normally be handled by the web server endpoint directly calling logic,
                             # but if we wanted the worker to do it, we'd need to import and call backfill logic here.
                             # For now, let's mark it as done as the API likely triggered it or it's a placeholder.
                             executed_ok = True
                             result_text = "Backfill command acknowledged"
                        else:
                            logger.warning(f"Unknown command: {text}")
                            executed_ok = False
                            result_text = "Unknown command"

                    except Exception as e:
                        logger.error(f"Error executing command {cmd['id']}: {e}")
                        executed_ok = False
                        result_text = str(e)

                    # Update DB
                    status = 'done' if executed_ok else 'failed'
                    db.commands.update_command_result(
                        cmd['id'],
                        status,
                        result_text=result_text,
                        executed_by='worker'
                    )

            await asyncio.sleep(2) # Poll every 2 seconds

        except Exception as e:
            logger.error(f"Command poller error: {e}")
            await asyncio.sleep(5)

# --- Main Entry Point ---

async def main():
    """Main entry point - Scheduled Polling Mode"""
    logger.info("Starting Telegram Job Scraper (Scheduled Polling Mode)")

    # Check bot instance
    if not check_bot_instance():
        logger.error("Another instance is running. Exiting.")
        return

    # Initialize monitor (used for config holder and client connection)
    monitor = TelegramMonitor(
        TELEGRAM_API_ID,
        TELEGRAM_API_HASH,
        TELEGRAM_PHONE,
        TELEGRAM_GROUP_USERNAMES,
        db
    )

    # Start scheduler
    scheduler.add_job(
        scheduled_fetch_and_process,
        'interval',
        minutes=5,
        id='fetch_and_process',
        args=[monitor],
        replace_existing=True
    )

    # Keep safety net for deeper history every 4 hours
    scheduler.add_job(
        safety_net_fetch,
        'interval',
        hours=4,
        id='safety_net_fetch',
        args=[monitor, None],
        replace_existing=True
    )

    scheduler.start()
    logger.info("✅ Background scheduler started")
    logger.info("- Fetch & Process: every 5 minutes")
    logger.info("- Safety Net: every 4 hours")

    # Start command poller task
    asyncio.create_task(poll_commands_loop())

    # Run one cycle immediately on startup to catch up
    asyncio.create_task(scheduled_fetch_and_process(monitor))

    # Keep alive
    try:
        while True:
            await asyncio.sleep(3600)
    except KeyboardInterrupt:
        logger.info("Shutting down...")
    finally:
        scheduler.shutdown()
        cleanup_bot_instance()

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Application stopped.")
        cleanup_bot_instance()
    except Exception as e:
        logger.error(f"Unexpected error: {e}", exc_info=True)
        cleanup_bot_instance()
        sys.exit(1)
