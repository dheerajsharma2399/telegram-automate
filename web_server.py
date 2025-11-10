import os
import logging
import asyncio
import ssl
from flask import Flask, render_template, jsonify, request
import requests
from database import Database
from dotenv import load_dotenv

load_dotenv()

from config import TELEGRAM_BOT_TOKEN, ADMIN_USER_ID, DATABASE_URL
import signal
import socket
import threading
import tempfile
import json
from urllib.parse import urljoin
from llm_processor import LLMProcessor
from sheets_sync import GoogleSheetsSync
from config import OPENROUTER_API_KEY, OPENROUTER_MODEL, OPENROUTER_FALLBACK_MODEL, GOOGLE_CREDENTIALS_JSON, SPREADSHEET_ID, TELEGRAM_API_ID, TELEGRAM_API_HASH, TELEGRAM_PHONE

app = Flask(__name__)
application = app  # Gunicorn expects 'application'
db = Database(DATABASE_URL)

# LLM processor and sheets sync available to web endpoints (optional)
llm_processor = None
try:
    llm_processor = LLMProcessor(OPENROUTER_API_KEY, OPENROUTER_MODEL, OPENROUTER_FALLBACK_MODEL)
except Exception:
    llm_processor = None

sheets_sync = None

def get_sheets_sync():
    global sheets_sync
    if sheets_sync is None and GOOGLE_CREDENTIALS_JSON and SPREADSHEET_ID:
        try:
            sheets_sync = GoogleSheetsSync(GOOGLE_CREDENTIALS_JSON, SPREADSHEET_ID)
        except Exception:
            pass
    return sheets_sync

# Bot application for webhook mode
bot_application = None

async def setup_bot_webhook():
    """Setup bot for webhook mode"""
    global bot_application
    try:
        # Check if token exists first
        from config import TELEGRAM_BOT_TOKEN
        if not TELEGRAM_BOT_TOKEN:
            logging.error("TELEGRAM_BOT_TOKEN not configured - skipping bot initialization")
            return False
            
        # Import the main module and setup bot
        import main
        bot_application = await main.setup_webhook_bot()
        if bot_application:
            logging.info("Bot application loaded for webhook mode")
            return True
        else:
            logging.error("Failed to setup bot application")
            return False
    except Exception as e:
        logging.error(f"Failed to setup bot webhook: {e}")
        return False

# Initialize bot if webhook mode is enabled
if os.getenv('BOT_RUN_MODE', '').lower() == 'webhook':
    try:
        bot_application = asyncio.run(setup_bot_webhook())
        # Auto-setup webhook URL if bot was successfully loaded
        if bot_application:
            def auto_setup_webhook():
                """Auto-setup webhook after web server starts"""
                import time
                time.sleep(5)  # Wait for server to start
                try:
                    # Use the correct domain for the new deployment
                    webhook_url = "https://job.mooh.me/webhook"
                    logging.info(f"Setting webhook to correct domain: {webhook_url}")
                    
                    # FIXED: Check if bot_application is properly initialized
                    if hasattr(bot_application, 'bot'):
                        async def do_set_webhook():
                            await bot_application.bot.set_webhook(
                                url=webhook_url,
                                allowed_updates=['message', 'callback_query', 'edited_message']
                            )
                        
                        loop = asyncio.new_event_loop()
                        asyncio.set_event_loop(loop)
                        loop.run_until_complete(do_set_webhook())
                        
                        logging.info(f"Auto-configured webhook to: {webhook_url}")
                    else:
                        logging.warning("bot_application is not properly initialized - skipping webhook setup")
                except Exception as e:
                    logging.warning(f"Failed to set webhook: {e}")
            
            # Start auto-setup in background thread
            threading.Thread(target=auto_setup_webhook, daemon=True).start()
    except Exception as e:
        logging.error(f"Bot webhook initialization failed: {e}")

logging.basicConfig(level=logging.INFO)

# --- Helper Functions ---

def send_telegram_command(command):
    """Sends a command to the Telegram bot as the admin user."""
    if not TELEGRAM_BOT_TOKEN or not ADMIN_USER_ID:
        logging.error("TELEGRAM_BOT_TOKEN or ADMIN_USER_ID not set.")
        return False, "Bot token or admin user ID is not configured."

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": ADMIN_USER_ID,
        "text": command,
    }
    try:
        response = requests.post(url, json=payload)
        response.raise_for_status()
        return True, response.json()
    except requests.exceptions.RequestException as e:
        logging.error(f"Failed to send command to Telegram: {e}")
        return False, str(e)


@app.route("/health")
def health():
    # Basic process health
    status = {"status": "ok"}
    # Check if the configured port is accepting connections (localhost)
    current_port = int(os.environ.get("PORT", 9501))
    try:
        with socket.create_connection(("127.0.0.1", current_port), timeout=1):
            status[f'http_port_{current_port}'] = 'listening'
    except Exception:
        status[f'http_port_{current_port}'] = 'not_listening'
    return jsonify(status)


@app.route("/test")
def test_endpoint():
    """A simple endpoint for testing network connectivity."""
    logging.info("Test endpoint was hit!")
    return "OK", 200


def _werkzeug_shutdown():
    # Werkzeug shutdown helper
    func = request.environ.get('werkzeug.server.shutdown')
    if func is None:
        raise RuntimeError('Not running with the Werkzeug Server')
    func()


