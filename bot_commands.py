#!/usr/bin/env python3
"""
Bot Commands Only
This module handles only bot commands and notifications
Message monitoring is handled by telegram_api_monitor.py
"""

import asyncio
import logging
from telethon import TelegramClient, events
from config import (
    TELEGRAM_API_ID,
    TELEGRAM_API_HASH,
    TELEGRAM_PHONE,
    TELEGRAM_BOT_TOKEN,
    ADMIN_USER_ID,
    AUTHORIZED_USER_IDS,
)
from database import Database
from config import TELEGRAM_GROUP_USERNAMES, DATABASE_URL
import aiohttp
from telethon.sessions import StringSession

# Setup logging
logging.basicConfig(
    level=logging.INFO, 
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("bot_commands.log"),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)

class BotCommandsHandler:
    def __init__(self, api_id: str, api_hash: str, phone: str, bot_token: str, db: Database):
        self.api_id = int(api_id)
        self.api_hash = api_hash
        self.phone = phone
        self.bot_token = bot_token
        self.db = db
        self.client = None
        self.authorized_users = [int(x) for x in AUTHORIZED_USER_IDS if x] if AUTHORIZED_USER_IDS else []
        if ADMIN_USER_ID and int(ADMIN_USER_ID) not in self.authorized_users:
            self.authorized_users.append(int(ADMIN_USER_ID))

    async def _command_handler(self, event):
        """Handle incoming commands from authorized users."""
        if event.sender_id not in self.authorized_users:
            return

        command_parts = event.message.text.strip().split()
        command = command_parts[0].lower()
        logger.info(f"🤖 Bot received command: '{command}' from user {event.sender_id}")

        # All commands are queued for processing by the web server
        supported_commands = [
            '/status', '/start', '/stop', '/process', '/generate_emails', 
            '/export', '/sync_sheets', '/stats', '/monitoring', '/alerts'
        ]

        if command == '/status':
            try:
                await self._handle_status_command(event)
            except Exception as e:
                logger.error(f"Error processing /status command: {e}")
                await event.respond("❌ Sorry, there was an error retrieving the status.")
        
        elif command == '/stats':
            try:
                await self._handle_stats_command(event, command_parts)
            except Exception as e:
                logger.error(f"Error processing /stats command: {e}")
                await event.respond("❌ Sorry, there was an error retrieving statistics.")

        elif command == '/monitoring':
            try:
                await self._handle_monitoring_command(event)
            except Exception as e:
                logger.error(f"Error processing /monitoring command: {e}")
                await event.respond("❌ Sorry, there was an error checking monitoring status.")

        elif command in supported_commands:
            try:
                await self._queue_command(event, command_parts)
            except Exception as e:
                logger.error(f"Error enqueuing command {command_parts[0]}: {e}")
                await event.respond(f"❌ Sorry, there was an error queuing your command.")

        else:
            await event.respond(f"❓ Command `{command}` is not recognized.", parse_mode='markdown')

    async def _handle_status_command(self, event):
        """Enhanced status command with monitoring service info"""
        try:
            # Get monitoring service status
            monitoring_status = self.db.get_config('monitoring_status') or 'stopped'
            service_status = self.db.get_config('monitoring_service_status') or 'not_started'
            service_started = self.db.get_config('monitoring_service_started')
            
            # Get database stats
            unprocessed_count = self.db.get_unprocessed_count()
            jobs_today = self.db.get_jobs_today_stats()
            
            # Determine status
            service_emoji = "✅" if service_status == 'running' else "❌" if service_status == 'failed' else "⏳"
            processing_emoji = "🟢" if monitoring_status == 'running' else "🔴"
            
            message = (
                f"📊 **Job Scraper System Status**\n\n"
                f"🤖 **Bot Status:** `Connected` ✅\n"
                f"📡 **Telegram API Monitor:** `{service_status}` {service_emoji}\n"
                f"⚙️ **Automatic Processing:** `{monitoring_status}` {processing_emoji}\n"
                f"📨 **Unprocessed Messages:** `{unprocessed_count}`\n"
                f"✅ **Processed Jobs (Today):** `{jobs_today.get('total', 0)}`\n"
                f"   📧 **With Email:** `{jobs_today.get('with_email', 0)}`\n"
                f"   🔗 **Without Email:** `{jobs_today.get('without_email', 0)}`\n"
            )
            
            if service_started:
                message += f"🕐 **Service Started:** `{service_started[:19]}`\n"
            
            message += f"\n💡 **Architecture:** Telegram API monitors messages, Bot handles commands only"
            await event.respond(message, parse_mode='markdown')
            
        except Exception as e:
            logger.error(f"Error in status command: {e}")
            await event.respond("❌ Error retrieving system status")

    async def _handle_stats_command(self, event, command_parts):
        """Enhanced stats command"""
        try:
            days = 7
            if len(command_parts) > 1 and command_parts[1].isdigit():
                days = int(command_parts[1])
            
            stats = self.db.get_stats(days)
            message = f"📈 **Statistics for the last {days} days**\n\n"
            
            if stats.get("by_method"):
                message += "**💼 Jobs by Application Method:**\n"
                for method, count in stats["by_method"].items():
                    message += f"  • {method.capitalize()}: {count}\n"
            
            if stats.get("top_companies"):
                message += "\n**🏢 Top 5 Companies:**\n"
                for company, count in stats["top_companies"].items():
                    message += f"  • {company}: {count} jobs\n"
            
            await event.respond(message, parse_mode='markdown')
            
        except Exception as e:
            logger.error(f"Error in stats command: {e}")
            await event.respond("❌ Error retrieving statistics")

    async def _handle_monitoring_command(self, event):
        """Check monitoring service status"""
        try:
            service_status = self.db.get_config('monitoring_service_status') or 'not_started'
            service_started = self.db.get_config('monitoring_service_started')
            
            status_emoji = "✅" if service_status == 'running' else "❌" if service_status == 'failed' else "⏳"
            status_text = service_status.replace('_', ' ').title()
            
            message = (
                f"📡 **Telegram API Monitoring Service**\n\n"
                f"**Status:** `{status_text}` {status_emoji}\n"
            )
            
            if service_started:
                message += f"**Started:** {service_started[:19]}\n"
            
            message += f"\n💡 This service monitors Premium Referrals groups for job messages"
            
            if service_status == 'not_started':
                message += f"\n🚀 **To start:** Use `/start` command or web dashboard"
            elif service_status == 'running':
                message += f"\n✅ **Working:** Message monitoring is active"
            elif service_status == 'stopped':
                message += f"\n⏸️ **Stopped:** Use `/start` to resume monitoring"
            elif service_status == 'error':
                message += f"\n❌ **Error:** Check monitoring_service.log for details"
            
            await event.respond(message, parse_mode='markdown')
            
        except Exception as e:
            logger.error(f"Error in monitoring command: {e}")
            await event.respond("❌ Error checking monitoring service status")

    async def _queue_command(self, event, command_parts):
        """Queue command for processing by web server"""
        try:
            command_text = event.message.text.strip()
            command_id = self.db.enqueue_command(command_text)
            
            if command_id:
                await event.respond(
                    f"✅ **Command queued successfully!**\n\n"
                    f"📝 **Command:** `{command_text}`\n"
                    f"🆔 **ID:** `{command_id}`\n"
                    f"⏳ **Status:** `Queued for execution`\n\n"
                    f"💡 The command will be processed by the web server.",
                    parse_mode='markdown'
                )
                logger.info(f"📋 Queued command: {command_text} (ID: {command_id})")
            else:
                await event.respond("❌ Failed to queue command. Please try again.")
                
        except Exception as e:
            logger.error(f"Error queuing command: {e}")
            await event.respond("❌ Error queuing command. Check logs for details.")

    async def start_bot_commands(self):
        """Start bot command handling (without message monitoring)"""
        logger.info("🤖 Starting Bot Commands Handler...")
        
        try:
            # Connect using stored session
            session_string = self.db.get_telegram_session()
            if not session_string:
                logger.error("❌ No Telegram session found in database")
                return False
            
            self.client = TelegramClient(StringSession(session_string), self.api_id, self.api_hash)
            await self.client.connect()
            
            if not await self.client.is_user_authorized():
                logger.error("❌ Telegram session is invalid or expired")
                return False
            
            # Update login status
            self.db.set_telegram_login_status('connected')
            logger.info("✅ Bot connected to Telegram for command handling")
            
            # Register command handler only (NO message monitoring)
            if self.authorized_users:
                @self.client.on(events.NewMessage(from_users=self.authorized_users, pattern=r'^/\w+'))
                async def command_dispatch(event):
                    await self._command_handler(event)
                
                logger.info(f"🤖 Bot command handler registered for {len(self.authorized_users)} authorized users")
                logger.info("📡 Message monitoring handled separately by telegram_api_monitor.py")
            else:
                logger.warning("⚠️ No authorized users configured for bot commands")
                return False
            
            # Start bot client
            await self.client.run_until_disconnected()
            return True
            
        except Exception as e:
            logger.error(f"❌ Error in bot commands: {e}")
            self.db.set_telegram_login_status('connection_failed')
            return False
        finally:
            if self.client:
                await self.client.disconnect()
                self.client = None

    async def send_notification(self, message: str):
        """Send notification to admin user using Bot API"""
        if not (self.bot_token and ADMIN_USER_ID):
            logger.warning("Bot token or admin user ID not configured")
            return False
        
        try:
            url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
            payload = {
                "chat_id": int(ADMIN_USER_ID),
                "text": message,
                "parse_mode": "markdown"
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload) as response:
                    if response.status == 200:
                        logger.info(f"✅ Notification sent: {message[:50]}...")
                        return True
                    else:
                        error_text = await response.text()
                        logger.error(f"❌ Failed to send notification: {error_text}")
                        return False
                        
        except Exception as e:
            logger.error(f"❌ Error sending notification: {e}")
            return False

# Main function to run bot commands only
async def start_bot_commands_only():
    """Start the bot for commands only (no message monitoring)"""
    try:
        logger.info("🤖 Starting Bot Commands Only...")
        
        # Initialize database
        db = Database(DATABASE_URL)
        
        # Create and start bot commands handler
        bot_handler = BotCommandsHandler(
            TELEGRAM_API_ID,
            TELEGRAM_API_HASH,
            TELEGRAM_PHONE,
            TELEGRAM_BOT_TOKEN,
            db
        )
        
        # Start bot (commands only)
        success = await bot_handler.start_bot_commands()
        
        if not success:
            logger.error("❌ Bot commands failed to start")
            return False
        
        return True
        
    except Exception as e:
        logger.error(f"❌ Error in bot commands: {e}")
        return False

if __name__ == "__main__":
    asyncio.run(start_bot_commands_only())