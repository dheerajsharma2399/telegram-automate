import asyncio
import logging
from telethon import TelegramClient, events
from config import (
    TELEGRAM_API_ID,
    TELEGRAM_API_HASH,
    TELEGRAM_PHONE,
    TELEGRAM_GROUP_USERNAME,
    ADMIN_USER_ID,
    TELEGRAM_BOT_TOKEN,
    AUTHORIZED_USER_IDS,
)
from database import Database
from config import TELEGRAM_GROUP_USERNAMES, DATABASE_URL
from message_utils import extract_message_text, should_process_message, get_message_info
import aiohttp
from datetime import datetime, timedelta

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
    def __init__(self, api_id: str, api_hash: str, phone: str, group_usernames, db: Database, historical_fetcher=None):
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
        self.historical_fetcher = historical_fetcher
        self.client = None # Initialize client as None
        self._handler_registered = False
        self._current_monitored_group_ids = set()
        self.initial_group_usernames = group_usernames
        self.authorized_users = [int(x) for x in AUTHORIZED_USER_IDS if x] if AUTHORIZED_USER_IDS else []
        if ADMIN_USER_ID and int(ADMIN_USER_ID) not in self.authorized_users:
            self.authorized_users.append(int(ADMIN_USER_ID))

    async def _command_handler(self, event):
        """Handle incoming commands from authorized users."""
        sender = await event.get_sender()
        if not sender:
            logging.warning("Could not get sender for a command event.")
            return

        sender_id = sender.id
        if sender_id not in self.authorized_users:
            return

        command_parts = event.message.text.strip().split()
        command = command_parts[0].lower()
        logging.info(f"Received command: '{command}' from user {event.sender_id}")

        supported_commands = ['/status', '/start', '/stop', '/process', '/generate_emails', '/export', '/sync_sheets', '/stats']

        if command == '/status':
            try:
                processing_status = self.db.get_config('monitoring_status') or 'stopped'
                unprocessed_count = self.db.get_unprocessed_count()
                jobs_today = self.db.get_jobs_today_stats()
                
                status_emoji = "[RUNNING]" if processing_status == 'running' else "[STOPPED]"
                status_text = "Running" if processing_status == 'running' else "Stopped"
                
                message = (
                    f"[STATUS] **Job Scraper Status**\n\n"
                    f"[MONITOR] **Message Monitoring:** `Running`\n"
                    f"[PROCESSING] **Automatic Processing:** `{status_text}` {status_emoji}\n"
                    f"[QUEUE] **Unprocessed Messages:** `{unprocessed_count}`\n"
                    f"[OK] **Processed Jobs (Today):** `{jobs_today.get('total', 0)}`\n"
                    f"    - With Email: `{jobs_today.get('with_email', 0)}`\n"
                    f"    - Without Email: `{jobs_today.get('without_email', 0)}`"
                )
                await event.respond(message, parse_mode='markdown')
            except Exception as e:
                logging.error(f"Error processing /status command: {e}")
                await event.respond("Sorry, there was an error retrieving the status.")
        
        elif command == '/stats':
            try:
                days = 7
                if len(command_parts) > 1 and command_parts[1].isdigit():
                    days = int(command_parts[1])
                
                stats = self.db.get_stats(days)
                message = f"[STATUS] **Statistics for the last {days} days**\n\n"
                
                if stats.get("by_method"):
                    message += "**Jobs by Application Method:**\n"
                    for method, count in stats["by_method"].items():
                        message += f"  - {method.capitalize()}: {count}\n"
                
                if stats.get("top_companies"):
                    message += "\n**Top 5 Companies:**\n"
                    for company, count in stats["top_companies"].items():
                        message += f"  - {company}: {count} jobs\n"
                
                await event.respond(message, parse_mode='markdown')
            except Exception as e:
                logging.error(f"Error processing /stats command: {e}")
                await event.respond("Sorry, there was an error retrieving statistics.")

        elif command in supported_commands:
            try:
                command_text = event.message.text.strip()
                self.db.enqueue_command(command_text)
                await event.respond(f"Command `{command_text}` has been queued for execution.", parse_mode='markdown')
            except Exception as e:
                logging.error(f"Error enqueuing command {command_text}: {e}")
                await event.respond(f"Sorry, there was an error queuing your command.")

        else:
            await event.respond(f"Command `{command}` is not recognized.", parse_mode='markdown')

    async def start(self):
        logging.info("Starting Telegram monitor loop...")
        
        while True:
            try:
                session_string = self.db.get_telegram_session()
                
                if session_string and session_string.strip():
                    logging.info("Restoring Telegram session from database...")
                    if not self.client or not self.client.is_connected():
                        try:
                            # The client.is_user_authorized() check below is sufficient to validate the session.
                            # No need for a heuristic check here.
                                
                            self.client = TelegramClient(StringSession(session_string), self.api_id, self.api_hash)
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
                            await self.send_admin_notification("[OK] Bot connected to Telegram.")
                            
                            await self._prime_dialog_cache()

                        except Exception as e:
                            error_msg = str(e).lower()
                            if "not a valid string" in error_msg or "invalid" in error_msg:
                                logging.warning(f"Stored session string is invalid: {e}. Clearing from database.")
                                self.db.set_telegram_session('')
                                self.db.set_telegram_login_status('session_expired')
                            else:
                                logging.error(f"Failed to connect with stored session: {e}")
                                self.db.set_telegram_login_status('connection_failed')
                            self.client = None
                            await asyncio.sleep(30)
                            continue

                    logging.info("Client connected and authorized. Setting up message handlers.")
                    try:
                        await self._ensure_handler_registered()
                        await self.client.run_until_disconnected()
                        logging.info("Client disconnected. Will attempt to reconnect.")
                        self.db.set_telegram_login_status('disconnected')
                        await self.send_admin_notification("[ERROR] Bot disconnected from Telegram.")
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

    async def send_admin_notification(self, message):
        if TELEGRAM_BOT_TOKEN and ADMIN_USER_ID:
            url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
            payload = {
                "chat_id": ADMIN_USER_ID,
                "text": message,
            }
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.post(url, json=payload) as response:
                        if response.status != 200:
                            logging.error(f"Failed to send admin notification: {await response.text()}")
            except Exception as e:
                logging.error(f"Failed to send admin notification: {e}")

    async def stop(self):
        """Stops the Telegram client."""
        if self.client and self.client.is_connected():
            logging.info("Stopping Telegram monitor...")
            await self.client.disconnect()

    async def _process_and_store_message(self, message, group_id):
        """Process and store a single message."""
        try:
            # Check if message should be processed
            if not should_process_message(message):
                return

            msg_info = get_message_info(message)

            # Ignore commands from authorized users in job groups
            if message.sender_id in self.authorized_users and msg_info['is_bot_command']:
                logging.info(f"Ignoring command '{msg_info['text']}' in job group.")
                return

            # Add to database
            new_id = self.db.add_raw_message(
                message_id=message.id,
                message_text=msg_info['text'],
                sender_id=message.sender_id,
                sent_at=message.date,
                group_id=group_id
            )

            if new_id:
                logging.info(f"Stored new message {message.id} from group {group_id}")
            else:
                logging.debug(f"Message {message.id} from group {group_id} already exists.")

        except Exception as e:
            logging.error(f"Failed to process/store message {message.id}: {e}")

    async def _prime_dialog_cache(self):
        """
        Fetches all dialogs to prime the client's entity cache.
        This helps prevent 'Cannot find any entity' errors for groups the client is in.
        """
        if not self.client or not self.client.is_connected():
            return
        try:
            logging.info("Priming entity cache by fetching dialogs...")
            await self.client.get_dialogs(limit=10) # Fetch a few dialogs to get started
            logging.info("Entity cache primed.")
        except Exception as e:
            logging.warning(f"Could not prime entity cache: {e}")


    async def _ensure_handler_registered(self):
        """Ensure the NewMessage handler is registered for the current monitored groups configured in DB."""
        if not self.client or self._handler_registered:
            return

        groups_val = self.db.get_config('monitored_groups') or ''
        groups_config_list = [s.strip() for s in groups_val.split(',') if s.strip()]

        group_entities = []
        for g_str in groups_config_list:
            try:
                entity = await self.client.get_input_entity(g_str)
                group_entities.append(entity)
                logging.info(f"Resolved entity for monitoring: {g_str} (ID: {entity.id})")
            except Exception as e:
                logging.error(f"Failed to get entity for {g_str}. Please ensure the bot has access to this group/channel and the ID/username is correct: {e}")
        
        new_group_ids = {entity.id for entity in group_entities}

        if new_group_ids == self._current_monitored_group_ids and self._handler_registered:
            logging.info("Monitored groups unchanged and handlers already registered.")
            return

        # Remove existing handlers to prevent duplicates if called multiple times
        if self._handler_registered:
            if hasattr(self, 'job_message_handler'):
                self.client.remove_event_handler(self.job_message_handler)
            if hasattr(self, 'command_dispatch_handler'):
                self.client.remove_event_handler(self.command_dispatch_handler)
            self._handler_registered = False

        if group_entities:
            @self.client.on(events.NewMessage(chats=group_entities))
            async def job_message_handler(event):
                group_id = event.chat_id
                await self._process_and_store_message(event.message, group_id)
            self.client.add_event_handler(job_message_handler)
            self.job_message_handler = job_message_handler # Store handler for removal
            logging.info(f"NewMessage handler registered for {len(group_entities)} groups.")
        else:
            logging.warning("No group entities resolved to monitor for jobs. NewMessage handler not registered.")

        if self.authorized_users:
            @self.client.on(events.NewMessage(from_users=self.authorized_users, pattern=r'^/\w+'))
            async def command_dispatch_handler(event):
                await self._command_handler(event)
            self.client.add_event_handler(command_dispatch_handler)
            self.command_dispatch_handler = command_dispatch_handler # Store handler for removal
            logging.info(f"Command handler registered for {len(self.authorized_users)} authorized users.")
        else:
            logging.warning("No authorized users configured for commands. Command handler not registered.")

        self._handler_registered = True
        self._current_monitored_group_ids = new_group_ids
        logging.info("Event handlers registered.")
    
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