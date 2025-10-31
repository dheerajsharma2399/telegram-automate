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
import aiohttp

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
        self.authorized_users = [int(x) for x in AUTHORIZED_USER_IDS if x] if AUTHORIZED_USER_IDS else []
        if ADMIN_USER_ID and int(ADMIN_USER_ID) not in self.authorized_users:
            self.authorized_users.append(int(ADMIN_USER_ID))

    async def _command_handler(self, event):
        """Handle incoming commands from authorized users."""
        if event.sender_id not in self.authorized_users:
            return

        command_text = event.message.text.strip()
        command = command_text.split()[0].lower()
        logging.info(f"Received command: '{command}' from user {event.sender_id}")

        supported_commands = ['/status', '/start', '/stop', '/process', '/generate_emails', '/export', '/sync_sheets']

        if command == '/status':
            try:
                processing_status = self.db.get_config('monitoring_status') or 'stopped'
                unprocessed_count = self.db.get_unprocessed_count()
                jobs_today = self.db.get_jobs_today_stats()
                
                status_emoji = "🟢" if processing_status == 'running' else "🔴"
                status_text = "Running" if processing_status == 'running' else "Stopped"
                
                message = (
                    f"📊 **Job Scraper Status**\n\n"
                    f"⚪️ **Message Monitoring:** `Running`\n"
                    f"⚙️ **Automatic Processing:** `{status_text}` {status_emoji}\n"
                    f"📨 **Unprocessed Messages:** `{unprocessed_count}`\n"
                    f"✅ **Processed Jobs (Today):** `{jobs_today.get('total', 0)}`\n"
                    f"    - With Email: `{jobs_today.get('with_email', 0)}`\n"
                    f"    - Without Email: `{jobs_today.get('without_email', 0)}`"
                )
                await event.respond(message, parse_mode='markdown')
            except Exception as e:
                logging.error(f"Error processing /status command: {e}")
                await event.respond("Sorry, there was an error retrieving the status.")
        
        elif command in supported_commands:
            try:
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
                            # Validate session string format before creating client
                            if not session_string.startswith('1@') and len(session_string) < 100:
                                logging.warning("Stored session string appears invalid format. Clearing from database.")
                                self.db.set_telegram_session('')
                                self.db.set_telegram_login_status('session_expired')
                                await asyncio.sleep(30)
                                continue
                                
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
                            await self.send_admin_notification("✅ Bot connected to Telegram.")
                            
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
                            self.db.set_telegram_login_status('disconnected')
                            await self.send_admin_notification("❌ Bot disconnected from Telegram.")
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

        if self._handler_registered:
            return

        # Handler 1: For scraping new job messages from groups
        group_entities = []
        groups_val = self.db.get_config('monitored_groups') or ''
        groups = [s for s in groups_val.split(',') if s] or list(self.initial_group_usernames or [])
        for g in groups:
            try:
                cleaned_g = int(g)
            except (ValueError, TypeError):
                cleaned_g = g
            try:
                ent = await self.client.get_entity(cleaned_g)
                group_entities.append(ent)
                logging.info(f"Monitoring group for jobs: {g}")
            except Exception as e:
                logging.error(f"Failed to get entity for {g}: {e}")

        if group_entities:
            @self.client.on(events.NewMessage(chats=group_entities))
            async def job_message_handler(event):
                try:
                    logging.info(f"New job message received: {event.message.id}")
                    self.db.add_raw_message(
                        message_id=event.message.id,
                        message_text=event.message.text,
                        sender_id=event.message.sender_id,
                        sent_at=event.message.date,
                    )
                except Exception as e:
                    logging.error(f"Failed to add raw message: {e}")
        else:
            logging.warning("No group entities resolved to monitor for jobs.")

        # Handler 2: For commands from authorized users
        if self.authorized_users:
            @self.client.on(events.NewMessage(from_users=self.authorized_users, pattern=r'^/\w+'))
            async def command_dispatch(event):
                await self._command_handler(event)
            logging.info(f"Command handler registered for {len(self.authorized_users)} authorized users.")
        else:
            logging.warning("No authorized users configured for commands.")

        self._handler_registered = True
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