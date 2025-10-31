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
import json
from urllib.parse import urljoin
from llm_processor import LLMProcessor
from sheets_sync import GoogleSheetsSync
from config import OPENROUTER_API_KEY, OPENROUTER_MODEL, OPENROUTER_FALLBACK_MODEL, GOOGLE_CREDENTIALS_JSON, SPREADSHEET_ID

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

def setup_bot_webhook():
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
        bot_application = main.setup_webhook_bot()
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
        setup_bot_webhook()
        # Auto-setup webhook URL if bot was successfully loaded
        if bot_application:
            def auto_setup_webhook():
                """Auto-setup webhook after web server starts"""
                import time
                time.sleep(5)  # Wait for server to start
                try:
                    # Get webhook URL from service URL
                    service_url = os.getenv('RENDER_SERVICE_URL') or os.getenv('SERVICE_URL') or os.getenv('DEPLOYMENT_URL')
                    if service_url:
                        webhook_url = f"{service_url}/webhook"
                        logging.info(f"Attempting to set webhook to: {webhook_url}")
                        
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
                        logging.warning("Could not determine service URL for webhook setup. Please set it manually via the API.")
                except Exception as e:
                    logging.warning(f"Auto webhook setup failed: {e}")
            
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


# --- Telegram Webhook Endpoint ---

def process_webhook_async(update_data):
    """Process webhook update in separate thread"""
    try:
        if not bot_application:
            logging.error("Bot application not available for webhook")
            return False
        
        from telegram import Update
        update = Update.de_json(update_data, bot_application.bot)
        
        # Create new event loop for this thread
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        try:
            loop.run_until_complete(bot_application.process_update(update))
            logging.info(f"Processed webhook update: {update.update_id}")
            return True
        finally:
            loop.close()
            
    except Exception as e:
        logging.error(f"Error processing webhook: {e}")
        return False

@app.route("/webhook", methods=["POST"])
def telegram_webhook():
    """Handle incoming Telegram webhook updates"""
    try:
        # Check if bot application is available
        if not bot_application:
            logging.error("Bot application not available for webhook")
            return jsonify({"error": "Bot not initialized"}), 500
        
        # Get the update data
        update_data = request.get_json(force=True)
        logging.info(f"Received webhook update: {update_data}")
        if not update_data:
            return jsonify({"error": "No update data"}), 400
        
        # Process the update in a separate thread
        import threading
        thread = threading.Thread(target=process_webhook_async, args=(update_data,))
        thread.start()
        
        # Don't wait for completion - return immediately
        logging.info(f"Webhook update queued for processing: {update_data.get('update_id', 'unknown')}")
        return jsonify({"status": "queued"})
            
    except Exception as e:
        logging.error(f"Error processing webhook: {e}")
        return jsonify({"error": str(e)}), 500

@app.route("/api/setup_webhook", methods=["POST"])
def setup_webhook():
    """Setup webhook URL for the bot"""
    try:
        if not bot_application:
            return jsonify({"error": "Bot application not available"}), 500
        
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

@app.route('/api/generate_emails', methods=['POST'])
def api_generate_emails():
    """Generate enhanced email bodies for processed jobs.
    
    This endpoint supports:
    1. Direct generation when running as standalone service
    2. Command queuing when running as dashboard-only service
    
    If LLM processor is available, generates enhanced job-specific emails.
    If not available, enqueues command for bot service to handle.
    """
    try:
        payload = request.get_json(force=True) or {}
        job_ids = payload.get('job_ids')
        run_now = payload.get('run_now', False)

        # Case 1: Direct generation (standalone mode)
        if llm_processor and run_now:
            # FIXED: Direct email generation ONLY for email sheet jobs without email_body
            email_jobs_without_emails = db.get_email_jobs_needing_generation()
            if not email_jobs_without_emails:
                return jsonify({"message": "No jobs found in the 'email' sheet that need email body generation.", "generated": 0})
            
            generated = 0
            for job in email_jobs_without_emails:
                try:
                    # Use enhanced email generation with job-specific content
                    email_body = llm_processor.generate_email_body(job, job.get('jd_text', ''))
                    if email_body:
                        db.update_job_email_body(job['job_id'], email_body)
                        generated += 1
                except Exception as e:
                    logging.error(f"Failed to generate email for job {job.get('job_id')}: {e}")
            
            return jsonify({
                "message": f"Generated {generated} email bodies for 'email' sheet jobs.",
                "generated": generated,
                "mode": "direct_generation"
            })
        
        # Case 2: Command queuing (service separation mode)
        else:
            # enqueue the command for the bot poller to execute
            cmd = '/generate_emails'
            if job_ids:
                cmd = f"/generate_emails {','.join(map(str, job_ids))}"

            if hasattr(db, 'enqueue_command') and callable(getattr(db, 'enqueue_command')):
                cmd_id = db.enqueue_command(cmd)
                return jsonify({
                    "message": "Email generation enqueued.",
                    "command_id": cmd_id,
                    "mode": "command_queue"
                })
            else:
                ok, resp = send_telegram_command(cmd)
                if ok:
                    return jsonify({
                        "message": "Email generation sent via Telegram fallback.",
                        "telegram_response": resp,
                        "mode": "telegram_fallback"
                    })
                else:
                    return jsonify({"error": "Failed to enqueue generation and Telegram fallback failed.", "details": resp}), 500
                    
    except Exception as e:
        logging.exception('Failed to generate emails')
        return jsonify({'error': str(e)}), 500

@app.route('/api/sheets/generate_email_bodies', methods=['POST'])
def api_sheets_generate_email_bodies():
    """Generate email bodies from Google Sheets data.
    
    This endpoint can generate emails directly if LLM processor is available,
    or delegate to the bot service if not.
    """
    try:
        payload = request.get_json(force=True) or {}
        sheet = payload.get('sheet', 'email')
        limit = payload.get('limit', 50)
        
        sheets_sync = get_sheets_sync()
        if not sheets_sync:
            return jsonify({'error': 'Google Sheets not configured'}), 500
        
        if llm_processor:
            # Direct generation mode - generate emails for sheet data
            try:
                # This would need to be implemented based on your sheets_sync capabilities
                return jsonify({
                    'message': 'Direct sheet-based email generation not fully implemented',
                    'recommendation': 'Use the /generate_emails command for now'
                })
            except Exception as e:
                logging.error(f'Sheet generation error: {e}')
                return jsonify({'error': str(e)}), 500
        else:
            # Queue mode - delegate to bot
            cmd = f'/sync_sheets'
            if hasattr(db, 'enqueue_command'):
                cmd_id = db.enqueue_command(cmd)
                return jsonify({"message": "Sheet sync enqueued.", "command_id": cmd_id})
            else:
                ok, resp = send_telegram_command(cmd)
                if ok:
                    return jsonify({"message": "Sheet sync sent via Telegram.", "telegram_response": resp})
                else:
                    return jsonify({"error": "Failed to sync sheets", "details": resp}), 500
                    
    except Exception as e:
        logging.exception('Failed to generate email bodies from sheet')
        return jsonify({'error': str(e)}), 500


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