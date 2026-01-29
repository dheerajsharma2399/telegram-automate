import os
import logging
from logging.handlers import RotatingFileHandler
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
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters
from sheets_sync import GoogleSheetsSync
from config import OPENROUTER_API_KEY, OPENROUTER_MODEL, OPENROUTER_FALLBACK_MODEL, GOOGLE_CREDENTIALS_JSON, SPREADSHEET_ID, TELEGRAM_API_ID, TELEGRAM_API_HASH, TELEGRAM_PHONE

# --- Logging Setup ---
log_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'logs')
if not os.path.exists(log_dir):
    os.makedirs(log_dir)

log_file_path = os.path.join(log_dir, 'app.log')

log_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')

# Unified logger
log_handler = RotatingFileHandler(log_file_path, maxBytes=1024*1024, backupCount=5)
log_handler.setFormatter(log_formatter)

werkzeug_logger = logging.getLogger('werkzeug') # Gunicorn/Flask's internal logger
werkzeug_logger.addHandler(log_handler)
werkzeug_logger.setLevel(logging.INFO)

app_logger = logging.getLogger(__name__)
app_logger.addHandler(log_handler)
app_logger.setLevel(logging.INFO)

# Also configure the root logger to capture more logs
root_logger = logging.getLogger()
root_logger.addHandler(log_handler)
root_logger.setLevel(logging.INFO)

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

# Global Application instance for this web worker to handle webhooks
_webhook_app_instance = None

async def dummy_handler(update, context):
    """Dummy handler that does nothing and is awaitable."""
    pass

async def _get_or_create_webhook_application():
    """
    Lazily initializes and returns the telegram.ext.Application instance for this worker.
    This ensures it's created once per Gunicorn worker.
    """
    global _webhook_app_instance
    if _webhook_app_instance is None:
        if not TELEGRAM_BOT_TOKEN:
            logging.error("TELEGRAM_BOT_TOKEN not configured - cannot initialize webhook Application.")
            return None
        
        _webhook_app_instance = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
        # Add handlers that mirror those in main.py's setup_webhook_bot to ensure updates are processed correctly.
        # These handlers will typically be dummy handlers as the actual bot logic runs in main.py.
        _webhook_app_instance.add_handler(MessageHandler(filters.ALL, dummy_handler), group=-1)
        _webhook_app_instance.add_handler(CommandHandler("start", dummy_handler))
        _webhook_app_instance.add_handler(CommandHandler("stop", dummy_handler))
        _webhook_app_instance.add_handler(CommandHandler("status", dummy_handler))
        _webhook_app_instance.add_handler(CommandHandler("process", dummy_handler))
        _webhook_app_instance.add_handler(CommandHandler("stats", dummy_handler))
        _webhook_app_instance.add_handler(CommandHandler("export", dummy_handler))
        _webhook_app_instance.add_handler(CommandHandler("sync_sheets", dummy_handler))
        _webhook_app_instance.add_handler(CallbackQueryHandler(dummy_handler))
        _webhook_app_instance.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, dummy_handler))

        await _webhook_app_instance.initialize()
        logging.info("Webhook Application initialized for this web worker.")
    return _webhook_app_instance

def get_sheets_sync():
    global sheets_sync
    if sheets_sync is None and GOOGLE_CREDENTIALS_JSON and SPREADSHEET_ID:
        try:
            sheets_sync = GoogleSheetsSync(GOOGLE_CREDENTIALS_JSON, SPREADSHEET_ID)
        except Exception:
            pass
    return sheets_sync

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

def read_log_file(log_file, lines=1000):
    """Reads the last N lines of a log file."""
    try:
        with open(log_file, "r") as f:
            if lines == -1: # Read all lines
                return "".join(f.readlines())
            else:
                file_lines = f.readlines()[-lines:]
                return "".join(file_lines)
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
            "monitoring_status": db.config.get_config("monitoring_status"),
            "unprocessed_count": db.messages.get_unprocessed_count(),
            "jobs_today": db.jobs.get_jobs_today_stats(),
            "telegram_status": db.auth.get_telegram_login_status(),
            "telegram_session_exists": bool(db.auth.get_telegram_session()),
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
        pending = db.commands.list_all_pending_commands()
        return jsonify(pending)
    except Exception as e:
        logging.exception('Failed to fetch pending commands')
        return jsonify({'error': str(e)}), 500


