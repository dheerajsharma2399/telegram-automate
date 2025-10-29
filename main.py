import asyncio
import logging
import csv
import os
import requests
from datetime import datetime
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

# Initialize components
db = Database(DATABASE_PATH)
llm_processor = LLMProcessor(OPENROUTER_API_KEY, OPENROUTER_MODEL, OPENROUTER_FALLBACK_MODEL)
sheets_sync = GoogleSheetsSync(GOOGLE_CREDENTIALS_JSON, SPREADSHEET_ID) if GOOGLE_CREDENTIALS_JSON and SPREADSHEET_ID else None
scheduler = AsyncIOScheduler()

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
                job_id = db.add_processed_job(processed_data)
            
            db.update_message_status(message["id"], "processed")
            logger.info(f"Processed message {message['id']} and found {len(parsed_jobs)} jobs.")

        except Exception as e:
            logger.error(f"Failed to process message {message['id']}: {e}")
            db.update_message_status(message["id"], "failed", str(e))

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command"""
    if not is_authorized(update.effective_user.id):
        await update.message.reply_text("❌ Unauthorized access.")
        return
    
    if not scheduler.running:
        scheduler.add_job(process_jobs, IntervalTrigger(minutes=PROCESSING_INTERVAL_MINUTES), args=[context])
        scheduler.start()
        db.set_config('monitoring_status', 'running')
        await update.message.reply_text(
            "✅ Job processing started!\n\n"
            "📊 Use /status to check progress\n"
            "⚙️ Use /process to manually process jobs"
        )
    else:
        await update.message.reply_text("⚠️ Job processing is already running!")

async def stop_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /stop command"""
    if not is_authorized(update.effective_user.id):
        await update.message.reply_text("❌ Unauthorized access.")
        return
    
    if scheduler.running:
        scheduler.shutdown()
        db.set_config('monitoring_status', 'stopped')
        await update.message.reply_text(
            "🛑 Job processing stopped.\n\n"
            "Use /start to resume processing."
        )
    else:
        await update.message.reply_text("⚠️ Job processing is not running.")


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
    """Handle /sync_sheets command"""
    if not is_authorized(update.effective_user.id):
        await update.message.reply_text("❌ Unauthorized access.")
        return

    if not (sheets_sync and sheets_sync.client):
        await update.message.reply_text("Google Sheets is not configured.")
        return

    await update.message.reply_text("🔄 Syncing database with Google Sheets...")
    
    try:
        unsynced_jobs = db.get_unsynced_jobs()
        if not unsynced_jobs:
            await update.message.reply_text("No jobs to sync. All jobs are already synced with Google Sheets.")
            return

        synced_count = 0
        for job in unsynced_jobs:
            if sheets_sync.sync_job(job):
                db.mark_job_synced(job['job_id'])
                synced_count += 1
        
        await update.message.reply_text(f"✅ Synced {synced_count} jobs to Google Sheets.")

    except Exception as e:
        logger.error(f"Failed to sync with Google Sheets: {e}")
        await update.message.reply_text(f"❌ Failed to sync with Google Sheets: {e}")