@app.route('/_shutdown', methods=['POST'])
def shutdown():
    # Simple protection: require admin id token in JSON body
    try:
        data = request.get_json(force=True) or {}
        token = data.get('token')
        if str(token) != str(ADMIN_USER_ID):
            return jsonify({'error': 'Unauthorized'}), 403
    except Exception:
        return jsonify({'error': 'Bad request'}), 400

    # Optionally enqueue stop command
    try:
        if hasattr(db, 'enqueue_command'):
            db.enqueue_command('/stop')
    except Exception as e:
        logging.warning(f'Failed to enqueue stop command during shutdown: {e}')

    # Shutdown in a thread to avoid blocking the request
    threading.Thread(target=_werkzeug_shutdown).start()
    return jsonify({'message': 'Shutting down'})

def read_log_file(log_file, lines=100):
    """Reads the last N lines of a log file."""
    try:
        with open(log_file, "r") as f:
            lines = f.readlines()[-lines:]
        return "".join(lines)
    except FileNotFoundError:
        return f"Log file not found: {log_file}"
    except Exception as e:
        return f"Error reading log file: {e}"

# --- API Routes for Frontend ---

@app.route("/api/status")
def api_status():
    """API endpoint to get current application status."""
    try:
        status = {
            "monitoring_status": db.get_config("monitoring_status"),
            "unprocessed_count": db.get_unprocessed_count(),
            "jobs_today": db.get_jobs_today_stats(),
            "telegram_status": db.get_telegram_login_status(),
            "telegram_session_exists": bool(db.get_telegram_session()),
        }
        return jsonify(status)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/bot/force_restart", methods=["POST"])
def force_restart_bot():
    """Deletes the bot lock file to allow restart."""
    lock_file = os.path.join(tempfile.gettempdir(), 'telegram_bot.lock')
    try:
        if os.path.exists(lock_file):
            os.remove(lock_file)
            return jsonify({"message": "Lock file removed. The bot worker should restart."})
        else:
            return jsonify({"message": "No lock file found."})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/pending_commands')
def api_pending_commands():
    """Return all pending commands from the DB."""
    try:
        pending = db.list_all_pending_commands()
        return jsonify(pending)
    except Exception as e:
        logging.exception('Failed to fetch pending commands')
        return jsonify({'error': str(e)}), 500


@app.route('/api/command/<int:cmd_id>/cancel', methods=['POST'])
def api_cancel_command(cmd_id):
    try:
        ok = False
        if hasattr(db, 'cancel_command'):
            ok = db.cancel_command(cmd_id)
        if not ok:
            return jsonify({'error': 'Command not found or could not be cancelled'}), 404
        return jsonify({'message': 'Command cancelled'})
    except Exception as e:
        logging.exception('Failed to cancel command')
        return jsonify({'error': str(e)}), 500


@app.route('/api/monitored_groups', methods=['GET'])
def api_get_monitored_groups():
    try:
        val = db.get_config('monitored_groups') or ''
        groups = [s for s in val.split(',') if s]
        return jsonify({'groups': groups})
    except Exception as e:
        logging.exception('Failed to get monitored groups')
        return jsonify({'error': str(e)}), 500


@app.route('/api/monitored_groups', methods=['POST'])
def api_add_monitored_group():
    try:
        data = request.get_json(force=True) or {}
        group = data.get('group')
        if not group:
            return jsonify({'error': 'group required'}), 400
        current = db.get_config('monitored_groups') or ''
        groups = [s for s in current.split(',') if s]
        if group in groups:
            return jsonify({'message': 'already present', 'groups': groups})
        groups.append(group)
        db.set_config('monitored_groups', ','.join(groups))
        return jsonify({'message': 'added', 'groups': groups})
    except Exception as e:
        logging.exception('Failed to add monitored group')
        return jsonify({'error': str(e)}), 500


@app.route('/api/monitored_groups', methods=['DELETE'])
def api_remove_monitored_group():
    try:
        data = request.get_json(force=True) or {}
        group = data.get('group')
        if not group:
            return jsonify({'error': 'group required'}), 400
        current = db.get_config('monitored_groups') or ''
        groups = [s for s in current.split(',') if s]
        if group not in groups:
            return jsonify({'error': 'not found', 'groups': groups}), 404
        groups = [g for g in groups if g != group]
        db.set_config('monitored_groups', ','.join(groups))
        return jsonify({'message': 'removed', 'groups': groups})
    except Exception as e:
        logging.exception('Failed to remove monitored group')
        return jsonify({'error': str(e)}), 500

@app.route("/api/queue")
def api_queue():
    """API endpoint to get the unprocessed message queue."""
    try:
        queue = db.get_unprocessed_messages(limit=100)
        return jsonify(queue)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/logs")
def api_logs():
    """API endpoint to get logs."""
    try:
        logs = {
            "bot_logs": read_log_file("bot.log"),
            "monitor_logs": read_log_file("monitor.log"),
            "webhook_logs": read_log_file("webhook.log"),
        }
        return jsonify(logs)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/command", methods=["POST"])
def api_command():
    """API endpoint to send a command to the bot."""
    command = request.json.get("command")
    if not command:
        return jsonify({"error": "Command not specified"}), 400
    # Enqueue command in database for the bot process to pick up
    try:
        if hasattr(db, 'enqueue_command') and callable(getattr(db, 'enqueue_command')):
            cmd_id = db.enqueue_command(command)
            return jsonify({"message": f"Command '{command}' enqueued.", "command_id": cmd_id})
        else:
            logging.error("Database object missing 'enqueue_command' method, falling back to Telegram send.")
            ok, resp = send_telegram_command(command)
            if ok:
                return jsonify({"message": f"Command '{command}' sent via Telegram as fallback.", "telegram_response": resp})
            else:
                return jsonify({"error": "Failed to enqueue command and Telegram fallback failed.", "details": resp}), 500
    except Exception as e:
        logging.error(f"Failed to enqueue command: {e}")
        return jsonify({"error": "Failed to enqueue command", "details": str(e)}), 500


