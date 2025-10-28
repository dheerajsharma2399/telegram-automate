# Telegram Job Scraper Bot

A Telegram automation project that monitors job postings in Telegram groups, parses job details using LLMs (OpenRouter), stores structured data in a local SQLite database, and optionally syncs results to Google Sheets. It also includes a web dashboard for monitoring and control, and exposes a small REST API for programmatic control.

This README documents repository structure, requirements, configuration, running locally, deployment notes, and troubleshooting steps.

---

## Key features

- Monitor one or more Telegram groups for new messages (Telethon).
- Parse job postings into structured fields using an LLM with a deterministic prompt + regex fallback.
- Store raw messages and processed jobs in SQLite (`jobs.db`).
- Sync processed jobs to Google Sheets (optional) and export CSVs.
- Web dashboard (Flask) for status, logs, and issuing commands to the bot.
- Command queue so the dashboard can enqueue work for the bot to pick up.
- On-demand email-body generation (templated or via LLM) from dashboard, Telegram command, or sheet rows.

---

## Repository layout

- `main.py` - The Telegram bot and orchestrator (command handlers, scheduler, command poller).
- `monitor.py` - Telethon-based monitor that listens to configured Telegram groups and stores raw messages.
- `database.py` - SQLite wrapper with helper methods and safe schema migrations.
- `llm_processor.py` - LLM integration and lightweight templated email generator.
- `sheets_sync.py` - Google Sheets helper to sync jobs and generate email bodies from sheet rows.
- `web_server.py` - Flask dashboard and REST API endpoints used by the frontend.
- `templates/index.html` - Dashboard UI.
- `config.py` - Environment-driven config and LLM prompt.
- `requirements.txt` - Python dependencies.
- `Procfile`, `render.yaml` - Deployment helpers.
- `data/` - Local exports and other generated artifacts.

---

## Quickstart (development)

1. Create and activate a Python virtual env

```powershell
python -m venv venv
venv\Scripts\Activate.ps1   # PowerShell
```

2. Install dependencies

```powershell
pip install -r requirements.txt
```

3. Set environment variables

Create a `.env` file in the project root or set variables in your environment. Minimum recommended values for basic local runs:

- `TELEGRAM_API_ID` and `TELEGRAM_API_HASH` (from my.telegram.org)
- `TELEGRAM_PHONE` (phone for Telethon session login)
- `TELEGRAM_BOT_TOKEN` (Bot token from BotFather)
- `OPENROUTER_API_KEY` (optional but required for LLM parsing)
- `GOOGLE_CREDENTIALS_JSON` and `SPREADSHEET_ID` (optional, for Sheets sync)
- `AUTHORIZED_USER_IDS` (comma-separated user ids allowed to run bot commands)
- `ADMIN_USER_ID` (id used by dashboard fallback notifications)

Example `.env` (do NOT commit this to source control):

```text
TELEGRAM_API_ID=123456
TELEGRAM_API_HASH=abcdef1234567890
TELEGRAM_PHONE=+15551234567
TELEGRAM_BOT_TOKEN=123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11
AUTHORIZED_USER_IDS=123456789
ADMIN_USER_ID=123456789
OPENROUTER_API_KEY=sk-xxxxx
GOOGLE_CREDENTIALS_JSON={"type": "service_account", ...}
SPREADSHEET_ID=1AbCdEfGhIjKlMnOpQrStUvWxYz
```

4. Run components locally

- Run the web dashboard (Flask)

```powershell
python web_server.py
```

- Run the Telegram bot (this starts the bot and launches Telethon monitor and poller threads)

```powershell
python main.py
```

The dashboard is available at http://localhost:5000 by default.

---

## Major runtime behaviors

- `main.py` runs the Telegram Bot (python-telegram-bot) and starts background threads:
	- `TelegramMonitor` (Telethon) runs in its own asyncio loop and stores incoming messages in the DB.
	- A command poller thread periodically reads `commands_queue` rows and executes corresponding bot handlers (start/stop/process/generate_emails etc.).
	- A scheduler thread periodically runs `process_jobs()` which fetches unprocessed raw messages, calls the `LLMProcessor` to extract job objects, adds `processed_jobs` rows, and optionally syncs to Google Sheets.

- `sheets_sync.generate_email_bodies_from_sheet()` can read JD text from a sheet, call the local templated generator (`LLMProcessor.generate_email_body`) and write the generated email bodies back to the sheet. Optionally it updates the DB if the sheet contains `job_id` values.