async def generate_emails_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /generate_emails command - generate personalized email bodies for processed jobs."""
    if not is_authorized(update.effective_user.id):
        await update.message.reply_text("❌ Unauthorized access.")
        return

    # optional arg: comma separated job ids
    target_ids = None
    if context.args:
        arg = context.args[0]
        target_ids = [x.strip() for x in arg.split(',') if x.strip()]

    await update.message.reply_text("🧠 Generating email bodies... this may take a moment.")

    try:
        # Fetch jobs to generate for: jobs without email body or specified
        jobs = []
        if target_ids:
            # query the DB for these job_ids
            with db.get_connection() as conn:
                cur = conn.cursor()
                q = f"SELECT * FROM processed_jobs WHERE job_id IN ({','.join(['?']*len(target_ids))})"
                cur.execute(q, target_ids)
                jobs = [dict(r) for r in cur.fetchall()]
        else:
            jobs = db.get_jobs_without_email_body()

        if not jobs:
            await update.message.reply_text("No jobs found to generate emails for.")
            return

        generated = 0
        for job in jobs:
            try:
                # use LLMProcessor.generate_email_body if available
                jd = job.get('jd_text') or ''
                email_body = None
                try:
                    email_body = llm_processor.generate_email_body(job, jd)
                except Exception:
                    email_body = None

                if email_body:
                    db.update_job_email_body(job['job_id'], email_body)
                    generated += 1
            except Exception as e:
                logger.exception(f"Failed to generate email for job {job.get('job_id')}: {e}")

        await update.message.reply_text(f"✅ Generated email bodies for {generated} jobs.")

    except Exception as e:
        logger.exception(f"Error during generate_emails: {e}")
        await update.message.reply_text(f"❌ Failed to generate emails: {e}")


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

def main():
    """Run the bot."""
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    application.add_handler(MessageHandler(filters.ALL, log_all_messages), group=-1)
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("stop", stop_command))
    application.add_handler(CommandHandler("status", status_command))
    application.add_handler(CommandHandler("process", process_command))
    application.add_handler(CommandHandler("stats", stats_command))
    application.add_handler(CommandHandler("export", export_command))
    application.add_handler(CommandHandler("generate_emails", generate_emails_command))
    application.add_handler(CommandHandler("sync_sheets", sync_sheets_command))
    # Handle callback queries from inline keyboards
    application.add_handler(CallbackQueryHandler(callback_query_handler))
    # Simple non-command text handler for diagnostics
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, echo_text_handler))

    # Start the telegram monitor
    monitor = TelegramMonitor(
        TELEGRAM_API_ID, 
        TELEGRAM_API_HASH,
        TELEGRAM_PHONE,
        TELEGRAM_GROUP_USERNAMES,
        db
    )
    # Start the Telegram monitor in a separate thread with its own event loop
    import threading
    def _start_monitor_thread():
        try:
            asyncio.run(monitor.start())
        except Exception as e:
            logger.exception(f"Monitor thread exited with error: {e}")
    threading.Thread(target=_start_monitor_thread, daemon=True).start()

    # Background task: poll commands queued by the web dashboard
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
                            async def reply_text(self, *a, **k):
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
                            elif text.startswith('/generate_emails'):
                                parts = text.split(' ', 1)
                                args = []
                                if len(parts) > 1:
                                    args = [parts[1]]
                                fake_ctx = _SN(args=args)
                                await generate_emails_command(fake_update, fake_ctx)
                                executed_ok = True
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

                        # Mark executed in DB and optionally update result
                        try:
                            db.mark_command_executed(cmd['id'])
                            if hasattr(db, 'update_command_result'):
                                db.update_command_result(cmd['id'], 'done' if executed_ok else 'failed', result_text=result_text, executed_by=str(AUTHORIZED_USER_IDS[0]) if AUTHORIZED_USER_IDS else 'dashboard')
                        except Exception:
                            logger.exception('Failed to mark command executed in DB')

                        # Notify admin of result if ADMIN_USER_ID set
                        try:
                            if os.getenv('TELEGRAM_BOT_TOKEN') and os.getenv('ADMIN_USER_ID'):
                                note = f"Command executed: {cmd['command']} - {'OK' if executed_ok else 'FAILED'}"
                                if result_text:
                                    note += f"\n{result_text}"
                                # best-effort notify via bot API
                                url = f"https://api.telegram.org/bot{os.getenv('TELEGRAM_BOT_TOKEN')}/sendMessage"
                                requests.post(url, json={"chat_id": os.getenv('ADMIN_USER_ID'), "text": note})
                        except Exception:
                            logger.exception('Failed to notify admin about command execution')
                await sleep(2)
            except Exception as e:
                logger.error(f"Command poller error: {e}")
                await sleep(5)

    # Start command poller
    try:
        from types import SimpleNamespace
        # Run poller in its own thread/event loop so it doesn't depend on Application loop
        def _start_poller_thread():
            try:
                asyncio.run(poll_commands())
            except Exception as e:
                logger.exception(f"Poller thread exited with error: {e}")
        threading.Thread(target=_start_poller_thread, daemon=True).start()
    except Exception:
        logger.exception("Failed to start command poller")

    # Start the job processing scheduler by running a dedicated thread that
    # periodically calls the async `process_jobs` coroutine. We do this instead
    # of using AsyncIOScheduler.start() here because that requires a running
    # asyncio event loop in the current thread (which we don't have). The
    # daemon thread will call `asyncio.run(...)` for each invocation.
    def _scheduler_thread():
        import time
        logger.info("Job scheduler thread started")
        while True:
            try:
                asyncio.run(process_jobs(application))
            except Exception as e:
                logger.exception(f"Scheduler thread error when running process_jobs: {e}")
            # sleep until next interval
            time.sleep(max(1, PROCESSING_INTERVAL_MINUTES * 60))

    try:
        threading.Thread(target=_scheduler_thread, daemon=True).start()
        db.set_config('monitoring_status', 'running')
    except Exception:
        logger.exception("Failed to start scheduler thread")

    logger.info("Telegram bot is running...")
    # Run polling (blocking). run_polling will manage the Application lifecycle.
    application.run_polling(close_loop=False)

if __name__ == '__main__':
    try:
        main()
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot stopped.")