# NEW: Job Relevance Filtering Endpoints

@app.route("/api/jobs/relevant")
def api_relevant_jobs():
    """Get relevant jobs (fresher-friendly)"""
    try:
        has_email = request.args.get('has_email')
        if has_email == 'true':
            jobs = db.get_relevant_jobs(has_email=True)
        elif has_email == 'false':
            jobs = db.get_relevant_jobs(has_email=False)
        else:
            jobs = db.get_relevant_jobs()
        
        return jsonify({
            "jobs": jobs,
            "count": len(jobs),
            "filter": "relevant" + (" (with email)" if has_email == 'true' else " (without email)" if has_email == 'false' else " (all)")
        })
    except Exception as e:
        logging.error(f"Failed to fetch relevant jobs: {e}")
        return jsonify({"error": str(e)}), 500

@app.route("/api/jobs/irrelevant")
def api_irrelevant_jobs():
    """Get irrelevant jobs (experienced required)"""
    try:
        has_email = request.args.get('has_email')
        if has_email == 'true':
            jobs = db.get_irrelevant_jobs(has_email=True)
        elif has_email == 'false':
            jobs = db.get_irrelevant_jobs(has_email=False)
        else:
            jobs = db.get_irrelevant_jobs()
        
        return jsonify({
            "jobs": jobs,
            "count": len(jobs),
            "filter": "irrelevant" + (" (with email)" if has_email == 'true' else " (without email)" if has_email == 'false' else " (all)")
        })
    except Exception as e:
        logging.error(f"Failed to fetch irrelevant jobs: {e}")
        return jsonify({"error": str(e)}), 500

@app.route("/api/jobs/stats")
def api_jobs_stats():
    """Get job statistics including relevance breakdown"""
    try:
        relevant_with_email = db.get_relevant_jobs(has_email=True)
        relevant_without_email = db.get_relevant_jobs(has_email=False)
        irrelevant_with_email = db.get_irrelevant_jobs(has_email=True)
        irrelevant_without_email = db.get_irrelevant_jobs(has_email=False)
        
        return jsonify({
            "relevant": {
                "total": len(relevant_with_email) + len(relevant_without_email),
                "with_email": len(relevant_with_email),
                "without_email": len(relevant_without_email)
            },
            "irrelevant": {
                "total": len(irrelevant_with_email) + len(irrelevant_without_email),
                "with_email": len(irrelevant_with_email),
                "without_email": len(irrelevant_without_email)
            },
            "total_jobs": len(relevant_with_email) + len(relevant_without_email) + len(irrelevant_with_email) + len(irrelevant_without_email)
        })
    except Exception as e:
        logging.error(f"Failed to fetch job stats: {e}")
        return jsonify({"error": str(e)}), 500

@app.route("/api/jobs")
def api_jobs():
    """API endpoint to get all processed jobs that are not hidden."""
    try:
        jobs = db.get_jobs_by_sheet_name('non-email')
        return jsonify(jobs)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/jobs/hide", methods=["POST"])
def api_hide_jobs():
    """API endpoint to mark jobs as hidden."""
    try:
        data = request.get_json(force=True) or {}
        job_ids = data.get('job_ids')
        if not job_ids or not isinstance(job_ids, list):
            return jsonify({"error": "job_ids must be a non-empty list"}), 400
        
        rows_affected = db.hide_jobs(job_ids)
        return jsonify({"message": f"{rows_affected} jobs hidden successfully."})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ===============================================
# DASHBOARD JOBS API ENDPOINTS (NEW)
# ===============================================

@app.route("/api/dashboard/jobs", methods=["GET"])
def get_dashboard_jobs():
    """Get all dashboard jobs with optional filtering"""
    try:
        status_filter = request.args.get('status')
        relevance_filter = request.args.get('relevance')
        include_archived = request.args.get('include_archived', 'false').lower() == 'true'
        
        jobs = db.get_dashboard_jobs(
            status_filter=status_filter,
            relevance_filter=relevance_filter,
            include_archived=include_archived
        )
        
        return jsonify({
            "jobs": jobs,
            "count": len(jobs),
            "filters": {
                "status": status_filter,
                "relevance": relevance_filter,
                "include_archived": include_archived
            }
        })
    except Exception as e:
        logging.error(f"Failed to fetch dashboard jobs: {e}")
        return jsonify({"error": str(e)}), 500

@app.route("/api/dashboard/jobs", methods=["POST"])
def add_job_to_dashboard():
    """Add a new job to the dashboard"""
    try:
        data = request.get_json(force=True) or {}
        
        # Required fields validation
        required_fields = ['company_name', 'job_role', 'application_link']
        missing_fields = [field for field in required_fields if not data.get(field)]
        if missing_fields:
            return jsonify({"error": f"Missing required fields: {missing_fields}"}), 400
        
        # Add default values
        data.setdefault('application_status', 'not_applied')
        data.setdefault('job_relevance', 'relevant')
        data.setdefault('conflict_status', 'none')
        data.setdefault('is_duplicate', False)
        
        job_id = db.add_dashboard_job(data)
        if job_id:
            return jsonify({
                "message": "Job added to dashboard successfully",
                "job_id": job_id
            }), 201
        else:
            return jsonify({"error": "Failed to add job to dashboard"}), 500
            
    except Exception as e:
        logging.error(f"Failed to add job to dashboard: {e}")
        return jsonify({"error": str(e)}), 500

