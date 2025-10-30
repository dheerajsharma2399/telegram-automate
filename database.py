import sqlite3
import os
import psycopg2
from urllib.parse import urlparse
from datetime import datetime
from contextlib import contextmanager
from typing import List, Dict, Optional
import logging

class Database:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self.db_type = os.getenv('DATABASE_TYPE', 'sqlite')
        self.database_url = os.getenv('DATABASE_URL')
        self.logger = logging.getLogger(__name__)
        
        # Initialize database based on type
        self.init_database()
    
    def _parse_database_url(self):
        """Parse DATABASE_URL into connection parameters"""
        if not self.database_url:
            return None
        
        result = urlparse(self.database_url)
        return {
            'user': result.username,
            'password': result.password,
            'host': result.hostname,
            'port': result.port or 5432,
            'dbname': result.path[1:] if result.path else 'postgres'
        }
    
    def _get_connection_params(self):
        """Get database connection parameters"""
        if self.db_type == 'postgresql' and self.database_url:
            return self._parse_database_url()
        return None
    
    @contextmanager
    def get_connection(self):
        """Get database connection based on database type"""
        if self.db_type == 'postgresql' and self.database_url:
            params = self._get_connection_params()
            conn = psycopg2.connect(**params)
            conn.autocommit = False
            try:
                yield conn
                conn.commit()
            except Exception as e:
                conn.rollback()
                raise e
            finally:
                conn.close()
        else:
            # SQLite fallback
            conn = sqlite3.connect(self.db_path, timeout=10)
            conn.row_factory = sqlite3.Row
            try:
                yield conn
                conn.commit()
            except Exception as e:
                conn.rollback()
                raise e
            finally:
                conn.close()
    
    def init_database(self):
        """Initialize database with required tables"""
        if self.db_type == 'postgresql' and self.database_url:
            self._init_postgresql_tables()
        else:
            self._init_sqlite_tables()
    
    def _init_postgresql_tables(self):
        """Initialize PostgreSQL tables"""
        params = self._get_connection_params()
        conn = psycopg2.connect(**params)
        cursor = conn.cursor()
        
        try:
            # Raw messages table
            cursor.execute('''
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
            ''')
            
            # Processed jobs table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS processed_jobs (
                    id SERIAL PRIMARY KEY,
                    raw_message_id INTEGER REFERENCES raw_messages(id),
                    job_id TEXT UNIQUE NOT NULL,
                    first_name TEXT,
                    last_name TEXT,
                    email TEXT,
                    phone TEXT,
                    company_name TEXT,
                    job_role TEXT,
                    location TEXT,
                    eligibility TEXT,
                    application_method TEXT,
                    status TEXT DEFAULT 'pending',
                    updated_at TIMESTAMP,
                    jd_text TEXT,
                    email_subject TEXT,
                    email_body TEXT,
                    application_link TEXT,
                    recruiter_name TEXT,
                    synced_to_sheets BOOLEAN DEFAULT FALSE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Bot config table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS bot_config (
                    key TEXT PRIMARY KEY,
                    value TEXT,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Commands queue
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS commands_queue (
                    id SERIAL PRIMARY KEY,
                    command TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    executed_at TIMESTAMP NULL,
                    status TEXT DEFAULT 'pending',
                    result_text TEXT,
                    executed_by TEXT
                )
            ''')
            
            # Initialize default config
            cursor.execute('''
                INSERT INTO bot_config (key, value) VALUES
                ('monitoring_status', 'stopped'),
                ('last_processed_message_id', '0'),
                ('total_messages_processed', '0'),
                ('total_jobs_extracted', '0'),
                ('telegram_session', ''),
                ('telegram_login_status', 'not_authenticated')
                ON CONFLICT (key) DO NOTHING
            ''')
            
            # Create indexes for better performance
            indexes = [
                "CREATE INDEX IF NOT EXISTS idx_raw_messages_status ON raw_messages(status);",
                "CREATE INDEX IF NOT EXISTS idx_processed_jobs_email ON processed_jobs(email);",
                "CREATE INDEX IF NOT EXISTS idx_processed_jobs_created_at ON processed_jobs(created_at);",
                "CREATE INDEX IF NOT EXISTS idx_commands_queue_status ON commands_queue(status);"
            ]
            
            for index_sql in indexes:
                cursor.execute(index_sql)
            
            conn.commit()
            self.logger.info("PostgreSQL tables initialized successfully")
            
        except Exception as e:
            self.logger.error(f"Failed to initialize PostgreSQL tables: {e}")
            raise
        finally:
            cursor.close()
            conn.close()
    
    def _init_sqlite_tables(self):
        """Initialize SQLite tables"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # Raw messages table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS raw_messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    message_id INTEGER UNIQUE NOT NULL,
                    message_text TEXT NOT NULL,
                    sender_id INTEGER,
                    sent_at TIMESTAMP,
                    status TEXT DEFAULT 'unprocessed',
                    error_message TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Processed jobs table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS processed_jobs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    raw_message_id INTEGER,
                    job_id TEXT UNIQUE NOT NULL,
                    first_name TEXT,
                    last_name TEXT,
                    email TEXT,
                    phone TEXT,
                    company_name TEXT,
                    job_role TEXT,
                    location TEXT,
                    eligibility TEXT,
                    application_method TEXT,
                    status TEXT DEFAULT 'pending',
                    updated_at TIMESTAMP,
                    jd_text TEXT,
                    email_subject TEXT,
                    email_body TEXT,
                    application_link TEXT,
                    recruiter_name TEXT,
                    synced_to_sheets BOOLEAN DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (raw_message_id) REFERENCES raw_messages(id)
                )
            ''')
            
            # Bot config table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS bot_config (
                    key TEXT PRIMARY KEY,
                    value TEXT,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Commands queue
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS commands_queue (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    command TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    executed_at TIMESTAMP NULL,
                    status TEXT DEFAULT 'pending',
                    result_text TEXT,
                    executed_by TEXT
                )
            ''')
            
            # Initialize default config
            cursor.execute('''
                INSERT OR IGNORE INTO bot_config (key, value) VALUES
                ('monitoring_status', 'stopped'),
                ('last_processed_message_id', '0'),
                ('total_messages_processed', '0'),
                ('total_jobs_extracted', '0'),
                ('telegram_session', ''),
                ('telegram_login_status', 'not_authenticated')
            ''')

    def add_raw_message(self, message_id: int, message_text: str, 
                       sender_id: int, sent_at: datetime) -> int:
        """Add a new raw message"""
        with self.get_connection() as conn:
            if self.db_type == 'postgresql':
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT INTO raw_messages 
                    (message_id, message_text, sender_id, sent_at, status)
                    VALUES (%s, %s, %s, %s, %s)
                    ON CONFLICT (message_id) DO NOTHING
                    RETURNING id
                ''', (message_id, message_text, sender_id, sent_at, 'unprocessed'))
                result = cursor.fetchone()
                return result[0] if result else None
            else:
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT OR IGNORE INTO raw_messages 
                    (message_id, message_text, sender_id, sent_at, status)
                    VALUES (?, ?, ?, ?, 'unprocessed')
                ''', (message_id, message_text, sender_id, sent_at))
                return cursor.lastrowid
    
    def get_unprocessed_messages(self, limit: int = 10) -> List[Dict]:
        """Get unprocessed messages"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            if self.db_type == 'postgresql':
                cursor.execute('''
                    SELECT * FROM raw_messages 
                    WHERE status = %s
                    ORDER BY created_at ASC
                    LIMIT %s
                ''', ('unprocessed', limit))
            else:
                cursor.execute('''
                    SELECT * FROM raw_messages 
                    WHERE status = 'unprocessed'
                    ORDER BY created_at ASC
                    LIMIT ?
                ''', (limit,))
            return [dict(row) for row in cursor.fetchall()]

    def enqueue_command(self, command: str) -> int:
        """Enqueue a command (from web dashboard) to be executed by the bot."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            if self.db_type == 'postgresql':
                cursor.execute('''
                    INSERT INTO commands_queue (command, status) 
                    VALUES (%s, %s) 
                    RETURNING id
                ''', (command, 'pending'))
                return cursor.fetchone()[0]
            else:
                cursor.execute('''
                    INSERT INTO commands_queue (command, status) 
                    VALUES (?, 'pending')
                ''', (command,))
                return cursor.lastrowid

    def get_pending_commands(self, limit: int = 10) -> List[Dict]:
        """Retrieve pending commands for the bot to execute."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            if self.db_type == 'postgresql':
                cursor.execute('''
                    SELECT * FROM commands_queue
                    WHERE status = %s
                    ORDER BY created_at ASC
                    LIMIT %s
                ''', ('pending', limit))
            else:
                cursor.execute('''
                    SELECT * FROM commands_queue
                    WHERE status = 'pending'
                    ORDER BY created_at ASC
                    LIMIT ?
                ''', (limit,))
            return [dict(row) for row in cursor.fetchall()]

    def list_all_pending_commands(self) -> List[Dict]:
        """Return all pending commands (no limit)."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            if self.db_type == 'postgresql':
                cursor.execute('''
                    SELECT * FROM commands_queue
                    WHERE status = %s
                    ORDER BY created_at ASC
                ''', ('pending',))
            else:
                cursor.execute('''
                    SELECT * FROM commands_queue
                    WHERE status = 'pending'
                    ORDER BY created_at ASC
                ''')
            return [dict(row) for row in cursor.fetchall()]

    def cancel_command(self, command_id: int) -> bool:
        """Cancel (mark done/cancelled) a pending command by id."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            if self.db_type == 'postgresql':
                cursor.execute('SELECT id FROM commands_queue WHERE id = %s AND status = %s', (command_id, 'pending'))
            else:
                cursor.execute('SELECT id FROM commands_queue WHERE id = ? AND status = "pending"', (command_id,))
            
            if not cursor.fetchone():
                return False
            
            if self.db_type == 'postgresql':
                cursor.execute('''
                    UPDATE commands_queue SET status = %s, executed_at = CURRENT_TIMESTAMP
                    WHERE id = %s
                ''', ('cancelled', command_id))
            else:
                cursor.execute('''
                    UPDATE commands_queue SET status = 'cancelled', executed_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                ''', (command_id,))
            return True

    def get_config(self, key: str) -> Optional[str]:
        """Get config value"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            if self.db_type == 'postgresql':
                cursor.execute('SELECT value FROM bot_config WHERE key = %s', (key,))
            else:
                cursor.execute('SELECT value FROM bot_config WHERE key = ?', (key,))
            row = cursor.fetchone()
            return row[0] if row else None
    
    def set_config(self, key: str, value: str):
        """Set config value"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            if self.db_type == 'postgresql':
                cursor.execute('''
                    INSERT INTO bot_config (key, value, updated_at)
                    VALUES (%s, %s, CURRENT_TIMESTAMP)
                    ON CONFLICT (key) DO UPDATE SET
                    value = EXCLUDED.value,
                    updated_at = CURRENT_TIMESTAMP
                ''', (key, value))
            else:
                cursor.execute('''
                    INSERT OR REPLACE INTO bot_config (key, value, updated_at)
                    VALUES (?, ?, CURRENT_TIMESTAMP)
                ''', (key, value))

    def mark_command_executed(self, command_id: int):
        """Mark a command as executed."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            if self.db_type == 'postgresql':
                cursor.execute('''
                    UPDATE commands_queue SET status = %s, executed_at = CURRENT_TIMESTAMP
                    WHERE id = %s
                ''', ('done', command_id))
            else:
                cursor.execute('''
                    UPDATE commands_queue SET status = 'done', executed_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                ''', (command_id,))

    def update_command_result(self, command_id: int, status: str, result_text: str = None, executed_by: str = None):
        """Update a command's status, result text and who executed it."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            if self.db_type == 'postgresql':
                cursor.execute('''
                    UPDATE commands_queue
                    SET status = %s, executed_at = CURRENT_TIMESTAMP, result_text = %s, executed_by = %s
                    WHERE id = %s
                ''', (status, result_text, executed_by, command_id))
            else:
                cursor.execute('''
                    UPDATE commands_queue
                    SET status = ?, executed_at = CURRENT_TIMESTAMP, result_text = ?, executed_by = ?
                    WHERE id = ?
                ''', (status, result_text, executed_by, command_id))
    
    def update_message_status(self, message_id: int, status: str, error_message: str = None):
        """Update message processing status"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            if self.db_type == 'postgresql':
                cursor.execute('''
                    UPDATE raw_messages 
                    SET status = %s, error_message = %s
                    WHERE id = %s
                ''', (status, error_message, message_id))
            else:
                cursor.execute('''
                    UPDATE raw_messages 
                    SET status = ?, error_message = ?
                    WHERE id = ?
                ''', (status, error_message, message_id))
    
    def add_processed_job(self, job_data: Dict) -> int:
        """Add a processed job with ALL fields from LLM extraction"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            if self.db_type == 'postgresql':
                cursor.execute('''
                    INSERT INTO processed_jobs (
                        raw_message_id, job_id, first_name, last_name, email, phone,
                        company_name, job_role, location, eligibility,
                        application_method, jd_text, email_subject, email_body,
                        application_link, recruiter_name, status, updated_at
                    ) VALUES (
                        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
                    )
                    ON CONFLICT (job_id) DO NOTHING
                    RETURNING id
                ''', (
                    job_data.get('raw_message_id'),
                    job_data.get('job_id'),
                    job_data.get('first_name'),
                    job_data.get('last_name'),
                    job_data.get('email'),
                    job_data.get('phone'),
                    job_data.get('company_name'),
                    job_data.get('job_role'),
                    job_data.get('location'),
                    job_data.get('eligibility'),
                    job_data.get('application_method'),
                    job_data.get('jd_text'),
                    job_data.get('email_subject'),
                    job_data.get('email_body'),
                    job_data.get('application_link'),
                    job_data.get('recruiter_name'),
                    job_data.get('status'),
                    job_data.get('updated_at')
                ))
                result = cursor.fetchone()
                return result[0] if result else None
            else:
                cursor.execute('''
                    INSERT OR IGNORE INTO processed_jobs (
                        raw_message_id, job_id, first_name, last_name, email, phone,
                        company_name, job_role, location, eligibility,
                        application_method, jd_text, email_subject, email_body,
                        application_link, recruiter_name, status, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    job_data.get('raw_message_id'),
                    job_data.get('job_id'),
                    job_data.get('first_name'),
                    job_data.get('last_name'),
                    job_data.get('email'),
                    job_data.get('phone'),
                    job_data.get('company_name'),
                    job_data.get('job_role'),
                    job_data.get('location'),
                    job_data.get('eligibility'),
                    job_data.get('application_method'),
                    job_data.get('jd_text'),
                    job_data.get('email_subject'),
                    job_data.get('email_body'),
                    job_data.get('application_link'),
                    job_data.get('recruiter_name'),
                    job_data.get('status'),
                    job_data.get('updated_at')
                ))
                return cursor.lastrowid
    
    def mark_job_synced(self, job_id: str):
        """Mark job as synced to Google Sheets"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            if self.db_type == 'postgresql':
                cursor.execute('''
                    UPDATE processed_jobs 
                    SET synced_to_sheets = TRUE
                    WHERE job_id = %s
                ''', (job_id,))
            else:
                cursor.execute('''
                    UPDATE processed_jobs 
                    SET synced_to_sheets = 1
                    WHERE job_id = ?
                ''', (job_id,))

    def get_unprocessed_count(self) -> int:
        """Get count of unprocessed messages"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            if self.db_type == 'postgresql':
                cursor.execute("SELECT COUNT(*) FROM raw_messages WHERE status = %s", ('unprocessed',))
            else:
                cursor.execute("SELECT COUNT(*) FROM raw_messages WHERE status = 'unprocessed'")
            return cursor.fetchone()[0]

    def get_jobs_today_stats(self) -> Dict:
        """Get statistics of jobs processed today."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            if self.db_type == 'postgresql':
                cursor.execute("""
                    SELECT
                        COUNT(id) as total,
                        SUM(CASE WHEN application_method = 'email' THEN 1 ELSE 0 END) as with_email,
                        SUM(CASE WHEN application_method != 'email' THEN 1 ELSE 0 END) as without_email
                    FROM processed_jobs
                    WHERE DATE(created_at) = CURRENT_DATE
                """)
            else:
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
                "total": stats[0] or 0,
                "with_email": stats[1] or 0,
                "without_email": stats[2] or 0,
            }

    def get_processed_jobs_by_email_status(self, has_email: bool) -> List[Dict]:
        """Get processed jobs based on whether they have an email."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            if has_email:
                if self.db_type == 'postgresql':
                    cursor.execute('SELECT * FROM processed_jobs WHERE email IS NOT NULL AND email != %s ORDER BY created_at DESC', ('',))
                else:
                    cursor.execute('SELECT * FROM processed_jobs WHERE email IS NOT NULL AND email != "" ORDER BY created_at DESC')
            else:
                if self.db_type == 'postgresql':
                    cursor.execute('SELECT * FROM processed_jobs WHERE email IS NULL OR email = %s ORDER BY created_at DESC', ('',))
                else:
                    cursor.execute('SELECT * FROM processed_jobs WHERE email IS NULL OR email == "" ORDER BY created_at DESC')
            return [dict(row) for row in cursor.fetchall()]

    def get_unsynced_jobs(self) -> List[Dict]:
        """Get all processed jobs that have not been synced to Google Sheets."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            if self.db_type == 'postgresql':
                cursor.execute('SELECT * FROM processed_jobs WHERE synced_to_sheets = FALSE ORDER BY created_at ASC')
            else:
                cursor.execute('SELECT * FROM processed_jobs WHERE synced_to_sheets = 0 ORDER BY created_at ASC')
            return [dict(row) for row in cursor.fetchall()]

    def update_job_email_body(self, job_id: str, email_body: str):
        """Update the email_body for an existing processed job."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            if self.db_type == 'postgresql':
                cursor.execute('''
                    UPDATE processed_jobs
                    SET email_body = %s, updated_at = CURRENT_TIMESTAMP
                    WHERE job_id = %s
                ''', (email_body, job_id))
            else:
                cursor.execute('''
                    UPDATE processed_jobs
                    SET email_body = ?, updated_at = CURRENT_TIMESTAMP
                    WHERE job_id = ?
                ''', (email_body, job_id))

    def get_jobs_without_email_body(self) -> List[Dict]:
        """Get all processed jobs that do not have an email body."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            if self.db_type == 'postgresql':
                cursor.execute('SELECT * FROM processed_jobs WHERE email_body IS NULL OR email_body = %s ORDER BY created_at ASC', ('',))
            else:
                cursor.execute('SELECT * FROM processed_jobs WHERE email_body IS NULL OR email_body == "" ORDER BY created_at ASC')
            return [dict(row) for row in cursor.fetchall()]

    def get_telegram_session(self) -> Optional[str]:
        """Get stored Telegram session string"""
        return self.get_config('telegram_session')
    
    def set_telegram_session(self, session_string: str):
        """Store Telegram session string"""
        self.set_config('telegram_session', session_string)
    
    def get_telegram_login_status(self) -> str:
        """Get current Telegram login status"""
        return self.get_config('telegram_login_status') or 'not_authenticated'
    
    def set_telegram_login_status(self, status: str):
        """Set Telegram login status"""
        self.set_config('telegram_login_status', status)

    def get_email_jobs_needing_generation(self) -> List[Dict]:
        """Get email sheet jobs that need email body generation"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            if self.db_type == 'postgresql':
                cursor.execute('''
                    SELECT * FROM processed_jobs
                    WHERE email IS NOT NULL
                    AND email != %s
                    AND (email_body IS NULL OR email_body = %s)
                    ORDER BY created_at DESC
                ''', ('', ''))
            else:
                cursor.execute('''
                    SELECT * FROM processed_jobs
                    WHERE email IS NOT NULL
                    AND email != ''
                    AND (email_body IS NULL OR email_body = '')
                    ORDER BY created_at DESC
                ''')
            return [dict(row) for row in cursor.fetchall()]