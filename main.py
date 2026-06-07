import asyncio
import fcntl
import logging
import os
import sys
import tempfile
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from logging.handlers import RotatingFileHandler

from config import *
from datetime import datetime
from database import Database, init_database
from llm_processor import LLMProcessor
from sheets_sync import GoogleSheetsSync
from monitor import TelegramMonitor
from message_utils import log_execution
from services.processing_service import ProcessingService
from services.scraping_service import ScrapingService
from services.telegram_session import TelegramSessionService

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

# Lazy runtime state. Keep imports side-effect free for tests/tooling.
db = None
llm_processor = None
scheduler = AsyncIOScheduler()
sheets_sync = None
_processing_service = None


def get_scraping_service():
    current_db = get_db()
    session_service = TelegramSessionService(current_db, TELEGRAM_API_ID, TELEGRAM_API_HASH, TELEGRAM_PHONE)
    return ScrapingService(current_db, session_service)



def get_db():
    global db
    if db is None:
        if not DATABASE_URL:
            raise RuntimeError("DATABASE_URL is not configured")
        db = Database(DATABASE_URL)
        try:
            init_database(db.pool)
        except Exception as e:
            logger.warning(f"Runtime database initialization check failed: {e}")
    return db


def get_llm_processor():
    global llm_processor
    if llm_processor is None:
        llm_processor = LLMProcessor(OPENROUTER_API_KEYS, OPENROUTER_MODELS, OPENROUTER_FALLBACK_MODELS)
    return llm_processor


def get_sheets_sync():
    global sheets_sync
    if sheets_sync is None and GOOGLE_CREDENTIALS_JSON and SPREADSHEET_ID:
        from sheets_sync import MultiSheetSync
        sheets_sync = MultiSheetSync(GOOGLE_CREDENTIALS_JSON, SPREADSHEET_ID, ADDITIONAL_SPREADSHEET_IDS)
    return sheets_sync


def get_processing_service():
    global _processing_service
    if _processing_service is None:
        _processing_service = ProcessingService(get_db(), get_llm_processor(), get_sheets_sync)
    return _processing_service

# --- Lock Management ---

_lock_fd = None