@app.route("/api/dashboard/jobs/<int:job_id>", methods=["PATCH"])
def update_job_status(job_id):
    """Update job application status"""
    try:
        data = request.get_json(force=True) or {}
        status = data.get('status')
        application_date = data.get('application_date')
        
        if not status:
            return jsonify({"error": "Status is required"}), 400
        
        valid_statuses = ['not_applied', 'applied', 'interview', 'rejected', 'offer', 'archived']
        if status not in valid_statuses:
            return jsonify({"error": f"Invalid status. Must be one of: {valid_statuses}"}), 400
        
        success = db.update_dashboard_job_status(job_id, status, application_date)
        if success:
            return jsonify({"message": f"Job status updated to {status}"})
        else:
            return jsonify({"error": "Job not found"}), 404
            
    except Exception as e:
        logging.error(f"Failed to update job status: {e}")
        return jsonify({"error": str(e)}), 500

@app.route("/api/dashboard/jobs/<int:job_id>/notes", methods=["POST"])
def add_job_notes(job_id):
    """Add notes to a job"""
    try:
        data = request.get_json(force=True) or {}
        notes = data.get('notes', '').strip()
        
        if not notes:
            return jsonify({"error": "Notes cannot be empty"}), 400
        
        success = db.add_job_notes(job_id, notes)
        if success:
            return jsonify({"message": "Notes added successfully"})
        else:
            return jsonify({"error": "Job not found"}), 404
            
    except Exception as e:
        logging.error(f"Failed to add notes to job: {e}")
        return jsonify({"error": str(e)}), 500

@app.route("/api/dashboard/jobs/bulk_status", methods=["POST"])
def bulk_update_status():
    """Update status for multiple jobs"""
    try:
        data = request.get_json(force=True) or {}
        job_ids = data.get('job_ids', [])
        status = data.get('status')
        application_date = data.get('application_date')
        
        if not job_ids or not isinstance(job_ids, list):
            return jsonify({"error": "job_ids must be a non-empty list"}), 400
        
        if not status:
            return jsonify({"error": "status is required"}), 400
        
        valid_statuses = ['not_applied', 'applied', 'interview', 'rejected', 'offer', 'archived']
        if status not in valid_statuses:
            return jsonify({"error": f"Invalid status. Must be one of: {valid_statuses}"}), 400
        
        updated_count = db.bulk_update_status(job_ids, status, application_date)
        return jsonify({
            "message": f"Updated {updated_count} jobs to {status}",
            "updated_count": updated_count
        })
        
    except Exception as e:
        logging.error(f"Failed to bulk update status: {e}")
        return jsonify({"error": str(e)}), 500

@app.route("/api/dashboard/import", methods=["POST"])
def import_jobs_from_sheets():
    """Import non-email jobs from processed_jobs to dashboard"""
    try:
        data = request.get_json(force=True) or {}
        sheet_name = data.get('sheet_name', 'non-email')
        max_jobs = data.get('max_jobs', 50)
        
        if sheet_name != 'non-email':
            return jsonify({"error": "Currently only 'non-email' sheet is supported"}), 400
        
        imported_count = db.import_jobs_from_processed(sheet_name, max_jobs)
        
        return jsonify({
            "message": f"Imported {imported_count} jobs from {sheet_name} sheet",
            "imported_count": imported_count
        })
        
    except Exception as e:
        logging.error(f"Failed to import jobs: {e}")
        return jsonify({"error": str(e)}), 500

