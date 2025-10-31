import asyncio
import logging
from telethon import TelegramClient, events
from config import (
    TELEGRAM_API_ID,
    TELEGRAM_API_HASH,
    TELEGRAM_PHONE,
    TELEGRAM_GROUP_USERNAME,
)
from database import Database
from config import TELEGRAM_GROUP_USERNAMES, DATABASE_URL

logging.basicConfig(
    level=logging.INFO, 
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("monitor.log"),
        logging.StreamHandler()
    ]
)

from telethon.sessions import StringSession

class TelegramMonitor:
    def __init__(self, api_id: str, api_hash: str, phone: str, group_usernames, db: Database):
        self.api_id = int(api_id)
        self.api_hash = api_hash
        self.phone = phone
        if isinstance(group_usernames, (str, int)):
            self.group_usernames = [group_usernames]
        else:
            self.group_usernames = list(group_usernames or [])
        cleaned = []
        for g in self.group_usernames:
            try:
                cleaned.append(int(g))
            except (ValueError, TypeError):
                cleaned.append(g)
        self.group_usernames = cleaned
        self.db = db
        self.client = None # Initialize client as None
        self._handler_registered = False
        self.initial_group_usernames = group_usernames

    async def start(self):
        logging.info("Starting Telegram monitor loop...")
        
        while True:
            try:
                session_string = self.db.get_telegram_session()
                
                if session_string:
                    logging.info("Restoring Telegram session from database...")
                    if not self.client or not self.client.is_connected():
                        self.client = TelegramClient(StringSession(session_string), self.api_id, self.api_hash)
                        try:
                            await self.client.connect()
                            if not await self.client.is_user_authorized():
                                logging.warning("Stored session is invalid or expired. Clearing from database.")
                                self.db.set_telegram_session('')
                                self.db.set_telegram_login_status('session_expired')
                                await self.client.disconnect()
                                self.client = None
                                await asyncio.sleep(30)
                                continue
                            
                            # Update login status to connected
                            self.db.set_telegram_login_status('connected')
                            logging.info("Successfully restored Telegram session and connected.")
                            
                        except Exception as e:
                            logging.error(f"Failed to connect with stored session: {e}")
                            self.db.set_telegram_session('')
                            self.db.set_telegram_login_status('connection_failed')
                            self.client = None
                            await asyncio.sleep(30)
                            continue

                    logging.info("Client connected and authorized. Setting up message handlers.")
                    try:
                        await self._ensure_handler_registered()

                        async def _refresh_loop():
                            while True:
                                try:
                                    await asyncio.sleep(60)
                                    await self._ensure_handler_registered()
                                except asyncio.CancelledError:
                                    break
                                except Exception as e:
                                    logging.error(f"Error in monitor refresh loop: {e}")

                        refresher = asyncio.create_task(_refresh_loop())
                        try:
                            await self.client.run_until_disconnected()
                            logging.info("Client disconnected. Will attempt to reconnect.")
                        finally:
                            refresher.cancel()
                    except Exception as e:
                        logging.error(f"Error during monitor execution: {e}")
                    finally:
                        await self.stop()
                else:
                    logging.info("No active Telegram session found in database. Waiting for setup via web UI.")
                    self.db.set_telegram_login_status('not_authenticated')
                    await asyncio.sleep(30) # Wait before checking for a session again
                    
            except Exception as e:
                logging.error(f"Error in monitor start loop: {e}")
                await asyncio.sleep(30)

    async def stop(self):
        """Stops the Telegram client."""
        if self.client and self.client.is_connected():
            logging.info("Stopping Telegram monitor...")
            await self.client.disconnect()

    async def _ensure_handler_registered(self):
        """Ensure the NewMessage handler is registered for the current monitored groups configured in DB.
        Re-registers the handler when the list of monitored groups changes.
        """
        if not self.client:
            return

        groups_val = self.db.get_config('monitored_groups') or ''
        groups = [s for s in groups_val.split(',') if s] or list(self.initial_group_usernames or [])

        cleaned = []
        for g in groups:
            try:
                cleaned.append(int(g))
            except Exception:
                cleaned.append(g)

        if self._handler_registered and getattr(self, '_last_groups', None) == cleaned:
            return

        try:
            if self._handler_registered:
                self.client.remove_event_handler(None, events.NewMessage)
        except Exception:
            pass

        entities = []
        for g in cleaned:
            try:
                ent = await self.client.get_entity(g)
                entities.append(ent)
                logging.info(f"Monitoring group: {g}")
            except Exception as e:
                logging.error(f"Failed to get entity for {g}: {e}")

        if not entities:
            logging.warning("No group entities resolved to monitor.")
            self._handler_registered = False
            self._last_groups = cleaned
            return

        @self.client.on(events.NewMessage(chats=entities))
        async def handler(event):
            try:
                logging.info(f"New message received: {event.message.id}")
                self.db.add_raw_message(
                    message_id=event.message.id,
                    message_text=event.message.text,
                    sender_id=event.message.sender_id,
                    sent_at=event.message.date,
                )
            except Exception as e:
                logging.error(f"Failed to add raw message: {e}")

        self._handler_registered = True
        self._last_groups = cleaned
        logging.info(f"Message handler registered for {len(entities)} groups.")
    
    async def save_session_to_db(self):
        """Save current session string to database"""
        try:
            if self.client and self.client.is_connected():
                session_string = self.client.session.save()
                self.db.set_telegram_session(session_string)
                self.db.set_telegram_login_status('connected')
                logging.info("Telegram session saved to database")
                return True
        except Exception as e:
            logging.error(f"Failed to save Telegram session to database: {e}")
        return False
    
    async def clear_session_from_db(self):
        """Clear session from database"""
        try:
            self.db.set_telegram_session('')
            self.db.set_telegram_login_status('not_authenticated')
            logging.info("Telegram session cleared from database")
            return True
        except Exception as e:
            logging.error(f"Failed to clear Telegram session from database: {e}")
            return False

if __name__ == "__main__":
    db = Database(DATABASE_URL)
    monitor = TelegramMonitor(
        TELEGRAM_API_ID,
        TELEGRAM_API_HASH,
        TELEGRAM_PHONE,
        TELEGRAM_GROUP_USERNAMES,
        db,
    )
    asyncio.run(monitor.start())