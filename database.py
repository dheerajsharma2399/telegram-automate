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
    JobRepository,
    ConfigRepository,
    CommandRepository,
    DashboardRepository
)

# Global pool
_pool = None

def init_connection_pool(db_url: str):
    """Initializes the global connection pool."""
    global _pool
    if _pool is None:
        try:
            _pool = ThreadedConnectionPool(
                1, 20,
                db_url,
                cursor_factory=RealDictCursor
            )
            logging.info("PostgreSQL connection pool created for Supabase")
        except Exception as e:
            logging.error(f"Failed to setup PostgreSQL pool: {e}")
            raise
    return _pool

@contextmanager
def get_db_connection(pool):
    """Get PostgreSQL connection from pool"""
    connection = pool.getconn()
    try:
        yield connection
    except Exception:
        connection.rollback()
        raise
    finally:
        pool.putconn(connection)

def init_database(pool):
    """Initialize all required tables in Supabase"""
    with get_db_connection(pool) as conn:
        try:
            with conn.cursor() as cursor:
                # Raw messages table
                cursor.execute("""
            CREATE TABLE IF NOT EXISTS raw_messages (
                id SERIAL PRIMARY KEY,
                message_id BIGINT NOT NULL,
                message_text TEXT,
                sender_id INTEGER,
                group_id BIGINT,
                sent_at TIMESTAMP,
                status TEXT DEFAULT 'unprocessed',
                error_message TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            CREATE UNIQUE INDEX IF NOT EXISTS raw_messages_group_message_id_idx ON raw_messages (group_id, message_id);
                """)
                
                # Add group_id column if it doesn't exist for backward compatibility
                cursor.execute("""
            ALTER TABLE raw_messages
            ADD COLUMN IF NOT EXISTS group_id BIGINT;
                """)
                
                # Alter sender_id to BIGINT to support larger user/channel IDs
                cursor.execute("""
            ALTER TABLE raw_messages
            ALTER COLUMN sender_id TYPE BIGINT USING sender_id::BIGINT;
                """)
                
                # Processed jobs table
                cursor.execute("""
            CREATE TABLE IF NOT EXISTS processed_jobs (
                id SERIAL PRIMARY KEY,
                raw_message_id INTEGER,
                job_id TEXT UNIQUE NOT NULL,
                first_name TEXT,
                last_name TEXT,
                email TEXT,
                company_name TEXT,
                job_role TEXT,
                location TEXT,
                eligibility TEXT,
                application_link TEXT,
                application_method TEXT,
                status TEXT DEFAULT 'pending',
                updated_at TIMESTAMP,
                jd_text TEXT,
                email_subject TEXT,
                email_body TEXT,
                synced_to_sheets BOOLEAN DEFAULT FALSE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                is_hidden BOOLEAN DEFAULT FALSE,
                sheet_name TEXT,
                FOREIGN KEY (raw_message_id) REFERENCES raw_messages(id)
            )
                """)
                
                # Add is_hidden column to processed_jobs if it doesn't exist
                cursor.execute("""
            ALTER TABLE processed_jobs
            ADD COLUMN IF NOT EXISTS is_hidden BOOLEAN DEFAULT FALSE;
                """)
                
                # Add job_relevance column to processed_jobs if it doesn't exist
                cursor.execute("""
            ALTER TABLE processed_jobs
            ADD COLUMN IF NOT EXISTS job_relevance TEXT DEFAULT 'relevant';
                """)
                
                # Add sheet_name column to processed_jobs if it doesn't exist
                cursor.execute("""
            ALTER TABLE processed_jobs
            ADD COLUMN IF NOT EXISTS sheet_name TEXT;
                """)
                
                # Bot config table
                cursor.execute("""
            CREATE TABLE IF NOT EXISTS bot_config (
                key TEXT PRIMARY KEY,
                value TEXT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
                """)
                
                # Commands queue table
                cursor.execute("""
            CREATE TABLE IF NOT EXISTS commands_queue (
                id SERIAL PRIMARY KEY,
                command TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                executed_at TIMESTAMP NULL,
                status TEXT DEFAULT 'pending',
                result_text TEXT,
                executed_by TEXT
            )
                """)
                
                # Telegram authentication table (NEW - for session storage)
                cursor.execute("""
            CREATE TABLE IF NOT EXISTS telegram_auth (
                id SERIAL PRIMARY KEY,
                session_string TEXT,
                login_status TEXT DEFAULT 'not_authenticated',
                phone_number TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
                """)
                
                # Initialize default config
                cursor.execute("""
            INSERT INTO bot_config (key, value) VALUES
            ('monitoring_status', 'stopped'),
            ('last_processed_message_id', '0'),
            ('total_messages_processed', '0'),
            ('total_jobs_extracted', '0')
            ON CONFLICT (key) DO NOTHING
                """)
                
                # Initialize Telegram auth record
                cursor.execute("""
            INSERT INTO telegram_auth (id, login_status)
            VALUES (1, 'not_authenticated')
            ON CONFLICT (id) DO NOTHING
                """)
                
                # Create dashboard_jobs table for job management
                cursor.execute("""
            CREATE TABLE IF NOT EXISTS dashboard_jobs (
                id SERIAL PRIMARY KEY,
                source_job_id TEXT,
                original_sheet TEXT,
                company_name TEXT,
                job_role TEXT,
                location TEXT,
                application_link TEXT,
                phone TEXT,
                recruiter_name TEXT,
                job_relevance TEXT DEFAULT 'relevant',
                original_created_at TIMESTAMP,
                application_status TEXT DEFAULT 'not_applied',
                application_date TIMESTAMP,
                notes TEXT,
                is_duplicate BOOLEAN DEFAULT FALSE,
                duplicate_of_id INTEGER,
                conflict_status TEXT DEFAULT 'none',
                is_hidden BOOLEAN DEFAULT FALSE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
                """)
                
                # Add is_hidden column to dashboard_jobs if it doesn't exist for backward compatibility
                cursor.execute("""
            ALTER TABLE dashboard_jobs
            ADD COLUMN IF NOT EXISTS is_hidden BOOLEAN DEFAULT FALSE;
                """)

                # Add indexes to dashboard_jobs for faster filtering and lookups
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_dashboard_jobs_application_status ON dashboard_jobs (application_status);")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_dashboard_jobs_job_relevance ON dashboard_jobs (job_relevance);")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_dashboard_jobs_source_job_id ON dashboard_jobs (source_job_id);")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_dashboard_jobs_is_hidden ON dashboard_jobs (is_hidden);")
                
                # Create job_duplicate_groups table for duplicate tracking
                cursor.execute("""
            CREATE TABLE IF NOT EXISTS job_duplicate_groups (
                id SERIAL PRIMARY KEY,
                primary_job_id INTEGER,
                duplicate_jobs JSON,
                confidence_score FLOAT DEFAULT 0.8,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
                """)
            conn.commit()
            logging.info("All tables initialized in Supabase")
        except Exception as e:
            conn.rollback()
            logging.error(f"Database initialization failed: {e}")
            raise

class Database:
    def __init__(self, db_url: str):
        self.pool = init_connection_pool(db_url)
        init_database(self.pool)
        
        # Instantiate repositories
        self.auth = TelegramAuthRepository(self.pool)
        self.messages = MessageRepository(self.pool)
        self.jobs = JobRepository(self.pool)
        self.config = ConfigRepository(self.pool)
        self.commands = CommandRepository(self.pool)
        self.dashboard = DashboardRepository(self.pool)

    def get_connection(self):
        return get_db_connection(self.pool)