@app.route("/api/dashboard/duplicates", methods=["GET"])
def get_detected_duplicates():
    """Get detected duplicate jobs"""
    try:
        # Simple query to get duplicate jobs
        with db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM dashboard_jobs
                WHERE is_duplicate = TRUE
                ORDER BY created_at DESC
            """)
            duplicates = [dict(row) for row in cursor.fetchall()]
        
        return jsonify({
            "duplicates": duplicates,
            "count": len(duplicates)
        })
        
    except Exception as e:
        logging.error(f"Failed to get duplicates: {e}")
        return jsonify({"error": str(e)}), 500

@app.route("/api/dashboard/duplicates/<int:job_id>", methods=["POST"])
def mark_as_duplicate_endpoint(job_id):
    """Mark a job as duplicate"""
    try:
        data = request.get_json(force=True) or {}
        duplicate_of_id = data.get('duplicate_of_id')
        confidence_score = data.get('confidence_score', 0.8)
        
        if not duplicate_of_id:
            return jsonify({"error": "duplicate_of_id is required"}), 400
        
        success = db.mark_as_duplicate(job_id, duplicate_of_id, confidence_score)
        if success:
            return jsonify({"message": "Job marked as duplicate"})
        else:
            return jsonify({"error": "Failed to mark as duplicate"}), 500
            
    except Exception as e:
        logging.error(f"Failed to mark as duplicate: {e}")
        return jsonify({"error": str(e)}), 500

@app.route("/api/dashboard/detect_duplicates", methods=["POST"])
def detect_duplicates_endpoint():
    """Detect duplicate jobs in dashboard"""
    try:
        detected_count = db.detect_duplicate_jobs()
        return jsonify({
            "message": f"Detected {detected_count} potential duplicates",
            "detected_count": detected_count
        })
        
    except Exception as e:
        logging.error(f"Failed to detect duplicates: {e}")
        return jsonify({"error": str(e)}), 500

@app.route("/api/dashboard/jobs/export", methods=["GET"])
def export_dashboard_jobs():
    """Export dashboard jobs to CSV format"""
    try:
        format_type = request.args.get('format', 'csv')
        export_data = db.export_dashboard_jobs(format_type)
        
        if format_type == 'csv':
            # For now, return JSON with CSV data
            return jsonify(export_data)
        else:
            return jsonify({"error": "Only CSV format is currently supported"}), 400
            
    except Exception as e:
        logging.error(f"Failed to export jobs: {e}")
        return jsonify({"error": str(e)}), 500

@app.route("/api/dashboard/stats", methods=["GET"])
def get_dashboard_stats():
    """Get dashboard job statistics"""
    try:
        # Get jobs by status
        all_jobs = db.get_dashboard_jobs()
        
        stats = {
            "total_jobs": len(all_jobs),
            "by_status": {},
            "by_relevance": {},
            "recent_additions": 0
        }
        
        # Calculate statistics
        from datetime import datetime, timedelta
        yesterday = datetime.now() - timedelta(days=1)
        
        for job in all_jobs:
            status = job.get('application_status', 'unknown')
            relevance = job.get('job_relevance', 'unknown')
            
            stats["by_status"][status] = stats["by_status"].get(status, 0) + 1
            stats["by_relevance"][relevance] = stats["by_relevance"].get(relevance, 0) + 1
            
            # Count recent additions
            if job.get('created_at') and job['created_at'] > yesterday:
                stats["recent_additions"] += 1
        
        return jsonify(stats)
        
    except Exception as e:
        logging.error(f"Failed to get dashboard stats: {e}")
        return jsonify({"error": str(e)}), 500

@app.route("/api/dashboard/jobs/<int:job_id>/message", methods=["GET"])
def get_dashboard_job_message(job_id: int):
    """Get the original raw message and job description for a dashboard job"""
    try:
        # Get the dashboard job
        with db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM dashboard_jobs WHERE id = %s", (job_id,))
            job = cursor.fetchone()
            
            if not job:
                return jsonify({"error": "Job not found"}), 404
            
            job = dict(job)
            
            # Get the original processed job if source_job_id exists
            original_job = None
            raw_message = None
            
            if job.get('source_job_id'):
                # Get original processed job
                cursor.execute("SELECT * FROM processed_jobs WHERE job_id = %s", (job['source_job_id'],))
                original_job = cursor.fetchone()
                if original_job:
                    original_job = dict(original_job)
                
                # Get raw message if raw_message_id exists in processed job
                if original_job and original_job.get('raw_message_id'):
                    cursor.execute("SELECT * FROM raw_messages WHERE id = %s", (original_job['raw_message_id'],))
                    raw_message = cursor.fetchone()
                    if raw_message:
                        raw_message = dict(raw_message)
            
            return jsonify({
                "dashboard_job": job,
                "original_job": original_job,
                "raw_message": raw_message
            })
            
    except Exception as e:
        logging.error(f"Failed to get job message for job {job_id}: {e}")
        return jsonify({"error": str(e)}), 500


# --- Telegram Webhook Endpoint ---

async def process_webhook_async(update_data):
    """Process webhook update in an async context"""
    try:
        if not bot_application:
            logging.error("Bot application not available for webhook")
            return False
        
        # FIXED: Check if bot_application is properly initialized
        if not hasattr(bot_application, 'bot'):
            logging.error("Bot application not properly initialized for webhook")
            return False
        
        from telegram import Update
        update = Update.de_json(update_data, bot_application.bot)
        
        await bot_application.process_update(update)
        logging.info(f"Processed webhook update: {update.update_id}")
        return True
            
    except Exception as e:
        logging.error(f"Error processing webhook: {e}")
        return False

# --- Webhook Logger Setup ---
webhook_logger = logging.getLogger('webhook')
webhook_logger.setLevel(logging.INFO)
webhook_handler = logging.FileHandler('webhook.log')
webhook_handler.setFormatter(logging.Formatter('%(asctime)s - %(message)s'))
webhook_logger.addHandler(webhook_handler)


@app.route("/webhook", methods=["POST"])
def telegram_webhook():
    """Handle incoming Telegram webhook updates"""
    webhook_logger.info("--- WEBHOOK ENDPOINT HIT ---")
    try:
        headers = {k: v for k, v in request.headers.items()}
        webhook_logger.info(f"Request Headers: {headers}")
        raw_body = request.get_data(as_text=True)
        webhook_logger.info(f"Raw Request Body: {raw_body}")

        # Check if bot application is available
        if not bot_application:
            webhook_logger.error("Bot application not available for webhook")
            return jsonify({"error": "Bot not initialized"}), 500
        
        # Get the update data from the raw body
        update_data = json.loads(raw_body)
        if not update_data:
            return jsonify({"error": "No update data"}), 400
        
        # Process the update in a separate thread with its own event loop
        def run_in_thread(data):
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(process_webhook_async(data))
            loop.close()

        import threading
        thread = threading.Thread(target=run_in_thread, args=(update_data,))
        thread.start()
        
        webhook_logger.info(f"Webhook update queued for processing: {update_data.get('update_id', 'unknown')}")
        return jsonify({"status": "queued"})
            
    except Exception as e:
        webhook_logger.error(f"Error processing webhook: {e}")
        return jsonify({"error": str(e)}), 500

@app.route("/api/setup_webhook", methods=["POST"])
def setup_webhook():
    """Setup webhook URL for the bot"""
    try:
        if not bot_application:
            return jsonify({"error": "Bot application not available"}), 500
        
        # FIXED: Check if bot_application is properly initialized
        if not hasattr(bot_application, 'bot'):
            return jsonify({"error": "Bot application not properly initialized"}), 500
        
        data = request.get_json(force=True) or {}
        webhook_url = data.get('webhook_url')
        
        if not webhook_url:
            service_url = os.getenv('RENDER_SERVICE_URL') or os.getenv('SERVICE_URL') or os.getenv('DEPLOYMENT_URL')
            if service_url:
                webhook_url = f"{service_url}/webhook"
            else:
                return jsonify({"error": "No webhook URL provided and unable to construct it"}), 400
        
        async def do_set_webhook():
            await bot_application.bot.set_webhook(
                url=webhook_url,
                allowed_updates=['message', 'callback_query', 'edited_message']
            )

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(do_set_webhook())
        
        logging.info(f"Webhook set to: {webhook_url}")
        return jsonify({"message": f"Webhook set to {webhook_url}"})
        
    except Exception as e:
        logging.error(f"Failed to setup webhook: {e}")
        return jsonify({"error": str(e)}), 500

@app.route("/api/remove_webhook", methods=["POST"])
def remove_webhook():
    """Remove webhook and switch to polling"""
    try:
        if not bot_application:
            return jsonify({"error": "Bot application not available"}), 500
        
        # FIXED: Check if bot_application is properly initialized
        if not hasattr(bot_application, 'bot'):
            return jsonify({"error": "Bot application not properly initialized"}), 500
        
        async def do_delete_webhook():
            await bot_application.bot.delete_webhook()

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(do_delete_webhook())

        logging.info("Webhook removed")
        return jsonify({"message": "Webhook removed successfully"})
        
    except Exception as e:
        logging.error(f"Failed to remove webhook: {e}")
        return jsonify({"error": str(e)}), 500

# @app.route('/api/generate_emails', methods=['POST'])
# def api_generate_emails():
#     """Generate enhanced email bodies for processed jobs.
#     
#     This endpoint supports:
#     1. Direct generation when running as standalone service
#     2. Command queuing when running as dashboard-only service
#     
#     If LLM processor is available, generates enhanced job-specific emails.
#     If not available, enqueues command for bot service to handle.
#     """
#     try:
#         payload = request.get_json(force=True) or {}
#         job_ids = payload.get('job_ids')
#         run_now = payload.get('run_now', False)

