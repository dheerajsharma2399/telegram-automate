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
from message_utils import extract_message_text, get_message_info, send_rate_limited_telegram_notification
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
        
        # Message queue for reliability
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

    def _should_capture_message(self, message) -> tuple[bool, str]:
        """
        Determine if message should be captured (VERY PERMISSIVE)
        Returns: (should_capture, reason)
        """
        # Always skip service messages
        if getattr(message, 'service', None):
            return False, "service_message"
        
        # Get text from message
        message_text = extract_message_text(message)
        
        # Skip only if NO text AND NO media
        if not message_text and not hasattr(message, 'media'):
            return False, "empty_no_media"
        
        # Skip bot commands ONLY from authorized users
        if message_text.startswith('/') and message.sender_id in self.authorized_users:
            return False, "authorized_user_command"
        
        # CAPTURE EVERYTHING ELSE
        return True, "ok"

    async def _queue_message(self, message, group_id):
        """Add message to processing queue"""
        try:
            await self.message_queue.put((message, group_id))
            self.stats['total_received'] += 1
        except asyncio.QueueFull:
            logging.warning(f"⚠️ Message queue full! Message {message.id} from group {group_id} dropped")
            self.stats['total_errors'] += 1

    async def _message_worker(self):
        """Background worker to process queued messages with retry logic"""
        logging.info("✅ Message worker started")
        
        while True:
            try:
                message, group_id = await self.message_queue.get()
                
                # Process with retry
                max_retries = 3
                success = False
                
                for attempt in range(max_retries):
                    try:
                        # Check if should capture
                        should_capture, reason = self._should_capture_message(message)
                        
                        if not should_capture:
                            logging.debug(f"⏭️  Skipping message {message.id}: {reason}")
                            self.stats['total_skipped'] += 1
                            success = True
                            break
                        
                        # Extract text
                        message_text = extract_message_text(message)
                        
                        # Save to database
                        # CRITICAL FIX: Run synchronous DB call in a separate thread to avoid blocking asyncio loop
                        new_id = await asyncio.to_thread(
                            self.db.messages.add_raw_message,
                            message_id=message.id,
                            message_text=message_text or '',
                            sender_id=message.sender_id if message.sender_id else None,
                            sent_at=message.date,
                            group_id=group_id
                        )
                        
                        if new_id:
                            logging.info(f"✅ Saved message {message.id} from group {group_id} (ID: {new_id})")
                            self.stats['total_saved'] += 1
                            self.stats['last_message_time'] = datetime.now(IST)
                        else:
                            logging.debug(f"ℹ️  Message {message.id} already exists (duplicate)")
                            self.stats['total_saved'] += 1  # Still count as success
                        
                        success = True
                        break
                        
                    except Exception as e:
                        logging.error(f"❌ Attempt {attempt + 1} failed for message {message.id}: {e}")
                        if attempt < max_retries - 1:
                            await asyncio.sleep(1)
                        else:
                            logging.critical(f"🚨 LOST MESSAGE {message.id} from group {group_id} after {max_retries} attempts")
                            self.stats['total_errors'] += 1
                
                self.message_queue.task_done()
                
                # Log stats every 100 messages
                if self.stats['total_received'] % 100 == 0:
                    await self._log_stats()
                
            except Exception as e:
                logging.error(f"Worker error: {e}")
                await asyncio.sleep(1)

    async def _log_stats(self):
        """Log current statistics"""
        last_time = self.stats['last_message_time']
        time_str = last_time.strftime('%Y-%m-%d %H:%M:%S IST') if last_time else 'Never'
        
        logging.info(f"📊 Monitor Stats:")
        logging.info(f"   Received: {self.stats['total_received']}")
        logging.info(f"   Saved: {self.stats['total_saved']}")
        logging.info(f"   Skipped: {self.stats['total_skipped']}")
        logging.info(f"   Errors: {self.stats['total_errors']}")
        logging.info(f"   Last message: {time_str}")
        logging.info(f"   Queue size: {self.message_queue.qsize()}")

    async def _command_handler(self, event):
        """Handle incoming commands from authorized users"""
        if not event.sender_id:
            logging.warning(f"Could not determine sender_id for command event")
            return

        if event.sender_id not in self.authorized_users:
            return
        
        command_text = event.message.text.strip()
        logging.info(f"Received command: '{command_text}' from user {event.sender_id}")
        
        # Queue command for execution
        self.db.commands.enqueue_command(command_text)
        # await event.respond(f"Command `{command_text}` queued for execution.", parse_mode='markdown')

    async def start(self):
        logging.info("🚀 Starting Telegram monitor loop...")
        
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
                            
                            # Start message worker BEFORE connecting
                            if not self.worker_task or self.worker_task.done():
                                self.worker_task = asyncio.create_task(self._message_worker())
                                logging.info("✅ Message worker started")
                            
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
                            
                            # Prime dialog cache
                            await self._prime_dialog_cache()
                            
                            # Register handlers AFTER connection
                            await self._ensure_handler_registered()
                            
                            # Start periodic handler updates
                            if self._update_handlers_task is None or self._update_handlers_task.done():
                                self._update_handlers_task = asyncio.create_task(
                                    self._periodically_update_handlers()
                                )
                            
                            # Run until disconnected
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

    async def _periodically_update_handlers(self):
        """Periodically check for group changes"""
        await asyncio.sleep(10)  # Initial delay
        
        while self.client and self.client.is_connected():
            try:
                await self._ensure_handler_registered(force_check=True)
            except Exception as e:
                logging.error(f"Handler update error: {e}")
            await asyncio.sleep(60)

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

    async def _ensure_handler_registered(self, force_check: bool = False):
        """Register message handlers for monitored groups"""
        if not self.client:
            return
        
        if not force_check and self._handler_registered:
            return

        # Get groups from config
        groups_val = self.db.config.get_config('monitored_groups') or ''
        groups_config_list_str = [s.strip() for s in groups_val.split(',') if s.strip()]

        # Convert to proper types
        groups_config_list = []
        for g in groups_config_list_str:
            try:
                groups_config_list.append(int(g))
            except (ValueError, TypeError):
                groups_config_list.append(g)

        # Resolve entities
        unique_groups = sorted(list(set(groups_config_list)))
        group_entities = []
        
        for g_str in unique_groups:
            try:
                from telethon.utils import get_peer_id
                entity = await self.client.get_entity(g_str)
                group_entities.append(entity)
                logging.info(f"✅ Resolved entity: {g_str} (ID: {get_peer_id(entity)})")
            except Exception as e:
                logging.error(f"❌ Failed to resolve entity {g_str}: {e}")
                continue
        
        new_group_ids = {get_peer_id(entity) for entity in group_entities}

        if new_group_ids == self._current_monitored_group_ids and self._handler_registered:
            logging.debug("Monitored groups unchanged")
            return

        # Remove existing handlers
        if self._handler_registered:
            if hasattr(self, 'job_message_handler'):
                self.client.remove_event_handler(self.job_message_handler)
            if hasattr(self, 'command_dispatch_handler'):
                self.client.remove_event_handler(self.command_dispatch_handler)
            self._handler_registered = False

        # Register job message handler (captures EVERYTHING)
        if group_entities:
            @self.client.on(events.NewMessage(chats=group_entities))
            async def job_message_handler(event):
                if not isinstance(event, events.NewMessage.Event):
                    return
                
                if not event.chat_id or not event.message:
                    return
                
                # Just queue it - worker will process
                await self._queue_message(event.message, event.chat_id)
            
            self.client.add_event_handler(job_message_handler)
            self.job_message_handler = job_message_handler
            logging.info(f"✅ Job handler registered for {len(group_entities)} groups")
        else:
            logging.warning("⚠️ No group entities resolved")

        # Register command handler (authorized users only)
        if self.authorized_users:
            @self.client.on(events.NewMessage(from_users=self.authorized_users, pattern=r'^/\w+'))
            async def command_dispatch_handler(event):
                if not hasattr(event, 'message') or not hasattr(event, 'sender_id'):
                    return
                
                logging.info(f"Command from {event.sender_id}: {event.message.text}")
                await self._command_handler(event)
            
            self.client.add_event_handler(command_dispatch_handler)
            self.command_dispatch_handler = command_dispatch_handler
            logging.info(f"✅ Command handler registered for {len(self.authorized_users)} users")
        else:
            logging.warning("⚠️ No authorized users configured")

        self._handler_registered = True
        self._current_monitored_group_ids = new_group_ids
        logging.info("✅ Event handlers registered")
    
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