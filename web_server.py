import os
import logging
from logging.handlers import RotatingFileHandler
import asyncio
import ssl
import functools
from flask import Flask, render_template, jsonify, request
import requests
from database import Database
from dotenv import load_dotenv
from auth_utils import require_api_key

load_dotenv()

from config import ADMIN_USER_ID, DATABASE_URL
import signal
import socket
import threading
import tempfile
import json
from urllib.parse import urljoin
from llm_processor import LLMProcessor
from sheets_sync import GoogleSheetsSync
from config import (
    OPENROUTER_API_KEY, OPENROUTER_API_KEYS, OPENROUTER_MODEL, OPENROUTER_MODELS,
    OPENROUTER_FALLBACK_MODEL, OPENROUTER_FALLBACK_MODELS,
    GOOGLE_CREDENTIALS_JSON, SPREADSHEET_ID, TELEGRAM_API_ID, TELEGRAM_API_HASH,
    TELEGRAM_PHONE, ADDITIONAL_SPREADSHEET_IDS
)
from sheets_sync import MultiSheetSync

# Initialize Flask app
app = Flask(__name__)

# Initialize database and LLM processor at module level
# This ensures they're available when Gunicorn imports the module
db = Database(DATABASE_URL) if DATABASE_URL else None
llm_processor = LLMProcessor(OPENROUTER_API_KEYS, OPENROUTER_MODELS, OPENROUTER_FALLBACK_MODELS) if OPENROUTER_API_KEYS else None
sheets_sync = None
_sheets_lock = threading.Lock()

def get_sheets_sync():
    global sheets_sync
    if sheets_sync is None and GOOGLE_CREDENTIALS_JSON and SPREADSHEET_ID:
        with _sheets_lock:
            if sheets_sync is None:  # Double-checked locking
                try:
                    # Use MultiSheetSync to support additional sheets
                    sheets_sync = MultiSheetSync(GOOGLE_CREDENTIALS_JSON, SPREADSHEET_ID, ADDITIONAL_SPREADSHEET_IDS)
                except Exception as e:
                    logging.error(f"Failed to initialize Sheets Sync: {e}")
    return sheets_sync

# Set config for apply routes (after db and get_sheets_sync are defined)
app.config["DB"] = db
app.config["GET_SHEETS_SYNC"] = get_sheets_sync

# Register Apply blueprint if available
try:
    from apply_routes import apply_bp
    app.register_blueprint(apply_bp, url_prefix='/apply')
except ImportError:
    logging.warning("apply_routes not available")

# --- Helper Functions ---

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
