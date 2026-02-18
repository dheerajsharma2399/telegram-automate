import os
import asyncio
import logging
from datetime import datetime, timedelta

# Ensure paths are correct for imports
import sys
# Add project root to sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import (
    DATABASE_URL,
    TELEGRAM_API_ID,
    TELEGRAM_API_HASH,
    TELEGRAM_PHONE,
    AUTHORIZED_USER_IDS,
    ADMIN_USER_ID
)
from database import Database
from telethon import TelegramClient
from telethon.sessions import StringSession

# --- Logging Setup ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

async def run_diagnostics():
    logger.info("--- Starting Diagnostic Script ---")

    # 1. Test Database Connection
    logger.info("\n--- Test 1: Database Connection ---")
    db = None
    try:
        db = Database(DATABASE_URL)
        logger.info("Successfully connected to PostgreSQL database.")
    except Exception as e:
        logger.error(f"Failed to connect to database: {e}")
        return # Cannot proceed without DB

    # 2. Test Telegram Session and Client Connection
    logger.info("\n--- Test 2: Telegram Session and Client Connection ---")
    telegram_status = db.auth.get_telegram_login_status()
    session_string = db.auth.get_telegram_session()
    logger.info(f"Telegram login status from DB: '{telegram_status}'")
    logger.info(f"Telegram session string exists in DB: {bool(session_string)}")

    client = None
    if session_string:
        try:
            client = TelegramClient(StringSession(session_string), int(TELEGRAM_API_ID), TELEGRAM_API_HASH)
            await client.connect()
            if await client.is_user_authorized():
                logger.info("Successfully connected Telegram client and user is authorized.")
            else:
                logger.error("Telegram client connected, but user is NOT authorized. Session might be expired.")
                db.auth.set_telegram_login_status('session_expired')
                await client.disconnect()
                client = None
        except Exception as e:
            logger.error(f"Failed to connect Telegram client with stored session: {e}")
            client = None
    else:
        logger.warning("No Telegram session string found in database. Bot cannot monitor.")

    # 3. Test Command Enqueueing
    logger.info("\n--- Test 3: Command Enqueueing ---")
    test_command = "/diagnostic_test_command"
    try:
        cmd_id = db.commands.enqueue_command(test_command)
        if cmd_id:
            logger.info(f"Successfully enqueued test command '{test_command}' with ID: {cmd_id}")
            # Verify it's in the queue
            pending_commands = db.commands.list_all_pending_commands()
            found = any(c['id'] == cmd_id for c in pending_commands)
            logger.info(f"Test command found in pending queue: {found}")
            # Clean up: mark as done
            db.commands.update_command_result(cmd_id, 'done', result_text="Diagnostic cleanup")
            logger.info(f"Cleaned up test command {cmd_id}.")
        else:
            logger.error(f"Failed to enqueue test command '{test_command}'.")
    except Exception as e:
        logger.error(f"Error during command enqueueing test: {e}")

    # 4. Test Command Polling (simulated)
    logger.info("\n--- Test 4: Command Polling (Simulated) ---")
    try:
        # Enqueue a command for the poller to find
        poller_test_command = "/poller_test"
        poller_cmd_id = db.commands.enqueue_command(poller_test_command)
        if poller_cmd_id:
            logger.info(f"Enqueued command '{poller_test_command}' for poller test (ID: {poller_cmd_id}).")
            
            pending = db.commands.get_pending_commands(limit=1)
            logger.info(f"Pending commands retrieved by poller test: {pending}") # Added debug log
            if pending and pending[0]['id'] == poller_cmd_id:
                logger.info(f"Poller successfully retrieved pending command: {pending[0]['command']}")
                db.commands.update_command_result(poller_cmd_id, 'done', result_text="Poller test cleanup")
                logger.info(f"Cleaned up poller test command {poller_cmd_id}.")
            else:
                logger.error("Poller test failed: Did not retrieve the enqueued command.")
        else:
            logger.error("Poller test failed: Could not enqueue command.")
    except Exception as e:
        logger.error(f"Error during command polling test: {e}")

    if client and client.is_connected():
        await client.disconnect()

    logger.info("\n--- Diagnostic Script Finished ---")

if __name__ == "__main__":
    asyncio.run(run_diagnostics())