- The web dashboard exposes endpoints under `/api/*` for status, logs, queue, pending commands, monitored groups management, and triggering generation. The dashboard uses `POST /api/generate_emails` with `{"run_now": true}` to perform synchronous generation on the server.

---

## Notable commands (Telegram)

- /start — start scheduled processing and set monitoring_status=running
- /stop — stop scheduled processing
- /status — show counts and current state
- /process — immediately run processing cycle (runs LLM parse & sheet sync)
- /generate_emails — generate email_body for unsynced jobs (accepts optional comma-separated job ids)
- /sync_sheets — manual sync of unsynced jobs to Google Sheets
- /export — create CSV exports and send as documents to the admin chat

The bot also has a simple `/stats` and diagnostic text/callback handlers to help debug.

---

## API endpoints (web dashboard)

- GET /api/status — JSON including monitoring_status, unprocessed_count and jobs_today stats
- GET /api/queue — unprocessed raw messages
- GET /api/pending_commands — list pending commands in DB
- POST /api/command {command} — enqueue a command for the bot
- POST /api/generate_emails {run_now:bool, job_ids: [..]} — enqueue or run server-side generate_emails
- POST /api/sheets/generate_email_bodies {sheet: 'email', limit: int} — server-side sheet-based generation
- GET /api/logs — returns last entries from `bot.log` and `monitor.log`
- GET/POST/DELETE /api/monitored_groups — manage configured monitored group usernames/ids stored in `bot_config`

---

## Google Sheets integration

- If `GOOGLE_CREDENTIALS_JSON` and `SPREADSHEET_ID` are configured the app will attempt to authorize and create/get two worksheets: `email` and `non-email`.
- Each worksheet header includes `Email Body` column; `sheets_sync.generate_email_bodies_from_sheet` writes generated text into that column for rows missing it.
- `sheets_sync.sync_job(job_data)` appends rows to the appropriate worksheet based on whether job_data has an `email` value.

---

## Configuration and environment variables

Key variables (see `config.py` for the full list and defaults):

- TELEGRAM_API_ID, TELEGRAM_API_HASH, TELEGRAM_PHONE, TELEGRAM_BOT_TOKEN
- TELEGRAM_GROUP_USERNAMES (comma-separated)
- AUTHORIZED_USER_IDS, ADMIN_USER_ID
- OPENROUTER_API_KEY, OPENROUTER_MODEL, OPENROUTER_FALLBACK_MODEL
- GOOGLE_CREDENTIALS_JSON, SPREADSHEET_ID
- DATABASE_PATH (default: jobs.db)
- PROCESSING_INTERVAL_MINUTES (default: 5)

Security note: Never commit secrets (API keys, service account JSON) into source control. Use host secret management (Render, GitHub Secrets, environment variables) for deployment.

---

## Troubleshooting and common issues

- "table processed_jobs has no column named email_body"
	- The code includes safe `ALTER TABLE` migration attempts. If you see this error, make sure the running process has write access to `jobs.db` and restart the bot; the migration will add the column.

- Telethon login prompt / code
	- The monitor uses Telethon and will ask for a login code the first time if the session file doesn't exist. If running in a headless environment, manually create the session on your machine and upload the session file.

- Google Sheets errors
	- Ensure `GOOGLE_CREDENTIALS_JSON` contains a valid Service Account JSON and the service account has access to the spreadsheet. Large updates may run into Sheets API quotas; the code writes row-by-row.

- LLM failures or rate-limits
	- Check `OPENROUTER_API_KEY` and consider using `OPENROUTER_FALLBACK_MODEL` for retries. The LLM client applies exponential backoff; still, heavy usage may trigger provider rate limits.

- Web dashboard shows stale logs
	- The dashboard reads log files directly. Ensure `bot.log` and `monitor.log` are being written by the running processes and that the web server has read permissions.

---

## Development notes and next steps

- Consider adding unit tests for `LLMProcessor._extract_json`, `database` helpers, and `sheets_sync` writers.
- Harden command poller with retries/backoff and better mapping from command text to handler functions.
- Replace the lightweight templated `generate_email_body` with a server-side LLM call under a configurable flag to improve output quality (requires rate-limiting & cost controls).
- Add CI checks to ensure database migrations remain idempotent and safe for existing databases.

---

## Deployment

