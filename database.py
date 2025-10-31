#!/usr/bin/env python3
"""
Pure PostgreSQL Database Wrapper for Telegram Job Scraper
Optimized for Supabase with Telegram session storage
"""
import os
import logging
from contextlib import contextmanager
from typing import List, Dict, Optional
import psycopg2
from psycopg2.extras import RealDictCursor
from psycopg2.pool import ThreadedConnectionPool

class Database:
    def __init__(self, db_url: str):
        self.db_url = db_url
        self.logger = logging.getLogger(__name__)
        self._setup_postgresql()
        self.init_database()
    
    def _setup_postgresql(self):
        """Setup PostgreSQL connection for Supabase"""
        try:
            self.pool = ThreadedConnectionPool(
                1, 20, 
                self.db_url,
                cursor_factory=RealDictCursor
            )
            self.logger.info("PostgreSQL connection pool created for Supabase")
        except Exception as e:
            self.logger.error(f"Failed to setup PostgreSQL pool: {e}")
            raise
    
    @contextmanager
    def get_connection(self):
        """Get PostgreSQL connection from pool"""
        conn = self.pool.getconn()
        conn.autocommit = True
        try:
            yield conn
        finally:
            self.pool.putconn(conn)
    
    def init_database(self):
        """Initialize all required tables in Supabase"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # Raw messages table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS raw_messages (
                    id SERIAL PRIMARY KEY,
                    message_id INTEGER UNIQUE NOT NULL,
                    message_text TEXT NOT NULL,
                    sender_id INTEGER,
                    sent_at TIMESTAMP,
                    status TEXT DEFAULT 'unprocessed',
                    error_message TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
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
                    FOREIGN KEY (raw_message_id) REFERENCES raw_messages(id)
                )
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
            
            self.logger.info("All tables initialized in Supabase")
    
    # === TELEGRAM SESSION MANAGEMENT (NEW METHODS) ===
    
    def get_telegram_session(self) -> Optional[str]:
        """Get stored Telegram session string from Supabase"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT session_string FROM telegram_auth WHERE id = 1")
            result = cursor.fetchone()
            return result['session_string'] if result and result['session_string'] else None
    
    def set_telegram_session(self, session_string: str):
        """Store Telegram session string in Supabase"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE telegram_auth 
                SET session_string = %s, updated_at = CURRENT_TIMESTAMP 
                WHERE id = 1
            """, (session_string,))
            self.logger.info("Telegram session updated in Supabase")
    
    def get_telegram_login_status(self) -> str:
        """Get Telegram login status from Supabase"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT login_status FROM telegram_auth WHERE id = 1")
            result = cursor.fetchone()
            return result['login_status'] if result else 'not_authenticated'
    
    def set_telegram_login_status(self, status: str):
        """Set Telegram login status in Supabase"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE telegram_auth 
                SET login_status = %s, updated_at = CURRENT_TIMESTAMP 
                WHERE id = 1
            """, (status,))
            self.logger.info(f"Telegram login status updated: {status}")
    
    # === MESSAGE MANAGEMENT ===
    
    def add_raw_message(self, message_id: int, message_text: str, 
                       sender_id: int, sent_at) -> int:
        """Add a new raw message"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO raw_messages 
                (message_id, message_text, sender_id, sent_at, status)
                VALUES (%s, %s, %s, %s, 'unprocessed')
                ON CONFLICT (message_id) DO NOTHING
                RETURNING id
            """, (message_id, message_text, sender_id, sent_at))
            result = cursor.fetchone()
            return result['id'] if result else None
    
    def get_unprocessed_messages(self, limit: int = 10) -> List[Dict]:
        """Get unprocessed messages"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM raw_messages 
                WHERE status = 'unprocessed'
                ORDER BY created_at ASC
                LIMIT %s
            """, (limit,))
            return [dict(row) for row in cursor.fetchall()]
    
    def update_message_status(self, message_id: int, status: str, 
                            error_message: str = None):
        """Update message processing status"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE raw_messages 
                SET status = %s, error_message = %s
                WHERE id = %s
            """, (status, error_message, message_id))
    
    def get_unprocessed_count(self) -> int:
        """Get count of unprocessed messages"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM raw_messages WHERE status = 'unprocessed'")
            result = cursor.fetchone()
            return result['count'] if result else 0
    
    def get_jobs_today_stats(self) -> Dict:
        """Get statistics of jobs processed today"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT
                    COUNT(id) as total,
                    SUM(CASE WHEN application_method = 'email' THEN 1 ELSE 0 END) as with_email,
                    SUM(CASE WHEN application_method != 'email' THEN 1 ELSE 0 END) as without_email
                FROM processed_jobs
                WHERE DATE(created_at) = DATE('now')
            """)
            stats = cursor.fetchone()
            return {
                "total": stats["total"] or 0,
                "with_email": stats["with_email"] or 0,
                "without_email": stats["without_email"] or 0,
            }
    
    # === CONFIG MANAGEMENT ===
    
    def get_config(self, key: str) -> Optional[str]:
        """Get config value"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT value FROM bot_config WHERE key = %s", (key,))
            result = cursor.fetchone()
            return result['value'] if result else None
    
    def set_config(self, key: str, value: str):
        """Set config value"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO bot_config (key, value, updated_at)
                VALUES (%s, %s, CURRENT_TIMESTAMP)
                ON CONFLICT (key) DO UPDATE SET 
                value = EXCLUDED.value, 
                updated_at = EXCLUDED.updated_at
            """, (key, value))
    
    # === COMMAND QUEUE MANAGEMENT ===
    
    def get_pending_commands(self, limit: int = 10) -> List[Dict]:
        """Retrieve pending commands"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM commands_queue
                WHERE status = 'pending'
                ORDER BY created_at ASC
                LIMIT %s
            """, (limit,))
            return [dict(row) for row in cursor.fetchall()]
    
    def list_all_pending_commands(self) -> List[Dict]:
        """Return all pending commands (no limit)."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM commands_queue
                WHERE status = 'pending'
                ORDER BY created_at ASC
            """)
            return [dict(row) for row in cursor.fetchall()]
    
    def enqueue_command(self, command: str) -> int:
        """Enqueue a command (from web dashboard) to be executed by the bot."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO commands_queue (command, status) VALUES (%s, 'pending')
                RETURNING id
            """, (command,))
            result = cursor.fetchone()
            return result['id'] if result else None
    
    def mark_command_executed(self, command_id: int):
        """Mark a command as executed."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE commands_queue SET status = 'done', executed_at = CURRENT_TIMESTAMP
                WHERE id = %s
            """, (command_id,))
    
    def update_command_result(self, command_id: int, status: str, result_text: str = None, executed_by: str = None):
        """Update a command's status, result text and who executed it."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE commands_queue
                SET status = %s, executed_at = CURRENT_TIMESTAMP, result_text = %s, executed_by = %s
                WHERE id = %s
            """, (status, result_text, executed_by, command_id))
    
    def cancel_command(self, command_id: int) -> bool:
        """Cancel (mark done/cancelled) a pending command by id."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT id FROM commands_queue WHERE id = %s AND status = "pending"', (command_id,))
            if not cursor.fetchone():
                return False
            cursor.execute("""
                UPDATE commands_queue SET status = 'cancelled', executed_at = CURRENT_TIMESTAMP
                WHERE id = %s
            """, (command_id,))
    
    # === PROCESSED JOBS MANAGEMENT ===
    
    def add_processed_job(self, job_data: Dict) -> int:
        """Add a processed job"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO processed_jobs (
                    raw_message_id, job_id, first_name, last_name, email,
                    company_name, job_role, location, eligibility, application_link,
                    application_method, jd_text, email_subject, email_body, status, updated_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
            """, (
                job_data.get('raw_message_id'),
                job_data.get('job_id'),
                job_data.get('first_name'),
                job_data.get('last_name'),
                job_data.get('email'),
                job_data.get('company_name'),
                job_data.get('job_role'),
                job_data.get('location'),
                job_data.get('eligibility'),
                job_data.get('application_link'),
                job_data.get('application_method'),
                job_data.get('jd_text'),
                job_data.get('email_subject'),
                job_data.get('email_body'),
                job_data.get('status'),
                job_data.get('updated_at')
            ))
            result = cursor.fetchone()
            return result['id'] if result else None
    
    def mark_job_synced(self, job_id: str):
        """Mark job as synced to Google Sheets"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE processed_jobs 
                SET synced_to_sheets = TRUE
                WHERE job_id = %s
            """, (job_id,))
    
    def get_processed_jobs_by_email_status(self, has_email: bool) -> List[Dict]:
        """Get processed jobs based on whether they have an email."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            if has_email:
                cursor.execute('SELECT * FROM processed_jobs WHERE email IS NOT NULL AND email != \'\' ORDER BY created_at DESC')
            else:
                cursor.execute('SELECT * FROM processed_jobs WHERE email IS NULL OR email = \'\' ORDER BY created_at DESC')
            return [dict(row) for row in cursor.fetchall()]
    
    def get_unsynced_jobs(self) -> List[Dict]:
        """Get all processed jobs that have not been synced to Google Sheets."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM processed_jobs WHERE synced_to_sheets = FALSE ORDER BY created_at ASC')
            return [dict(row) for row in cursor.fetchall()]
    
    def update_job_email_body(self, job_id: str, email_body: str):
        """Update the email_body for an existing processed job."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE processed_jobs
                SET email_body = %s, updated_at = CURRENT_TIMESTAMP
                WHERE job_id = %s
            """, (email_body, job_id))
    
    def get_processed_job_by_id(self, job_id: str) -> Optional[Dict]:
        """Get a single processed job by job_id for sheets sync"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM processed_jobs WHERE job_id = %s", (job_id,))
            result = cursor.fetchone()
            return dict(result) if result else None
    
    def get_email_jobs_needing_generation(self) -> List[Dict]:
        """Get email sheet jobs that need email body generation."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM processed_jobs
                WHERE email IS NOT NULL AND email != ''
                AND (email_body IS NULL OR email_body = '')
                ORDER BY created_at ASC
            """)
            return [dict(row) for row in cursor.fetchall()]
    
    def get_stats(self, days: int = 7) -> Dict:
        """Get job statistics for the last N days."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT
                    application_method, 
                    COUNT(id) as count
                FROM processed_jobs
                WHERE created_at >= CURRENT_DATE - INTERVAL '%s days'
                GROUP BY application_method
            """, (days,))
            by_method = {row['application_method']: row['count'] for row in cursor.fetchall()}

            cursor.execute("""
                SELECT
                    company_name, 
                    COUNT(id) as count
                FROM processed_jobs
                WHERE created_at >= CURRENT_DATE - INTERVAL '%s days'
                GROUP BY company_name
                ORDER BY count DESC
                LIMIT 5
            """, (days,))
            top_companies = {row['company_name']: row['count'] for row in cursor.fetchall()}

            return {
                "by_method": by_method,
                "top_companies": top_companies,
            }
            return True
