#!/usr/bin/env python3
"""
Database Layer Initializer for Telegram Job Scraper
Initializes the connection pool and repository instances.
"""
import logging
import psycopg2
from psycopg2.extras import RealDictCursor
from psycopg2.pool import ThreadedConnectionPool
from contextlib import contextmanager

from database_repositories import (
    BaseRepository,
    TelegramAuthRepository,
    MessageRepository,
    EventRepository,
    QueueRepository,
    UnifiedJobRepository,
    ConfigRepository,
    CommandRepository
)

# Global pool
_pool = None

def init_connection_pool(db_url: str):
    """Initializes the global connection pool."""
    global _pool
    if _pool is None:
        try:
            _pool = ThreadedConnectionPool(
                minconn=2,  # Keep minimum 2 connections warm
                maxconn=20,
                dsn=db_url,
                cursor_factory=RealDictCursor
            )
            logging.info("PostgreSQL connection pool created for Supabase")
        except Exception as e:
            logging.error(f"Failed to setup PostgreSQL pool: {e}")
            raise
    return _pool

@contextmanager
def get_db_connection(pool):
    """Get PostgreSQL connection from pool with timeout handling"""
    connection = None
    try:
        connection = pool.getconn()
        if connection is None:
            raise Exception("Connection pool exhausted - failed to get connection")
        yield connection
    except Exception as e:
        if connection:
            connection.rollback()
        logging.error(f"Database connection error: {e}")
        raise
    finally:
        if connection is not None:
            pool.putconn(connection)

