import asyncio
import logging
import csv
import os
import requests
import sys
import tempfile
from datetime import datetime
import aiohttp
from telegram import Update
from telegram.ext import (
    Application, CommandHandler, ContextTypes, MessageHandler, CallbackQueryHandler, filters
)
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from config import *
from database import Database
from llm_processor import LLMProcessor
from sheets_sync import GoogleSheetsSync
from monitor import TelegramMonitor

# Setup logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    handlers=[
        logging.FileHandler("bot.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Bot instance locking mechanism
def check_bot_instance():
    """Check if another bot instance is already running"""
    lock_file = os.path.join(tempfile.gettempdir(), 'telegram_bot.lock')
    
    try:
        if os.path.exists(lock_file):
            with open(lock_file, 'r') as f:
                old_pid = f.read().strip()
            logger.warning(f"Bot lock file exists. Old PID: {old_pid}")
            # Try to verify if the old process is still running
            try:
                # On Unix systems, we can check if the process exists
                if os.name == 'posix':
                    os.kill(int(old_pid), 0)  # Signal 0 just checks if process exists
                    logger.error("Old bot instance still running. Aborting.")
                    return False
                else:
                    # On Windows, we can't easily check, so remove stale lock
                    logger.warning("Removing stale lock file on Windows")
                    os.remove(lock_file)
            except (OSError, ProcessLookupError, ValueError):
                # Process doesn't exist, safe to remove lock
                os.remove(lock_file)
                logger.info("Removed stale lock file")
        
        # Create new lock file
        with open(lock_file, 'w') as f:
            f.write(str(os.getpid()))
        logger.info(f"Created bot lock file with PID: {os.getpid()}")
        return True
        
    except Exception as e:
        logger.error(f"Could not manage bot lock file: {e}")
        return False

def cleanup_bot_instance():
    """Clean up bot instance lock"""
    lock_file = os.path.join(tempfile.gettempdir(), 'telegram_bot.lock')
    try:
        if os.path.exists(lock_file):
            os.remove(lock_file)
            logger.info("Cleaned up bot lock file")
    except Exception as e:
        logger.error(f"Could not remove lock file: {e}")

# Initialize components
db = Database(DATABASE_URL)
llm_processor = LLMProcessor(OPENROUTER_API_KEY, OPENROUTER_MODEL, OPENROUTER_FALLBACK_MODEL)
sheets_sync = None

def get_sheets_sync():
    global sheets_sync
    if sheets_sync is None and GOOGLE_CREDENTIALS_JSON and SPREADSHEET_ID:
        sheets_sync = GoogleSheetsSync(GOOGLE_CREDENTIALS_JSON, SPREADSHEET_ID)
    return sheets_sync

scheduler = AsyncIOScheduler()

# New background job to import any missed jobs to dashboard
async def auto_import_jobs_to_dashboard():
    """Background service to automatically import non-email jobs to dashboard"""
    try:
        logger.info("Running background job import...")
        
        # Import any non-email jobs that aren't in dashboard yet
        imported_count = db.import_jobs_from_processed('non-email', max_jobs=50)
        
        if imported_count > 0:
            logger.info(f"Background import completed: {imported_count} jobs imported to dashboard")
        else:
            logger.info("Background import: No new jobs to import")
            
    except Exception as e:
        logger.error(f"Background import job failed: {e}")

# Authorization check
def is_authorized(user_id: int) -> bool:
    """Check if user is authorized to use the bot"""
    if not AUTHORIZED_USER_IDS:
        return True  # If no IDs specified, allow all
    return user_id in AUTHORIZED_USER_IDS

async def process_jobs(context: ContextTypes.DEFAULT_TYPE):
    """The core job processing function."""
    logger.info("Starting job processing...")
    unprocessed_messages = db.get_unprocessed_messages(limit=BATCH_SIZE)
    if not unprocessed_messages:
        logger.info("No unprocessed messages to process.")
        return

    for message in unprocessed_messages:
        try:
            db.update_message_status(message["id"], "processing")
            parsed_jobs = await llm_processor.parse_jobs(message["message_text"])
            
            if not parsed_jobs:
                db.update_message_status(message["id"], "processed", "No jobs found")
                continue

            for job_data in parsed_jobs:
                processed_data = llm_processor.process_job_data(job_data, message["id"])
                
                # Add job to processed_jobs table
                try:
                    job_id = db.add_processed_job(processed_data)
                except AttributeError:
                    # Fallback for compatibility - check alternative method names
                    if hasattr(db, 'insert_processed_job'):
                        job_id = db.insert_processed_job(processed_data)
                    elif hasattr(db, 'save_processed_job'):
                        job_id = db.save_processed_job(processed_data)
                    else:
                        logger.error("No compatible database method found for processed jobs")
                        raise Exception("Database method not available")
                
                # AUTOMATIC DASHBOARD POPULATION: Add non-email jobs to dashboard
                if processed_data.get('application_method') != 'email':
                    try:
                        # Convert processed job to dashboard format (using only available columns)
                        dashboard_job_data = {
                            'source_job_id': processed_data.get('job_id'),
                            'original_sheet': 'non-email',
                            'company_name': processed_data.get('company_name'),
                            'job_role': processed_data.get('job_role'),
                            'location': processed_data.get('location'),
                            'application_link': processed_data.get('application_link'),
                            'phone': None,  # processed_jobs doesn't have phone column
                            'recruiter_name': None,  # processed_jobs doesn't have recruiter_name column
                            'job_relevance': 'relevant',  # Default to relevant
                            'original_created_at': processed_data.get('updated_at'),
                            'application_status': 'not_applied'
                        }
                        
                        # Add to dashboard if not already present
                        with db.get_connection() as conn:
                            cursor = conn.cursor()
                            cursor.execute(
                                "SELECT id FROM dashboard_jobs WHERE source_job_id = %s",
                                (processed_data.get('job_id'),)
                            )
                            if not cursor.fetchone():
                                db.add_dashboard_job(dashboard_job_data)
                                logger.info(f"Auto-imported non-email job to dashboard: {processed_data.get('company_name')} - {processed_data.get('job_role')}")
                    except Exception as e:
                        logger.error(f"Failed to auto-import job to dashboard: {e}")
            
            db.update_message_status(message["id"], "processed")
            logger.info(f"Processed message {message['id']} and found {len(parsed_jobs)} jobs.")

        except Exception as e:
            logger.error(f"Failed to process message {message['id']}: {e}")
            db.update_message_status(message["id"], "failed", str(e))

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command to begin the automatic job processing schedule."""
    if not is_authorized(update.effective_user.id):
        await update.message.reply_text("❌ Unauthorized access.")
        return
    
    if not scheduler.running:
        scheduler.add_job(process_jobs, IntervalTrigger(minutes=PROCESSING_INTERVAL_MINUTES), args=[context])
        # Add background import job that runs every 5 minutes
        scheduler.add_job(auto_import_jobs_to_dashboard, IntervalTrigger(minutes=5))
        scheduler.start()
        db.set_config('monitoring_status', 'running')
        await update.message.reply_text(
            "✅ Automatic job processing has been started.\n\nI will now check for jobs every 10 minutes and import them to dashboard every 5 minutes. Note: Message monitoring is always running in the background."
        )
    else:
        await update.message.reply_text("⚠️ Automatic job processing is already running!")

async def stop_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /stop command to halt the automatic job processing schedule."""
    if not is_authorized(update.effective_user.id):
        await update.message.reply_text("❌ Unauthorized access.")
        return
    
    if scheduler.running:
        scheduler.shutdown()
        db.set_config('monitoring_status', 'stopped')
        await update.message.reply_text(
            "🛑 Automatic job processing has been stopped.\n\nUse /start to resume."
        )
    else:
        await update.message.reply_text("⚠️ Automatic job processing is not running.")


async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /status command"""
    if not is_authorized(update.effective_user.id):
        await update.message.reply_text("❌ Unauthorized access.")
        return
    
    processing_status = db.get_config('monitoring_status')
    unprocessed_count = db.get_unprocessed_count()
    jobs_today = db.get_jobs_today_stats()
    
    status_emoji = "🟢" if processing_status == 'running' else "🔴"
    status_text = "Running" if processing_status == 'running' else "Stopped"
    
    message = (
        f"📊 *Job Scraper Status*\n\n"
        f"🟢 Monitoring: *Running*\n"
        f"{status_emoji} Job Processing: *{status_text}*\n"
        f"📨 Unprocessed Messages: *{unprocessed_count}*\n"
        f"✅ Processed Jobs (Today): *{jobs_today['total']}*\n"
        f"  - 📧 With Email: *{jobs_today['with_email']}*\n"
        f"  - 🔗 Without Email: *{jobs_today['without_email']}*\n"
    )
    await update.message.reply_text(message, parse_mode='Markdown')

async def process_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /process command"""
    if not is_authorized(update.effective_user.id):
        await update.message.reply_text("❌ Unauthorized access.")
        return
    
    await update.message.reply_text("⚙️ Manually starting job processing...")
    await process_jobs(context)
    await update.message.reply_text("✅ Manual processing complete.")

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /stats command"""
    if not is_authorized(update.effective_user.id):
        await update.message.reply_text("❌ Unauthorized access.")
        return

    days = 7
    if context.args:
        try:
            days = int(context.args[0])
        except (ValueError, IndexError):
            await update.message.reply_text("Usage: /stats [days]")
            return

    stats = db.get_stats(days)
    message = f"📊 *Statistics for the last {days} days*\n\n"
    message += "*Jobs by Application Method:*"
    for method, count in stats["by_method"].items():
        message += f"  - {method.capitalize()}: {count}\n"
    
    message += "\n*Top 5 Companies:*"
    for company, count in stats["top_companies"].items():
        message += f"  - {company}: {count} jobs\n"

    await update.message.reply_text(message, parse_mode='Markdown')

async def export_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /export command"""
    if not is_authorized(update.effective_user.id):
        await update.message.reply_text("❌ Unauthorized access.")
        return

    await update.message.reply_text("📦 Generating CSV exports...")
    
    try:
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")

        # Export jobs with email
        os.makedirs("data/email", exist_ok=True)
        email_jobs = db.get_processed_jobs_by_email_status(has_email=True)
        if email_jobs:
            email_file_path = os.path.join("data", "email", f"email_jobs_{timestamp}.csv")
            with open(email_file_path, "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=email_jobs[0].keys())
                writer.writeheader()
                writer.writerows(email_jobs)
            await update.message.reply_document(
                document=open(email_file_path, "rb"),
                caption="Jobs with email applications.",
                filename=os.path.basename(email_file_path)
            )
        else:
            await update.message.reply_text("No processed jobs with emails to export.")

        # Export jobs without email
        os.makedirs("data/non-email", exist_ok=True)
        non_email_jobs = db.get_processed_jobs_by_email_status(has_email=False)
        if non_email_jobs:
            non_email_file_path = os.path.join("data", "non-email", f"non_email_jobs_{timestamp}.csv")
            with open(non_email_file_path, "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=non_email_jobs[0].keys())
                writer.writeheader()
                writer.writerows(non_email_jobs)
            await update.message.reply_document(
                document=open(non_email_file_path, "rb"),
                caption="Jobs without email applications.",
                filename=os.path.basename(non_email_file_path)
            )
        else:
            await update.message.reply_text("No processed jobs without emails to export.")

    except Exception as e:
        logger.error(f"Failed to export CSV: {e}")
        await update.message.reply_text(f"❌ Failed to export CSV: {e}")

async def sync_sheets_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /sync_sheets command with enhanced logging and debugging"""
    if not is_authorized(update.effective_user.id):
        await update.message.reply_text("❌ Unauthorized access.")
        return

    sheets_sync = get_sheets_sync()
    if not (sheets_sync and sheets_sync.client):
        await update.message.reply_text("Google Sheets is not configured.")
        return

    await update.message.reply_text("🔄 Syncing database with Google Sheets...")
    
    try:
        unsynced_jobs = db.get_unsynced_jobs()
        if not unsynced_jobs:
            await update.message.reply_text("No jobs to sync. All jobs are already synced with Google Sheets.")
            return

        logger.info(f"Starting sync for {len(unsynced_jobs)} unsynced jobs")
        await update.message.reply_text(f"📊 Found {len(unsynced_jobs)} jobs to sync. Starting process...")

        synced_count = 0
        failed_count = 0
        
        for i, job in enumerate(unsynced_jobs, 1):
            job_id = job.get('job_id', f'job_{i}')
            company = job.get('company_name', 'Unknown Company')
            role = job.get('job_role', 'Unknown Role')
            
            try:
                logger.info(f"Syncing job {i}/{len(unsynced_jobs)}: {job_id}")
                await update.message.reply_text(f"🔄 Syncing job {i}/{len(unsynced_jobs)}: {company} - {role}")
                
                if sheets_sync.sync_job(job):
                    db.mark_job_synced(job_id)
                    synced_count += 1
                    logger.info(f"Successfully synced job {job_id}")
                else:
                    failed_count += 1
                    logger.warning(f"Failed to sync job {job_id}")
                    
            except Exception as e:
                failed_count += 1
                logger.error(f"Error syncing job {job_id}: {e}")
                await update.message.reply_text(f"❌ Failed to sync job {i}: {company} - {e}")
        
        # Final status message
        if synced_count > 0:
            await update.message.reply_text(
                f"✅ Sync completed!\n\n"
                f"📊 Results:\n"
                f"✅ Synced: {synced_count} jobs\n"
                f"{f'❌ Failed: {failed_count} jobs' if failed_count > 0 else '🎉 All jobs synced successfully'}"
            )
        else:
            await update.message.reply_text(f"❌ No jobs were synced successfully. Please check the logs for details.")

    except Exception as e:
        logger.error(f"Failed to sync with Google Sheets: {e}")
        await update.message.reply_text(f"❌ Failed to sync with Google Sheets: {e}")


# async def generate_emails_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
#     """Handle /generate_emails command - generate personalized email bodies for processed jobs."""
#     if not is_authorized(update.effective_user.id):
#         await update.message.reply_text("❌ Unauthorized access.")
#         return

#     # optional arg: comma separated job ids
#     target_ids = None
#     if context.args:
#         arg = context.args[0]
#         target_ids = [x.strip() for x in arg.split(',') if x.strip()]

#     await update.message.reply_text("🧠 Generating email bodies... this may take a moment.")

#     try:
#         # Fetch jobs to generate for: ONLY email sheet jobs without email body or specified
#         jobs = []
#         if target_ids:
#             # query the DB for these job_ids (only jobs with email for email sheet)
#             with db.get_connection() as conn:
#                 cur = conn.cursor()
#                 # Use %s for psycopg2 placeholders
#                 q = f"SELECT * FROM processed_jobs WHERE job_id IN ({','.join(['%s']*len(target_ids))}) AND email IS NOT NULL AND email != ''"
#                 cur.execute(q, target_ids)
#                 jobs = [dict(r) for r in cur.fetchall()]
#         else:
#             # Only get email sheet jobs that need email generation
#             jobs = db.get_email_jobs_needing_generation()

#         if not jobs:
#             await update.message.reply_text("No jobs found in the 'email' sheet that need email body generation.")
#             return

#         generated = 0
#         synced = 0
#         for job in jobs:
#             try:
#                 # use LLMProcessor.generate_email_body if available
#                 jd = job.get('jd_text') or ''
#                 email_body = None
#                 try:
#                     email_body = llm_processor.generate_email_body(job, jd)
#                 except Exception:
#                     email_body = None

#                 if email_body:
#                     # Store email in database
#                     db.update_job_email_body(job['job_id'], email_body)
                    
#                     # AUTO-SYNC TO GOOGLE SHEETS
#                     sheets_sync = get_sheets_sync()
#                     if sheets_sync and sheets_sync.client:
#                         try:
#                             # Get fresh job data for sheets sync (includes the new email body)
#                             fresh_job_data = db.get_processed_job_by_id(job['job_id'])
#                             if fresh_job_data and sheets_sync.sync_job(fresh_job_data):
#                                 db.mark_job_synced(job['job_id'])
#                                 synced += 1
#                         except Exception as e:
#                             logger.warning(f"Failed to sync job {job['job_id']} to sheets: {e}")
                    
#                     generated += 1
#             except Exception as e:
#                 logger.exception(f"Failed to generate email for job {job.get('job_id')}: {e}")

#         # Success message with sync info
#         if synced > 0:
#             await update.message.reply_text(f"✅ Generated email bodies for {generated} jobs.\n📊 Synced {synced} jobs to Google Sheets.")
#         else:
#             await update.message.reply_text(f"✅ Generated email bodies for {generated} jobs.")

#     except Exception as e:
#         logger.exception(f"Error during generate_emails: {e}")
#         await update.message.reply_text(f"❌ Failed to generate emails: {e}")


async def log_all_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.info(f"Received update: {update}")


async def callback_query_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Simple handler for inline keyboard callback queries."""
    try:
        cq = update.callback_query
        logger.info(f"Received callback_query: data={getattr(cq, 'data', None)} from {getattr(cq.from_user, 'id', None)}")
        # Acknowledge the callback so Telegram stops showing the loading state
        await cq.answer()
        # Optionally send a small message or edit the message
        if cq.data:
            await cq.message.reply_text(f"Button pressed: {cq.data}")
    except Exception as e:
        logger.exception(f"Error in callback_query_handler: {e}")


async def echo_text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Reply to plain text messages (non-commands) for debugging/diagnostics."""
    try:
        text = update.message.text if update.message else None
        logger.info(f"Echo handler received text: {text}")
        # Only reply in private chats for now to avoid spamming groups
        if update.effective_chat and update.effective_chat.type == 'private':
            await update.message.reply_text("I received your message. Try /status or press a button if present.")
    except Exception as e:
        logger.exception(f"Error in echo_text_handler: {e}")

# Global application instance for webhook handling
application = None

def setup_webhook_bot():
    """Setup the bot application object for webhook mode, without starting background tasks."""
    global application
    if application:
        return application

    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    # Add all handlers
    application.add_handler(MessageHandler(filters.ALL, log_all_messages), group=-1)
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("stop", stop_command))
    application.add_handler(CommandHandler("status", status_command))
    application.add_handler(CommandHandler("process", process_command))
    application.add_handler(CommandHandler("stats", stats_command))
    application.add_handler(CommandHandler("export", export_command))
    # application.add_handler(CommandHandler("generate_emails", generate_emails_command))
    application.add_handler(CommandHandler("sync_sheets", sync_sheets_command))
    application.add_handler(CallbackQueryHandler(callback_query_handler))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, echo_text_handler))
    
    return application

def setup_bot():
    """Set up the bot with proper error handling and start background tasks."""
    global application
    
    try:
        # Check bot instance
        if not check_bot_instance():
            logger.error("Cannot start bot: Another instance is running")
            return None
            
        application = setup_webhook_bot()

        # Start the telegram monitor
        monitor = TelegramMonitor(
            TELEGRAM_API_ID, 
            TELEGRAM_API_HASH,
            TELEGRAM_PHONE,
            TELEGRAM_GROUP_USERNAMES,
            db
        )
        
        # Start the Telegram monitor in a separate thread
        import threading
        def _start_monitor_thread():
            try:
                asyncio.run(monitor.start())
            except Exception as e:
                logger.exception(f"Monitor thread exited with error: {e}")
        threading.Thread(target=_start_monitor_thread, daemon=True).start()

        # Start command poller
        async def poll_commands():
            from asyncio import sleep
            while True:
                try:
                    pending = db.get_pending_commands(limit=10)
                    if pending:
                        for cmd in pending:
                            text = cmd['command'].strip()

                            # build a robust fake update/context for handlers
                            class _FakeMessage:
                                async def reply_text(self, text, **kwargs):
                                    if TELEGRAM_BOT_TOKEN and ADMIN_USER_ID:
                                        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
                                        payload = {"chat_id": ADMIN_USER_ID, "text": text}
                                        try:
                                            async with aiohttp.ClientSession() as session:
                                                await session.post(url, json=payload)
                                        except Exception as e:
                                            logger.error(f"Failed to send reply from fake message: {e}")
                                    return None
                                async def reply_document(self, *a, **k):
                                    return None

                            from types import SimpleNamespace as _SN
                            fake_update = _SN(effective_user=_SN(id=int(AUTHORIZED_USER_IDS[0]) if AUTHORIZED_USER_IDS else 0), message=_FakeMessage())

                            executed_ok = False
                            result_text = None
                            try:
                                if text.startswith('/start'):
                                    await start_command(fake_update, application)
                                    executed_ok = True
                                elif text.startswith('/stop'):
                                    await stop_command(fake_update, application)
                                    executed_ok = True
                                elif text.startswith('/process'):
                                    await process_jobs(application)
                                    executed_ok = True
                                # elif text.startswith('/generate_emails'):
                                #     parts = text.split(' ', 1)
                                #     args = []
                                #     if len(parts) > 1:
                                #         args = [parts[1]]
                                #     fake_ctx = _SN(args=args)
                                #     await generate_emails_command(fake_update, fake_ctx)
                                #     executed_ok = True
                                elif text.startswith('/export'):
                                    await export_command(fake_update, application)
                                    executed_ok = True
                                elif text.startswith('/sync_sheets'):
                                    await sync_sheets_command(fake_update, application)
                                    executed_ok = True
                                else:
                                    # Unknown command: send it as admin message to bot chat as fallback
                                    ok, resp = False, None
                                    try:
                                        if TELEGRAM_BOT_TOKEN and ADMIN_USER_ID:
                                            r = requests.post(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage", json={"chat_id": ADMIN_USER_ID, "text": text}, timeout=5)
                                            ok = r.ok
                                            try:
                                                resp = r.json()
                                            except Exception:
                                                resp = r.text
                                        else:
                                            ok = False
                                    except Exception:
                                        ok = False
                                    executed_ok = ok
                                    result_text = str(resp)
                            except Exception as e:
                                logger.exception(f"Error executing command from queue id={cmd['id']}: {e}")
                                executed_ok = False
                                result_text = str(e)

                            # Mark executed in DB
                            try:
                                db.mark_command_executed(cmd['id'])
                                if hasattr(db, 'update_command_result'):
                                    db.update_command_result(cmd['id'], 'done' if executed_ok else 'failed', result_text=result_text, executed_by=str(AUTHORIZED_USER_IDS[0]) if AUTHORIZED_USER_IDS else 'dashboard')
                            except Exception:
                                logger.exception('Failed to mark command executed in DB')
                    await sleep(2)
                except Exception as e:
                    logger.error(f"Command poller error: {e}")
                    await sleep(5)

        # Start command poller thread
        try:
            def _start_poller_thread():
                try:
                    asyncio.run(poll_commands())
                except Exception as e:
                    logger.exception(f"Poller thread exited with error: {e}")
            threading.Thread(target=_start_poller_thread, daemon=True).start()
        except Exception:
            logger.exception("Failed to start command poller")

        # Start job processing scheduler
        def _scheduler_thread():
            import time
            logger.info("Job scheduler thread started")
            while True:
                try:
                    asyncio.run(process_jobs(application))
                except Exception as e:
                    logger.exception(f"Scheduler thread error when running process_jobs: {e}")
                time.sleep(max(1, PROCESSING_INTERVAL_MINUTES * 60))

        # try:
        #     threading.Thread(target=_scheduler_thread, daemon=True).start()
        #     db.set_config('monitoring_status', 'running')
        # except Exception:
        #     logger.exception("Failed to start scheduler thread")

        logger.info("Telegram bot setup complete!")
        return application
        
    except Exception as e:
        logger.error(f"Failed to setup bot: {e}")
        return None

def run_bot_polling():
    """Run bot in polling mode (for local development)"""
    logger.info("Starting bot in polling mode...")
    
    global application
    application = setup_bot()
    if not application:
        logger.error("Failed to setup bot. Exiting.")
        return False
    
    try:
        logger.info("Starting bot polling...")
        application.run_polling(
            drop_pending_updates=True,
            allowed_updates=['message', 'callback_query', 'edited_message'],
            timeout=10
        )
        return True
    except KeyboardInterrupt:
        logger.info("Bot stopped by user.")
        return True
    except Exception as e:
        if "409" in str(e) or "Conflict" in str(e):
            logger.warning("Bot conflict detected, but continuing...")
            return True
        else:
            logger.error(f"Bot polling error: {e}")
            return False
    finally:
        logger.info("Cleaning up bot resources...")
        cleanup_bot_instance()

def run_bot_webhook():
    """Run bot in webhook mode (for production deployment)"""
    logger.info("Bot configured for webhook mode - use web server to handle webhooks")
    
    global application
    application = setup_bot()
    if not application:
        logger.error("Failed to setup bot. Exiting.")
        return False
    
    # Webhook setup will be handled by web server
    logger.info("Bot ready for webhook mode")

    # Keep the main thread alive for the background threads to run
    import time
    while True:
        time.sleep(3600) # Sleep for a long time

    return True

def main():
    """Main entry point - determine run mode from environment"""
    logger.info("Starting Telegram Job Bot...")
    
    # Determine run mode
    run_mode = os.getenv('BOT_RUN_MODE', 'polling').lower()
    
    if run_mode == 'webhook':
        return run_bot_webhook()
    elif run_mode == 'polling':
        return run_bot_polling()
    else:
        logger.error(f"Unknown bot run mode: {run_mode}. Use 'polling' or 'webhook'")
        return False

if __name__ == '__main__':
    try:
        success = main()
        if not success:
            sys.exit(1)
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot stopped.")
        cleanup_bot_instance()
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        cleanup_bot_instance()
        sys.exit(1)