# Project Architecture

## Overview
This is a **Telegram Job Scraper & Automation System**. It monitors Telegram channels/groups for job postings, parses them using LLMs (via OpenRouter), stores them in a PostgreSQL (Supabase or self-hosted) database, syncs to Google Sheets, and provides a Flask web dashboard for full management.

**Owner**: Dheeraj Sharma  
**Live URL**: https://job.mooh.me  
**Repo**: https://github.com/dheerajsharma2399/telegram-automate

---

## Tech Stack

| Layer | Technology |
|---|---|
| Language | Python 3.11 |
| Web Framework | Flask (Gunicorn in production) |
| Telegram Client | Telethon (async, **user-account mode** — NOT bot token) |
| Database | PostgreSQL via `psycopg2` (ThreadedConnectionPool + RealDictCursor) |
| LLM | OpenRouter API (primary + fallback model pools, regex fallback) |
| Scheduling | APScheduler (`AsyncIOScheduler`) |
| Sheets | gspread + google-auth-oauthlib |
| Process Manager | honcho (Procfile) |
| Deployment | Docker + Dokploy + Traefik on VPS |

---

## Two-Process Architecture

```
Procfile:
  web:    gunicorn web_server:app   (port 9501)   ← Flask dashboard + REST API
  worker: python main.py                           ← Telegram polling + job processing
```

The two processes share **only the PostgreSQL database** for state and IPC.
- `commands_queue` table: web → worker command delivery
- `bot_config` table: shared runtime state (monitoring_status, etc.)
- `telegram_auth` table: Telethon session (set via web UI, used by worker)

**Never merge these two processes.** Telethon's async event loop and Gunicorn's sync workers are incompatible in the same process.

---

## Core Components

### 1. Web Server (`web_server.py`)
- Flask application serving the dashboard and all REST API endpoints.
- Handles Telegram OTP auth flow (stores session string to DB).
- Enqueues commands for the worker via `commands_queue` table.
- Initializes `Database`, `LLMProcessor`, and `MultiSheetSync` at module level (for Gunicorn).

### 2. Worker / Main (`main.py`)
- Entry point for the background worker process.
- Starts `APScheduler` with 3 jobs: fetch+process (10min), safety net (4hr), deep recovery (daily 3AM).
- Runs `poll_commands_loop()` as a background async task (polls every 2 seconds).
- On startup: forces `monitoring_status = 'running'` in DB regardless of prior state.

### 3. Telegram Monitor (`monitor.py`)
- `TelegramMonitor` manages the Telethon client lifecycle.
- Reads session string from `telegram_auth` DB table.
- Primes entity cache with `get_dialogs(limit=500)` on connect (required for group entity resolution).
- Runs `client.run_until_disconnected()` to keep connection alive for the scheduler.

### 4. Historical Message Fetcher (`historical_message_fetcher.py`)
- `HistoricalMessageFetcher` — uses the live Telethon client passed from the monitor.
- Fetches messages group-by-group using `client.iter_messages()` with time-window filtering.
- Batch-inserts to `raw_messages` using `execute_batch()` for efficiency (100 messages/batch).
- `ON CONFLICT DO NOTHING` ensures idempotency across overlapping time windows.

### 5. LLM Processor (`llm_processor.py`)
- `LLMProcessor` — parses job postings from message text.
- **Failover chain**: primary model pool → fallback model pool → `_regex_fallback()`.
- Post-processing: merges fragmented job entries, backfills missing links/emails via regex, reconstructs raw `jd_text` via position-based text slicing.
- `process_job_data()` enriches raw LLM output into a database-ready dict.

### 6. Database Layer (`database.py` + `database_repositories.py`)
- `init_connection_pool()`: creates a `ThreadedConnectionPool` (min=2, max=20) with `RealDictCursor`.
- `init_database()`: creates all tables + indexes + seeds default config. Called once at startup via `initialize_db.py`.
- `Database` class: bundles all repositories under one object (`db.messages`, `db.jobs`, etc.).
- All repositories extend `BaseRepository` which provides `get_connection()` context manager.

### 7. Sheets Sync (`sheets_sync.py`)
- `GoogleSheetsSync`: connects to a single spreadsheet, manages 4 worksheets (email, non-email, email-exp, non-email-exp).
- `MultiSheetSync`: wrapper that broadcasts writes to primary + additional spreadsheets; reads only from primary.
- Idempotent sync: checks Column A (Job ID) before appending. Handles 429 quota errors with 60s sleep + retry.

### 8. Message Utils (`message_utils.py`)
- `extract_message_text()`: handles all Telethon message types (direct, forwarded, captions, polls, web previews).
- `should_process_message()`: filter — skips empty messages and bot commands.
- `log_execution` decorator: wraps sync/async functions with timing and error logging.