@app.route('/api/command/<int:cmd_id>/cancel', methods=['POST'])
def api_cancel_command(cmd_id):
    try:
        ok = False
        if hasattr(db.commands, 'cancel_command'):
            ok = db.commands.cancel_command(cmd_id)
        if not ok:
            return jsonify({'error': 'Command not found or could not be cancelled'}), 404
        return jsonify({'message': 'Command cancelled'})
    except Exception as e:
        logging.exception('Failed to cancel command')
        return jsonify({'error': str(e)}), 500


@app.route('/api/monitored_groups', methods=['GET'])
def api_get_monitored_groups():
    try:
        val = db.config.get_config('monitored_groups') or ''
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
        current = db.config.get_config('monitored_groups') or ''
        groups = [s for s in current.split(',') if s]
        if group in groups:
            return jsonify({'message': 'already present', 'groups': groups})
        groups.append(group)
        db.config.set_config('monitored_groups', ','.join(groups))
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
        current = db.config.get_config('monitored_groups') or ''
        groups = [s for s in current.split(',') if s]
        if group not in groups:
            return jsonify({'error': 'not found', 'groups': groups}), 404
        groups = [g for g in groups if g != group]
        db.config.set_config('monitored_groups', ','.join(groups))
        return jsonify({'message': 'removed', 'groups': groups})
    except Exception as e:
        logging.exception('Failed to remove monitored group')
        return jsonify({'error': str(e)}), 500

@app.route("/api/queue")
def api_queue():
    """API endpoint to get the unprocessed message queue."""
    try:
        queue = db.messages.get_unprocessed_messages(limit=100)
        return jsonify(queue)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/logs")
