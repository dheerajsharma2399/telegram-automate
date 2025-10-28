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
from config import TELEGRAM_GROUP_USERNAMES

logging.basicConfig(
    level=logging.INFO, 
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("monitor.log"),
        logging.StreamHandler()
    ]
)

class TelegramMonitor:
    def __init__(self, api_id: str, api_hash: str, phone: str, group_usernames, db: Database):
        """group_usernames may be a single string/ID or an iterable of strings/IDs."""
        self.api_id = int(api_id)
        self.api_hash = api_hash
        self.phone = phone
        # Normalize to list
        if isinstance(group_usernames, (str, int)):
            self.group_usernames = [group_usernames]
        else:
            self.group_usernames = list(group_usernames or [])
        # try to convert numeric strings to ints where possible
        cleaned = []
        for g in self.group_usernames:
            try:
                cleaned.append(int(g))
            except (ValueError, TypeError):
                cleaned.append(g)
        self.group_usernames = cleaned
        self.db = db
        self.client = TelegramClient('telegram_monitor', self.api_id, self.api_hash)
        self._handler_registered = False
        # initial groups (may be overridden by DB-stored config)
        self.initial_group_usernames = group_usernames

    async def start(self):
        """Starts the Telegram client and listens for new messages in the specified group."""
        logging.info("Starting Telegram monitor...")
        await self.client.connect()

        if not await self.client.is_user_authorized():
            logging.info("First-time login. Please enter the code you receive on Telegram.")
            await self.client.send_code_request(self.phone)
            try:
                await self.client.sign_in(self.phone, input('Enter code: '))
            except Exception as e:
                logging.error(f"Failed to sign in: {e}")
                return

        try:
            # register the handler (and refresh periodically to pick up DB changes)
            await self._ensure_handler_registered()

            # background task: periodically refresh the handler if monitored groups change
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
            finally:
                refresher.cancel()

        except Exception as e:
            logging.error(f"Error setting up monitor: {e}")
        finally:
            await self.stop()

    async def stop(self):
        """Stops the Telegram client."""
        if self.client.is_connected():
            logging.info("Stopping Telegram monitor...")
            await self.client.disconnect()

    async def _ensure_handler_registered(self):
        """Ensure the NewMessage handler is registered for the current monitored groups configured in DB.
        Re-registers the handler when the list of monitored groups changes.
        """
        # Fetch config from DB if available, otherwise use initial config
        groups_val = self.db.get_config('monitored_groups') or ''
        groups = [s for s in groups_val.split(',') if s] or list(self.initial_group_usernames or [])

        # Normalize and clean
        cleaned = []
        for g in groups:
            try:
                cleaned.append(int(g))
            except Exception:
                cleaned.append(g)

        # If already registered and groups unchanged, do nothing
        if self._handler_registered and getattr(self, '_last_groups', None) == cleaned:
            return

        # Unregister previous handlers if any
        try:
            if self._handler_registered:
                # Telethon does not provide a simple API to remove specific handlers by closure,
                # but we can clear all handlers and re-register. This is acceptable for this
                # small monitor which only registers one handler.
                self.client.remove_event_handler(None, events.NewMessage)
        except Exception:
            pass

        # Resolve entities
        entities = []
        for g in cleaned:
            try:
                ent = await self.client.get_entity(g)
                entities.append(ent)
                logging.info(f"Monitoring group: {g}")
            except Exception as e:
                logging.error(f"Failed to get entity for {g}: {e}")

        if not entities:
            logging.error("No group entities resolved to monitor.")
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

if __name__ == "__main__":
    # This is for testing the monitor independently
    db = Database("jobs.db")
    monitor = TelegramMonitor(
        TELEGRAM_API_ID,
        TELEGRAM_API_HASH,
        TELEGRAM_PHONE,
        TELEGRAM_GROUP_USERNAME,
        db,
    )
    asyncio.run(monitor.start())