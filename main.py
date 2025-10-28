import asyncio
import logging
import csv
import os
from datetime import datetime
from telegram import Update
from telegram.ext import (
    Application, CommandHandler, ContextTypes, MessageHandler, filters
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
monitor = None
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
                
                if sheets_sync and sheets_sync.client:
                    if sheets_sync.sync_job(processed_data):
                        db.mark_job_synced(processed_data['job_id'])
            
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
    
    current_status = db.get_config('monitoring_status')
    if current_status == 'running':
        await update.message.reply_text("⚠️ Monitoring is already running!")
        return
    
    db.set_config('monitoring_status', 'running')
    
    global monitor
    if monitor is None:
        monitor = TelegramMonitor(
            TELEGRAM_API_ID, 
            TELEGRAM_API_HASH,
            TELEGRAM_PHONE,
            TELEGRAM_GROUP_USERNAME,
            db
        )
        asyncio.create_task(monitor.start())

    if not scheduler.running:
        scheduler.add_job(process_jobs, IntervalTrigger(minutes=PROCESSING_INTERVAL_MINUTES), args=[context])
        scheduler.start()
    
    await update.message.reply_text(
        "✅ Job monitoring started!\n\n"
        "🔄 Listening for new job postings in the group...\n"
        "📊 Use /status to check progress\n"
        "⚙️ Use /process to manually process jobs"
    )

async def stop_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /stop command"""
    if not is_authorized(update.effective_user.id):
        await update.message.reply_text("❌ Unauthorized access.")
        return
    
    db.set_config('monitoring_status', 'stopped')
    
    global monitor
    if monitor:
        await monitor.stop()
        monitor = None

    if scheduler.running:
        scheduler.shutdown()
    
    await update.message.reply_text(
        "🛑 Job monitoring stopped.\n\n"
        "Use /start to resume monitoring."
    )

async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /status command"""
    if not is_authorized(update.effective_user.id):
        await update.message.reply_text("❌ Unauthorized access.")
        return
    
    monitoring_status = db.get_config('monitoring_status')
    unprocessed_count = db.get_unprocessed_count()
    jobs_today = db.get_jobs_today_stats()
    
    status_emoji = "🟢" if monitoring_status == 'running' else "🔴"
    status_text = "Running" if monitoring_status == 'running' else "Stopped"
    
    message = (
        f"📊 *Job Scraper Status*\n\n"
        f"{status_emoji} Monitoring: *{status_text}*\n"
        f"📨 Unprocessed Messages: *{unprocessed_count}*\n"
        f"✅ Processed Jobs (Today): *{jobs_today['total']}*\n"
        f"  - 📧 With Email: *{jobs_today['with_email']}*\n"
        f"  - 🔗 Without Email: *{jobs_today['without_email']}*"
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
            await update.message.reply_text("All jobs are already synced with Google Sheets.")
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


async def log_all_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.info(f"Received update: {update}")

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
    application.add_handler(CommandHandler("sync_sheets", sync_sheets_command))

    logger.info("Telegram bot is running...")
    application.run_polling()

if __name__ == '__main__':
    main()
