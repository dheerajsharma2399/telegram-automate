import asyncio
import logging
from telethon import TelegramClient, events
from config import (
    TELEGRAM_API_ID,
    TELEGRAM_API_HASH,
    TELEGRAM_PHONE,
    AUTHORIZED_USER_IDS,
)
from database import Database
from config import TELEGRAM_GROUP_USERNAMES, DATABASE_URL
from message_utils import extract_message_text, get_message_info, send_rate_limited_telegram_notification, log_execution
from datetime import datetime, timedelta
import psycopg2
import pytz

from telethon.sessions import StringSession

# IST timezone
IST = pytz.timezone('Asia/Kolkata')

class TelegramMonitor:
    def __init__(self, api_id: str, api_hash: str, phone: str, group_usernames, db: Database):
        self.api_id = int(api_id)
        self.api_hash = api_hash
        self.phone = phone
        if isinstance(group_usernames, (str, int)):
            self.group_usernames = [group_usernames]
        else:
            self.group_usernames = list(group_usernames or [])

        # Convert numeric strings to integers
        cleaned = []
        for g in self.group_usernames:
            try:
                cleaned.append(int(g))
            except (ValueError, TypeError):
                cleaned.append(g)
        self.group_usernames = cleaned

        self.db = db
        self.client = None
        self._handler_registered = False
        self._current_monitored_group_ids = set()
        self.initial_group_usernames = group_usernames
        self._update_handlers_task = None
        self.authorized_users = [int(x) for x in AUTHORIZED_USER_IDS if x] if AUTHORIZED_USER_IDS else []

        # Message queue for reliability (kept for potential future hybrid mode)
        self.message_queue = asyncio.Queue(maxsize=1000)
        self.worker_task = None

        # Statistics tracking
        self.stats = {
            'total_received': 0,
            'total_saved': 0,
            'total_skipped': 0,
            'total_errors': 0,
            'last_message_time': None
        }

    @log_execution
    async def start(self):
        logging.info("🚀 Starting Telegram connection manager (Scheduled Polling Mode)...")

        while True:
            try:
                session_string = self.db.auth.get_telegram_session()

                if session_string and session_string.strip():
                    logging.info("Restoring Telegram session from database...")

                    if not self.client or not self.client.is_connected():
                        try:
                            # Create client
                            self.client = TelegramClient(
                                StringSession(session_string),
                                self.api_id,
                                self.api_hash
                            )

                            # Connect client
                            await self.client.connect()

                            if not await self.client.is_user_authorized():
                                logging.warning("Stored session is invalid or expired")
                                self.db.auth.set_telegram_session('')
                                self.db.auth.set_telegram_login_status('session_expired')
                                await self.client.disconnect()
                                self.client = None
                                await asyncio.sleep(30)
                                continue

                            # Update status
                            self.db.auth.set_telegram_login_status('connected')
                            logging.info("✅ Successfully connected to Telegram")

                            # Prime dialog cache - Critical for get_entity to work in fetchers
                            await self._prime_dialog_cache()

                            # Run until disconnected
                            # This keeps the connection alive for the scheduled fetcher to use
                            await self.client.run_until_disconnected()

                        except Exception as e:
                            error_msg = str(e).lower()
                            if "not a valid string" in error_msg or "invalid" in error_msg:
                                logging.warning(f"Invalid session string: {e}")
                                self.db.auth.set_telegram_session('')
                                self.db.auth.set_telegram_login_status('session_expired')
                            else:
                                logging.error(f"Connection error: {e}")
                                self.db.auth.set_telegram_login_status('connection_failed')

                            self.client = None
                            await asyncio.sleep(30)
                            continue

                else:
                    logging.info("No Telegram session found. Waiting for setup...")
                    self.db.auth.set_telegram_login_status('not_authenticated')
                    await asyncio.sleep(30)

            except (psycopg2.Error, OSError) as e:
                logging.error(f"Monitor error: {e}")
                await asyncio.sleep(30)
            finally:
                await self.stop()

    async def stop(self):
        """Stop the monitor"""
        if self.client and self.client.is_connected():
            logging.info("Stopping Telegram monitor...")
            await self.client.disconnect()

    async def _prime_dialog_cache(self):
        """Prime entity cache"""
        if not self.client or not self.client.is_connected():
            return
        try:
            logging.info("Priming entity cache (fetching top 500 dialogs)...")
            await self.client.get_dialogs(limit=500)
            logging.info("✅ Entity cache primed")
        except Exception as e:
            logging.warning(f"Could not prime cache: {e}")

    async def save_session_to_db(self):
        """Save session to database"""
        if self.client and self.client.is_connected():
            session_string = self.client.session.save()
            self.db.auth.set_telegram_session(session_string)
            self.db.auth.set_telegram_login_status('connected')
            logging.info("Telegram session saved")
            return True
        return False

    async def clear_session_from_db(self):
        """Clear session from database"""
        try:
            self.db.auth.set_telegram_session('')
            self.db.auth.set_telegram_login_status('not_authenticated')
            logging.info("Telegram session cleared")
            return True
        except Exception as e:
            logging.error(f"Failed to clear session: {e}")
            return False

if __name__ == "__main__":
    # Configure logging only when running standalone
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler("/app/logs/app.log"),
            logging.StreamHandler()
        ]
    )
    db = Database(DATABASE_URL)
    monitor = TelegramMonitor(
        TELEGRAM_API_ID,
        TELEGRAM_API_HASH,
        TELEGRAM_PHONE,
        TELEGRAM_GROUP_USERNAMES,
        db,
    )
    asyncio.run(monitor.start())