def api_logs():
    """API endpoint to get logs."""
    lines = request.args.get('lines', 1000, type=int)
    app_logger.info(f"API logs endpoint was hit! Fetching last {lines} lines.")
    try:
        logs = {
            "app_logs": read_log_file(log_file_path, lines=lines),
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
        if hasattr(db.commands, 'enqueue_command') and callable(getattr(db.commands, 'enqueue_command')):
            cmd_id = db.commands.enqueue_command(command)
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
            jobs = db.jobs.get_relevant_jobs(has_email=True)
        elif has_email == 'false':
            jobs = db.jobs.get_relevant_jobs(has_email=False)
        else:
            jobs = db.jobs.get_relevant_jobs()
        
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
            jobs = db.jobs.get_irrelevant_jobs(has_email=True)
        elif has_email == 'false':
            jobs = db.jobs.get_irrelevant_jobs(has_email=False)
        else:
            jobs = db.jobs.get_irrelevant_jobs()
        
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
        with db.get_connection() as conn:
            with conn.cursor() as cursor:
                # Use COUNT for efficiency
                query = """
                    SELECT
                        COUNT(*) FILTER (WHERE job_relevance = 'relevant' AND email IS NOT NULL AND email != '') as relevant_with_email,
                        COUNT(*) FILTER (WHERE job_relevance = 'relevant' AND (email IS NULL OR email = '')) as relevant_without_email,
                        COUNT(*) FILTER (WHERE job_relevance = 'irrelevant' AND email IS NOT NULL AND email != '') as irrelevant_with_email,
                        COUNT(*) FILTER (WHERE job_relevance = 'irrelevant' AND (email IS NULL OR email = '')) as irrelevant_without_email
                    FROM processed_jobs
                """
                cursor.execute(query)
                stats = cursor.fetchone()

        relevant_total = stats['relevant_with_email'] + stats['relevant_without_email']
        irrelevant_total = stats['irrelevant_with_email'] + stats['irrelevant_without_email']

        return jsonify({
            "relevant": {"total": relevant_total, "with_email": stats['relevant_with_email'], "without_email": stats['relevant_without_email']},
            "irrelevant": {"total": irrelevant_total, "with_email": stats['irrelevant_with_email'], "without_email": stats['irrelevant_without_email']},
            "total_jobs": relevant_total + irrelevant_total
        })
    except Exception as e:
        logging.error(f"Failed to fetch job stats: {e}")
        return jsonify({"error": str(e)}), 500

@app.route("/api/jobs")
def api_jobs():
    """API endpoint to get all processed jobs that are not hidden."""
    try:
        jobs = db.jobs.get_jobs_by_sheet_name('non-email')
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
        
        rows_affected = db.jobs.hide_jobs(job_ids)
        return jsonify({"message": f"{rows_affected} jobs hidden successfully."})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/sheets/advanced_sync", methods=["POST"])
def api_advanced_sheets_sync():
    """Advanced sync: Sync jobs from past N days, skipping existing ones in sheets."""
    try:
        data = request.get_json(force=True) or {}
        days = int(data.get('days', 7))
        
        sheets_sync = get_sheets_sync()
        if not (sheets_sync and sheets_sync.client):
            return jsonify({"error": "Google Sheets not configured"}), 500

        # 1. Fetch jobs from DB
        jobs = db.jobs.get_jobs_created_since(days)
        if not jobs:
            return jsonify({"message": "No jobs found in the specified period", "synced_count": 0})

        # 2. Pre-fetch existing IDs from sheets to minimize API calls during check
        existing_ids = {}
        for s_name in ['email', 'non-email', 'email-exp', 'non-email-exp']:
            existing_ids[s_name] = sheets_sync.get_all_job_ids(s_name)

        synced_count = 0
        skipped_count = 0
        
        for job in jobs:
            # Determine target sheet name logic
            sheet_name = job.get('sheet_name')
            if not sheet_name:
                job_relevance = job.get('job_relevance', 'relevant')
                has_email = bool(job.get('email'))
                if job_relevance == 'relevant':
                    sheet_name = 'email' if has_email else 'non-email'
                else:
                    sheet_name = 'email-exp' if has_email else 'non-email-exp'
            
            # Check if exists in the target sheet
            if sheet_name in existing_ids and job.get('job_id') in existing_ids[sheet_name]:
                skipped_count += 1
                if not job.get('synced_to_sheets'):
                    db.jobs.mark_job_synced(job.get('job_id'))
                continue
            
            #   # Mark as unsynced so background task picks it up
                with db.get_connection() as conn:
                    with conn.cursor() as cursor:
                        cursor.execute("UPDATE processed_jobs SET synced_to_sheets = FALSE, sheet_name = %s WHERE job_id = %s", 
                                     (sheet_name, job.get('job_id')))
                    conn.commit()
                synced_count += 1 # Count as "queued for sync"
            else:
                # Small batch, sync immediately
                if not job.get('sheet_name'):
                    job['sheet_name'] = sheet_name
                    
                if sheets_sync.sync_job(job):
                    db.jobs.mark_job_synced(job.get('job_id'))
                    if sheet_name in existing_ids:
                        existing_ids[sheet_name].add(job.get('job_id'))
                    synced_count += 1
                
        return jsonify({a
 })    except Exception as e:
        logging.error(f"Advanced sync failed: {e}")
        return jsonify(
# ===============================================
# DASHBOARD JOBS API ENDPOINTS (NEW)
# ===============================================

@app.route("/api/dashboard/jobs", methods=["GET"])
def get_dashboard_jobs():
    """Get all dashboard jobs with optional filtering"""
    try:
        status_filter = request.args.get('status')
        relevance_filter = request.args.get('relevance')
        job_role_filter = request.args.get('job_role')
        page = request.args.get('page', 1, type=int)
        page_size = request.args.get('page_size', 50, type=int)
        include_archived = request.args.get('include_archived', 'false').lower() == 'true'
        sort_by = request.args.get('sort_by', 'created_at')
        sort_order = request.args.get('sort_order', 'DESC')
        
        # Correctly call the repository method
        result = db.dashboard.get_dashboard_jobs(
            status_filter=status_filter,
            relevance_filter=relevance_filter,
            job_role_filter=job_role_filter,
            include_archived=include_archived,
            page=page,
            page_size=page_size,
            sort_by=sort_by,
            sort_order=sort_order
        )
        
        return jsonify(result)
    except Exception as e:
        logging.error(f"Failed to fetch dashboard jobs: {e}")
        return jsonify({"error": str(e)}), 500

@app.route("/api/dashboard/jobs/archive_older_than", methods=["POST"])
def archive_jobs_older_than():
    """Archive jobs older than N days"""
    try:
        data = request.get_json(force=True) or {}
        days = data.get('days')
        
        if days is None:
            return jsonify({"error": "days parameter is required"}), 400
            
        try:
            days = int(days)
            if days < 0:
                raise ValueError
        except ValueError:
            return jsonify({"error": "days must be a non-negative integer"}), 400
            
        archived_count = db.dashboard.archive_jobs_older_than(days)
        
        return jsonify({
            "message": f"Archived {archived_count} jobs older than {days} days",
            "archived_count": archived_count
        })
        
    except Exception as e:
        logging.error(f"Failed to archive old jobs: {e}")
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
        
        job_id = db.dashboard.add_dashboard_job(data)
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
        archive = data.get('archive', False)
        
        if not status:
            return jsonify({"error": "Status is required"}), 400
        
        valid_statuses = ['not_applied', 'applied', 'interview', 'rejected', 'offer', 'archived']
        if status not in valid_statuses:
            return jsonify({"error": f"Invalid status. Must be one of: {valid_statuses}"}), 400
        
        # Use bulk_update_status for consistency, treating a single update as a bulk update of one
        updated_count = db.dashboard.bulk_update_status([job_id], status, application_date, archive=archive)

        if updated_count > 0:
            return jsonify({"message": f"Job status updated to {status}"})
        else:
            return jsonify({"error": "Job not found or failed to update"}), 404
            
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
        
        success = db.dashboard.add_job_notes(job_id, notes)
        if success:
            return jsonify({"message": "Notes added successfully"})
        else:
            return jsonify({"error": "Job not found"}), 404
            
    except Exception as e:
        logging.error(f"Failed to add notes to job: {e}")
        return jsonify({"error": str(e)}), 500

@app.route("/api/dashboard/jobs/bulk_update", methods=["POST"])
def bulk_update_status():
    """Update status for multiple jobs"""
    try:
        data = request.get_json(force=True) or {}
        job_ids = data.get('job_ids', [])
        status = data.get('status')
        application_date = data.get('application_date')
        archive = data.get('archive', False)

        # Convert job_ids from string to int to prevent SQL type errors
        try:
            job_ids = [int(job_id) for job_id in job_ids]
        except (ValueError, TypeError):
            return jsonify({"error": "job_ids must be a list of valid integers"}), 400

        if not job_ids or not isinstance(job_ids, list):
            return jsonify({"error": "job_ids must be a non-empty list"}), 400
        
        if not status:
            return jsonify({"error": "status is required"}), 400
        
        valid_statuses = ['not_applied', 'applied', 'interview', 'rejected', 'offer', 'archived']
        if status not in valid_statuses:
            return jsonify({"error": f"Invalid status. Must be one of: {valid_statuses}"}), 400
        
        updated_count = db.dashboard.bulk_update_status(job_ids, status, application_date, archive=archive)
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
        
        imported_count = db.dashboard.import_jobs_from_processed(sheet_name, max_jobs)
        
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
        
        success = db.dashboard.mark_as_duplicate(job_id, duplicate_of_id, confidence_score)
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
        detected_count = db.dashboard.detect_duplicate_jobs()
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
        export_data = db.dashboard.export_dashboard_jobs(format_type)
        
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
        with db.get_connection() as conn:
            with conn.cursor() as cursor:
                # Total jobs
                cursor.execute("SELECT COUNT(*) as total FROM dashboard_jobs WHERE is_hidden = FALSE")
                total_jobs = cursor.fetchone()['total']

                # By status
                cursor.execute("""
                    SELECT application_status, COUNT(*) as count
                    FROM dashboard_jobs WHERE is_hidden = FALSE
                    GROUP BY application_status
                """)
                by_status = {row['application_status']: row['count'] for row in cursor.fetchall()}

                # By relevance
                cursor.execute("""
                    SELECT job_relevance, COUNT(*) as count
                    FROM dashboard_jobs WHERE is_hidden = FALSE
                    GROUP BY job_relevance
                """)
                by_relevance = {row['job_relevance']: row['count'] for row in cursor.fetchall()}

        return jsonify({
            "total_jobs": total_jobs,
            "by_status": by_status,
            "by_relevance": by_relevance,
        })
        
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
        # Get the Application instance for this worker
        bot_application = await _get_or_create_webhook_application()
        if bot_application is None:
            logging.error("Failed to get webhook Application instance.")
            return False
        
        # _get_or_create_webhook_application already initializes it.
        # No need for an additional initialize() call here.
        
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
webhook_logger.addHandler(log_handler) # Use the unified log_handler


@app.route("/webhook", methods=["POST"])
def telegram_webhook():
    """Handle incoming Telegram webhook updates"""
    webhook_logger.info("--- WEBHOOK ENDPOINT HIT ---")
    try:
        webhook_logger.info(f"Request Headers: {request.headers}")
        raw_body = request.get_data(as_text=True)
        webhook_logger.info(f"Raw Request Body: {raw_body}")
        
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
    # This endpoint needs to set the webhook for the *main bot's* Application instance.
    # If main.py is running as a separate worker, it should be responsible for setting its own webhook.
    # For now, let's create a temporary Application instance to set the webhook.
    if not TELEGRAM_BOT_TOKEN:
        return jsonify({"error": "TELEGRAM_BOT_TOKEN not configured"}), 500

    try:
        data = request.get_json(force=True) or {}
        webhook_url = data.get('webhook_url')
        
        if not webhook_url:
            service_url = os.getenv('RENDER_SERVICE_URL') or os.getenv('SERVICE_URL') or os.getenv('DEPLOYMENT_URL')
            if service_url:
                webhook_url = f"{service_url}/webhook"
            else:
                return jsonify({"error": "No webhook URL provided and unable to construct it"}), 400
        
        temp_app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
        async def do_set_webhook():
            await temp_app.bot.set_webhook(
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
    if not TELEGRAM_BOT_TOKEN:
        return jsonify({"error": "TELEGRAM_BOT_TOKEN not configured"}), 500

    try:
        # Create a temporary Application instance just for deleting webhook
        temp_app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
        async def do_delete_webhook():
            await temp_app.bot.delete_webhook()

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(do_delete_webhook())

        logging.info("Webhook removed")
        return jsonify({"message": "Webhook removed successfully"})
        
    except Exception as e:
        logging.error(f"Failed to remove webhook: {e}")
        return jsonify({"error": str(e)}), 500

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
        db.auth.set_telegram_session(session_string)
        db.auth.set_telegram_login_status('connected')

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
        db.auth.set_telegram_session('')
        db.auth.set_telegram_login_status('not_authenticated')
        return jsonify({"message": "Telegram session cleared successfully."})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/telegram/status")
def api_telegram_status():
    """Get detailed Telegram connection status"""
    try:
        status = {
            "login_status": db.auth.get_telegram_login_status(),
            "session_exists": bool(db.auth.get_telegram_session()),
            "authorized": db.auth.get_telegram_login_status() == 'connected'
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
        
        if hours_back < 1 or hours_back > 168:
            return jsonify({"error": "hours_back must be between 1 and 168"}), 400
        
        # Import the historical message fetcher
        import sys
        import os
        sys.path.append(os.path.dirname(os.path.abspath(__file__)))
        
        from historical_message_fetcher import HistoricalMessageFetcher
        
        # Initialize fetcher
        if not all([TELEGRAM_API_ID, TELEGRAM_API_HASH, TELEGRAM_PHONE]):
            return jsonify({"error": "Telegram API credentials not configured"}), 500
        
        async def run_enhanced_fetch():
            client = None
            try:
                # Create a temporary client for this operation
                session_string = db.auth.get_telegram_session()
                if not session_string:
                    raise ConnectionError("No active Telegram session found. Please authenticate first.")
                
                client = TelegramClient(StringSession(session_string), int(TELEGRAM_API_ID), TELEGRAM_API_HASH)
                await client.connect()
                if not await client.is_user_authorized():
                    raise ConnectionError("Telegram session is invalid or expired.")

                fetcher = HistoricalMessageFetcher(db, client)
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
                if client and client.is_connected():
                    await client.disconnect()

        # Run the async function
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            result = loop.run_until_complete(run_enhanced_fetch())
            # Ensure hours_back is always in the result for the frontend
            result['hours_back'] = hours_back
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