---

## Database Schema

### `raw_messages`
```sql
id SERIAL PRIMARY KEY
message_id BIGINT, group_id BIGINT  -- UNIQUE together
message_text TEXT
sender_id BIGINT, sent_at TIMESTAMP
status TEXT  -- unprocessed | processing | processed | failed
```

### `jobs` (unified table)
```sql
id SERIAL PRIMARY KEY
job_id TEXT UNIQUE  -- generated: job_{msg_id}_{timestamp}
source TEXT  -- telegram | manual
status TEXT  -- not_applied | pending | applied | interview | rejected | offer | archived
company_name, job_role, location, eligibility, salary, jd_text TEXT
raw_message_id INTEGER REFERENCES raw_messages(id)
email, phone, application_link, notes TEXT
is_hidden BOOLEAN  -- soft delete
is_duplicate BOOLEAN
duplicate_of_id INTEGER
job_relevance TEXT  -- relevant | irrelevant
synced_to_sheets BOOLEAN
metadata JSONB  -- {original_sheet, last_sheet, ...}
```

### `bot_config`
```sql
key TEXT PRIMARY KEY, value TEXT, updated_at TIMESTAMP
-- Default keys: monitoring_status, last_processed_message_id,
--               total_messages_processed, total_jobs_extracted, monitored_groups
```

### `commands_queue` (IPC)
```sql
id SERIAL PRIMARY KEY
command TEXT, status TEXT  -- pending | done | failed | cancelled
result_text TEXT, executed_by TEXT
created_at, executed_at TIMESTAMP
```

### `telegram_auth`
```sql
id SERIAL PRIMARY KEY  -- always id=1, single row
session_string TEXT  -- Telethon StringSession
login_status TEXT  -- not_authenticated | connected | session_expired | connection_failed
phone_number TEXT
```

---

## Data Flow

```
STEP 1 — FETCH (every 10 min)
  scheduled_fetch_and_process(monitor)
    → HistoricalMessageFetcher.fetch_historical_messages(hours_back=12)
      → client.iter_messages(group, limit=None) until time cutoff
      → _save_messages_batch() → INSERT INTO raw_messages ON CONFLICT DO NOTHING

STEP 2 — PROCESS (immediately after fetch)
  process_jobs()
    → db.messages.get_unprocessed_messages(limit=10)
    → mark status='processing'
    → LLMProcessor.parse_jobs(message_text)
      → OpenRouter API → JSON array
      → fallback chain if needed
    → for each parsed job:
        → check duplicate (company+role or email match)
        → llm_processor.process_job_data() → enriched dict
        → db.jobs.add_processed_job() → INSERT INTO jobs ON CONFLICT DO UPDATE
        → if application_method != 'email': also add to dashboard view
    → mark message status='processed'

STEP 3 — SYNC (after processing)
  sync_sheets_automatically()
    → db.jobs.get_unsynced_jobs()
    → MultiSheetSync.sync_job(job) → Google Sheets
    → db.jobs.mark_job_synced(job_id)

STEP 4 — COMMAND IPC
  Web: POST /api/command → db.commands.enqueue_command('/process')
  Worker: poll_commands_loop() (every 2s) → execute → mark done/failed
```

---

## Job Relevance Classification

The LLM is instructed to set `job_relevance` in the system prompt:
- `relevant` — fresher-friendly roles (0-2 years experience, 2024/2025/2026 batch)
- `irrelevant` — experienced roles (3+ years)

This classification drives Google Sheets routing (historically) and dashboard filtering.

## Sheet Routing Logic

| `sheet_name` value | Target worksheet |
|---|---|
| `email` | `email` sheet |
| `non-email` | `non-email` sheet |
| `email-exp` | redirected → `email` |
| `non-email-exp` | redirected → `non-email` |
| missing | inferred from `bool(job.email)` |

---

## Startup Sequence

```
Docker CMD: python initialize_db.py && honcho start

initialize_db.py:
  1. init_connection_pool(DATABASE_URL)
  2. init_database(pool)  ← CREATE TABLE IF NOT EXISTS, seed bot_config
  3. Seed monitored_groups from TELEGRAM_GROUP_USERNAMES env var if DB is empty

honcho start (Procfile):
  web:    gunicorn --bind 0.0.0.0:$PORT --workers 2 web_server:app
  worker: python main.py
    → check_bot_instance() (PID lock file)
    → force monitoring_status = 'running'
    → start APScheduler (3 jobs)
    → asyncio.create_task(poll_commands_loop())
    → asyncio.create_task(scheduled_fetch_and_process(monitor))  ← immediate first run
    → asyncio.sleep(3600) loop (keep-alive)
```