def check_bot_instance():
    """Check if another bot instance is already running using atomic file locking"""
    global _lock_fd
    lock_file = os.path.join(tempfile.gettempdir(), 'telegram_bot.lock')
    
    try:
        _lock_fd = open(lock_file, 'w')
        # Try to acquire exclusive lock (non-blocking)
        fcntl.flock(_lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        _lock_fd.write(str(os.getpid()))
        _lock_fd.flush()
        logger.info(f"Created bot lock file with PID: {os.getpid()}")
        return True
    except (IOError, OSError) as e:
        logger.error(f"Another bot instance is running (lock held): {e}")
        return False

def cleanup_bot_instance():
    """Clean up bot instance lock"""
    global _lock_fd
    if _lock_fd:
        try:
            fcntl.flock(_lock_fd, fcntl.LOCK_UN)
            _lock_fd.close()
            logger.info("Released bot lock file")
        except Exception as e:
            logger.error(f"Could not release lock: {e}")

# --- Core Logic ---

@log_execution
async def safety_net_fetch(monitor, context):
    """Hourly check for missed messages"""
    current_db = get_db()
    scraper = get_scraping_service()
    result = await scraper.fetch_historical_messages(hours_back=6, enqueue_process=False, client=monitor.client)

    if result.get("fetched_count", 0) > 0:
        logger.warning(f"⚠️ Safety net caught {result.get('fetched_count', 0)} missed messages!")

@log_execution
async def daily_deep_fetch(monitor, context):
    """
    Daily deep fetch to cover potential downtime.
    Fetches messages from the last 3 days (72 hours).
    Any duplicates will be handled by the database constraint (ON CONFLICT DO NOTHING),
    so this is safe to run repeatedly.
    """

    logger.info("🕵️ Starting daily downtime recovery fetch (Last 72 hours)...")

    current_db = get_db()
    scraper = get_scraping_service()

    # 72 hours = 3 days coverage
    result = await scraper.fetch_historical_messages(hours_back=72, enqueue_process=False, client=monitor.client)

    logger.info(f"✅ Daily recovery fetch complete. Retrieved {result.get('fetched_count', 0)} messages.")

    if result.get("fetched_count", 0) > 0:
        logger.info("Recovered messages were ingested as raw_events for processor_worker.")

@log_execution
async def sync_sheets_automatically():
    """Synchronize unsynced jobs to Google Sheets."""
    await get_processing_service().sync_sheets_automatically()

@log_execution
async def process_jobs(context=None):
    """Compatibility wrapper for the processing service."""
    return await get_processing_service().process_pending_messages(batch_size=BATCH_SIZE, sync_sheets=True)

@log_execution
async def scheduled_fetch_and_process(monitor):
    """
    Scheduled task to fetch recent messages into raw_events.
    Replaces continuous monitoring with robust polling.
    """
    current_db = get_db()
    status = current_db.config.get_config('monitoring_status')
    if status != 'running':
        logger.info(f"⏸️ Monitoring is paused (Status: {status}). Skipping scheduled fetch.")
        return

    logger.info("🕒 Starting scheduled fetch cycle...")

    try:
        scraper = get_scraping_service()
        logger.info("Fetching messages from last 10 minutes...")
        hours_back = FETCH_LOOKBACK_MINUTES / 60.0
        logger.info(f"Fetching messages from last {FETCH_LOOKBACK_MINUTES} minutes ({hours_back:.2f} hours)...")
        result = await scraper.fetch_historical_messages(hours_back=hours_back, enqueue_process=False, client=monitor.client)
        logger.info(f"✅ Scheduled fetch retrieved {result.get('fetched_count', 0)} messages.")
    except Exception as e:
        logger.error(f"❌ Error during scheduled fetch: {e}", exc_info=True)

    logger.info("🕒 Scheduled fetch complete; raw_events are queued for processor_worker.")

async def poll_commands_loop():
    """
    Background task to poll and execute pending commands from the database.
    Process commands like /process, /start, /export from the web UI.
    """
    current_db = get_db()
    logger.info("🔧 Starting command poller loop...")
    while True:
        try:
            pending = current_db.commands.get_pending_commands(limit=5)
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
                    current_db.commands.update_command_result(
                        cmd['id'],
                        status,
                        result_text=result_text,
                        executed_by='worker'
                    )

            # Heartbeat (log every ~30 seconds to show aliveness)
            if int(asyncio.get_event_loop().time()) % 30 == 0:
                 logger.debug("💓 Bot heartbeat - waiting for commands...")

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

    current_db = get_db()
    # Initialize monitor (used for config holder and client connection)
    monitor = TelegramMonitor(
        TELEGRAM_API_ID,
        TELEGRAM_API_HASH,
        TELEGRAM_PHONE,
        TELEGRAM_GROUP_USERNAMES,
        current_db
    )

    # Check initial status
    # FORCE START: Ensure monitoring is set to 'running' on startup to fix "stuck" state
    current_status = current_db.config.get_config('monitoring_status')
    logger.info(f"Current monitoring status: {current_status}")
    
    if current_status != 'running':
        logger.warning(f"⚠️ Status was '{current_status}'. Forcing to 'running' to ensure startup.")
        current_db.config.set_config('monitoring_status', 'running')
        logger.info("✅ Monitoring forced to 'running'")

    # Start scheduler
    scheduler.add_job(
        scheduled_fetch_and_process,
        'interval',
        minutes=FETCH_INTERVAL_MINUTES,
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
    logger.info(f"- Fetch & Process: every {FETCH_INTERVAL_MINUTES} minutes")
    logger.info("- Safety Net: every 4 hours")

    # Deep Fetch for Downtime Recovery (Daily at 3 AM)
    scheduler.add_job(
        daily_deep_fetch,
        'cron',
        hour=3,
        minute=0,
        id='daily_deep_fetch',
        args=[monitor, None],
        replace_existing=True
    )
    logger.info("- Downtime Recovery: Daily at 03:00 AM (Last 3 Days)")

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