#         # Case 1: Direct generation (standalone mode)
#         if llm_processor and run_now:
#             logging.info("Direct email generation triggered.")
#             email_jobs_without_emails = db.get_email_jobs_needing_generation()
#             logging.info(f"Found {len(email_jobs_without_emails)} jobs needing email generation.")

#             if not email_jobs_without_emails:
#                 return jsonify({"message": "No jobs found that need an email body generated.", "generated": 0})
            
#             generated = 0
#             for job in email_jobs_without_emails:
#                 try:
#                     # Use enhanced email generation with job-specific content
#                     email_body = llm_processor.generate_email_body(job, job.get('jd_text', ''))
#                     if email_body:
#                         db.update_job_email_body(job['job_id'], email_body)
#                         generated += 1
#                 except Exception as e:
#                     logging.error(f"Failed to generate email for job {job.get('job_id')}: {e}")
            
#             return jsonify({
#                 "message": f"Generated {generated} email bodies for 'email' sheet jobs.",
#                 "generated": generated,
#                 "mode": "direct_generation"
#             })
        
#         # Case 2: Command queuing (service separation mode)
#         else:
#             # enqueue the command for the bot poller to execute
#             cmd = '/generate_emails'
#             if job_ids:
#                 cmd = f"/generate_emails {','.join(map(str, job_ids))}"

#             if hasattr(db, 'enqueue_command') and callable(getattr(db, 'enqueue_command')):
#                 cmd_id = db.enqueue_command(cmd)
#                 return jsonify({
#                     "message": "Email generation enqueued.",
#                     "command_id": cmd_id,
#                     "mode": "command_queue"
#                 })
#             else:
#                 ok, resp = send_telegram_command(cmd)
#                 if ok:
#                     return jsonify({
#                         "message": "Email generation sent via Telegram fallback.",
#                         "telegram_response": resp,
#                         "mode": "telegram_fallback"
#                     })
#                 else:
#                     return jsonify({"error": "Failed to enqueue generation and Telegram fallback failed.", "details": resp}), 500
                    
#     except Exception as e:
#         logging.exception('Failed to generate emails')
#         return jsonify({'error': str(e)}), 500

