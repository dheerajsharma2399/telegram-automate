# Deployment Guide

## Infrastructure

- **Host**: `152.67.7.111` (Oracle Cloud VPS, managed via Dokploy)
- **Domain**: `job.mooh.me`
- **Docker network**: `dokploy-network` (external, managed by Dokploy/Traefik)
- **TLS**: Traefik with Let's Encrypt (`letsencrypt` cert resolver)

---

## Architecture: Two Separate Docker Compose Stacks

The system is intentionally split into two independent stacks for security isolation.

### Stack 1 — Database (`database-compose.yaml`)

Runs separately, managed outside the app repo.

| Service | Description |
|---------|-------------|
| `postgres` | PostgreSQL 15, bound to Tailscale IP only (not public internet) |
| `adminer` | DB admin UI at `https://adminer.mooh.me`, Tailscale-only middleware |

- Data persisted at `/home/ubuntu/torrent/adminer-pgdb`
- Not accessible from the public internet — only reachable via Tailscale VPN or from containers on `dokploy-network`

### Stack 2 — Application (`docker-compose.yaml`)

| Service | Description |
|---------|-------------|
| `telegram-job-scraper` | Single container running both `web` + `worker` via `honcho start` |

- Connects to database over `dokploy-network` using hostname `postgres-db`
- Exposed publicly at `https://job.mooh.me` via Traefik reverse proxy
- Internal port: `9501`
- Memory limit: `512M`, CPU limit: `0.5`

---

## Startup Sequence (Container Boot)

Defined in `Dockerfile:41`:

```
CMD python initialize_db.py && honcho start
```

1. **`initialize_db.py`** runs first:
   - Calls `init_database(pool)` — creates all tables if not exists (idempotent DDL)
   - Seeds `monitored_groups` config from `TELEGRAM_GROUP_USERNAMES` env var if DB table is empty
   - On config validation failure (e.g. build environment without secrets), exits 0 gracefully

2. **`honcho start`** launches two processes defined in `Procfile`:
   - `web`: `gunicorn -c gunicorn_config.py web_server:app` — Flask dashboard on port 9501
   - `worker`: `python main.py` — asyncio worker (Telethon + APScheduler)

The two processes communicate **only via the `commands_queue` table in PostgreSQL**.

---

## Environment Variables

### Required

| Variable | Description |
|----------|-------------|
| `POSTGRES_PASSWORD` | PostgreSQL password (used to build `DATABASE_URL`) |
| `POSTGRES_DB` | Database name (default: `telegram_bot`) |
| `TELEGRAM_API_ID` | Telegram API ID from my.telegram.org |
| `TELEGRAM_API_HASH` | Telegram API hash |
| `TELEGRAM_PHONE` | Phone number for Telethon user-account auth |
| `TELEGRAM_GROUP_USERNAMES` | Comma-separated list of group IDs (e.g. `-100xxxx,-yyyy`) |
| `OPENROUTER_API_KEY` | OpenRouter API key for LLM parsing |
| `ADMIN_USER_ID` | Telegram user ID for admin notifications + shutdown token |

### Optional

| Variable | Description | Default |
|----------|-------------|---------|
| `GOOGLE_CREDENTIALS_JSON` | Full JSON content of GCP service account | — (Sheets disabled) |
| `SPREADSHEET_ID` | Primary Google Sheets ID | — (Sheets disabled) |
| `ADDITIONAL_SPREADSHEET_IDS` | Comma-separated extra sheet IDs | — |
| `AUTHORIZED_USER_IDS` | Comma-separated Telegram user IDs for auth | — |
| `OPENROUTER_MODEL` | Primary LLM model | `anthropic/claude-3.5-sonnet` |
| `OPENROUTER_FALLBACK_MODEL` | Fallback LLM model | `openai/gpt-4o-mini` |
| `BATCH_SIZE` | Messages to process per batch | `10` |
| `PROCESSING_INTERVAL_MINUTES` | Scheduler interval | `5` |
| `MAX_RETRIES` | LLM retry count | `3` |
| `PORT` | Web server port | `9501` |

> **WARNING (Bug #1)**: As of last analysis, `config.py:70-74` incorrectly raises `ValueError` if `GOOGLE_CREDENTIALS_JSON` or `SPREADSHEET_ID` are missing, despite them being optional. See `memory/known_bugs.md` Bug #1 for fix.

---

## Deployment Commands

### First deploy / fresh start

```bash
# 1. Start database stack (run once, on the VPS)
docker-compose -f database-compose.yaml up -d

# 2. Build and start application stack
docker-compose up -d --build
```

### Redeploy after code change

```bash
docker-compose up -d --build
```

Or use the helper script if present:

```bash
./deploy.sh
```

### View logs

```bash
docker-compose logs -f telegram-job-scraper
```

### Stop

```bash
docker-compose down
```

---

## Health Check

The container has a built-in Docker health check (defined in `Dockerfile:37-38`):

```
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:9501/health || exit 1
```

The `/health` endpoint is at `web_server.py:53`.

---

## Gunicorn Configuration (`gunicorn_config.py`)

- `workers = 1` — single worker to avoid DB connection pool contention
- `worker_class = "sync"` — standard synchronous workers
- `bind = "0.0.0.0:9501"` (or `PORT` env var)
- `timeout = 120`

---

## Lessons Learned / Past Fixes

1. **Telethon entity resolution**: Telethon fails to resolve group entities by ID unless they are in the dialog cache. Fix: call `get_dialogs(limit=500)` on startup (`monitor.py:125` — `_prime_dialog_cache`). Also match group IDs with both absolute value and `-100` prefix variants.

2. **Scheduled polling over persistent connection**: Switched from `client.run_until_disconnected()` to APScheduler tasks running every 10 minutes. More stable on VPS environments prone to silent TCP disconnects.

3. **IPC via DB**: The `poll_commands_loop` in `main.py:353` polls `commands_queue` every 2 seconds. Dashboard commands (`/process`, `/fetch`, `/stop`) are enqueued by the web process and consumed by the worker. This was restored after a regression removed it.

4. **`initialize_db.py` for env seeding**: Standardised startup to run `initialize_db.py` before `honcho start`. This auto-seeds `monitored_groups` from `TELEGRAM_GROUP_USERNAMES` on first boot so the worker knows which groups to monitor without manual DB setup.

5. **Graceful shutdown port mismatch (unfixed bug)**: `_signal_handler` in `web_server.py:758` falls back to port `8888` instead of `9501`. See `memory/known_bugs.md` Bug #4.
