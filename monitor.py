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

logging.basicConfig(
    level=logging.INFO, 
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("monitor.log"),
        logging.StreamHandler()
    ]
)

class TelegramMonitor:
    def __init__(self, api_id: str, api_hash: str, phone: str, group_username: str, db: Database):
        self.api_id = int(api_id)
        self.api_hash = api_hash
        self.phone = phone
        self.group_username = group_username
        try:
            self.group_username = int(group_username)
        except (ValueError, TypeError):
            pass # It's a username string, so we leave it as is.
        self.db = db
        self.client = TelegramClient('telegram_monitor', self.api_id, self.api_hash)

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
            entity = await self.client.get_entity(self.group_username)
            logging.info(f"Monitoring group: {self.group_username}")

            @self.client.on(events.NewMessage(chats=entity))
            async def handler(event):
                logging.info(f"New message received: {event.message.id}")
                self.db.add_raw_message(
                    message_id=event.message.id,
                    message_text=event.message.text,
                    sender_id=event.message.sender_id,
                    sent_at=event.message.date,
                )

            await self.client.run_until_disconnected()

        except Exception as e:
            logging.error(f"Error setting up monitor: {e}")
        finally:
            await self.stop()

    async def stop(self):
        """Stops the Telegram client."""
        if self.client.is_connected():
            logging.info("Stopping Telegram monitor...")
            await self.client.disconnect()

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