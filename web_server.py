import os
import logging
from flask import Flask, render_template, jsonify, request
import requests
from database import Database
from dotenv import load_dotenv

load_dotenv()

from config import TELEGRAM_BOT_TOKEN, ADMIN_USER_ID
import signal
import socket
import threading
import json
from urllib.parse import urljoin
from llm_processor import LLMProcessor
from sheets_sync import GoogleSheetsSync
from config import OPENROUTER_API_KEY, OPENROUTER_MODEL, OPENROUTER_FALLBACK_MODEL, GOOGLE_CREDENTIALS_JSON, SPREADSHEET_ID

app = Flask(__name__)
db = Database(os.getenv("DATABASE_PATH", "jobs.db"))

# LLM processor and sheets sync available to web endpoints (optional)
llm_processor = None
try:
    llm_processor = LLMProcessor(OPENROUTER_API_KEY, OPENROUTER_MODEL, OPENROUTER_FALLBACK_MODEL)
except Exception:
    llm_processor = None

sheets_sync = None
try:
    if GOOGLE_CREDENTIALS_JSON and SPREADSHEET_ID:
        sheets_sync = GoogleSheetsSync(GOOGLE_CREDENTIALS_JSON, SPREADSHEET_ID)
except Exception:
    sheets_sync = None

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
    # Check if port 5000 is accepting connections (localhost)
    try:
        with socket.create_connection(("127.0.0.1", 5000), timeout=1):
            status['http_port_5000'] = 'listening'
    except Exception:
        status['http_port_5000'] = 'not_listening'
    return jsonify(status)


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
        }
        return jsonify(status)
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


@app.route('/api/sheets/generate_email_bodies', methods=['POST'])
def api_sheets_generate_email_bodies():
    """Trigger generation of email bodies by reading JD Text from the main sheet and writing back email_body."""
    try:
        if not llm_processor:
            return jsonify({'error': 'LLM processor not configured on server'}), 500

        payload = request.get_json(force=True) or {}
        sheet = payload.get('sheet', 'email')
        limit = payload.get('limit')

        summary = sheets_sync.generate_email_bodies_from_sheet(llm_processor, db=db, sheet_name=sheet, limit=limit)
        return jsonify({'message': 'Sheet generation complete', 'summary': summary})
    except Exception as e:
        logging.exception('Failed to trigger sheets email generation')
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


@app.route('/api/generate_emails', methods=['POST'])
def api_generate_emails():
    """Trigger server-side generation of email bodies for processed jobs (enqueue a bot command).
    This will enqueue a /generate_emails command which the bot will pick up and run.
    """
    try:
        # Optionally accept a list of job_ids to target; for now we trigger general generation
        payload = request.get_json(force=True) or {}
        job_ids = payload.get('job_ids')
        run_now = bool(payload.get('run_now'))

        # If run_now requested, attempt synchronous generation on the server
        if run_now:
            if llm_processor is None:
                return jsonify({'error': 'LLM processor not configured on server'}), 500

            # Determine target jobs
            try:
                if job_ids:
                    # fetch specified jobs
                    with db.get_connection() as conn:
                        cur = conn.cursor()
                        q = f"SELECT * FROM processed_jobs WHERE job_id IN ({','.join(['?']*len(job_ids))})"
                        cur.execute(q, job_ids)
                        jobs = [dict(r) for r in cur.fetchall()]
                else:
                    jobs = db.get_unsynced_jobs()

                if not jobs:
                    return jsonify({'message': 'No jobs found to generate emails for.'})

                generated = 0
                for job in jobs:
                    try:
                        jd = job.get('jd_text') or ''
                        email_body = None
                        try:
                            email_body = llm_processor.generate_email_body(job, jd)
                        except Exception:
                            email_body = None

                        if email_body:
                            db.update_job_email_body(job['job_id'], email_body)
                            generated += 1
                            # Optionally sync immediately to sheets
                            try:
                                if sheets_sync and sheets_sync.client:
                                    sheets_sync.sync_job({**job, 'email_body': email_body})
                                    db.mark_job_synced(job['job_id'])
                            except Exception:
                                pass

                    except Exception as e:
                        logging.exception(f"Failed to generate email for job {job.get('job_id')}: {e}")

                return jsonify({'message': f'Generated email bodies for {generated} jobs.'})
            except Exception as e:
                logging.exception('Synchronous generation failed')
                return jsonify({'error': str(e)}), 500

        # Otherwise enqueue the command for the bot poller to execute
        cmd = '/generate_emails'
        if job_ids:
            cmd = f"/generate_emails {','.join(job_ids)}"

        if hasattr(db, 'enqueue_command') and callable(getattr(db, 'enqueue_command')):
            cmd_id = db.enqueue_command(cmd)
            return jsonify({"message": "Email generation enqueued.", "command_id": cmd_id})
        else:
            ok, resp = send_telegram_command(cmd)
            if ok:
                return jsonify({"message": "Email generation sent via Telegram fallback.", "telegram_response": resp})
            else:
                return jsonify({"error": "Failed to enqueue generation and Telegram fallback failed.", "details": resp}), 500
    except Exception as e:
        logging.exception('Failed to enqueue generate_emails')
        return jsonify({'error': str(e)}), 500


def _signal_handler(signum, frame):
    """On SIGTERM/SIGINT, attempt graceful shutdown by calling the shutdown endpoint."""
    try:
        # Determine the port the app is likely running on. The app.run() uses PORT env or 8080 by default.
        port = os.environ.get('PORT') or os.environ.get('FLASK_RUN_PORT') or os.environ.get('PORT', None)
        if not port:
            port = '8080'
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

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))