# @app.route('/api/sheets/generate_email_bodies', methods=['POST'])
# def api_sheets_generate_email_bodies():
#     """Generate email bodies from Google Sheets data.
#     
#     This endpoint can generate emails directly if LLM processor is available,
#     or delegate to the bot service if not.
#     """
#     try:
#         payload = request.get_json(force=True) or {}
#         sheet = payload.get('sheet', 'email')
#         limit = payload.get('limit', 50)
#         
#         sheets_sync = get_sheets_sync()
#         if not sheets_sync:
#             return jsonify({'error': 'Google Sheets not configured'}), 500
#         
#         if llm_processor:
#             # Direct generation mode - generate emails for sheet data
#             try:
#                 jobs_to_generate = sheets_sync.get_jobs_needing_email_generation(sheet)
#                 if not jobs_to_generate:
#                     return jsonify({"message": f"No jobs found in '{sheet}' sheet that need an email body generated.", "generated": 0})

#                 generated_count = 0
#                 for job in jobs_to_generate:
#                     try:
#                         # Ensure job_id is present for logging and updating
#                         job_id = job.get('Job ID', 'unknown_job')
                        
#                         # Use enhanced email generation with job-specific content
#                         # Pass job_data as a dictionary, and jd_text
#                         email_body = llm_processor.generate_email_body(job, job.get('Job Description', ''))
                        
#                         if email_body:
#                             if sheets_sync.update_job_email_body_in_sheet(job_id, email_body, sheet):
#                                 generated_count += 1
#                             else:
#                                 logging.warning(f"Failed to update email body for job {job_id} in sheet {sheet}.")
#                         else:
#                             logging.warning(f"LLM did not generate an email body for job {job_id}.")
#                     except Exception as e:
#                         logging.error(f"Error generating or updating email for job {job.get('Job ID', 'unknown')}: {e}")
                
#                 return jsonify({
#                     "message": f"Generated and updated email bodies for {generated_count} jobs in '{sheet}' sheet.",
#                     "generated": generated_count,
#                     "mode": "direct_sheet_generation"
#                 })
#             except Exception as e:
#                 logging.error(f'Sheet generation error: {e}')
#                 return jsonify({'error': str(e)}), 500
#         else:
#             # Queue mode - delegate to bot
#             cmd = f'/sync_sheets'
#             if hasattr(db, 'enqueue_command'):
#                 cmd_id = db.enqueue_command(cmd)
#                 return jsonify({"message": "Sheet sync enqueued.", "command_id": cmd_id})
#             else:
#                 ok, resp = send_telegram_command(cmd)
#                 if ok:
#                     return jsonify({"message": "Sheet sync sent via Telegram.", "telegram_response": resp})
#                 else:
#                     return jsonify({"error": "Failed to sync sheets", "details": resp}), 500
                    
#     except Exception as e:
#         logging.exception('Failed to generate email bodies from sheet')
#         return jsonify({'error': str(e)}), 500


def _signal_handler(signum, frame):
    """On SIGTERM/SIGINT, attempt graceful shutdown by calling the shutdown endpoint."""
    try:
        # Determine the port the app is likely running on. The app.run() uses PORT env or 9501 by default.
        port = os.environ.get('PORT') or os.environ.get('FLASK_RUN_PORT') or os.environ.get('PORT', None)
        if not port:
            port = '8888'
        url = f"http://127.0.0.1:{port}/_shutdown"
        payload = {'token': ADMIN_USER_ID}
        try:
            requests.post(url, json=payload, timeout=2)
            return
        except Exception as e:
            logging.info(f"Signal handler couldn't hit shutdown endpoint ({url}): {e}; attempting direct exit.")
            # Best-effort: enqueue a stop command so bot processes can stop
            try:
                if hasattr(db, 'enqueue_command'):
                    db.enqueue_command('/stop')
            except Exception:
                pass
            # Force exit to ensure Ctrl+C stops the process completely
            try:
                os._exit(0)
            except Exception:
                pass
    except Exception as e:
        logging.error(f"Unexpected error in signal handler while shutting down: {e}")
        try:
            os._exit(0)
        except Exception:
            pass


# Register signal handlers for graceful shutdown
try:
    signal.signal(signal.SIGINT, _signal_handler)
    signal.signal(signal.SIGTERM, _signal_handler)
except Exception:
    # Some environments don't allow signal handling (e.g., Windows UN*); ignore
    logging.info('Signal handlers not registered (platform limitation).')

# --- HTML Page Routes ---

@app.route("/")
def index():
    return render_template("index.html")
from telethon.sessions import StringSession
from telethon import TelegramClient, errors
from flask import session

app.secret_key = os.getenv("FLASK_SECRET_KEY", "super-secret")

# In-memory store for Telegram client sessions during setup
telegram_clients = {}

@app.route("/api/telegram/setup", methods=["POST"])
def telegram_setup():
    from config import TELEGRAM_API_ID, TELEGRAM_API_HASH, TELEGRAM_PHONE
    
    api_id = TELEGRAM_API_ID
    api_hash = TELEGRAM_API_HASH
    phone = TELEGRAM_PHONE

    if not all([api_id, api_hash, phone]):
        return jsonify({"error": "TELEGRAM_API_ID, TELEGRAM_API_HASH, and TELEGRAM_PHONE must be set in the environment."}), 400

    try:
        client = TelegramClient(StringSession(), int(api_id), api_hash)
        
        async def do_send_code():
            await client.connect()
            result = await client.send_code_request(phone)
            return result.phone_code_hash

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        phone_code_hash = loop.run_until_complete(do_send_code())

        session["phone"] = phone
        session["phone_code_hash"] = phone_code_hash
        telegram_clients[phone] = client

        return jsonify({"message": "OTP code sent to your Telegram account."})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/telegram/signin", methods=["POST"])
