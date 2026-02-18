# Project Architecture

## Overview
This is a **Telegram Job Scraper & Automation System**. It monitors Telegram channels/groups for job postings, parses them using LLMs (OpenRouter), stores them in a PostgreSQL database, and syncs them to Google Sheets. It includes a web dashboard for management.

## Tech Stack
- **Backend**: Python 3.11 (Flask)
- **Telegram Client**: Telethon (Async)
- **Database**: PostgreSQL (via `psycopg2`)
- **LLM Integration**: OpenRouter API (Claude/GPT)
- **Task Scheduling**: APScheduler (AsyncIOScheduler)
- **Deployment**: Docker (Dokploy) on VPS

## Core Components

### 1. Web Server (`web_server.py`)
- Flask application serving the dashboard and API.
- Exposes API endpoints for the frontend (`/api/status`, `/api/jobs`, etc.).

### 2. Monitor (`monitor.py`)
- Connects to Telegram using `Telethon`.
- **Mode**: Scheduled Polling (switched from continuous listener for stability).
- Fetches messages from configured groups (`TELEGRAM_GROUP_USERNAMES`).
- Stores raw messages in `raw_messages` table.

### 3. Processor (`main.py`)
- **Scheduler**: Runs `scheduled_fetch_and_process` every 5 minutes.
- **Job Processing**:
    - Reads `unprocessed` messages from DB.
    - Sends text to LLM (`llm_processor.py`).
    - Parses JSON response.
    - Saves to `processed_jobs`.
    - Auto-imports non-email jobs to dashboard.
- **Command Poller**: Background loop that executes pending commands (`/process`, `/sync_sheets`) from the database queue.

### 4. Integration (`sheets_sync.py`)
- Syncs processed jobs to Google Sheets.
- Handles different sheets based on job type (Email vs Non-Email).

### 5. Database Layer (`database.py`, `database_repositories.py`)
- Manages PostgreSQL connection pool.
- Repositories pattern for cleaner data access (`JobRepository`, `MessageRepository`, etc.).