This section contains step-by-step instructions to deploy the project to Render (recommended) and to run it locally in production-like mode.

### Deploying to Render

1. Prepare repository
	- Make sure the repository contains `render.yaml` (this project includes one) and all code is pushed to a Git provider (GitHub/GitLab).

2. Create services on Render
	- In Render dashboard, click "New" → "Web Service" and connect the repository.
	- Name: `job-dashboard` (or your chosen name)
	- Branch: `main` (or whichever branch you deploy)
	- Environment: Python
	- Build command: `pip install -r requirements.txt`
	- Start command: `python web_server.py`
	- Health check path: `/health` (optional but recommended)

	- Create a second service for the bot process:
	  - Click "New" → "Background Worker" (or another Web Service if you prefer) and connect same repo.
	  - Name: `telegram-job-bot` (or your chosen name)
	  - Build command: `pip install -r requirements.txt`
	  - Start command: `python main.py`

3. Add environment variables and secrets
	- In each service's Environment settings, add the required environment variables (do NOT commit secrets to the repo):
	  - `TELEGRAM_API_ID`, `TELEGRAM_API_HASH`, `TELEGRAM_PHONE`, `TELEGRAM_BOT_TOKEN`
	  - `AUTHORIZED_USER_IDS` (comma-separated), `ADMIN_USER_ID`
	  - `OPENROUTER_API_KEY`, `OPENROUTER_MODEL`, `OPENROUTER_FALLBACK_MODEL` (optional)
	  - `GOOGLE_CREDENTIALS_JSON` (the full JSON content as a secret string) and `SPREADSHEET_ID` (if you use Google Sheets)
	  - `DATABASE_PATH` (optional) — default is `jobs.db` (SQLite stored in service filesystem; for durability consider remote DB)

	Notes:
	- For `GOOGLE_CREDENTIALS_JSON`, Render allows you to set environment variables; paste the JSON content as the variable value. Prefer using a secret or Render's file/secret management if available.
	- If you prefer not to keep the credentials JSON in an env var, use a secure file store and adapt the code to read from a mounted file.

4. Deploy and verify
	- Deploy the services via the Render UI. Watch the build logs for any missing dependencies.
	- Check `http://<SERVICE>.onrender.com/health` and the service logs.
	- Check the bot logs and ensure Telethon session completes login (for first-time login, Telethon will attempt to sign in; for headless instances you may need to generate a session locally and upload the session file).

5. Post-deploy considerations
	- On Render, the ephemeral filesystem means SQLite `jobs.db` will live on the instance. If you want durability across deploys, use a hosted DB (Postgres) and refactor `database.py` accordingly.
	- Use Render's environment secret management for API keys and the Google credentials JSON.

### Local production-like run (recommended steps)

Option A — run services separately (simple)

1. Create a Python venv and install dependencies

```powershell
python -m venv venv
venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

2. Prepare environment variables

Create `.env` file in the project root with the required variables (example in Quickstart). `web_server.py` and `config.py` load environment variables using python-dotenv.

3. Start the web dashboard in one terminal

```powershell
python web_server.py
```

4. Start the Telegram bot in another terminal

```powershell
python main.py
```

5. First-time Telethon login

- The Telethon monitor will ask for a login code the first time the session is created. If you can't interactively complete the login on the server, create the `telegram_monitor.session` locally (by running the monitor locally once) and copy the session files into the same workspace on the server.

Option B — use Honcho/Procfile to run both processes (convenient for local dev)

1. Install `honcho`

```powershell
pip install honcho
```

2. Run both processes as defined in `Procfile`

```powershell
honcho start
```

This will run the processes declared in `Procfile` together (web server and bot) and stream logs for both.

Notes and production tips

- File permissions: ensure the running user has write access to `jobs.db`, `bot.log`, and `monitor.log`.
- Persisting data: SQLite works for single-instance deployments but is not highly available. For production, consider a hosted Postgres/MySQL and adjust `database.py`.
- Secrets: store API keys and service account JSON in your host's secret management (Render secrets, cloud secret manager, or environment variables). Do not store secrets in the repo.
- Telethon session: for headless deployments, generate the Telethon session locally and copy `telegram_monitor.session*` files to the server.


## License

This project uses the LICENSE file included in the repository.

---

If you'd like, I can also add a short CONTRIBUTING.md, a sample `.env.example`, and a small test script to validate the email generation path. Let me know which you'd prefer next.