def init_database(pool):
    """Initialize all required tables in Supabase"""
    with get_db_connection(pool) as conn:
        try:
            with conn.cursor() as cursor:
                # 1. Raw messages table
                cursor.execute("""
            CREATE TABLE IF NOT EXISTS raw_messages (
                id SERIAL PRIMARY KEY,
                message_id BIGINT NOT NULL,
                message_text TEXT,
                sender_id BIGINT,
                group_id BIGINT,
                sent_at TIMESTAMP,
                status TEXT DEFAULT 'unprocessed',
                error_message TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            CREATE UNIQUE INDEX IF NOT EXISTS raw_messages_group_message_id_idx ON raw_messages (group_id, message_id);
                """)

                cursor.execute("""
            CREATE TABLE IF NOT EXISTS raw_events (
                id SERIAL PRIMARY KEY,
                source TEXT NOT NULL CHECK (source IN ('telegram', 'linkedin', 'reddit', 'discord', 'manual')),
                source_id TEXT NOT NULL,
                content TEXT NOT NULL,
                metadata JSONB DEFAULT '{}'::jsonb,
                status TEXT DEFAULT 'unprocessed' CHECK (status IN ('unprocessed', 'processing', 'processed', 'failed', 'skipped')),
                error_message TEXT,
                created_at TIMESTAMP DEFAULT NOW(),
                UNIQUE (source, source_id)
            );
            CREATE INDEX IF NOT EXISTS idx_raw_events_status ON raw_events(status) WHERE status = 'unprocessed';
            CREATE INDEX IF NOT EXISTS idx_raw_events_source ON raw_events(source);
            CREATE INDEX IF NOT EXISTS idx_raw_events_metadata_gin ON raw_events USING gin(metadata);
                """)

                cursor.execute("""
            CREATE TABLE IF NOT EXISTS processing_queue (
                id SERIAL PRIMARY KEY,
                event_id INTEGER REFERENCES raw_events(id) ON DELETE CASCADE,
                priority INTEGER DEFAULT 0,
                status TEXT DEFAULT 'pending' CHECK (status IN ('pending', 'claimed', 'done', 'failed')),
                claimed_by TEXT,
                retry_count INTEGER DEFAULT 0,
                max_retries INTEGER DEFAULT 3,
                next_retry_at TIMESTAMP,
                error_message TEXT,
                created_at TIMESTAMP DEFAULT NOW(),
                claimed_at TIMESTAMP,
                completed_at TIMESTAMP
            );
            CREATE INDEX IF NOT EXISTS idx_pq_status_priority ON processing_queue(status, priority DESC) WHERE status = 'pending';
                """)

                # 2. Unified jobs table
                cursor.execute("""
            CREATE TABLE IF NOT EXISTS jobs (
                id SERIAL PRIMARY KEY,
                job_id TEXT UNIQUE NOT NULL,
                source TEXT NOT NULL CHECK (source IN ('telegram', 'manual')),
                status TEXT DEFAULT 'not_applied' CHECK (status IN ('not_applied', 'pending', 'applied', 'interview', 'rejected', 'offer', 'archived')),
                company_name TEXT,
                job_role TEXT,
                location TEXT,
                eligibility TEXT,
                salary TEXT,
                jd_text TEXT,
                raw_message_id INTEGER REFERENCES raw_messages(id),
                email TEXT,
                phone TEXT,
                application_link TEXT,
                recruiter_name TEXT,
                is_hidden BOOLEAN DEFAULT FALSE,
                is_duplicate BOOLEAN DEFAULT FALSE,
                duplicate_of_id INTEGER,
                job_relevance TEXT CHECK (job_relevance IN ('relevant', 'irrelevant')),
                synced_to_sheets BOOLEAN DEFAULT FALSE,
                metadata JSONB DEFAULT '{}'::jsonb,
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW()
            );
            CREATE INDEX IF NOT EXISTS idx_jobs_job_id ON jobs(job_id);
            CREATE INDEX IF NOT EXISTS idx_jobs_source ON jobs(source);
            CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);
            CREATE INDEX IF NOT EXISTS idx_jobs_company_name ON jobs(company_name);
            CREATE INDEX IF NOT EXISTS idx_jobs_job_relevance ON jobs(job_relevance);
            CREATE INDEX IF NOT EXISTS idx_jobs_created_at ON jobs(created_at);
            CREATE INDEX IF NOT EXISTS idx_jobs_metadata_gin ON jobs USING gin(metadata);
                """)

                cursor.execute("ALTER TABLE jobs ADD COLUMN IF NOT EXISTS confidence_score FLOAT")
                cursor.execute("ALTER TABLE jobs ADD COLUMN IF NOT EXISTS extraction_method TEXT")
                cursor.execute("ALTER TABLE jobs ADD COLUMN IF NOT EXISTS job_fingerprint TEXT")
                cursor.execute("ALTER TABLE jobs ADD COLUMN IF NOT EXISTS normalized_role TEXT")
                cursor.execute("ALTER TABLE jobs ADD COLUMN IF NOT EXISTS role_category TEXT")
                cursor.execute("ALTER TABLE jobs ADD COLUMN IF NOT EXISTS experience_hint TEXT")
                cursor.execute("ALTER TABLE jobs ADD COLUMN IF NOT EXISTS location_hint TEXT")
                cursor.execute("ALTER TABLE jobs ADD COLUMN IF NOT EXISTS contact_method TEXT")
                cursor.execute("ALTER TABLE jobs ADD COLUMN IF NOT EXISTS poster_name TEXT")
                cursor.execute("ALTER TABLE jobs ADD COLUMN IF NOT EXISTS poster_url TEXT")
                cursor.execute("ALTER TABLE jobs ADD COLUMN IF NOT EXISTS post_url TEXT")
                cursor.execute("ALTER TABLE jobs ADD COLUMN IF NOT EXISTS source_event_id INTEGER REFERENCES raw_events(id)")
                cursor.execute("""
            DO $$
            BEGIN
                IF EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_name = 'jobs' AND column_name = 'search_vector'
                      AND generation_expression IS NULL
                ) THEN
                    -- Drop dependent index first, then the non-generated column
                    EXECUTE 'DROP INDEX IF EXISTS idx_jobs_search';
                    EXECUTE 'ALTER TABLE jobs DROP COLUMN search_vector';
                END IF;
                -- Add as generated column (skip if already a generated column)
                IF NOT EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_name = 'jobs' AND column_name = 'search_vector'
                ) THEN
                    EXECUTE '
                        ALTER TABLE jobs
                        ADD COLUMN search_vector tsvector GENERATED ALWAYS AS (
                            setweight(to_tsvector(''english'', coalesce(company_name, '''')), ''A'') ||
                            setweight(to_tsvector(''english'', coalesce(job_role, '''')), ''A'') ||
                            setweight(to_tsvector(''english'', coalesce(normalized_role, '''')), ''B'') ||
                            setweight(to_tsvector(''english'', coalesce(role_category, '''')), ''B'') ||
                            setweight(to_tsvector(''english'', coalesce(jd_text, '''')), ''C'')
                        ) STORED
                    ';
                END IF;
            END $$;
                """)
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_jobs_search ON jobs USING gin(search_vector)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_jobs_fingerprint ON jobs(job_fingerprint)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_jobs_normalized_role ON jobs(normalized_role)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_jobs_confidence ON jobs(confidence_score)")

                # Add apply_runs table
                cursor.execute("""
            CREATE TABLE IF NOT EXISTS apply_runs (
                run_id          TEXT PRIMARY KEY,
                job_id          TEXT NOT NULL,
                profile_used    TEXT,
                status          TEXT DEFAULT 'running',
                email_subject   TEXT,
                email_body      TEXT,
                approved_subject TEXT,
                approved_body   TEXT,
                tokens_used     INTEGER DEFAULT 0,
                model_used      TEXT,
                error_message   TEXT,
                approved_at     TIMESTAMP,
                created_at      TIMESTAMP DEFAULT NOW()
            )
                """)
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_apply_runs_job_id ON apply_runs(job_id)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_apply_runs_status ON apply_runs(status)")

                # Add columns to jobs table
                cursor.execute("ALTER TABLE jobs ADD COLUMN IF NOT EXISTS apply_status TEXT DEFAULT 'pending'")
                cursor.execute("ALTER TABLE jobs ADD COLUMN IF NOT EXISTS apply_run_id TEXT")
                cursor.execute("ALTER TABLE jobs ADD COLUMN IF NOT EXISTS recruiter_name TEXT")

                # 3. Bot config table
                cursor.execute("""
            CREATE TABLE IF NOT EXISTS bot_config (
                key TEXT PRIMARY KEY,
                value TEXT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
                """)

                # 4. Commands queue table
                cursor.execute("""
            CREATE TABLE IF NOT EXISTS commands_queue (
                id SERIAL PRIMARY KEY,
                command TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                executed_at TIMESTAMP NULL,
                status TEXT DEFAULT 'pending',
                result_text TEXT,
                executed_by TEXT
            );
                """)

                # 5. Telegram authentication table
                cursor.execute("""
            CREATE TABLE IF NOT EXISTS telegram_auth (
                id SERIAL PRIMARY KEY,
                session_string TEXT,
                login_status TEXT DEFAULT 'not_authenticated',
                phone_number TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
                """)

                # 6. Job duplicate groups table (optional extended tracking)
                cursor.execute("""
            CREATE TABLE IF NOT EXISTS job_duplicate_groups (
                id SERIAL PRIMARY KEY,
                primary_job_id INTEGER,
                duplicate_jobs JSONB,
                confidence_score FLOAT DEFAULT 0.8,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
                """)

                # Initialize default config
                cursor.execute("""
            INSERT INTO bot_config (key, value) VALUES
            ('monitoring_status', 'running'),
            ('last_processed_message_id', '0'),
            ('total_messages_processed', '0'),
            ('total_jobs_extracted', '0')
            ON CONFLICT (key) DO NOTHING;
                """)

                # Initialize Telegram auth record
                cursor.execute("""
            INSERT INTO telegram_auth (id, login_status)
            VALUES (1, 'not_authenticated')
            ON CONFLICT (id) DO NOTHING;
                """)

            conn.commit()
            logging.info("All unified tables initialized in Supabase")
        except Exception as e:
            conn.rollback()
            logging.error(f"Database initialization failed: {e}")
            raise

class Database:
    def __init__(self, db_url: str):
        self.pool = init_connection_pool(db_url)
        # init_database(self.pool) # Removed to prevent deadlocks on concurrent startup

        # Instantiate repositories
        self.auth = TelegramAuthRepository(self.pool)
        self.messages = MessageRepository(self.pool)
        self.events = EventRepository(self.pool)
        self.queue = QueueRepository(self.pool)
        self.jobs = UnifiedJobRepository(self.pool)
        self.config = ConfigRepository(self.pool)
        self.commands = CommandRepository(self.pool)

    def get_connection(self):
        return get_db_connection(self.pool)
