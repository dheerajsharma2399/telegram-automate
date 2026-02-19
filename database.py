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
                notes TEXT,
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
        self.jobs = UnifiedJobRepository(self.pool)
        self.config = ConfigRepository(self.pool)
        self.commands = CommandRepository(self.pool)

    def get_connection(self):
        return get_db_connection(self.pool)
