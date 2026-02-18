import asyncio
import logging
from telethon import TelegramClient
from config import (
    TELEGRAM_API_ID,
    TELEGRAM_API_HASH,
    TELEGRAM_PHONE,
    AUTHORIZED_USER_IDS,
    TELEGRAM_GROUP_USERNAMES,
    DATABASE_URL
)
from database import Database
from message_utils import log_execution
from telethon.sessions import StringSession
import psycopg2

class TelegramMonitor:
    def __init__(self, api_id: str, api_hash: str, phone: str, group_usernames, db: Database):
        self.api_id = int(api_id)
        self.api_hash = api_hash
        self.phone = phone

        # Parse group usernames/IDs
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
        self.authorized_users = [int(x) for x in AUTHORIZED_USER_IDS if x] if AUTHORIZED_USER_IDS else []

    @log_execution
    async def start(self):
        """
        Starts the Telegram Client and keeps it connected.
        This is the main loop for the Worker process.
        """
        logging.info("🚀 Starting Telegram connection manager (Scheduled Polling Mode)...")

        while True:
            try:
                session_string = self.db.auth.get_telegram_session()

                if session_string and session_string.strip():
                    if not self.client or not self.client.is_connected():
                        logging.info("Restoring Telegram session from database...")
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
                            # This blocks here, keeping the connection alive for the scheduler
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
                        # If already connected but loop broke, just sleep and retry
                        await asyncio.sleep(10)

                else:
                    logging.info("No Telegram session found. Waiting for setup...")
                    self.db.auth.set_telegram_login_status('not_authenticated')
                    await asyncio.sleep(30)

            except (psycopg2.Error, OSError) as e:
                logging.error(f"Monitor error: {e}")
                await asyncio.sleep(30)
            except Exception as e:
                logging.error(f"Unexpected monitor error: {e}", exc_info=True)
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

if __name__ == "__main__":
    # Configure logging only when running standalone
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler("logs/app.log"),
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
