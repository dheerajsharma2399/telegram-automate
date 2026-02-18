# Deployment Guide

## Infrastructure (Dokploy VPS)
- **Host**: 152.67.7.111
- **Domain**: `job.mooh.me`
- **Network**: `dokploy-network` (Docker network)

## Deployment Architecture
The system is split into two Docker Compose stacks for security and stability.

### 1. Database Stack (`database-compose.yaml`)
- **Services**:
    - `postgres`: PostgreSQL 15 (bound to Tailscale IP `***REMOVED***` ONLY).
    - `adminer`: Database UI (accessible at `https://adminer.mooh.me`, protected by Tailscale middleware).
- **Security**: Not accessible from public internet.
- **Persistence**: Data stored at `/home/ubuntu/torrent/adminer-pgdb`.

### 2. Application Stack (`docker-compose.yaml`)
- **Services**:
    - `telegram-job-scraper`: The main Python app.
- **Connectivity**: Connects to the database via internal Docker network hostname `postgres-db`.
- **Public Access**:
    - `https://job.mooh.me`: Dashboard (Public).

## Environment Configuration (`.env`)
Key variables required for deployment:
- `DATABASE_URL`: Internal Docker connection string (`postgresql://postgres:pass@postgres-db:5432/telegram_bot`).
- `TAILSCALE_IP`: For binding the database securely.
- `TELEGRAM_GROUP_USERNAMES`: Comma-separated list of group/channel IDs (e.g., `-100xxxx`, `-yyyy`).
- `GOOGLE_CREDENTIALS_JSON`: Full JSON content for service account.

## Deployment Commands
A helper script `deploy.sh` handles the sequence:

```bash
./deploy.sh
```

**Manual Steps:**
1.  **Database**: `docker-compose -f database-compose.yaml up -d`
2.  **App**: `docker-compose -f docker-compose.yaml up -d --build`

## Recent Fixes & Learnings
1.  **Telethon ID Resolution**:
    - Telethon often fails to resolve entities by ID if they aren't in the recent dialog cache.
    - **Fix**: Increased `get_dialogs(limit=500)` and implemented robust ID matching (checking absolute values and `-100` prefixes) in `monitor.py`.
2.  **Scheduled Polling**:
    - Switched from continuous `client.run_until_disconnected()` to a scheduled task running every 5 minutes.
    - This is more stable on VPS environments prone to silent disconnects.
3.  **Command Polling**:
    - Restored `poll_commands_loop` in `main.py` to ensure dashboard commands (`/process`) are executed by the worker.
4.  **Configuration Standardization**:
    - Standardized `.env` file with grouped sections.
    - Implemented `initialize_db.py` logic to auto-seed `monitored_groups` from environment variables if the database config is empty.
