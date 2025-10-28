import os
import logging
from flask import Flask, render_template, jsonify, request
import requests
from database import Database
from dotenv import load_dotenv

load_dotenv()

from config import TELEGRAM_BOT_TOKEN, ADMIN_USER_ID

app = Flask(__name__)
db = Database(os.getenv("DATABASE_PATH", "jobs.db"))

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
    
    success, response = send_telegram_command(command)
    if success:
        return jsonify({"message": f"Command '{command}' sent successfully.", "response": response})
    else:
        return jsonify({"error": f"Failed to send command '{command}'.", "details": response}), 500

# --- HTML Page Routes ---

@app.route("/")
def index():
    return render_template("index.html")

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))