def telegram_signin():
    data = request.json
    code = data.get("code")
    password = data.get("password")
    
    phone = session.get("phone")
    phone_code_hash = session.get("phone_code_hash")

    if not phone or not code:
        return jsonify({"error": "Session expired or code not provided. Please start over."}), 400

    client = telegram_clients.get(phone)
    if not client:
        return jsonify({"error": "No active setup process found for this phone number. Please start over."}), 400

    try:
        async def do_sign_in():
            await client.sign_in(phone, code, phone_code_hash=phone_code_hash)

        loop = asyncio.get_event_loop()
        
        try:
            loop.run_until_complete(do_sign_in())
        except errors.SessionPasswordNeededError:
            if not password:
                return jsonify({"error": "Two-factor authentication is enabled. Please provide a password."}), 400
            async def do_sign_in_with_password():
                await client.sign_in(password=password)
            loop.run_until_complete(do_sign_in_with_password())


        session_string = client.session.save()
        db.set_telegram_session(session_string)
        db.set_telegram_login_status('connected')

        # Clean up
        del telegram_clients[phone]
        session.pop("phone", None)
        session.pop("phone_code_hash", None)

        return jsonify({"message": "Successfully signed in! The application is now configured."})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/telegram/clear_session", methods=["POST"])
def api_clear_telegram_session():
    """Clear Telegram session from database"""
    try:
        db.set_telegram_session('')
        db.set_telegram_login_status('not_authenticated')
        return jsonify({"message": "Telegram session cleared successfully."})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/telegram/status")
def api_telegram_status():
    """Get detailed Telegram connection status"""
    try:
        status = {
            "login_status": db.get_telegram_login_status(),
            "session_exists": bool(db.get_telegram_session()),
            "authorized": db.get_telegram_login_status() == 'connected'
        }
        return jsonify(status)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/fetch_historical_messages", methods=["POST"])
def fetch_historical_messages():
    """Fetch historical messages from Telegram groups AND process them with duplicate removal"""
    try:
        data = request.get_json(force=True) or {}
        hours_back = data.get('hours_back', 12)  # Default to 12 hours
        
        if hours_back < 1 or hours_back > 48:
            return jsonify({"error": "hours_back must be between 1 and 48"}), 400
        
        # Import the historical message fetcher
        import sys
        import os
        sys.path.append(os.path.dirname(os.path.abspath(__file__)))
        
        from historical_message_fetcher import HistoricalMessageFetcher
        
        # Initialize fetcher
        if not all([TELEGRAM_API_ID, TELEGRAM_API_HASH, TELEGRAM_PHONE]):
            return jsonify({"error": "Telegram API credentials not configured"}), 500
        
        fetcher = HistoricalMessageFetcher(TELEGRAM_API_ID, TELEGRAM_API_HASH, TELEGRAM_PHONE, db)
        
        async def run_enhanced_fetch():
            try:
                # Connect to Telegram
                if await fetcher.connect_client():
                    logging.info("Connected to Telegram for enhanced historical message fetch")
                    
                    # Fetch, process, and deduplicate messages
                    result = await fetcher.fetch_and_process_historical_messages(hours_back)
                    
                    logging.info(f"Enhanced historical message process complete: {result}")
                    return result
                else:
                    logging.error("Failed to connect to Telegram for enhanced historical fetch")
                    return {
                        "fetched_count": 0,
                        "processed_count": 0,
                        "duplicates_found": 0,
                        "duplicates_removed": 0,
                        "status": "connection_failed"
                    }
            except Exception as e:
                logging.error(f"Error in enhanced historical fetch: {e}")
                return {
                    "fetched_count": 0,
                    "processed_count": 0,
                    "duplicates_found": 0,
                    "duplicates_removed": 0,
                    "status": "error",
                    "error": str(e)
                }
            finally:
                await fetcher.close()

        # Run the async function
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            result = loop.run_until_complete(run_enhanced_fetch())
        finally:
            loop.close()

        return jsonify(result)
        
    except Exception as e:
        logging.error(f"Failed to fetch historical messages: {e}")
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    # Create Flask application instance for Gunicorn
    application = app
    
    # Get port from environment
    port = int(os.environ.get("PORT", 9501))
    
    # Start the web server (always run, whether dev or production)
    try:
        logging.info(f"Starting web server on port {port}...")
        logging.info(f"Environment: {os.environ.get('FLASK_ENV', 'production')}")
        logging.info(f"Service Type: {os.environ.get('CONTAINER_TYPE', 'web')}")
        
        # Setup SSL context for HTTPS if enabled
        ssl_context = None
        if os.getenv('HTTPS_ENABLED', 'false').lower() == 'true':
            try:
                ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
                ssl_context.load_cert_chain(
                    os.getenv('SSL_CERT_PATH', '/etc/ssl/certs/telegram-bot.crt'),
                    os.getenv('SSL_KEY_PATH', '/etc/ssl/private/telegram-bot.key')
                )
                logging.info("HTTPS enabled - SSL context loaded")
            except Exception as e:
                logging.warning(f"Failed to setup SSL context: {e}")
                ssl_context = None
        
        logging.info(f"Access URL: http://localhost:{port}")
        logging.info(f"Health Check: http://localhost:{port}/health")
        logging.info(f"API Status: http://localhost:{port}/api/status")
        
        app.run(
            host="0.0.0.0", 
            port=port, 
            debug=os.getenv('FLASK_ENV', 'production') == 'development',
            ssl_context=ssl_context
        )
    except Exception as e:
        logging.error(f"Failed to start web server: {e}")
        raise